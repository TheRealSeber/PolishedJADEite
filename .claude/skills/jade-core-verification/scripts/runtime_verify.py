#!/usr/bin/env python3
"""Runtime verification for JADE migration consumer playground.

Discovers consumer projects in consumer-playground/, injects jade.jar,
compiles, runs in Docker, asserts expected output markers.

Output: artifacts/07-runtime-verify.json
Exit: 0 = all pass, 2 = failures, 3 = env error
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------
PLAYGROUND_DIR = pathlib.Path("consumer-playground")
TIMEOUT_BUFFER = 15  # extra seconds beyond test-config timeout for docker pull etc.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
DOCKER_IMAGE_CONFIG_PATH = REPO_ROOT / "config" / "docker-images.json"


def iso_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def read_json(path: pathlib.Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: pathlib.Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    tmp.replace(path)


def version_key(raw: str) -> str:
    parts = raw.replace("_", ".").split(".")
    numeric = [int(x) for x in parts if x.isdigit()]
    if len(numeric) == 1 and numeric[0] >= 5:
        return f"1.{numeric[0]}"
    if len(numeric) >= 2 and numeric[0] == 1:
        return f"1.{numeric[1]}"
    return raw


def java_major(version: str) -> int:
    key = version_key(version)
    if key.startswith("1."):
        parts = key.split(".")
        if len(parts) > 1 and parts[1].isdigit():
            return int(parts[1])
    nums = [int(x) for x in key.replace("-", ".").split(".") if x.isdigit()]
    return nums[0] if nums else 0


def load_docker_image_registry(config_path: pathlib.Path) -> Dict[str, str]:
    payload = read_json(config_path)
    required = {"java-8", "java-11", "java-17"}
    missing = sorted(required - set(payload.keys()))
    if missing:
        raise ValueError(
            f"Docker image config missing required keys: {', '.join(missing)}"
        )
    return {str(k): str(v) for k, v in payload.items()}


def resolve_docker_image(target_version: str, registry: Dict[str, str]) -> str:
    major = java_major(target_version)
    if major >= 17:
        return registry["java-17"]
    if major >= 11:
        return registry["java-11"]
    return registry["java-8"]


def resolve_consumer_docker_image(
    consumer_cfg: Dict[str, Any], run_cfg: Dict[str, Any], registry: Dict[str, str]
) -> str:
    configured = str(consumer_cfg.get("docker_image", "")).strip()
    if configured == "${TARGET_DOCKER_IMAGE}" or not configured:
        return resolve_docker_image(str(run_cfg.get("target_version", "")), registry)
    return configured


def discover_consumers() -> List[Tuple[pathlib.Path, Dict[str, Any]]]:
    """Find all consumer projects with valid test-config.json."""
    consumers: List[Tuple[pathlib.Path, Dict[str, Any]]] = []
    if not PLAYGROUND_DIR.exists():
        return consumers
    for candidate in sorted(PLAYGROUND_DIR.iterdir()):
        if not candidate.is_dir():
            continue
        config_path = candidate / "test-config.json"
        if not config_path.exists():
            continue
        try:
            cfg = read_json(config_path)
            consumers.append((candidate, cfg))
        except (json.JSONDecodeError, OSError) as exc:
            print(
                f"WARNING: skipping {candidate.name}: invalid test-config.json ({exc})",
                file=sys.stderr,
            )
    return consumers


JADE_IMPORT_RE = re.compile(
    r"^\s*import\s+(?:static\s+)?jade\.([\w.]+?)\s*;", re.MULTILINE
)


def collect_consumer_jade_fqns(project_dir: pathlib.Path) -> List[str]:
    """Extract sorted JADE FQNs imported by a consumer project's Java sources."""
    fqns: set = set()
    for java_file in sorted(project_dir.glob("**/*.java")):
        try:
            text = java_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for match in JADE_IMPORT_RE.finditer(text):
            fqns.add("jade." + match.group(1))
    return sorted(fqns)


def map_jade_fqns_to_node_paths(
    fqns: List[str], graph_nodes: Dict[str, Any]
) -> List[str]:
    """Map consumer JADE FQNs to workspace-relative graph node paths."""
    paths: set = set()
    for fqn in fqns:
        for path, node in graph_nodes.items():
            if not isinstance(node, dict):
                continue
            pkg = node.get("package", "")
            cls = node.get("class_name", "")
            if f"{pkg}.{cls}" == fqn:
                paths.add(path)
                break
    return sorted(paths)


def build_consumer_map(
    consumers: List[Tuple[pathlib.Path, Dict[str, Any]]],
    graph_nodes: Optional[Dict[str, Any]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Build a deterministic consumer -> JADE-usage map.

    ``node_paths`` are populated only when a graph is available; otherwise
    they stay empty and the map remains advisory.
    """
    graph_nodes = graph_nodes if isinstance(graph_nodes, dict) else {}
    result: Dict[str, Dict[str, Any]] = {}
    for project_dir, cfg in consumers:
        name = str(cfg.get("name", project_dir.name))
        fqns = collect_consumer_jade_fqns(project_dir)
        result[name] = {
            "jade_fqns": fqns,
            "node_paths": map_jade_fqns_to_node_paths(fqns, graph_nodes),
        }
    return result


def load_graph_nodes(artifacts: pathlib.Path) -> Optional[Dict[str, Any]]:
    """Load the 03.5 graph's node map, or None when missing/malformed."""
    graph_path = artifacts / "03.5-knowledge-graph.json"
    if not graph_path.exists():
        return None
    try:
        data = read_json(graph_path)
    except (json.JSONDecodeError, OSError):
        return None
    nodes = data.get("nodes")
    return nodes if isinstance(nodes, dict) else None


def load_impacted_nodes(artifacts: pathlib.Path) -> List[str]:
    """Changed/removed nodes from a 07-graph-diff.json, or [] when absent."""
    diff_path = artifacts / "07-graph-diff.json"
    if not diff_path.exists():
        return []
    try:
        diff = read_json(diff_path)
    except (json.JSONDecodeError, OSError):
        return []
    nodes = set(diff.get("changed_nodes", [])) | set(diff.get("removed_nodes", []))
    return sorted(n for n in nodes if isinstance(n, str))


def order_consumers_by_impact(
    consumers: List[Tuple[pathlib.Path, Dict[str, Any]]],
    consumer_map: Dict[str, Dict[str, Any]],
    impacted_nodes: List[str],
    graph_nodes: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Tuple[pathlib.Path, Dict[str, Any]]], Dict[str, Any]]:
    """Order impacted consumers first; every consumer remains in the run.

    Advisory only: if no impacted nodes or no usable graph, the original
    order is preserved and coverage metadata is empty.
    """
    if not impacted_nodes or not isinstance(graph_nodes, dict):
        return consumers, {}
    impacted = set(impacted_nodes)
    impacted_consumers = []
    for name, meta in consumer_map.items():
        if set(meta.get("node_paths", [])) & impacted:
            impacted_consumers.append(name)
    impacted_set = set(impacted_consumers)
    ordered = [c for c in consumers if str(c[1].get("name", c[0].name)) in impacted_set] + [
        c for c in consumers if str(c[1].get("name", c[0].name)) not in impacted_set
    ]
    return ordered, {"impacted_consumers": sorted(impacted_consumers)}


def verify_deps(workspace: pathlib.Path, cfg: Dict[str, Any]) -> List[str]:
    """Check that all classpath_deps exist. Returns list of missing paths."""
    missing: List[str] = []
    for dep in cfg.get("classpath_deps", []):
        full = workspace / dep
        if not full.exists():
            missing.append(dep)
    return missing


def compile_consumer(
    project_dir: pathlib.Path,
    workspace: pathlib.Path,
    cfg: Dict[str, Any],
    build_dir: pathlib.Path,
) -> Tuple[bool, str]:
    """Compile consumer .java files against workspace jars. Returns (ok, output)."""
    java_files = sorted(project_dir.glob("**/*.java"))
    if not java_files:
        return False, "No .java files found in project directory"

    # Build classpath from workspace deps
    cp_parts: List[str] = []
    for dep in cfg.get("classpath_deps", []):
        full = workspace / dep
        cp_parts.append(str(full.resolve()))
    classpath = os.pathsep.join(cp_parts)

    javac = shutil.which("javac")
    if not javac:
        javac = "javac"  # hope it's on PATH

    source_level = cfg.get("source_level")
    cmd = [javac]
    if source_level:
        cmd.extend(["-source", str(source_level), "-target", str(source_level)])
    cmd.extend(["-cp", classpath, "-d", str(build_dir)])
    cmd.extend(str(f.resolve()) for f in java_files)

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "JAVA_TOOL_OPTIONS": ""},
        )
        output = (proc.stdout + proc.stderr).strip()
        return proc.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "Compilation timed out after 120s"
    except OSError as exc:
        return False, f"Failed to run javac: {exc}"


def run_in_docker(
    workspace: pathlib.Path,
    build_dir: pathlib.Path,
    cfg: Dict[str, Any],
) -> Tuple[int, str, str]:
    """Run consumer in Docker. Returns (exit_code, stdout, stderr)."""
    docker_image = cfg["docker_image"]
    main_class = cfg["main_class"]
    timeout = cfg.get("timeout_seconds", 60) + TIMEOUT_BUFFER

    # Build container classpath
    cp_parts: List[str] = ["/playground"]
    for dep in cfg.get("classpath_deps", []):
        cp_parts.append(f"/ws/{dep}")
    classpath = ":".join(cp_parts)

    # Normalize paths for Docker on Windows: drive letter + forward slashes
    def _docker_path(p: pathlib.Path) -> str:
        raw = str(p.resolve())
        # e.g. C:\Users\... -> /c/Users/... or keep as C:/Users/...
        if ":" in raw and raw[1] == ":":
            drive = raw[0].lower()
            rest = raw[2:].replace("\\", "/")
            return f"{drive}:{rest}"
        return raw.replace("\\", "/")

    ws_docker = _docker_path(workspace)
    bd_docker = _docker_path(build_dir)

    cmd = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{ws_docker}:/ws",
        "-v",
        f"{bd_docker}:/playground",
        "-w",
        "/playground",
        docker_image,
        "java",
        "-cp",
        classpath,
        main_class,
    ]
    cmd.extend(cfg.get("boot_args", []))

    print(
        f"  $ docker run ... {docker_image} java -cp ... {main_class} {' '.join(cfg.get('boot_args', []))}"
    )
    print(f"     ws={ws_docker} bd={bd_docker}")

    # Use temp files for stdout/stderr so we can read output even on timeout
    tmp_out = tempfile.NamedTemporaryFile(
        mode="w", delete=False, suffix=".out", prefix="jade-rt-"
    )
    tmp_err = tempfile.NamedTemporaryFile(
        mode="w", delete=False, suffix=".err", prefix="jade-rt-"
    )
    tmp_out_path = pathlib.Path(tmp_out.name)
    tmp_err_path = pathlib.Path(tmp_err.name)
    tmp_out.close()
    tmp_err.close()

    try:
        with open(tmp_out_path, "w") as fout, open(tmp_err_path, "w") as ferr:
            proc = subprocess.run(
                cmd,
                stdout=fout,
                stderr=ferr,
                timeout=timeout,
                env={**os.environ, "MSYS_NO_PATHCONV": "1"},
            )
        stdout_text = tmp_out_path.read_text(errors="replace")
        stderr_text = tmp_err_path.read_text(errors="replace")
        return proc.returncode, stdout_text, stderr_text
    except subprocess.TimeoutExpired:
        stdout_text = tmp_out_path.read_text(errors="replace")
        stderr_text = tmp_err_path.read_text(errors="replace")
        return -1, stdout_text, stderr_text + f"\nContainer timed out after {timeout}s"
    except OSError as exc:
        return -2, "", f"Failed to run docker: {exc}"
    finally:
        tmp_out_path.unlink(missing_ok=True)
        tmp_err_path.unlink(missing_ok=True)


def test_consumer(
    project_dir: pathlib.Path,
    workspace: pathlib.Path,
    cfg: Dict[str, Any],
) -> Dict[str, Any]:
    """Run one consumer test. Returns result dict."""
    name = cfg["name"]
    result: Dict[str, Any] = {
        "project": name,
        "status": "PENDING",
        "duration_seconds": 0.0,
        "jade_booted": False,
        "stdout_snippet": "",
        "error": None,
    }

    t0 = time.monotonic()

    print(f"\n=== Consumer: {name} ===")

    # Check deps
    missing = verify_deps(workspace, cfg)
    if missing:
        result["status"] = "FAIL"
        result["error"] = f"Missing dependencies: {', '.join(missing)}"
        result["duration_seconds"] = round(time.monotonic() - t0, 1)
        return result

    # Compile
    with tempfile.TemporaryDirectory(prefix=f"jade-rt-{name}-") as tmp:
        build_dir = pathlib.Path(tmp)
        ok, output = compile_consumer(project_dir, workspace, cfg, build_dir)
        if not ok:
            result["status"] = "FAIL"
            result["error"] = "Compilation failed"
            result["stdout_snippet"] = output[:2000]
            result["duration_seconds"] = round(time.monotonic() - t0, 1)
            return result

        # Run in Docker
        rc, stdout, stderr = run_in_docker(workspace, build_dir, cfg)
        combined = stdout + "\n" + stderr

        result["duration_seconds"] = round(time.monotonic() - t0, 1)
        result["stdout_snippet"] = (
            combined[-5000:] if len(combined) > 5000 else combined
        )

        # Timeout is always a failure
        if rc == -1:
            result["status"] = "FAIL"
            result["error"] = "Container timed out"
            return result

        # Check for failure patterns FIRST (reverse assertion)
        failure_patterns = [
            "NullPointerException",
            "ArrayIndexOutOfBoundsException",
            "Exception",
            "SEVERE:",
        ]
        found_failures = [p for p in failure_patterns if p in combined]
        if found_failures:
            result["status"] = "FAIL"
            result["error"] = f"Failure patterns detected: {found_failures}"
            return result

        # Check expected markers
        markers = cfg.get("expected_stdout_markers", [])
        missing_markers = [m for m in markers if m not in combined]

        if missing_markers:
            result["status"] = "FAIL"
            result["error"] = f"Missing expected markers: {missing_markers}"
        else:
            result["status"] = "PASS"
            result["jade_booted"] = "is ready" in combined

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="JADE Runtime Verification")
    parser.add_argument("--workspace", required=True, help="Path to migrated workspace")
    parser.add_argument(
        "--artifacts", required=True, help="Path to artifacts directory"
    )
    parser.add_argument("--config", required=True, help="Path to 00-run-config.json")
    args = parser.parse_args()

    workspace = pathlib.Path(args.workspace)
    artifacts = pathlib.Path(args.artifacts)

    # Read run config
    try:
        run_cfg = read_json(pathlib.Path(args.config))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: cannot read config: {exc}", file=sys.stderr)
        return 3

    run_id = run_cfg.get("run_id", "unknown")

    try:
        registry = load_docker_image_registry(DOCKER_IMAGE_CONFIG_PATH)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: invalid docker image config: {exc}", file=sys.stderr)
        return 3

    # Verify env
    if shutil.which("docker") is None:
        print("ERROR: docker not found on PATH", file=sys.stderr)
        return 3
    # Check daemon is reachable
    try:
        subprocess.run(["docker", "info"], capture_output=True, timeout=10, check=False)
    except (subprocess.TimeoutExpired, OSError):
        print("ERROR: docker daemon not running or unreachable", file=sys.stderr)
        return 3

    # Discover consumers
    consumers = discover_consumers()
    if not consumers:
        result = {
            "run_id": run_id,
            "generated_at": iso_now(),
            "overall_pass": True,
            "total_consumers": 0,
            "passed": 0,
            "failed": 0,
            "results": [],
            "consumer_coverage": {},
        }
        write_json(artifacts / "07-runtime-verify.json", result)
        print("No consumer projects found — pass")
        return 0

    # Advisory graph-backed consumer map + impacted-first ordering.
    # Every consumer still runs; the final gate stays overall_pass.
    graph_nodes = load_graph_nodes(artifacts)
    consumer_map = build_consumer_map(consumers, graph_nodes)
    write_json(artifacts / "consumer-map.json", consumer_map)
    impacted_nodes = load_impacted_nodes(artifacts)
    consumers, consumer_coverage = order_consumers_by_impact(
        consumers, consumer_map, impacted_nodes, graph_nodes
    )

    # Test each consumer
    results: List[Dict[str, Any]] = []
    for project_dir, cfg in consumers:
        cfg = dict(cfg)
        cfg["docker_image"] = resolve_consumer_docker_image(cfg, run_cfg, registry)
        result = test_consumer(project_dir, workspace, cfg)
        results.append(result)
        status_icon = "PASS" if result["status"] == "PASS" else "FAIL"
        print(f"  [{status_icon}] {result['project']} ({result['duration_seconds']}s)")

    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")

    output = {
        "run_id": run_id,
        "generated_at": iso_now(),
        "overall_pass": failed == 0,
        "total_consumers": len(results),
        "passed": passed,
        "failed": failed,
        "consumer_coverage": consumer_coverage,
        "results": results,
    }
    write_json(artifacts / "07-runtime-verify.json", output)

    if failed > 0:
        print(f"\n{failed} consumer(s) FAILED", file=sys.stderr)
        return 2

    print(f"\nAll {passed} consumer(s) PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

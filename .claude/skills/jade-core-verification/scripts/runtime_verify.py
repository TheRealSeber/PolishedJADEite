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
    if major > 17:
        raise ValueError(
            f"Target Java {major} is unsupported; supported Docker images stop at Java 17"
        )
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


def _safe_relative_path(
    root: pathlib.Path, raw_path: Any, field: str, *, require_exists: bool = False
) -> Optional[str]:
    """Return an error when a configured path escapes its owning root."""
    if not isinstance(raw_path, str) or not raw_path.strip():
        return f"{field} must be a non-empty relative path"

    candidate = pathlib.Path(raw_path)
    if candidate.is_absolute():
        return f"{field} must be relative to {root}"

    root_resolved = root.resolve()
    candidate_resolved = (root_resolved / candidate).resolve()
    try:
        candidate_resolved.relative_to(root_resolved)
    except ValueError:
        return f"{field} must remain inside the consumer/workspace root ({root})"

    if require_exists and not candidate_resolved.is_dir():
        return f"{field} does not name an existing directory: {raw_path}"
    return None


def validate_consumer_config(
    project_dir: pathlib.Path,
    cfg: Dict[str, Any],
    workspace: pathlib.Path,
) -> Tuple[Dict[str, Any], List[str]]:
    """Normalize and validate consumer build configuration without building it."""
    normalized = dict(cfg)
    errors: List[str] = []

    if "maven_executable" in normalized:
        errors.append(
            "maven_executable is not supported; the verifier selects Maven"
        )
        normalized.pop("maven_executable", None)

    if normalized.get("_config_error"):
        errors.append(str(normalized["_config_error"]))

    build_mode = normalized.get("build_mode", "javac")
    if not isinstance(build_mode, str) or build_mode not in {"javac", "maven"}:
        errors.append("build_mode must be either 'javac' or 'maven'")
    else:
        normalized["build_mode"] = build_mode

    if build_mode == "maven":
        project_root = normalized.get("maven_project_root")
        if project_root is None:
            errors.append("maven_project_root is required when build_mode is 'maven'")
        else:
            error = _safe_relative_path(
                project_dir, project_root, "maven_project_root", require_exists=True
            )
            if error:
                errors.append(error)

        if "jade_artifact" in normalized:
            error = _safe_relative_path(
                workspace, normalized["jade_artifact"], "jade_artifact"
            )
            if error:
                errors.append(error)

        if "maven_runtime_lib_dir" in normalized:
            error = _safe_relative_path(
                project_dir,
                normalized["maven_runtime_lib_dir"],
                "maven_runtime_lib_dir",
            )
            if error:
                errors.append(error)

    classpath_deps = normalized.get("classpath_deps", [])
    if not isinstance(classpath_deps, list):
        errors.append("classpath_deps must be a list of relative paths")
        classpath_deps = []

    for dependency in classpath_deps:
        error = _safe_relative_path(workspace, dependency, "classpath_deps")
        if error:
            errors.append(error)

    if "artifact_output_dir" in normalized:
        error = _safe_relative_path(
            project_dir, normalized["artifact_output_dir"], "artifact_output_dir"
        )
        if error:
            errors.append(error)

    return normalized, errors


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
            if not isinstance(cfg, dict):
                cfg = {
                    "name": candidate.name,
                    "_config_error": (
                        "invalid test-config.json: top-level value must be an object"
                    ),
                }
            consumers.append((candidate, cfg))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
            print(
                f"WARNING: invalid {candidate.name}/test-config.json ({exc})",
                file=sys.stderr,
            )
            consumers.append(
                (
                    candidate,
                    {
                        "name": candidate.name,
                        "_config_error": f"invalid test-config.json: {exc}",
                    },
                )
            )
    return consumers


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


def _maven_command() -> List[str]:
    maven = shutil.which("mvn") or "mvn"
    return [maven]


def build_maven_consumer(
    project_dir: pathlib.Path,
    workspace: pathlib.Path,
    cfg: Dict[str, Any],
    build_dir: pathlib.Path,
) -> Tuple[bool, str]:
    """Build a Maven consumer and stage its classes and runtime jars."""
    project_root = project_dir / cfg["maven_project_root"]
    jade_artifact = cfg.get("jade_artifact")
    if jade_artifact is None:
        deps = cfg.get("classpath_deps", [])
        jade_artifact = deps[0] if deps else None
    path_error = _safe_relative_path(workspace, jade_artifact, "jade_artifact")
    if path_error:
        return False, path_error
    jade_path = (workspace / jade_artifact).resolve()
    if not jade_path.is_file():
        return False, f"jade_artifact does not exist: {jade_artifact}"

    build_dir.mkdir(parents=True, exist_ok=True)
    runtime_lib_dir = cfg.get("maven_runtime_lib_dir", "lib")
    path_error = _safe_relative_path(
        build_dir, runtime_lib_dir, "maven_runtime_lib_dir"
    )
    if path_error:
        return False, path_error

    maven_cmd = _maven_command()
    with tempfile.TemporaryDirectory(prefix="jade-maven-repo-") as repo:
        isolated_project = pathlib.Path(repo) / "consumer"
        shutil.copytree(
            project_root,
            isolated_project,
            ignore=shutil.ignore_patterns("target"),
        )
        common_args = ["-B", "-ntp", f"-Dmaven.repo.local={repo}"]
        install_cmd = maven_cmd + common_args + [
            "org.apache.maven.plugins:maven-install-plugin:3.1.2:install-file",
            f"-Dfile={jade_path}",
            "-DgroupId=com.tilab.jade",
            "-DartifactId=jade",
            "-Dversion=4.6",
            "-Dpackaging=jar",
            "-DgeneratePom=true",
        ]
        try:
            install_proc = subprocess.run(
                install_cmd,
                cwd=isolated_project,
                capture_output=True,
                text=True,
                timeout=300,
                env={**os.environ, "JAVA_TOOL_OPTIONS": ""},
            )
        except subprocess.TimeoutExpired:
            return False, "Maven JADE artifact install timed out after 300s"
        except OSError as exc:
            return False, f"Failed to run Maven JADE artifact install: {exc}"

        install_output = (install_proc.stdout + install_proc.stderr).strip()
        if install_proc.returncode != 0:
            return False, (
                f"Maven JADE artifact install failed (exit {install_proc.returncode}):\n"
                f"{install_output}"
            )

        cmd = maven_cmd + common_args + [
            "package",
            "dependency:copy-dependencies",
            "-DincludeScope=runtime",
            "-DoutputDirectory=target/dependency",
        ]
        try:
            proc = subprocess.run(
                cmd,
                cwd=isolated_project,
                capture_output=True,
                text=True,
                timeout=300,
                env={**os.environ, "JAVA_TOOL_OPTIONS": ""},
            )
        except subprocess.TimeoutExpired:
            return False, "Maven build timed out after 300s"
        except OSError as exc:
            return False, f"Failed to run Maven: {exc}"

        output = (install_output + "\n" + proc.stdout + proc.stderr).strip()
        if proc.returncode != 0:
            return False, f"Maven build failed (exit {proc.returncode}):\n{output}"

        classes = isolated_project / "target" / "classes"
        dependencies = isolated_project / "target" / "dependency"
        if not classes.is_dir():
            return False, f"Maven build produced no compiled output: {classes}"
        shutil.copytree(classes, build_dir, dirs_exist_ok=True)
        if dependencies.is_dir():
            shutil.copytree(
                dependencies,
                build_dir / runtime_lib_dir,
                dirs_exist_ok=True,
            )

    return True, output


def consumer_classpath(cfg: Dict[str, Any]) -> List[str]:
    """Return the container classpath for either consumer build mode."""
    classpath = ["/playground"]
    dependencies = list(cfg.get("classpath_deps", []))
    jade_artifact = cfg.get("jade_artifact")
    if (
        cfg.get("build_mode") == "maven"
        and jade_artifact
        and jade_artifact not in dependencies
    ):
        dependencies.append(jade_artifact)
    classpath.extend(f"/ws/{dep}" for dep in dependencies)
    if cfg.get("build_mode") == "maven":
        runtime_dir = cfg.get("maven_runtime_lib_dir", "lib")
        classpath.append(f"/playground/{runtime_dir}/*")
    return classpath


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
    classpath = ":".join(consumer_classpath(cfg))

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
    cfg, config_errors = validate_consumer_config(project_dir, cfg, workspace)
    name = cfg.get("name", project_dir.name)
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

    if config_errors:
        result["status"] = "FAIL"
        result["error"] = "Invalid consumer configuration: " + "; ".join(config_errors)
        result["duration_seconds"] = round(time.monotonic() - t0, 1)
        return result

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
        if cfg["build_mode"] == "maven":
            ok, output = build_maven_consumer(
                project_dir, workspace, cfg, build_dir
            )
        else:
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

        if rc != 0:
            result["status"] = "FAIL"
            result["error"] = f"Container exited with code {rc}"
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

        configured_failure_markers = cfg.get("failure_stdout_markers", [])
        if isinstance(configured_failure_markers, str):
            configured_failure_markers = [configured_failure_markers]
        elif not isinstance(configured_failure_markers, list):
            configured_failure_markers = []
        singular_marker = cfg.get("failure_stdout_marker")
        if isinstance(singular_marker, str):
            configured_failure_markers = [
                *configured_failure_markers,
                singular_marker,
            ]
        configured_failure_markers = [
            marker for marker in configured_failure_markers if isinstance(marker, str)
        ]
        found_configured_failures = [
            marker for marker in configured_failure_markers if marker in combined
        ]
        if found_configured_failures:
            result["status"] = "FAIL"
            result["error"] = (
                "Configured failure markers detected: "
                f"{found_configured_failures}"
            )
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
        }
        write_json(artifacts / "07-runtime-verify.json", result)
        print("No consumer projects found — pass")
        return 0

    # Test each consumer
    results: List[Dict[str, Any]] = []
    for project_dir, cfg in consumers:
        cfg = dict(cfg)
        try:
            cfg["docker_image"] = resolve_consumer_docker_image(
                cfg, run_cfg, registry
            )
        except ValueError as exc:
            print(f"ERROR: invalid Docker image configuration: {exc}", file=sys.stderr)
            return 3
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

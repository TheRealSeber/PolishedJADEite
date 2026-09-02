#!/usr/bin/env python3
"""verify_shard.py -- Compile one shard in Docker against the previous rule commit jar.

Loads one shard from a rule's shard plan (``05-rule-shards-<rule-id>.json``),
compiles the shard's editable files inside a Docker container with ``javac``
against the jar built at the previous rule commit, and writes a hard
PASS/FAIL verification artifact plus the full javac log.

No ``-sourcepath`` is passed to javac: types outside the shard resolve
against the baseline jar's compiled classes rather than against in-tree
sources. That is the entire point of the gate -- it catches a consumer of a
changed API that this shard's edits have not touched.

Exit codes:
  0 = PASS with no warnings
  1 = PASS with warnings (missing read-only context file, empty read-only
      context, unresolved baseline jar commit, or javac warnings present)
  2 = FAIL (compile errors, artifact and log ARE written) or a structural
      error in the shard plan / run config / shard file set (artifact and
      log are NOT written)
  3 = missing input file or environment error -- Docker unavailable, the
      baseline jar not built yet, an invalid Docker image registry, etc.
      Neither the artifact nor the log is ever written on this path.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
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

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SHARD_VERIFY_VERSION = 1
REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
DOCKER_IMAGE_CONFIG_PATH = REPO_ROOT / "config" / "docker-images.json"
RUNTIME_VERIFY_PATH = pathlib.Path(__file__).resolve().parent / "runtime_verify.py"
DEFAULT_JAR_RELPATH = pathlib.PurePosixPath("src/jade/lib/jade.jar")
DEFAULT_LIB_RELPATH = pathlib.PurePosixPath("src/jade/lib")
JAVAC_DIAGNOSTIC_RE = re.compile(
    r"^(?P<file>.+?\.java):(?P<line>\d+):\s+(?P<kind>error|warning):\s+(?P<message>.*)$"
)
ID_RE = re.compile(r"[A-Za-z0-9_.-]+")
CONTAINER_WS = "/ws"
CONTAINER_OUT = "/out"
CONTAINER_JAR = "/jar"
DOCKER_IMAGE_RESOLUTION_SOURCE = "central-registry"

# A shard plan (``05-rule-shards-<rule-id>.json``, produced upstream by
# plan_shards.py) describes a graph-closed slice of one rule's flagged files
# that can be compiled together as one verification unit. Every shard entry
# must carry these keys (see plan_shards.py's ``_plan_body_local`` /
# ``_plan_signature``); ``editable_files`` is the set actually being verified
# here, ``read_only_context`` is extra source that may be needed to resolve
# types but is never itself a compile target of this shard.
REQUIRED_SHARD_KEYS = (
    "shard_id",
    "rule_id",
    "class",
    "editable_files",
    "read_only_context",
    "entry_points",
    "invariants",
    "graph_artifact",
    "parallel_safe",
)


# ---------------------------------------------------------------------------
# Small helpers shared with the rest of the repo's script style
# ---------------------------------------------------------------------------
def iso_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def read_json(path: pathlib.Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json_atomic(path: pathlib.Path, payload: Dict[str, Any]) -> None:
    directory = path.parent
    directory.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".shard-verify-", suffix=".tmp", dir=str(directory))
    tmp_path = pathlib.Path(tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def _write_text_atomic(path: pathlib.Path, text: str) -> None:
    directory = path.parent
    directory.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".shard-verify-", suffix=".tmp", dir=str(directory))
    tmp_path = pathlib.Path(tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", errors="replace") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def _relpath_to_repo_root(path: pathlib.Path) -> str:
    """POSIX path relative to REPO_ROOT when possible, else an absolute POSIX path.

    Real pipeline runs always live under REPO_ROOT, but tests legitimately
    point --workspace/--baseline-jar at an isolated tmp_path outside the repo;
    falling back to an absolute path keeps the artifact honest in that case
    instead of raising.
    """
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


# ---------------------------------------------------------------------------
# Step 1 -- load runtime_verify.py's Docker helpers (never copy, never edit)
# ---------------------------------------------------------------------------
def _load_runtime_verify():
    if not RUNTIME_VERIFY_PATH.is_file():
        raise FileNotFoundError(f"runtime_verify.py not found at {RUNTIME_VERIFY_PATH}")
    spec = importlib.util.spec_from_file_location(
        "jade_runtime_verify", RUNTIME_VERIFY_PATH
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot create module spec for {RUNTIME_VERIFY_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Step 2 -- shard plan loading and validation
# ---------------------------------------------------------------------------
def _load_shard_plan(path: pathlib.Path) -> Dict[str, Any]:
    data = read_json(path)
    if not isinstance(data, dict) or not isinstance(data.get("shards"), list):
        raise ValueError(f"shard plan must be a JSON object with a 'shards' list: {path}")
    return data


def _find_shard(plan: Dict[str, Any], shard_id: str) -> Optional[Dict[str, Any]]:
    for shard in plan.get("shards", []):
        if isinstance(shard, dict) and shard.get("shard_id") == shard_id:
            return shard
    return None


def _validate_shard(shard: Dict[str, Any]) -> Optional[str]:
    if not isinstance(shard, dict):
        return "shard entry must be a JSON object"
    missing_keys = [key for key in REQUIRED_SHARD_KEYS if key not in shard]
    if missing_keys:
        return f"shard is missing required keys: {', '.join(missing_keys)}"
    editable = shard.get("editable_files")
    if (
        not isinstance(editable, list)
        or not editable
        or not all(isinstance(f, str) and f for f in editable)
    ):
        return "editable_files must be a non-empty list of strings"
    read_only = shard.get("read_only_context")
    if not isinstance(read_only, list) or not all(isinstance(f, str) for f in read_only):
        return "read_only_context must be a list of strings"
    return None


# ---------------------------------------------------------------------------
# Step 3 -- baseline jar commit lookup (09-rule-commit-log.json)
# ---------------------------------------------------------------------------
def _resolve_baseline_jar_commit(
    artifacts_dir: pathlib.Path, rule_id: str
) -> Tuple[Optional[str], bool]:
    """Return (commit_hash, found). ``found`` is False when unresolved."""
    path = artifacts_dir / "09-rule-commit-log.json"
    if not path.is_file():
        return None, False
    try:
        data = read_json(path)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None, False
    if isinstance(data, list):
        entries = data
    elif isinstance(data, dict):
        entries = [data]
    else:
        entries = []
    match: Optional[Dict[str, Any]] = None
    for entry in entries:
        if isinstance(entry, dict) and entry.get("rule_id") == rule_id:
            match = entry
    if match is None:
        return None, False
    commit_hash = match.get("commit_hash")
    if isinstance(commit_hash, str) and commit_hash:
        return commit_hash, True
    return None, False


# ---------------------------------------------------------------------------
# Step 7 -- pure Docker command builder (no I/O, testable without Docker)
# ---------------------------------------------------------------------------
def _docker_path(p: pathlib.Path) -> str:
    """Copy of runtime_verify._docker_path's Windows-drive-letter normalization."""
    raw = str(p.resolve())
    if len(raw) > 1 and raw[1] == ":":
        drive = raw[0].lower()
        rest = raw[2:].replace("\\", "/")
        return f"{drive}:{rest}"
    return raw.replace("\\", "/")


def build_docker_command(
    image: str,
    ws_docker: str,
    build_docker: str,
    classpath: str,
    javac_encoding: str,
    javac_source: str,
    javac_target: str,
    jar_dir_docker: Optional[str] = None,
) -> List[str]:
    """Assemble the ``docker run ... javac ...`` argv. Pure, no I/O."""
    cmd: List[str] = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{ws_docker}:{CONTAINER_WS}:ro",
        "-v",
        f"{build_docker}:{CONTAINER_OUT}",
    ]
    if jar_dir_docker is not None:
        cmd += ["-v", f"{jar_dir_docker}:{CONTAINER_JAR}:ro"]
    cmd += [
        "-w",
        CONTAINER_OUT,
        image,
        "javac",
        "-nowarn",
        "-proc:none",
        "-implicit:none",
        "-encoding",
        javac_encoding,
        "-source",
        javac_source,
        "-target",
        javac_target,
        "-cp",
        classpath,
        "-d",
        f"{CONTAINER_OUT}/classes",
        f"@{CONTAINER_OUT}/sources.txt",
    ]
    return cmd


def _collect_workspace_lib_jars(
    workspace: pathlib.Path,
    warnings: Optional[List[Dict[str, Any]]] = None,
) -> List[str]:
    """Sorted container-path entries for every jar under DEFAULT_LIB_RELPATH.

    Exists so the classpath never has to hardcode a library file name --
    today this directory holds nothing beyond the baseline jar itself (if
    that even exists yet), but a future rule commit may vendor more jars
    there and this glob picks them up automatically.

    A jar that resolves outside the workspace (a symlink to a system or
    cache directory) is skipped rather than fatal: only the workspace is
    bind-mounted into the container, so such a jar would not be readable
    there anyway.  Each skip is recorded in *warnings* when provided, so a
    silently shortened classpath stays visible in the artifact.
    """
    lib_dir = workspace / str(DEFAULT_LIB_RELPATH)
    if not lib_dir.is_dir():
        return []
    workspace_resolved = workspace.resolve()
    entries: List[str] = []
    for jar_path in sorted(lib_dir.rglob("*.jar")):
        try:
            rel = jar_path.resolve().relative_to(workspace_resolved).as_posix()
        except ValueError:
            if warnings is not None:
                warnings.append(
                    {
                        "kind": "lib_jar_outside_workspace",
                        "message": (
                            "Library jar resolves outside the workspace and is "
                            "excluded from the classpath"
                        ),
                        "file": jar_path.as_posix(),
                    }
                )
            continue
        entries.append(f"{CONTAINER_WS}/{rel}")
    return entries


# ---------------------------------------------------------------------------
# Step 8 -- container execution (swappable layer; tests replace this function)
# ---------------------------------------------------------------------------
def run_shard_in_docker(
    cmd: List[str], build_dir: pathlib.Path, timeout_seconds: int
) -> Tuple[int, str, str]:
    """Run the javac container. Returns (exit_code, stdout_text, stderr_text).

    stdout/stderr are captured through temp files inside build_dir (not
    pipes) so a TimeoutExpired still yields whatever javac had already
    written. -1 = timeout, -2 = OSError launching docker.
    """
    out_path = build_dir / "out.txt"
    err_path = build_dir / "err.txt"
    try:
        with out_path.open("w", encoding="utf-8") as fout, err_path.open(
            "w", encoding="utf-8"
        ) as ferr:
            proc = subprocess.run(
                cmd,
                stdout=fout,
                stderr=ferr,
                timeout=timeout_seconds,
                env={**os.environ, "MSYS_NO_PATHCONV": "1"},
                check=False,
            )
        stdout_text = out_path.read_text(encoding="utf-8", errors="replace")
        stderr_text = err_path.read_text(encoding="utf-8", errors="replace")
        return proc.returncode, stdout_text, stderr_text
    except subprocess.TimeoutExpired:
        stdout_text = out_path.read_text(encoding="utf-8", errors="replace") if out_path.exists() else ""
        stderr_text = err_path.read_text(encoding="utf-8", errors="replace") if err_path.exists() else ""
        stderr_text += f"\nContainer timed out after {timeout_seconds}s"
        return -1, stdout_text, stderr_text
    except OSError as exc:
        return -2, "", f"Failed to run docker: {exc}"


# ---------------------------------------------------------------------------
# Step 9 -- javac diagnostic parsing
# ---------------------------------------------------------------------------
def parse_javac_output(
    log_text: str, workspace_prefix: str = f"{CONTAINER_WS}/"
) -> Tuple[List[Dict[str, Any]], int]:
    """Parse javac ``file:line: kind: message`` diagnostics.

    Returns (errors, warning_count). Errors are deduplicated and sorted by
    (file, line, message); ``N errors``/``N warnings`` summary lines are
    ignored since exit_code plus this parsed list are the source of truth.
    """
    errors_seen = set()
    warning_count = 0
    for line in log_text.splitlines():
        match = JAVAC_DIAGNOSTIC_RE.match(line)
        if not match:
            continue
        file_ = match.group("file")
        if file_.startswith(workspace_prefix):
            file_ = file_[len(workspace_prefix):]
        kind = match.group("kind")
        message = match.group("message")
        if kind == "error":
            errors_seen.add((file_, int(match.group("line")), message))
        elif kind == "warning":
            warning_count += 1
    errors = [
        {"file": f, "line": ln, "message": msg}
        for f, ln, msg in sorted(errors_seen)
    ]
    return errors, warning_count


def _build_log_excerpt(log_text: str, limit: int = 20000) -> str:
    lines = log_text.splitlines()
    if len(lines) <= 200:
        excerpt = log_text
    else:
        excerpt = "\n".join(lines[:100] + ["[... truncated ...]"] + lines[-100:])
    return excerpt[:limit]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Compile one shard in Docker against the previous rule commit jar"
    )
    parser.add_argument("--artifacts-dir", required=True, help="Path to artifacts directory")
    parser.add_argument("--rule-id", required=True, help="Rule id owning the shard")
    parser.add_argument("--shard-id", required=True, help="Shard id to verify")
    parser.add_argument(
        "--shards-artifact",
        default=None,
        help="Shard plan artifact (default: <artifacts-dir>/05-rule-shards-<rule-id>.json)",
    )
    parser.add_argument(
        "--workspace",
        default=None,
        help="Migration workspace root (default: workspace_path from run config, resolved against repo root)",
    )
    parser.add_argument(
        "--baseline-jar",
        default=None,
        help="Jar built at the previous rule commit (default: <workspace>/src/jade/lib/jade.jar)",
    )
    parser.add_argument(
        "--run-config",
        default=None,
        help="Run config JSON (default: <artifacts-dir>/00-run-config.json)",
    )
    parser.add_argument(
        "--javac-encoding",
        default="ISO-8859-1",
        help="Source encoding passed to javac",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=600,
        help="javac container timeout in seconds",
    )
    parser.add_argument("--output", default=None, help="Override output artifact path")
    args = parser.parse_args(argv)

    # ---- Step 1: load runtime_verify.py's Docker helpers ------------------
    try:
        rv = _load_runtime_verify()
    except Exception as exc:  # noqa: BLE001 -- any load failure is fatal here
        print(f"ERROR [RUNTIME_VERIFY_UNAVAILABLE] {exc}", file=sys.stderr)
        return 3

    # ---- Step 2: validate ids, load shard plan, find + validate shard -----
    if not ID_RE.fullmatch(args.rule_id):
        print(f"ERROR [INVALID_ID] --rule-id is invalid: {args.rule_id!r}", file=sys.stderr)
        return 2
    if not ID_RE.fullmatch(args.shard_id):
        print(f"ERROR [INVALID_ID] --shard-id is invalid: {args.shard_id!r}", file=sys.stderr)
        return 2

    artifacts_dir = pathlib.Path(args.artifacts_dir)
    shards_path = (
        pathlib.Path(args.shards_artifact)
        if args.shards_artifact
        else artifacts_dir / f"05-rule-shards-{args.rule_id}.json"
    )
    if not shards_path.is_file():
        print(f"ERROR [SHARD_PLAN_NOT_FOUND] {shards_path}", file=sys.stderr)
        return 3
    try:
        plan = _load_shard_plan(shards_path)
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        print(f"ERROR [SHARD_PLAN_MALFORMED] {exc}", file=sys.stderr)
        return 2

    shard = _find_shard(plan, args.shard_id)
    if shard is None:
        print(f"ERROR [SHARD_NOT_FOUND] {args.shard_id}", file=sys.stderr)
        return 2

    shard_error = _validate_shard(shard)
    if shard_error:
        print(f"ERROR [SHARD_MALFORMED] {shard_error}", file=sys.stderr)
        return 2

    # ---- Step 3: run config, workspace, baseline jar -----------------------
    run_config_path = (
        pathlib.Path(args.run_config) if args.run_config else artifacts_dir / "00-run-config.json"
    )
    if not run_config_path.is_file():
        print(f"ERROR [RUN_CONFIG_NOT_FOUND] {run_config_path}", file=sys.stderr)
        return 3
    try:
        run_cfg = read_json(run_config_path)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"ERROR [RUN_CONFIG_MALFORMED] {exc}", file=sys.stderr)
        return 2
    if not isinstance(run_cfg, dict):
        print("ERROR [RUN_CONFIG_MALFORMED] run config must be a JSON object", file=sys.stderr)
        return 2

    target_version = str(run_cfg.get("target_version", ""))
    if not target_version:
        print("ERROR [RUN_CONFIG_MALFORMED] run config is missing target_version", file=sys.stderr)
        return 2

    if args.workspace:
        workspace = pathlib.Path(args.workspace)
    else:
        workspace_path = run_cfg.get("workspace_path")
        if not isinstance(workspace_path, str) or not workspace_path:
            print("ERROR [RUN_CONFIG_MALFORMED] run config is missing workspace_path", file=sys.stderr)
            return 2
        workspace = REPO_ROOT / workspace_path
    if not workspace.is_dir():
        print(f"ERROR [WORKSPACE_NOT_FOUND] {workspace}", file=sys.stderr)
        return 3

    baseline_jar = (
        pathlib.Path(args.baseline_jar) if args.baseline_jar else workspace / str(DEFAULT_JAR_RELPATH)
    )
    if not baseline_jar.is_file():
        print(
            f"ERROR [BASELINE_JAR_NOT_FOUND] {baseline_jar}. "
            "Build the jar at the previous rule commit before verifying a shard",
            file=sys.stderr,
        )
        return 3

    baseline_jar_commit, commit_found = _resolve_baseline_jar_commit(artifacts_dir, args.rule_id)

    warnings: List[Dict[str, Any]] = []
    if not commit_found:
        warnings.append(
            {
                "kind": "baseline_jar_commit_unknown",
                "message": (
                    "No matching commit_hash found in 09-rule-commit-log.json "
                    f"for rule_id={args.rule_id}"
                ),
            }
        )

    editable_files = shard["editable_files"]
    for relpath in editable_files:
        if not (workspace / relpath).is_file():
            print(f"ERROR [SHARD_FILE_MISSING] {relpath}", file=sys.stderr)
            return 2

    read_only_context = shard["read_only_context"]
    for relpath in read_only_context:
        if not (workspace / relpath).is_file():
            warnings.append(
                {
                    "kind": "read_only_file_missing_on_disk",
                    "file": relpath,
                    "message": f"read_only_context file not found on disk: {relpath}",
                }
            )
    if read_only_context == []:
        warnings.append(
            {
                "kind": "empty_read_only_context",
                "message": "shard declares no read_only_context files",
            }
        )

    # ---- Step 4: resolve Docker image from the central registry -----------
    try:
        registry = rv.load_docker_image_registry(DOCKER_IMAGE_CONFIG_PATH)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR [DOCKER_IMAGE_CONFIG_INVALID] {exc}", file=sys.stderr)
        return 3
    try:
        docker_image = rv.resolve_docker_image(target_version, registry)
        registry_key = rv.registry_key_for_runtime_version(target_version, registry)
    except ValueError as exc:
        print(f"ERROR [DOCKER_IMAGE_UNRESOLVED] {exc}", file=sys.stderr)
        return 3
    javac_source = javac_target = rv.version_key(target_version)

    # ---- Step 5: environment gate (before touching any container) ---------
    if shutil.which("docker") is None:
        print("ERROR [DOCKER_NOT_FOUND] docker not found on PATH", file=sys.stderr)
        return 3
    try:
        docker_info = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
            check=False,
            env={**os.environ, "MSYS_NO_PATHCONV": "1"},
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        print(f"ERROR [DOCKER_DAEMON_UNREACHABLE] {exc}", file=sys.stderr)
        return 3
    if docker_info.returncode != 0:
        print(
            f"ERROR [DOCKER_DAEMON_UNREACHABLE] docker info failed with exit code {docker_info.returncode}",
            file=sys.stderr,
        )
        return 3

    # ---- Step 6-8: working directory, docker command, container run ------
    build_dir = artifacts_dir / f".shard-verify-{args.shard_id}"
    try:
        build_dir.mkdir(parents=True, exist_ok=True)
        (build_dir / "classes").mkdir(exist_ok=True)

        sorted_editable = sorted(editable_files)
        sources_path = build_dir / "sources.txt"
        with sources_path.open("w", encoding="utf-8", newline="\n") as f:
            for relpath in sorted_editable:
                f.write(f"{CONTAINER_WS}/{relpath}\n")

        ws_docker = _docker_path(workspace)
        build_docker_str = _docker_path(build_dir)

        workspace_resolved = workspace.resolve()
        baseline_resolved = baseline_jar.resolve()
        try:
            jar_rel = baseline_resolved.relative_to(workspace_resolved)
            jar_cp = f"{CONTAINER_WS}/{pathlib.PurePosixPath(jar_rel.as_posix())}"
            jar_dir_docker = None
        except ValueError:
            jar_dir_docker = _docker_path(baseline_resolved.parent)
            jar_cp = f"{CONTAINER_JAR}/{baseline_resolved.name}"

        lib_entries = _collect_workspace_lib_jars(workspace, warnings)
        classpath_parts = [jar_cp] + [e for e in lib_entries if e != jar_cp]
        classpath = ":".join(classpath_parts)

        cmd = build_docker_command(
            image=docker_image,
            ws_docker=ws_docker,
            build_docker=build_docker_str,
            classpath=classpath,
            javac_encoding=args.javac_encoding,
            javac_source=javac_source,
            javac_target=javac_target,
            jar_dir_docker=jar_dir_docker,
        )

        effective_timeout = args.timeout_seconds + rv.TIMEOUT_BUFFER
        start = time.monotonic()
        exit_code, stdout_text, stderr_text = run_shard_in_docker(
            cmd, build_dir, effective_timeout
        )
        duration_seconds = round(time.monotonic() - start, 2)
    finally:
        shutil.rmtree(build_dir, ignore_errors=True)

    # ---- Step 9: parse javac diagnostics -----------------------------------
    log_text = stdout_text + "\n" + stderr_text
    errors, warning_count = parse_javac_output(log_text, workspace_prefix=f"{CONTAINER_WS}/")
    if warning_count > 0:
        warnings.append(
            {
                "kind": "javac_warnings_present",
                "message": f"javac reported {warning_count} warning(s)",
            }
        )

    # ---- Step 10: status, log, artifact -----------------------------------
    status = "PASS" if exit_code == 0 and not errors else "FAIL"

    log_path = artifacts_dir / f"07-shard-verify-{args.shard_id}.log"
    try:
        _write_text_atomic(log_path, log_text)
    except OSError as exc:
        print(f"ERROR [WRITE_FAILED] {exc}", file=sys.stderr)
        return 3

    compiled_files = sorted(editable_files)
    payload: Dict[str, Any] = {
        "schema_version": SHARD_VERIFY_VERSION,
        "run_id": run_cfg.get("run_id", ""),
        "rule_id": args.rule_id,
        "shard_id": args.shard_id,
        "shard_class": shard["class"],
        "status": status,
        "generated_at": iso_now(),
        "docker_image": docker_image,
        "docker_image_resolution_source": DOCKER_IMAGE_RESOLUTION_SOURCE,
        "docker_image_registry_key": registry_key,
        "docker_image_config": _relpath_to_repo_root(DOCKER_IMAGE_CONFIG_PATH),
        "javac_source": javac_source,
        "javac_target": javac_target,
        "javac_encoding": args.javac_encoding,
        "baseline_jar": _relpath_to_repo_root(baseline_jar),
        "baseline_jar_commit": baseline_jar_commit,
        "compiled_files": compiled_files,
        "compiled_file_count": len(compiled_files),
        "exit_code": exit_code,
        "duration_seconds": duration_seconds,
        "errors": errors,
        "error_count": len(errors),
        "javac_log": log_path.name,
        "javac_log_excerpt": _build_log_excerpt(log_text),
        "warnings": sorted(warnings, key=lambda w: json.dumps(w, sort_keys=True)),
    }

    output_path = pathlib.Path(args.output) if args.output else (
        artifacts_dir / f"07-shard-verify-{args.shard_id}.json"
    )
    try:
        _write_json_atomic(output_path, payload)
    except OSError as exc:
        print(f"ERROR [WRITE_FAILED] {exc}", file=sys.stderr)
        return 3

    print(f"Shard verify written: {output_path}")
    print(f"  shard_id={args.shard_id} class={shard['class']} status={status}")
    print(f"  docker_image={docker_image} registry_key={registry_key} source={javac_source}")
    print(
        f"  files={payload['compiled_file_count']} errors={payload['error_count']} "
        f"exit_code={exit_code} duration={duration_seconds}s"
    )

    if status == "FAIL":
        for error in errors[:20]:
            print(
                f"ERROR [JAVAC] {error['file']}:{error['line']}: {error['message']}",
                file=sys.stderr,
            )
        return 2

    if payload["warnings"]:
        for warning in payload["warnings"]:
            print(f"WARNING [SHARD_VERIFY] {json.dumps(warning, sort_keys=True)}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

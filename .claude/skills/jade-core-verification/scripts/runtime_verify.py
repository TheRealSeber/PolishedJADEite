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
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------
PLAYGROUND_DIR = pathlib.Path("consumer-playground")
TIMEOUT_BUFFER = 15  # extra seconds beyond test-config timeout for docker pull etc.
MAVEN_DEPENDENCY_PLUGIN_VERSION = "3.6.1"
ALLOWED_MAVEN_PLUGINS = {
    ("org.apache.maven.plugins", "maven-compiler-plugin"),
    ("org.apache.maven.plugins", "maven-dependency-plugin"),
}
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
    """Normalise a JDK version string to the form javac accepts on the
    command line: bare major ("11", "17", ...) for JDK 9+, where the
    "-source"/"-target 1.X" spelling was dropped, and the legacy "1.X" form
    only for the JDK 5-8 releases that predate the change."""
    parts = raw.replace("_", ".").split(".")
    numeric = [int(x) for x in parts if x.isdigit()]
    if len(numeric) == 1 and numeric[0] >= 9:
        return str(numeric[0])
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


def _registry_java_versions(registry: Dict[str, str]) -> set[int]:
    versions = set()
    for key in registry:
        prefix, _, suffix = str(key).partition("java-")
        if not prefix and suffix.isdigit() and int(suffix) > 0:
            versions.add(int(suffix))
    return versions


def parse_runtime_java_version(
    raw_version: Any, registry: Optional[Dict[str, str]] = None
) -> int:
    if registry is None:
        raise ValueError(
            "runtime_java_version validation requires a loaded Docker registry"
        )
    if isinstance(raw_version, bool):
        raise ValueError("runtime_java_version must be a numeric Java version")
    if isinstance(raw_version, int):
        major = raw_version
    elif isinstance(raw_version, str) and raw_version.strip().isdigit():
        major = int(raw_version.strip())
    else:
        raise ValueError("runtime_java_version must be a numeric Java version")
    if registry is not None and major not in _registry_java_versions(registry):
        raise ValueError(
            f"runtime_java_version {major} is unsupported by the Docker registry"
        )
    return major


def resolve_docker_image(target_version: str, registry: Dict[str, str]) -> str:
    if not isinstance(target_version, str) or not target_version.strip():
        raise ValueError(
            "Target Java version is invalid or unsupported: value is missing"
        )
    major = java_major(target_version)
    if major <= 0:
        raise ValueError(
            f"Target Java version is invalid or unsupported: {target_version}"
        )
    if major > 17:
        image_key = f"java-{major}"
        if image_key not in registry:
            raise ValueError(
                f"Target Java {major} is unsupported; registry has no {image_key} image"
            )
        return registry[image_key]
    if major >= 17:
        return registry["java-17"]
    if major >= 11:
        return registry["java-11"]
    return registry["java-8"]


def registry_key_for_runtime_version(
    runtime_version: Any, registry: Dict[str, str]
) -> str:
    major = java_major(str(runtime_version))
    if major >= 18:
        key = f"java-{major}"
    elif major >= 17:
        key = "java-17"
    elif major >= 11:
        key = "java-11"
    else:
        key = "java-8"
    if key not in registry:
        raise ValueError(f"Docker registry key is unavailable: {key}")
    return key


def resolve_consumer_docker_image(
    consumer_cfg: Dict[str, Any], run_cfg: Dict[str, Any], registry: Dict[str, str]
) -> str:
    if "runtime_java_version" in consumer_cfg:
        runtime_version = parse_runtime_java_version(
            consumer_cfg["runtime_java_version"], registry
        )
    else:
        runtime_version = str(run_cfg.get("target_version", ""))
    configured = consumer_cfg.get("docker_image", "")
    if configured is None or not isinstance(configured, str):
        raise ValueError(
            "docker_image must be ${TARGET_DOCKER_IMAGE} or omitted"
        )
    configured = configured.strip()
    if configured and configured != "${TARGET_DOCKER_IMAGE}":
        raise ValueError(
            "docker_image must be ${TARGET_DOCKER_IMAGE} or omitted"
        )
    return resolve_docker_image(str(runtime_version), registry)


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


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def validate_maven_pom(project_root: pathlib.Path) -> Optional[str]:
    if (project_root / ".mvn").exists():
        return "Maven .mvn metadata directory is not allowed"
    pom_path = project_root / "pom.xml"
    if not pom_path.is_file():
        return f"Maven POM not found: {pom_path}"
    try:
        root = ET.parse(pom_path).getroot()
    except (ET.ParseError, OSError) as exc:
        return f"Maven POM cannot be parsed: {exc}"

    for node in root.iter():
        if _xml_local_name(node.tag) in {
            "parent",
            "modules",
            "repositories",
            "pluginRepositories",
        }:
            return f"Maven POM element {_xml_local_name(node.tag)} is not allowed"
        if _xml_local_name(node.tag) == "systemPath":
            return "Maven systemPath dependencies are not allowed"
        if _xml_local_name(node.tag) == "scope" and (
            (node.text or "").strip() == "system"
        ):
            return "Maven system dependencies are not allowed"

    properties = {}
    for node in root:
        if _xml_local_name(node.tag) == "properties":
            properties = {
                _xml_local_name(child.tag): (child.text or "").strip()
                for child in node
            }
    jade_dependencies = []
    for dependencies in root:
        if _xml_local_name(dependencies.tag) != "dependencies":
            continue
        for dependency in dependencies:
            if _xml_local_name(dependency.tag) != "dependency":
                continue
            values = {
                _xml_local_name(child.tag): (child.text or "").strip()
                for child in dependency
            }
            if (
                values.get("groupId") == "com.tilab.jade"
                and values.get("artifactId") == "jade"
            ):
                jade_dependencies.append(values.get("version"))
    resolved_jade_versions = [
        properties.get(version[2:-1], version)
        if isinstance(version, str) and version.startswith("${") and version.endswith("}")
        else version
        for version in jade_dependencies
    ]
    if resolved_jade_versions != ["4.6"]:
        return "Maven POM must declare exactly com.tilab.jade:jade:4.6"

    for build in [child for child in root if _xml_local_name(child.tag) == "build"]:
        if any(_xml_local_name(node.tag) == "extension" for node in build.iter()):
            return "Maven build extensions are not allowed"
        for node in build.iter():
            if _xml_local_name(node.tag) == "extensions" and (
                (node.text or "").strip().lower() == "true"
            ):
                return "Maven build extensions are not allowed"
        for plugin in [node for node in build.iter() if _xml_local_name(node.tag) == "plugin"]:
            group_id = next(
                (
                    (child.text or "").strip()
                    for child in plugin
                    if _xml_local_name(child.tag) == "groupId"
                ),
                "org.apache.maven.plugins",
            )
            artifact_id = next(
                (
                    (child.text or "").strip()
                    for child in plugin
                    if _xml_local_name(child.tag) == "artifactId"
                ),
                "",
            )
            if (group_id, artifact_id) not in ALLOWED_MAVEN_PLUGINS:
                return f"Maven plugin {group_id}:{artifact_id} is not allowlisted"
            if artifact_id == "maven-compiler-plugin":
                forbidden = {
                    "fork",
                    "executable",
                    "compilerArgs",
                    "compilerArgument",
                    "compilerArguments",
                    "annotationProcessorPaths",
                    "annotationProcessorPath",
                    "proc",
                }
                if any(_xml_local_name(node.tag) in forbidden for node in plugin.iter()):
                    return "Maven compiler execution controls are not allowed"

    for profile in [node for node in root.iter() if _xml_local_name(node.tag) == "profile"]:
        if any(_xml_local_name(node.tag) in {"plugin", "extension"} for node in profile.iter()):
            return "Maven profiles with build plugins or extensions are not allowed"
        if any(
            _xml_local_name(node.tag) == "extensions"
            and (node.text or "").strip().lower() == "true"
            for node in profile.iter()
        ):
            return "Maven profiles with build plugins or extensions are not allowed"
    return None


def validate_maven_project(project_root: pathlib.Path) -> Optional[str]:
    for metadata in project_root.rglob(".mvn"):
        return "Maven .mvn metadata directory is not allowed"
    pom_paths = sorted(project_root.rglob("pom.xml"))
    if not pom_paths:
        return f"Maven POM not found: {project_root / 'pom.xml'}"
    for pom_path in pom_paths:
        error = validate_maven_pom(pom_path.parent)
        if error:
            return f"{pom_path}: {error}"
    return None


def validate_consumer_config(
    project_dir: pathlib.Path,
    cfg: Dict[str, Any],
    workspace: pathlib.Path,
    registry: Optional[Dict[str, str]] = None,
) -> Tuple[Dict[str, Any], List[str]]:
    """Normalize and validate consumer build configuration without building it."""
    normalized = dict(cfg)
    errors: List[str] = []

    if "maven_executable" in normalized:
        errors.append(
            "maven_executable is not supported; the verifier selects Maven"
        )
        normalized.pop("maven_executable", None)

    if "docker_image" in normalized:
        configured_image = normalized["docker_image"]
        if configured_image is None or not isinstance(configured_image, str):
            errors.append("docker_image must be ${TARGET_DOCKER_IMAGE} or omitted")
        elif configured_image.strip() not in {"", "${TARGET_DOCKER_IMAGE}"}:
            errors.append("docker_image must be ${TARGET_DOCKER_IMAGE} or omitted")

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

    if "runtime_java_version" in normalized:
        try:
            normalized["runtime_java_version"] = parse_runtime_java_version(
                normalized["runtime_java_version"], registry
            )
        except ValueError as exc:
            errors.append(str(exc))

    main_class = normalized.get("main_class")
    if not isinstance(main_class, str) or not main_class.strip():
        errors.append("main_class must be a non-empty string")
    boot_args = normalized.get("boot_args")
    if not isinstance(boot_args, list) or not all(
        isinstance(arg, str) for arg in boot_args
    ):
        errors.append("boot_args must be a list of strings")
    timeout_seconds = normalized.get("timeout_seconds")
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or timeout_seconds <= 0
    ):
        errors.append("timeout_seconds must be a positive number")

    if "expected_stdout_markers" in normalized:
        markers = normalized["expected_stdout_markers"]
        if (
            not isinstance(markers, list)
            or not markers
            or any(
                not isinstance(marker, str) or not marker.strip() for marker in markers
            )
        ):
            errors.append(
                "expected_stdout_markers must be a non-empty list of non-empty strings"
            )
    else:
        errors.append("expected_stdout_markers is required")

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


JADE_IMPORT_RE = re.compile(
    r"^\s*import\s+(?:static\s+)?jade\.([\w.]+?)\s*;", re.MULTILINE
)

# consumer-playground test runners report their own pass/fail outcome with a
# SCREAMING_SNAKE_CASE "..._FAILED" marker (RESTAURANT_TEST_FAILED,
# JRBA_TEST_FAILED, HW_JADE_FAILED, DF_REGISTRATION_FAILED, ...). A consumer
# whose test-config.json never declared failure_stdout_markers for its own
# convention must not be reported PASS just because an unrelated success
# marker also happened to print earlier in the run -- this is exactly how
# restaurant-recommendation was reported PASS in
# migration-runs/jade-8-to-11/artifacts/07-runtime-verify.json while its own
# TestRunnerAgent had printed RESTAURANT_TEST_FAILED. Requires a word boundary
# on both sides so a bare "FAILED" (no identifier prefix) is not matched.
GENERIC_FAILURE_MARKER_RE = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*_FAILED\b")


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


def _fqn_index(graph_nodes: Dict[str, Any]) -> Dict[str, str]:
    """Map ``pkg.Class`` FQN -> node path for the given graph nodes."""
    index: Dict[str, str] = {}
    for path, node in graph_nodes.items():
        if not isinstance(node, dict):
            continue
        pkg = node.get("package", "")
        cls = node.get("class_name", "")
        if pkg and cls:
            index.setdefault(f"{pkg}.{cls}", path)
    return index


def map_jade_fqns_to_node_paths(
    fqns: List[str], graph_nodes: Dict[str, Any]
) -> List[str]:
    """Map consumer JADE FQNs to workspace-relative graph node paths."""
    if not fqns or not isinstance(graph_nodes, dict):
        return []
    index = _fqn_index(graph_nodes)
    paths = {index[fqn] for fqn in fqns if fqn in index}
    return sorted(paths)


def _consumer_name(project_dir: pathlib.Path, cfg: Dict[str, Any]) -> str:
    return str(cfg.get("name", project_dir.name))


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
        name = _consumer_name(project_dir, cfg)
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
    ordered = [
        c for c in consumers if _consumer_name(c[0], c[1]) in impacted_set
    ] + [c for c in consumers if _consumer_name(c[0], c[1]) not in impacted_set]
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

    pom_error = validate_maven_project(project_root)
    if pom_error:
        return False, f"Maven POM rejected: {pom_error}"

    with tempfile.TemporaryDirectory(prefix="jade-maven-repo-") as repo:
        isolated_project = pathlib.Path(repo) / "consumer"
        shutil.copytree(
            project_root,
            isolated_project,
            ignore=shutil.ignore_patterns("target"),
        )
        maven_cmd = _maven_command()
        common_args = [
            "-B",
            "-ntp",
            f"-Dmaven.repo.local={repo}",
            # JDK 23+ disables implicit annotation processing (JEP 486 in
            # JDK 25); Lombok and Immutables processors must be enabled
            # explicitly or consumers fail to compile on modern host JDKs.
            "-Dmaven.compiler.proc=full",
        ]
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
            f"org.apache.maven.plugins:maven-dependency-plugin:{MAVEN_DEPENDENCY_PLUGIN_VERSION}:copy-dependencies",
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
    docker_image = cfg.get("_resolved_docker_image") or cfg.get("docker_image")
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
        f"{ws_docker}:/ws:ro",
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
    registry: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Run one consumer test. Returns result dict."""
    cfg, config_errors = validate_consumer_config(
        project_dir, cfg, workspace, registry
    )
    name = cfg.get("name", project_dir.name)
    declared_image = cfg.get("docker_image")
    resolved_image = cfg.get("_resolved_docker_image")
    result: Dict[str, Any] = {
        "project": name,
        "status": "PENDING",
        "duration_seconds": 0.0,
        "jade_booted": False,
        "stdout_snippet": "",
        "error": None,
        "docker_image": resolved_image or declared_image,
        "declared_docker_image": declared_image,
        "resolved_docker_image": resolved_image,
        "docker_image_resolution_source": cfg.get(
            "_docker_image_resolution_source"
        ),
        "docker_image_registry_key": cfg.get("_docker_image_registry_key"),
        "runtime_java_version": cfg.get("runtime_java_version"),
    }
    if cfg.get("build_mode") == "maven":
        result["maven_dependency_plugin_version"] = MAVEN_DEPENDENCY_PLUGIN_VERSION

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

        # Check expected markers up front only to build the exclusion set for
        # the generic failure-marker scan below; the actual pass/fail
        # decision on these still happens after every failure check.
        markers = cfg.get("expected_stdout_markers", [])
        if not isinstance(markers, list):
            markers = []
        expected_marker_set = {m for m in markers if isinstance(m, str)}

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

        # Generic safety net for the repo-wide "..._FAILED" outcome
        # convention: catches a consumer's own failure signal even when its
        # test-config.json never opted in via failure_stdout_markers. Markers
        # that are themselves declared as expected/configured are excluded so
        # a legitimate success or already-handled failure marker can't
        # double-trigger here.
        generic_failure_matches = sorted(
            match
            for match in set(GENERIC_FAILURE_MARKER_RE.findall(combined))
            if match not in expected_marker_set
            and match not in configured_failure_markers
        )
        if generic_failure_matches:
            result["status"] = "FAIL"
            result["error"] = (
                "Unconfigured failure markers detected: "
                f"{generic_failure_matches}"
            )
            return result

        # Check expected markers
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
    if not isinstance(run_cfg, dict):
        print("ERROR: run config must be a JSON object", file=sys.stderr)
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
        docker_info = subprocess.run(
            ["docker", "info"], capture_output=True, timeout=10, check=False
        )
    except (subprocess.TimeoutExpired, OSError):
        print("ERROR: docker daemon not running or unreachable", file=sys.stderr)
        return 3
    if docker_info.returncode != 0:
        print(
            f"ERROR: docker info failed with exit code {docker_info.returncode}",
            file=sys.stderr,
        )
        return 3

    # Discover consumers
    consumers = discover_consumers()
    if not consumers:
        result = {
            "run_id": run_id,
            "generated_at": iso_now(),
            "overall_pass": False,
            "total_consumers": 0,
            "passed": 0,
            "failed": 1,
            "results": [],
            "error": "No valid consumer configs discovered",
            "consumer_coverage": {},
        }
        write_json(artifacts / "07-runtime-verify.json", result)
        print("ERROR: No valid consumer configs discovered", file=sys.stderr)
        return 2

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
        try:
            cfg["_resolved_docker_image"] = resolve_consumer_docker_image(
                cfg, run_cfg, registry
            )
            runtime_version = cfg.get(
                "runtime_java_version", run_cfg.get("target_version")
            )
            cfg["_docker_image_resolution_source"] = "central-registry"
            cfg["_docker_image_registry_key"] = registry_key_for_runtime_version(
                runtime_version, registry
            )
        except ValueError as exc:
            result = {
                "project": cfg.get("name", project_dir.name),
                "status": "FAIL",
                "duration_seconds": 0.0,
                "jade_booted": False,
                "stdout_snippet": "",
                "error": f"Invalid consumer configuration: {exc}",
                "docker_image": None,
                "declared_docker_image": cfg.get("docker_image"),
                "resolved_docker_image": None,
                "docker_image_resolution_source": None,
                "docker_image_registry_key": None,
                "runtime_java_version": cfg.get("runtime_java_version"),
            }
            if cfg.get("build_mode") == "maven":
                result[
                    "maven_dependency_plugin_version"
                ] = MAVEN_DEPENDENCY_PLUGIN_VERSION
            results.append(result)
            print(f"  [FAIL] {result['project']} (0.0s)")
            continue
        try:
            result = test_consumer(project_dir, workspace, cfg, registry)
        except Exception as exc:
            result = {
                "project": cfg.get("name", project_dir.name),
                "status": "FAIL",
                "duration_seconds": 0.0,
                "jade_booted": False,
                "stdout_snippet": "",
                "error": f"Consumer verification setup failed: {exc}",
                "docker_image": cfg.get("_resolved_docker_image"),
                "declared_docker_image": cfg.get("docker_image"),
                "resolved_docker_image": cfg.get("_resolved_docker_image"),
                "docker_image_resolution_source": cfg.get(
                    "_docker_image_resolution_source"
                ),
                "docker_image_registry_key": cfg.get("_docker_image_registry_key"),
                "runtime_java_version": cfg.get("runtime_java_version"),
            }
            if cfg.get("build_mode") == "maven":
                result[
                    "maven_dependency_plugin_version"
                ] = MAVEN_DEPENDENCY_PLUGIN_VERSION
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

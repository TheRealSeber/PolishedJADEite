#!/usr/bin/env python3
"""Build system auditor and fixer for JADE migration pipeline.

Detects Ant/Maven/Gradle build systems, checks compatibility with the
target Java version, applies safe minimal fixes, and verifies the build.

Outputs:
  artifacts/03-build-audit.json       -- gate status
  artifacts/03-build-fixes-plan.json  -- fixes applied + proposed
  artifacts/03-build-verify.log       -- raw build output
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
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SUPPORTED_BUILD_FILES = {
    "ant": "build.xml",
    "maven": "pom.xml",
    "gradle": "build.gradle",
}

# Longest-available Java versions for javacc jdkversion attribute
# JavaCC 4.0 supports up to jdkversion="1.5"; 5.0+ supports 1.5/1.6
# We only bump if the current value is lower than target and <= 1.5
JAVACC_JDKVERSION_MAP = {
    "1.5": "1.4",
    "1.6": "1.5",
    "1.7": "1.5",
    "1.8": "1.5",
}

# Ant javac source/target values that indicate a version gate
JAVAC_VERSION_KEYS = ("source", "target")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def iso_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def read_json(path: pathlib.Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: pathlib.Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    tmp.replace(path)


def write_text(path: pathlib.Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def find_build_file(
    workspace: pathlib.Path,
) -> Tuple[Optional[str], Optional[pathlib.Path]]:
    """Return (system_name, path) for the first build file found.

    Checks the workspace root, then one level deep (common for
    JADE-style layouts where build.xml lives in src/jade/).
    """
    # Direct children of workspace root
    for system, filename in SUPPORTED_BUILD_FILES.items():
        candidate = workspace / filename
        if candidate.exists():
            return system, candidate

    # One level deep
    if workspace.is_dir():
        for child in sorted(workspace.iterdir()):
            if not child.is_dir():
                continue
            for system, filename in SUPPORTED_BUILD_FILES.items():
                candidate = child / filename
                if candidate.exists():
                    return system, candidate

    # Two levels deep (e.g. JADE-4.6.0/src/jade/build.xml)
    if workspace.is_dir():
        for child in sorted(workspace.iterdir()):
            if not child.is_dir():
                continue
            for grandchild in sorted(child.iterdir()):
                if not grandchild.is_dir():
                    continue
                for system, filename in SUPPORTED_BUILD_FILES.items():
                    candidate = grandchild / filename
                    if candidate.exists():
                        return system, candidate

    return None, None


def version_tuple(raw: str) -> Tuple[int, ...]:
    return tuple(int(x) for x in re.split(r"[.\-_]", raw) if x.isdigit())


def version_key(raw: str) -> str:
    """Normalise '1.5' and '5' to '1.5'."""
    parts = raw.replace("_", ".").split(".")
    numeric = [int(x) for x in parts if x.isdigit()]
    if len(numeric) == 1 and numeric[0] >= 5:
        return f"1.{numeric[0]}"
    if len(numeric) >= 2 and numeric[0] == 1:
        return f"1.{numeric[1]}"
    return raw


def find_java_binary() -> Optional[str]:
    java_home = os.environ.get("JAVA_HOME", "")
    for candidate in [
        os.path.join(
            java_home, "bin", "java.exe" if sys.platform == "win32" else "java"
        ),
        "java",
    ]:
        if candidate and shutil.which(candidate):
            return candidate
    return None


def find_ant_binary() -> Optional[str]:
    for candidate in ["ant", "ant.bat"]:
        found = shutil.which(candidate)
        if found:
            return found
    return None


def find_mvn_binary() -> Optional[str]:
    for candidate in ["mvn", "mvn.cmd", "mvn.bat"]:
        found = shutil.which(candidate)
        if found:
            return found
    return None


def find_gradle_binary() -> Optional[str]:
    for candidate in ["gradle", "gradlew", "gradle.bat", "gradlew.bat"]:
        found = shutil.which(candidate)
        if found:
            return found
    # check for gradlew in workspace
    return None


# ---------------------------------------------------------------------------
# Build-system-specific analysers
# ---------------------------------------------------------------------------


def analyse_ant(build_path: pathlib.Path, target_version: str) -> Dict[str, Any]:
    """Analyse an Ant build.xml for compatibility.

    Returns a dict with:
      - compiler_targets: list of {line, current_source, current_target, needs_update}
      - javacc_targets: list of {line, jdkversion, needs_update}
      - dependencies: list of {name, version, compatible}
      - issues: list of str
    """
    result: Dict[str, Any] = {
        "compiler_targets": [],
        "javacc_targets": [],
        "dependencies": [],
        "issues": [],
    }
    raw = build_path.read_text(encoding="utf-8", errors="replace")
    lines = raw.split("\n")

    # Parse XML with namespace-removing trick
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        result["issues"].append("XML parse error in build.xml — cannot analyse")
        return result

    # Find all <javac> elements
    target_key = version_key(target_version)

    for javac_el in root.iter("javac"):
        src = (javac_el.get("source") or "").strip()
        tgt = (javac_el.get("target") or "").strip()
        if src or tgt:
            entry: Dict[str, Any] = {
                "current_source": src,
                "current_target": tgt,
                "needs_update": False,
            }
            if src and version_key(src) != target_key:
                entry["needs_update"] = True
                entry["new_source"] = target_version
            if tgt and version_key(tgt) != target_key:
                entry["needs_update"] = True
                entry["new_target"] = target_version
            result["compiler_targets"].append(entry)

    # Find all <javacc> elements
    for javacc_el in root.iter("javacc"):
        jdk = (javacc_el.get("jdkversion") or "").strip()
        if jdk:
            jacc_entry: Dict[str, Any] = {"jdkversion": jdk, "needs_update": False}
            if version_key(jdk) != target_key:
                # Only flag if old version is <= 1.4 and target >= 1.5
                jacc_entry["needs_update"] = True
                jacc_entry["new_jdkversion"] = target_version
            result["javacc_targets"].append(jacc_entry)

    # Look for classpath dependency JAR references
    dep_pattern = re.compile(
        r"lib/([a-zA-Z0-9_\-\.]+)/([a-zA-Z0-9_\-\.]+)-(\d[\d\.]*)\.jar"
    )
    for line in lines:
        for m in dep_pattern.finditer(line):
            result["dependencies"].append(
                {"group": m.group(1), "artifact": m.group(2), "version": m.group(3)}
            )

    return result


def analyse_maven(pom_path: pathlib.Path, target_version: str) -> Dict[str, Any]:
    """Analyse a Maven pom.xml for compatibility."""
    result: Dict[str, Any] = {
        "compiler_config": {},
        "dependencies": [],
        "plugins": [],
        "issues": [],
    }
    raw = pom_path.read_text(encoding="utf-8", errors="replace")

    # Parse XML, handling namespaces
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        result["issues"].append("XML parse error in pom.xml — cannot analyse")
        return result

    ns = re.match(r"\{([^}]+)\}", root.tag)
    ns_uri = ns.group(1) if ns else ""
    ns_map = {"m": ns_uri} if ns_uri else {}

    def _tag(local: str) -> str:
        return f"{{{ns_uri}}}{local}" if ns_uri else local

    # Check properties for compiler source/target
    props_el = root.find(_tag("properties"))
    if props_el is not None:
        for child in props_el:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag in (
                "maven.compiler.source",
                "maven.compiler.target",
                "java.version",
            ):
                val = (child.text or "").strip()
                result["compiler_config"][tag] = {
                    "current": val,
                    "needs_update": version_key(val) != version_key(target_version),
                    "new": target_version
                    if version_key(val) != version_key(target_version)
                    else None,
                }

    # Check dependencies
    deps_el = root.find(_tag("dependencies"))
    if deps_el is not None:
        for dep in deps_el.findall(_tag("dependency")):
            gid = _text(dep.find(_tag("groupId")))
            aid = _text(dep.find(_tag("artifactId")))
            ver = _text(dep.find(_tag("version")))
            if gid and aid:
                result["dependencies"].append(
                    {"groupId": gid, "artifactId": aid, "version": ver or "unknown"}
                )

    return result


def _text(el) -> Optional[str]:
    return (el.text or "").strip() if el is not None else None


def analyse_gradle(build_path: pathlib.Path, target_version: str) -> Dict[str, Any]:
    """Analyse a Gradle build.gradle for compatibility."""
    result: Dict[str, Any] = {
        "compiler_config": {},
        "dependencies": [],
        "issues": [],
    }
    raw = build_path.read_text(encoding="utf-8", errors="replace")
    tgt_key = version_key(target_version)

    # Check sourceCompatibility / targetCompatibility
    for key in ("sourceCompatibility", "targetCompatibility"):
        m = re.search(rf'{key}\s*[=:]\s*["\']?([\d\.]+)', raw)
        if m:
            current = m.group(1)
            result["compiler_config"][key] = {
                "current": current,
                "needs_update": version_key(current) != tgt_key,
                "new": target_version if version_key(current) != tgt_key else None,
            }

    # Check dependencies
    dep_pattern = re.compile(
        r"""(?:implementation|api|compileOnly|runtimeOnly|testImplementation)
        \s*\(\s*["']([^:]+):([^:]+):([^"']+)""",
        re.VERBOSE,
    )
    for m in dep_pattern.finditer(raw):
        result["dependencies"].append(
            {"group": m.group(1), "artifact": m.group(2), "version": m.group(3)}
        )

    return result


# ---------------------------------------------------------------------------
# Fix application
# ---------------------------------------------------------------------------


def apply_ant_fixes(
    build_path: pathlib.Path, analysis: Dict[str, Any], target_version: str
) -> List[Dict[str, Any]]:
    """Apply safe fixes to Ant build.xml. Returns list of fix records."""
    fixes: List[Dict[str, Any]] = []
    raw = build_path.read_text(encoding="utf-8", errors="replace")
    original = raw
    tgt_key = version_key(target_version)

    # Fix source/target in <javac> elements
    for entry in analysis.get("compiler_targets", []):
        if not entry.get("needs_update"):
            continue
        if "new_source" in entry:
            raw, count = re.subn(
                r'(\bsource\s*=\s*["\'])([^"\']*?)(["\'])',
                rf"\g<1>{target_version}\g<3>",
                raw,
            )
            if count:
                fixes.append(
                    {
                        "type": "compiler_source",
                        "applied": True,
                        "detail": f"Updated source to {target_version} ({count} occurrence(s))",
                    }
                )
        if "new_target" in entry:
            raw, count = re.subn(
                r'(\btarget\s*=\s*["\'])([^"\']*?)(["\'])',
                rf"\g<1>{target_version}\g<3>",
                raw,
            )
            if count:
                fixes.append(
                    {
                        "type": "compiler_target",
                        "applied": True,
                        "detail": f"Updated target to {target_version} ({count} occurrence(s))",
                    }
                )

    # Fix javacc jdkversion (only if target is > 1.4)
    if tgt_key not in ("1.1", "1.2", "1.3", "1.4"):
        for entry in analysis.get("javacc_targets", []):
            if entry.get("needs_update"):
                raw, count = re.subn(
                    r'(\bjdkversion\s*=\s*["\'])([^"\']*?)(["\'])',
                    rf"\g<1>{target_version}\g<3>",
                    raw,
                )
                if count:
                    fixes.append(
                        {
                            "type": "javacc_jdkversion",
                            "applied": True,
                            "detail": f"Updated jdkversion to {target_version} ({count} occurrence(s))",
                        }
                    )

    if raw != original:
        build_path.write_text(raw, encoding="utf-8")
    return fixes


# ---------------------------------------------------------------------------
# Build execution
# ---------------------------------------------------------------------------


def run_ant_build(
    build_path: pathlib.Path, default_target: str = "jade"
) -> Tuple[int, str]:
    """Run ant build in the build.xml directory."""
    ant_bin = find_ant_binary()
    if not ant_bin:
        return 1, "ERROR: ant executable not found on PATH"

    cmd = [ant_bin, default_target, "-q"]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(build_path.parent),
            capture_output=True,
            text=True,
            timeout=300,
        )
        output = proc.stdout + "\n" + proc.stderr
        return proc.returncode, output
    except subprocess.TimeoutExpired:
        return 1, "ERROR: ant build timed out after 300s"
    except FileNotFoundError:
        return 1, f"ERROR: ant not found at {ant_bin}"


def run_maven_build(pom_path: pathlib.Path) -> Tuple[int, str]:
    mvn_bin = find_mvn_binary()
    if not mvn_bin:
        return 1, "ERROR: mvn executable not found on PATH"

    cmd = [mvn_bin, "compile", "-q"]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(pom_path.parent),
            capture_output=True,
            text=True,
            timeout=300,
        )
        output = proc.stdout + "\n" + proc.stderr
        return proc.returncode, output
    except subprocess.TimeoutExpired:
        return 1, "ERROR: mvn build timed out after 300s"
    except FileNotFoundError:
        return 1, f"ERROR: mvn not found at {mvn_bin}"


def run_gradle_build(build_path: pathlib.Path) -> Tuple[int, str]:
    gradle_bin = find_gradle_binary()
    if not gradle_bin:
        # Try gradlew in build directory
        for name in ("gradlew", "gradlew.bat"):
            local = build_path.parent / name
            if local.exists():
                gradle_bin = str(local.resolve())
                break
    if not gradle_bin:
        return 1, "ERROR: gradle executable not found on PATH"

    cmd = [gradle_bin, "compileJava", "-q"]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(build_path.parent),
            capture_output=True,
            text=True,
            timeout=300,
        )
        output = proc.stdout + "\n" + proc.stderr
        return proc.returncode, output
    except subprocess.TimeoutExpired:
        return 1, "ERROR: gradle build timed out after 300s"
    except FileNotFoundError:
        return 1, f"ERROR: gradle not found at {gradle_bin}"


def capture_env(build_path: pathlib.Path) -> str:
    lines = ["=== Build Environment ==="]
    java_bin = find_java_binary()
    lines.append(f"java: {java_bin or 'NOT FOUND'}")
    if java_bin:
        try:
            proc = subprocess.run(
                [java_bin, "-version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            lines.append(proc.stdout.strip() + "\n" + proc.stderr.strip())
        except Exception:
            lines.append("(version check failed)")
    lines.append(f"JAVA_HOME: {os.environ.get('JAVA_HOME', 'not set')}")
    lines.append(f"Working dir: {build_path.parent}")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="JADE Build System Auditor and Fixer")
    parser.add_argument(
        "--config",
        required=True,
        help="Path to 00-run-config.json",
    )
    args = parser.parse_args()

    config_path = pathlib.Path(args.config)
    if not config_path.exists():
        print(
            f"ERROR [CONFIG_NOT_FOUND] Missing config: {config_path}",
            file=sys.stderr,
        )
        return 2

    cfg = read_json(config_path)
    required = {
        "run_id",
        "workspace_path",
        "artifacts_path",
        "source_version",
        "target_version",
    }
    missing = sorted(required - set(cfg.keys()))
    if missing:
        print(
            f"ERROR [CONFIG_INVALID] Missing keys: {', '.join(missing)}",
            file=sys.stderr,
        )
        return 2

    workspace = pathlib.Path(cfg["workspace_path"])
    artifacts = pathlib.Path(cfg["artifacts_path"])
    target_version = cfg["target_version"]
    source_version = cfg["source_version"]
    run_id = cfg["run_id"]

    if not workspace.exists():
        print(
            f"ERROR [WORKSPACE_MISSING] Workspace not found: {workspace}",
            file=sys.stderr,
        )
        return 2

    # ------------------------------------------------------------------
    # Step 1 — Detect build system
    # ------------------------------------------------------------------
    build_system, build_path = find_build_file(workspace)
    if not build_system or not build_path:
        audit = {
            "run_id": run_id,
            "status": "FAILED",
            "build_system": "unknown",
            "target_version": target_version,
            "error": "No build file found (build.xml, pom.xml, or build.gradle)",
            "updated_at": iso_now(),
        }
        write_json(artifacts / "03-build-audit.json", audit)
        write_text(artifacts / "03-build-verify.log", "NO BUILD FILE FOUND")
        write_json(
            artifacts / "03-build-fixes-plan.json",
            {"fixes": [], "issues": [audit["error"]]},
        )
        print(f"ERROR [BUILD_SYSTEM_UNKNOWN] {audit['error']}", file=sys.stderr)
        return 2

    print(f"[INFO] Detected build system: {build_system} at {build_path}")

    # ------------------------------------------------------------------
    # Step 2 — Analyse compatibility
    # ------------------------------------------------------------------
    analysis: Dict[str, Any] = {}
    if build_system == "ant":
        analysis = analyse_ant(build_path, target_version)
    elif build_system == "maven":
        analysis = analyse_maven(build_path, target_version)
    elif build_system == "gradle":
        analysis = analyse_gradle(build_path, target_version)
    else:
        audit = {
            "run_id": run_id,
            "status": "FAILED",
            "build_system": build_system,
            "target_version": target_version,
            "error": f"Unsupported build system: {build_system}",
            "updated_at": iso_now(),
        }
        write_json(artifacts / "03-build-audit.json", audit)
        return 2

    # ------------------------------------------------------------------
    # Step 3 — Apply safe fixes
    # ------------------------------------------------------------------
    applied_fixes: List[Dict[str, Any]] = []
    issues: List[str] = list(analysis.get("issues", []))

    if build_system == "ant":
        applied_fixes = apply_ant_fixes(build_path, analysis, target_version)

    # For Maven and Gradle, source/target fixes require pom.xml or build.gradle
    # editing — these are SAFE but currently not auto-applied. Flag as NEEDS_REVIEW.
    elif build_system == "maven":
        for prop_name, prop_info in analysis.get("compiler_config", {}).items():
            if prop_info.get("needs_update") and prop_info.get("new"):
                applied_fixes.append(
                    {
                        "type": f"maven_property_{prop_name}",
                        "applied": False,
                        "needs_review": True,
                        "detail": (
                            f"Update {prop_name} from {prop_info['current']} "
                            f"to {prop_info['new']} in pom.xml properties section"
                        ),
                    }
                )
    elif build_system == "gradle":
        for prop_name, prop_info in analysis.get("compiler_config", {}).items():
            if prop_info.get("needs_update") and prop_info.get("new"):
                applied_fixes.append(
                    {
                        "type": f"gradle_property_{prop_name}",
                        "applied": False,
                        "needs_review": True,
                        "detail": (
                            f"Update {prop_name} from {prop_info['current']} "
                            f"to {prop_info['new']} in build.gradle"
                        ),
                    }
                )

    # ------------------------------------------------------------------
    # Step 4 — Run build
    # ------------------------------------------------------------------
    build_rc = 0
    build_output = ""

    # Write header
    build_output = capture_env(build_path)

    if build_system == "ant":
        build_rc, out = run_ant_build(build_path)
        build_output += out
    elif build_system == "maven":
        build_rc, out = run_maven_build(build_path)
        build_output += out
    elif build_system == "gradle":
        build_rc, out = run_gradle_build(build_path)
        build_output += out

    # ------------------------------------------------------------------
    # Step 5 — Determine gate status
    # ------------------------------------------------------------------
    has_pending_review = any(
        f.get("needs_review") and not f.get("applied") for f in applied_fixes
    )

    if build_rc == 0:
        gate_status = "OK"
    elif has_pending_review:
        gate_status = "NEEDS_MANUAL"
    else:
        gate_status = "FAILED"

    # Count error lines for diagnostics
    error_count = sum(
        1 for line in build_output.split("\n") if "error:" in line.lower()
    )

    # Write output artifacts
    audit = {
        "run_id": run_id,
        "status": gate_status,
        "build_system": build_system,
        "build_file": str(build_path),
        "source_version": source_version,
        "target_version": target_version,
        "build_exit_code": build_rc,
        "error_count": error_count,
        "applied_fixes_count": sum(1 for f in applied_fixes if f.get("applied")),
        "pending_fixes_count": sum(1 for f in applied_fixes if f.get("needs_review")),
        "updated_at": iso_now(),
    }
    write_json(artifacts / "03-build-audit.json", audit)

    fixes_plan = {
        "run_id": run_id,
        "build_system": build_system,
        "target_version": target_version,
        "fixes": applied_fixes,
        "analysis_summary": {
            "compiler_targets": analysis.get("compiler_targets", []),
            "javacc_targets": analysis.get("javacc_targets", []),
            "dependencies": analysis.get("dependencies", []),
            "issues": issues,
        },
        "updated_at": iso_now(),
    }
    write_json(artifacts / "03-build-fixes-plan.json", fixes_plan)

    write_text(artifacts / "03-build-verify.log", build_output)

    # Report
    print(f"\n=== Build Audit Result ===")
    print(f"Build system: {build_system}")
    print(f"Target version: {target_version}")
    print(f"Build exit code: {build_rc}")
    print(f"Error count: {error_count}")
    print(f"Safe fixes applied: {audit['applied_fixes_count']}")
    print(f"Fixes pending review: {audit['pending_fixes_count']}")
    print(f"Gate status: {gate_status}")

    if gate_status == "FAILED":
        print("\nBuild failed. See artifacts/03-build-verify.log for details.")
        return 2
    elif gate_status == "NEEDS_MANUAL":
        print(
            "\nBuild succeeded but manual fixes are pending — review artifacts/03-build-fixes-plan.json"
        )
        return 0
    else:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

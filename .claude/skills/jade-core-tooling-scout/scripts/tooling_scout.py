#!/usr/bin/env python3
"""JADE Tooling Scout -- probe, run, collect, merge.

Discovers what can be auto-assisted by OpenRewrite, PMD, and Checkstyle
before manual scanner work.  Never rewrites code -- discovery/report only.

Engine runs on a modern JDK (JAVA_HOME=$modern_jdk_path), target is a
legacy workspace.  Modern JDK used only to execute tool binaries;
tools are configured to analyze the legacy source level.
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
import traceback
from typing import Any, Dict, List, Optional, Tuple


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


def resolve_bin(name: str) -> Optional[str]:
    return shutil.which(name)


def run_cmd(
    cmd: List[str],
    *,
    cwd: Optional[pathlib.Path] = None,
    env: Optional[Dict[str, str]] = None,
    timeout: int = 120,
) -> Tuple[int, str, str]:
    try:
        p = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        return p.returncode, (p.stdout or ""), (p.stderr or "")
    except FileNotFoundError:
        return -1, "", f"binary not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return -2, "", f"timeout after {timeout}s: {chr(39).join(cmd)}"
    except Exception as exc:
        return -3, "", str(exc)


def os_pathsep() -> str:
    return ";" if sys.platform == "win32" else ":"


def java_home_env(jdk_path: pathlib.Path) -> Dict[str, str]:
    env = dict(os.environ)
    env["JAVA_HOME"] = str(jdk_path)
    env["PATH"] = str(jdk_path / "bin") + os_pathsep() + env.get("PATH", "")
    return env


def check_jdk(jdk_path: pathlib.Path) -> Optional[str]:
    java_bin = jdk_path / "bin" / ("java.exe" if sys.platform == "win32" else "java")
    if not java_bin.exists():
        return f"java binary not found at {java_bin}"
    env = java_home_env(jdk_path)
    code, out, err = run_cmd([str(java_bin), "-version"], env=env)
    if code != 0:
        return f"java -version failed: {err or out}"
    combined = (err + out).lower()
    version = None
    for part in combined.splitlines():
        s = part.strip()
        if s and "version" in s:
            version = s
            break
    if not version:
        return f"could not parse Java version from: {combined[:200]}"
    for token in version.replace(chr(34), " ").split():
        if token and token[0].isdigit():
            try:
                major = int(token.split(".")[0])
                if major < 11:
                    return f"JDK {major} too old; need 11+ (detected: {version})"
                return None
            except ValueError:
                continue
    return f"could not determine major version from: {version}"


TOOL_NAMES = ["openrewrite", "pmd", "checkstyle"]


def probe_openrewrite(workspace: pathlib.Path, env: Dict[str, str]) -> Dict[str, Any]:
    result: Dict[str, Any] = {"available": False, "version": None, "reason": ""}
    mvn = resolve_bin("mvn") or resolve_bin("mvnw")
    gradle = resolve_bin("gradle") or resolve_bin("gradlew")
    rewrite_configs = list(workspace.glob("**/rewrite.y*ml")) + list(
        workspace.glob("**/.rewrite/**")
    )

    if not mvn and not gradle and not rewrite_configs:
        result["reason"] = "no maven/gradle/rewrite.yml detected"
        return result

    if mvn:
        pom = workspace / "pom.xml"
        if pom.exists():
            code, out, err = run_cmd(
                [str(mvn), "org.openrewrite.maven:rewrite-maven-plugin:discover", "-q"],
                cwd=workspace,
                env=env,
                timeout=60,
            )
            if code == 0:
                result["available"] = True
                result["discover_output"] = out
            else:
                result["reason"] = (
                    f"mvn rewrite:discover failed (exit {code}): {err[:500]}"
                )
        else:
            result["reason"] = "maven found but no pom.xml in workspace"

    if gradle and not result["available"]:
        build_file = workspace / "build.gradle"
        if not build_file.exists():
            build_file = workspace / "build.gradle.kts"
        if build_file.exists() or list(workspace.glob("*.gradle*")):
            code, out, err = run_cmd(
                [str(gradle), "rewriteDiscover", "--dry-run"],
                cwd=workspace,
                env=env,
                timeout=60,
            )
            if code == 0:
                result["available"] = True
                result["discover_output"] = out
            else:
                prev = result.get("reason", "")
                result["reason"] = (
                    prev + f" | gradle rewriteDiscover failed (exit {code})"
                )
        else:
            prev = result.get("reason", "")
            result["reason"] = prev + " | no build.gradle in workspace"

    if not result["available"] and rewrite_configs:
        result["available"] = True
        result["reason"] = ""

    return result


def probe_pmd(env: Dict[str, str]) -> Dict[str, Any]:
    result: Dict[str, Any] = {"available": False, "version": None, "reason": ""}
    pmd = resolve_bin("pmd")
    if pmd:
        code, out, err = run_cmd([str(pmd), "--version"], env=env, timeout=15)
        if code == 0:
            result["available"] = True
            result["version"] = (out + err).strip().splitlines()[0].strip()
        else:
            result["reason"] = f"pmd --version failed (exit {code})"
    else:
        result["reason"] = "pmd binary not on PATH"
    return result


def probe_checkstyle(env: Dict[str, str]) -> Dict[str, Any]:
    result: Dict[str, Any] = {"available": False, "version": None, "reason": ""}
    cs = resolve_bin("checkstyle")
    if not cs:
        for candidate in [
            pathlib.Path("checkstyle/checkstyle-all.jar"),
            pathlib.Path("tools/checkstyle/checkstyle-all.jar"),
            pathlib.Path("~/.checkstyle/checkstyle-all.jar").expanduser(),
        ]:
            if candidate.exists():
                result["available"] = True
                result["jar_path"] = str(candidate)
                return result
        result["reason"] = "checkstyle binary/jar not found"
        return result
    code, out, err = run_cmd([str(cs), "--version"], env=env, timeout=15)
    if code == 0:
        result["available"] = True
        result["version"] = (out + err).strip().splitlines()[0].strip()
    else:
        result["reason"] = f"checkstyle --version failed (exit {code})"
    return result


def run_openrewrite_discover(
    workspace: pathlib.Path, env: Dict[str, str]
) -> List[Dict[str, Any]]:
    """Dry-run OpenRewrite discovery, return parsed recipe list."""
    recipes: List[Dict[str, Any]] = []
    mvn = resolve_bin("mvn") or resolve_bin("mvnw")

    if mvn:
        code, out, err = run_cmd(
            [
                str(mvn),
                "org.openrewrite.maven:rewrite-maven-plugin:discover",
                "-Ddetail=true",
                "-q",
            ],
            cwd=workspace,
            env=env,
            timeout=120,
        )
        if code == 0 and out.strip():
            for line in out.splitlines():
                s = line.strip()
                if s and not s.startswith("[INFO]") and not s.startswith("[WARNING]"):
                    recipes.append(
                        {
                            "name": s.split()[0] if s.split() else s,
                            "status": "applicable",
                            "description": s,
                        }
                    )
        elif code == 0:
            recipes.append(
                {
                    "name": "openrewrite:discover",
                    "status": "not_applicable",
                    "description": "discover ran but returned no recipes",
                }
            )

    for yml_file in workspace.glob("**/rewrite.y*ml"):
        try:
            content = yml_file.read_text(encoding="utf-8")
            for line in content.splitlines():
                s = line.strip()
                if s.startswith("-") and "org.openrewrite" in s:
                    name = s.lstrip("- ").strip()
                    recipes.append(
                        {
                            "name": name,
                            "status": "applicable",
                            "description": f"registered in {yml_file.name}",
                        }
                    )
        except Exception:
            pass

    return recipes


def run_pmd_scan(
    workspace: pathlib.Path,
    env: Dict[str, str],
    source_version: str,
    target_version: str,
) -> List[Dict[str, Any]]:
    """Run PMD rules against workspace, return violations."""
    violations: List[Dict[str, Any]] = []
    pmd = resolve_bin("pmd")
    if not pmd:
        return violations

    rulesets = [
        "category/java/bestpractices.xml",
        "category/java/codestyle.xml/UnnecessaryImport",
        "category/java/codestyle.xml/UnnecessaryFullyQualifiedName",
        "category/java/errorprone.xml",
    ]
    java_files = list(workspace.rglob("*.java"))
    if not java_files:
        return violations

    file_list_path = workspace / ".pmd_filelist.txt"
    try:
        file_list_path.write_text(
            "\n".join(str(f) for f in java_files), encoding="utf-8"
        )
        ruleset_arg = ",".join(rulesets)
        code, out, err = run_cmd(
            [
                str(pmd),
                "check",
                "--file-list",
                str(file_list_path),
                "--rulesets",
                ruleset_arg,
                "--format",
                "json",
                "--no-cache",
            ],
            env=env,
            timeout=300,
        )
        if code in (0, 4) and out.strip():
            try:
                data = json.loads(out)
                for file_entry in data.get("files", []):
                    file_path = file_entry.get("filename", "")
                    for v in file_entry.get("violations", []):
                        violations.append(
                            {
                                "file": _rel_path(file_path, workspace),
                                "line": v.get("beginline", 0),
                                "rule": v.get("rule", ""),
                                "ruleset": v.get("ruleset", ""),
                                "priority": v.get("priority", 0),
                                "description": v.get("description", ""),
                            }
                        )
            except json.JSONDecodeError:
                pass
    finally:
        try:
            file_list_path.unlink(missing_ok=True)
        except Exception:
            pass

    return violations


def run_checkstyle_scan(
    workspace: pathlib.Path, env: Dict[str, str]
) -> List[Dict[str, Any]]:
    violations: List[Dict[str, Any]] = []
    cs = resolve_bin("checkstyle")
    if not cs:
        return violations

    java_files = list(workspace.rglob("*.java"))
    if not java_files:
        return violations

    config_xml = workspace / ".checkstyle_migration.xml"
    config_content = """<?xml version="1.0"?>
<!DOCTYPE module PUBLIC
  "-//Checkstyle//DTD Checkstyle Configuration 1.3//EN"
  "https://checkstyle.org/dtds/configuration_1_3.dtd">
<module name="Checker">
  <module name="TreeWalker">
    <module name="UnusedImports"/>
    <module name="RedundantImport"/>
    <module name="IllegalImport">
      <property name="illegalPkgs" value="sun.*, com.sun.*"/>
    </module>
    <module name="RegexpSinglelineJava">
      <property name="format" value="@Deprecated"/>
      <property name="message" value="Deprecated API usage"/>
    </module>
    <module name="RegexpSinglelineJava">
      <property name="format" value="com\.sun\.(jvmdi|jvmpi)"/>
      <property name="message" value="JVMDI/JVMPI reference (removed in Java 6)"/>
    </module>
  </module>
</module>"""
    try:
        config_xml.write_text(config_content, encoding="utf-8")
        code, out, err = run_cmd(
            [str(cs), "-c", str(config_xml), "-f", "json", str(workspace)],
            env=env,
            timeout=300,
        )
        if out.strip():
            try:
                data = json.loads(out)
                for file_entry in data.get("files", []):
                    file_path = file_entry.get("name", "")
                    for err_item in file_entry.get("errors", []):
                        violations.append(
                            {
                                "file": _rel_path(file_path, workspace),
                                "line": err_item.get("line", 0),
                                "check": err_item.get("source", ""),
                                "severity": err_item.get("severity", "error"),
                                "message": err_item.get("message", ""),
                            }
                        )
            except json.JSONDecodeError:
                pass
    finally:
        try:
            config_xml.unlink(missing_ok=True)
        except Exception:
            pass

    return violations


def _rel_path(absolute: str, base: pathlib.Path) -> str:
    try:
        return str(pathlib.Path(absolute).relative_to(base))
    except ValueError:
        return absolute


def merge_into_manifest(
    manifest_path: pathlib.Path,
    findings: Dict[str, Any],
    tool_probes: Dict[str, Dict[str, Any]],
) -> int:
    manifest = read_json(manifest_path)
    existing: List[Dict[str, Any]] = manifest.get("rules", [])
    existing_ids = {r.get("rule_id", "") for r in existing}
    new_entries: List[Dict[str, Any]] = []
    ts = iso_now()

    # OpenRewrite recipes
    or_data = findings.get("openrewrite", {})
    if or_data.get("available"):
        for recipe in or_data.get("recipes", []):
            rid = f"tooling:openrewrite:{recipe.get('name', 'unknown')}"
            if rid in existing_ids:
                continue
            new_entries.append(
                {
                    "rule_id": rid,
                    "source": "tooling-scout",
                    "provenance": {
                        "tool": "openrewrite",
                        "tool_version": tool_probes.get("openrewrite", {}).get(
                            "version"
                        ),
                        "detected_at": ts,
                        "confidence": "high"
                        if recipe.get("status") == "applicable"
                        else "medium",
                    },
                    "description": recipe.get("description", ""),
                    "auto_fixable": True,
                }
            )

    # PMD violations grouped by rule
    pmd_data = findings.get("pmd", {})
    if pmd_data.get("available"):
        seen_rules: set = set()
        for v in pmd_data.get("violations", []):
            rule_name = v.get("rule", "unknown")
            if rule_name in seen_rules:
                continue
            seen_rules.add(rule_name)
            rid = f"tooling:pmd:{rule_name}"
            if rid in existing_ids:
                continue
            new_entries.append(
                {
                    "rule_id": rid,
                    "source": "tooling-scout",
                    "provenance": {
                        "tool": "pmd",
                        "tool_version": tool_probes.get("pmd", {}).get("version"),
                        "detected_at": ts,
                        "confidence": "medium",
                    },
                    "description": f"PMD {rule_name} violation(s) detected",
                    "auto_fixable": False,
                }
            )

    # Checkstyle violations grouped by check
    cs_data = findings.get("checkstyle", {})
    if cs_data.get("available"):
        seen_checks: set = set()
        for v in cs_data.get("violations", []):
            check_name = v.get("check", "unknown")
            if check_name in seen_checks:
                continue
            seen_checks.add(check_name)
            rid = f"tooling:checkstyle:{check_name}"
            if rid in existing_ids:
                continue
            new_entries.append(
                {
                    "rule_id": rid,
                    "source": "tooling-scout",
                    "provenance": {
                        "tool": "checkstyle",
                        "tool_version": tool_probes.get("checkstyle", {}).get(
                            "version"
                        ),
                        "detected_at": ts,
                        "confidence": "low",
                    },
                    "description": f"Checkstyle {check_name} violation(s) detected",
                    "auto_fixable": False,
                }
            )

    manifest["rules"] = existing + new_entries
    write_json(manifest_path, manifest)
    return len(new_entries)


def main() -> int:
    parser = argparse.ArgumentParser(description="JADE Tooling Scout")
    parser.add_argument(
        "--modern-jdk", required=True, help="Path to modern JDK (11/17+)"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--validate", action="store_true", help="Validate inputs and JDK only"
    )
    mode.add_argument(
        "--probe", action="store_true", help="Probe tool availability only"
    )
    mode.add_argument(
        "--run", action="store_true", help="Probe + run tools + write reports"
    )
    mode.add_argument(
        "--merge",
        action="store_true",
        help="Merge findings into manifest (needs prior --run)",
    )
    mode.add_argument(
        "--all",
        action="store_true",
        help="Full pipeline: validate -> probe -> run -> merge",
    )
    args = parser.parse_args()

    # --- Validate JDK ---
    modern_jdk = pathlib.Path(args.modern_jdk).resolve()
    jdk_err = check_jdk(modern_jdk)
    if jdk_err:
        print(f"ERROR [JDK_UNUSABLE] {jdk_err}", file=sys.stderr)
        return 3
    env = java_home_env(modern_jdk)

    # --- Locate config ---
    config_path = pathlib.Path("artifacts/00-run-config.json")
    if not config_path.exists():
        print(f"ERROR [CONFIG_NOT_FOUND] Missing: {config_path}", file=sys.stderr)
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

    run_id: str = cfg["run_id"]
    workspace = pathlib.Path(cfg["workspace_path"])
    artifacts_dir = pathlib.Path(cfg["artifacts_path"])
    source_version: str = cfg["source_version"]
    target_version: str = cfg["target_version"]
    manifest_path = artifacts_dir / "01-breaking-changes-manifest.json"

    if args.validate:
        if not workspace.exists():
            print(f"ERROR [WORKSPACE_MISSING] {workspace}", file=sys.stderr)
            return 2
        if not manifest_path.exists():
            print(f"ERROR [MANIFEST_MISSING] {manifest_path}", file=sys.stderr)
            return 2
        print(
            f"OK: JDK {modern_jdk} validated, workspace={workspace}, artifacts={artifacts_dir}"
        )
        return 0

    # --- Probe tools ---
    tool_probes: Dict[str, Dict[str, Any]] = {}
    tool_probes["openrewrite"] = probe_openrewrite(workspace, env)
    tool_probes["pmd"] = probe_pmd(env)
    tool_probes["checkstyle"] = probe_checkstyle(env)

    available_tools = [t for t in TOOL_NAMES if tool_probes[t]["available"]]
    unavailable_tools = [t for t in TOOL_NAMES if not tool_probes[t]["available"]]

    if args.probe:
        print(
            json.dumps(
                {
                    "available_tools": available_tools,
                    "unavailable_tools": unavailable_tools,
                    "details": {t: tool_probes[t] for t in TOOL_NAMES},
                },
                indent=2,
            )
        )
        return 0

    # --- Run tools ---
    findings: Dict[str, Any] = {
        "run_id": run_id,
        "source_version": source_version,
        "target_version": target_version,
        "workspace_path": str(workspace),
        "openrewrite": {"available": False, "version": None, "recipes": []},
        "pmd": {"available": False, "version": None, "violations": []},
        "checkstyle": {"available": False, "version": None, "violations": []},
    }

    if tool_probes["openrewrite"]["available"]:
        print("Running OpenRewrite discover (dry-run)...", file=sys.stderr)
        recipes = run_openrewrite_discover(workspace, env)
        findings["openrewrite"] = {
            "available": True,
            "version": tool_probes["openrewrite"].get("version"),
            "recipes": recipes,
        }

    if tool_probes["pmd"]["available"]:
        print("Running PMD scan...", file=sys.stderr)
        violations = run_pmd_scan(workspace, env, source_version, target_version)
        findings["pmd"] = {
            "available": True,
            "version": tool_probes["pmd"].get("version"),
            "violations": violations,
        }

    if tool_probes["checkstyle"]["available"]:
        print("Running Checkstyle scan...", file=sys.stderr)
        violations = run_checkstyle_scan(workspace, env)
        findings["checkstyle"] = {
            "available": True,
            "version": tool_probes["checkstyle"].get("version"),
            "violations": violations,
        }

    # Write findings
    write_json(artifacts_dir / "02-linter-findings.json", findings)

    # Build summary report
    or_recipes = findings["openrewrite"].get("recipes", [])
    or_applicable = sum(1 for r in or_recipes if r.get("status") == "applicable")

    report = {
        "run_id": run_id,
        "modern_jdk": str(modern_jdk),
        "available_tools": available_tools,
        "unavailable_tools": unavailable_tools,
        "findings_summary": {
            "openrewrite": {
                "recipes_total": len(or_recipes),
                "recipes_applicable": or_applicable,
                "recipes_not_applicable": len(or_recipes) - or_applicable,
            },
            "pmd": {
                "violations_total": len(findings["pmd"].get("violations", [])),
                "rulesets_used": [
                    "category/java/bestpractices.xml",
                    "category/java/codestyle.xml",
                    "category/java/errorprone.xml",
                ],
            },
            "checkstyle": {
                "violations_total": len(findings["checkstyle"].get("violations", [])),
                "checks_triggered": sorted(
                    set(
                        v.get("check", "")
                        for v in findings["checkstyle"].get("violations", [])
                    )
                ),
            },
        },
        "manifest_merge_count": 0,
        "updated_at": iso_now(),
    }
    write_json(artifacts_dir / "02-tooling-scout-report.json", report)

    if args.run:
        print(f"Reports written to {artifacts_dir}")
        return 0

    # --- Merge into manifest ---
    if args.merge or args.all:
        if not manifest_path.exists():
            print(
                f"ERROR [MANIFEST_MISSING] Cannot merge: {manifest_path}",
                file=sys.stderr,
            )
            return 2
        merged = merge_into_manifest(manifest_path, findings, tool_probes)
        report["manifest_merge_count"] = merged
        report["updated_at"] = iso_now()
        write_json(artifacts_dir / "02-tooling-scout-report.json", report)
        print(f"Merged {merged} entries into manifest")

    print("DONE")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        traceback.print_exc(file=sys.stderr)
        raise SystemExit(1)

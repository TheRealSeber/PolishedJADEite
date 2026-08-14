#!/usr/bin/env python3
"""Create and register a migration recipe in the canonical registry layout."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import sys
import tempfile
from typing import Dict


BUCKETS = {"1.5-to-1.6", "1.7", "1.7-to-1.8", "shared"}
REGISTRY_SCRIPT_PREFIX = ".claude/skills/java-migration-skill-registry"
REQUIRED_ENTRY_FIELDS = ("skill", "script", "description")


def _safe_segment(value: str, label: str) -> None:
    path = pathlib.PurePath(value)
    if not value or len(path.parts) != 1 or path.parts[0] in {".", ".."}:
        raise ValueError(f"{label} must be one path segment")
    if path.is_absolute() or "/" in value or "\\" in value:
        raise ValueError(f"{label} must not contain path separators")


def _validate_registry(registry: Dict, registry_root: pathlib.Path) -> None:
    prefix = pathlib.PurePosixPath(REGISTRY_SCRIPT_PREFIX).parts
    for rule_id, entry in registry.items():
        if isinstance(rule_id, str) and rule_id.startswith("_"):
            continue
        if not isinstance(rule_id, str) or not rule_id:
            raise ValueError("invalid registry entry: rule_id must be a non-empty string")
        if not isinstance(entry, dict):
            raise ValueError(f"invalid registry entry {rule_id}: expected object")
        missing = [field for field in REQUIRED_ENTRY_FIELDS if field not in entry]
        if missing:
            raise ValueError(
                f"invalid registry entry {rule_id}: missing {', '.join(missing)}"
            )
        if any(
            not isinstance(entry[field], str) or not entry[field].strip()
            for field in REQUIRED_ENTRY_FIELDS
        ):
            raise ValueError(f"invalid registry entry {rule_id}: fields must be non-empty strings")

        script = entry["script"]
        script_path = pathlib.PurePosixPath(script)
        if (
            "\\" in script
            or script_path.is_absolute()
            or ".." in script_path.parts
            or script_path.parts[: len(prefix)] != prefix
            or len(script_path.parts) <= len(prefix)
        ):
            raise ValueError(f"invalid registry entry {rule_id}: unsafe script path")
        resolved_script = registry_root.joinpath(*script_path.parts[len(prefix) :])
        if not resolved_script.is_file():
            raise ValueError(f"invalid registry entry {rule_id}: script does not exist")


def _read_registry(path: pathlib.Path, registry_root: pathlib.Path) -> Dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid registry: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("registry root must be a JSON object")
    _validate_registry(payload, registry_root)
    return payload


def _write_json_atomic(path: pathlib.Path, payload: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = pathlib.Path(raw_tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _stage_recipe_files(
    recipe_dir: pathlib.Path,
    recipe_name: str,
    description: str,
    source_dir: pathlib.Path | None,
) -> pathlib.Path:
    temp_dir = pathlib.Path(tempfile.mkdtemp(prefix=f".{recipe_name}.", dir=recipe_dir.parent))
    try:
        if source_dir is not None:
            source_skill = source_dir / "SKILL.md"
            source_script = source_dir / "scripts" / "apply.py"
            if not source_skill.is_file() or not source_script.is_file():
                raise ValueError("--source-dir must contain SKILL.md and scripts/apply.py")
            shutil.copy2(source_skill, temp_dir / "SKILL.md")
            (temp_dir / "scripts").mkdir()
            shutil.copy2(source_script, temp_dir / "scripts" / "apply.py")
        else:
            (temp_dir / "SKILL.md").write_text(
                f"# {recipe_name}\n\n{description}\n\nInvoked by the migration rule dispatcher.\n",
                encoding="utf-8",
            )
            scripts_dir = temp_dir / "scripts"
            scripts_dir.mkdir()
            (scripts_dir / "apply.py").write_text(
                "#!/usr/bin/env python3\n"
                'import argparse, json\n\n'
                'parser = argparse.ArgumentParser()\n'
                'parser.add_argument("--file", required=True)\n'
                'parser.add_argument("--line", required=True, type=int)\n'
                "parser.parse_args()\n"
                'print(json.dumps({"status": "SKIPPED", "changes": 0, "warnings": [], "errors": []}))\n',
                encoding="utf-8",
            )
        return temp_dir
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def register_recipe(
    *,
    registry_path: pathlib.Path,
    registry_root: pathlib.Path,
    recipe_name: str,
    bucket: str,
    rule_id: str,
    description: str,
    source_dir: pathlib.Path | None = None,
    force: bool = False,
) -> str:
    _safe_segment(recipe_name, "recipe-name")
    _safe_segment(bucket, "bucket")
    if bucket not in BUCKETS:
        raise ValueError(f"bucket must be one of: {', '.join(sorted(BUCKETS))}")
    if not rule_id or not description:
        raise ValueError("rule-id and description are required")

    registry = _read_registry(registry_path, registry_root)
    recipe_dir = registry_root / bucket / recipe_name
    script = f"{REGISTRY_SCRIPT_PREFIX}/{bucket}/{recipe_name}/scripts/apply.py"
    entry = {"skill": recipe_name, "script": script, "description": description}
    existing_entry = registry.get(rule_id)

    if recipe_dir.exists() and not force:
        if existing_entry == entry and (recipe_dir / "SKILL.md").is_file() and (recipe_dir / "scripts" / "apply.py").is_file():
            return "unchanged"
        raise FileExistsError(f"recipe already exists: {recipe_dir}")
    if existing_entry is not None and existing_entry != entry and not force:
        raise FileExistsError(f"rule already registered: {rule_id}")

    recipe_dir.parent.mkdir(parents=True, exist_ok=True)
    staged_dir = _stage_recipe_files(recipe_dir, recipe_name, description, source_dir)
    backup_dir: pathlib.Path | None = None
    try:
        if recipe_dir.exists():
            backup_dir = pathlib.Path(tempfile.mkdtemp(prefix=f".{recipe_name}.backup.", dir=recipe_dir.parent))
            shutil.rmtree(backup_dir)
            os.replace(recipe_dir, backup_dir)
        os.replace(staged_dir, recipe_dir)
        registry[rule_id] = entry
        _validate_registry(registry, registry_root)
        _write_json_atomic(registry_path, registry)
    except Exception:
        shutil.rmtree(staged_dir, ignore_errors=True)
        if recipe_dir.exists():
            shutil.rmtree(recipe_dir, ignore_errors=True)
        if backup_dir is not None and backup_dir.exists():
            os.replace(backup_dir, recipe_dir)
        raise
    else:
        if backup_dir is not None:
            shutil.rmtree(backup_dir)
    return "updated" if force and (recipe_dir.exists() or existing_entry is not None) else "created"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe-name", required=True)
    parser.add_argument("--bucket", required=True, choices=sorted(BUCKETS))
    parser.add_argument("--rule-id", required=True)
    parser.add_argument("--description", required=True)
    parser.add_argument("--source-dir", type=pathlib.Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    repo_root = pathlib.Path(__file__).resolve().parents[4]
    registry_root = repo_root / ".claude/skills/java-migration-skill-registry"
    registry_path = repo_root / ".claude/skills/jade-core-rule-dispatcher/recipe-registry.json"
    try:
        result = register_recipe(
            registry_path=registry_path,
            registry_root=registry_root,
            recipe_name=args.recipe_name,
            bucket=args.bucket,
            rule_id=args.rule_id,
            description=args.description,
            source_dir=args.source_dir.resolve() if args.source_dir else None,
            force=args.force,
        )
    except (FileExistsError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"{result}: {args.recipe_name} ({args.rule_id})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Recipe registry mode resolution shared by the dispatcher and the registrar.

A registry entry is either a *script* recipe -- the historical form, carrying a
canonical ``scripts/apply.py`` path that the dispatcher runs as a subprocess --
or an *agent* recipe, carrying a canonical ``SKILL.md`` that the dispatcher
hands to a subagent through the shard contract. An entry with no ``mode`` key
is a script recipe, so registries written before agent mode existed keep
validating and dispatching exactly as they did.

This module holds only the resolution and validation rules. It never reads a
task, never touches a workspace file, and never launches anything.
"""

from __future__ import annotations

import pathlib
from typing import Any, Optional

RECIPE_MODES = ("script", "agent")
DEFAULT_RECIPE_MODE = "script"

REGISTRY_PREFIX = (".claude", "skills", "java-migration-skill-registry")
REGISTRY_BUCKETS = {"1.5-to-1.6", "1.7", "1.7-to-1.8", "8-to-11", "shared"}

REQUIRED_SCRIPT_FIELDS = ("skill", "script", "description")
REQUIRED_AGENT_FIELDS = ("skill", "skill_md", "description")


def entry_mode(entry: Any) -> str:
    """Return the mode of *entry*, defaulting to ``script``.

    Raises ValueError for a non-object entry or an unknown mode value, so a
    typo in the registry fails loudly instead of silently dispatching down the
    script path.
    """
    if not isinstance(entry, dict):
        raise ValueError("Recipe registry entry must be a JSON object")
    mode = entry.get("mode")
    if mode is None:
        return DEFAULT_RECIPE_MODE
    if mode in RECIPE_MODES:
        return mode
    raise ValueError(
        f"Recipe registry entry 'mode' must be one of {RECIPE_MODES}: {mode!r}"
    )


def check_skill_md_string(skill_md: Any) -> Optional[str]:
    """Validate a ``skill_md`` value as a string. Returns a reason, or None.

    Purely lexical -- no filesystem access -- so the same check can run against
    a registry that references recipes not present in this checkout.
    """
    if not isinstance(skill_md, str) or not skill_md.strip():
        return "'skill_md' must be a non-empty string"
    if "\\" in skill_md:
        return "'skill_md' must use forward slashes"
    path = pathlib.PurePosixPath(skill_md)
    if path.is_absolute():
        return "'skill_md' must be a repository-relative path"
    parts = path.parts
    if parts[: len(REGISTRY_PREFIX)] != REGISTRY_PREFIX:
        return "'skill_md' must live under the migration skill registry"
    if len(parts) != len(REGISTRY_PREFIX) + 3 or parts[-1] != "SKILL.md":
        return "'skill_md' must be <bucket>/<recipe>/SKILL.md"
    bucket, recipe_name = parts[len(REGISTRY_PREFIX) : len(REGISTRY_PREFIX) + 2]
    if bucket not in REGISTRY_BUCKETS:
        return f"unknown registry bucket: {bucket}"
    if recipe_name in {".", ".."} or not recipe_name:
        return "unsafe recipe directory name"
    canonical = "/".join((*REGISTRY_PREFIX, bucket, recipe_name, "SKILL.md"))
    if skill_md != canonical:
        return "'skill_md' is not in canonical form"
    return None


def resolve_skill_md_path(
    skill_md: str, repo_root: Optional[pathlib.Path] = None
) -> pathlib.Path:
    """Resolve *skill_md* to an on-disk path, refusing anything outside the registry."""
    reason = check_skill_md_string(skill_md)
    if reason is not None:
        raise ValueError(f"Recipe SKILL.md path is invalid: {reason}")
    if repo_root is None:
        repo_root = pathlib.Path(__file__).resolve().parents[4]
    repo_root = repo_root.resolve()
    candidate = repo_root / skill_md
    if candidate.is_symlink():
        raise ValueError(f"Recipe SKILL.md must not be a symlink: {skill_md}")
    resolved = candidate.resolve()
    try:
        resolved.relative_to(repo_root)
    except ValueError as exc:
        raise ValueError(
            f"Recipe SKILL.md path outside repository: {skill_md}"
        ) from exc
    return resolved


def validate_registry_entry(rule_id: str, entry: Any) -> Optional[str]:
    """Validate one registry entry. Returns an error string, or None if valid."""
    try:
        mode = entry_mode(entry)
    except ValueError as exc:
        return f"invalid registry entry {rule_id}: {exc}"

    required = REQUIRED_AGENT_FIELDS if mode == "agent" else REQUIRED_SCRIPT_FIELDS
    forbidden = "script" if mode == "agent" else "skill_md"

    for field in required:
        value = entry.get(field)
        if not isinstance(value, str) or not value.strip():
            return (
                f"invalid registry entry {rule_id}: "
                f"'{field}' must be a non-empty string in {mode} mode"
            )
    if forbidden in entry:
        return (
            f"invalid registry entry {rule_id}: "
            f"'{forbidden}' must not be present in {mode} mode"
        )
    if mode == "agent":
        reason = check_skill_md_string(entry["skill_md"])
        if reason is not None:
            return f"invalid registry entry {rule_id}: {reason}"
    return None

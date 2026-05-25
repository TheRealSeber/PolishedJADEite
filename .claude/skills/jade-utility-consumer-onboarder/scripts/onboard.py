#!/usr/bin/env python3
"""Consumer Onboarder — ingest external JADE projects into consumer-playground/.

Extracts a ZIP archive, copies Java sources preserving package structure,
generates a boilerplate test-config.json.

Usage:
    python onboard.py --zip-file hw-jade.zip --project-name my-project
    python onboard.py --zip-file hw-jade.zip --project-name my-project --agent-class hw:HelloWorldAgent
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import sys
import tempfile
import zipfile
from typing import Dict, List, Optional, Set

# Constants
PLAYGROUND_DIR = pathlib.Path("consumer-playground")
SKIP_DIRS: Set[str] = {".idea", ".mvn", "target", "src/test", ".git"}
SKIP_EXTENSIONS: Set[str] = {".class", ".jar", ".xml", ".iml", ".properties", ".mf"}
STANDARD_CLASSPATH_DEPS: List[str] = [
    "src/jade/lib/jade.jar",
    "src/jade/lib/commons-codec/commons-codec-1.3.jar",
]


def discover_source_root(extract_dir: pathlib.Path) -> pathlib.Path:
    """Detect Java source root inside extracted directory.

    Prefers Maven/Gradle layout (src/main/java/), falls back to root.
    """
    common_roots = [
        extract_dir / "src" / "main" / "java",  # Maven/Gradle standard (preferred)
        extract_dir,  # plain project fallback
    ]
    for root in common_roots:
        if root.exists() and list(root.glob("**/*.java")):
            return root
    # If none, just return the extract dir
    return extract_dir


def should_copy(path: pathlib.Path, extract_dir: pathlib.Path) -> bool:
    """Decide whether a file should be copied to the playground."""
    # Skip directories and non-.java files
    if path.is_dir():
        return False
    if path.suffix.lower() != ".java":
        return False
    # Skip test source directories
    rel = str(path.relative_to(extract_dir))
    parts = pathlib.Path(rel).parts
    if "test" in parts:
        return False
    return True


def extract_java_sources(
    zip_path: pathlib.Path,
    project_name: str,
) -> int:
    """Extract Java source files from ZIP into consumer-playground/<project_name>/.

    Returns count of files copied.
    """
    dest_dir = PLAYGROUND_DIR / project_name
    dest_dir.mkdir(parents=True, exist_ok=True)

    copied = 0
    with tempfile.TemporaryDirectory(prefix=f"jade-onboard-{project_name}-") as tmp:
        tmp_path = pathlib.Path(tmp)

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp_path)

        source_root = discover_source_root(tmp_path)
        print(f"Source root detected: {source_root.relative_to(tmp_path)}")

        for java_file in source_root.glob("**/*.java"):
            if not should_copy(java_file, source_root):
                continue

            rel_path = java_file.relative_to(source_root)
            dest_path = dest_dir / rel_path
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(java_file, dest_path)
            print(f"  Copied: {rel_path}")
            copied += 1

    print(f"Extracted {copied} Java files to {dest_dir}")
    return copied


def generate_test_config(
    project_name: str,
    agent_class: Optional[str],
) -> Dict:
    """Generate a boilerplate test-config.json."""
    boot_args = (
        ["-agents", agent_class]
        if agent_class
        else ["-agents", "REPLACE_ME:YourAgentClass"]
    )

    return {
        "name": project_name,
        "description": f"Consumer test for {project_name}",
        "docker_image": "${TARGET_DOCKER_IMAGE}",
        "main_class": "jade.Boot",
        "boot_args": boot_args,
        "expected_stdout_markers": ["is ready"],
        "timeout_seconds": 90,
        "classpath_deps": STANDARD_CLASSPATH_DEPS,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Onboard a JADE project into consumer-playground"
    )
    parser.add_argument(
        "--zip-file", required=True, help="Path to ZIP archive of the project"
    )
    parser.add_argument(
        "--project-name",
        required=True,
        help="Name for the consumer playground directory",
    )
    parser.add_argument(
        "--agent-class",
        default=None,
        help="Agent class for boot_args (e.g. test:MyAgentClass)",
    )
    args = parser.parse_args()

    zip_path = pathlib.Path(args.zip_file)
    if not zip_path.exists():
        print(f"ERROR: ZIP file not found: {zip_path}", file=sys.stderr)
        return 2

    project_name = args.project_name
    dest_dir = PLAYGROUND_DIR / project_name

    # Check if destination already exists
    if dest_dir.exists():
        print(f"ERROR: Destination already exists: {dest_dir}", file=sys.stderr)
        print("Remove it first or use a different --project-name", file=sys.stderr)
        return 2

    # Create playground dir if needed
    PLAYGROUND_DIR.mkdir(parents=True, exist_ok=True)

    # Extract
    count = extract_java_sources(zip_path, project_name)
    if count == 0:
        print(f"ERROR: No Java files found in ZIP", file=sys.stderr)
        shutil.rmtree(dest_dir, ignore_errors=True)
        return 2

    # Generate config
    config = generate_test_config(project_name, args.agent_class)
    config_path = dest_dir / "test-config.json"
    with config_path.open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    config_path.write_text(config_path.read_text() + "\n")  # trailing newline
    print(f"Config written to {config_path}")

    # Summary
    print(f"\nOnboarded: {project_name}")
    print(f"  Files: {count}")
    print(f"  Config: {config_path}")
    if not args.agent_class:
        print(
            f"  WARNING: No --agent-class provided. Update boot_args in {config_path}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

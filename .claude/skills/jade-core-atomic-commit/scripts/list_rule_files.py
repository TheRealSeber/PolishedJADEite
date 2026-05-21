#!/usr/bin/env python3
"""Extract a flat list of file paths touched by a single migration rule.

Input:  batch artifact JSON (e.g. artfacts/08-rule-batch-raw-types.json)
Output: newline-delimited list of relative file paths on stdout.

The batch artifact supports two schemas:

  Schema A — per-file records:
      {"rule_id": "raw-types", "files": [{"path": "src/Foo.java", "status": "modified"}, ...]}

  Schema B — plain list:
      {"rule_id": "raw-types", "files": ["src/Foo.java", "src/Bar.java", ...]}

Mising or empty files key produces empty output (exit 0, not an error).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List


def extract_files(batch: dict) -> List[str]:
    files = batch.get("files")
    if files is None:
        return []

    if not isinstance(files, list):
        print(
            f"ERROR [BATCH_ARTIFACT_INVALID] 'files' must be a list, got {type(files).__name__}",
            file=sys.stderr,
        )
        sys.exit(2)

    result: List[str] = []
    for item in files:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            path = item.get("path")
            if path:
                result.append(path)
        else:
            print(
                f"ERROR [BATCH_ARTIFACT_INVALID] Unexpected item type in files list: {type(item).__name__}",
                file=sys.stderr,
            )
            sys.exit(2)
    return result


def main() -> None:
    if len(sys.argv) < 2:
        print("ERROR [USAGE] list_rule_files.py <batch-artifact.json>", file=sys.stderr)
        sys.exit(2)

    artifact_path = Path(sys.argv[1])
    if not artifact_path.exists():
        print(f"ERROR [BATCH_ARTIFACT_MISSING] {artifact_path}", file=sys.stderr)
        sys.exit(2)

    try:
        with artifact_path.open("r", encoding="utf-8") as fh:
            batch = json.load(fh)
    except json.JSONDecodeError as exc:
        print(f"ERROR [BATCH_ARTIFACT_INVALID] Invalid JSON: {exc}", file=sys.stderr)
        sys.exit(2)

    for f in extract_files(batch):
        print(f)


if __name__ == "__main__":
    main()

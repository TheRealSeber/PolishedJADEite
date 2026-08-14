#!/usr/bin/env python3
"""NOOP recipe — marks informational rules as SKIPPED (no source changes needed)."""

import argparse
import json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--line", type=int, required=True)
    parser.parse_args()

    result = {
        "status": "SKIPPED",
        "changes": 0,
        "warnings": [],
        "errors": [],
        "diff_summary": "No source changes required for Java 1.5→1.6; informational rule",
    }
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

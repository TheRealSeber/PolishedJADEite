#!/usr/bin/env python3
"""Informational recipe — TreeSet/TreeMap already implement NavigableSet/NavigableMap in Java 6."""

import argparse, json, sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--line", type=int, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            {
                "status": "SKIPPED",
                "changes": 0,
                "warnings": [
                    "TreeSet/TreeMap already implement NavigableSet/NavigableMap in Java 6 — informational rule"
                ],
                "errors": [],
                "diff_summary": "TreeSet/TreeMap already implement Navigable* in Java 6; no code change needed",
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

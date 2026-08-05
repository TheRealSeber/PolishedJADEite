#!/usr/bin/env python3
"""query_graph.py -- CLI query interface for Knowledge Graph artifacts.

Query types: dependents, impact-chain, rule-scope, consumer-coverage, transform-order
Exit codes: 0=success, 1=no results, 2=failure, 3=env-error
"""

import argparse
import json
import os
import sys

from schema import KnowledgeGraph


def cmd_dependents(kg: KnowledgeGraph, args):
    if not args.target:
        print("ERROR: --target required for dependents query", file=sys.stderr)
        sys.exit(2)
    results = kg.query_dependents(args.target)
    print(json.dumps(results, indent=2))
    sys.exit(0 if results else 1)


def cmd_impact_chain(kg: KnowledgeGraph, args):
    if not args.target:
        print("ERROR: --target required for impact-chain query", file=sys.stderr)
        sys.exit(2)
    results = kg.query_call_sites(args.target, args.method or "")
    print(json.dumps(results, indent=2))
    sys.exit(0 if results else 1)


def cmd_rule_scope(kg: KnowledgeGraph, args):
    flagged = args.files or []
    if not flagged:
        print("ERROR: --files required for rule-scope query", file=sys.stderr)
        sys.exit(2)
    results = kg.query_rule_scope(flagged)
    print(json.dumps(results, indent=2))
    sys.exit(0)


def cmd_consumer_coverage(kg: KnowledgeGraph, args):
    files = args.files or []
    if not files:
        print("ERROR: --files required for consumer-coverage query", file=sys.stderr)
        sys.exit(2)
    consumer_map = {}
    if args.consumer_map:
        with open(args.consumer_map, "r") as f:
            consumer_map = json.load(f)
    results = kg.query_consumer_coverage(files, consumer_map)
    print(json.dumps(results, indent=2))
    sys.exit(0)


def cmd_transform_order(kg: KnowledgeGraph, args):
    rules = args.rules or []
    if not rules:
        print("ERROR: --rules required for transform-order query", file=sys.stderr)
        sys.exit(2)
    rule_files = {}
    if args.rule_files_map:
        with open(args.rule_files_map, "r") as f:
            rule_files = json.load(f)
    results = kg.query_transform_order(rules, rule_files)
    print(json.dumps(results, indent=2))
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="Query a Knowledge Graph artifact")
    parser.add_argument("--graph", required=True, help="Path to 03.5-knowledge-graph.json")
    parser.add_argument("--query", required=True,
                        choices=["dependents", "impact-chain", "rule-scope",
                                 "consumer-coverage", "transform-order"],
                        help="Query type")
    parser.add_argument("--target", help="Target file path (for dependents, impact-chain)")
    parser.add_argument("--method", help="Method name (for impact-chain)")
    parser.add_argument("--files", nargs="*", help="List of files (for rule-scope, consumer-coverage)")
    parser.add_argument("--rules", nargs="*", help="List of rule IDs (for transform-order)")
    parser.add_argument("--consumer-map", help="Path to consumer file map JSON")
    parser.add_argument("--rule-files-map", help="Path to rule-to-files map JSON")

    args = parser.parse_args()

    if not os.path.isfile(args.graph):
        print(f"ERROR: graph file not found: {args.graph}", file=sys.stderr)
        sys.exit(3)

    try:
        kg = KnowledgeGraph.load(args.graph)
    except Exception as e:
        print(f"ERROR: failed to load graph: {e}", file=sys.stderr)
        sys.exit(2)

    handlers = {
        "dependents": cmd_dependents,
        "impact-chain": cmd_impact_chain,
        "rule-scope": cmd_rule_scope,
        "consumer-coverage": cmd_consumer_coverage,
        "transform-order": cmd_transform_order,
    }
    handlers[args.query](kg, args)


if __name__ == "__main__":
    main()

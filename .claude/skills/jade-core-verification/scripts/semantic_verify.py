#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Event model
# ---------------------------------------------------------------------------

LIFECYCLE_PATTERNS: List[Tuple[re.Pattern, str, List[str]]] = [
    (
        re.compile(r"Agent\s+(\S+?)\s+(?:is\s+born|started)"),
        "AGENT_STARTED",
        ["agent"],
    ),
    (
        re.compile(r"Agent\s+(\S+?)\s+suspended"),
        "AGENT_SUSPENDED",
        ["agent"],
    ),
    (
        re.compile(r"Agent\s+(\S+?)\s+resumed"),
        "AGENT_RESUMED",
        ["agent"],
    ),
    (
        re.compile(r"Agent\s+(\S+?)\s+(?:moved|migrated)"),
        "AGENT_MOVED",
        ["agent"],
    ),
    (
        re.compile(r"Agent\s+(\S+?)\s+(?:terminated|died)"),
        "AGENT_TERMINATED",
        ["agent"],
    ),
    (
        re.compile(r"(?:Agent\s+)?container\s+(\S+?)\s+(?:is\s+ready|ready)"),
        "CONTAINER_READY",
        ["container"],
    ),
    (
        re.compile(r"(?:Agent\s+)?container\s+(\S+?)\s+shut"),
        "CONTAINER_SHUTDOWN",
        ["container"],
    ),
    (
        re.compile(r"joinPlatform.*(\S+?)"),
        "PLATFORM_JOIN",
        ["container"],
    ),
    (
        re.compile(r"Main\s*[-]?\s*[Cc]ontainer\s+(\S+?)"),
        "MAIN_ELECTED",
        ["container"],
    ),
]

ACL_PATTERNS: List[Tuple[re.Pattern, str, List[str]]] = [
    (
        re.compile(
            r"(?:sends?|send(?:ing)?)\s+ACL\s*\(\s*(\w+)\s*\)\s+(?:to|->>?)\s+(\S+)"
        ),
        "ACL_SEND",
        ["performative", "receiver"],
    ),
    (
        re.compile(
            r"(?:receiv(?:ed|e|ing))\s+ACL\s*\(\s*(\w+)\s*\)\s+(?:from|<<-?)\s+(\S+)"
        ),
        "ACL_RECEIVE",
        ["performative", "sender"],
    ),
    (
        re.compile(r"ACL\s+(\w+)\s+(\S+)\s*->\s*(\S+)"),
        "ACL_SEND",
        ["performative", "sender", "receiver"],
    ),
]

DF_AMS_PATTERNS: List[Tuple[re.Pattern, str, List[str]]] = [
    (
        re.compile(
            r"(?:reg(?:istered|ister(?:ed)?).*?service|DFService.*?(?:reg(?:ister)?))"
        ),
        "DF_REGISTER",
        ["agent"],
    ),
    (
        re.compile(r"(?:dereg(?:istered|ister(?:ed)?).*?service)"),
        "DF_DEREGISTER",
        ["agent"],
    ),
    (
        re.compile(r"(?:modif(?:ied|y).*?service)"),
        "DF_MODIFY",
        ["agent"],
    ),
    (
        re.compile(r"(?:search.*?(?:DF|DFService)|DFService.*?search)"),
        "DF_SEARCH",
        ["agent"],
    ),
    (
        re.compile(r"(?:DF.*?result.*?(\d+)\s+(?:result|match|agent))"),
        "DF_SEARCH_RESULT",
        ["count"],
    ),
    (
        re.compile(r"AMS.*?(?:describe|description).*?(\S+)"),
        "AMS_DESCRIBE",
        ["target"],
    ),
    (
        re.compile(r"AMS.*?kill.*?(\S+)"),
        "AMS_KILL",
        ["target"],
    ),
]


@dataclass
class SemanticEvent:
    layer: str
    event_type: str
    fields: Dict[str, str]
    source_agent: str
    original_message: str
    source_file: str = ""


@dataclass
class LayerDiff:
    layer: str
    pass_: bool
    diffs: List[Dict[str, Any]] = field(default_factory=list)
    baseline_count: int = 0
    migrated_count: int = 0
    matched_count: int = 0
    tolerated_count: int = 0
    unmatched_baseline: List[str] = field(default_factory=list)
    unmatched_migrated: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "layer": self.layer,
            "pass": self.pass_,
            "diffs": self.diffs,
            "baseline_count": self.baseline_count,
            "migrated_count": self.migrated_count,
            "matched_count": self.matched_count,
            "tolerated_count": self.tolerated_count,
            "unmatched_baseline": self.unmatched_baseline,
            "unmatched_migrated": self.unmatched_migrated,
        }


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

RE_AGENT_LOCAL = re.compile(r"^([^@]+)(?:@.*)?$")
RE_SERVICE_SPEC = re.compile(r"(?:service|type)[=:]\s*(\S+)", re.IGNORECASE)


def _agent_local(name: str) -> str:
    m = RE_AGENT_LOCAL.match(name.strip())
    return m.group(1) if m else name.strip()


def _extract_lifecycle(message: str, source_agent: str) -> Optional[SemanticEvent]:
    for pat, etype, groups in LIFECYCLE_PATTERNS:
        m = pat.search(message)
        if m:
            fields: Dict[str, str] = {}
            for i, key in enumerate(groups, 1):
                fields[key] = _agent_local(m.group(i))
            fields.setdefault("agent", _agent_local(source_agent))
            return SemanticEvent(
                layer="lifecycle",
                event_type=etype,
                fields=fields,
                source_agent=fields.get("agent", _agent_local(source_agent)),
                original_message=message,
            )
    return None


def _extract_acl(message: str, source_agent: str) -> Optional[SemanticEvent]:
    for pat, etype, groups in ACL_PATTERNS:
        m = pat.search(message)
        if m:
            fields: Dict[str, str] = {}
            for i, key in enumerate(groups, 1):
                fields[key] = _agent_local(m.group(i))
            fields.setdefault("sender", _agent_local(source_agent))
            return SemanticEvent(
                layer="acl",
                event_type=etype,
                fields=fields,
                source_agent=fields.get(
                    "sender", fields.get("receiver", _agent_local(source_agent))
                ),
                original_message=message,
            )
    return None


def _extract_df_ams(message: str, source_agent: str) -> Optional[SemanticEvent]:
    for pat, etype, groups in DF_AMS_PATTERNS:
        m = pat.search(message)
        if m:
            fields: Dict[str, str] = {}
            for i, key in enumerate(groups, 1):
                fields[key] = _agent_local(m.group(i))
            fields.setdefault("agent", _agent_local(source_agent))
            return SemanticEvent(
                layer="df_ams",
                event_type=etype,
                fields=fields,
                source_agent=fields.get("agent", _agent_local(source_agent)),
                original_message=message,
            )
    return None


def _extract_from_raw(evt: Dict[str, Any]) -> Optional[SemanticEvent]:
    message = evt.get("message", "")
    source_agent = evt.get("sender", evt.get("agent", evt.get("source", "")))
    performative = evt.get("performative", "")

    if performative:
        return SemanticEvent(
            layer="acl",
            event_type="ACL_SEND",
            fields={
                "performative": performative.upper(),
                "sender": _agent_local(evt.get("sender", source_agent)),
                "receiver": _agent_local(evt.get("receiver", "")),
            },
            source_agent=_agent_local(evt.get("sender", source_agent)),
            original_message=message,
            source_file=evt.get("_file", ""),
        )

    semantic = (
        _extract_lifecycle(message, source_agent)
        or _extract_acl(message, source_agent)
        or _extract_df_ams(message, source_agent)
    )
    if semantic:
        semantic.source_file = evt.get("_file", "")
    return semantic


# ---------------------------------------------------------------------------
# Event signature
# ---------------------------------------------------------------------------


def _event_signature(evt: SemanticEvent) -> str:
    parts = [evt.layer, evt.event_type]
    for k in sorted(evt.fields.keys()):
        parts.append(f"{k}={evt.fields[k]}")
    return "|".join(parts)


def _event_fingerprint(evt: SemanticEvent) -> str:
    return f"{evt.layer}:{evt.event_type}"


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


def _load_tolerance(path: pathlib.Path) -> Dict[str, Any]:
    default = {
        "tolerance": {
            "agent_count_delta": {
                "max_deviation": 0,
                "allow_extra": False,
                "allow_missing": False,
            },
            "lifecycle_order": {"strict": True, "allowed_reorder_events": []},
            "acl_message_count": {"max_deviation": 0, "allow_duplicates": False},
            "df_outcome_count": {
                "max_deviation": 0,
                "allow_extra": False,
                "allow_missing": False,
            },
            "timing": {"ignore": True, "max_skew_ms": 5000},
        },
        "ignore_events": [],
        "require_events": [],
        "agent_allowlist": [],
        "agent_blocklist": [],
        "conversation_id_matching": "strict",
    }
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            user = json.load(f)
        default.update(user)
    return default


def _compare_layer(
    baseline: List[SemanticEvent],
    migrated: List[SemanticEvent],
    layer: str,
    tolerance: Dict[str, Any],
) -> LayerDiff:
    result = LayerDiff(
        layer=layer,
        pass_=True,
        baseline_count=len(baseline),
        migrated_count=len(migrated),
    )

    tol = tolerance.get("tolerance", {})

    base_sigs: List[str] = [_event_signature(e) for e in baseline]
    mig_sigs: List[str] = [_event_signature(e) for e in migrated]
    base_fps: List[str] = [_event_fingerprint(e) for e in baseline]
    mig_fps: List[str] = [_event_fingerprint(e) for e in migrated]

    base_counter = Counter(base_sigs)
    mig_counter = Counter(mig_sigs)

    all_sigs = set(base_sigs) | set(mig_sigs)
    matched = 0
    tolerated = 0

    for sig in sorted(all_sigs):
        bc = base_counter.get(sig, 0)
        mc = mig_counter.get(sig, 0)
        if bc == mc:
            matched += bc
        elif bc > 0 and mc == 0:
            result.unmatched_baseline.append(sig)
        elif mc > 0 and bc == 0:
            result.unmatched_migrated.append(sig)
        else:
            delta = abs(bc - mc)
            matched += min(bc, mc)
            tolerated += delta
            if bc > mc:
                result.unmatched_baseline.append(f"{sig} (extra {delta})")
            else:
                result.unmatched_migrated.append(f"{sig} (extra {delta})")

    result.matched_count = matched
    result.tolerated_count = tolerated

    if layer == "lifecycle":
        lc_tol = tol.get("lifecycle_order", {})
        if lc_tol.get("strict", True):
            base_seq = [(e.event_type, e.source_agent) for e in baseline]
            mig_seq = [(e.event_type, e.source_agent) for e in migrated]
            reorder_ok = set(lc_tol.get("allowed_reorder_events", []))
            for i, (bt, ba) in enumerate(base_seq):
                if i >= len(mig_seq):
                    result.diffs.append(
                        {
                            "type": "missing_event",
                            "index": i,
                            "baseline": f"{bt}:{ba}",
                            "migrated": None,
                            "tolerated": False,
                        }
                    )
                    break
                if (bt, ba) != mig_seq[i]:
                    if bt in reorder_ok:
                        result.diffs.append(
                            {
                                "type": "order_mismatch",
                                "event": f"{bt}:{ba}",
                                "baseline_index": i,
                                "migrated_index": i,
                                "tolerated": True,
                                "reason": f"allowed_reorder_events includes {bt}",
                            }
                        )
                    else:
                        result.diffs.append(
                            {
                                "type": "order_mismatch",
                                "event": f"{bt}:{ba}",
                                "baseline_index": i,
                                "migrated": f"{mig_seq[i][0]}:{mig_seq[i][1]}"
                                if i < len(mig_seq)
                                else None,
                                "tolerated": False,
                            }
                        )

            if len(mig_seq) > len(base_seq):
                for i in range(len(base_seq), len(mig_seq)):
                    result.diffs.append(
                        {
                            "type": "extra_event",
                            "index": i,
                            "migrated": f"{mig_seq[i][0]}:{mig_seq[i][1]}",
                            "tolerated": tol.get("agent_count_delta", {}).get(
                                "allow_extra", False
                            ),
                        }
                    )

        agent_count_delta = tol.get("agent_count_delta", {})
        agents_base = set(e.source_agent for e in baseline)
        agents_mig = set(e.source_agent for e in migrated)
        extra = agents_mig - agents_base
        missing = agents_base - agents_mig
        if extra and not agent_count_delta.get("allow_extra", False):
            result.pass_ = False
        if missing and not agent_count_delta.get("allow_missing", False):
            result.pass_ = False

    elif layer == "acl":
        acl_tol = tol.get("acl_message_count", {})
        count_delta = abs(len(baseline) - len(migrated))
        if count_delta > acl_tol.get("max_deviation", 0):
            result.pass_ = False
            result.diffs.append(
                {
                    "type": "count_mismatch",
                    "baseline_count": len(baseline),
                    "migrated_count": len(migrated),
                    "delta": count_delta,
                    "max_allowed": acl_tol.get("max_deviation", 0),
                    "tolerated": False,
                }
            )

    elif layer == "df_ams":
        df_tol = tol.get("df_outcome_count", {})
        extra = set(mig_sigs) - set(base_sigs)
        missing = set(base_sigs) - set(mig_sigs)
        if extra and not df_tol.get("allow_extra", False):
            result.pass_ = False
            for sig in extra:
                result.diffs.append(
                    {
                        "type": "extra_df_outcome",
                        "signature": sig,
                        "tolerated": False,
                    }
                )
        if missing and not df_tol.get("allow_missing", False):
            result.pass_ = False
            for sig in missing:
                result.diffs.append(
                    {
                        "type": "missing_df_outcome",
                        "signature": sig,
                        "tolerated": False,
                    }
                )

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _load_events(path: pathlib.Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("events", [])


def _extract_semantic(
    raw_events: List[Dict[str, Any]], tolerance: Dict[str, Any]
) -> List[SemanticEvent]:
    ignore = set(tolerance.get("ignore_events", []))
    allowlist = set(tolerance.get("agent_allowlist", []))
    blocklist = set(tolerance.get("agent_blocklist", []))
    require = set(tolerance.get("require_events", []))

    result: List[SemanticEvent] = []
    seen_requires: Set[str] = set()

    for evt in raw_events:
        semantic = _extract_from_raw(evt)
        if semantic is None:
            continue

        if semantic.event_type in ignore:
            continue

        if blocklist and semantic.source_agent in blocklist:
            continue

        if allowlist and semantic.source_agent not in allowlist:
            continue

        if semantic.event_type in require:
            seen_requires.add(semantic.event_type)

        result.append(semantic)

    return result


def _iso_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _write_json_atomic(path: pathlib.Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    tmp.replace(path)


def _partition_events(
    events: List[SemanticEvent],
) -> Tuple[List[SemanticEvent], List[SemanticEvent], List[SemanticEvent]]:
    lifecycle: List[SemanticEvent] = []
    acl: List[SemanticEvent] = []
    df_ams: List[SemanticEvent] = []
    for e in events:
        if e.layer == "lifecycle":
            lifecycle.append(e)
        elif e.layer == "acl":
            acl.append(e)
        elif e.layer == "df_ams":
            df_ams.append(e)
    return lifecycle, acl, df_ams


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Semantic verification of JADE migration traces"
    )
    parser.add_argument(
        "--baseline",
        required=True,
        type=pathlib.Path,
        help="Path to normalized baseline trace JSON",
    )
    parser.add_argument(
        "--migrated",
        required=True,
        type=pathlib.Path,
        help="Path to normalized migrated trace JSON",
    )
    parser.add_argument(
        "--tolerance",
        default=None,
        type=pathlib.Path,
        help="Path to tolerance configuration JSON",
    )
    parser.add_argument(
        "--artifacts-dir",
        default=pathlib.Path("artifacts"),
        type=pathlib.Path,
        help="Directory to write output artifacts",
    )
    args = parser.parse_args()

    if not args.baseline.exists():
        print(f"ERROR [BASELINE_NOT_FOUND] {args.baseline}", file=sys.stderr)
        return 2
    if not args.migrated.exists():
        print(f"ERROR [MIGRATED_NOT_FOUND] {args.migrated}", file=sys.stderr)
        return 2

    tolerance_path = args.tolerance or pathlib.Path("tolerance_config.json")
    tolerance = _load_tolerance(tolerance_path)

    baseline_raw = _load_events(args.baseline)
    migrated_raw = _load_events(args.migrated)

    baseline_sem = _extract_semantic(baseline_raw, tolerance)
    migrated_sem = _extract_semantic(migrated_raw, tolerance)

    bl, ba, bd = _partition_events(baseline_sem)
    ml, ma, md = _partition_events(migrated_sem)

    lifecycle_diff = _compare_layer(bl, ml, "lifecycle", tolerance)
    acl_diff = _compare_layer(ba, ma, "acl", tolerance)
    df_ams_diff = _compare_layer(bd, md, "df_ams", tolerance)

    overall_pass = lifecycle_diff.pass_ and acl_diff.pass_ and df_ams_diff.pass_

    diff_payload = {
        "timestamp": _iso_now(),
        "overall_pass": overall_pass,
        "sections": [
            section.to_dict() for section in (lifecycle_diff, acl_diff, df_ams_diff)
        ],
    }

    metrics_payload = {
        "timestamp": _iso_now(),
        "overall_pass": overall_pass,
        "baseline_event_count": len(baseline_sem),
        "migrated_event_count": len(migrated_sem),
        "matched_count": (
            lifecycle_diff.matched_count
            + acl_diff.matched_count
            + df_ams_diff.matched_count
        ),
        "tolerated_diff_count": (
            lifecycle_diff.tolerated_count
            + acl_diff.tolerated_count
            + df_ams_diff.tolerated_count
        ),
        "unmatched_baseline": len(lifecycle_diff.unmatched_baseline)
        + len(acl_diff.unmatched_baseline)
        + len(df_ams_diff.unmatched_baseline),
        "unmatched_migrated": len(lifecycle_diff.unmatched_migrated)
        + len(acl_diff.unmatched_migrated)
        + len(df_ams_diff.unmatched_migrated),
        "lifecycle_outcome_pass": lifecycle_diff.pass_,
        "acl_outcome_pass": acl_diff.pass_,
        "df_ams_outcome_pass": df_ams_diff.pass_,
    }

    _write_json_atomic(args.artifacts_dir / "07-semantic-diff.json", diff_payload)
    _write_json_atomic(args.artifacts_dir / "07-metrics.json", metrics_payload)

    print(f"Semantic verification {'PASSED' if overall_pass else 'FAILED'}")
    print(
        f"  Lifecycle: {'PASS' if lifecycle_diff.pass_ else 'FAIL'} "
        f"({lifecycle_diff.matched_count} match, {lifecycle_diff.tolerated_count} tolerated)"
    )
    print(
        f"  ACL:       {'PASS' if acl_diff.pass_ else 'FAIL'} "
        f"({acl_diff.matched_count} match, {acl_diff.tolerated_count} tolerated)"
    )
    print(
        f"  DF/AMS:    {'PASS' if df_ams_diff.pass_ else 'FAIL'} "
        f"({df_ams_diff.matched_count} match, {df_ams_diff.tolerated_count} tolerated)"
    )

    if not overall_pass:
        _write_json_atomic(
            args.artifacts_dir / "failure-summary.json",
            {
                "code": "VERIFICATION_FAILED",
                "message": "Semantic verification did not pass. See artifacts/07-semantic-diff.json for details.",
                "updated_at": _iso_now(),
            },
        )
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

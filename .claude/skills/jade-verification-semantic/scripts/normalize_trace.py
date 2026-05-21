#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from typing import Any, Dict, List, Optional, Set

RE_TIMESTAMP_JADE = re.compile(
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}\s+\d{1,2}:\d{2}:\d{2}\s*(?:AM|PM)\b"
)
RE_TIMESTAMP_ISO = re.compile(
    r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b"
)
RE_TIMESTAMP_SHORT = re.compile(r"\b\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?\b")
RE_THREAD_ID = re.compile(
    r"\[(?:Thread|pool|ForkJoinPool|worker|agent-pool|TP-Processor|http-nio|qtp)[^\]]*\]"
)
RE_THREAD_ALT = re.compile(r"<Thread-\d+>")
RE_HEX_NONCE = re.compile(r"\b(?:0x)?[a-fA-F0-9]{16,}\b")
RE_UUID = re.compile(
    r"\b[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}\b"
)
RE_MEMORY_ADDR = re.compile(r"@[a-fA-F0-9]{4,16}\b")
RE_PLATFORM_ADDR = re.compile(r"@[\w.\-]+:\d+(?:/[A-Z]+)?")
RE_LOG4J_PREFIX = re.compile(
    r"^\s*(?:TRACE|DEBUG|INFO|WARN(?:ING)?|ERROR|FATAL|SEVERE|FINE|FINER|FINEST|CONFIG)\s+"
)
RE_LOG4J_LEVEL_LINE = re.compile(
    r"^(?:\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:,\d+)?\s+)?"
    r"(?:\[[^\]]*\]\s+)?"
    r"(TRACE|DEBUG|INFO|WARN(?:ING)?|ERROR|FATAL|SEVERE|FINE|FINER|FINEST|CONFIG)\s+"
    r"(\S+)\s*[-:]\s+"
)
RE_WHITESPACE = re.compile(r"\s+")
RE_JADE_HEADER = re.compile(r"This is JADE \d+\.\d+")
RE_JADE_BANNER = re.compile(r"^-{5,}$")

JADE_LOG_LEVELS: Set[str] = {
    "INFO",
    "WARNING",
    "SEVERE",
    "FINE",
    "FINER",
    "FINEST",
    "CONFIG",
    "TRACE",
    "DEBUG",
    "ERROR",
    "FATAL",
}


def _jade_log_parse(line: str) -> Optional[Dict[str, Any]]:
    stripped = line.strip()
    if not stripped:
        return None

    if RE_JADE_BANNER.match(stripped):
        return None
    if RE_JADE_HEADER.search(stripped):
        return None

    working = stripped
    working = RE_TIMESTAMP_JADE.sub("", working)
    working = RE_TIMESTAMP_ISO.sub("", working)
    working = RE_TIMESTAMP_SHORT.sub("", working)
    working = RE_THREAD_ID.sub("", working)
    working = RE_THREAD_ALT.sub("", working)
    working = RE_HEX_NONCE.sub("", working)
    working = RE_UUID.sub("", working)
    working = RE_MEMORY_ADDR.sub("", working)
    working = RE_PLATFORM_ADDR.sub("@PLATFORM", working)
    working = RE_WHITESPACE.sub(" ", working).strip()

    if len(working) < 3:
        return None

    level: Optional[str] = None
    source: Optional[str] = None
    message: str = working

    m = RE_LOG4J_LEVEL_LINE.match(working)
    if m:
        level = m.group(1)
        source = m.group(2)
        message = working[m.end() :].strip()

    if level is None:
        for candidate in (
            "INFO: ",
            "WARNING: ",
            "SEVERE: ",
            "FINE: ",
            "FINER: ",
            "FINEST: ",
            "CONFIG: ",
            "TRACE: ",
            "DEBUG: ",
            "ERROR: ",
            "FATAL: ",
        ):
            if working.startswith(candidate):
                level = candidate.rstrip(": ")
                message = working[len(candidate) :].strip()
                break

    if level is None and source is None and message.startswith("Agent "):
        level = "INFO"
    if level is None and source is None:
        level = "LOG"

    return {
        "level": level,
        "source": source,
        "message": message,
    }


def _sniffer_xml_parse(content: str) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []

    msg_pattern = re.compile(
        r"<message>\s*"
        r"<sender>(.*?)</sender>\s*"
        r"<receiver>(.*?)</receiver>\s*"
        r"<performative>(.*?)</performative>\s*"
        r"(?:<content>.*?</content>\s*)?"
        r"(?:<conversation-id>(.*?)</conversation-id>\s*)?"
        r"(?:<in-reply-to>(.*?)</in-reply-to>\s*)?"
        r"(?:<timestamp>\d+</timestamp>\s*)?"
        r"</message>",
        re.DOTALL,
    )

    for m in msg_pattern.finditer(content):
        sender = m.group(1).strip()
        receiver = m.group(2).strip()
        performative = m.group(3).strip().upper()
        conv_id = (m.group(4) or "").strip() or None
        in_reply_to = (m.group(5) or "").strip() or None

        sender = RE_PLATFORM_ADDR.sub("@PLATFORM", sender)
        receiver = RE_PLATFORM_ADDR.sub("@PLATFORM", receiver)

        events.append(
            {
                "level": "ACL",
                "source": "sniffer",
                "message": f"ACL {performative} {sender} -> {receiver}",
                "sender": sender,
                "receiver": receiver,
                "performative": performative,
                "conversation_id": conv_id,
                "in_reply_to": in_reply_to,
            }
        )

    return events


def _detect_format(path: pathlib.Path) -> str:
    with path.open("r", encoding="utf-8", errors="replace") as f:
        head = f.read(4096)
    if head.lstrip().startswith("<?xml") or "<snifferTrace>" in head:
        return "sniffer-xml"
    if head.strip().startswith("{") and '"' in head:
        return "jsonl"
    return "jade-log"


def _normalize_jsonl_line(obj: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    message = str(obj.get("message", obj.get("msg", obj.get("text", ""))))
    if not message:
        if "event" in obj:
            message = str(obj["event"])
        else:
            message = json.dumps(obj)

    message = RE_PLATFORM_ADDR.sub("@PLATFORM", message)
    message = RE_UUID.sub("", message)
    message = RE_HEX_NONCE.sub("", message)
    message = RE_WHITESPACE.sub(" ", message).strip()

    return {
        "level": obj.get("level", obj.get("severity", "INFO")),
        "source": obj.get("source", obj.get("logger", None)),
        "message": message,
    }


def normalize_file(path: pathlib.Path, fmt: str) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []

    with path.open("r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    if fmt == "sniffer-xml":
        results.extend(_sniffer_xml_parse(content))
        return results

    if fmt == "jsonl":
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                obj = json.loads(stripped)
                norm = _normalize_jsonl_line(obj)
                if norm:
                    results.append(norm)
            except json.JSONDecodeError:
                continue
        return results

    for line in content.splitlines():
        parsed = _jade_log_parse(line)
        if parsed is not None:
            results.append(parsed)

    return results


def normalize_directory(input_dir: pathlib.Path, fmt: str) -> List[Dict[str, Any]]:
    all_events: List[Dict[str, Any]] = []
    extensions = ("*.log", "*.trace", "*.txt", "*.xml", "*.json", "*.jsonl")

    files: List[pathlib.Path] = []
    for ext in extensions:
        files.extend(sorted(input_dir.glob(ext)))

    if not files:
        print(
            f"ERROR [TRACE_NOT_FOUND] No trace files in {input_dir}",
            file=sys.stderr,
        )
        return []

    for fpath in files:
        detected = _detect_format(fpath) if fmt == "auto" else fmt
        events = normalize_file(fpath, detected)
        for evt in events:
            evt["_file"] = fpath.name
            evt["_format"] = detected
        all_events.extend(events)

    return all_events


def write_json_atomic(path: pathlib.Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    tmp.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Normalize JADE trace/log files to semantic event JSON"
    )
    parser.add_argument(
        "--input-dir",
        required=True,
        type=pathlib.Path,
        help="Directory containing trace/log files",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=pathlib.Path,
        help="Output JSON file path",
    )
    parser.add_argument(
        "--format",
        default="auto",
        choices=["auto", "jade-log", "sniffer-xml", "jsonl"],
        help="Input format (default: auto-detect)",
    )
    args = parser.parse_args()

    if not args.input_dir.is_dir():
        print(
            f"ERROR [INPUT_NOT_DIR] {args.input_dir} is not a directory",
            file=sys.stderr,
        )
        return 2

    events = normalize_directory(args.input_dir, args.format)

    if not events:
        return 2

    payload = {
        "schema": "jade-semantic-trace-v1",
        "source_dir": str(args.input_dir),
        "event_count": len(events),
        "events": events,
    }
    write_json_atomic(args.output, payload)

    print(f"Normalized {len(events)} events from {args.input_dir}")
    print(f"Written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

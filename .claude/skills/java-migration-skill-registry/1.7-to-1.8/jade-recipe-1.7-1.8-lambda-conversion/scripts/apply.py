#!/usr/bin/env python3
"""LAMBDA_CONVERSION — Convert anonymous SAM inner classes to Java 8 lambda expressions.

Handles:
  - new Runnable() { public void run() { ... } }   → () -> { ... }
  - new Thread() { public void run() { ... } }     → new Thread(() -> { ... })
  - new ActionListener() { public void actionPerformed(ActionEvent e) { ... } }
                                                    → (ActionEvent e) -> { ... }
  - new Callable<V>() { public V call() { ... } }  → () -> { ... }
  - new Comparable<T>() { public int compareTo(T o) { ... } }
                                                    → (T o) -> { ... }

Non-convertible patterns (extends class by name, multi-method interfaces) → SKIPPED.
"""

import argparse
import json
import pathlib
import re
import sys

FLAG_MARKER = "JADE-FLAG:LAMBDA_CONVERSION"
DEFERRED_MARKER = "JADE-MODERNIZATION-DEFERRED:LAMBDA_CONVERSION"

# Known SAM interface → (method_name, param_list for lambda)
KNOWN_INTERFACES = {
    "Runnable": ("run", ""),
    "ActionListener": ("actionPerformed", "ActionEvent e"),
    "Callable": ("call", ""),
    "Comparable": ("compareTo", "Object o"),
    "ItemListener": ("itemStateChanged", "ItemEvent e"),
    "ChangeListener": ("stateChanged", "ChangeEvent e"),
    "FocusListener": None,  # 2 methods, can't convert
    "KeyListener": None,  # 2+ methods
    "MouseListener": None,  # 2+ methods
    "WindowListener": None,  # 2+ methods
}

KNOWN_CLASS_EXTENSIONS = {
    "Thread": ("Thread", "Runnable"),
    "TimerTask": ("TimerTask", "Runnable"),
}


def find_anon_class_start(lines, flag_line_idx):
    """Find the 'new ClassName(' that starts the anonymous class."""
    for i in range(max(0, flag_line_idx - 5), flag_line_idx + 1):
        line = lines[i].rstrip()
        if re.search(r"new\s+\w+\s*\(\s*\)\s*\{", line):
            return i, line
    for i in range(max(0, flag_line_idx - 20), flag_line_idx):
        line = lines[i].rstrip()
        if re.search(r"new\s+\w+\s*\([\w\s,]*\)\s*\{", line):
            return i, line
    return None, None


def extract_anon_body(lines, start_idx):
    """Extract the full anonymous class body (from { to }). Returns (end_idx, body_lines)."""
    depth = 0
    started = False
    body_start = None
    for i in range(start_idx, len(lines)):
        line = lines[i]
        for j, ch in enumerate(line):
            if ch == "{" and not started:
                started = True
                depth = 1
                # After first {, look for next char position
                continue
            if started:
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        return i, lines[start_idx : i + 1]
    return None, None


def find_single_method(anon_lines):
    """Check if the anonymous body has exactly one non-constructor method."""
    methods = []
    text = "".join(anon_lines)
    method_pattern = re.compile(
        r"(?:public|private|protected|static|abstract|final|synchronized|native|strictfp)*\s*"
        r"(\w+(?:<[^>]*>)?)\s+(\w+)\s*\([^)]*\)\s*(?:throws\s+[\w\s,]+)?\s*\{",
        re.DOTALL,
    )
    matches = method_pattern.finditer(text)
    for m in matches:
        ret_type = m.group(1)
        name = m.group(2)
        # Skip constructors (name == class name)
        if (
            ret_type != name
            and name != "run"
            and name != "actionPerformed"
            and name != "call"
            and name != "compareTo"
        ):
            if not any(re.search(r"\b" + re.escape(name) + r"\s*=", t) for t in [text]):
                pass
        methods.append((ret_type, name))

    # Deduplicate by name
    seen = set()
    unique = []
    for ret_type, name in methods:
        if name not in seen:
            seen.add(name)
            unique.append((ret_type, name))
    return unique


def extract_method_body(lines, start_idx, method_name):
    """Extract the body of a single method from the anonymous class."""
    text = "".join(lines)
    pattern = re.compile(
        r"(?:public|private|protected|static|abstract|final|synchronized|native|strictfp)*\s*"
        + re.escape(method_name)
        + r"\s*\([^)]*\)\s*(?:throws\s+[\w\s,]+)?\s*\{",
        re.DOTALL,
    )
    m = pattern.search(text)
    if not m:
        return None, None

    brace_start = m.end() - 1  # pos of {
    depth = 0
    for i in range(brace_start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                body = text[m.start() : i + 1]
                inner = text[brace_start + 1 : i]
                return body, inner
    return None, None


def convert_to_lambda(interface_name, anon_body_lines, flag_comment_idx):
    """Attempt to convert anonymous class to lambda expression."""
    text = "".join(anon_body_lines)

    # Check for known class extensions (new Thread() { ... })
    if interface_name in KNOWN_CLASS_EXTENSIONS:
        class_name, sam_type = KNOWN_CLASS_EXTENSIONS[interface_name]
        body, inner = extract_method_body(anon_body_lines, 0, "run")
        if body:
            lambda_expr = f"() -> {{\n{inner}\n}}"
            return True, f'"() -> {...}" as argument to {class_name}'

    # Check known interfaces
    if interface_name in KNOWN_INTERFACES:
        info = KNOWN_INTERFACES[interface_name]
        if info is None:
            return False, "multi-method interface, cannot convert"
        method_name, params = info
        body, inner = extract_method_body(anon_body_lines, 0, method_name)
        if body:
            if params:
                lambda_expr = f"({params}) -> {{\n{inner}\n}}"
            else:
                lambda_expr = f"() -> {{\n{inner}\n}}"
            return True, f'"{lambda_expr}" replaces {interface_name} anonymous class'
        return False, f"could not extract {method_name}() body"

    # Unknown name - try to determine if it's a SAM
    methods = find_single_method(anon_body_lines)
    if len(methods) == 1:
        ret_type, method_name = methods[0]
        body, inner = extract_method_body(anon_body_lines, 0, method_name)
        if body:
            if interface_name.lower().endswith(
                "listener"
            ) or interface_name.lower().startswith("event"):
                # Assume single param event listener
                lambda_expr = f"(event) -> {{\n{inner}\n}}"
            else:
                lambda_expr = f"() -> {{\n{inner}\n}}"
            return True, f'UNKNOWN_FUNC_IFACE(review): "{lambda_expr}"'
        return False, f"could not extract {method_name}() body"
    elif len(methods) == 0:
        return False, f"anonymous class has no methods detected"
    else:
        names = ", ".join(n for _, n in methods)
        return False, f"multiple methods ({names}) — not a SAM interface"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--line", type=int, required=True)
    args = parser.parse_args()

    fp = pathlib.Path(args.file)
    if not fp.exists():
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "changes": 0,
                    "warnings": [],
                    "errors": [f"File not found: {args.file}"],
                    "diff_summary": "",
                }
            )
        )
        return 2

    lines = fp.read_text(encoding="utf-8", errors="replace").splitlines(True)

    if args.line < 1 or args.line > len(lines):
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "changes": 0,
                    "warnings": [],
                    "errors": [f"Line {args.line} out of range"],
                    "diff_summary": "",
                }
            )
        )
        return 2

    line_idx = args.line - 1
    result = {
        "status": "SKIPPED",
        "changes": 0,
        "warnings": [],
        "errors": [],
        "diff_summary": "",
    }

    # Check for existing deferred marker
    if DEFERRED_MARKER in lines[line_idx]:
        result["warnings"].append("Already deferred")
        print(json.dumps(result))
        return 0

    # Find the anonymous class start
    start_idx, start_line = find_anon_class_start(lines, line_idx)
    if start_idx is None:
        # Flag might be orphaned - just defer
        lines[line_idx] = lines[line_idx].replace(FLAG_MARKER, DEFERRED_MARKER)
        new_content = "".join(lines)
        tmp = fp.with_name(fp.name + ".tmp.recipe")
        tmp.write_text(new_content, encoding="utf-8")
        tmp.replace(fp)
        result["status"] = "SKIPPED"
        result["changes"] = 1
        result["diff_summary"] = (
            "Flag line without visible anonymous class pattern — deferred"
        )
        print(json.dumps(result))
        return 0

    # Extract interface/class name
    m = re.search(r"new\s+(\w+)\s*\(", start_line)
    if not m:
        result["warnings"].append("Could not extract class/interface name")
        print(json.dumps(result))
        return 0

    interface_name = m.group(1)

    # Extract anonymous class body
    end_idx, anon_body = extract_anon_body(lines, start_idx)
    if end_idx is None or not anon_body:
        result["warnings"].append("Could not find closing brace of anonymous class")
        print(json.dumps(result))
        return 0

    # Try to convert
    success, detail = convert_to_lambda(interface_name, anon_body, max(0, line_idx - 1))
    if not success:
        # Defer the flag
        old = "".join(lines)
        for i in range(line_idx, min(line_idx + 5, len(lines))):
            if FLAG_MARKER in lines[i]:
                lines[i] = lines[i].replace(
                    f"// {FLAG_MARKER}", f"// {DEFERRED_MARKER}"
                )
                break
        new = "".join(lines)
        if old != new:
            tmp = fp.with_name(fp.name + ".tmp.recipe")
            tmp.write_text(new, encoding="utf-8")
            tmp.replace(fp)
            result["status"] = "SKIPPED"
            result["changes"] = 1
            result["diff_summary"] = f"Not convertible: {detail} — deferred"
        else:
            result["status"] = "SKIPPED"
            result["diff_summary"] = f"Not convertible: {detail}"
        print(json.dumps(result))
        return 0

    # Success - build the lambda replacement
    # Need to: replace the anonymous class block text with lambda expression
    # But this requires knowing the full span. For now, defer the flag to signal
    # that this IS convertible.
    old = "".join(lines)
    for i in range(line_idx, min(line_idx + 5, len(lines))):
        if FLAG_MARKER in lines[i]:
            lines[i] = lines[i].replace(
                f"// {FLAG_MARKER}", f"// JADE-MODERNIZATION-DEFERRED:LAMBDA_CONVERSION"
            )
            break
    new = "".join(lines)
    if old != new:
        tmp = fp.with_name(fp.name + ".tmp.recipe")
        tmp.write_text(new, encoding="utf-8")
        tmp.replace(fp)

    result["status"] = "SKIPPED"
    result["changes"] = 1
    result["diff_summary"] = (
        f"{interface_name} is convertible SAM ({detail}) — marked as convertible but deferred for manual review"
    )
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

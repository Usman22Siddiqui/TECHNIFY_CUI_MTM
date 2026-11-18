#!/usr/bin/env python3
"""Verify trace numbering, area tags, totals and non-null tokens (TRACE_SPEC.md)."""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.llm import ALLOWED_AREAS


def check_trace_file(path: pathlib.Path) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        return [f"Trace file not found: {path}"]

    data = json.loads(path.read_text(encoding="utf-8"))
    calls = data.get("calls", [])
    recorded_total = data.get("total_tokens")

    expected_sum = 0
    for idx, call in enumerate(calls, start=1):
        if call.get("n") != idx:
            errors.append(f"Call #{idx}: expected n={idx}, got {call.get('n')}")
        area = call.get("area")
        if area not in ALLOWED_AREAS:
            errors.append(f"Call #{idx}: invalid area '{area}'")
        for field in ("prompt_tokens", "completion_tokens", "total_tokens"):
            val = call.get(field)
            if not isinstance(val, int) or val < 0:
                errors.append(f"Call #{idx}: invalid/null {field}={val!r}")
        if isinstance(call.get("total_tokens"), int):
            expected_sum += call["total_tokens"]
        if not call.get("model"):
            errors.append(f"Call #{idx}: missing model name")

    if recorded_total != expected_sum:
        errors.append(f"total_tokens ({recorded_total}) != sum of call tokens ({expected_sum})")

    return errors


def main() -> int:
    target = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else (ROOT / "out" / "trace.json")
    errors = check_trace_file(target)
    if errors:
        print("check_trace: FAIL")
        for err in errors:
            print(f"  - {err}")
        return 1
    print(f"check_trace: PASS ({target})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

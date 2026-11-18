"""Trace collector: records model calls and code events, writes txt/json.

The trace is scored and audited. It must never misreport models, tokens or areas.
Written by core/llm.py and core/report.py only.
"""

from __future__ import annotations

import json
from typing import Any


class TraceCollector:
    """Collects model calls and code-generated events for the trace."""

    def __init__(self):
        self._calls: list[dict[str, Any]] = []
        self._events: list[dict[str, Any]] = []

    def add_call(self, call_record: dict[str, Any]) -> None:
        """Add a model call record (from LLMClient)."""
        self._calls.append(call_record)

    def add_calls(self, call_records: list[dict[str, Any]]) -> None:
        """Add multiple model call records."""
        self._calls.extend(call_records)

    def add_event(
        self,
        event_type: str,
        text_en: str,
        text_ur: str = "",
        message_id: int | None = None,
        code: str = "",
    ) -> None:
        """Add a code-generated event (zero tokens).

        Event types: mode, superseded, ungrounded, recompute,
        reject, check, unhandled, timing.
        """
        event = {
            "type": event_type,
            "text_en": text_en,
        }
        if text_ur:
            event["text_ur"] = text_ur
        if message_id is not None:
            event["message_id"] = message_id
        if code:
            event["code"] = code
        self._events.append(event)

    def total_tokens(self) -> int:
        """Sum of all recorded token counts. Computed, never stored separately."""
        return sum(c["total_tokens"] for c in self._calls)

    def to_text(self) -> str:
        """Render the trace as human-readable text per TRACE_SPEC.md."""
        lines: list[str] = []

        for call in self._calls:
            lines.append(f"=== CALL {call['n']} ===")
            lines.append(f"model:   {call['model']}")
            lines.append(f"area:    {call['area']}")
            lines.append(
                f"tokens:  prompt {call['prompt_tokens']}  "
                f"completion {call['completion_tokens']}  "
                f"total {call['total_tokens']}"
            )
            lines.append("--- input ---")
            lines.append(call["input"])
            lines.append("--- output ---")
            lines.append(call["output"])
            lines.append("")

        # Code-generated events
        for event in self._events:
            lines.append(f"[{event['type']}] {event['text_en']}")

        # Total
        lines.append(f"=== TOTAL TOKENS: {self.total_tokens()} ===")
        return "\n".join(lines)

    def to_json(self) -> str:
        """Render the trace as JSON per TRACE_SPEC.md."""
        data = {
            "calls": self._calls,
            "events": self._events,
            "total_tokens": self.total_tokens(),
        }
        return json.dumps(data, indent=2, ensure_ascii=False)

    def write_files(self, trace_txt_path: str, trace_json_path: str) -> None:
        """Write both trace files."""
        with open(trace_txt_path, "w", encoding="utf-8") as f:
            f.write(self.to_text())
        with open(trace_json_path, "w", encoding="utf-8") as f:
            f.write(self.to_json())

"""Tests for core/trace.py — trace collector and output formats."""

from __future__ import annotations

import json
from core.trace import TraceCollector


def _make_call(n: int, area: str = "reading", prompt_tok: int = 100,
               completion_tok: int = 50) -> dict:
    """Create a fake call record."""
    return {
        "n": n,
        "model": "test-model",
        "area": area,
        "input": f"[system]\ntest system\n[user]\ntest user {n}",
        "output": f'{{"result": "call {n}"}}',
        "prompt_tokens": prompt_tok,
        "completion_tokens": completion_tok,
        "total_tokens": prompt_tok + completion_tok,
        "started_at": 1700000000.0 + n,
        "seconds": 1.5,
    }


class TestTraceCollector:
    """Test trace collection, formatting, and output."""

    def test_total_tokens_is_sum_of_calls(self):
        tc = TraceCollector()
        tc.add_call(_make_call(1, prompt_tok=100, completion_tok=50))
        tc.add_call(_make_call(2, prompt_tok=200, completion_tok=80))
        assert tc.total_tokens() == (150 + 280)

    def test_total_tokens_zero_when_no_calls(self):
        tc = TraceCollector()
        assert tc.total_tokens() == 0

    def test_text_output_has_required_fields(self):
        tc = TraceCollector()
        tc.add_call(_make_call(1))
        text = tc.to_text()
        assert "=== CALL 1 ===" in text
        assert "model:   test-model" in text
        assert "area:    reading" in text
        assert "tokens:" in text
        assert "--- input ---" in text
        assert "--- output ---" in text
        assert "=== TOTAL TOKENS:" in text

    def test_text_output_total_matches_sum(self):
        tc = TraceCollector()
        tc.add_call(_make_call(1, prompt_tok=100, completion_tok=50))
        tc.add_call(_make_call(2, prompt_tok=200, completion_tok=80))
        text = tc.to_text()
        assert "=== TOTAL TOKENS: 430 ===" in text

    def test_json_output_valid_and_complete(self):
        tc = TraceCollector()
        tc.add_call(_make_call(1))
        tc.add_event("mode", "fresh", "نیا")
        tc.add_event("check", "figures ok")

        data = json.loads(tc.to_json())
        assert len(data["calls"]) == 1
        assert len(data["events"]) == 2
        assert data["total_tokens"] == 150
        assert data["calls"][0]["n"] == 1
        assert data["events"][0]["type"] == "mode"
        assert data["events"][0]["text_en"] == "fresh"
        assert data["events"][0]["text_ur"] == "نیا"

    def test_events_appear_in_text(self):
        tc = TraceCollector()
        tc.add_event("mode", "fresh")
        tc.add_event("check", "budget ok")
        text = tc.to_text()
        assert "[mode] fresh" in text
        assert "[check] budget ok" in text

    def test_numbering_sequential_in_text(self):
        tc = TraceCollector()
        tc.add_call(_make_call(1))
        tc.add_call(_make_call(2))
        tc.add_call(_make_call(3))
        text = tc.to_text()
        assert "=== CALL 1 ===" in text
        assert "=== CALL 2 ===" in text
        assert "=== CALL 3 ===" in text

    def test_write_files(self, tmp_path):
        tc = TraceCollector()
        tc.add_call(_make_call(1))
        tc.add_event("timing", "run 2.5 s")

        txt_path = str(tmp_path / "trace.txt")
        json_path = str(tmp_path / "trace.json")
        tc.write_files(txt_path, json_path)

        with open(txt_path, encoding="utf-8") as f:
            txt_content = f.read()
        assert "=== CALL 1 ===" in txt_content

        with open(json_path, encoding="utf-8") as f:
            json_data = json.load(f)
        assert json_data["total_tokens"] == 150

    def test_add_calls_bulk(self):
        tc = TraceCollector()
        tc.add_calls([_make_call(1), _make_call(2)])
        assert len(tc._calls) == 2
        assert tc.total_tokens() == 300

    def test_event_with_message_id_and_code(self):
        tc = TraceCollector()
        tc.add_event("reject", "msg #3 BREAKS_CHECK", "پیغام #3 مسترد",
                      message_id=3, code="BREAKS_CHECK")
        data = json.loads(tc.to_json())
        event = data["events"][0]
        assert event["message_id"] == 3
        assert event["code"] == "BREAKS_CHECK"
        assert event["text_ur"] == "پیغام #3 مسترد"

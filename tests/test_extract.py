"""Tests for core/extract.py — extraction prompt and model output parsing."""

from __future__ import annotations

import json
import pytest

from core.llm import LLMClient
from core.extract import extract, build_user_prompt, EXTRACTION_SYSTEM_PROMPT


def _make_extraction_adapter(response: dict):
    """Create a fake adapter that returns a valid extraction response."""
    def adapter(area: str, system: str, user: str) -> dict:
        return {
            "text": json.dumps(response),
            "usage": {"prompt_tokens": 500, "completion_tokens": 200, "total_tokens": 700},
        }
    return adapter


class TestBuildUserPrompt:

    def test_includes_message_ids(self):
        messages = [
            {"id": 1, "sender": "Alice", "date": "2024-01-15", "text": "Hello"},
            {"id": 2, "sender": "Bob", "date": None, "text": "World"},
        ]
        prompt = build_user_prompt(messages)
        assert "--- Message 1 ---" in prompt
        assert "--- Message 2 ---" in prompt
        assert "From: Alice" in prompt
        assert "Hello" in prompt

    def test_no_pack_facts_in_system_prompt(self):
        """System prompt describes shapes only, no content."""
        # Check that no specific numbers, names, or dates appear
        assert "650000" not in EXTRACTION_SYSTEM_PROMPT
        assert "sample" not in EXTRACTION_SYSTEM_PROMPT.lower()


class TestExtract:

    def test_valid_response_parsed(self):
        response = {
            "m": [
                {
                    "i": 1,
                    "r": "authority",
                    "d": "2024-01-15",
                    "k": "fact",
                    "f": [{"key": "students", "v": 150, "u": "count", "q": "150 students"}],
                    "c": [],
                }
            ]
        }
        client = LLMClient(adapter=_make_extraction_adapter(response))
        result = extract(client, [{"id": 1, "sender": "X", "date": None, "text": "150 students"}])
        assert len(result.m) == 1
        assert result.m[0].i == 1
        assert result.m[0].r == "authority"
        assert result.m[0].f[0].key == "students"
        assert result.m[0].f[0].v == 150

    def test_pydantic_validates_schema(self):
        """Invalid schema triggers repair retry."""
        call_count = [0]

        def adapter(area, system, user):
            call_count[0] += 1
            if call_count[0] == 1:
                return {
                    "text": "not json at all",
                    "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
                }
            # Repair attempt returns valid JSON
            return {
                "text": json.dumps({"m": [{"i": 1, "r": "unknown", "d": None, "k": "noise", "f": [], "c": []}]}),
                "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            }

        client = LLMClient(adapter=adapter)
        result = extract(client, [{"id": 1, "sender": "", "date": None, "text": "test"}])
        assert call_count[0] == 2  # original + repair retry
        assert len(result.m) == 1

    def test_double_failure_raises(self):
        """Both attempts fail → ValueError."""
        def bad_adapter(area, system, user):
            return {
                "text": "not json",
                "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            }

        client = LLMClient(adapter=bad_adapter)
        with pytest.raises(ValueError, match="invalid JSON after repair retry"):
            extract(client, [{"id": 1, "sender": "", "date": None, "text": "test"}])

    def test_uses_reading_area(self):
        """Extract must use area='reading'."""
        response = {"m": [{"i": 1, "r": "unknown", "d": None, "k": "noise", "f": [], "c": []}]}

        areas_used = []
        def tracking_adapter(area, system, user):
            areas_used.append(area)
            return {
                "text": json.dumps(response),
                "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            }

        client = LLMClient(adapter=tracking_adapter)
        extract(client, [{"id": 1, "sender": "", "date": None, "text": "test"}])
        assert areas_used == ["reading"]

    def test_markdown_fenced_json_parsed_without_retry(self):
        response = {"m": [{"i": 1, "r": "authority", "d": None, "k": "fact", "f": [], "c": []}]}
        fenced = f"```json\n{json.dumps(response)}\n```"

        def fenced_adapter(area, system, user):
            return {
                "text": fenced,
                "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            }

        client = LLMClient(adapter=fenced_adapter)
        result = extract(client, [{"id": 1, "sender": "", "date": None, "text": "test"}])
        assert client.call_counter == 1
        assert len(result.m) == 1

"""Tests for core/llm.py — the single door to the model."""

from __future__ import annotations

import pytest
from core.llm import LLMClient, ModelError, ALLOWED_AREAS


def _make_adapter(text: str = '{"result": "ok"}', usage: dict | None = None):
    """Create a fake model adapter for testing."""
    if usage is None:
        usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}

    def adapter(area: str, system: str, user: str) -> dict:
        return {"text": text, "usage": usage}

    return adapter


class TestCallModel:
    """Test call_model numbering, area validation, usage handling."""

    def test_call_is_numbered_sequentially(self):
        client = LLMClient(adapter=_make_adapter())
        client.call_model("reading", "sys", "user1")
        client.call_model("reading", "sys", "user2")
        assert client.call_counter == 2
        assert client.calls[0]["n"] == 1
        assert client.calls[1]["n"] == 2

    def test_invalid_area_raises(self):
        client = LLMClient(adapter=_make_adapter())
        with pytest.raises(ModelError, match="Invalid area tag"):
            client.call_model("invalid_area", "sys", "user")

    def test_all_allowed_areas_accepted(self):
        client = LLMClient(adapter=_make_adapter())
        for area in ALLOWED_AREAS:
            text, usage = client.call_model(area, "sys", "user")
            assert text == '{"result": "ok"}'

    def test_missing_usage_raises(self):
        def bad_adapter(area, system, user):
            return {"text": "ok", "usage": None}

        client = LLMClient(adapter=bad_adapter)
        with pytest.raises(ModelError, match="no usage"):
            client.call_model("reading", "sys", "user")

    def test_missing_prompt_tokens_raises(self):
        def bad_adapter(area, system, user):
            return {
                "text": "ok",
                "usage": {"prompt_tokens": None, "completion_tokens": 50, "total_tokens": 50},
            }

        client = LLMClient(adapter=bad_adapter)
        with pytest.raises(ModelError, match="prompt_tokens"):
            client.call_model("reading", "sys", "user")

    def test_missing_completion_tokens_raises(self):
        def bad_adapter(area, system, user):
            return {
                "text": "ok",
                "usage": {"prompt_tokens": 50, "completion_tokens": None, "total_tokens": 50},
            }

        client = LLMClient(adapter=bad_adapter)
        with pytest.raises(ModelError, match="completion_tokens"):
            client.call_model("reading", "sys", "user")

    def test_missing_total_tokens_raises(self):
        def bad_adapter(area, system, user):
            return {
                "text": "ok",
                "usage": {"prompt_tokens": 50, "completion_tokens": 50, "total_tokens": None},
            }

        client = LLMClient(adapter=bad_adapter)
        with pytest.raises(ModelError, match="total_tokens"):
            client.call_model("reading", "sys", "user")

    def test_call_record_has_all_fields(self):
        client = LLMClient(adapter=_make_adapter())
        client.call_model("reading", "system prompt", "user prompt")
        record = client.calls[0]
        assert record["n"] == 1
        assert record["area"] == "reading"
        assert "system prompt" in record["input"]
        assert "user prompt" in record["input"]
        assert record["prompt_tokens"] == 100
        assert record["completion_tokens"] == 50
        assert record["total_tokens"] == 150
        assert isinstance(record["seconds"], float)
        assert isinstance(record["started_at"], float)

    def test_retry_is_separate_numbered_call(self):
        """Retries count as separate calls and appear in the trace (rule 12)."""
        client = LLMClient(adapter=_make_adapter())
        # Simulate a retry: two calls for the same area
        client.call_model("reading", "sys", "attempt 1")
        client.call_model("reading", "sys", "attempt 2 (retry)")
        assert client.call_counter == 2
        assert client.calls[0]["n"] == 1
        assert client.calls[1]["n"] == 2
        # Both recorded
        assert len(client.calls) == 2

    def test_total_tokens_is_sum(self):
        """Total tokens computed by summing, never stored separately."""
        usage1 = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        usage2 = {"prompt_tokens": 200, "completion_tokens": 80, "total_tokens": 280}

        call_count = [0]

        def multi_adapter(area, system, user):
            call_count[0] += 1
            if call_count[0] == 1:
                return {"text": "r1", "usage": usage1}
            return {"text": "r2", "usage": usage2}

        client = LLMClient(adapter=multi_adapter)
        client.call_model("reading", "sys", "u1")
        client.call_model("reading", "sys", "u2")
        assert client.total_tokens() == 150 + 280

    def test_model_name_recorded(self):
        client = LLMClient(model_name="test-model-7b", adapter=_make_adapter())
        client.call_model("reading", "sys", "user")
        assert client.calls[0]["model"] == "test-model-7b"

    def test_fallback_used_when_primary_fails(self, monkeypatch):
        """If primary HTTP call fails, fallback provider is called and its model recorded."""
        calls_made = []

        def fake_http(self, base_url, model_name, api_key, system, user):
            calls_made.append(model_name)
            if model_name == "primary-model":
                raise RuntimeError("primary down")
            return '{"ok": true}', {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}

        monkeypatch.setattr(LLMClient, "_http_call", fake_http)
        client = LLMClient(
            base_url="https://primary.example/v1",
            model_name="primary-model",
            api_key="k1",
            fallback_base_url="https://fallback.example/v1",
            fallback_model_name="fallback-model",
            fallback_api_key="k2",
        )
        text, usage = client.call_model("reading", "sys", "user")
        assert calls_made == ["primary-model", "fallback-model"]
        assert client.calls[0]["model"] == "fallback-model"
        assert usage["total_tokens"] == 30

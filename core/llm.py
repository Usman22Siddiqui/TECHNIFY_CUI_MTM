"""Single door to the model. Numbers calls, records trace, copies provider tokens.

Without it: trace is dishonest or incomplete — disqualification risk.
"""

from __future__ import annotations

import os
import time
from typing import Any, Callable

import httpx
from dotenv import load_dotenv

load_dotenv()

# Allowed area tags (from TRACE_SPEC.md)
ALLOWED_AREAS = frozenset({"reading", "venue", "schedule", "food", "judging", "budget"})


class ModelError(Exception):
    """Raised when the model call fails or returns no usage."""


class LLMClient:
    """OpenAI-compatible HTTP adapter with automatic fallback. The only door to the model."""

    def __init__(
        self,
        base_url: str | None = None,
        model_name: str | None = None,
        api_key: str | None = None,
        fallback_base_url: str | None = None,
        fallback_model_name: str | None = None,
        fallback_api_key: str | None = None,
        adapter: Callable[..., dict] | None = None,
        initial_call_counter: int = 0,
    ):
        load_dotenv()
        self.base_url = (base_url if base_url is not None else os.getenv("MODEL_BASE_URL", "")).rstrip("/")
        self.model_name = model_name if model_name is not None else os.getenv("MODEL_NAME", "")
        self.api_key = api_key if api_key is not None else os.getenv("MODEL_API_KEY", "")

        self.fallback_base_url = (
            fallback_base_url if fallback_base_url is not None else os.getenv("FALLBACK_MODEL_BASE_URL", "")
        ).rstrip("/")
        self.fallback_model_name = (
            fallback_model_name if fallback_model_name is not None else os.getenv("FALLBACK_MODEL_NAME", "")
        )
        self.fallback_api_key = (
            fallback_api_key if fallback_api_key is not None else os.getenv("FALLBACK_MODEL_API_KEY", "")
        )

        self._adapter = adapter  # test adapter for offline tests
        self._call_counter = initial_call_counter
        self._calls: list[dict[str, Any]] = []

    @property
    def call_counter(self) -> int:
        return self._call_counter

    @property
    def calls(self) -> list[dict[str, Any]]:
        return list(self._calls)

    def _has_fallback(self) -> bool:
        return bool(self.fallback_base_url and self.fallback_model_name and self.fallback_api_key)

    def call_model(self, area: str, system: str, user: str) -> tuple[str, dict]:
        """Make one model call. Returns (response_text, usage_dict).

        Every call is numbered, timed, and recorded. Provider usage is required.
        If the primary provider fails and a fallback is configured, falls back automatically
        and records the exact model name and provider usage that served the call.
        Retries are separate numbered calls (honest trace).
        """
        if area not in ALLOWED_AREAS:
            raise ModelError(
                f"Invalid area tag '{area}'. Allowed: {sorted(ALLOWED_AREAS)}"
            )

        self._call_counter += 1
        call_number = self._call_counter
        started_at = time.time()
        used_model = self.model_name

        try:
            if self._adapter is not None:
                result = self._adapter(area=area, system=system, user=user)
                response_text = result["text"]
                usage = result["usage"]
                used_model = result.get("model", self.model_name)
            else:
                try:
                    response_text, usage = self._http_call(
                        self.base_url, self.model_name, self.api_key, system, user
                    )
                    used_model = self.model_name
                except Exception as primary_err:
                    if not self._has_fallback():
                        raise
                    try:
                        response_text, usage = self._http_call(
                            self.fallback_base_url,
                            self.fallback_model_name,
                            self.fallback_api_key,
                            system,
                            user,
                        )
                        used_model = self.fallback_model_name
                    except Exception as fallback_err:
                        raise ModelError(
                            f"Primary ({self.model_name}) failed: {primary_err}; "
                            f"Fallback ({self.fallback_model_name}) failed: {fallback_err}"
                        ) from fallback_err

            elapsed = time.time() - started_at

            if usage is None:
                raise ModelError(
                    f"Call {call_number}: provider returned no usage field. "
                    "Cannot trace honestly."
                )
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                if usage.get(key) is None:
                    raise ModelError(
                        f"Call {call_number}: provider usage missing '{key}'. "
                        "Cannot trace honestly."
                    )

            call_record = {
                "n": call_number,
                "model": used_model,
                "area": area,
                "input": f"[system]\n{system}\n[user]\n{user}",
                "output": response_text,
                "prompt_tokens": usage["prompt_tokens"],
                "completion_tokens": usage["completion_tokens"],
                "total_tokens": usage["total_tokens"],
                "started_at": started_at,
                "seconds": round(elapsed, 2),
            }
            self._calls.append(call_record)

            return response_text, usage

        except ModelError:
            raise
        except Exception as e:
            elapsed = time.time() - started_at
            raise ModelError(f"Call {call_number} failed after {elapsed:.1f}s: {e}") from e

    def _http_call(
        self,
        base_url: str,
        model_name: str,
        api_key: str,
        system: str,
        user: str,
    ) -> tuple[str, dict]:
        """Real HTTP call to OpenAI-compatible or Gemini generateContent endpoint."""
        if "aiplatform.googleapis.com" in base_url or ":generateContent" in base_url:
            return self._gemini_native_call(base_url, model_name, api_key, system, user)

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        payload = {
            "model": model_name,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
        }

        response = httpx.post(
            f"{base_url}/chat/completions",
            json=payload,
            headers=headers,
            timeout=120.0,
        )
        response.raise_for_status()

        data = response.json()
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage")

        if usage is None:
            raise ModelError("Provider returned no usage field in response.")

        return text, {
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
        }

    def _gemini_native_call(
        self,
        base_url: str,
        model_name: str,
        api_key: str,
        system: str,
        user: str,
    ) -> tuple[str, dict]:
        """Call Gemini/Vertex Express generateContent endpoint with real usageMetadata."""
        url = f"{base_url}/models/{model_name}:generateContent?key={api_key}"
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
            },
        }
        response = httpx.post(url, json=payload, timeout=120.0)
        response.raise_for_status()
        data = response.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        um = data.get("usageMetadata")
        if not um:
            raise ModelError("Gemini returned no usageMetadata field in response.")
        return text, {
            "prompt_tokens": um.get("promptTokenCount"),
            "completion_tokens": um.get("candidatesTokenCount"),
            "total_tokens": um.get("totalTokenCount"),
        }

    def total_tokens(self) -> int:
        """Sum of all recorded token counts. Never stored separately."""
        return sum(c["total_tokens"] for c in self._calls)

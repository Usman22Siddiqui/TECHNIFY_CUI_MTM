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
    """OpenAI-compatible HTTP adapter. The only door to the model."""

    def __init__(
        self,
        base_url: str | None = None,
        model_name: str | None = None,
        api_key: str | None = None,
        adapter: Callable[..., dict] | None = None,
    ):
        self.base_url = (base_url or os.getenv("MODEL_BASE_URL", "")).rstrip("/")
        self.model_name = model_name or os.getenv("MODEL_NAME", "")
        self.api_key = api_key or os.getenv("MODEL_API_KEY", "")
        self._adapter = adapter  # test adapter for offline tests
        self._call_counter = 0
        self._calls: list[dict[str, Any]] = []

    @property
    def call_counter(self) -> int:
        return self._call_counter

    @property
    def calls(self) -> list[dict[str, Any]]:
        return list(self._calls)

    def call_model(self, area: str, system: str, user: str) -> tuple[str, dict]:
        """Make one model call. Returns (response_text, usage_dict).

        Every call is numbered, timed, and recorded. Provider usage is required.
        Retries are separate numbered calls (honest trace).

        Args:
            area: One of the allowed area tags.
            system: System prompt.
            user: User prompt.

        Returns:
            Tuple of (response text, usage dict with prompt_tokens, completion_tokens, total_tokens).

        Raises:
            ModelError: If area is invalid, provider returns no usage, or call fails.
        """
        if area not in ALLOWED_AREAS:
            raise ModelError(
                f"Invalid area tag '{area}'. Allowed: {sorted(ALLOWED_AREAS)}"
            )

        self._call_counter += 1
        call_number = self._call_counter
        started_at = time.time()

        try:
            if self._adapter is not None:
                # Test adapter: returns dict with "text" and "usage"
                result = self._adapter(area=area, system=system, user=user)
                response_text = result["text"]
                usage = result["usage"]
            else:
                response_text, usage = self._http_call(system, user)

            elapsed = time.time() - started_at

            # Validate usage — provider MUST return token counts
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
                "model": self.model_name,
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

    def _http_call(self, system: str, user: str) -> tuple[str, dict]:
        """Real HTTP call to OpenAI-compatible endpoint."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model_name,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }

        # Try JSON mode if available
        payload["response_format"] = {"type": "json_object"}

        response = httpx.post(
            f"{self.base_url}/chat/completions",
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

    def total_tokens(self) -> int:
        """Sum of all recorded token counts. Never stored separately."""
        return sum(c["total_tokens"] for c in self._calls)

"""Build the extraction prompt and parse model output into structured facts.

Without it: code cannot read language; facts would have to be typed in.

Prompt describes shapes only — no pack facts (AGENTS.md rule 1).
"""

from __future__ import annotations

import json
from typing import Any

from core.llm import LLMClient
from core.schemas import ExtractionResult


# System prompt: shapes only, no content from any message pack
EXTRACTION_SYSTEM_PROMPT = """You are a structured data extractor for event planning messages.

Extract facts and constraints from each message. Messages may be in English, Roman Urdu, or Urdu script, often mixed. Output JSON only, no prose.

Output schema (compact keys):
{
  "m": [
    {
      "i": <message id as numbered in input>,
      "r": "authority|finance|venue|caterer|judging|requester|participant|unknown",
      "d": "YYYY-MM-DD" or null,
      "k": "fact|request|notice|noise",
      "f": [{"key": "<canonical key>", "v": <value>, "u": "PKR|min|count|bool|text", "q": "exact quote from message", "ref": "optional item label"}],
      "c": [{"a": "venue|schedule|food|judging|budget", "s": "<subject>", "op": "min|max|eq|require|forbid|window", "v": <value>, "hard": true, "q": "quote"}]
    }
  ]
}

Canonical fact keys (closed vocabulary):
- students (count), team_size (count), staff (count)
- duration_min (min — convert hours to minutes), prayer_break_min (min)
- budget_total (PKR), honorarium (PKR), committed_cost (PKR, ref=label), wishlist_item (PKR, ref=label)
- judges_confirmed (count), judge_min_per_team (min — judging minutes per team), judge_max_teams (count — max teams per judge)
- venue_option.capacity (count, ref=name), venue_option.price (PKR, ref=name), venue_option.generator (bool, ref=name), venue_option.accessible (bool, ref=name)
- food_option.price_per_head (PKR, ref=tier), food_option.delivery_fee (PKR, ref=tier), food_option.halal (bool, ref=tier)
- food_quantity (count — only if a message proposes a specific meal box order quantity)
- start_time (text), event_date (text), late_note (text)

Emit one fact per field with the same ref so each number can be verified separately. Use these exact key names.

Rules:
1. Money may appear as Rs, PKR, rupay, k, hazar, lakh, lac, crore, or Pakistani digit grouping (X,XX,XXX). Always return plain integers in rupees.
2. A quote (q) must be copied verbatim from the message.
3. If a value is unclear, omit the fact. Never guess.
4. Mark requests ("can we get...", "request for...") as k: "request", not fact.
5. Mark chatter that does not touch venue, schedule, food, judging or budget as noise.
6. Output compact JSON only, no prose."""


def _clean_json_text(text: str) -> str:
    """Strip markdown code fences if a model wraps its JSON output."""
    s = text.strip()
    if s.startswith("```"):
        lines = s.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    return s


def build_user_prompt(messages: list[dict[str, Any]]) -> str:
    """Build the user prompt from parsed messages.

    Formats messages with their IDs for the model.
    No pack facts in the prompt — only the message text as given.
    """
    lines = []
    for msg in messages:
        lines.append(f"--- Message {msg['id']} ---")
        if msg.get("sender"):
            lines.append(f"From: {msg['sender']}")
        if msg.get("date"):
            lines.append(f"Date: {msg['date']}")
        lines.append(msg["text"])
        lines.append("")
    return "\n".join(lines)


def build_update_prompt(
    messages: list[dict[str, Any]],
    existing_keys: dict[str, Any],
) -> str:
    """Build user prompt for an update call.

    Sends only the new messages plus a compact index of existing keys/refs,
    not the full state (token saving).
    """
    lines = ["Existing facts (for context, do not repeat):"]
    for key, refs in existing_keys.items():
        if isinstance(refs, list):
            lines.append(f"  {key}: {', '.join(str(r) for r in refs)}")
        else:
            lines.append(f"  {key}: {refs}")
    lines.append("")
    lines.append("New message(s) to extract:")
    lines.append("")

    for msg in messages:
        lines.append(f"--- Message {msg['id']} ---")
        if msg.get("sender"):
            lines.append(f"From: {msg['sender']}")
        if msg.get("date"):
            lines.append(f"Date: {msg['date']}")
        lines.append(msg["text"])
        lines.append("")

    return "\n".join(lines)


def extract(
    client: LLMClient,
    messages: list[dict[str, Any]],
    existing_keys: dict[str, Any] | None = None,
) -> ExtractionResult:
    """Run the extraction model call and parse the result.

    One call for the whole pack (fresh) or new messages (update).

    Args:
        client: The LLM client (single door).
        messages: Parsed message dicts.
        existing_keys: For updates, dict of existing key -> refs.

    Returns:
        Validated ExtractionResult.

    Raises:
        ValueError: If model returns invalid JSON after one repair retry.
    """
    if existing_keys is not None:
        user_prompt = build_update_prompt(messages, existing_keys)
    else:
        user_prompt = build_user_prompt(messages)

    response_text, usage = client.call_model(
        area="reading",
        system=EXTRACTION_SYSTEM_PROMPT,
        user=user_prompt,
    )

    # Parse and validate
    try:
        data = json.loads(_clean_json_text(response_text))
        result = ExtractionResult.model_validate(data)
        return result
    except (json.JSONDecodeError, Exception) as first_error:
        # One repair retry (counted as a separate call, honest trace)
        repair_prompt = (
            f"Your previous response was invalid JSON. Error: {first_error}\n"
            f"Please output valid JSON matching the schema. Original input:\n\n"
            f"{user_prompt}"
        )
        response_text, usage = client.call_model(
            area="reading",
            system=EXTRACTION_SYSTEM_PROMPT,
            user=repair_prompt,
        )
        try:
            data = json.loads(_clean_json_text(response_text))
            result = ExtractionResult.model_validate(data)
            return result
        except Exception as second_error:
            raise ValueError(
                f"Model returned invalid JSON after repair retry. "
                f"First error: {first_error}. Second error: {second_error}"
            ) from second_error

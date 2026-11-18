# Trace Spec

The trace is scored and audited. It must never misreport models, tokens or areas.

## Required per call

- Call number (1, 2, 3, ... across the whole run; updates continue numbering)
- Model name exactly as sent to the provider
- One area tag: `reading`, `venue`, `schedule`, `food`, `judging`, `budget`
- Input (full prompt as sent)
- Output (full raw response)
- Token counts as the provider reports: prompt, completion, total
- End of trace: total tokens (sum of recorded counts)

## Additional lines (code-generated, zero tokens)

- `[mode] fresh | update` and why
- `[superseded] msg #a replaced by msg #b (key)`
- `[ungrounded] msg #i key value dropped`
- `[recompute] areas: budget (code, 0 tokens); unchanged: venue, food, ...`
- `[reject] msg #i CODE: reason`  (English; Urdu version in JSON and UI only)
- `[check] figures ok | budget ok | venue ok | schedule ok | judges ok | coverage ok`
- `[unhandled] constraint subject not enforced: <subject>`
- `[timing] run 12.4 s`

## Text format

```
=== CALL 1 ===
model:   <model name>
area:    reading
tokens:  prompt <n>  completion <n>  total <n>
--- input ---
<prompt>
--- output ---
<response>

[recompute] ...
[check] ...
=== TOTAL TOKENS: <n> ===
```

## JSON format (`out/trace.json`)

```
{ "calls": [ { "n", "model", "area", "input", "output", "prompt_tokens", "completion_tokens", "total_tokens", "started_at", "seconds" } ],
  "events": [ { "type", "message_id", "code", "text_en", "text_ur" } ],
  "total_tokens": 0 }
```

## Rules

- Written by `core/llm.py` and `core/report.py` only.
- Retries are separate numbered calls.
- Totals are computed by summing recorded counts, never stored separately.
- The saved file for upload (`out/trace.txt`) contains the complete trace of the whole session (first run plus every update).
- `scripts/check_trace.py` verifies numbering, area tags, totals and that every call's tokens are non-null.

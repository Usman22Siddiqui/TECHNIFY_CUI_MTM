# Architecture

## Principle

The model reads language. Code does everything else. Fewer parts, each justified.

## Data flow

```
messages.txt
   |
 parse.py ------> messages[] (id, hash, sender, date, text)
   |
 mode detect (fresh | update) using state/state.json
   |
 extract.py ---> core/llm.py ---> model        (area = reading, 1 call)
   |
 ground.py      every number/quote must appear in its source message
   |
 resolve.py     supersession by date, sender authority, relevance
   |
 planner.py     judging -> headcount -> venue, food -> schedule -> budget
   |
 validate.py    six checks on the candidate plan
   |            fail -> reject message(s), keep old plan, write reason
   v
 commit state.json, out/plan.json, out/trace.txt, out/trace.json, out/report.html
```

## Modules and what breaks without them

| Module | One-line purpose | Without it |
|---|---|---|
| `parse.py` | Split the file into messages, hash each | Cannot tell new messages from old; no update mode |
| `llm.py` | Only door to the model; numbers calls; copies provider token counts | Trace is dishonest or incomplete: disqualification risk |
| `extract.py` | Turns Roman Urdu / English text into structured facts | Code cannot read language; facts would have to be typed in |
| `ground.py` | Rejects extracted values not present in the source text | A hallucinated number silently corrupts the plan |
| `resolve.py` | Picks latest price, checks sender authority, drops noise | Old price used; a caterer could change the headcount |
| `planner.py` | Exact arithmetic and scheduling | A model would round or miscount; tokens wasted |
| `validate.py` | Six checks; gate for every commit | A wrong message breaks the plan |
| `update.py` | Applies new messages to a copy of state, recomputes only affected areas | Full re-run on every change: slower, more tokens |
| `report.py` | Terminal output plus offline HTML | UI points lost; judges cannot read the trace |
| `i18n/` | Urdu / English catalogue | No language switch |

## Dependency graph (drives updates)

Each planner area declares the facts and upstream outputs it reads. The update engine does not use a hand-maintained table that can drift.

```
areas = {
  judging:  reads facts[students, team_size, judges_confirmed, honorarium, judge_min_per_team, judge_max_teams]
  headcount (derived): reads facts[students, staff] + judging.judges_used
  venue:    reads headcount, facts[venue_options], constraints[venue.*]
  food:     reads headcount, facts[food_options], constraints[food.*]
  schedule: reads facts[duration_min, prayer_break_min], judging.rounds, constraints[schedule.*]
  budget:   reads facts[budget_total, committed_costs, wishlist], venue.cost, food.cost, judging.cost
}
```

On update: hash each area's inputs before and after applying the new facts; recompute (in topological order) only areas whose input hash changed; then validate the full plan.

## State file

```
state/state.json
{
  "pack_id": "<hash of first message set>",
  "messages": [{ "id", "hash", "sender", "role", "date", "text", "status": "accepted|rejected|ignored|superseded", "reason_code", "reason_en", "reason_ur" }],
  "facts": { "<key>": { "value", "unit", "source_ids": [..], "quote": "..." } },
  "constraints": [ { "area", "subject", "op", "value", "hard", "source_id" } ],
  "plan": { ... },
  "checks": { "figures": true, ... },
  "call_counter": 0
}
```

## Model access

A single OpenAI-compatible HTTP adapter (works with Ollama, Groq, OpenRouter, Gemini's compatible endpoint). Settings in `.env`: `MODEL_BASE_URL`, `MODEL_NAME`, `MODEL_API_KEY`. Temperature 0. JSON output mode where the provider supports it. Token counts read from `usage.prompt_tokens` and `usage.completion_tokens`. If the provider omits usage, fail loudly.

## Stack

| Concern | Choice | Reason |
|---|---|---|
| Language | Python 3.11 | Fast to build, readable in a viva |
| Validation | pydantic | Rejects malformed model JSON |
| HTTP | httpx | Simple, works with local and hosted models |
| Terminal | rich | Readable plan, trace, rejections |
| HTML | jinja2 to one static file, vanilla JS for the language switch and trace panel | No server, no build step, offline-safe |
| Tests | pytest | Feedback loop for the coding agent |
| State | JSON file | Easy to inspect during judging |

## Layout

```
run.py
core/  parse.py llm.py extract.py ground.py resolve.py planner.py validate.py update.py report.py
config/ defaults.toml authority.json subjects.json
ui/ template.html.j2 styles.css app.js i18n/en.json i18n/ur.json fonts/
scripts/ lint_no_facts.py rehearsal.py
tests/ fixtures/ golden/ test_*.py
state/ out/
```

## Performance budget

- Fresh run: one model call, target under 30 s even on a laptop model; hard cap 2 minutes.
- Update: one model call, target under 15 s; hard cap 1 minute and at most 5 calls.
- If the model returns invalid JSON: one repair retry (counted and traced). If still invalid: abort the update, keep the old plan, trace the failure.

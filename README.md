# Mind to Machine: Event Planning Agent

An agent that reads a pack of messages (English, Roman Urdu, Urdu script) and plans a 4-hour physical hackathon in Islamabad: venue, schedule, food, judging, budget. It accepts new messages later, updates only what changed, and rejects messages that would break the plan, with the reason printed in the trace.

## Run

```
python run.py messages.txt
```

One command, no flags. The same command handles the first pack and every later message. Model choice lives in `.env`, never in flags.

## Setup

```
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                  # add model endpoint, name, key
python run.py tests/fixtures/sample_pack.txt
```

## Outputs (written to `out/`)

| File | What it is |
|---|---|
| `plan.json` | Final plan: venue, schedule, food, judging, budget, six check results |
| `trace.txt` | Numbered model calls with model, area, input, output, tokens, total |
| `trace.json` | Same trace, machine readable (the UI reads this) |
| `report.html` | Offline bilingual (Urdu / English) interface: plan, trace, rejected messages |

## Read the docs in this order

1. `AGENTS.md` : rules every agent and human must follow
2. `docs/PRD.md` : what we are building and how it is scored
3. `docs/ARCHITECTURE.md` : parts, data flow, why each part exists
4. `docs/EXTRACTION_SPEC.md` : the only model call and its schema
5. `docs/PLANNER_SPEC.md` : arithmetic, schedule, six checks
6. `docs/UPDATE_ENGINE.md` : new messages, rejection, dependency recompute
7. `docs/TRACE_SPEC.md` : exact trace format
8. `docs/DESIGN_SYSTEM.md` : colours, type, layout, anti-template rules
9. `docs/PAKISTAN_FEATURES.md` : localisation features
10. `docs/TESTING.md`, `docs/TASKS.md`, `docs/JUDGE_QA.md`

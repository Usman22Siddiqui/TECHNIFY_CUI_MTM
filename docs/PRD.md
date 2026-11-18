# PRD: Mind to Machine Event Planning Agent

## Goal

Given an unseen pack of about ten messages (emails, WhatsApp, notices; English and Roman Urdu), produce a valid plan for a 4-hour hackathon covering venue, schedule, food, judging and budget. Keep it valid when new messages arrive. Spend as few tokens as possible.

## How the score maps to design decisions

| Component | Pts | Design decision that earns it |
|---|---|---|
| Output | 30 | Figures computed by code, never by the model. Six validator checks run on every plan. Grounding check rejects any extracted number not present in its source message. |
| Catching the wrong message | 20 | Validator-gated commit plus sender authority matrix. Rejection reason is a templated string citing the rule and message id. |
| Understanding | 20 | Few parts, each with a one-line purpose and a stated failure mode (`docs/JUDGE_QA.md`). |
| Handling change | 10 | Dependency recompute: only areas whose inputs changed are recomputed. One reading call per update. |
| UI | 10 | Plan, trace and rejected messages on one offline page. Urdu / English switch. |
| Predicting a change | 5 | Only `reading` ever calls a model, so the written prediction always matches the trace. |
| Token use | 5 | One reading call for the whole pack. Compact JSON in and out. No model call in planning. |
| Bonus | 10 | Use one small model for every call (confirm the organisers' list at the help desk). |

## Users

1. **The judge or volunteer** who reads the trace and plan in a few minutes.
2. **The event organiser** who wants a plan they can paste into the WhatsApp group and print for the Dean's office.

## Scope

**P0 (must ship by 1:25)**
- Parse messages from file; single command; state persisted.
- One reading call producing structured facts, constraints and per-message relevance.
- Planner for venue, schedule, food, judging, budget in plain code.
- Six-check validator; validator-gated commit.
- Update flow with at most one model call, rejection with reason.
- Trace in the exact required format, saved to file.
- Offline `report.html` with plan, trace, rejected messages; Urdu / English switch.

**P1**
- Prayer-aware schedule, dietary and generator constraints, WhatsApp share text, lakh formatting toggle, traffic buffer.

**P2**
- Print-ready A4 plan, Rs sanity guard, local pasting UI via a tiny stdlib server.

## Non-goals

No agent framework. No database. No login. No model calls for arithmetic. No live web lookups at run time.

## Success metrics

- Sample pack run: under 60 s, one model call, plan passes six checks.
- Update run: one model call, under 20 s.
- Hand-written unseen packs (`tests/fixtures/unseen_*.txt`): plan valid in at least 9 of 10.
- Every wrong-message fixture rejected with a correct reason.

## Open questions for the help desk (ask early, answers get announced to all teams)

1. Which models are on the small-model list?
2. If only `reading` calls a model during an update, does that satisfy "only the affected areas made model calls"?
3. How do the three follow-up messages arrive: a new file each, or one cumulative file?
4. Are retries counted as separate model calls?
5. Is honorarium paid per confirmed judge or per judge needed?
6. Are event start time and date ever given in the pack?

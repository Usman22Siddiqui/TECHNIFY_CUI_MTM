# Master prompt for Antigravity

Paste everything below the line into the first Antigravity session (planning mode). Put `AGENTS.md` and the `docs/` folder in the repo root first.

---

You are the lead engineer on a 4.5-hour hackathon build. Our team's project is an agent system that reads a pack of messages (English, Roman Urdu, Urdu script) from a text file and plans a 4-hour physical event for 150 students: venue, schedule, food, judging, budget. It must accept new messages later and update the plan. It is scored on correct output, catching wrong messages, our ability to explain the system, handling change, UI, and token use. Fewer tokens score higher. Code freeze is in a fixed number of hours, so work fast and keep it simple.

## Step 0: read before doing anything

Read these files completely, in this order, and treat them as the source of truth:

1. `AGENTS.md` (hard rules; a violation can disqualify us)
2. `README.md`
3. `docs/PRD.md`
4. `docs/ARCHITECTURE.md`
5. `docs/EXTRACTION_SPEC.md`
6. `docs/PLANNER_SPEC.md`
7. `docs/UPDATE_ENGINE.md`
8. `docs/TRACE_SPEC.md`
9. `docs/DESIGN_SYSTEM.md`
10. `docs/PAKISTAN_FEATURES.md`
11. `docs/TESTING.md`
12. `docs/TASKS.md`
13. `docs/JUDGE_QA.md`

If two documents disagree, `AGENTS.md` wins, then `ARCHITECTURE.md`. List any conflicts or gaps you find and ask me before guessing.

## Non-negotiables (repeat of AGENTS.md, in short)

- No facts from the sample pack in code or prompts: no prices, names, numbers, dates, senders or message text. Prompts describe shapes only.
- One command: `python run.py <messages_file>`. No flags. Fresh run versus update is decided from the file and `state/state.json`.
- The model is used only for reading language (area `reading`). Planning, arithmetic, validation, supersession, authority checks and rejection reasons are plain Python.
- Every model call goes through `core/llm.py::call_model`. Tokens come from the provider's `usage` field, never estimated. Retries are traced as separate calls.
- The plan is always valid: a candidate plan is committed only if all six checks pass; otherwise keep the old plan and print a templated bilingual reason citing the message id.
- No agent frameworks. No CDN. The HTML report is one offline static file.
- Do not invent event facts. Missing values are `unknown` and traced.

## How to work

1. **Plan first.** Produce one plan artifact covering milestones M0 to M9 from `docs/TASKS.md`, with the files you will create per milestone and the tests that prove each one. Wait for my approval before writing code.
2. **One milestone at a time.** Do not start the next until the current one has passing tests, a clean lint (`scripts/lint_no_facts.py`), and a successful run on the sample fixture.
3. **Do not run parallel agents on the same files.**
4. **After each milestone**, report in this exact format and then stop for my go-ahead:
   - What was built (files)
   - Tests run and results (paste output)
   - Sample pack run: seconds elapsed, model calls, total tokens
   - Anything that deviates from the docs, and why
   - Risks or questions
5. **Commit after each milestone** with a clear message and push. Never commit `.env`.
6. Prefer the standard library. Allowed: `pydantic`, `httpx`, `rich`, `jinja2`, `pytest`. Ask before adding anything else.
7. Use a fake model adapter for tests so they run offline and instantly. Real model calls only in `scripts/rehearsal.py` and manual runs.

## What the finished system must do

1. **Read** every message from a text file exactly as given, through one command, no hints from us.
2. **One reading call** per fresh run, returning compact JSON per message: sender role, date, kind (fact, request, notice, noise), structured facts with verbatim quotes, and generic constraints. Pakistani money formats and Roman Urdu number words must be understood (`6,50,000`, `650k`, `6.5 lakh`, `paanch hazar`, `Rs 1200/-`).
3. **Ground** every extracted number against its quote in the source message; drop and trace anything ungrounded.
4. **Resolve** in code: latest dated fact wins per key, sender authority from `config/authority.json`, noise and requests excluded from spending (requests go to a wishlist).
5. **Plan** in code, in the order and with the formulas of `docs/PLANNER_SPEC.md`: judging, headcount, venue, food, schedule, budget, degradation ladder if over budget.
6. **Validate** six checks: figures, budget, venue, schedule, judges, coverage.
7. **Update** with at most one reading call: apply new messages to a candidate copy of state, recompute only areas whose input hash changed (dependency graph derived from each area's declared inputs, not a hand-kept table), validate, then commit or reject with a templated English and Urdu reason.
8. **Trace** exactly as in `docs/TRACE_SPEC.md`: numbered calls, model name, one area tag, full input, full output, provider token counts, total at the end, plus code-generated lines for mode, supersession, ungrounded drops, recomputed areas, rejections, checks, timing. Save `out/trace.txt`, `out/trace.json`, `out/plan.json`, `out/report.html`.
9. **Show** the plan, trace and rejected messages in terminal (rich) and in `report.html`.

## UI direction

Follow `docs/DESIGN_SYSTEM.md` exactly. Theme from our portfolio: butter cream background, deep forest green text, olive secondary, one orange accent, dark forest terminal panel for the trace. It must not look generated: no grid of identical rounded cards, no gradient washes, no emoji icons, no eyebrow labels above every heading, no arrows appended to buttons, one motion moment only (trace printing in on first load). The sections have different shapes: schedule ruler with proportional heights, budget ledger with right-aligned figures, judge grid, rejected messages shown struck through with the reason beneath in English and Urdu. Fonts bundled locally; the page works fully offline. Before building the UI, write a short design plan (tokens, layout, what will make it unmistakably ours), review it against the anti-template rules, and show it to me.

## Pakistan-specific features

Build in the priority order of `docs/PAKISTAN_FEATURES.md`: P0 first (Urdu / English switch with RTL and persistence, Roman Urdu and Urdu-script reading, Pakistani number formats, bilingual rejection reasons, lakh grouping toggle, WhatsApp copy summary), then P1 (generator and load-shedding constraint, prayer-aware schedule, halal and Ramadan handling, 12-hour PKT time and Urdu digits, commute buffer, offline UI), then P2. All UI text goes through `ui/i18n/en.json` and `ui/i18n/ur.json`. The trace files stay English-canonical.

## Quality bars

- Fresh run under 60 seconds, update run under 20 seconds, with a hard maximum of 2 minutes and 1 minute.
- Unseen packs will have different numbers, wording, senders, and constraint kinds we have not seen. Never special-case the sample pack. Build the generic constraint engine; unknown constraint subjects are shown as `unhandled`, never silently dropped.
- Planner and validator are pure functions with unit tests for every edge in `docs/PLANNER_SPEC.md`.
- Two practice messages must pass: a cost change that recomputes only the budget, and a wrong message (an order quantity below the headcount) that is rejected with a clear reason while the plan stays valid.
- A fresh pack arriving after an old `state.json` must correctly start fresh (see mode rules in `docs/UPDATE_ENGINE.md`).
- Every module must be explainable in one sentence, with a stated failure mode. If you add something we cannot justify, remove it.

## Stop and ask me when

- Docs conflict or are missing a decision.
- A change would require putting a fact into code.
- You want to add a dependency or a model call outside `reading`.
- A test cannot pass without weakening a rule in `AGENTS.md`.

## Begin

Start with Step 0, then give me the plan artifact. Do not write code yet.

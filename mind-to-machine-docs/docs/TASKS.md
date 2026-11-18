# Build Plan for Antigravity

Work in order. One milestone at a time. After each: tests pass, sample pack runs, commit, push. Tell the agent at the start of every session: "Read AGENTS.md and the docs it lists before doing anything."

## How to use Antigravity here

1. Open the repo as the workspace. Put `AGENTS.md` in the root (and mirror it into the rules folder your Antigravity version reads, if it has one).
2. Use planning mode. Ask for a plan artifact for the milestone, review it against the docs, approve, then let it build.
3. Run one agent at a time. Parallel agents editing the same files cause conflicts.
4. After each milestone ask it to run `pytest -q`, `python scripts/lint_no_facts.py`, and the sample pack, and to show you the output.
5. Review the diff yourself. Every team member should read `llm.py`, `planner.py`, `validate.py`, `update.py` at least once.

## Timeline (10:00 start, freeze 1:25)

| Time | Milestone |
|---|---|
| 10:00 to 10:20 | M0 setup, model access test, repo pushed |
| 10:20 to 10:50 | M1 llm.py and trace |
| 10:50 to 11:30 | M2 parse and extract and ground |
| 11:30 to 12:10 | M3 planner and M4 validate |
| 12:10 to 12:40 | M5 update engine |
| 12:40 to 1:05 | M6 report UI and M7 Pakistan features |
| 1:05 to 1:20 | M8 hardening, rehearsal |
| 1:20 to 1:25 | M9 final push, hash submitted |

## M0 Setup

- Create repo, `.gitignore` (`.env`, `state/`, `out/`, `.venv/`), `.env.example`, folders from `ARCHITECTURE.md`.
- Test model access: key, rate limit, latency for a 2,000-token prompt. A local model must finish a full run inside 2 minutes.
- Ask the help desk the questions in `PRD.md`.
- Accept: repo pushed, organisers added if private, one hello call works.

Prompt: "Create the project skeleton exactly as in docs/ARCHITECTURE.md. No logic yet. Add .gitignore, .env.example, requirements.txt, and an empty pytest run that passes."

## M1 llm.py and trace

- `call_model(area, system, user)` returning text and usage. Numbering, timing, areas check, usage required.
- Trace collector with text and JSON writers.
- Accept: fake adapter test; real call recorded with real usage; total equals sum.

## M2 parse, extract, ground

- Parse numbered rows and blank-line blocks and plain lines; keep sender, date, text.
- Extraction prompt from `EXTRACTION_SPEC.md`; pydantic schema; repair retry.
- Grounding with Pakistani number formats.
- Accept: sample pack yields facts with quotes; hallucinated number is dropped in a test.

## M3 planner

- All formulas in `PLANNER_SPEC.md`, degradation ladder, schedule builder.
- Accept: golden test for the sample pack; edge tests.

## M4 validate

- Six checks, `validate(plan, facts, constraints)`.
- Accept: each check has a passing and a failing test.

## M5 update engine

- Mode detection, candidate state, dependency recompute, authority, rejection codes, bilingual templates.
- Accept: practice change touches budget only; practice wrong message rejected; one model call each; fresh-after-update works.

## M6 report UI

- Terminal output with `rich`; `report.html` per `DESIGN_SYSTEM.md`.
- Accept: plan, trace, rejected messages visible; works offline; mobile width fine.

## M7 Pakistan features

- F1 to F6 first, then F7 to F12 as time allows. See `PAKISTAN_FEATURES.md`.
- Accept: language switch works and persists; WhatsApp copy matches plan.

## M8 hardening

- `scripts/rehearsal.py` twice, timed. Fix slow paths. Run on a fresh clone with `git status` clean.
- Check that nothing in `src/` leaks pack facts.

## M9 freeze

- Final push before 1:20. Submit repo link and commit hash. Verify `git log -1` equals submitted hash. Then stop touching the code.

## If time runs short (cut order)

Drop P2 features, then F11, F9, F8, F7. Never drop: validator-gated commit, grounding, trace honesty, bilingual rejection reasons, one reading call.

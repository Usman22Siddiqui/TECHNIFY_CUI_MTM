# AGENTS.md

Rules for every coding agent (Antigravity or otherwise) and every team member. Read this file first, then the docs listed in `README.md`. If a task conflicts with a rule here, stop and ask; do not work around it.

## Project in one paragraph

A Python tool that reads a message pack from a text file, calls a small model once to turn messy language into structured facts, then uses plain code to plan venue, schedule, food, judging and budget, validate six checks, and print a faithful trace. New messages update the plan with at most one model call.

## Hard rules (a violation can disqualify the team)

1. **No pack facts in code or prompts.** No prices, names, venue names, numbers, dates, senders or message text from the sample pack anywhere in `src/` or in prompt strings. Prompts describe the *shape* of the task, never its content. Test fixtures live only under `tests/` and are never imported by `src/`.
2. **One command, no flags.** `python run.py <messages_file>`. Fresh run versus update is decided from the file and `state/state.json`, never from a flag or an environment hint.
3. **The model is only for reading language.** Arithmetic, selection, scheduling, validation, supersession, authority checks and rejection reasons are plain code.
4. **One door to the model.** Every model call goes through `core/llm.py::call_model(area, system, user)`. It numbers the call, records model name, area tag, full input, full output, and token counts copied from the provider's `usage` field. Never estimate tokens. If the provider returns no usage, raise an error.
5. **Allowed area tags:** `reading`, `venue`, `schedule`, `food`, `judging`, `budget`. Exactly one tag per call.
6. **The plan is always valid.** A candidate plan replaces the current plan only if all six checks pass. Otherwise keep the old plan, mark the message rejected, and print the reason.
7. **Rejection reasons are templated code strings** (English plus Urdu), each citing the message id and the rule that failed. Not model-written.
8. **No agent frameworks.** No LangChain, CrewAI, AutoGen. Every module must be explainable in one sentence along with what breaks without it.
9. **Offline UI.** `report.html` is a single static file: no CDN, no external fonts, no network requests. Fonts are bundled.
10. **All UI text goes through the i18n catalogue** (`ui/i18n/en.json`, `ui/i18n/ur.json`). No hardcoded visible strings.
11. **Secrets:** `.env` is git-ignored. Commit `.env.example` only.
12. **Honest trace.** Retries count as model calls and appear in the trace. Never hide, merge or reorder calls.

## Working method for agents

- Plan first. Produce a short plan artifact, wait for approval, then build one milestone at a time from `docs/TASKS.md`.
- Do not run parallel agents that edit the same files.
- After each milestone: run `pytest -q`, run the sample pack, commit with a clear message, push.
- Prefer the standard library. Allowed dependencies: `pydantic`, `httpx`, `rich`, `jinja2`, `pytest`, and one prayer-time library if used (see `docs/PAKISTAN_FEATURES.md`). Ask before adding anything else.
- Keep functions small and pure where possible. Planner and validator take dicts in and return dicts out, with no I/O.
- Do not invent facts about the event. If a value is missing from the messages, the plan marks it `unknown` and the trace says so. Defaults that are design parameters (for example minimum transition minutes) live in `config/defaults.toml` with a comment explaining why.

## Definition of done for any task

- Unit tests added and passing.
- `python run.py tests/fixtures/sample_pack.txt` completes in well under 60 seconds.
- `scripts/lint_no_facts.py` passes.
- Trace totals equal the sum of per-call tokens.
- Docs updated if behaviour changed.

## Freeze

Code freeze is at 1:25. After the final push: `git status` must be clean and `git log -1` must match the submitted hash. No edits after that.

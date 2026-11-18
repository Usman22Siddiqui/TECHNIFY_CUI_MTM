# Testing

## Layout

```
tests/
  fixtures/  sample_pack.txt  practice_change.txt  practice_wrong.txt  unseen_01..10.txt  wrong_*.txt
  golden/    sample_pack.json (expected plan figures; tests only)
  test_parse.py test_ground.py test_resolve.py test_planner.py test_validate.py
  test_update.py test_trace.py test_modes.py test_i18n.py
scripts/
  lint_no_facts.py  check_trace.py  rehearsal.py  check_git_clean.sh
```

## What to test

1. **Planner units**: ceil edges, capacity boundary, price ties, no venue fits, generator required, infeasible budget, judge shortage, short duration.
2. **Grounding**: number formats from `PAKISTAN_FEATURES.md` F3, quote not present, number present but in different message.
3. **Supersession**: older price, same-day tie, different ref not superseded.
4. **Authority**: every role against every key group (data driven from `authority.json`).
5. **Validator**: each of six checks fails when it should; candidate failing never commits.
6. **Updates**: practice change recomputes budget only; practice wrong message rejected with `BREAKS_CHECK`; one model call each; at most 5 always.
7. **Modes**: no state, same file again, cumulative file, one-message file, unrelated new pack of 10 after an old state (must be fresh).
8. **Trace**: numbering, area tags in allowed set, totals equal sum, tokens non-null, retry numbered.
9. **i18n**: every key exists in both files; RTL attribute flips; no hardcoded visible string.
10. **Timing**: fresh run under 60 s, update under 20 s on the actual laptop and model.

## Fake model for tests

Provide `core/llm.py` with a test adapter that returns canned JSON and fake usage numbers, so planner and update tests run offline and instantly. Real model runs happen only in `scripts/rehearsal.py`.

## No-facts lint

`scripts/lint_no_facts.py` scans `src/`, `core/`, `config/` and prompt files for:
- any numeric literal outside an allowlist of design parameters (`config/defaults.toml` is the only place for those),
- any string copied from fixtures (fixtures are tokenised and compared),
- any import from `tests/`.
It must pass before every commit.

## Write your own unseen packs

Create at least ten new packs with: different senders and wording, Roman Urdu and Urdu script, different numbers, a new constraint kind in at least five (generator, halal, accessibility, fixed start time, price cap, minimum staff, reserved window), one cumulative follow-up, and one wrong message per pack. Keep the facts in the fixtures only.

## Adversarial follow-up ideas

- A vendor tries to reduce a quantity.
- A message lowers capacity below headcount.
- A late message restates an old price.
- A request from the student side presented as approved.
- A message that is right but sent by the wrong role.
- A new hard constraint that removes the current cheapest venue.
- A change that makes the budget infeasible (expect `BREAKS_CHECK` or the degradation ladder).

## Dress rehearsal (`scripts/rehearsal.py`)

Simulates the judging session: a fresh unseen pack, then three single-message runs, then saves the plan and trace. Prints elapsed time per run and checks `git status`. Run it twice with a stopwatch before 1:20.

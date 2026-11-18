# Planner and Validator Spec (plain code, no model)

All functions are pure: dicts in, dicts out. No I/O, no model calls. Design parameters that are not facts from messages live in `config/defaults.toml` with a comment each.

## Order of computation

1. **Judging**
   - `teams = ceil(students / team_size)`
   - `judges_needed = ceil(teams * judge_min_per_team / (judge_min_per_team * judge_max_teams))` which reduces to `ceil(teams / judge_max_teams)`
   - `judges_used = judges_needed`. If `judges_needed > judges_confirmed`, flag a shortfall (check fails).
   - Assign teams round-robin to judges so each judge has at most `judge_max_teams`.
   - `rounds = max teams on any judge`. `judging_minutes = rounds * judge_min_per_team + transitions`.
   - `judge_cost = judges_used * honorarium`.
   - Also compute `judge_cost_worst_case = judges_confirmed * honorarium` and show it as information. The budget check uses the base figure but the UI shows both.
   - Unused confirmed judges are listed as reserves (covers a late or absent judge).
2. **Headcount** = `students + staff + judges_used`. This is the number to seat and feed.
3. **Venue**
   - Candidates: every venue option with `capacity >= headcount`.
   - Apply hard constraints (generator required, max price, accessibility, etc.).
   - Pick the cheapest. Tie-break: smaller capacity, then name order.
   - If none qualifies: venue check fails; report the closest option and the gap.
4. **Food**
   - Use the latest price per head for the chosen tier (supersession already applied).
   - `food_cost = headcount * price_per_head + delivery_fee`.
   - Apply dietary constraints (halal required, vegetarian share) as filters or counts.
   - Quantity always equals headcount. No message can change it directly.
5. **Schedule** (see below)
6. **Budget**
   - `spent = venue_cost + food_cost + judge_cost + sum(committed_costs)`
   - `remaining = budget_total - spent`
   - Wishlist items (requests) are listed with a flag `fits` or `does_not_fit` against `remaining`. They are never added to `spent` without authority approval.

## Degradation ladder (only if over budget)

Try in order, stop at the first that makes the plan valid, and trace each step:
1. Cheaper food tier.
2. Cheaper venue that still fits and satisfies hard constraints.
3. Fewer judges is **not** allowed (judging check). Stop.
If still invalid: plan is marked `infeasible`, with the smallest gap and the reason. Never output an invalid plan as valid.

## Schedule construction

Inputs: `duration_min`, `prayer_break_min`, judging block length, minimum block lengths from `config/defaults.toml`, optional `start_time`, optional window constraints.

Blocks in order: arrival buffer, opening, build (part 1), lunch, prayer break, build (part 2), judging, closing.

Rules:
- Minute total of all blocks equals `duration_min` exactly.
- Blocks are contiguous; none overlaps; none has zero or negative length.
- Prayer block length is at least `prayer_break_min`.
- Judging block length is at least `rounds * judge_min_per_team + transitions`.
- Remaining minutes after fixed blocks go to build time, split between part 1 and part 2.
- If `start_time` is known, print clock times (12-hour, PKT). Otherwise print offsets (`+0:45`). Never invent a start time.
- If prayer-time alignment is on (see `PAKISTAN_FEATURES.md`) and the clock window is known, move the prayer block to the nearest valid prayer window without breaking any rule above.

## The six checks (`validate.py`)

Each returns `{ok: bool, detail: str, code: str}`.

| Check | Passes when |
|---|---|
| `figures` | Recomputing teams, judges, headcount, venue cost, food cost, judge cost and totals from facts gives the same numbers as the plan; every fact used is grounded |
| `budget` | `spent <= budget_total` |
| `venue` | Chosen venue capacity `>= headcount` and all hard venue constraints hold |
| `schedule` | Blocks sum to duration, contiguous, prayer and judging lengths satisfied, window constraints respected |
| `judges` | `judges_used <= judges_confirmed`, each judge has at most `judge_max_teams`, every team has exactly one judge slot of `judge_min_per_team` minutes |
| `coverage` | All five areas present and non-empty, plus every hard constraint is either satisfied or listed as unhandled |

`validate()` is also run on the **candidate** plan during updates. Candidate fails: it is discarded.

## Worked example for tests only

Do not copy these numbers into `src/`. They belong in `tests/golden/sample_pack.json` as expected output for the sample fixture.

- teams 50, judges needed 17, headcount 177
- cheapest venue with capacity at least 177 is the 200-seat hall at the lowest price
- food: 177 boxes at the latest price
- judge cost: 17 honoraria; worst case with all 20 confirmed shown beside it
- committed costs summed from the finance message
- the DJ is a request: shown in the wishlist, flagged `fits`, not spent

## Unit tests the planner must have

`ceil` edge cases (students not divisible by team size), headcount boundary (capacity exactly equal), tie on price, no venue fits, generator required, infeasible budget, one judge short, prayer minutes larger than expected, duration too short for judging.

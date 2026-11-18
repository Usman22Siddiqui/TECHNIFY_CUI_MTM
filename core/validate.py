"""Six checks; gate for every commit.

Without it: a wrong message breaks the plan.

Pure functions: dicts in, dicts out. No I/O, no model calls.
"""

from __future__ import annotations

import math
from typing import Any

from core.planner import load_defaults, find_unhandled_constraints


CHECK_NAMES: tuple[str, ...] = (
    "figures",
    "budget",
    "venue",
    "schedule",
    "judges",
    "coverage",
)


def _check_figures(
    plan: dict[str, Any],
    facts: dict[str, Any],
    constraints: list[dict[str, Any]],
    defaults: dict[str, Any],
) -> dict[str, Any]:
    """Recompute teams, judges, headcount, costs and totals from facts and verify match."""
    judging = plan.get("judging", {})
    headcount = plan.get("headcount", {})
    venue = plan.get("venue", {})
    food = plan.get("food", {})
    budget = plan.get("budget", {})

    # Verify required numeric facts exist
    students = facts.get("students")
    team_size = facts.get("team_size")
    max_teams = facts.get("judge_max_teams")
    honorarium = facts.get("honorarium", 0)
    staff = facts.get("staff", 0)

    if any(x is None for x in (students, team_size, max_teams)):
        return {"ok": False, "code": "FIGURES_MISSING", "detail": "Required numeric facts missing"}

    # Apply judging max_teams tightening constraint if any
    eff_max_teams = int(max_teams)
    for c in constraints:
        if c.get("subject") == "judging.max_teams_per_judge" and isinstance(c.get("value"), (int, float)):
            eff_max_teams = min(eff_max_teams, int(c["value"]))

    expected_teams = math.ceil(int(students) / int(team_size))
    expected_judges = math.ceil(expected_teams / eff_max_teams)
    expected_hc = int(students) + int(staff or 0) + expected_judges
    expected_judge_cost = expected_judges * int(honorarium or 0)

    if judging.get("teams") != expected_teams:
        return {"ok": False, "code": "FIGURES_MISMATCH", "detail": f"teams {judging.get('teams')} != {expected_teams}"}
    if judging.get("judges_used") != expected_judges:
        return {"ok": False, "code": "FIGURES_MISMATCH", "detail": f"judges_used {judging.get('judges_used')} != {expected_judges}"}
    if headcount.get("total") != expected_hc:
        return {"ok": False, "code": "FIGURES_MISMATCH", "detail": f"headcount {headcount.get('total')} != {expected_hc}"}
    if judging.get("cost") != expected_judge_cost:
        return {"ok": False, "code": "FIGURES_MISMATCH", "detail": f"judge_cost {judging.get('cost')} != {expected_judge_cost}"}

    # Verify food quantity equals headcount and no conflicting food_quantity override
    req_qty = food.get("requested_quantity")
    if req_qty is not None and int(req_qty) != expected_hc:
        return {
            "ok": False,
            "code": "FOOD_QUANTITY_MISMATCH",
            "detail": f"requested food quantity {req_qty} does not match headcount {expected_hc}",
        }
    if food.get("quantity") != expected_hc:
        return {
            "ok": False,
            "code": "FOOD_QUANTITY_MISMATCH",
            "detail": f"food quantity {food.get('quantity')} != headcount {expected_hc}",
        }

    # Verify food cost against facts
    tier = food.get("tier")
    food_opts = facts.get("food_options", {}) or {}
    if tier and tier in food_opts:
        opt = food_opts[tier]
        exp_food_cost = expected_hc * int(opt.get("price_per_head", 0)) + int(opt.get("delivery_fee", 0))
        if food.get("cost") != exp_food_cost:
            return {"ok": False, "code": "FIGURES_MISMATCH", "detail": f"food_cost {food.get('cost')} != {exp_food_cost}"}

    # Verify venue cost against facts
    v_name = venue.get("selected")
    venue_opts = facts.get("venue_options", {}) or {}
    if v_name and v_name in venue_opts:
        exp_venue_cost = int(venue_opts[v_name].get("price", 0))
        if venue.get("cost") != exp_venue_cost:
            return {"ok": False, "code": "FIGURES_MISMATCH", "detail": f"venue_cost {venue.get('cost')} != {exp_venue_cost}"}

    # Verify budget spent sum
    committed_total = sum(int(v) for v in (facts.get("committed_costs", {}) or {}).values())
    expected_spent = int(venue.get("cost", 0)) + int(food.get("cost", 0)) + expected_judge_cost + committed_total
    if budget.get("spent") != expected_spent:
        return {"ok": False, "code": "FIGURES_MISMATCH", "detail": f"spent {budget.get('spent')} != {expected_spent}"}

    return {"ok": True, "code": "OK", "detail": f"teams={expected_teams}, hc={expected_hc}, spent={expected_spent}"}


def _check_budget(plan: dict[str, Any], facts: dict[str, Any], constraints: list[dict[str, Any]]) -> dict[str, Any]:
    """Passes when spent <= budget_total (and any hard budget cap/reserve)."""
    budget = plan.get("budget", {})
    budget_total = budget.get("budget_total")
    spent = budget.get("spent")
    remaining = budget.get("remaining")

    if budget_total == "unknown" or remaining == "unknown" or budget_total is None:
        return {"ok": False, "code": "BUDGET_UNKNOWN", "detail": "budget_total is unknown"}

    effective_cap = int(budget.get("effective_cap", budget_total))
    reserve = int(budget.get("reserve", 0))
    spendable = effective_cap - reserve

    if int(spent) > spendable:
        over = int(spent) - spendable
        return {
            "ok": False,
            "code": "OVER_BUDGET",
            "detail": f"spent Rs {spent} exceeds limit Rs {spendable} by Rs {over}",
        }

    return {"ok": True, "code": "OK", "detail": f"spent Rs {spent} <= Rs {spendable} (remaining Rs {remaining})"}


def _check_venue(plan: dict[str, Any], facts: dict[str, Any], constraints: list[dict[str, Any]]) -> dict[str, Any]:
    """Passes when chosen venue capacity >= headcount and all hard venue constraints hold."""
    venue = plan.get("venue", {})
    hc = int(plan.get("headcount", {}).get("total", 0))
    selected = venue.get("selected")

    if not selected or venue.get("status") != "ok":
        gap = venue.get("gap", 0)
        return {"ok": False, "code": "NO_VENUE", "detail": f"no qualifying venue (capacity gap {gap})"}

    cap = int(venue.get("capacity", 0))
    if cap < hc:
        return {"ok": False, "code": "VENUE_TOO_SMALL", "detail": f"{selected} capacity {cap} < headcount {hc}"}

    # Verify hard venue constraints against chosen option
    opt = (facts.get("venue_options", {}) or {}).get(selected, venue)
    for c in constraints:
        if c.get("area") != "venue" or not c.get("hard", True):
            continue
        subj = c.get("subject", "")
        op = c.get("op", "")
        val = c.get("value")
        if subj == "venue.generator" and (op == "require" or val is True) and not opt.get("generator", False):
            return {"ok": False, "code": "VENUE_CONSTRAINT", "detail": f"{selected} lacks required generator"}
        if subj == "venue.accessible" and (op == "require" or val is True) and not opt.get("accessible", False):
            return {"ok": False, "code": "VENUE_CONSTRAINT", "detail": f"{selected} lacks required accessibility"}
        if subj == "venue.capacity_min" and isinstance(val, (int, float)) and cap < int(val):
            return {"ok": False, "code": "VENUE_CONSTRAINT", "detail": f"{selected} capacity {cap} < min {int(val)}"}
        if subj == "venue.max_price" and isinstance(val, (int, float)) and int(venue.get("cost", 0)) > int(val):
            return {"ok": False, "code": "VENUE_CONSTRAINT", "detail": f"{selected} price {venue.get('cost')} > max {int(val)}"}

    return {"ok": True, "code": "OK", "detail": f"{selected} (capacity {cap} >= {hc})"}


def _check_schedule(
    plan: dict[str, Any],
    facts: dict[str, Any],
    constraints: list[dict[str, Any]],
    defaults: dict[str, Any],
) -> dict[str, Any]:
    """Blocks sum to duration, contiguous, positive, prayer and judging lengths satisfied, windows ok."""
    sched = plan.get("schedule", {})
    judging = plan.get("judging", {})
    blocks = sched.get("blocks", []) or []
    dur = facts.get("duration_min")

    if not blocks or dur is None or not sched.get("feasible", False):
        reason = sched.get("reason") or "; ".join(sched.get("window_violations", [])) or "schedule infeasible"
        return {"ok": False, "code": "SCHEDULE_INFEASIBLE", "detail": reason}

    # Check contiguity, positive length, exact sum
    total = 0
    cursor = 0
    prayer_len = 0
    judging_len = 0
    for b in blocks:
        mins = int(b.get("minutes", 0))
        if mins <= 0:
            return {"ok": False, "code": "SCHEDULE_ZERO_BLOCK", "detail": f"block '{b.get('name')}' has length {mins}"}
        if int(b.get("start_min", -1)) != cursor or int(b.get("end_min", -1)) != cursor + mins:
            return {"ok": False, "code": "SCHEDULE_GAP", "detail": f"block '{b.get('name')}' not contiguous"}
        cursor += mins
        total += mins
        if b.get("name") == "prayer_break":
            prayer_len = mins
        if b.get("name") == "judging":
            judging_len = mins

    if total != int(dur):
        return {"ok": False, "code": "SCHEDULE_SUM", "detail": f"blocks sum to {total} != duration {dur}"}

    # Prayer minimum
    req_prayer = int(facts.get("prayer_break_min") or 0)
    for c in constraints:
        if c.get("subject") == "schedule.break_min" and isinstance(c.get("value"), (int, float)):
            req_prayer = max(req_prayer, int(c["value"]))
    if prayer_len < req_prayer:
        return {"ok": False, "code": "SCHEDULE_PRAYER", "detail": f"prayer {prayer_len} < required {req_prayer}"}

    # Judging minimum
    rounds = int(judging.get("rounds", 0))
    min_per_team = int(judging.get("judge_min_per_team", 0))
    trans_min = int(defaults.get("schedule", {}).get("transition_min", 5))
    min_judging = rounds * min_per_team + max(0, rounds - 1) * trans_min
    if judging_len < min_judging:
        return {"ok": False, "code": "SCHEDULE_JUDGING", "detail": f"judging {judging_len} < required {min_judging}"}

    if sched.get("window_violations"):
        return {"ok": False, "code": "SCHEDULE_WINDOW", "detail": "; ".join(sched["window_violations"])}

    return {"ok": True, "code": "OK", "detail": f"{len(blocks)} contiguous blocks summing to {total} min"}


def _check_judges(plan: dict[str, Any], facts: dict[str, Any], constraints: list[dict[str, Any]]) -> dict[str, Any]:
    """judges_used <= judges_confirmed, max teams per judge respected, every team has exactly 1 slot."""
    judging = plan.get("judging", {})
    if judging.get("status") == "unknown":
        return {"ok": False, "code": "JUDGES_UNKNOWN", "detail": "judging facts missing"}

    used = int(judging.get("judges_used", 0))
    confirmed = int(judging.get("judges_confirmed", 0))
    teams = int(judging.get("teams", 0))
    max_teams = int(judging.get("judge_max_teams", 0))
    min_per_team = int(judging.get("judge_min_per_team", 0))
    assignments: dict[str, list[int]] = judging.get("assignments", {}) or {}

    if used <= 0 or min_per_team <= 0:
        return {"ok": False, "code": "JUDGES_INVALID", "detail": "invalid judge count or slot length"}
    if used > confirmed:
        return {
            "ok": False,
            "code": "JUDGES_SHORTFALL",
            "detail": f"need {used} judges but only {confirmed} confirmed (short by {used - confirmed})",
        }

    # Every judge <= max_teams; every team 1..teams covered exactly once
    seen: list[int] = []
    for j_id, t_list in assignments.items():
        if len(t_list) > max_teams:
            return {"ok": False, "code": "JUDGE_OVERLOAD", "detail": f"{j_id} assigned {len(t_list)} > max {max_teams}"}
        seen.extend(t_list)

    if len(seen) != teams or set(seen) != set(range(1, teams + 1)):
        return {"ok": False, "code": "TEAM_COVERAGE", "detail": f"assigned teams do not cover 1..{teams} exactly once"}

    return {"ok": True, "code": "OK", "detail": f"{used}/{confirmed} judges covering {teams} teams"}


def _check_coverage(
    plan: dict[str, Any],
    facts: dict[str, Any],
    constraints: list[dict[str, Any]],
) -> dict[str, Any]:
    """All five areas present and non-empty, plus every hard constraint satisfied or listed unhandled."""
    required_areas = ("venue", "schedule", "food", "judging", "budget")
    missing_areas: list[str] = []

    for area in required_areas:
        section = plan.get(area)
        if not section or section.get("status") in ("unknown", "none_fits"):
            missing_areas.append(area)

    if missing_areas:
        return {
            "ok": False,
            "code": "MISSING_AREAS",
            "detail": f"incomplete or missing areas: {', '.join(missing_areas)}",
        }

    # Check staff.min shortfall
    if plan.get("headcount", {}).get("staff_shortfall", 0) > 0:
        return {
            "ok": False,
            "code": "STAFF_SHORTFALL",
            "detail": f"staff short by {plan['headcount']['staff_shortfall']} against staff.min",
        }

    # Check hard food constraints satisfied
    food = plan.get("food", {})
    for c in constraints:
        if not c.get("hard", True):
            continue
        subj = c.get("subject", "")
        val = c.get("value")
        if subj == "food.halal" and (c.get("op") == "require" or val is True) and not food.get("halal", True):
            return {"ok": False, "code": "FOOD_CONSTRAINT", "detail": "chosen food option is not halal"}
        if subj == "food.max_price_per_head" and isinstance(val, (int, float)):
            if int(food.get("price_per_head", 0)) > int(val):
                return {"ok": False, "code": "FOOD_CONSTRAINT", "detail": f"food price/head {food.get('price_per_head')} > max {int(val)}"}

    # Ensure every unhandled hard constraint is explicitly recorded on plan["unhandled_constraints"]
    expected_unhandled = find_unhandled_constraints(constraints)
    recorded_subjects = {c.get("subject") for c in plan.get("unhandled_constraints", [])}
    for u in expected_unhandled:
        if u.get("subject") not in recorded_subjects:
            return {
                "ok": False,
                "code": "SILENT_CONSTRAINT_DROP",
                "detail": f"unhandled constraint '{u.get('subject')}' was dropped silently",
            }

    unhandled_note = f" ({len(expected_unhandled)} unhandled listed)" if expected_unhandled else ""
    return {"ok": True, "code": "OK", "detail": f"all 5 areas covered{unhandled_note}"}


def validate(
    plan: dict[str, Any],
    facts: dict[str, Any],
    constraints: list[dict[str, Any]] | None = None,
    defaults: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Run all six validator checks on a plan.

    Pure function: dicts in, dict of 6 check results out.
    """
    c_list = constraints or []
    cfg = defaults if defaults is not None else load_defaults()

    return {
        "figures": _check_figures(plan, facts, c_list, cfg),
        "budget": _check_budget(plan, facts, c_list),
        "venue": _check_venue(plan, facts, c_list),
        "schedule": _check_schedule(plan, facts, c_list, cfg),
        "judges": _check_judges(plan, facts, c_list),
        "coverage": _check_coverage(plan, facts, c_list),
    }


def all_checks_pass(checks: dict[str, dict[str, Any]]) -> bool:
    """Return True iff all six checks passed."""
    return all(checks.get(name, {}).get("ok", False) for name in CHECK_NAMES)


def first_failure(checks: dict[str, dict[str, Any]]) -> tuple[str, dict[str, Any]] | None:
    """Return (check_name, result) for the first failing check, or None."""
    for name in CHECK_NAMES:
        res = checks.get(name, {})
        if not res.get("ok", False):
            return name, res
    return None

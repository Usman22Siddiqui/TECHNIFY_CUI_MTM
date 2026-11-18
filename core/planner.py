"""Exact arithmetic and scheduling. Pure functions: dicts in, dicts out.

Without it: a model would round or miscount; tokens wasted.
"""

from __future__ import annotations

import datetime
import json
import math
import pathlib
import re
import tomllib
from typing import Any


CONFIG_DIR = pathlib.Path(__file__).resolve().parent.parent / "config"

# Dependency order & declared inputs per area (drives update.py directly — never hand-duplicated)
AREA_ORDER: tuple[str, ...] = (
    "judging",
    "headcount",
    "venue",
    "food",
    "schedule",
    "budget",
)

AREA_INPUTS: dict[str, dict[str, tuple[str, ...]]] = {
    "judging": {
        "facts": (
            "students",
            "team_size",
            "judges_confirmed",
            "honorarium",
            "judge_min_per_team",
            "judge_max_teams",
        ),
        "upstream": (),
        "constraints": ("judging",),
    },
    "headcount": {
        "facts": ("students", "staff"),
        "upstream": ("judging.judges_used",),
        "constraints": ("staff",),
    },
    "venue": {
        "facts": ("venue_options",),
        "upstream": ("headcount.total",),
        "constraints": ("venue",),
    },
    "food": {
        "facts": ("food_options", "food_quantity"),
        "upstream": ("headcount.total",),
        "constraints": ("food",),
    },
    "schedule": {
        "facts": ("duration_min", "prayer_break_min", "start_time", "event_date", "late_note"),
        "upstream": ("judging.rounds", "judging.judging_minutes"),
        "constraints": ("schedule",),
    },
    "budget": {
        "facts": ("budget_total", "committed_costs", "wishlist"),
        "upstream": ("venue.cost", "food.cost", "judging.cost"),
        "constraints": ("budget",),
    },
}


def load_defaults(path: pathlib.Path | None = None) -> dict[str, Any]:
    """Load design parameters from config/defaults.toml."""
    target = path or (CONFIG_DIR / "defaults.toml")
    with open(target, "rb") as f:
        return tomllib.load(f)


def load_known_subjects(path: pathlib.Path | None = None) -> set[str]:
    """Load known constraint subjects from config/subjects.json."""
    target = path or (CONFIG_DIR / "subjects.json")
    with open(target, "r", encoding="utf-8") as f:
        data = json.load(f)
    return set(data.get("known", []))


def load_prayer_defaults(path: pathlib.Path | None = None) -> dict[str, Any]:
    """Load offline Islamabad prayer windows from config/prayer_defaults.json."""
    target = path or (CONFIG_DIR / "prayer_defaults.json")
    if not target.exists():
        return {}
    with open(target, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_constraints(
    constraints: list[dict[str, Any]],
    area: str | None = None,
    subject: str | None = None,
    hard_only: bool = False,
) -> list[dict[str, Any]]:
    out = []
    for c in constraints or []:
        if area is not None and c.get("area") != area:
            continue
        if subject is not None and c.get("subject") != subject:
            continue
        if hard_only and not c.get("hard", True):
            continue
        out.append(c)
    return out


# ---------------------------------------------------------------------------
# 1. Judging
# ---------------------------------------------------------------------------

def plan_judging(
    facts: dict[str, Any],
    constraints: list[dict[str, Any]],
    defaults: dict[str, Any],
) -> dict[str, Any]:
    """Compute teams, judges needed, round-robin assignment, judging minutes, cost."""
    students = facts.get("students")
    team_size = facts.get("team_size")
    judges_confirmed = facts.get("judges_confirmed")
    honorarium = facts.get("honorarium")
    min_per_team = facts.get("judge_min_per_team")
    max_teams = facts.get("judge_max_teams")

    # Apply explicit judging constraints if they override/tighten
    for c in _get_constraints(constraints, area="judging"):
        subj = c.get("subject", "")
        val = c.get("value")
        if subj == "judging.min_per_team" and isinstance(val, (int, float)):
            min_per_team = max(int(val), int(min_per_team or 0))
        elif subj == "judging.max_teams_per_judge" and isinstance(val, (int, float)):
            max_teams = int(val) if max_teams is None else min(int(max_teams), int(val))

    missing = []
    for name, val in (
        ("students", students),
        ("team_size", team_size),
        ("judges_confirmed", judges_confirmed),
        ("judge_min_per_team", min_per_team),
        ("judge_max_teams", max_teams),
    ):
        if val is None or (isinstance(val, (int, float)) and val <= 0):
            missing.append(name)

    if missing:
        return {
            "status": "unknown",
            "missing": missing,
            "teams": "unknown",
            "judges_needed": "unknown",
            "judges_used": 0,
            "judges_confirmed": judges_confirmed if judges_confirmed is not None else "unknown",
            "reserves": 0,
            "shortfall": 0,
            "rounds": 0,
            "transitions": 0,
            "judging_minutes": 0,
            "assignments": {},
            "honorarium": honorarium if honorarium is not None else "unknown",
            "cost": 0,
            "worst_case_cost": 0,
        }

    students_i = int(students)
    team_size_i = int(team_size)
    judges_confirmed_i = int(judges_confirmed)
    min_per_team_i = int(min_per_team)
    max_teams_i = int(max_teams)
    honorarium_i = int(honorarium) if honorarium is not None else 0

    teams = math.ceil(students_i / team_size_i)
    judges_needed = math.ceil(teams / max_teams_i)
    judges_used = judges_needed
    shortfall = max(0, judges_needed - judges_confirmed_i)
    reserves = max(0, judges_confirmed_i - judges_used)

    # Round-robin assignment: team 1..teams across judge 1..judges_used
    assignments: dict[str, list[int]] = {f"J{j}": [] for j in range(1, judges_used + 1)}
    for t_idx in range(teams):
        j_num = (t_idx % judges_used) + 1
        assignments[f"J{j_num}"].append(t_idx + 1)

    rounds = max((len(ts) for ts in assignments.values()), default=0)
    transition_min = int(defaults.get("schedule", {}).get("transition_min", 5))
    transitions = max(0, rounds - 1) * transition_min
    judging_minutes = rounds * min_per_team_i + transitions

    cost = judges_used * honorarium_i
    worst_case_cost = judges_confirmed_i * honorarium_i

    return {
        "status": "shortfall" if shortfall > 0 else "ok",
        "missing": [],
        "teams": teams,
        "team_size": team_size_i,
        "judges_needed": judges_needed,
        "judges_used": judges_used,
        "judges_confirmed": judges_confirmed_i,
        "reserves": reserves,
        "shortfall": shortfall,
        "judge_min_per_team": min_per_team_i,
        "judge_max_teams": max_teams_i,
        "rounds": rounds,
        "transitions": transitions,
        "judging_minutes": judging_minutes,
        "assignments": assignments,
        "honorarium": honorarium_i,
        "cost": cost,
        "worst_case_cost": worst_case_cost,
    }


# ---------------------------------------------------------------------------
# 2. Headcount
# ---------------------------------------------------------------------------

def plan_headcount(
    facts: dict[str, Any],
    judging: dict[str, Any],
    constraints: list[dict[str, Any]],
) -> dict[str, Any]:
    """Headcount = students + staff + judges_used."""
    students = facts.get("students")
    staff = facts.get("staff")
    judges_used = judging.get("judges_used", 0)

    # Enforce staff.min constraint if present
    staff_min = 0
    for c in _get_constraints(constraints, subject="staff.min"):
        if isinstance(c.get("value"), (int, float)):
            staff_min = max(staff_min, int(c["value"]))

    if students is None or judging.get("status") == "unknown":
        return {
            "status": "unknown",
            "students": students if students is not None else "unknown",
            "staff": staff if staff is not None else "unknown",
            "judges_used": judges_used,
            "total": 0,
            "staff_shortfall": 0,
        }

    students_i = int(students)
    staff_i = int(staff) if staff is not None else 0
    staff_shortfall = max(0, staff_min - staff_i)
    total = students_i + staff_i + int(judges_used)

    return {
        "status": "ok" if staff_shortfall == 0 else "shortfall",
        "students": students_i,
        "staff": staff_i,
        "staff_min": staff_min,
        "staff_shortfall": staff_shortfall,
        "judges_used": int(judges_used),
        "total": total,
    }


# ---------------------------------------------------------------------------
# 3. Venue
# ---------------------------------------------------------------------------

def _venue_qualifies(
    opt: dict[str, Any],
    headcount: int,
    constraints: list[dict[str, Any]],
) -> tuple[bool, list[str]]:
    """Check whether a venue option meets headcount and hard venue constraints."""
    reasons: list[str] = []
    cap = opt.get("capacity")
    price = opt.get("price")

    if cap is None or int(cap) < headcount:
        gap = headcount - int(cap or 0)
        reasons.append(f"capacity {cap} < headcount {headcount} (short by {gap})")
    if price is None:
        reasons.append("price unknown")

    for c in _get_constraints(constraints, area="venue", hard_only=True):
        subj = c.get("subject", "")
        op = c.get("op", "")
        val = c.get("value")
        if subj == "venue.generator" and (op == "require" or val is True):
            if not opt.get("generator", False):
                reasons.append("generator required")
        elif subj == "venue.accessible" and (op == "require" or val is True):
            if not opt.get("accessible", False):
                reasons.append("accessibility required")
        elif subj == "venue.capacity_min" and isinstance(val, (int, float)):
            if int(cap or 0) < int(val):
                reasons.append(f"capacity {cap} < min {int(val)}")
        elif subj == "venue.max_price" and isinstance(val, (int, float)):
            if price is not None and int(price) > int(val):
                reasons.append(f"price {price} > max {int(val)}")

    return len(reasons) == 0, reasons


def plan_venue(
    facts: dict[str, Any],
    headcount: dict[str, Any],
    constraints: list[dict[str, Any]],
    exclude_names: set[str] | None = None,
) -> dict[str, Any]:
    """Pick cheapest qualifying venue; tie-break smaller capacity, then name order."""
    options: dict[str, dict[str, Any]] = facts.get("venue_options", {}) or {}
    total_hc = int(headcount.get("total", 0))
    excluded = exclude_names or set()

    if not options or total_hc <= 0:
        return {
            "status": "unknown",
            "selected": None,
            "capacity": 0,
            "cost": 0,
            "generator": False,
            "reason": "No venue options or headcount unknown",
            "closest": None,
            "gap": 0,
            "alternatives": [],
        }

    qualifying: list[dict[str, Any]] = []
    rejected_opts: list[dict[str, Any]] = []

    for name, raw_opt in options.items():
        if name in excluded:
            continue
        opt = dict(raw_opt)
        opt["name"] = name
        ok, reasons = _venue_qualifies(opt, total_hc, constraints)
        if ok:
            qualifying.append(opt)
        else:
            rejected_opts.append({"name": name, "capacity": opt.get("capacity", 0), "price": opt.get("price", 0), "reasons": reasons})

    if not qualifying:
        # Find closest option by capacity (highest capacity first)
        all_opts = [dict(v, name=k) for k, v in options.items() if k not in excluded]
        closest = max(all_opts, key=lambda o: int(o.get("capacity") or 0)) if all_opts else None
        gap = max(0, total_hc - int(closest.get("capacity") or 0)) if closest else total_hc
        return {
            "status": "none_fits",
            "selected": None,
            "capacity": 0,
            "cost": 0,
            "generator": False,
            "reason": f"No venue qualifies for headcount {total_hc}",
            "closest": closest,
            "gap": gap,
            "rejected_options": rejected_opts,
            "alternatives": [],
        }

    # Sort: cheapest price, then smaller capacity, then alphabetical name
    qualifying.sort(key=lambda o: (int(o["price"]), int(o["capacity"]), str(o["name"]).lower()))
    chosen = qualifying[0]

    gen_required = any(
        c.get("subject") == "venue.generator" and (c.get("op") == "require" or c.get("value") is True)
        for c in _get_constraints(constraints, area="venue", hard_only=True)
    )

    reason_parts = [f"cheapest qualifying venue (capacity {chosen['capacity']} >= {total_hc})"]
    if gen_required:
        reason_parts.append("generator backup verified")

    return {
        "status": "ok",
        "selected": chosen["name"],
        "capacity": int(chosen["capacity"]),
        "cost": int(chosen["price"]),
        "generator": bool(chosen.get("generator", False)),
        "accessible": bool(chosen.get("accessible", False)),
        "generator_required": gen_required,
        "reason": "; ".join(reason_parts),
        "closest": None,
        "gap": 0,
        "alternatives": [o["name"] for o in qualifying[1:]],
    }


# ---------------------------------------------------------------------------
# 4. Food
# ---------------------------------------------------------------------------

def plan_food(
    facts: dict[str, Any],
    headcount: dict[str, Any],
    constraints: list[dict[str, Any]],
    preferred_tier: str | None = None,
    exclude_tiers: set[str] | None = None,
) -> dict[str, Any]:
    """Compute food selection and cost. Quantity always equals headcount."""
    options: dict[str, dict[str, Any]] = facts.get("food_options", {}) or {}
    total_hc = int(headcount.get("total", 0))
    excluded = exclude_tiers or set()

    if not options or total_hc <= 0:
        return {
            "status": "unknown",
            "tier": None,
            "quantity": total_hc,
            "price_per_head": 0,
            "delivery_fee": 0,
            "cost": 0,
            "halal": True,
            "vegetarian_count": 0,
            "ramadan_iftar": False,
            "requested_quantity": facts.get("food_quantity"),
            "alternatives": [],
        }

    halal_required = False
    max_pph: int | None = None
    veg_share: float = 0.0
    ramadan_flag = False
    requested_qty = facts.get("food_quantity")

    for c in _get_constraints(constraints, area="food"):
        subj = c.get("subject", "")
        op = c.get("op", "")
        val = c.get("value")
        if subj == "food.halal" and (op == "require" or val is True):
            halal_required = True
        elif subj == "food.max_price_per_head" and isinstance(val, (int, float)):
            max_pph = int(val) if max_pph is None else min(max_pph, int(val))
        elif subj == "food.vegetarian_share" and isinstance(val, (int, float)):
            veg_share = float(val)
        elif subj in ("food.ramadan", "food.iftar") and (op == "require" or val is True):
            ramadan_flag = True
        elif subj == "food.quantity" and isinstance(val, (int, float)):
            requested_qty = int(val)

    qualifying: list[dict[str, Any]] = []
    for tier, raw_opt in options.items():
        if tier in excluded:
            continue
        pph = raw_opt.get("price_per_head")
        if pph is None:
            continue
        if halal_required and raw_opt.get("halal") is False:
            continue
        if max_pph is not None and int(pph) > max_pph:
            continue
        opt = dict(raw_opt)
        opt["tier"] = tier
        opt["price_per_head"] = int(pph)
        opt["delivery_fee"] = int(opt.get("delivery_fee") or 0)
        qualifying.append(opt)

    if not qualifying:
        return {
            "status": "none_fits",
            "tier": None,
            "quantity": total_hc,
            "price_per_head": 0,
            "delivery_fee": 0,
            "cost": 0,
            "halal": halal_required,
            "vegetarian_count": 0,
            "ramadan_iftar": ramadan_flag,
            "requested_quantity": requested_qty,
            "alternatives": [],
        }

    # Sort by total cost ascending, then tier name
    qualifying.sort(key=lambda o: (total_hc * o["price_per_head"] + o["delivery_fee"], o["tier"].lower()))

    chosen = qualifying[0]
    if preferred_tier:
        for opt in qualifying:
            if opt["tier"] == preferred_tier:
                chosen = opt
                break

    cost = total_hc * chosen["price_per_head"] + chosen["delivery_fee"]
    veg_count = 0
    if veg_share > 0:
        veg_count = math.ceil(total_hc * veg_share) if veg_share <= 1 else int(round(veg_share))

    return {
        "status": "ok",
        "tier": chosen["tier"],
        "quantity": total_hc,
        "price_per_head": chosen["price_per_head"],
        "delivery_fee": chosen["delivery_fee"],
        "cost": cost,
        "halal": bool(chosen.get("halal", True)),
        "halal_required": halal_required,
        "vegetarian_count": veg_count,
        "ramadan_iftar": ramadan_flag,
        "requested_quantity": requested_qty,
        "alternatives": [o["tier"] for o in qualifying if o["tier"] != chosen["tier"]],
    }


# ---------------------------------------------------------------------------
# 5. Schedule
# ---------------------------------------------------------------------------

def _parse_clock_minutes(time_str: str | None) -> int | None:
    """Parse '09:00', '2:30 PM', '14:00' into minutes since midnight."""
    if not time_str:
        return None
    s = str(time_str).strip().upper()
    m = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*(AM|PM)?$", s)
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    ampm = m.group(3)
    if ampm == "PM" and hour != 12:
        hour += 12
    elif ampm == "AM" and hour == 12:
        hour = 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour * 60 + minute


def format_pkt_12h(minutes_since_midnight: int) -> str:
    """Format minutes since midnight as 12-hour PKT clock string (e.g. '2:30 PM')."""
    total = minutes_since_midnight % (24 * 60)
    hour24 = total // 60
    minute = total % 60
    suffix = "AM" if hour24 < 12 else "PM"
    hour12 = hour24 % 12
    if hour12 == 0:
        hour12 = 12
    return f"{hour12}:{minute:02d} {suffix}"


def format_offset(minutes: int) -> str:
    """Format offset from start as '+H:MM'."""
    hours = minutes // 60
    mins = minutes % 60
    return f"+{hours}:{mins:02d}"


def _is_friday(date_str: str | None) -> bool:
    if not date_str:
        return False
    try:
        dt = datetime.date.fromisoformat(str(date_str).strip())
        return dt.weekday() == 4  # Friday
    except ValueError:
        return False


def plan_schedule(
    facts: dict[str, Any],
    judging: dict[str, Any],
    constraints: list[dict[str, Any]],
    defaults: dict[str, Any],
    prayer_defaults: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construct contiguous schedule blocks summing exactly to duration_min."""
    duration_min = facts.get("duration_min")
    if duration_min is None or int(duration_min) <= 0 or judging.get("status") == "unknown":
        return {
            "status": "unknown",
            "duration_min": duration_min if duration_min is not None else "unknown",
            "start_time": facts.get("start_time") or "unknown",
            "blocks": [],
            "total_minutes": 0,
            "feasible": False,
            "deficit": 0,
            "late_buffer_applied": False,
            "prayer_aligned": False,
        }

    dur = int(duration_min)
    sched_cfg = defaults.get("schedule", {})
    arrival = int(sched_cfg.get("arrival_buffer_min", 15))
    late_note = facts.get("late_note")
    late_buffer_applied = False
    if late_note:
        arrival += int(sched_cfg.get("late_buffer_extra_min", 10))
        late_buffer_applied = True

    opening = int(sched_cfg.get("opening_min", 10))
    lunch = int(sched_cfg.get("lunch_min", 25))
    closing = int(sched_cfg.get("closing_min", 10))
    split_ratio = float(sched_cfg.get("build_split_ratio", 0.6))

    prayer_req = facts.get("prayer_break_min")
    if prayer_req is not None:
        prayer_min = max(1, int(prayer_req))
    else:
        prayer_min = int(sched_cfg.get("default_prayer_min", 15))

    # Apply schedule constraints
    start_time_raw = facts.get("start_time")
    no_session_windows: list[tuple[int, int]] = []
    ramadan_iftar = any(
        c.get("subject") in ("food.ramadan", "food.iftar") and (c.get("op") == "require" or c.get("value") is True)
        for c in (constraints or [])
    )

    for c in _get_constraints(constraints, area="schedule"):
        subj = c.get("subject", "")
        val = c.get("value")
        if subj == "schedule.break_min" and isinstance(val, (int, float)):
            prayer_min = max(prayer_min, int(val))
        elif subj == "schedule.start_time" and val:
            start_time_raw = str(val)
        elif subj == "schedule.no_session_window" and val:
            parsed_win = _parse_window(val)
            if parsed_win:
                no_session_windows.append(parsed_win)

    judging_min = int(judging.get("judging_minutes", 0))
    fixed_total = arrival + opening + lunch + prayer_min + judging_min + closing
    remaining_for_build = dur - fixed_total

    if remaining_for_build < 2 or judging_min <= 0:
        return {
            "status": "infeasible",
            "duration_min": dur,
            "start_time": start_time_raw or "unknown",
            "blocks": [],
            "total_minutes": 0,
            "feasible": False,
            "deficit": max(0, 2 - remaining_for_build),
            "late_buffer_applied": late_buffer_applied,
            "prayer_aligned": False,
            "reason": f"Fixed blocks ({fixed_total} min) leave {remaining_for_build} min for build inside {dur} min",
        }

    build_1 = max(1, round(remaining_for_build * split_ratio))
    build_2 = remaining_for_build - build_1
    if build_2 < 1:
        build_1 -= 1
        build_2 = 1

    # F8: Prayer-aware alignment when start_time is known
    start_clock = _parse_clock_minutes(start_time_raw)
    prayer_aligned = False
    prayer_name = None
    event_date = facts.get("event_date")

    if start_clock is not None:
        p_cfg = prayer_defaults if prayer_defaults is not None else load_prayer_defaults()
        target_windows = []
        if _is_friday(event_date) and "friday_jumuah" in p_cfg:
            target_windows.append(p_cfg["friday_jumuah"])
        target_windows.extend(p_cfg.get("windows", []))

        # Current prayer start = start_clock + arrival + opening + build_1 + lunch
        # We can shift minutes between build_1 and build_2 (keeping both >= 1) to align prayer_break
        event_end_clock = start_clock + dur
        for win in target_windows:
            w_start = _parse_clock_minutes(win.get("start"))
            w_end = _parse_clock_minutes(win.get("end"))
            w_pref = _parse_clock_minutes(win.get("preferred")) or w_start
            if w_start is None or w_end is None:
                continue
            # Check if window overlaps event
            if w_start < event_end_clock and w_end > start_clock:
                # Desired build_1 so prayer starts at w_pref (or inside [w_start, w_end - prayer_min])
                desired_offset = w_pref - start_clock
                desired_b1 = desired_offset - (arrival + opening + lunch)
                min_b1 = 1
                max_b1 = remaining_for_build - 1
                if min_b1 <= desired_b1 <= max_b1:
                    build_1 = desired_b1
                    build_2 = remaining_for_build - build_1
                    prayer_aligned = True
                    prayer_name = win.get("name")
                    break
                else:
                    # Clamp within feasible build_1 and check if still inside [w_start, w_end]
                    clamped_b1 = max(min_b1, min(max_b1, desired_b1))
                    actual_prayer_start = start_clock + arrival + opening + clamped_b1 + lunch
                    if w_start <= actual_prayer_start <= (w_end - prayer_min):
                        build_1 = clamped_b1
                        build_2 = remaining_for_build - build_1
                        prayer_aligned = True
                        prayer_name = win.get("name")
                        break

    meal_key = "iftar" if ramadan_iftar else "lunch"
    raw_blocks = [
        ("arrival", arrival),
        ("opening", opening),
        ("build_1", build_1),
        (meal_key, lunch),
        ("prayer_break", prayer_min),
        ("build_2", build_2),
        ("judging", judging_min),
        ("closing", closing),
    ]

    blocks: list[dict[str, Any]] = []
    cursor = 0
    for idx, (name, length) in enumerate(raw_blocks, start=1):
        b_start = cursor
        b_end = cursor + length
        block: dict[str, Any] = {
            "index": idx,
            "name": name,
            "minutes": length,
            "start_min": b_start,
            "end_min": b_end,
            "start_label": format_pkt_12h(start_clock + b_start) if start_clock is not None else format_offset(b_start),
            "end_label": format_pkt_12h(start_clock + b_end) if start_clock is not None else format_offset(b_end),
        }
        if name == "prayer_break" and prayer_name:
            block["prayer_name"] = prayer_name
        blocks.append(block)
        cursor = b_end

    # Check window conflicts if no_session_windows were specified
    window_violations: list[str] = []
    if start_clock is not None and no_session_windows:
        for block in blocks:
            if block["name"] in ("build_1", "build_2", "judging"):
                abs_s = start_clock + block["start_min"]
                abs_e = start_clock + block["end_min"]
                for ws, we in no_session_windows:
                    if abs_s < we and abs_e > ws:
                        window_violations.append(
                            f"{block['name']} overlaps forbidden window {format_pkt_12h(ws)}-{format_pkt_12h(we)}"
                        )

    return {
        "status": "ok" if not window_violations else "window_conflict",
        "duration_min": dur,
        "start_time": format_pkt_12h(start_clock) if start_clock is not None else "unknown",
        "clock_mode": start_clock is not None,
        "blocks": blocks,
        "total_minutes": cursor,
        "feasible": len(window_violations) == 0,
        "deficit": 0,
        "late_buffer_applied": late_buffer_applied,
        "prayer_aligned": prayer_aligned,
        "prayer_name": prayer_name,
        "window_violations": window_violations,
    }


def _parse_window(val: Any) -> tuple[int, int] | None:
    """Parse window value like '13:00-14:00' or ['13:00', '14:00']."""
    if isinstance(val, (list, tuple)) and len(val) == 2:
        s = _parse_clock_minutes(str(val[0]))
        e = _parse_clock_minutes(str(val[1]))
        if s is not None and e is not None and e > s:
            return (s, e)
    elif isinstance(val, str) and "-" in val:
        parts = val.split("-", 1)
        s = _parse_clock_minutes(parts[0])
        e = _parse_clock_minutes(parts[1])
        if s is not None and e is not None and e > s:
            return (s, e)
    return None


# ---------------------------------------------------------------------------
# 6. Budget
# ---------------------------------------------------------------------------

def plan_budget(
    facts: dict[str, Any],
    venue: dict[str, Any],
    food: dict[str, Any],
    judging: dict[str, Any],
    constraints: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute spent, remaining, and wishlist fit flags."""
    budget_total = facts.get("budget_total")
    committed_costs: dict[str, int] = dict(facts.get("committed_costs", {}) or {})
    wishlist_raw: dict[str, dict[str, Any]] = facts.get("wishlist", {}) or {}

    venue_cost = int(venue.get("cost", 0))
    food_cost = int(food.get("cost", 0))
    judge_cost = int(judging.get("cost", 0))
    judge_worst_case = int(judging.get("worst_case_cost", 0))
    committed_total = sum(int(v) for v in committed_costs.values())

    spent = venue_cost + food_cost + judge_cost + committed_total

    # Apply budget.cap / budget.reserve constraints
    effective_cap = int(budget_total) if budget_total is not None else None
    reserve = 0
    for c in _get_constraints(constraints, area="budget", hard_only=True):
        subj = c.get("subject", "")
        val = c.get("value")
        if subj == "budget.cap" and isinstance(val, (int, float)):
            effective_cap = int(val) if effective_cap is None else min(effective_cap, int(val))
        elif subj == "budget.reserve" and isinstance(val, (int, float)):
            reserve = max(reserve, int(val))

    if effective_cap is None:
        return {
            "status": "unknown",
            "budget_total": "unknown",
            "effective_cap": "unknown",
            "reserve": reserve,
            "venue_cost": venue_cost,
            "food_cost": food_cost,
            "judge_cost": judge_cost,
            "judge_cost_worst_case": judge_worst_case,
            "committed_costs": committed_costs,
            "committed_total": committed_total,
            "spent": spent,
            "remaining": "unknown",
            "wishlist": [],
        }

    spendable_cap = effective_cap - reserve
    remaining = spendable_cap - spent

    wishlist_items: list[dict[str, Any]] = []
    for label, item in sorted(wishlist_raw.items()):
        item_cost = int(item.get("cost", 0))
        wishlist_items.append({
            "label": item.get("label", label),
            "cost": item_cost,
            "status": "fits" if item_cost <= remaining else "does_not_fit",
            "source_id": item.get("source_id", 0),
            "quote": item.get("quote", ""),
        })

    return {
        "status": "ok" if remaining >= 0 else "over_budget",
        "budget_total": int(budget_total),
        "effective_cap": effective_cap,
        "reserve": reserve,
        "venue_cost": venue_cost,
        "food_cost": food_cost,
        "judge_cost": judge_cost,
        "judge_cost_worst_case": judge_worst_case,
        "committed_costs": committed_costs,
        "committed_total": committed_total,
        "spent": spent,
        "remaining": remaining,
        "wishlist": wishlist_items,
    }


# ---------------------------------------------------------------------------
# Full plan + Degradation ladder
# ---------------------------------------------------------------------------

def find_unhandled_constraints(
    constraints: list[dict[str, Any]],
    known_subjects: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Return constraints whose subject is not handled by code (never silently dropped)."""
    known = known_subjects if known_subjects is not None else load_known_subjects()
    # Also recognise food.ramadan / food.iftar / food.quantity as handled
    handled = known | {"food.ramadan", "food.iftar", "food.quantity"}
    return [c for c in (constraints or []) if c.get("subject") not in handled]


def build_plan(
    facts: dict[str, Any],
    constraints: list[dict[str, Any]] | None = None,
    defaults: dict[str, Any] | None = None,
    known_subjects: set[str] | None = None,
    prayer_defaults: dict[str, Any] | None = None,
    preferred_food_tier: str | None = None,
) -> dict[str, Any]:
    """Run all planning areas in dependency order + degradation ladder if over budget.

    Pure function: dicts in, dicts out.
    """
    c_list = constraints or []
    cfg = defaults if defaults is not None else load_defaults()
    p_cfg = prayer_defaults if prayer_defaults is not None else load_prayer_defaults()

    judging = plan_judging(facts, c_list, cfg)
    headcount = plan_headcount(facts, judging, c_list)
    venue = plan_venue(facts, headcount, c_list)
    food = plan_food(facts, headcount, c_list, preferred_tier=preferred_food_tier)
    schedule = plan_schedule(facts, judging, c_list, cfg, prayer_defaults=p_cfg)
    budget = plan_budget(facts, venue, food, judging, c_list)

    degradation_steps: list[str] = []

    # Degradation ladder (PLANNER_SPEC.md): only if over budget
    if budget.get("status") == "over_budget":
        # Step 1: Try cheaper food tier
        if food.get("status") == "ok" and food.get("alternatives"):
            tried_food = {food["tier"]}
            while budget.get("status") == "over_budget":
                alt_food = plan_food(facts, headcount, c_list, exclude_tiers=tried_food)
                if alt_food.get("status") != "ok":
                    break
                tried_food.add(alt_food["tier"])
                if alt_food["cost"] < food["cost"]:
                    degradation_steps.append(
                        f"food tier switched from '{food['tier']}' to cheaper '{alt_food['tier']}' "
                        f"(saved Rs {food['cost'] - alt_food['cost']})"
                    )
                    food = alt_food
                    budget = plan_budget(facts, venue, food, judging, c_list)
                else:
                    break

        # Step 2: Try cheaper venue that still fits and satisfies hard constraints
        if budget.get("status") == "over_budget" and venue.get("status") == "ok" and venue.get("alternatives"):
            tried_venues = {venue["selected"]}
            while budget.get("status") == "over_budget":
                alt_venue = plan_venue(facts, headcount, c_list, exclude_names=tried_venues)
                if alt_venue.get("status") != "ok":
                    break
                tried_venues.add(alt_venue["selected"])
                if alt_venue["cost"] < venue["cost"]:
                    degradation_steps.append(
                        f"venue switched from '{venue['selected']}' to cheaper '{alt_venue['selected']}' "
                        f"(saved Rs {venue['cost'] - alt_venue['cost']})"
                    )
                    venue = alt_venue
                    budget = plan_budget(facts, venue, food, judging, c_list)
                else:
                    break

        # Step 3: Fewer judges is NOT allowed. Stop.
        if budget.get("status") == "over_budget":
            degradation_steps.append(
                f"infeasible: over budget by Rs {abs(int(budget['remaining']))}; reducing judges is forbidden"
            )

    unhandled = find_unhandled_constraints(c_list, known_subjects=known_subjects)
    feasible = (
        judging.get("status") == "ok"
        and headcount.get("status") == "ok"
        and venue.get("status") == "ok"
        and food.get("status") == "ok"
        and schedule.get("feasible", False)
        and budget.get("status") == "ok"
    )

    return {
        "feasible": feasible,
        "judging": judging,
        "headcount": headcount,
        "venue": venue,
        "food": food,
        "schedule": schedule,
        "budget": budget,
        "degradation_steps": degradation_steps,
        "unhandled_constraints": unhandled,
    }

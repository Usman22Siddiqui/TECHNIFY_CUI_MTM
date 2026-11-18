"""Tests for core/planner.py — all formulas, edge cases, degradation ladder, PK features."""

from __future__ import annotations

from core.planner import (
    build_plan,
    load_defaults,
    plan_judging,
    plan_headcount,
    plan_venue,
    plan_food,
    plan_schedule,
    plan_budget,
    format_pkt_12h,
)


def _base_facts() -> dict:
    """Synthetic baseline event facts for unit testing."""
    return {
        "students": 150,
        "team_size": 3,
        "staff": 10,
        "duration_min": 240,
        "prayer_break_min": 20,
        "judges_confirmed": 20,
        "honorarium": 3000,
        "judge_min_per_team": 10,
        "judge_max_teams": 3,
        "budget_total": 650000,
        "venue_options": {
            "Small Room": {"name": "Small Room", "capacity": 120, "price": 60000, "generator": True},
            "Main Hall": {"name": "Main Hall", "capacity": 200, "price": 120000, "generator": False},
            "Auditorium": {"name": "Auditorium", "capacity": 250, "price": 180000, "generator": True},
        },
        "food_options": {
            "Standard": {"tier": "Standard", "price_per_head": 900, "delivery_fee": 5000, "halal": True},
        },
        "committed_costs": {"printing": 15000, "banners": 10000},
        "wishlist": {"DJ": {"label": "DJ", "cost": 25000, "source_id": 8, "quote": "DJ 25000"}},
    }


class TestWorkedExampleGolden:
    """Verify worked example formulas from PLANNER_SPEC.md."""

    def test_sample_worked_example_figures(self):
        plan = build_plan(_base_facts(), [])
        assert plan["feasible"] is True
        assert plan["judging"]["teams"] == 50
        assert plan["judging"]["judges_needed"] == 17
        assert plan["judging"]["judges_used"] == 17
        assert plan["judging"]["reserves"] == 3
        assert plan["judging"]["cost"] == 17 * 3000
        assert plan["judging"]["worst_case_cost"] == 20 * 3000
        assert plan["headcount"]["total"] == 177
        assert plan["venue"]["selected"] == "Main Hall"
        assert plan["venue"]["cost"] == 120000
        assert plan["food"]["quantity"] == 177
        assert plan["food"]["cost"] == 177 * 900 + 5000
        assert plan["schedule"]["total_minutes"] == 240
        expected_spent = 120000 + (177 * 900 + 5000) + (17 * 3000) + 25000
        assert plan["budget"]["spent"] == expected_spent
        assert plan["budget"]["remaining"] == 650000 - expected_spent
        assert plan["budget"]["wishlist"][0]["label"] == "DJ"
        assert plan["budget"]["wishlist"][0]["status"] == "fits"


class TestPlannerEdgeCases:

    def test_ceil_edge_students_not_divisible(self):
        facts = _base_facts()
        facts["students"] = 151  # 151 / 3 -> 51 teams -> ceil(51/3) = 17 judges
        j = plan_judging(facts, [], load_defaults())
        assert j["teams"] == 51
        assert j["judges_needed"] == 17

        facts["students"] = 154  # 154 / 3 -> 52 teams -> ceil(52/3) = 18 judges
        j2 = plan_judging(facts, [], load_defaults())
        assert j2["teams"] == 52
        assert j2["judges_needed"] == 18

    def test_headcount_boundary_exact_capacity(self):
        facts = _base_facts()
        facts["venue_options"] = {
            "Exact Hall": {"name": "Exact Hall", "capacity": 177, "price": 100000, "generator": True},
        }
        plan = build_plan(facts, [])
        assert plan["venue"]["status"] == "ok"
        assert plan["venue"]["selected"] == "Exact Hall"

    def test_venue_price_tie_breaks_smaller_capacity_then_name(self):
        facts = _base_facts()
        facts["venue_options"] = {
            "Zeta Hall": {"name": "Zeta Hall", "capacity": 200, "price": 100000},
            "Alpha Hall": {"name": "Alpha Hall", "capacity": 200, "price": 100000},
            "Big Hall": {"name": "Big Hall", "capacity": 300, "price": 100000},
        }
        plan = build_plan(facts, [])
        assert plan["venue"]["selected"] == "Alpha Hall"

    def test_no_venue_fits_reports_closest_and_gap(self):
        facts = _base_facts()
        facts["venue_options"] = {
            "Tiny A": {"name": "Tiny A", "capacity": 100, "price": 50000},
            "Tiny B": {"name": "Tiny B", "capacity": 160, "price": 80000},
        }
        plan = build_plan(facts, [])
        assert plan["venue"]["status"] == "none_fits"
        assert plan["venue"]["closest"]["name"] == "Tiny B"
        assert plan["venue"]["gap"] == 17  # 177 - 160
        assert plan["feasible"] is False

    def test_generator_constraint_picks_generator_venue(self):
        facts = _base_facts()
        constraints = [{"area": "venue", "subject": "venue.generator", "op": "require", "value": True, "hard": True}]
        plan = build_plan(facts, constraints)
        assert plan["venue"]["selected"] == "Auditorium"
        assert plan["venue"]["generator"] is True

    def test_one_judge_short_flags_shortfall(self):
        facts = _base_facts()
        facts["judges_confirmed"] = 16  # 17 needed
        plan = build_plan(facts, [])
        assert plan["judging"]["status"] == "shortfall"
        assert plan["judging"]["shortfall"] == 1
        assert plan["feasible"] is False

    def test_degradation_ladder_cheaper_food_tier(self):
        facts = _base_facts()
        facts["budget_total"] = 350000
        facts["food_options"] = {
            "Premium": {"tier": "Premium", "price_per_head": 1500, "delivery_fee": 5000, "halal": True},
            "Economy": {"tier": "Economy", "price_per_head": 700, "delivery_fee": 3000, "halal": True},
        }
        plan = build_plan(facts, [], preferred_food_tier="Premium")
        assert plan["feasible"] is True
        assert plan["food"]["tier"] == "Economy"
        assert len(plan["degradation_steps"]) >= 1

    def test_infeasible_budget_never_reduces_judges(self):
        facts = _base_facts()
        facts["budget_total"] = 100000  # impossible
        plan = build_plan(facts, [])
        assert plan["feasible"] is False
        assert plan["judging"]["judges_used"] == 17
        assert plan["budget"]["status"] == "over_budget"
        assert any("reducing judges is forbidden" in s for s in plan["degradation_steps"])

    def test_schedule_sum_and_contiguity(self):
        plan = build_plan(_base_facts(), [])
        blocks = plan["schedule"]["blocks"]
        assert sum(b["minutes"] for b in blocks) == 240
        for idx in range(len(blocks)):
            assert blocks[idx]["minutes"] > 0
            if idx > 0:
                assert blocks[idx]["start_min"] == blocks[idx - 1]["end_min"]

    def test_duration_too_short_for_judging(self):
        facts = _base_facts()
        facts["duration_min"] = 60  # fixed blocks exceed 60 min
        plan = build_plan(facts, [])
        assert plan["schedule"]["feasible"] is False
        assert plan["feasible"] is False

    def test_prayer_minutes_larger_than_default(self):
        facts = _base_facts()
        facts["prayer_break_min"] = 45
        plan = build_plan(facts, [])
        prayer_block = next(b for b in plan["schedule"]["blocks"] if b["name"] == "prayer_break")
        assert prayer_block["minutes"] == 45
        assert plan["schedule"]["total_minutes"] == 240

    def test_prayer_aware_schedule_with_start_time_and_friday(self):
        facts = _base_facts()
        facts["start_time"] = "11:00"
        facts["event_date"] = "2026-11-20"  # Friday
        plan = build_plan(facts, [])
        assert plan["schedule"]["clock_mode"] is True
        assert plan["schedule"]["prayer_aligned"] is True
        assert plan["schedule"]["prayer_name"] == "Jumuah"
        assert plan["schedule"]["total_minutes"] == 240

    def test_late_note_adds_arrival_buffer(self):
        facts = _base_facts()
        base_plan = build_plan(facts, [])
        facts["late_note"] = "Heavy traffic on Kashmir Highway"
        late_plan = build_plan(facts, [])
        base_arr = base_plan["schedule"]["blocks"][0]["minutes"]
        late_arr = late_plan["schedule"]["blocks"][0]["minutes"]
        assert late_arr > base_arr
        assert late_plan["schedule"]["late_buffer_applied"] is True
        assert late_plan["schedule"]["total_minutes"] == 240

    def test_ramadan_iftar_and_vegetarian_share(self):
        facts = _base_facts()
        constraints = [
            {"area": "food", "subject": "food.ramadan", "op": "require", "value": True, "hard": True},
            {"area": "food", "subject": "food.vegetarian_share", "op": "eq", "value": 0.1, "hard": True},
        ]
        plan = build_plan(facts, constraints)
        assert plan["food"]["ramadan_iftar"] is True
        assert plan["food"]["vegetarian_count"] == 18  # ceil(177 * 0.1)
        assert any(b["name"] == "iftar" for b in plan["schedule"]["blocks"])

    def test_unhandled_constraint_never_dropped(self):
        facts = _base_facts()
        constraints = [
            {"area": "venue", "subject": "venue.projector_4k", "op": "require", "value": True, "hard": True},
        ]
        plan = build_plan(facts, constraints)
        assert len(plan["unhandled_constraints"]) == 1
        assert plan["unhandled_constraints"][0]["subject"] == "venue.projector_4k"

    def test_missing_facts_marked_unknown(self):
        plan = build_plan({}, [])
        assert plan["judging"]["status"] == "unknown"
        assert plan["budget"]["budget_total"] == "unknown"
        assert plan["feasible"] is False

    def test_pkt_12h_formatting(self):
        assert format_pkt_12h(0) == "12:00 AM"
        assert format_pkt_12h(9 * 60 + 30) == "9:30 AM"
        assert format_pkt_12h(12 * 60) == "12:00 PM"
        assert format_pkt_12h(14 * 60 + 30) == "2:30 PM"

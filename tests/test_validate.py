"""Tests for core/validate.py — passing and failing tests for all six checks."""

from __future__ import annotations

import copy
from core.planner import build_plan
from core.validate import validate, all_checks_pass, first_failure, CHECK_NAMES


def _valid_facts() -> dict:
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
            "Main Hall": {"name": "Main Hall", "capacity": 200, "price": 120000, "generator": True},
        },
        "food_options": {
            "Standard": {"tier": "Standard", "price_per_head": 900, "delivery_fee": 5000, "halal": True},
        },
        "committed_costs": {"printing": 15000},
        "wishlist": {},
    }


class TestSixChecksPass:

    def test_valid_plan_passes_all_six_checks(self):
        facts = _valid_facts()
        plan = build_plan(facts, [])
        checks = validate(plan, facts, [])
        assert set(checks.keys()) == set(CHECK_NAMES)
        assert all_checks_pass(checks) is True
        assert first_failure(checks) is None


class TestEachCheckFails:

    def test_figures_fails_on_tampered_headcount(self):
        facts = _valid_facts()
        plan = build_plan(facts, [])
        bad = copy.deepcopy(plan)
        bad["headcount"]["total"] = 150  # wrong, should be 177
        checks = validate(bad, facts, [])
        assert checks["figures"]["ok"] is False
        assert all_checks_pass(checks) is False

    def test_figures_fails_on_wrong_food_quantity_request(self):
        facts = _valid_facts()
        facts["food_quantity"] = 150  # below headcount 177!
        plan = build_plan(facts, [])
        checks = validate(plan, facts, [])
        assert checks["figures"]["ok"] is False
        assert checks["figures"]["code"] == "FOOD_QUANTITY_MISMATCH"

    def test_budget_fails_when_over_budget(self):
        facts = _valid_facts()
        facts["budget_total"] = 200000
        plan = build_plan(facts, [])
        checks = validate(plan, facts, [])
        assert checks["budget"]["ok"] is False
        assert checks["budget"]["code"] == "OVER_BUDGET"

    def test_venue_fails_when_capacity_below_headcount(self):
        facts = _valid_facts()
        facts["venue_options"]["Main Hall"]["capacity"] = 100
        plan = build_plan(facts, [])
        checks = validate(plan, facts, [])
        assert checks["venue"]["ok"] is False

    def test_venue_fails_when_generator_constraint_violated(self):
        facts = _valid_facts()
        facts["venue_options"]["Main Hall"]["generator"] = False
        constraints = [{"area": "venue", "subject": "venue.generator", "op": "require", "value": True, "hard": True}]
        plan = build_plan(facts, constraints)
        checks = validate(plan, facts, constraints)
        assert checks["venue"]["ok"] is False

    def test_schedule_fails_when_blocks_do_not_sum(self):
        facts = _valid_facts()
        plan = build_plan(facts, [])
        bad = copy.deepcopy(plan)
        bad["schedule"]["blocks"][0]["minutes"] += 10
        checks = validate(bad, facts, [])
        assert checks["schedule"]["ok"] is False

    def test_schedule_fails_when_duration_too_short(self):
        facts = _valid_facts()
        facts["duration_min"] = 50
        plan = build_plan(facts, [])
        checks = validate(plan, facts, [])
        assert checks["schedule"]["ok"] is False

    def test_judges_fails_on_shortfall(self):
        facts = _valid_facts()
        facts["judges_confirmed"] = 10  # need 17
        plan = build_plan(facts, [])
        checks = validate(plan, facts, [])
        assert checks["judges"]["ok"] is False
        assert checks["judges"]["code"] == "JUDGES_SHORTFALL"

    def test_judges_fails_when_team_missing(self):
        facts = _valid_facts()
        plan = build_plan(facts, [])
        bad = copy.deepcopy(plan)
        bad["judging"]["assignments"]["J1"].pop()
        checks = validate(bad, facts, [])
        assert checks["judges"]["ok"] is False
        assert checks["judges"]["code"] == "TEAM_COVERAGE"

    def test_coverage_fails_when_area_missing(self):
        facts = _valid_facts()
        plan = build_plan(facts, [])
        bad = copy.deepcopy(plan)
        bad["food"]["status"] = "unknown"
        checks = validate(bad, facts, [])
        assert checks["coverage"]["ok"] is False
        assert checks["coverage"]["code"] == "MISSING_AREAS"

    def test_coverage_fails_when_unhandled_constraint_dropped(self):
        facts = _valid_facts()
        constraints = [{"area": "venue", "subject": "venue.custom_stage", "op": "require", "value": True, "hard": True}]
        plan = build_plan(facts, constraints)
        # Properly listed -> passes
        assert validate(plan, facts, constraints)["coverage"]["ok"] is True
        # Silently dropped -> fails
        bad = copy.deepcopy(plan)
        bad["unhandled_constraints"] = []
        assert validate(bad, facts, constraints)["coverage"]["ok"] is False

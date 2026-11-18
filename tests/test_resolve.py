"""Tests for core/resolve.py — supersession, authority, noise/request, unit guard."""

from __future__ import annotations

import pytest
from core.resolve import resolve_facts, load_authority_config, format_rejection


class TestSupersession:

    def test_newer_date_wins(self):
        msgs = [
            {
                "i": 1, "r": "caterer", "d": "2024-02-01", "k": "fact",
                "f": [{"key": "food_option.price_per_head", "v": 800, "u": "PKR", "q": "800", "ref": "Standard"}],
                "c": [],
            },
            {
                "i": 2, "r": "caterer", "d": "2024-02-05", "k": "fact",
                "f": [{"key": "food_option.price_per_head", "v": 950, "u": "PKR", "q": "950", "ref": "Standard"}],
                "c": [],
            },
        ]
        res = resolve_facts(msgs)
        assert res["facts"]["food_options"]["Standard"]["price_per_head"] == 950
        assert len(res["superseded"]) == 1
        assert res["superseded"][0]["old_id"] == 1
        assert res["superseded"][0]["new_id"] == 2

    def test_older_date_arriving_late_is_out_of_date(self):
        msgs = [
            {
                "i": 1, "r": "caterer", "d": "2024-02-10", "k": "fact",
                "f": [{"key": "food_option.price_per_head", "v": 950, "u": "PKR", "q": "950", "ref": "Standard"}],
                "c": [],
            },
            {
                "i": 2, "r": "caterer", "d": "2024-02-02", "k": "fact",
                "f": [{"key": "food_option.price_per_head", "v": 800, "u": "PKR", "q": "800", "ref": "Standard"}],
                "c": [],
            },
        ]
        res = resolve_facts(msgs)
        assert res["facts"]["food_options"]["Standard"]["price_per_head"] == 950
        assert len(res["rejected"]) == 1
        assert res["rejected"][0]["code"] == "OUT_OF_DATE"
        assert "msg #2" in res["rejected"][0]["reason_en"]

    def test_same_day_tie_later_id_wins(self):
        msgs = [
            {
                "i": 1, "r": "finance", "d": "2024-02-05", "k": "fact",
                "f": [{"key": "committed_cost", "v": 10000, "u": "PKR", "q": "10000", "ref": "printing"}],
                "c": [],
            },
            {
                "i": 3, "r": "finance", "d": "2024-02-05", "k": "fact",
                "f": [{"key": "committed_cost", "v": 14000, "u": "PKR", "q": "14000", "ref": "printing"}],
                "c": [],
            },
        ]
        res = resolve_facts(msgs)
        assert res["facts"]["committed_costs"]["printing"] == 14000
        assert len(res["superseded"]) == 1

    def test_different_ref_not_superseded(self):
        msgs = [
            {
                "i": 1, "r": "venue", "d": "2024-02-01", "k": "fact",
                "f": [
                    {"key": "venue_option.capacity", "v": 200, "u": "count", "q": "200", "ref": "Hall A"},
                    {"key": "venue_option.price", "v": 100000, "u": "PKR", "q": "100000", "ref": "Hall A"},
                ],
                "c": [],
            },
            {
                "i": 2, "r": "venue", "d": "2024-02-05", "k": "fact",
                "f": [
                    {"key": "venue_option.capacity", "v": 250, "u": "count", "q": "250", "ref": "Hall B"},
                    {"key": "venue_option.price", "v": 150000, "u": "PKR", "q": "150000", "ref": "Hall B"},
                ],
                "c": [],
            },
        ]
        res = resolve_facts(msgs)
        assert "Hall A" in res["facts"]["venue_options"]
        assert "Hall B" in res["facts"]["venue_options"]
        assert len(res["superseded"]) == 0


class TestAuthorityMatrix:
    """Data-driven tests against config/authority.json."""

    def test_every_role_against_every_key(self):
        cfg = load_authority_config()
        roles = cfg["roles"]
        allowed_map = cfg["authority"]["allowed_keys"]

        for key, allowed_roles in allowed_map.items():
            if key == "wishlist_item":
                continue
            for role in roles:
                msg = {
                    "i": 1, "r": role, "d": "2024-02-01", "k": "fact",
                    "f": [{"key": key, "v": 100, "u": "count", "q": "100", "ref": "item"}],
                    "c": [],
                }
                res = resolve_facts([msg], authority_config=cfg)
                if role in allowed_roles:
                    assert len(res["rejected"]) == 0, f"{role} should be allowed for {key}"
                else:
                    assert len(res["rejected"]) == 1, f"{role} should be rejected for {key}"
                    assert res["rejected"][0]["code"] == "NO_AUTHORITY"

    def test_contradicts_authority_when_authority_already_set_fact(self):
        msgs = [
            {
                "i": 1, "r": "authority", "d": "2024-02-01", "k": "fact",
                "f": [{"key": "students", "v": 150, "u": "count", "q": "150"}],
                "c": [],
            },
            {
                "i": 2, "r": "caterer", "d": "2024-02-02", "k": "fact",
                "f": [{"key": "students", "v": 120, "u": "count", "q": "120"}],
                "c": [],
            },
        ]
        res = resolve_facts(msgs)
        assert res["facts"]["students"] == 150
        assert len(res["rejected"]) == 1
        assert res["rejected"][0]["code"] == "CONTRADICTS_AUTHORITY"


class TestRelevanceAndGuards:

    def test_noise_dropped(self):
        msgs = [
            {"i": 1, "r": "participant", "d": "2024-02-01", "k": "noise", "f": [], "c": []},
        ]
        res = resolve_facts(msgs)
        assert res["message_statuses"][1]["status"] == "ignored"
        assert res["message_statuses"][1]["reason_code"] == "NOT_RELEVANT"

    def test_request_goes_to_wishlist_not_committed_costs(self):
        msgs = [
            {
                "i": 1, "r": "requester", "d": "2024-02-01", "k": "request",
                "f": [{"key": "wishlist_item", "v": 25000, "u": "PKR", "q": "DJ 25000", "ref": "DJ"}],
                "c": [],
            },
        ]
        res = resolve_facts(msgs)
        assert "DJ" in res["facts"]["wishlist"]
        assert res["facts"]["wishlist"]["DJ"]["cost"] == 25000
        assert res["facts"]["committed_costs"] == {}

    def test_unit_anomaly_rejected(self):
        msgs = [
            {
                "i": 1, "r": "finance", "d": "2024-02-01", "k": "fact",
                "f": [{"key": "budget_total", "v": 650000, "u": "PKR", "q": "650000"}],
                "c": [],
            },
            {
                "i": 2, "r": "finance", "d": "2024-02-05", "k": "fact",
                "f": [{"key": "budget_total", "v": 650, "u": "PKR", "q": "650"}],
                "c": [],
            },
        ]
        res = resolve_facts(msgs)
        assert res["facts"]["budget_total"] == 650000
        assert len(res["rejected"]) == 1
        assert res["rejected"][0]["code"] == "UNIT_ANOMALY"

    def test_bilingual_rejection_templates_exist_for_all_codes(self):
        codes = [
            ("UNGROUNDED", {}),
            ("NO_AUTHORITY", {"key": "students"}),
            ("BREAKS_CHECK", {"check": "budget", "detail": "over"}),
            ("OUT_OF_DATE", {"key": "food", "newer_id": 2}),
            ("CONTRADICTS_AUTHORITY", {"key": "students"}),
            ("UNIT_ANOMALY", {"key": "budget_total", "value": 650, "existing": 650000}),
            ("REQUEST_ONLY", {}),
            ("NOT_RELEVANT", {}),
        ]
        for code, kwargs in codes:
            en, ur = format_rejection(9, "caterer", code, **kwargs)
            assert "REJECTED msg #9" in en
            assert code in en
            assert "Plan unchanged" in en
            assert "مسترد پیغام #9" in ur
            assert code in ur
            assert "منصوبہ برقرار ہے" in ur

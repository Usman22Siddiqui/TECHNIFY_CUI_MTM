"""Tests for core/ground.py — grounding check with Pakistani number formats."""

from __future__ import annotations

from core.ground import normalise_number, ground_facts, _extract_all_numbers


class TestNormaliseNumber:
    """Pakistani number format normalisation."""

    def test_plain_integer(self):
        assert normalise_number("650000") == 650000

    def test_international_commas(self):
        assert normalise_number("650,000") == 650000

    def test_lakh_grouping(self):
        """Rs 6,50,000 → 650000"""
        assert normalise_number("6,50,000") == 650000

    def test_k_suffix(self):
        """650k → 650000"""
        assert normalise_number("650k") == 650000

    def test_lakh_suffix(self):
        """6.5 lakh → 650000"""
        assert normalise_number("6.5 lakh") == 650000

    def test_lac_suffix(self):
        """1.2 lac → 120000"""
        assert normalise_number("1.2 lac") == 120000

    def test_rs_prefix(self):
        """Rs 1200 → 1200"""
        assert normalise_number("Rs 1200") == 1200

    def test_rs_prefix_with_slash_dash(self):
        """Rs 1200/- → 1200"""
        assert normalise_number("Rs 1200/-") == 1200

    def test_pkr_prefix(self):
        assert normalise_number("PKR 50000") == 50000

    def test_paanch_hazar(self):
        """paanch hazar → 5000"""
        assert normalise_number("paanch hazar") == 5000

    def test_das_hazar(self):
        """das hazar → 10000"""
        assert normalise_number("das hazar") == 10000

    def test_ek_lakh(self):
        """ek lakh → 100000"""
        assert normalise_number("ek lakh") == 100000

    def test_do_hazar(self):
        """do hazar → 2000"""
        assert normalise_number("do hazar") == 2000

    def test_crore(self):
        """1 crore → 10000000"""
        assert normalise_number("1 crore") == 10000000

    def test_empty_string(self):
        assert normalise_number("") is None

    def test_non_numeric(self):
        assert normalise_number("hello world") is None

    def test_decimal(self):
        assert normalise_number("1200.50") == 1200


class TestExtractAllNumbers:

    def test_multiple_formats_in_text(self):
        text = "Budget is Rs 6,50,000 and food costs 650k per batch"
        nums = _extract_all_numbers(text)
        assert 650000 in nums

    def test_number_words_in_text(self):
        text = "paanch hazar rupees for printing"
        nums = _extract_all_numbers(text)
        assert 5000 in nums

    def test_mixed_numbers(self):
        text = "150 students, budget 6.5 lakh, 20 judges"
        nums = _extract_all_numbers(text)
        assert 150 in nums
        assert 650000 in nums
        assert 20 in nums


class TestGroundFacts:

    def test_grounded_fact_kept(self):
        """Number present in source → kept."""
        extracted = [{"i": 1, "f": [{"key": "students", "v": 150, "u": "count", "q": "150 students"}], "c": []}]
        source = [{"id": 1, "text": "We have 150 students", "raw": "We have 150 students"}]
        grounded, dropped = ground_facts(extracted, source)
        assert len(grounded[0]["f"]) == 1
        assert len(dropped) == 0

    def test_hallucinated_number_dropped(self):
        """Number NOT in source → dropped."""
        extracted = [{"i": 1, "f": [{"key": "students", "v": 999, "u": "count", "q": "999"}], "c": []}]
        source = [{"id": 1, "text": "We have 150 students", "raw": "We have 150 students"}]
        grounded, dropped = ground_facts(extracted, source)
        assert len(grounded[0]["f"]) == 0
        assert len(dropped) == 1
        assert dropped[0]["reason"] == "UNGROUNDED"
        assert dropped[0]["value"] == 999

    def test_number_in_wrong_message_dropped(self):
        """Number exists but in a different message → dropped from this one."""
        extracted = [
            {"i": 1, "f": [{"key": "budget_total", "v": 500000, "u": "PKR", "q": "500000"}], "c": []},
        ]
        source = [
            {"id": 1, "text": "Hello, we need to plan an event", "raw": "Hello, we need to plan an event"},
            {"id": 2, "text": "Budget is 500000", "raw": "Budget is 500000"},
        ]
        grounded, dropped = ground_facts(extracted, source)
        assert len(grounded[0]["f"]) == 0
        assert len(dropped) == 1

    def test_non_numeric_fact_always_kept(self):
        """Non-numeric facts (text, bool) are not checked."""
        extracted = [{"i": 1, "f": [{"key": "late_note", "v": "traffic jam", "u": "text", "q": "traffic jam"}], "c": []}]
        source = [{"id": 1, "text": "There is a traffic jam", "raw": "There is a traffic jam"}]
        grounded, dropped = ground_facts(extracted, source)
        assert len(grounded[0]["f"]) == 1
        assert len(dropped) == 0

    def test_lakh_format_grounded(self):
        """6,50,000 in source matches 650000 extracted."""
        extracted = [{"i": 1, "f": [{"key": "budget_total", "v": 650000, "u": "PKR", "q": "6,50,000"}], "c": []}]
        source = [{"id": 1, "text": "Budget is Rs 6,50,000", "raw": "Budget is Rs 6,50,000"}]
        grounded, dropped = ground_facts(extracted, source)
        assert len(grounded[0]["f"]) == 1
        assert len(dropped) == 0

    def test_k_format_grounded(self):
        """650k in source matches 650000 extracted."""
        extracted = [{"i": 1, "f": [{"key": "budget_total", "v": 650000, "u": "PKR", "q": "650k"}], "c": []}]
        source = [{"id": 1, "text": "Budget 650k", "raw": "Budget 650k"}]
        grounded, dropped = ground_facts(extracted, source)
        assert len(grounded[0]["f"]) == 1
        assert len(dropped) == 0

    def test_constraints_passed_through(self):
        """Constraints are not affected by grounding."""
        extracted = [{"i": 1, "f": [], "c": [{"a": "venue", "s": "generator", "op": "require", "v": True, "hard": True, "q": "generator needed"}]}]
        source = [{"id": 1, "text": "generator needed", "raw": "generator needed"}]
        grounded, dropped = ground_facts(extracted, source)
        assert len(grounded[0]["c"]) == 1

    def test_multiple_facts_mixed(self):
        """Some facts grounded, some not."""
        extracted = [{"i": 1, "f": [
            {"key": "students", "v": 150, "u": "count", "q": "150"},
            {"key": "budget_total", "v": 999999, "u": "PKR", "q": "999999"},
        ], "c": []}]
        source = [{"id": 1, "text": "150 students attending", "raw": "150 students attending"}]
        grounded, dropped = ground_facts(extracted, source)
        assert len(grounded[0]["f"]) == 1  # only 150 kept
        assert grounded[0]["f"][0]["v"] == 150
        assert len(dropped) == 1  # 999999 dropped

    def test_boolean_fact_not_dropped(self):
        """Boolean facts must not be treated as integer 1/0."""
        extracted = [{"i": 1, "f": [{"key": "venue_option", "v": True, "u": "bool", "q": "has generator", "ref": "Hall A"}], "c": []}]
        source = [{"id": 1, "text": "Hall A has generator backup", "raw": "Hall A has generator backup"}]
        grounded, dropped = ground_facts(extracted, source)
        assert len(grounded[0]["f"]) == 1
        assert len(dropped) == 0

    def test_hours_to_minutes_grounded(self):
        """'4 hours' in source grounds duration_min=240."""
        extracted = [{"i": 1, "f": [{"key": "duration_min", "v": 240, "u": "min", "q": "4 hours"}], "c": []}]
        source = [{"id": 1, "text": "The event lasts 4 hours.", "raw": "The event lasts 4 hours."}]
        grounded, dropped = ground_facts(extracted, source)
        assert len(grounded[0]["f"]) == 1
        assert len(dropped) == 0

    def test_urdu_script_and_digits_grounded(self):
        """Urdu-Indic digits and Urdu number words are grounded."""
        extracted = [{"i": 1, "f": [
            {"key": "students", "v": 150, "u": "count", "q": "۱۵۰"},
            {"key": "committed_cost", "v": 5000, "u": "PKR", "q": "پانچ ہزار"},
        ], "c": []}]
        source = [{"id": 1, "text": "۱۵۰ طلباء اور پانچ ہزار روپے", "raw": "۱۵۰ طلباء اور پانچ ہزار روپے"}]
        grounded, dropped = ground_facts(extracted, source)
        assert len(grounded[0]["f"]) == 2
        assert len(dropped) == 0

    def test_free_delivery_grounds_zero(self):
        """'Delivery free hai' grounds delivery_fee=0."""
        extracted = [{"i": 1, "f": [{"key": "food_option.delivery_fee", "v": 0, "u": "PKR", "q": "Delivery free hai", "ref": "Standard"}], "c": []}]
        source = [{"id": 1, "text": "Delivery free hai.", "raw": "Delivery free hai."}]
        grounded, dropped = ground_facts(extracted, source)
        assert len(grounded[0]["f"]) == 1
        assert len(dropped) == 0

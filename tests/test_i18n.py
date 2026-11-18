"""Tests for UI, i18n, offline HTML report, and Pakistan formatting features (M6 + M7)."""

from __future__ import annotations

import json
import pathlib
import re

from core.planner import build_plan
from core.report import format_rupees, load_i18n, render_html
from core.trace import TraceCollector
from core.validate import validate


class TestI18nCatalogue:

    def test_en_and_ur_have_identical_keys(self):
        en = load_i18n("en")
        ur = load_i18n("ur")
        assert set(en.keys()) == set(ur.keys())
        for k, v in en.items():
            assert isinstance(v, str) and v.strip(), f"Empty en key: {k}"
        for k, v in ur.items():
            assert isinstance(v, str) and v.strip(), f"Empty ur key: {k}"

    def test_ur_contains_urdu_script(self):
        ur = load_i18n("ur")
        # Core navigation labels must be in Urdu script
        for key in ("plan", "venue", "schedule", "food", "judging", "budget", "rejected"):
            assert any("\u0600" <= ch <= "\u06FF" for ch in ur[key]), f"{key} not in Urdu script"


class TestFormatters:

    def test_international_grouping(self):
        assert format_rupees(650000, "international") == "Rs 650,000"
        assert format_rupees(1200, "international") == "Rs 1,200"

    def test_lakh_grouping(self):
        assert format_rupees(650000, "lakh") == "Rs 6,50,000 (6.5 lakh)"
        assert format_rupees(120000, "lakh") == "Rs 1,20,000 (1.2 lakh)"
        assert format_rupees(5000, "lakh") == "Rs 5,000"


class TestOfflineHtmlReport:

    def _sample_state_and_trace(self):
        facts = {
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
            "wishlist": {"DJ": {"label": "DJ", "cost": 25000, "source_id": 6, "quote": "DJ 25000"}},
        }
        plan = build_plan(facts, [])
        checks = validate(plan, facts, [])
        state = {
            "pack_id": "abc123",
            "messages": [
                {"id": 1, "hash": "h1", "sender": "Dean", "role": "authority", "date": "2024-03-01", "text": "150 students", "status": "accepted", "reason_code": "", "reason_en": "", "reason_ur": ""},
                {
                    "id": 7, "hash": "h7", "sender": "Caterer", "role": "caterer", "date": "2024-03-06",
                    "text": "Order 150 boxes instead.", "status": "rejected",
                    "reason_code": "BREAKS_CHECK",
                    "reason_en": "REJECTED msg #7 (caterer): BREAKS_CHECK. Plan unchanged.",
                    "reason_ur": "مسترد پیغام #7 (کیٹرر): BREAKS_CHECK۔ منصوبہ برقرار ہے",
                },
            ],
            "plan": plan,
            "checks": checks,
        }
        trace = TraceCollector()
        trace.add_call({
            "n": 1, "model": "fake-small", "area": "reading",
            "input": "test prompt", "output": "{}",
            "prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150,
            "started_at": 1.0, "seconds": 0.2,
        })
        trace.add_event("check", "figures ok | budget ok")
        return state, trace

    def test_report_is_fully_offline_no_external_urls(self):
        state, trace = self._sample_state_and_trace()
        html = render_html(state, trace)
        # Must NOT contain http:// or https:// links (no CDN, no external fonts)
        assert "http://" not in html
        assert "https://" not in html

    def test_report_contains_plan_trace_and_rejected_bilingual(self):
        state, trace = self._sample_state_and_trace()
        html = render_html(state, trace)
        assert "Main Hall" in html
        assert "Standard" in html
        assert "call 1" in html
        assert "150" in html
        assert "REJECTED msg #7" in html
        assert "مسترد پیغام #7" in html
        assert "toggle-lakh" in html
        assert "btn-whatsapp" in html
        assert 'data-lang="ur"' in html
        assert 'dir="ltr"' in html
        # No emoji characters (design system anti-template rule 5)
        emoji_re = re.compile("[\U0001F300-\U0001FAFF]")
        assert not emoji_re.search(html)

    def test_empty_state_shows_no_messages_prompt(self):
        trace = TraceCollector()
        html = render_html({"messages": [], "plan": {}, "checks": {}}, trace)
        assert "No messages loaded" in html

"""Tests for core/update.py — dependency recompute, validator-gated commit, rejections."""

from __future__ import annotations

import json
import pathlib

from core.llm import LLMClient
from core.parse import compute_hash
from core.update import run_pipeline


def _make_msg(idx: int, sender: str, date: str | None, text: str) -> dict:
    return {
        "id": idx,
        "hash": compute_hash(f"{sender}:{date}:{text}"),
        "sender": sender,
        "date": date,
        "text": text,
        "raw": text,
    }


def _baseline_pack_and_extraction():
    messages = [
        _make_msg(1, "Dean Office", "2024-03-01", "150 students, team size 3, 10 staff, 4 hours, prayer break 20 min."),
        _make_msg(2, "Finance", "2024-03-01", "Budget is Rs 6,50,000. Printing 15000, honorarium 3000."),
        _make_msg(3, "Judging Lead", "2024-03-01", "20 judges confirmed, 10 min per team, max 3 teams per judge."),
        _make_msg(4, "Venue Admin", "2024-03-01", "Main Hall capacity 200 price 120000 no generator. Auditorium capacity 250 price 180000 has generator."),
        _make_msg(5, "Caterer", "2024-03-02", "Standard box Rs 900 per head plus 5000 delivery."),
        _make_msg(6, "Student Rep", "2024-03-02", "Can we also get a DJ for 25000?"),
    ]
    extraction = {
        "m": [
            {
                "i": 1, "r": "authority", "d": "2024-03-01", "k": "fact",
                "f": [
                    {"key": "students", "v": 150, "u": "count", "q": "150 students"},
                    {"key": "team_size", "v": 3, "u": "count", "q": "team size 3"},
                    {"key": "staff", "v": 10, "u": "count", "q": "10 staff"},
                    {"key": "duration_min", "v": 240, "u": "min", "q": "4 hours"},
                    {"key": "prayer_break_min", "v": 20, "u": "min", "q": "prayer break 20 min"},
                ],
                "c": [],
            },
            {
                "i": 2, "r": "finance", "d": "2024-03-01", "k": "fact",
                "f": [
                    {"key": "budget_total", "v": 650000, "u": "PKR", "q": "Rs 6,50,000"},
                    {"key": "committed_cost", "v": 15000, "u": "PKR", "q": "Printing 15000", "ref": "printing"},
                    {"key": "honorarium", "v": 3000, "u": "PKR", "q": "honorarium 3000"},
                ],
                "c": [],
            },
            {
                "i": 3, "r": "judging", "d": "2024-03-01", "k": "fact",
                "f": [
                    {"key": "judges_confirmed", "v": 20, "u": "count", "q": "20 judges confirmed"},
                    {"key": "judge_min_per_team", "v": 10, "u": "min", "q": "10 min per team"},
                    {"key": "judge_max_teams", "v": 3, "u": "count", "q": "max 3 teams per judge"},
                ],
                "c": [],
            },
            {
                "i": 4, "r": "venue", "d": "2024-03-01", "k": "fact",
                "f": [
                    {"key": "venue_option.capacity", "v": 200, "u": "count", "q": "capacity 200", "ref": "Main Hall"},
                    {"key": "venue_option.price", "v": 120000, "u": "PKR", "q": "price 120000", "ref": "Main Hall"},
                    {"key": "venue_option.generator", "v": False, "u": "bool", "q": "no generator", "ref": "Main Hall"},
                    {"key": "venue_option.capacity", "v": 250, "u": "count", "q": "capacity 250", "ref": "Auditorium"},
                    {"key": "venue_option.price", "v": 180000, "u": "PKR", "q": "price 180000", "ref": "Auditorium"},
                    {"key": "venue_option.generator", "v": True, "u": "bool", "q": "has generator", "ref": "Auditorium"},
                ],
                "c": [],
            },
            {
                "i": 5, "r": "caterer", "d": "2024-03-02", "k": "fact",
                "f": [
                    {"key": "food_option.price_per_head", "v": 900, "u": "PKR", "q": "Rs 900", "ref": "Standard"},
                    {"key": "food_option.delivery_fee", "v": 5000, "u": "PKR", "q": "5000 delivery", "ref": "Standard"},
                ],
                "c": [],
            },
            {
                "i": 6, "r": "requester", "d": "2024-03-02", "k": "request",
                "f": [{"key": "wishlist_item", "v": 25000, "u": "PKR", "q": "DJ for 25000", "ref": "DJ"}],
                "c": [],
            },
        ]
    }
    return messages, extraction


def _fake_client(response_dict: dict, initial_counter: int = 0) -> LLMClient:
    def adapter(area: str, system: str, user: str) -> dict:
        return {
            "text": json.dumps(response_dict),
            "usage": {"prompt_tokens": 300, "completion_tokens": 120, "total_tokens": 420},
        }
    return LLMClient(model_name="fake-small-model", adapter=adapter, initial_call_counter=initial_counter)


class TestUpdateEngine:

    def test_fresh_then_cost_change_recomputes_budget_only(self, tmp_path: pathlib.Path):
        """Practice change: printing cost updated -> recomputes ONLY budget, 1 model call."""
        state_path = tmp_path / "state.json"
        messages, extraction = _baseline_pack_and_extraction()

        r1 = run_pipeline(messages, state_path, client=_fake_client(extraction))
        assert r1["mode"] == "fresh"
        assert r1["committed"] is True
        assert r1["state"]["plan"]["venue"]["selected"] == "Main Hall"
        old_spent = r1["state"]["plan"]["budget"]["spent"]
        assert r1["state"]["call_counter"] == 1

        # Practice change: printing cost increases from 15000 to 22000 (+7000)
        follow_up = [_make_msg(1, "Finance", "2024-03-05", "Printing invoice updated to Rs 22,000.")]
        follow_ext = {
            "m": [{
                "i": 1, "r": "finance", "d": "2024-03-05", "k": "fact",
                "f": [{"key": "committed_cost", "v": 22000, "u": "PKR", "q": "Rs 22,000", "ref": "printing"}],
                "c": [],
            }]
        }
        r2 = run_pipeline(follow_up, state_path, client=_fake_client(follow_ext))
        assert r2["mode"] == "update"
        assert r2["committed"] is True
        assert r2["recomputed"] == ["budget"]
        assert "venue" in r2["unchanged"]
        assert "food" in r2["unchanged"]
        assert "schedule" in r2["unchanged"]
        assert "judging" in r2["unchanged"]
        assert r2["state"]["plan"]["budget"]["spent"] == old_spent + 7000
        assert r2["state"]["call_counter"] == 2
        assert len(r2["state"]["trace_calls"]) == 2

    def test_practice_wrong_message_rejected_breaks_check(self, tmp_path: pathlib.Path):
        """Practice wrong message: order quantity below headcount -> BREAKS_CHECK, plan unchanged."""
        state_path = tmp_path / "state.json"
        messages, extraction = _baseline_pack_and_extraction()
        r1 = run_pipeline(messages, state_path, client=_fake_client(extraction))
        old_plan = r1["state"]["plan"]

        # Wrong message: caterer suggests rounding down to 150 boxes (headcount is 177!)
        wrong_msg = [_make_msg(1, "Caterer", "2024-03-06", "Let's round down the lunch order to 150 boxes.")]
        wrong_ext = {
            "m": [{
                "i": 1, "r": "caterer", "d": "2024-03-06", "k": "fact",
                "f": [{"key": "food_quantity", "v": 150, "u": "count", "q": "150 boxes"}],
                "c": [],
            }]
        }
        r2 = run_pipeline(wrong_msg, state_path, client=_fake_client(wrong_ext))
        assert r2["mode"] == "update"
        assert r2["committed"] is False
        assert r2["state"]["plan"] == old_plan  # Plan UNCHANGED!
        rejected_msgs = [m for m in r2["state"]["messages"] if m["status"] == "rejected"]
        assert len(rejected_msgs) == 1
        assert rejected_msgs[0]["reason_code"] == "BREAKS_CHECK"
        assert "msg #7" in rejected_msgs[0]["reason_en"]
        assert "مسترد پیغام #7" in rejected_msgs[0]["reason_ur"]
        assert r2["state"]["call_counter"] == 2

    def test_generator_constraint_update_recomputes_venue_and_budget(self, tmp_path: pathlib.Path):
        """New hard generator constraint switches venue -> Auditorium and updates budget."""
        state_path = tmp_path / "state.json"
        messages, extraction = _baseline_pack_and_extraction()
        run_pipeline(messages, state_path, client=_fake_client(extraction))

        outage_msg = [_make_msg(1, "Dean Office", "2024-03-06", "IESCO load shedding scheduled; venue must have a generator.")]
        outage_ext = {
            "m": [{
                "i": 1, "r": "authority", "d": "2024-03-06", "k": "fact",
                "f": [],
                "c": [{"a": "venue", "s": "venue.generator", "op": "require", "v": True, "hard": True, "q": "must have a generator"}],
            }]
        }
        r2 = run_pipeline(outage_msg, state_path, client=_fake_client(outage_ext))
        assert r2["committed"] is True
        assert r2["recomputed"] == ["venue", "budget"]
        assert r2["state"]["plan"]["venue"]["selected"] == "Auditorium"

    def test_fresh_pack_after_old_state_archives_and_starts_fresh(self, tmp_path: pathlib.Path):
        """Unrelated 6-message pack after existing state starts fresh and archives old state."""
        state_path = tmp_path / "state.json"
        messages, extraction = _baseline_pack_and_extraction()
        run_pipeline(messages, state_path, client=_fake_client(extraction))

        # Brand new pack (different text -> 0 hash overlap, >= 4 messages)
        new_msgs = [_make_msg(i, m["sender"], m["date"], m["text"] + " [pack2]") for i, m in enumerate(messages, start=1)]
        r2 = run_pipeline(new_msgs, state_path, client=_fake_client(extraction))
        assert r2["mode"] == "fresh"
        assert r2["state"]["call_counter"] == 1  # reset for new pack
        archive_files = list((tmp_path / "archive").glob("state_*.json"))
        assert len(archive_files) == 1

    def test_same_file_twice_makes_zero_model_calls(self, tmp_path: pathlib.Path):
        state_path = tmp_path / "state.json"
        messages, extraction = _baseline_pack_and_extraction()
        run_pipeline(messages, state_path, client=_fake_client(extraction))

        second_client = _fake_client(extraction)
        r2 = run_pipeline(messages, state_path, client=second_client)
        assert r2["mode"] == "update"
        assert second_client.call_counter == 0

"""Tests for mode detection (fresh vs update) in core/update.py."""

from __future__ import annotations

from core.parse import compute_hash
from core.update import detect_mode


def _msg(idx: int, text: str) -> dict:
    return {"id": idx, "hash": compute_hash(text), "sender": "S", "date": None, "text": text, "raw": text}


class TestModeDetection:

    def test_no_state_is_fresh(self):
        msgs = [_msg(1, "hello"), _msg(2, "world")]
        mode, reason, to_proc = detect_mode(msgs, None)
        assert mode == "fresh"
        assert len(to_proc) == 2

    def test_same_file_again_is_update_with_zero_new(self):
        msgs = [_msg(1, "m1"), _msg(2, "m2"), _msg(3, "m3")]
        state = {"messages": msgs}
        mode, reason, to_proc = detect_mode(msgs, state)
        assert mode == "update"
        assert to_proc == []

    def test_cumulative_file_is_update_unseen_only(self):
        m1, m2, m3 = _msg(1, "m1"), _msg(2, "m2"), _msg(3, "m3")
        state = {"messages": [m1, m2]}
        mode, reason, to_proc = detect_mode([m1, m2, m3], state)
        assert mode == "update"
        assert len(to_proc) == 1
        assert to_proc[0]["text"] == "m3"

    def test_one_message_file_no_overlap_is_update(self):
        state = {"messages": [_msg(1, "old1"), _msg(2, "old2")]}
        mode, reason, to_proc = detect_mode([_msg(1, "new follow-up")], state)
        assert mode == "update"
        assert len(to_proc) == 1

    def test_three_message_file_no_overlap_is_update(self):
        state = {"messages": [_msg(1, "old1")]}
        incoming = [_msg(i, f"new{i}") for i in range(1, 4)]
        mode, reason, to_proc = detect_mode(incoming, state, fresh_threshold=4)
        assert mode == "update"
        assert len(to_proc) == 3

    def test_unrelated_pack_of_ten_after_old_state_is_fresh(self):
        state = {"messages": [_msg(i, f"old_pack_{i}") for i in range(1, 11)]}
        incoming = [_msg(i, f"new_pack_{i}") for i in range(1, 11)]
        mode, reason, to_proc = detect_mode(incoming, state, fresh_threshold=4)
        assert mode == "fresh"
        assert len(to_proc) == 10

"""Tests for core/parse.py — message file parsing."""

from __future__ import annotations

import os
import tempfile

from core.parse import parse_messages, compute_hash


def _write_temp(content: str) -> str:
    """Write content to a temp file and return its path."""
    fd, path = tempfile.mkstemp(suffix=".txt")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)
    return path


class TestParseMessages:

    def test_numbered_format(self):
        content = (
            "1. Alice - 2024-01-15\n"
            "Hello, the budget is set.\n\n"
            "2. Bob - 2024-01-16\n"
            "The venue is booked.\n"
        )
        path = _write_temp(content)
        try:
            msgs = parse_messages(path)
            assert len(msgs) == 2
            assert msgs[0]["id"] == 1
            assert msgs[1]["id"] == 2
            assert msgs[0]["sender"] == "Alice"
            assert msgs[0]["date"] == "2024-01-15"
            assert msgs[1]["sender"] == "Bob"
        finally:
            os.unlink(path)

    def test_blank_line_separated(self):
        content = (
            "First message here.\n"
            "It has two lines.\n"
            "\n"
            "Second message here.\n"
        )
        path = _write_temp(content)
        try:
            msgs = parse_messages(path)
            assert len(msgs) == 2
        finally:
            os.unlink(path)

    def test_hash_is_deterministic(self):
        content = "1. Test\nSome text\n"
        path = _write_temp(content)
        try:
            msgs1 = parse_messages(path)
            msgs2 = parse_messages(path)
            assert msgs1[0]["hash"] == msgs2[0]["hash"]
        finally:
            os.unlink(path)

    def test_hash_changes_with_content(self):
        path1 = _write_temp("1. Test\nContent A\n")
        path2 = _write_temp("1. Test\nContent B\n")
        try:
            msgs1 = parse_messages(path1)
            msgs2 = parse_messages(path2)
            assert msgs1[0]["hash"] != msgs2[0]["hash"]
        finally:
            os.unlink(path1)
            os.unlink(path2)

    def test_sender_date_extraction(self):
        content = "1. Dr. Ahmed Khan - 2024-03-20\nImportant update.\n"
        path = _write_temp(content)
        try:
            msgs = parse_messages(path)
            assert msgs[0]["sender"] == "Dr. Ahmed Khan"
            assert msgs[0]["date"] == "2024-03-20"
        finally:
            os.unlink(path)

    def test_message_without_date(self):
        content = "1. Anonymous\nJust some text.\n"
        path = _write_temp(content)
        try:
            msgs = parse_messages(path)
            assert len(msgs) == 1
            # Date may be None
        finally:
            os.unlink(path)

    def test_empty_file(self):
        path = _write_temp("")
        try:
            msgs = parse_messages(path)
            assert len(msgs) == 0
        finally:
            os.unlink(path)

    def test_sequential_ids(self):
        content = "1. A\nText1\n\n2. B\nText2\n\n3. C\nText3\n"
        path = _write_temp(content)
        try:
            msgs = parse_messages(path)
            ids = [m["id"] for m in msgs]
            assert ids == [1, 2, 3]
        finally:
            os.unlink(path)


class TestComputeHash:

    def test_same_input_same_hash(self):
        assert compute_hash("hello") == compute_hash("hello")

    def test_different_input_different_hash(self):
        assert compute_hash("hello") != compute_hash("world")

    def test_whitespace_stripped(self):
        assert compute_hash("  hello  ") == compute_hash("hello")

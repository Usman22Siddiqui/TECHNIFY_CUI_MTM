"""Parse a messages file into structured message records.

Without it: cannot tell new messages from old; no update mode.

Handles three formats:
- Numbered rows: "1. sender - date\ntext"
- Blank-line separated blocks
- Plain lines with header pattern
"""

from __future__ import annotations

import hashlib
import re
from typing import Any


def parse_messages(file_path: str) -> list[dict[str, Any]]:
    """Parse a messages file into message records.

    Each message gets:
        id: sequential integer (1-based)
        hash: sha256 of the raw text (for update detection)
        sender: extracted from header line if present
        date: extracted from header line if present (YYYY-MM-DD)
        text: the full message body
        raw: the original block as-is

    Returns:
        List of message dicts.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    blocks = _split_into_blocks(content)
    messages = []

    for idx, block in enumerate(blocks, start=1):
        raw = block.strip()
        if not raw:
            continue

        sender, date, body = _parse_header(raw)
        msg_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()

        messages.append({
            "id": idx,
            "hash": msg_hash,
            "sender": sender,
            "date": date,
            "text": body,
            "raw": raw,
        })

    return messages


def _split_into_blocks(content: str) -> list[str]:
    """Split content into message blocks.

    Strategy:
    1. Try numbered format: "1. ...", "2. ...", etc.
    2. Try separator lines (----, ====, ****).
    3. Fall back to blank-line separation.
    """
    # Strip PDF/table boilerplate lines if present
    cleaned_lines = [
        ln for ln in content.splitlines()
        if not re.match(r"^\s*Page\s+\d+\s+of\s+\d+\s*$", ln, re.IGNORECASE)
        and not re.match(r"^\s*#\s+From\s+Date\s+Message\s*$", ln, re.IGNORECASE)
    ]
    content = "\n".join(cleaned_lines)

    # Try numbered format: lines starting with "digit." or "digit)"
    numbered_pattern = re.compile(r"^(\d+)[.)]\s", re.MULTILINE)
    matches = list(numbered_pattern.finditer(content))

    if len(matches) >= 2:
        blocks = []
        for i, match in enumerate(matches):
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            blocks.append(content[start:end])
        return blocks

    # Try space-numbered table rows starting with sequential integers ("1 ...", "2 ...")
    space_num_pattern = re.compile(r"^(\d+)\s+(?=[A-Za-z\u0600-\u06FF])", re.MULTILINE)
    space_matches = list(space_num_pattern.finditer(content))
    if len(space_matches) >= 2 and [int(m.group(1)) for m in space_matches[:2]] == [1, 2]:
        blocks = []
        for i, match in enumerate(space_matches):
            start = match.start()
            end = space_matches[i + 1].start() if i + 1 < len(space_matches) else len(content)
            blocks.append(content[start:end])
        return blocks

    # Try separator lines
    separator_pattern = re.compile(r"^[-=*]{3,}\s*$", re.MULTILINE)
    parts = separator_pattern.split(content)
    if len(parts) >= 2:
        return [p for p in parts if p.strip()]

    # Fall back to blank-line separation (two or more newlines)
    blocks = re.split(r"\n\s*\n", content)
    return [b for b in blocks if b.strip()]


def _parse_header(raw: str) -> tuple[str, str | None, str]:
    """Extract sender, date and body from a message block.

    Returns:
        (sender, date_str_or_None, body_text)
    """
    lines = raw.split("\n")
    first_line = lines[0].strip()

    # Remove leading number: "1. " or "1) "
    first_line = re.sub(r"^\d+[.)]\s*", "", first_line)

    # Try to extract sender and date from first line
    # Patterns: "Sender Name - 2024-01-15" or "Sender (date)" or "From: Sender"
    sender = ""
    date = None
    body_start = 0

    # Pattern: "Sender - YYYY-MM-DD" or "Sender – YYYY-MM-DD"
    date_pattern = re.compile(
        r"^(.+?)\s*[-–—]\s*(\d{4}-\d{2}-\d{2})\s*$"
    )
    match = date_pattern.match(first_line)
    if match:
        sender = match.group(1).strip()
        date = match.group(2)
        body_start = 1
    else:
        # Pattern: "From: Sender" or "Sender:"
        from_pattern = re.compile(r"^(?:From:\s*)?(.+?)(?:\s*[-–—:]\s*(.+))?$")
        match = from_pattern.match(first_line)
        if match and len(lines) > 1:
            potential_sender = match.group(1).strip()
            rest = match.group(2) or ""
            # Check if rest looks like a date
            date_in_rest = re.search(r"\d{4}-\d{2}-\d{2}", rest)
            if date_in_rest:
                sender = potential_sender
                date = date_in_rest.group(0)
                body_start = 1
            elif len(potential_sender) < 60 and not any(
                c in potential_sender for c in ".!?"
            ):
                # Short first line without sentence punctuation = likely a header
                sender = potential_sender
                body_start = 1

    body = "\n".join(lines[body_start:]).strip()
    if not body:
        body = "\n".join(lines).strip()
        sender = ""

    return sender, date, body


def compute_hash(text: str) -> str:
    """Compute SHA-256 hash of message text for update detection."""
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()

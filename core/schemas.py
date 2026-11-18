"""Pydantic models for extraction output and internal state.

Shapes only — no pack facts. Keys from EXTRACTION_SPEC.md.
"""

from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


# --- Extraction output schema (compact keys save tokens) ---

class ExtractedFact(BaseModel):
    """A single fact extracted from a message."""
    key: str                        # canonical key from closed vocabulary
    v: Any                          # value (int, float, str, bool)
    u: str = "text"                 # unit: PKR, min, count, bool, text
    q: str = ""                     # verbatim quote from the message
    ref: str = ""                   # optional item label (e.g. venue name, food tier)


class ExtractedConstraint(BaseModel):
    """A constraint extracted from a message."""
    a: str                          # area: venue, schedule, food, judging, budget
    s: str                          # subject (open set)
    op: str                         # operator: min, max, eq, require, forbid, window
    v: Any = None                   # value
    hard: bool = True               # hard constraint vs soft preference
    q: str = ""                     # verbatim quote


class ExtractedMessage(BaseModel):
    """Extraction result for one message."""
    i: int                          # message id
    r: str = "unknown"              # role: authority|finance|venue|caterer|judging|requester|participant|unknown
    d: Optional[str] = None         # date YYYY-MM-DD or null
    k: str = "fact"                 # kind: fact|request|notice|noise
    f: list[ExtractedFact] = Field(default_factory=list)   # facts
    c: list[ExtractedConstraint] = Field(default_factory=list)  # constraints


class ExtractionResult(BaseModel):
    """Full extraction output from the model."""
    m: list[ExtractedMessage]       # one entry per message


# --- Internal state models ---

class FactRecord(BaseModel):
    """A resolved fact in the state."""
    key: str
    value: Any
    unit: str = "text"
    source_ids: list[int] = Field(default_factory=list)
    quote: str = ""
    ref: str = ""
    status: str = "active"          # active | superseded | ungrounded | rejected


class ConstraintRecord(BaseModel):
    """A resolved constraint in the state."""
    area: str
    subject: str
    op: str
    value: Any = None
    hard: bool = True
    source_id: int = 0


class MessageRecord(BaseModel):
    """A message in the state."""
    id: int
    hash: str
    sender: str = ""
    role: str = "unknown"
    date: Optional[str] = None
    text: str = ""
    status: str = "accepted"        # accepted | rejected | ignored | superseded
    reason_code: str = ""
    reason_en: str = ""
    reason_ur: str = ""

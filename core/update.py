"""Apply new messages to a copy of state, recompute only affected areas.

Without it: full re-run on every change — slower, more tokens.
"""

from __future__ import annotations

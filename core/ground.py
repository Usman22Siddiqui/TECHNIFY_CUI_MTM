"""Reject extracted values not present in the source text.

Without it: a hallucinated number silently corrupts the plan.
"""

from __future__ import annotations

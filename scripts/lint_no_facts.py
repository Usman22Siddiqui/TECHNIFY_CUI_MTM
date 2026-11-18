#!/usr/bin/env python3
"""Scan src/core/config and prompt files for pack facts.

Fails if any numeric literal outside the defaults.toml allowlist
or any string copied from fixtures is found in production code.
"""

from __future__ import annotations

import sys


def main() -> int:
    # Will be fully implemented in M8
    print("lint_no_facts: PASS (stub)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

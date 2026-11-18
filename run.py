"""Mind to Machine — Event Planning Agent.

Single entry point. No flags. Fresh vs update decided from
the incoming file and state/state.json.

Usage:
    python run.py <messages_file>
"""

from __future__ import annotations

import sys
import time
import pathlib


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python run.py <messages_file>")
        sys.exit(1)

    messages_file = pathlib.Path(sys.argv[1])
    if not messages_file.exists():
        print(f"File not found: {messages_file}")
        sys.exit(1)

    start = time.perf_counter()

    # --- Pipeline (wired in M5) ---
    # 1. parse messages
    # 2. detect mode (fresh / update)
    # 3. extract (one model call, area=reading)
    # 4. ground (reject ungrounded numbers)
    # 5. resolve (supersession + authority)
    # 6. plan (judging → headcount → venue, food → schedule → budget)
    # 7. validate (six checks)
    # 8. commit or reject
    # 9. write outputs

    elapsed = time.perf_counter() - start
    print(f"[timing] run {elapsed:.1f} s")


if __name__ == "__main__":
    main()

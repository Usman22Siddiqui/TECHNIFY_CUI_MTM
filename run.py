"""Mind to Machine — Event Planning Agent.

Single entry point. No flags. Fresh vs update decided from
the incoming file and state/state.json.

Usage:
    python run.py <messages_file>
"""

from __future__ import annotations

import json
import pathlib
import sys

from core.parse import parse_messages
from core.update import run_pipeline


ROOT_DIR = pathlib.Path(__file__).resolve().parent
STATE_PATH = ROOT_DIR / "state" / "state.json"
OUT_DIR = ROOT_DIR / "out"


def write_outputs(result: dict, out_dir: pathlib.Path = OUT_DIR) -> None:
    """Write out/plan.json, out/trace.txt, out/trace.json, and out/report.html."""
    out_dir.mkdir(parents=True, exist_ok=True)
    state = result["state"]
    trace = result["trace"]

    plan_payload = {
        "pack_id": state.get("pack_id"),
        "plan": state.get("plan"),
        "checks": state.get("checks"),
        "messages": state.get("messages"),
    }
    (out_dir / "plan.json").write_text(
        json.dumps(plan_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    trace.write_files(str(out_dir / "trace.txt"), str(out_dir / "trace.json"))

    # Render terminal summary and offline HTML report (if report module implemented)
    try:
        from core.report import render_report
        render_report(state, trace, out_dir)
    except ImportError:
        pass


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1].startswith("-"):
        print("Usage: python run.py <messages_file>")
        sys.exit(1)

    messages_file = pathlib.Path(sys.argv[1])
    if not messages_file.exists():
        print(f"File not found: {messages_file}")
        sys.exit(1)

    incoming = parse_messages(str(messages_file))
    result = run_pipeline(incoming, STATE_PATH)
    write_outputs(result, OUT_DIR)


if __name__ == "__main__":
    main()

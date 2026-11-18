#!/usr/bin/env python3
"""Dress rehearsal: fresh pack + follow-up runs, timed, trace verified.

Uses the real configured model if MODEL_NAME is set in .env (unless --offline is passed),
otherwise runs with a deterministic offline test adapter to verify the full end-to-end
pipeline and output artifacts.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.llm import LLMClient
from core.parse import parse_messages
from core.update import run_pipeline
from run import write_outputs
from scripts.check_trace import check_trace_file


def _offline_adapter(step_name: str):
    """Deterministic canned extraction responses for offline rehearsal of tests/fixtures."""
    canned = {
        "sample_pack": {
            "m": [
                {
                    "i": 1, "r": "authority", "d": "2024-03-01", "k": "fact",
                    "f": [
                        {"key": "duration_min", "v": 240, "u": "min", "q": "4-hour"},
                        {"key": "students", "v": 150, "u": "count", "q": "150 students"},
                        {"key": "team_size", "v": 3, "u": "count", "q": "teams of 3"},
                        {"key": "staff", "v": 10, "u": "count", "q": "10 staff"},
                        {"key": "prayer_break_min", "v": 20, "u": "min", "q": "20 minute prayer break"},
                    ],
                    "c": [],
                },
                {
                    "i": 2, "r": "finance", "d": "2024-03-01", "k": "fact",
                    "f": [
                        {"key": "budget_total", "v": 650000, "u": "PKR", "q": "Rs 6,50,000"},
                        {"key": "committed_cost", "v": 15000, "u": "PKR", "q": "printing Rs 15,000", "ref": "printing"},
                        {"key": "committed_cost", "v": 10000, "u": "PKR", "q": "banners Rs 10,000", "ref": "banners"},
                        {"key": "honorarium", "v": 3000, "u": "PKR", "q": "Rs 3,000"},
                    ],
                    "c": [],
                },
                {
                    "i": 3, "r": "judging", "d": "2024-03-01", "k": "fact",
                    "f": [
                        {"key": "judges_confirmed", "v": 20, "u": "count", "q": "20 judges confirmed"},
                        {"key": "judge_min_per_team", "v": 10, "u": "min", "q": "10 minutes"},
                        {"key": "judge_max_teams", "v": 3, "u": "count", "q": "at most 3 teams"},
                    ],
                    "c": [],
                },
                {
                    "i": 4, "r": "venue", "d": "2024-03-01", "k": "fact",
                    "f": [
                        {"key": "venue_option.capacity", "v": 120, "u": "count", "q": "seats 120", "ref": "Small Seminar Room"},
                        {"key": "venue_option.price", "v": 60000, "u": "PKR", "q": "Rs 60,000", "ref": "Small Seminar Room"},
                        {"key": "venue_option.generator", "v": True, "u": "bool", "q": "has generator", "ref": "Small Seminar Room"},
                        {"key": "venue_option.capacity", "v": 200, "u": "count", "q": "seats 200", "ref": "Main Hall"},
                        {"key": "venue_option.price", "v": 120000, "u": "PKR", "q": "Rs 1,20,000", "ref": "Main Hall"},
                        {"key": "venue_option.generator", "v": False, "u": "bool", "q": "no generator", "ref": "Main Hall"},
                        {"key": "venue_option.capacity", "v": 250, "u": "count", "q": "seats 250", "ref": "Grand Auditorium"},
                        {"key": "venue_option.price", "v": 180000, "u": "PKR", "q": "Rs 1,80,000", "ref": "Grand Auditorium"},
                        {"key": "venue_option.generator", "v": True, "u": "bool", "q": "has generator", "ref": "Grand Auditorium"},
                    ],
                    "c": [],
                },
                {
                    "i": 5, "r": "caterer", "d": "2024-03-01", "k": "fact",
                    "f": [
                        {"key": "food_option.price_per_head", "v": 800, "u": "PKR", "q": "Rs 800", "ref": "Standard"},
                        {"key": "food_option.delivery_fee", "v": 5000, "u": "PKR", "q": "paanch hazar", "ref": "Standard"},
                        {"key": "food_option.halal", "v": True, "u": "bool", "q": "All halal", "ref": "Standard"},
                    ],
                    "c": [{"a": "food", "s": "food.halal", "op": "require", "v": True, "hard": True, "q": "All halal"}],
                },
                {
                    "i": 6, "r": "caterer", "d": "2024-03-03", "k": "fact",
                    "f": [
                        {"key": "food_option.price_per_head", "v": 900, "u": "PKR", "q": "Rs 900/-", "ref": "Standard"},
                        {"key": "food_option.delivery_fee", "v": 5000, "u": "PKR", "q": "5,000 rupees", "ref": "Standard"},
                    ],
                    "c": [],
                },
                {
                    "i": 7, "r": "requester", "d": "2024-03-03", "k": "request",
                    "f": [{"key": "wishlist_item", "v": 25000, "u": "PKR", "q": "DJ setup for Rs 25,000", "ref": "DJ"}],
                    "c": [],
                },
                {"i": 8, "r": "participant", "d": "2024-03-03", "k": "noise", "f": [], "c": []},
                {"i": 9, "r": "finance", "d": "2024-03-02", "k": "notice", "f": [], "c": []},
                {"i": 10, "r": "participant", "d": "2024-03-03", "k": "noise", "f": [], "c": []},
            ]
        },
        "practice_change": {
            "m": [{
                "i": 1, "r": "finance", "d": "2024-03-05", "k": "fact",
                "f": [{"key": "committed_cost", "v": 22000, "u": "PKR", "q": "Rs 22,000", "ref": "printing"}],
                "c": [],
            }]
        },
        "practice_wrong": {
            "m": [{
                "i": 1, "r": "caterer", "d": "2024-03-06", "k": "fact",
                "f": [{"key": "food_quantity", "v": 150, "u": "count", "q": "150 boxes"}],
                "c": [],
            }]
        },
    }

    def adapter(area: str, system: str, user: str) -> dict:
        payload = json.dumps(canned[step_name])
        return {
            "text": payload,
            "usage": {"prompt_tokens": 420, "completion_tokens": 180, "total_tokens": 600},
        }

    return LLMClient(model_name="offline-rehearsal-adapter", adapter=adapter)


def main() -> int:
    load_dotenv()
    offline = ("--offline" in sys.argv) or not bool(os.getenv("MODEL_NAME", "").strip())
    mode_label = "OFFLINE ADAPTER" if offline else f"LIVE MODEL ({os.getenv('MODEL_NAME')})"
    print(f"=== Mind to Machine Dress Rehearsal [{mode_label}] ===")

    state_path = ROOT / "state" / "state.json"
    out_dir = ROOT / "out"
    if state_path.exists():
        state_path.unlink()

    fixtures_dir = ROOT / "tests" / "fixtures"
    steps = [
        ("sample_pack", fixtures_dir / "sample_pack.txt"),
        ("practice_change", fixtures_dir / "practice_change.txt"),
        ("practice_wrong", fixtures_dir / "practice_wrong.txt"),
    ]

    for name, fpath in steps:
        t0 = time.perf_counter()
        msgs = parse_messages(str(fpath))
        client = _offline_adapter(name) if offline else None
        res = run_pipeline(msgs, state_path, client=client)
        write_outputs(res, out_dir)
        dt = time.perf_counter() - t0
        print(
            f"[{name}] mode={res['mode']} committed={res['committed']} "
            f"recomputed={res['recomputed']} calls={res['state']['call_counter']} "
            f"tokens={res['trace'].total_tokens()} elapsed={dt:.2f}s"
        )

    # Verify golden on fresh run? Check final trace integrity
    trace_errors = check_trace_file(out_dir / "trace.json")
    if trace_errors:
        print("Rehearsal trace check FAILED:", trace_errors)
        return 1

    print("\nOutputs verified: out/plan.json, out/trace.txt, out/trace.json, out/report.html")
    git_res = subprocess.run(["git", "status", "--short"], cwd=str(ROOT), capture_output=True, text=True)
    print("git status:", git_res.stdout.strip() or "(clean)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

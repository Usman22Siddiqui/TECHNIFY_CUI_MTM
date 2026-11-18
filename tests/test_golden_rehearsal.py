"""End-to-end golden test against tests/fixtures/sample_pack.txt and tests/golden/sample_pack.json."""

from __future__ import annotations

import json
import pathlib

from core.parse import parse_messages
from core.update import run_pipeline
from run import write_outputs
from scripts.check_trace import check_trace_file
from scripts.lint_no_facts import main as lint_main
from scripts.rehearsal import _offline_adapter


ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_sample_pack_matches_golden_and_practice_updates(tmp_path: pathlib.Path):
    golden = json.loads((ROOT / "tests" / "golden" / "sample_pack.json").read_text(encoding="utf-8"))
    state_path = tmp_path / "state.json"
    out_dir = tmp_path / "out"

    # 1. Fresh run on sample_pack.txt
    msgs = parse_messages(str(ROOT / "tests" / "fixtures" / "sample_pack.txt"))
    res = run_pipeline(msgs, state_path, client=_offline_adapter("sample_pack"))
    write_outputs(res, out_dir)

    plan = res["state"]["plan"]
    assert res["mode"] == "fresh"
    assert res["committed"] is True
    assert plan["judging"]["teams"] == golden["teams"]
    assert plan["judging"]["judges_needed"] == golden["judges_needed"]
    assert plan["judging"]["judges_used"] == golden["judges_used"]
    assert plan["judging"]["reserves"] == golden["reserves"]
    assert plan["headcount"]["total"] == golden["headcount"]
    assert plan["venue"]["selected"] == golden["venue_selected"]
    assert plan["venue"]["cost"] == golden["venue_cost"]
    assert plan["food"]["quantity"] == golden["food_quantity"]
    assert plan["food"]["price_per_head"] == golden["food_price_per_head"]
    assert plan["food"]["delivery_fee"] == golden["food_delivery_fee"]
    assert plan["food"]["cost"] == golden["food_cost"]
    assert plan["judging"]["cost"] == golden["judge_cost"]
    assert plan["judging"]["worst_case_cost"] == golden["judge_cost_worst_case"]
    assert plan["budget"]["committed_total"] == golden["committed_total"]
    assert plan["budget"]["spent"] == golden["spent"]
    assert plan["budget"]["remaining"] == golden["remaining"]
    assert plan["budget"]["wishlist"][0]["status"] == golden["wishlist_dj_status"]

    # 2. Practice change (printing cost -> budget only)
    msgs2 = parse_messages(str(ROOT / "tests" / "fixtures" / "practice_change.txt"))
    res2 = run_pipeline(msgs2, state_path, client=_offline_adapter("practice_change"))
    write_outputs(res2, out_dir)
    assert res2["mode"] == "update"
    assert res2["committed"] is True
    assert res2["recomputed"] == ["budget"]
    assert res2["state"]["plan"]["budget"]["spent"] == golden["spent"] + 7000

    # 3. Practice wrong message (150 boxes < 177 headcount -> BREAKS_CHECK)
    msgs3 = parse_messages(str(ROOT / "tests" / "fixtures" / "practice_wrong.txt"))
    res3 = run_pipeline(msgs3, state_path, client=_offline_adapter("practice_wrong"))
    write_outputs(res3, out_dir)
    assert res3["mode"] == "update"
    assert res3["committed"] is False
    assert res3["state"]["plan"]["budget"]["spent"] == golden["spent"] + 7000

    # 4. Verify all four output files and trace integrity
    for fname in ("plan.json", "trace.txt", "trace.json", "report.html"):
        assert (out_dir / fname).exists()
    assert check_trace_file(out_dir / "trace.json") == []


def test_lint_no_facts_passes():
    assert lint_main() == 0

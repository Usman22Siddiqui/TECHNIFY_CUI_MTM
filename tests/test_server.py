"""Tests for server.py — live stdlib HTTP backend and interactive frontend."""

from __future__ import annotations

import pathlib
import threading

import httpx

from core.report import render_html
from core.trace import TraceCollector
from scripts.rehearsal import _offline_adapter
from server import create_server


def _start_test_server(tmp_path: pathlib.Path, adapter_sequence: list[str]):
    idx = [0]

    def factory():
        step = adapter_sequence[min(idx[0], len(adapter_sequence) - 1)]
        idx[0] += 1
        return _offline_adapter(step)

    srv = create_server(
        host="127.0.0.1",
        port=0,  # OS picks free port
        state_path=tmp_path / "state.json",
        out_dir=tmp_path / "out",
        client_factory=factory,
    )
    port = srv.server_address[1]
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    return srv, f"http://127.0.0.1:{port}"


def test_live_server_full_lifecycle(tmp_path: pathlib.Path):
    root = pathlib.Path(__file__).resolve().parent.parent
    sample_text = (root / "tests" / "fixtures" / "sample_pack.txt").read_text(encoding="utf-8")
    change_text = (root / "tests" / "fixtures" / "practice_change.txt").read_text(encoding="utf-8")
    wrong_text = (root / "tests" / "fixtures" / "practice_wrong.txt").read_text(encoding="utf-8")

    srv, base = _start_test_server(tmp_path, ["sample_pack", "practice_change", "practice_wrong"])
    try:
        # 1. Health check
        r = httpx.get(f"{base}/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}

        # 2. Landing page renders interactive composer
        r_home = httpx.get(f"{base}/")
        assert r_home.status_code == 200
        assert 'id="live-composer"' in r_home.text
        assert "http://" not in r_home.text
        assert "https://" not in r_home.text

        # 3. Empty run rejected with 400
        r_empty = httpx.post(f"{base}/api/run", json={"text": "   "})
        assert r_empty.status_code == 400

        # 4. Run fresh sample pack (persists to out/plan.txt)
        r1 = httpx.post(f"{base}/api/run", json={"text": sample_text})
        assert r1.status_code == 200
        b1 = r1.json()
        assert b1["mode"] == "fresh"
        assert b1["committed"] is True
        assert b1["plan"]["headcount"]["total"] == 177
        assert b1["plan"]["budget"]["spent"] == 360300
        assert (tmp_path / "out" / "plan.txt").exists()
        r_ptxt = httpx.get(f"{base}/api/plan.txt")
        assert r_ptxt.status_code == 200
        assert "150 students" in r_ptxt.text

        # 5. Run update (printing cost change -> budget only)
        r2 = httpx.post(f"{base}/api/run", json={"text": change_text})
        assert r2.status_code == 200
        b2 = r2.json()
        assert b2["mode"] == "update"
        assert b2["committed"] is True
        assert b2["recomputed"] == ["budget"]
        assert b2["plan"]["budget"]["spent"] == 367300

        # 6. Run wrong update -> rejected, plan unchanged
        r3 = httpx.post(f"{base}/api/run", json={"text": wrong_text})
        assert r3.status_code == 200
        b3 = r3.json()
        assert b3["committed"] is False
        assert b3["plan"]["budget"]["spent"] == 367300

        # 7. State & trace endpoints
        r_state = httpx.get(f"{base}/api/state")
        assert r_state.status_code == 200
        assert r_state.json()["has_state"] is True
        assert r_state.json()["calls"] == 3

        r_trace = httpx.get(f"{base}/api/trace.txt")
        assert r_trace.status_code == 200
        assert "=== CALL 1 ===" in r_trace.text
        assert "=== TOTAL TOKENS:" in r_trace.text

        # 8. Reset archives state and clears active state
        r_reset = httpx.post(f"{base}/api/reset")
        assert r_reset.status_code == 200
        assert httpx.get(f"{base}/api/state").json()["has_state"] is False
    finally:
        srv.shutdown()
        srv.server_close()


def test_offline_report_has_no_composer():
    """Default render_html (used by run.py) stays 100% offline with no composer."""
    html = render_html({"messages": [], "plan": {}, "checks": {}}, TraceCollector())
    assert 'id="live-composer"' not in html


def test_desktop_gui_submit_saves_plan_txt_and_schedules(tmp_path: pathlib.Path):
    """GUI submit helper writes out/plan.txt and runs full planning + scheduling."""
    from gui import submit_text_to_backend, format_plan_overview

    root = pathlib.Path(__file__).resolve().parent.parent
    sample_text = (root / "tests" / "fixtures" / "sample_pack.txt").read_text(encoding="utf-8")
    plan_txt = tmp_path / "out" / "plan.txt"
    state_path = tmp_path / "state" / "state.json"
    out_dir = tmp_path / "out"

    res = submit_text_to_backend(
        sample_text,
        plan_txt_path=plan_txt,
        state_path=state_path,
        out_dir=out_dir,
        client=_offline_adapter("sample_pack"),
    )
    assert plan_txt.exists()
    assert "150 students" in plan_txt.read_text(encoding="utf-8")
    assert res["committed"] is True
    assert res["state"]["plan"]["schedule"]["total_minutes"] == 240
    overview = format_plan_overview(res["state"])
    assert "SCHEDULE (240 min" in overview
    assert "[PASS] FIGURES" in overview

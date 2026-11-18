"""Tiny stdlib HTTP server for live interactive web access (P2 feature).

Zero external dependencies beyond stdlib + core/. Leaves `python run.py <file>`
and standalone offline `out/report.html` completely untouched.

Usage:
    python server.py
    # Opens on http://127.0.0.1:8080 (or $PORT when deployed on Render / HF Spaces)
"""

from __future__ import annotations

import json
import os
import pathlib
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

from core.llm import LLMClient
from core.parse import parse_messages
from core.report import render_html
from core.trace import TraceCollector
from core.update import archive_state, load_state, run_pipeline
from run import write_outputs


ROOT_DIR = pathlib.Path(__file__).resolve().parent
DEFAULT_STATE_PATH = ROOT_DIR / "state" / "state.json"
DEFAULT_OUT_DIR = ROOT_DIR / "out"

_MAX_BODY_BYTES = 1_048_576  # 1 MiB message upload limit


def _build_trace_from_state(state: dict[str, Any] | None) -> TraceCollector:
    tc = TraceCollector()
    if not state:
        return tc
    tc.add_calls(state.get("trace_calls", []))
    for ev in state.get("trace_events", []):
        tc.add_event(
            ev["type"],
            ev["text_en"],
            text_ur=ev.get("text_ur", ""),
            message_id=ev.get("message_id"),
            code=ev.get("code", ""),
        )
    return tc


def create_server(
    host: str = "0.0.0.0",
    port: int = 8080,
    state_path: pathlib.Path = DEFAULT_STATE_PATH,
    out_dir: pathlib.Path = DEFAULT_OUT_DIR,
    client_factory: Callable[[], LLMClient | None] | None = None,
) -> ThreadingHTTPServer:
    """Create a configured ThreadingHTTPServer (injectable for offline tests)."""
    pipeline_lock = threading.Lock()

    class MTMHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            # Quiet standard logs unless overridden
            pass

        def _send_bytes(self, status: int, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, status: int, payload: dict[str, Any]) -> None:
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._send_bytes(status, "application/json; charset=utf-8", raw)

        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]

            if path == "/health":
                self._send_json(HTTPStatus.OK, {"status": "ok"})
                return

            if path in ("/", "/index.html", "/report.html"):
                with pipeline_lock:
                    state = load_state(state_path) or {"messages": [], "plan": {}, "checks": {}}
                    trace = _build_trace_from_state(state)
                    html = render_html(state, trace, live_mode=True)
                self._send_bytes(HTTPStatus.OK, "text/html; charset=utf-8", html.encode("utf-8"))
                return

            if path == "/api/state":
                with pipeline_lock:
                    state = load_state(state_path)
                    trace = _build_trace_from_state(state)
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "has_state": state is not None,
                        "plan": (state or {}).get("plan", {}),
                        "checks": (state or {}).get("checks", {}),
                        "messages": (state or {}).get("messages", []),
                        "total_tokens": trace.total_tokens(),
                        "calls": len(trace._calls),
                    },
                )
                return

            if path == "/api/trace.txt":
                with pipeline_lock:
                    state = load_state(state_path)
                    trace = _build_trace_from_state(state)
                self._send_bytes(
                    HTTPStatus.OK,
                    "text/plain; charset=utf-8",
                    trace.to_text().encode("utf-8"),
                )
                return

            if path == "/api/plan.txt":
                plan_txt = out_dir / "plan.txt"
                content = plan_txt.read_text(encoding="utf-8") if plan_txt.exists() else ""
                self._send_bytes(
                    HTTPStatus.OK,
                    "text/plain; charset=utf-8",
                    content.encode("utf-8"),
                )
                return

            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

        def do_POST(self) -> None:
            path = self.path.split("?", 1)[0]

            if path == "/api/reset":
                with pipeline_lock:
                    if state_path.exists():
                        archive_state(state_path)
                        state_path.unlink()
                    plan_txt = out_dir / "plan.txt"
                    if plan_txt.exists():
                        plan_txt.unlink()
                self._send_json(HTTPStatus.OK, {"reset": True})
                return

            if path == "/api/run":
                length = int(self.headers.get("Content-Length", "0") or "0")
                if length <= 0 or length > _MAX_BODY_BYTES:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid request size"})
                    return

                raw_body = self.rfile.read(length)
                try:
                    data = json.loads(raw_body.decode("utf-8"))
                except Exception:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid JSON body"})
                    return

                text = str(data.get("text", "")).strip()
                if not text:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Message text is required"})
                    return

                with pipeline_lock:
                    try:
                        out_dir.mkdir(parents=True, exist_ok=True)
                        plan_txt_path = out_dir / "plan.txt"
                        plan_txt_path.write_text(text + "\n", encoding="utf-8")

                        incoming = parse_messages(str(plan_txt_path))
                        if not incoming:
                            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "No messages parsed"})
                            return

                        client = client_factory() if client_factory is not None else None
                        result = run_pipeline(incoming, state_path, client=client)
                        write_outputs(result, out_dir)
                    except Exception as exc:
                        self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
                        return

                self._send_json(
                    HTTPStatus.OK,
                    {
                        "mode": result["mode"],
                        "committed": result["committed"],
                        "recomputed": result["recomputed"],
                        "unchanged": result["unchanged"],
                        "elapsed": round(result["elapsed"], 2),
                        "total_tokens": result["trace"].total_tokens(),
                        "plan_txt_path": str(plan_txt_path),
                        "plan": result["state"].get("plan", {}),
                        "checks": result["state"].get("checks", {}),
                    },
                )
                return

            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    return ThreadingHTTPServer((host, port), MTMHandler)


def main() -> None:
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))
    server = create_server(host=host, port=port)
    print(f"Mind to Machine live server listening on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

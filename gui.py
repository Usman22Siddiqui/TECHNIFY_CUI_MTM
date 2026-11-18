"""Python desktop GUI (stdlib tkinter) for Mind to Machine.

Enter messages/test cases -> saved to out/plan.txt -> backend parses, extracts
(1 LLM call), grounds, resolves, plans, schedules, validates 6 checks, and
displays the schedule, budget, checks, rejections, and live trace.

Usage:
    python gui.py
"""

from __future__ import annotations

import pathlib
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
import webbrowser
from typing import Any

from core.llm import LLMClient
from core.parse import parse_messages
from core.report import format_rupees, load_i18n
from core.update import archive_state, load_state, run_pipeline
from core.validate import CHECK_NAMES
from run import write_outputs


ROOT_DIR = pathlib.Path(__file__).resolve().parent
STATE_PATH = ROOT_DIR / "state" / "state.json"
OUT_DIR = ROOT_DIR / "out"
PLAN_TXT_PATH = OUT_DIR / "plan.txt"

# Portfolio design system tokens (docs/DESIGN_SYSTEM.md)
CREAM = "#FEF8DC"
CREAM_DEEP = "#F5EBC3"
TAN = "#E6D9B5"
FOREST = "#223318"
FOREST_DEEP = "#1A2812"
OLIVE = "#5F6B35"
ORANGE = "#E0A04F"
SIGNAL_OK = "#4F7A2B"
SIGNAL_FAIL = "#A63D2B"


def submit_text_to_backend(
    text: str,
    plan_txt_path: pathlib.Path = PLAN_TXT_PATH,
    state_path: pathlib.Path = STATE_PATH,
    out_dir: pathlib.Path = OUT_DIR,
    client: LLMClient | None = None,
) -> dict[str, Any]:
    """Save GUI input text to out/plan.txt and run the full planning backend."""
    clean = text.strip()
    if not clean:
        raise ValueError("Input message text is empty.")

    plan_txt_path.parent.mkdir(parents=True, exist_ok=True)
    plan_txt_path.write_text(clean + "\n", encoding="utf-8")

    incoming = parse_messages(str(plan_txt_path))
    if not incoming:
        raise ValueError("No messages could be parsed from input.")

    result = run_pipeline(incoming, state_path, client=client)
    write_outputs(result, out_dir)
    return result


def format_plan_overview(state: dict[str, Any]) -> str:
    """Render a clean human-readable plan, schedule, and checks summary."""
    plan = state.get("plan", {})
    checks = state.get("checks", {})
    if not plan:
        return "No plan computed yet. Enter messages on the left and click 'Save to plan.txt & Plan'."

    hc = plan.get("headcount", {})
    v = plan.get("venue", {})
    f = plan.get("food", {})
    j = plan.get("judging", {})
    s = plan.get("schedule", {})
    b = plan.get("budget", {})

    lines: list[str] = []
    lines.append("CHECKS")
    for name in CHECK_NAMES:
        chk = checks.get(name, {})
        mark = "PASS" if chk.get("ok") else "FAIL"
        lines.append(f"  [{mark}] {name.upper():<9} {chk.get('detail', '')}")

    lines.append("")
    lines.append("HEADCOUNT")
    lines.append(
        f"  Total: {hc.get('total')}  "
        f"(students={hc.get('students')}, staff={hc.get('staff')}, judges={hc.get('judges_used')})"
    )

    lines.append("")
    lines.append("VENUE")
    lines.append(
        f"  Selected: {v.get('selected')} | Capacity: {v.get('capacity')} | "
        f"Cost: {format_rupees(v.get('cost', 0))} | Generator: {v.get('generator')}"
    )
    if v.get("reason"):
        lines.append(f"  Reason: {v.get('reason')}")

    lines.append("")
    lines.append(f"SCHEDULE ({s.get('total_minutes', 0)} min, start: {s.get('start_time', 'unknown')})")
    for blk in s.get("blocks", []):
        lines.append(
            f"  {blk['index']:02d}. {blk['start_label']:>8} - {blk['end_label']:<8}  "
            f"{blk['name']:<14} ({blk['minutes']} min)"
        )

    lines.append("")
    lines.append("FOOD")
    lines.append(
        f"  Tier: {f.get('tier')} | Qty: {f.get('quantity')} boxes x "
        f"{format_rupees(f.get('price_per_head', 0))} + delivery {format_rupees(f.get('delivery_fee', 0))} "
        f"= {format_rupees(f.get('cost', 0))}"
    )

    lines.append("")
    lines.append("JUDGING")
    lines.append(
        f"  Judges: {j.get('judges_used')}/{j.get('judges_confirmed')} (reserves: {j.get('reserves')}) | "
        f"Teams: {j.get('teams')} | Rounds: {j.get('rounds')} | Duration: {j.get('judging_minutes')} min"
    )
    lines.append(
        f"  Cost: {format_rupees(j.get('cost', 0))} "
        f"(worst case all confirmed: {format_rupees(j.get('worst_case_cost', 0))})"
    )

    lines.append("")
    lines.append("BUDGET")
    lines.append(f"  Budget total: {format_rupees(b.get('budget_total', 'unknown'))}")
    lines.append(f"  Venue:        {format_rupees(b.get('venue_cost', 0))}")
    lines.append(f"  Food:         {format_rupees(b.get('food_cost', 0))}")
    lines.append(f"  Judging:      {format_rupees(b.get('judge_cost', 0))}")
    for lbl, amt in (b.get("committed_costs") or {}).items():
        lines.append(f"  Committed ({lbl}): {format_rupees(amt)}")
    lines.append(f"  SPENT:        {format_rupees(b.get('spent', 0))}")
    lines.append(f"  REMAINING:    {format_rupees(b.get('remaining', 'unknown'))}")

    wl = b.get("wishlist") or []
    if wl:
        lines.append("")
        lines.append("WISHLIST (not spent)")
        for item in wl:
            lines.append(f"  - {item['label']}: {format_rupees(item['cost'])} [{item['status']}]")

    unhandled = plan.get("unhandled_constraints") or []
    if unhandled:
        lines.append("")
        lines.append("UNHANDLED CONSTRAINTS")
        for u in unhandled:
            lines.append(f"  - {u.get('subject')} ({u.get('op')} {u.get('value')}) [msg #{u.get('source_id')}]")

    return "\n".join(lines)


def format_rejections(state: dict[str, Any]) -> str:
    rejected = [m for m in state.get("messages", []) if m.get("status") == "rejected"]
    if not rejected:
        return "No messages rejected."
    lines: list[str] = []
    for m in rejected:
        lines.append(f"Message #{m.get('id')} ({m.get('role')}, {m.get('sender')}) — {m.get('reason_code')}")
        lines.append(f"  Text: {m.get('text')}")
        lines.append(f"  EN:   {m.get('reason_en')}")
        lines.append(f"  UR:   {m.get('reason_ur')}")
        lines.append("")
    return "\n".join(lines)


class MTMDesktopApp:
    """Tkinter desktop GUI wired directly to the Mind to Machine backend."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.t = load_i18n("en")
        self.root.title(f"{self.t['app_title']} — {self.t['page_heading']}")
        self.root.geometry("1220x760")
        self.root.configure(bg=CREAM)
        self._build_ui()
        self._refresh_from_disk()

    def _build_ui(self) -> None:
        # Top bar
        top = tk.Frame(self.root, bg=CREAM, padx=16, pady=10)
        top.pack(fill=tk.X)

        tk.Label(
            top,
            text=f"{self.t['app_title']}  |  out/plan.txt -> backend planner & scheduler",
            bg=CREAM,
            fg=FOREST,
            font=("Consolas", 11, "bold"),
        ).pack(side=tk.LEFT)

        self.status_var = tk.StringVar(value="Ready")
        tk.Label(
            top,
            textvariable=self.status_var,
            bg=CREAM,
            fg=OLIVE,
            font=("Consolas", 10),
        ).pack(side=tk.RIGHT)

        # Main split pane
        pane = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg=TAN, sashwidth=6)
        pane.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 14))

        # Left panel: Message / test case input
        left = tk.Frame(pane, bg=CREAM_DEEP, padx=12, pady=12)
        pane.add(left, minsize=420)

        tk.Label(
            left,
            text=f"{self.t['composer_heading']} (saved to out/plan.txt)",
            bg=CREAM_DEEP,
            fg=FOREST,
            font=("Segoe UI", 11, "bold"),
            anchor="w",
        ).pack(fill=tk.X, pady=(0, 6))

        self.input_box = scrolledtext.ScrolledText(
            left,
            wrap=tk.WORD,
            bg=CREAM,
            fg=FOREST,
            insertbackground=FOREST,
            font=("Consolas", 10),
            relief=tk.SOLID,
            bd=1,
        )
        self.input_box.pack(fill=tk.BOTH, expand=True)

        btn_row = tk.Frame(left, bg=CREAM_DEEP, pady=8)
        btn_row.pack(fill=tk.X)

        self.run_btn = tk.Button(
            btn_row,
            text="Save to plan.txt & Plan",
            command=self._on_run,
            bg=FOREST,
            fg=CREAM,
            activebackground=OLIVE,
            activeforeground=CREAM,
            font=("Segoe UI", 10, "bold"),
            padx=12,
            pady=6,
            relief=tk.FLAT,
            cursor="hand2",
        )
        self.run_btn.pack(side=tk.LEFT, padx=(0, 6))

        tk.Button(
            btn_row,
            text=self.t["upload_txt"],
            command=self._on_load_file,
            bg=CREAM,
            fg=FOREST,
            font=("Segoe UI", 9),
            padx=10,
            pady=6,
            relief=tk.SOLID,
            bd=1,
            cursor="hand2",
        ).pack(side=tk.LEFT, padx=(0, 6))

        tk.Button(
            btn_row,
            text=self.t["reset_session"],
            command=self._on_reset,
            bg=CREAM,
            fg=SIGNAL_FAIL,
            font=("Segoe UI", 9),
            padx=10,
            pady=6,
            relief=tk.SOLID,
            bd=1,
            cursor="hand2",
        ).pack(side=tk.LEFT, padx=(0, 6))

        tk.Button(
            btn_row,
            text="Open report.html",
            command=self._on_open_report,
            bg=CREAM,
            fg=OLIVE,
            font=("Segoe UI", 9),
            padx=10,
            pady=6,
            relief=tk.SOLID,
            bd=1,
            cursor="hand2",
        ).pack(side=tk.RIGHT)

        # Right panel: Tabbed outputs (Schedule & Plan | Trace | Rejected | plan.txt)
        right = tk.Frame(pane, bg=CREAM, padx=6, pady=6)
        pane.add(right, minsize=520)

        notebook = ttk.Notebook(right)
        notebook.pack(fill=tk.BOTH, expand=True)

        self.plan_view = self._make_readonly_text(notebook, bg=CREAM, fg=FOREST)
        self.trace_view = self._make_readonly_text(notebook, bg=FOREST_DEEP, fg=CREAM)
        self.rejected_view = self._make_readonly_text(notebook, bg=CREAM_DEEP, fg=SIGNAL_FAIL)
        self.plantxt_view = self._make_readonly_text(notebook, bg=CREAM, fg=FOREST)

        notebook.add(self.plan_view, text="Schedule & Plan")
        notebook.add(self.trace_view, text="Trace (Terminal)")
        notebook.add(self.rejected_view, text="Rejected Messages")
        notebook.add(self.plantxt_view, text="out/plan.txt")

    def _make_readonly_text(self, parent: tk.Widget, bg: str, fg: str) -> scrolledtext.ScrolledText:
        widget = scrolledtext.ScrolledText(
            parent,
            wrap=tk.WORD,
            bg=bg,
            fg=fg,
            font=("Consolas", 10),
            relief=tk.FLAT,
            padx=10,
            pady=10,
        )
        widget.configure(state=tk.DISABLED)
        return widget

    def _set_text(self, widget: scrolledtext.ScrolledText, content: str) -> None:
        widget.configure(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.insert("1.0", content)
        widget.configure(state=tk.DISABLED)

    def _refresh_from_disk(self) -> None:
        state = load_state(STATE_PATH) or {}
        self._set_text(self.plan_view, format_plan_overview(state))
        self._set_text(self.rejected_view, format_rejections(state))

        trace_txt = OUT_DIR / "trace.txt"
        self._set_text(
            self.trace_view,
            trace_txt.read_text(encoding="utf-8") if trace_txt.exists() else "No trace recorded yet.",
        )
        self._set_text(
            self.plantxt_view,
            PLAN_TXT_PATH.read_text(encoding="utf-8") if PLAN_TXT_PATH.exists() else "(out/plan.txt not written yet)",
        )

    def _on_load_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Select messages text file",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return
        content = pathlib.Path(path).read_text(encoding="utf-8")
        self.input_box.delete("1.0", tk.END)
        self.input_box.insert("1.0", content)
        self.status_var.set(f"Loaded {pathlib.Path(path).name}")

    def _on_run(self) -> None:
        text = self.input_box.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("Empty input", self.t["live_error_empty"])
            return

        self.run_btn.configure(state=tk.DISABLED)
        self.status_var.set(self.t["running_messages"])

        def worker() -> None:
            try:
                res = submit_text_to_backend(text)
                verdict = "COMMITTED" if res["committed"] else "REJECTED (plan unchanged)"
                msg = (
                    f"{res['mode'].upper()} | {verdict} | "
                    f"recomputed={','.join(res['recomputed']) or 'none'} | "
                    f"{res['trace'].total_tokens()} tok | {res['elapsed']:.1f}s"
                )
                self.root.after(0, lambda: self._on_run_done(msg, None))
            except Exception as exc:
                self.root.after(0, lambda e=exc: self._on_run_done("", str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_run_done(self, status_msg: str, error_msg: str | None) -> None:
        self.run_btn.configure(state=tk.NORMAL)
        if error_msg:
            self.status_var.set(f"Error: {error_msg}")
            messagebox.showerror("Run failed", error_msg)
            return
        self.status_var.set(status_msg)
        self._refresh_from_disk()

    def _on_reset(self) -> None:
        if STATE_PATH.exists():
            archive_state(STATE_PATH)
            STATE_PATH.unlink()
        if PLAN_TXT_PATH.exists():
            PLAN_TXT_PATH.unlink()
        for fname in ("trace.txt", "trace.json", "plan.json"):
            p = OUT_DIR / fname
            if p.exists():
                p.unlink()
        self.input_box.delete("1.0", tk.END)
        self.status_var.set("Session reset (previous state archived)")
        self._refresh_from_disk()

    def _on_open_report(self) -> None:
        report = OUT_DIR / "report.html"
        if not report.exists():
            messagebox.showinfo("No report yet", "Run messages first to generate out/report.html.")
            return
        webbrowser.open(report.as_uri())


def main() -> None:
    root = tk.Tk()
    MTMDesktopApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

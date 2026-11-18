"""Terminal output plus offline HTML report.

Without it: UI points lost; judges cannot read the trace.
"""

from __future__ import annotations

import base64
import json
import pathlib
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from rich.console import Console
from rich.table import Table

from core.trace import TraceCollector
from core.validate import CHECK_NAMES


UI_DIR = pathlib.Path(__file__).resolve().parent.parent / "ui"
I18N_DIR = UI_DIR / "i18n"
FONTS_DIR = UI_DIR / "fonts"


def load_i18n(lang: str = "en") -> dict[str, str]:
    """Load i18n dictionary from ui/i18n/<lang>.json."""
    path = I18N_DIR / f"{lang}.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def format_rupees(amount: int | float | str, grouping: str = "international") -> str:
    """Format an integer rupee amount in international or Pakistani lakh grouping."""
    if amount is None or amount == "unknown":
        return "unknown"
    n = int(round(float(amount)))
    neg = n < 0
    s = str(abs(n))
    if grouping == "lakh":
        if len(s) <= 3:
            grouped = s
        else:
            last3 = s[-3:]
            rest = s[:-3]
            parts = []
            while len(rest) > 2:
                parts.insert(0, rest[-2:])
                rest = rest[:-2]
            if rest:
                parts.insert(0, rest)
            grouped = ",".join(parts) + "," + last3
        prefix = "-" if neg else ""
        if abs(n) >= 100_000:
            lakh_val = f"{n / 100_000:.2f}".rstrip("0").rstrip(".")
            return f"Rs {prefix}{grouped} ({lakh_val} lakh)"
        return f"Rs {prefix}{grouped}"
    return f"Rs {n:,}"


def _build_embedded_font_faces() -> str:
    """Inline any bundled .woff2 files in ui/fonts/ as base64 @font-face rules."""
    if not FONTS_DIR.exists():
        return ""
    font_map = {
        "InterTight-ExtraBold.woff2": ("Inter Tight", 800),
        "Inter-Regular.woff2": ("Inter", 400),
        "Inter-Medium.woff2": ("Inter", 500),
        "JetBrainsMono-Regular.woff2": ("JetBrains Mono", 400),
        "JetBrainsMono-Medium.woff2": ("JetBrains Mono", 500),
        "NotoNastaliqUrdu-Bold.woff2": ("Noto Nastaliq Urdu", 700),
        "NotoNaskhArabic-Regular.woff2": ("Noto Naskh Arabic", 400),
    }
    rules: list[str] = []
    for filename, (family, weight) in font_map.items():
        fpath = FONTS_DIR / filename
        if fpath.exists():
            b64 = base64.b64encode(fpath.read_bytes()).decode("ascii")
            rules.append(
                f"@font-face {{ font-family: '{family}'; font-weight: {weight}; "
                f"font-display: swap; src: url('data:font/woff2;base64,{b64}') format('woff2'); }}"
            )
    return "\n".join(rules)


def render_html(state: dict[str, Any], trace: TraceCollector) -> str:
    """Render a self-contained, offline report.html string."""
    en = load_i18n("en")
    ur = load_i18n("ur")

    styles_css = (UI_DIR / "styles.css").read_text(encoding="utf-8")
    app_js = (UI_DIR / "app.js").read_text(encoding="utf-8")
    font_faces_css = _build_embedded_font_faces()

    messages = state.get("messages", [])
    rejected_messages = [m for m in messages if m.get("status") == "rejected"]

    embedded_payload = {
        "i18n": {"en": en, "ur": ur},
        "plan": state.get("plan", {}),
        "checks": state.get("checks", {}),
        "trace_text": trace.to_text(),
    }
    embedded_json = json.dumps(embedded_payload, ensure_ascii=False).replace("</", "<\\/")

    env = Environment(
        loader=FileSystemLoader(str(UI_DIR)),
        autoescape=select_autoescape(["html", "j2"]),
    )
    template = env.get_template("template.html.j2")
    return template.render(
        t=en,
        plan=state.get("plan", {}),
        checks=state.get("checks", {}),
        check_names=CHECK_NAMES,
        messages=messages,
        rejected_messages=rejected_messages,
        trace_calls=trace._calls,
        trace_events=trace._events,
        total_tokens=trace.total_tokens(),
        styles_css=styles_css,
        app_js=app_js,
        font_faces_css=font_faces_css,
        embedded_json=embedded_json,
    )


def print_terminal_summary(state: dict[str, Any], trace: TraceCollector) -> None:
    """Print plan, six checks, rejected messages, and trace summary using rich."""
    console = Console()
    plan = state.get("plan", {})
    checks = state.get("checks", {})

    table = Table(title="Event Plan Summary")
    table.add_column("Area", style="bold")
    table.add_column("Details")

    hc = plan.get("headcount", {})
    v = plan.get("venue", {})
    f = plan.get("food", {})
    j = plan.get("judging", {})
    s = plan.get("schedule", {})
    b = plan.get("budget", {})

    table.add_row("Headcount", f"{hc.get('total')} (students={hc.get('students')}, staff={hc.get('staff')}, judges={hc.get('judges_used')})")
    table.add_row("Venue", f"{v.get('selected')} — cap {v.get('capacity')}, {format_rupees(v.get('cost', 0))}")
    table.add_row("Food", f"{f.get('tier')} — {f.get('quantity')} x {format_rupees(f.get('price_per_head', 0))} + {format_rupees(f.get('delivery_fee', 0))} = {format_rupees(f.get('cost', 0))}")
    table.add_row("Judging", f"{j.get('judges_used')}/{j.get('judges_confirmed')} judges, {j.get('teams')} teams, {j.get('judging_minutes')} min, {format_rupees(j.get('cost', 0))} (worst case {format_rupees(j.get('worst_case_cost', 0))})")
    table.add_row("Schedule", f"{len(s.get('blocks', []))} blocks summing to {s.get('total_minutes')} min (start: {s.get('start_time')})")
    table.add_row("Budget", f"spent {format_rupees(b.get('spent', 0))} / {format_rupees(b.get('budget_total', 'unknown'))} | remaining {format_rupees(b.get('remaining', 'unknown'))}")
    console.print(table)

    checks_str = "  ".join(
        f"[green]{n}: OK[/green]" if checks.get(n, {}).get("ok") else f"[red]{n}: FAIL ({checks.get(n, {}).get('detail', '')})[/red]"
        for n in CHECK_NAMES
    )
    console.print(f"Checks: {checks_str}")

    rejected = [m for m in state.get("messages", []) if m.get("status") == "rejected"]
    if rejected:
        console.print("\n[bold red]Rejected messages:[/bold red]")
        for m in rejected:
            console.print(f"  {m.get('reason_en')}")

    console.print(f"\nTrace: {len(trace._calls)} call(s), {trace.total_tokens()} total tokens")


def render_report(
    state: dict[str, Any],
    trace: TraceCollector,
    out_dir: pathlib.Path,
    print_console: bool = True,
) -> pathlib.Path:
    """Write out/report.html and optionally print terminal summary."""
    out_dir.mkdir(parents=True, exist_ok=True)
    html = render_html(state, trace)
    report_path = out_dir / "report.html"
    report_path.write_text(html, encoding="utf-8")
    if print_console:
        print_terminal_summary(state, trace)
    return report_path

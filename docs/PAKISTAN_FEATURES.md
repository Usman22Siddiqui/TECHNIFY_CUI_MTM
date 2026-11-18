# Pakistan-Specific Features

Small features with real effect on accuracy, explainability and UI score. Priority: P0 must ship, P1 should, P2 if time.

| # | Feature | Pri | What it does | Where | Test |
|---|---|---|---|---|---|
| F1 | Urdu / English switch | P0 | Whole interface flips language and direction (RTL), fonts swap, choice persists | `ui/i18n`, `app.js`, CSS logical properties | Toggle, reload, check `dir` and no clipped text |
| F2 | Roman Urdu and Urdu script reading | P0 | Reading prompt and fixtures cover mixed English, Roman Urdu and Urdu script | `extract.py`, fixtures | Same facts extracted from three phrasings |
| F3 | Pakistani number formats | P0 | Understands `Rs 6,50,000`, `650k`, `6.5 lakh`, `paanch hazar`, `1.2 lac`, `Rs 1200/-`; grounding check normalises the same way | `ground.py` | Table-driven unit tests |
| F4 | Bilingual rejection reasons | P0 | Every rejection explained in English and Urdu from templates | `update.py`, `i18n` | Each reason code has both strings |
| F5 | Lakh / crore grouping toggle | P0 | Show `Rs 650,000` or `Rs 6,50,000`, and short form `6.5 lakh` | `report.py`, `app.js` | Snapshot of formatter |
| F6 | WhatsApp-ready summary | P0 | One button copies the plan as WhatsApp text (`*bold*`, short lines), in the current language | `app.js` | Copy output matches plan figures |
| F7 | Generator and load-shedding awareness | P1 | A power outage or load-shedding message becomes a hard `venue.generator` constraint; plan shows a power-backup badge | `resolve.py`, planner | Fixture with outage message picks a generator venue |
| F8 | Prayer-aware schedule | P1 | Prayer break is placed at the nearest valid prayer window when the start time is known; Friday congregational prayer window is blocked when the date is a Friday. Prayer times come from a local library or a bundled offline table, never a live lookup | `planner.py`, `config/prayer_defaults.json` | Window fixtures |
| F9 | Dietary and Ramadan handling | P1 | Halal requirement, vegetarian share, and Ramadan flag (iftar slot instead of lunch) become food and schedule constraints | `planner.py` | Constraint fixtures |
| F10 | PKT 12-hour time and Urdu digits | P1 | Clock times as `2:30 PM`; optional Urdu-Indic digits in the Urdu view | `report.py`, `app.js` | Formatter tests |
| F11 | Commute buffer | P1 | A lateness note (traffic on a named road) adds an arrival buffer block and keeps reserve judges visible | `planner.py` | Fixture with a late-arrival note |
| F12 | Offline-first UI | P1 | Fonts, scripts, styles all bundled; page works with no internet (venue Wi-Fi is not reliable) | `ui/` | Open page with network off |
| F13 | Print-ready A4 plan | P2 | Print stylesheet for the Dean's office, both languages | `styles.css` | Print preview |
| F14 | Rupee unit guard | P2 | Flags values that look like thousands versus rupees mix-ups using the known range of the same key | `resolve.py` | `UNIT_ANOMALY` fixture |

## Why these matter to the agent, not only the UI

- F2 and F3 raise the accuracy of the reading step on an unseen pack, which is the 30-point output score.
- F7, F8, F9 and F11 are implemented as constraints in the general constraint engine. That is the right answer to "constraints of a kind you have not seen".
- F4 strengthens the 20-point "why was it rejected" evidence.
- F1, F5 and F6 are visible in the first minute of a judge visit.

## Rules

- All Urdu UI text comes from `ui/i18n/ur.json`. Have a native speaker proofread it before the freeze.
- Trace files stay English-canonical. Urdu appears in the UI and in `reason_ur` fields only.
- The reading model must accept Urdu script input. Keep one fixture in Urdu script.
- Never type message facts into prompts to improve Roman Urdu handling. Teach shapes, not content.

## Starter UI strings (verify before use)

| Key | English | Urdu |
|---|---|---|
| plan | Plan | منصوبہ |
| venue | Venue | مقام |
| schedule | Schedule | شیڈول |
| food | Food | کھانا |
| judging | Judging | ججنگ |
| budget | Budget | بجٹ |
| trace | Trace | ٹریس |
| rejected | Rejected messages | مسترد پیغامات |
| checks | Checks | جانچ |
| prayer_break | Prayer break | نماز کا وقفہ |
| total | Total | کل |
| remaining | Remaining | باقی |
| pass | Passed | کامیاب |
| fail | Failed | ناکام |
| copy_whatsapp | Copy for WhatsApp | واٹس ایپ کے لیے کاپی کریں |
| language | Language | زبان |
| plan_unchanged | Plan unchanged | منصوبہ برقرار ہے |

# Design System

The theme comes from Usman's portfolio (usman.sys): butter cream ground, deep forest green type, olive secondary, one warm orange accent, a dark green terminal panel. The brief is to keep that identity and avoid a generated-template look.

Colour values were read by eye from the screenshot. Eyedrop the PNG and correct these tokens before building.

## Tokens

```
--cream:        #FEF8DC   page background
--cream-deep:   #F5EBC3   table stripes, inset areas
--tan:          #E6D9B5   borders, ring colour (the photo ring in the portfolio)
--forest:       #223318   primary text, headings, dark panels
--forest-deep:  #1A2812   trace panel background
--olive:        #5F6B35   secondary headings, active states
--olive-muted:  #6B6B55   body secondary text
--orange:       #E0A04F   prompt marks, focus ring, one highlight per screen
--orange-ink:   #A8651A   orange used as text (passes contrast on cream)
--signal-ok:    #4F7A2B   check passed
--signal-fail:  #A63D2B   check failed, rejected message
```

Contrast rules: `--orange` on cream fails for text, so text uses `--orange-ink`. `--olive-muted` is for text of 16px and above. Check every pair with a contrast tool.

## Typography

| Role | Face | Notes |
|---|---|---|
| Display and headings | Inter Tight (or Archivo) 800, tight tracking | Echoes the heavy grotesque in the portfolio hero |
| Body | Inter 400 / 500 | 16px base, line length under 75 characters |
| Data, trace, amounts, times | JetBrains Mono 400 / 500 | Tabular figures; this is real data, so mono is earned |
| Urdu headings | Noto Nastaliq Urdu | Page title and section titles only, line-height 2.1 |
| Urdu body and tables | Noto Naskh Arabic | Nastaliq is too tall for dense tables |

All fonts bundled in `ui/fonts/` (woff2) and loaded with `@font-face`. No CDN.

## Anti-template rules

The page must read as built for this tool, not generated. Follow these:

1. No grid of identical rounded cards. Sections have different shapes because their content differs: a timeline, a ledger, a grid, a terminal.
2. No gradient washes, glow, glassmorphism or stock blob decoration. The portfolio's 3D shapes stay on the portfolio.
3. One radius scale with meaning: 2px for table cells and inputs, 6px for panels, 999px only for the language switch. Never one radius everywhere.
4. Borders use `--tan`. Shadows: none, except one soft shadow under the trace panel to lift it.
5. No emoji icons. Use a small inline SVG set (check, cross, copy, print, globe) drawn with 1.5px strokes.
6. Sentence-case labels. Uppercase mono is allowed only for the top navigation and the six check names, as in the portfolio. Not above every heading.
7. No tracked-out eyebrow text above headings, no middle-dot strings, no arrows appended to buttons.
8. Numbering only where order is real: schedule blocks and trace calls.
9. Motion: one moment only. On first load the trace prints line by line (about 1.2 s total). Everything else responds to a click: language switch, expand call, copy. Respect `prefers-reduced-motion`.
10. Real copy. Buttons say what happens: "Copy plan for WhatsApp", "Download trace", "Show Urdu".

## Layout concept

Left aligned, asymmetric, two columns on desktop (plan about 62%, trace about 38%), single column on mobile with the trace below.

```
+--------------------------------------------------------------------------+
| mind to machine                      [ Plan | Trace | Rejected ]  [ اردو ] |
+--------------------------------------------------------------------------+
| Hackathon plan, Islamabad                    |  usman@control-panel        |
| 150 students, 50 teams, 4 hours              |  $ run messages.txt         |
|                                              |  call 1  reading  1,842 tok |
| Checks                                       |  [recompute] budget         |
|  figures ok  budget ok  venue ok             |  [reject] msg 9 BREAKS_CHECK|
|  schedule ok  judges ok  coverage ok         |  ...                        |
|                                              |                             |
| Venue          (one clear line + reason)     |  total tokens 1,842         |
| Schedule       (vertical ruler, heights      |                             |
|                 proportional to minutes)     |                             |
| Food           (ledger line)                 |                             |
| Judging        (judge x team grid)           |                             |
| Budget         (ledger, right aligned Rs)    |                             |
| Wishlist       (requests that fit / do not)  |                             |
+----------------------------------------------+-----------------------------+
| Rejected messages: original text struck through, reason beneath, in English   |
| and Urdu, with the rule that failed                                          |
+--------------------------------------------------------------------------+
```

## The memorable element

The trace panel. It reuses the dark forest terminal from the portfolio: orange `$` prompt, mono text, each call collapsible, token count right aligned, running total pinned at the bottom. Everything else stays quiet.

## Components

- **Language switch**: pill toggle, `English | اردو`. Flips `dir`, swaps fonts, persists in `localStorage`. Logical CSS properties everywhere (`margin-inline-start`, `padding-inline`, `text-align: start`).
- **Check line**: name, tick or cross, one-line detail. Failure shows the detail text in `--signal-fail`.
- **Schedule ruler**: vertical bar, each block height proportional to minutes, label and minutes beside it. Prayer block uses an olive fill so it stands out.
- **Budget ledger**: label left, amount right, tabular figures, subtotal rule, remaining in bold. Toggle for lakh grouping.
- **Judge grid**: rows judges, columns rounds, cell shows team id. Reserves listed below.
- **Rejected message**: `--cream-deep` block, quote struck through, reason code in mono, English and Urdu explanation, message id and sender role.
- **Empty state**: "No messages loaded. Run `python run.py <file>`."
- **Error state**: say what failed and what to do. No apologies.

## Quality floor

Responsive to 360px. Visible keyboard focus (orange ring). Colour is never the only signal (icons and words too). Print stylesheet produces a clean A4 plan.

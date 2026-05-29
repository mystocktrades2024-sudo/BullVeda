# Handoff: SwingTrade V2 — Aurora Glass terminal redesign

## Overview

This is a high-fidelity redesign of the SwingTrade V2 swing-trading terminal:
a hedge-fund-grade dashboard that scans the US equity universe daily, scores
every name on a 5-pillar model across strategy "sleeves," and lets the operator
drill into any ticker through **14 analytical lenses** to reach a disciplined
BUY / WATCH / SHORT / AVOID decision with a pre-placed, risk-first trade ticket.

It is **informational** — it never auto-trades. The user always makes the call;
the system surfaces the evidence and enforces the discipline.

## About the design files

The files in this bundle are **design references created in HTML/CSS/JSX** —
prototypes showing intended look and behavior, not production code to copy directly.

**Your task is to recreate these designs in the target codebase's existing environment**
(React + Vite, Next.js, Remix, etc.) using its established patterns, design tokens, and
libraries. If no environment exists yet, choose the most appropriate framework and
implement the designs there.

The prototypes are written with React 18 + Babel-in-browser + plain CSS — convenient
for fast iteration, but **NOT** the right shape for production. Specifically you should:

- Migrate JSX out of `<script type="text/babel">` into proper module files with a build step
- Replace `window.X` exports with ESM imports
- Use CSS modules / Tailwind / styled-components / your team's choice in place of the
  flat global `.css` files (the tokens are designed to drop in as CSS custom properties
  regardless of styling layer)
- Replace mock data in `src/data.jsx` with real feeds from EODHD / Schwab / Zacks
  (see §8 below)
- Wire the `LightweightCharts` library for the real OHLC chart in the Chart lens
  (currently a synthetic SVG)

## Fidelity

**High-fidelity (hifi).** Pixel-perfect mockups with final colors, typography, spacing,
radii, shadows, and interactions. Recreate the UI faithfully — every token in the system
has been deliberately chosen.

## Information architecture (two levels)

### Level 1 — Workspace (left sidebar / icon rail, 56px wide)

Top-level surfaces, grouped:

- **Scan results:** Market Map (heatmap, default landing), Watchlist, Screener,
  Elite Picks, BUY candidates, Killed/AVOID, Industries, Themes, Leveraged, Crypto,
  Events (IPO/Splits), Pre-Market, Pairs.
- **Strategy & performance:** Strategies, Performance, Accuracy, Macro · Events,
  Options Flow, Alerts.
- **Knowledge:** Playbook (rulebook), Reference/Cheat, Thesis Library, Research.
- **Admin:** Settings, System Status, CapStudio (RBAC), Audit/Change History,
  Research Lab, Factor Exposure.

The icon rail shows icons only (44×36px touch targets, 10px radius). Hover reveals
a tooltip. Counts appear as small pills in the top-right of the icon. The first
icon in each group gets a 1px top separator. Brand mark at top, market-status
pulse at bottom.

### Level 2 — Detail panel (opens on ticker click)

Three-column layout (direction E):

```
+--------+----------------+---------------------------+
| ICON   | SCAN COLUMN    | DETAIL PANEL              |
| RAIL   | (Map / BUY /   | command bar (44px)        |
| 56px   |  Watch / Elite)| ticker header (60px)      |
|        | S/M/L/XL       | 14-tab pill nav (50px)    |
|        |                | lens body (scroll)        |
+--------+----------------+---------------------------+
```

**Focus mode** (press `F` or click `◉ Focus` in detail header): scan column collapses
to a thin 64px rail showing just symbol + chg for the next few candidates. Detail
panel takes the rest of the screen. Press `F` again to exit.

When **no ticker is selected**, the right pane shows the **Home view** instead of
the detail panel — a landing surface with the Market Map full-width + summary cards.
**Esc** or clicking the Home button (top-left of command bar) returns to home.

## Screens / Views

### Home view

Full-bleed landing surface shown when no ticker is "drilled into."

**Layout:** Vertical flex column, full-width:

1. **Hero strip** (1fr | auto grid):
   - Left: eyebrow ("SwingTrade · 2026-05-28 · 14:23 ET") · big title with counts
     (612 ranked / 14 BUY · 8 WATCH-CLOSE · 31 AVOID) · explainer line
   - Right: 6-cell macro stats grid (S&P · NASDAQ · RUSSELL · VIX · DXY · US10Y) —
     each cell shows label, value (mono 14px), delta (color-coded)

2. **Main grid** (2fr | 1fr):
   - Left: Market Map (treemap heatmap, sized by mcap, colored by 1D %)
   - Right: Top BUY · today list (5 rows) + Macro · regime card (6 indicators
     + bull/low-vix verdict pill)

3. **Three-column row** (1fr | 1fr | 1fr):
   - Day's movers (4×3 grid of 12 cells, click to drill)
   - Calendar · next 14d (FOMC, PCE, ECB, ER events)
   - Your book (3 KPIs + segmented allocation bar + sleep score)

### Detail panel (14 lenses)

Each lens is a vertical scroll of "sections" following a recurring grammar:

- **Hero band** at top: verdict/score, a key visual (gauge, radar, chart, cone),
  and a 3–6 tile KPI strip.
- **Numbered sections** (`§1`, `§2`, …) each with a header (title + sub + freshness
  pill + state toggle), a body (table / tile-grid / SVG viz), and an optional
  plain-English "read" note.
- **Cross-Lens row** near the bottom: a 5-cell strip showing how the *other*
  disciplines see this name. Conflicts are surfaced, not smoothed. First cell
  is the lead and has the lens's accent color as a top border.
- **"The Call" footer:** a one-line verdict for that lens's time-horizon.

The 14 lenses (in order — preserve this; it follows the operator's funnel):

| # | Lens               | Kbd | Accent | The question                                   |
|---|--------------------|-----|--------|------------------------------------------------|
| 1 | Overview · Verdict | 1   | copper | Should I look closer?                          |
| 2 | Plan · Ticket      | 2   | copper | Execution-ready ticket                         |
| 3 | Chart              | 3   | copper | Full OHLC + indicators                         |
| 4 | Technicals         | T   | cy     | 10-section discipline view                     |
| 5 | Patterns           | 4   | violet | Chart patterns + Elliott/Wyckoff               |
| 6 | SMC                | 5   | cy     | Smart Money Concepts                           |
| 7 | Investment · Value | V   | blue   | Intrinsic value & quality                      |
| 8 | Risk               | R   | rd     | VaR · Kelly · stress                           |
| 9 | Earnings           | E   | amb    | ER countdown & implied move                    |
| 10| Options            | O   | amb    | IV · flow · payoff                             |
| 11| Portfolio          | P   | copper | Cap usage & correlation                        |
| 12| Tape · Flow        | I   | violet | News + insider + 13F                           |
| 13| Track Record       | 7   | gn     | Has this setup worked?                         |
| 14| ML Edge            | M   | violet | 3-headed model forecast                        |

Per-lens content details are in `src/lens-*.jsx` files.

## Recurring grammar (component library)

Learn these once and the whole product becomes consistent:

- **Section header:** `§N` accent number (pill-shaped, color-mixed with lens accent),
  uppercase mono title, dim sub-line, freshness pill (right). Three style variants
  switchable via tweaks: `copper` (default), `minimal` (no number, thin rule),
  `sticky-rail` (left mark).
- **KPI tile:** glass card, uppercase mono label (`label-cap`), big mono value
  color-coded by tone, sub-note. Three style variants: `bare` (value-only),
  `sparkline` (with mini chart), `delta` (with up/down arrow).
- **Pill:** small rounded tag — `gn` / `rd` / `amb` / `copper` / `cy` / `violet` /
  `blue` / `ink` variants, with optional dot prefix and small modifier.
- **Wilson pill** — sample-size honesty surface: `n / wr / wilson lb` mono strip.
  When n<30, turns red with "n<30 · ACT WITH CAUTION" warning. Required on every
  edge claim.
- **Data table:** dense, right-aligned numerics, color-coded `<b>` cells, sticky
  header with glass bg.
- **Cross-Lens 5-cell strip:** equal cells, lead cell border-topped in the lens's
  accent color. Cells show: lens name (label-cap), verdict (big mono, tone-colored),
  short note (dim mono).
- **State wrapper** — every data-bound section must define four states:
  1. **Live** (default) — green/cyan "LIVE" or freshness pill
  2. **Loading** — spinner + "Fetching from {source}…"
  3. **Empty** — italic dim message naming the source, e.g.
     *"No insider transactions for this ticker. Source: EODHD InsiderTransactions."*
  4. **Scaffold** — amber banner: *"⚠ Partial scaffolding — layout built, but
     {feed} isn't wired yet. Numbers below are illustrative."*

**Why states matter:** the dashboard began as a prototype seeded with one example
ticker (AVGO/Broadcom). The single most important rule is: **never let prototype
numbers masquerade as live**. A beautiful fake number is worse than an ugly
"no data." This is the honesty contract.

## Interactions & behavior

- **Click a ticker anywhere** (heatmap cell, watchlist row, BUY card, scan list) →
  opens the detail panel on the last-viewed sub-tab.
- **Sub-tab nav** is keyboard-driven (1–7, T/V/R/E/O/P/I/M) and click.
- **Mode toggle** (SWING / POSITION / INVESTMENT in command bar) re-ranks the
  verdict, stop, T1/T2, and hold-period on Plan/Overview without refetching —
  the same ticker reads differently per horizon. See `modeAdjust()` in
  `src/lens-plan.jsx`.
- **Detail panel is responsive** — observes its rendered width and applies a
  `sizeCat` class (`S` / `M` / `L` / `XL`) that controls reflow:
  - S: grids collapse to 1 column, hero strip stacks 3×2 instead of 6×1
  - M: 2-column grids stay 2-column
  - L / XL: full grammar
- **Live polling:** intraday price updates ≤30s during market hours; each
  section shows a freshness pill (green ≤ threshold, red if stale).
- **Lazy data:** heavier sections (holders, financials, ML) fetch on first
  view and repaint; show a loading state, never a blank.
- **Focus mode** (`F`): scan column collapses to 64px rail showing symbol + chg
  only. Detail panel takes the rest of the screen. Press `F` again to exit.
- **Esc:** drill back out — detail → home.
- **Theme switching** via Tweaks panel → Theme palette. Sets `data-theme="..."`
  on `<html>` and all tokens re-resolve.

## State management

Top-level `App` state:

```
surface:     string  // active L1 surface ("market-map", "buy", "watchlist", "elite", ...)
ticker:      object | null  // null = home view; object = drilled-in
lensId:      string  // active sub-tab ("plan", "technicals", ...)
detailWidth: number  // observed via ResizeObserver for reflow
```

Tweaks (persisted via the Tweaks host protocol — your codebase should swap this
for localStorage or user-prefs API):

```
theme:       string  // "midnight-cyan" | "deep-violet" | ... | "ivory-editorial"
mode:        "SWING" | "POSITION" | "INVESTMENT"
scanWidth:   "S" | "M" | "L" | "XL"
focus:       boolean
heroStyle:   "radar" | "gauge" | "cone"
headerStyle: "copper" | "minimal" | "sticky-rail"
kpiStyle:    "bare" | "sparkline" | "delta"
```

## Design tokens

All tokens are defined in `tokens.css` and exposed as CSS custom properties.
The base theme (Aurora Cyan / `midnight-cyan`) is the default — all 9 themes
swap `--bg`, `--ink`, and `--copper` (brand accent) but keep sentiment colors
(`--gn` / `--rd` / `--amb`) for universal financial semantics. Light themes
flip `color-scheme` and use darker translucency for glass surfaces.

### Color tokens (Aurora Cyan default)

```
--bg:      #0a0e14        page background (deep navy-black)
--bg-1:    #0f141b        card surface
--bg-2:    #141a23        panel surface
--bg-3:    #1a2230        inset / hover
--line:    #232a37        borders
--line-2:  #313a4d        borders strong
--ink:     #e7ecf2        primary text
--ink-1:   #b4bccb        ink·1
--ink-2:   #8590a3        ink·2 · dim
--ink-3:   #5e6a7e        ink·3 · dimmer
--copper:  #5dd6d6        brand accent (cyan in this theme)
--gn:      #4ade80        bullish · pass · good
--rd:      #f87171        bearish · fail · risk
--amb:     #fbbf24        neutral · caution
--cy:      #5dd6d6        categorical (Tech / SMC)
--violet:  #a78bfa        categorical (Patterns / Tape / ML)
--blue:    #5b9bf2        categorical (Investment)
```

### Aurora Glass overlay tokens

```
--r-glass:    14px        large radii
--r-pill:     999px       pill radii (controls, buttons, tabs)
--glass-bg-1: rgba(255,255,255,0.025)    translucent surface
--glass-bg-2: rgba(255,255,255,0.045)
--glass-bg-3: rgba(255,255,255,0.065)
--glass-line: rgba(255,255,255,0.08)     translucent borders
--glass-line-2: rgba(255,255,255,0.16)
--glass-blur: blur(22px)                 backdrop-filter
```

For light themes, glass tokens flip to `rgba(0,0,0,0.0X)`. The body background
is a layered aurora gradient using `color-mix(in oklab, var(--copper) 18%, transparent)`
so the bloom always coordinates with the active brand accent.

### Themes (9 total)

| ID                | Display name      | Variant | Accent (--copper) |
|-------------------|-------------------|---------|-------------------|
| midnight-cyan     | Aurora Cyan       | dark    | #5dd6d6           |
| deep-violet       | Aurora Violet     | dark    | #a78bfa           |
| forest-terminal   | Aurora Mint       | dark    | #6ee098           |
| obsidian-gold     | Aurora Sunset     | dark    | #d97757           |
| carbon-amber      | Aurora Amber      | dark    | #fbbf24           |
| bronze-noir       | Aurora Bronze     | dark    | #c79152           |
| slate-mint        | Aurora Slate      | dark    | #5ee3a8           |
| arctic-light      | Daylight Pearl    | light   | #2563c8           |
| ivory-editorial   | Daylight Sand     | light   | #b85d3e           |

### Typography

- **JetBrains Mono** (`--mono`) — all numbers, labels, section headers, ticker
  symbols, all data. Use `font-feature-settings: "tnum"` (tabular nums) and
  `font-variant-numeric: tabular-nums` everywhere numbers align in columns.
- **Inter** (`--sans`) — explainer prose, "read" notes, the few human sentences.
- **Label-caps** — mono 10px, letter-spacing 0.14em, text-transform uppercase,
  `--ink-3`. Used for `§N HEADER`, KPI tile labels, freshness pills.
- **Big numbers** — mono 22–60px, font-weight 500, letter-spacing -0.01em,
  tabular nums. ER countdown number is the biggest (60px with copper text-shadow
  glow).
- **Section titles** — mono 12px, letter-spacing 0.18em, uppercase, `--ink`.

### Spacing scale

Use 4px grid: 4, 6, 8, 10, 12, 14, 16, 20, 24, 32. Section padding is `14px 16px`.
Hero padding is `16px 20px`. Cards have `12px 14px` padding.

### Radii

```
--r-1: 3px       very small (kbd hints, dots)
--r-2: 10px      buttons, segmented controls (was 5px in non-aurora — overridden)
--r-3: 14px      cards
--r-4: 18px      large containers
--r-pill: 999px  pills, tabs, mode toggle, search field, surface tabs
--r-glass: 14px  glass cards (same as r-3)
```

### Shadows / glows

```
--shadow-1: shadow-1 inset hairline (0 0 0 1px var(--line))
--shadow-2: 0 12px 32px -8px rgba(0,0,0,0.6)
--bloom:    0 0 18px rgba(255,255,255,0.04)
```

Active interactive elements get a per-accent glow:
```
box-shadow:
  inset 0 0 0 1px color-mix(in oklab, var(--accent) 30%, transparent),
  0 0 18px color-mix(in oklab, var(--accent) 24%, transparent);
```

## Data sources (for empty/scaffold state labels)

- **EODHD** — OHLCV, fundamentals (Highlights, Valuation, Financials 5yr, Holders,
  InsiderTransactions, Earnings history + analyst trend), news + sentiment,
  economic events, IPO/split calendar.
- **Schwab** — options chains + Greeks, quotes, movers, market hours.
- **Zacks** — rank, ESP, premium screens.
- **Scan output** (`cache/last_bundle.json`) — ~600 scored tickers/day, each with
  score, 5-pillar breakdown, verdict, decisions-by-mode, kelly sizing, setup family,
  catalyst tags.
- **`setup_stats.json`** — Wilson-CI'd per-setup-family win-rate / PF / median-R / decay.
- **`ml_edge_predictions.json`** — per-ticker ML forecasts.
- **`portfolio_state`** — live positions, equity (NAV), cash.

Surface the source name in section sub-lines and empty states so the user always
knows where a number came from and can tell live from scaffold.

## Design principles (non-negotiable)

1. **Decision-first.** Every surface answers one question. Lead with the verdict.
2. **Risk before reward.** Size and stop above targets, always.
3. **Honest states.** Live / loading / empty / scaffolding — never a plausible fake.
4. **Sample-size visible.** Show `n` and Wilson LB on every edge claim; flag `n<30`.
5. **Conflicts surfaced, not smoothed.** Cross-lens disagreement is a feature.
6. **Consistent grammar.** Reuse the section-header / KPI-tile / pill / table vocabulary.
7. **Mode-aware.** SWING vs POSITION vs INVESTMENT changes the read; respect the toggle.
8. **Dense but scannable.** This is a pro terminal — high information density, but every
   number color-coded and every section skimmable via its header + read-note.

## Assets

No external image assets. All icons are inline SVG (see `src/icon-rail.jsx` for
sidebar icons and `src/lens-icons.jsx` for the 14 lens glyphs). The brand mark is
a 3-bar bar-chart with a diagonal slash, inline SVG.

Fonts loaded from Google Fonts:
- Inter (weights 400, 500, 600, 700)
- JetBrains Mono (weights 400, 500, 600)

## Files (in this bundle)

### HTML entry points
- `SwingTrade Terminal.html` — full interactive prototype
- `SwingTrade Canvas.html` — static design canvas (component grammar + theme
  swatches + Market Map + 3 full lenses scrollable)
- `SwingTrade Directions.html` — early shell direction wireframes (E + C picked)
- `SwingTrade Design Languages.html` — visual direction comparison (Carbon vs
  Aurora Glass vs Atelier; Aurora Glass picked)

### CSS (load order matters)
- `tokens.css` — design tokens + 9 named themes
- `components.css` — section header, KPI tile, pill, button, segmented control,
  state wrapper, Wilson pill, cross-lens strip styles
- `shell.css` — icon rail, scan column, command bar, detail panel, Market Map
- `lenses.css` — lens-specific styles (Plan hero, ticket, waterfall, ladder,
  time-anatomy ribbon, value scale, quality cards, bull/bear)
- `lens-extras.css` — Chart, Patterns, SMC, Risk, Earnings, Options, Portfolio,
  Tape, Track Record, ML lens-specific styles
- `aurora.css` — Aurora Glass aesthetic overlay (gradient bg, backdrop-blur on all
  surfaces, pill controls, larger radii, luminous active states)
- `visual-rich.css` — Rich detail tabs (per-lens icon + accent + verdict dot) +
  Home view styling

### React/JSX (in load order)
- `tweaks-panel.jsx` — Tweaks panel host protocol + form controls (starter component)
- `design-canvas.jsx` — Design canvas wrapper (starter component, for Canvas file only)
- `src/data.jsx` — mock data: TICKER, HEATMAP, WATCHLIST, NAV groups, LENSES with
  per-lens metadata (kbd, accent, verdict, question)
- `src/components.jsx` — SectionHeader, FreshnessPill, Pill, WilsonPill, KpiTile,
  CrossLens, StateWrap, Sparkline, Gauge, Radar, Cone
- `src/lens-icons.jsx` — 14 inline SVG glyphs for the lens tabs
- `src/detail-panel.jsx` — DetailPanel shell + DetailHeader + DetailTabs +
  DetailLens routing + VerdictHero + StateToggle + LensOverview
- `src/lens-plan.jsx` — Plan · Ticket (PlanHero, OrderTicket, SizingWaterfall,
  PriceLadder, InvalidationLadder, TimeAnatomy, ReactionPlaybook, PostFillChecklist)
- `src/lens-technicals.jsx` — Technicals (indicator dashboard, MA stack, pattern
  matrix, S/R ladder, volume, statistical backbone, regime edge)
- `src/lens-investment.jsx` — Investment · Value (value scale, quality scorecard,
  peer cohort, 5y statements, capital allocation, bull/bear, catalyst calendar)
- `src/lens-chart-patterns.jsx` — Chart (big OHLC, HTF bias, annotations) +
  Patterns (Wyckoff, Elliott, Monte Carlo, action ladder)
- `src/lens-smc-risk.jsx` — SMC (OB table, structure log, liquidity sweeps,
  MTF screener) + Risk (loss cones, Kelly, VaR table, stress grid, liquidity)
- `src/lens-earnings-options.jsx` — Earnings (countdown, implied cone, beat prob,
  8Q history, IV crush) + Options (vol richness, UOA, chain grid, strategy matrix,
  payoff)
- `src/lens-portfolio-tape.jsx` — Portfolio (held state, position sim, correlation,
  factor) + Tape (sentiment dial, news timeline, insider, holders, calendar)
- `src/lens-track-ml.jsx` — Track Record (Wilson, edge decay, walk-forward, MC
  distribution) + ML Edge (3-headed forecast, prob bars, hit-net, calibration, SHAP)
- `src/icon-rail.jsx` — left icon rail (sidebar with 12 nav items grouped by Scan
  / Tools / Admin)
- `src/market-map.jsx` — treemap heatmap (sized by mcap, colored by 1D %, grouped
  by sector)
- `src/surfaces.jsx` — Watchlist / Elite Picks / BUY candidates / stub surfaces
  (legacy from earlier iteration — main flow uses ScanColumn + Home)
- `src/scan-column.jsx` — middle column (BUY / MAP / WATCH / ELITE tabs, S/M/L/XL
  width preset, focus-mode collapsed rail)
- `src/theme-picker.jsx` — curated theme palette picker (9 themes with swatches)
- `src/home.jsx` — Home view (hero strip + market map + side cards + movers +
  calendar + book)
- `src/app.jsx` — root App component (composes the shell, manages state, renders
  CommandBar + IconRail + ScanColumn + Home/DetailPanel + Tweaks)

## Implementation order (suggested)

1. **Tokens + shell** — implement `tokens.css` + base layout (icon rail · scan
   column · main pane). Get the 3-column grid + Aurora Glass overlay landing
   first. Verify backdrop-filter is supported in your target browsers.
2. **Component grammar** — implement the 7 atomic components (`SectionHeader`,
   `KpiTile`, `Pill`, `WilsonPill`, `CrossLens`, `StateWrap`, `FreshnessPill`)
   with all variants and tones. Build a Storybook page for each.
3. **Home view** — implement the landing surface. Real macro data wiring goes here.
4. **Plan · Ticket lens** (the most important lens — start here once grammar is in)
5. **Technicals + Chart lenses** — these need LightweightCharts for real OHLC.
6. **Remaining lenses** in the order in §3 — each one is a self-contained vertical
   scroll of sections following the grammar.
7. **Mode toggle wiring** — verify the Plan lens re-ranks correctly on
   SWING/POSITION/INVESTMENT.
8. **Theme picker** — wire `data-theme` switching via your settings store.
9. **Focus mode** — keyboard + button + scan-column collapse transition.
10. **Honesty contract** — go through every section and verify all four states
    work. This is the most important rule in the product.

Good luck. Reach out if anything's ambiguous.

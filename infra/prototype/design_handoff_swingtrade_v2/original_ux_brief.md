# SwingTrade V2 Dashboard — UX Designer Brief

**Audience:** UX/product designer rebuilding or extending the SwingTrade terminal.
**Purpose:** describe what the product is, who uses it, how it's organized, what each
surface does, and the design rules — so the interface can be (re)built faithfully.
**Last updated:** 2026-05-27 · maintained by the SwingTrade team.

> This brief documents the *current* canonical dashboard: `infra/prototype/kairos.html`
> served at `https://trade.mystockholding.com` (tunnel → `localhost:7432`). It is a
> single-page, dark-terminal app. There is no separate design file — this doc is the spec.

---

## 1. Product in one sentence

A **hedge-fund-grade swing-trading terminal** that scans the US equity universe daily,
scores every name on a 5-pillar model across multiple strategy "sleeves," and lets the
operator drill into any ticker through 14 analytical lenses to reach a disciplined
BUY / WATCH / SHORT / AVOID decision with a pre-placed, risk-first trade ticket.

It is **informational** — it never auto-trades. The user always makes the call; the
system surfaces the evidence and enforces the discipline (R:R floors, position caps,
Wilson-CI sample-size gates, stop placement).

---

## 2. Who uses it & what they're trying to do

| User | Account size | Primary job-to-be-done |
|---|---|---|
| **The owner** (power user) | $5K paper → live | "What's the single best risk-adjusted entry today, and what's the exact ticket?" |
| **Retail members** | $1K – $100K+ | "Is this name worth my limited capital, and how much should I size?" |

Design implications:
- **Decision-first, not data-first.** Every surface should answer a specific question
  (each tab carries its question in the nav tooltip — see §4).
- **Risk numbers come before reward numbers.** Position size, max loss, and stop must
  be visible *above* targets on any trade ticket.
- **Honesty over polish.** When a data feed is missing, show an explicit "no data" or
  "partial scaffolding" state — never a plausible-looking fake number. (This is a hard
  rule; see §7.)
- **Sample-size discipline is visible.** Win-rates and edge claims always show `n` and a
  Wilson 95% lower bound, with a red "n<30 ACT WITH CAUTION" pill below the floor.

---

## 3. Information architecture (two levels)

### Level 1 — Workspace (left sidebar)
Top-level surfaces, grouped:

- **Scan results:** Market Map (heatmap), Watchlist, Screener, Elite Picks, BUY
  candidates, Killed/AVOID, Industries, Themes, Leveraged, Crypto, Events (IPO/Splits),
  Pre-Market, Pairs.
- **Strategy & performance:** Strategies, Performance, Accuracy, Macro · Events,
  Options Flow, Alerts.
- **Knowledge:** Playbook (rulebook), Reference/Cheat, Thesis Library, Research.
- **Admin:** Settings, System Status, CapStudio (RBAC), Audit/Change History,
  Research Lab, Factor Exposure.

The **Market Map** (TradingView-style heatmap, sized by market cap, colored by daily %)
is the default landing surface.

### Level 2 — Detail page (opens on ticker click)
A persistent, resizable right-hand panel with **14 sub-tabs**. This is the heart of the
product and where most design effort should go. Each has a keyboard shortcut and a
one-line "question it answers":

| # | Sub-tab | Kbd | The question it answers |
|---|---|---|---|
| 1 | **Overview · Verdict** | 1 | Should I look closer? Master verdict + 5-pillar radar + pre-mortem + rule-engine + macro drill-downs |
| 2 | **Plan · Ticket** | 2 | Execution-ready ticket — entry / stop / size / targets / pre-mortem / order rules |
| 3 | **Chart** | 3 | Full OHLC chart with indicator overlays (EMAs, Fibs, SMC, VWAP) |
| 4 | **Technicals** | T | 10-section discipline view — indicators, S/R, stats, cross-source, pre-mortem, sizing |
| 5 | **Patterns** | 4 | Chart patterns — cup-and-handle, VCP, flag, triangle, breakout-base + Elliott/Wyckoff/Monte-Carlo |
| 6 | **SMC** | 5 | Smart Money Concepts — order blocks, CHoCH, BoS, FVG, liquidity sweeps |
| 7 | **Investment · Value** | V | Intrinsic value, margin-of-safety, 5-yr statements, quality, bull-vs-bear |
| 8 | **Risk** | R | VaR, Sharpe, drawdown, Kelly sizing, liquidity, stress scenarios |
| 9 | **Earnings** | E | ER countdown, implied-move cone, beat probability, ESP, 8-quarter history |
| 10 | **Options** | O | IV surface, max pain, unusual options activity, strategy matrix, payoff |
| 11 | **Portfolio** | P | Cap usage, held-state, correlation to book, factor tilt, sleep-test, simulator |
| 12 | **Tape · Flow** | I | Combined news + insider + sentiment + 13F + catalyst calendar |
| 13 | **Track Record** | 7 | Has this setup worked? Forward expectancy, walk-forward holdout, edge decay |
| 14 | **ML Edge** | M | 3-headed ML forecast — direction, magnitude cone, hit-net probability |

**Design note:** the sub-tab order is intentional — it follows the operator's funnel:
*screen → ticket → confirm technically → value-check → risk-check → catalyst-check →
verify edge*. Preserve this ordering.

---

## 4. The 14 lenses in detail

Each lens is a vertical scroll of "sections." A recurring layout grammar repeats across
all of them — **learn this grammar and the whole product becomes consistent:**

- **Hero band** at top: verdict/score, a key visual (gauge, radar, chart, or cone), and
  a 3–6 tile KPI strip.
- **Numbered sections** (`§1`, `§2`, …) each with a header (title + sub + freshness pill),
  a body (table / tile-grid / SVG viz), and an optional plain-English "read" note.
- **Cross-Lens row** near the bottom: a 5-cell strip showing how the *other* disciplines
  see this name (e.g., on the Risk lens: Risk / Value / Swing / Earnings / News). Conflicts
  are surfaced, not smoothed.
- **"The Call" footer:** a one-line verdict for that lens's time-horizon.

### Per-lens content (what data each shows)

1. **Overview** — verdict hero (score gauge + 5-pillar radar), KPI strip with sparklines,
   trigger/invalidate/sizing action rows, cross-tab confluence heatmap, sleeve attribution +
   mechanism hypothesis, stress-scenario matrix, pre-mortem banner, collapsible Rule-Engine
   (gate cascade audit) and Macro drill-downs.
2. **Plan · Ticket** — order ticket (action/symbol/order-type/TIF/limit/qty/stop/$risk/T1/T2/trail/time-stop),
   P&L profile, KPI tiles, sizing cascade waterfall (half-Kelly × regime × VIX × DD × β ×
   VaR × Sharpe), §1 price ladder, §2 size explorer, §3 invalidation ladder, §4 **time
   anatomy** (timeline scaled to hold-period), §5 reaction playbook, §6 pre-mortem, §7
   post-fill checklist.
3. **Chart** — full OHLC LightweightChart + HTF-bias strip.
4. **Technicals** — 10 sections: indicator dashboard (RSI/MACD/Stoch/ADX/MFI/CMF),
   EMA/SMA stack, pattern+signal detection, S/R confluence ladder, volume analytics,
   **statistical backbone (Wilson LB on this setup)**, cross-source confluence (6 lenses),
   regime-conditional edge (same setup across 4 regimes), pre-mortem, sizing+exits.
5. **Patterns** — method matrix, Wyckoff panel, Elliott-wave panel, Monte-Carlo panel,
   radar + structural levels, scenarios, action ladder, execution ticket.
6. **SMC** — order blocks, fair-value gaps, BoS/CHoCH structure, liquidity sweeps, VWAP,
   price-ladder SVG, LuxAlgo MTF screener. (Renders a TradingView chart of real bars.)
7. **Investment · Value** — value-gap hero (bear/fair/target/bull scale + MoS), §3 quality
   scorecard, §4 peer cohort, §5 5-year statements (revenue/GP/NI/FCF/buyback with
   sparklines), §6 capital allocation, §7 **bull-vs-bear cards**, §8 long-horizon catalyst
   calendar.
8. **Risk** — loss-distribution cones (1σ/2σ/3σ), live Kelly sizing metrics, VaR/CVaR,
   liquidity ladder, stress-scenario heatmap (6 scenarios × 5 outcomes), beta exposure.
9. **Earnings** — ER countdown + implied-move cone, ESP status, beat-probability,
   8-quarter beat/miss history, pre-ER drift, IV-crush projection.
10. **Options** — vol-regime cockpit, vol richness, flow (UOA), full chain grid, strategy
    matrix, profit calculator, payoff diagrams, scenario P&L, mgmt rules.
11. **Portfolio** — held-position state, position simulator (live R:R/sizing/NAV-risk),
    cap usage, correlation-to-book, factor exposure, tax-lot status, sleep-test, suitability.
12. **Tape · Flow** — 30-day news timeline, sentiment distribution, source distribution,
    insider Form-4 table, 13F holders, catalyst calendar.
13. **Track Record** — Wilson CI per setup, profit factor (raw + haircut), median R,
    edge-decay over trailing windows, KS drift, forward Monte-Carlo distribution.
14. **ML Edge** — 3-headed model: direction probability, magnitude cone, hit-net
    (P-T1-first − P-stop-first), with calibration.

---

## 5. Visual design language

Dark terminal aesthetic, copper accent. Two themes (dark default, light toggle).

**Color tokens** (CSS vars, dark theme):
| Token | Hex | Meaning |
|---|---|---|
| `--bg` / `--bg-0` | `#0a0d0c` | page background (near-black) |
| `--bg-1` / `--bg-2` / `--bg-3` | `#11151a` / `#161a1e` / `#1c2125` | card / panel / inset surfaces |
| `--line` / `--line-2` | `#262b2d` / `#353a3c` | borders |
| `--ink` / `--ink-1/2/3` | `#ecefe9` → `#686c68` | text, 4 emphasis levels |
| `--copper` | `#d97757` | **brand accent** — section numbers, active states, highlights |
| `--gn` | `#4ade80` | bullish / pass / good (with `--gn-bg`, `--gn-dim`) |
| `--rd` | `#f87171` | bearish / fail / risk |
| `--amb` | `#fbbf24` | neutral / caution / marginal |
| `--cy`, `--violet` | accent variants | secondary categorical (lens lead colors) |

**Typography:** JetBrains Mono (`--mono`) for all numbers, labels, and data;
system sans for prose. Tabular-nums everywhere numbers align in columns.
Uppercase + wide letter-spacing (`0.10–0.18em`) for labels and section headers.

**Component vocabulary** (reuse, don't reinvent):
- **Section header:** `§N` copper number + uppercase title + dim sub-line + freshness pill (right).
- **KPI tile:** label (uppercase, dim) / big value (color-coded) / sub-note.
- **Pill:** small rounded tag — green/red/amber/copper variants for status.
- **Data table:** dense, right-aligned numerics, color-coded `<b>` cells.
- **Tile grid:** 3/4/5/6-column responsive grids of KPI tiles.
- **Gauge / radar / cone / sparkline / heatmap:** inline SVG, no chart library except
  TradingView LightweightCharts for price.
- **Cross-Lens strip:** 5 equal cells, lead cell border-topped in the lens's accent color.

---

## 6. Interaction patterns

- **Click a ticker anywhere** (heatmap cell, watchlist row, BUY card) → opens the detail
  panel on the last-viewed sub-tab.
- **Sub-tab nav** is keyboard-driven (1–7, T/V/R/E/O/P/I/M) and click.
- **Mode toggle** (SWING / POSITION / INVESTMENT) re-ranks the verdict, stop, T1/T2, and
  hold-period on Plan/Overview without refetching — the same ticker reads differently per
  horizon.
- **Detail panel is resizable** (edge drag + S/M/L/XL presets).
- **Live polling:** intraday price updates ≤30s during market hours; each section shows a
  freshness pill (green ≤ threshold, red if stale).
- **Lazy data:** heavier sections (holders, financials, ML) fetch on first view and repaint;
  show a loading state, never a blank.

---

## 7. Critical states (do not skip these)

Every data-bound component must define **four** states. This is the most important rule
in the product — it is what separates this terminal from a demo.

1. **Live** — real per-ticker data. Default. Tag with a green/cyan "LIVE" or freshness pill.
2. **Loading** — async fetch in flight. Spinner or "Fetching from …" line. Never blank.
3. **Empty / No data** — the feed exists but this ticker has nothing (e.g., no insider
   buys, no options market). Show a centered, dim, italic message that names the source:
   *"No insider transactions for this ticker. Source: EODHD InsiderTransactions."*
4. **Partial scaffolding** — the section's layout is built but a feed isn't wired yet.
   Show an explicit **amber banner**: *"⚠ Partial scaffolding — Live: X, Y, Z. Demo: …
   until <feed> is wired."* Never let prototype/placeholder numbers masquerade as live.

**Why this matters:** the dashboard began as a prototype seeded with one example ticker
(AVGO/Broadcom). A large part of recent work was replacing those baked-in fixtures with
live per-ticker data and, where a feed genuinely doesn't exist yet, swapping the fake
numbers for honest empty/scaffolding states. A redesign must preserve this honesty
contract — a beautiful fake number is worse than an ugly "no data."

---

## 8. Data sources (so labels can cite them)

- **EODHD** — primary market data: OHLCV, fundamentals (Highlights, Valuation, Financials
  5yr, Holders, InsiderTransactions, Earnings history + analyst trend), news + sentiment,
  economic events, IPO/split calendar.
- **Schwab** — options chains + Greeks, quotes, movers, market hours.
- **Zacks** — rank, ESP, premium screens.
- **Scan output** (`cache/last_bundle.json`) — ~600 scored tickers/day, each with score,
  5-pillar breakdown, verdict, decisions-by-mode, kelly sizing, setup family, catalyst tags.
- **`setup_stats.json`** — Wilson-CI'd per-setup-family win-rate / PF / median-R / decay.
- **`ml_edge_predictions.json`** — per-ticker ML forecasts.
- **`portfolio_state`** — live positions, equity (NAV), cash.

Surface the source name in section sub-lines and empty states so the user always knows
where a number came from and can tell live from scaffold.

---

## 9. Design principles (non-negotiable)

1. **Decision-first.** Every surface answers one question. Lead with the verdict.
2. **Risk before reward.** Size and stop above targets, always.
3. **Honest states.** Live / loading / empty / scaffolding — never a plausible fake.
4. **Sample-size visible.** Show `n` and Wilson LB on every edge claim; flag `n<30`.
5. **Conflicts surfaced, not smoothed.** Cross-lens disagreement is a feature.
6. **Consistent grammar.** Reuse the section-header / KPI-tile / pill / table vocabulary.
7. **Mode-aware.** SWING vs POSITION vs INVESTMENT changes the read; respect the toggle.
8. **Dense but scannable.** This is a pro terminal — high information density, but every
   number color-coded and every section skimmable via its header + read-note.

---

## 10. What to deliver (suggested designer outputs)

1. A **component library** for the recurring grammar in §5 (section header, KPI tile,
   pill, data table, tile grid, cross-lens strip, the four states from §7).
2. **Hi-fi mocks of the detail page** for 2–3 representative sub-tabs (suggest: Plan ·
   Ticket, Technicals, Investment · Value) covering all four states each.
3. The **Market Map** landing surface.
4. A **light-theme** pass of the above (the app supports a theme toggle).
5. **Responsive behavior** for the resizable detail panel at S/M/L/XL widths.

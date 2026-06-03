# BullVeda Data-Freshness Spec — how & when every tab refreshes

**Owner:** phanirajgarimella · **Created:** 2026-06-03 · **Status:** design (live wiring in progress)

The dashboard has ~30 main tabs and several hundred sub-sections. Rather than spec each
individually, every surface is assigned to one of **8 refresh classes**. A class defines
*how* (source + mechanism) and *when* (cadence/trigger). To know any tab's freshness,
find its class.

---

## The 8 refresh classes

| # | Class | How (source + mechanism) | When (cadence/trigger) | Cost |
|---|-------|--------------------------|------------------------|------|
| **L** | **LIVE** | Schwab L1 quote channel → server pushes quote → **client recomputes** all price-relative fields | every **10–20s** while market open (portfolio/watchlist 10s, scanner 20s, open-detail 5s) | Schwab only (off EODHD); ~1–3 req/refresh |
| **S** | **SCAN** | Full scan pipeline writes `last_bundle.json` → `build_data.py` → BullVeda re-pulls bundle | **5×/day**: 05:15 heavy · 07:00 · 09:30 · 11:30 · 13:30 light | EODHD (the metered one) |
| **O** | **OPTIONS-SESSION** | Schwab options (chain/IV/gamma) → options-flow refresh | every **15–30 min** during RTH | Schwab only |
| **N** | **NEWS** | EODHD news + social scrapes | every **2–4h** (RTH 4h cache) | EODHD news (cheap) + free scrapes |
| **W** | **WEEKLY** | EODHD fundamentals → `enrich-fundamentals-weekly` | **Saturday 03:00** (6-day TTL) | EODHD ~3K/week |
| **D** | **DAILY-BUILD** | Morning heavy-scan side-builders (calendar/membership/themes) | **05:15 only** (HOUR<7 gate) | EODHD small + free |
| **P** | **ON-OPEN** | When a detail panel/tab opens → fetch that ticker's fresh quote + stale-check options/news | **on user open**, then class-L while open | Schwab + lazy EODHD |
| **X** | **STATIC** | Build-time content; changes only on deploy/config | on rebuild / config save | none |

**The core mechanism (class L):** the scan computes *levels* (entry, stop, targets, EMAs, 52w
range, ATR). The live channel pushes only *price*. The client then recomputes everything
price-relative for free — R:R, distance-to-entry/stop/target, "in zone?", P&L, 52w marker,
market cap, % from each EMA. One quote → dozens of live fields, zero per-field API.

---

## Main tabs → refresh class

| Tab | Primary class | What's live (L) vs scan (S) vs slower |
|---|---|---|
| **Market Map** (state/hero/index/opportunity/setups/discovery/movers/attention) | **L + S** | index strip + movers + price = L; regime/funnel/setups/opportunity = S |
| **Watchlist** | **L + S** | price/%chg/RVOL/dist = L; score/verdict/setup = S |
| **Screener** | **L + S** | price/%chg = L; all scores/filters/ranks = S |
| **Elite Picks** | **L + S** | price/live-R:R/dist-to-entry = L; conviction/factors/narrative = S |
| **Bullish candidates (buy)** | **L + S** | price/R:R/P&L = L; score/gates/plan = S |
| **Excluded (killed)** | **S** | kill reasons + scores = S (price L if shown) |
| **Industries** | **D + S** | sector heatmap/leadership = D (morning); RS ranks = S |
| **Themes** | **D** | ETF-holding baskets = morning build |
| **Leveraged** | **L + S** | price/NAV = L; picks/ranks = S |
| **Crypto** | **L + S** | price = L (Schwab/feed); ranks = S |
| **Events · IPO/Splits** | **D** | calendar = morning build (next 30d) |
| **Pre-Market** | **L + D** | pre-market quotes = L (Schwab ext-hours); gap board = D/premarket-scan |
| **Pairs** | **L + S** | spread/z-score = L (from live prices); pair ranks = S |
| **Strategies** | **S** | sleeve stats/activation = S; setup-family WR = S |
| **Performance** | **S** | P&L tiles/equity/attribution = S (per scan); closed trades = S |
| **Accuracy** | **S** | calibration/Kupiec/Basel = S |
| **Macro · Events** | **D + N** | macro calendar = D; macro wire = N |
| **Options Flow** | **O** | UOA/sweeps/net-premium = O (15–30 min) |
| **Alerts** | **L + S** | threshold crossings eval on L price; alert list = S |
| **Playbook** | **X** | static rulebook |
| **Reference / Cheat** | **X** | static |
| **Thesis Library** | **S** | per-ticker theses = S |
| **Research** | **S** | research notes = S |
| **Settings** | **X** | config (save-triggered) |
| **System Status** | **special** | data-health/quota/job-status — see note below |
| **CapStudio · RBAC** | **X** | capability matrix (config) |
| **Audit · Change Hx** | **S** | audit ledger rebuilt every scan |
| **Research Lab** | **S/on-demand** | diagnostic endpoints, refresh on run |
| **Factor Exposure** | **S** | factor attribution = S |
| **Earnings** | **D + N + S** | calendar = D; beat-predict = morning; reporters = S |
| **Portfolio (book)** | **L + S** | live P&L/exposure/marks = L; closed journal = S |

**System Status special case:** quota counter + per-job last-run + data-health should refresh
on a **light timer (60s)** independent of scans (it's monitoring, not market data) — cheap,
reads local state + 1 quota sync.

---

## Per-ticker detail sub-tabs → refresh class

The detail panel opens via class **P** (on-open fresh quote), then individual sub-tabs:

| Detail sub-tab | Class | Live fields (L) | Scan/slower fields |
|---|---|---|---|
| **Overview · Bias** | **L + S** | price, %chg, RVOL, live R:R, 52w marker, dist-to-entry | score, verdict, gates, RSI/MACD values |
| **Plan · Ticket** | **L + S** | "in entry zone?", dist-to-stop/target, live R:R, live P&L | setup, entry/stop/target levels, sizing, invalidation, narrative |
| **Chart** | **L + S + (intraday)** | price marker, vs-VWAP | OHLCV bars (S); 1H/4H intraday (every 30–60 min) |
| **Technicals** | **L + S** | price vs EMA/SMA distances | EMA stack, RSI/StochRSI/MACD/MFI/CMF, ATR/Bollinger, MA alignment |
| **Patterns** | **S** | — | classical/harmonic/Elliott/Wyckoff/Gann/Wolfe/Ichimoku (close-based) |
| **SMC** | **S** | — | order blocks, FVG, BOS/CHoCH, liquidity sweeps, premium/discount, OTE (close-based) |
| **Investment · Value** | **W + L** | price vs intrinsic (uses live price) | intrinsic value/5y, margin of safety, valuation = W |
| **Earnings (detail)** | **D + N + S** | — | beat probability, 8-qtr history, EPS revisions, ER countdown/cone |
| **Risk** | **L + S** | live VaR/exposure (uses live price) | sizing policy, stress heatmap, loss cones, liquidity ladder |
| **Options** | **O** | — | chain, IV rank/term, skew, gamma, max pain, spreads, tickets (15–30 min) |
| **Tape · Flow** | **O + L** | time & sales prints = L-ish (Schwab) | block trades, sweeps, net-premium = O |
| **AI Edge (ML)** | **S** | — | ML forecast (dir/mag/hit), features, model registry (per scan) |
| **Time Anatomy** | **S** | — | survival table lookup (regime-conditioned, per scan) |
| **Thesis** | **S** | — | mechanism, falsifier, scenario tree |
| **Models & regime** | **S** | — | regime model, sequence model, ensemble |

---

## Implementation status (2026-06-03)

| Piece | Status |
|---|---|
| Class S (5×/day scan) | ✅ live (deployed today) |
| Class W (Saturday fundamentals) | ✅ live (deployed today) |
| Class D (morning builders) | ✅ live (heavy-scan gated) |
| Class L (live Schwab quotes) | 🔨 to build — `/api/live_quotes` + client recompute |
| Class O (options session refresh) | 🔨 to build — 15–30 min Schwab options timer |
| Class N (news 2–4h) | ✅ partial (cache TTL); auto-surface to build |
| Class P (on-open fresh) | 🔨 to build — detail-open quote fetch |
| Switch `/api/ticker` quote EODHD→Schwab | 🔨 to do (off-budget + real-time) |

## Budget summary
- **EODHD** (metered, 95K/day): only classes S, W, D, N spend it → **~7K/day floor** after fixes.
- **Schwab** (no daily cap, ~120/min): classes L, O, P → trivial (batched 500/req).
- **Free**: social scrapes (N), local state (Status).

All cadences are config knobs (see `config/config.json` → `freshness` block, to be added).

---

# PERMANENT Provider-Routing Policy (the durable contract)

**Problem this fixes:** on 2026-06-03 EODHD hit 100% by 09:30 and the scan aborted. Root
cause was *routing*, not volume — fundamentals were re-fetched nightly (~62K/night), live
quotes spent EODHD on every click, and ml-edge cold-fetched the whole universe. The rule
below is permanent: **EODHD is the scarce resource; route everything possible off it.**

## The iron rule
> **EODHD (95K/day, metered) is used ONLY for what no other source provides.**
> **Schwab (no daily cap) carries ALL live/quote/options data.**
> **Free sources carry sentiment, insider, IPO, membership.**
> Target sustained EODHD spend: **≤ 15K/day** (≈6× headroom to the 85K throttle).

## Permanent provider assignment (by data type — never re-route without updating this)

| Data type | Provider | Why permanent | Enforcement point |
|---|---|---|---|
| Live price / %chg / quote | **Schwab** | no daily cap; real-time | `/api/live_quotes`, `/api/ticker` (Schwab-primary), `BV.fetchLive` |
| Options chain / IV / gamma / flow | **Schwab** | off-budget; 15-min refresh | `/api/options`, `refresh_options_flow.py` (StartInterval 900s) |
| Daily/weekly OHLCV | **EODHD** | sole source; **1 bulk call/day** | `bulk_eod` (7200s TTL) |
| Fundamentals | **EODHD** | sole source; quarterly | **Saturday-only** (`enrich-fundamentals-weekly`, 6-day TTL) |
| News + sentiment | **EODHD news** | adequate; 4h TTL | scan + `/api/news` |
| Earnings calendar / EPS | **EODHD** | sole source; 6h TTL | morning builders |
| WSB / retail sentiment | **ApeWisdom (free)** | Reddit `.json` 403s now | `build_retail_sentiment.py` |
| StockTwits sentiment | **StockTwits (free)** | public API works | `build_retail_sentiment.py` |
| Insider clusters | **openinsider (free)** | pre-aggregated, 1 call vs 3000 EODHD | `build_universe_insider_cluster.py` (EODHD fallback) |
| IPO / splits calendar | **EODHD** | works (8+31/day); EDGAR S-1 if it thins | `fetch_corporate_events.py` |
| Index membership | **Wikipedia (free)** | point-in-time snapshots | `snapshot_membership.py` |
| ML forecasts | **Local models** | compute on cached features | `ml.run_ml_edge --universe bundle` |
| SMC / patterns / time-anatomy / scoring | **Local compute** | no API | client + scan engine |

## Permanent EODHD-conservation rules (enforced, not advisory)

1. **Never spend EODHD on a live quote.** All quotes → Schwab. (`/api/ticker` Schwab-primary, 2026-06-03.)
2. **Fundamentals fetch once per week (Saturday), never nightly.** (`enrich-nightly --skip-fundamentals`; `enrich-fundamentals-weekly` Sat 03:00.)
3. **ml-edge reads the bundle, never cold-fetches `--universe all`.** (`com.swingtrade.ml-edge` → `bundle`.)
4. **Scans = 1 heavy + 4 light/day.** Heavy deep-enriches ≤1500; light deep-enriches ≤150. (`run_daily_scan.sh` clock gate.)
5. **No redundant nightly enrich.** `full-enrich-nightly` retired; folded into 05:15 heavy.
6. **Budget guard stays on:** throttle ≥85%, abort ≥97% (`eodhd_quota` config). The guard is the backstop, not the plan.
7. **No manual full scans during the day.** Use `swing_trade.py regen` (0 EODHD) to rebuild the dashboard from the last bundle.

## Steady-state daily EODHD budget (post-fix)

| Consumer | Calls/day | Notes |
|---|---|---|
| `enrich-nightly` (tech-only weeknights) | ~60–260 | bulk_eod + calendar bulks |
| `enrich-fundamentals-weekly` (Sat only) | ~3,000 / **7** ≈ 430 avg | amortized |
| Heavy scan 05:15 | ~1,500 | fundamentals warm from Sat |
| 4 light scans | ~2,400 | ~600 each |
| ml-edge (bundle) + intraday | ~600 | |
| news / iv / misc | ~1,000 | |
| **Total** | **≈ 6–9K/day** | **vs 95K cap → ~10× headroom** |

Schwab (live quotes, options) and free sources (WSB/insider/membership) add **zero** to this.

**Review trigger:** if EODHD sustained spend exceeds ~20K/day, something re-routed wrong —
check this table first. The provider for each data type is fixed; only cadence is tunable.

---

# Per-surface API cost + data risk (2026-06-03)

The principle after the routing fix: **interaction is free; only scanning costs EODHD.**
Clicking around the dashboard = ~1 Schwab call (live quote) + ~0 EODHD (detail renders
from bundle/cache; ML/SMC/technicals are local compute).

## Left-nav surfaces

| Surface | Provider(s) | Cadence | API calls/update | Risk |
|---|---|---|---|---|
| Home / Market Map | scan + Schwab | 30min; price 10–20s | Schwab ~1 · EODHD 0 | Low |
| Signal Scanner | scan + Schwab | 30min; price 20s | Schwab 1–3 batch · EODHD 0 | Low |
| Themes | EODHD ETF | 1×/day | EODHD ~25 | Med (daily) |
| Sectors · ETFs | EODHD | 1×/day+scan | EODHD ~22 | Low |
| Pre-Market | Schwab ext-hrs | 05:30/06:00 | Schwab 1 · EODHD 0 | Med |
| Upcoming IPOs | EODHD calendar | 1×/day | EODHD ~2 | **High — sparse source** |
| Crypto Market | EODHD + list | 30min | EODHD ~20 | **High — no 24/7 feed** |
| News · Sentiment | EODHD news + StockTwits/ApeWisdom | 2–4h / build | EODHD ~few-hundred (cached) · free 1–9 | Med — scrape fragility |
| Momentum | scan + local | 30min + 08:00 | EODHD 0 (in-scan) | Low |
| Earnings AI | EODHD + Zacks(Gmail) + local | morning | EODHD ~10 · Gmail 0 | Med |
| ML Predictions | local models | 30min / daily retrain | **0 API** | Med — model drift (monitored) |
| Options Flow | Schwab options | 15min | Schwab ~30–60 · EODHD 0 | Low |
| Insider Trading | openinsider (+EODHD fallback) | weekly+scan | **1 free call** (3000 EODHD only on scrape fail) | Med — scrape fragility |
| SMC / Patterns | local smc_engine | 1×/day | **0** (cached bars) | Med — daily-stale |
| Strategies · Backtest | local + EODHD | scan / Sun | EODHD heavy Sun only | Med — backtest caveats |
| Automated Trade | Alpaca paper | 06:35+10min | Alpaca · EODHD 0 | Med — PAPER only |
| My Portfolios | Alpaca + Schwab | sync+10–20s | Alpaca 1 + Schwab 1 · EODHD 0 | Low |
| Book Risk | Alpaca + local | scan | Alpaca 1 · EODHD 0 | Low |
| Track Record | local logs | 30min | **0 API** | Med — WATCH-entry bias |
| Playbook/Settings/Users/Status/Help | static/config/local | manual/60s | 0–1 | Low |

## Detail sub-tabs (per ticker open)

| Sub-tab | Provider(s) | Cadence | API calls/open | Risk |
|---|---|---|---|---|
| 01 Overview | scan+ML+Schwab | 30min; 5s | Schwab 1 · EODHD 0–1 · ML 0 | Low |
| 02 Plan | scan+Schwab | 30min; 5s | Schwab 1 · EODHD 0 | Low |
| 03 Chart | EODHD bars | on-open+lazy | EODHD 0 cached / 1 cold | Med |
| 04 Technicals | EODHD→local | 30min | 0 (cached) | Low |
| 05 Patterns | local | 30min | 0 | Med — heuristic |
| 06 SMC | local smc_engine | daily | 0 (cached bars) | Med |
| 07 Investment·Value | EODHD fundamentals | weekly | EODHD 0 cached / 1 cold | Med — ≤7d stale (OK) |
| 08 Earnings | EODHD+Zacks+local | daily | EODHD 0–1 | Med |
| 09 Risk | local+Alpaca+Schwab | 30min/live | Schwab 1 · EODHD 0 | Low |
| 10 Options | Schwab chain | 15min | Schwab 1–2 (2h cache) · EODHD 0 | Low |
| 11 Tape · Flow | Schwab+local | 15min | Schwab 1–2 · EODHD 0 | Med |
| 12 AI Edge | local models | 30min | **0 API** | Med — drift |
| 13 Time Anatomy | local table | scan lookup | **0 API** | Med — base-rate not prediction |

## Risk map — what to watch
- **High:** IPOs (sparse — EDGAR S-1 backstop not yet wired), Crypto (no 24/7 feed).
- **Med — scrape fragility:** News/social (ApeWisdom/StockTwits), Insider (openinsider) — free, no SLA, can silently empty on site changes (each has a fallback + honest empty-state).
- **Med — model:** ML Edge, Time Anatomy, beat-predict — estimates, not facts; ML drift monitored + retrained daily.
- **Med — discipline:** Track Record (WATCH-entry bias), Strategies (survivorship haircut).
- **Low:** Scanner, Plan, Options, Portfolio, live prices (Schwab + scan-fresh + real broker).

## Two structural risks
1. **Free-scrape fragility** — News/social + insider ride free third-party sources with no SLA. Mitigated by fallbacks + honest "—".
2. **EODHD-dependence when maxed** — anything EODHD-sourced freezes if quota maxes (happened 2026-06-03). The routing fix keeps daily spend ~8K (10× headroom) so it shouldn't recur; live data moved to Schwab to decouple.

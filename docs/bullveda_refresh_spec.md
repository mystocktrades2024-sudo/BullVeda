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

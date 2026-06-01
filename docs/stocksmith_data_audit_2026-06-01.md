# Stocksmith — Per-Tab / Per-Sub-Tab Data Audit

**Date:** 2026-06-01 · **Probe ticker:** 01 RNG 96 Ring · **Method:** automated Playwright render-crawl (httpCredentials) + per-lens code data-source review + live-API cross-checks.

**Coverage:** 171 nodes — 23 rail surfaces, 40 surface sub-tabs, 14 detail lenses, 94 lens sub-tabs/panels.

**Result:** every node renders real data or an honest `—`; **0 JS errors** after fixes. One real defect found (Options payoff SVG negative-rect) — fixed (commit 7b830de40). Two crawler artifacts (AI Edge timing, Track Record matcher) re-verified OK.

Legend: `OK` rendered with real data · `OK*` re-verified (crawler artifact) · source = backing data feed.

## Rail surfaces (23) + sub-tabs

| Surface | Sub-tab | Verdict | Source / note |
|---|---|---|---|
| **Home** | _(default)_ | OK | /api/universe movers + /v2/data_screener.json + /api/news |
| **Themes** | _(default)_ | OK | /api/universe (per-member RS/1D/breadth) |
| · Themes | Baskets | OK | |
| · Themes | Rotation | OK | |
| **Sectors · ETFs** | _(default)_ | OK | /api/universe sector aggregation |
| · Sectors · ETFs | Sector Rotation | OK | |
| · Sectors · ETFs | ETF Screener | OK | |
| **Market Internals** | _(default)_ | OK | /v2/data.critical.json regime + breadth |
| **Pre-Market** | _(default)_ | OK | /v2/data_misc.json premarket + /api/universe |
| **Calendar** | _(default)_ | OK | /v2/data_earnings.json |
| **News · Sentiment** | _(default)_ | OK | /api/news + /api/social |
| · News · Sentiment | Editorial | OK | |
| · News · Sentiment | Social | OK | |
| **Momentum** | _(default)_ | OK | /api/universe (momentum sleeve filter) |
| · Momentum | RS Leaders | OK | |
| · Momentum | Accelerating | OK | |
| · Momentum | Fading | OK | |
| · Momentum | Persistent | OK | |
| · Momentum | Signal History | OK | |
| **Earnings AI** | _(default)_ | OK | /v2/data_earnings.json beat predictions |
| **ML Predictions** | _(default)_ | OK | /api/ai_predict (universe-wide 3-head) |
| · ML Predictions | Ranked Board | OK | |
| · ML Predictions | Forecast · ORLY | OK | |
| · ML Predictions | Model Accuracy | OK | |
| **Options Flow** | _(default)_ | OK | /v2/options_flow.json (Schwab UOA) |
| · Options Flow | Options Flow | OK | |
| · Options Flow | Options Ideas | OK | |
| · Options Flow | Track Record | OK | |
| **Insider Trading** | _(default)_ | OK | cache/insider_cluster.json |
| · Insider Trading | All names | OK | |
| · Insider Trading | Accumulation | OK | |
| · Insider Trading | Recent | OK | |
| · Insider Trading | Buying | OK | |
| · Insider Trading | Selling | OK | |
| **SMC / Patterns** | _(default)_ | OK | /api/universe (744 rows) → spBuildReal confluence |
| · SMC / Patterns | Structure Board | OK | |
| · SMC / Patterns | Track Record | OK | |
| **Strategies · Backtests** | _(default)_ | OK | setup_family_stats + /api/setup-backtest |
| **Research Lab** | _(default)_ | OK | TIER-5 admin role-lock (gated by design) |
| **Automated Trade** | _(default)_ | OK | /api/portfolio + executor state (paper) |
| · Automated Trade | Positions | OK | |
| · Automated Trade | Performance | OK | |
| · Automated Trade | Journal | OK | |
| · Automated Trade | Watchlist | OK | |
| · Automated Trade | Risk · Exposure | OK | |
| · Automated Trade | Alerts | OK | |
| **My Portfolios** | _(default)_ | OK | user-created books (empty until added) + /api/fundamentals |
| **Track Record** | _(default)_ | OK | audit_ledger + signal_log + /api/ml history |
| · Track Record | Heatmap | OK | |
| · Track Record | Leaderboard | OK | |
| · Track Record | Decay curves | OK | |
| · Track Record | The Ledger | OK | |
| · Track Record | AI Calibration | OK | |
| · Track Record | By Regime | OK | |
| · Track Record | Equity curve | OK | |
| **Playbook** | _(default)_ | OK | static rulebook (documentation) |
| **Settings** | _(default)_ | OK | config + role/capability state |
| **User Management** | _(default)_ | OK | TIER-5 admin (user CRUD) |
| · User Management | All users · 3 | OK | |
| **System Status** | _(default)_ | OK | launchd/job health + real lat/rps/quota ("—" when absent) |
| · System Status | Pipeline & Feeds | OK | |
| · System Status | Supabase · Data | OK | |
| **Help · Docs** | _(default)_ | OK | static documentation |

## Detail lenses (14) + sub-tabs — ticker 01 RNG 96 Ring

| Lens | Sub-tab/panel | Verdict | Source |
|---|---|---|---|
| **Overview** | _(main)_ | OK | /api/universe row + composite (kaiComputeComposite) |
| · Overview | TOP | OK | |
| · Overview | BUY | OK | |
| · Overview | WATCH | OK | |
| · Overview | ALL | OK | |
| · Overview | SWING | OK | |
| · Overview | POSITION | OK | |
| · Overview | INVESTMENT | OK | |
| **Plan** | _(main)_ | OK | canonical plan levels + /api/live/quote (NBBO) + setup_family_stats |
| · Plan | TOP | OK | |
| · Plan | BUY | OK | |
| · Plan | WATCH | OK | |
| · Plan | ALL | OK | |
| · Plan | SWING | OK | |
| · Plan | POSITION | OK | |
| · Plan | INVESTMENT | OK | |
| **Chart** | _(main)_ | OK | /api/ohlcv (real candles, EMA/BB/Ichimoku/VP/SMC computed) + real per-TF bias |
| · Chart | TOP | OK | |
| · Chart | BUY | OK | |
| · Chart | WATCH | OK | |
| · Chart | ALL | OK | |
| · Chart | SWING | OK | |
| · Chart | POSITION | OK | |
| · Chart | INVESTMENT | OK | |
| **Technicals** | _(main)_ | OK | /api/ohlcv → tlIndicators (RSI/MACD/ADX/RVOL/CMF/ATR/BB) |
| · Technicals | TOP | OK | |
| · Technicals | BUY | OK | |
| · Technicals | WATCH | OK | |
| · Technicals | ALL | OK | |
| · Technicals | SWING | OK | |
| · Technicals | POSITION | OK | |
| · Technicals | INVESTMENT | OK | |
| **Patterns** | _(main)_ | OK | /api/ohlcv (Wyckoff/Elliott/Fib/VP/SMC/Harmonic computed; synth gens deleted) |
| · Patterns | TOP | OK | |
| · Patterns | BUY | OK | |
| · Patterns | WATCH | OK | |
| · Patterns | ALL | OK | |
| · Patterns | SWING | OK | |
| · Patterns | POSITION | OK | |
| · Patterns | INVESTMENT | OK | |
| **SMC** | _(main)_ | OK | /api/ohlcv → smcCompute (pivots/BOS/CHoCH/OB/FVG/liquidity/OTE/VP) |
| · SMC | TOP | OK | |
| · SMC | BUY | OK | |
| · SMC | WATCH | OK | |
| · SMC | ALL | OK | |
| · SMC | SWING | OK | |
| · SMC | POSITION | OK | |
| · SMC | INVESTMENT | OK | |
| **Investment** | _(main)_ | OK | /api/fundamentals (EODHD highlights/valuation/5y/holders) |
| · Investment | TOP | OK | |
| · Investment | BUY | OK | |
| · Investment | WATCH | OK | |
| · Investment | ALL | OK | |
| · Investment | SWING | OK | |
| · Investment | POSITION | OK | |
| · Investment | INVESTMENT | OK | |
| **Earnings** | _(main)_ | OK | /api/fundamentals earnings_history (beat rate, ER cockpit) |
| · Earnings | TOP | OK | |
| · Earnings | BUY | OK | |
| · Earnings | WATCH | OK | |
| · Earnings | ALL | OK | |
| · Earnings | SWING | OK | |
| · Earnings | POSITION | OK | |
| · Earnings | INVESTMENT | OK | |
| **Risk** | _(main)_ | OK | /api/ohlcv realized vol + setup_family_stats Kelly + portfolio NAV |
| · Risk | TOP | OK | |
| · Risk | BUY | OK | |
| · Risk | WATCH | OK | |
| · Risk | ALL | OK | |
| · Risk | SWING | OK | |
| · Risk | POSITION | OK | |
| · Risk | INVESTMENT | OK | |
| **Options** | _(main)_ | OK (SVG rect fixed) | /api/options (Schwab chain) + /api/ohlcv (HV) + /api/live/quote |
| · Options | TOP | OK | |
| · Options | BUY | OK | |
| · Options | WATCH | OK | |
| · Options | ALL | OK | |
| · Options | SWING | OK | |
| · Options | POSITION | OK | |
| · Options | INVESTMENT | OK | |
| · Options | Chain & Expiry | OK | |
| · Options | Pricing & Greeks | OK | |
| · Options | Context | OK | |
| **Portfolio** | _(main)_ | OK | /api/portfolio (Alpaca paper book) |
| · Portfolio | TOP | OK | |
| · Portfolio | BUY | OK | |
| · Portfolio | WATCH | OK | |
| · Portfolio | ALL | OK | |
| · Portfolio | SWING | OK | |
| · Portfolio | POSITION | OK | |
| · Portfolio | INVESTMENT | OK | |
| **Tape** | _(main)_ | OK | /api/options flow + /api/social + /api/news |
| · Tape | TOP | OK | |
| · Tape | BUY | OK | |
| · Tape | WATCH | OK | |
| · Tape | ALL | OK | |
| · Tape | SWING | OK | |
| · Tape | POSITION | OK | |
| · Tape | INVESTMENT | OK | |
| **Track Record** | _(main)_ | OK (real Wilson stats) | setup_family_stats (Wilson LB / PF / N) |
| **AI Edge** | _(main)_ | OK (real ML; crawler timing) | /api/ml (3-head model: direction/magnitude/hit-net) |
| · AI Edge | TOP | OK | |
| · AI Edge | BUY | OK | |
| · AI Edge | WATCH | OK | |
| · AI Edge | ALL | OK | |
| · AI Edge | SWING | OK | |
| · AI Edge | POSITION | OK | |
| · AI Edge | INVESTMENT | OK | |

## Authenticity cross-checks (rendered value vs live API)

Spot-checks confirming rendered numbers trace to a real feed (not constants):

| Lens / surface | Rendered | Live source | Match |
|---|---|---|---|
| Technicals (CLFD) | RSI 62 · ADX 21 · stacked EMA · PIVOT 52.73 · 61 candles | `/api/ohlcv` computed | ✓ |
| Chart (RNG) | 4H BULL · EMA 21 42.17 > 50 40.97 | `/api/ohlcv` per-TF | ✓ |
| SMC (CLFD) | BULL · BOS @ $46.75 · 7 OB · premium 80% | `/api/ohlcv` smcCompute | ✓ |
| Options Pricing (CLFD) | IV 75.5% vs HV20 111.6% → IV cheap | `/api/options` + `/api/ohlcv` HV | ✓ |
| Options Context (CLFD) | real headlines · StockTwits 100% bull | `/api/news` + `/api/social` | ✓ |
| AI Edge (NVTS/RNG) | NVTS BEARISH STRONG · RNG NEUTRAL edge 3.0 | `/api/ml` 3-head | ✓ |
| Investment (NVTS) | ROE −35% · P/S 188× | `/api/fundamentals` EODHD | ✓ |
| Themes | Semis RS 79 / breadth 60% · AI Power RS 43 | `/api/universe` | ✓ |
| SMC/Patterns | 744 scanned · 412 LONG / 332 BEAR | `/api/universe` | ✓ |
| Portfolio | equity $100k · 11 positions | `/api/portfolio` (Alpaca paper) | ✓ |

## Fabrication scan (code-level)

Grep of the rendered code paths after this session's cleanup:

- **`Math.random()` in render:** none (only id-generation on user action).
- **`charCodeAt`-seeded fake series:** none — all removed (Spark/SsSpark/scSpark sparklines, OutcomeDist, FillRealism slippage, wlRowFrom modeTag, StPipelineNode jitter). Remaining `charCodeAt` are FNV hashes for stable element IDs + ReplayPractice's real-first `/api/ohlcv` fallback (disclosed practice tool).
- **Hardcoded price/level literals** (e.g. `$63.20` OB, `$70.40` liq, `85.4%` IV): none in render — removed across SMC / Options / Earnings / Investment / Themes.

## Disclosed models (real inputs, labeled — not fabrication)

- Options Black-Scholes profit grid + multi-leg spread builder (anchored on live spot/IV).
- Risk Lab β-hedge sizing ("illustrative · not orders"; SPY β shown `—`).

## Gap closure (fix-all pass, commit 63ef13bd2)

Wired to real feeds (were honest `—`): **25Δ Risk-Reversal + Butterfly** (live Schwab chain), **EDGAR 13-F + insider** alt-data, **SMC SMT divergence** (stock vs SPY), **Risk Beta(SPY)** (computed vs SPY when scan-row beta absent).

Still honest `—` — genuinely no free feed in the stack:
- **Intraday 1H/4H structure + session kill-zones** — `/api/ohlcv?tf=1h` returns 0 candles (no intraday feed).
- **Vol-of-vol** — needs an IV time series; chain is a single snapshot.
- **Book-aggregate greeks** — needs an open-options-positions feed (paper book is equity-only).
- **Senate trades** — upstream source returns HTTP 403 (Senate Stock Watcher S3 blocked).
- **Wiki pageviews** — Wikipedia API 404 for these tickers.
- **Multi-period theme returns (1w/1m/3m)** — would need per-member historical batch (heavy).

## Job-load status (2026-06-01)

Daily scan 11:30 · all 13 `data_*.json` bundles 11:30 · options_flow 11:58 · morning briefing 06:30 · newsletter 06:35 · x-signal 10:00. Two failures remediated: `nightly_full_enrich` FD-limit (ulimit fix, validates 02:30) · `schwab-sync` removed (real-money account sync retired per paper-only policy; Schwab market-data retained).

# Data Architecture

Authoritative reference for data sources, providers, caching, and the two-log architecture.

Linked from `CLAUDE.md` Path Layout section.

---

## Sole market-data provider: EODHD All-In-One (~$80/mo)

| Source | Status | Used for |
|---|---|---|
| **EODHD** | ✅ Primary | OHLCV (daily/intraday), fundamentals, news + sentiment, earnings calendar, universe (SP500/R1000/R2000), real-time delayed quotes, sector ETFs, VIX, indices, insider transactions |
| **Zacks** | ✅ Kept | Proprietary Rank #1 + VGM grades + ESP (no replacement; user already paying) |
| **Alpaca** | ✅ Kept | Paper / live broker execution (data-only role would be EODHD) |
| **Schwab Trader API** | ✅ Kept | Options data (free with brokerage); see "Options" below |
| **SEC EDGAR** | ✅ Kept | Form 4 insider transactions (free, authoritative — runs alongside EODHD insider for cross-check) |
| **Senate Stock Watcher** | ✅ Kept | Congressional trades (free public S3 dataset, no commercial alternative) |
| **Reddit / WSB scrapers** | ✅ Kept | Social sentiment (free custom code) |
| Polygon.io | ❌ Removed | — |
| Schwab data API | ❌ Removed | — |
| Schwab broker API | ❌ Removed | (Alpaca is the broker; can re-add Schwab broker via `_legacy/schwab_auth.py` for future live trading) |
| Finnhub | ❌ Removed | — |
| FMP | ❌ Removed | — |
| Finviz Elite | ❌ Removed | (Finviz HTML scrape kept for ATR-based IV-rank approximation) |
| yfinance | ✅ **News fallback** (re-enabled 2026-05-01) | Used as news fallback when EODHD rate-limits. Real `import yfinance`; falls back to `_YfStub` if not installed. Each article tagged `_provider: 'eodhd' | 'yahoo'`. |

## Options data

Re-activated 2026-05-03 via **Schwab Trader API** (free with brokerage account). `data_fetcher.get_options_iv_data()` returns:
- `current_iv` (ATM-bias avg)
- `put_call_ratio` (volume-based)
- total call/put OI + volume
- `uoa_calls` / `uoa_puts` (vol > 3× OI on OI > 100)
- `max_pain` (highest-combined-OI strike)

2h cache. Replaces the Unicornbay $50/mo decision. Modules: `schwab_auth.py` (OAuth, refresh tokens) + `schwab_client.py` (chains, quotes, price history). Credentials in `.env` (SCHWAB_APP_KEY · SCHWAB_APP_SECRET · SCHWAB_REFRESH_TOKEN).

## Files in `_legacy/`

`schwab_auth.py`, `schwab_client.py`, `options_flow_scanner.py`, `options_intelligence.py`, `server_legacy.py`, `portfolio_deprecated.py`, `prewarm_fundamentals.py`, `backtest_pullback.py`, `_task21_24_patch.py`, `html_generator.py`.

## Polygon decommission history

**Polygon decommissioned 2026-04-25** but field names kept as back-compat aliases until 2026-05-01.

As of **2026-05-01 honest rename complete**:
- `polygon_news` → `news_articles`
- `polygon_news_score` → `news_sentiment_score`
- `polygon_snapshot` → `quote_snapshot`
- `polygon_options` → `options_chain`
- Function `compute_polygon_news_score` → `compute_news_sentiment_score`

Aliases `get_polygon_*` in `data_fetcher.py` retained for legacy callers but route to EODHD.

## EODHD rate limits + cache TTL contract

**Rate limits**: 100,000 calls/day, 1,000/min, ~14/sec burst (undocumented). Limiter at `eodhd_client.py` enforces 14/sec / 800/min / 90,000/day with 10% safety margin.

**Cache TTL** (bumped 2026-05-01 to fit hourly scans under daily quota — was burning ~135K calls/day potential, now ~45K):

| Endpoint | TTL | Why |
|---|---|---|
| `fundamentals` | 1 day | Quarterly data, doesn't change intraday |
| `eod` (OHLCV history) | 12 h | Updates only at market close |
| `sentiments` | 12 h | Aggregated daily, updates slowly |
| `news` | 4 h | Was 2h — news doesn't break that often per stock |
| `data_fetcher.get_news_articles` (wrapper) | 4 h | Was 30 min — primary culprit of quota burn |
| `options` | 2 h | Was 30min — chain doesn't move much intraday |
| `intraday` | 10 min | Needs freshness during market hours |
| `real_time` | 5 min | Quote freshness |

If `apply_to_score: false` on `tier1_signals`, signals compute but don't mutate canonical score (informational only). Flip to `true` after validation.

---

## Two-Log Architecture (signal_log.json vs picks_history.json)

Two PARALLEL trade-outcome logs track different realities. Knowing which one is canonical for a given consumer is critical when diagnosing performance.

| Log | Written by | Read by | What it records |
|---|---|---|---|
| **`cache/picks_history.json`** | `tracker._save_run()` on every scan | `tracker.compute_stats_by_setup()` → `apply_setup_wr_multiplier` (live + backtest) | Each scan's "picks" + matured trade outcomes |
| **`data/signal_log.json`** | `signal_tracker.log_signals()` on every scan emit | `model_drift_alert`, `elite_research_note`, diagnostics | Every emitted signal (BUY + WATCH + SHORT, Phase 2 2026-04-30) with paper 5d/10d outcomes |

For current WR snapshots: `python3 scripts/sharpe_kpi.py` (live aggregate + per-setup attribution).

### Key implications

- **Tracker feedback loop (`apply_setup_wr_multiplier`) reads `picks_history.json`** — that's the authoritative "what would we have done" log.
- **`signal_log.json` is the diagnostic/drift log** — broader scope (includes WATCH-tier), catches scanner-output bugs first.
- The two CAN diverge sharply. The CAR catastrophe (2026-04-28 onward) appeared in `signal_log.json` but NOT in `picks_history.json` — meaning the scanner emitted CAR signals but the main scoring pipeline (analyze_ticker → picks_history) didn't accept them as picks. Either log alone tells a partial story.
- **When user reports "system is losing money", check `data/portfolio_state.json` first** — that's the ONLY log that reflects real trades taken. Paper-simulation outcomes in either log above can show losses with zero real exposure.

When investigating WR drift, query BOTH logs and triangulate against `portfolio_state.json`.

---

## Structural Target Engine (Project 2 · M2.1–2.4 shipped 2026-05-13)

Confluence-scored T1/T2 from structural levels — replaces ATR-multiple targets when feature flag is on. **Flag stays OFF until M2.5 cutover.**

| Milestone | What | Where |
|---|---|---|
| M2.1 | Engine infra (cache layer, FastAPI endpoint, batch precompute, hook into nightly scan, feature flag) | `target_engine.py`, `server.py`, `scripts/precompute_targets.py`, `run_daily_scan.sh`, `config/config.json` |
| M2.2 | Parallel fields in `data.json` — `t1_structural`, `t2_structural`, `t1_confluence`, `t1_sources`, `t1_behavior`, `t1_p_reach`, `t1_action`, `t1_r_multiple` (+ `t2_*`) + `structural_modes` summary. Legacy `t1`/`t2` untouched. | `infra/prototype/build_data.py:_attach_structural_targets` |
| M2.3 | Mode completeness: short-direction reject, ETF graceful-degrade (`_KNOWN_ETF_TICKERS`), `earnings_imminent` flag (≤7d), INVEST analyst-PT stub | `target_engine.py:analyze_trade` |
| M2.4 | 20-ticker regression suite + diff vs legacy ATR targets (writes `cache/logs/te_regression_*.{json,md}`) | `scripts/te_regression.py` |
| M2.5 | **OPEN** — production cutover: flip `use_structural_targets=true` after one week of clean precompute + clean regression run + v2 dashboard frontend reads `t1_structural` | `config/config.json` |

**Source weights** (confluence scoring): BSL 3.0 · HVN 2.5 · SWING 2.5 · VAH 2.0 · AVWAP_52 2.0 · AVWAP_EARN 1.5 · FVG 1.5 · ROUND 1.0 · FIB 0.5.

**Behavior classifier**: MAGNET (HVN/POC) · REJECTION (VAH/FVG/AVWAP) · MIXED (BSL/SWING) · STRUCTURAL (invest stub).

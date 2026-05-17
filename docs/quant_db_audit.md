# Quant DB Audit — what a real quant DB has that yours doesn't

**Audit date:** 2026-05-17 · **Current:** 21 tables in Supabase + 13,983 rows in aux SQLite DBs + 95,597 lines in JSONL files **not** in any DB.

> **The headline:** Your Supabase has trade journal + portfolio state. A real quant DB also has **market data + fundamentals (PIT) + smart-money + risk attribution + ML outputs + ops telemetry.** You're missing 5 of the 7 layers a hedge-fund stack needs.

---

## What's missing — by impact

### Tier 0 · Blocking institutional validity (fix first)

| Gap | What | Why it matters | Effort |
|---|---|---|---|
| `decision_log` table | 92,229 JSONL lines NOT in Supabase | Per-ticker per-scan gate evaluations — the "why we said BUY/WATCH/AVOID" trail. Audit principle 4 requires this be queryable. Currently grep-only. | M |
| `index_membership_pit` | Point-in-time S&P 500 / R1000 / NDX membership history | **Fixes audit flaw #1 (survivorship bias).** Currently using current membership for historical backtests — every backtest WR/PF is biased +3pp. CLAUDE.md flags this as REJECTED-paid but Wikipedia revision history is FREE. | L |
| `fundamentals_pit` | Quarterly EPS/rev/margins keyed by *filing date* not period_end | **Fixes audit flaw #4 (fundamental look-ahead).** Currently `BACKTEST_NO_FUNDAMENTALS=1` disables the entire pillar instead. Free via SEC EDGAR. | L |
| `corporate_actions` | Splits + special dividends + spinoffs | Without these, any historical OHLCV is broken on adjustment events. EODHD provides — currently re-fetched on every scan. | S |
| `exit_signals` | 147 JSONL lines NOT in DB | When the engine flagged "TIME TO EXIT" and what happened. Critical for exit-rule calibration. | S |
| `earnings_outcomes` | 1,917 JSONL lines NOT in DB | Beat-prediction outcomes — feeds the PEAD sleeve calibration. Currently can't compute calibration in SQL. | S |

### Tier 1 · High-value (real edge improvement)

| Gap | What | Why it matters |
|---|---|---|
| `ohlcv_daily` | Full price history per ticker, point-in-time | Cold storage of every OHLCV bar. No more re-fetching from EODHD on every backtest. Use TimescaleDB hypertable. |
| `regime_history` | Daily regime classification + transition events | Currently in `cache/regime_history.json`. Hysteresis transitions in `cache/regime_hysteresis.json`. Should be a queryable time series for regime-conditional attribution. |
| `macro_indicators` | Daily VIX / VIX1D / MOVE / HYG / UUP / GLD / DXY / breadth pct_above_50d | Inputs to regime classifier. Currently re-fetched on every scan. Build a column-store fact table. |
| `insider_transactions` | Form 4 filings parsed per insider per ticker | Feeds Insider Cluster sleeve. Currently scraped from Finviz Elite on-demand — no historical query. |
| `institutional_holdings` | 13F filings quarterly | Track institutional accumulation/distribution. Currently inferred from Finviz inst_own_pct snapshot (lossy). |
| `short_interest_history` | Bi-monthly SI reports | Squeeze detection requires SI trend, not just last value. Free from FINRA / NASDAQ. |
| `news_events` | Every news headline with sentiment + source + ticker + timestamp | Currently fetched per-scan, never persisted. Sentiment-vs-price correlation impossible to study. |
| `rolling_sharpe_history` | 2 JSONL lines now — should be persistent time series | Daily portfolio Sharpe / Sortino / Calmar — required by principle 11 (edge erosion radar). |
| `iv_history` | 1,226 JSONL lines NOT in DB | Per-ticker IV rank time series. Needed for options sizing on the catalyst sleeves. |
| `orders` | 63 JSONL lines NOT in DB | Every Alpaca paper order submitted + status + fill. Required to measure paper-vs-live slippage. |
| `kelly_size_history` | Per-position-open kelly mult inputs (drawdown_mult × regime_mult × vix_mult × earnings_mult × var_floor × sharpe_mult) | Currently computed but discarded. Without persistence, can't audit "why was I sized 0.6× on AAPL?" |
| `wilson_ci_snapshot` | Daily Wilson LB per (setup × regime × score_band × entry_quality) cell | Currently computed at scan-time, never persisted → can't plot edge decay over time. |
| `model_predictions` | 3-headed model forecasts per ticker per day per horizon | Currently rendered but not stored → no Brier-score calibration, no prediction-vs-realized study. |
| `slippage_realized` | Entry/exit slippage vs expected per fill | Calibrates the audit-#5 slippage model. Critical for paper-to-live transition. |

### Tier 2 · Catalyst calendars (free data, big edge)

| Table | What | Source (free) |
|---|---|---|
| `earnings_calendar_pit` | Earnings dates per ticker, **vintage-tracked** (when was the date first published) | Zacks (already paid) + EODHD |
| `fomc_calendar` | Fed meeting dates + statement times | Fed website (FRED ical) |
| `economic_calendar` | CPI/NFP/retail-sales/PMI release dates + actual vs forecast | BLS/BEA RSS |
| `ipo_calendar` | Upcoming IPOs with price range, share count | NASDAQ + NYSE public feeds |
| `splits_calendar` | Upcoming splits | EODHD corporate actions endpoint |
| `fda_calendar` | Biotech PDUFA dates | FDA public adcomm + Reddit r/biotech_stocks |
| `congressional_trades` | Senate/House disclosures (referenced in CLAUDE.md as missing P0) | Senate Stock Watcher API (free) |

### Tier 3 · Risk / attribution (institutional table stakes)

| Table | What |
|---|---|
| `position_risk_snapshot` | Daily per-position VaR/CVaR/beta/sector-exposure |
| `portfolio_risk_history` | Daily portfolio-level VaR, max DD, beta, Sharpe-126d, Sortino, correlation matrix |
| `stop_levels_history` | Every stop adjustment with reason (manual / trailing / breakeven / regime_flip) |
| `strategy_pnl_attribution` | Daily $ PnL split by sleeve (Momentum / PEAD / Insider / Mean-Rev / Defensive / VCP / ESP) |
| `setup_x_regime_grid` | Materialized view: rolling 90d WR/PF/Wilson_LB per (setup × regime × score_band × entry_quality) |
| `factor_returns` | Daily HML/SMB/MOM/QMJ/RMW factor returns — for portfolio attribution |
| `var_breaches` | When realized loss > VaR estimate — calibrates the risk model |

### Tier 4 · ML / model lifecycle

| Table | What |
|---|---|
| `model_versions` | model_id, training_cutoff, feature_set_hash, hyperparams, holdout metrics |
| `model_features_snapshot` | Feature vector per ticker per scan (replay/debug) |
| `model_calibration` | Predicted prob vs realized outcome (Brier per horizon) |
| `prediction_residuals` | actual − predicted (used by drift detection) |
| `feature_importance_history` | Per-retrain feature importance for explainability |

### Tier 5 · Sentiment / alt data

| Table | What |
|---|---|
| `reddit_mentions_daily` | WSB/r/stocks mention count + sentiment per ticker |
| `stocktwits_volume` | Message volume per ticker per day |
| `google_trends_spikes` | Search-interest deviation from baseline |
| `dark_pool_volume` | FINRA TRF prints (DPI) |

### Tier 6 · Ops telemetry (you can't improve what you can't measure)

| Table | What |
|---|---|
| `eodhd_quota_usage` | Daily quota consumption per data type |
| `api_latency_metrics` | Per-endpoint p50/p95/p99 latency |
| `cache_hit_ratio` | fundamentals.db / enrichment_cache.db hit rates per scan |
| `launchd_runs` | Every plist firing with success/failure/duration |
| `data_quality_checks` | Daily assertions (NULL counts, freshness, range checks) — feeds dashboard alerts |
| `config_history` | Every config.json change (commit hash, author, before/after diff) |
| `feature_flag_changes` | When each `_enabled` flag flipped |

### Tier 7 · Multi-user (already referenced in CLAUDE.md)

| Table | What |
|---|---|
| `users` | Multi-user identity (currently `data/users.json` — single-table not in DB) |
| `user_portfolio_state` | Per-user portfolio_state (currently mono) |
| `user_watchlists` | Per-user custom_tickers |
| `user_alerts_prefs` | Per-user alert routing |
| `user_audit_log` | Who did what when (already exists as JSONL, not in DB) |
| `friends_leaderboard_state` | QuantLeaders module references this — backing table missing |

---

## Stats missing **inside existing tables**

The current tables have the right *shape* but are missing analytical columns. These are zero-cost to add (everything is in `raw_json`):

### `signal_log` — extract from raw_json into typed columns
- `entry_quality` (FRESH / PULLBACK / VALID / EXTENDED / MISSED)
- `catalyst_tier` (1 / 2 / 3)
- `conviction_tier` (T1 / T2 / T3 / WATCH)
- `score_band` ('60-69' / '70-79' / '80-89' / '90-100')
- `setup_family` (typed, not free-text)
- `gates_passed[]`, `gates_failed[]` (array of gate names)
- `wilson_lb_at_entry`, `expected_wr`, `expected_pf` (per setup × regime cell at decision time)
- `kelly_mult` (final), `vix_at_entry`, `regime_at_entry`, `sector_rs_at_entry`
- `expected_hold_days`, `actual_hold_days`
- `exit_price` (not just outcome bucket text)
- `mae_date`, `mfe_date` (when did worst/best happen — for time-in-loss analysis)
- `breakeven_stop_hit`, `trailed`, `partial_taken`
- `r_multiple` = actual_pnl_pct / risk_pct

### `closed_trades` — add per-trade calibration columns
- `score_at_entry`, `rs_rank_at_entry`, `regime_at_entry`
- `r_multiple`, `slippage_entry_pct`, `slippage_exit_pct`
- `commission_dollars`, `borrow_fee_dollars` (if short)
- `time_in_loss_pct` (% of hold underwater)
- `time_to_breakeven_days`, `time_to_target1_days`
- `max_dd_during_hold_pct`, `max_gap_overnight_pct`
- `earnings_during_hold` (bool), `news_events_during_hold` (count)

### `positions` — live risk telemetry
- `risk_dollars` = (entry − stop) × shares
- `risk_pct_of_portfolio`
- `correlation_to_portfolio` (live, recomputed daily)
- `beta_to_spy`, `sector_concentration_pct`
- `days_held`, `expected_target_date`
- `unrealized_pnl_high`, `unrealized_pnl_low` (high-water + drawdown marks during hold)
- `wilson_lb_at_entry` (so you can spot in-hold edge erosion)

### `backtest_runs` — institutional metrics
- `calmar_ratio`, `sortino_ratio`, `omega_ratio`
- `var_95`, `cvar_95`, `downside_deviation`, `mar_ratio`
- `recovery_time_avg_days`, `consecutive_losses_max`
- `monte_carlo_summary_json` (P5/P50/P95 of final equity over 1000 bootstrap resamples)
- `regime_breakdown_json` (per-regime stats)
- `setup_breakdown_json` (per-setup stats)
- `equity_curve_array_json` (daily equity for plot reproducibility)

### `runs` — scan telemetry
- `scan_duration_s`, `data_fill_rate`, `eodhd_quota_used`
- `tickers_evaluated`, `tickers_killed`, `tickers_passed_gates`
- `git_commit`, `config_hash`
- `regime_at_open`, `regime_at_close`, `regime_transition_flag`

---

## Aux DBs that should fold into Supabase

| Source | Rows | Notes |
|---|---:|---|
| `data/fundamentals.db.fundamentals` | 2,076 | Should become `fundamentals_pit` (with `report_date` added for PIT) |
| `data/enrichment_cache.db.enrichment` | 11,907 | Should become `ticker_enrichment_snapshot` (k/v with TTL) |
| `data/decision_log.jsonl` | 92,229 | The biggest gap — per-ticker scan decisions |
| `data/exit_signals.jsonl` | 147 | Should fold into `signal_log.exit_events` or its own table |
| `data/earnings_outcomes.jsonl` | 1,917 | Already covered by Tier 0 |
| `data/iv_history.jsonl` | 1,226 | Already covered by Tier 1 |
| `cache/orders.jsonl` | 63 | Already covered by Tier 1 |
| `cache/eod_actions.jsonl` | 13 | End-of-day decisions log |
| `cache/regime_history.json` | — | Daily regime — already covered |
| `cache/regime_hysteresis.json` | — | Hysteresis state — fold into `regime_transitions` |
| `cache/rolling_sharpe_history.jsonl` | 2 | Already covered |
| `data/smc_hit_rates.json` | — | Smart Money Concept block calibration |

---

## Postgres-specific features the schema doesn't use

| Feature | Use case |
|---|---|
| **TimescaleDB hypertables** | `ohlcv_daily`, `news_events`, `model_predictions`, `signal_log`, `decision_log` — 10-100× query speedup on time-range scans |
| **BRIN indexes** | All `ts` / `date` columns — 10× smaller than B-tree, faster on append-mostly tables |
| **Partitioning by month** | `signal_log`, `gap_events`, `decision_log` — keeps active partition hot |
| **Materialized views** | `setup_x_regime_grid`, `monthly_pnl_by_setup`, `wilson_ci_snapshot` — refreshed nightly |
| **JSONB GIN indexes** | All `raw_json` columns — query `raw_json->>'setup_family' = 'VCP'` fast |
| **Row-level security** | When multi-user lands — already noted in 001 migration but disabled |
| **Generated columns** | `r_multiple` = `pnl_pct / risk_pct` — computed at write time, no app-code drift |
| **Triggers** | `equity_audit` should be a trigger on `portfolio_state` UPDATE, not app-code call |
| **CTE materialization** | For the kill-list query — currently computed in Python, should be a SQL view |
| **Foreign data wrapper** | Mount the SQLite db as a Postgres FDW for zero-copy migration |

---

## Schema integrity gaps in current 21 tables

| Issue | Impact |
|---|---|
| Most tables have no `created_at` / `updated_at` | Can't query "what changed in the last hour" |
| No `created_by` / `tombstoned_at` (soft-delete) | DELETEs are destructive, no audit |
| No version column for optimistic concurrency | Race conditions possible on `portfolio_state` updates |
| `picks` and `trades` tables missing in Supabase | Schema is incomplete (you found this in the last check) |
| `direction` CHECK constraints were dropped | Type discipline lost — `'neutral'` rows now possible |
| `observed_at NOT NULL` constraints were dropped | Lost a server-side timestamp guarantee |
| `meta.value` was changed from TEXT to JSONB without documenting | Drift between migration file and actual schema |
| No FK from `signal_log.ticker → custom_tickers.ticker` or any ticker master | Ticker typos go unflagged |
| No `tickers` master table | Sector / industry / market_cap re-fetched on every scan |
| No `data_sources` table tracking what fed each scan | Can't replay a scan with the same data version |

---

## Recommended sequencing (P0 → P3 ROI)

| # | Item | Effort | ROI |
|---|---|---|---|
| 1 | Wire `decision_log.jsonl` → Postgres table (92K rows) | M | **Highest** — turns grep into SQL |
| 2 | Build `index_membership_pit` from Wikipedia | L | Fixes audit #1 — every backtest gets +3pp WR honest |
| 3 | Build `fundamentals_pit` from SEC EDGAR | L | Fixes audit #4 — unblocks fundamentals pillar in backtest |
| 4 | Fold `exit_signals` + `earnings_outcomes` + `iv_history` + `orders` JSONL → tables | S | 4 quick wins for sleeve calibration |
| 5 | Extract typed columns from existing `raw_json` (signal_log + closed_trades) | S | Zero-cost analytical depth |
| 6 | Build `ohlcv_daily` cold storage (TimescaleDB hypertable) | M | Stops re-fetching every backtest |
| 7 | `corporate_actions` table | S | Required for accurate historical PnL |
| 8 | `model_predictions` + `model_calibration` | M | Enables Brier-score model drift detection |
| 9 | `position_risk_snapshot` + `portfolio_risk_history` daily | M | Institutional risk management |
| 10 | Catalyst calendars (FOMC, IPO, FDA, congressional) | M | Tier-1 catalyst sleeves get firmer footing |
| 11 | TimescaleDB extension + hypertable conversion | S | One-time setup, big query speedup |
| 12 | Materialized views for `setup_x_regime_grid` | S | Replaces in-Python computation |
| 13 | Multi-user tables | L | Unblocks the $1K–$1M unified vision |

---

## Bottom line

You have **a good trade journal** (signal_log, closed_trades, positions) and **a serviceable backtest ledger** (backtest_runs, backtest_trades, walk_forward_folds).

You are **missing the entire market-data layer, the entire fundamentals-PIT layer, the entire risk-attribution layer, and the entire ML-output layer.** Every backtest reach is bottlenecked by EODHD round-trips because you have no cold storage. Every risk question requires re-running the scan because nothing is persisted. Every model audit is impossible because predictions vanish after render.

The Supabase tab you just built is the right scaffolding — fix the duplication issue, then start filling the 5 missing layers from Tier 0 down.

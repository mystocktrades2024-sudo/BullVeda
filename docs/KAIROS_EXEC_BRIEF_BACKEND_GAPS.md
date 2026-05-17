# Kairos · Exec Brief · Backend Wire-Up Gap Audit

**Date:** 2026-05-13
**Source:** `infra/prototype/kairos.html` Exec Brief builders + TV chart adapters
**Status:** Frontend complete · backend fields require wire-up in `build_data.py`

This document catalogs every `t.*` field the Exec Brief and TV chart system
**reads**. Where the field is already populated by `build_data.py` it's marked
✅ wired. Where it's expected but absent it's marked ❌ missing and needs
backend work.

The framework rule (no fabrication) means missing fields render as `—` in the
UI today. This is the file that closes the gap by listing every field to add.

---

## Per-tab Exec Brief gap matrix

### 1 · Overview (synthesis)

| Field | Status | Source / Owner |
|---|---|---|
| `t.score` | ✅ wired | `analysis.py` composite score |
| `t.conviction` / `t.conviction_tier` | ✅ wired | `decision_engine.py` |
| `t.verdict` / `t.decision` | ✅ wired | `decision_engine.py` |
| `t.regime` | ✅ wired | `data_fetcher.get_market_regime()` |
| `t.rr_t1` / `t.trade_levels.rr_t1` | ✅ wired | `canonical_trade_plan.py` |
| `t.analyst_target` | ✅ wired | EODHD analyst feed |
| `t.decision.gates_evaluated` | ⚠️ partial | Surfaced for some tickers; verify universal |

### 2 · Plan · Ticket

| Field | Status | Source / Owner |
|---|---|---|
| `t.price` | ✅ wired | EODHD real-time |
| `t.stop` / `t.trade_levels.stop` | ✅ wired | `canonical_trade_plan.py` |
| `t.target1` / `t.t1` | ✅ wired | `canonical_trade_plan.py` |
| `t.size_pct` / `t.kelly_sizing.size_pct_equity` | ✅ wired | `kelly_size.py` |
| `t.atr` | ✅ wired | technical indicators |
| `t.setup_family` / `t.setup` | ✅ wired | `analysis.py` |
| `t.entry_quality` | ✅ wired | `analysis.classify_entry_quality()` |

### 3 · Technicals

| Field | Status | Source / Owner |
|---|---|---|
| `t.rs_rank` | ✅ wired | `analysis.py` |
| `t.atr` | ✅ wired | technicals |
| `t.rvol` | ✅ wired | technicals |
| `t.pct_from_high` | ✅ wired | technicals |
| ❌ `t.htf_bias_w` (weekly trend) | **MISSING** | Add: `analysis.compute_htf_bias(t, 'weekly')` |
| ❌ `t.htf_bias_m` (monthly trend) | **MISSING** | Add: `analysis.compute_htf_bias(t, 'monthly')` |
| ❌ `t.adx_14` (trend strength) | **MISSING** | Add: TA-lib ADX(14) |
| ❌ `t.squeeze_on` + `t.squeeze_duration` | **MISSING** | Bollinger-inside-Keltner detector |
| ❌ `t.vwap_anchored_52w` | **MISSING** | Anchored VWAP from 52w high date |
| ❌ `t.pivot_s1` / `t.pivot_r1` etc. | **MISSING** | Classical daily pivot points |
| ❌ `t.tv_rating_composite` | **MISSING** | TradingView rating aggregator (may need scrape) |

### 4 · Investment · Value

| Field | Status | Source / Owner |
|---|---|---|
| `t.analyst_target` | ✅ wired | EODHD |
| `t.f_score` (Piotroski) | ⚠️ partial | Some tickers via `fund_score`; need universal F-score per `analysis.compute_piotroski()` |
| `t.roic` | ❌ **MISSING** | Compute: NOPAT / invested-capital · `analysis.compute_roic()` |
| `t.wacc` | ❌ **MISSING** | Compute: cost-of-equity + after-tax cost-of-debt · `analysis.compute_wacc()` |
| `t.dividend_yield` | ⚠️ partial | EODHD has it; verify field name |
| `t.buyback_yield` | ❌ **MISSING** | Compute: Δshares-outstanding from 4q comparison |
| `t.altman_z` | ❌ **MISSING** | Compute: Altman Z-score from balance sheet |
| ❌ `t.interest_coverage` | **MISSING** | EBIT / interest expense |
| ❌ `t.net_debt_ebitda` | **MISSING** | (debt − cash) / EBITDA |
| ❌ `t.insider_ownership_pct` | **MISSING** | EODHD insider summary |
| ❌ `t.dcf_sensitivity_table` | **MISSING** | Backend computes IV at WACC ±100bp · growth ±200bp |

### 5 · Risk

| Field | Status | Source / Owner |
|---|---|---|
| `t.beta` | ✅ wired | EODHD |
| `t.kelly_size.kelly_pct` | ✅ wired | `kelly_size.py` |
| ❌ `t.sharpe_1y` | **MISSING** | Compute: (R − Rf) / σ · 1y trailing |
| ❌ `t.sharpe_3y` | **MISSING** | Same · 3y trailing |
| ❌ `t.sortino_1y` | **MISSING** | (R − Rf) / σ_downside |
| ❌ `t.calmar` | **MISSING** | annual return / max-DD |
| ❌ `t.max_dd_3y` | **MISSING** | Compute from price history |
| ❌ `t.var_95_1d` / `cvar_95_1d` | **MISSING** | Statistical VaR/CVaR |
| ❌ `t.info_ratio` | **MISSING** | alpha / tracking error vs benchmark |
| ❌ `t.alpha_3y` | **MISSING** | CAPM-adjusted excess return |
| `t.adv_dollar_60d` | ✅ wired | EODHD |

### 6 · Earnings

| Field | Status | Source / Owner |
|---|---|---|
| `t.earn_days` | ✅ wired | Earnings calendar |
| `t.zacks_earnings_esp` | ✅ wired | Zacks |
| `t.earnings_beat` (8q rate) | ✅ wired | `analysis.py` |
| ❌ `t.implied_move_pct` | **MISSING** | options chain ATM straddle |
| ❌ `t.iv_rank` | ⚠️ partial | Some tickers via Schwab; verify universal |
| ❌ `t.pead_5d_avg_pct` / `pead_20d_avg_pct` | **MISSING** | Compute from 8q history × post-print returns |
| ❌ `t.realized_vs_implied_8q` | **MISSING** | Backend: realized 1d ER move vs IM |
| ❌ `t.sector_beat_rate` | **MISSING** | Aggregate beat-rate across sector tickers |
| ❌ `t.whisper_eps` | **MISSING** | Estimize/Whisper (paid · alternative: skip) |
| ❌ `t.pre_announce_history` | **MISSING** | Last 8 quarters pre-announce flag |
| `t.cohort_peers[].er_sympathy_*` | ⚠️ partial | Already on punch list (KAIROS-COHORT-SYMPATHY) |

### 7 · Options

| Field | Status | Source / Owner |
|---|---|---|
| `t.iv_rank` | ⚠️ partial | Schwab feed; verify universal |
| `t.atm_iv` | ❌ **MISSING** | Schwab chain ATM call+put avg |
| `t.put_call_oi` | ⚠️ partial | Schwab feed |
| `t.max_pain` | ⚠️ partial | Schwab feed |
| `t.uoa_calls` / `t.uoa_puts` | ⚠️ partial | Schwab vol vs OI scanner |
| ❌ `t.iv_history` (252d) | **MISSING** | Persist daily IV rank snapshots |
| ❌ `t.skew_25d` / `t.risk_reversal_25d` | **MISSING** | Schwab full chain analytics |
| ❌ `t.term_structure` (7d/30d/60d/90d/180d/365d IV) | **MISSING** | Schwab multi-expiry |

### 8 · Portfolio

| Field | Status | Source / Owner |
|---|---|---|
| `t.is_held` / `t.in_portfolio` | ⚠️ partial | Read from `portfolio_state.json` |
| `t.current_alloc_pct` | ⚠️ partial | Read from `portfolio_state.json` |
| ❌ `t.target_alloc_pct` | **MISSING** | New portfolio policy table |
| ❌ `t.investor_goal` | **MISSING** | Per-account or per-position goal label |
| ❌ `t.sector_alloc_pct` | **MISSING** | Per-sector book exposure |
| ❌ `t.book_correlations[]` | **MISSING** | Per-position-pair 60d corr matrix |
| ❌ `t.factor_loadings` (momentum/quality/value/size/vol) | **MISSING** | Fama-French + custom |
| ❌ `t.wash_sale_risk` | **MISSING** | Check recent loss-takings on same symbol |

### 9 · Tape · Flow

| Field | Status | Source / Owner |
|---|---|---|
| `t.news_sentiment_score` | ✅ wired | `compute_news_sentiment_score()` |
| `t.insider.buys` / `t.insider.sells` | ✅ wired | SEC EDGAR + EODHD |
| `t.insider.ceo_buy` | ⚠️ partial | EODHD Form 4 — verify CEO flag accurate |
| `t.catalysts_pending` | ❌ **MISSING** | FDA/contract/M&A — need separate catalyst feed |
| ❌ `t.short_pct_of_float` | **MISSING** | Finviz scrape (already kept) |
| ❌ `t.days_to_cover` | **MISSING** | Short interest / avg daily volume |
| ❌ `t.borrow_rate` | **MISSING** | Schwab securities-lending if available |
| ❌ `t.13d_filings[]` | **MISSING** | SEC EDGAR activist filer scrape |

### 10 · Track Record

| Field | Status | Source / Owner |
|---|---|---|
| `t._setup_wr` | ✅ wired | `tracker.compute_stats_by_setup()` |
| `t._setup_wilson_lb` | ✅ wired | `tracker.py` Wilson LB |
| `t._setup_pf` | ✅ wired | `tracker.py` profit factor |
| `t._setup_avg_r` | ✅ wired | `tracker.py` |
| `t._setup_n` | ✅ wired | `tracker.py` |
| ❌ `t._setup_sharpe` | **MISSING** | Compute per-setup Sharpe |
| ❌ `t._setup_regime_wr` (per regime) | **MISSING** | `tracker.compute_regime_conditional()` |
| ❌ `t._setup_holdout_wr` (walk-forward 15%) | **MISSING** | Already in backtest reports; surface per-ticker |
| ❌ `t._setup_decay_90/180/365` | **MISSING** | Rolling WR over 3 windows |

---

## Macro drill (inside Overview)

| Field | Status | Source / Owner |
|---|---|---|
| `t.regime` | ✅ wired |  |
| ❌ `t.vix_term` (VIX vs VIX3M) | **MISSING** | EODHD VIX feed |
| ❌ `t.yield_curve_history[tenor]` | **MISSING** | FRED 2y/5y/10y/30y daily series |
| ❌ `t.credit_spreads` (HY-OAS, IG-OAS) | **MISSING** | FRED ICE BofA series |
| ❌ `t.cross_asset` (DXY, gold, oil, BTC) | **MISSING** | EODHD ETF/index feed |
| ❌ `t.macro_calendar` (FOMC, CPI, NFP, PPI) | **MISSING** | FRED or Trading Economics free |
| ❌ `t.sector_rotation` (XLF/XLE/XLV/XLK/XLY 21d) | **MISSING** | EODHD sector ETFs daily |

---

## TV chart data adapters · what's needed

| Chart | Field needed | Status |
|---|---|---|
| Overview · 60d strip | `t.price_history[]` (60 daily bars) | ⚠️ check field name |
| Plan · 30d ladder | `t.price_history[]` (30 daily bars) | same |
| Options · IV cone | `t.iv_history[]` (252 daily IV-rank points) | ❌ persist daily |
| Macro · yield curve | `t.yield_curve_history[tenor]` | ❌ FRED ingest |

---

## Priority recommendation (P0/P1/P2)

### P0 · ship-blocking (the call breaks without these)
1. `t.sharpe_1y`, `t.sharpe_3y` — Risk lens is meaningless without
2. `t.f_score`, `t.altman_z`, `t.roic`, `t.wacc` — Value lens
3. `t.target_alloc_pct`, `t.investor_goal` — Portfolio lens
4. `t.price_history[]` — every chart depends on this

### P1 · canonical (a professional expects them)
5. `t.iv_history[]` — Options lens IV cone
6. `t.htf_bias_w`, `t.htf_bias_m` — Technicals HTF
7. `t.implied_move_pct`, `t.pead_5d_avg_pct` — Earnings forecast
8. `t.max_dd_3y`, `t.calmar`, `t.sortino_1y` — Risk depth
9. `t.short_pct_of_float`, `t.days_to_cover` — Tape Flow

### P2 · advanced (edge cases · drill-down)
10. `t.dcf_sensitivity_table` — Value DCF audit
11. `t.adx_14`, `t.squeeze_on` — Technicals advanced
12. `t.factor_loadings` — Portfolio style box
13. `t.catalysts_pending[]` — Tape Flow catalyst calendar
14. `t.yield_curve_history`, `t.credit_spreads` — Macro depth
15. `t.13d_filings[]` — Activist watch
16. `t.wash_sale_risk` — Tax compliance

---

## Implementation plan (build_data.py)

1. **Open `infra/prototype/build_data.py`**
2. For each P0 field above, add the compute step in the per-ticker enrichment block
3. Run `python3 swing_trade.py regen` to test
4. Verify in browser: P0 fields should turn from `—` to real values in Exec Brief
5. Repeat for P1/P2 in subsequent sprints

The Exec Brief code is **defensive** — every field reads with `null`-safe
extraction and renders `—` when missing. So backend wire-up can be done
incrementally without breaking the UI.

# SwingTrade System Hardening Checklist

**Started:** 2026-04-15 (PST)
**Profile in effect:** `industry_standard` (50% WR, 2.5 R:R, 10–20 trades/mo)
**Legend:** `[ ]` not started · `[~]` in progress · `[x]` done · `[!]` blocked · `[-]` skipped

**UI Tabs (reference):** Trades · Strategies · Portfolio · Performance · Screener · Themes · Research · Leveraged · Industries · Market · Crypto · Playbook · Guide · Reference · System Status · Settings

---

## Phase 0 — Validate Claims ✅ DONE 2026-04-15

| # | Action | Status | Finding | Tab Impacted | Feature |
|---|---|---|---|---|---|
| 0.1 | Verify `max_size_pct` wiring | [x] | Partially wired — computed in `data_fetcher.py:2394` but not read by executor sizing path | System Status | Visibility only |
| 0.2 | Verify signal dedup | [x] | Same-day dedup works `(ticker, date)`; cross-day dedup missing | Performance | n/a (investigation) |
| 0.3 | Verify drift targets | [x] | Auto-dynamic via `config._meta.last_backtest_wr`; Wilson CI + n≥30 present | System Status | n/a (investigation) |
| 0.4 | Verify config validator depth | [x] | Good baseline (ordering, unreachability, universe); missing per-regime required-keys | Settings | n/a (investigation) |

---

## Phase 1 — Unblock the Migration 🔴

| # | Action | Status | File | Tab Impacted | Feature Added |
|---|---|---|---|---|---|
| 1.1 | Move per-setup RS floors to config (`setup_gates` block) | [x] | `industry_standard.json`, `analysis.py:5675–5705` | Settings, Screener | Config-driven setup gates (RS floors, RVOL, weekly_bull per setup) |
| 1.2 | Setup gates read `weekly_bull_required` from config | [x] | `analysis.py:5689, 5714` | Screener, Trades | Per-setup weekly-bull toggle |
| 1.3 | `catalyst_override_offset` configurable (default 10) | [x] | `industry_standard.json` [x], `analysis.py:~5752` [x] | Settings, Screener | Tunable catalyst override |
| 1.4 | `rsi_cap` setup-conditional (leaders get 85) | [x] | `analysis.py:5649` | Trades, Screener | Leader-aware RSI gate (no longer cuts Minervini runs) |
| 1.5 | Wire `avoid_below` into decision layer | [x] | `analysis.py:5737–5744` | Screener | AVOID floor config-driven |
| 1.6 | Add explicit `watch_min_score` to every regime4 bucket | [x] | `industry_standard.json` | Settings, Screener | Explicit WATCH floor per regime4 |
| 1.7 | Wire `max_size_pct` into position sizing | [x] | `executor.py`, `portfolio_tracker.py` | Portfolio, Trades | Regime-adaptive position sizing (100/70/35/0% per regime4) |

**Exit gate:** Scan emits **5–15 BUYs/day** in trending market (verified via Screener tab count).

---

## Phase 2 — Safety Rails 🔴

| # | Action | Status | File | Tab Impacted | Feature Added |
|---|---|---|---|---|---|
| 2.1 | Hard-assert regime completeness | [x] | `config_validator.py` | Settings, System Status | Startup validation fails loudly on missing keys |
| 2.2 | Echo effective resolved config at scan start | [x] | `swing_trade.py` scan entry | System Status, Screener | "Active Config" banner showing profile + every resolved threshold |
| 2.3 | Update drift target meta after Phase 4 rerun | [ ] | `config/config.json` `_meta.last_backtest_wr` | System Status, Performance | Live vs backtest drift with correct baseline |

**Exit gate:** Synthetic missing-key test caught by validator at startup.

---

## Phase 3 — Observability Foundation 🟠

| # | Action | Status | File | Tab Impacted | Feature Added |
|---|---|---|---|---|---|
| 3.1 | Persist full decision log (every ticker + gate chain) | [x] | `signal_tracker.log_decisions()` → `data/decision_log.jsonl` | System Status, Screener | "Why not BUY?" — per-ticker gate-kill chain exposed |
| 3.2 | Dedup new-BUY counter (first-day BUY per ticker) | [x] | `signal_tracker.log_signals` | Performance | "New BUYs/week" metric separate from raw count |
| 3.3 | Flip-rate metric | [x] | `performance_metrics.compute_flip_rate` | Performance | Whipsaw detector: BUY↔WATCH flips within 3d |
| 3.4 | Hysteresis on BUY↔WATCH (`±2` score band) | [x] | `analysis.py` end of decision fn | Screener, Trades | Stable signals (fewer same-ticker flips) |
| 3.5 | WATCH→BUY conversion tracking | [x] | `tracker.py`, `signal_tracker.py` | Performance, Screener | "Watchlist conversion rate" per setup |

**Exit gate:** One scan produces `decision_log.jsonl` with all tickers + resolved gate chains.

---

## Phase 4 — Honest Backtest Rerun 🟠

| # | Action | Status | File | Tab Impacted | Feature Added |
|---|---|---|---|---|---|
| 4.1 | Re-run walk-forward with `industry_standard --years 3` | [ ] | `walk_forward_parallel.py` | Performance, Reference | Profile-matched backtest baseline |
| 4.2 | Apply survivorship haircut `SURVIVORSHIP_WR_ADJUSTMENT=4` | [ ] | `backtest.py` env | Performance | Honest WR (raw + adjusted surfaced side-by-side) |
| 4.3 | Run with/without fundamentals (`BACKTEST_NO_FUNDAMENTALS=1`) | [ ] | `backtest.py` env | Performance | Look-ahead-bias delta (upper bound) |
| 4.4 | Report `{wr_raw, wr_adj, n, wilson_low, wilson_high, pf, rr}` per setup | [ ] | backtest summary | Performance, Playbook | Per-setup confidence intervals |
| 4.5 | HARD GATE: adjusted WR ≥ 48% on ≥200 trades, PF ≥ 1.8 | [ ] | manual review | Performance | Go/no-go decision |

**Exit gate:** 4.5 passes. If not → tune or revert to `quality_lock`.

---

## Phase 5 — Exit Logic 🟠

| # | Action | Status | File | Tab Impacted | Feature Added |
|---|---|---|---|---|---|
| 5.1 | Add `classify_exit_state(position)` | [x] | `analysis.py` new fn | Portfolio, Trades | Daily EXIT/TRIM/HOLD verdict per open position |
| 5.2 | Wire exit verdict into EOD scan | [x] | `portfolio_tracker.py`, `eod_manager.py` | Portfolio | Automated exit signals (trail stop, thesis invalid, time stop, regime flip) |
| 5.3 | Persist exit reason alongside P&L | [x] | `tracker.py` | Performance, Portfolio | "Why did this close?" attribution per trade |

**Exit gate:** Every open paper position has daily computable exit verdict.

---

## Phase 6 — Signal Quality Metrics 🟡

| # | Action | Status | File | Tab Impacted | Feature Added |
|---|---|---|---|---|---|
| 6.1 | Score calibration (isotonic → P(win)) + Brier | [x] | new `calibration.py` | Performance | Score-to-probability chart; Brier score weekly |
| 6.2 | Benchmark-relative WR (ticker return − SPY) | [x] | `performance_metrics.py` | Performance | "SPY-relative alpha" per trade |
| 6.3 | False-negative tracker (winners we didn't BUY) | [x] | new `false_negatives.py` | Performance, Screener | "Missed winners" table with blocking-gate attribution |
| 6.4 | Factor exposure per BUY basket | [x] | `sector_rotation.py` | Market, Themes, Portfolio | Daily beta + top-3 factor exposure of active BUYs |
| 6.5 | Per-setup MFE/MAE aggregation | [x] | `performance_metrics.py` | Performance, Playbook | "Setup efficiency" metric (MFE/MAE ratio) |

**Exit gate:** Quality scorecard visible on Performance tab.

---

## Phase 7 — Code Quality 🟡

| # | Action | Status | File | Tab Impacted | Feature Added |
|---|---|---|---|---|---|
| 7.1 | Extract `effective_buy_min()` pure function | [x] | `analysis.py` | System Status | Logged threshold breakdown (base → cycle → season → breadth) |
| 7.2 | Audit + delete dead 52wk elite-breakout branch | [x] | `analysis.py:5469` | — (internal) | — (cleanup) |
| 7.3 | Split setup weight multiplier from score → sizing only | [x] | `analysis.py`, `tracker.py` | Screener, Portfolio | Removes reflexive score-inflation loop; multiplier drives size instead |
| 7.4 | Split AVOID → `no_edge_now` vs `hard_reject` | [x] | decision fn | Screener | "Monitor anyway" tier between WATCH and AVOID |

**Exit gate:** Decision core unit-testable as pure fn.

---

## Phase 8 — Usability 🟢

| # | Action | Status | File | Tab Impacted | Feature Added |
|---|---|---|---|---|---|
| 8.1 | "Why this verdict?" panel | [x] | `analyze.html`, `html_generator.py`, `server.py` | Trades, Screener, Research | Expandable gate-chain per ticker tile |
| 8.2 | Watchlist trigger price on tile | [x] | `tracker.check_watch_triggers`, `html_generator.py` | Trades, Screener | "Alerts at $X (breakout)" sub-line per WATCH |
| 8.3 | Banner for suppressed BUYs | [x] | `html_generator.py` | Trades, Portfolio, System Status | Top-bar: "⚠ Circuit breaker active / PDT limit hit / Drawdown kill-switch" |
| 8.4 | Signal-age badge | [x] | `html_generator.py` | Trades, Screener | "RS as of 18h ago" freshness chip |

**Exit gate:** User can reconstruct any verdict from UI alone.

---

## Paper-Trade Validation Gate (7 days)

| # | Criterion | Status | Tab to Check |
|---|---|---|---|
| PT.1 | New BUYs/week within 10–20 target | [ ] | Performance |
| PT.2 | Flip rate < 20% | [ ] | Performance |
| PT.3 | Zero silent config fallback warnings | [ ] | System Status |
| PT.4 | Every open position has exit verdict | [ ] | Portfolio |
| PT.5 | False-negative rate logged | [ ] | Performance |

---

## Live Trade Graduation Gate (30 closed trades)

| # | Criterion | Status | Tab to Check |
|---|---|---|---|
| LV.1 | Actual WR within Wilson CI of backtest | [ ] | Performance |
| LV.2 | PF ≥ 1.5 | [ ] | Performance |
| LV.3 | SPY-relative alpha positive | [ ] | Performance |
| LV.4 | Max drawdown within expectation | [ ] | Portfolio |

---

## Rollback Triggers (any one → revert to `quality_lock`)

| # | Trigger | Monitored By |
|---|---|---|
| RB.1 | <2 BUYs/day for 5 consecutive trending days | Performance |
| RB.2 | Flip rate >30% | Performance |
| RB.3 | First 20 live trades WR <40% | Performance |
| RB.4 | Any silent config fallback in prod | System Status |

---

## Tab-Impact Summary

| Tab | Phases Touching It | Key New Features |
|---|---|---|
| **Trades** | 1, 3, 5, 8 | Leader-aware RSI, hysteresis, exit verdict, "why this verdict?" panel, suppression banner, signal-age badge |
| **Strategies** | — | No direct changes |
| **Portfolio** | 1, 5, 6, 8 | `max_size_pct` sizing, exit verdicts, factor exposure, suppression banner |
| **Performance** | 0, 3, 4, 5, 6 | Flip rate, WATCH conversion, profile-matched backtest, survivorship-adjusted WR, calibration curve, SPY-relative alpha, false negatives, MFE/MAE, per-trade exit reason |
| **Screener** | 1, 2, 3, 4, 6, 7, 8 | Config-driven setup gates, active-config banner, decision log, hysteresis, AVOID tiering, "why this verdict?", watchlist trigger prices, signal-age |
| **Themes** | 6 | Factor exposure |
| **Research** | 8 | "Why this verdict?" |
| **Leveraged** | — | No direct changes |
| **Industries** | — | No direct changes |
| **Market** | 6 | Factor exposure |
| **Crypto** | — | No direct changes |
| **Playbook** | 4, 6 | Per-setup CI, MFE/MAE efficiency |
| **Guide** | — | No direct changes (docs only) |
| **Reference** | 4 | Backtest result tables |
| **System Status** | 0, 2, 3, 7, 8 | `max_size_pct` visibility, config banner, decision log, threshold breakdown, suppression banner |
| **Settings** | 0, 1, 2 | Validator, setup_gates config, catalyst override, watch_min_score, regime4 completeness |

---

## Progress Log

| Date | Phase | Items done | Items blocked | Notes |
|---|---|---|---|---|
| 2026-04-15 | 0 | 0.1–0.4 | — | Validation complete; added 1.7 (`max_size_pct` wiring) |
| 2026-04-15 | Wave 1 | Config schema+validator (A), Observability infra (C), Banner+drift (E) | — | 3 parallel agents: setup_gates live in all profiles, decision_logger.py created, print_active_config_banner wired, drift_check emits compliance line |
| 2026-04-15 | Wave 2 | Decision rewiring (B), Sizing+exits (D) | — | 2 parallel agents: analysis.py reads setup_gates/catalyst_offset/rsi_cap/avoid_below from config; hysteresis ±2 added; log_decisions_batch wired; max_size_pct applied in sizing; classify_exit_state appended; EOD runs classifier; exit_signals.jsonl persisted |
| 2026-04-15 | Wave 3 | Quality metrics (6), Code quality (7), UI (8) | Phase 4 still pending | 3 parallel agents: calibration.py + false_negatives.py + factor_exposure created; SPY-relative alpha + setup efficiency added; effective_buy_min extracted as pure fn; 52wk elite branch instrumented; setup weight multiplier now sizing-only; AVOID tier field added; why-panel + watch-trigger + suppression banner + RS-age chip all wired into html_generator + analyze.html |

---

## Effort & Sequencing

| Phase | Effort | Cumulative | Blocking? |
|---|---|---|---|
| 1 Unblock migration | 4–5 hrs | 5 hrs | Yes — scan must work |
| 2 Safety rails | 2 hrs | 7 hrs | Yes — prevents silent regressions |
| 3 Observability | 4 hrs | 11 hrs | Yes — can't tune without data |
| 4 Backtest rerun | 2 hr setup + overnight | 13 hrs | Yes — hard gate before live |
| 5 Exit logic | 6 hrs | 19 hrs | Yes for live trading |
| 6 Signal quality | 4 hrs | 23 hrs | No — post-launch iteration |
| 7 Code quality | 2 hrs | 25 hrs | No |
| 8 Usability | 2 hrs | 27 hrs | No |
| Paper gate | 7 days | — | Yes |
| Live gate | ~6 weeks to 30 trades | — | Yes |

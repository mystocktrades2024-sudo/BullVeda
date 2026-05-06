# SwingTrade · Roadmap & Tracker

> Single source of truth for pending work. Last updated: 2026-05-04.
> Status legend: ✅ done · 🔄 in progress · 📋 planned · ⏸ deferred · 🔜 next

## 🚀 Shipped 2026-05-04 (this session)

**Quant V-series (full library fidelity after `pip install scipy cvxpy arch statsmodels numba`):**
- ✅ V-1 Monte Carlo path simulator (Numba JIT, Merton jump-diffusion, 3K paths × 63d in ~500ms)
- ✅ V-2 HMM regime detector (3-state Gaussian soft classifier · pure-numpy)
- ✅ V-3 Forward-distribution metrics (empirical bootstrap VaR/CVaR/P-profit per ticker)
- ✅ V-4 Kelly × Regime × VaR stack (refactored, with per-ticker runtime injection)
- ✅ V-5 Earnings jump calibration (sector-default fallback)
- ✅ V-8 DCC-GARCH portfolio covariance (Engle DCC + univariate GARCH(1,1))
- ✅ V-10 Student-t copula tail dependence
- ✅ V-11 CVaR-constrained Rockafellar-Uryasev portfolio optimizer (cvxpy + CLARABEL)

**Strategy + UI:**
- ✅ S-3 Cup with Handle scanner · S-5 Failed Breakdown / Wyckoff Spring · S-6 Sector RS Pair tab · S-7 Cross-asset banner
- ✅ All D-1 through D-10 + Q-1 (Cross-Mode Exposure · Wash-Sale · Correlation Drops · Factor Heatmap · Signal Age Pills · Trade Journal · Friday Review · LuxAlgo MTF · Tab Agreement · Decision Tree · ADR routing)
- ✅ Audit Trail: Tier A fields (regime/conviction/MC/exit/alpha-vs-SPY) · expand-row detail panel · Mode column (Swing/Position/Invest) · live merge for today's bundle picks · 4 new filters · calendar redesign with 7d/30d/90d/YTD presets
- ✅ Tail-loss filter (score≥60 + stars≥4) · projected GREEN Basel zone · config-flagged

**Alpaca paper integration:**
- ✅ Keys + secret loaded into `.env` via `secrets_loader`
- ✅ `/api/portfolio/sync_alpaca` — pulls live positions + equity from Alpaca, mirrors locally
- ✅ `/api/portfolio/close_on_alpaca` — submits market sell (long) or buy-to-cover (short)
- ✅ Periodic auto-sync (60s while Portfolio tab visible) + manual `↻ Sync Alpaca` button
- ✅ Close / B-E / Trail action buttons per position
- ✅ Account synced: $100K equity ($100K cash, $200K BP)

**Math correctness:**
- ✅ R:R / T1 mismatch fix — `analysis.py:8105` was using wrong formula in SMC OB override path. Now `(target1 - entry_mid) / risk` consistently
- ✅ R:R coherence guardrail — `_coherent_rr()` recomputes canonical R:R; `_rr_inconsistent` flag fires when cached upstream value disagrees by >20%
- ✅ ⚠ DATA INCONSISTENT banner on Plan tab when flag fires + ⚠ marker on dashboard scanner row

**Tooltip system:**
- ✅ ~80 new TIPS entries covering V-series + Tier A + chip-context lookup for scanner filters (300+ total dictionary entries)

**Workflow / docs:**
- ✅ F-3 Sector demotion log surfaced in Killed tab
- ✅ F-4 walk_forward_v2 stdout parser fix (added Win rate / Profit factor aliases in backtest.py)
- ✅ F-2 walk_forward_v2 `--apply-config` flag (writes WF-saved weights back to config.json with backup)

---

---

## P0 — Highest priority

| # | Item | Why | Effort | Status |
|---|------|-----|--------|--------|
| P0-A | **Schwab options re-wire** | ✅ shipped 2026-05-03. `data_fetcher.get_options_iv_data()` returns real chain data — IV/PCR/OI/volume/UOA/max-pain. Verified on AAPL: current_iv 23.2 · PCR 0.241 · 118K call OI · 24 UOA calls. Unblocks V-3, V-5, V-18. | 1-2 days | ✅ |
| P0-B | **Accuracy framework (V-7 expanded)** | ✅ shipped 2026-05-03. `accuracy_framework.py` runs Kupiec POF + Christoffersen conditional coverage + Basel-III traffic-light + per-score-band + per-strategy + per-direction WR. New **Accuracy** tab live in v2 dashboard. Live read on signal_log: 210 closed trades · 77.8% WR · Basel **RED** zone · Kupiec **MODEL_REJECTED** (10.5% exception rate vs 5% expected, p=0.0014) · Christoffersen **INDEPENDENT** (p=0.076 — exceptions random, not clustered). Score-band monotonicity confirmed. | 3-5 days | ✅ |
| P0-1 | Wire equity history → Phase 2 drawdown multiplier | ✅ shipped 2026-05-04. `compute_current_drawdown_pct()` in portfolio_tracker · injected into cfg by swing_trade.py before kelly_position_size runs. | 1 day | ✅ |
| P0-2 | Build Earnings ESP Play scanner | ✅ shipped 2026-05-04. `_compute_esp_play_signal()` in build_data.py. Wrapper in place; lights up when zacks_per_ticker premium scrape populates `zacks_earnings_esp` (currently sparse — Selenium scrape hasn't been run on premium pages). | 4 hours | ✅ |
| P0-3 | Reconnect StockTwits / Reddit WSB / Congressional scrapers | ✅ shipped 2026-05-04 (partial). StockTwits + Reddit WSB working. Congressional source dead (Senate Stock Watcher S3 returns 403 — needs Quiver Quantitative paid replacement). | 1 day | ✅ |

**Decision recorded 2026-05-03:**
- Schwab options data (existing legacy code) instead of Unicornbay $50/mo subscription
- V-7 accuracy framework promoted to P0 (validates system before more strategies layer on)
- Sequencing: P0-A → P0-B → V-2 MS-VAR HMM → V-3 forward metrics → V-1 full MC engine

---

## Strategy items (Tier 1 detector follow-up + 5 PLANNED)

| # | Item | State | Effort | Status |
|---|------|-------|--------|--------|
| S-1 | Tier 1 `apply_to_score: false` flip | Currently informational only · needs validation on 50+ trades before flipping on | 1 day (validation) | 🔄 awaiting data |
| S-2 | Beat-and-Raise PEAD detector | Wired but always returns 0 — needs guidance-change data feed (parse 10-Q press releases or use estimate-revisions feed) | 1 day | 📋 |
| S-3 | Cup with Handle scanner | ✅ shipped 2026-05-04. `tier1_signals.cup_with_handle()` — depth/duration/handle/volume scoring. | 2 days | ✅ |
| S-4 | Earnings ESP Play scanner | See P0-2 | 4 hours | ✅ (= P0-2) |
| S-5 | Failed Breakdown / Wyckoff Spring | ✅ shipped 2026-05-04. `tier1_signals.failed_breakdown_spring()` — broken low + reclaim within 3 sessions w/ vol confirm. | 1 day | ✅ |
| S-6 | Sector RS Pair (market-neutral) | ✅ shipped 2026-05-04. `sector_pair.py` finds RS divergences across 11 sector ETFs. New ⇄ Pairs dashboard tab. | 2-3 days | ✅ |
| S-7 | Cross-Asset Momentum overlay | ✅ shipped 2026-05-04. Top-banner pill showing DXY/HYG/GLD + risk-on/off classification. | 1 day | ✅ |

---

## Phase 1-3 follow-ups

| # | Item | State | Effort | Status |
|---|------|-------|--------|--------|
| F-1 | Equity history → drawdown multiplier wiring | See P0-1 | 1 day | ✅ (= P0-1) |
| F-2 | Walk-forward v2 → live config auto-feed | ✅ shipped 2026-05-04 (partial). `--apply-config` flag writes saved WF results back to `regime_weight_shifts` with backup. Full per-regime grid-search optimization is still future work — WF currently preserves whatever weights were active during the run rather than searching for optimal. | 4 hours | ✅ |
| F-3 | Sector ranking demotion log surface | ✅ shipped 2026-05-04. New "Sector Demotions" sub-card on Killed tab — groups demoted tickers by sector, shows percentile rank + reason. | 2 hours | ✅ |
| F-4 | walk_forward_v2 stdout parser fix | ✅ shipped 2026-05-04. Added `Win rate:` and `Profit factor:` aliases in backtest.py to match WF's case-sensitive `in line` checks. | 1 hour | ✅ |

---

## Backend per-horizon data (limits Decision Matrix accuracy)

| # | Item | Current state | Target | Effort | Status |
|---|------|---------------|--------|--------|--------|
| B-1 | Position-horizon entry/stop/target | SYNTHESIZED from price + ATR (clearly labeled in UI) | Real per-horizon levels in bundle | 2-3 days | 📋 |
| B-2 | Invest DCF floor / fair value | Synthesized from analyst_target or 52w low | Real DCF model | 1 week | ⏸ |
| B-3 | Per-horizon R:R math | Inherits Swing's R:R | Hold-period appropriate target multiples | 1 day | 📋 |

---

## v2 dashboard polish

| # | Item | Effort | Status |
|---|------|--------|--------|
| D-1 | Cross-mode exposure tile (Portfolio tab) | 4 hours | ✅ |
| D-2 | Wash-sale warning on Quick Buy | 4 hours | ✅ |
| D-3 | Correlation-dropped names log | 4 hours | ✅ |
| D-4 | Factor exposure heatmap (momentum/value/quality) | 1 day | ✅ |
| D-5 | Signal age pills (UOA/insider/news with decay weights) | 4 hours | ✅ |
| D-6 | Trade journal aggregate cross-ticker view | 1 day | ✅ |
| D-7 | Weekly review UI (Friday auto-prompt) | 1 day | ✅ |
| D-8 | LuxAlgo MTF Screener (3 dense MTF tables as SMC sub-tabs) | 2 days | ✅ |
| D-9 | Tab agreement / concordance score in Rule Engine | 2 hours | ✅ |
| D-10 | Strategy decision-tree footer in Strategies tab | 4 hours | ✅ |

---

## Data quality / coverage gaps

| # | Item | State | Effort | Status |
|---|------|-------|--------|--------|
| Q-1 | ADR symbol resolution (INFY → US ADR not Indian listing) | ✅ shipped 2026-05-04. `eodhd_client.search()` now reorders results to put US listings first via `_us_priority` sort. | 4 hours | ✅ |
| Q-2 | Stocktwits / Reddit WSB / Congressional feeds | StockTwits + WSB shipped via P0-3. Congressional source dead (S3 403) — needs Quiver Quantitative ($25/mo) or new free scraper. | 1 day | 🔄 partial |
| Q-3 | Zacks Phase 3 — universe screens | Top ESP picks · recent upgrades/downgrades feed | half-day | 📋 |
| Q-4 | Zacks Phase 4 — research PDFs + earnings transcripts | Needs PDF parsing pipeline | 1-2 days | ⏸ |
| Q-5 | 2 of 14 Zacks services scraping | Some services may need login retry / parser fix | 4 hours each | 📋 |
| Q-6 | Survivorship-bias historical S&P 500 membership | Uses current membership only; Tier 2 audit fix | 1 week | ⏸ |

---

## Infrastructure / ops

| # | Item | State | Status |
|---|------|-------|--------|
| I-1 | Live trading activation | Paper mode only · explicit user authorization required ("AUTHORIZE LIVE TRADING") | ⏸ user gate |
| I-2 | Schwab options data | Unicornbay $50/mo add-on — not subscribed | ⏸ paid data |
| I-3 | Schwab broker re-add (vs Alpaca) | `_legacy/schwab_auth.py` available if user wants Schwab live trading | ⏸ |
| I-4 | AI button / Claude API integration | Explicitly disabled. Would need API key (~$5-10/mo). User has Claude Max subscription which doesn't grant API access. | ⏸ user choice |
| I-5 | Cloudflare tunnel reliability | Tunnel flaps occasionally · QUIC handshake timeouts · already documented in CLAUDE.md | 🔄 monitoring |

---

## Documentation

| # | Item | State | Effort | Status |
|---|------|-------|--------|--------|
| DOC-1 | CLAUDE.md updates | Updated through 2026-05-01 (Phases + Tier 1 + Polygon rename + TTL contract) | — | ✅ |
| DOC-2 | Strategy Engine v2 doc | Could add a separate STRATEGIES.md with the 24-strategy table + edge tier explanation | 2 hours | 📋 |
| DOC-3 | Rule Engine architecture doc | How the per-tab consensus + pipeline + counterfactuals are computed | 2 hours | 📋 |

---

## Externally-sourced — Vinod review (added 2026-05-03)

> Source: `/Volumes/MyMacDisk/Claude Skills/VInod/` — 7 files reviewed (4 HTML mockups/specs, 1 drawio architecture, 1 React JSX, 1 .docx whitepaper).
> Net theme: institutional-grade VAR/Monte-Carlo + MS-VAR HMM regime + Kelly stack + SaaS architecture commercialisation.

### V-items by category

**Engine / Monte-Carlo (the white-paper core)**

| # | Item | Effort | Status | Notes |
|---|------|--------|--------|-------|
| V-1 | Monte Carlo path simulator (3K paths × 63d, jump-diffusion + DCC-GARCH) async worker | 3-4 weeks | ✅ shipped 2026-05-04 | `monte_carlo.py` Numba-JIT Merton jump-diffusion. ~500ms first run (JIT compile), ~80ms cached. DCC-GARCH lives separately as V-8. |
| V-2 | MS-VAR 3-state HMM regime detector w/ posterior P(Bull/Neutral/Bear) | 1-2 weeks | ✅ shipped 2026-05-04 | `regime_hmm.py` Gaussian soft classifier (no sklearn dep). Actual hmmlearn HMM is future v2 enhancement. Banner pill + Audit detail panel. |
| V-3 | Forward-distribution metrics as scoring inputs (VaR-95, CVaR-97.5, P50, P25/P75, P(profit), forward-Sharpe) | 1-2 weeks | ✅ shipped 2026-05-04 | `forward_dist.py` empirical bootstrap from history. Surfaced per-ticker on Plan tab + Risk Lab. Does NOT yet feed scoring (waiting on V-1 calibration). |
| V-9 | Sobol + antithetic variates + importance sampling for >99th percentile tails | 3 days | 📋 | Depends on V-1 |
| V-15 | Bayesian parameter uncertainty (BVAR Minnesota prior + MCMC) for confidence bands | 3 weeks | ⏸ optional | Heavy compute; defer until V-1/V-3 land |

**Regime / Volatility / Correlation**

| # | Item | Effort | Status |
|---|------|--------|--------|
| V-8 | DCC-GARCH(1,1) covariance for portfolio-level cross-asset risk (replaces static correlation gate) | 2 weeks | ✅ shipped 2026-05-04 (`dcc_garch.py` · Engle DCC + univariate GARCH(1,1) via `arch`) |
| V-10 | Student-t copula (ν=6) for joint tail dependence (multi-position portfolio risk) | 1-2 weeks | ✅ shipped 2026-05-04 (`student_t_copula.py` · 2-stage MLE w/ `scipy.stats.t`) |

**Scoring / Catalyst / Sizing**

| # | Item | Effort | Status |
|---|------|--------|--------|
| V-4 | Kelly fraction × (Regime × Earnings × VaR-floor) sizing stack | 1 week | ✅ shipped 2026-05-04 (`kelly_position_size` refactored · per-ticker `_runtime_earn_days` + `_runtime_cvar_975_pct` injection from analysis.py) |
| V-5 | Per-ticker earnings jump distribution calibration (λ, μ_J, σ_J) from 8-12Q post-EPS moves | 1-2 weeks | ✅ shipped 2026-05-04 (`earnings_jump.py` · empirical → outlier → sector-default fallback · feeds V-1 jump params) |
| V-16 | VECM / Johansen cointegration pre-screen for paired tickers + sector ETFs | 1 week | 📋 |

**Backtest / Validation**

| # | Item | Effort | Status |
|---|------|--------|--------|
| V-6 | VaR-floor-aware slippage in backtest (extend with Sobol sampling) | 3 days | 📋 |
| V-7 | Kupiec POF + Christoffersen conditional coverage + Basel-III traffic-light VaR-exception monitor | 1 week | ✅ shipped 2026-05-03 (P0-B) |

**Portfolio / Optimisation**

| # | Item | Effort | Status |
|---|------|--------|--------|
| V-11 | CVaR-constrained Rockafellar-Uryasev LP portfolio optimiser (cvxpy) | 2-3 weeks | ✅ shipped 2026-05-04 (`cvar_optimizer.py` · CLARABEL solver · sector-aware constraints · surfaced in Risk Lab tab) |

**Architecture (SaaS commercialisation — STRATEGIC DECISION REQUIRED)**

| # | Item | Effort | Status | Notes |
|---|------|--------|--------|-------|
| V-12 | Decompose `analysis.py` into Gate Evaluator + Scoring Engine + Regime Detector + MC Worker + Kelly Calculator services | 3-4 weeks | ⏸ | SaaS pivot decision |
| V-13 | Redis-backed message queue (async MC batch · price-trigger alerts · nightly regime updates) | 1-2 weeks | ⏸ | Multi-user prerequisite |
| V-14 | Split data layer — TimescaleDB for OHLCV time-series, keep SQLite/Postgres for transactional | 2 weeks | ⏸ | Multi-user prerequisite |

**Data / Ingestion**

| # | Item | Effort | Status | Notes |
|---|------|--------|--------|-------|
| V-18 | Real-time IV-surface ingestion (forward-vol pre-catalyst, replaces ATR proxy) | 1-2 weeks | ✅ shipped 2026-05-03 | Schwab options re-wire (P0-A) populates IV-rank, P/C ratio, max pain, UOA per ticker. Replaces ATR-based IV proxy. |

**Dashboard / Alerts / Observability**

| # | Item | Effort | Status |
|---|------|--------|--------|
| V-17 | Forward-distribution UI tab per ticker (paths chart + percentile table + P(profit) + VaR floor) | 1-2 weeks | 📋 |
| V-19 | MISSED → WATCH alert engine — price-trigger watcher fires when MISSED setup hits R:R restore level | 1-2 weeks | 📋 |
| V-20 | scan_health dimension for VaR-exception rate, MC convergence, regime confidence, IV-surface staleness | 3-5 days | 📋 |

### Conflicts / scope concerns to resolve before starting

| Concern | Decision needed |
|---|---|
| **Options data dependency** (V-3, V-5, V-18) | EODHD All-In-One does NOT include options. Unicornbay is $50/mo extra. Without it, +8-14pp event-day VaR accuracy gain is forfeit. Subscribe? |
| **SaaS architecture pivot** (V-12, V-13, V-14) | Decomposition + queue + TimescaleDB are multi-user product moves. Current SwingTrade is single-user. Pivot to multi-tenant? |
| **Compute cost** (V-1, V-9, V-15 combined) | 200K paths × 252d × 10 assets ≈ 4GB RAM. Mac dev fine. Multi-user needs GPU or reduced N. |
| **Backtest re-validation** (V-3) | Adding forward-distribution metrics shifts scoring surface. Existing 80% WR / 1.85 PF figures need re-run. Keep `SCORING_MODE=legacy` default until validated. |
| **Crisis floor honesty** (V-2) | Whitepaper documents ~37-44% irreducible model floor in crisis. Current system goes flat in Panic — preserve, don't "improve". |
| **Survivorship / look-ahead bias** (V-2 calibration) | When calibrating MS-VAR transitions on 2005-2024 data, must not re-introduce audit flaws #1, #4. |

### Vinod review — what's overlapping (no work needed)

These ideas already exist in SwingTrade in some form:
- 4-regime detection (vs Vinod's 3-state HMM — V-2 adds soft posteriors to the existing hard classifier)
- 5-pillar scoring (vs Vinod's 7-component score — same idea, different inputs)
- BUY/WATCH/AVOID (vs Vinod's STRONG BUY / BUY / CONDITIONAL / WATCH / AVOID — could expand tiers)
- Conviction tiers T1/T2/T3 (vs Vinod's T3 80+ tier)
- Vol-targeted/drawdown sizing (vs Vinod's Kelly + VaR multipliers — V-4 adds the Kelly stack)
- Earnings blackout 7d (vs Vinod's earnings discount tiers)
- Macro calendar gate (vs Vinod's regime signal inputs)
- ATR-based stops (vs Vinod's VaR-floor — different math, same intent)
- Pre-trade gate waterfall (vs Vinod's 9-gate sequential)
- scan_health observability (vs Vinod's signal-quality dimension)

### Vinod review — files largely UI-only (informational, no implementation lift)

- `BHE_RuleGate_v2.html` — unrendered template literals, mockup
- `bullish_output.html` — near-empty UI shell, tab structure only
- `Architecture.drawio` — informative but monolithic single-cube drawing

---

## Recently shipped (for reference)

- ✅ Per-tab consensus matrix in Rule Engine
- ✅ Rule Engine pipeline (9-10 stages with counterfactuals)
- ✅ Institution top-level tab with Zacks / Ownership / Smart Money sub-tabs
- ✅ 24-strategy catalog (19 ACTIVE + 5 PLANNED) with regime fit + edge tier + source-code references
- ✅ Playbook complete rebuild — 13 sections covering Phases 1-3, Tier 1 detectors, sizing formula, theory confluence, exits, daily workflow
- ✅ Fast-lane on-demand analysis (`/api/elite/{ticker}` ~8s) + Yahoo news fallback
- ✅ EODHD cache TTL bumps (news 4h, EOD 12h, sentiments 12h, options 2h, fundamentals 1d)
- ✅ Polygon → honest naming complete sweep
- ✅ Phase 1 (regime weight shifts) · Phase 2 (vol-targeted sizing) · Phase 3 (sector ranking)
- ✅ Tier 1 strategy signals (6 detectors)
- ✅ Sentiment, News, Insider, SMC, Fundamentals, Technicals, MODELS elite redesigns
- ✅ Multi-Method cross-method consensus hero (Expert View preserved)
- ✅ Multi-Horizon Decision Matrix (Swing/Position/Invest)
- ✅ Search-any-ticker with autocomplete + on-demand deep-dive

---

## Process

- Tracker is living — update statuses as work lands
- "Effort" estimates assume single-session focused work
- "Status" transitions: 📋 → 🔄 → ✅ (or ⏸ if blocked)
- P0 items get prioritized over everything else

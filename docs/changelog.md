# SwingTrade — Shipped Enhancements Changelog

Append shipped feature blocks here rather than into root CLAUDE.md. The active
config knobs and wire locations stay in code; this file is for the *narrative*
of what shipped and when, so root CLAUDE.md can stay lean.

---

## 2026-05-18 — AI Prediction tab · universe expansion · rolling-Sharpe bug fix

Three thematically linked shipments in one session: a workspace-grade AI Prediction surface, universe expansion to ~3000 tickers, and a critical fix to the rolling-Sharpe brake that had been falsely pausing all new BUYs.

### A · AI Prediction sub-tab (23 modules) — `AIPRED-CORE`

New comprehensive forecasting workbench under **ML Edge → ✦ AI Prediction**, shared between the Workspaces tab and the QuantDetail per-ticker view via `window._qdMlAiBody`. Modules:

1. Coverage banner with universe pills + sector-coverage gap + survivorship indicator
2. Hero cone chart (SVG, q10/q25/q50/q75/q90, confidence-shaded)
3. **Trade-Exec strip** — Side · Entry · Stop · T1 (q50) · T2 (q75) · R:R · ½-Kelly · 📋 copy ticket
4. Live-status chips — prediction age · spot Δ since pred · % of q50 captured · trained · stability badge · position-model warning
5. Stress overlay (VIX +50% / SPY −2%, real bucketed shift from historical data)
6. Landmines bar (earnings + macro events in horizon)
7. Walk-forward equity curve (real picks_history when ≥5 resolved, score-band proxy otherwise) + Sharpe + WR + PF + max DD
8. Cross-horizon coherence (3 mini-cones for swing/position/invest with banner)
9. Forward distribution histogram (10-bin PDF from quantiles)
10. Calibration card + reliability diagram + 30-day AUC drift sparkline
11–14. Universe scans grid: Top 10 Bulls · Top 10 Bears · Horizon-Flip · R:R Reward — with top-SHAP-driver per row
15. Sector rollup heatmap
16. Auto-suggested pair trades (market-neutral within sector)
17. Open positions overlay (mini-cone + HOLD/TRIM/EXIT/ADD AI verdict)
18. Δ vs yesterday
19. R2000 alpha leak
20. 30-day drift trend
21. Why-missed failure log (expandable)
22. Launchd install banner
23. Inline side drawer for row-click preview

UX layer: parallel async fetches · URL state persistence (`#aip:swing:all:NVDA`) · keyboard shortcuts (1/2/3/4 + Esc) · mobile responsive grid · compact-banner toggle.

### B · Universe expansion — 2960 tickers — `AIPRED-UNIVERSE` + `AIPRED-SURVIVORSHIP`

`ml/universe_loader.py` aggregates S&P 500 (503) + R1000 (981) + R2000 (1963) via EODHD index_components → 2960 unique. `run_ml_edge.py --universe {bundle|sp500|r1000|r2000|all|custom:NAME}` flag. `--min-adv` liquidity filter. Membership flags stamped per-payload. Point-in-time snapshots: `data/membership/{sp500|r1000|r2000}_YYYY-MM.csv` — monthly launchd captures the baseline. Survivorship haircut tracker via `/api/membership-history`.

### C · Real Schwab spread overlay — `AIPRED-SCHWAB`

Replaces ADV-band heuristic for top-100 picks per mode. Calls `schwab_client.get_quotes_batch()`, reads `q.quote.bidPrice`/`askPrice`, computes real `spread_bps`, recomputes `q50_net`. Stamps `spread_source: 'schwab_live'`. Live on 182 tickers in production verification.

### D · Real VIX-regime stress — `AIPRED-STRESS`

Replaces heuristic with bucketed mean from 355,128 historical samples (`scripts/build_stress_buckets.py` → `cache/ml/stress_buckets.json`). Three scenarios: base, spy_down (156K), vix elevated (37K). UI cone label distinguishes `STRESS · real` vs `STRESS · heuristic` fallback.

### E · Autonomous launchd refresh — `AIPRED-AUTOREFRESH`

Three new plists installed at `~/Library/LaunchAgents/`:
- `com.swingtrade.ml-edge.plist` — daily 5 AM PT full universe
- `com.swingtrade.ml-edge-intraday.plist` — top-100 every 2h during market hours (9/11/13 PT)
- `com.swingtrade.membership-snapshot.plist` — monthly on the 1st at 6 AM PT

### F · Picks-history closed loop — `AIPRED-TRACK`

30 top picks per mode logged to `cache/ml_edge_picks_history.jsonl` per run. `scripts/resolve_ml_picks.py` backfills outcomes via OHLCV lookup. `/api/ml-edge-track` aggregates resolved trades → real WR/avg-R/PF for the walk-forward equity curve.

### G · Slack regression alerts + telemetry

`cache/ml/telemetry.jsonl` per-run wall-time + cache hit-rate + failures. Slack webhook posts when failures jump >25% or calibration health flips. `cache/ml/calibration_history.jsonl` daily → feeds drift sparkline. New endpoints: `/api/calibration-history`, `/api/ml-edge-diff`, `/api/ml-edge-drift`, `/api/ml-edge-telemetry`, `/api/launchd-status`.

### H · 🚀 Momentum workspace tab — `MOMENTUM-TAB`

New sidebar workspace ranking by `composite = raw_momentum_score×0.5 + sharpe_norm×0.25 + rs_rank×0.25`. Filterable by setup family + grade A/B/C. Sector rollup. Sidebar count = Grade-A + composite≥80.

### I · 🔴 CRITICAL FIX · rolling-Sharpe brake firing on contaminated data — `ROLLING-SHARPE-FIX`

Two upstream bugs were poisoning `data/signal_log.json`:

1. **WATCH-conviction contamination** — `swing_trade.py` line 3110 was writing `verdict='BUY'` for picks in `buy_candidates` even when conviction was WATCH (paper-only, no sizing). 133 mislabeled rows.

2. **Same-trade duplicate logging** — Resolver re-emitted same closed trade as fresh daily signal. VRT stop hit counted 3× in rolling-20. 90 duplicates total.

**Net effect:** real rolling Sharpe was −0.42; contaminated data reported −1.732, activating the system-wide brake. WULF and other strong setups scored 0 across the board.

Three-layer fix:

| Layer | Where | What |
|---|---|---|
| Writer (upstream) | `swing_trade.py` `_resolve_verdict()` | If conviction is WATCH, override bucket label to WATCH before writing |
| Reader (compute-time) | `decision_engine.compute_rolling_sharpe_kill_state()` | Dedupe by (ticker, entry_price, pnl, exit_reason); filter conviction='WATCH' |
| Historical (one-shot) | `scripts/dedupe_signal_log.py` | Corrected 133 mislabels + removed 90 dupes; backed up at `data/signal_log.json.bak-20260518-174936` |

**Verification:** post-fix rolling Sharpe = **−0.299** (above −0.50 threshold) → brake inactive → 5 fresh BUY candidates (ORCL/Q/AVGO/DVN/SLB).

### J · UI fixes downstream of the kill discovery

- **Pre-Mortem banner** (`PREMORTEM-REASON`) now reads `t.decision.reason` and surfaces actual kill cause (PORTFOLIO SAFETY BRAKE / HARD GATE FAIL / SYSTEM KILL) instead of "ER in 0d" boilerplate.
- **Composite Score = 0** label (`SCORE-ZERO-LABEL`) distinguishes: PORTFOLIO BRAKE · HARD GATE · SUPPRESSED · SUB-THRESHOLD based on real reason.
- **setDetailTicker** (`SETDETAIL-FALLBACK`) falls back to `window.__mlEdgeCache` when ticker isn't in scan bundle — R2000-only ML Edge picks (HOOD, ARES, STEM) can now open the detail page.

### Files touched

```
analysis.py                              # SHAP per-row plumbing
data_fetcher.py                          # get_universe_as_of reads R1000/R2000 snapshots
decision_engine.py                       # rolling-Sharpe dedupe + WATCH filter
ml/run_ml_edge.py                        # --universe + --min-adv + --limit + Schwab spread + picks capture + telemetry + slack
ml/universe_loader.py                    # NEW · S&P/R1000/R2000 loader + custom universes
scripts/build_stress_buckets.py          # NEW · 355K-sample stress bucketing
scripts/dedupe_signal_log.py             # NEW · one-shot historical cleanup
scripts/resolve_ml_picks.py              # NEW · ML-edge paper-pick outcome resolver
scripts/snapshot_membership.py           # NEW · monthly index membership capture
server.py                                # 7 new endpoints
swing_trade.py                           # _resolve_verdict (WATCH override)
infra/launchd/com.swingtrade.ml-edge.plist             # NEW
infra/launchd/com.swingtrade.ml-edge-intraday.plist    # NEW
infra/launchd/com.swingtrade.membership-snapshot.plist # NEW
infra/prototype/kairos.html              # AI Prediction sub-tab + Momentum workspace + UI fixes
data/membership/r1000_2026-05.csv        # NEW · today's R1000 baseline
data/membership/r2000_2026-05.csv        # NEW · today's R2000 baseline
data/universes/example_watchlist.yml     # NEW · custom-universe example
```

### Operational unlocks

- Full universe of 2960 tickers scored daily (autonomously)
- 5 BUY candidates available today after rescan (system was at 0 before the fix)
- Real walk-forward track record starts accumulating tomorrow (resolver picks up matured paper picks)
- Survivorship haircut starts shrinking from 3pp toward 0.5pp as monthly snapshots accumulate over 24+ months

---

## 2026-05-01 — Strategy enhancement bundle

All four phases below are config-flagged in `config/config.json` and additive — they do not break existing scoring. Set `_enabled: false` on any block to roll back.

### Phase 1 — Walk-forward regime weights (live scoring)

Per-regime tech/qg pillar shifts now read from `config.regime_weight_shifts` (was hardcoded). Walk-forward optimal weights paste directly into config:

```json
"regime_weight_shifts": {
  "_enabled": true,
  "risk_on_trending":  { "tech":  3, "qg": -3 },
  "risk_on_choppy":    { "tech":  0, "qg":  0 },
  "risk_off_trending": { "tech": -5, "qg":  5 },
  "panic":             { "tech": -8, "qg":  8 }
}
```

Wire location: `analysis.py:7769` (replaces hardcoded `_bear_shift` / `_bull_shift`).

### Phase 2 — Vol-targeted / drawdown sizing

`config.portfolio_vol_targeting` adds per-trade size multiplier based on drawdown from peak equity. Currently a no-op (multiplier=1.0) until equity history is wired by `portfolio_tracker`. Bands:

| Drawdown | Size multiplier |
|---|---|
| Above peak / 0–3% | 1.00× |
| 3–5% | 0.85× |
| 5–10% | 0.65× |
| 10–15% | 0.40× |
| > 15% | 0.20× |

Wire location: `analysis.py:kelly_position_size`. Bundle field: `kelly_size.drawdown_mult`, `kelly_size.drawdown_pct`.

### Phase 3 — Cross-sectional sector ranking

Post-scoring step computes `sector_pct_rank` (0–100) per ticker, demotes BUY → WATCH if rank < threshold (default 60th percentile within sector). Forces relative-strength selection vs absolute score floor.

```json
"sector_relative_ranking": {
  "_enabled": true,
  "min_sector_percentile_for_buy": 60.0,
  "demote_to_watch_below_threshold": true,
  "min_candidates_per_sector_for_ranking": 3
}
```

Wire location: `swing_trade.py:2871` (after VIX kill switches, before bundle write). Uses `cfg`, not `config` (caught in 2026-05-01 hot fix).

### Tier 1 — 6 additive strategy signals (`tier1_signals.py`)

Pure-function detectors that compute additive points per ticker. Default `apply_to_score: false` (informational only — surfaced in `tier1_signals` bundle field for ranking tiebreakers and dashboard display).

| # | Detector | Trigger | Points |
|---|---|---|---|
| 1 | Insider cluster | 3+ insiders 30d, +CEO/CFO bonus, +urgency bonus | up to +12 |
| 2 | Beat-and-Raise | EPS+Rev+ guidance="raised" (currently no-ops — needs guidance data wired) | +8 / -3 |
| 3 | NR7 / Inside Day | Today's range = narrowest of 7 OR inside yesterday's | up to +6 |
| 4 | Volume Dry-Up | 5d vol < 0.7× 20d AND price near EMA21/50 AND not declining | +3 |
| 5 | OBV Divergence | Bull/bear divergence over 20d window | +5 / -5 |
| 6 | Mean Reversion | RSI<35 + above 200SMA + fund≥4 + ATR<6% + not falling-knife | up to +10 |

Cap: ±8 net points when `apply_to_score: true`.

### Zacks v2 (rebuild for legacy retirement)

Surfaced bundle-level Zacks data + new per-ticker enrichment:

- **Bundle-level**: `zacks_universe` (r1_full, r1_missing, r1_scores, sell_list), `zacks_premium_services` (16 services), `zacks_email_digest`
- **Per-ticker**: `zacks_held_by_services`, `zacks_email_mentions`, `zacks_rank_rationale`, plus Phase 1 enrichment fields (`zacks_industry_rank`, `zacks_earnings_esp`, `zacks_lt_growth`, `zacks_recommendation`, `zacks_estimate_revisions`, `zacks_revision_counts`, `zacks_eps_surprise_history`, `zacks_brokerage_recommendations`)
- **v2 Zacks tab**: new tab in elite-detail.html (verdict banner + style scores + service membership + email digests + Phase 1 enrichment panels + horizon impact)

Premium services scraped (12 of 14 currently): ultimate, tazr, bbt, counterstrike, headlinetrader, alt_energy, blockchain, tech_innovators, surprise_trader, insider_trader, value_investor, home_run_investor, income_investor (added 2026-05-01).

Per-ticker enrichment (`zacks_per_ticker.py`): lightweight `requests` pass for Industry Rank + ESP + LT Growth + Recommendation; Selenium pass (uses logged-in driver) for Estimate Revisions + Surprise History + Broker Recs. Capped at top 60 R1 tickers per scan, 6h cache.

---

## Earlier shipped batches (single session, 8 commits)

- **Batch 1** (10 items): tests, UX polish, correlation banner, DOM-patch, gap handling, what-if simulator, schema versioning, killed-drift alert
- **Batch 2** (7 items): legacy migration, undo-close, live price polling, log rotation, position alerts, earnings warnings, daily backups
- **Batch 3** (6 items): FastAPI migration, + Add Position button, HTML split (18MB→3.6MB), SQLite migration, paper trading activation CLI, + Add custom ticker
- **Audit Batch** (all 10 flaws): backtest-live parity, Kelly sizing, Wilson CI, walk-forward v2, realistic slippage, entry_quality mapping, survivorship haircut, scoring normalization flag, fundamentals flag
- **Earlier**: secrets rotation, portfolio.py deprecation, correlation gate, industry cap, conditional 52wk Breakout, elite-RS override

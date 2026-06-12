# SwingTrade — Shipped Enhancements Changelog

Append shipped feature blocks here rather than into root CLAUDE.md. The active
config knobs and wire locations stay in code; this file is for the *narrative*
of what shipped and when, so root CLAUDE.md can stay lean.

---

## 2026-06-11 — Thesis Chart RSI/MACD sub-panes: un-truncate in full mode + on by default

**Bug:** In the Thesis Chart full-screen mode (`.tc-full`), the RSI(14) and MACD(12,26,9) oscillator sub-panes were truncated at the bottom of the viewport — only a sliver of MACD showed. Root cause: `.tc-full .tc-chart-card` was `flex:1` without `min-height:0`, so the card grew to fit its *content* instead of staying bounded by the viewport height. The main price pane (`.tc-lw { flex:1 }`) then absorbed nearly all that height and pushed the fixed-height sub-panes below the fold. The panes also carried the default `flex-shrink:1`, so they got squeezed when room was tight.

**Fix** (`infra/prototype/bullveda/`, files `lens-thesis-chart.css` + `src/lens-thesis-chart.jsx`, bundle rebuilt into `BullVeda.html` via `node build_bullveda.cjs`):
- `.tc-full .tc-chart-card` → added `min-height:0` so the card honors its viewport-bounded `flex:1` height.
- Added `.tc-full .tc-osc { flex:0 0 auto }` so each oscillator pane reserves its 120px and the main chart yields room instead of shoving them off-screen.
- `LensChart` indicator defaults flipped `rsi:false → rsi:true` and `macd:false → macd:true` so both panes render on chart open alongside the Traders Trend Dashboard.

**Commit note:** these changes landed inside commit `edc17ebeb` ("FEAT: remove PRACTICE · REPLAY section from Chart tab") — a concurrent automated process committed the entire working tree at the same moment, bundling this fix under that unrelated message rather than its own. Code is correct and verified in HEAD; only the commit message doesn't reflect it. Logged here for the audit trail.

---

## 2026-05-19 — Per-mode decisions (Option A) · user-agency action bar · backtest guard rail

Multiple shipments in one session. Major theme: dashboard becomes a **trader's cockpit, not a gatekeeper**. The SWING / POSITION / INVEST mode toggle does real work end-to-end, and the user can BUY / SHORT / + WATCH regardless of system verdict.

### A · Per-mode decisions (Option A) — `MODE-1` `MODE-2` `MODE-3`

Pre-2026-05-19, the SWING / POS / INV pills in the detail header were cosmetic — same verdict, stop, T1, T2, R:R across modes. Now each mode applies its own rulebook end-to-end.

**Phase 1 (`3e812743` — `MODE-1`):**
- New `_MODE_RULEBOOK` in `analysis.py` (SWING 1.25× ATR / R:R 3.0 / FRESH-PULLBACK only / 14d ER buffer · POSITION 1.75× ATR / R:R 2.5 / FRESH-PULLBACK-VALID / no ER buffer · INVESTMENT −15% DD / R:R 2.0 / any entry / ER irrelevant)
- `compute_decisions_by_mode()` per ticker runs `make_decision()` 3x with mode-mutated configs
- Output as `t.decisions_by_mode = {swing, position, investment}` with per-mode verdict / stop / T1 / T2 / R:R / size_mult / horizon
- Frontend (`renderQuickActionBar`, `renderPlanTab`, Overview plan strip) reads `t.decisions_by_mode[mode]` via `_qdStrategyCurrent()` with legacy fallback

**Phase 2 (`d5eb49c5` — `MODE-2`):**
- Per-mode `final_alloc_pct = base × size_mult`, capped 5% NAV (CLAUDE.md principle 10 single-name cap)
- New `diverge_note` field surfaces the exact rule that caused divergence from legacy: "R:R 2.4 < 3.0 mode floor" / "entry VALID not in mode gate ['FRESH','PULLBACK']" / "ER in 8d < 14d mode blackout"
- Frontend chip shows "size 5.5% NAV (1.30×)" and amber "⚠ R:R..." divergence pill

**Phase 3 (`6df0095d` — `MODE-3`):**
- New `_MODE_PILLAR_WEIGHTS` (SWING catalyst+tech-heavy · POSITION balanced · INVEST fundamentals-heavy, each sums to 1.0)
- `compute_decisions_by_mode` accepts `pillar_pcts` and computes mode-specific composite = Σ (pct × weight × 100) passed to `make_decision()`
- **Explicit principle-7 override**: weights are intuition, not walk-forward validated. Validation deferred to `MODE-4`.
- Three safety rails: (1) config-gated rollback (`per_mode_pillar_reweight._enabled`, default true), (2) UI-only impact — legacy `t.score` still drives `decision_log` + alerts + kill-list + Wilson LB pipelines, (3) chip shows both scores when divergence ≥5pts ("score 58 (legacy 45)")

**Validation owed (`MODE-4`, OPEN):** `scripts/validate_per_mode_weights.py` (in flight) — baseline + 3 per-mode-weighted backtests, revert flag if any mode shows ≤1.0× PF or ≤−5pp WR vs baseline. Plan in `docs/per_mode_decisions_roadmap.md`.

### B · User-agency action bar — `UI-AGENCY-1` (`c97db4b4`)

Detail page no longer hides BUY when the system says WATCH/AVOID. New sticky `renderQuickActionBar` at top of every detail view shows: ticker + price + verdict chip (informational only) + always-clickable **▲ BUY · ▼ SHORT · + WATCH** buttons. New `window._openQuickAction()` global router handles BUY (long modal), SHORT (short modal), and WATCH (POST `/api/custom/add` with idempotent "already tracked" handling — toast amber-info instead of red-error on duplicate). Memory: `feedback_user_agency_actions.md` ("system informs, user decides").

### C · Backtest min_score guard rail (Path C) — `BT-GUARD-1` (`d754830`)

Users (and Claude sessions) repeatedly launched 252d backtests with `--min-score 65` (the live threshold), producing 0 BUYs across all 252 days. Historical scoring is structurally suppressed (sentiment/options/catalyst pillars depend on real-time data not in EODHD backfill). Guard rail: `backtest.py` now warns loudly when `--min-score > 55` (backtest-safe floor); new `--accept-low-buys` flag silences for legitimate grid-search; `--smoke` bypasses. Full root-cause analysis in `docs/backtest_historical_scoring_diagnostic.md`.

### D · Strategy Lab rebuild — `UI-STRAT-1` (`93ec11842`)

Old Strategy Lab was 4-section table with fake numbers. Rebuilt as 13-section HF cockpit: portfolio cockpit (Kelly cascade per sleeve · current vs target NAV · per-sleeve Sharpe / max-DD / R-mult histogram), setup-family performance (LIVE from `setup_stats.json` with Wilson 95% CI bars + PF haircut + USABLE/HALF-SIZE/SKIP verdict), edge erosion radar (rolling 90d/6mo/12mo decay + KS-drift), BT vs Live divergence (surfaces PEAD canary BT 2.04 vs live 0.88 = −57%), phase promotion ledger, regime×sleeve grid 8×4, correlation 8×8 + eigenvalue λ₁, sleeve interaction overlap, recent picks roster, auto-quarantine surface, mechanism + falsifier, playbook, pre-mortem. Async `_stratLabPatch()` fetches live setup_stats.json.

### E · Crypto tab — 20yr HF analyst lens — `UI-CRYPTO-1` (`696731a4d`)

Old Crypto tab was 4-card stub. Rebuilt as 13-section senior-HF surface fusing cycle posture + Graham-Buffett value floors + swing-trader execution: cycle posture banner (Pi-Cycle / MVRV-Z / NUPL / 200wk MA), spot KPIs, **Margin of Safety floors** (realized price · thermo-cap · cost of production · 200wk MA · LTH/STH cost), ETH owner-earnings DCF, BTC hard-money compounding, stablecoin liquidity, macro drivers, spot ETF flows, derivatives tape, on-chain valuation composite, catalyst calendar, adjacent equities (COIN/MSTR/MARA/RIOT/CLSK/HOOD/IBIT/ETHA + BTC β + NAV premium), L1/L2 rotation, regime-conditional playbook, pre-mortem.

### F · ML Edge theme fix + tf-* visual port — `UI-MLEDGE-1` (`696731a4d`)

ML Edge per-ticker sub-tab had hardcoded dark CSS vars *inline* on `#qd-ml-root`, blocking the `body.light` theme toggle. Moved palette into `_ensureMlEdgeStyles()` stylesheet with `body.light` overrides. Then ported workspace QuantMlEdge to the tape-flow `tf-*` design system: `tf-hero` 3-col + `tf-pulse-strip` 4 live feeds (top bulls / top bears / horizon flips / model health) + `tf-confluence` (4 KPI cells + X/4 filters-passing score) + `tf-vbar` verdict badge. All 6 sections rewritten — no data lost. New memory: `feedback_inline_css_vars_break_theming.md`.

### G · Help registry 14 → 38 entries — `UI-HELP-1` (`696731a4d`)

Help registry covered only workspace tabs. Added 24 new entries: 13 detail sub-tabs (overview / chart / technicals / patterns / smc / value / risk / er_lab / options / detail_portfolio / intel / edge / ml_edge) + 11 MarketsV2 ports (crypto / market / macro / premarket / events / themes / strategies / leveraged / industries / marketmap / audittrail). `kairosHelpFor` now threads `isDetail` through the dispatcher — prefers `K_HELP_CONTENT['detail_' + key]`, falls back to bare key (resolves the portfolio workspace ↔ detail-subtab collision). MarketsV2 render block now calls `_injectHelpBtn` (was previously skipped, so `?` showed the previous tab's content).

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

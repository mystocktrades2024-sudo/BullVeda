# SwingTrade — Shipped Enhancements Changelog

Append shipped feature blocks here rather than into root CLAUDE.md. The active
config knobs and wire locations stay in code; this file is for the *narrative*
of what shipped and when, so root CLAUDE.md can stay lean.

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

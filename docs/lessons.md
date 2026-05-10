# SwingTrade — Lessons Learned

Production-relevant patterns discovered during debugging. Append new entries here rather than into root CLAUDE.md.

---

## 2026-05-10 overnight — GATE-1 / Q1-step5 "system not generating profit" diagnosis

### Lesson 1 — Two-source kill list

`decision_engine.compute_setup_kill_list()` MERGES two sources:
1. **Live signal_log evidence** (computed each scan from `data/signal_log.json`)
2. **`config.static_setup_kill_list`** (manual entries with declared n+wr_lb+source)

When reverting a setup kill, you must remove from BOTH:
- `setup_score_multiplier[setup] = 1.0` (multiplier)
- `static_setup_kill_list[]` (manual entry)

Skipping step 2 leaves the setup kill-listed even if multiplier says 1.0×.
Verify with: `python3 -c "from decision_engine import compute_setup_kill_list; print(compute_setup_kill_list())"`

Real incident: 2026-05-10 A5-followup set TC mult to 1.0 but forgot to remove
the static_setup_kill_list entry; backtest still showed 0 BUYs because TC was
kill-listed via the static path. Fix in commit b02935ad8.

### Lesson 2 — `weekly_df` must be passed to `score_technicals` in backtest

`backtest._score_as_of()` must explicitly resample daily OHLCV to weekly
(`W-FRI`) and pass it to `score_technicals(df, regime, spy_close, weekly_df=...)`.
Without it, `_weekly_ema_alignment(None)` returns `bullish: False`,
`weekly_bull` is False everywhere, and every `setup_gates.*.weekly_bull_required: True`
demotes the BUY to WATCH.

Symptom: backtest produces 0 BUYs across 60+ days even with reasonable thresholds.
Root cause was NOT the kill list, NOT the score floor — it was missing weekly_df.

Resampling daily → weekly is leakage-free (uses only data ≤ as_of_date).
Fix in commit 985cd182b.

### Lesson 3 — Global multipliers can mask regime-specific failures

A setup can have positive expectancy GLOBALLY but lose heavily in ONE regime.

Example (250d backtest 2026-05-10): Trend Continuation had:
- Global: n=140, WR 41%, avg +2.08% — positive expectancy
- BUT in bull regime: n=85, WR 28%, PF 0.55, avg −1.05% — disaster
- AND in neutral regime: n=27, PF 1.75 — works
- AND in bear regime: n=6, PF 2.68 — works

A single global multiplier averages these out. The fix is `setup_score_multiplier_by_regime`
config block (Variant F, commit f0a66543e) which lets you set
`{setup: {bull: 0.0, neutral: 1.0, bear: 1.5}}` per setup. Read by
`analysis.py:8790` block; same demotion gate (n≥30, wr_lb<0.30) applies.

### Lesson 4 — Score floor isn't always the live-BUY blocker

Counterintuitive finding: regime4_thresholds at 80 was raised in 2026-05-08
based on score-band attribution (60-79 band losing). But today's live scan
showed top 5 WATCH all scoring 81-103, blocked by `entry_quality` (EXTENDED
or MISSED), not score floor. **Lowering thresholds doesn't help when the
gate that's actually firing is entry_quality.** Diagnose by reading
`reject_reason` field on WATCH picks before tuning thresholds.

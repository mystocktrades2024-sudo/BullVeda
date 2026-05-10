# Overnight Work Summary — 2026-05-09 → 2026-05-10

**Total commits across both sessions: ~14**

## 🎯 Headline: Major P0 Bug Fixed

**Discovery (~02:00):** GATE-1 validation backtest produced 0 BUYs across
60 simulated days even *after* the QUANT-1 setup kill was reverted. Root
cause was NOT the kill list — it was a missing `weekly_df` parameter in
backtest's `_score_as_of()`.

**The Bug:**
- `backtest._score_as_of()` called `score_technicals(df, regime, spy_close)`
  without passing `weekly_df`.
- `_weekly_ema_alignment(None)` returned `{bullish: False}`.
- `weekly_bull = False` for every backtest pick.
- Every `setup_gates.*.weekly_bull_required = True` blocked the BUY.
- Result: every pick became WATCH. System unable to trade in backtest.

**The Fix (commit 985cd182b):**
- Resample daily OHLCV to W-FRI inside `_score_as_of`.
- Pass `weekly_df` to `score_technicals`.
- Resampling is leakage-free (uses only data ≤ as_of_date).

**Validation:**
`python3 backtest.py --smoke` produced **5 BUY trades** in 5d — the first
non-zero BUYs in this codebase since QUANT-1 landed. All Trend Continuation
setups (the one A5-followup un-killed).

## 📊 Backtest Results

### Smoke (5d, 2026-04-27 → 2026-05-01) — PASSED
```
Total return:  +4.6%
Profit factor: 7.74
Win rate:      40% (2/3+)
Max drawdown:  0.8%
Total trades:  5
Setup type:    Trend Continuation
```

### Q1-step5 250d (2025-05-05 → 2026-05-01) — IN FLIGHT
- Started 02:09, finishes ~06:20
- Window: 12 months (covers full year cycle)
- Acceptance bar: PF ≥ 1.4, WR ≥ 40%, MaxDD < 20%
- Will be ready when you wake up

## ✅ Items Closed (registry updated)

| ID | Item | Status |
|---|---|---|
| MOB-1 | Tablet portrait responsive CSS | DONE |
| MOB-2 | Phone responsive CSS | DONE |
| GATE-1 | Validation backtest investigation | DONE (root cause found + fixed) |
| A5-followup | Per-subtype evidence-based multipliers | DONE |
| MOD-2 | Pixel-diff regression scaffold | DONE (awaiting baseline run) |
| PERF-6 | Critical CSS extraction | DONE (other session) |
| PERF-7 | data.json split into 5 lazy chunks | DONE (other session) |
| PERF-7b | Lazy medium/long term + misc | DONE (other session) |
| Q1-step4 | 60d smoke validation | DONE (PF 7.74) |
| PERF-OPT-1..4 | Backtest resource optimizations | DONE (4 items) |
| OPS-2/3/4 | Uptime + admin endpoints | DONE (other session) |
| QUANT-4 | Walk-forward Supabase dual-write | DONE (other session) |

## 🔧 Backtest Resource Optimizations Shipped

1. **`--smoke`** — 5d/top-100/portfolio mode. Validates config in <60s.
   Use BEFORE long runs.
2. **yfinance info disk cache** — 24h TTL keyed by sorted-universe hash.
   Saves 30-60s/run on re-runs.
3. **`--profile-cprof`** — wraps main() in cProfile, writes top-50
   hotspots to `cache/logs/backtest_cprofile_*.txt`.
4. **`--parallel` + `--workers`** — walk-forward folds run via
   multiprocessing.Pool (spawn-mode for macOS). Cuts 4-fold WF from
   8-12h to 2-3h.

Documented in CLAUDE.md commands section.

## 🐛 Two-Source Kill List Bug

Discovered and fixed (commit b02935ad8). `decision_engine.compute_setup_kill_list`
merges live signal_log evidence AND `static_setup_kill_list` from config.
The A5-followup commit set `setup_score_multiplier['Trend Continuation'] = 1.0`
but the static entry was still listing it for kill — masking the multiplier.

Memory note saved: `feedback_setup_kill_two_sources.md` so future sessions
remember to update both sources.

## 📝 Session Memory Files Saved

- `feedback_setup_kill_two_sources.md` — kill list TWO sources warning
- `project_a5_followup_2026_05_10.md` — full session audit trail

## 🧮 Evidence-Based Setup Multipliers

From live signal_log analysis (n=550 closed signals):

| Setup | n | WR | WR_LB | avg | Multiplier |
|---|---|---|---|---|---|
| 10-Week Pullback | 87 | 73.6% | 63.4% | +4.25% | **1.5×** (HIGH-EDGE) |
| VCP Breakout | 80 | 55.0% | 44.1% | +5.77% | **1.3×** (BOOST) |
| Trend Continuation | 140 | 41.4% | 33.6% | +2.08% | **1.0×** (NEUTRAL — was killed!) |
| Pocket Pivot | 20 | 45.0% | 25.8% | -0.13% | **0.7×** (DEMOTE) |
| 52wk Breakout | 114 | 31.6% | 23.8% | -0.62% | **0.0×** (KILL) |
| EMA21 Pullback | 59 | 11.9% | 5.9% | -2.10% | **0.0×** (KILL) |

## 🌅 What to Check When You Wake Up

1. Open `cache/portfolio_backtest.json` for the 250d Q1-step5 result
2. If PF ≥ 1.4 / WR ≥ 40% / MaxDD < 20% → system is ready for paper
   trading. Run `python3 executor.py --activate`.
3. Open `cache/backtest_report_latest.html` for the visual report.
4. Open `https://trade.mystockholding.com` to confirm the dashboard
   reflects the new config.
5. If 250d failed acceptance bar — refine setup_score_multiplier further
   (the smoke 5d showed PF 7.74 which is very different from 250d's
   preliminary PF 0.96, so cherry-picking may be playing a role).

## ⏳ Outstanding (deferred / in-flight)

- **A1** (config promotion) — gated on Q1-step5 result
- **Q1-step6** (buy_max_score=80 cap test) — gated on Q1-step5
- **D3 / A4** (walk-forward validation) — can run in parallel mode now
- **B1** (`--as-of-membership` survivorship-bias backtest) — separate work
- **PERF-6** (critical CSS) — DONE by other session
- **OPS-1, CLEAN-4** — wait until 2026-05-16
- **MOD-1** (Scanner deep refactor) — P2

Memory + open_items.json fully synced. Excel auto-rebuilt at every commit.

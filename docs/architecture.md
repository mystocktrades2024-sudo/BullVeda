# SwingTrade Architecture

**Last updated:** 2026-05-06

This document explains how a swing-trading signal flows from raw market data to a verdict on the V2 dashboard. Read this before modifying scoring, gating, or display logic.

## Core principle: a BUY is a real BUY

The system enforces a single source of truth for every ticker's verdict. Every dashboard surface (overview, plan, fundamentals, audit log) reads from one decision object. Contradictions across tabs are bugs, not features.

The **decision engine** (`decision_engine.py`) aggregates 8 hard gates into a final verdict. No other code path computes verdicts independently — all of them defer to engine output.

---

## Data flow (one full scan)

```
EODHD (sole data provider, 1000/min budget)
       │
       ▼
swing_trade.py                        — orchestrates daily scan (~12-15 min)
   1. fetch S&P 500 + Russell 1000 OHLCV (~1005 tickers)
   2. compute technicals, fundamentals, sentiment, gates per ticker
   3. score every ticker → pass to analysis.compute_trade_plan()
   4. apply regime classification (4-regime)
   5. apply sector ranking, kill-list demotion
   ──── decision_engine.compute_final_verdict() runs here ────
   6. for every ticker, run 8-gate cascade (see "Gate cascade" below)
   7. apply sector concentration cap (≤3 BUYs per sector)
   8. apply portfolio position cap (≤15 total open)
   9. compute elite picks (top 5 by EV score)
       │
       ▼
cache/last_bundle.json                — single source of truth bundle
       │
       ├─ cache/bundles/YYYY-MM-DD.json   ← per-day archive (90-day retention)
       │
       ▼
infra/prototype/build_data.py         — V2 dashboard builder
   - reads bundle
   - applies _PREV_BUNDLE_INDEX for scan-over-scan diff (change_log)
   - writes per-ticker JSON with all decision-engine output preserved
       │
       ▼
infra/prototype/data.json             — full V2 data (all tickers, all sections)
infra/prototype/tickers.json          — per-ticker drill-down (75 tickers)
       │
       ▼
http://localhost:7432/v2/             — main V2 dashboard (signal scanner, etc.)
http://localhost:7432/v2/elite-detail.html?t=AVT  — per-ticker drill-down
```

## The 8-gate cascade (decision_engine.py)

Every ticker passes (or fails) every gate. **All gates must pass for a BUY.** Any gate failure → verdict becomes WATCH or WAIT, never BUY. The cascade order matters: system-wide blocks (circuit breaker, macro blackout) check first, then per-ticker conditions.

| # | Gate | Check | Failure mode |
|---|---|---|---|
| 0 | **System circuit breaker** | `system_status.circuit_breaker.active == False` AND `forced_cash.active == False` AND `macro_calendar.blackout_today == False` | All BUYs → WAIT (drawdown limit hit, forced cash, FOMC/CPI day, etc.) |
| 1 | **Liquidity / price** | `gate.passed == True` (existing pre-trade gate; price > $2, daily $-volume > $5M, drawdown OK, etc.) | Ticker fails basic tradeability filters |
| 2 | **Multi-timeframe** | `medium_term_gate_status` is empty/passed | Higher-timeframe quality gate failed |
| 3 | **Entry quality** | `entry_quality not in {MISSED, EXTENDED}` | Late entry — pivot already passed; chasing |
| 4 | **Decision state** | `decision_state.state not in {MISSED, NO_EDGE}` | State machine says wait |
| 5 | **Tail-loss filter** | `conviction.tail_filter_demoted == False` | Score+stars combo doesn't clear conviction floor |
| 6 | **Earnings proximity** | `earn_days >= 5` (or null) | Earnings within 5 days — binary risk too high |
| 7 | **Setup performance** | Setup not in active kill list | Setup auto-killed for WR<35% AND avg<0% over n≥30 |
| 8 | **Fundamental adequacy** | `fund_score / fund_max >= 0.50` (or no data) | Fundamentals are weak (<50% of max) |

**Soft gates** (non-blocking — emit a caveat in `caveats` list):
- `analyst_upside < 0` → "price above analyst target"
- `tier1_signals.total_points == 0` → "no tier-1 high-conviction signals"
- `zacks_rank_rationale.growth == 'F'` → "Zacks growth grade: F"
- `5 ≤ earn_days < 10` → "earnings in N days" (caveat, not block)

Verdict logic:
- **All hard gates pass + score ≥ regime threshold** → BUY
- **All hard gates pass but score below threshold** → WATCH
- **System-wide gate (#0) fails** → WAIT (no BUYs anywhere, regardless)
- **Per-ticker gate fails** → WATCH (entry/decision/multi-timeframe) or WAIT (tail-loss/earnings/setup-killed/fundamentals)

## Setup performance auto-tuning (Phase 3.2)

`compute_setup_kill_list()` and `compute_setup_size_multipliers()` read `data/signal_log.json` (real outcomes from prior scans) and compute live per-setup metrics. These run every scan, so the rules adapt to fresh data without code changes.

### Kill list
A setup is auto-killed (multiplier 0.0×, gate 7 blocks it) when:
- WR < 35% AND avg PnL < 0 AND n ≥ 30 closed signals

Example as of 2026-05-06: **EMA21 Pullback** (WR 20%, avg -2.48%, n=35) — auto-killed.

### Size multipliers (#8: regime-conditional)
```
1.5×  expectancy avg ≥ 4% AND WR ≥ 60% (high-edge setups)
1.3×  expectancy avg ≥ 2% (proven setups)
1.0×  expectancy avg ≥ 0 OR n < 20 (default)
0.7×  expectancy avg < 0 (loss-prone, not killed yet)
0.0×  killed by performance floor

× regime modifier:
  risk_on_trending  1.00
  risk_on_choppy    0.85
  risk_off_*        0.70
  panic             0.50
```

The multiplier is then applied to `kelly_size.suggested_shares`, `position_value`, `final_alloc_pct`, `dollar_risk` so live trade plans honor historical setup edge.

## V2 dashboard panels (elite-detail.html)

Each ticker page shows (in order):
1. **Verdict card** — verdict + score + sector strength badge (preserved from elite-detail's existing UI)
2. **Multi-timeframe row** — Swing/Position/Invest verdicts with alignment indicator
3. **Setup edge sizing badge** — when setup_size_multiplier ≠ 1.0×
4. **"Why this is BUY/WATCH" panel** — numbered 8-gate walkthrough with pass/fail icons and reasons (`_renderDecisionEnginePanels()` in elite-detail.html)
5. **Pillars** (technical/catalyst/RS/quality) — preserved from elite-detail
6. **Forward-distribution panel** — SVG histogram + 6 stat tiles (P(profit), median, Sharpe, VaR-95, CVaR-97.5, Mean ± σ)
7. **Audit log panel** — scan-over-scan changes (verdict swaps, score deltas, entry-quality changes, stop changes)

All panels are populated from fields in `tickers.json` produced by `build_data.py`. No frontend recomputes verdicts.

## File map

| File | Role |
|---|---|
| `swing_trade.py` | Daily scan orchestrator; calls decision_engine before bundle write |
| `decision_engine.py` | Single source of truth for verdicts; 8-gate cascade |
| `analysis.py` | Per-ticker scoring (technicals, fundamentals, trade plan, kelly_size) |
| `data_fetcher.py` | EODHD client wrappers + market data cache |
| `signal_tracker.py` | Tracks open positions, computes MAE/MFE, applies exit rules |
| `reprocess_bundle.py` | Re-applies decision_engine to existing bundle without re-scan |
| `analyze_signals.py` | Auto-generates per-setup/regime/score performance breakdown |
| `engine_health_check.py` | Cron-friendly health check; alerts on engine failure |
| `backtest.py` | EODHD-based backtest using the live scoring path (single-window + portfolio modes) |
| `backtest/walk_forward_v2.py` | True walk-forward (4 folds × grid search) |
| `infra/prototype/build_data.py` | V2 dashboard data builder; computes change_log |
| `infra/prototype/elite-detail.html` | Per-ticker drill-down (production) |
| `infra/prototype/dashboard.html` | Main V2 dashboard (signal scanner, lists) |

## Key bundle fields written by decision engine

Every ticker in `last_bundle.json` after engine runs:

```json
{
  "ticker": "AVT",
  "verdict": "WATCH",                    // top-level — single source of truth
  "decision": {"verdict": "WATCH", ...}, // legacy mirror for build_data.py:1139 fallback
  "reject_reason": "Re-entry not...",    // empty string for BUYs
  "caveats": ["no tier-1..."],
  "gates_evaluated": [
    {"name": "liquidity_price", "passed": true,  "reason": ""},
    {"name": "entry_quality",   "passed": false, "reason": "MISSED — wait for pullback"},
    ...
  ],
  "audit_trail": {
    "ticker": "AVT", "verdict": "WATCH",
    "hard_gates_passed": false,
    "gate_failures": ["entry_quality", "decision_state", "tail_loss_filter"],
    "decided_by": "decision_engine.compute_final_verdict",
  },
  "setup_size_multiplier": 1.3,          // post-regime adjustment
  "kelly_size": { ... },                 // multiplied in-place by setup_size_multiplier
  "change_log": {                        // present only when changes vs prior snapshot
    "prior_date": "2026-05-05",
    "changes": [{"field": "verdict", "from": "BUY", "to": "WATCH"}, ...]
  }
}
```

## Scan-end safety hooks

After bundle write:
1. **Bundle archive** — copy to `cache/bundles/YYYY-MM-DD.json` (per-day snapshot)
2. **90-day retention** — purge snapshots older than 90 days
3. **Mac notification on failure** — engine crash or 0-tickers-scored → osascript notification
4. **engine_health_check.py** — runnable manually or via cron (`30 7 * * 1-5`)

## Failure modes and recovery

| Symptom | Likely cause | Diagnosis | Recovery |
|---|---|---|---|
| Dashboard shows BUY but tabs disagree | Engine didn't run | Check `bundle.decision_engine_version` field; missing → engine failed | `git log` then revert to prior known-good commit |
| 0 BUYs daily but expecting some | Circuit breaker active | Check `bundle.system_status.circuit_breaker.active` | Wait for drawdown to recover, or override config |
| Earnings gate not firing | `earn_days` data missing | Run `python3 analyze_signals.py` and check earnings stats | Investigate EODHD earnings endpoint |
| Setup auto-killed unexpectedly | Sample size hit threshold | Run `python3 -c "from decision_engine import compute_setup_kill_list; print(compute_setup_kill_list())"` | Wait for sample to grow; threshold reverts |
| V2 dashboard shows old data | build_data didn't run | Check `infra/prototype/data.json` mtime | `python3 infra/prototype/build_data.py` |

## Testing & verification

- **Engine logic**: `python3 -c "from decision_engine import compute_final_verdict; ..."` — run on any bundle ticker
- **Health**: `python3 engine_health_check.py`
- **Backtest**: `python3 backtest.py --portfolio --days 750` (uses live scoring path via EODHD; walk-forward via `python3 backtest/walk_forward_v2.py --folds 4`)
- **Re-process without re-scan**: `python3 reprocess_bundle.py` (cheap iteration on engine logic)

## Known limitations / not-yet-built

- No portfolio-level Kelly (current sizing is per-ticker; doesn't account for correlation between open positions)
- No real-time intraday alerts (system is EOD; intraday signals are out of scope)
- `_compute_mode_verdicts` in build_data.py still computes per-timeframe verdicts independently (medium/long-term aren't gated through engine — only swing/short-term is)
- Some tickers from non-standard sections (zacks_tab, extended_leaders) have sparse `gates_evaluated` because the underlying signal data wasn't computed for them; engine treats this as "gate skipped, defaulting to pass"

## Migration history (today, 2026-05-06)

- 13 commits implementing the architecture above. See `git log --oneline` for the commit trail.
- Decision engine wired across swing_trade.py, build_data.py, reprocess_bundle.py, all elite-detail panels.
- Pre-existing legacy code paths (multiple verdict-writing engines) demoted from authoritative to fallback. Defense-in-depth retained but not relied upon.

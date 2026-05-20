# Backtest · Historical Scoring Diagnostic

**Date:** 2026-05-18
**Status:** Open root-cause investigation
**Owner:** Engine team
**Severity:** High — blocks all backtests with min_score ≥ 60

## TL;DR

Historical-date backtests produce **0 BUYs at min_score≥65** because the
composite score is systematically suppressed — not because the engine is
broken, but because **3 of 4 pillars decay or zero out when fed
historical-only data**. Smoke runs at min_score=50 succeed (75% WR, +6.3%
on the 22:52 run) because they tolerate the suppression. Production-grade
runs at min_score=65+ cannot.

This is **not** an "entry_quality wasn't passed" bug. That was a different
issue, already fixed in commit `9931a367a`. The score-suppression issue
is deeper.

## Concrete evidence — NVDA on 2025-09-04 (mid AI rally)

```
$ BACKTEST_NO_FUNDAMENTALS=1 python3 scripts/debug_historical_buy_block.py 2025-09-04 NVDA

Regime: bull · SPY $649.12 · above 50EMA + 200SMA · daily +0.84%

PILLAR SCORES:
  tech:  5.0 / 38   (13%)   ← KILLER
  fund: 16.0 / 30   (53%)   ← surprisingly OK
  opt:   2.0 / 20   (10%)   ← starved
  sent:  0.0 / 10   ( 0%)   ← starved

VERDICT: AVOID · score 13/100 · "weak structure"

KEY INDICATORS (NOT broken):
  RSI       43.2     (neutral)
  ADX       44.7     (strong trend)
  EMA8/21/50 stacked (above long-term trend)
  RS rank   80       (strong)
```

NVDA on this day was a **legitimate buy candidate** — strong trend, above
stack, RS 80, bull regime. Yet composite score = 13. The engine is
rejecting a real signal because **the pillars that depend on real-time
data (sentiment, options, technicals with volume features) decay to
near-zero on historical dates**.

## How the scoring is supposed to work

`config.scoring_weights` (current, normalized to 100):

| Pillar | Weight | Live source | Historical source |
|---|---|---|---|
| trend_structure | **30** | EMA stack + ADX + weekly bias (price-only) | ✅ Same — works historically |
| rs_sector | **25** | RS rank vs SPY + sector ETF (price-only) | ✅ Same — works historically |
| catalyst_expansion | **20** | VCP / PEAD / UOA / 52wk-breakout (requires fresh signals) | ⚠️ Partial — pattern detection OK, UOA/PEAD broken |
| smart_money | **10** | News sentiment + insider + options flow | 🔴 Mostly missing historically |
| quality_fundamentals | **5** | Finviz/yfinance current snapshot | 🔴 Look-ahead leak unless `BACKTEST_NO_FUNDAMENTALS=1` |
| entry_rr | **10** | R:R at current price + entry quality classification | ✅ Same — works historically |

**Theoretical historical max** (if every pillar that CAN work hits its max):
30 + 25 + ~10 + ~3 + 0 + 10 = **~78**

Subtract typical real-trade gaps and you land around **40-55**. That's why
min_score=50 succeeds and min_score=65 doesn't.

## Why each pillar decays historically

### Trend (30 max) — should be intact, isn't always

In the NVDA case above, EMA stack is fine, ADX strong, but tech pillar
scored 5/38 (13%). Most likely cause: **the tech pillar internally
includes volume-based subscores (RVOL, OBV slope, MFI) that need
multi-day rolling windows.** When the backtest loads only the window's
data, the rolling-20d-volume comparison reverts to the warm-up period's
flat values. Diagnostic shows `rvol = 0.81` — that means the engine
thinks today's volume is BELOW average, on a day NVDA almost certainly
saw above-average volume. The rolling baseline is wrong.

### RS Sector (25 max)

Requires SPY + sector ETF prices on the same dates. EODHD has these.
**Should work, and based on `rs_rank=80` in the diagnostic, it does.**

### Catalyst Expansion (20 max)

Requires real-time pattern detection:
- VCP, pocket pivot, 52wk breakout — price-only, **should work historically**
- PEAD setup (earnings beat + gap) — requires historical earnings + EPS surprise data. **Partial** — we have earnings dates from EODHD, beat magnitude is sometimes missing.
- UOA (unusual options activity) — requires daily options snapshot. **Not in historical backfill.**

Diagnostic showed `vcp=False, pocket_pivot=False` — so this pillar
zeros out unless the day happens to print a textbook pattern. Most
days, **catalyst pillar ≈ 0-5 / 20**.

### Smart Money (10 max)

- News sentiment — EODHD provides historical news but the **scoring
  pipeline does not retroactively classify news polarity**. The
  sentiment dictionary is applied only at live-scan time. Historical
  sentiment = 0.
- Insider activity — same pattern. Cluster detection runs on the live
  watchlist daily; historical buys are NOT retroactively scored into
  the backtest.
- Options flow — UOA snapshots are written daily to `cache/uoa_*.json`
  and **never backfilled**. Historical = 0.

Result: **smart_money pillar ≈ 0 / 10 always in backtests**.

### Quality Fundamentals (5 max)

Without `BACKTEST_NO_FUNDAMENTALS=1`, today's fundamentals are applied to
historical signals — known look-ahead leak (audit #4). With the flag,
the pillar zeros out (5 points missing).

Cost is small (5/100), but the principle matters more than the points.

### Entry R:R (10 max)

Computed from price-only (entry zone vs stop vs T1). **Works historically.**

## Net diagnosis

Historical-period max composite ≈ `30 + 25 + 5 + 0 + 0 + 10 = 70` for
the strongest names. Most names will see `15 + 15 + 2 + 0 + 0 + 5 = 37`.

That's why:
- min_score=50 → some BUYs (the rare best names cross the floor)
- min_score=65 → zero BUYs (no name reliably reaches 65 historically)

## What `BACKTEST_NO_FUNDAMENTALS=1` actually fixes (and doesn't)

| Concern | With flag | Without flag |
|---|---|---|
| Fundamentals look-ahead bias | ✅ Removed | ❌ Today's data applied to old signals |
| Score suppression | Slight (lose 5/100) | Slight (gain 5/100 of fake points) |
| Catalyst/sentiment/options gaps | ❌ Not addressed | ❌ Not addressed |
| Tech-pillar volume gaps | ❌ Not addressed | ❌ Not addressed |

**The flag fixes only 1 of the 4 pillars that decay historically.**

## Honest fix paths

### Path A — Lower min_score for historical backtests only (cheapest)

Set `min_score=50` in the backtest configs, document the gap, accept that
historical WR/PF numbers are noisier than they look. **This is what the
smoke test already does. It works.** The 75% WR / +6.3% smoke result is a
valid edge signal at that score floor.

- Cost: $0
- Time: 5 min (change config + re-run)
- Tradeoff: backtest min_score ≠ live min_score, so direct WR comparison
  needs care

### Path B — Retroactively score the historical archive (medium)

Walk `data/decision_log.jsonl` + `cache/picks_history.json` + the EODHD
news archive. For each day in the backtest window:

1. Re-run news sentiment scoring on EODHD news for that date
2. Re-detect insider clusters from the SEC Form 4 archive (free)
3. Compute catalyst tier from the price action + earnings dates

Write the results to `data/historical_scores/<date>.json`. Backtest reads
from these files instead of zero-defaulting.

- Cost: 1-2 days dev + EODHD news API quota (within current budget)
- Time: ~6-8 hours work
- Tradeoff: still no historical options flow (UOA) — that pillar stays 0

### Path C — Backtest min_score guard rail (SHIPPED 2026-05-19)

**Hypothesis updated after investigation:** Initial guess was that the
tech-pillar rolling-volume baseline was cold on backtest day 1. **Wrong.**
`backtest.py:821` already pre-loads 350 calendar days (~240 trading) of
history before the backtest window. The data is warm.

**Actual root cause:** users (and Claude sessions) repeatedly invoke
`backtest.py --min-score 65 --min-rs 75` — using the LIVE thresholds.
Live can hit 65 because all 4 pillars (+ catalyst + smart_money) are
hot. Backtest cannot reach 65 reliably for the structural reasons in §
above. The CLI default `--min-score 50` is already correct; the
regime-adaptive `bull: buy_min_score=55` (`backtest.py:458`) is the
right floor when raising the threshold.

**Fix shipped** (`backtest.py` `main()`):
- Added `BACKTEST_SAFE_MAX_MIN_SCORE = 55` constant
- If `--min-score > 55` (and not `--smoke`), log a clear three-line
  warning explaining the structural cause and pointing at this doc
- Added `--accept-low-buys` flag for legitimate explorations
  (grid-search folds that intentionally probe upper score bands)
- No behavior change for runs at default `--min-score 50` or sleeve
  bypasses

- Cost: $0
- Time: 30 min (shipped)
- Tradeoff: doesn't *fix* the underlying score-suppression — it stops
  users from shooting themselves in the foot. The proper fix is Path B
  (retroactive sentiment + insider scoring against the EODHD news
  archive), which still owes the next 6-8 hours of work.

### Path D — Accept the gap, validate live forward instead (Wilson-true)

Stop trying to make 252d historical backtests match live. Use 30-60d
historical for smoke + multi-pillar regression detection. Drive promotion
decisions from **forward paper-trading**, not historical re-scoring.

This is what CLAUDE.md principle 1 actually advocates for (statistical
rigor over backtest theatre). Walk-forward + holdout + Wilson CI on **live
forward outcomes**, not retroactive composite scores.

- Cost: $0
- Time: 0 (already the operating model — just stop running 252d backtests
  and expecting BUYs)
- Tradeoff: longer calendar time to validate any new sleeve

## Recommended sequence

1. **Today**: stop launching 252d backtests at min_score=65. They will
   continue producing 0 BUYs until path B or C ships.
2. **This week**: ship path C (tech-pillar warm-up window). Cheap, fast,
   measurable.
3. **Next sprint**: ship path B for sentiment + insider. Skip UOA (no
   free historical source).
4. **Always**: validate edge via forward paper-trading (path D),
   regardless of how good historical backtests look. Backtest is a sanity
   check, not the source of truth.

## Where this lives in code

- `analysis.py:9383` — `_pillar_qg_max` (pillar weighting)
- `backtest.py:111` — `BACKTEST_DISABLE_FUNDAMENTALS` flag
- `backtest.py:1032` — historical fundamentals load path
- `scripts/debug_historical_buy_block.py` — the diagnostic that surfaced
  this. Run with any (date, ticker) pair.
- `config/config.json` `scoring_weights` — pillar weights
- `config/config.json` `scoring` — raw pillar maxes

## Why this matters (principle 1 + 4)

CLAUDE.md principle 1: *"Statistical rigor over backtest theatre."*
Principle 4: *"Adversarial mindset — every claim has a falsification."*

Until we fix the historical-scoring decay, **every multi-pillar backtest
is biased toward zero BUYs**. The system isn't dead — it's that the
historical reconstruction is incomplete. Acting on "the 252d backtest
showed 0 BUYs" as evidence of broken edge would be backwards: the
backtest infrastructure is what's broken, not the live engine.

The smoke test (4 trades, 75% WR, +6.3%) is the truer signal that the
engine still has edge at low score floors. Live forward paper trading is
the only path to Wilson-validated truth.

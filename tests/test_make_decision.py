#!/usr/bin/env python3
"""Integration test for analysis.make_decision().

Locks down the verdict logic so threshold tuning doesn't silently regress.
Run: python3 -m tests.test_make_decision   (or)   python3 tests/test_make_decision.py

Covers 13 scenarios:
  1.  Elite BUY               — strong score + RS + weekly bull + catalyst → BUY
  2.  Weak score              — score below watch_min                      → AVOID
  3.  Score enough, no catalyst, no override                                → WATCH
  4.  BUY score but RSI > 75 (overbought)                                   → WATCH
  5.  BUY score but RS < long_min_rs                                         → WATCH
  6.  BUY score but weekly not bullish                                       → WATCH
  7.  SHORT: bear regime + VIX ≥ 25 + all filters pass                      → SHORT
  8.  SHORT blocked — VIX < 25                                              → AVOID
  9.  SHORT blocked — not bear regime                                        → AVOID
 10.  SHORT blocked — RS too high (>30)                                      → AVOID
 11.  SHORT blocked — earnings within window                                 → AVOID
 12.  SHORT blocked — sector not underperforming                             → AVOID
 13.  SHORT blocked — TTM squeeze active                                     → AVOID
 14.  52wk Breakout + RS<80 (not elite) → WATCH
 15.  Pre-market gap >3% → WATCH (demoted)
"""

import sys
from pathlib import Path

# Make `analysis` importable when run directly from SwingTrade dir
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import json
from analysis import make_decision

_CFG = json.loads((_root / "config" / "config.json").read_text())

# Minimal defaults — override per test case
def _mk(**overrides) -> dict:
    base = dict(
        total_score=75.0,
        rr_ratio=3.5,
        config=_CFG,
        weak_regime=False,
        direction="long",
        bear_score=6,
        rs_rank=85,
        vix=18.0,
        sector_outperforming=True,
        sector_etf="XLK",
        has_catalyst=True,
        rsi=55.0,
        weekly_bull=True,
        adx=25.0,
        regime_name="neutral",
        breadth={"pct_above_50d": 60},
        entry_quality="PULLBACK",
        regime4="risk_on_trending",
        setup_type="Trend Continuation",
        short_float=5.0,
        days_to_earnings=30,
        sector_underperforming=False,
        stock_vs_spy_20d=5.0,
        todays_gap_pct=0.5,
        squeeze_on=False,
        rvol=1.0,
        days_to_cover=1.0,
        market_cycle="",
    )
    base.update(overrides)
    return base


def _call(**kwargs) -> dict:
    return make_decision(**_mk(**kwargs))


def run():
    passed, failed = 0, 0
    def case(n: str, result: dict, expected: str, extra=""):
        nonlocal passed, failed
        actual = result.get("verdict")
        ok = actual == expected
        mark = "✓" if ok else "✗"
        if ok:
            passed += 1
        else:
            failed += 1
        detail = result.get("reason", "")[:80]
        extra_s = f" [{extra}]" if extra else ""
        print(f"  {mark} {n:<60} expected={expected:<6} got={actual:<6}{extra_s}")
        if not ok:
            print(f"    reason: {detail}")

    print("=" * 80)
    print("make_decision integration tests")
    print("=" * 80)

    # 1. Elite BUY
    case("1.  Elite BUY (score 85, RS 90, weekly bull, catalyst, PULLBACK)",
         _call(total_score=85, rs_rank=90), "BUY")

    # 2. Weak score → AVOID
    case("2.  Weak score (40)",
         _call(total_score=40, rr_ratio=2.0), "AVOID")

    # 3. Score enough, no catalyst, no override (+15 bar)
    case("3.  Score 73, no catalyst, no override",
         _call(total_score=73, has_catalyst=False), "WATCH")

    # 4. BUY score but RSI > 75
    case("4.  RSI overbought (77)",
         _call(total_score=85, rsi=77), "WATCH")

    # 5. BUY score but RS < long_min_rs (default 65)
    case("5.  RS too low (50)",
         _call(total_score=85, rs_rank=50), "WATCH")

    # 6. BUY score but weekly not bullish
    case("6.  Weekly not bull",
         _call(total_score=85, weekly_bull=False), "WATCH")

    # 7. Confirmed SHORT — bear regime requires rr >= 4.0
    case("7.  SHORT: bear regime + VIX 28 + bear_score 13 + rr 4.2 + filters pass",
         _call(direction="short", weak_regime=True, regime_name="bear", regime4="risk_off_trending",
               vix=28, bear_score=13, rsi=75, rs_rank=25, rr_ratio=4.2,
               sector_outperforming=False, sector_underperforming=True,
               short_float=8, days_to_earnings=30, squeeze_on=False,
               setup_type=""), "SHORT")

    # 8. SHORT blocked VIX < 25
    case("8.  SHORT blocked: VIX 20 < 25",
         _call(direction="short", weak_regime=True, regime_name="bear",
               vix=20, bear_score=14, rsi=75, rs_rank=25), "AVOID")

    # 9. SHORT blocked not bear regime
    case("9.  SHORT blocked: neutral regime",
         _call(direction="short", weak_regime=False, regime_name="neutral",
               vix=28, bear_score=14, rsi=75, rs_rank=25), "AVOID")

    # 10. SHORT blocked RS > 30
    case("10. SHORT blocked: RS 60 > 30",
         _call(direction="short", weak_regime=True, regime_name="bear", vix=28,
               bear_score=14, rsi=75, rs_rank=60, sector_underperforming=True), "AVOID")

    # 11. SHORT blocked earnings within 7d
    case("11. SHORT blocked: earnings in 3 days",
         _call(direction="short", weak_regime=True, regime_name="bear", vix=28,
               bear_score=14, rsi=75, rs_rank=25, sector_underperforming=True,
               days_to_earnings=3), "AVOID")

    # 12. SHORT blocked sector not underperforming
    case("12. SHORT blocked: sector leading",
         _call(direction="short", weak_regime=True, regime_name="bear", vix=28,
               bear_score=14, rsi=75, rs_rank=25, sector_underperforming=False), "AVOID")

    # 13. SHORT blocked squeeze_on
    case("13. SHORT blocked: TTM squeeze active",
         _call(direction="short", weak_regime=True, regime_name="bear", vix=28,
               bear_score=14, rsi=75, rs_rank=25, sector_underperforming=True,
               squeeze_on=True), "AVOID")

    # AI-9: SHORT blocked DTC > 5 (squeeze concentration)
    case("13b.SHORT blocked: DTC 7.5 > 5 (squeeze trap)",
         _call(direction="short", weak_regime=True, regime_name="bear", vix=28,
               bear_score=14, rsi=75, rs_rank=25, sector_underperforming=True,
               days_to_cover=7.5), "AVOID")

    # 14. 52wk Breakout + RS<80 (not elite)
    case("14. 52wk Breakout + RS 70 (not elite)",
         _call(total_score=85, rs_rank=70, setup_type="52wk Breakout"), "WATCH")

    # 15. Pre-market gap >3%
    case("15. Pre-market gap +4.5% → demoted to WATCH",
         _call(total_score=85, rs_rank=90, todays_gap_pct=4.5), "WATCH")

    # AI-8: RVOL gate for breakouts
    case("16. VCP Breakout with RVOL 0.5 → WATCH (no volume)",
         _call(total_score=85, rs_rank=90, setup_type="VCP Breakout", rvol=0.5), "WATCH")
    case("17. VCP Breakout with RVOL 1.5 → BUY (has volume)",
         _call(total_score=85, rs_rank=90, setup_type="VCP Breakout", rvol=1.5), "BUY")

    # AI-7: Elite-RS override (in risk_on_choppy, buy_min=72)
    case("18. Choppy + elite RS 97 + Trend Cont score 70 → BUY (override to 67)",
         _call(total_score=70, rs_rank=97, setup_type="Trend Continuation",
               regime4="risk_on_choppy"), "BUY")
    case("19. Choppy + RS 80 + Trend Cont score 70 → WATCH (no elite override)",
         _call(total_score=70, rs_rank=80, setup_type="Trend Continuation",
               regime4="risk_on_choppy"), "WATCH")

    # AI-43: market-cycle-aware score bar adjustment
    case("20. Topping cycle + choppy (buy_min 72+3=75) + score 72 → WATCH",
         _call(total_score=72, rs_rank=90, regime4="risk_on_choppy",
               market_cycle="topping"), "WATCH")
    case("21. Early-bull cycle + trending (buy_min 65-2=63) + score 64 → BUY",
         _call(total_score=64, rs_rank=90, regime4="risk_on_trending",
               market_cycle="early_bull"), "BUY")

    # AI-44: Seasonality — Santa rally lowers bar from 65 to 61; score 64 passes
    case("22. Santa rally seasonal_adj -4 + score 64 + RS 90 + risk_on_trending → BUY",
         _call(total_score=64, rs_rank=90, regime4="risk_on_trending",
               setup_type="Trend Continuation",
               seasonal_adj={"buy_min_add": -4, "label": "Santa rally"}), "BUY")

    print("=" * 80)
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
    print("=" * 80)
    return failed == 0


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)

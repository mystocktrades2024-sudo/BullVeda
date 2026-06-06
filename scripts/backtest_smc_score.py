#!/usr/bin/env python3
"""Point-in-time backtest of the SMC composite score vs forward returns.

For each ticker we walk its daily history; at each step t we score SMC using ONLY
bars[:t+1] (no lookahead — causal indicators), then measure the realized forward
return at t+5 / t+10 / t+20. We then check:
  (1) does a higher smc_score → higher forward return (monotonic bands + corr)?
  (2) which bias×zone cell actually pays (validates the weight design)?

Usage: python3 scripts/backtest_smc_score.py [TICKER ...]
"""
from __future__ import annotations
import sys, os, math, statistics
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pattern_data as pdat
import engines.smc as smc

UNIV = (sys.argv[1:] or (
    "AAPL MSFT NVDA AMD GOOGL META AMZN TSLA AVGO ORCL CRM ADBE NFLX "
    "JPM BAC GS WFC MS C V MA "
    "UNH JNJ PFE MRK ABBV LLY "
    "XOM CVX COP "
    "CAT DE HON GE BA "
    "WMT COST HD PG KO PEP MCD NKE DIS "
    "INTC QCOM TXN MU"
).split())

H = [5, 10, 20]
STEP = 5
META = pdat.mode_meta("SWING")


def agg(rets):
    if not rets:
        return None
    wr = sum(1 for x in rets if x > 0) / len(rets)
    return (len(rets), statistics.mean(rets) * 100, statistics.median(rets) * 100, wr * 100)


def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return cov / (sx * sy) if sx and sy else 0.0


def main():
    rows = []
    skipped = 0
    for tk in UNIV:
        try:
            df, tier, meta = pdat.get_bars(tk, "SWING")
        except Exception as e:
            skipped += 1; continue
        if df is None or len(df) < 90:
            skipped += 1; continue
        closes = df["Close"].values
        N = len(df)
        for t in range(60, N - max(H) - 1, STEP):
            sl = df.iloc[:t + 1]
            try:
                o = smc.detect(sl, META, tk, light=True)
            except Exception:
                continue
            if not o.get("ok"):
                continue
            c0 = closes[t]
            if c0 <= 0:
                continue
            rec = {"score": o["smc_score"], "bias": o["bias"], "zone": o["range"]["zone"]}
            for h in H:
                rec["f%d" % h] = closes[t + h] / c0 - 1
            rows.append(rec)

    print(f"\nUniverse: {len(UNIV)} tickers ({skipped} skipped) · samples: {len(rows)} · step {STEP} bars\n")
    if not rows:
        print("no samples"); return

    # (1) score bands
    bands = [(1, 50), (50, 65), (65, 80), (80, 100)]
    print("SCORE BAND |   n   |  5d mean  wr   | 10d mean  wr   | 20d mean  wr")
    print("-" * 70)
    for lo, hi in bands:
        sub = [r for r in rows if lo <= r["score"] < hi]
        line = f"{lo:>3}-{hi:<4} | {len(sub):>5} |"
        for h in H:
            a = agg([r["f%d" % h] for r in sub])
            line += f" {a[1]:+6.2f}% {a[3]:3.0f}% |" if a else "      --      |"
        print(line)

    print()
    for h in H:
        c = pearson([r["score"] for r in rows], [r["f%d" % h] for r in rows])
        print(f"corr(score, fwd-{h}d) = {c:+.3f}")

    # (2) bias × zone (10-day)
    print("\nBIAS × ZONE (forward 10d):")
    print("-" * 50)
    for bias in ["bull", "bear", "range"]:
        for zone in ["discount", "equilibrium", "premium"]:
            sub = [r["f10"] for r in rows if r["bias"] == bias and r["zone"] == zone]
            a = agg(sub)
            if a and a[0] >= 20:
                print(f"  {bias:5} {zone:11} | mean {a[1]:+6.2f}%  wr {a[3]:3.0f}%  n={a[0]}")


if __name__ == "__main__":
    main()

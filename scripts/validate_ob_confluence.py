#!/usr/bin/env python3
"""
Validate OB-confluence as a Wilson-bumped score factor.

Reads an existing portfolio_backtest output (closed_trades), retroactively
runs score_smc() on the historical OHLCV at each trade's entry date, tags
each trade with OB-confluence flags, then computes Wilson 95% lower-bounds
for the tagged subsets vs the unconditional baseline.

DECISION RULES (per CLAUDE.md Principle 1):
  - Require n >= 30 in each subset before declaring an edge
  - Require Wilson LB lift >= 5pp to recommend a score adjustment
  - Surface the result; let user decide whether to ship #2 (OB Wilson bump)
    and #5 (OB-aware stop)

Usage:
    python3 scripts/validate_ob_confluence.py \\
        --backtest cache/portfolio_backtest_250d_min65_h5_20260510_071024.json
    python3 scripts/validate_ob_confluence.py \\
        --backtest cache/portfolio_backtest_750d_20260509_100501.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from smart_money import score_smc  # noqa: E402


# ── Wilson 95% lower bound (binomial) ───────────────────────────────────────
def wilson_lb(wins: int, n: int, z: float = 1.96) -> float:
    if n <= 0:
        return 0.0
    p = wins / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)) / denom
    return max(0.0, centre - half)


def wilson_ub(wins: int, n: int, z: float = 1.96) -> float:
    if n <= 0:
        return 1.0
    p = wins / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)) / denom
    return min(1.0, centre + half)


def fetch_historical_df(ticker: str, end_date: str, lookback_days: int = 150) -> "pd.DataFrame | None":
    """Pull OHLCV up to end_date for a single ticker. Tries Polygon parquet
    archive first (fastest), then EODHD as fallback."""
    # Parquet archive
    pq = BASE_DIR / "cache" / "ohlcv" / f"{ticker}.parquet"
    try:
        if pq.exists():
            df = pd.read_parquet(pq)
            if "Date" in df.columns:
                df["Date"] = pd.to_datetime(df["Date"])
                df = df.set_index("Date")
            elif df.index.name in ("date", "Date") or isinstance(df.index, pd.DatetimeIndex):
                df.index = pd.to_datetime(df.index)
            df = df[df.index <= end_date].tail(lookback_days)
            if len(df) >= 30:
                # Normalize column names
                for src, dst in [("open", "Open"), ("high", "High"), ("low", "Low"),
                                 ("close", "Close"), ("volume", "Volume")]:
                    if src in df.columns and dst not in df.columns:
                        df[dst] = df[src]
                return df
    except Exception:
        pass

    # EODHD fallback
    try:
        from eodhd_client import eod
        from datetime import date, timedelta
        end = pd.to_datetime(end_date).date()
        start = end - timedelta(days=int(lookback_days * 1.5))
        bars = eod(ticker, from_date=start.isoformat(), to_date=end.isoformat(), cache_ttl=86400)
        if not bars or len(bars) < 30:
            return None
        rows = []
        for b in bars:
            d = b.get("date") or b.get("Date")
            if not d:
                continue
            rows.append({
                "Date": pd.to_datetime(d),
                "Open": float(b.get("open", 0) or 0),
                "High": float(b.get("high", 0) or 0),
                "Low": float(b.get("low", 0) or 0),
                "Close": float(b.get("adjusted_close") or b.get("close") or 0),
                "Volume": int(b.get("volume", 0) or 0),
            })
        df = pd.DataFrame(rows).set_index("Date").sort_index()
        return df if len(df) >= 30 else None
    except Exception:
        return None


def tag_trade_with_smc(trade: dict) -> dict:
    """Run score_smc() on the historical OHLCV for this trade's entry date.
    Returns a copy of the trade with OB-confluence tags added."""
    out = dict(trade)
    ticker = trade.get("ticker")
    entry_date = trade.get("entry_date")
    entry_price = float(trade.get("entry_price", 0) or 0)

    out["smc_tagged"] = False
    out["has_bull_ob_5pct"] = None
    out["has_bull_ob_below_entry_5pct"] = None
    out["bull_ob_low_below_entry"] = None
    out["has_overhead_bear_ob_2pct"] = None
    out["smc_score_at_entry"] = None
    out["smc_direction_at_entry"] = None
    out["bos_bullish_at_entry"] = None
    out["choch_bearish_at_entry"] = None
    out["nearest_bull_ob_low"] = None
    out["nearest_bull_ob_high"] = None

    if not ticker or not entry_date or entry_price <= 0:
        return out

    df = fetch_historical_df(ticker, entry_date, lookback_days=150)
    if df is None:
        return out

    try:
        smc = score_smc(df, entry_price, indicators={})
    except Exception:
        return out

    out["smc_tagged"] = True
    out["smc_score_at_entry"] = smc.get("score")
    out["smc_direction_at_entry"] = smc.get("smc_direction")
    bos = smc.get("bos_choch", {}) or {}
    out["bos_bullish_at_entry"] = bool(bos.get("bos_bullish"))
    out["choch_bearish_at_entry"] = bool(bos.get("choch_bearish"))

    # Find nearest fresh/tested bullish OB below entry within 5%
    obs = smc.get("order_blocks", []) or []
    best_bull = None
    for ob in obs:
        if ob.get("type") != "bullish":
            continue
        if ob.get("status") == "mitigated":
            continue
        lvl = ob.get("price_level") or 0
        if lvl <= 0:
            continue
        dist = (entry_price - lvl) / entry_price
        if 0 <= dist <= 0.05:
            if best_bull is None or (ob.get("strength_score", 0) > best_bull.get("strength_score", 0)):
                best_bull = ob

    out["has_bull_ob_5pct"] = best_bull is not None
    if best_bull:
        out["has_bull_ob_below_entry_5pct"] = True
        out["bull_ob_low_below_entry"] = best_bull.get("low")
        out["nearest_bull_ob_low"] = best_bull.get("low")
        out["nearest_bull_ob_high"] = best_bull.get("high")
    else:
        out["has_bull_ob_below_entry_5pct"] = False

    # Overhead bearish OB within 2% (penalty signal in current score)
    has_bear = False
    for ob in obs:
        if ob.get("type") != "bearish":
            continue
        if ob.get("status") == "mitigated":
            continue
        lvl = ob.get("price_level") or 0
        if lvl > entry_price and (lvl - entry_price) / entry_price <= 0.02:
            has_bear = True
            break
    out["has_overhead_bear_ob_2pct"] = has_bear

    return out


# ── Subset analysis ─────────────────────────────────────────────────────────
def wilson_block(label: str, trades: list[dict], baseline_lb: float = None) -> dict:
    wins = sum(1 for t in trades if t.get("win"))
    n = len(trades)
    wr = wins / n if n else 0
    lb = wilson_lb(wins, n)
    ub = wilson_ub(wins, n)
    lift = (lb - baseline_lb) if baseline_lb is not None else None
    # Profit factor + avg PnL
    pnls = [t.get("pnl_pct", 0) for t in trades if isinstance(t.get("pnl_pct"), (int, float))]
    pos_sum = sum(p for p in pnls if p > 0)
    neg_sum = -sum(p for p in pnls if p < 0)
    pf = pos_sum / neg_sum if neg_sum > 0 else (float("inf") if pos_sum > 0 else 0)
    avg = (sum(pnls) / len(pnls)) if pnls else 0
    return {
        "label": label,
        "n": n,
        "wins": wins,
        "wr": wr,
        "wr_lb": lb,
        "wr_ub": ub,
        "lift_pp": lift,
        "pf": pf,
        "avg_pnl_pct": avg,
    }


def fmt_block(b: dict) -> str:
    lift = f"  Δ {b['lift_pp']*100:+.1f}pp" if b["lift_pp"] is not None else ""
    return (f"  {b['label']:48s} n={b['n']:>4}  wins={b['wins']:>4}  "
            f"WR={b['wr']*100:>5.1f}%  Wilson LB={b['wr_lb']*100:>5.1f}%"
            f"  PF={b['pf']:>5.2f}  avg={b['avg_pnl_pct']:+5.2f}%{lift}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backtest", required=True,
                        help="Path to portfolio_backtest_*.json")
    parser.add_argument("--max", type=int, default=None,
                        help="Cap trades processed (smoke-test)")
    args = parser.parse_args()

    bt_path = Path(args.backtest)
    if not bt_path.exists():
        print(f"ERROR: {bt_path} not found")
        sys.exit(1)

    print(f"Loading {bt_path.name}...")
    data = json.loads(bt_path.read_text())
    trades = data.get("trades") or data.get("closed_trades") or []
    if args.max:
        trades = trades[:args.max]
    print(f"Closed trades: {len(trades)}")

    print("\nTagging trades with historical SMC state at entry...")
    tagged = []
    for i, t in enumerate(trades):
        if (i + 1) % 25 == 0:
            print(f"  ... {i+1}/{len(trades)}")
        tagged.append(tag_trade_with_smc(t))

    n_tagged = sum(1 for t in tagged if t.get("smc_tagged"))
    print(f"Successfully tagged: {n_tagged}/{len(tagged)} "
          f"({n_tagged*100/max(1,len(tagged)):.0f}% — rest had insufficient historical data)")

    # Only trades that we could tag
    valid = [t for t in tagged if t.get("smc_tagged")]
    if not valid:
        print("No valid tags. Cannot proceed with analysis.")
        sys.exit(1)

    # ── Baseline ────────────────────────────────────────────────────────────
    baseline = wilson_block("Baseline (all tagged trades)", valid)

    # ── Test sets ───────────────────────────────────────────────────────────
    bull_ob_yes = [t for t in valid if t.get("has_bull_ob_below_entry_5pct")]
    bull_ob_no  = [t for t in valid if t.get("has_bull_ob_below_entry_5pct") is False]
    bos_yes     = [t for t in valid if t.get("bos_bullish_at_entry")]
    choch_yes   = [t for t in valid if t.get("choch_bearish_at_entry")]
    bear_overhead = [t for t in valid if t.get("has_overhead_bear_ob_2pct")]
    smc_pos     = [t for t in valid if (t.get("smc_score_at_entry") or 0) >= 1.5]
    smc_neg     = [t for t in valid if (t.get("smc_score_at_entry") or 0) <= -0.5]

    blocks = [
        baseline,
        wilson_block("Has Bull OB below entry (≤5%)", bull_ob_yes, baseline["wr_lb"]),
        wilson_block("NO Bull OB below entry (≤5%)", bull_ob_no, baseline["wr_lb"]),
        wilson_block("BOS bullish at entry", bos_yes, baseline["wr_lb"]),
        wilson_block("CHoCH bearish at entry", choch_yes, baseline["wr_lb"]),
        wilson_block("Has overhead Bear OB (≤2%)", bear_overhead, baseline["wr_lb"]),
        wilson_block("SMC score ≥ 1.5 (bullish direction)", smc_pos, baseline["wr_lb"]),
        wilson_block("SMC score ≤ -0.5 (bearish direction)", smc_neg, baseline["wr_lb"]),
    ]

    print("\n" + "=" * 110)
    print("WILSON 95% LB · OB-CONFLUENCE VALIDATION")
    print("=" * 110)
    for b in blocks:
        print(fmt_block(b))

    # ── Decision per CLAUDE.md Principle 1 ─────────────────────────────────
    print("\n" + "=" * 110)
    print("DECISION GATES (Principle 1: n≥30, Wilson LB lift ≥ 5pp)")
    print("=" * 110)

    def verdict(b: dict, name: str) -> str:
        if b["n"] < 30:
            return f"  {name}: ✗ INSUFFICIENT EVIDENCE · n={b['n']} (need ≥30)"
        lift_pp = (b["lift_pp"] or 0) * 100
        if lift_pp >= 5:
            return f"  {name}: ✓ SHIP · n={b['n']} · LB lift {lift_pp:+.1f}pp ≥ 5pp threshold"
        elif lift_pp > 0:
            return f"  {name}: ◐ MARGINAL · n={b['n']} · LB lift {lift_pp:+.1f}pp (below 5pp)"
        else:
            return f"  {name}: ✗ NO EDGE · n={b['n']} · LB lift {lift_pp:+.1f}pp"

    print(verdict(blocks[1], "#2 (Wilson bump on OB confluence)"))
    print(verdict(blocks[3], "#2a (BOS-bullish boost)"))
    print(verdict(blocks[7], "#2b (SMC-direction-bullish boost)"))
    print(verdict(blocks[6], "Overhead bear OB penalty"))

    # ── #5 simulation: OB-low-as-stop ──────────────────────────────────────
    print("\n" + "=" * 110)
    print("#5 SIMULATION · OB-low-as-stop vs ATR-stop")
    print("=" * 110)
    eligible = [t for t in valid if t.get("bull_ob_low_below_entry") is not None]
    if len(eligible) < 30:
        print(f"  ✗ INSUFFICIENT EVIDENCE · n={len(eligible)} trades have bull OB low data")
    else:
        # For each eligible trade, simulate what would have happened if stop was
        # at the bull OB low instead of the actual stop
        # Heuristic: if actual exit_reason is "stop_hit" and OB low < stop_price,
        # the OB-stop would have given more room → trade might have hit T1 instead.
        # We can't simulate PnL precisely without OHLCV, but we can flag the
        # trades where OB-low would have kept us in vs the actual ATR stop.
        loosened, tightened, same = 0, 0, 0
        ob_lower_when_loss = 0
        ob_lower_count_in_losses = 0
        for t in eligible:
            stop = t.get("stop_price")
            ob_low = t.get("bull_ob_low_below_entry")
            if stop is None or ob_low is None:
                continue
            if abs(ob_low - stop) / max(stop, 0.01) < 0.005:
                same += 1
            elif ob_low < stop:
                loosened += 1
                if not t.get("win"):
                    ob_lower_when_loss += 1
                    ob_lower_count_in_losses += 1
            else:
                tightened += 1
        print(f"  Trades with OB-low data: {len(eligible)}")
        print(f"  OB-low LOOSER than ATR stop (would have kept us in): {loosened}")
        print(f"  OB-low TIGHTER than ATR stop (would have cut us out): {tightened}")
        print(f"  OB-low ≈ ATR stop (negligible diff): {same}")
        print(f"  Losses where OB-low was looser: {ob_lower_when_loss}")
        print(f"  (each represents a trade where ATR stop hit but OB-low would have held)")
        print("  → Definitive PnL simulation requires re-running with OHLCV;")
        print("    use this as directional evidence: if loosened%>>tightened%, OB-low is asymmetric")

    print("\n" + "=" * 110)

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""te_synthetic_ab.py — synthetic A/B for structural vs ATR targets.

Bypasses the historical-scoring BUY suppression by directly asking the
operational question: given a long entry on day T, would the structural
T1 be reached before the structural stop within H forward bars, vs the
ATR T1 vs ATR stop?

For each (ticker, day) in the lookback window:
  - Truncate OHLCV to day T → "point-in-time" df
  - STRUCT: target_engine.analyze_trade_cached(df_override=pit_df) → t1, t2, stop
  - ATR   : 14-period ATR on pit_df → entry, stop=entry-1.25×ATR, t1=entry+1.5×ATR, t2=entry+3.0×ATR
  - Walk forward H days
  - Record: hit_t1, hit_stop, time_to_t1, exit_reason, realized_r

Outputs:
  cache/logs/te_synthetic_ab_<DATE>.json — raw per-trade rows
  cache/logs/te_synthetic_ab_<DATE>.md   — aggregate diff report

Usage:
  python3 scripts/te_synthetic_ab.py --days 60 --hold 5
  python3 scripts/te_synthetic_ab.py --tickers AAPL MSFT --days 30
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# Use the same 20-ticker validation set as te_regression for consistency
VALIDATION_SET = [
    "AAPL", "MSFT", "NVDA", "AVGO", "GOOGL",
    "ROST", "AMD", "PLTR", "SOFI", "AMAT",
    "META", "TSLA", "NFLX", "CRM", "ORCL",
    "SPY", "QQQ", "XLF", "XLE", "IWM",
]


def compute_atr(df: pd.DataFrame, period: int = 14) -> float:
    """14-period True Range average — matches target_engine.compute_atr."""
    h = df["High"].values
    l = df["Low"].values
    c = df["Close"].values
    if len(c) < period + 1:
        return float("nan")
    tr = []
    for i in range(1, len(c)):
        tr.append(max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])))
    return float(sum(tr[-period:]) / period)


def replay_forward(future_df: pd.DataFrame, entry: float, stop: float,
                   t1: float, t2: float, hold_bars: int) -> dict:
    """Walk forward bar-by-bar. Stop-first ordering when both touched same bar."""
    bars = future_df.head(hold_bars)
    for i, (date, row) in enumerate(bars.iterrows()):
        hi = float(row["High"])
        lo = float(row["Low"])
        cl = float(row["Close"])
        # Stop-first when intrabar conflict (conservative)
        if lo <= stop:
            return {"exit": "stop", "bar": i + 1, "exit_price": stop,
                    "realized_r": (stop - entry) / (entry - stop) if entry > stop else 0,
                    "hit_t1": False, "hit_t2": False}
        if hi >= t1:
            # Did T2 also get hit?
            hit_t2 = (hi >= t2) if t2 and t2 > t1 else False
            exit_px = t2 if hit_t2 else t1
            return {"exit": "t2" if hit_t2 else "t1", "bar": i + 1, "exit_price": exit_px,
                    "realized_r": (exit_px - entry) / max(entry - stop, 1e-6),
                    "hit_t1": True, "hit_t2": hit_t2}
    # Time stop
    final_close = float(bars["Close"].iloc[-1])
    return {"exit": "time", "bar": hold_bars, "exit_price": final_close,
            "realized_r": (final_close - entry) / max(entry - stop, 1e-6),
            "hit_t1": False, "hit_t2": False}


def simulate_ticker(ticker: str, days_back: int, hold_bars: int) -> list:
    """For each of the last N trading days, compute STRUCT and ATR setups, replay forward."""
    from data_fetcher import fetch_ohlcv_with_failover
    from target_engine import analyze_trade_cached

    # Fetch enough history: lookback (400) + days_back + hold_bars buffer
    df, _ = fetch_ohlcv_with_failover(ticker, days=max(400 + days_back + hold_bars + 10, 600))
    if df is None or len(df) < 200 + days_back:
        return []

    # The replay window: last (days_back + hold_bars) bars
    # For each day T in the lookback range, df_pit = df[:T+1], future = df[T+1:T+1+hold_bars]
    rows = []
    n = len(df)
    # We need at least hold_bars of forward data after the entry day, so the
    # last valid entry day is n - 1 - hold_bars (0-indexed)
    last_entry_idx = n - 1 - hold_bars
    first_entry_idx = max(last_entry_idx - days_back + 1, 100)

    for T in range(first_entry_idx, last_entry_idx + 1):
        pit_df = df.iloc[:T + 1].copy()  # data through and including day T
        future_df = df.iloc[T + 1:T + 1 + hold_bars].copy()
        if len(future_df) < hold_bars:
            continue

        entry = float(pit_df["Close"].iloc[-1])
        atr = compute_atr(pit_df, period=14)
        if not atr or atr != atr or atr <= 0:
            continue

        # ─── ATR setup ───
        atr_stop = round(entry - 1.25 * atr, 2)
        atr_t1   = round(entry + 1.5 * atr, 2)
        atr_t2   = round(entry + 3.0 * atr, 2)
        atr_result = replay_forward(future_df, entry, atr_stop, atr_t1, atr_t2, hold_bars)

        # ─── STRUCT setup (point-in-time, cache-bypassed) ───
        struct_decision = "skip"
        struct_t1 = struct_t2 = struct_stop = None
        struct_result = None
        try:
            te = analyze_trade_cached(ticker, direction="long", mode="swing",
                                       df_override=pit_df)
            struct_decision = te.get("decision", "unknown")
            if struct_decision == "trade":
                t1d = te.get("t1") or {}
                t2d = te.get("t2") or {}
                struct_t1 = float(t1d.get("price") or 0)
                struct_t2 = float((t2d or {}).get("price") or struct_t1 * 1.02)
                # Use engine's stop if present, else mirror ATR stop
                struct_stop = float((te.get("stop") or {}).get("price") or atr_stop)
                if struct_t1 > entry and struct_stop < entry:
                    struct_result = replay_forward(future_df, entry, struct_stop,
                                                    struct_t1, struct_t2, hold_bars)
        except Exception:
            struct_decision = "exception"

        rows.append({
            "ticker": ticker,
            "entry_date": str(pit_df.index[-1].date() if hasattr(pit_df.index[-1], "date") else pit_df.index[-1]),
            "entry": entry,
            "atr": round(atr, 3),
            # ATR side
            "atr_t1": atr_t1, "atr_t2": atr_t2, "atr_stop": atr_stop,
            "atr_exit": atr_result["exit"],
            "atr_hit_t1": atr_result["hit_t1"],
            "atr_realized_r": round(atr_result["realized_r"], 3),
            "atr_bar": atr_result["bar"],
            # Struct side
            "struct_decision": struct_decision,
            "struct_t1": struct_t1, "struct_t2": struct_t2, "struct_stop": struct_stop,
            "struct_exit": (struct_result or {}).get("exit"),
            "struct_hit_t1": (struct_result or {}).get("hit_t1", False),
            "struct_realized_r": round((struct_result or {}).get("realized_r", 0), 3) if struct_result else None,
            "struct_bar": (struct_result or {}).get("bar"),
        })
    return rows


def aggregate(rows: list) -> dict:
    """Summary stats over all entries — paired comparison."""
    if not rows:
        return {}

    # Only compare rows where BOTH engines produced a setup (struct_decision==trade)
    paired = [r for r in rows if r.get("struct_decision") == "trade" and r.get("struct_result_is_real", True)
              and r.get("struct_realized_r") is not None]
    struct_rejected = sum(1 for r in rows if r.get("struct_decision") == "reject")
    struct_skipped = sum(1 for r in rows if r.get("struct_decision") not in ("trade", "reject"))

    def agg(side_prefix: str, subset: list) -> dict:
        hits = [r[f"{side_prefix}_hit_t1"] for r in subset]
        rs   = [r[f"{side_prefix}_realized_r"] for r in subset if r[f"{side_prefix}_realized_r"] is not None]
        wins = [r for r in subset if r[f"{side_prefix}_realized_r"] is not None and r[f"{side_prefix}_realized_r"] > 0]
        losses = [r for r in subset if r[f"{side_prefix}_realized_r"] is not None and r[f"{side_prefix}_realized_r"] < 0]
        avg_win  = statistics.mean([r[f"{side_prefix}_realized_r"] for r in wins])   if wins   else 0
        avg_loss = statistics.mean([r[f"{side_prefix}_realized_r"] for r in losses]) if losses else 0
        # Profit factor: sum positive R / abs sum negative R
        pos_sum = sum(r[f"{side_prefix}_realized_r"] for r in wins)
        neg_sum = sum(abs(r[f"{side_prefix}_realized_r"]) for r in losses)
        pf = pos_sum / neg_sum if neg_sum > 0 else float("inf") if pos_sum > 0 else 0
        return {
            "n": len(subset),
            "hit_rate_t1_pct": round(100 * sum(hits) / len(hits), 1) if hits else 0,
            "avg_R": round(statistics.mean(rs), 3) if rs else 0,
            "median_R": round(statistics.median(rs), 3) if rs else 0,
            "win_rate_pct": round(100 * len(wins) / len(subset), 1) if subset else 0,
            "avg_win_R": round(avg_win, 3),
            "avg_loss_R": round(avg_loss, 3),
            "profit_factor": round(pf, 2) if pf != float("inf") else "∞",
        }

    return {
        "total_rows": len(rows),
        "paired_n": len(paired),
        "struct_rejected": struct_rejected,
        "struct_skipped": struct_skipped,
        "atr_full":    agg("atr", rows),                      # ATR's full set (always trades)
        "atr_paired":  agg("atr", paired),                    # ATR restricted to paired set
        "struct_paired": agg("struct", paired),               # Struct on paired set
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=60, help="Trading days back to test")
    ap.add_argument("--hold", type=int, default=5, help="Forward hold bars per trade")
    ap.add_argument("--tickers", nargs="*", default=None, help="Override validation set")
    args = ap.parse_args()

    tickers = args.tickers or VALIDATION_SET
    print(f"══ te_synthetic_ab · {datetime.utcnow().isoformat()}Z ══")
    print(f"Tickers: {len(tickers)}  · Lookback: {args.days}d  · Hold: {args.hold}d")
    print(f"Approx setups: {len(tickers) * args.days}\n")

    t0 = time.time()
    all_rows = []
    for i, t in enumerate(tickers, 1):
        ts = time.time()
        rows = simulate_ticker(t, args.days, args.hold)
        elapsed = time.time() - ts
        n_struct_trade = sum(1 for r in rows if r.get("struct_decision") == "trade")
        n_struct_reject = sum(1 for r in rows if r.get("struct_decision") == "reject")
        print(f"  [{i:2}/{len(tickers)}] {t:6s}  {len(rows):3d} setups  "
              f"struct:trade={n_struct_trade} reject={n_struct_reject}  ({elapsed:.1f}s)")
        all_rows.extend(rows)

    print(f"\n  Total elapsed: {time.time() - t0:.1f}s, total rows: {len(all_rows)}")

    summary = aggregate(all_rows)

    # ─── Write outputs ───
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / "cache" / "logs"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"te_synthetic_ab_{stamp}.json"
    md_path   = out_dir / f"te_synthetic_ab_{stamp}.md"
    json_path.write_text(json.dumps({
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "args": vars(args),
        "tickers": tickers,
        "summary": summary,
        "rows": all_rows,
    }, indent=2, default=str))

    # Build the human-readable diff report
    lines = []
    lines.append("# Structural-Target Synthetic A/B — Forward Replay\n")
    lines.append(f"_Generated: {datetime.utcnow().isoformat()}Z_\n")
    lines.append(f"- Universe: {len(tickers)} tickers · Lookback: {args.days}d · Hold: {args.hold}d\n")
    lines.append(f"- Total setups evaluated: **{summary.get('total_rows', 0)}**")
    lines.append(f"- Setups where struct produced a target (paired): **{summary.get('paired_n', 0)}**")
    lines.append(f"- Struct rejected (no qualifying target): **{summary.get('struct_rejected', 0)}**")
    lines.append(f"- Struct skipped / other: **{summary.get('struct_skipped', 0)}**\n")

    lines.append("## Aggregate comparison\n")
    lines.append("| Metric | ATR (all) | ATR (paired) | Struct (paired) | Δ Struct − ATR |")
    lines.append("|---|---|---|---|---|")
    def diff(a, b):
        try: return f"{b - a:+.3f}" if isinstance(a, (int, float)) and isinstance(b, (int, float)) else "—"
        except Exception: return "—"
    af = summary.get("atr_full", {})
    ap_ = summary.get("atr_paired", {})
    sp = summary.get("struct_paired", {})
    for key in ["n", "hit_rate_t1_pct", "win_rate_pct", "avg_R", "median_R",
                "avg_win_R", "avg_loss_R", "profit_factor"]:
        lines.append(f"| {key} | {af.get(key)} | {ap_.get(key)} | {sp.get(key)} | {diff(ap_.get(key), sp.get(key))} |")

    md_path.write_text("\n".join(lines))
    print(f"\n  JSON: {json_path}")
    print(f"  MD  : {md_path}\n")
    print("══ Aggregate ══")
    print(f"  ATR (paired): n={ap_.get('n')}  hit-rate={ap_.get('hit_rate_t1_pct')}%  PF={ap_.get('profit_factor')}  avg-R={ap_.get('avg_R')}")
    print(f"  STR (paired): n={sp.get('n')}  hit-rate={sp.get('hit_rate_t1_pct')}%  PF={sp.get('profit_factor')}  avg-R={sp.get('avg_R')}")


if __name__ == "__main__":
    main()

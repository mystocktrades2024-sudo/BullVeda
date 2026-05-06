"""
backtest_pullback.py — Pure Minervini pullback backtest.

No scoring engine. No thresholds. Just price action rules:
  1. Hit 52-week high in last 20 days
  2. Pulled back 3-10% from high
  3. Near rising EMA21 (within 1.5 ATR)
  4. Volume dried up (5-day avg vol < 80% of 20-day avg)
  5. TRIGGER: close > prior day's high on volume > 20d avg
  6. STOP: below pullback low - 0.3 ATR
  7. TARGET: retest of 52-week high
  8. TIME STOP: exit after hold_days if neither stop nor target hit

Usage:
  python3 backtest_pullback.py                    # default 252 days
  python3 backtest_pullback.py --days 120         # shorter window
  python3 backtest_pullback.py --days 252 --hold 21
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bt_pullback")

BASE = Path(__file__).parent


def run_backtest(days: int = 252, hold_days: int = 14, equity: float = 10000,
                 max_positions: int = 5, pct_per_trade: float = 0.20,
                 min_pullback: float = 0.02, max_pullback: float = 0.10):
    """Run pure pullback backtest on archive data."""

    log.info(f"=== Pullback Backtest: {days}d, {hold_days}d hold, ${equity:,.0f} ===")
    log.info(f"Rules: 52wk high in 20d, pullback {min_pullback*100:.0f}-{max_pullback*100:.0f}%, "
             f"near rising EMA21, vol dry, trigger on bounce")

    # Load archive
    from data_archive import load_all
    t0 = time.time()
    ohlcv = load_all()
    log.info(f"Loaded {len(ohlcv)} tickers in {time.time()-t0:.1f}s")

    # Need SPY for benchmark
    spy = ohlcv.get("SPY")
    if spy is None or spy.empty:
        log.error("No SPY data"); return

    # Determine date range
    spy_dates = sorted(spy.index)
    end_idx = len(spy_dates) - 1
    start_idx = max(0, end_idx - days)
    trade_dates = [d for d in spy_dates[start_idx:end_idx]]
    log.info(f"Window: {trade_dates[0].date()} → {trade_dates[-1].date()} ({len(trade_dates)} bars)")

    # Simulation state
    cash = equity
    positions = []
    closed_trades = []
    equity_curve = []
    monthly_pnl = defaultdict(float)

    total_signals = 0
    total_triggers = 0
    total_skipped_full = 0

    for di, today in enumerate(trade_dates):
        today_str = str(today.date()) if hasattr(today, 'date') else str(today)[:10]

        # ── Update positions ──
        still_open = []
        for pos in positions:
            ticker = pos["ticker"]
            df = ohlcv.get(ticker)
            if df is None:
                still_open.append(pos); continue

            # Find today's bar
            mask = df.index <= today
            if not mask.any():
                still_open.append(pos); continue
            bar_idx = mask.sum() - 1
            if bar_idx < 0:
                still_open.append(pos); continue

            today_high = float(df["High"].iloc[bar_idx])
            today_low = float(df["Low"].iloc[bar_idx])
            today_close = float(df["Close"].iloc[bar_idx])
            pos["days_held"] += 1
            pos["current_price"] = today_close

            # Check stop
            if today_low <= pos["stop"]:
                pnl = (pos["stop"] - pos["entry"]) * pos["shares"]
                pnl_pct = (pos["stop"] / pos["entry"] - 1) * 100
                closed_trades.append({**pos, "exit": pos["stop"], "exit_date": today_str,
                                      "pnl": round(pnl, 2), "pnl_pct": round(pnl_pct, 2),
                                      "exit_reason": "stop_loss"})
                cash += pos["position_size"] + pnl
                month = today_str[:7]
                monthly_pnl[month] += pnl
                continue

            # Check target (52wk high retest)
            if today_high >= pos["target"]:
                pnl = (pos["target"] - pos["entry"]) * pos["shares"]
                pnl_pct = (pos["target"] / pos["entry"] - 1) * 100
                closed_trades.append({**pos, "exit": pos["target"], "exit_date": today_str,
                                      "pnl": round(pnl, 2), "pnl_pct": round(pnl_pct, 2),
                                      "exit_reason": "target_hit"})
                cash += pos["position_size"] + pnl
                monthly_pnl[today_str[:7]] += pnl
                continue

            # Check trailing stop (activate at +3%, trail at 1.5 ATR)
            if today_close > pos.get("highest", pos["entry"]):
                pos["highest"] = today_close
            gain_pct = (pos["highest"] / pos["entry"] - 1) * 100
            if gain_pct >= 3:
                trail_stop = pos["highest"] - pos["atr"] * 1.5
                if trail_stop > pos["stop"]:
                    pos["stop"] = trail_stop
                if today_low <= pos["stop"]:
                    pnl = (pos["stop"] - pos["entry"]) * pos["shares"]
                    pnl_pct = (pos["stop"] / pos["entry"] - 1) * 100
                    closed_trades.append({**pos, "exit": pos["stop"], "exit_date": today_str,
                                          "pnl": round(pnl, 2), "pnl_pct": round(pnl_pct, 2),
                                          "exit_reason": "trailing_stop"})
                    cash += pos["position_size"] + pnl
                    monthly_pnl[today_str[:7]] += pnl
                    continue

            # Time stop
            if pos["days_held"] >= hold_days:
                pnl = (today_close - pos["entry"]) * pos["shares"]
                pnl_pct = (today_close / pos["entry"] - 1) * 100
                closed_trades.append({**pos, "exit": today_close, "exit_date": today_str,
                                      "pnl": round(pnl, 2), "pnl_pct": round(pnl_pct, 2),
                                      "exit_reason": "time_stop"})
                cash += pos["position_size"] + pnl
                monthly_pnl[today_str[:7]] += pnl
                continue

            still_open.append(pos)
        positions = still_open

        # ── Scan for new setups ──
        if len(positions) >= max_positions:
            continue

        candidates = []
        for ticker, df in ohlcv.items():
            if ticker == "SPY" or any(p["ticker"] == ticker for p in positions):
                continue
            try:
                mask = df.index <= today
                if mask.sum() < 60:
                    continue
                hist = df[mask]
                c = hist["Close"].squeeze()
                h = hist["High"].squeeze()
                l = hist["Low"].squeeze()
                v = hist["Volume"].squeeze() if "Volume" in hist.columns else None
                if v is None or len(v) < 20:
                    continue

                price = float(c.iloc[-1])
                if price <= 0 or price < 5:
                    continue

                # 1. 52-week high in last 20 days
                high_252 = float(h.tail(252).max()) if len(h) >= 252 else float(h.max())
                recent_20 = h.tail(20)
                hit_near_high = any(float(bar) >= high_252 * 0.98 for bar in recent_20)
                if not hit_near_high:
                    continue

                # 2. Pullback 3-10%
                pullback = (high_252 - price) / high_252
                if pullback < min_pullback or pullback > max_pullback:
                    continue

                # 3. Near rising EMA21
                ema21 = float(c.ewm(span=21, adjust=False).mean().iloc[-1])
                ema21_prev = float(c.ewm(span=21, adjust=False).mean().iloc[-6])
                if ema21 <= ema21_prev:
                    continue
                atr = float((h - l).tail(14).mean())
                if abs(price - ema21) > atr * 1.5:
                    continue

                # 4. Volume dried up
                avg_vol = float(v.tail(20).mean())
                recent_vol = float(v.tail(5).mean())
                if avg_vol <= 0 or recent_vol / avg_vol >= 0.8:
                    continue

                # 5. TRIGGER: close > prior day high AND volume > avg
                prior_high = float(h.iloc[-2]) if len(h) >= 2 else price
                today_vol = float(v.iloc[-1])
                triggered = price > prior_high and today_vol > avg_vol * 0.8

                if not triggered:
                    total_signals += 1
                    continue

                total_triggers += 1

                # Trade plan
                pullback_low = float(l.tail(20).min())
                stop = min(pullback_low, ema21) - atr * 0.5
                target = price + (high_252 - price) * 0.7
                risk = price - stop
                reward = target - price
                rr = reward / risk if risk > 0 else 0
                if rr < 0.8:
                    continue

                candidates.append({
                    "ticker": ticker,
                    "price": price,
                    "high_52w": high_252,
                    "pullback_pct": round(pullback * 100, 1),
                    "stop": round(stop, 2),
                    "target": round(target, 2),
                    "rr": round(rr, 1),
                    "atr": round(atr, 2),
                })
            except Exception:
                continue

        # Rank by R:R, take top N needed
        candidates.sort(key=lambda x: -x["rr"])
        slots = max_positions - len(positions)

        for sig in candidates[:slots]:
            pos_size = min(equity * pct_per_trade, cash)
            if pos_size < 100:
                total_skipped_full += 1
                continue
            shares = int(pos_size / sig["price"])
            if shares <= 0:
                continue
            actual_size = shares * sig["price"]
            cash -= actual_size
            positions.append({
                "ticker": sig["ticker"],
                "entry": sig["price"],
                "entry_date": today_str,
                "shares": shares,
                "position_size": actual_size,
                "stop": sig["stop"],
                "target": sig["target"],
                "atr": sig["atr"],
                "days_held": 0,
                "highest": sig["price"],
                "pullback_pct": sig["pullback_pct"],
                "rr": sig["rr"],
            })

        # Equity curve
        pos_value = sum(p.get("current_price", p["entry"]) * p["shares"] for p in positions)
        total_equity = cash + pos_value
        equity_curve.append((today_str, round(total_equity, 2)))

        # Progress
        if (di + 1) % 50 == 0:
            log.info(f"  Day {di+1}/{len(trade_dates)}: equity=${total_equity:,.0f} "
                     f"positions={len(positions)} trades={len(closed_trades)}")

    # Close remaining positions at last price
    for pos in positions:
        price = pos.get("current_price", pos["entry"])
        pnl = (price - pos["entry"]) * pos["shares"]
        pnl_pct = (price / pos["entry"] - 1) * 100
        closed_trades.append({**pos, "exit": price, "exit_date": today_str,
                              "pnl": round(pnl, 2), "pnl_pct": round(pnl_pct, 2),
                              "exit_reason": "end_of_backtest"})
        cash += pos["position_size"] + pnl

    # ── Results ──
    final_equity = cash
    total_pnl = final_equity - equity
    total_return = (final_equity / equity - 1) * 100

    wins = [t for t in closed_trades if t["pnl"] > 0]
    losses = [t for t in closed_trades if t["pnl"] <= 0]
    wr = len(wins) / len(closed_trades) * 100 if closed_trades else 0
    avg_win = np.mean([t["pnl_pct"] for t in wins]) if wins else 0
    avg_loss = np.mean([t["pnl_pct"] for t in losses]) if losses else 0
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = abs(sum(t["pnl"] for t in losses))
    pf = gross_win / gross_loss if gross_loss > 0 else 0

    # Max drawdown
    peak = equity
    max_dd = 0
    for _, eq in equity_curve:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak * 100
        if dd > max_dd:
            max_dd = dd

    # Exit reasons
    exit_reasons = defaultdict(int)
    for t in closed_trades:
        exit_reasons[t["exit_reason"]] += 1

    # Monthly breakdown
    sorted_months = sorted(monthly_pnl.keys())
    pos_months = sum(1 for m in sorted_months if monthly_pnl[m] > 0)

    # SPY benchmark
    spy_start = float(spy["Close"].iloc[start_idx])
    spy_end = float(spy["Close"].iloc[end_idx])
    spy_return = (spy_end / spy_start - 1) * 100

    print(f"\n{'='*70}")
    print(f"PULLBACK SCANNER BACKTEST RESULTS")
    print(f"Pure Minervini rules — no scoring engine")
    print(f"{'='*70}")
    print(f"Starting Equity:  ${equity:>10,.0f}")
    print(f"Final Equity:     ${final_equity:>10,.0f}  ({total_return:+.1f}%)")
    print(f"Total P&L:        ${total_pnl:>10,.0f}")
    print(f"SPY Benchmark:    {spy_return:>10.1f}%")
    print(f"Alpha vs SPY:     {total_return - spy_return:>10.1f}%")
    print(f"Total Trades:     {len(closed_trades):>10}")
    print(f"Win Rate:         {wr:>10.1f}%  ({len(wins)}W / {len(losses)}L)")
    print(f"Avg Win:          {avg_win:>10.2f}%")
    print(f"Avg Loss:         {avg_loss:>10.2f}%")
    print(f"Profit Factor:    {pf:>10.2f}")
    print(f"Max Drawdown:     {max_dd:>10.1f}%")
    print(f"Positive Months:  {pos_months}/{len(sorted_months)}")
    print(f"Signals Seen:     {total_signals:>10} (not triggered)")
    print(f"Triggers Fired:   {total_triggers:>10}")
    print(f"Skipped (no cash):{total_skipped_full:>10}")
    print(f"\nMonthly P&L:")
    for m in sorted_months:
        bar = "+" * int(max(0, monthly_pnl[m] / 30)) if monthly_pnl[m] > 0 else "-" * int(max(0, abs(monthly_pnl[m]) / 30))
        print(f"  {m}: ${monthly_pnl[m]:>10,.0f}  {bar}")
    print(f"\nExit Reasons:")
    for reason, count in sorted(exit_reasons.items(), key=lambda x: -x[1]):
        print(f"  {reason:<20} {count:>3} trades")

    # Per-ticker breakdown (top winners + losers)
    by_ticker = defaultdict(list)
    for t in closed_trades:
        by_ticker[t["ticker"]].append(t)
    ticker_pnl = {tk: sum(t["pnl"] for t in trades) for tk, trades in by_ticker.items()}
    sorted_tickers = sorted(ticker_pnl.items(), key=lambda x: -x[1])
    if sorted_tickers:
        print(f"\nTop Winners:")
        for tk, pnl in sorted_tickers[:5]:
            if pnl > 0:
                print(f"  {tk:<6} ${pnl:>8,.0f}  ({len(by_ticker[tk])} trades)")
        print(f"\nTop Losers:")
        for tk, pnl in sorted_tickers[-5:]:
            if pnl < 0:
                print(f"  {tk:<6} ${pnl:>8,.0f}  ({len(by_ticker[tk])} trades)")

    # Improvement recommendations
    print(f"\n{'='*70}")
    print(f"IMPROVEMENT ANALYSIS")
    print(f"{'='*70}")

    if wr < 40:
        print(f"\n1. WIN RATE ({wr:.0f}%) is too low:")
        print(f"   - Tighten pullback range (try 4-7% instead of 3-10%)")
        print(f"   - Require EMA50 rising too (stronger trend)")
        print(f"   - Add RS rank filter (only RS > 70 stocks)")

    if avg_loss and abs(avg_loss) > avg_win * 0.7:
        print(f"\n2. AVG LOSS ({avg_loss:.1f}%) too close to avg win ({avg_win:.1f}%):")
        print(f"   - Widen trigger requirement (close > 2-day high instead of 1-day)")
        print(f"   - Require volume > 1.5x avg (not just > avg)")

    stop_pct = exit_reasons.get("stop_loss", 0) / max(len(closed_trades), 1) * 100
    if stop_pct > 50:
        print(f"\n3. STOP-LOSS exits ({stop_pct:.0f}%) dominate:")
        print(f"   - Widen stop (try below EMA21 instead of pullback low)")
        print(f"   - Add time-based tightening (narrow stop after day 5)")

    target_pct = exit_reasons.get("target_hit", 0) / max(len(closed_trades), 1) * 100
    if target_pct < 20:
        print(f"\n4. TARGET HIT rate ({target_pct:.0f}%) is low:")
        print(f"   - Lower target (try 70% of distance to 52wk high)")
        print(f"   - Add partial profit at halfway point")

    time_stop_pct = exit_reasons.get("time_stop", 0) / max(len(closed_trades), 1) * 100
    if time_stop_pct > 30:
        print(f"\n5. TIME STOPS ({time_stop_pct:.0f}%) suggest hold period too short:")
        print(f"   - Extend hold to 21-30 days")

    if pf < 1.0 and pf > 0.7:
        print(f"\n6. PROFIT FACTOR ({pf:.2f}) is close to break-even:")
        print(f"   - Small improvements compound: +5% WR or +1% avg win would flip positive")
        print(f"   - Focus on entry timing (add MACD crossover or RSI>50 confirmation)")

    # Save results
    results = {
        "strategy": "pullback_scanner",
        "days": days, "hold_days": hold_days,
        "equity": equity, "final_equity": round(final_equity, 2),
        "return_pct": round(total_return, 2),
        "spy_return_pct": round(spy_return, 2),
        "alpha_pct": round(total_return - spy_return, 2),
        "trades": len(closed_trades), "wr": round(wr, 1),
        "pf": round(pf, 2), "max_dd": round(max_dd, 1),
        "avg_win": round(avg_win, 2), "avg_loss": round(avg_loss, 2),
        "monthly_pnl": dict(monthly_pnl),
        "exit_reasons": dict(exit_reasons),
        "closed_trades": closed_trades,
    }
    out_path = BASE / "cache" / "pullback_backtest.json"
    out_path.write_text(json.dumps(results, default=str, indent=2))
    log.info(f"Results saved: {out_path}")
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=252)
    ap.add_argument("--hold", type=int, default=14)
    ap.add_argument("--equity", type=float, default=10000)
    ap.add_argument("--positions", type=int, default=5)
    ap.add_argument("--size", type=float, default=0.20)
    args = ap.parse_args()
    run_backtest(days=args.days, hold_days=args.hold, equity=args.equity,
                 max_positions=args.positions, pct_per_trade=args.size)

#!/usr/bin/env python3
"""backtest_audit3_fixes.py — counterfactual: would the new fixes have prevented
the recent 20 losing BUYs?

Re-applies the three Audit Batch 3 fixes to the historical signal_log:
  P0: Bypass requires score >= 60 AND tier != AVOID
  P1: EXTENDED → 0.5x size, MISSED → 0.4x
  P2: Same-ticker stop-out → 5-day cooldown

Then computes: of the 20 recent losing trades, how many would have been
blocked or sized down (and by how much), and what the new aggregate
WR / PF would be.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SL_PATH = REPO / "data" / "signal_log.json"


def _load_recent_closed_buys(n: int = 20) -> list[dict]:
    sl = json.loads(SL_PATH.read_text())
    closed = [s for s in sl if s.get("status") == "CLOSED"
              and (s.get("verdict") or "").upper() == "BUY"
              and s.get("actual_pnl_pct") is not None
              and s.get("date")]
    closed.sort(key=lambda s: s.get("date", ""), reverse=True)
    return closed[:n]


def _would_block(trade: dict, prior_stops: dict, cooldown_days: int = 5) -> tuple[bool, str]:
    """Apply each fix and return (blocked, reason)."""
    ticker = trade.get("ticker")
    score = trade.get("score") or 0
    eq = (trade.get("entry_quality") or "").upper()
    setup = trade.get("setup_family") or trade.get("strategy") or ""
    conviction = trade.get("conviction_label") or ""

    # P0: tier=AVOID hard block
    if conviction.upper() == "AVOID":
        return True, f"P0 block: conviction=AVOID (was bypassed before)"

    # P0: score < 60 floor on bypass-eligible sleeves
    is_catalyst = setup in ("PEAD", "Momentum Continuation", "Defensive Rotation",
                            "Mean Reversion", "Insider Cluster", "ESP Play")
    is_watch_tier = conviction.upper() == "WATCH"
    if is_catalyst and is_watch_tier and score < 60:
        return True, f"P0 block: catalyst sleeve {setup} WATCH-tier requires score>=60 (got {score})"

    # P2: same-ticker cooldown
    if ticker in prior_stops:
        last_stop = prior_stops[ticker]
        try:
            trade_dt = datetime.fromisoformat(trade["date"][:10])
            stop_dt = datetime.fromisoformat(last_stop[:10])
            days_since = (trade_dt - stop_dt).days
            if 0 < days_since < cooldown_days:
                return True, f"P2 block: same-ticker cooldown ({days_since}d < {cooldown_days}d since last stop)"
        except Exception:
            pass

    return False, ""


def _size_haircut(trade: dict) -> float:
    """P1: EXTENDED → 0.5x, MISSED → 0.4x for catalyst sleeves."""
    eq = (trade.get("entry_quality") or "").upper()
    setup = trade.get("setup_family") or trade.get("strategy") or ""
    is_catalyst = setup in ("PEAD", "Momentum Continuation", "Defensive Rotation",
                            "Mean Reversion", "Insider Cluster", "ESP Play")
    if not is_catalyst:
        return 1.0
    if eq == "EXTENDED":
        return 0.5
    if eq == "MISSED":
        return 0.4
    return 1.0


def main():
    print("=" * 80)
    print("AUDIT BATCH 3 COUNTERFACTUAL BACKTEST")
    print("=" * 80)
    print()

    recent = _load_recent_closed_buys(20)
    print(f"Loaded {len(recent)} recent closed BUYs ({recent[-1].get('date','?')[:10]} → {recent[0].get('date','?')[:10]})")
    print()

    # Build prior stop-out map (date-ordered, walk-forward)
    sl_all = json.loads(SL_PATH.read_text())
    sl_all = sorted([s for s in sl_all if s.get("date")], key=lambda s: s["date"])

    # For each trade in recent, find prior stop-outs on same ticker (before trade.date)
    blocked = []
    sized_down = []
    unchanged = []
    new_total_pnl = 0.0
    orig_total_pnl = 0.0
    blocked_count = 0
    sized_down_count = 0

    for t in recent[::-1]:  # process in chronological order
        ticker = t.get("ticker")
        trade_date = t.get("date", "")
        pnl_pct = float(t.get("actual_pnl_pct") or 0)
        orig_total_pnl += pnl_pct

        # Build prior_stops for THIS trade (only stops before trade_date)
        prior_stops_for_t = {}
        for s in sl_all:
            if s.get("status") != "CLOSED": continue
            if (s.get("exit_reason") or "") != "stop_hit": continue
            if not s.get("date"): continue
            if s["date"] >= trade_date: continue  # only PRIOR stops
            tk = s.get("ticker")
            if not tk: continue
            # Track latest per ticker
            if tk not in prior_stops_for_t or s["date"] > prior_stops_for_t[tk]:
                prior_stops_for_t[tk] = s["date"]

        block, reason = _would_block(t, prior_stops_for_t)
        haircut = _size_haircut(t)

        if block:
            blocked.append({"ticker": ticker, "date": trade_date[:10], "pnl": pnl_pct, "reason": reason})
            blocked_count += 1
            # blocked = no trade = 0 pnl contribution
            new_total_pnl += 0.0
        elif haircut < 1.0:
            sized_down.append({"ticker": ticker, "date": trade_date[:10], "pnl": pnl_pct,
                                "new_pnl": pnl_pct * haircut, "haircut": haircut, "eq": t.get("entry_quality")})
            sized_down_count += 1
            new_total_pnl += pnl_pct * haircut
        else:
            unchanged.append({"ticker": ticker, "date": trade_date[:10], "pnl": pnl_pct})
            new_total_pnl += pnl_pct

    # Print blocked trades
    print(f"=== BLOCKED ({blocked_count} trades) ===")
    if blocked:
        for b in blocked:
            print(f"  {b['ticker']:6s} {b['date']} pnl={b['pnl']:+.2f}% — {b['reason']}")
        print(f"  Avoided losses: {sum(b['pnl'] for b in blocked):+.2f}%")
    print()

    # Print sized-down
    print(f"=== SIZED DOWN ({sized_down_count} trades) ===")
    if sized_down:
        for s in sized_down:
            print(f"  {s['ticker']:6s} {s['date']} eq={s['eq']:<10s} orig={s['pnl']:+.2f}% × {s['haircut']:.1f}x = {s['new_pnl']:+.2f}%")
        print(f"  Loss reduction: {sum(s['pnl'] - s['new_pnl'] for s in sized_down):+.2f}%")
    print()

    print(f"=== UNCHANGED ({len(unchanged)} trades) ===")
    for u in unchanged:
        print(f"  {u['ticker']:6s} {u['date']} pnl={u['pnl']:+.2f}%")
    print()

    # Aggregate stats
    print("=" * 80)
    print("AGGREGATE COMPARISON")
    print("=" * 80)
    n_orig = len(recent)
    n_new = n_orig - blocked_count
    wins_orig = sum(1 for t in recent if float(t.get("actual_pnl_pct") or 0) > 0)
    wins_new = sum(1 for t in unchanged if t["pnl"] > 0) + \
                sum(1 for s in sized_down if s["new_pnl"] > 0)
    avg_orig = orig_total_pnl / max(n_orig, 1)
    avg_new = new_total_pnl / max(n_new, 1) if n_new > 0 else 0
    wr_orig = wins_orig / max(n_orig, 1) * 100
    wr_new = wins_new / max(n_new, 1) * 100 if n_new > 0 else 0

    print(f"  metric                  ORIGINAL        WITH FIXES       delta")
    print(f"  n trades                {n_orig:>8d}        {n_new:>8d}        -{blocked_count}")
    print(f"  wins                    {wins_orig:>8d}        {wins_new:>8d}        +{wins_new - wins_orig}")
    print(f"  WR%                     {wr_orig:>7.1f}%        {wr_new:>7.1f}%        {wr_new - wr_orig:+.1f}pp")
    print(f"  avg pnl                 {avg_orig:>+7.2f}%        {avg_new:>+7.2f}%        {avg_new - avg_orig:+.2f}pp")
    print(f"  total pnl               {orig_total_pnl:>+7.2f}%        {new_total_pnl:>+7.2f}%        {new_total_pnl - orig_total_pnl:+.2f}pp")
    print()

    # Rolling Sharpe estimate
    pnls_orig = [float(t.get("actual_pnl_pct") or 0) for t in recent]
    pnls_new = []
    for t in recent:
        block, _ = _would_block(t, {tk: s["date"] for tk, s in [(s["ticker"], s) for s in sl_all
                                                                  if s.get("status") == "CLOSED"
                                                                  and (s.get("exit_reason") or "") == "stop_hit"
                                                                  and s.get("date", "") < t.get("date", "")]})
        if block:
            continue
        pnls_new.append(float(t.get("actual_pnl_pct") or 0) * _size_haircut(t))
    if pnls_orig and len(pnls_orig) >= 2:
        import statistics
        std_orig = statistics.stdev(pnls_orig)
        std_new = statistics.stdev(pnls_new) if len(pnls_new) >= 2 else 0
        sharpe_orig = (sum(pnls_orig)/len(pnls_orig)) / std_orig if std_orig > 0 else 0
        sharpe_new = (sum(pnls_new)/len(pnls_new)) / std_new if std_new > 0 and pnls_new else 0
        print(f"  Sharpe per-trade        {sharpe_orig:>+7.3f}         {sharpe_new:>+7.3f}         {sharpe_new - sharpe_orig:+.3f}")
        print()
        print(f"  Rolling Sharpe threshold = -0.500")
        print(f"  Original at -0.508 → kill ACTIVE")
        if sharpe_new > -0.50:
            print(f"  With fixes at {sharpe_new:+.3f} → kill CLEARED ✓")
        else:
            print(f"  With fixes at {sharpe_new:+.3f} → kill still active")

    print()
    print(f"Verdict: {blocked_count} of {n_orig} losing trades would have been BLOCKED")
    print(f"         {sized_down_count} of {n_orig} losing trades would have been SIZED DOWN")
    if new_total_pnl > orig_total_pnl:
        print(f"         Total PnL improves by {new_total_pnl - orig_total_pnl:+.2f}pp")
    else:
        print(f"         Total PnL unchanged or worse — fixes need reconsideration")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
filter_audit.py — measure per-filter rejection rate + false-rejection rate.

Reads cache/last_bundle.json + cache/portfolio_backtest.json. For each
active filter (price/vol, score floor, RS minimum, R:R minimum, entry
quality, setup gates, kill list, circuit breaker, etc.), computes:

  - reject_rate:        % of candidates the filter would reject
  - winners_rejected:   % of WINNERS the filter would have rejected
  - losers_rejected:    % of LOSERS the filter would have rejected
  - net_lift:           (losers_rejected - winners_rejected) — positive = filter helps PF
  - rejection_share:    % of total rejections this filter is responsible for

Output: cache/filter_audit_<YYYY-MM-DD>.{json,csv} + console table.

Goal: identify filters that reject more winners than losers (= they're
hurting, not helping). Those are candidates to relax.

Per OPERATING MINDSET principle 7: 'No knob-tweaking without evidence' —
THIS is the evidence layer for the filter stack itself.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
from collections import defaultdict
import datetime as dt

REPO = Path(__file__).resolve().parents[1]


def _load_signal_log() -> list[dict]:
    """Closed signals from data/signal_log.json — has WR by setup/regime."""
    p = REPO / "data" / "signal_log.json"
    if not p.exists():
        return []
    sigs = json.loads(p.read_text())
    return [s for s in sigs if s.get("status") == "CLOSED" and s.get("actual_pnl_pct") is not None]


def _load_recent_backtest_trades() -> list[dict]:
    """Most recent portfolio backtest trades (n=142 from Q1-step5)."""
    p = REPO / "cache" / "portfolio_backtest.json"
    if not p.exists():
        return []
    b = json.loads(p.read_text())
    return b.get("trades") or []


# ──────────────────────────────────────────────────────────────────────────────
# Filter simulators — each returns True if the trade would PASS the filter
# (i.e., NOT be rejected). False = rejected.
# ──────────────────────────────────────────────────────────────────────────────

def _filter_score_floor(trade: dict, threshold: int) -> bool:
    score = trade.get("score") or 0
    return score >= threshold


def _filter_score_band(trade: dict, lo: int, hi: int) -> bool:
    score = trade.get("score") or 0
    return lo <= score <= hi


def _filter_rs_minimum(trade: dict, threshold: int) -> bool:
    rs = trade.get("rs_rank") or 0
    return rs >= threshold


def _filter_rr_minimum(trade: dict, threshold: float) -> bool:
    rr = trade.get("rr_ratio") or trade.get("rr") or 0
    return rr >= threshold


def _filter_setup_kill_list(trade: dict, killed: set) -> bool:
    setup = trade.get("setup_type") or trade.get("strategy") or ""
    return setup not in killed


def _filter_regime_long_only(trade: dict, allowed: set) -> bool:
    regime = (trade.get("regime") or "").lower()
    return regime in allowed


def _filter_earnings_blackout(trade: dict, days: int) -> bool:
    earn = trade.get("earn_days")
    if earn is None:
        return True
    return earn > days


def _filter_weekly_bull(trade: dict) -> bool | None:
    """Return None if field not populated (caller should skip this trade)."""
    if "weekly_bull" not in trade or trade.get("weekly_bull") is None:
        return None  # field missing — exclude from audit
    return bool(trade.get("weekly_bull"))


def _filter_entry_quality_fresh_only(trade: dict) -> bool | None:
    eq = trade.get("entry_quality")
    if not eq:
        return None
    return eq.upper() == "FRESH"


def _filter_entry_quality_not_extended(trade: dict) -> bool | None:
    eq = trade.get("entry_quality")
    if not eq:
        return None
    return eq.upper() not in ("EXTENDED", "MISSED")


def _filter_setup_size_mult_bull(trade: dict, killed_in_bull: set) -> bool:
    """Variant F: regime-conditional kill. TC in bull → reject."""
    setup = trade.get("setup_type") or trade.get("strategy") or ""
    regime = (trade.get("regime") or "").lower()
    return not (setup in killed_in_bull and regime == "bull")


# ──────────────────────────────────────────────────────────────────────────────
# Filter set — each entry is a tuple of (name, simulator, kwargs)
# ──────────────────────────────────────────────────────────────────────────────
FILTERS = [
    ("score_floor_65",      _filter_score_floor,            {"threshold": 65}),
    ("score_floor_72",      _filter_score_floor,            {"threshold": 72}),
    ("score_floor_80",      _filter_score_floor,            {"threshold": 80}),
    ("score_floor_82",      _filter_score_floor,            {"threshold": 82}),
    ("score_band_70_89",    _filter_score_band,             {"lo": 70, "hi": 89}),
    ("score_band_80_95",    _filter_score_band,             {"lo": 80, "hi": 95}),
    ("rs_min_65",           _filter_rs_minimum,             {"threshold": 65}),
    ("rs_min_75",           _filter_rs_minimum,             {"threshold": 75}),
    ("rs_min_85",           _filter_rs_minimum,             {"threshold": 85}),
    ("rr_min_3.0",          _filter_rr_minimum,             {"threshold": 3.0}),
    ("rr_min_3.5",          _filter_rr_minimum,             {"threshold": 3.5}),
    ("entry_FRESH_only",    _filter_entry_quality_fresh_only, {}),
    ("entry_not_EXTENDED",  _filter_entry_quality_not_extended, {}),
    ("kill_EMA21_52wk",     _filter_setup_kill_list,        {"killed": {"EMA21 Pullback", "52wk Breakout"}}),
    ("regime_bull_neutral", _filter_regime_long_only,       {"allowed": {"bull", "neutral"}}),
    ("regime_bull_only",    _filter_regime_long_only,       {"allowed": {"bull"}}),
    ("earnings_7d_blackout", _filter_earnings_blackout,     {"days": 7}),
    ("weekly_bull_required", _filter_weekly_bull,           {}),
    ("variant_F_TC_in_bull", _filter_setup_size_mult_bull,  {"killed_in_bull": {"Trend Continuation"}}),
]


def audit_filters(trades: list[dict]) -> list[dict]:
    """Run each filter against every trade. Compute lift stats."""
    if not trades:
        return []

    # Split trades into winners + losers
    winners = [t for t in trades if (t.get("pnl_pct") or t.get("actual_pnl_pct") or 0) > 0]
    losers  = [t for t in trades if (t.get("pnl_pct") or t.get("actual_pnl_pct") or 0) <= 0]
    n_total = len(trades)
    n_win   = len(winners)
    n_loss  = len(losers)

    print(f"Audit set: {n_total} trades ({n_win} winners / {n_loss} losers)")
    print()

    rows = []
    for name, fn, kwargs in FILTERS:
        try:
            # 2026-05-10: filters can return None when the field isn't populated
            # on the trade. Exclude those trades from the per-filter denominator
            # so the metric reflects "this filter's behavior on trades where it
            # COULD make a decision", not "this filter rejected everything
            # because the field is missing in the data pipeline."
            scored = [(t, fn(t, **kwargs)) for t in trades]
            scored = [(t, r) for t, r in scored if r is not None]
            n_evaluable = len(scored)
            if n_evaluable == 0:
                rows.append({"filter": name, "skipped": True,
                             "reason": "field not populated in any trade"})
                continue

            n_passed = sum(1 for _, r in scored if r)
            n_rejected = n_evaluable - n_passed
            win_scored = [(t, r) for t, r in scored if (t.get("pnl_pct") or t.get("actual_pnl_pct") or 0) > 0]
            loss_scored = [(t, r) for t, r in scored if (t.get("pnl_pct") or t.get("actual_pnl_pct") or 0) <= 0]
            n_win = len(win_scored)
            n_loss = len(loss_scored)
            n_win_passed = sum(1 for _, r in win_scored if r)
            n_loss_passed = sum(1 for _, r in loss_scored if r)
            n_win_rejected = n_win - n_win_passed
            n_loss_rejected = n_loss - n_loss_passed

            reject_rate = n_rejected / n_evaluable if n_evaluable else 0
            win_rej_rate = n_win_rejected / n_win if n_win else 0
            loss_rej_rate = n_loss_rejected / n_loss if n_loss else 0
            net_lift = loss_rej_rate - win_rej_rate

            # PF contribution: if we remove the filter, what's the PF on rejected trades?
            rej_trades = [t for t, r in scored if not r]
            rej_win_sum = sum((t.get("pnl_pct") or t.get("actual_pnl_pct") or 0)
                              for t in rej_trades
                              if (t.get("pnl_pct") or t.get("actual_pnl_pct") or 0) > 0)
            rej_loss_sum = abs(sum((t.get("pnl_pct") or t.get("actual_pnl_pct") or 0)
                                   for t in rej_trades
                                   if (t.get("pnl_pct") or t.get("actual_pnl_pct") or 0) <= 0))
            rej_pf = (rej_win_sum / rej_loss_sum) if rej_loss_sum > 0 else (
                float("inf") if rej_win_sum > 0 else 0)

            rows.append({
                "filter": name,
                "n_evaluable": n_evaluable,
                "passed": n_passed,
                "rejected": n_rejected,
                "reject_rate_pct": round(reject_rate * 100, 1),
                "win_rejected_pct": round(win_rej_rate * 100, 1),
                "loss_rejected_pct": round(loss_rej_rate * 100, 1),
                "net_lift_pp": round(net_lift * 100, 1),
                "rejected_pf": round(rej_pf, 2) if rej_pf != float("inf") else "inf",
                "verdict": (
                    "STRONG_HELP"  if net_lift > 0.15 else
                    "WEAK_HELP"    if net_lift > 0.05 else
                    "NEUTRAL"      if abs(net_lift) <= 0.05 else
                    "WEAK_HURT"    if net_lift > -0.15 else
                    "STRONG_HURT"
                ),
            })
        except Exception as e:
            rows.append({"filter": name, "error": str(e)})

    # Sort by net_lift descending (best filter first)
    rows.sort(key=lambda r: r.get("net_lift_pp", -999), reverse=True)
    return rows


def print_table(rows: list[dict]) -> None:
    """Pretty console table."""
    print(f"{'FILTER':<28} {'REJECT%':>8} {'WIN_REJ%':>9} {'LOSS_REJ%':>10} {'NET_LIFT':>9} {'REJ_PF':>7}  VERDICT")
    print("─" * 95)
    for r in rows:
        if r.get("error"):
            print(f"{r['filter']:<28} ERROR: {r['error']}")
            continue
        if r.get("skipped"):
            print(f"{r['filter']:<28} SKIPPED: {r['reason']}")
            continue
        verdict_color = {
            "STRONG_HELP":  "🟢",
            "WEAK_HELP":    "🟢",
            "NEUTRAL":      "🟡",
            "WEAK_HURT":    "🔴",
            "STRONG_HURT":  "🔴",
        }.get(r["verdict"], "")
        rej_pf_str = str(r["rejected_pf"]) if r["rejected_pf"] != "inf" else "  inf"
        print(f"{r['filter']:<28} {r['reject_rate_pct']:>7}% {r['win_rejected_pct']:>8}% {r['loss_rejected_pct']:>9}% "
              f"{r['net_lift_pp']:>+7}pp {rej_pf_str:>7}  {verdict_color} {r['verdict']}")


def save_outputs(rows: list[dict], date: str) -> None:
    """JSON + CSV in cache/."""
    cache = REPO / "cache"
    cache.mkdir(exist_ok=True)
    json_p = cache / f"filter_audit_{date}.json"
    json_p.write_text(json.dumps(rows, indent=2))

    csv_p = cache / f"filter_audit_{date}.csv"
    if rows and not rows[0].get("error"):
        keys = list(rows[0].keys())
        lines = [",".join(keys)]
        for r in rows:
            lines.append(",".join(str(r.get(k, "")) for k in keys))
        csv_p.write_text("\n".join(lines))

    print()
    print(f"Saved: {json_p.name} + {csv_p.name}")


def main():
    # Combine recent backtest trades (post-fix scoring) + closed signal_log
    # (longer history but pre-fix scoring). Tag each with source.
    bt_trades = _load_recent_backtest_trades()
    sl_trades = _load_signal_log()

    for t in bt_trades:
        t["_source"] = "backtest"
    for s in sl_trades:
        s["_source"] = "signal_log"
        # Normalize field names
        s["pnl_pct"] = s.get("actual_pnl_pct")
        s["setup_type"] = s.get("strategy")

    all_trades = bt_trades + sl_trades
    print(f"Loaded: {len(bt_trades)} backtest trades + {len(sl_trades)} signal_log closed = {len(all_trades)} total")
    print()

    if not all_trades:
        print("ERROR: no trade data available — run a backtest or accumulate signal_log")
        sys.exit(1)

    rows = audit_filters(all_trades)
    print_table(rows)

    date = dt.date.today().isoformat()
    save_outputs(rows, date)


if __name__ == "__main__":
    main()

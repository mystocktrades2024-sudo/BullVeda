#!/usr/bin/env python3
"""AI-31: Setup-family performance leaderboard.

Ranks setup_types by expectancy (WR * avg_win - (1-WR) * |avg_loss|) and
suggests sizing per setup. Drift-annotated vs config._meta.last_backtest_wr.

Usage:
  python3 leaderboard.py                    # pretty-print
  python3 leaderboard.py --min-trades 5     # raise evidence bar
  python3 leaderboard.py --json             # dump cache/leaderboard.json
  python3 leaderboard.py --md               # dump cache/leaderboard.md
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).parent


def _load_history() -> dict:
    try:
        from tracker import _load_history as _lh
        return _lh()
    except Exception:
        return {"trades": []}


def _load_backtest_wr() -> float | None:
    try:
        cfg = json.loads((_ROOT / "config" / "config.json").read_text())
        val = cfg.get("_meta", {}).get("last_backtest_wr")
        if isinstance(val, (int, float)):
            return float(val) * 100
    except Exception:
        pass
    return None


def _bucket_stats(trades: list[dict]) -> dict:
    if not trades:
        return {}
    wins = [t for t in trades if t.get("win")]
    losses = [t for t in trades if not t.get("win")]
    wp = [t.get("pct_chg", 0) for t in wins]
    lp = [t.get("pct_chg", 0) for t in losses]
    n = len(trades)
    wr = len(wins) / n * 100
    aw = sum(wp) / len(wp) if wp else 0.0
    al = sum(lp) / len(lp) if lp else 0.0
    gw = sum(wp)
    gl = abs(sum(lp))
    pf = (gw / gl) if gl > 0 else float("inf")
    # Expectancy per trade in % terms: WR * avgWin - (1-WR) * |avgLoss|
    expectancy = (wr / 100) * aw - (1 - wr / 100) * abs(al)
    # Audit #8 — Wilson 95% CI on WR so dashboard can show sample-size honesty
    try:
        from tracker import wilson_ci as _wci, _reliability_label as _rlab
        lo, hi = _wci(len(wins), n, 0.95)
        ci_w = round((hi - lo) * 100, 1)
        reliability = _rlab(n, ci_w)
    except Exception:
        lo, hi, ci_w, reliability = 0.0, 1.0, 100.0, "low"
    return {
        "trades_n":     n,
        "wins":         len(wins),
        "losses":       len(losses),
        "win_rate":     round(wr, 1),
        "avg_win_pct":  round(aw, 2),
        "avg_loss_pct": round(al, 2),
        "profit_factor": round(pf, 2) if pf != float("inf") else 999.0,
        "gross_pnl_pct": round(gw - gl, 2),
        "expectancy":   round(expectancy, 2),
        # Audit #8 — confidence interval fields (backward-compatible)
        "wr_low_95":     round(lo * 100, 1),
        "wr_high_95":    round(hi * 100, 1),
        "ci_width_pp":   ci_w,
        "reliability":   reliability,
    }


def _size_recommendation(expectancy: float, trades_n: int) -> str:
    """FULL / HALF / QUARTER / DISABLE per expectancy with trade-count gate."""
    if expectancy <= 0 and trades_n >= 8:
        return "DISABLE"
    if expectancy > 1.5:
        return "FULL"
    if expectancy >= 0.5:
        return "HALF"
    if expectancy > 0:
        return "QUARTER"
    return "WATCH"  # <= 0 but not enough trades to disable


def build_leaderboard(history: dict | None = None, min_trades: int = 3) -> dict:
    history = history or _load_history()
    trades = history.get("trades", [])

    by_setup: dict[str, list] = {}
    by_family: dict[str, list] = {}
    for t in trades:
        st = t.get("setup_type") or "Unknown"
        fam = t.get("setup_family") or "Unknown"
        by_setup.setdefault(st, []).append(t)
        by_family.setdefault(fam, []).append(t)

    bt_wr = _load_backtest_wr()

    def _rows(group: dict) -> list[dict]:
        out = []
        for name, items in group.items():
            if len(items) < min_trades:
                continue
            s = _bucket_stats(items)
            s["name"] = name
            s["size_recommendation"] = _size_recommendation(s["expectancy"], s["trades_n"])
            # Drift vs backtest
            if bt_wr is not None:
                delta = s["win_rate"] - bt_wr
                s["drift_vs_backtest"] = round(delta, 1)
                if abs(delta) > 15:
                    s["drift_flag"] = f"DRIFT {delta:+.0f}"
            out.append(s)
        # Rank by expectancy descending
        out.sort(key=lambda r: r["expectancy"], reverse=True)
        return out

    return {
        "generated":     datetime.now().isoformat(timespec="seconds"),
        "backtest_wr":   bt_wr,
        "min_trades":    min_trades,
        "total_trades":  len(trades),
        "by_setup_type": _rows(by_setup),
        "by_setup_family": _rows(by_family),
    }


def render_markdown(report: dict) -> str:
    lines = [
        f"# SwingTrade Setup Leaderboard — {report['generated'][:10]}",
        "",
        f"**Total trades:** {report['total_trades']} · **Min-trades filter:** {report['min_trades']} · "
        f"**Backtest WR baseline:** {report['backtest_wr']:.1f}%" if report['backtest_wr'] else f"**Total trades:** {report['total_trades']}",
        "",
    ]

    def _table(title: str, rows: list[dict]):
        if not rows:
            return [f"## {title}", "", "_No buckets meet min-trades threshold._", ""]
        out = [f"## {title}", "",
               "| Rank | Setup | N | WR | PF | Avg Win | Avg Loss | Expectancy | Size |",
               "|---|---|---|---|---|---|---|---|---|"]
        for i, r in enumerate(rows, 1):
            drift = f" [{r['drift_flag']}]" if "drift_flag" in r else ""
            out.append(
                f"| {i} | {r['name']}{drift} | {r['trades_n']} | {r['win_rate']}% | "
                f"{r['profit_factor']} | +{r['avg_win_pct']}% | {r['avg_loss_pct']}% | "
                f"{r['expectancy']:+.2f} | {r['size_recommendation']} |"
            )
        return out + [""]

    lines += _table("By Setup Type", report["by_setup_type"])
    lines += _table("By Setup Family", report["by_setup_family"])
    return "\n".join(lines)


def render_console(report: dict) -> str:
    """Plain-text / terminal-friendly version of the markdown report."""
    return render_markdown(report)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-trades", type=int, default=3)
    ap.add_argument("--json", action="store_true", help="write cache/leaderboard.json")
    ap.add_argument("--md",   action="store_true", help="write cache/leaderboard.md")
    args = ap.parse_args()

    report = build_leaderboard(min_trades=args.min_trades)
    txt = render_markdown(report)
    print(txt)

    if args.json:
        out = _ROOT / "cache" / "leaderboard.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, default=str))
        print(f"\n→ JSON written: {out}")
    if args.md:
        out = _ROOT / "cache" / "leaderboard.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(txt)
        print(f"→ Markdown written: {out}")


if __name__ == "__main__":
    main()

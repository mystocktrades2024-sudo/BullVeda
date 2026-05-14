#!/usr/bin/env python3
"""sharpe_setup_trend.py — per-setup Sharpe over rolling time windows.

Tracks Sharpe-per-trade for each setup_family across consecutive time windows
(default: rolling 20-trade or 30-day windows). Plots the trend so you can spot
edge erosion BEFORE it shows up in aggregate stats.

CLAUDE.md principle 11: "Alpha decays. What worked 6 months ago may be
priced-in now." This is the early warning system.

Inputs:
  cache/picks_history.json (canonical trade outcomes)

Outputs:
  console table (per-setup × per-window stats)
  cache/sharpe_setup_trend_<DATE>.json
  cache/sharpe_setup_trend_<DATE>.html (simple line chart)

Usage:
  python3 scripts/sharpe_setup_trend.py                   # 20-trade windows
  python3 scripts/sharpe_setup_trend.py --window-trades 30
  python3 scripts/sharpe_setup_trend.py --window-days 30  # use calendar windows
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def _load_setup_trades() -> list[dict]:
    """Load trades sorted by entry_date, with setup_family + pnl_pct + win."""
    rows: list[dict] = []
    ph = REPO / "cache" / "picks_history.json"
    if not ph.exists():
        return rows
    d = json.loads(ph.read_text())
    for t in d.get("trades") or []:
        if t.get("pct_chg") is None:
            continue
        pnl = float(t["pct_chg"])
        if abs(pnl) > 100:
            continue
        rows.append({
            "ticker": t.get("ticker"),
            "setup_family": t.get("setup_family") or "unknown",
            "pnl_pct": pnl,
            "win": pnl > 0,
            "entry_date": t.get("entry_date"),
        })
    rows.sort(key=lambda r: r.get("entry_date") or "")
    return rows


def _trade_windows(trades: list[dict], window_size: int) -> list[list[dict]]:
    """Split trades into consecutive non-overlapping windows of fixed size."""
    out = []
    for i in range(0, len(trades), window_size):
        chunk = trades[i:i + window_size]
        if len(chunk) >= max(5, window_size // 4):  # keep partial trailing window if at least 1/4 full
            out.append(chunk)
    return out


def _date_windows(trades: list[dict], days: int) -> list[list[dict]]:
    """Split trades into consecutive calendar-day windows."""
    if not trades:
        return []
    by_date = sorted(trades, key=lambda r: r.get("entry_date") or "")
    first_d = datetime.fromisoformat(by_date[0]["entry_date"]).date()
    last_d = datetime.fromisoformat(by_date[-1]["entry_date"]).date()
    out: list[list[dict]] = []
    cur = first_d
    while cur <= last_d:
        end = cur + timedelta(days=days)
        win = [t for t in trades if cur.isoformat() <= (t.get("entry_date") or "") < end.isoformat()]
        if win:
            out.append(win)
        cur = end
    return out


def _stats(grp: list[dict]) -> dict:
    from lib.sharpe_utils import per_trade_sharpe, per_trade_sortino
    n = len(grp)
    if n == 0:
        return {"n": 0}
    pnls = [t["pnl_pct"] for t in grp]
    wins = sum(1 for t in grp if t["win"])
    sh, mean, std = per_trade_sharpe(pnls)
    so, dd = per_trade_sortino(pnls)
    win_pnls = [p for p in pnls if p > 0]
    loss_pnls = [p for p in pnls if p <= 0]
    pf_w = sum(win_pnls)
    pf_l = abs(sum(loss_pnls)) or 1
    return {
        "n": n,
        "wr": round(wins / n, 3),
        "avg_pnl": mean,
        "stdev": std,
        "sharpe_per_trade": sh,
        "sortino_per_trade": so,
        "pf": round(pf_w / pf_l, 3),
        "first_entry": grp[0].get("entry_date"),
        "last_entry": grp[-1].get("entry_date"),
    }


def _trend_verdict(sharpes: list[float | None]) -> str:
    """Classify the trend across windows: improving / stable / degrading."""
    valid = [s for s in sharpes if s is not None]
    if len(valid) < 2:
        return "insufficient"
    delta = valid[-1] - valid[0]
    # Rolling mean of last half vs first half
    half = len(valid) // 2
    if half == 0:
        return "insufficient"
    first_half_mean = sum(valid[:half]) / half
    last_half_mean = sum(valid[half:]) / (len(valid) - half)
    diff = last_half_mean - first_half_mean
    if diff > 0.15:
        return "improving"
    if diff < -0.15:
        return "DEGRADING"
    return "stable"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window-trades", type=int, default=20)
    ap.add_argument("--window-days", type=int, default=0,
                    help="If >0, use calendar-day windows instead of trade-count windows")
    ap.add_argument("--no-html", action="store_true")
    args = ap.parse_args()

    trades = _load_setup_trades()
    if not trades:
        print("ERROR: no trades in picks_history.json", file=sys.stderr)
        sys.exit(1)
    print(f"Loaded {len(trades)} closed trades  ({trades[0].get('entry_date')} → {trades[-1].get('entry_date')})")
    print()

    # Group by setup_family
    by_setup: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        by_setup[t["setup_family"]].append(t)

    # Per-setup × per-window stats
    out_per_setup: dict[str, dict] = {}
    for setup, items in sorted(by_setup.items(), key=lambda kv: -len(kv[1])):
        if len(items) < 10:
            continue
        if args.window_days > 0:
            windows = _date_windows(items, args.window_days)
            window_label = f"{args.window_days}d-window"
        else:
            windows = _trade_windows(items, args.window_trades)
            window_label = f"{args.window_trades}-trade-window"
        if len(windows) < 2:
            continue
        win_stats = [_stats(w) for w in windows]
        sharpes = [s.get("sharpe_per_trade") for s in win_stats]
        verdict = _trend_verdict(sharpes)
        out_per_setup[setup] = {
            "n_total": len(items),
            "n_windows": len(windows),
            "verdict": verdict,
            "windows": win_stats,
        }
        print(f"━━━ {setup}  ({len(items)} trades, {len(windows)} {window_label}) — VERDICT: {verdict}")
        print(f"  {'#':>3} {'PERIOD':<23} {'n':>4} {'WR':>6} {'avg':>7} {'σ':>6} {'Sh/t':>6} {'So/t':>6} {'PF':>5}")
        for i, s in enumerate(win_stats, 1):
            sh = s.get("sharpe_per_trade")
            so = s.get("sortino_per_trade")
            sh_str = f"{sh:+.2f}" if sh is not None else "  —"
            so_str = f"{so:+.2f}" if so is not None else "  —"
            period = f"{s.get('first_entry','?')}→{s.get('last_entry','?')}"[:23]
            print(f"  {i:>3} {period:<23} {s['n']:>4} {s['wr']*100:>5.1f}% "
                  f"{s.get('avg_pnl', 0):>+6.2f}% {s.get('stdev', 0):>5.2f} {sh_str:>6} {so_str:>6} {s['pf']:>5.2f}")
        print()

    # Persist JSON
    out = {
        "generated_at": date.today().isoformat(),
        "n_trades_total": len(trades),
        "window_label": (f"{args.window_days}d" if args.window_days else f"{args.window_trades}t"),
        "per_setup": out_per_setup,
    }
    out_p = REPO / "cache" / f"sharpe_setup_trend_{date.today().isoformat()}.json"
    out_p.write_text(json.dumps(out, indent=2, default=str))
    print(f"Saved: {out_p}")

    # HTML trend viz
    if not args.no_html:
        html_p = REPO / "cache" / f"sharpe_setup_trend_{date.today().isoformat()}.html"
        _emit_html(out_per_setup, html_p)
        print(f"Saved: {html_p}")


def _emit_html(per_setup: dict, path: Path) -> None:
    """Tiny self-contained HTML with one SVG line per setup family."""
    series_blocks = []
    for setup, data in per_setup.items():
        sharpes = [s.get("sharpe_per_trade") or 0 for s in data["windows"]]
        wins = [s.get("wr", 0) * 100 for s in data["windows"]]
        n_each = [s.get("n", 0) for s in data["windows"]]
        verdict = data["verdict"]
        v_color = {"improving": "#3fb950", "stable": "#79c0ff",
                   "DEGRADING": "#f85149", "insufficient": "#7d8590"}.get(verdict, "#7d8590")
        # Build SVG
        w, h = 600, 100
        if not sharpes:
            continue
        smin = min(sharpes + [0])
        smax = max(sharpes + [0.5])
        srange = max(smax - smin, 0.5)
        pts = []
        for i, s in enumerate(sharpes):
            x = 30 + (i / max(1, len(sharpes) - 1)) * (w - 60)
            y = h - 20 - ((s - smin) / srange) * (h - 40)
            pts.append(f"{x:.0f},{y:.0f}")
        # Zero baseline
        zero_y = h - 20 - ((0 - smin) / srange) * (h - 40)
        svg = (
            f"<svg width='{w}' height='{h}' style='background:#0d1117'>"
            f"<line x1='30' y1='{zero_y:.0f}' x2='{w-30}' y2='{zero_y:.0f}' stroke='#30363d' stroke-dasharray='2,2'/>"
            f"<polyline fill='none' stroke='{v_color}' stroke-width='2' points='{' '.join(pts)}'/>"
            + "".join(f"<circle cx='{p.split(',')[0]}' cy='{p.split(',')[1]}' r='3' fill='{v_color}'/>" for p in pts)
            + f"<text x='5' y='15' fill='#7d8590' font-size='11' font-family='monospace'>{smax:.2f}</text>"
            + f"<text x='5' y='{h-5}' fill='#7d8590' font-size='11' font-family='monospace'>{smin:.2f}</text>"
            + "</svg>"
        )
        n_label = f"({sum(n_each)} trades, {len(sharpes)} windows)"
        series_blocks.append(
            f"<div class='setup-card'>"
            f"<div class='setup-head'><span class='setup-name'>{setup}</span>"
            f"<span class='verdict' style='color:{v_color}'>{verdict.upper()}</span></div>"
            f"<div class='setup-meta'>{n_label}</div>"
            f"{svg}"
            f"</div>"
        )

    html = f"""<!DOCTYPE html>
<html><head><meta charset='utf-8'><title>Sharpe-per-Setup Trend (Edge Erosion Radar)</title>
<style>
  body {{ background:#0d1117; color:#c9d1d9; font-family:-apple-system,BlinkMacSystemFont,'SF Pro',sans-serif;
         margin:0; padding:24px; }}
  h1 {{ margin:0 0 24px 0; font-size:22px; font-weight:600; color:#f0f6fc; }}
  .subtitle {{ color:#7d8590; margin-bottom:24px; }}
  .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
  .setup-card {{ background:#161b22; border:1px solid #30363d; border-radius:8px; padding:16px; }}
  .setup-head {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:4px; }}
  .setup-name {{ font-weight:600; font-size:14px; color:#f0f6fc; }}
  .verdict {{ font-size:11px; font-weight:600; letter-spacing:0.5px; }}
  .setup-meta {{ font-size:12px; color:#7d8590; margin-bottom:12px; }}
</style>
</head><body>
<h1>Sharpe-per-Setup Trend &mdash; Edge Erosion Radar</h1>
<div class='subtitle'>Each line: Sharpe-per-trade across consecutive windows. Stable line = robust edge. Falling line = erosion.</div>
<div class='grid'>
{''.join(series_blocks)}
</div>
</body></html>
"""
    path.write_text(html)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""AI-17: Live-vs-backtest drift alerter.

Compares live win-rate (from tracker history) against backtested WR
(config._meta.last_backtest_wr). Reports overall + per-setup deltas.
Designed to run weekly via launchd/cron; prints a summary and writes
cache/drift_report.json. If drift > threshold, also flags to stdout
with a clear WARN banner so email/cron wrappers can surface it.

Usage:
  python3 drift_check.py                # just summarize
  python3 drift_check.py --slack        # also POST to SLACK_WEBHOOK_URL
  python3 drift_check.py --min-trades 20 --drift-threshold 15

---------------------------------------------------------------------------
Phase 4 backtest (pending rerun) will populate the following keys under
`config._meta`, consumed by this script:
  * _meta.last_backtest_wr   — e.g. 0.50  (50% WR target)
  * _meta.target_wr          — e.g. 0.50  (industry-standard swing baseline)
  * _meta.target_rr          — e.g. 2.5   (industry-standard R:R baseline)
  * _meta.target_trades_per_month — optional dict {"min": 10, "max": 20}
Until Phase 4 writes those, this script falls back to the documented
industry-standard defaults (target_wr=0.50, target_rr=2.5, 10-20 tpm).
---------------------------------------------------------------------------
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).parent


def _load_backtest_wr() -> float | None:
    try:
        cfg = json.loads((_ROOT / "config" / "config.json").read_text())
        val = cfg.get("_meta", {}).get("last_backtest_wr")
        if isinstance(val, (int, float)):
            return float(val) * 100
    except Exception:
        pass
    return None


def _load_targets() -> dict:
    """Load industry-standard targets from config._meta, with safe defaults.

    Defaults (documented industry-standard for swing trading):
      * target_wr  = 0.50  (50% win rate baseline)
      * target_rr  = 2.5   (reward:risk)
      * target_trades_per_month = {min: 10, max: 20}
    """
    targets = {
        "target_wr": 0.50,
        "target_rr": 2.5,
        "target_trades_per_month": {"min": 10, "max": 20},
    }
    try:
        cfg = json.loads((_ROOT / "config" / "config.json").read_text())
        meta = cfg.get("_meta", {}) or {}
        if isinstance(meta.get("target_wr"), (int, float)):
            targets["target_wr"] = float(meta["target_wr"])
        if isinstance(meta.get("target_rr"), (int, float)):
            targets["target_rr"] = float(meta["target_rr"])
        tpm = meta.get("target_trades_per_month")
        if isinstance(tpm, dict) and "min" in tpm and "max" in tpm:
            targets["target_trades_per_month"] = {
                "min": int(tpm["min"]), "max": int(tpm["max"]),
            }
    except Exception:
        pass
    return targets


def _estimate_trades_per_month(stats: dict) -> float | None:
    """Derive average trades/month from tracker history window, if available."""
    try:
        from tracker import _load_history
        h = _load_history()
        trades = h.get("trades", [])
        if not trades:
            return None
        # Pull entry/exit/evaluated_at timestamps — any date-ish field.
        from datetime import datetime as _dt
        dates = []
        for t in trades:
            for k in ("evaluated_at", "exit_date", "entry_date", "date"):
                v = t.get(k)
                if not v:
                    continue
                try:
                    dates.append(_dt.fromisoformat(str(v)[:10]))
                    break
                except Exception:
                    continue
        if len(dates) < 2:
            return None
        dates.sort()
        span_days = max(1.0, (dates[-1] - dates[0]).days)
        months = span_days / 30.4375
        return round(len(dates) / months, 2) if months > 0 else None
    except Exception:
        return None


def _compute_compliance(stats: dict, bt_wr: float | None, targets: dict,
                       live_rr: float | None, tpm: float | None) -> dict:
    """Industry-standard compliance check.

    Pass/fail rules:
      * WR  : live WR >= target_wr * 90 (i.e. within 10% of target)
      * R:R : live (or backtest) realized R:R >= target_rr
      * Vol : trades/month within [min, max] inclusive
    """
    tgt_wr_pct = targets["target_wr"] * 100
    tgt_rr     = targets["target_rr"]
    tpm_range  = targets["target_trades_per_month"]

    live_wr = stats.get("win_rate") if stats.get("sufficient_data") else None

    checks = {}

    # WR check
    if live_wr is not None:
        wr_floor = tgt_wr_pct * 0.9
        checks["wr"] = {
            "pass": live_wr >= wr_floor,
            "actual": round(live_wr, 1),
            "target": round(tgt_wr_pct, 1),
            "floor": round(wr_floor, 1),
            "note": f"{live_wr:.1f}% vs target {tgt_wr_pct:.0f}% (floor {wr_floor:.0f}%)",
        }
    else:
        checks["wr"] = {"pass": None, "note": "insufficient data"}

    # R:R check
    if live_rr is not None:
        checks["rr"] = {
            "pass": live_rr >= tgt_rr,
            "actual": round(live_rr, 2),
            "target": tgt_rr,
            "note": f"{live_rr:.2f} vs target {tgt_rr}",
        }
    else:
        checks["rr"] = {"pass": None, "note": "realized R:R unknown"}

    # Volume check
    if tpm is not None:
        lo, hi = tpm_range["min"], tpm_range["max"]
        checks["volume"] = {
            "pass": lo <= tpm <= hi,
            "actual": tpm,
            "target_min": lo,
            "target_max": hi,
            "note": f"{tpm:.1f} trades/mo vs target {lo}-{hi}",
        }
    else:
        checks["volume"] = {"pass": None, "note": "trades/month unknown"}

    return checks


def _compliance_summary_line(checks: dict) -> str:
    """Render 'Compliance: WR ✓ | R:R ✗ (1.8 < 2.5) | Volume ✓'."""
    parts = []
    name_map = {"wr": "WR", "rr": "R:R", "volume": "Volume"}
    for key in ("wr", "rr", "volume"):
        c = checks.get(key, {})
        label = name_map[key]
        if c.get("pass") is True:
            parts.append(f"{label} ✓")
        elif c.get("pass") is False:
            if key == "wr":
                parts.append(f"{label} ✗ ({c.get('actual')}% < {c.get('floor')}%)")
            elif key == "rr":
                parts.append(f"{label} ✗ ({c.get('actual')} < {c.get('target')})")
            elif key == "volume":
                parts.append(f"{label} ✗ ({c.get('actual')} not in "
                             f"{c.get('target_min')}-{c.get('target_max')})")
        else:
            parts.append(f"{label} ?")
    return "Compliance: " + " | ".join(parts)


def _compute_live_stats(min_trades: int):
    try:
        from tracker import compute_stats
        return compute_stats(min_trades=min_trades)
    except Exception as e:
        return {"error": str(e), "sufficient_data": False}


def _per_setup_stats() -> dict:
    """Bucket history by setup_type."""
    try:
        from tracker import _load_history
        h = _load_history()
        trades = h.get("trades", [])
    except Exception:
        return {}
    buckets: dict[str, list] = {}
    for t in trades:
        st = t.get("setup_type") or "Unknown"
        buckets.setdefault(st, []).append(t)
    out = {}
    for st, items in buckets.items():
        if len(items) < 3:
            continue
        wins = sum(1 for t in items if t.get("win"))
        n = len(items)
        try:
            from tracker import wilson_ci as _wci
            lo, hi = _wci(wins, n, 0.95)
            ci_lo_pct = round(lo * 100, 1)
            ci_hi_pct = round(hi * 100, 1)
            ci_width = round((hi - lo) * 100, 1)
        except Exception:
            ci_lo_pct, ci_hi_pct, ci_width = 0.0, 100.0, 100.0
        out[st] = {
            "trades": n,
            "wins": wins,
            "win_rate": round(wins / n * 100, 1),
            # Audit #8 — Wilson CI fields
            "wr_low_95":  ci_lo_pct,
            "wr_high_95": ci_hi_pct,
            "ci_width_pp": ci_width,
        }
    return out


def _post_slack(msg: str) -> None:
    """Post a message to Slack webhook if SLACK_WEBHOOK_URL is set."""
    try:
        from secrets_loader import get_secret
        url = get_secret("SLACK_WEBHOOK_URL", default="")
    except Exception:
        url = os.environ.get("SLACK_WEBHOOK_URL", "")
    if not url:
        print("[slack] SLACK_WEBHOOK_URL not set — skipping")
        return
    try:
        import urllib.request
        data = json.dumps({"text": msg}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
        print("[slack] posted")
    except Exception as e:
        print(f"[slack] error: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-trades", type=int, default=10,
                    help="Minimum trades before reporting (default 10)")
    ap.add_argument("--drift-threshold", type=float, default=15.0,
                    help="WR drift pts (positive abs) to trigger WARN (default 15)")
    ap.add_argument("--min-alert-n", type=int, default=30,
                    help="Audit #8: per-setup min trades before drift alert (default 30)")
    ap.add_argument("--slack", action="store_true", help="Post to Slack on WARN")
    args = ap.parse_args()

    bt_wr = _load_backtest_wr()
    stats = _compute_live_stats(args.min_trades)
    per_setup = _per_setup_stats()
    targets = _load_targets()

    # Realized R:R from avg_win / |avg_loss| if both present
    live_rr = None
    try:
        aw = stats.get("avg_win")
        al = stats.get("avg_loss")
        if isinstance(aw, (int, float)) and isinstance(al, (int, float)) and al:
            live_rr = round(aw / abs(al), 2)
    except Exception:
        live_rr = None

    tpm = _estimate_trades_per_month(stats)
    compliance = _compute_compliance(stats, bt_wr, targets, live_rr, tpm)

    report = {
        "as_of": datetime.now().isoformat(timespec="seconds"),
        "backtest_wr": bt_wr,
        "target_wr": targets["target_wr"],
        "target_rr": targets["target_rr"],
        "target_trades_per_month": targets["target_trades_per_month"],
        "live_realized_rr": live_rr,
        "live_trades_per_month": tpm,
        "compliance": compliance,
        "live": stats,
        "by_setup": per_setup,
        "alerts": [],
    }

    print("=" * 72)
    print("SwingTrade Drift Check")
    print("=" * 72)
    print(f"Backtest WR baseline: {bt_wr:.1f}%" if bt_wr is not None else "Backtest WR: unknown (config._meta.last_backtest_wr missing)")

    if not stats.get("sufficient_data"):
        msg = f"Insufficient trade data — need {args.min_trades}+ (have {stats.get('total_trades', 0)})"
        print(msg)
        report["alerts"].append({"level": "INFO", "msg": msg})
    else:
        live_wr = stats.get("win_rate", 0)
        print(f"Live WR ({stats.get('total_trades')} trades): {live_wr:.1f}%")
        if bt_wr is not None:
            delta = live_wr - bt_wr
            abs_delta = abs(delta)
            level = "OK" if abs_delta <= 5 else ("WATCH" if abs_delta <= args.drift_threshold else "WARN")
            marker = "✓" if level == "OK" else ("!" if level == "WATCH" else "🔴")
            msg = f"{marker} Delta vs backtest: {delta:+.1f} pts [{level}]"
            print(msg)
            if level == "WARN":
                report["alerts"].append({"level": "WARN", "msg": msg, "delta": delta})

        # per-direction
        bd = stats.get("by_direction", {})
        if bd:
            print("\nBy direction:")
            for direction in ("long", "short"):
                d = bd.get(direction, {})
                if d.get("trades", 0) >= 3:
                    print(f"  {direction:5s}: {d.get('trades', 0)} trades · WR {d.get('win_rate', 0):.1f}% · PF {d.get('profit_factor', 0):.2f}")

        if per_setup:
            print("\nBy setup (min 3 trades):")
            for st, s in sorted(per_setup.items(), key=lambda kv: -kv[1]["trades"]):
                marker = ""
                ci_note = f" [CI {s.get('wr_low_95', 0):.0f}-{s.get('wr_high_95', 0):.0f}%]"
                if bt_wr is not None:
                    d = s["win_rate"] - bt_wr
                    n = s["trades"]
                    # Audit #8: only alert when sample size is meaningful AND
                    # backtest WR falls outside the live Wilson CI (i.e. the
                    # delta exceeds statistical noise).
                    outside_ci = not (s.get("wr_low_95", 0) <= bt_wr <= s.get("wr_high_95", 100))
                    if abs(d) > args.drift_threshold and n >= args.min_alert_n and outside_ci:
                        marker = f" ← DRIFT {d:+.0f}"
                        report["alerts"].append({
                            "level": "WARN", "setup": st,
                            "msg": f"{st} drifted {d:+.0f} pts (n={n}, CI {s.get('wr_low_95',0):.0f}-{s.get('wr_high_95',0):.0f}%)",
                            "delta": d, "n": n,
                            "wr_low_95": s.get("wr_low_95"), "wr_high_95": s.get("wr_high_95"),
                        })
                    elif abs(d) > args.drift_threshold:
                        # Drift present but below statistical confidence — note, don't alert
                        reason = "n<min" if n < args.min_alert_n else "within CI"
                        marker = f" ← drift {d:+.0f} (muted: {reason})"
                print(f"  {st:24s}: {s['trades']:3d} trades · WR {s['win_rate']:.1f}%{ci_note}{marker}")

    # Industry-Standard Compliance section
    print("\n" + "-" * 72)
    print("Industry-Standard Compliance")
    print("-" * 72)
    print(f"  target_wr:  {targets['target_wr']*100:.0f}% "
          f"(floor {targets['target_wr']*100*0.9:.0f}%)")
    print(f"  target_rr:  {targets['target_rr']}")
    tpm_r = targets["target_trades_per_month"]
    print(f"  target_trades_per_month: {tpm_r['min']}-{tpm_r['max']}")
    for key in ("wr", "rr", "volume"):
        c = compliance.get(key, {})
        status = "✓" if c.get("pass") is True else ("✗" if c.get("pass") is False else "?")
        print(f"    {key:6s} [{status}] {c.get('note', '')}")
    summary = _compliance_summary_line(compliance)
    print(summary)

    # Record compliance failures as WATCH-level alerts (not WARN, to avoid
    # pager storms until Phase 4 populates firm targets).
    for key, c in compliance.items():
        if c.get("pass") is False:
            report["alerts"].append({
                "level": "WATCH",
                "msg": f"Compliance fail — {key}: {c.get('note')}",
                "check": key,
            })

    # Persist report
    out_path = _ROOT / "cache" / "drift_report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, default=str))
    print(f"\nReport written to {out_path}")

    # Slack notification for WARN-level alerts
    warn_alerts = [a for a in report["alerts"] if a["level"] == "WARN"]
    if warn_alerts and args.slack:
        lines = ["*SwingTrade drift alert*"] + [f"• {a['msg']}" for a in warn_alerts]
        _post_slack("\n".join(lines))

    return 1 if warn_alerts else 0


if __name__ == "__main__":
    sys.exit(main())

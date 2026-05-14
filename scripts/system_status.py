#!/usr/bin/env python3
"""system_status.py — comprehensive system status report.

Reports current state to stdout (CLI) and Slack:
  - Active sleeves
  - Last scan summary (timestamp, regime, BUY/WATCH/SHORT counts)
  - Rolling Sharpe kill state
  - Portfolio open positions
  - Recent errors from scan logs
  - Autorun launchd agent status

Usage:
  python3 scripts/system_status.py              # Print + post to Slack
  python3 scripts/system_status.py --no-slack   # Print only
  python3 scripts/system_status.py --quiet      # Slack only, no console
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def _load_bundle() -> dict:
    p = REPO / "cache" / "last_bundle.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def _load_config() -> dict:
    return json.loads((REPO / "config" / "config.json").read_text())


def _check_launchd_agents() -> dict:
    """Check which launchd agents are loaded + their last exit codes."""
    out: dict = {}
    agents = [
        "com.swingtrade.morning-briefing",
        "com.swingtrade.weekly-diagnostics",
        "com.swingtrade.tunnel-healthcheck",
        "com.swingtrade.server",
        "com.swingtrade.ticker-snapshots",
        "com.swingtrade.enrich-nightly",
        "com.swingtrade.prewarm",
    ]
    try:
        proc = subprocess.run(["launchctl", "list"], capture_output=True, text=True, timeout=10)
        loaded = proc.stdout
        for ag in agents:
            if ag not in loaded:
                out[ag] = {"loaded": False}
                continue
            # parse line "PID Status Label"
            for line in loaded.split("\n"):
                if ag in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        pid = parts[0]
                        status = parts[1]
                        out[ag] = {
                            "loaded": True,
                            "pid": pid if pid != "-" else None,
                            "last_exit_status": int(status) if status.lstrip("-").isdigit() else status,
                        }
                    break
    except Exception as e:
        out["_error"] = str(e)
    return out


def _rolling_sharpe_state() -> dict:
    try:
        from decision_engine import compute_rolling_sharpe_kill_state
        cfg = _load_config()
        return compute_rolling_sharpe_kill_state(cfg)
    except Exception as e:
        return {"error": str(e)}


def _portfolio_state() -> dict:
    p = REPO / "data" / "portfolio_state.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def _recent_scan_errors(n_lines: int = 200) -> list[str]:
    """Tail the most recent scan log for error/warning lines."""
    log_dir = REPO / "cache" / "logs"
    if not log_dir.exists():
        return []
    logs = sorted(log_dir.glob("scan_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not logs:
        return []
    try:
        tail = subprocess.run(["tail", "-n", str(n_lines), str(logs[0])],
                              capture_output=True, text=True, timeout=10)
        errors = []
        for line in tail.stdout.split("\n"):
            if any(x in line for x in ["ERROR", "CRITICAL", "Traceback", "❌", "FAILED"]):
                errors.append(line[:200])
        return errors[-5:]  # last 5 errors only
    except Exception:
        return []


def _sleeve_states(cfg: dict) -> dict:
    sleeves = {}
    for k in ["momentum_sleeve", "defensive_rotation_sleeve", "mean_reversion_sleeve",
              "pead_sleeve", "insider_cluster_sleeve", "esp_play_sleeve",
              "prefomc_drift_overlay"]:
        block = cfg.get(k, {})
        sleeves[k.replace("_sleeve", "").replace("_overlay", "")] = bool(block.get("_enabled"))
    return sleeves


def _build_report() -> dict:
    cfg = _load_config()
    bundle = _load_bundle()
    rs = _rolling_sharpe_state()
    pf = _portfolio_state()
    agents = _check_launchd_agents()
    errors = _recent_scan_errors()
    sleeves = _sleeve_states(cfg)

    regime = bundle.get("regime", {})
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "last_scan": {
            "timestamp": bundle.get("run_timestamp"),
            "regime": regime.get("regime"),
            "regime4": regime.get("regime4"),
            "spy_price": regime.get("spy_price"),
            "vix": regime.get("vix_current"),
            "buy_count": len(bundle.get("buy_candidates") or []),
            "watch_count": len(bundle.get("watch_list") or []),
            "short_count": len(bundle.get("near_short_blocked") or []),
        },
        "sleeves_enabled": sleeves,
        "rolling_sharpe": rs,
        "portfolio": {
            "open_positions": len(pf.get("positions") or []),
            "equity": pf.get("equity") or pf.get("cash"),
            "active_paper": pf.get("active") if pf else None,
        },
        "launchd_agents": agents,
        "recent_errors": errors,
    }


def _format_slack(report: dict) -> tuple[str, list]:
    """Return (plain_text, blocks) for Slack."""
    last = report["last_scan"]
    rs = report["rolling_sharpe"]
    pf = report["portfolio"]
    sleeves = report["sleeves_enabled"]
    agents = report["launchd_agents"]
    errors = report["recent_errors"]

    plain = (f"🟢 SwingTrade status — last scan {last.get('timestamp')} | "
             f"regime={last.get('regime4')} | BUY={last.get('buy_count')} "
             f"WATCH={last.get('watch_count')}")

    # Build blocks
    blocks = []
    blocks.append({
        "type": "header",
        "text": {"type": "plain_text", "text": "📊 SwingTrade System Status"}
    })
    # Last scan
    rs_active = rs.get("active") if isinstance(rs, dict) else False
    rs_emoji = "🔴" if rs_active else "🟢"
    sleeves_on = sum(1 for v in sleeves.values() if v)
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": (
                f"*Last scan*: `{last.get('timestamp', 'n/a')}`\n"
                f"*Regime*: `{last.get('regime4', 'unknown')}` "
                f"(SPY `${last.get('spy_price', '?')}`, VIX `{last.get('vix', '?')}`)\n"
                f"*Signals*: BUY *{last.get('buy_count', 0)}* · "
                f"WATCH *{last.get('watch_count', 0)}* · "
                f"SHORT-blocked *{last.get('short_count', 0)}*\n"
                f"*Rolling Sharpe kill*: {rs_emoji} active={rs_active} "
                f"(sharpe `{rs.get('sharpe', 'n/a')}` vs threshold `{rs.get('threshold', 'n/a')}`)\n"
                f"*Open positions*: *{pf.get('open_positions', 0)}* "
                f"(equity `${pf.get('equity', 'n/a')}`)\n"
                f"*Sleeves enabled*: {sleeves_on}/{len(sleeves)} "
                f"({', '.join(k for k, v in sleeves.items() if v)})"
            )
        }
    })
    # Launchd agents
    agents_text_lines = []
    for ag, info in agents.items():
        if ag.startswith("_"):
            continue
        if not isinstance(info, dict):
            continue
        if info.get("loaded"):
            ec = info.get("last_exit_status", 0)
            emo = "🟢" if ec == 0 else "🟡" if isinstance(ec, int) and ec != 0 else "🔴"
            short = ag.replace("com.swingtrade.", "")
            agents_text_lines.append(f"{emo} `{short}` (last_exit={ec})")
        else:
            short = ag.replace("com.swingtrade.", "")
            agents_text_lines.append(f"⚪ `{short}` not loaded")
    if agents_text_lines:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Launchd agents:*\n" + "\n".join(agents_text_lines)
            }
        })
    # Errors
    if errors:
        err_text = "\n".join(f"• `{e[:150]}`" for e in errors[-3:])
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"⚠️ *Recent scan errors:*\n{err_text}"}
        })
    # Footer / clickable links
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": (
                "<https://trade.mystockholding.com/v2/dashboard.html|🔗 Live Dashboard> · "
                "<https://trade.mystockholding.com/reports|📚 Report Archive> · "
                "<https://trade.mystockholding.com/reports/latest/dashboard|🗂️ Latest Dashboard Snapshot> · "
                "<https://trade.mystockholding.com/reports/latest/morning-briefing|🌅 Morning Briefing>"
            )
        }
    })
    return plain, blocks


def _post_slack(plain: str, blocks: list) -> bool:
    try:
        from secrets_loader import get_secret as _gs
        webhook = _gs("SLACK_WEBHOOK_URL", default="")
    except Exception:
        webhook = ""
    if not webhook:
        return False
    from alerts import _slack_post
    return _slack_post(webhook, plain, blocks)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-slack", action="store_true", help="Don't post to Slack")
    ap.add_argument("--quiet", action="store_true", help="Slack only, no console")
    ap.add_argument("--json", action="store_true", help="Output raw JSON")
    args = ap.parse_args()

    report = _build_report()

    if args.json:
        print(json.dumps(report, indent=2, default=str))
        return

    if not args.quiet:
        last = report["last_scan"]
        rs = report["rolling_sharpe"]
        pf = report["portfolio"]
        sleeves = report["sleeves_enabled"]
        agents = report["launchd_agents"]
        print("=" * 70)
        print("📊 SwingTrade System Status")
        print("=" * 70)
        print(f"Generated:        {report['generated_at']}")
        print()
        print("LAST SCAN")
        print(f"  Timestamp:      {last.get('timestamp', 'n/a')}")
        print(f"  Regime:         {last.get('regime4', 'unknown')} (SPY ${last.get('spy_price', '?')}, VIX {last.get('vix', '?')})")
        print(f"  Counts:         BUY={last.get('buy_count', 0)} WATCH={last.get('watch_count', 0)} SHORT-blocked={last.get('short_count', 0)}")
        print()
        print("ROLLING SHARPE KILL")
        rs_active = rs.get("active") if isinstance(rs, dict) else False
        print(f"  Active:         {'🔴 YES — BUYs halted' if rs_active else '🟢 NO'}")
        print(f"  Sharpe:         {rs.get('sharpe', 'n/a')} vs threshold {rs.get('threshold', 'n/a')}")
        if rs.get("reason"):
            print(f"  Reason:         {rs.get('reason')}")
        print()
        print("SLEEVES")
        for k, v in sleeves.items():
            print(f"  {k:30s} {'✓ enabled' if v else '✗ disabled'}")
        print()
        print("PORTFOLIO")
        print(f"  Open positions: {pf.get('open_positions', 0)}")
        print(f"  Equity:         ${pf.get('equity', 'n/a')}")
        print()
        print("LAUNCHD AGENTS")
        for ag, info in agents.items():
            if ag.startswith("_") or not isinstance(info, dict):
                continue
            short = ag.replace("com.swingtrade.", "")
            if info.get("loaded"):
                ec = info.get("last_exit_status", 0)
                emo = "🟢" if ec == 0 else "🟡"
                print(f"  {emo} {short:30s} last_exit={ec}")
            else:
                print(f"  ⚪ {short:30s} not loaded")
        if report["recent_errors"]:
            print()
            print("⚠️ RECENT ERRORS (last 5 from current day's scan)")
            for e in report["recent_errors"]:
                print(f"  • {e[:160]}")
        print()
        print(f"Dashboard: https://trade.mystockholding.com")
        print(f"            http://localhost:7432/v2/")

    if not args.no_slack:
        plain, blocks = _format_slack(report)
        ok = _post_slack(plain, blocks)
        if not args.quiet:
            print()
            print(f"Slack post: {'✓ sent' if ok else '✗ failed (check SLACK_WEBHOOK_URL)'}")


if __name__ == "__main__":
    main()

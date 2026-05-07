"""
engine_health_check.py — Verify decision_engine ran successfully on latest scan.

Exit code 0 if healthy, 1 if any check fails. Sends Mac notification on failure
so even unattended cron runs alert the user.

Checks performed:
  1. cache/last_bundle.json has decision_engine_version field (engine touched it)
  2. Bundle has no decision_engine_failed flag
  3. Latest scan log contains "Decision engine: scored N tickers" line with N > 0
  4. Bundle's buy_candidates all have verdict == BUY (no stale rows)
  5. Sample ticker has gates_evaluated array populated (engine output present)
  6. Bundle reflects current circuit-breaker state — if breaker active and
     buy_candidates non-empty, that's a gating failure

Usage:
    python3 engine_health_check.py            # human-readable output
    python3 engine_health_check.py --quiet    # silent on success, alert on fail
    python3 engine_health_check.py --no-notify # skip Mac notification

Cron example (run 30min after scheduled scan):
    30 7 * * 1-5 cd "/path/to/SwingTrade" && python3 engine_health_check.py --quiet
"""
from __future__ import annotations
import argparse
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent
BUNDLE = ROOT / "cache" / "last_bundle.json"
LOG_DIR = ROOT / "cache" / "logs"


def _mac_notify(title: str, message: str, subtitle: str = "") -> None:
    try:
        sub = f'subtitle "{subtitle}"' if subtitle else ""
        script = f'display notification "{message}" with title "{title}" {sub}'
        subprocess.run(["osascript", "-e", script], timeout=5, capture_output=True)
    except Exception:
        pass


def _alert(level: str, title: str, body: str) -> None:
    """Try Slack via alerts.send_alert (also fires Mac notify); fall back to bare Mac."""
    try:
        sys.path.insert(0, str(ROOT))
        from alerts import send_alert
        send_alert(level=level, title=title, body=body)
    except Exception:
        _mac_notify(title=f"🚨 {title}", message=body[:200])


def _scan_in_progress() -> bool:
    """True if a swing_trade.py scan is currently running.
    Health check should not flag missing engine line during in-progress scans.
    """
    try:
        out = subprocess.run(["pgrep", "-f", "swing_trade.py"], capture_output=True, text=True, timeout=3)
        return bool(out.stdout.strip())
    except Exception:
        return False


def check_health(notify: bool = True) -> tuple[bool, list[str]]:
    """Returns (healthy, list_of_failures)."""
    failures: list[str] = []

    # If scan is currently running, defer the engine-line check — it'll fire
    # only at scan completion, not during enrichment/scoring (which can take 15+ min).
    in_progress = _scan_in_progress()

    # 1+2: bundle exists and has engine version
    if not BUNDLE.exists():
        failures.append("cache/last_bundle.json missing — scan never completed")
        return False, failures
    try:
        b = json.loads(BUNDLE.read_text())
    except Exception as e:
        failures.append(f"bundle JSON unreadable: {e}")
        return False, failures
    if "decision_engine_version" not in b:
        failures.append("bundle missing decision_engine_version — engine never ran on latest scan")
    if b.get("decision_engine_failed"):
        de = b["decision_engine_failed"]
        failures.append(f"bundle flagged engine failure: {de.get('type')}: {de.get('error')}")

    # 3: latest scan log contains the engine line with N > 0 — skip if scan still running
    logs = sorted(LOG_DIR.glob("scan_*.log"), key=lambda p: p.stat().st_mtime, reverse=True) if LOG_DIR.exists() else []
    if not logs:
        failures.append("no scan logs found — system may not be running")
    elif not in_progress:
        latest = logs[0]
        text = latest.read_text(errors="ignore")
        m = re.search(r"Decision engine: scored (\d+) tickers", text)
        if not m:
            failures.append(f"latest log {latest.name} has no 'Decision engine:' line")
        elif int(m.group(1)) == 0:
            failures.append(f"latest scan: engine scored 0 tickers (silent failure)")

    # 4: buy_candidates all have verdict==BUY
    bc = b.get("buy_candidates") or []
    bad_buys = [r.get("ticker") for r in bc if isinstance(r, dict) and r.get("verdict") != "BUY"]
    if bad_buys:
        failures.append(f"buy_candidates has {len(bad_buys)} non-BUY rows: {bad_buys[:5]}")

    # 5: sample ticker has gates_evaluated
    sample = next((r for r in (b.get("all_scored") or []) if isinstance(r, dict)), None)
    if sample and not sample.get("gates_evaluated"):
        failures.append(f"sample ticker {sample.get('ticker')} has empty gates_evaluated — engine output missing")

    # 6: circuit breaker enforced
    cb = (b.get("system_status") or {}).get("circuit_breaker") or {}
    if cb.get("active") and bc:
        failures.append(f"circuit breaker active but {len(bc)} BUYs surfacing — gating failed")

    healthy = len(failures) == 0
    if not healthy and notify:
        _alert(
            level="CRITICAL",
            title=f"Engine health FAIL — {len(failures)} check(s)",
            body="; ".join(failures[:3])[:300],
        )
    return healthy, failures


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true", help="silent on success")
    ap.add_argument("--no-notify", action="store_true", help="skip Mac notification")
    args = ap.parse_args()

    healthy, failures = check_health(notify=not args.no_notify)

    if healthy:
        if not args.quiet:
            in_prog = _scan_in_progress()
            print(f"✓ Engine health: OK ({date.today()})" + (" — scan currently running, deferred engine-line check" if in_prog else ""))
            b = json.loads(BUNDLE.read_text())
            print(f"  Bundle decision_engine_version: {b.get('decision_engine_version')}")
            print(f"  buy_candidates: {len(b.get('buy_candidates') or [])}")
            print(f"  watch_list:     {len(b.get('watch_list') or [])}")
            cb = (b.get('system_status') or {}).get('circuit_breaker') or {}
            print(f"  circuit_breaker active: {cb.get('active', False)}")
        sys.exit(0)
    else:
        print("✗ Engine health: FAIL")
        for i, f in enumerate(failures, 1):
            print(f"  {i}. {f}")
        sys.exit(1)


if __name__ == "__main__":
    main()

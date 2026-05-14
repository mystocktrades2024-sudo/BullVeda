#!/usr/bin/env python3
"""
_weekly_diag_compare.py — compare this week's regime_sharpe_decomp to last week's,
send Slack alert if material regression.

Called by weekly_diagnostics.sh on Sunday evenings.

Triggers Slack alert when:
  - aggregate Sharpe drops by > 0.10 vs prior week
  - choppy regime PF drops below 1.0
  - rolling-20-BUY Sharpe is below -0.5 (kill threshold)
"""
from __future__ import annotations
import json
import os
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _slack_post(webhook: str, text: str) -> bool:
    try:
        import requests
        r = requests.post(webhook, json={"text": text}, timeout=8)
        return r.status_code == 200
    except Exception:
        return False


def _load_env_webhook() -> str | None:
    env_p = REPO / ".env"
    if not env_p.exists():
        return os.environ.get("SLACK_WEBHOOK_URL")
    for line in env_p.read_text().splitlines():
        line = line.strip()
        if line.startswith("SLACK_WEBHOOK_URL="):
            return line.split("=", 1)[1].strip()
    return None


def _find_decomp(target_date: date) -> dict | None:
    """Return the regime_sharpe_decomp_<date>.json closest to target_date."""
    candidates = sorted(
        (REPO / "cache").glob("regime_sharpe_decomp_*.json"),
        key=lambda p: p.stat().st_mtime, reverse=True,
    )
    target_str = target_date.isoformat()
    for p in candidates:
        if target_str in p.name:
            return json.loads(p.read_text())
    return None


def main():
    today_p = REPO / "cache" / f"regime_sharpe_decomp_{date.today().isoformat()}.json"
    if not today_p.exists():
        print(f"[compare] today's decomp missing — skipping")
        return
    today_data = json.loads(today_p.read_text())

    prior_p = None
    for delta in range(7, 14):
        candidate_date = date.today() - timedelta(days=delta)
        candidate_p = REPO / "cache" / f"regime_sharpe_decomp_{candidate_date.isoformat()}.json"
        if candidate_p.exists():
            prior_p = candidate_p
            break

    today_agg = (today_data.get("aggregate") or {})
    today_choppy = ((today_data.get("by_regime") or {}).get("risk_on_choppy") or {})

    msgs = []

    # Warning: choppy PF degraded
    cp = today_choppy.get("pf", 0)
    if cp and cp < 1.0:
        msgs.append(f"⚠️ Choppy regime PF dropped to {cp:.2f} (n={today_choppy.get('n')})")

    # Compare to prior week
    if prior_p:
        prior_data = json.loads(prior_p.read_text())
        prior_agg = (prior_data.get("aggregate") or {})
        d_sharpe = today_agg.get("sharpe_per_trade", 0) - prior_agg.get("sharpe_per_trade", 0)
        if d_sharpe < -0.10:
            msgs.append(
                f"⚠️ Aggregate Sharpe regressed {prior_agg.get('sharpe_per_trade'):.3f} → "
                f"{today_agg.get('sharpe_per_trade'):.3f} (Δ {d_sharpe:+.3f}) "
                f"vs prior week {prior_p.name}"
            )

    # Check rolling-Sharpe kill state
    try:
        import sys as _sys
        _sys.path.insert(0, str(REPO))
        from decision_engine import compute_rolling_sharpe_kill_state
        cfg = json.loads((REPO / "config" / "config.json").read_text())
        rs = compute_rolling_sharpe_kill_state(cfg)
        if rs.get("active"):
            msgs.append(f"🔴 ROLLING-SHARPE KILL ACTIVE — {rs.get('reason')}")
        elif rs.get("sharpe") is not None and rs["sharpe"] < -0.4:
            msgs.append(
                f"⚠️ Rolling Sharpe near kill threshold "
                f"({rs['sharpe']:.3f} vs -0.50, n={rs.get('n')})"
            )
    except Exception as e:
        print(f"[compare] rolling-Sharpe check failed: {e}")

    if not msgs:
        print(f"[compare] no regressions detected — agg Sharpe {today_agg.get('sharpe_per_trade')}")
        return

    body = (f"*Kairos weekly diagnostics — {date.today().isoformat()}*\n\n"
            + "\n".join(msgs)
            + f"\n\nFull report: {today_p}")

    print("[compare] regressions detected:")
    print(body)

    webhook = _load_env_webhook()
    if webhook:
        if _slack_post(webhook, body):
            print(f"[compare] Slack alert sent")
        else:
            print(f"[compare] Slack post failed")
    else:
        print(f"[compare] SLACK_WEBHOOK_URL not configured — alert printed to log only")


if __name__ == "__main__":
    main()

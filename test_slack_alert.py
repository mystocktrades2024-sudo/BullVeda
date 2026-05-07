"""
test_slack_alert.py — Verify Slack webhook config is working.

Usage:
    python3 test_slack_alert.py             # send a test alert
    python3 test_slack_alert.py --check     # report config without sending

Reads SLACK_WEBHOOK_URL from .env via secrets_loader, falls back to
config/config.json → alerts.slack_webhook (legacy path).
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))


def check_config() -> str | None:
    """Return webhook URL if configured, None if not."""
    try:
        from secrets_loader import get_secret
        url = get_secret("SLACK_WEBHOOK_URL", default="")
        if url:
            return url
    except Exception:
        pass
    try:
        import json
        cfg = json.loads((ROOT / "config" / "config.json").read_text())
        url = (cfg.get("alerts") or {}).get("slack_webhook", "")
        if url and "hooks.slack.com" in url and "..." not in url:
            return url
    except Exception:
        pass
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="report config, do not send")
    args = ap.parse_args()

    webhook = check_config()
    if not webhook:
        print("✗ SLACK_WEBHOOK_URL not configured")
        print()
        print("To set up:")
        print("  1. Create a Slack app + Incoming Webhook for your channel")
        print("     https://api.slack.com/messaging/webhooks")
        print(f"  2. Edit {ROOT / '.env'} and add:")
        print("     SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL")
        print("  3. Re-run this script (without --check) to verify")
        sys.exit(1)

    masked = webhook[:38] + "..." + webhook[-6:] if len(webhook) > 50 else "(short)"
    print(f"✓ Webhook configured: {masked}")
    if args.check:
        return

    from alerts import send_alert
    print("Sending test alert (level=INFO, no Slack post — INFO is local-only)...")
    send_alert(level="INFO", title="Test alert (INFO)",
               body="This is a quiet INFO test — should NOT appear in Slack.")
    print("Sending test alert (level=WARN — should appear in Slack)...")
    ok = send_alert(level="WARN", title="SwingTrade Slack test",
                    body="Slack integration is working. Engine failures, drift detection, "
                         "and CRITICAL alerts will now post here.")
    if ok:
        print("✓ Slack post succeeded — check your Slack channel")
    else:
        print("✗ Slack post failed — webhook may be invalid or revoked")
        sys.exit(1)


if __name__ == "__main__":
    main()

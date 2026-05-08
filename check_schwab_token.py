#!/usr/bin/env python3
"""
check_schwab_token.py — daily Schwab refresh-token health check.

Schwab refresh tokens expire 7 days after issue. This script:
  1. Reads the current refresh_token from .env
  2. Calls Schwab's /oauth/token endpoint with grant_type=refresh_token
  3. On success: rotates the refresh_token (extending life by another 7 days),
     writes the new token to .env
  4. On failure: posts a Slack alert telling the user to re-OAuth before
     options data goes dark

Run daily via launchd. Side benefit: the daily refresh keeps the token
alive indefinitely as long as the user doesn't ignore failure alerts.
"""
from __future__ import annotations
import base64
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
LOG_FILE = BASE / "cache" / "logs" / "schwab_token_check.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [schwab_token] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"


def _load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    env_path = BASE / ".env"
    if not env_path.exists():
        return env
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def _write_env(updates: dict[str, str]) -> None:
    """Update specific keys in .env, preserving the rest."""
    env_path = BASE / ".env"
    lines = env_path.read_text().splitlines() if env_path.exists() else []
    out: list[str] = []
    seen: set[str] = set()
    for line in lines:
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            k = s.split("=", 1)[0].strip()
            if k in updates:
                out.append(f"{k}={updates[k]}")
                seen.add(k)
                continue
        out.append(line)
    for k, v in updates.items():
        if k not in seen:
            out.append(f"{k}={v}")
    env_path.write_text("\n".join(out) + "\n")


def _slack_alert(title: str, body: str, level: str = "WARN") -> None:
    """Forward to alerts.send_alert which handles Slack + macOS notification."""
    try:
        # Make sure SLACK_WEBHOOK_URL is in os.environ for alerts.py
        env = _load_env()
        if env.get("SLACK_WEBHOOK_URL") and not os.environ.get("SLACK_WEBHOOK_URL"):
            os.environ["SLACK_WEBHOOK_URL"] = env["SLACK_WEBHOOK_URL"]
        from alerts import send_alert
        send_alert(level, title, body)
    except Exception as e:
        log.warning(f"Slack alert failed: {e}")


def main() -> int:
    env = _load_env()
    key = env.get("SCHWAB_APP_KEY")
    secret = env.get("SCHWAB_APP_SECRET")
    refresh = env.get("SCHWAB_REFRESH_TOKEN")

    if not (key and secret and refresh):
        log.error("Missing Schwab credentials in .env (need SCHWAB_APP_KEY, "
                  "SCHWAB_APP_SECRET, SCHWAB_REFRESH_TOKEN)")
        _slack_alert(
            "🔑 Schwab credentials missing",
            "check_schwab_token.py couldn't find Schwab API credentials in .env. "
            "Options data will not flow until this is fixed."
        )
        return 1

    # Track when the current refresh token was issued, for surfacing in alerts.
    issued_at = env.get("SCHWAB_REFRESH_ISSUED_AT")
    age_days = None
    if issued_at:
        try:
            age_days = (time.time() - float(issued_at)) / 86400
        except (TypeError, ValueError):
            pass

    log.info(f"Probing Schwab refresh endpoint (token age: "
             f"{f'{age_days:.1f}d' if age_days is not None else 'unknown'})")

    import urllib.request, urllib.error
    auth = base64.b64encode(f"{key}:{secret}".encode()).decode()
    body = f"grant_type=refresh_token&refresh_token={refresh}".encode()
    req = urllib.request.Request(
        TOKEN_URL,
        data=body,
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            tok = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode()[:300]
        except Exception:
            pass
        log.error(f"Schwab refresh FAILED — HTTP {e.code}: {err_body}")
        days_str = f"{age_days:.1f} days" if age_days is not None else "unknown age"
        _slack_alert(
            "🔑 Schwab re-auth needed — options data dark",
            (
                f"Schwab refresh token rejected (HTTP {e.code}, age {days_str}). "
                f"Options panels (UOA, IV rank, P/C, max-pain, gamma) will return "
                f"NO_DATA until re-authenticated.\n\n"
                f"Fix: in a terminal where you can complete a browser OAuth, run:\n"
                f"```\n"
                f"cd /Volumes/MyMacDisk/Claude\\ Skills/SwingTrade\n"
                f"python3 schwab_auth.py oauth\n"
                f"```"
            ),
            level="CRITICAL",
        )
        return 2
    except Exception as e:
        log.error(f"Schwab refresh request error: {e}")
        return 3

    # Success — write back the rotated tokens
    new_access = tok.get("access_token")
    new_refresh = tok.get("refresh_token") or refresh  # fallback if Schwab didn't rotate
    expires_in = int(tok.get("expires_in", 1800))
    expires_at = int(time.time()) + expires_in - 60

    updates = {
        "SCHWAB_ACCESS_TOKEN":     new_access,
        "SCHWAB_REFRESH_TOKEN":    new_refresh,
        "SCHWAB_TOKEN_EXPIRES_AT": str(expires_at),
        "SCHWAB_REFRESH_ISSUED_AT": str(int(time.time())),
    }
    _write_env(updates)

    log.info(f"✓ Refresh OK — access_token rotated, refresh_token age reset to 0d. "
             f"Next forced refresh: in 24h.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""
Email Report — SwingTrade
=========================
Sends the dashboard HTML as an email attachment after each scan.

Uses Gmail SMTP with App Password (not OAuth).

Setup (one-time):
  1. Go to myaccount.google.com → Security → 2-Step Verification (must be ON)
  2. Search "App Passwords" → Create one for "Mail" / "Mac"
  3. Copy the 16-char password into config/config.json → email.app_password
  4. Set your Gmail address in config/config.json → email.from_address
  5. Set recipient(s) in config/config.json → email.to_addresses

Configuration in config/config.json:
    {
        "email": {
            "enabled": true,
            "from_address": "you@gmail.com",
            "app_password": "xxxx xxxx xxxx xxxx",
            "to_addresses": ["you@gmail.com"],
            "subject_prefix": "SwingTrade Report"
        }
    }
"""

from __future__ import annotations

import json
import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

log = logging.getLogger("swingtrade.email")

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config" / "config.json"


def _load_email_config() -> dict | None:
    """Load email config from config.json. Returns None if not configured."""
    try:
        cfg = json.loads(CONFIG_PATH.read_text())
        email_cfg = cfg.get("email", {})
        if not email_cfg.get("enabled", False):
            return None
        # AI-2d: prefer env/.env for app_password; fall back to config.json
        if not email_cfg.get("app_password"):
            try:
                from secrets_loader import get_secret as _gs
                _pw = _gs("GMAIL_APP_PASSWORD", default="")
                if _pw:
                    email_cfg["app_password"] = _pw
            except Exception:
                pass
        required = ["from_address", "app_password", "to_addresses"]
        for key in required:
            if not email_cfg.get(key):
                log.warning(f"Email config missing '{key}' — skipping email (set GMAIL_APP_PASSWORD in .env)")
                return None
        return email_cfg
    except Exception as e:
        log.warning(f"Could not load email config: {e}")
        return None


def send_dashboard_email(
    html_path: str | Path,
    buy_count: int = 0,
    sell_count: int = 0,
    regime: str = "unknown",
) -> bool:
    """Send the dashboard HTML file as an email attachment.

    Args:
        html_path: Path to the dashboard HTML file
        buy_count: Number of BUY signals (for subject line)
        sell_count: Number of SELL signals (for subject line)
        regime: Market regime (for subject line)

    Returns:
        True if sent successfully, False otherwise
    """
    cfg = _load_email_config()
    if cfg is None:
        return False

    html_path = Path(html_path)
    if not html_path.exists():
        log.warning(f"Dashboard file not found: {html_path}")
        return False

    now = datetime.now()
    date_str = now.strftime("%b %d %I:%M%p")
    prefix = cfg.get("subject_prefix", "SwingTrade Report")

    # Build subject line with key info
    subject = f"{prefix} — {date_str} | {regime.upper()} | {buy_count} BUY, {sell_count} SELL"

    # Build email
    msg = MIMEMultipart()
    msg["From"] = cfg["from_address"]
    msg["To"] = ", ".join(cfg["to_addresses"])
    msg["Subject"] = subject

    # Brief text body
    body = (
        f"SwingTrade Scan — {date_str}\n"
        f"Regime: {regime.upper()}\n"
        f"BUY signals: {buy_count}\n"
        f"SELL signals: {sell_count}\n\n"
        f"Open the attached HTML file in a browser for the full dashboard."
    )
    msg.attach(MIMEText(body, "plain"))

    # Attach HTML dashboard. If the dashboard was generated in split-mode
    # (references external dashboard.css/dashboard.js), inline those assets
    # so the emailed attachment is a standalone single-file HTML.
    # ST_DATA is trimmed to top 50 tickers to stay under Gmail's 25 MB limit.
    html_text = html_path.read_text(encoding="utf-8")
    parent = html_path.parent
    _inlines = [
        ('<link rel="stylesheet" href="dashboard.css">', parent / "dashboard.css", "style"),
        ('src="dashboard-data.js"', parent / "dashboard-data.js", "script"),
        ('<script src="dashboard.js"></script>', parent / "dashboard.js", "script"),
    ]
    for tag, asset, wrap in _inlines:
        if tag in html_text and asset.exists():
            # For partial matches (like dashboard-data.js with onerror attr),
            # find the full <script ...>...</script> tag and replace it entirely
            if tag != html_text and not tag.startswith("<"):
                _idx = html_text.find(tag)
                if _idx >= 0:
                    _tag_start = html_text.rfind("<script", 0, _idx)
                    _tag_end = html_text.find("</script>", _idx) + len("</script>")
                    if _tag_start >= 0 and _tag_end > _tag_start:
                        tag = html_text[_tag_start:_tag_end]
            body = asset.read_text(encoding="utf-8")
            # Trim ST_DATA to top 50 tickers (BUY/WATCH first, then by score)
            if "dashboard-data" in str(asset):
                try:
                    import json as _ej
                    _start = body.find("{")
                    _end = body.rfind("}") + 1
                    if _start >= 0 and _end > _start:
                        _all = _ej.loads(body[_start:_end])
                        # Keep BUY + WATCH + top by score
                        _buy = {k: v for k, v in _all.items() if v.get("verdict") == "BUY"}
                        _watch = {k: v for k, v in _all.items() if v.get("verdict") == "WATCH"}
                        _rest = sorted(
                            [(k, v) for k, v in _all.items() if k not in _buy and k not in _watch],
                            key=lambda x: x[1].get("score", 0), reverse=True
                        )
                        _trimmed = {**_buy, **_watch}
                        _slots = 50 - len(_trimmed)
                        for k, v in _rest[:max(0, _slots)]:
                            _trimmed[k] = v
                        body = body[:_start] + _ej.dumps(_trimmed, separators=(",", ":")) + body[_end:]
                        log.info(f"Email ST_DATA trimmed: {len(_all)} → {len(_trimmed)} tickers")
                except Exception as _te:
                    log.debug(f"ST_DATA trim failed: {_te}")
            html_text = html_text.replace(
                tag,
                f"<{wrap}>\n{body}\n</{wrap}>",
            )
    html_data = html_text.encode("utf-8")
    attachment = MIMEBase("text", "html")
    attachment.set_payload(html_data)
    encoders.encode_base64(attachment)
    filename = f"SwingTrade_Dashboard_{now.strftime('%Y%m%d_%H%M')}.html"
    attachment.add_header("Content-Disposition", f"attachment; filename={filename}")
    msg.attach(attachment)

    # Send via Gmail SMTP
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(cfg["from_address"], cfg["app_password"])
            server.send_message(msg)
        log.info(f"Dashboard emailed to {cfg['to_addresses']}")
        return True
    except smtplib.SMTPAuthenticationError:
        log.error("Gmail auth failed — check app_password in config.json")
        return False
    except Exception as e:
        log.error(f"Email send failed: {e}")
        return False

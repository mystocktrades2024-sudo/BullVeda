"""autorun_reporter.py — uniform Slack status posts from launchd autoruns.

Drop-in helper for any launchd-triggered script to post completion status
to Slack with consistent formatting + emoji.

Usage:
    from lib.autorun_reporter import report

    # In your script:
    try:
        # ... do the work ...
        report("morning-briefing", "complete",
               summary="14 BUY, 49 WATCH, regime=risk_on_choppy",
               duration_sec=420)
    except Exception as e:
        report("morning-briefing", "failed", summary=str(e)[:200])
        raise

Levels: success | warning | failed | info
Each one maps to an emoji + Slack severity.

Posts to webhook from SLACK_WEBHOOK_URL env (or alerts._slack_post). Silent
no-op if webhook not configured. Designed to never crash the caller —
exceptions in reporting are swallowed.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

_LEVEL_EMOJI = {
    "success": "🟢",
    "info":    "🔵",
    "warning": "🟡",
    "failed":  "🔴",
    "complete": "🟢",  # alias for success
}


def _get_webhook() -> str:
    try:
        from secrets_loader import get_secret as _gs
        return _gs("SLACK_WEBHOOK_URL", default="") or ""
    except Exception:
        return os.environ.get("SLACK_WEBHOOK_URL", "")


_REPORT_KIND_MAP = {
    # autorun name → report kind (for "latest" link)
    "morning-briefing": "morning-briefing",
    "weekly-diagnostics": "dashboard",  # weekly produces dashboard snapshot
    "prewarm-cache": None,  # no HTML output
    "enrich-nightly": None,
    "ticker-snapshots": None,
}


def report(autorun_name: str, status: str,
           summary: str = "", duration_sec: float | None = None,
           details: dict | None = None) -> bool:
    """Post a one-line status to Slack for the named autorun.

    autorun_name:  short identifier (e.g. "morning-briefing", "weekly-diagnostics")
    status:        "success" | "complete" | "warning" | "failed" | "info"
    summary:       one-line human description
    duration_sec:  optional, formatted as "Xs" or "Ym"
    details:       optional dict, rendered as small fields

    Returns True if Slack post succeeded, False otherwise.
    Never raises — designed to be call-and-forget.

    Automatically appends report-archive links if there's an HTML output
    associated with this autorun.
    """
    try:
        webhook = _get_webhook()
        if not webhook:
            return False

        emoji = _LEVEL_EMOJI.get(status.lower(), "⚪")
        ts = datetime.now().strftime("%H:%M:%S PT")
        dur_str = ""
        if duration_sec is not None:
            if duration_sec < 60:
                dur_str = f" · {duration_sec:.0f}s"
            elif duration_sec < 3600:
                dur_str = f" · {duration_sec/60:.1f}m"
            else:
                dur_str = f" · {duration_sec/3600:.1f}h"

        text = f"{emoji} *{autorun_name}* · `{status}` @ {ts}{dur_str}"
        if summary:
            text += f"\n{summary[:300]}"

        blocks = [{
            "type": "section",
            "text": {"type": "mrkdwn", "text": text},
        }]
        if details:
            field_lines = []
            for k, v in list(details.items())[:6]:  # cap at 6 fields
                vs = str(v)[:80]
                field_lines.append(f"  `{k}`: {vs}")
            if field_lines:
                blocks.append({
                    "type": "context",
                    "elements": [{"type": "mrkdwn", "text": "\n".join(field_lines)}],
                })

        # Add report archive links — always include, special-case latest if available
        report_kind = _REPORT_KIND_MAP.get(autorun_name)
        link_text = "<https://trade.mystockholding.com/reports|📚 Report Archive>"
        if report_kind:
            link_text = (
                f"<https://trade.mystockholding.com/reports/latest/{report_kind}|🗂️ Latest {autorun_name}> · "
                + link_text
            )
        link_text += " · <https://trade.mystockholding.com/kairos.html|🔗 Live Dashboard>"
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": link_text}],
        })

        from alerts import _slack_post
        return _slack_post(webhook, text, blocks)
    except Exception:
        # Never crash the caller — autorun status posting is best-effort
        return False


def report_complete(autorun_name: str, summary: str = "", duration_sec: float | None = None,
                     **details) -> bool:
    """Convenience wrapper for success completion with arbitrary detail kwargs."""
    return report(autorun_name, "success", summary=summary,
                  duration_sec=duration_sec, details=details if details else None)


def report_failed(autorun_name: str, error: str = "", duration_sec: float | None = None) -> bool:
    """Convenience wrapper for failure."""
    return report(autorun_name, "failed", summary=error[:300], duration_sec=duration_sec)

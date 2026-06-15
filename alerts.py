"""
Alert System — SwingTrade
=========================
Sends BUY/SELL/WATCH signals to:
  1. macOS native notification (osascript — always available)
  2. Slack webhook (configured via config/config.json → alerts.slack_webhook)

Usage (called automatically by swing_trade.py after each scan):
    from alerts import send_scan_alerts
    send_scan_alerts(buy_candidates, sell_candidates, watch_candidates)

Configuration:
    In config/config.json → "alerts" section:
    {
        "alerts": {
            "enabled": true,
            "slack_webhook": "https://hooks.slack.com/services/...",
            "mac_notify": true,
            "min_score_notify": 55
        }
    }
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

import requests

log = logging.getLogger("swingtrade.alerts")

BASE_DIR    = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config" / "config.json"


def _load_alert_cfg() -> dict:
    try:
        cfg = json.loads(CONFIG_PATH.read_text())
        return cfg.get("alerts", {})
    except Exception:
        return {}


# ── macOS native notification ─────────────────────────────────────────────────

def _mac_notify(title: str, message: str, subtitle: str = "") -> None:
    """Send a macOS notification via osascript (no external library needed)."""
    try:
        script = (
            f'display notification "{message}" '
            f'with title "{title}"'
            + (f' subtitle "{subtitle}"' if subtitle else "")
        )
        subprocess.run(["osascript", "-e", script], timeout=5, capture_output=True)
    except Exception as e:
        log.debug(f"Mac notify failed: {e}")


# ── Slack webhook ─────────────────────────────────────────────────────────────

def _slack_post(webhook: str, text: str, blocks: list | None = None) -> bool:
    """POST a message to a Slack webhook. Returns True on success."""
    try:
        payload: dict = {"text": text}
        if blocks:
            payload["blocks"] = blocks
        resp = requests.post(webhook, json=payload, timeout=8)
        return resp.status_code == 200
    except Exception as e:
        log.debug(f"Slack post failed: {e}")
        return False


# AI-30: Alert severity tiers — INFO / WARN / CRITICAL
#   INFO: routine (scan complete, watch triggers, daily summary)
#   WARN: drift detected, drawdown >5%, consecutive losses, stale data
#   CRITICAL: kill switch triggered, vendor down, regime flip to risk_off,
#             broker connection lost, unexpected data sanity failures
# All levels log via log.{info,warning,error}. Slack formatting adds
# severity emoji + routing. INFO throttled by default.

_LEVEL_EMOJI = {"INFO": "ℹ️", "WARN": "⚠️", "CRITICAL": "🔴"}


def send_alert(level: str, title: str, body: str = "", webhook: str | None = None,
               force_slack: bool = False) -> bool:
    """Severity-tiered alert. level ∈ {INFO, WARN, CRITICAL}.

    - Logs at appropriate severity
    - Mac notification for WARN/CRITICAL
    - Slack post for WARN/CRITICAL only (INFO stays local to reduce noise)
    - force_slack=True posts INFO to Slack too (no Mac notification) — used by
      opt-in feeds (entry-watcher shadow, daily signal alerts) the owner wants
      in Slack but that aren't warnings.
    """
    level = level.upper()
    if level not in _LEVEL_EMOJI:
        level = "INFO"
    emoji = _LEVEL_EMOJI[level]
    _dash = "https://trade.mystockholding.com"
    msg = f"{emoji} [{level}] {title}" + (f" — {body}" if body else "") + f"\n<{_dash}|Open Dashboard>"

    if level == "CRITICAL":
        log.error(msg)
    elif level == "WARN":
        log.warning(msg)
    else:
        log.info(msg)

    # Mac notification for WARN/CRITICAL
    if level in ("WARN", "CRITICAL"):
        try:
            import subprocess
            subprocess.run(
                ["osascript", "-e",
                 f'display notification "{body[:200]}" with title "SwingTrade {level}: {title[:80]}"'],
                check=False, timeout=5,
            )
        except Exception:
            pass

    # Slack for WARN/CRITICAL (or any level when force_slack) — auto-load webhook
    if level in ("WARN", "CRITICAL") or force_slack:
        if not webhook:
            try:
                from secrets_loader import get_secret as _gs
                webhook = _gs("SLACK_WEBHOOK_URL", default="")
            except Exception:
                pass
            if not webhook:
                try:
                    cfg = _load_alert_cfg()
                    webhook = cfg.get("slack_webhook", "")
                except Exception:
                    pass
        if webhook:
            # force_slack feeds (entry alerts, daily digests) carry their own
            # formatting/emoji — post clean, without the *[LEVEL]* prefix.
            if force_slack and level == "INFO":
                text = f"{title}\n{body}" if body else title
            else:
                text = f"{emoji} *[{level}]* {title}\n{body}"
            _slack_post(webhook, text)
            return True
    return False


def _slack_blocks_for_picks(
    buy_list: list[dict],
    sell_list: list[dict],
    watch_list: list[dict],
    regime: str,
    spy_price: float | None,
    near_short_blocked: list[dict] | None = None,
) -> list:
    """Build Slack Block Kit message for scan results."""
    blocks = []

    # Header
    spy_str = f" | SPY ${spy_price:.2f}" if spy_price else ""
    blocks.append({
        "type": "header",
        "text": {"type": "plain_text", "text": f"SwingTrade Scan — {regime.upper()}{spy_str}"}
    })

    def _fmt_pick_detail(p: dict, emoji: str) -> str:
        ticker = p.get("ticker", "")
        price  = p.get("entry_price", p.get("price", 0))
        score  = p.get("score", "?")
        setup  = p.get("setup_type", "")
        rr     = p.get("rr_ratio", "")
        plan   = p.get("trade_plan") or p
        stop   = plan.get("stop", 0)
        t1     = plan.get("target1", 0)
        t2     = plan.get("target2", 0)
        entry_lo = plan.get("entry_low", plan.get("primary_zone_low", price))
        entry_hi = plan.get("entry_high", plan.get("primary_zone_high", price))
        rs     = p.get("rs_rank", "")
        family = p.get("setup_family", "")
        hold   = p.get("hold_period_guide", "")
        stars  = p.get("star_rating", "")

        line1 = f"{emoji} *{ticker}*  `${price:.2f}`  Score: *{score}*  RS: *{rs}*"
        line2 = f"    Setup: _{setup}_ ({family}) · Hold: {hold}"
        line3 = f"    Entry: `${entry_lo:.2f}` – `${entry_hi:.2f}` · Stop: `${stop:.2f}` · T1: `${t1:.2f}` · T2: `${t2:.2f}`"
        line4 = f"    R:R: *{rr}:1*" + (f" · Stars: {'⭐' * int(stars)}" if stars else "")
        return f"{line1}\n{line2}\n{line3}\n{line4}"

    if buy_list:
        lines = [_fmt_pick_detail(p, ":large_green_circle:") for p in buy_list[:5]]
        blocks.append({"type": "section",
                        "text": {"type": "mrkdwn",
                                 "text": "*:rocket: BUY SIGNALS*\n\n" + "\n\n".join(lines)}})

    if watch_list:
        lines = [_fmt_pick_detail(p, ":large_yellow_circle:") for p in watch_list[:5]]
        blocks.append({"type": "section",
                        "text": {"type": "mrkdwn",
                                 "text": "*:eyes: WATCH LIST*\n\n" + "\n\n".join(lines)}})

    if sell_list:
        lines = [_fmt_pick_detail(p, ":red_circle:") for p in sell_list[:5]]
        blocks.append({"type": "section",
                        "text": {"type": "mrkdwn",
                                 "text": "*:chart_with_downwards_trend: SHORT SIGNALS*\n\n" + "\n\n".join(lines)}})

    if near_short_blocked:
        # Compact one-line-per-ticker — these are informational only, blocked by gates
        def _compact(p):
            t = p.get("ticker", "")
            s = p.get("score", "?")
            rs = p.get("rs_rank", "")
            reason = ((p.get("decision") or {}).get("reason") or "").strip()
            if len(reason) > 90:
                reason = reason[:87] + "…"
            return f":warning: *{t}* Score:{s} RS:{rs} — _{reason}_"
        lines = [_compact(p) for p in near_short_blocked[:5]]
        blocks.append({"type": "section",
                        "text": {"type": "mrkdwn",
                                 "text": "*:construction: NEAR-SHORT (blocked by gates)*\n\n" + "\n".join(lines)}})

    blocks.append({"type": "divider"})
    _dash_url = "https://trade.mystockholding.com"
    blocks.append({
        "type": "context",
        "elements": [{"type": "mrkdwn",
                       "text": f"<{_dash_url}|:chart_with_upwards_trend: Open Dashboard> · <{_dash_url}|trade.mystockholding.com>"}]
    })
    return blocks


# ── Public API ────────────────────────────────────────────────────────────────

def send_scan_alerts(
    buy_candidates: list[dict],
    sell_candidates: list[dict],
    watch_candidates: list[dict],
    regime: str = "unknown",
    spy_price: float | None = None,
    near_short_blocked: list[dict] | None = None,
) -> None:
    """Send alerts for scan results. Called automatically after each scan.

    sell_candidates    = real SHORT verdicts (passed all gates)
    near_short_blocked = bear setups blocked by gates (regime / VIX / sector / etc.)
    """
    cfg = _load_alert_cfg()
    if not cfg.get("enabled", True):
        return

    min_score = cfg.get("min_score_notify", 50)

    # Filter to meaningful picks only
    buys  = [p for p in buy_candidates  if p.get("score", 0) >= min_score]
    sells = [p for p in sell_candidates if p.get("score", 0) >= min_score]
    near  = near_short_blocked or []
    watches = watch_candidates[:5]

    if not buys and not sells and not watches and not near:
        return  # nothing worth alerting

    # ── macOS notification ────────────────────────────────────────────────────
    if cfg.get("mac_notify", True):
        parts = []
        if buys:
            top = buys[0]
            parts.append(f"BUY: {top['ticker']} ${top.get('entry_price', top.get('price', 0)):.2f} Score:{top['score']}")
        if sells:
            top = sells[0]
            parts.append(f"SHORT: {top['ticker']} Score:{top['score']}")
        if watches and not parts:
            parts.append(f"WATCH: {', '.join(p['ticker'] for p in watches[:3])}")

        msg = " | ".join(parts)
        _mac_notify(
            title=f"SwingTrade ({regime.upper()})",
            message=msg,
            subtitle=f"{len(buys)} buy, {len(sells)} short, {len(watches)} watch, {len(near)} near-short blocked",
        )
        log.info(f"Mac notification sent: {msg}")

    # ── Slack notification ────────────────────────────────────────────────────
    # AI-2d: prefer env / .env via secrets_loader; fall back to config
    webhook = ""
    try:
        from secrets_loader import get_secret as _gs
        webhook = _gs("SLACK_WEBHOOK_URL", default="")
    except Exception:
        pass
    if not webhook:
        webhook = cfg.get("slack_webhook", "")
    if webhook:
        blocks = _slack_blocks_for_picks(buys, sells, watches, regime, spy_price, near_short_blocked=near)
        near_note = f" | {len(near)} Near-Short Blocked" if near else ""
        plain  = (f"SwingTrade {regime.upper()}: "
                  f"{len(buys)} BUY | {len(sells)} SHORT | {len(watches)} WATCH{near_note}")
        ok = _slack_post(webhook, text=plain, blocks=blocks)
        if ok:
            log.info("Slack alert sent.")
        else:
            log.warning("Slack alert failed (check webhook URL in config/config.json → alerts.slack_webhook)")


def send_watch_promotion(ticker: str, score: int, setup: str, rr: float) -> None:
    """Alert when a WATCH pick enters its entry zone (auto-promotion trigger)."""
    cfg = _load_alert_cfg()
    if not cfg.get("enabled", True):
        return

    msg = f"{ticker} entered entry zone! Score:{score} R:R {rr}:1 — {setup}"

    if cfg.get("mac_notify", True):
        _mac_notify("SwingTrade — WATCH Triggered", msg, subtitle="Entry zone hit")

    webhook = cfg.get("slack_webhook", "")
    if webhook:
        _slack_post(webhook, text=f":bell: WATCH TRIGGERED: {msg}")

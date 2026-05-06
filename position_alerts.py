"""Position-level alerts. Throttled via data/alert_sent_log.json."""
from pathlib import Path
from datetime import datetime, date, timezone, timedelta
import json
import logging

log = logging.getLogger("position_alerts")
BASE_DIR = Path(__file__).parent
ALERT_LOG_PATH = BASE_DIR / "data" / "alert_sent_log.json"

ET = timezone(timedelta(hours=-5))


def _is_market_hours() -> bool:
    """Return True if currently within 9:30-16:00 ET, Mon-Fri."""
    now = datetime.now(ET)
    if now.weekday() >= 5:  # weekend
        return False
    t = now.time()
    from datetime import time as _dt_time
    return _dt_time(9, 30) <= t <= _dt_time(16, 0)


def _load_alert_log() -> dict:
    if not ALERT_LOG_PATH.exists():
        return {}
    try:
        return json.load(open(ALERT_LOG_PATH))
    except Exception:
        return {}


def _save_alert_log(data: dict):
    ALERT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    json.dump(data, open(ALERT_LOG_PATH, "w"), indent=2, default=str)


def _already_sent_today(ticker: str, alert_type: str) -> bool:
    log_data = _load_alert_log()
    today = date.today().isoformat()
    key = f"{ticker}:{alert_type}"
    return log_data.get(key, "") == today


def _mark_sent(ticker: str, alert_type: str):
    log_data = _load_alert_log()
    today = date.today().isoformat()
    log_data[f"{ticker}:{alert_type}"] = today
    # Purge entries older than 7 days
    cutoff = (date.today() - timedelta(days=7)).isoformat()
    log_data = {k: v for k, v in log_data.items() if v >= cutoff}
    _save_alert_log(log_data)


def _send(level: str, title: str, body: str):
    """Send via Slack + Mac notification. Best-effort."""
    try:
        from alerts import send_alert
        send_alert(level=level, title=title, body=body)
    except Exception as e:
        log.debug(f"Alert dispatch failed: {e}")


def check_stop_approach(position: dict, current_price: float, atr: float) -> bool:
    """If price is within 1 ATR of stop (long) or 1 ATR above (short), alert."""
    ticker = position["ticker"]
    direction = position.get("direction", "long")
    stop = position.get("stop", 0)
    if not stop or not atr:
        return False

    if direction == "long":
        distance = current_price - stop
    else:
        distance = stop - current_price

    if 0 < distance <= atr:
        if _already_sent_today(ticker, "stop_approach"):
            return False
        _send("WARN",
              f"\u26a0\ufe0f {ticker} approaching stop",
              f"Price ${current_price:.2f} within {distance/atr:.2f} ATR of stop ${stop:.2f}")
        _mark_sent(ticker, "stop_approach")
        return True
    return False


def check_t1_hit(position: dict, current_price: float) -> bool:
    """If price >= T1 (long) or <= T1 (short), alert."""
    ticker = position["ticker"]
    direction = position.get("direction", "long")
    t1 = position.get("target1", 0)
    if not t1:
        return False

    hit = (direction == "long" and current_price >= t1) or \
          (direction == "short" and current_price <= t1)
    if hit:
        if _already_sent_today(ticker, "t1_hit"):
            return False
        entry = position.get("entry_price", t1)
        pnl_pct = abs((t1 - entry) / entry * 100)
        _send("INFO",
              f"\U0001f3af {ticker} hit T1",
              f"Price ${current_price:.2f} reached T1 ${t1:.2f} ({pnl_pct:.1f}% gain). "
              f"Consider 50% partial + move stop to BE.")
        _mark_sent(ticker, "t1_hit")
        return True
    return False


def send_eod_digest(positions: list, summary: dict) -> bool:
    """Send end-of-day summary with all position P&L. Once per day."""
    if _already_sent_today("_PORTFOLIO_", "eod_digest"):
        return False
    if not positions:
        return False

    lines = [f"\U0001f4ca EOD Portfolio Summary \u2014 {date.today().isoformat()}"]
    total_pnl = 0.0
    for p in positions:
        ticker = p["ticker"]
        entry = p.get("entry_price", 0)
        current = p.get("current_price", entry)
        shares = p.get("shares", 0)
        direction = p.get("direction", "long")
        pnl = (current - entry) * shares if direction == "long" else (entry - current) * shares
        pnl_pct = ((current - entry) / entry * 100) if direction == "long" else ((entry - current) / entry * 100)
        total_pnl += pnl
        arrow = "\U0001f4c8" if pnl >= 0 else "\U0001f4c9"
        lines.append(f"  {arrow} {ticker} ({direction[0].upper()}): {pnl:+.2f} ({pnl_pct:+.1f}%)")

    lines.append(f"\nTotal unrealized: ${total_pnl:+.2f}")
    lines.append(f"Open positions: {len(positions)} \u00b7 Cash: ${summary.get('cash', 0):.2f}")

    _send("INFO", f"EOD Digest \u2014 {len(positions)} positions", "\n".join(lines))
    _mark_sent("_PORTFOLIO_", "eod_digest")
    return True


def run_alerts_pass():
    """Main entry \u2014 called from EOD manager or scan pipeline.
    Respects market hours gate. Skips all alerts when market closed."""
    if not _is_market_hours():
        log.debug("Outside market hours \u2014 skipping alerts")
        return {"skipped": True, "reason": "outside_market_hours"}

    try:
        from portfolio_tracker import get_portfolio_summary
        from data_fetcher import fetch_ohlcv_with_failover
    except ImportError as e:
        return {"error": str(e)}

    summary = get_portfolio_summary()
    positions = summary.get("positions", [])
    if not positions:
        return {"skipped": True, "reason": "no_positions"}

    alerts_sent = []
    for p in positions:
        ticker = p.get("ticker", "")
        try:
            df, _ = fetch_ohlcv_with_failover(ticker, days=30)
            if df is None or df.empty:
                continue
            current = float(df["Close"].iloc[-1])
            # ATR = avg of high-low over last 14 bars
            if "High" in df.columns and "Low" in df.columns and len(df) >= 14:
                atr = (df["High"].tail(14) - df["Low"].tail(14)).mean()
            else:
                atr = current * 0.02  # fallback 2%

            if check_stop_approach(p, current, atr):
                alerts_sent.append({"ticker": ticker, "type": "stop_approach"})
            if check_t1_hit(p, current):
                alerts_sent.append({"ticker": ticker, "type": "t1_hit"})
        except Exception as e:
            log.debug(f"Alert check failed for {ticker}: {e}")

    return {"alerts_sent": alerts_sent, "positions_checked": len(positions)}


if __name__ == "__main__":
    # Smoke test \u2014 runs checks regardless of market hours
    import position_alerts as _pa
    _pa._is_market_hours = lambda: True
    r = _pa.run_alerts_pass()
    print(f"Alert pass result: {r}")

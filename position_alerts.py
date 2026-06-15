"""Position-level alerts. Throttled via data/alert_sent_log.json."""
from pathlib import Path
from datetime import datetime, date, timezone, timedelta
import json
import logging

log = logging.getLogger("position_alerts")
BASE_DIR = Path(__file__).parent
ALERT_LOG_PATH = BASE_DIR / "data" / "alert_sent_log.json"


def _is_market_hours() -> bool:
    """Return True if currently within 9:30-16:00 America/New_York, Mon-Fri.

    DST-aware (uses zoneinfo). Previously this used hardcoded UTC-5 (EST),
    which made the gate off by 1 hour during EDT (March-November) — alerts
    could fire 1 hour after close. Fixed 2026-05-08."""
    try:
        import zoneinfo
        now = datetime.now(zoneinfo.ZoneInfo("America/New_York"))
    except ImportError:
        # Python <3.9 fallback (unlikely path)
        ET = timezone(timedelta(hours=-4))  # rough EDT, only used in fallback
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
        send_alert(level=level, title=title, body=body, force_slack=True)
    except Exception as e:
        log.debug(f"Alert dispatch failed: {e}")


def _card(rows, footer=None):
    """Clean scannable card body (matches entry-alert + digest style)."""
    lines = ["—" * 21]
    for label, value in rows:
        lines.append(f"{label:<8}{value}" if label else str(value))
    if footer:
        lines.append(footer)
    return "\n".join(lines)


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
              f"\u26a0\ufe0f  {ticker} \u2014 approaching stop",
              _card([("Price", f"${current_price:.2f}"),
                     ("Stop", f"${stop:.2f}"),
                     ("Dist", f"{distance/atr:.2f} ATR away")]))
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
              f"\U0001f3af  {ticker} — T1 hit  ·  +{pnl_pct:.1f}%",
              _card([("Price", f"${current_price:.2f}"),
                     ("T1", f"${t1:.2f}")],
                    footer="💡 Take 50% partial · move stop to break-even"))
        _mark_sent(ticker, "t1_hit")
        return True
    return False


def check_stop_hit(position: dict, current_price: float) -> bool:
    """HARD EXIT: stop level breached. Long: price <= stop. Short: price >= stop.
    Fires 24/7 (premarket, after-hours, overnight) — never gated by market hours.
    """
    ticker = position["ticker"]
    direction = position.get("direction", "long")
    stop = position.get("stop", 0)
    if not stop:
        return False
    breached = (current_price <= stop) if direction == "long" else (current_price >= stop)
    if not breached:
        return False
    if _already_sent_today(ticker, "stop_hit"):
        return False
    entry = position.get("entry_price", 0)
    pnl_pct = ((current_price - entry) / entry * 100) if entry and direction == "long" else 0
    _send("CRITICAL",
          f"\U0001f6a8  {ticker} — STOP HIT · exit now",
          _card([("Price", f"${current_price:.2f}"),
                 ("Stop", f"${stop:.2f}"),
                 ("Entry", f"${entry:.2f}"),
                 ("P&L", f"{pnl_pct:+.2f}%")],
                footer="💡 Sell at market or set a tight stop-limit"))
    _mark_sent(ticker, "stop_hit")
    return True


def check_t2_hit(position: dict, current_price: float) -> bool:
    """HARD: T2 reached. Long: price >= t2. Short: price <= t2. 24/7."""
    ticker = position["ticker"]
    direction = position.get("direction", "long")
    t2 = position.get("target2", 0)
    if not t2:
        return False
    hit = (current_price >= t2) if direction == "long" else (current_price <= t2)
    if not hit:
        return False
    if _already_sent_today(ticker, "t2_hit"):
        return False
    entry = position.get("entry_price", 0)
    pnl_pct = abs((t2 - entry) / entry * 100) if entry else 0
    _send("INFO",
          f"\U0001f4b0  {ticker} — T2 hit  ·  +{pnl_pct:.1f}%",
          _card([("Price", f"${current_price:.2f}"),
                 ("T2", f"${t2:.2f}")],
                footer="💡 Full exit or trail the runner"))
    _mark_sent(ticker, "t2_hit")
    return True


def check_adverse_gap(position: dict, current_price: float, prev_close: float, atr: float) -> bool:
    """HARD: adverse gap > 2 ATR (long: gap-down, short: gap-up). 24/7.
    Catches premarket/overnight catalyst moves before they widen further at open.
    """
    if not prev_close or not atr:
        return False
    ticker = position["ticker"]
    direction = position.get("direction", "long")
    gap = current_price - prev_close
    adverse_gap = gap if direction == "short" else -gap  # positive = adverse
    if adverse_gap < 2 * atr:
        return False
    if _already_sent_today(ticker, "adverse_gap"):
        return False
    gap_pct = (current_price / prev_close - 1) * 100
    direction_word = "GAP DOWN" if direction == "long" else "GAP UP"
    _send("WARN",
          f"⚠️  {ticker} — {direction_word} {gap_pct:+.1f}%",
          _card([("Price", f"${current_price:.2f}"),
                 ("Prev cl", f"${prev_close:.2f}"),
                 ("Adverse", f"{abs(adverse_gap)/atr:.1f} ATR")],
                footer="💡 Review premarket/AH news; tighten stop or exit at open"))
    _mark_sent(ticker, "adverse_gap")
    return True


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


def _get_schwab_batch(tickers: list) -> dict:
    """Batch real-time quotes from Schwab. Works 24/7 (AH, overnight, premarket).
    Returns {ticker: {price, prev_close}}; empty dict on failure.
    """
    if not tickers:
        return {}
    try:
        import schwab_client as _sc
        data = _sc.get_quotes_batch(tickers[:500]) or {}
        out = {}
        for sym, blob in data.items():
            if not isinstance(blob, dict): continue
            q = blob.get("quote") or {}
            try:
                last = q.get("lastPrice")
                pc = q.get("closePrice")
                if last is None: continue
                out[sym] = {
                    "price": round(float(last), 2),
                    "prev_close": round(float(pc), 2) if pc is not None else None,
                }
            except (TypeError, ValueError):
                continue
        return out
    except Exception as e:
        log.debug(f"Schwab batch quote failed: {e}")
        return {}


def run_alerts_pass():
    """Main entry \u2014 called from EOD manager or scan pipeline every 60s.

    Price source strategy (2026-05-19):
     - Schwab live-quote (real-time, 24/7) is PRIMARY for current price
     - EODHD OHLCV is fallback for current + provides ATR + prev_close
     - ATR is always computed from EODHD (Schwab doesn't expose it directly)

    Hard exits (stop_hit, t2_hit, adverse_gap) fire 24/7 \u2014 they trigger on
    breached price levels and can't wait until market open (premarket gaps
    can blow through stops before 9:30am).

    Soft alerts (stop_approach within 1 ATR, t1_hit pre-trail) only fire
    during 9:30am\u20134pm ET to avoid pre/post-market noise on bid-ask spread.
    """
    try:
        from portfolio_tracker import get_portfolio_summary
        from data_fetcher import fetch_ohlcv_with_failover
    except ImportError as e:
        return {"error": str(e)}

    summary = get_portfolio_summary()
    positions = summary.get("positions", [])
    if not positions:
        return {"skipped": True, "reason": "no_positions"}

    in_hours = _is_market_hours()
    # Single batch call to Schwab for ALL position tickers \u2014 efficient + 24/7
    tickers = [p.get("ticker") for p in positions if p.get("ticker")]
    schwab_quotes = _get_schwab_batch(tickers)
    schwab_hit, schwab_miss = 0, 0
    alerts_sent = []
    for p in positions:
        ticker = p.get("ticker", "")
        if not ticker: continue
        try:
            # Get EODHD OHLCV for ATR computation (always \u2014 Schwab doesn't give ATR)
            df = None
            try:
                df_result, _ = fetch_ohlcv_with_failover(ticker, days=30)
                if df_result is not None and not df_result.empty:
                    df = df_result
            except Exception:
                pass

            # Resolve current price: Schwab first (real-time, 24/7), EODHD fallback
            sq = schwab_quotes.get(ticker)
            current = None
            prev_close = None
            price_source = None
            if sq and sq.get("price", 0) > 0:
                current = sq["price"]
                prev_close = sq.get("prev_close")
                price_source = "schwab"
                schwab_hit += 1
            if current is None and df is not None:
                current = float(df["Close"].iloc[-1])
                prev_close = prev_close or (float(df["Close"].iloc[-2]) if len(df) >= 2 else current)
                price_source = "eodhd"
                schwab_miss += 1
            if current is None:
                log.debug(f"No price available for {ticker} \u2014 skipping")
                continue

            # Backfill prev_close from EODHD if Schwab didn't have it
            if not prev_close and df is not None and len(df) >= 2:
                prev_close = float(df["Close"].iloc[-2])
            prev_close = prev_close or current

            # ATR from EODHD (Schwab doesn't expose intra-bar OHLC easily)
            if df is not None and "High" in df.columns and "Low" in df.columns and len(df) >= 14:
                atr = float((df["High"].tail(14) - df["Low"].tail(14)).mean())
            else:
                atr = current * 0.02  # fallback 2%

            # HARD EXITS \u2014 fire 24/7 regardless of session
            if check_stop_hit(p, current):
                alerts_sent.append({"ticker": ticker, "type": "stop_hit", "price_source": price_source})
            if check_t2_hit(p, current):
                alerts_sent.append({"ticker": ticker, "type": "t2_hit", "price_source": price_source})
            if check_adverse_gap(p, current, prev_close, atr):
                alerts_sent.append({"ticker": ticker, "type": "adverse_gap", "price_source": price_source})

            # SOFT ALERTS \u2014 regular hours only (extended-hour spreads are wide)
            if in_hours:
                if check_stop_approach(p, current, atr):
                    alerts_sent.append({"ticker": ticker, "type": "stop_approach", "price_source": price_source})
                if check_t1_hit(p, current):
                    alerts_sent.append({"ticker": ticker, "type": "t1_hit", "price_source": price_source})
        except Exception as e:
            log.debug(f"Alert check failed for {ticker}: {e}")

    return {
        "alerts_sent": alerts_sent,
        "positions_checked": len(positions),
        "in_hours": in_hours,
        "schwab_hit": schwab_hit,
        "schwab_miss": schwab_miss,
    }


if __name__ == "__main__":
    # Smoke test \u2014 runs checks regardless of market hours
    import position_alerts as _pa
    _pa._is_market_hours = lambda: True
    r = _pa.run_alerts_pass()
    print(f"Alert pass result: {r}")

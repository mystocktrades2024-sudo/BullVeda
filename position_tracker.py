"""
Position Tracker — SwingTrade
=============================
Lightweight tracker for ACTUAL positions (entries/exits) with P&L tracking
and stop-loss alerts.

Storage: data/positions.json
  {
    "open_positions": [...],
    "closed_positions": [...]
  }

Distinct from portfolio_tracker.py (paper-trade state) and custom_tracker.py
(watchlist mark-to-market). This tracks real money positions.
"""

from __future__ import annotations

import json
import os
import tempfile
import logging
from datetime import datetime, date
from pathlib import Path

log = logging.getLogger("swingtrade.position_tracker")

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
POSITIONS_PATH = DATA_DIR / "positions.json"


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------

def _ensure_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


def _load() -> dict:
    _ensure_dir()
    if not POSITIONS_PATH.exists():
        return {"open_positions": [], "closed_positions": []}
    try:
        with open(POSITIONS_PATH, "r") as f:
            data = json.load(f)
        data.setdefault("open_positions", [])
        data.setdefault("closed_positions", [])
        return data
    except (json.JSONDecodeError, OSError):
        return {"open_positions": [], "closed_positions": []}


def _save(data: dict) -> None:
    """Atomic write: write to tmp then rename."""
    _ensure_dir()
    fd, tmp_path = tempfile.mkstemp(
        prefix="positions_", suffix=".json.tmp", dir=str(DATA_DIR)
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, default=str)
        os.replace(tmp_path, POSITIONS_PATH)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Price helpers (Schwab -> Polygon -> archive -> yfinance)
# ---------------------------------------------------------------------------

def _fetch_current_price(ticker: str) -> float | None:
    """Latest price via EODHD real-time, archive fallback."""
    # Layer 1: EODHD real-time (15-min delayed)
    try:
        import eodhd_client as _eod
        rt = _eod.real_time(ticker)
        if isinstance(rt, dict):
            px = rt.get("close") or rt.get("previousClose")
            if px and px != "NA":
                v = float(px)
                if v > 0:
                    return v
    except Exception:
        pass
    # Layer 2: archive (cached)
    try:
        from data_archive import load_ticker
        df = load_ticker(ticker)
        if df is not None and not df.empty:
            return float(df["Close"].iloc[-1])
    except Exception:
        pass
    return None


def _batch_prices(tickers: list[str]) -> dict[str, float | None]:
    """Fetch prices for multiple tickers — EODHD batch real-time, archive fallback."""
    out: dict[str, float | None] = {t: None for t in tickers}
    if not tickers:
        return out
    # Layer 1: EODHD batch real-time
    try:
        import eodhd_client as _eod
        rt = _eod.real_time(tickers[:500])
        rows = rt if isinstance(rt, list) else ([rt] if isinstance(rt, dict) else [])
        for q in rows:
            code = (q.get("code") or "").split(".")[0].upper()
            px = q.get("close") or q.get("previousClose")
            if code in [t.upper() for t in tickers] and px and px != "NA":
                try:
                    out[code] = float(px)
                except (ValueError, TypeError):
                    pass
    except Exception:
        pass
    # Layer 2: archive for remaining
    missing = [t for t in tickers if out[t] is None]
    if missing:
        try:
            from data_archive import load_ticker
            for t in missing:
                df = load_ticker(t)
                if df is not None and not df.empty:
                    out[t] = float(df["Close"].iloc[-1])
        except Exception:
            pass
    # Layer 3: per-ticker EODHD for any still missing
    missing = [t for t in tickers if out[t] is None]
    for t in missing:
        out[t] = _fetch_current_price(t)
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def open_position(
    ticker: str,
    entry_price: float,
    shares: int,
    stop: float,
    target1: float,
    target2: float | None = None,
    setup_type: str = "",
    notes: str = "",
) -> dict:
    """Add a new open position. Returns the position dict."""
    if not ticker or not isinstance(ticker, str):
        return {"success": False, "error": "Invalid ticker"}
    ticker = ticker.upper().strip()

    if entry_price <= 0 or shares <= 0 or stop <= 0 or target1 <= 0:
        return {"success": False, "error": "entry_price, shares, stop, target1 must be positive"}

    data = _load()

    # Check for duplicate open position
    for pos in data["open_positions"]:
        if pos.get("ticker") == ticker and pos.get("status") == "open":
            return {"success": False, "error": f"{ticker} already has an open position"}

    now = datetime.now()
    position = {
        "ticker": ticker,
        "entry_price": round(entry_price, 4),
        "entry_date": now.date().isoformat(),
        "shares": int(shares),
        "stop": round(stop, 4),
        "target1": round(target1, 4),
        "target2": round(target2, 4) if target2 else None,
        "setup_type": setup_type,
        "notes": notes,
        "status": "open",
        "opened_at": now.isoformat(timespec="seconds"),
    }

    data["open_positions"].append(position)
    _save(data)

    log.info(f"Opened position: {ticker} {shares}sh @ ${entry_price:.2f} | Stop ${stop:.2f} | T1 ${target1:.2f}")
    return {"success": True, "position": position}


def close_position(ticker: str, exit_price: float, notes: str = "") -> dict:
    """Close an open position. Moves to closed_positions with P&L computed."""
    if not ticker or not isinstance(ticker, str):
        return {"success": False, "error": "Invalid ticker"}
    ticker = ticker.upper().strip()

    if exit_price <= 0:
        return {"success": False, "error": "exit_price must be positive"}

    data = _load()

    # Find the open position
    idx = None
    for i, pos in enumerate(data["open_positions"]):
        if pos.get("ticker") == ticker and pos.get("status") == "open":
            idx = i
            break

    if idx is None:
        return {"success": False, "error": f"No open position for {ticker}"}

    pos = data["open_positions"].pop(idx)
    entry_price = pos["entry_price"]
    shares = pos["shares"]

    # Compute P&L
    pnl_dollars = round((exit_price - entry_price) * shares, 2)
    pnl_pct = round((exit_price - entry_price) / entry_price * 100, 2) if entry_price > 0 else 0.0

    # Compute realized R (risk was entry - stop)
    risk_per_share = abs(entry_price - pos["stop"])
    realized_r = round((exit_price - entry_price) / risk_per_share, 2) if risk_per_share > 0 else 0.0

    now = datetime.now()
    closed_trade = {
        "ticker": ticker,
        "entry_price": entry_price,
        "exit_price": round(exit_price, 4),
        "entry_date": pos["entry_date"],
        "exit_date": now.date().isoformat(),
        "shares": shares,
        "pnl_pct": pnl_pct,
        "pnl_dollars": pnl_dollars,
        "realized_r": realized_r,
        "setup_type": pos.get("setup_type", ""),
        "notes": notes or pos.get("notes", ""),
        "closed_at": now.isoformat(timespec="seconds"),
    }

    data["closed_positions"].append(closed_trade)
    _save(data)

    log.info(f"Closed position: {ticker} @ ${exit_price:.2f} | P&L {pnl_pct:+.1f}% (${pnl_dollars:+.2f}) | R: {realized_r:+.2f}")
    return {"success": True, "trade": closed_trade}


def get_open_positions() -> list[dict]:
    """Return open positions enriched with current_price, pnl, days_held, distance_to_stop."""
    data = _load()
    positions = data.get("open_positions", [])
    if not positions:
        return []

    tickers = [p["ticker"] for p in positions]
    prices = _batch_prices(tickers)
    today = date.today()

    enriched: list[dict] = []
    for pos in positions:
        tk = pos["ticker"]
        entry = pos["entry_price"]
        cur = prices.get(tk)
        shares = pos["shares"]

        pnl_pct = None
        pnl_dollars = None
        distance_to_stop_pct = None

        if cur and entry:
            pnl_pct = round((cur - entry) / entry * 100, 2)
            pnl_dollars = round((cur - entry) * shares, 2)

        if cur and pos.get("stop"):
            distance_to_stop_pct = round((cur - pos["stop"]) / cur * 100, 2)

        try:
            ed = date.fromisoformat(pos.get("entry_date", ""))
            days_held = (today - ed).days
        except Exception:
            days_held = 0

        # Earnings date lookup
        _earnings_date = None
        _days_to_earnings = None
        try:
            from data_fetcher import get_earnings_date
            _ed = get_earnings_date(tk)
            _earnings_date = _ed.get("earnings_date")
            _days_to_earnings = _ed.get("days_to_earnings")
        except Exception:
            pass

        enriched.append({
            **pos,
            "current_price": round(cur, 4) if cur else None,
            "pnl_pct": pnl_pct,
            "pnl_dollars": pnl_dollars,
            "days_held": days_held,
            "distance_to_stop_pct": distance_to_stop_pct,
            "earnings_date": _earnings_date,
            "days_to_earnings": _days_to_earnings,
        })

    return enriched


def get_closed_positions() -> dict:
    """Return closed positions list with summary stats."""
    data = _load()
    closed = data.get("closed_positions", [])

    if not closed:
        return {"trades": [], "summary": {"total_trades": 0, "win_rate": 0, "avg_r": 0, "total_pnl": 0}}

    wins = [t for t in closed if t.get("pnl_dollars", 0) > 0]
    losses = [t for t in closed if t.get("pnl_dollars", 0) <= 0]
    win_rate = round(len(wins) / len(closed) * 100, 1) if closed else 0

    all_r = [t.get("realized_r", 0) for t in closed if t.get("realized_r") is not None]
    avg_r = round(sum(all_r) / len(all_r), 2) if all_r else 0

    total_pnl = round(sum(t.get("pnl_dollars", 0) for t in closed), 2)

    return {
        "trades": closed,
        "summary": {
            "total_trades": len(closed),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": win_rate,
            "avg_r": avg_r,
            "total_pnl": total_pnl,
        },
    }


def check_stops() -> list[dict]:
    """Return list of open positions where current price <= stop.

    Uses batch price fetch (Schwab -> Polygon -> archive -> yfinance).
    """
    data = _load()
    positions = data.get("open_positions", [])
    if not positions:
        return []

    tickers = [p["ticker"] for p in positions]
    prices = _batch_prices(tickers)

    stopped_out: list[dict] = []
    for pos in positions:
        tk = pos["ticker"]
        cur = prices.get(tk)
        stop = pos.get("stop")
        if cur and stop and cur <= stop:
            stopped_out.append({
                "ticker": tk,
                "current_price": round(cur, 4),
                "stop": stop,
                "entry_price": pos["entry_price"],
                "shares": pos["shares"],
                "loss_pct": round((cur - pos["entry_price"]) / pos["entry_price"] * 100, 2),
                "loss_dollars": round((cur - pos["entry_price"]) * pos["shares"], 2),
            })

    return stopped_out


def get_summary() -> dict:
    """Portfolio summary: open_count, total_invested, unrealized/realized P&L, win_rate, avg_r."""
    data = _load()
    open_pos = data.get("open_positions", [])
    closed = data.get("closed_positions", [])

    # Get current prices for unrealized P&L
    tickers = [p["ticker"] for p in open_pos]
    prices = _batch_prices(tickers) if tickers else {}

    total_invested = 0.0
    unrealized_pnl = 0.0
    for pos in open_pos:
        cost = pos["entry_price"] * pos["shares"]
        total_invested += cost
        cur = prices.get(pos["ticker"])
        if cur:
            unrealized_pnl += (cur - pos["entry_price"]) * pos["shares"]

    realized_pnl = sum(t.get("pnl_dollars", 0) for t in closed)

    wins = [t for t in closed if t.get("pnl_dollars", 0) > 0]
    win_rate = round(len(wins) / len(closed) * 100, 1) if closed else 0.0

    all_r = [t.get("realized_r", 0) for t in closed if t.get("realized_r") is not None]
    avg_r = round(sum(all_r) / len(all_r), 2) if all_r else 0.0

    return {
        "open_count": len(open_pos),
        "closed_count": len(closed),
        "total_invested": round(total_invested, 2),
        "unrealized_pnl": round(unrealized_pnl, 2),
        "realized_pnl": round(realized_pnl, 2),
        "win_rate": win_rate,
        "avg_r": avg_r,
    }

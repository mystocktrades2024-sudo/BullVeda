"""
Custom Ticker Tracker (PT-22).

Allows users to add arbitrary tickers (stocks, ETFs, crypto like BTC-USD) to a
custom watchlist so the Performance tab can mark them to market even if they
weren't surfaced by the daily scan.

Storage: data/custom_tracked.json
  {
    "tickers": [
      {"ticker","entry_price","entry_date","entry_time","note","added_at","source":"CUSTOM"}
    ]
  }
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, date
from pathlib import Path

import logging
log = logging.getLogger("swingtrade.custom_tracker")

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
CUSTOM_PATH = DATA_DIR / "custom_tracked.json"


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------

def _ensure_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


def _load() -> dict:
    _ensure_dir()
    if not CUSTOM_PATH.exists():
        return {"tickers": []}
    try:
        with open(CUSTOM_PATH, "r") as f:
            data = json.load(f)
        if "tickers" not in data or not isinstance(data["tickers"], list):
            data = {"tickers": []}
        return data
    except (json.JSONDecodeError, OSError):
        return {"tickers": []}


def _save(data: dict) -> None:
    """Atomic write: write to tmp then rename."""
    _ensure_dir()
    fd, tmp_path = tempfile.mkstemp(
        prefix="custom_tracked_", suffix=".json.tmp", dir=str(DATA_DIR)
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, CUSTOM_PATH)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Price helpers
# ---------------------------------------------------------------------------

def _fetch_current_price(ticker: str) -> float | None:
    """Latest close price via EODHD real-time, archive fallback."""
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
    try:
        from data_archive import load_ticker
        df = load_ticker(ticker)
        if df is not None and not df.empty:
            return float(df["Close"].iloc[-1])
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def add_custom_ticker(ticker: str, note: str = "") -> dict:
    """Add a ticker to the custom watchlist using current price as entry."""
    if not ticker or not isinstance(ticker, str):
        return {"success": False, "error": "Invalid ticker"}
    ticker = ticker.upper().strip()
    if not ticker:
        return {"success": False, "error": "Invalid ticker"}

    data = _load()
    for row in data["tickers"]:
        if row.get("ticker") == ticker:
            return {"success": False, "ticker": ticker, "error": "Already tracked"}

    price = _fetch_current_price(ticker)
    if price is None:
        return {
            "success": False,
            "ticker": ticker,
            "error": f"Could not fetch price for {ticker} (yfinance returned no data)",
        }

    now = datetime.now()
    entry = {
        "ticker": ticker,
        "entry_price": round(price, 4),
        "entry_date": now.date().isoformat(),
        "entry_time": now.strftime("%H:%M:%S"),
        "note": note or "",
        "added_at": now.isoformat(timespec="seconds"),
        "source": "CUSTOM",
    }
    data["tickers"].append(entry)
    _save(data)

    return {
        "success": True,
        "ticker": ticker,
        "entry_price": entry["entry_price"],
        "entry_date": entry["entry_date"],
    }


def remove_custom_ticker(ticker: str) -> dict:
    """Remove a ticker from the custom watchlist."""
    if not ticker or not isinstance(ticker, str):
        return {"success": False, "error": "Invalid ticker"}
    ticker = ticker.upper().strip()

    data = _load()
    before = len(data["tickers"])
    data["tickers"] = [t for t in data["tickers"] if t.get("ticker") != ticker]
    if len(data["tickers"]) == before:
        return {"success": False, "ticker": ticker, "error": "Not tracked"}
    _save(data)
    return {"success": True, "ticker": ticker}


def _batch_current_prices(tickers: list[str]) -> dict[str, float | None]:
    """Fetch prices via EODHD batch real-time, archive fallback."""
    out: dict[str, float | None] = {t: None for t in tickers}
    if not tickers:
        return out
    try:
        import eodhd_client as _eod
        rt = _eod.real_time(tickers[:500])
        rows = rt if isinstance(rt, list) else ([rt] if isinstance(rt, dict) else [])
        upper_set = {t.upper(): t for t in tickers}
        for q in rows:
            code = (q.get("code") or "").split(".")[0].upper()
            if code in upper_set:
                px = q.get("close") or q.get("previousClose")
                if px and px != "NA":
                    try:
                        out[upper_set[code]] = float(px)
                    except (ValueError, TypeError):
                        pass
    except Exception:
        pass
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
    missing = [t for t in tickers if out[t] is None]
    for t in missing:
        out[t] = _fetch_current_price(t)
    return out


def get_custom_tickers() -> list[dict]:
    """Return enriched list with current price, pnl%, and days held."""
    data = _load()
    rows = data.get("tickers", [])
    if not rows:
        return []

    tickers = [r["ticker"] for r in rows]
    current_prices = _batch_current_prices(tickers)
    today = date.today()

    enriched: list[dict] = []
    for r in rows:
        tk = r["ticker"]
        entry = r.get("entry_price")
        cur = current_prices.get(tk)
        pnl_pct = None
        if entry and cur:
            try:
                pnl_pct = round((cur - entry) / entry * 100.0, 2)
            except Exception:
                pnl_pct = None
        try:
            ed = date.fromisoformat(r.get("entry_date", ""))
            days_held = (today - ed).days
        except Exception:
            days_held = 0
        enriched.append({
            "ticker": tk,
            "entry_price": entry,
            "entry_date": r.get("entry_date"),
            "entry_time": r.get("entry_time"),
            "note": r.get("note", ""),
            "current_price": round(cur, 4) if cur else None,
            "pnl_pct": pnl_pct,
            "days_held": days_held,
            "source": "CUSTOM",
        })
    return enriched


def update_custom_mtm(tickers: list[dict]) -> list[dict]:
    """Add D1/D2/D3/D4/D5/W1/W2/M1 % returns from entry_price."""
    out: list[dict] = []
    for row in tickers:
        enriched = dict(row)
        tk = row.get("ticker")
        entry_price = row.get("entry_price")
        entry_date_str = row.get("entry_date")
        # init
        for k in ("D1", "D2", "D3", "D4", "D5", "W1", "W2", "M1"):
            enriched[k] = None

        if not tk or not entry_price or not entry_date_str:
            out.append(enriched)
            continue

        try:
            hist = yf.Ticker(tk).history(period="60d")
        except Exception:
            out.append(enriched)
            continue

        if hist is None or hist.empty:
            out.append(enriched)
            continue

        # Normalize index to date
        try:
            entry_d = date.fromisoformat(entry_date_str)
        except Exception:
            out.append(enriched)
            continue

        # Find bars on/after entry_date
        try:
            idx_dates = [d.date() if hasattr(d, "date") else d for d in hist.index]
        except Exception:
            out.append(enriched)
            continue

        # Collect closes from the first bar >= entry_d
        closes_after: list[float] = []
        for d_, close in zip(idx_dates, hist["Close"].values):
            if d_ >= entry_d:
                try:
                    closes_after.append(float(close))
                except Exception:
                    pass

        offsets = {"D1": 1, "D2": 2, "D3": 3, "D4": 4, "D5": 5,
                   "W1": 5, "W2": 10, "M1": 21}
        for label, off in offsets.items():
            if len(closes_after) > off:
                try:
                    p = closes_after[off]
                    enriched[label] = round((p - entry_price) / entry_price * 100.0, 2)
                except Exception:
                    enriched[label] = None

        out.append(enriched)
    return out


def clear_all_custom() -> dict:
    """Remove all custom tickers — intended for testing."""
    data = _load()
    n = len(data.get("tickers", []))
    _save({"tickers": []})
    return {"success": True, "count_removed": n}

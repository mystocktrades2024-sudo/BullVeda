"""
false_negatives.py — Recall diagnostics for the SwingTrade screener.

For a given scan date we look forward N days and find every S&P 500 ticker that
actually ran (> threshold %). We then cross-reference against the decision_log
to see which winners we caught vs. which were blocked — and by what gate.

Usage:
    python3 false_negatives.py                 # today, default 5d / 5% threshold
    python3 false_negatives.py 2026-04-10      # specific scan date
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta
from typing import Any, Optional

log = logging.getLogger("swingtrade.false_negatives")

_DEFAULT_FN_PATH = "cache/false_negatives.json"


# ────────────────────────────────────────────────────────────────────────────
# Data helpers
# ────────────────────────────────────────────────────────────────────────────

def _parse_date(s: Any) -> Optional[date]:
    if s is None:
        return None
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _get_universe() -> list[str]:
    """Return the S&P 500 ticker list (with best-effort fallbacks)."""
    try:
        from data_fetcher import get_sp500  # type: ignore
        tickers = get_sp500() or []
        if tickers:
            return list(tickers)
    except Exception as e:
        log.debug(f"get_sp500 failed: {e}")
    return []


def _get_ohlcv(ticker: str, days: int = 30):
    """Fetch OHLCV bars. Tries Polygon first, falls back to yfinance."""
    try:
        from data_fetcher import get_polygon_ohlcv  # type: ignore
        df = get_polygon_ohlcv(ticker, days=days, timespan="day")
        if df is not None and len(df) > 0:
            return df
    except Exception as e:
        log.debug(f"Polygon fetch failed for {ticker}: {e}")

    try:
        from data_fetcher import yf  # _YfStub (yfinance removed 2026-04-25)
        df = yf.download(ticker, period=f"{max(days, 30)}d", interval="1d",
                         progress=False, threads=False, auto_adjust=True)
        if df is not None and len(df) > 0:
            return df
    except Exception as e:
        log.debug(f"yfinance fetch failed for {ticker}: {e}")
    return None


def _ticker_sector(ticker: str) -> str:
    try:
        from data_fetcher import _TICKER_TO_SECTOR  # type: ignore
        return _TICKER_TO_SECTOR.get(ticker, "Unknown")
    except Exception:
        return "Unknown"


# ────────────────────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────────────────────

def find_universe_winners(scan_date: str,
                          forward_days: int = 5,
                          threshold_pct: float = 5.0) -> list[dict]:
    """Find all S&P 500 tickers that gained >threshold_pct within forward_days.

    Returns list of:
        {ticker, entry_date, exit_date, return_pct, sector}
    """
    d = _parse_date(scan_date)
    if d is None:
        log.error(f"Invalid scan_date: {scan_date!r}")
        return []

    tickers = _get_universe()
    if not tickers:
        log.warning("Empty S&P 500 universe; cannot evaluate winners.")
        return []

    winners: list[dict] = []
    # Fetch ~forward_days + buffer back from "today" relative to scan_date.
    today = date.today()
    days_span = (today - d).days + forward_days + 5
    days_span = max(days_span, forward_days + 5)

    for t in tickers:
        try:
            df = _get_ohlcv(t, days=days_span)
            if df is None or len(df) == 0:
                continue

            # Normalize index → date list
            try:
                import pandas as pd  # type: ignore
                if isinstance(df.columns, pd.MultiIndex):
                    df = df.droplevel(1, axis=1)
            except Exception:
                pass

            # Close column
            if "Close" not in df.columns:
                continue
            close = df["Close"]
            try:
                close = close.squeeze()
            except Exception:
                pass
            close = close.dropna()
            if len(close) < 2:
                continue

            # Find first index >= scan_date
            idx_dates = []
            for ix in close.index:
                try:
                    idx_dates.append(ix.date() if hasattr(ix, "date") else
                                     _parse_date(str(ix)))
                except Exception:
                    idx_dates.append(None)

            start_i = None
            for i, dt in enumerate(idx_dates):
                if dt is not None and dt >= d:
                    start_i = i
                    break
            if start_i is None or start_i >= len(close) - 1:
                continue

            end_i = min(start_i + forward_days, len(close) - 1)
            entry_price = float(close.iloc[start_i])
            if entry_price <= 0:
                continue

            # Best close within window = "best exit"
            window = close.iloc[start_i:end_i + 1]
            max_close = float(window.max())
            max_i = int(window.values.argmax()) + start_i
            ret_pct = (max_close / entry_price - 1.0) * 100.0

            if ret_pct > threshold_pct:
                entry_dt = idx_dates[start_i]
                exit_dt = idx_dates[max_i]
                winners.append({
                    "ticker": t,
                    "entry_date": entry_dt.isoformat() if entry_dt else None,
                    "exit_date": exit_dt.isoformat() if exit_dt else None,
                    "return_pct": round(ret_pct, 2),
                    "sector": _ticker_sector(t),
                })
        except Exception as e:
            log.debug(f"find_universe_winners: skipping {t}: {e}")

    winners.sort(key=lambda w: w["return_pct"], reverse=True)
    return winners


def categorize_missed_winners(scan_date: str, forward_days: int = 5) -> dict:
    """Cross-reference universe winners against decision_log entries for that
    date. For each winner we didn't BUY, look up verdict + blocking gate.
    """
    d = _parse_date(scan_date)
    if d is None:
        return {
            "winners": 0, "caught": 0, "missed": 0, "recall_pct": 0.0,
            "by_gate": {}, "top_misses": [],
        }

    winners = find_universe_winners(scan_date, forward_days=forward_days)

    # Load decision_log for that date (and a day before in case of timezone drift)
    try:
        from decision_logger import load_recent_decisions  # type: ignore
        days_back = max(1, (date.today() - d).days + 2)
        decisions = load_recent_decisions(days=days_back)
    except Exception as e:
        log.warning(f"categorize_missed_winners: decision log unavailable: {e}")
        decisions = []

    # Index decisions by (ticker, date)
    decision_by_ticker: dict[str, dict] = {}
    for rec in decisions:
        try:
            rec_d = _parse_date(rec.get("date"))
            if rec_d != d:
                continue
            t = rec.get("ticker")
            if not t:
                continue
            # Prefer BUY over WATCH over AVOID if multiple rows for same ticker
            prev = decision_by_ticker.get(t)
            v = str(rec.get("verdict") or "").upper()
            prev_v = str((prev or {}).get("verdict") or "").upper()
            rank = {"BUY": 3, "WATCH": 2, "AVOID": 1}
            if prev is None or rank.get(v, 0) > rank.get(prev_v, 0):
                decision_by_ticker[t] = rec
        except Exception:
            continue

    caught = 0
    missed_list: list[dict] = []
    by_gate: dict[str, int] = {}

    for w in winners:
        t = w["ticker"]
        rec = decision_by_ticker.get(t)
        verdict = str((rec or {}).get("verdict") or "UNKNOWN").upper()
        if verdict == "BUY":
            caught += 1
            continue

        # Winner we didn't buy → determine blocking gate
        gates = (rec or {}).get("gates_hit") or []
        blocking = None
        if gates:
            blocking = str(gates[0])
        elif verdict == "UNKNOWN":
            blocking = "not_scanned"
        else:
            blocking = f"{verdict}_no_gate"

        by_gate[blocking] = by_gate.get(blocking, 0) + 1
        missed_list.append({
            "ticker": t,
            "return_pct": w["return_pct"],
            "verdict": verdict,
            "blocking_gate": blocking,
            "sector": w.get("sector"),
        })

    total = len(winners)
    missed = len(missed_list)
    recall = (caught / total) if total else 0.0

    # Sort by_gate desc
    by_gate_sorted = dict(sorted(by_gate.items(), key=lambda kv: kv[1], reverse=True))
    missed_list.sort(key=lambda m: m["return_pct"], reverse=True)

    return {
        "scan_date": d.isoformat(),
        "forward_days": forward_days,
        "winners": total,
        "caught": caught,
        "missed": missed,
        "recall_pct": round(recall * 100.0, 2),
        "by_gate": by_gate_sorted,
        "top_misses": missed_list[:10],
    }


def save_fn_report(scan_date: Optional[str] = None,
                   path: str = _DEFAULT_FN_PATH) -> None:
    """Compute false-negative report and persist as JSON."""
    if scan_date is None:
        scan_date = date.today().isoformat()

    try:
        report = categorize_missed_winners(scan_date)
    except Exception as e:
        log.error(f"save_fn_report: compute failed: {e}")
        report = {
            "scan_date": scan_date, "winners": 0, "caught": 0, "missed": 0,
            "recall_pct": 0.0, "by_gate": {}, "top_misses": [],
            "error": str(e),
        }

    try:
        report["generated_at"] = datetime.now().isoformat(timespec="seconds")
    except Exception:
        pass

    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, default=str)
        log.info(f"False-negative report written to {path} "
                 f"(winners={report.get('winners')}, recall={report.get('recall_pct')}%)")
    except Exception as e:
        log.error(f"Failed to write FN report: {e}")


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                        datefmt="%H:%M:%S")
    sd = sys.argv[1] if len(sys.argv) > 1 else None
    save_fn_report(sd)
    print(f"False-negative report saved to {_DEFAULT_FN_PATH}")

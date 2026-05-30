"""Live-bar feature extractor — produces the same 17-feature row at inference
time that ml/historical_backfill.py produced for training.

For a live ticker, we fetch recent EODHD bars (250d to cover all rolling
windows + 52w range) and compute features as of the most recent bar. This
makes mode-specific predictions truly native (model sees the same feature
distribution it was trained on), not a fudge over the legacy live-bundle
features which include categorical signals (regime/setup/entry_quality) we
deliberately excluded from historical training."""
from __future__ import annotations
import os
import sys
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import eodhd_client  # noqa: E402

FEATURE_COLS = [
    "ema8_dist", "ema21_dist", "ema50_dist", "ema200_dist",
    "sma20_dist", "sma50_dist", "sma200_dist",
    "rsi_14", "macd_hist_pct", "atr_pct", "rvol_20",
    "ret_5d", "ret_21d", "ret_63d",
    "dist_52w_high", "dist_52w_low",
    "rs_vs_spy_63d",
]

_spy_cache: pd.Series | None = None


def _bars_df(bars: list[dict]) -> pd.DataFrame | None:
    if not bars:
        return None
    df = pd.DataFrame(bars).rename(columns={"adjusted_close": "adj_close"})
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df["px"] = df["adj_close"].fillna(df["close"])
    return df


def _archive_bars_df(ticker: str) -> "pd.DataFrame | None":
    """Load bars from the daily scan's local Parquet archive (NO network call).

    The 06:30 scan runs ``data_archive.delta_update`` right before scanning, so
    ``data/ohlcv/{ticker}.parquet`` already holds today's fresh bars minutes
    before ML Edge runs. Reading it here avoids re-hitting the EODHD quota
    (which caused today's 402-on-SPY).

    The archive frame is date-INDEXED with capitalized OHLCV columns; this
    reshapes it to the EXACT shape ``_bars_df`` returns (a ``date`` *column*
    plus lowercase ``open/high/low/close/adj_close/volume`` and ``px``), so the
    downstream 17-feature math in ``_features_from_df`` is byte-for-byte
    identical regardless of source. Archive has no adjusted close, so ``px``
    falls back to ``close`` (same as ``_bars_df`` when ``adj_close`` is NaN).

    Returns None (caller falls back to ``eodhd_client.eod``) if the archive has
    no usable bars or on any error.
    """
    try:
        from data_archive import load_ticker as _archive_load
    except Exception:
        return None
    try:
        adf = _archive_load(ticker)
    except Exception:
        return None
    if adf is None or len(adf) == 0:
        return None
    try:
        df = adf.reset_index()
        # The archive index is unnamed → reset_index() yields an "index" col;
        # otherwise it carries the index name (usually "date" or "Date").
        idx_col = df.columns[0]
        df = df.rename(columns={
            idx_col: "date",
            "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Volume": "volume",
        })
        if "date" not in df.columns or "close" not in df.columns:
            return None
        df["date"] = pd.to_datetime(df["date"])
        if df["date"].dt.tz is not None:
            df["date"] = df["date"].dt.tz_localize(None)
        df = df.sort_values("date").reset_index(drop=True)
        # Archive carries no adjusted close → mirror _bars_df fallback semantics.
        df["adj_close"] = df.get("adj_close", df["close"])
        df["px"] = df["adj_close"].fillna(df["close"])
        # Guard: need the columns _features_from_df consumes.
        for col in ("high", "low", "volume", "px"):
            if col not in df.columns:
                return None
        return df
    except Exception:
        return None


def _spy_series() -> pd.Series:
    global _spy_cache
    if _spy_cache is not None:
        return _spy_cache
    # Prefer the scan's already-fetched bars (no network); fall back to EODHD.
    df = None
    try:
        df = _archive_bars_df("SPY")
    except Exception:
        df = None
    if df is None:
        today = datetime.utcnow().date()
        from_d = (today - timedelta(days=400)).isoformat()
        bars = eodhd_client.eod("SPY", from_date=from_d, to_date=today.isoformat())
        df = _bars_df(bars)
    _spy_cache = df.set_index("date")["px"] if df is not None else pd.Series(dtype=float)
    return _spy_cache


def _features_from_df(df: pd.DataFrame, spy_px: pd.Series) -> dict | None:
    """Compute the 17 features as of the LAST bar in df. Returns dict or None
    if any window is short (need ≥252 bars for 52w range)."""
    if len(df) < 252:
        return None
    px = df["px"]
    vol = df["volume"]

    df["ema8"]   = px.ewm(span=8,   adjust=False).mean()
    df["ema21"]  = px.ewm(span=21,  adjust=False).mean()
    df["ema50"]  = px.ewm(span=50,  adjust=False).mean()
    df["ema200"] = px.ewm(span=200, adjust=False).mean()
    sma20  = px.rolling(20).mean()
    sma50  = px.rolling(50).mean()
    sma200 = px.rolling(200).mean()

    # RSI 14
    delta = px.diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    rs    = gain / loss.replace(0, np.nan)
    df["rsi_14"] = 100 - (100 / (1 + rs))

    # MACD histogram (12,26,9) / price
    macd      = px.ewm(span=12, adjust=False).mean() - px.ewm(span=26, adjust=False).mean()
    macd_sig  = macd.ewm(span=9, adjust=False).mean()
    df["macd_hist_pct"] = (macd - macd_sig) / px

    # ATR 14 / px * 100
    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - px.shift(1)).abs()
    tr3 = (df["low"]  - px.shift(1)).abs()
    tr  = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["atr_pct"] = tr.rolling(14).mean() / px * 100

    df["rvol_20"] = vol / vol.rolling(20).mean()
    df["ret_5d"]  = px.pct_change(5)
    df["ret_21d"] = px.pct_change(21)
    df["ret_63d"] = px.pct_change(63)

    high_252 = df["high"].rolling(252).max()
    low_252  = df["low"].rolling(252).min()
    df["dist_52w_high"] = (high_252 - px) / px
    df["dist_52w_low"]  = (px - low_252)  / px

    # RS vs SPY (63d) — date-aligned merge
    spy = spy_px.reindex(df["date"]).reset_index(drop=True)
    spy_ret_63 = spy.pct_change(63)
    df["rs_vs_spy_63d"] = df["ret_63d"] - spy_ret_63

    df["ema8_dist"]   = (px - df["ema8"])   / px
    df["ema21_dist"]  = (px - df["ema21"])  / px
    df["ema50_dist"]  = (px - df["ema50"])  / px
    df["ema200_dist"] = (px - df["ema200"]) / px
    df["sma20_dist"]  = (px - sma20)  / px
    df["sma50_dist"]  = (px - sma50)  / px
    df["sma200_dist"] = (px - sma200) / px

    last = df[FEATURE_COLS].iloc[-1]
    if last.isna().any():
        return None
    return {c: float(last[c]) for c in FEATURE_COLS}


def extract_for_ticker(ticker: str) -> dict | None:
    """Returns a 17-feature dict for the latest bar of `ticker`, or None on failure."""
    # Prefer the scan's already-fetched bars (local Parquet archive, no network).
    # Only fall through to a live EODHD fetch if the archive has nothing usable.
    df = None
    try:
        df = _archive_bars_df(ticker)
    except Exception:
        df = None
    if df is None:
        today = datetime.utcnow().date()
        from_d = (today - timedelta(days=400)).isoformat()  # 400d covers 252+rolling
        try:
            bars = eodhd_client.eod(ticker, from_date=from_d, to_date=today.isoformat())
        except Exception:
            return None
        df = _bars_df(bars)
    if df is None:
        return None
    return _features_from_df(df, _spy_series())


def extract_batch(tickers: list[str]) -> dict[str, dict]:
    """Returns {ticker: features_dict | None}. Uses SPY cache once."""
    _spy_series()  # prewarm
    out = {}
    for tk in tickers:
        out[tk] = extract_for_ticker(tk)
    return out

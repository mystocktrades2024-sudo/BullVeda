"""pattern_data.py — shared mode-aware bar provider for the BullVeda Patterns lens.

Every pattern detector (Wyckoff, Elliott, Fibonacci, Volume Profile, …) reads
its bars from here so the SWING / POSITION / INVEST toggle drives the timeframe
uniformly:

    SWING       → daily bars, ~1 year      (2–15 day horizon)
    POSITION    → weekly bars, ~3 years     (1–6 month horizon)
    INVESTMENT  → monthly bars, ~12 years    (1–5 year horizon)

The detectors themselves are timeframe-agnostic — the same climax→range→spring
logic on weekly bars yields the position-horizon read automatically. All bars
are REAL (EODHD → Schwab → archive failover); weekly/monthly are resampled from
daily so one fetch serves every mode.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd

# mode → (calendar days to fetch, pandas resample rule or None, label, horizon)
_MODE_CFG = {
    "SWING":      {"days": 300,  "rule": None,    "tf": "Daily",   "horizon": "2–15d"},
    "POSITION":   {"days": 1150, "rule": "W-FRI", "tf": "Weekly",  "horizon": "1–6mo"},
    "INVESTMENT": {"days": 4500, "rule": "ME",    "tf": "Monthly", "horizon": "1–5yr"},
}
# accept lowercase / aliases
_MODE_ALIAS = {
    "swing": "SWING", "position": "POSITION", "invest": "INVESTMENT",
    "investment": "INVESTMENT", "INVEST": "INVESTMENT",
}


def norm_mode(mode: Optional[str]) -> str:
    if not mode:
        return "SWING"
    m = str(mode).strip()
    return _MODE_ALIAS.get(m, _MODE_ALIAS.get(m.lower(), m if m in _MODE_CFG else "SWING"))


def mode_meta(mode: str) -> Dict[str, Any]:
    cfg = _MODE_CFG[norm_mode(mode)]
    return {"tf": cfg["tf"], "horizon": cfg["horizon"], "mode": norm_mode(mode)}


def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["High"], df["Low"], df["Close"]
    pc = c.shift(1)
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(span=n, adjust=False).mean()


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    """Attach the shared per-bar features every detector reuses."""
    df = df.copy()
    df["spread"] = df["High"] - df["Low"]
    df["atr"] = _atr(df, 14)
    df["avgvol"] = df["Volume"].rolling(50, min_periods=10).mean()
    df["rvol"] = df["Volume"] / df["avgvol"]
    df["spread_atr"] = df["spread"] / df["atr"].replace(0, np.nan)
    rng = (df["High"] - df["Low"]).replace(0, np.nan)
    df["clv"] = (df["Close"] - df["Low"]) / rng           # close location value
    df["ema20"] = df["Close"].ewm(span=20, adjust=False).mean()
    df["ema50"] = df["Close"].ewm(span=50, adjust=False).mean()
    df = df.fillna({"rvol": 1.0, "spread_atr": 1.0, "clv": 0.5})
    return df


def _normalize_cols(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    ren = {}
    for c in df.columns:
        cl = str(c).lower()
        if cl in ("open", "o"):
            ren[c] = "Open"
        elif cl in ("high", "h"):
            ren[c] = "High"
        elif cl in ("low", "l"):
            ren[c] = "Low"
        elif cl in ("close", "c", "adjusted_close", "adj_close"):
            ren.setdefault(c, "Close")
        elif cl in ("volume", "v"):
            ren[c] = "Volume"
    df = df.rename(columns=ren)
    need = {"Open", "High", "Low", "Close", "Volume"}
    if not need.issubset(set(df.columns)):
        return None
    return df[["Open", "High", "Low", "Close", "Volume"]].dropna()


def get_bars(ticker: str, mode: str = "SWING", enriched: bool = True
             ) -> Tuple[Optional[pd.DataFrame], str, Dict[str, Any]]:
    """Real OHLCV at the timeframe implied by ``mode``. Returns (df, tier, meta).

    df is the resampled, optionally-enriched frame; tier ∈ {eodhd,schwab,archive,
    failed}; meta has {tf, horizon, mode}. df is None when no data is available.
    """
    mode = norm_mode(mode)
    cfg = _MODE_CFG[mode]
    meta = mode_meta(mode)
    try:
        from data_fetcher import fetch_ohlcv_with_failover
        df, tier = fetch_ohlcv_with_failover(ticker, days=cfg["days"])
    except Exception as e:  # pragma: no cover
        return None, f"error:{e}", meta
    if df is None or getattr(df, "empty", True) or len(df) < 24:
        return None, tier or "failed", meta

    df = _normalize_cols(df)
    if df is None or len(df) < 24:
        return None, "schema", meta

    # resample daily → weekly / monthly for position / invest
    rule = cfg["rule"]
    if rule:
        try:
            df = df.resample(rule).agg({"Open": "first", "High": "max", "Low": "min",
                                        "Close": "last", "Volume": "sum"}).dropna()
        except Exception:
            pass

    if len(df) < 24:
        return None, "short", meta
    if enriched:
        df = enrich(df)
    return df, tier, meta


def fmt_date(ts, tf: str = "Daily") -> str:
    """Date label appropriate to the timeframe (monthly → 'Mar '24')."""
    try:
        ts = pd.Timestamp(ts)
        if tf == "Monthly":
            return ts.strftime("%b '%y")
        return ts.strftime("%b %d")
    except Exception:
        return ""

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
    # SWING_4H — intraday entry-refinement for swing trades. Schwab 30-min bars
    # resampled to 4H (EODHD has no intraday). Daily stays the structure/bias TF;
    # this is the lower-timeframe entry view. Schwab-only (no EODHD failover).
    # SWING_1H — 1-hour intraday (Schwab 30-min resampled to 1H). Schwab-only.
    "SWING_1H":   {"days": 60,   "rule": None,    "tf": "1H",      "horizon": "1–5d",  "intraday": "1h"},
    "SWING_4H":   {"days": 150,  "rule": None,    "tf": "4H",      "horizon": "2–15d", "intraday": "4h"},
    "POSITION":   {"days": 1150, "rule": "W-FRI", "tf": "Weekly",  "horizon": "1–6mo"},
    "INVESTMENT": {"days": 4500, "rule": "ME",    "tf": "Monthly", "horizon": "1–5yr"},
}
# accept lowercase / aliases
_MODE_ALIAS = {
    "swing": "SWING", "position": "POSITION", "invest": "INVESTMENT",
    "investment": "INVESTMENT", "INVEST": "INVESTMENT",
    "1h": "SWING_1H", "1H": "SWING_1H", "swing_1h": "SWING_1H", "swing1h": "SWING_1H",
    "4h": "SWING_4H", "4H": "SWING_4H", "swing_4h": "SWING_4H", "swing4h": "SWING_4H",
}


def _fetch_intraday_resampled(ticker: str, days: int = 150, rule: str = "4h"
                              ) -> Tuple[Optional[pd.DataFrame], str]:
    """Schwab 30-min bars resampled to ``rule`` (e.g. 4H). Schwab is the ONLY
    intraday source (EODHD All-In-One has no intraday), so there is no failover —
    if Schwab fails the caller surfaces an honest 'intraday unavailable' state.
    Returns (df with lowercase OHLCV cols, tier)."""
    try:
        import time
        import schwab_client as sc
        now_ms = int(time.time() * 1000)
        start_ms = now_ms - int(days) * 86400 * 1000
        r = sc.get_pricehistory(ticker, period_type="day", frequency_type="minute",
                                frequency=30, start_date=start_ms, end_date=now_ms)
        candles = r.get("candles") if isinstance(r, dict) else None
        if not candles:
            return None, "schwab_empty"
        df = pd.DataFrame(candles)
        if "datetime" not in df.columns:
            return None, "schwab_schema"
        df["_dt"] = pd.to_datetime(df["datetime"], unit="ms")
        df = df.set_index("_dt").sort_index()
        agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
        have = {k: v for k, v in agg.items() if k in df.columns}
        df4 = df.resample(rule).agg(have).dropna()
        if df4.empty:
            return None, "schwab_empty"
        return df4, "schwab"
    except Exception as e:  # pragma: no cover
        return None, f"schwab_err:{e}"


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
    # Intraday (4H) path — Schwab-only, already resampled to the target rule.
    if cfg.get("intraday"):
        df, tier = _fetch_intraday_resampled(ticker, days=cfg["days"], rule=cfg["intraday"])
        if df is None or getattr(df, "empty", True):
            return None, tier or "failed", meta
        df = _normalize_cols(df)
        if df is None or len(df) < 24:
            return None, ("short" if df is not None else "schema"), meta
        if enriched:
            df = enrich(df)
        return df, tier, meta
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

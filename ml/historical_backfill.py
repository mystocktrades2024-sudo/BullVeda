"""Historical multi-horizon backfill for native swing/position/invest models.

For each ticker in infra/prototype/tickers.json (178 enriched names that match
the live inference universe), fetches full EODHD bar history (3 years), then
computes:
  - 18 pure-technical features per bar (EMA stack, RSI, MACD, ATR%, RS vs SPY,
    RVOL, returns_5/21/63d, sma-distances, 52w-range distances)
  - 3 forward-return labels: y_5d, y_21d, y_126d
And writes the row-level table to cache/ml/historical_backfill.json.

Trade-off: this uses a SIMPLER feature spec than the live model. We drop the
categorical features (regime4 / setup_family / entry_quality / catalyst_tier /
conviction_tier) because reconstructing them historically requires re-running
analysis.py against historical state — out of scope for v2. The replacement is
~50× more training data, which compensates for the smaller feature space."""
from __future__ import annotations
import json
import os
import sys
import time
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import eodhd_client  # noqa: E402
import data_fetcher  # noqa: E402

OUT = os.path.join(ROOT, "cache", "ml", "historical_backfill.json")

# How far back to fetch. Need at least 252 trading days + 126d label window
# + 200d feature warmup = ~580 calendar days minimum. Add buffer = 3y.
HISTORY_DAYS = 3 * 365


def _bars_to_df(bars: list[dict]) -> pd.DataFrame | None:
    if not bars:
        return None
    df = pd.DataFrame(bars).rename(columns={"adjusted_close": "adj_close"})
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    # use adjusted close where available (split/dividend safe)
    df["px"] = df["adj_close"].fillna(df["close"])
    return df


def _compute_features(df: pd.DataFrame, spy_px: pd.Series) -> pd.DataFrame:
    """Compute 18 technical features per bar — fully vectorized."""
    px = df["px"]
    vol = df["volume"]

    # EMAs
    df["ema8"]   = px.ewm(span=8,   adjust=False).mean()
    df["ema21"]  = px.ewm(span=21,  adjust=False).mean()
    df["ema50"]  = px.ewm(span=50,  adjust=False).mean()
    df["ema200"] = px.ewm(span=200, adjust=False).mean()
    df["ema8_dist"]   = (px - df["ema8"])   / px
    df["ema21_dist"]  = (px - df["ema21"])  / px
    df["ema50_dist"]  = (px - df["ema50"])  / px
    df["ema200_dist"] = (px - df["ema200"]) / px

    # SMAs (alternative form, used by Finviz pipeline elsewhere)
    sma20  = px.rolling(20).mean()
    sma50  = px.rolling(50).mean()
    sma200 = px.rolling(200).mean()
    df["sma20_dist"]  = (px - sma20)  / px
    df["sma50_dist"]  = (px - sma50)  / px
    df["sma200_dist"] = (px - sma200) / px

    # RSI 14
    delta = px.diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    rs    = gain / loss.replace(0, np.nan)
    df["rsi_14"] = 100 - (100 / (1 + rs))

    # MACD histogram (12,26,9), normalized by price
    macd      = px.ewm(span=12, adjust=False).mean() - px.ewm(span=26, adjust=False).mean()
    macd_sig  = macd.ewm(span=9, adjust=False).mean()
    df["macd_hist_pct"] = (macd - macd_sig) / px

    # ATR 14% (mean true range / price)
    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - px.shift(1)).abs()
    tr3 = (df["low"]  - px.shift(1)).abs()
    tr  = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["atr_pct"] = tr.rolling(14).mean() / px * 100

    # RVOL 20
    df["rvol_20"] = vol / vol.rolling(20).mean()

    # Forward-looking returns at 5/21/63d (LAGGED into the past — these are PAST returns)
    df["ret_5d"]  = px.pct_change(5)
    df["ret_21d"] = px.pct_change(21)
    df["ret_63d"] = px.pct_change(63)

    # 52w range distances
    high_252 = df["high"].rolling(252).max()
    low_252  = df["low"].rolling(252).min()
    df["dist_52w_high"] = (high_252 - px) / px
    df["dist_52w_low"]  = (px - low_252)  / px

    # Relative strength vs SPY (63d) — daily-aligned merge
    spy = spy_px.reindex(df["date"]).reset_index(drop=True)
    spy_ret_63 = spy.pct_change(63)
    df["rs_vs_spy_63d"] = df["ret_63d"] - spy_ret_63

    return df


def _compute_labels(df: pd.DataFrame) -> pd.DataFrame:
    """Forward returns at 5/21/126 trading days. Rows where any horizon is missing
    are dropped downstream by training."""
    px = df["px"]
    df["y_5d"]   = px.shift(-5)   / px - 1
    df["y_21d"]  = px.shift(-21)  / px - 1
    df["y_126d"] = px.shift(-126) / px - 1
    return df


# Raw per-ticker features
RAW_FEATURE_COLS = [
    "ema8_dist", "ema21_dist", "ema50_dist", "ema200_dist",
    "sma20_dist", "sma50_dist", "sma200_dist",
    "rsi_14", "macd_hist_pct", "atr_pct", "rvol_20",
    "ret_5d", "ret_21d", "ret_63d",
    "dist_52w_high", "dist_52w_low",
    "rs_vs_spy_63d",
]

# Cross-sectional percentile-rank features. Each row gets the rank of its
# feature value within ALL tickers on the same date (0..1). The model learns
# "ROST has the highest RSI among the universe TODAY" instead of "ROST's RSI
# is 72" — a much more informative signal because it normalizes for market-
# wide regimes (every stock has high RSI when SPY's running).
PCTRANK_BASE_COLS = [
    "rsi_14", "macd_hist_pct", "atr_pct", "rvol_20",
    "ret_5d", "ret_21d", "ret_63d",
    "dist_52w_high", "dist_52w_low", "rs_vs_spy_63d",
    "ema21_dist", "ema50_dist",
]
PCTRANK_COLS = [f"pctrank_{c}" for c in PCTRANK_BASE_COLS]
FEATURE_COLS = RAW_FEATURE_COLS + PCTRANK_COLS

LABEL_COLS = ["y_5d", "y_21d", "y_126d"]


def main():
    # Expanded universe — S&P 500 ∪ Russell 1000 = ~1,000 unique tickers.
    # 5× larger than the previous infra/prototype/tickers.json (178) which
    # was the enrichment-cache subset. More samples for the regression heads
    # and more cross-sectional context for the pct_rank features.
    sp500 = data_fetcher.get_sp500()
    r1000 = data_fetcher.get_russell1000()
    universe = sorted(set(sp500) | set(r1000))
    print(f"[backfill] universe: {len(universe)} tickers (S&P 500: {len(sp500)} ∪ R1000: {len(r1000)})")

    today = datetime.utcnow().date()
    from_date = (today - timedelta(days=HISTORY_DAYS)).isoformat()
    to_date   = today.isoformat()

    # SPY benchmark series (one fetch)
    spy_bars = eodhd_client.eod("SPY", from_date=from_date, to_date=to_date)
    if not spy_bars:
        raise RuntimeError("SPY bars unavailable — abort backfill")
    spy_df = _bars_to_df(spy_bars).set_index("date")["px"]
    print(f"[backfill] SPY bars: {len(spy_df)}")

    rows = []
    skipped = []
    t0 = time.time()
    for i, ticker in enumerate(universe):
        if (i + 1) % 25 == 0:
            print(f"[backfill] {i+1}/{len(universe)} ({ticker}) · rows so far: {len(rows)} · elapsed {time.time()-t0:.0f}s")
        try:
            bars = eodhd_client.eod(ticker, from_date=from_date, to_date=to_date)
            df = _bars_to_df(bars)
            if df is None or len(df) < 252 + 126:
                skipped.append((ticker, "too few bars"))
                continue
            df = _compute_features(df, spy_df)
            df = _compute_labels(df)
            df["ticker"] = ticker
            # Keep only rows where every RAW feature + every label is finite.
            # Cross-sectional pctrank features are added AFTER concat in the
            # orchestrator (we need all tickers on the same date to compute rank).
            keep = df[RAW_FEATURE_COLS + LABEL_COLS + ["date", "ticker"]].dropna()
            rows.append(keep)
        except Exception as e:
            skipped.append((ticker, str(e)[:80]))
    print(f"[backfill] fetch+compute complete in {time.time()-t0:.0f}s")
    print(f"[backfill] skipped: {len(skipped)} tickers")
    if skipped[:5]:
        for tk, reason in skipped[:5]:
            print(f"  {tk}: {reason}")

    big = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    print(f"[backfill] before cross-sectional rank: {big.shape}")
    if big.empty:
        raise RuntimeError("no rows produced — abort write")

    # Cross-sectional percentile-rank features — for each (date), rank every
    # ticker's feature value vs all OTHER tickers on the same date. Output is
    # in [0, 1]: 0.0 = lowest in universe, 1.0 = highest. This is what makes
    # "ROST has high RSI relative to its peers TODAY" learnable.
    t_rank = time.time()
    for col in PCTRANK_BASE_COLS:
        big[f"pctrank_{col}"] = big.groupby("date")[col].rank(pct=True, method="average")
    print(f"[backfill] pct_rank features computed in {time.time()-t_rank:.0f}s")
    # Drop the few rows where rank is NaN (date had <2 tickers)
    big = big.dropna(subset=PCTRANK_COLS)
    print(f"[backfill] after rank + dropna: {big.shape}")

    # Honest reporting on what made it through
    print(f"[backfill] date range: {big['date'].min().date()} → {big['date'].max().date()}")
    print(f"[backfill] tickers in final: {big['ticker'].nunique()}")
    print(f"[backfill] mean labels: y_5d={big['y_5d'].mean()*100:.2f}% y_21d={big['y_21d'].mean()*100:.2f}% y_126d={big['y_126d'].mean()*100:.2f}%")
    print(f"[backfill] label std:   y_5d={big['y_5d'].std()*100:.2f}% y_21d={big['y_21d'].std()*100:.2f}% y_126d={big['y_126d'].std()*100:.2f}%")

    # Serialize as JSON records (sub-50MB, simple, no extra deps)
    big["date"] = big["date"].dt.strftime("%Y-%m-%d")
    payload = {
        "_meta": {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "n_rows":   int(len(big)),
            "n_tickers":int(big["ticker"].nunique()),
            "date_min": big["date"].min(),
            "date_max": big["date"].max(),
            "feature_cols": FEATURE_COLS,
            "label_cols":   LABEL_COLS,
            "skipped":     [{"ticker": t, "reason": r} for t, r in skipped],
        },
        "rows": big.to_dict(orient="records"),
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(payload, f, default=str)
    size_mb = os.path.getsize(OUT) / 1024 / 1024
    print(f"[backfill] wrote {OUT} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()

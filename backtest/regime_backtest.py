"""
Regime backtester — validate that the 4-regime classifier actually segments
forward returns. Principle 18: "Regime detection IS the strategy. Fund/test
the regime classifier 10× more rigorously than any individual setup."

For each historical day, classify the regime using only as-of-date data
(no leakage), then measure SPY forward returns over 5d / 10d / 20d horizons.
Aggregate per regime → Wilson CI, mean, median, Sharpe-proxy, sample size.

If `risk_on_trending` does not show materially better forward returns than
`risk_on_choppy`, the regime classifier is providing no edge and the entire
4-regime apparatus is theatre.

v1 caveats (documented, not hidden):
  - Breadth proxied from SPY 1-month return until v2 wires bulk_eod %above50d.
  - Hysteresis applied as currently configured (vix_risk_off_enter=22 etc.).
  - Forward-return basket is SPY only; v2 should add equal-weight basket (RSP).

Usage:
    python3 backtest/regime_backtest.py --years 5
    python3 backtest/regime_backtest.py --years 10 --out cache/regime_backtest_10y.json
"""
from __future__ import annotations

import sys
import json
import math
import argparse
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable

import pandas as pd
import numpy as np

# Make project root importable regardless of where this is invoked from
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import eodhd_client  # noqa: E402
import data_fetcher as _df_mod  # noqa: E402  (reuse get_sp500 dot/dash convention)


# ── Config defaults (mirror data_fetcher.get_market_regime + config.regime_hysteresis) ──

DEFAULT_HYSTERESIS = {
    "vix_risk_off_enter": 22.0,
    "vix_risk_on_return": 18.0,
    "breadth_bullish_enter": 53.0,
    "breadth_bearish_enter": 47.0,
}

DEFAULT_THRESHOLDS = {
    "panic_vix": 35.0,
    "panic_breadth": 20.0,
    "trending_vix": 18.0,
    "trending_breadth": 65.0,
    "risk_off_consecutive_closes": 1,  # 1 = current behavior (single-bar trigger)
}


# ── Data loading ────────────────────────────────────────────────────────────

def fetch_history(years: int = 5) -> dict[str, pd.DataFrame]:
    end = date.today()
    start = end - timedelta(days=int(years * 365.25) + 60)
    out: dict[str, pd.DataFrame] = {}
    for sym in ("SPY", "QQQ", "VIX"):
        bars = eodhd_client.eod(sym, from_date=start.isoformat(), to_date=end.isoformat())
        if not bars:
            raise RuntimeError(f"Failed to load {sym} EOD history")
        df = pd.DataFrame(bars)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        for col in ("open", "high", "low", "close", "adjusted_close", "volume"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        out[sym] = df
    return out


# ── Real breadth (v2): % of S&P 500 constituents above their 50d MA ─────────

_BREADTH_CACHE = _ROOT / "cache" / "breadth_history_5y.parquet"


def fetch_breadth_real(years: int = 5, index: str = "GSPC",
                       force_refresh: bool = False) -> pd.Series:
    """
    Compute %above50d historical series from S&P 500 constituents.

    Survivorship caveat (principle 6): uses CURRENT constituent list against
    historical prices. Apply ~-3pp WR haircut on derived stats. Wikipedia
    point-in-time membership wiring is a separate effort.

    Caches the final series to cache/breadth_history_5y.parquet — second
    invocation is effectively instant.
    """
    if not force_refresh and _BREADTH_CACHE.exists():
        try:
            cached = pd.read_parquet(_BREADTH_CACHE)["breadth_real"]
            # If cache covers the requested window and is fresh (<1d old), reuse
            cache_age_h = (date.today() - cached.index[-1].date()).days * 24
            if cache_age_h < 24:
                return cached
        except Exception:
            pass

    print(f"[regime-backtest] Fetching {index} constituents...")
    tickers = _df_mod.get_sp500()  # dot/dash-normalized via repo helper
    if not tickers or len(tickers) < 100:
        raise RuntimeError(f"Failed to load {index} constituents (got {len(tickers) if tickers else 0})")
    print(f"  {len(tickers)} tickers in {index}")

    end = date.today()
    start = end - timedelta(days=int(years * 365.25) + 60)
    print(f"[regime-backtest] Pulling 5y daily history for {len(tickers)} constituents (cached after first run)...")

    series_by_ticker: dict[str, pd.Series] = {}
    failed = 0
    for i, t in enumerate(tickers, 1):
        if i % 50 == 0:
            print(f"  progress: {i}/{len(tickers)} ({failed} failed)")
        try:
            bars = eodhd_client.eod(t, from_date=start.isoformat(), to_date=end.isoformat())
            if not bars:
                failed += 1
                continue
            df = pd.DataFrame(bars)
            df["date"] = pd.to_datetime(df["date"])
            s = df.set_index("date")["close"].astype(float).sort_index()
            series_by_ticker[t] = s
        except Exception:
            failed += 1
            continue

    print(f"  fetched {len(series_by_ticker)} / {len(tickers)} ({failed} failed)")
    if len(series_by_ticker) < 100:
        raise RuntimeError(f"Insufficient constituents fetched: {len(series_by_ticker)}")

    prices = pd.DataFrame(series_by_ticker).sort_index()
    sma50 = prices.rolling(50, min_periods=50).mean()
    above = prices > sma50
    breadth = (above.sum(axis=1) / above.notna().sum(axis=1) * 100).rename("breadth_real")
    breadth = breadth.dropna()

    _BREADTH_CACHE.parent.mkdir(parents=True, exist_ok=True)
    breadth.to_frame().to_parquet(_BREADTH_CACHE)
    print(f"[regime-backtest] Cached breadth series → {_BREADTH_CACHE} ({len(breadth)} dates)")
    return breadth


# ── Classifier (mirrors data_fetcher.get_market_regime, no leakage) ─────────

def classify_replay(
    spy: pd.DataFrame,
    qqq: pd.DataFrame,
    vix: pd.DataFrame,
    *,
    hysteresis: dict | None = None,
    thresholds: dict | None = None,
    breadth_source: str = "spy_1m_proxy",
    breadth_real: pd.Series | None = None,
) -> pd.DataFrame:
    """
    Replay the regime classifier day-by-day. For row at date t, all inputs
    are computed from data <= t (no look-ahead).
    """
    hyst = {**DEFAULT_HYSTERESIS, **(hysteresis or {})}
    thr = {**DEFAULT_THRESHOLDS, **(thresholds or {})}

    spy = spy.copy()
    spy["ema50"] = spy["close"].ewm(span=50, adjust=False).mean()
    spy["sma200"] = spy["close"].rolling(200).mean()

    qqq = qqq.copy()
    qqq["ema50"] = qqq["close"].ewm(span=50, adjust=False).mean()

    df = pd.DataFrame(index=spy.index)
    df["spy_close"] = spy["close"]
    df["spy_ema50"] = spy["ema50"]
    df["spy_sma200"] = spy["sma200"]
    df["spy_above_ema50"] = spy["close"] > spy["ema50"]
    df["spy_above_sma200"] = spy["close"] > spy["sma200"]
    # Consecutive-close confirmation for risk_off_trending. With n=1 this is
    # identical to the current single-bar trigger; n=2 requires 2 consecutive
    # closes below EMA50 before flipping risk-off.
    n_below = int(thr.get("risk_off_consecutive_closes", 1))
    if n_below > 1:
        df["spy_below_ema50_streak"] = (
            (~df["spy_above_ema50"]).astype(int)
            .groupby((df["spy_above_ema50"]).cumsum()).cumsum()
        )
        df["risk_off_confirmed"] = df["spy_below_ema50_streak"] >= n_below
    else:
        df["risk_off_confirmed"] = ~df["spy_above_ema50"]
    df["qqq_above_ema50"] = (qqq["close"] > qqq["ema50"]).reindex(df.index, method="ffill")
    df["vix"] = vix["close"].reindex(df.index, method="ffill")

    if breadth_source == "spy_1m_proxy":
        # v1 proxy: scaled SPY 1-month return. Used when real breadth is unavailable.
        spy_1m = spy["close"].pct_change(21) * 100
        df["breadth"] = (50 + spy_1m * 2.5).clip(0, 100)
    elif breadth_source == "real":
        if breadth_real is None:
            raise ValueError("breadth_source='real' requires breadth_real series")
        df["breadth"] = breadth_real.reindex(df.index, method="ffill")
    else:
        raise NotImplementedError(f"breadth_source={breadth_source!r} not yet wired")

    regimes = []
    prev = "risk_on_choppy"
    for ts, row in df.iterrows():
        vix_cur = row["vix"]
        breadth = row["breadth"]
        above_50 = bool(row["spy_above_ema50"])
        above_200 = bool(row["spy_above_sma200"])
        qqq_above = bool(row["qqq_above_ema50"]) if pd.notna(row["qqq_above_ema50"]) else True

        is_off = prev in ("risk_off_trending", "panic")
        is_on = prev == "risk_on_trending"

        vix_thresh_on = hyst["vix_risk_on_return"] if is_off else thr["trending_vix"]
        breadth_for_bull = hyst["breadth_bullish_enter"] if not is_on else 50.0

        risk_off_confirmed = bool(row["risk_off_confirmed"])

        if pd.notna(vix_cur) and vix_cur > thr["panic_vix"]:
            r = "panic"
        elif pd.notna(breadth) and breadth < thr["panic_breadth"]:
            r = "panic"
        elif risk_off_confirmed:
            r = "risk_off_trending"
        elif (above_50 and above_200 and qqq_above
              and pd.notna(vix_cur) and vix_cur < vix_thresh_on
              and pd.notna(breadth) and breadth > max(thr["trending_breadth"], breadth_for_bull)):
            r = "risk_on_trending"
        else:
            r = "risk_on_choppy"

        regimes.append(r)
        prev = r

    df["regime4"] = regimes
    return df


# ── Forward returns + statistics ────────────────────────────────────────────

def attach_forward_returns(spy: pd.DataFrame, regime_df: pd.DataFrame,
                           horizons: Iterable[int] = (5, 10, 20)) -> pd.DataFrame:
    df = regime_df.copy()
    for h in horizons:
        df[f"fwd_{h}d"] = (spy["close"].shift(-h) / spy["close"] - 1.0) * 100.0
    return df


def wilson_lb(wins: int, total: int, z: float = 1.96) -> float:
    if total <= 0:
        return 0.0
    p = wins / total
    n = total
    denom = 1.0 + z * z / n
    centre = p + z * z / (2.0 * n)
    margin = z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n))
    return max(0.0, (centre - margin) / denom)


def aggregate_by_regime(df: pd.DataFrame, horizons: Iterable[int] = (5, 10, 20)) -> dict:
    results: dict = {}
    total_days = len(df)
    for regime in ("risk_on_trending", "risk_on_choppy", "risk_off_trending", "panic"):
        sub = df[df["regime4"] == regime]
        n = len(sub)
        if n == 0:
            continue
        per_regime = {
            "n_days": n,
            "pct_of_period": round(n / total_days * 100, 1),
        }
        for h in horizons:
            col = f"fwd_{h}d"
            r = sub[col].dropna()
            if r.empty:
                continue
            wins = int((r > 0).sum())
            mean = float(r.mean())
            std = float(r.std()) if len(r) > 1 else 0.0
            sharpe = (mean / std * math.sqrt(252 / h)) if std > 0 else 0.0
            per_regime[f"h{h}"] = {
                "n": int(len(r)),
                "mean_pct": round(mean, 2),
                "median_pct": round(float(r.median()), 2),
                "std_pct": round(std, 2),
                "wr_pct": round(wins / len(r) * 100, 1),
                "wr_lb_pct": round(wilson_lb(wins, len(r)) * 100, 1),
                "sharpe_proxy": round(sharpe, 2),
                "min_pct": round(float(r.min()), 2),
                "max_pct": round(float(r.max()), 2),
            }
        results[regime] = per_regime
    return results


def regime_run_stats(df: pd.DataFrame) -> dict:
    """Run-length analysis: average duration per regime, whipsaw count."""
    df = df.copy()
    df["regime_change"] = df["regime4"] != df["regime4"].shift()
    df["regime_id"] = df["regime_change"].cumsum()
    runs = df.groupby(["regime_id", "regime4"]).size().reset_index(name="duration_days")
    out: dict = {}
    for regime in runs["regime4"].unique():
        durs = runs[runs["regime4"] == regime]["duration_days"]
        out[regime] = {
            "n_runs": int(len(durs)),
            "mean_duration_days": round(float(durs.mean()), 1),
            "median_duration_days": float(durs.median()),
            "min_duration_days": int(durs.min()),
            "max_duration_days": int(durs.max()),
            "whipsaws_under_3d": int((durs < 3).sum()),
        }
    return out


# ── Reporting ───────────────────────────────────────────────────────────────

def _print_summary(rf: pd.DataFrame, forward: dict, durations: dict) -> None:
    print()
    print("=== REGIME FORWARD-RETURN BACKTEST ===")
    print(f"Period: {rf.index[0].date()} → {rf.index[-1].date()} ({len(rf)} trading days)")
    print(f"Breadth source: SPY 1m return proxy (v1 — bulk_eod %above50d pending)")
    print()
    header = f"{'Regime':<22}{'Days':>7}{'%P':>6}{'5d µ':>8}{'5d WR':>8}{'5d LB':>8}{'10d µ':>9}{'10d WR':>9}{'20d µ':>9}{'Sharpe':>9}"
    print(header)
    print("-" * len(header))
    for regime in ("risk_on_trending", "risk_on_choppy", "risk_off_trending", "panic"):
        if regime not in forward:
            continue
        d = forward[regime]
        h5 = d.get("h5", {})
        h10 = d.get("h10", {})
        h20 = d.get("h20", {})
        print(f"{regime:<22}{d['n_days']:>7}{d['pct_of_period']:>6.1f}"
              f"{h5.get('mean_pct', float('nan')):>8.2f}{h5.get('wr_pct', float('nan')):>8.1f}{h5.get('wr_lb_pct', float('nan')):>8.1f}"
              f"{h10.get('mean_pct', float('nan')):>9.2f}{h10.get('wr_pct', float('nan')):>9.1f}"
              f"{h20.get('mean_pct', float('nan')):>9.2f}"
              f"{h10.get('sharpe_proxy', float('nan')):>9.2f}")
    print()
    print("Regime run lengths (whipsaw audit):")
    for regime, d in durations.items():
        print(f"  {regime:<22} runs={d['n_runs']:>4}  mean={d['mean_duration_days']:>5.1f}d  median={d['median_duration_days']:>4.0f}d  whipsaws<3d={d['whipsaws_under_3d']:>3}  max={d['max_duration_days']}d")
    print()
    print("Edge interpretation:")
    h10s = {r: forward[r].get("h10", {}).get("sharpe_proxy") for r in forward}
    on_t = h10s.get("risk_on_trending")
    on_c = h10s.get("risk_on_choppy")
    if on_t is not None and on_c is not None:
        diff = on_t - on_c
        verdict = "STRONG SEPARATION" if diff > 0.5 else "MODERATE" if diff > 0.2 else "WEAK / NO EDGE"
        print(f"  risk_on_trending Sharpe(10d) - risk_on_choppy Sharpe(10d) = {diff:+.2f}  →  {verdict}")
    print()


# ── Variant comparison ─────────────────────────────────────────────────────

# Each variant is (name, thresholds_override, hysteresis_override).
# Hypotheses tied to baseline findings:
#   V1 — fixes risk_off whipsaws (most important)
#   V2 — loosens trending entry (currently fires only 2.8% of days)
#   V3 — tightens panic VIX threshold (rarely fires anyway)
#   V4 — combined V1 + V2 (the candidate fix)
#   V5 — V4 + 3-bar SPY/EMA50 confirmation (more conservative)
DEFAULT_VARIANTS = [
    ("baseline",       {}, {}),
    ("V1_2bar_riskoff", {"risk_off_consecutive_closes": 2}, {}),
    ("V2_loose_trend",  {"trending_breadth": 60.0, "trending_vix": 20.0}, {}),
    ("V3_no_breadth_panic", {"panic_breadth": 0.0}, {}),
    ("V4_2bar+loose",   {"risk_off_consecutive_closes": 2, "trending_breadth": 60.0, "trending_vix": 20.0}, {}),
    ("V5_3bar+loose",   {"risk_off_consecutive_closes": 3, "trending_breadth": 60.0, "trending_vix": 20.0}, {}),
]


def run_variant(data: dict, name: str, thr_override: dict, hyst_override: dict,
                horizons: tuple = (5, 10, 20),
                breadth_source: str = "spy_1m_proxy",
                breadth_real: pd.Series | None = None) -> dict:
    rf = classify_replay(
        data["SPY"], data["QQQ"], data["VIX"],
        thresholds=thr_override or None,
        hysteresis=hyst_override or None,
        breadth_source=breadth_source,
        breadth_real=breadth_real,
    )
    rf = attach_forward_returns(data["SPY"], rf, horizons=horizons)
    forward = aggregate_by_regime(rf, horizons=horizons)
    durations = regime_run_stats(rf)

    # Aggregate "tradeable days" (anything except panic) and their forward stats
    tradeable_long = rf[rf["regime4"].isin(["risk_on_trending", "risk_on_choppy"])]
    h = horizons[1] if len(horizons) > 1 else horizons[0]
    col = f"fwd_{h}d"
    rl = tradeable_long[col].dropna()
    long_wr = (rl > 0).sum() / len(rl) * 100 if len(rl) else 0.0
    long_lb = wilson_lb(int((rl > 0).sum()), len(rl)) * 100 if len(rl) else 0.0
    return {
        "name": name,
        "thr_override": thr_override,
        "hyst_override": hyst_override,
        "regime_distribution": {k: int(v) for k, v in rf["regime4"].value_counts().items()},
        "forward_returns_by_regime": forward,
        "regime_run_stats": durations,
        "long_eligible_days": int(len(tradeable_long)),
        "long_eligible_pct": round(len(tradeable_long) / len(rf) * 100, 1),
        f"long_eligible_{h}d_wr": round(long_wr, 1),
        f"long_eligible_{h}d_wr_lb": round(long_lb, 1),
    }


def _print_variant_table(results: list[dict]) -> None:
    print()
    print("=== VARIANT COMPARISON (5y backtest, SPY 10d forward returns) ===")
    print()
    hdr = (f"{'Variant':<22}{'TrendDays':>10}{'TrendWR':>9}{'TrendLB':>9}"
           f"{'ChoppyDays':>11}{'ChoppyWR':>10}{'OffDays':>9}{'OffMean':>9}"
           f"{'OffRuns':>9}{'OffWhip':>9}"
           f"{'EligDays':>10}{'EligWR':>9}{'EligLB':>9}")
    print(hdr)
    print("-" * len(hdr))
    for r in results:
        fwd = r["forward_returns_by_regime"]
        runs = r["regime_run_stats"]
        t = fwd.get("risk_on_trending", {}).get("h10", {})
        c = fwd.get("risk_on_choppy", {}).get("h10", {})
        o = fwd.get("risk_off_trending", {}).get("h10", {})
        oruns = runs.get("risk_off_trending", {})
        line = (
            f"{r['name']:<22}"
            f"{fwd.get('risk_on_trending', {}).get('n_days', 0):>10}"
            f"{t.get('wr_pct', float('nan')):>9.1f}"
            f"{t.get('wr_lb_pct', float('nan')):>9.1f}"
            f"{fwd.get('risk_on_choppy', {}).get('n_days', 0):>11}"
            f"{c.get('wr_pct', float('nan')):>10.1f}"
            f"{fwd.get('risk_off_trending', {}).get('n_days', 0):>9}"
            f"{o.get('mean_pct', float('nan')):>9.2f}"
            f"{oruns.get('n_runs', 0):>9}"
            f"{oruns.get('whipsaws_under_3d', 0):>9}"
            f"{r['long_eligible_days']:>10}"
            f"{r['long_eligible_10d_wr']:>9.1f}"
            f"{r['long_eligible_10d_wr_lb']:>9.1f}"
        )
        print(line)
    print()
    print("Reading the table:")
    print("  TrendDays = how often risk_on_trending fires (higher = classifier is reachable)")
    print("  EligWR    = win rate on all long-eligible (trending+choppy) days, 10d horizon")
    print("  EligLB    = Wilson lower-bound on EligWR — this is what the system inherits")
    print("  OffWhip   = risk_off runs <3 days (whipsaws — fewer is better)")
    print()


# ── CLI ─────────────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--years", type=int, default=5, help="History years to backfill (default 5)")
    p.add_argument("--out", default="cache/regime_backtest_latest.json")
    p.add_argument("--horizons", default="5,10,20", help="Comma-separated forward-return horizons in trading days")
    p.add_argument("--variants", action="store_true", help="Run baseline + threshold variants and compare")
    p.add_argument("--breadth-source", choices=("proxy", "real"), default="proxy",
                   help="proxy = SPY 1m return scaled (fast); real = %above50d from SP500 constituents (slower first run, then cached)")
    p.add_argument("--refresh-breadth", action="store_true", help="Force re-fetch of constituent breadth (ignore parquet cache)")
    args = p.parse_args()

    horizons = tuple(int(x) for x in args.horizons.split(","))

    print(f"[regime-backtest] Pulling {args.years}y of SPY/QQQ/VIX from EODHD...")
    data = fetch_history(args.years)
    print(f"  SPY: {len(data['SPY'])} bars · {data['SPY'].index[0].date()} → {data['SPY'].index[-1].date()}")
    print(f"  QQQ: {len(data['QQQ'])} bars")
    print(f"  VIX: {len(data['VIX'])} bars")

    breadth_real: pd.Series | None = None
    breadth_source = "spy_1m_proxy" if args.breadth_source == "proxy" else "real"
    if args.breadth_source == "real":
        breadth_real = fetch_breadth_real(years=args.years, force_refresh=args.refresh_breadth)
        print(f"  Real breadth series: {len(breadth_real)} dates · "
              f"{breadth_real.index[0].date()} → {breadth_real.index[-1].date()} "
              f"(current value: {breadth_real.iloc[-1]:.1f})")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if args.variants:
        print(f"[regime-backtest] Running {len(DEFAULT_VARIANTS)} variants...")
        results = [
            run_variant(data, name, thr, hyst, horizons,
                        breadth_source=breadth_source, breadth_real=breadth_real)
            for (name, thr, hyst) in DEFAULT_VARIANTS
        ]
        payload = {
            "as_of": str(data["SPY"].index[-1].date()),
            "period_start": str(data["SPY"].index[0].date()),
            "period_end": str(data["SPY"].index[-1].date()),
            "n_bars": int(len(data["SPY"])),
            "horizons": list(horizons),
            "variants": results,
            "breadth_source": breadth_source,
        }
        out_path.write_text(json.dumps(payload, indent=2, default=str))
        print(f"[regime-backtest] Wrote {out_path}")
        _print_variant_table(results)
        return 0

    print("[regime-backtest] Replaying classifier day-by-day (no leakage)...")
    rf = classify_replay(
        data["SPY"], data["QQQ"], data["VIX"],
        breadth_source=breadth_source, breadth_real=breadth_real,
    )
    rf = attach_forward_returns(data["SPY"], rf, horizons=horizons)

    print("[regime-backtest] Aggregating forward returns by regime...")
    forward = aggregate_by_regime(rf, horizons=horizons)
    durations = regime_run_stats(rf)

    payload = {
        "as_of": str(rf.index[-1].date()),
        "period_start": str(rf.index[0].date()),
        "period_end": str(rf.index[-1].date()),
        "n_bars": int(len(rf)),
        "years_requested": args.years,
        "horizons": list(horizons),
        "thresholds": DEFAULT_THRESHOLDS,
        "hysteresis": DEFAULT_HYSTERESIS,
        "breadth_source": breadth_source,
        "breadth_caveat": (
            "Proxied from SPY 1m return * 2.5 + 50 (v1 default)" if breadth_source == "spy_1m_proxy"
            else "Real %above50d from current SP500 constituents — survivorship caveat applies (principle 6)."
        ),
        "regime_distribution": {k: int(v) for k, v in rf["regime4"].value_counts().items()},
        "forward_returns_by_regime": forward,
        "regime_run_stats": durations,
    }
    out_path.write_text(json.dumps(payload, indent=2, default=str))
    print(f"[regime-backtest] Wrote {out_path}")

    _print_summary(rf, forward, durations)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
Tier-1 Historical Backfill (S-1 unblock)

Replays Tier-1 detectors against the OHLCV that was available at each
signal_log entry's date, then correlates detector points with realized outcome.

Output:
  - cache/tier1_backfill.json — per-signal: {detector_name: points} + realized R
  - Console summary — per-detector: trigger rate, hit rate, avg R-multiple

This unblocks S-1 (apply_to_score: false → true): with 200+ replayed signals,
we can statistically validate whether each detector adds vs subtracts edge.

Run:
  python3 tier1_backfill.py
"""
from __future__ import annotations
import json
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path
import pandas as pd

BASE = Path(__file__).parent
SIGNAL_LOG = BASE / "data" / "signal_log.json"
OHLCV_DIR = BASE / "data" / "ohlcv"
OUT_PATH = BASE / "cache" / "tier1_backfill.json"


def _load_ohlcv(ticker: str) -> pd.DataFrame | None:
    """Load OHLCV parquet; return None if missing or unreadable."""
    p = OHLCV_DIR / f"{ticker}.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
        # Normalize column names
        df.columns = [c.capitalize() if c.lower() in ("open","high","low","close","volume") else c for c in df.columns]
        return df.sort_index()
    except Exception:
        return None


def _slice_at(df: pd.DataFrame, sig_date: str, lookback_bars: int = 60) -> pd.DataFrame | None:
    """Return df slice ending at sig_date with at least lookback_bars history."""
    try:
        ts = pd.to_datetime(sig_date)
        sub = df[df.index <= ts]
        if len(sub) < lookback_bars:
            return None
        return sub.tail(lookback_bars + 5)
    except Exception:
        return None


def _r_multiple(sig: dict) -> float | None:
    pnl = sig.get("actual_pnl_pct")
    e = sig.get("entry_price"); s = sig.get("stop")
    if pnl is None or not e or not s: return None
    risk_pct = (e - s) / e * 100 if e else None
    if not risk_pct or risk_pct <= 0: return None
    return pnl / risk_pct


def backfill(min_history: int = 30) -> dict:
    """Run all Tier-1 detectors against each closed signal in signal_log."""
    import tier1_signals as t1

    log = json.loads(SIGNAL_LOG.read_text())
    closed = [s for s in log if s.get("status") == "CLOSED"]
    print(f"Closed signals: {len(closed)}")

    # Detector name → list of (points, r_multiple)
    by_det = defaultdict(list)
    # Triggered events: detector → list of {ticker, date, points, r}
    detail = defaultdict(list)
    skipped = 0
    processed = 0

    ohlcv_cache: dict = {}

    for sig in closed:
        tk = sig.get("ticker"); sig_date = sig.get("date")
        if not tk or not sig_date:
            skipped += 1; continue

        if tk not in ohlcv_cache:
            ohlcv_cache[tk] = _load_ohlcv(tk)
        df = ohlcv_cache[tk]
        if df is None:
            skipped += 1; continue

        df_at = _slice_at(df, sig_date, lookback_bars=min_history)
        if df_at is None:
            skipped += 1; continue

        r = _r_multiple(sig)
        if r is None:
            skipped += 1; continue

        # Run detectors. NR7 / vol_dryup / OBV / cup / spring need OHLCV only.
        # Mean-reversion needs RSI + above_200sma; we approximate from OHLCV here.
        from ta.momentum import RSIIndicator
        try:
            rsi = float(RSIIndicator(df_at["Close"], window=14).rsi().iloc[-1])
        except Exception:
            rsi = 50.0
        ema200 = df_at["Close"].rolling(200).mean()
        try:
            above_200 = bool(df_at["Close"].iloc[-1] > ema200.iloc[-1])
        except Exception:
            above_200 = False
        try:
            atr_series = (df_at["High"] - df_at["Low"]).rolling(14).mean()
            atr_pct = float((atr_series.iloc[-1] / df_at["Close"].iloc[-1]) * 100)
        except Exception:
            atr_pct = 3.0
        ema21 = df_at["Close"].rolling(21).mean().iloc[-1] if len(df_at) >= 21 else None
        ema50 = df_at["Close"].rolling(50).mean().iloc[-1] if len(df_at) >= 50 else None

        # Lower-case Close column needed for some detectors
        df_lc = df_at.copy()
        df_lc.columns = [c.lower() for c in df_lc.columns]

        # Detectors:
        last5_chg = None
        if len(df_at) >= 6:
            last5_chg = float((df_at["Close"].iloc[-1] - df_at["Close"].iloc[-6]) / df_at["Close"].iloc[-6])

        results = {
            "nr7":         t1.nr7_inside_day(df_at),
            "vol_dryup":   t1.volume_dryup_at_support(df_at, ema21=ema21, ema50=ema50),
            "obv_div":     t1.obv_divergence(df_at),
            "mean_rev":    t1.mean_reversion_setup(rsi, above_200, fund_score=4.0, atr_pct=atr_pct, last5_close_chg=last5_chg),
            "cup_handle":  t1.cup_with_handle(df_at),
            "spring":      t1.failed_breakdown_spring(df_at),
            # insider_cluster + beat_raise need other data we don't have at sig date — skip
        }
        for det_name, det_out in results.items():
            pts = det_out.get("points", 0) if isinstance(det_out, dict) else 0
            if pts != 0:
                by_det[det_name].append((pts, r))
                detail[det_name].append({
                    "ticker": tk, "date": sig_date, "points": pts,
                    "r": round(r, 2), "narrative": det_out.get("narrative", "")[:80],
                })
        processed += 1

    print(f"Processed: {processed}, skipped: {skipped}")

    # Aggregate per detector
    summary = {}
    for det_name in ["nr7", "vol_dryup", "obv_div", "mean_rev", "cup_handle", "spring"]:
        rows = by_det.get(det_name, [])
        if not rows:
            summary[det_name] = {"n": 0, "trigger_rate": 0,
                                 "avg_r": None, "median_r": None, "win_rate": None,
                                 "interpretation": "no triggers in 210-trade history"}
            continue
        pts = [p for p, _ in rows]
        rs  = [r for _, r in rows]
        wins = sum(1 for r in rs if r > 0)
        avg_r = statistics.mean(rs)
        med_r = statistics.median(rs)
        wr = wins / len(rs) * 100
        # Verdict: if avg_r > 0.5 → keep, < 0 → drop, between → marginal
        verdict = ("STRONG_KEEP — high avg R" if avg_r >= 1.0 else
                   "KEEP — positive edge" if avg_r >= 0.5 else
                   "MARGINAL — flat or noise" if avg_r >= 0 else
                   "DROP — negative edge")
        summary[det_name] = {
            "n":             len(rows),
            "trigger_rate":  round(len(rows) / max(1, processed) * 100, 1),
            "avg_points":    round(statistics.mean(pts), 2),
            "avg_r":         round(avg_r, 2),
            "median_r":      round(med_r, 2),
            "win_rate":      round(wr, 1),
            "interpretation": verdict,
        }

    overall = {
        "processed":    processed,
        "skipped":      skipped,
        "total_signals_in_log": len(closed),
        "computed_at":  datetime.now().isoformat(),
        "by_detector":  summary,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps({"summary": overall, "detail": dict(detail)}, indent=2, default=str))

    # Console report
    print(f"\n{'─'*72}")
    print(f"Tier-1 Detector Validation — {processed} historical signals replayed")
    print(f"{'─'*72}")
    print(f"{'Detector':14} {'N':>4} {'Trig%':>6} {'AvgR':>6} {'WR%':>6}  Verdict")
    print(f"{'─'*72}")
    for det_name, s in summary.items():
        if s["n"] == 0:
            print(f"  {det_name:12} {s['n']:>4}  {s['trigger_rate']!s:>5}     —      —    {s['interpretation']}")
        else:
            print(f"  {det_name:12} {s['n']:>4}  {s['trigger_rate']:>5.1f}  {s['avg_r']:>+6.2f}  {s['win_rate']:>5.1f}  {s['interpretation']}")
    print(f"{'─'*72}")
    print(f"\nDetailed per-trigger log: {OUT_PATH}")

    # Recommendation for S-1 flip
    print(f"\nS-1 (apply_to_score: false → true) recommendation:")
    keep_dets = [d for d, s in summary.items() if s["n"] >= 10 and (s["avg_r"] or 0) >= 0.5]
    drop_dets = [d for d, s in summary.items() if s["n"] >= 10 and (s["avg_r"] or 0) < 0]
    if keep_dets:
        print(f"  ✓ FLIP TO TRUE for: {', '.join(keep_dets)}")
    if drop_dets:
        print(f"  ✗ KEEP FALSE (or invert) for: {', '.join(drop_dets)}")
    if not keep_dets and not drop_dets:
        print(f"  ⚠ Insufficient triggers (need n≥10 per detector). Continue running scans to gather more.")
    return overall


if __name__ == "__main__":
    backfill()

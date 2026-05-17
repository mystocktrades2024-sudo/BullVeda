#!/usr/bin/env python3
"""
snapshot_iv.py — daily ATM IV snapshot for IV-rank computation.

Schwab gives current IV per chain. Computing proper iv_rank requires
252 days of historical ATM IV. This script captures one snapshot per
ticker per day, building the history over time.

Storage:
  data/iv_history.jsonl  — append-only, one entry per ticker per day:
    {date: 'YYYY-MM-DD', ticker: 'AAPL', current_iv: 49.7, ts: <epoch>}

Usage:
  - Cron: daily 3:30pm PT (just before close, IVs settled)
  - Manual: python3 snapshot_iv.py

After 30+ days of history, compute_iv_rank() returns a 30-day rolling
rank (0-100). At 252+ days, we get proper Bloomberg-style IV rank.
"""
from __future__ import annotations
import json
import logging
import sys
import time
from datetime import datetime, date
from pathlib import Path

BASE = Path(__file__).resolve().parent
LOG_FILE = BASE / "cache" / "logs" / "snapshot_iv.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
HISTORY_FILE = BASE / "data" / "iv_history.jsonl"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [snapshot_iv] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


def _load_universe(top_n: int = 200) -> list[str]:
    """Universe = top-N by screener score UNION refresh_options_flow.OPTIONS_LIQUID_SEED.

    2026-05-15 · Same fix as refresh_options_flow.py — IV history must cover
    the high-options-liquidity names (AAPL/NVDA/SPY/etc) regardless of whether
    the screener flags them as setups. Otherwise iv_rank computation has gaps
    for the most-traded names.
    """
    bundle_path = BASE / "cache" / "last_bundle.json"
    try:
        from refresh_options_flow import OPTIONS_LIQUID_SEED as _seed
    except Exception:
        _seed = []
    if not bundle_path.exists():
        log.warning("No bundle — falling back to OPTIONS_LIQUID_SEED only")
        return list(dict.fromkeys(_seed))
    bundle = json.loads(bundle_path.read_text())
    candidates: dict[str, float] = {}
    for sec in ("buy_candidates", "watch_list", "all_scored", "medium_term_picks", "long_term_picks"):
        items = bundle.get(sec) or []
        if not isinstance(items, list):
            continue
        for r in items:
            if not isinstance(r, dict): continue
            t = r.get("ticker")
            if not t: continue
            score = float(r.get("score") or r.get("composite_score") or 0)
            candidates[t] = max(candidates.get(t, 0), score)
    ranked = sorted(candidates.items(), key=lambda kv: -kv[1])
    screener_top = [t for t, _ in ranked[:top_n]]
    seen = set(screener_top)
    out = list(screener_top)
    for t in _seed:
        if t not in seen:
            out.append(t); seen.add(t)
    return out


def _already_snapshotted_today(today_str: str) -> set[str]:
    """Read existing history; return set of (ticker) already captured today."""
    if not HISTORY_FILE.exists():
        return set()
    seen = set()
    try:
        for line in HISTORY_FILE.read_text().splitlines():
            line = line.strip()
            if not line: continue
            try:
                e = json.loads(line)
                if e.get("date") == today_str:
                    seen.add(e.get("ticker"))
            except Exception:
                continue
    except Exception:
        pass
    return seen


def main() -> int:
    today = date.today().isoformat()
    tickers = _load_universe(top_n=200)
    if not tickers:
        log.error("No universe to snapshot")
        return 1

    already = _already_snapshotted_today(today)
    todo = [t for t in tickers if t not in already]
    if not todo:
        log.info(f"All {len(tickers)} tickers already snapshotted today ({today})")
        return 0

    log.info(f"Snapshotting IV for {len(todo)} tickers (skipping {len(already)} already done)")

    from data_fetcher import get_options_iv_data
    captured = 0
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY_FILE.open("a") as out:
        for t in todo:
            try:
                r = get_options_iv_data(t)
                iv = r.get("current_iv")
                if iv is None:
                    continue
                entry = {
                    "date":       today,
                    "ticker":     t,
                    "current_iv": float(iv),
                    "ts":         int(time.time()),
                }
                out.write(json.dumps(entry) + "\n")
                captured += 1
            except Exception as e:
                log.debug(f"snapshot {t} failed: {e}")
    log.info(f"Captured IV for {captured}/{len(todo)} tickers")
    return 0


def compute_iv_rank(ticker: str, current_iv: float | None = None,
                     window_days: int = 252) -> dict:
    """
    Compute IV rank from accumulated history.
    Returns {iv_rank: 0-100, iv_pct: 0-100, history_days: N, ready: bool}.

    iv_rank = (current_iv - 252d_low) / (252d_high - 252d_low) × 100
    iv_pct  = percentile of current_iv within the 252d distribution

    Falls back to shorter window if <window_days history available
    (with `ready: False` flag).
    """
    if not HISTORY_FILE.exists():
        return {"iv_rank": None, "iv_pct": None, "history_days": 0, "ready": False}
    samples: list[float] = []
    today_iv = current_iv
    try:
        from datetime import datetime as _dt, timedelta
        cutoff = (_dt.now() - timedelta(days=window_days)).strftime("%Y-%m-%d")
        for line in HISTORY_FILE.read_text().splitlines():
            line = line.strip()
            if not line: continue
            try:
                e = json.loads(line)
            except Exception:
                continue
            if e.get("ticker") != ticker:
                continue
            if e.get("date", "") < cutoff:
                continue
            iv = e.get("current_iv")
            if iv is not None:
                samples.append(float(iv))
                today_iv = today_iv if today_iv is not None else float(iv)  # latest as fallback
    except Exception:
        pass
    n = len(samples)
    if n < 5 or today_iv is None:
        return {"iv_rank": None, "iv_pct": None, "history_days": n, "ready": False}
    lo, hi = min(samples), max(samples)
    rank = ((today_iv - lo) / (hi - lo) * 100) if hi > lo else 50
    pct = (sum(1 for x in samples if x <= today_iv) / n * 100)
    return {
        "iv_rank":      round(rank, 1),
        "iv_pct":       round(pct, 1),
        "history_days": n,
        "ready":        n >= 30,  # 30 days = minimal usable rolling rank
    }


if __name__ == "__main__":
    sys.exit(main())

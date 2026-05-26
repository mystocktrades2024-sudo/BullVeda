#!/usr/bin/env python3
"""
momentum_snapshot_backfill.py — synthesize historical momentum snapshots from
data/decision_log.jsonl so the Momentum HISTORY calibration block has data
immediately (instead of waiting 5+ trading days for organic snapshots from
the live momentum_snapshot.py path).

Mirrors the live writer schema in momentum_snapshot.py exactly so
momentum_history_api.build_momentum_history() consumes both interchangeably.
Each backfilled row gets `_synthetic: true` for transparency.

Per CLAUDE.md principle 1 (statistical rigor — surface n + caveats),
11 (edge erosion — calibration window starts now, not in 5 days),
20 (process > outcome — preserve decision_log provenance via _synthetic flag).

Usage:
  python3 scripts/momentum_snapshot_backfill.py                     # default --days 30
  python3 scripts/momentum_snapshot_backfill.py --days 60
  python3 scripts/momentum_snapshot_backfill.py --from-date 2026-04-15 --to-date 2026-05-24
  python3 scripts/momentum_snapshot_backfill.py --top-n 25 --force
  python3 scripts/momentum_snapshot_backfill.py --dry-run
"""
from __future__ import annotations
import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo("America/Los_Angeles")
except Exception:  # pragma: no cover
    _TZ = timezone(timedelta(hours=-8))

BASE_DIR = Path(__file__).resolve().parent.parent
DECISION_LOG = BASE_DIR / "data" / "decision_log.jsonl"
OUT_PATH = BASE_DIR / "data" / "momentum_snapshots.jsonl"
DEFAULT_TOP_N = 20

# Mirror live writer's setup-level alpha attribution
_ZERO_ALPHA_SETUPS = ["trend continuation", "breakout expansion"]
_ALPHA_SETUPS = ["vcp", "52w breakout", "52wk breakout", "10wp", "10 week pullback"]


def _today_pt() -> str:
    return datetime.now(_TZ).strftime("%Y-%m-%d")


def _parse(d: str):
    try:
        return datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=_TZ)
    except Exception:
        return None


def _sleeve_from_setup(setup_type: str) -> dict:
    """
    Synthesize sleeve from decision_log's setup_type field.
    Mirrors the spirit of momentum_snapshot._sleeve_of but using only fields
    that exist in decision_log (we don't have the *_audit dicts here).
    """
    s = str(setup_type or "")
    sl = s.lower()
    if "pead" in sl:
        return {"code": "esp", "label": "ESP Play"}
    if "insider" in sl:
        return {"code": "ins", "label": "Insider Cluster"}
    if "mean rev" in sl or "meanrev" in sl or "mean reversion" in sl:
        return {"code": "mrv", "label": "Mean Reversion"}
    if "defensive" in sl or "defrot" in sl:
        return {"code": "def", "label": "Defensive Rotation"}
    if s in {"Trend Continuation", "Breakout Expansion", "Impulse Catalyst", "Momentum"} \
            or any(k in sl for k in ("trend continuation", "breakout expansion",
                                     "impulse catalyst", "momentum")):
        return {"code": "mom", "label": "Mom Continuation"}
    return {"code": "pb", "label": "Pullback to Value"}


def _alpha_flag_from_setup(setup_type: str) -> str:
    s = str(setup_type or "").lower()
    if any(z in s for z in _ZERO_ALPHA_SETUPS):
        return "zero_alpha"
    if any(a in s for a in _ALPHA_SETUPS):
        return "alpha"
    return "neutral"


def _passes_momentum_filter(row: dict) -> bool:
    """
    Decision-log-only proxy for QuantMomentum._isMomentumCandidate:
      verdict in {BUY, WATCH, WAIT} AND direction=='long'
      AND (rs_rank >= 60 OR score >= 65)
    """
    verdict = str(row.get("verdict") or "").upper()
    if verdict not in {"BUY", "WATCH", "WAIT"}:
        return False
    direction = str(row.get("direction") or "").lower()
    if direction != "long":
        return False
    try:
        rs = float(row.get("rs_rank") or 0)
    except Exception:
        rs = 0.0
    try:
        sc = float(row.get("score") or 0)
    except Exception:
        sc = 0.0
    return rs >= 60 or sc >= 65


def _load_decision_log() -> list[dict]:
    if not DECISION_LOG.exists():
        return []
    rows: list[dict] = []
    with open(DECISION_LOG) as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                rows.append(json.loads(ln))
            except Exception:
                continue
    return rows


def _load_existing_pairs() -> tuple[set[str], set[tuple[str, str]]]:
    """Return (dates_present, (date,ticker) pairs present) from OUT_PATH."""
    dates: set[str] = set()
    pairs: set[tuple[str, str]] = set()
    if not OUT_PATH.exists():
        return dates, pairs
    with open(OUT_PATH) as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                o = json.loads(ln)
            except Exception:
                continue
            d = o.get("date")
            tk = o.get("ticker")
            if d:
                dates.add(d)
            if d and tk:
                pairs.add((d, str(tk).upper()))
    return dates, pairs


def _build_row(date: str, rank: int, src: dict) -> dict:
    """Construct a snapshot row matching momentum_snapshot.py schema EXACTLY."""
    sleeve = _sleeve_from_setup(src.get("setup_type"))
    try:
        score = float(src.get("score") or 0)
    except Exception:
        score = 0.0
    try:
        rs = float(src.get("rs_rank") or 0)
    except Exception:
        rs = 0.0
    try:
        price = float(src.get("entry_price") or 0)
    except Exception:
        price = 0.0
    return {
        "date": date,
        "ticker": str(src.get("ticker") or "").upper(),
        "rank": rank,
        # Composite proxy: use score (0-100) directly since decision_log
        # doesn't carry sharpe_126d / adx. _synthetic flag flags this caveat.
        "composite": round(score, 4),
        "sharpe_126d": None,
        "sharpe_1y": None,
        "rs_rank": rs,
        "score": score,
        "verdict": str(src.get("verdict") or "").upper(),
        "sleeve": sleeve["label"],
        "sleeve_code": sleeve["code"],
        "alpha_flag": _alpha_flag_from_setup(src.get("setup_type")),
        "setup": str(src.get("setup_type") or ""),
        "sector": None,
        "price": price,
        "ema_signal": None,
        "adx": None,
        "trend": None,
        "_synthetic": True,
        "_written_at": datetime.now(_TZ).isoformat(timespec="seconds"),
    }


def backfill(days: int = 30,
             from_date: str | None = None,
             to_date: str | None = None,
             top_n: int = DEFAULT_TOP_N,
             dry_run: bool = False,
             force: bool = False) -> dict:
    """
    Returns a dict {dates_processed, dates_skipped, rows_written, rows_skipped,
    from_date, to_date, sample_dates} for reporting.
    """
    today = _today_pt()
    today_dt = _parse(today)
    if from_date and to_date:
        lo = from_date
        hi = to_date
    else:
        hi = today
        lo = (today_dt - timedelta(days=days)).strftime("%Y-%m-%d") if today_dt else today

    raw = _load_decision_log()
    if not raw:
        return {"status": "skip", "reason": "decision_log empty/missing",
                "dates_processed": 0, "rows_written": 0}

    # Group decision-log rows by date, applying the momentum filter
    by_date: dict[str, list[dict]] = defaultdict(list)
    for r in raw:
        d = r.get("date")
        if not d or d < lo or d > hi:
            continue
        if not _passes_momentum_filter(r):
            continue
        by_date[d].append(r)

    if not by_date:
        return {"status": "skip", "reason": f"no momentum-eligible rows in {lo}..{hi}",
                "dates_processed": 0, "rows_written": 0, "from_date": lo, "to_date": hi}

    existing_dates, existing_pairs = _load_existing_pairs()

    rows_to_write: list[dict] = []
    dates_processed = 0
    dates_skipped = 0
    rows_skipped_dup = 0
    sample_dates: list[str] = []

    for d in sorted(by_date.keys()):
        if (not force) and d in existing_dates:
            dates_skipped += 1
            continue
        # Sort by score desc, take top-N
        candidates = sorted(by_date[d], key=lambda r: float(r.get("score") or 0), reverse=True)
        chosen = candidates[:top_n]
        seen_in_day: set[str] = set()
        for rank, src in enumerate(chosen, start=1):
            tk = str(src.get("ticker") or "").upper()
            if not tk or tk in seen_in_day:
                continue
            if (not force) and (d, tk) in existing_pairs:
                rows_skipped_dup += 1
                continue
            seen_in_day.add(tk)
            rows_to_write.append(_build_row(d, rank, src))
        dates_processed += 1
        if len(sample_dates) < 5:
            sample_dates.append(d)

    if dry_run:
        return {
            "status": "dry_run",
            "dates_processed": dates_processed,
            "dates_skipped": dates_skipped,
            "rows_written": 0,
            "rows_would_write": len(rows_to_write),
            "rows_skipped_dup": rows_skipped_dup,
            "from_date": lo,
            "to_date": hi,
            "sample_dates": sample_dates,
        }

    if rows_to_write:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(OUT_PATH, "a") as f:
            for row in rows_to_write:
                f.write(json.dumps(row, default=str) + "\n")

    return {
        "status": "ok",
        "dates_processed": dates_processed,
        "dates_skipped": dates_skipped,
        "rows_written": len(rows_to_write),
        "rows_skipped_dup": rows_skipped_dup,
        "from_date": lo,
        "to_date": hi,
        "sample_dates": sample_dates,
        "out_path": str(OUT_PATH),
    }


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days", type=int, default=30,
                   help="Days back from today (default 30; ignored if --from-date/--to-date)")
    p.add_argument("--from-date", type=str, default=None, help="YYYY-MM-DD lower bound")
    p.add_argument("--to-date", type=str, default=None, help="YYYY-MM-DD upper bound")
    p.add_argument("--top-n", type=int, default=DEFAULT_TOP_N,
                   help=f"Max rows per date (default {DEFAULT_TOP_N})")
    p.add_argument("--dry-run", action="store_true",
                   help="Show what WOULD be written, do not modify the file")
    p.add_argument("--force", action="store_true",
                   help="Overwrite even when (date,ticker) already exists")
    args = p.parse_args(argv)

    if bool(args.from_date) != bool(args.to_date):
        print("ERROR: --from-date and --to-date must be used together", file=sys.stderr)
        return 2

    res = backfill(
        days=args.days,
        from_date=args.from_date,
        to_date=args.to_date,
        top_n=args.top_n,
        dry_run=args.dry_run,
        force=args.force,
    )
    print(json.dumps(res, indent=2))

    if res.get("status") == "ok" and res.get("rows_written"):
        print("\nNext: bust the 1hr cache so /api/momentum-history sees backfilled rows:")
        print("  curl -u 'gari:Swing2026' 'http://localhost:7432/api/momentum-history?fresh=1' | head -c 200")

    return 0 if res.get("status") in {"ok", "dry_run", "skip"} else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

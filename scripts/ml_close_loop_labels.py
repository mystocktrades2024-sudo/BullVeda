#!/usr/bin/env python3
"""
ml_close_loop_labels.py — close the loop on ML predictions.

Walks cache/ml_edge_picks_history.jsonl, finds pending picks whose
horizon has elapsed (entry_date + horizon_days trading days ≤ today),
fetches realized closing prices from EODHD, computes:
    realized_pct = (exit_close - entry_close) / entry_close * 100
    realized_r   = realized_pct / (atr_pct or 1.0)
    status       = "resolved"

Writes the updated file back atomically. Idempotent — re-runs only touch
the picks still in pending state.

Output:
    cache/ml_edge_picks_history.jsonl   (updated in place)
    cache/ml/close_loop_report.json     (run summary)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import eodhd_client  # noqa: E402

PICKS_PATH   = ROOT / "cache" / "ml_edge_picks_history.jsonl"
REPORT_PATH  = ROOT / "cache" / "ml" / "close_loop_report.json"
HORIZON_BY_MODE = {"swing": 5, "position": 21, "invest": 126}


def _load_picks() -> list[dict]:
    rows: list[dict] = []
    if not PICKS_PATH.exists():
        return rows
    with open(PICKS_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _write_picks(rows: list[dict]) -> None:
    tmp = PICKS_PATH.with_suffix(".jsonl.tmp")
    with open(tmp, "w") as f:
        for r in rows:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")
    os.replace(tmp, PICKS_PATH)


def _trading_days_after(start: date, n: int) -> date:
    return start + timedelta(days=int(n * 1.45) + 2)


def _resolve_pick(pick: dict, today: date, max_age_days: int) -> tuple[bool, str, dict]:
    if pick.get("status") != "pending":
        return False, "not_pending", pick

    mode = pick.get("mode", "swing")
    horizon = pick.get("horizon_days") or HORIZON_BY_MODE.get(mode, 5)
    scan_date_str = pick.get("scan_date")
    if not scan_date_str:
        return False, "no_scan_date", pick
    try:
        scan_dt = datetime.fromisoformat(scan_date_str).date()
    except ValueError:
        return False, "bad_scan_date", pick

    age = (today - scan_dt).days
    if age < int(horizon * 1.45):
        return False, "too_fresh", pick
    if age > max_age_days:
        return False, "too_stale_skip", pick

    ticker = pick.get("ticker")
    if not ticker:
        return False, "no_ticker", pick

    target_exit = _trading_days_after(scan_dt, horizon + 1)
    from_date = scan_dt.isoformat()
    to_date = min(target_exit + timedelta(days=5), today).isoformat()

    bars = eodhd_client.eod(ticker, from_date=from_date, to_date=to_date)
    if not bars or len(bars) < 2:
        return False, "no_bars", pick

    entry_bar = None
    entry_date = None
    for b in bars:
        bd = b.get("date")
        if not bd:
            continue
        try:
            d = datetime.fromisoformat(bd).date()
        except ValueError:
            continue
        if d >= scan_dt:
            entry_bar = b
            entry_date = d
            break
    if entry_bar is None:
        return False, "no_entry_bar", pick

    entry_idx = bars.index(entry_bar)
    exit_idx = min(entry_idx + horizon, len(bars) - 1)
    exit_bar = bars[exit_idx]

    try:
        entry_close = float(entry_bar.get("adjusted_close") or entry_bar.get("close"))
        exit_close  = float(exit_bar.get("adjusted_close")  or exit_bar.get("close"))
    except (TypeError, ValueError):
        return False, "bad_close", pick
    if entry_close <= 0:
        return False, "bad_entry_price", pick

    realized_pct = (exit_close - entry_close) / entry_close * 100.0
    if pick.get("side") == "short":
        realized_pct = -realized_pct

    atr_pct = pick.get("atr") or 0
    realized_r = realized_pct / atr_pct if atr_pct else None

    pick.update({
        "status":         "resolved",
        "entry_date":     entry_date.isoformat(),
        "entry_close":    round(entry_close, 4),
        "exit_date":      exit_bar.get("date"),
        "exit_price":     round(exit_close, 4),
        "realized_pct":   round(realized_pct, 4),
        "realized_r":     round(realized_r, 4) if realized_r is not None else None,
        "resolved_at":    datetime.now(timezone.utc).isoformat(),
        "resolved_by":    "ml_close_loop_labels",
    })
    return True, "ok", pick


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-age-days", type=int, default=400)
    args = ap.parse_args()

    rows = _load_picks()
    if not rows:
        print(f"[close-loop] {PICKS_PATH} empty or missing — nothing to resolve")
        return

    today = date.today()
    reasons: dict[str, int] = {}
    resolved_count = 0
    by_mode = {"swing": 0, "position": 0, "invest": 0}
    started = time.time()

    for i, pick in enumerate(rows):
        did, reason, updated = _resolve_pick(pick, today, args.max_age_days)
        reasons[reason] = reasons.get(reason, 0) + 1
        if did:
            rows[i] = updated
            resolved_count += 1
            by_mode[updated.get("mode", "?")] = by_mode.get(updated.get("mode", "?"), 0) + 1

    elapsed = round(time.time() - started, 1)
    if not args.dry_run and resolved_count > 0:
        _write_picks(rows)

    report = {
        "ran_at":          datetime.now(timezone.utc).isoformat(),
        "today":           today.isoformat(),
        "rows_total":      len(rows),
        "resolved_now":    resolved_count,
        "by_mode":         by_mode,
        "skipped_reasons": reasons,
        "elapsed_sec":     elapsed,
        "dry_run":         args.dry_run,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)

    print(f"[close-loop] resolved {resolved_count} of {len(rows)} picks ({elapsed}s)")
    print(f"[close-loop] by_mode: {by_mode}")
    print(f"[close-loop] reasons: {reasons}")
    if args.dry_run:
        print("[close-loop] DRY RUN — no file written")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
options_flow_outcomes.py — Daily/scheduled outcome tracker for options-flow picks.

Reads cache/options_flow_history.jsonl (one line per pick logged by
refresh_options_flow.py at snapshot time) and walks each pick's price
history after the pick date to determine the realized outcome:

  - target_hit  : price >= target within HORIZON_DAYS (default 21)
  - stop_hit    : price <= stop within horizon (only counts if hit BEFORE target)
  - expired     : neither — pick stays open past horizon, treat as flat
  - open        : not enough days elapsed yet (snap_date + horizon > today)

Computes per-pick:
  - outcome (str)
  - days_to_outcome (int)
  - realized_return_pct (final close vs entry price)
  - mfe_pct  (max favorable excursion)
  - mae_pct  (max adverse excursion)

Writes cache/options_flow_outcomes.jsonl (append-only; idempotent — skips
picks already resolved).

Run via launchd nightly OR on-demand:
    python3 scripts/options_flow_outcomes.py [--horizon 21] [--rebuild]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))


def _load_history(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def _load_outcomes(path: Path) -> dict:
    """key = snap_date + '|' + ticker → outcome row."""
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            k = (row.get("snap_date") or "") + "|" + (row.get("ticker") or "")
            out[k] = row
        except Exception:
            continue
    return out


def _resolve_outcome(pick: dict, bars: list, horizon_days: int) -> dict | None:
    """Walk OHLCV bars from snap_date forward up to horizon_days. Return outcome."""
    entry = float(pick.get("price") or 0)
    target = float(pick.get("target") or 0)
    stop = float(pick.get("stop") or 0)
    if not entry or not target or not stop:
        return None
    snap_date = pick.get("snap_date") or ""
    if not snap_date:
        return None
    # Filter bars after snap_date, sorted asc
    forward = sorted(
        [b for b in bars if isinstance(b, dict) and (b.get("date") or "") > snap_date],
        key=lambda x: x.get("date") or ""
    )[:horizon_days]
    if not forward:
        return {"outcome": "open", "days_elapsed": 0}
    mfe = 0.0  # max favorable
    mae = 0.0  # max adverse
    outcome = None
    days_to = None
    last_close = entry
    for i, bar in enumerate(forward):
        h = float(bar.get("high") or 0)
        l = float(bar.get("low") or 0)
        c = float(bar.get("close") or 0)
        if h > 0:
            mfe = max(mfe, (h - entry) / entry * 100)
        if l > 0:
            mae = min(mae, (l - entry) / entry * 100)
        # Check stop first (conservative — if both touched in same session, stop counts)
        if stop > 0 and l > 0 and l <= stop and outcome is None:
            outcome = "stop_hit"
            days_to = i + 1
        # Then target
        if target > 0 and h > 0 and h >= target and outcome is None:
            outcome = "target_hit"
            days_to = i + 1
        last_close = c or last_close
        if outcome:
            break
    if outcome is None:
        # No level touched in horizon — treat as expired
        if len(forward) >= horizon_days:
            outcome = "expired"
            days_to = horizon_days
        else:
            outcome = "open"
            days_to = len(forward)
    realized_return = (last_close - entry) / entry * 100 if entry else 0.0
    return {
        "outcome": outcome,
        "days_to_outcome": days_to,
        "realized_return_pct": round(realized_return, 2),
        "mfe_pct": round(mfe, 2),
        "mae_pct": round(mae, 2),
        "horizon_days": horizon_days,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, default=21,
                        help="Days to wait before declaring 'expired' (default 21)")
    parser.add_argument("--rebuild", action="store_true",
                        help="Re-resolve already-tracked outcomes (default skips)")
    parser.add_argument("--max-age-days", type=int, default=180,
                        help="Skip picks older than this (default 180)")
    args = parser.parse_args()

    hist_path = BASE / "cache" / "options_flow_history.jsonl"
    out_path = BASE / "cache" / "options_flow_outcomes.jsonl"

    history = _load_history(hist_path)
    if not history:
        print(f"No history at {hist_path} — nothing to resolve")
        return 0

    existing = _load_outcomes(out_path) if not args.rebuild else {}
    print(f"Loaded {len(history)} history rows, {len(existing)} already resolved")

    # Group picks by ticker so we fetch OHLCV once per ticker
    by_ticker: dict[str, list[dict]] = {}
    for p in history:
        tk = (p.get("ticker") or "").upper()
        if not tk: continue
        # Skip already-resolved picks unless rebuild
        k = (p.get("snap_date") or "") + "|" + tk
        if k in existing and existing[k].get("outcome") not in ("open", None):
            continue
        # Skip too-old picks
        try:
            d = datetime.strptime(p.get("snap_date") or "", "%Y-%m-%d")
            if (datetime.now() - d).days > args.max_age_days: continue
        except Exception:
            continue
        by_ticker.setdefault(tk, []).append(p)

    print(f"To resolve: {sum(len(v) for v in by_ticker.values())} picks across {len(by_ticker)} tickers")

    try:
        import eodhd_client as eod
    except ImportError:
        print("ERROR: eodhd_client not importable")
        return 1

    resolved_rows = []
    today = datetime.now().strftime("%Y-%m-%d")
    for tk, picks in by_ticker.items():
        earliest = min(p.get("snap_date") or today for p in picks)
        try:
            bars = eod.eod(tk, from_date=earliest, to_date=today, period="d") or []
        except Exception as e:
            print(f"  {tk}: eod fetch failed — {type(e).__name__}: {str(e)[:80]}")
            continue
        if not bars:
            continue
        for p in picks:
            res = _resolve_outcome(p, bars, args.horizon)
            if not res: continue
            row = {**p, **res, "resolved_at": datetime.now(timezone.utc).isoformat()}
            resolved_rows.append(row)

    # Append-only write — re-write the whole file with non-stale + new rows
    print(f"Resolved {len(resolved_rows)} picks")
    if resolved_rows:
        all_rows = list(existing.values()) if not args.rebuild else []
        for r in resolved_rows:
            k = (r.get("snap_date") or "") + "|" + (r.get("ticker") or "")
            # Drop any prior version of this key
            all_rows = [x for x in all_rows
                        if (x.get("snap_date") or "") + "|" + (x.get("ticker") or "") != k]
            all_rows.append(r)
        all_rows.sort(key=lambda x: (x.get("snap_date") or "", x.get("ticker") or ""))
        out_path.write_text("\n".join(json.dumps(r, default=str) for r in all_rows) + "\n")
        print(f"Wrote {len(all_rows)} rows to {out_path}")

        # Summary
        from collections import Counter
        outcomes = Counter(r.get("outcome") for r in all_rows)
        print(f"\nOutcome summary:")
        for k, v in sorted(outcomes.items(), key=lambda x: -x[1]):
            pct = v / len(all_rows) * 100 if all_rows else 0
            print(f"  {k}: {v} ({pct:.1f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

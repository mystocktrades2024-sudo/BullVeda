#!/usr/bin/env python3
"""
backfill_earnings_outcomes.py
─────────────────────────────
Joins earnings_prediction_log.jsonl → earnings_outcomes.jsonl on
(ticker, report_date) and fills in realized_outcome + realized_surprise_pct
for any row that has already reported.

Run:
    python3 scripts/backfill_earnings_outcomes.py

Idempotent — rows already filled are skipped.  Prints a one-line summary.
"""

import json
import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PRED_LOG  = BASE / "data" / "earnings_prediction_log.jsonl"
OUTCOMES  = BASE / "data" / "earnings_outcomes.jsonl"
SURPRISE_BEAT_THRESHOLD  =  1.0   # surprise_pct > +1% → BEAT
SURPRISE_MISS_THRESHOLD  = -1.0   # surprise_pct < -1% → MISS


def _classify(surprise_pct, beat_flag):
    """Return BEAT / MISS / INLINE from raw outcome fields."""
    # Explicit beat flag first (some sources set this directly)
    if beat_flag is not None:
        b = str(beat_flag).strip().upper()
        if b in ("TRUE", "1", "BEAT", "YES"):
            return "BEAT"
        if b in ("FALSE", "0", "MISS", "NO"):
            return "MISS"
    # Derive from surprise_pct
    if surprise_pct is not None:
        try:
            sp = float(surprise_pct)
        except (TypeError, ValueError):
            return None
        if sp > SURPRISE_BEAT_THRESHOLD:
            return "BEAT"
        if sp < SURPRISE_MISS_THRESHOLD:
            return "MISS"
        return "INLINE"
    return None


def main():
    if not PRED_LOG.exists():
        print("backfill_earnings_outcomes: prediction log not found — nothing to do")
        return
    if not OUTCOMES.exists():
        print("backfill_earnings_outcomes: outcomes file not found — nothing to do")
        return

    today = datetime.date.today().isoformat()

    # Build outcome lookup: (TICKER, report_date) → outcome row
    outcome_map: dict = {}
    for line in OUTCOMES.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        tk = (o.get("ticker") or "").strip().upper()
        rd = (o.get("report_date") or "").strip()
        if tk and rd:
            outcome_map[(tk, rd)] = o

    # Load predictions
    raw_lines = PRED_LOG.read_text().splitlines()
    preds = []
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        try:
            preds.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    filled = skipped = upcoming = 0

    for p in preds:
        # Skip if already resolved
        if p.get("realized_outcome") is not None:
            skipped += 1
            continue

        rd = (p.get("report_date") or "").strip()
        # Skip if report date is in the future
        if rd > today:
            upcoming += 1
            continue

        tk = (p.get("ticker") or "").strip().upper()
        o = outcome_map.get((tk, rd))
        if not o:
            # Outcome not yet in file — company may have delayed or we haven't
            # fetched this date's outcomes yet.  Leave as null.
            continue

        sp  = o.get("surprise_pct")
        bfl = o.get("beat")
        outcome = _classify(sp, bfl)
        if outcome is None:
            continue

        p["realized_outcome"]      = outcome
        p["realized_surprise_pct"] = float(sp) if sp is not None else None
        filled += 1

    # Rewrite the log in-place (preserves order)
    PRED_LOG.write_text(
        "\n".join(json.dumps(p, separators=(",", ":")) for p in preds) + "\n"
    )

    print(
        f"backfill_earnings_outcomes: {filled} filled · "
        f"{skipped} already done · {upcoming} upcoming · "
        f"{len(preds) - filled - skipped - upcoming} no outcome yet"
    )

    # Print per-tier summary when there's anything filled
    if filled + skipped > 0:
        from collections import defaultdict
        by_tier = defaultdict(lambda: {"beat": 0, "miss": 0, "inline": 0})
        for p in preds:
            if not p.get("realized_outcome"):
                continue
            tier = (p.get("predicted_tier") or "UNSCORED").upper()
            outcome = p["realized_outcome"].upper()
            if outcome == "BEAT":
                by_tier[tier]["beat"] += 1
            elif outcome == "MISS":
                by_tier[tier]["miss"] += 1
            elif outcome == "INLINE":
                by_tier[tier]["inline"] += 1

        print("\nPer-tier beat rates (all resolved predictions):")
        for tier in ["STRONG", "SOLID", "MODERATE", "WEAK", "UNSCORED"]:
            d = by_tier.get(tier)
            if not d:
                continue
            total = d["beat"] + d["miss"] + d["inline"]
            if total == 0:
                continue
            br = d["beat"] / total * 100
            print(
                f"  {tier:10s}: {total:3d} resolved  "
                f"{d['beat']:3d} beat ({br:.0f}%)  "
                f"{d['miss']:3d} miss  {d['inline']:3d} inline"
            )


if __name__ == "__main__":
    main()

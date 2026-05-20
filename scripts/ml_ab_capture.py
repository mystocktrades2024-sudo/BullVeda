#!/usr/bin/env python3
"""ML A/B framework capture script.

Joins (every rules signal in latest scan) with (current ML edge prediction)
and writes paired rows to cache/ml_ab_pairs.jsonl. When signal_log later
records the realized outcome, the pair row gets stamped with realized_pct.

This produces the ground truth for the A/B test:
  - Bucket A: ALL rules BUYs (baseline performance)
  - Bucket B: rules BUYs where ML p_up > 0.40 (ML AGREES)
  - Bucket C: rules BUYs where ML p_up < 0.30 (ML DISAGREES — predicts down)
  - Bucket D: rules BUYs where ML p_t1_first > 0.30 (ML hit-net AGREES)

If Bucket B's Sharpe > Bucket A's Sharpe by a statistically significant margin
(95% CI doesn't include 0), ML adds value as a filter. Otherwise it doesn't.

Called from run_daily_scan.sh after every scan. Idempotent per (ticker, date)
key — re-runs update the existing pair row rather than duplicating.

Run: python3 scripts/ml_ab_capture.py [--days-back N for backfill]
"""
from __future__ import annotations
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

BASE = Path(__file__).parent.parent
PAIRS_PATH = BASE / "cache" / "ml_ab_pairs.jsonl"


def _load_jsonl(path: Path) -> list:
    if not path.exists(): return []
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try: out.append(json.loads(line))
            except: pass
    return out


def _save_jsonl(path: Path, rows: list):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def capture():
    """Build/update pair rows for current scan + backfill realized outcomes."""
    # 1. Load current scan bundle
    bundle_path = BASE / "cache" / "last_bundle.json"
    if not bundle_path.exists():
        print("ERR: cache/last_bundle.json missing — run a scan first")
        return
    bundle = json.loads(bundle_path.read_text())
    all_scored = bundle.get("all_scored", []) or []
    scan_date = (bundle.get("scan_date") or datetime.now().strftime("%Y-%m-%d"))[:10]

    # 2. Load current ML predictions
    ml_path = BASE / "cache" / "ml_edge_predictions.json"
    if not ml_path.exists():
        print("ERR: cache/ml_edge_predictions.json missing — ML hasn't run")
        return
    ml = json.loads(ml_path.read_text())
    ml_swing = (ml.get("predictions") or {}).get("swing", {})

    # 3. Load existing pairs (for idempotency + outcome backfill)
    existing = _load_jsonl(PAIRS_PATH)
    by_key = {(r.get("ticker"), r.get("date")): r for r in existing}

    # 4. For each rules signal today, write/update a pair row
    new_pairs = 0
    for s in all_scored:
        tk = s.get("ticker")
        if not tk: continue
        rules_verdict = s.get("verdict") or s.get("label") or "UNKNOWN"
        # Only track real signals (skip pure noise — AVOID without thesis)
        if rules_verdict not in ("BUY", "WATCH", "SHORT"): continue
        ml_t = ml_swing.get(tk, {})
        if not ml_t: continue
        direction = ml_t.get("direction", {})
        hit_net = ml_t.get("hit_net", {})
        magnitude = ml_t.get("magnitude", {})
        verdict_blob = ml_t.get("verdict", {})

        key = (tk, scan_date)
        row = by_key.get(key, {})
        row.update({
            "ticker": tk,
            "date": scan_date,
            "rules_verdict": rules_verdict,
            "rules_score": s.get("score"),
            "rules_setup": s.get("strategy") or s.get("setup_family"),
            "rules_rr": s.get("rr"),
            "rules_entry": s.get("entry_price") or s.get("price"),
            "ml_verdict": verdict_blob.get("text"),
            "ml_edge": verdict_blob.get("edge"),
            "ml_confidence": verdict_blob.get("confidence"),
            "ml_p_up": direction.get("p_up"),
            "ml_p_dn": direction.get("p_dn"),
            "ml_p_chop": direction.get("p_chop"),
            "ml_q50": magnitude.get("q50"),
            "ml_q25": magnitude.get("q25"),
            "ml_q75": magnitude.get("q75"),
            "ml_p_t1_first": hit_net.get("p_t1_first"),
            "ml_p_stop_first": hit_net.get("p_stop_first"),
            "captured_at": datetime.now().isoformat(timespec="seconds"),
        })
        # Preserve outcome fields if already present
        if "realized_pct" not in row:
            row["realized_pct"] = None
            row["result"] = None
            row["closed_at"] = None
        if key not in by_key:
            new_pairs += 1
            by_key[key] = row

    # 5. Backfill realized outcomes from signal_log
    sl_path = BASE / "data" / "signal_log.json"
    backfilled = 0
    if sl_path.exists():
        sl = json.loads(sl_path.read_text())
        # Index signal_log by (ticker, date)
        sl_index = {}
        for s in sl:
            if s.get("status") != "CLOSED": continue
            if s.get("actual_pnl_pct") is None: continue
            k = (s.get("ticker"), (s.get("date") or "")[:10])
            sl_index[k] = s
        for key, row in by_key.items():
            if row.get("realized_pct") is not None: continue
            s = sl_index.get(key)
            if s:
                row["realized_pct"] = s.get("actual_pnl_pct")
                row["result"] = s.get("result")
                row["closed_at"] = s.get("status_updated") or s.get("close_date")
                backfilled += 1

    # 6. Write back
    sorted_rows = sorted(by_key.values(), key=lambda r: (r.get("date") or "", r.get("ticker") or ""))
    _save_jsonl(PAIRS_PATH, sorted_rows)
    closed_count = sum(1 for r in sorted_rows if r.get("realized_pct") is not None)
    print(f"ml_ab_capture: total pairs={len(sorted_rows)} · new={new_pairs} · backfilled_outcomes={backfilled} · closed={closed_count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    capture()

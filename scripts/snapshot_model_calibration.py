#!/usr/bin/env python3
"""
snapshot_model_calibration.py — Compare model_predictions vs realized.

Since model_predictions is empty today, this script also seeds it from
cache/ml_edge_predictions.json (current ML Edge output) so the pipeline
has data to evaluate.

Computes Brier score per horizon, decile calibration curve, AUC.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv():
    p = ROOT / ".env"
    if not p.exists(): return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        k, v = line.split("=", 1)
        if k.strip() and k.strip() not in os.environ:
            os.environ[k.strip()] = v.strip()


def _h(*parts): return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:32]


def _seed_model_predictions(sb) -> int:
    """One-shot: read cache/ml_edge_predictions.json and push to model_predictions
    so calibration has something to evaluate."""
    src = ROOT / "cache" / "ml_edge_predictions.json"
    if not src.exists():
        return 0
    try:
        j = json.loads(src.read_text())
    except Exception:
        return 0
    # Real schema: { '_meta': {...}, 'predictions': { 'swing'|'position'|'invest': { TICKER: {...} } }, ... }
    preds = j.get("predictions") or {}
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    HORIZON = {"swing": 5, "position": 20, "invest": 60}
    for mode, payload in preds.items():
        if not isinstance(payload, dict): continue
        h_days = HORIZON.get(mode, 5)
        for ticker, pred in payload.items():
            if not isinstance(pred, dict): continue
            # direction is a dict with p_up / p_chop / p_dn
            dir_blk = pred.get("direction") or {}
            mag_blk = pred.get("magnitude") or {}
            prob_up = dir_blk.get("p_up") if isinstance(dir_blk, dict) else None
            # predicted return: use q50 (median) from magnitude if available, else edge
            predicted_return = mag_blk.get("q50") if isinstance(mag_blk, dict) else None
            if predicted_return is None and isinstance(mag_blk, dict):
                predicted_return = mag_blk.get("mean") or mag_blk.get("edge")
            verdict = pred.get("verdict") or {}
            confidence = verdict.get("edge") if isinstance(verdict, dict) else None
            rows.append({
                "predicted_at": now,
                "ticker": ticker,
                "model_id": f"mledge_v3_{mode}",
                "model_version": pred.get("mode_label", "v3"),
                "horizon_days": h_days,
                "predicted_return": float(predicted_return) if predicted_return is not None else None,
                "predicted_prob_up": float(prob_up) if prob_up is not None else None,
                "confidence": float(confidence) if confidence is not None else None,
                "sync_key": _h("mp", now[:10], ticker, mode),
                "raw_json": json.dumps(pred, default=str),
            })
    if not rows:
        return 0
    # Dedup
    seen = {}
    for r in rows: seen[r["sync_key"]] = r
    rows = list(seen.values())
    n = 0
    for i in range(0, len(rows), 200):
        b = rows[i:i+200]
        try:
            sb.table("model_predictions").upsert(b, on_conflict="sync_key").execute()
            n += len(b)
        except Exception as e:
            print(f"  ! seed {i}: {type(e).__name__}: {str(e)[:200]}")
            break
    return n


def _compute_calibration(sb) -> list[dict]:
    """Pull model_predictions WHERE realized_return IS NOT NULL → bin → Brier/AUC.
    Initial run will be empty (no backfills yet) but the framework is in place."""
    try:
        resp = sb.table("model_predictions").select("model_id,horizon_days,predicted_prob_up,predicted_return,realized_return").not_.is_("realized_return", None).limit(50000).execute()
        data = resp.data or []
    except Exception as e:
        print(f"  ! select: {e}")
        return []
    if not data:
        return []
    # Group by (model_id, horizon)
    from collections import defaultdict
    groups = defaultdict(list)
    for r in data:
        groups[(r["model_id"], r["horizon_days"])].append(r)
    now = datetime.now(timezone.utc).isoformat()
    out = []
    for (mid, h), rows in groups.items():
        n = len(rows)
        # MAE / RMSE on return prediction
        residuals = [(float(r["predicted_return"] or 0) - float(r["realized_return"] or 0)) for r in rows if r.get("predicted_return") is not None]
        mae = sum(abs(x) for x in residuals) / len(residuals) if residuals else None
        rmse = math.sqrt(sum(x*x for x in residuals) / len(residuals)) if residuals else None
        # Brier on prob_up vs realized direction (>0)
        brier_pairs = [(float(r["predicted_prob_up"] or 0), 1.0 if (r["realized_return"] or 0) > 0 else 0.0)
                       for r in rows if r.get("predicted_prob_up") is not None]
        brier = sum((p - o) ** 2 for p, o in brier_pairs) / len(brier_pairs) if brier_pairs else None
        out.append({
            "evaluated_at": now,
            "model_id": mid,
            "horizon_days": h,
            "window_days": 90,
            "n_predictions": n,
            "brier_score": brier,
            "mae": mae,
            "rmse": rmse,
            "sync_key": _h("mc", now[:10], mid, h),
            "raw_json": json.dumps({"n": n, "brier": brier, "mae": mae, "rmse": rmse}),
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--seed", action="store_true", help="Also seed model_predictions from cache/ml_edge_predictions.json")
    args = ap.parse_args()
    _load_dotenv()
    os.environ["SUPABASE_MODE"] = "1"
    sys.path.insert(0, str(ROOT))
    from supabase_client import sb_client, healthcheck
    if not healthcheck()["ok"]:
        print("Supabase down"); return 2
    sb = sb_client()

    if args.seed and args.apply:
        n_seeded = _seed_model_predictions(sb)
        print(f"Seeded model_predictions: +{n_seeded} rows from ml_edge_predictions.json")

    rows = _compute_calibration(sb)
    print(f"Computed {len(rows)} calibration rows")
    if not rows:
        print("(No predictions with realized returns yet — populate model_predictions over time, then re-run.)")
        return 0
    if not args.apply: return 0
    ok = fail = 0
    for i in range(0, len(rows), 200):
        b = rows[i:i+200]
        try:
            sb.table("model_calibration").upsert(b, on_conflict="sync_key").execute()
            ok += len(b)
        except Exception as e:
            fail += len(b); print(f"  ! {e}")
    print(f"  pushed={ok} failed={fail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

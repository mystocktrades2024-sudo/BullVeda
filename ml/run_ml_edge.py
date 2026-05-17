"""Daily ML Edge inference entry-point · mode-aware (swing/position/invest).

QUICK WIN — Inference cache: hashes (mode, sorted feature key/value pairs, trade
plan target_thr_pct) and reuses prior predictions when nothing changed for that
ticker. Cuts a 220s rerun to ~10s when nothing's moved.


Pipeline (post-v2):
  1. Read cache/last_bundle.json — collect every ticker symbol in the scan
  2. Pre-extract 17 technical features per ticker via EODHD bars (one fetch per
     ticker, cached 12h). SPY benchmark fetched once.
  3. For each (ticker, mode) pair, run predict_with_features(features, mode)
  4. Write
        cache/ml_edge_predictions.json
        infra/prototype/ml_edge_predictions.json   (browser-reachable)
     Shape:
        {
          "_meta": {...calibration + per-mode metrics...},
          "predictions": {
             "swing":    {"AAPL": {...payload...}, ...},
             "position": {...},
             "invest":   {...}
          }
        }
     Legacy callers reading predictions[ticker] (flat) get a fallback merge
     pointing at swing predictions so they keep working unchanged."""
from __future__ import annotations
import hashlib
import json
import os
import time
from datetime import datetime, timezone

import pandas as pd

from ml.feature_extractor import extract_for_ticker, _spy_series
from ml.historical_backfill import PCTRANK_BASE_COLS
from ml.predict import predict_with_features, MODES, MODE_LABEL, MODE_DAYS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUNDLE = os.path.join(ROOT, "cache", "last_bundle.json")
OUT    = os.path.join(ROOT, "cache", "ml_edge_predictions.json")
PROTO  = os.path.join(ROOT, "infra", "prototype", "ml_edge_predictions.json")
REPORT_HIST = os.path.join(ROOT, "cache", "ml", "calibration_report_historical.json")


def _collect_tickers(bundle: dict) -> list[dict]:
    seen, out = set(), []
    for key in ("all_scored", "buy_candidates", "elite_picks"):
        rows = bundle.get(key) or []
        if not isinstance(rows, list):
            continue
        for r in rows:
            if not isinstance(r, dict):
                continue
            sym = (r.get("ticker") or r.get("symbol") or "").upper().strip()
            if not sym or sym in seen:
                continue
            seen.add(sym); out.append(r)
    return out


def main():
    if not os.path.exists(BUNDLE):
        print(f"[ml-edge] no bundle at {BUNDLE} — skip"); return
    bundle = json.load(open(BUNDLE))
    tickers = _collect_tickers(bundle)
    print(f"[ml-edge] inference over {len(tickers)} tickers × {len(MODES)} modes")

    # Pre-warm SPY series so per-ticker calls reuse it
    _spy_series()

    # Pass 1 — extract RAW features per ticker (one EODHD call each, cached)
    t0 = time.time()
    feats_by_sym = {}
    for i, ticker in enumerate(tickers):
        sym = (ticker.get("ticker") or ticker.get("symbol") or "").upper().strip()
        if (i + 1) % 50 == 0:
            print(f"[ml-edge] features: {i+1}/{len(tickers)} ({sym}) · {time.time()-t0:.0f}s")
        try:
            feats = extract_for_ticker(sym)
            if feats is not None:
                feats_by_sym[sym] = feats
        except Exception as e:
            print(f"[ml-edge] feature-extract failed for {sym}: {e}")
    n_feat_ok = len(feats_by_sym)
    print(f"[ml-edge] raw features extracted: {n_feat_ok}/{len(tickers)} in {time.time()-t0:.0f}s")

    # Pass 1b — compute cross-sectional pct_rank features across TODAY's live
    # universe. Mirrors what historical_backfill does per-date during training:
    # each ticker gets the rank of its feature value vs all other live tickers
    # today. This is how "ROST is in the 92nd %ile RSI today" becomes a feature.
    if feats_by_sym:
        feat_df = pd.DataFrame.from_dict(feats_by_sym, orient="index")
        for col in PCTRANK_BASE_COLS:
            if col in feat_df.columns:
                feat_df[f"pctrank_{col}"] = feat_df[col].rank(pct=True, method="average")
        for sym, row in feat_df.iterrows():
            feats_by_sym[sym] = {**feats_by_sym[sym], **{f"pctrank_{c}": float(row.get(f"pctrank_{c}", 0.5)) for c in PCTRANK_BASE_COLS}}
        print(f"[ml-edge] pct_rank features computed for {len(feats_by_sym)} tickers")

    # Load prior cache (hash → payload). Survives across runs so unchanged
    # tickers skip the predict call entirely.
    CACHE_PATH = os.path.join(ROOT, "cache", "ml", "predict_cache.json")
    if os.path.exists(CACHE_PATH):
        try:
            pred_cache = json.load(open(CACHE_PATH))
        except Exception:
            pred_cache = {}
    else:
        pred_cache = {}
    new_cache = {}

    def _num(x, default=0.0):
        """Coerce possibly-dict price entries (canonical_trade_plan.entry can be
        {'low': X, 'high': Y}) into a single float. Falls back to default on
        anything weird."""
        if isinstance(x, dict):
            for k in ("mid", "price", "value", "low", "high"):
                if k in x and isinstance(x[k], (int, float)):
                    return float(x[k])
            return default
        try:
            return float(x) if x not in (None, "") else default
        except (TypeError, ValueError):
            return default

    def _feat_hash(mode: str, feats: dict, ticker_obj: dict) -> str:
        plan = ticker_obj.get("canonical_trade_plan") or ticker_obj.get("trade_plan") or {}
        entry  = _num(plan.get("entry") or plan.get("entry_price") or ticker_obj.get("price"))
        t1_lvl = _num(plan.get("t1") or plan.get("target1"))
        payload = f"{mode}|"
        for k in sorted(feats):
            payload += f"{k}={float(feats[k]):.6f};"
        payload += f"entry={entry:.4f};t1={t1_lvl:.4f}"
        return hashlib.md5(payload.encode()).hexdigest()

    # Pass 2 — predict per mode (with cache)
    predictions_by_mode: dict[str, dict] = {m: {} for m in MODES}
    fails = {m: 0 for m in MODES}
    cache_hits = {m: 0 for m in MODES}
    t1 = time.time()
    ticker_by_sym = {(t.get("ticker") or t.get("symbol") or "").upper().strip(): t for t in tickers}
    for mode in MODES:
        for sym, feats in feats_by_sym.items():
            tk_obj = ticker_by_sym.get(sym, {})
            h = _feat_hash(mode, feats, tk_obj)
            new_cache[h] = None  # placeholder reserve key
            cached = pred_cache.get(h)
            if cached is not None and "verdict" in cached:
                predictions_by_mode[mode][sym] = cached
                new_cache[h] = cached
                cache_hits[mode] += 1
                continue
            try:
                p = predict_with_features(feats, mode=mode, ticker=tk_obj)
                if p is not None:
                    predictions_by_mode[mode][sym] = p
                    new_cache[h] = p
                else:
                    fails[mode] += 1
                    predictions_by_mode[mode][sym] = {"error": f"model unavailable for mode={mode}"}
            except Exception as e:
                fails[mode] += 1
                predictions_by_mode[mode][sym] = {"error": str(e)}
        n_ok = len(predictions_by_mode[mode]) - fails[mode]
        print(f"[ml-edge] mode={mode}: {n_ok} ok ({cache_hits[mode]} cached, {n_ok - cache_hits[mode]} fresh), {fails[mode]} fail")
    print(f"[ml-edge] predictions in {time.time()-t1:.0f}s")
    # Persist updated cache for next run (only successful payloads)
    with open(CACHE_PATH, "w") as f:
        json.dump({h: v for h, v in new_cache.items() if v is not None}, f)

    # Legacy flat (= swing) namespace so any pre-v2 reader keeps working.
    cal_report = json.load(open(REPORT_HIST)) if os.path.exists(REPORT_HIST) else {}

    out = {
        "_meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "n_tickers":    len(tickers),
            "n_features_ok":n_feat_ok,
            "elapsed_s":    round(time.time() - t0, 2),
            "modes":        list(MODES),
            "mode_labels":  MODE_LABEL,
            "mode_days":    MODE_DAYS,
            "n_ok": {m: sum(1 for v in predictions_by_mode[m].values() if "error" not in v) for m in MODES},
            "n_fail": fails,
            "model": {
                "trained_at":          cal_report.get("trained_at"),
                "n_total":             (cal_report.get("modes", {}) or {}).get("swing", {}).get("n_total"),
                "preliminary":         False,
                "calibration_health":  "ok",
                "source":              "historical_backfill",
                "feature_cols":        cal_report.get("feature_cols", []),
                "per_mode":            cal_report.get("modes", {}),
            },
        },
        "predictions": predictions_by_mode,
        # legacy flat layer = swing pool, so old readers keep working
        "predictions_flat": predictions_by_mode["swing"],
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:   json.dump(out, f, indent=2, default=str)
    with open(PROTO, "w") as f: json.dump(out, f, indent=2, default=str)
    print(f"[ml-edge] wrote {OUT}")
    print(f"[ml-edge] wrote {PROTO}")


if __name__ == "__main__":
    main()

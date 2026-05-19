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
import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone

import pandas as pd

from ml.feature_extractor import extract_for_ticker, _spy_series
from ml.historical_backfill import PCTRANK_BASE_COLS
from ml.predict import predict_with_features, MODES, MODE_LABEL, MODE_DAYS
from ml.universe_loader import load_universe, get_universe_stats

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


def _parse_args(argv=None):
    """CLI args. Default = legacy behavior (read from last_bundle.json)."""
    ap = argparse.ArgumentParser(
        prog="ml.run_ml_edge",
        description="ML Edge inference — 3-headed forecast over a universe.",
    )
    ap.add_argument(
        "--universe",
        choices=["bundle", "sp500", "r1000", "r2000", "all"],
        default="bundle",
        help=(
            "Source for the ticker list. 'bundle' (default) reads cache/last_bundle.json "
            "= the daily scan output (~436 tickers). The other choices fetch the requested "
            "index from EODHD and run inference INDEPENDENT of the daily scan."
        ),
    )
    ap.add_argument(
        "--min-adv",
        type=float,
        default=0.0,
        help=(
            "Drop tickers whose 20-day average daily dollar volume is below this "
            "threshold (USD). Set 5_000_000 for retail-tradeable filter, 0 to disable. "
            "Default 0."
        ),
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Cap the number of tickers (after dedup). 0 = no cap. Useful for smoke tests.",
    )
    return ap.parse_args(argv)


def _collect_universe_tickers(universe_name: str) -> tuple[list[dict], dict]:
    """Build the ticker list from a universe slice (sp500/r1000/r2000/all).

    Returns (list-of-row-dicts, universe-stats-dict). Row dicts mirror the
    shape of bundle rows but carry only ticker/name/sector + membership flags.
    """
    rows = load_universe(universe_name)
    # Reshape to the (ticker, name, sector, in_sp500, in_r1000, in_r2000) row
    # the rest of the pipeline expects. _feat_hash + predict tolerate missing
    # fields gracefully (uses sym for hash + falls back on defaults for plan).
    out = []
    for r in rows:
        out.append({
            "ticker": r["ticker"],
            "symbol": r["ticker"],  # legacy alias some callers use
            "name": r.get("name"),
            "sector": r.get("sector"),
            "in_sp500": r.get("in_sp500", False),
            "in_r1000": r.get("in_r1000", False),
            "in_r2000": r.get("in_r2000", False),
        })
    stats = get_universe_stats()
    stats["selected"] = universe_name
    stats["selected_count"] = len(out)
    return out, stats


def main(argv=None):
    args = _parse_args(argv)

    # ── Source the ticker list ──────────────────────────────────────────
    universe_stats = None
    if args.universe == "bundle":
        if not os.path.exists(BUNDLE):
            print(f"[ml-edge] no bundle at {BUNDLE} — skip"); return
        bundle = json.load(open(BUNDLE))
        tickers = _collect_tickers(bundle)
        # Membership flags from universe loader (best-effort)
        try:
            uni_rows = load_universe("all", with_metadata=False)
            mem = {r["ticker"]: r for r in uni_rows}
            for t in tickers:
                sym = (t.get("ticker") or t.get("symbol") or "").upper().strip()
                r = mem.get(sym, {})
                t.setdefault("in_sp500", r.get("in_sp500", False))
                t.setdefault("in_r1000", r.get("in_r1000", False))
                t.setdefault("in_r2000", r.get("in_r2000", False))
        except Exception as e:
            print(f"[ml-edge] membership tagging skipped: {e}")
    else:
        tickers, universe_stats = _collect_universe_tickers(args.universe)

    # Liquidity filter — drop ticks below min-ADV (uses bundle-cached field
    # if present; missing ADV is treated as "unknown" and KEPT to avoid
    # dropping tickers when the bundle doesn't have ADV data yet).
    n_filtered = 0
    if args.min_adv > 0:
        kept = []
        for t in tickers:
            adv = t.get("adv_dollars") or t.get("dollar_volume") or t.get("adv_dollar_volume")
            if adv is not None and float(adv) < args.min_adv:
                n_filtered += 1
                continue
            kept.append(t)
        print(f"[ml-edge] liquidity filter: dropped {n_filtered} of {len(tickers)} (min-ADV ${args.min_adv:,.0f})")
        tickers = kept

    # Optional cap (smoke-test)
    if args.limit > 0 and len(tickers) > args.limit:
        tickers = tickers[:args.limit]
        print(f"[ml-edge] limit applied: {args.limit} tickers")

    print(f"[ml-edge] universe={args.universe} · inference over {len(tickers)} tickers × {len(MODES)} modes")

    # Pre-warm SPY series so per-ticker calls reuse it
    _spy_series()

    # Pass 1 — extract RAW features per ticker (one EODHD call each, cached)
    t0 = time.time()
    feats_by_sym = {}
    failures = {}  # ticker → human-readable reason (P2.1)
    for i, ticker in enumerate(tickers):
        sym = (ticker.get("ticker") or ticker.get("symbol") or "").upper().strip()
        if (i + 1) % 50 == 0:
            print(f"[ml-edge] features: {i+1}/{len(tickers)} ({sym}) · {time.time()-t0:.0f}s")
        try:
            feats = extract_for_ticker(sym)
            if feats is not None:
                feats_by_sym[sym] = feats
            else:
                failures[sym] = "feature_extract_returned_none"
        except Exception as e:
            failures[sym] = f"feature_extract_error: {type(e).__name__}: {str(e)[:120]}"
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

    # Build membership index + per-ticker enrichment from `tickers` list
    # (carries in_sp500/in_r1000/in_r2000 + sector). Indexed by uppercase sym.
    membership = {
        (t.get("ticker") or t.get("symbol") or "").upper().strip(): {
            "in_sp500": bool(t.get("in_sp500")),
            "in_r1000": bool(t.get("in_r1000")),
            "in_r2000": bool(t.get("in_r2000")),
            "sector":   t.get("sector"),
            "name":     t.get("name"),
        }
        for t in tickers
    }

    # Stamp membership + sector + frictions onto each per-ticker payload so the
    # UI can filter/group/adjust without a second fetch.
    # P3.1 spread tax · P3.2 capacity flag · P3.3 stability badge (later)
    ticker_full_by_sym = {(t.get("ticker") or t.get("symbol") or "").upper().strip(): t for t in tickers}
    for mode in MODES:
        for sym, payload in predictions_by_mode[mode].items():
            if not isinstance(payload, dict):
                continue
            mem = membership.get(sym, {})
            payload["in_sp500"] = mem.get("in_sp500", False)
            payload["in_r1000"] = mem.get("in_r1000", False)
            payload["in_r2000"] = mem.get("in_r2000", False)
            if mem.get("sector"):
                payload["sector"] = mem["sector"]
            if mem.get("name"):
                payload["name"] = mem["name"]

            # P3.1 · SPREAD TAX — estimate per-ticker bid-ask spread in bps,
            # subtract from q50 to surface "effective of frictions" forecast.
            # Heuristic: large-caps (S&P) ~ 2-5bp, mid-caps (R1000) ~ 5-15bp,
            # small-caps (R2000) ~ 15-50bp. Use ADV-dollars as the proxy.
            full = ticker_full_by_sym.get(sym, {})
            adv = full.get("adv_dollars") or full.get("dollar_volume") or full.get("adv_dollar_volume")
            if adv and float(adv) > 0:
                adv_m = float(adv) / 1_000_000.0
                if adv_m > 100:   spread_bps = 3.0
                elif adv_m > 50:  spread_bps = 6.0
                elif adv_m > 20:  spread_bps = 12.0
                elif adv_m > 10:  spread_bps = 22.0
                elif adv_m > 5:   spread_bps = 35.0
                else:             spread_bps = 60.0
            else:
                # Default for unknown — assume mid-cap-grade if R1000-only,
                # small-cap if R2000-only, large-cap if S&P 500
                if   mem.get("in_sp500"): spread_bps = 4.0
                elif mem.get("in_r1000"): spread_bps = 12.0
                elif mem.get("in_r2000"): spread_bps = 35.0
                else:                     spread_bps = 20.0
            mag = payload.get("magnitude") or {}
            q50 = mag.get("q50")
            if isinstance(q50, (int, float)):
                # Round-trip = 2× spread. Cost in % = spread_bps/100.
                friction_pct = (spread_bps * 2.0) / 100.0
                payload["q50_net"] = round(q50 - friction_pct, 3)
                payload["spread_bps"] = round(spread_bps, 1)
                payload["spread_source"] = "heuristic"   # may be overridden below
                payload["frictions_pct"] = round(friction_pct, 3)

            # P3.2 · CAPACITY FLAG — at a reference $100K account size and 5%
            # position size = $5K. Flag if $5K > 1% × ADV (= position would
            # materially impact price). Configurable account size via env.
            try:
                _ref_account = float(os.environ.get("ML_EDGE_REF_ACCOUNT", "100000"))
                _ref_pos_pct = float(os.environ.get("ML_EDGE_REF_POS_PCT", "0.05"))
                position_usd = _ref_account * _ref_pos_pct
                if adv and float(adv) > 0:
                    adv_pct = position_usd / float(adv)
                    payload["adv_pct"] = round(adv_pct * 100, 3)
                    payload["capacity_constrained"] = bool(adv_pct > 0.01)
            except Exception:
                pass

    out = {
        "_meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "universe":     args.universe,
            "min_adv":      args.min_adv,
            "n_tickers":    len(tickers),
            "n_filtered":   n_filtered,
            "n_features_ok":n_feat_ok,
            "elapsed_s":    round(time.time() - t0, 2),
            "modes":        list(MODES),
            "mode_labels":  MODE_LABEL,
            "mode_days":    MODE_DAYS,
            "n_ok": {m: sum(1 for v in predictions_by_mode[m].values() if "error" not in v) for m in MODES},
            "n_fail": fails,
            "failures": dict(list(failures.items())[:200]),  # ticker → reason (P2.1, capped to keep JSON small)
            "failures_total": len(failures),
            # #9 · sector tag for each failure (lookup from membership map)
            "failure_sectors": {
                sym: (membership.get(sym, {}).get("sector") or "Other")
                for sym in list(failures.keys())[:500]
            },
            "universe_stats": universe_stats,  # None when --universe=bundle
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
    # ── #5 · REAL SCHWAB SPREAD OVERLAY (top-100 picks per mode) ──────
    # For each mode, rank by p_up, batch-fetch live Schwab quotes for the
    # top-100, override spread_bps with real bid/ask, recompute q50_net.
    # Falls back to heuristic if Schwab unavailable / rate-limited.
    try:
        from schwab_client import get_quotes_batch as _schwab_quotes
        top_syms = set()
        for mode in MODES:
            ranked = sorted(
                [(s, p) for s, p in predictions_by_mode[mode].items()
                 if isinstance(p, dict) and "error" not in p],
                key=lambda kv: -(kv[1].get("direction", {}).get("p_up", 0))
            )
            for sym, _p in ranked[:100]:
                top_syms.add(sym)
        if top_syms:
            quotes = _schwab_quotes(top_syms)
            n_overridden = 0
            for sym, q in (quotes or {}).items():
                if not q:
                    continue
                # Schwab nests bid/ask under q.quote — handle both shapes
                qd = q.get("quote") if isinstance(q.get("quote"), dict) else q
                bid = qd.get("bidPrice") or qd.get("bid") or 0
                ask = qd.get("askPrice") or qd.get("ask") or 0
                if not (bid > 0 and ask > 0 and ask > bid):
                    continue
                mid = (bid + ask) / 2.0
                real_bps = ((ask - bid) / mid) * 10_000  # in basis points
                for mode in MODES:
                    payload = predictions_by_mode[mode].get(sym)
                    if not isinstance(payload, dict) or "error" in payload:
                        continue
                    payload["spread_bps"] = round(real_bps, 1)
                    payload["spread_source"] = "schwab_live"
                    friction_pct = (real_bps * 2.0) / 100.0
                    payload["frictions_pct"] = round(friction_pct, 3)
                    mag = payload.get("magnitude") or {}
                    q50 = mag.get("q50")
                    if isinstance(q50, (int, float)):
                        payload["q50_net"] = round(q50 - friction_pct, 3)
                n_overridden += 1
            print(f"[ml-edge] Schwab spread overlay: {n_overridden} tickers updated with real bid/ask")
            out["_meta"]["spread_overlay"] = {
                "source": "schwab_live",
                "n_overridden": n_overridden,
            }
    except Exception as e:
        print(f"[ml-edge] Schwab spread overlay skipped: {e}")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:   json.dump(out, f, indent=2, default=str)
    with open(PROTO, "w") as f: json.dump(out, f, indent=2, default=str)
    print(f"[ml-edge] wrote {OUT}")
    print(f"[ml-edge] wrote {PROTO}")

    # ── P2.2 · SNAPSHOT ARCHIVE — keep last 30 days for diff/drift analysis ──
    # On every run, dump a thin snapshot (no full payloads — just direction
    # + verdict per ticker per mode) into cache/ml_edge_history/{YYYY-MM-DD}.json.
    # Keeps storage small (~50KB per snapshot vs 5MB for the full predictions
    # file) while preserving enough data for: (a) day-over-day flip detection,
    # (b) 30-day drift trend, (c) cross-snapshot stability scoring.
    try:
        from pathlib import Path as _P
        snap_dir = _P(ROOT) / "cache" / "ml_edge_history"
        snap_dir.mkdir(parents=True, exist_ok=True)
        today = datetime.now().strftime("%Y-%m-%d")
        snap_path = snap_dir / f"{today}.json"
        thin = {
            "_meta": {
                "generated_at": out["_meta"]["generated_at"],
                "universe":     out["_meta"].get("universe"),
                "n_tickers":    out["_meta"]["n_tickers"],
            },
            "predictions": {},
        }
        for mode in MODES:
            thin["predictions"][mode] = {}
            for sym, payload in predictions_by_mode[mode].items():
                if not isinstance(payload, dict) or "error" in payload:
                    continue
                d = payload.get("direction") or {}
                m = payload.get("magnitude") or {}
                thin["predictions"][mode][sym] = {
                    "p_up":  round(d.get("p_up", 0.0), 4),
                    "p_dn":  round(d.get("p_dn", 0.0), 4),
                    "edge":  round(d.get("edge", 0.0), 4),
                    "q50":   round(m.get("q50", 0.0), 3),
                    "v":     ((payload.get("verdict") or {}).get("text") or "").upper()[:8],
                }
        with open(snap_path, "w") as f:
            json.dump(thin, f, default=str)
        print(f"[ml-edge] archived thin snapshot to {snap_path}")

        # Retention: keep last 35 snapshots, delete older
        snaps = sorted(snap_dir.glob("*.json"))
        for old in snaps[:-35]:
            try: old.unlink()
            except Exception: pass
    except Exception as e:
        print(f"[ml-edge] snapshot archive skipped: {e}")

    # ── #4 · CALIBRATION HISTORY TIME-SERIES (jsonl, append-only) ──────
    # One line per run: { date, mode, accuracy, auc, brier, log_loss, n_ok }.
    # Powers the calibration card's drift sparkline. Append-only = safe under
    # crash, easy to rotate.
    try:
        from pathlib import Path as _P
        cal_hist = _P(ROOT) / "cache" / "ml" / "calibration_history.jsonl"
        cal_hist.parent.mkdir(parents=True, exist_ok=True)
        today_iso = datetime.now().strftime("%Y-%m-%d")
        modes_cal = (cal_report.get("_modes") or cal_report.get("modes") or {})
        with open(cal_hist, "a") as f:
            for mk in MODES:
                m_data = modes_cal.get(mk) or {}
                dir_d = m_data.get("direction") or cal_report.get("direction") or {}
                hit_d = m_data.get("hit_net")   or cal_report.get("hit_net")   or {}
                f.write(json.dumps({
                    "date":      today_iso,
                    "mode":      mk,
                    "accuracy":  dir_d.get("accuracy"),
                    "log_loss":  dir_d.get("log_loss"),
                    "auc":       hit_d.get("auc"),
                    "brier":     hit_d.get("brier"),
                    "n_ok":      (out.get("_meta", {}).get("n_ok") or {}).get(mk, 0),
                    "n_fail":    (out.get("_meta", {}).get("n_fail") or {}).get(mk, 0),
                }) + "\n")
        print(f"[ml-edge] appended calibration history to {cal_hist}")
    except Exception as e:
        print(f"[ml-edge] calibration-history append skipped: {e}")

    # ── #19 · TELEMETRY (jsonl, append-only) ──────────────────────────
    # Per-run operational data: wall time, EODHD touches, cache hit rate.
    # Visible from a future "ops" tab; useful even today for offline review.
    try:
        from pathlib import Path as _P
        tel_path = _P(ROOT) / "cache" / "ml" / "telemetry.jsonl"
        tel_path.parent.mkdir(parents=True, exist_ok=True)
        n_total_predict = sum(len(predictions_by_mode[m]) for m in MODES)
        n_cache_hits = sum(cache_hits.get(m, 0) for m in MODES)
        cache_hit_rate = (n_cache_hits / max(1, n_total_predict)) * 100.0
        with open(tel_path, "a") as f:
            f.write(json.dumps({
                "ts":              datetime.now(timezone.utc).isoformat(),
                "universe":        args.universe,
                "n_tickers":       len(tickers),
                "n_features_ok":   n_feat_ok,
                "failures_total":  len(failures),
                "n_filtered":      n_filtered,
                "cache_hit_rate":  round(cache_hit_rate, 1),
                "elapsed_s":       round(time.time() - t0, 1),
                "elapsed_feat_s":  round(time.time() - t0 - (time.time() - t1), 1) if False else None,
                "elapsed_pred_s":  round(time.time() - t1, 1),
            }) + "\n")
        print(f"[ml-edge] appended telemetry to {tel_path}")
    except Exception as e:
        print(f"[ml-edge] telemetry append skipped: {e}")

    # ── #20 · REGRESSION ALERT (Slack webhook if env set) ──────────────
    # Compare to last 7 entries in telemetry.jsonl. Fire if any of:
    #   - calibration_health flipped from 'ok'
    #   - failures_total jumped >25% over 7-run median
    #   - any mode's AUC dropped >0.05 over 7-run median
    try:
        slack_url = os.environ.get("SLACK_WEBHOOK_ML_EDGE") or os.environ.get("SLACK_WEBHOOK_URL")
        if slack_url:
            import urllib.request
            import statistics
            tel_path = os.path.join(ROOT, "cache", "ml", "telemetry.jsonl")
            past = []
            if os.path.exists(tel_path):
                with open(tel_path) as f:
                    lines = f.readlines()[-8:-1]  # last 7 excluding current
                    for ln in lines:
                        try: past.append(json.loads(ln))
                        except Exception: pass
            warnings = []
            cur_fail = len(failures)
            if past:
                med_fail = statistics.median(p.get("failures_total", 0) for p in past)
                if med_fail > 0 and cur_fail > med_fail * 1.25:
                    warnings.append(f"⚠ Failures jumped: {cur_fail} vs 7-run median {med_fail:.0f}")
            if (cal_report.get("calibration_health") or "ok") != "ok":
                warnings.append(f"⚠ Calibration health: {cal_report.get('calibration_health')}")
            if warnings:
                msg = ":robot_face: *ML Edge regression alert*\n" + "\n".join(warnings)
                req = urllib.request.Request(
                    slack_url,
                    data=json.dumps({"text": msg}).encode(),
                    headers={"Content-Type": "application/json"},
                )
                urllib.request.urlopen(req, timeout=5).read()
                print(f"[ml-edge] regression alert posted to Slack")
    except Exception as e:
        print(f"[ml-edge] slack alert skipped: {e}")

    # ── #1 · PICKS-HISTORY CAPTURE — log today's top-10 bulls per mode as
    # paper picks. Outcomes get resolved by a separate job 5 days later
    # via cache/ml/resolve_picks.py (touches OHLCV, computes realized R).
    # This closes the credibility loop — without it, the walk-forward equity
    # curve has no real trades to anchor on.
    try:
        from pathlib import Path as _P
        ph_path = _P(ROOT) / "cache" / "ml_edge_picks_history.jsonl"
        today_iso = datetime.now().strftime("%Y-%m-%d")
        n_picked = 0
        with open(ph_path, "a") as f:
            for mk in MODES:
                pool = predictions_by_mode[mk]
                ranked = sorted(
                    [(s, p) for s, p in pool.items() if isinstance(p, dict) and "error" not in p],
                    key=lambda kv: -(kv[1].get("direction", {}).get("p_up", 0))
                )
                horizon_days = MODE_DAYS.get(mk, 5)
                for sym, p in ranked[:10]:
                    full = ticker_full_by_sym.get(sym, {})
                    spot = full.get("price") or full.get("spot") or full.get("close") or 0
                    atr = full.get("atr") or full.get("atr_14") or 0
                    mag = p.get("magnitude") or {}
                    dir_ = p.get("direction") or {}
                    f.write(json.dumps({
                        "scan_date":     today_iso,
                        "scan_ts":       out["_meta"]["generated_at"],
                        "ticker":        sym,
                        "mode":          mk,
                        "horizon_days":  horizon_days,
                        "side":          "long",
                        "entry":         spot,
                        "atr":           atr,
                        "q50":           mag.get("q50"),
                        "q25":           mag.get("q25"),
                        "q75":           mag.get("q75"),
                        "p_up":          dir_.get("p_up"),
                        "edge":          dir_.get("edge"),
                        "spread_bps":    p.get("spread_bps"),
                        "in_sp500":      p.get("in_sp500"),
                        "in_r1000":      p.get("in_r1000"),
                        "in_r2000":      p.get("in_r2000"),
                        "status":        "pending",
                        "exit_date":     None,
                        "exit_price":    None,
                        "realized_r":    None,
                        "realized_pct":  None,
                    }) + "\n")
                    n_picked += 1
        print(f"[ml-edge] logged {n_picked} paper picks to {ph_path}")
    except Exception as e:
        print(f"[ml-edge] picks-history append skipped: {e}")


if __name__ == "__main__":
    main()

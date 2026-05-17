#!/usr/bin/env python3
"""
fold_orphan_data.py — One-shot loader for ~95K JSONL lines + 14K aux SQLite rows
into the new Supabase tables created by migrations 005-009.

Idempotent — every insert uses sync_key for dedup (sha1 of row content).

Usage:
    python3 scripts/fold_orphan_data.py             # dry-run
    python3 scripts/fold_orphan_data.py --apply     # actually fold
    python3 scripts/fold_orphan_data.py --apply --only decision_log,exit_signals
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE = ROOT / "cache"

BATCH = 500


def _load_dotenv():
    p = ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() and k.strip() not in os.environ:
            os.environ[k.strip()] = v.strip()


def _h(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:32]


def _iter_jsonl(path: Path):
    if not path.exists():
        return
    for line in path.read_text(errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except Exception:
            pass


# =========================================================================
# Per-source extractors
# =========================================================================

def x_decision_log():
    """data/decision_log.jsonl → decision_log (92K rows)"""
    src = DATA / "decision_log.jsonl"
    for j in _iter_jsonl(src):
        date = j.get("date") or j.get("ts")
        if not date:
            continue
        ticker = j.get("ticker") or "?"
        yield {
            "observed_at": date,
            "decided_at": date,
            "ticker": ticker,
            "verdict": j.get("verdict"),
            "score": j.get("score"),
            "rs_rank": j.get("rs_rank"),
            "setup_family": j.get("setup_family") or j.get("setup_type"),
            "regime": j.get("regime4") or j.get("regime"),
            "gates_passed": json.dumps(j.get("gates_passed", [])) if j.get("gates_passed") else None,
            "gates_failed": json.dumps(j.get("gates_hit", [])) if j.get("gates_hit") else None,
            "reject_reason": j.get("reason"),
            "sync_key": _h(date, ticker, j.get("verdict"), j.get("score"), j.get("setup_type")),
            "raw_json": json.dumps(j),
        }


def x_exit_signals():
    src = DATA / "exit_signals.jsonl"
    for j in _iter_jsonl(src):
        ts = j.get("ts") or j.get("date")
        if not ts:
            continue
        ticker = j.get("ticker") or "?"
        verdict = j.get("verdict") or {}
        urgency_str = verdict.get("urgency") if isinstance(verdict, dict) else None
        urgency_map = {"LOW": 0.3, "MED": 0.6, "MEDIUM": 0.6, "HIGH": 0.9, "CRITICAL": 1.0}
        confidence = urgency_map.get(urgency_str) if urgency_str else None
        yield {
            "flagged_at": ts,
            "ticker": ticker,
            "direction": j.get("direction") or "long",
            "entry_price": j.get("entry_price"),
            "current_price": j.get("current"),
            "reason": verdict.get("reason") if isinstance(verdict, dict) else str(verdict),
            "confidence": confidence,
            "setup_family": j.get("setup_family"),
            "days_held": j.get("days_held"),
            "unrealized_pnl_pct": j.get("pnl_pct"),
            "acted_on": (verdict.get("action") == "EXIT") if isinstance(verdict, dict) else False,
            "sync_key": _h(ts, ticker),
            "raw_json": json.dumps(j),
        }


def x_earnings_outcomes():
    src = DATA / "earnings_outcomes.jsonl"
    for j in _iter_jsonl(src):
        rpt = j.get("report_date")
        ticker = j.get("ticker")
        if not (rpt and ticker):
            continue
        yield {
            "report_date": rpt,
            "ticker": ticker,
            "predicted_tier": j.get("predicted_tier"),
            "predicted_prob": j.get("predicted_prob"),
            "eps_estimate": j.get("estimate"),
            "eps_actual": j.get("actual"),
            "eps_surprise_pct": j.get("surprise_pct"),
            "beat": (j.get("beat") == "BEAT") if j.get("beat") else None,
            "gap_open_pct": j.get("gap_open_pct"),
            "close_5d_pct": j.get("close_5d_pct"),
            "close_10d_pct": j.get("close_10d_pct"),
            "sector": j.get("sector"),
            "sync_key": _h(rpt, ticker, j.get("estimate"), j.get("actual")),
            "raw_json": json.dumps(j),
        }


def x_iv_history():
    src = DATA / "iv_history.jsonl"
    for j in _iter_jsonl(src):
        ts = j.get("ts") or j.get("date")
        ticker = j.get("ticker")
        if not (ts and ticker):
            continue
        # ts can be epoch int or ISO string
        if isinstance(ts, (int, float)):
            from datetime import datetime, timezone
            ts = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        yield {
            "observed_at": ts,
            "ticker": ticker,
            "iv30": j.get("current_iv") or j.get("iv30"),
            "iv60": j.get("iv60"),
            "iv_rank": j.get("iv_rank"),
            "iv_percentile": j.get("iv_percentile"),
            "hv30": j.get("hv30"),
            "iv_hv_ratio": j.get("iv_hv_ratio"),
            "call_volume": j.get("call_volume"),
            "put_volume": j.get("put_volume"),
            "call_put_ratio": j.get("call_put_ratio"),
            "sync_key": _h(ts, ticker),
            "raw_json": json.dumps(j),
        }


def x_orders():
    src = CACHE / "orders.jsonl"
    for j in _iter_jsonl(src):
        ts = j.get("timestamp")
        ticker = j.get("ticker")
        if not (ts and ticker):
            continue
        yield {
            "submitted_at": ts,
            "broker": "alpaca_paper" if j.get("dry_run") is False else "dry_run",
            "order_id": j.get("alpaca_order_id"),
            "client_order_id": j.get("client_order_id"),
            "ticker": ticker,
            "direction": j.get("side"),
            "side": j.get("side"),
            "order_type": j.get("order_type") or "limit",
            "qty": j.get("qty"),
            "limit_price": j.get("entry_limit") or j.get("limit_price"),
            "stop_price": j.get("stop"),
            "status": j.get("status"),
            "filled_qty": j.get("filled_qty"),
            "filled_avg_price": j.get("filled_avg_price"),
            "expected_price": j.get("entry_limit"),
            "setup_type": j.get("setup"),
            "sync_key": _h(ts, ticker, j.get("side"), j.get("qty")),
            "raw_json": json.dumps(j),
        }


def x_eod_actions():
    src = CACHE / "eod_actions.jsonl"
    for j in _iter_jsonl(src):
        ts = j.get("timestamp")
        if not ts:
            continue
        yield {
            "acted_at": ts,
            "action_type": j.get("kind") or "UNKNOWN",
            "ticker": j.get("ticker"),
            "qty": j.get("shares") or j.get("qty"),
            "new_stop": j.get("new_stop"),
            "reason": j.get("reason"),
            "auto": (j.get("submitted") is True),
            "sync_key": _h(ts, j.get("ticker"), j.get("kind")),
            "raw_json": json.dumps(j),
        }


def x_rolling_sharpe():
    src = DATA / "rolling_sharpe_history.jsonl"
    for j in _iter_jsonl(src):
        ts = j.get("ts") or j.get("date") or j.get("observed_at")
        if not ts:
            continue
        window = j.get("window_days") or 126
        yield {
            "observed_at": ts,
            "window_days": window,
            "sharpe": j.get("sharpe"),
            "sortino": j.get("sortino"),
            "calmar": j.get("calmar"),
            "max_drawdown": j.get("max_drawdown"),
            "n_trades": j.get("n_trades"),
            "win_rate": j.get("win_rate"),
            "profit_factor": j.get("profit_factor"),
            "avg_r_multiple": j.get("avg_r_multiple"),
            "sync_key": _h(ts, window),
            "raw_json": json.dumps(j),
        }


def x_fundamentals_pit():
    """data/fundamentals.db.fundamentals → fundamentals_pit"""
    db = DATA / "fundamentals.db"
    if not db.exists():
        return
    c = sqlite3.connect(str(db))
    c.row_factory = sqlite3.Row
    try:
        cur = c.execute("SELECT * FROM fundamentals")
        for row in cur:
            d = dict(row)
            ticker = d.get("ticker")
            fetched = d.get("fetched_at")
            if not (ticker and fetched):
                continue
            # Schema doesn't carry period_end (snapshot-keyed by ticker, not PIT).
            # Use fetched_at as the period_end proxy so the PK is unique.
            period = fetched[:10]  # YYYY-MM-DD
            yield {
                "ticker": ticker,
                "period_end": period,
                "report_date": d.get("last_earnings"),
                "fetched_at": fetched,
                "eps_ttm": d.get("eps_ttm"),
                "revenue_ttm": d.get("revenue_ttm"),
                "gross_margin": d.get("gross_margin"),
                "operating_margin": d.get("operating_margin"),
                "net_margin": d.get("profit_margin"),
                "fcf": d.get("fcf_ttm"),
                "debt_to_equity": d.get("debt_equity"),
                "revenue_growth_yoy": d.get("revenue_growth"),
                "eps_growth_yoy": d.get("eps_growth_qoq"),
                "shares_out": d.get("shares_out"),
                "market_cap": d.get("market_cap"),
                "sector": d.get("sector"),
                "industry": d.get("industry"),
                "sync_key": _h(ticker, period),
                "raw_json": json.dumps(d, default=str),
            }
    finally:
        c.close()


def x_ticker_enrichment():
    """data/enrichment_cache.db → ticker_enrichment_snapshot (11,907 rows)"""
    db = DATA / "enrichment_cache.db"
    if not db.exists():
        return
    c = sqlite3.connect(str(db))
    c.row_factory = sqlite3.Row
    try:
        cur = c.execute("SELECT * FROM enrichment")
        for row in cur:
            d = dict(row)
            ticker = d.get("ticker") or d.get("symbol") or d.get("key")
            fetched_at = d.get("fetched_at") or d.get("updated_at") or "1970-01-01T00:00:00Z"
            if not ticker:
                continue
            payload = d.get("payload") or d.get("value") or json.dumps({k: v for k, v in d.items() if k != "id"})
            if isinstance(payload, str):
                try:
                    payload_obj = json.loads(payload)
                except Exception:
                    payload_obj = {"raw": payload}
            else:
                payload_obj = payload
            yield {
                "ticker": ticker,
                "source": d.get("source") or "finviz_elite",
                "fetched_at": fetched_at,
                "ttl_seconds": d.get("ttl_seconds") or 21600,
                "payload": json.dumps(payload_obj),
                "sync_key": _h(ticker, fetched_at),
            }
    finally:
        c.close()


# =========================================================================
# Source registry
# =========================================================================
SOURCES = {
    "decision_log":               (x_decision_log,        "decision_log",               ["observed_at", "sync_key"]),
    "exit_signals":               (x_exit_signals,        "exit_signals",               ["sync_key"]),
    "earnings_outcomes":          (x_earnings_outcomes,   "earnings_outcomes",          ["sync_key"]),
    "iv_history":                 (x_iv_history,          "iv_history",                 ["sync_key"]),
    "orders":                     (x_orders,              "orders",                     ["sync_key"]),
    "eod_actions":                (x_eod_actions,         "eod_actions",                ["sync_key"]),
    "rolling_sharpe":             (x_rolling_sharpe,      "rolling_sharpe_history",     ["sync_key"]),
    "fundamentals_pit":           (x_fundamentals_pit,    "fundamentals_pit",           ["sync_key"]),
    "ticker_enrichment_snapshot": (x_ticker_enrichment,   "ticker_enrichment_snapshot", ["sync_key"]),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--only", default="", help="comma-separated subset")
    args = ap.parse_args()

    _load_dotenv()
    os.environ["SUPABASE_MODE"] = "1"
    sys.path.insert(0, str(ROOT))
    from supabase_client import sb_client, healthcheck

    print("=" * 72)
    print(f"Fold orphan data → Supabase  ({'APPLY' if args.apply else 'DRY-RUN'})")
    print("=" * 72)

    hc = healthcheck()
    print(f"Supabase healthcheck: ok={hc['ok']} url={hc.get('url')}")
    if not hc["ok"]:
        print(f"  ERROR: {hc.get('error')}")
        return 2

    sb = sb_client() if args.apply else None
    only = set(args.only.split(",")) if args.only else set()

    total_start = time.time()
    grand_total = 0
    grand_pushed = 0
    grand_failed = 0
    for name, (extractor, table, on_conflict_cols) in SOURCES.items():
        if only and name not in only:
            continue
        print(f"\n→ {name:32s} → {table}")
        t0 = time.time()
        batch: list[dict] = []
        n_source = 0
        n_pushed = 0
        n_failed = 0
        first_err = None
        on_conflict = ",".join(on_conflict_cols)

        seen_keys: set = set()

        def _flush(b: list[dict]) -> tuple[int, int, str | None]:
            # Dedupe within-batch by sync_key to avoid PG21000 ON CONFLICT collisions
            dedup = []
            for r in b:
                k = r.get("sync_key")
                if k and k in seen_keys:
                    continue
                if k:
                    seen_keys.add(k)
                dedup.append(r)
            if not dedup:
                return 0, 0, None
            try:
                sb.table(table).upsert(dedup, on_conflict=on_conflict).execute()
                return len(dedup), 0, None
            except Exception as e:
                return 0, len(dedup), f"{type(e).__name__}: {str(e)[:200]}"

        for row in extractor():
            n_source += 1
            batch.append(row)
            if len(batch) >= BATCH:
                if args.apply:
                    p, f, err = _flush(batch)
                    n_pushed += p; n_failed += f
                    if err and not first_err:
                        first_err = err
                batch = []
                if n_source % 5000 == 0:
                    print(f"   ...{n_source:,} read · {n_pushed:,} pushed · {n_failed:,} failed", end="\r")

        if batch and args.apply:
            p, f, err = _flush(batch)
            n_pushed += p; n_failed += f
            if err and not first_err:
                first_err = err

        elapsed = time.time() - t0
        print(f"   source={n_source:>7,}  pushed={n_pushed:>7,}  failed={n_failed:>5,}  {elapsed:>5.1f}s")
        if first_err:
            print(f"   ! first error: {first_err}")
        grand_total += n_source
        grand_pushed += n_pushed
        grand_failed += n_failed

    print("\n" + "=" * 72)
    print(f"Grand total source: {grand_total:>10,}")
    print(f"Grand total pushed: {grand_pushed:>10,}")
    print(f"Grand total failed: {grand_failed:>10,}")
    print(f"Elapsed: {time.time() - total_start:.1f}s")
    return 0 if grand_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Sidecar sync — read existing production JSON outputs and push derivable rows
to Supabase tables. Safe pattern: no modification to production code."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
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


def _h(*parts):
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:32]


def _iter_jsonl(path):
    if not path.exists(): return
    for line in path.read_text(errors="ignore").splitlines():
        line = line.strip()
        if not line: continue
        try: yield json.loads(line)
        except Exception: pass


def extract_stop_levels(eod_path):
    rows = []
    for j in _iter_jsonl(eod_path):
        kind = (j.get("kind") or "").upper()
        ticker = j.get("ticker")
        ts = j.get("timestamp")
        if not (ticker and ts): continue
        new_stop = j.get("new_stop")
        old_stop = j.get("old_stop")
        reason = j.get("reason") or ""
        if new_stop is None:
            m = re.search(r'\$(\d+\.\d{2})', reason)
            if m and ("stop" in reason.lower() or "trail" in reason.lower()):
                try: new_stop = float(m.group(1))
                except: pass
        if new_stop is None and kind not in ("STOP_HIT", "EXIT", "STOP_ADJUST"):
            continue
        rows.append({
            "adjusted_at": ts, "ticker": ticker,
            "old_stop": old_stop, "new_stop": new_stop,
            "reason": (kind + ": " + reason)[:200] if reason else kind,
            "triggered_by": "system" if j.get("submitted") else "manual",
            "sync_key": _h("sl", ts, ticker, kind),
            "raw_json": json.dumps(j),
        })
    return rows


def extract_slippage(orders_path):
    rows = []
    for j in _iter_jsonl(orders_path):
        ts = j.get("timestamp")
        ticker = j.get("ticker")
        expected = j.get("entry_limit")
        filled = j.get("filled_avg_price")
        side = j.get("side")
        if not (ts and ticker and expected and filled): continue
        slippage = filled - expected
        slippage_pct = (slippage / expected * 100) if expected else 0
        rows.append({
            "filled_at": ts, "ticker": ticker,
            "order_id": j.get("alpaca_order_id"),
            "side": "entry" if side == "buy" else "exit",
            "expected_price": expected, "filled_price": filled,
            "slippage_dollars": slippage,
            "slippage_pct": round(slippage_pct, 4),
            "slippage_bps": round(slippage_pct * 100, 2),
            "sync_key": _h("sr", ts, ticker, side),
        })
    return rows


def extract_kelly(kelly_log_path):
    """Fold cache/kelly_size_log.jsonl → kelly_size_history rows."""
    rows = []
    for j in _iter_jsonl(kelly_log_path):
        ts = j.get("decided_at")
        if not ts: continue
        rows.append({
            "decided_at": ts,
            "ticker": j.get("ticker"),
            "base_kelly": j.get("base_kelly"),
            "drawdown_mult": j.get("drawdown_mult"),
            "regime_mult": j.get("regime_mult"),
            "vix_mult": j.get("vix_mult"),
            "earnings_mult": j.get("earnings_mult"),
            "var_floor_mult": j.get("var_floor_mult"),
            "sharpe_mult": j.get("sharpe_mult"),
            "final_kelly": j.get("effective_regime_cap"),
            "final_size_pct": j.get("final_alloc_pct"),
            "final_shares": j.get("final_shares"),
            "reason": j.get("reason"),
            "sync_key": _h("kelly", ts, j.get("ticker", "?")),
            "raw_json": json.dumps(j),
        })
    return rows


def extract_watch(watch_log_path):
    """Fold cache/watch_triggers.jsonl → watch_triggers rows."""
    rows = []
    for j in _iter_jsonl(watch_log_path):
        ts = j.get("triggered_at")
        ticker = j.get("ticker")
        if not (ts and ticker): continue
        rows.append({
            "ticker": ticker,
            "triggered_at": ts,
            "run_date": j.get("run_date"),
            "sync_key": j.get("sync_key") or _h("wt", ts, ticker),
            "raw_json": json.dumps(j),
        })
    return rows


def extract_signal_filter(signal_log_path):
    rows = []
    if not signal_log_path.exists(): return rows
    try: j = json.loads(signal_log_path.read_text())
    except: return rows
    if not isinstance(j, list): return rows
    for s in j:
        date = s.get("date")
        ticker = s.get("ticker")
        if not (date and ticker): continue
        status = (s.get("status") or "").upper()
        score = s.get("score")
        allow = status in ("OPEN", "CLOSED")
        reason = "whitelisted" if allow else "demoted_by_filter"
        sb_band = None
        if score is not None:
            try:
                sb_band = f">{int(float(score)//10)*10}" if float(score) >= 60 else "<60"
            except: pass
        rows.append({
            "decided_at": date, "ticker": ticker,
            "setup_type": s.get("strategy") or s.get("setup_type"),
            "setup_family": s.get("setup_family"),
            "regime": s.get("regime_at_entry") or s.get("regime"),
            "score": int(float(score)) if score is not None else None,
            "score_band": sb_band,
            "entry_quality": s.get("entry_quality"),
            "allow": allow,
            "reason": reason,
            "raw_context": json.dumps(s),
        })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    _load_dotenv()
    os.environ["SUPABASE_MODE"] = "1"
    sys.path.insert(0, str(ROOT))
    from supabase_client import sb_client, healthcheck

    if not healthcheck()["ok"]:
        print("Supabase down"); return 2
    sb = sb_client()

    stop_rows = extract_stop_levels(ROOT / "cache" / "eod_actions.jsonl")
    slip_rows = extract_slippage(ROOT / "cache" / "orders.jsonl")
    sf_rows = extract_signal_filter(ROOT / "data" / "signal_log.json")
    kelly_rows = extract_kelly(ROOT / "cache" / "kelly_size_log.jsonl")
    watch_rows = extract_watch(ROOT / "cache" / "watch_triggers.jsonl")
    print(f"  stop_levels_history:     {len(stop_rows)} rows")
    print(f"  slippage_realized:       {len(slip_rows)} rows")
    print(f"  signal_filter_decisions: {len(sf_rows)} rows")
    print(f"  kelly_size_history:      {len(kelly_rows)} rows")
    print(f"  watch_triggers:          {len(watch_rows)} rows")

    if not args.apply:
        print("\nDry-run."); return 0

    def push(table, rows, key):
        if not rows: return (0, 0)
        seen = {}
        for r in rows: seen[r[key]] = r
        rows = list(seen.values())
        ok = fail = 0
        for i in range(0, len(rows), 200):
            batch = rows[i:i+200]
            try:
                sb.table(table).upsert(batch, on_conflict=key).execute()
                ok += len(batch)
            except Exception as e:
                fail += len(batch)
                print(f"  ! {table}: {type(e).__name__}: {str(e)[:200]}")
                break
        return ok, fail

    for table, rows, key in [
        ("stop_levels_history", stop_rows, "sync_key"),
        ("slippage_realized",   slip_rows, "sync_key"),
        ("kelly_size_history",  kelly_rows, "sync_key"),
        ("watch_triggers",      watch_rows, "sync_key"),
    ]:
        ok, fail = push(table, rows, key)
        print(f"  {table:30s} pushed={ok} failed={fail}")

    if sf_rows:
        # signal_filter_decisions — no sync_key, plain insert capped at 500
        ok = fail = 0
        try:
            sb.table("signal_filter_decisions").insert(sf_rows[:500]).execute()
            ok = min(500, len(sf_rows))
        except Exception as e:
            fail = len(sf_rows)
            print(f"  ! signal_filter_decisions: {type(e).__name__}: {str(e)[:200]}")
        print(f"  signal_filter_decisions        pushed={ok} failed={fail} (capped at 500)")

    return 0


if __name__ == "__main__":
    sys.exit(main())

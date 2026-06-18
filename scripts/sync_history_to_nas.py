#!/usr/bin/env python3
"""
sync_history_to_nas.py — back up the precious track-history files to NAS Postgres.

Mirrors the audit-critical JSON histories into schema-flexible JSONB archive tables
on the NAS deep store (full retention), so the local files are no longer the only
copy — and so the audit can query them straight from Postgres.

Sources → NAS table:
  data/signal_log.json            → signal_log_archive
  cache/audit_ledger.json records → audit_ledger_archive
  cache/picks_history.json runs   → picks_runs_archive
                          trades   → picks_trades_archive
                  watch_triggers   → picks_watch_archive
  cache/ml_edge_picks_history.jsonl → ml_edge_archive

Idempotent (ON CONFLICT upsert). Best-effort — NAS down = no-op. Run any time;
wired into the nightly com.swingtrade.nas-sync job alongside the snapshot sync.

  python3 scripts/sync_history_to_nas.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import nas_pg


def _with_id(records, idfn):
    out = []
    for i, r in enumerate(records):
        if not isinstance(r, dict):
            continue
        rr = dict(r)
        rr["row_id"] = idfn(i, r)
        out.append(rr)
    return out


def _load_json(p: Path):
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def main():
    if not nas_pg.enabled():
        print("NAS_PG_URL not set — nothing to sync"); return
    total = 0

    # 1) signal_log.json (append-only list)
    sl = _load_json(ROOT / "data" / "signal_log.json")
    if isinstance(sl, list):
        rows = _with_id(sl, lambda i, r: f"{i}|{r.get('ticker')}|{r.get('date')}")
        n = nas_pg.archive_json("signal_log_archive", rows, ["row_id"])
        print(f"  signal_log_archive: {n}"); total += n

    # 2) audit_ledger records (already deduped by ticker+pick_date)
    al = _load_json(ROOT / "cache" / "audit_ledger.json")
    if isinstance(al, dict) and isinstance(al.get("records"), list):
        rows = _with_id(al["records"],
                        lambda i, r: f"{r.get('ticker')}|{r.get('pick_date')}|{r.get('mode')}")
        n = nas_pg.archive_json("audit_ledger_archive", rows, ["row_id"])
        print(f"  audit_ledger_archive: {n}"); total += n

    # 3) picks_history.json — runs / trades / watch_triggers
    ph = _load_json(ROOT / "cache" / "picks_history.json")
    if isinstance(ph, dict):
        runs = ph.get("runs") or []
        n = nas_pg.archive_json("picks_runs_archive",
                                _with_id(runs, lambda i, r: f"run|{r.get('run_date')}"),
                                ["row_id"])
        print(f"  picks_runs_archive: {n}"); total += n
        trades = ph.get("trades") or []
        n = nas_pg.archive_json("picks_trades_archive",
                                _with_id(trades, lambda i, r: f"{i}|{r.get('ticker')}|{r.get('entry_date') or r.get('date')}"),
                                ["row_id"])
        print(f"  picks_trades_archive: {n}"); total += n
        wt = ph.get("watch_triggers") or []
        n = nas_pg.archive_json("picks_watch_archive",
                                _with_id(wt, lambda i, r: f"{i}|{r.get('ticker')}|{r.get('date')}"),
                                ["row_id"])
        print(f"  picks_watch_archive: {n}"); total += n

    # 4) ml_edge_picks_history.jsonl (one JSON per line)
    mlf = ROOT / "cache" / "ml_edge_picks_history.jsonl"
    if mlf.exists():
        recs = []
        for ln in mlf.read_text().splitlines():
            ln = ln.strip()
            if ln:
                try:
                    recs.append(json.loads(ln))
                except Exception:
                    pass
        rows = _with_id(recs, lambda i, r: f"{i}|{r.get('ticker')}|{r.get('scan_date')}")
        n = nas_pg.archive_json("ml_edge_archive", rows, ["row_id"])
        print(f"  ml_edge_archive: {n}"); total += n

    print(f"✓ history sync done · {total} records upserted to NAS")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""precompute_rolling_tail.py — Pass 3 · rolling-tail warm (Finviz + archive, cheap).

Daily-Clock warm passes (Phase 3a). Passes 1-2 warm the HOT set (top-1000 by
dollar-volume) + the day's strategy picks with the full heavy lift (structural
targets ×3 modes, SMC, fundamentals, options/IV). That leaves the long TAIL —
universe − hot-set − strategy-picks, ~2,100 names — cold.

This pass warms ONLY the CHEAP layer for the tail, in batches, throughout the
session, converging to full tail coverage by EOD:

  CHEAP layer (what we DO compute here):
    • Finviz bulk fundamentals — already pulled once daily and cached 4h
      (data_fetcher.get_finviz_bulk, keyed finviz_bulk_<YYYYMMDD>). We call it
      ONCE per batch-run and reuse the cached dict for every tail name — we do
      NOT re-scrape per ticker. The membership check is a free dict lookup that
      confirms the name is covered by today's Finviz pull.
    • Daily bars — ARCHIVE-FIRST: data_archive.load_ticker() is a pure local
      Parquet read (zero API). The daily delta_update job keeps the archive
      current, so for the overwhelming majority of tail names this is a local
      read. Only when a name is MISSING from the archive do we fetch one EODHD
      delta via fetch_ohlcv_with_failover (EODHD→Schwab→archive chain).

  DEFERRED to on-click (what we do NOT compute here — too expensive for the tail):
    • 4H Schwab intraday bars
    • Elliott-Wave weekly / monthly
    • full structural target_engine (T1/T2/T3) ×3 modes
    • options / IV chains
  These stay on-demand: the FastAPI endpoints compute + cache them on first
  click for any tail name a user actually opens.

State / convergence:
  A state file (cache/rolling_tail_state.json, 12h TTL) records which tail names
  are done THIS cycle. Each batch advances through the not-yet-done remainder,
  so successive 45-min in-session runs converge through the ~2,100 tail and the
  whole tail is warmed by EOD. The state resets (empties) when older than 12h or
  when the tail composition changes materially (different scan day).

Politeness:
  Intended to run `nice` (low CPU priority) and HEAVY-labeled in launchd so it
  yields to the scan / heavy jobs. Client rate-limiters handle EODHD/Schwab
  pacing; the only API this pass can touch is the rare missing-archive EODHD
  delta.

Usage:
    python3 scripts/precompute_rolling_tail.py --dry-run            # plan + tail/batch counts, ZERO fetches
    python3 scripts/precompute_rolling_tail.py --batch-size 150     # one batch (advances state)
    python3 scripts/precompute_rolling_tail.py --limit 10           # tiny test
    python3 scripts/precompute_rolling_tail.py --reset              # clear state, start tail over
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import precompute_top1000 as pt              # noqa: E402  (universe rank + helpers)
import precompute_strategy_picks as psp      # noqa: E402  (sleeve-pick sourcing)

STATE_FILE = ROOT / "cache" / "rolling_tail_state.json"
STATE_TTL_S = 12 * 3600  # 12h


# ──────────────────────────────────────────────────────────────────────────
# State (which tail names are done this cycle)
# ──────────────────────────────────────────────────────────────────────────
def _load_state() -> dict:
    """Load the rolling-tail state. Empty/reset if stale (>12h) or unreadable."""
    try:
        st = json.loads(STATE_FILE.read_text())
        ts = float(st.get("started_ts", 0))
        if (time.time() - ts) > STATE_TTL_S:
            return {"started_ts": time.time(), "done": [], "tail_size": 0, "stale_reset": True}
        st.setdefault("done", [])
        return st
    except Exception:
        return {"started_ts": time.time(), "done": [], "tail_size": 0}


def _save_state(st: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(st, indent=2))


# ──────────────────────────────────────────────────────────────────────────
# Tail computation: universe − hot-set − strategy-picks
# ──────────────────────────────────────────────────────────────────────────
def compute_tail(top: int, top_per_sleeve: int) -> tuple[list, dict]:
    """Returns (tail_tickers, meta). tail = ranked-universe − hot-set − picks,
    minus delisted-tombstoned names."""
    # 1) Rank universe (one bulk_eod call) — same ranking as the hot-set pass.
    ranked, _dv = pt.rank_top(top_n=10 ** 9)  # rank ALL candidates (we slice below)
    hot = set(ranked[:top])

    # union the always-include set into the hot set (track-record + portfolio)
    hot |= pt._audit_ledger_tickers()
    hot |= pt._portfolio_tickers()

    # 2) Strategy picks (already warmed by Pass 2) — exclude from the tail.
    by_sleeve, _meta = psp.load_sleeve_picks(top_per_sleeve)
    picks = set()
    for s in psp.SLEEVES:
        for t, _sc in (by_sleeve.get(s) or []):
            picks.add(t)

    # 3) Tombstones — never warm a delisted name.
    tomb = set()
    try:
        import delisted_registry as dr
        if dr.is_enabled():
            tomb = dr.tombstoned_set()
    except Exception:
        tomb = set()

    tail = [t for t in ranked if t not in hot and t not in picks and t not in tomb]
    meta = {
        "ranked_universe": len(ranked),
        "hot_set": len(hot),
        "strategy_picks": len(picks),
        "tombstoned": len(tomb),
        "tail_size": len(tail),
    }
    return tail, meta


# ──────────────────────────────────────────────────────────────────────────
# Cheap warm (one ticker): Finviz membership (from prefetched bulk) + archive-first bars
# ──────────────────────────────────────────────────────────────────────────
def _warm_cheap(ticker: str, finviz_bulk: dict, stats: dict, failures: list) -> None:
    # 1) Finviz fundamentals — reuse the single prefetched bulk dict (no per-name scrape).
    if ticker in finviz_bulk:
        stats["finviz_hit"] += 1
    else:
        stats["finviz_miss"] += 1   # not in today's Finviz pull (e.g. illiquid/foreign)

    # 2) Daily bars — ARCHIVE-FIRST (local Parquet read, zero API).
    try:
        import data_archive as da
        df = da.load_ticker(ticker)
        if df is not None and len(df) >= 20:
            stats["bars_archive"] += 1
            return
    except Exception as e:
        failures.append({"ticker": ticker, "stage": "archive_read", "error": f"{type(e).__name__}: {e}"})

    # 3) Missing from archive → one EODHD delta via the failover chain.
    try:
        import data_fetcher as dfetch
        df, tier = dfetch.fetch_ohlcv_with_failover(ticker, days=400)
        if df is not None and len(df) >= 20:
            stats[f"bars_{tier}"] = stats.get(f"bars_{tier}", 0) + 1
        else:
            stats["bars_empty"] += 1
    except Exception as e:
        stats["bars_err"] += 1
        failures.append({"ticker": ticker, "stage": "bars_failover", "error": f"{type(e).__name__}: {e}"})


# ──────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Pass 3 · rolling-tail warm (cheap layer only)")
    ap.add_argument("--top", type=int, default=1000, help="hot-set cutoff to exclude from tail (default 1000)")
    ap.add_argument("--top-per-sleeve", type=int, default=20, help="strategy picks/sleeve to exclude (default 20)")
    ap.add_argument("--batch-size", type=int, default=150, help="tail names per run (default 150)")
    ap.add_argument("--limit", type=int, default=None, help="cap this batch (testing)")
    ap.add_argument("--dry-run", action="store_true", help="plan + tail/batch counts only, ZERO fetches")
    ap.add_argument("--reset", action="store_true", help="clear state and start the tail over")
    args = ap.parse_args()

    t_start = time.time()
    print(f"\n══ precompute_rolling_tail (Pass 3) · {time.strftime('%Y-%m-%d %H:%M:%S')} ══")
    print(f"  top(hot-set)={args.top}  top_per_sleeve={args.top_per_sleeve}  "
          f"batch_size={args.batch_size}  nice={os.nice(0)}")

    # ── Compute the tail ──
    print("\n── Computing tail (universe − hot-set − strategy-picks − tombstones) ──")
    tail, meta = compute_tail(args.top, args.top_per_sleeve)
    print(f"  ranked universe : {meta['ranked_universe']}")
    print(f"  hot set (excl)  : {meta['hot_set']}")
    print(f"  strat picks(excl): {meta['strategy_picks']}")
    print(f"  tombstoned(excl): {meta['tombstoned']}")
    print(f"  TAIL size       : {meta['tail_size']}")

    # ── State: which tail names are already done this cycle ──
    if args.reset:
        st = {"started_ts": time.time(), "done": [], "tail_size": meta["tail_size"]}
        print("  --reset → state cleared")
    else:
        st = _load_state()
        if st.get("stale_reset"):
            print("  state >12h old → reset (fresh tail cycle)")
        # if tail size changed materially (new scan day), reset progress
        if abs(int(st.get("tail_size", 0)) - meta["tail_size"]) > max(50, meta["tail_size"] * 0.1):
            print(f"  tail size changed ({st.get('tail_size')} → {meta['tail_size']}) → reset progress")
            st = {"started_ts": time.time(), "done": [], "tail_size": meta["tail_size"]}
    done = set(st.get("done", []))
    st["tail_size"] = meta["tail_size"]

    remaining = [t for t in tail if t not in done]
    print(f"\n── Progress ──")
    print(f"  done so far this cycle: {len(done)} / {meta['tail_size']}")
    print(f"  remaining             : {len(remaining)}")

    batch = remaining[: args.batch_size]
    if args.limit:
        batch = batch[: args.limit]
    print(f"  THIS batch            : {len(batch)} names")
    if batch:
        print(f"    {batch[:15]}{' …' if len(batch) > 15 else ''}")

    if args.dry_run:
        n_cycles = (len(remaining) + args.batch_size - 1) // max(1, args.batch_size)
        print(f"\n[DRY RUN] no fetches performed. Exiting.")
        print(f"  [DRY RUN] cheap layer = Finviz-bulk membership (prefetched once) + "
              f"archive-first daily bars (local Parquet; EODHD delta only if missing).")
        print(f"  [DRY RUN] DEFERRED to on-click: 4H Schwab, EW weekly/monthly, full structural targets, options.")
        print(f"  [DRY RUN] at batch_size={args.batch_size}: ~{n_cycles} more runs to converge the remaining tail.")
        pt._write_log({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "mode": "dry_run", "pass": "rolling_tail",
            "tail_meta": meta, "done": len(done), "remaining": len(remaining),
            "batch": len(batch), "batch_size": args.batch_size,
        })
        return

    if not batch:
        print("\n  Tail fully warmed this cycle — nothing to do. Exiting cleanly.")
        return

    # ── Prefetch Finviz bulk ONCE (cached 4h) — reused for every name in batch ──
    print("\n── Prefetching Finviz bulk (once; 4h-cached, reused per name) ──")
    finviz_bulk: dict = {}
    try:
        import data_fetcher as dfetch
        finviz_bulk = dfetch.get_finviz_bulk() or {}
        print(f"  Finviz bulk: {len(finviz_bulk)} tickers covered")
    except Exception as e:
        print(f"  Finviz bulk fetch failed (non-fatal — bars still warm): {e}")

    # ── Warm cheap layer for the batch ──
    print(f"\n── Warming {len(batch)} tail names (cheap layer) ──")
    stats = {k: 0 for k in (
        "finviz_hit", "finviz_miss",
        "bars_archive", "bars_eodhd", "bars_schwab", "bars_empty", "bars_err",
    )}
    failures: list = []
    for i, t in enumerate(batch, 1):
        _warm_cheap(t, finviz_bulk, stats, failures)
        done.add(t)
        if i % 50 == 0 or i == len(batch):
            elapsed = time.time() - t_start
            print(f"  [{i:3d}/{len(batch)}] {elapsed:6.1f}s · "
                  f"fv(hit={stats['finviz_hit']},miss={stats['finviz_miss']}) "
                  f"bars(arch={stats['bars_archive']},eodhd={stats['bars_eodhd']},"
                  f"schwab={stats['bars_schwab']},err={stats['bars_err']})")

    # ── Persist state ──
    st["done"] = sorted(done)
    _save_state(st)

    elapsed = round(time.time() - t_start, 1)
    print(f"\n══ Summary ({elapsed}s) ══")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print(f"  cycle progress: {len(done)} / {meta['tail_size']}  "
          f"({len(done) * 100 // max(1, meta['tail_size'])}%)")
    if failures:
        print(f"  failures: {len(failures)} (first 10):")
        for f in failures[:10]:
            print(f"    {f['ticker']:6s} {f['stage']:16s} {f['error']}")

    pt._write_log({
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": "run", "pass": "rolling_tail",
        "tail_meta": meta, "batch": len(batch),
        "done_after": len(done), "remaining_after": meta["tail_size"] - len(done),
        "elapsed_sec": elapsed, "stats": stats,
        "failures_count": len(failures), "failures_first_10": failures[:10],
    })


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""precompute_strategy_picks.py — Pass 2 · post-scan strategy warm + catalyst options/IV.

Daily-Clock warm passes (Phase 3a). The ~5:00 AM scan ranks the universe and
emits per-ticker picks tagged with a `setup_family` that — when a strategy
sleeve fires — IS the sleeve name (the 6 sleeve detectors in analysis.py
overwrite setup_family to "Momentum Continuation" / "PEAD" / "Insider Cluster" /
"ESP Play" / "Mean Reversion" / "Defensive Rotation"; everything else is the
core "Pullback to Value" engine, i.e. base families Trend Continuation /
Breakout Expansion / Impulse Catalyst).

This pass runs AFTER the scan (06:15 PT) and warms the day's TOP-20-per-sleeve
picks across the 7 sleeves (~140 names). Most of those names already had their
structural / SMC / fundamentals caches warmed by the EOD (7:30 PM) and morning
(3 AM) precompute_top1000 passes, so the NEW work here is mostly:

  • options/IV via Schwab (`schwab_client.get_chains`) — the catalyst sleeves
    PEAD / ESP Play need IV AT SIGNAL TIME, and the EOD/morning passes skip
    options (Schwab chains are in-session only). This is the gap Pass 2 closes
    (Open Risk #4).
  • structural / SMC / fundamentals gap-fill for any pick OUTSIDE the hot set
    (precompute_top1000 warms top-1000 by dollar-volume — a low-liquidity sleeve
    pick can fall outside it).

It REUSES precompute_top1000.warm_ticker (no duplicate warm logic) and the
shared scripts/lib/coverage_report.emit_coverage. Options-warm is FORCED ON in
this pass (skip_options=False) — that is the whole point of Pass 2 — and is
gated to this script (the nightly passes keep options off).

Sleeve picks are sourced from cache/last_bundle.json (the freshest scan output;
run_timestamp + run_date are stamped on it). We scan EVERY scored list
(all_scored ∪ buy_candidates ∪ watch_list ∪ medium_term_picks ∪
long_term_picks) so we catch sleeve picks regardless of which bucket the scan
routed them to, dedupe by ticker (best score wins), group by sleeve, and take
the top 20 per sleeve by score. If a sleeve has < 20 picks today, we take what
it has (most days the catalyst sleeves fire 0-handful).

Usage:
    python3 scripts/precompute_strategy_picks.py --dry-run     # plan + per-sleeve counts, ZERO fetches
    python3 scripts/precompute_strategy_picks.py --top-per-sleeve 20
    python3 scripts/precompute_strategy_picks.py --limit 5     # tiny test
    python3 scripts/precompute_strategy_picks.py               # real run (warms picks + options/IV)
    python3 scripts/precompute_strategy_picks.py --no-options  # skip options (debug)
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Reuse precompute_top1000's warm helpers + budget + coverage loader — do NOT
# duplicate warm logic (constraint: reuse, don't duplicate).
import precompute_top1000 as pt  # noqa: E402

ALL_MODES = pt.ALL_MODES
LAST_BUNDLE = ROOT / "cache" / "last_bundle.json"

# ── Sleeve roster (7 sleeves) ───────────────────────────────────────────────
# setup_family string written by analysis.py → canonical sleeve key. The 6
# strategy-sleeve detectors overwrite setup_family to their sleeve name; the
# 3 base families collapse into the core "Pullback to Value" engine.
SLEEVE_FAMILIES = {
    "Momentum Continuation": "Momentum",
    "Defensive Rotation":    "Defensive Rotation",
    "Mean Reversion":        "Mean Reversion",
    "PEAD":                  "PEAD",
    "Insider Cluster":       "Insider Cluster",
    "ESP Play":              "ESP",
    # core engine (base families) → Pullback
    "Trend Continuation":    "Pullback",
    "Breakout Expansion":    "Pullback",
    "Impulse Catalyst":      "Pullback",
}
# The 7 canonical sleeve buckets we report (stable order).
SLEEVES = ["Pullback", "Momentum", "Defensive Rotation",
           "Mean Reversion", "PEAD", "Insider Cluster", "ESP"]

# Lists in last_bundle.json that carry scored per-ticker pick dicts.
PICK_LIST_KEYS = [
    "all_scored", "buy_candidates", "watch_list",
    "medium_term_picks", "long_term_picks",
]


def _sleeve_for(row: dict) -> str | None:
    fam = (row.get("setup_family") or "").strip()
    return SLEEVE_FAMILIES.get(fam)


def load_sleeve_picks(top_per_sleeve: int) -> tuple[dict, dict]:
    """Read the freshest scan output and group picks by sleeve.

    Returns (picks_by_sleeve, meta) where picks_by_sleeve maps sleeve → list of
    (ticker, score) sorted desc, truncated to top_per_sleeve.
    """
    if not LAST_BUNDLE.exists():
        print(f"  ! {LAST_BUNDLE} not found — no scan output to source picks from.")
        return {s: [] for s in SLEEVES}, {"source": None}

    try:
        bundle = json.loads(LAST_BUNDLE.read_text())
    except Exception as e:
        print(f"  ! failed to read last_bundle.json: {e}")
        return {s: [] for s in SLEEVES}, {"source": None}

    # Dedupe by ticker — keep the highest-scoring occurrence across all lists.
    best: dict[str, dict] = {}
    seen_lists = {}
    for key in PICK_LIST_KEYS:
        rows = bundle.get(key) or []
        seen_lists[key] = len(rows) if isinstance(rows, list) else 0
        if not isinstance(rows, list):
            continue
        for r in rows:
            if not isinstance(r, dict):
                continue
            t = (r.get("ticker") or "").strip().upper()
            if not t:
                continue
            try:
                sc = float(r.get("score") or 0)
            except (TypeError, ValueError):
                sc = 0.0
            prev = best.get(t)
            if prev is None or sc > float(prev.get("score") or 0):
                best[t] = r

    # Drop delisted-tombstoned names (respect the delisted registry skip).
    tomb = set()
    try:
        import delisted_registry as dr
        if dr.is_enabled():
            tomb = dr.tombstoned_set()
    except Exception:
        tomb = set()

    by_sleeve: dict[str, list] = {s: [] for s in SLEEVES}
    skipped_tomb = 0
    for t, r in best.items():
        if t in tomb:
            skipped_tomb += 1
            continue
        sleeve = _sleeve_for(r)
        if sleeve is None:
            continue
        try:
            sc = float(r.get("score") or 0)
        except (TypeError, ValueError):
            sc = 0.0
        by_sleeve[sleeve].append((t, sc))

    # Sort each sleeve desc by score, take top N.
    for s in SLEEVES:
        by_sleeve[s].sort(key=lambda x: x[1], reverse=True)
        by_sleeve[s] = by_sleeve[s][:top_per_sleeve]

    meta = {
        "source": str(LAST_BUNDLE),
        "run_date": bundle.get("run_date"),
        "run_timestamp": bundle.get("run_timestamp"),
        "lists_scanned": seen_lists,
        "unique_tickers": len(best),
        "skipped_tombstoned": skipped_tomb,
    }
    return by_sleeve, meta


def main():
    ap = argparse.ArgumentParser(description="Pass 2 · post-scan strategy warm + catalyst options/IV")
    ap.add_argument("--top-per-sleeve", type=int, default=20, help="picks per sleeve (default 20)")
    ap.add_argument("--modes", nargs="*", default=ALL_MODES, choices=ALL_MODES)
    ap.add_argument("--limit", type=int, default=None, help="cap warmed-ticker count (testing)")
    ap.add_argument("--dry-run", action="store_true", help="plan + per-sleeve counts only, ZERO fetches")
    ap.add_argument("--force", action="store_true", help="bypass 12h target cache (recompute)")
    ap.add_argument("--no-options", dest="warm_options", action="store_false", default=True,
                    help="skip the Schwab options/IV warm (debug; defeats the purpose of Pass 2)")
    ap.add_argument("--skip-smc", action="store_true", help="skip SMC warm (already warmed by EOD pass)")
    ap.add_argument("--skip-fundamentals", dest="skip_fund", action="store_true",
                    help="skip fundamentals warm (already warmed nightly)")
    args = ap.parse_args()

    t_start = time.time()
    print(f"\n══ precompute_strategy_picks (Pass 2) · {time.strftime('%Y-%m-%d %H:%M:%S')} ══")
    print(f"  top_per_sleeve={args.top_per_sleeve}  modes={args.modes}  "
          f"warm_options={args.warm_options}  force={args.force}")

    # ── Source sleeve picks from the freshest scan ──
    print("\n── Sourcing sleeve picks (cache/last_bundle.json) ──")
    by_sleeve, meta = load_sleeve_picks(args.top_per_sleeve)
    if meta.get("source"):
        print(f"  scan: run_date={meta.get('run_date')} run_timestamp={meta.get('run_timestamp')}")
        print(f"  lists scanned: {meta.get('lists_scanned')}")
        print(f"  unique scored tickers: {meta.get('unique_tickers')}  "
              f"· dropped tombstoned: {meta.get('skipped_tombstoned')}")

    print("\n── Picks per sleeve (top {} each) ──".format(args.top_per_sleeve))
    final_set: list[str] = []
    seen = set()
    for s in SLEEVES:
        picks = by_sleeve.get(s) or []
        tickers = [t for t, _ in picks]
        print(f"  {s:18s}: {len(picks):3d} picks  {tickers[:12]}{' …' if len(tickers) > 12 else ''}")
        for t in tickers:
            if t not in seen:
                seen.add(t)
                final_set.append(t)

    print(f"\n  TOTAL unique strategy picks to warm: {len(final_set)}")

    if args.limit:
        final_set = final_set[: args.limit]
        print(f"  --limit → first {len(final_set)}: {final_set}")

    # ── Budget (reuse precompute_top1000.estimate_budget) ──
    skip_options = not args.warm_options
    budget = pt.estimate_budget(len(final_set), args.modes, args.skip_smc, args.skip_fund, skip_options)
    print(f"\n── Budget estimate (worst case, all cold) ──")
    print(f"  EODHD units (worst case): ~{budget['eodhd_units_worst_case']:,}")
    print(f"  Schwab get_chains calls:  {budget['schwab_calls']:,}  "
          f"{'(options/IV warm — the Pass-2 gap)' if not skip_options else '(options OFF)'}")
    print(f"  Est. runtime:             ~{budget['est_runtime_min']} min")
    print(f"  (12h-fresh structural/SMC caches from the EOD+morning passes are skipped → real cost far lower)")

    q = pt.quota_state()
    print(f"\n── EODHD quota now ──")
    print(f"  count={q.get('count'):,}  soft_limit={q.get('soft_limit'):,}  "
          f"remaining={q.get('remaining'):,}")

    if args.dry_run:
        print("\n[DRY RUN] no fetches performed. Exiting.")
        print(f"  [DRY RUN] options-warm step is {'ON (Schwab get_chains per pick)' if not skip_options else 'OFF'} "
              f"and is gated to THIS (strategy) pass only.")
        pt._write_log({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "mode": "dry_run", "pass": "strategy_picks",
            "top_per_sleeve": args.top_per_sleeve,
            "picks_per_sleeve": {s: len(by_sleeve.get(s) or []) for s in SLEEVES},
            "warm_set": len(final_set), "warm_options": args.warm_options,
            "budget": budget, "quota": q, "scan_meta": meta,
        })
        return

    if not final_set:
        print("\n  No sleeve picks to warm today. Exiting cleanly.")
        return

    # ── Abort if quota already past soft_limit ──
    if q.get("count", 0) > q.get("soft_limit", 95000):
        print(f"\n⛔ ABORT: EODHD usage {q.get('count'):,} > soft_limit {q.get('soft_limit'):,}. "
              f"Refusing a real run to protect the daily quota. Re-run after reset or use --dry-run.")
        sys.exit(2)

    # ── Warm (reuse precompute_top1000.warm_ticker) ──
    # Options forced ON for the strategy pass — this is the IV-at-signal gap.
    print(f"\n── Warming {len(final_set)} strategy picks "
          f"(structural + SMC + fundamentals{' + options/IV' if not skip_options else ''}) ──")
    steps = pt.PHASE_STEPS["full"]
    stats = {k: 0 for k in (
        "target_cache_hit", "target_computed", "target_err", "target_gap_skip",
        "fund_ok", "fund_empty", "fund_err",
        "smc_ok", "smc_nodata", "smc_err",
        "options_ok", "options_empty", "options_err",
    )}
    failures: list = []
    log_every = 20
    for i, t in enumerate(final_set, 1):
        pt.warm_ticker(t, args.modes, args.force, args.skip_smc, args.skip_fund,
                       skip_options, stats, failures, steps=steps)
        if i % log_every == 0 or i == len(final_set):
            elapsed = time.time() - t_start
            print(f"  [{i:3d}/{len(final_set)}] {elapsed:6.1f}s · "
                  f"tgt(hit={stats['target_cache_hit']},new={stats['target_computed']},err={stats['target_err']}) "
                  f"opt(ok={stats['options_ok']},empty={stats['options_empty']},err={stats['options_err']})")

    elapsed = round(time.time() - t_start, 1)
    print(f"\n══ Summary ({elapsed}s) ══")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    if failures:
        print(f"  failures: {len(failures)} (first 10):")
        for f in failures[:10]:
            print(f"    {f['ticker']:6s} {f['stage']:14s} {f['error']}")

    pt._write_log({
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": "run", "pass": "strategy_picks",
        "top_per_sleeve": args.top_per_sleeve,
        "picks_per_sleeve": {s: len(by_sleeve.get(s) or []) for s in SLEEVES},
        "warm_set": len(final_set), "warm_options": args.warm_options,
        "modes": args.modes, "elapsed_sec": elapsed, "stats": stats,
        "failures_count": len(failures), "failures_first_10": failures[:10],
        "budget": budget, "quota_after": pt.quota_state(), "scan_meta": meta,
    })

    # ── Coverage observability (reuse shared emit_coverage) ──
    target_total = stats["target_cache_hit"] + stats["target_computed"] + stats["target_err"]
    try:
        emit_coverage = pt._load_emit_coverage()
        by_source = {
            "target": {"total": target_total,
                       "warmed": stats["target_cache_hit"] + stats["target_computed"],
                       "failed": stats["target_err"]},
        }
        if not skip_options:
            by_source["options"] = {"warmed": stats["options_ok"] + stats["options_empty"],
                                    "failed": stats["options_err"]}
        emit_coverage(
            job="precompute_strategy_picks",
            stats={
                "total": target_total,
                "warmed": stats["target_cache_hit"] + stats["target_computed"],
                "failed": stats["target_err"],
                "duration_s": elapsed,
                "by_mode": by_source,
            },
            slack=True,
            slack_always=False,
        )
    except Exception as e:
        print(f"[coverage] emit failed (non-fatal): {e}")


if __name__ == "__main__":
    main()

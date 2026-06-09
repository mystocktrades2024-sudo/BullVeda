#!/usr/bin/env python3
"""precompute_top1000.py — unified warm-cache batch for the top-N ranked tickers.

Consolidates the per-detail-tab on-demand caches into ONE nightly job so the
top-1000 most-liquid tickers have every detail tab instant + fully populated:
Overview/Plan (target_engine), Fundamentals (EODHD), SMC (pattern_engines).
The long tail (beyond top-N) stays on-demand — the same caches are written by
the FastAPI endpoints on first click.

Why a single job instead of three separate ones:
- One bulk_eod(US) call ranks the whole universe by dollar-volume (close×volume)
  — no per-ticker fetch for ranking.
- A single ticker loop warms target_engine × 3 modes + fundamentals + SMC, so the
  expensive 4H/EW/SMC fetches each ticker triggers happen once, off-peak, on a
  fresh daily EODHD quota — instead of hundreds of unpredictable daytime
  cold-computes at 500+ users.

Caches warmed (each guarded; one failure never aborts the batch):
  - target_engine.analyze_trade_cached(t, mode) × {swing,position,invest}
      → cache/target_engine/{T}_{MODE}.json   (12h TTL, schema v2)  [Overview/Plan]
  - eodhd_client.fundamentals(t)
      → 7-day EODHD cache (same call /api/fundamentals + get_fundamentals_rich use)
  - pattern_engines.detect("smc", t, mode) via precompute_smc_risk
      → cache/pattern_precompute/smc_{T}_{MODE}.json                [SMC]
  - options: SKIPPED by default (Schwab chains are in-session only — off-hours
      warming is pointless). --no-skip-options calls schwab_client.get_chains(t).

NOT warmed here:
  - ML predictions — produced by a SEPARATE pipeline (scripts/ml_predict.sh →
    cache/ml_edge_predictions.json), currently capped at ~500 tickers. This script
    does NOT retrain ML; it REPORTS the cap-500 < top-1000 gap and recommends
    bumping the ml-predict cap so tickers 500–1000 get ML coverage too.

Always-included (UNION with top-N, even if outside it):
  - every ticker in cache/audit_ledger.json (track-record)
  - every ticker in data/portfolio_state.json (open positions + closed trades)

Phase split (Daily-Clock rebuild — structural targets are a function of the
FINAL daily bar, so compute them ONCE at EOD when the bar is fresh, not crammed
at 3 AM):
  --phase eod      HEAVY: structural targets (×3 modes) + SMC — the bar-dependent
                   lift (~8.3k EODHD + ~2.8k Schwab-4H). Gate behind --wait-for-eod
                   so it never runs on a stale bar.
  --phase morning  LIGHT (~5 min): Finviz/EODHD fundamentals refresh + gap-fill
                   ONLY the structural caches that are missing/stale (names that
                   failed at EOD, or new since). No 4H critical-path lift.
  --phase full     EVERYTHING (default for manual runs) — current behavior.

Usage:
    python3 scripts/precompute_top1000.py --dry-run                  # rank + plan + budget, ZERO fetches
    python3 scripts/precompute_top1000.py --phase eod --wait-for-eod # 19:30 heavy (poll for fresh bar)
    python3 scripts/precompute_top1000.py --phase morning            # 3 AM light gap-fill + fundamentals
    python3 scripts/precompute_top1000.py --phase eod --dry-run      # show eod step plan
    python3 scripts/precompute_top1000.py --limit 3                  # tiny test (warms 3)
    python3 scripts/precompute_top1000.py                            # full run (top 1000 ∪ track ∪ portfolio)
    python3 scripts/precompute_top1000.py --top 500                  # smaller N
    python3 scripts/precompute_top1000.py --modes swing              # one mode
    python3 scripts/precompute_top1000.py --force                    # bypass 12h target cache
    python3 scripts/precompute_top1000.py --no-skip-options          # also warm Schwab chains (in-session only)
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ALL_MODES = ["swing", "position", "invest"]
# pattern_engines uses uppercase mode names; invest maps to INVESTMENT
_SMC_MODE = {"swing": "SWING", "position": "POSITION", "invest": "INVESTMENT"}

ML_CACHE = ROOT / "cache" / "ml_edge_predictions.json"
ML_CAP_DEFAULT = 500  # current scripts/ml_predict.sh cap

# ── Phase contract (Daily-Clock split) ──────────────────────────────────────
# Which warm steps run in each phase. The EOD phase carries the bar-dependent
# heavy lift (structural targets + SMC, which fetch the 4H/EW/daily bars); the
# morning phase is a LIGHT pass — fundamentals refresh + gap-fill only the
# structural caches that EOD missed or that are now stale.
PHASE_STEPS = {
    "eod":     {"targets": True,  "smc": True,  "fundamentals": False, "gap_fill_only": False},
    "morning": {"targets": True,  "smc": False, "fundamentals": True,  "gap_fill_only": True},
    "full":    {"targets": True,  "smc": True,  "fundamentals": True,  "gap_fill_only": False},
}


def _needs_structural_warm(ticker: str, modes: list) -> bool:
    """True if ANY (ticker,mode) structural-target cache is missing or stale.

    Used by the morning (gap_fill_only) phase to skip names EOD already warmed
    — so the 3 AM pass only touches the handful that failed at EOD or are new.
    """
    import target_engine as te
    for mode in modes:
        try:
            path = te._cache_path(ticker, mode)
            if not te._cache_is_fresh(path):
                return True
        except Exception:
            return True
    return False


def _load_emit_coverage():
    """Load scripts/lib/coverage_report.emit_coverage by FILE PATH.

    A plain `from lib.coverage_report import ...` would collide with the
    top-level ROOT/lib package (sharpe_utils etc.), so we import the file
    directly via importlib to guarantee we get scripts/lib/coverage_report.py.
    """
    import importlib.util
    p = Path(__file__).resolve().parent / "lib" / "coverage_report.py"
    spec = importlib.util.spec_from_file_location("_scripts_coverage_report", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.emit_coverage


# ──────────────────────────────────────────────────────────────────────────
# Ranking
# ──────────────────────────────────────────────────────────────────────────
def _universe_codes() -> set:
    """SP500 ∪ R1000 ∪ R2000 ∪ NASDAQ-liquid — the candidate pool to rank."""
    import data_fetcher as df
    tickers: set = set()
    for name, fn, kw in (
        ("SP500", "get_sp500", {}),
        ("R1000", "get_russell1000", {}),
        ("R2000", "get_russell2000", {}),
        ("NASDAQ-liquid", "get_nasdaq_all", {"top_n": 0}),  # full liquidity-gated NASDAQ
    ):
        try:
            got = getattr(df, fn)(**kw) or []
            tickers.update(t.upper() for t in got)
            print(f"  {name}: {len(got)} tickers")
        except Exception as e:
            print(f"  {name} fetch failed: {e}")
    return tickers


def rank_top(top_n: int) -> tuple[list, dict]:
    """Rank the candidate universe by dollar-volume (close×volume) from ONE
    bulk_eod(US) call. Returns (top_codes, dollar_vol_map). No per-ticker fetch."""
    import eodhd_client as eod
    candidates = _universe_codes()
    print(f"  Candidate universe (deduped): {len(candidates)}")

    rows = eod.bulk_eod(exchange="US") or []
    if not isinstance(rows, list) or not rows:
        print("  ! bulk_eod(US) returned no rows — falling back to alpha-sorted candidates (no liquidity rank)")
        return sorted(candidates)[:top_n], {}

    dv: dict = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        code = (r.get("code") or "").strip().upper()
        if code not in candidates:
            continue
        try:
            dv[code] = float(r.get("close") or r.get("adjusted_close") or 0) * float(r.get("volume") or 0)
        except (TypeError, ValueError):
            continue

    ranked = sorted(dv.items(), key=lambda x: x[1], reverse=True)
    top = [c for c, _ in ranked[:top_n]]
    print(f"  Ranked {len(dv)} candidates by dollar-volume (1 bulk_eod call) → top {len(top)}")
    return top, dv


# ──────────────────────────────────────────────────────────────────────────
# Always-include union (track-record + portfolio)
# ──────────────────────────────────────────────────────────────────────────
def _audit_ledger_tickers() -> set:
    p = ROOT / "cache" / "audit_ledger.json"
    out: set = set()
    try:
        d = json.loads(p.read_text())
        for rec in d.get("records", []) or []:
            t = (rec.get("ticker") or "").strip().upper()
            if t:
                out.add(t)
    except Exception as e:
        print(f"  audit_ledger read failed: {e}")
    return out


def _portfolio_tickers() -> set:
    p = ROOT / "data" / "portfolio_state.json"
    out: set = set()
    try:
        d = json.loads(p.read_text())
        for key in ("positions", "closed_trades"):
            for rec in d.get(key, []) or []:
                t = (rec.get("ticker") or "").strip().upper()
                if t:
                    out.add(t)
    except Exception as e:
        print(f"  portfolio_state read failed: {e}")
    return out


# ──────────────────────────────────────────────────────────────────────────
# Budget estimate
# ──────────────────────────────────────────────────────────────────────────
def estimate_budget(n_tickers: int, modes: list, skip_smc: bool,
                    skip_fund: bool, skip_options: bool) -> dict:
    """Rough EODHD-unit + Schwab-call estimate for a FULL (un-cached) run.

    These are upper bounds (worst case: every ticker cold). With 12h-fresh
    caches skipped, real cost is far lower on a same-day re-run.
      - target_engine: each (ticker,mode) cold-computes ~3 EODHD-billed pulls
        (daily OHLCV + fundamentals + sector/RS context). Daily+fundamentals
        are shared across the 3 modes (cached intra-run), so ~ (1 daily + 1
        fundamentals) per ticker + ~1 mode-specific (EW/structural) per mode.
      - fundamentals: 1 EODHD fundamentals unit per ticker (7d cache; usually
        already warmed by the target_engine pass → ~0 net).
      - SMC: shares the same daily bars target_engine fetched (cached intra-run)
        → ~0 net EODHD on same-day; counted as 0.
      - Schwab: 1 get_chains per ticker when options enabled."""
    per_ticker_eodhd = 0
    if modes:
        per_ticker_eodhd += 2          # 1 daily OHLCV + 1 fundamentals (shared across modes)
        per_ticker_eodhd += len(modes) # ~1 mode-specific structural/EW pull per mode
    if not skip_fund:
        per_ticker_eodhd += 0          # same fundamentals call, cached from target pass
    eodhd_units = n_tickers * per_ticker_eodhd
    schwab_calls = 0 if skip_options else n_tickers
    # crude runtime: client paces EODHD ~950/min, but compute dominates ~ 2-3 (t×mode)/s
    secs = (n_tickers * len(modes)) / 2.5 if modes else n_tickers / 2.5
    return {
        "tickers": n_tickers,
        "modes": len(modes),
        "eodhd_units_worst_case": eodhd_units,
        "schwab_calls": schwab_calls,
        "est_runtime_min": round(secs / 60, 1),
    }


# ──────────────────────────────────────────────────────────────────────────
# Warm one ticker (all caches, each guarded)
# ──────────────────────────────────────────────────────────────────────────
def warm_ticker(ticker: str, modes: list, force: bool, skip_smc: bool,
                skip_fund: bool, skip_options: bool, stats: dict, failures: list,
                steps: dict | None = None):
    import target_engine as te

    steps = steps or PHASE_STEPS["full"]
    do_targets = steps.get("targets", True)
    do_smc = steps.get("smc", True) and not skip_smc
    do_fund = steps.get("fundamentals", True) and not skip_fund
    gap_fill_only = steps.get("gap_fill_only", False)

    # Morning gap-fill: skip structural targets for names already warmed at EOD.
    if do_targets and gap_fill_only and not force:
        if not _needs_structural_warm(ticker, modes):
            do_targets = False
            stats["target_gap_skip"] += 1

    # 1) target_engine × modes (Overview/Plan)
    if do_targets:
        for mode in modes:
            try:
                payload = te.analyze_trade_cached(ticker, mode=mode, force_refresh=force)
                cstat = (payload.get("_cache") or {}).get("status", "miss")
                if cstat == "hit":
                    stats["target_cache_hit"] += 1
                else:
                    stats["target_computed"] += 1
            except Exception as e:
                stats["target_err"] += 1
                failures.append({"ticker": ticker, "stage": f"target:{mode}", "error": f"{type(e).__name__}: {e}"})

    # 2) Fundamentals (warm 7-day EODHD cache — same call /api/fundamentals uses)
    if do_fund:
        try:
            import eodhd_client as eod
            f = eod.fundamentals(ticker)
            if f:
                stats["fund_ok"] += 1
            else:
                stats["fund_empty"] += 1
        except Exception as e:
            stats["fund_err"] += 1
            failures.append({"ticker": ticker, "stage": "fundamentals", "error": f"{type(e).__name__}: {e}"})

    # 3) SMC (reuse precompute_smc_risk per-ticker logic — don't duplicate)
    if do_smc:
        try:
            import precompute_smc_risk as smc
            smc_modes = [_SMC_MODE[m] for m in modes if m in _SMC_MODE]
            r = smc.precompute([ticker], ["smc"], smc_modes, dry_run=False, log_every=10_000)
            stats["smc_ok"] += int(r.get("ok", 0))
            stats["smc_nodata"] += int(r.get("no_data", 0))
            stats["smc_err"] += int(r.get("error", 0))
        except Exception as e:
            stats["smc_err"] += 1
            failures.append({"ticker": ticker, "stage": "smc", "error": f"{type(e).__name__}: {e}"})

    # 4) Options (default skipped — Schwab in-session only)
    if not skip_options:
        try:
            import schwab_client as sc
            chain = sc.get_chains(ticker, contract_type="ALL", strike_count=16)
            if chain:
                stats["options_ok"] += 1
            else:
                stats["options_empty"] += 1
        except Exception as e:
            stats["options_err"] += 1
            failures.append({"ticker": ticker, "stage": "options", "error": f"{type(e).__name__}: {e}"})


# ──────────────────────────────────────────────────────────────────────────
# ML cap report
# ──────────────────────────────────────────────────────────────────────────
def ml_cap_report(n_tickers: int) -> dict:
    ml_n = None
    try:
        d = json.loads(ML_CACHE.read_text())
        # ml_edge_predictions.json is per-symbol keyed
        ml_n = len(d) if isinstance(d, dict) else (len(d) if isinstance(d, list) else None)
    except Exception:
        ml_n = None
    cap = ML_CAP_DEFAULT
    gap = max(0, n_tickers - cap)
    rep = {
        "ml_predictions_present": ml_n,
        "ml_cap": cap,
        "warmed_tickers": n_tickers,
        "uncovered_by_ml": gap,
    }
    print("\n── ML coverage ──")
    print(f"  ml_edge_predictions.json symbols present: {ml_n if ml_n is not None else 'unreadable'}")
    print(f"  ML pipeline cap: {cap}  (scripts/ml_predict.sh)")
    if gap > 0:
        print(f"  ⚠ {gap} of {n_tickers} warmed tickers fall OUTSIDE the ML cap "
              f"(ranks {cap+1}–{n_tickers}) → those tabs serve on-demand ML only.")
        print(f"  → RECOMMENDATION: bump the ml-predict cap to {n_tickers} for full "
              f"top-{n_tickers} ML coverage (separate pipeline — not changed by this script).")
    else:
        print(f"  ML cap covers all {n_tickers} warmed tickers. ✓")
    return rep


# ──────────────────────────────────────────────────────────────────────────
# Quota guard
# ──────────────────────────────────────────────────────────────────────────
def quota_state() -> dict:
    try:
        import eodhd_client as eod
        return eod.eodhd_quota_status()
    except Exception:
        # fall back to raw file
        try:
            st = json.loads((ROOT / "cache" / "eodhd_quota.json").read_text())
            return {"count": st.get("count", 0), "soft_limit": 95000, "daily_limit": 100000,
                    "date": st.get("date"), "remaining": max(0, 100000 - st.get("count", 0))}
        except Exception:
            return {"count": 0, "soft_limit": 95000, "daily_limit": 100000, "remaining": 100000}


# ──────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Unified warm-cache batch for top-N ranked tickers")
    ap.add_argument("--top", type=int, default=1000, help="rank cutoff (default 1000)")
    ap.add_argument("--modes", nargs="*", default=ALL_MODES, choices=ALL_MODES)
    ap.add_argument("--limit", type=int, default=None, help="cap warmed-ticker count (testing)")
    ap.add_argument("--dry-run", action="store_true", help="rank + plan + budget only, ZERO fetches beyond ranking")
    ap.add_argument("--force", action="store_true", help="bypass 12h target cache (recompute)")
    ap.add_argument("--skip-options", dest="skip_options", action="store_true", default=True,
                    help="skip Schwab options (default — in-session only)")
    ap.add_argument("--no-skip-options", dest="skip_options", action="store_false",
                    help="also warm Schwab options chains")
    ap.add_argument("--skip-smc", action="store_true", help="skip SMC warm")
    ap.add_argument("--skip-fundamentals", dest="skip_fund", action="store_true", help="skip fundamentals warm")
    ap.add_argument("--phase", choices=["eod", "morning", "full"], default="full",
                    help="eod=heavy targets+SMC (bar-dependent) · morning=light fundamentals+gap-fill · full=everything (default)")
    ap.add_argument("--wait-for-eod", action="store_true",
                    help="(eod phase) poll EODHD until TODAY's EOD bar is posted before warming; "
                         "skip cleanly if it never posts. Never run targets on a stale bar.")
    args = ap.parse_args()

    steps = PHASE_STEPS[args.phase]

    t_start = time.time()
    print(f"\n══ precompute_top1000 · {time.strftime('%Y-%m-%d %H:%M:%S')} ══")
    print(f"  phase={args.phase}  top={args.top}  modes={args.modes}  force={args.force}")
    print(f"  skip_options={args.skip_options}  skip_smc={args.skip_smc}  skip_fundamentals={args.skip_fund}")

    # ── Phase step plan (always printed) ──
    _plan = []
    if steps["targets"]:
        _plan.append("structural-targets×modes" + (" [gap-fill only]" if steps["gap_fill_only"] else ""))
    if steps["smc"] and not args.skip_smc:
        _plan.append("SMC")
    if steps["fundamentals"] and not args.skip_fund:
        _plan.append("fundamentals")
    if not args.skip_options:
        _plan.append("options(Schwab)")
    print(f"  PHASE '{args.phase}' will run: {', '.join(_plan) if _plan else '(nothing)'}")
    if args.phase == "eod":
        print(f"  wait_for_eod={args.wait_for_eod}"
              + ("" if args.wait_for_eod else "  ⚠ not waiting — may compute on a stale bar if EODHD hasn't posted"))

    # ── Rank ──
    print("\n── Ranking (1 bulk_eod call) ──")
    top, dv_map = rank_top(args.top)
    top_set = set(top)

    # ── Track-record + portfolio union ──
    audit = _audit_ledger_tickers()
    port = _portfolio_tickers()
    always = (audit | port)
    added = sorted(always - top_set)
    final = top + added  # top kept in rank order, extras appended
    print(f"\n── Always-include union ──")
    print(f"  audit_ledger tickers: {len(audit)}  ·  portfolio tickers: {len(port)}")
    print(f"  added by union (outside top {args.top}): {len(added)}")
    print(f"  FINAL warm set: {len(final)} tickers")

    if args.limit:
        final = final[: args.limit]
        print(f"  --limit → first {len(final)}: {final}")

    # ── Budget estimate (always printed BEFORE any warming) ──
    budget = estimate_budget(len(final), args.modes, args.skip_smc, args.skip_fund, args.skip_options)
    print(f"\n── Full-run budget estimate (worst case, all cold) ──")
    print(f"  EODHD units (worst case): ~{budget['eodhd_units_worst_case']:,}")
    print(f"  Schwab get_chains calls:  {budget['schwab_calls']:,}")
    print(f"  Est. runtime:             ~{budget['est_runtime_min']} min")
    print(f"  (12h-fresh caches are skipped without --force → real same-day cost is far lower)")

    q = quota_state()
    print(f"\n── EODHD quota now ──")
    print(f"  count={q.get('count'):,}  soft_limit={q.get('soft_limit'):,}  "
          f"daily_limit={q.get('daily_limit'):,}  remaining={q.get('remaining'):,}")

    # ── ML cap report ──
    ml_rep = ml_cap_report(len(final))

    if args.dry_run:
        print("\n[DRY RUN] no fetches performed (ranking bulk_eod only). Exiting.")
        if args.phase == "eod" and args.wait_for_eod:
            print("  [DRY RUN] --wait-for-eod: would poll EODHD (~1 call/15min, ≤3h) "
                  "for today's fresh EOD bar before warming.")
        _write_log({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "mode": "dry_run", "phase": args.phase, "top": args.top, "warm_set": len(final),
            "added_by_union": len(added), "budget": budget, "ml": ml_rep,
            "quota": q,
        })
        return

    # ── Wait-for-fresh-bar gate (eod phase only) — never warm on a stale bar ──
    if args.phase == "eod" and args.wait_for_eod:
        import importlib.util
        _p = ROOT / "scripts" / "lib" / "eod_freshness.py"
        _spec = importlib.util.spec_from_file_location("_eod_freshness", _p)
        _fresh = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_fresh)
        print("\n── Waiting for fresh EOD bar (Daily-Clock Open Risk #3) ──")
        if not _fresh.wait_for_fresh_bar():
            print("⛔ EOD bar never posted within the poll window — skipping EOD precompute "
                  "(morning gap-fill will catch these). Exiting cleanly.")
            _write_log({
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "mode": "skip_stale_bar", "phase": args.phase, "warm_set": len(final),
            })
            return

    # ── Abort if quota already past soft_limit (and not dry-run) ──
    if q.get("count", 0) > q.get("soft_limit", 95000):
        print(f"\n⛔ ABORT: EODHD usage {q.get('count'):,} > soft_limit {q.get('soft_limit'):,}. "
              f"Refusing a real run to protect the daily quota. Re-run after reset (3am PT) or use --dry-run.")
        sys.exit(2)

    # ── Warm ──
    print(f"\n── Warming {len(final)} tickers ──")
    stats = {k: 0 for k in (
        "target_cache_hit", "target_computed", "target_err", "target_gap_skip",
        "fund_ok", "fund_empty", "fund_err",
        "smc_ok", "smc_nodata", "smc_err",
        "options_ok", "options_empty", "options_err",
    )}
    failures: list = []
    log_every = 25
    for i, t in enumerate(final, 1):
        warm_ticker(t, args.modes, args.force, args.skip_smc, args.skip_fund,
                    args.skip_options, stats, failures, steps=steps)
        if i % log_every == 0 or i == len(final):
            elapsed = time.time() - t_start
            rate = i / elapsed if elapsed > 0 else 0
            eta = (len(final) - i) / rate if rate > 0 else 0
            print(f"  [{i:4d}/{len(final)}] {elapsed:6.1f}s · {rate:4.1f} tkr/s · ETA {eta/60:5.1f}m · "
                  f"tgt(hit={stats['target_cache_hit']},new={stats['target_computed']},err={stats['target_err']}) "
                  f"fund(ok={stats['fund_ok']},err={stats['fund_err']}) "
                  f"smc(ok={stats['smc_ok']},nd={stats['smc_nodata']},err={stats['smc_err']})")

    elapsed = round(time.time() - t_start, 1)
    print(f"\n══ Summary ({elapsed}s) ══")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    if failures:
        print(f"  failures: {len(failures)} (first 10):")
        for f in failures[:10]:
            print(f"    {f['ticker']:6s} {f['stage']:14s} {f['error']}")

    _write_log({
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": "run", "top": args.top, "warm_set": len(final),
        "added_by_union": len(added), "modes": args.modes,
        "elapsed_sec": elapsed, "stats": stats,
        "failures_count": len(failures), "failures_first_10": failures[:10],
        "budget": budget, "ml": ml_rep,
        "quota_after": quota_state(),
    })

    # ── Coverage observability (Open Risk #12) — additive, never affects warm logic ──
    target_total = stats["target_cache_hit"] + stats["target_computed"] + stats["target_err"]
    try:
        emit_coverage = _load_emit_coverage()
        by_source = {
            "target": {"total": target_total,
                       "warmed": stats["target_cache_hit"] + stats["target_computed"],
                       "failed": stats["target_err"]},
        }
        if not args.skip_fund:
            by_source["fund"] = {"warmed": stats["fund_ok"] + stats["fund_empty"],
                                 "failed": stats["fund_err"]}
        if not args.skip_smc:
            by_source["smc"] = {"warmed": stats["smc_ok"] + stats["smc_nodata"],
                                "failed": stats["smc_err"]}
        emit_coverage(
            job="precompute_top1000",
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

    # exit non-zero if target-stage failure rate is high
    if target_total and stats["target_err"] > target_total * 0.10:
        print("\n⚠ target-stage failure rate > 10% — exit 1")
        sys.exit(1)


def _write_log(obj: dict):
    log_path = ROOT / "cache" / "logs" / "precompute_top1000.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as f:
        f.write(json.dumps(obj) + "\n")


if __name__ == "__main__":
    main()

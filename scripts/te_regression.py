#!/usr/bin/env python3
"""te_regression.py — structural-target engine regression + diff report.

Project 2 · Milestone 2.4 validation harness.

Runs target_engine across a stable 20-ticker validation set (single-name + ETF
mix), captures per-(ticker, mode) output, and compares against the legacy
ATR-based targets stored in cache/last_bundle.json. Emits:

  - cache/logs/te_regression_<DATE>.json — full per-ticker results
  - cache/logs/te_regression_<DATE>.md   — human-readable diff report
  - cache/logs/te_regression.log         — append-only summary line per run

Run modes:
  python3 scripts/te_regression.py                 # full 20-ticker validation
  python3 scripts/te_regression.py --quick         # 5 tickers, fast smoke
  python3 scripts/te_regression.py --tickers ROST AVGO --modes swing
  python3 scripts/te_regression.py --fail-threshold 3   # exit 1 if >3 errors

Exit codes:
  0 — all engine calls completed (decision in {trade, wait, reject})
  1 — failure count exceeds --fail-threshold (default 5)
  2 — no validation tickers produced any output
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# Stable 20-ticker validation set · mix of mega-cap, mid-cap, ETF, small-cap
VALIDATION_SET = [
    # Mega-cap equities
    "AAPL", "MSFT", "NVDA", "AVGO", "GOOGL",
    # Mid-cap equities (well-traded, plenty of structure)
    "ROST", "AMD", "PLTR", "SOFI", "AMAT",
    # Smaller/mid-cap quality
    "META", "TSLA", "NFLX", "CRM", "ORCL",
    # ETFs (graceful-degrade path)
    "SPY", "QQQ", "XLF", "XLE", "IWM",
]

QUICK_SET = ["ROST", "AVGO", "AAPL", "SPY", "XLF"]


def _load_legacy_targets(ticker: str) -> dict:
    """Pull legacy t1/t2 from cache/last_bundle.json for diff comparison.

    Returns {} on miss · the diff report just leaves the "legacy" column blank.
    """
    path = ROOT / "cache" / "last_bundle.json"
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            bundle = json.load(f)
    except Exception:
        return {}
    # Search BUY, WATCH, all_scored lists
    for key in ("buy_candidates", "watch", "all_scored", "killed"):
        for row in (bundle.get(key) or []):
            if (row.get("ticker") or "").upper() == ticker.upper():
                tp = row.get("trade_plan") or {}
                return {
                    "t1_legacy":   tp.get("target1") or row.get("target1"),
                    "t2_legacy":   tp.get("target2") or row.get("target2"),
                    "stop_legacy": tp.get("stop") or row.get("stop"),
                    "rr_legacy":   tp.get("rr_ratio") or row.get("rr_ratio"),
                    "setup":       row.get("setup_family") or row.get("setup"),
                }
    return {}


def _pct_diff(a, b):
    """Percent difference (b vs a · positive = b higher). None if undefined."""
    try:
        if not a or not b:
            return None
        return round((float(b) - float(a)) / float(a) * 100, 2)
    except Exception:
        return None


def run_ticker(ticker: str, mode: str, equity: float = 25000.0) -> dict:
    """Single (ticker, mode) regression entry · captures latency, decision, diff."""
    import target_engine as te

    t0 = time.time()
    error = None
    try:
        analysis = te.analyze_trade_cached(ticker, mode=mode, equity=equity,
                                           force_refresh=False)
    except Exception as e:
        return {
            "ticker": ticker, "mode": mode, "error": f"{type(e).__name__}: {e}",
            "decision": "error", "elapsed_sec": round(time.time() - t0, 3),
        }

    elapsed = round(time.time() - t0, 3)
    cache = (analysis.get("_cache") or {})
    legacy = _load_legacy_targets(ticker)

    t1 = analysis.get("t1") if isinstance(analysis.get("t1"), dict) else None
    t2 = analysis.get("t2") if isinstance(analysis.get("t2"), dict) else None

    return {
        "ticker": ticker,
        "mode": mode,
        "decision": analysis.get("decision"),
        "warnings": analysis.get("warnings") or [],
        "is_etf": analysis.get("is_etf", False),
        "invest_stub": analysis.get("invest_stub", False),
        "catalyst": analysis.get("catalyst"),
        "price": analysis.get("price_at_analysis"),
        "stop": (analysis.get("stop") or {}).get("price"),
        "t1": (t1 or {}).get("price"),
        "t1_confluence": (t1 or {}).get("confluence"),
        "t1_behavior": (t1 or {}).get("behavior"),
        "t1_r_mult": (t1 or {}).get("r_multiple"),
        "t2": (t2 or {}).get("price"),
        "t2_behavior": (t2 or {}).get("behavior"),
        # Diff vs legacy ATR targets (when bundle has the ticker)
        "legacy_t1": legacy.get("t1_legacy"),
        "legacy_t2": legacy.get("t2_legacy"),
        "t1_diff_pct": _pct_diff(legacy.get("t1_legacy"), (t1 or {}).get("price")),
        "t2_diff_pct": _pct_diff(legacy.get("t2_legacy"), (t2 or {}).get("price")),
        "legacy_setup": legacy.get("setup"),
        # Performance / freshness
        "cache_status": cache.get("status"),
        "elapsed_sec": elapsed,
        "compute_sec": cache.get("computed_in_sec"),
    }


def _build_markdown(results: list, summary: dict) -> str:
    lines = []
    lines.append(f"# Structural Target Engine — Regression Report")
    lines.append(f"")
    lines.append(f"_Generated: {summary['timestamp']}_")
    lines.append(f"")
    lines.append(f"## Summary")
    lines.append(f"")
    lines.append(f"- **Total runs**: {summary['total']}")
    lines.append(f"- **Trade decision**: {summary['decision_trade']}")
    lines.append(f"- **Wait/reject**: {summary['decision_wait']} / {summary['decision_reject']}")
    lines.append(f"- **Errors**: {summary['errors']}")
    lines.append(f"- **Median latency**: {summary['median_elapsed_sec']}s")
    lines.append(f"- **Cache hits**: {summary['cache_hits']} / {summary['total']}")
    if summary.get('top_warnings'):
        lines.append(f"- **Top warnings**: {summary['top_warnings']}")
    lines.append(f"")
    lines.append(f"## Per-ticker results")
    lines.append(f"")
    lines.append(f"| Ticker | Mode | Dec | T1 (struct) | T2 (struct) | T1 Legacy | T1 Δ% | Behavior | Cache | ms |")
    lines.append(f"|---|---|---|---|---|---|---|---|---|---|")
    for r in results:
        dec_emoji = {"trade": "✓", "wait": "⏸", "reject": "✗", "error": "‼"}.get(r['decision'], "?")
        t1_str = f"${r['t1']:.2f}" if r.get('t1') else "—"
        t2_str = f"${r['t2']:.2f}" if r.get('t2') else "—"
        legacy_str = f"${r['legacy_t1']:.2f}" if r.get('legacy_t1') else "—"
        diff_str = f"{r['t1_diff_pct']:+.1f}%" if r.get('t1_diff_pct') is not None else "—"
        beh = r.get('t1_behavior') or "—"
        cache = r.get('cache_status') or "—"
        ms = int(r['elapsed_sec'] * 1000) if r.get('elapsed_sec') else 0
        lines.append(f"| {r['ticker']} | {r['mode']} | {dec_emoji} {r['decision']} | "
                     f"{t1_str} | {t2_str} | {legacy_str} | {diff_str} | {beh} | {cache} | {ms} |")
    lines.append(f"")
    lines.append(f"## Errors / rejects (detail)")
    lines.append(f"")
    err_rows = [r for r in results if r['decision'] in ("reject", "error")]
    if not err_rows:
        lines.append(f"_None — all decisions = trade/wait_")
    else:
        for r in err_rows:
            warns = ", ".join((r.get('warnings') or [])[:3])
            lines.append(f"- **{r['ticker']} · {r['mode']}** · {r['decision']} — {warns or '(no warnings)'}")
    lines.append(f"")
    lines.append(f"## Special-mode flags")
    lines.append(f"")
    etfs = [r for r in results if r.get('is_etf')]
    stubs = [r for r in results if r.get('invest_stub')]
    cats = [r for r in results if r.get('catalyst')]
    lines.append(f"- ETF graceful-degrade fired: **{len(etfs)}** rows")
    if etfs:
        lines.append(f"  - {', '.join(set(r['ticker'] for r in etfs))}")
    lines.append(f"- INVEST stub fired: **{len(stubs)}** rows")
    if stubs:
        lines.append(f"  - {', '.join(r['ticker'] for r in stubs)}")
    lines.append(f"- Earnings-imminent catalyst flag: **{len(cats)}** rows")
    if cats:
        for r in cats:
            d = (r.get('catalyst') or {}).get('days_until')
            lines.append(f"  - {r['ticker']} — earnings in {d}d")
    lines.append(f"")
    return "\n".join(lines)


def run_regression(tickers: list, modes: list, equity: float, fail_threshold: int) -> tuple:
    print(f"\n══ te_regression · {datetime.utcnow().isoformat()}Z ══")
    print(f"Validation set: {len(tickers)} tickers × {len(modes)} modes "
          f"= {len(tickers)*len(modes)} runs")
    print(f"Modes: {modes}")
    print(f"Fail threshold: {fail_threshold} errors\n")

    results = []
    t_start = time.time()
    for i, tk in enumerate(tickers, 1):
        for mode in modes:
            r = run_ticker(tk, mode, equity=equity)
            results.append(r)
            dec = r['decision']
            symbol = {"trade": "✓", "wait": "⏸", "reject": "✗", "error": "‼"}.get(dec, "?")
            extras = []
            if r.get('is_etf'):       extras.append("ETF")
            if r.get('invest_stub'):  extras.append("STUB")
            if r.get('catalyst'):     extras.append(f"EARN-{r['catalyst'].get('days_until')}d")
            extra_str = f" [{', '.join(extras)}]" if extras else ""
            ms = int(r['elapsed_sec'] * 1000)
            t1 = f"${r['t1']:.2f}" if r.get('t1') else "—"
            diff = f" (Δ{r['t1_diff_pct']:+.1f}%)" if r.get('t1_diff_pct') is not None else ""
            print(f"  [{i:2d}/{len(tickers)}] {tk:6s} {mode:9s} {symbol} {dec:7s} "
                  f"T1={t1}{diff:12s} {ms:5d}ms{extra_str}")

    elapsed_total = round(time.time() - t_start, 1)

    # Compute summary stats
    summary = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "total": len(results),
        "decision_trade":  sum(1 for r in results if r['decision'] == "trade"),
        "decision_wait":   sum(1 for r in results if r['decision'] == "wait"),
        "decision_reject": sum(1 for r in results if r['decision'] == "reject"),
        "errors":          sum(1 for r in results if r['decision'] == "error"),
        "cache_hits":      sum(1 for r in results if r.get('cache_status') == "hit"),
        "median_elapsed_sec": round(statistics.median([r['elapsed_sec'] for r in results]), 3) if results else 0,
        "total_elapsed_sec": elapsed_total,
        "etf_flags":       sum(1 for r in results if r.get('is_etf')),
        "invest_stubs":    sum(1 for r in results if r.get('invest_stub')),
        "earnings_flags":  sum(1 for r in results if r.get('catalyst')),
    }

    # Aggregate top warnings
    from collections import Counter
    warn_counter = Counter()
    for r in results:
        for w in (r.get('warnings') or []):
            # Keep first ~40 chars as bucket key
            key = w.split(" — ")[0] if " — " in w else w[:40]
            warn_counter[key] += 1
    summary['top_warnings'] = ", ".join([f"{k}({v})" for k, v in warn_counter.most_common(5)])

    return results, summary


def main():
    ap = argparse.ArgumentParser(description="target_engine regression suite (M2.4)")
    ap.add_argument("--tickers", nargs="*", help="explicit ticker list")
    ap.add_argument("--modes", nargs="*", default=["swing", "position"],
                    choices=["swing", "position", "invest"])
    ap.add_argument("--equity", type=float, default=25000.0)
    ap.add_argument("--quick", action="store_true",
                    help="run only 5-ticker smoke set")
    ap.add_argument("--fail-threshold", type=int, default=5,
                    help="exit 1 if errors exceed this count (default 5)")
    args = ap.parse_args()

    if args.tickers:
        tickers = [t.upper() for t in args.tickers]
    elif args.quick:
        tickers = QUICK_SET
    else:
        tickers = VALIDATION_SET

    results, summary = run_regression(tickers, args.modes, args.equity,
                                      args.fail_threshold)

    # Write outputs
    log_dir = ROOT / "cache" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    date_stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    json_path = log_dir / f"te_regression_{date_stamp}.json"
    with open(json_path, "w") as f:
        json.dump({"summary": summary, "results": results}, f, indent=2, default=str)

    md_path = log_dir / f"te_regression_{date_stamp}.md"
    with open(md_path, "w") as f:
        f.write(_build_markdown(results, summary))

    # Append-only run log (one line per execution)
    summary_log_path = log_dir / "te_regression.log"
    with open(summary_log_path, "a") as f:
        f.write(json.dumps({**summary, "json_path": str(json_path),
                            "md_path": str(md_path)}) + "\n")

    # Console summary
    print(f"\n══ Summary ══")
    print(f"  Trade : {summary['decision_trade']}")
    print(f"  Wait  : {summary['decision_wait']}")
    print(f"  Reject: {summary['decision_reject']}")
    print(f"  Error : {summary['errors']}")
    print(f"  Cache hits: {summary['cache_hits']}/{summary['total']}")
    print(f"  Median latency: {summary['median_elapsed_sec']}s")
    print(f"  Total elapsed: {summary['total_elapsed_sec']}s")
    print(f"  Top warnings: {summary['top_warnings'] or '<none>'}")
    print()
    print(f"  JSON: {json_path}")
    print(f"  MD:   {md_path}")
    print()

    # Exit code
    if summary['total'] == 0:
        print("⚠ no results produced", file=sys.stderr)
        sys.exit(2)
    if summary['errors'] > args.fail_threshold:
        print(f"⚠ errors ({summary['errors']}) exceed fail threshold ({args.fail_threshold})",
              file=sys.stderr)
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()

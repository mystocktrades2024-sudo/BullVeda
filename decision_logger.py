"""
Decision Logger — persists every scan verdict (BUY/WATCH/AVOID/SHORT) with
its full gate chain so scan behavior can be tuned from data.

Storage: JSONL (one entry per line) at data/decision_log.jsonl.
Rotates when file exceeds 50MB — active file is moved to
data/decision_log.YYYYMM.jsonl and a fresh file is started.

Part of HARDENING_CHECKLIST items 3.1–3.3, 3.5.
"""

from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

log = logging.getLogger("decision_logger")

BASE_DIR = Path(__file__).parent
DECISION_LOG_PATH = BASE_DIR / "data" / "decision_log.jsonl"
MAX_LOG_BYTES = 50 * 1024 * 1024  # 50MB rotation threshold


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ensure_parent() -> None:
    DECISION_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def _rotate_if_needed() -> None:
    """If the active log exceeds MAX_LOG_BYTES, rename it with YYYYMM suffix."""
    try:
        if DECISION_LOG_PATH.exists() and DECISION_LOG_PATH.stat().st_size >= MAX_LOG_BYTES:
            stamp = datetime.now().strftime("%Y%m")
            target = BASE_DIR / "data" / f"decision_log.{stamp}.jsonl"
            # If target already exists (monthly rotation already occurred), append-suffix.
            if target.exists():
                i = 1
                while True:
                    cand = BASE_DIR / "data" / f"decision_log.{stamp}.{i}.jsonl"
                    if not cand.exists():
                        target = cand
                        break
                    i += 1
            DECISION_LOG_PATH.rename(target)
            log.info("Rotated decision_log → %s", target.name)
    except Exception as exc:
        log.warning("decision_log rotation failed: %s", exc)


def _normalize_verdict(decision: Dict[str, Any]) -> str:
    """Pull verdict from a decision dict, tolerating a few schema variations."""
    v = (
        decision.get("verdict")
        or decision.get("decision")
        or decision.get("action")
        or decision.get("status")
        or ""
    )
    v = str(v).upper().strip()
    if v in {"BUY", "WATCH", "AVOID", "SHORT"}:
        return v
    # Common aliases
    if v in {"LONG"}:
        return "BUY"
    if v in {"SKIP", "REJECT", "REJECTED"}:
        return "AVOID"
    return v or "UNKNOWN"


def _build_entry(
    ticker: str,
    scan_date: str,
    decision: Dict[str, Any],
    context: Dict[str, Any],
) -> Dict[str, Any]:
    """Assemble the persisted entry dict."""
    ctx = context or {}
    dec = decision or {}

    score_breakdown = (
        dec.get("score_breakdown")
        or dec.get("scoring_breakdown")
        or ctx.get("score_breakdown")
        or {}
    )

    entry = {
        "date": scan_date,
        "ticker": str(ticker or "").upper(),
        "verdict": _normalize_verdict(dec),
        "reason": dec.get("reason") or dec.get("why") or "",
        "score": dec.get("score"),
        "rs_rank": dec.get("rs_rank") or ctx.get("rs_rank"),
        "setup_type": (
            dec.get("setup_type")
            or dec.get("strategy")
            or ctx.get("setup_type")
        ),
        "direction": (dec.get("direction") or ctx.get("direction") or "long"),
        "regime4": ctx.get("regime4") or dec.get("regime4"),
        "profile": ctx.get("profile") or dec.get("profile"),
        "gates_hit": list(dec.get("gates_hit") or ctx.get("gates_hit") or []),
        "score_breakdown": score_breakdown,
        "has_catalyst": bool(
            dec.get("has_catalyst")
            if dec.get("has_catalyst") is not None
            else ctx.get("has_catalyst", False)
        ),
        "weekly_bull": bool(
            dec.get("weekly_bull")
            if dec.get("weekly_bull") is not None
            else ctx.get("weekly_bull", False)
        ),
        "rr_ratio": dec.get("rr_ratio") or dec.get("rr") or ctx.get("rr"),
        "entry_price": dec.get("entry_price") or dec.get("price") or ctx.get("entry_price"),
    }
    return entry


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def log_decision(
    ticker: str,
    scan_date: str,
    decision: Dict[str, Any],
    context: Dict[str, Any],
) -> None:
    """Append a single decision entry to data/decision_log.jsonl."""
    if not ticker:
        return
    try:
        _ensure_parent()
        _rotate_if_needed()
        entry = _build_entry(ticker, scan_date, decision, context)
        with DECISION_LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, default=str) + "\n")
    except Exception as exc:
        log.warning("log_decision failed for %s: %s", ticker, exc)


def log_decisions_batch(
    results: List[Dict[str, Any]],
    scan_date: str,
    profile: Optional[str] = None,
) -> int:
    """Batch-append many decisions in one call. Returns count written."""
    if not results:
        return 0
    _ensure_parent()
    _rotate_if_needed()

    written = 0
    try:
        with DECISION_LOG_PATH.open("a", encoding="utf-8") as fh:
            for r in results:
                if not isinstance(r, dict):
                    continue
                ticker = r.get("ticker") or r.get("symbol") or ""
                if not ticker:
                    continue

                # The canonical shape is r["decision"] = {verdict, reason, ...}.
                # Everything else (plan, indicators, catalyst_tags) lives on r.
                decision = r.get("decision") if isinstance(r.get("decision"), dict) else {}
                plan = r.get("trade_plan") if isinstance(r.get("trade_plan"), dict) else {}
                if not plan:
                    plan = r.get("plan") if isinstance(r.get("plan"), dict) else {}
                indicators = (
                    r.get("technicals", {}).get("indicators", {})
                    if isinstance(r.get("technicals"), dict) else {}
                )
                if not indicators and isinstance(r.get("indicators"), dict):
                    indicators = r.get("indicators")

                ctx = dict(r.get("context") or {})
                if profile and not ctx.get("profile"):
                    ctx["profile"] = profile
                # Pull fields from canonical locations, letting explicit context win.
                ctx.setdefault("regime4", r.get("regime4"))
                ctx.setdefault("direction", r.get("direction"))
                ctx.setdefault("rs_rank", r.get("rs_rank") or indicators.get("rs_rank"))
                ctx.setdefault(
                    "setup_type",
                    plan.get("setup_type") or r.get("setup_type"),
                )
                ctx.setdefault(
                    "rr",
                    r.get("rr") or plan.get("rr_ratio") or plan.get("rr"),
                )
                ctx.setdefault(
                    "entry_price",
                    r.get("price") or plan.get("entry_low") or plan.get("price"),
                )
                ctx.setdefault(
                    "has_catalyst",
                    bool(r.get("catalyst_tags") or r.get("catalysts")),
                )
                ctx.setdefault(
                    "weekly_bull",
                    bool(indicators.get("weekly_bull")),
                )
                ctx.setdefault("score_breakdown", r.get("score_breakdown") or {})
                # gates_hit is a Wave 2B addition; pass through if present.
                if "gates_hit" in r and "gates_hit" not in ctx:
                    ctx["gates_hit"] = r.get("gates_hit") or []

                # 2026-05-18 · Fix C: surface "insufficient_history" + similar
                # gate reasons from score_breakdown when score=0. Previously
                # decision_log lost this info, leaving 14-25 tickers/day
                # showing score=0 with no explanation.
                _reason = decision.get("reason") or decision.get("why") or ""
                _score_val = r.get("score") or 0
                _breakdown = ctx.get("score_breakdown") or {}
                if _score_val == 0 and isinstance(_breakdown, dict):
                    _gate = _breakdown.get("gate")
                    if _gate:
                        # e.g. "insufficient_history", "missing_fundamentals"
                        _reason = f"score=0 ({_gate}) — {_reason}" if _reason else f"score=0 ({_gate})"
                    elif _breakdown:
                        # No explicit gate — annotate which pillar(s) returned 0
                        _zero_pillars = [k for k in ("tech","catalyst","rs","smart_money","quality_gate","entry_rr")
                                         if (_breakdown.get(k) or 0) == 0]
                        if _zero_pillars:
                            _reason = f"score=0 (zero pillars: {','.join(_zero_pillars)}) — {_reason}" if _reason else f"score=0 (zero pillars: {','.join(_zero_pillars)})"

                # Build a flat decision-shaped dict for _build_entry.
                dec_flat = {
                    "verdict": decision.get("verdict"),
                    "reason": _reason,
                    "score": r.get("score"),
                    "direction": r.get("direction") or decision.get("direction"),
                    "setup_type": ctx.get("setup_type"),
                    "rr_ratio": ctx.get("rr"),
                    "entry_price": ctx.get("entry_price"),
                    "rs_rank": ctx.get("rs_rank"),
                    "has_catalyst": ctx.get("has_catalyst"),
                    "weekly_bull": ctx.get("weekly_bull"),
                    "gates_hit": ctx.get("gates_hit") or [],
                    "score_breakdown": ctx.get("score_breakdown") or {},
                }
                entry = _build_entry(ticker, scan_date, dec_flat, ctx)
                fh.write(json.dumps(entry, default=str) + "\n")
                written += 1
    except Exception as exc:
        log.warning("log_decisions_batch failed: %s", exc)
    if written:
        log.info("decision_logger: wrote %d entries for %s", written, scan_date)
    return written


def _iter_log_lines(path: Path) -> Iterable[Dict[str, Any]]:
    """Yield decoded JSONL records from a file, skipping malformed lines."""
    if not path.exists():
        return
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except IOError as exc:
        log.warning("Failed to read %s: %s", path, exc)


def load_recent_decisions(days: int = 7) -> List[Dict[str, Any]]:
    """Return decision entries from the last `days` calendar days (inclusive).

    Reads the active decision_log.jsonl (rotated archives are not scanned —
    callers who need longer history should read them directly).
    """
    if days <= 0:
        return []
    cutoff = date.today() - timedelta(days=days - 1)
    out: List[Dict[str, Any]] = []
    for rec in _iter_log_lines(DECISION_LOG_PATH):
        d = rec.get("date")
        try:
            d_parsed = datetime.strptime(str(d)[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
        if d_parsed >= cutoff:
            out.append(rec)
    return out


def compute_gate_kill_counts(days: int = 7) -> Dict[str, int]:
    """Count, over the last `days` days, how many BUY-candidate tickers each
    gate knocked out.

    A gate is considered to have "killed a BUY" when the entry's verdict is
    AVOID (or WATCH, where a gate demoted an otherwise-strong candidate) and
    the gate name appears in `gates_hit`.

    Returns {gate_name: count} sorted descending.
    """
    counts: Dict[str, int] = defaultdict(int)
    for rec in load_recent_decisions(days=days):
        verdict = str(rec.get("verdict") or "").upper()
        if verdict not in ("AVOID", "WATCH"):
            continue
        for g in rec.get("gates_hit") or []:
            if g:
                counts[str(g)] += 1
    return dict(sorted(counts.items(), key=lambda kv: kv[1], reverse=True))


def compute_watch_to_buy_conversions(days: int = 30) -> Dict[str, Any]:
    """For each ticker that was WATCH and later BUY within the window, track
    conversion time and per-setup conversion rate.

    Returns:
        {
          "window_days": int,
          "total_watch": int,
          "total_converted": int,
          "overall_rate_pct": float,
          "avg_days_to_convert": float | None,
          "by_setup": {
              setup: {"watch_count": N, "converted": M,
                      "rate_pct": X, "avg_days_to_convert": Y | None}
          },
          "conversions": [ {ticker, setup, watch_date, buy_date, days} ]
        }
    """
    recs = load_recent_decisions(days=days)
    # Group by ticker → list[(date, verdict, setup)]
    by_ticker: Dict[str, List[tuple]] = defaultdict(list)
    for r in recs:
        try:
            d = datetime.strptime(str(r.get("date"))[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
        verdict = str(r.get("verdict") or "").upper()
        setup = r.get("setup_type") or "unknown"
        by_ticker[r.get("ticker", "")].append((d, verdict, setup))

    conversions: List[Dict[str, Any]] = []
    watch_by_setup: Dict[str, int] = defaultdict(int)
    convert_by_setup: Dict[str, List[int]] = defaultdict(list)
    total_watch = 0

    for ticker, events in by_ticker.items():
        if not ticker:
            continue
        events.sort(key=lambda e: e[0])
        # Walk chronologically; for each WATCH, find next BUY.
        i = 0
        while i < len(events):
            d_i, v_i, s_i = events[i]
            if v_i == "WATCH":
                total_watch += 1
                watch_by_setup[s_i] += 1
                # Find next BUY after this date
                for j in range(i + 1, len(events)):
                    d_j, v_j, s_j = events[j]
                    if v_j == "BUY":
                        gap = (d_j - d_i).days
                        conversions.append({
                            "ticker": ticker,
                            "setup": s_i,
                            "watch_date": d_i.isoformat(),
                            "buy_date": d_j.isoformat(),
                            "days": gap,
                        })
                        convert_by_setup[s_i].append(gap)
                        break
            i += 1

    by_setup: Dict[str, Dict[str, Any]] = {}
    for setup, wc in watch_by_setup.items():
        converted_list = convert_by_setup.get(setup, [])
        converted = len(converted_list)
        avg_days = (
            round(sum(converted_list) / converted, 2) if converted else None
        )
        by_setup[setup] = {
            "watch_count": wc,
            "converted_count": converted,
            "rate_pct": round(converted / wc * 100, 2) if wc else 0.0,
            "avg_days_to_convert": avg_days,
        }

    total_converted = len(conversions)
    avg_overall_days = (
        round(sum(c["days"] for c in conversions) / total_converted, 2)
        if total_converted else None
    )

    return {
        "window_days": days,
        "total_watch": total_watch,
        "total_converted": total_converted,
        "overall_rate_pct": (
            round(total_converted / total_watch * 100, 2) if total_watch else 0.0
        ),
        "avg_days_to_convert": avg_overall_days,
        "by_setup": by_setup,
        "conversions": conversions,
    }

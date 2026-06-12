"""edge_labels.py — honest, regime-conditional edge tier from the live track record.

Phase 2 of the 2026-06-11 signal-screener audit
(docs/signal_screener_audit_2026_06_11.html).

The audit showed the system's headline ranking signals (composite score, catalyst
tier, conviction tier) are anti-correlated with realized outcomes — the more
strongly the system flags a trade, the LESS reliably it wins. The fix is NOT to
kill signals (that hides them); it is to label them honestly and let the ranking
reflect what actually worked.

This module reads the realized track record (cache/picks_history.json) and, for
each (setup_family x coarse-regime) cell, computes realized PF / win rate / Wilson
lower bound and assigns an honest tier:

    PROVEN     n>=30, PF>=1.20, Wilson LB>=40%   (real, risk-adjusted edge)
    DEVELOPING n>=30, 1.0<=PF<1.20               (positive but below floor)
    WEAK       PF<1.0  (n>=10)                    (loses money in this regime)
    UNPROVEN   n<30                               (not enough evidence yet)

It is INFORMATIONAL ONLY — it never gates a verdict or zeroes a score. Consumers
attach `edge_tier` to each signal row for display (badge + sort key); the BUY
stays visible and clickable regardless of tier.

Survival rails (regime gate / macro blackout / circuit breaker) are unrelated and
unaffected.
"""

from __future__ import annotations

import json
import math
import os
from typing import Optional

# --- coarse-regime mapping (mirrors data_fetcher.py:3187 + analysis.py) ----------
# risk_on_trending -> bull ; risk_on_choppy -> neutral ; risk_off/panic -> bear
_REGIME_COARSE = {
    "risk_on_trending": "bull",
    "bull": "bull",
    "risk_on_choppy": "neutral",
    "neutral": "neutral",
    "choppy": "neutral",
    "risk_off_trending": "bear",
    "risk_off": "bear",
    "panic": "bear",
    "bear": "bear",
}

_DEFAULT_TIERS = {
    "proven": {"min_n": 30, "min_pf": 1.20, "min_wilson_lb": 40.0},
    "weak": {"max_pf": 1.00},
    "unproven_max_n": 30,
}

_TIER_META = {
    "PROVEN":     {"rank": 0, "tone": "good", "icon": "✓"},
    "DEVELOPING": {"rank": 1, "tone": "neutral", "icon": "•"},
    "UNPROVEN":   {"rank": 2, "tone": "muted", "icon": "?"},
    "WEAK":       {"rank": 3, "tone": "warn", "icon": "⚠"},
}

# module-level cache: {table, mtime, path}
_CACHE: dict = {}


def coarse_regime(regime: Optional[str]) -> str:
    return _REGIME_COARSE.get(str(regime or "").strip().lower(), "neutral")


def _wilson_lb(wins: int, n: int, z: float = 1.96) -> float:
    if n <= 0:
        return 0.0
    p = wins / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return 100.0 * (centre - margin) / denom


def _pf(returns: list[float]) -> float:
    w = sum(r for r in returns if r > 0)
    l = -sum(r for r in returns if r < 0)
    if l <= 0:
        return 9.99 if w > 0 else 1.0
    return w / l


def _classify(n: int, pf: float, wlb: float, tiers: dict) -> str:
    pr = tiers.get("proven", _DEFAULT_TIERS["proven"])
    weak = tiers.get("weak", _DEFAULT_TIERS["weak"])
    unproven_max_n = tiers.get("unproven_max_n", _DEFAULT_TIERS["unproven_max_n"])
    # WEAK first — a losing cell is weak even at large n (that IS the finding).
    if n >= 10 and pf < float(weak.get("max_pf", 1.0)):
        return "WEAK"
    if n < int(unproven_max_n):
        return "UNPROVEN"
    if (pf >= float(pr.get("min_pf", 1.20))
            and wlb >= float(pr.get("min_wilson_lb", 40.0))
            and n >= int(pr.get("min_n", 30))):
        return "PROVEN"
    return "DEVELOPING"


def build_edge_table(picks_history_path: str, tiers: Optional[dict] = None) -> dict:
    """Return {(family, coarse_regime): {...stats, tier...}} plus ('*FAMILY*', family)
    aggregate cells (across all regimes) used as a fallback when a regime cell is sparse."""
    tiers = tiers or _DEFAULT_TIERS
    try:
        with open(picks_history_path) as fh:
            doc = json.load(fh)
    except Exception:
        return {}
    trades = doc.get("trades") if isinstance(doc, dict) else doc
    if not isinstance(trades, list):
        return {}

    # bucket returns by cell
    by_cell: dict = {}
    by_family: dict = {}
    for r in trades:
        pc = r.get("pct_chg")
        if not isinstance(pc, (int, float)) or math.isnan(pc):
            continue
        fam = (r.get("setup_family") or "").strip()
        if not fam:
            continue
        reg = coarse_regime(r.get("regime4") or r.get("regime"))
        by_cell.setdefault((fam, reg), []).append(float(pc))
        by_family.setdefault(fam, []).append(float(pc))

    def _stats(returns: list[float]) -> dict:
        n = len(returns)
        wins = sum(1 for x in returns if x > 0)
        pf = _pf(returns)
        wlb = _wilson_lb(wins, n)
        wr = 100.0 * wins / n if n else 0.0
        avg = sum(returns) / n if n else 0.0
        return {"n": n, "wr": round(wr, 1), "pf": round(pf, 2),
                "wilson_lb": round(wlb, 1), "avg_ret": round(avg, 2),
                "tier": _classify(n, pf, wlb, tiers)}

    table: dict = {}
    for cell, rets in by_cell.items():
        table[cell] = _stats(rets)
    for fam, rets in by_family.items():
        table[("*FAMILY*", fam)] = _stats(rets)
    return table


def _load_table(picks_history_path: str, tiers: Optional[dict]) -> dict:
    """Cached table load — rebuilds only when picks_history mtime changes."""
    try:
        mtime = os.path.getmtime(picks_history_path)
    except OSError:
        mtime = 0
    if (_CACHE.get("path") == picks_history_path and _CACHE.get("mtime") == mtime
            and _CACHE.get("tiers_id") == id(tiers)):
        return _CACHE.get("table") or {}
    table = build_edge_table(picks_history_path, tiers)
    _CACHE.update({"path": picks_history_path, "mtime": mtime,
                   "tiers_id": id(tiers), "table": table})
    return table


def lookup_edge(setup_family: Optional[str], regime: Optional[str],
                picks_history_path: str = "cache/picks_history.json",
                tiers: Optional[dict] = None) -> Optional[dict]:
    """Return an honest edge-tier dict for (family, regime), or None if no data.

    Output shape:
        {tier, label, icon, tone, sort_rank, pf, n, wr, wilson_lb, avg_ret,
         regime_cell, basis}
    `basis` = "regime" when the (family x regime) cell had n>=10, else "family"
    (aggregate fallback). Display this so the user knows the granularity.
    """
    fam = (setup_family or "").strip()
    if not fam:
        return None
    table = _load_table(picks_history_path, tiers)
    if not table:
        return None
    reg = coarse_regime(regime)
    cell = table.get((fam, reg))
    basis = "regime"
    if not cell or cell.get("n", 0) < 10:
        cell = table.get(("*FAMILY*", fam))
        basis = "family"
    if not cell:
        return None
    tier = cell["tier"]
    meta = _TIER_META.get(tier, _TIER_META["UNPROVEN"])
    reg_word = {"bull": "trending", "neutral": "choppy", "bear": "risk-off"}.get(reg, reg)
    if basis == "regime":
        label = f"{tier.title()} edge in {reg_word}: PF {cell['pf']} (n={cell['n']})"
    else:
        label = f"{tier.title()} edge (all-regime): PF {cell['pf']} (n={cell['n']})"
    return {
        "tier": tier,
        "label": label,
        "icon": meta["icon"],
        "tone": meta["tone"],
        "sort_rank": meta["rank"],
        "pf": cell["pf"],
        "n": cell["n"],
        "wr": cell["wr"],
        "wilson_lb": cell["wilson_lb"],
        "avg_ret": cell["avg_ret"],
        "regime_cell": reg,
        "basis": basis,
    }


if __name__ == "__main__":
    # quick self-test against the live file
    import pprint
    t = build_edge_table("cache/picks_history.json")
    print(f"cells: {len(t)}")
    for reg in ("bull", "neutral", "bear"):
        for fam in ("Trend Continuation", "Breakout Expansion", "Impulse Catalyst"):
            e = lookup_edge(fam, reg)
            if e:
                print(f"{fam:22} x {reg:8} -> {e['tier']:10} {e['label']}")

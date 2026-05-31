#!/usr/bin/env python3
"""build_leaders.py — emit infra/prototype/data_leaders.json for the Track Record surface.

Root-cause fix (2026-05-31): the dashboard fetches /v2/data_leaders.json for the
Track Record ("leaders") tab, but build_data.py never produced it → the tab was
empty / "stale month axis". This module is the producer.

Output contract = the prototype's `window.SigLedger` shape (see the design handoff
`src/signalledger-data.jsx`). The JS layer reads this JSON and runs the SAME pure
reducers (aggregate / leaderboard / ledger / decay / calibration / regime / equity)
with `ret(sig,hz)` reading the REAL forward grid instead of the mock decay function.

THE DATE FIX (HANDOVER_track_record.md §0):
    Never bucket on a bare field name again. ONE coalescer resolves the signal date
    across both stores' differing schemas, and `age` is derived from it:
        pick_date || entry_date || date || signal_date || asof
    Maturity is taken from the REAL grid (a horizon return that exists = matured),
    which is more honest than comparing trading-day horizons to a calendar age.

Sources (8 engines, per handover). audit_ledger has no `_source` tag — every row
is `_source=None` — so the engine is DERIVED from `setup`. Earnings / Options / AI
come from their own logs (PEAD prediction log / options_flow_outcomes / ml_edge
close-loop) and are layered in where available; the rest map from audit_ledger.

Run:  python3 infra/prototype/build_leaders.py
"""
from __future__ import annotations

import json
import datetime as _dt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # SwingTrade/
AUDIT_LEDGER = ROOT / "cache" / "audit_ledger.json"
SIGNAL_LOG   = ROOT / "data"  / "signal_log.json"
OUT          = Path(__file__).resolve().parent / "data_leaders.json"

# ── horizons: the REAL grid audit_ledger carries (D1-D7 / W1-W8 / M1-M12) ──────
def _build_horizons() -> list[dict]:
    hz: list[dict] = []
    for d in range(1, 8):   hz.append({"id": f"D{d}", "label": f"D{d}", "days": d,      "group": "D"})
    for w in range(1, 9):   hz.append({"id": f"W{w}", "label": f"W{w}", "days": w * 5,  "group": "W"})
    for m in range(1, 13):  hz.append({"id": f"M{m}", "label": f"M{m}", "days": m * 21, "group": "M"})
    for i, h in enumerate(hz):
        h["idx"] = i
    return hz

HORIZONS = _build_horizons()
# audit_ledger stores horizon returns under lowercase keys: d1..d7, w1..w8, m1..m12
_GRID_KEYS = [h["id"].lower() for h in HORIZONS]

# ── 8 sources (engines) ───────────────────────────────────────────────────────
SOURCES = [
    {"id": "screeners", "label": "Screeners"},
    {"id": "earnings",  "label": "Earnings"},
    {"id": "options",   "label": "Options"},
    {"id": "ai",        "label": "AI Predictions"},
    {"id": "insiders",  "label": "Insiders"},
    {"id": "momentum",  "label": "Momentum"},
    {"id": "smc",       "label": "SMC / Patterns"},
    {"id": "verdict",   "label": "Overall Verdict"},
]

# setup → engine. audit_ledger setups seen: pullback, momentum, bounce, breakout,
# ema_pullback, vcp, insider_cluster, EMA21 Pullback, breakdown, mean_reversion, …
def _setup_to_source(setup: str, family: str) -> str:
    s = (setup or "").strip().lower()
    f = (family or "").strip().lower()
    if "insider" in s:                                   return "insiders"
    if "momentum" in s:                                  return "momentum"
    if any(k in s for k in ("vcp", "breakout", "52w", "cup", "squeeze", "spring")):
        return "smc"
    if any(k in s for k in ("pead", "gap", "earnings", "esp")):
        return "earnings"
    if any(k in s for k in ("uoa", "option")):           return "options"
    # family fallback
    if "breakout" in f:                                  return "smc"
    if "impulse" in f or "catalyst" in f:                return "earnings"
    if "special" in f:                                   return "insiders"
    # pullback / ema_pullback / bounce / mean_reversion / breakdown / rebreak / …
    return "screeners"


def _regime_bucket(regime4: str | None) -> str | None:
    """Collapse the 4-regime code to the prototype's bull/chop/bear axis.
    risk_on_trending → bull · risk_on_choppy → chop · risk_off_* / panic → bear."""
    r = (regime4 or "").strip().lower()
    if not r:
        return None
    if "trending" in r and "off" not in r:
        return "bull"
    if "choppy" in r or "chop" in r:
        return "chop"
    if "off" in r or "panic" in r or "bear" in r:
        return "bear"
    return None


def _coalesce_date(r: dict) -> str | None:
    """ONE canonical signal-date resolver — the durable fix for the empty-bucket bug."""
    for k in ("pick_date", "entry_date", "date", "signal_date", "asof"):
        v = r.get(k)
        if v:
            return str(v)[:10]
    return None


def _age_days(date_str: str, today: _dt.date) -> int | None:
    try:
        d = _dt.date.fromisoformat(date_str)
        return max(0, (today - d).days)
    except Exception:
        return None


def _grid(r: dict) -> dict:
    """Real forward-return grid keyed by HORIZON id (uppercase); None = not matured."""
    out: dict = {}
    for h in HORIZONS:
        v = r.get(h["id"].lower())
        out[h["id"]] = float(v) if isinstance(v, (int, float)) else None
    return out


def build(today: _dt.date | None = None) -> dict:
    today = today or _dt.date.today()
    signals: list[dict] = []
    month_hist: dict[str, int] = {}
    src_hist: dict[str, int] = {}
    sid = 0

    if AUDIT_LEDGER.exists():
        recs = (json.loads(AUDIT_LEDGER.read_text()) or {}).get("records") or []
        for r in recs:
            ds = _coalesce_date(r)
            if not ds:
                continue
            age = _age_days(ds, today)
            if age is None:
                continue
            src = _setup_to_source(r.get("setup"), r.get("setup_family"))
            grid = _grid(r)
            sig = {
                "id":        f"s{sid}",
                "source":    src,
                "sym":       r.get("ticker"),
                "dir":       (r.get("direction") or "long").lower(),
                "regime":    _regime_bucket(r.get("regime4")),  # bull/chop/bear from regime4 (null where untagged)
                "age":       age,
                "date":      ds,
                "refPrice":  r.get("price_at_pick"),
                "predProb":  None,
                "verdict":   r.get("verdict"),
                "setup":     r.get("setup"),
                "ret":       grid,                 # REAL grid; null entry = maturing
            }
            signals.append(sig)
            sid += 1
            month_hist[ds[:7]] = month_hist.get(ds[:7], 0) + 1
            src_hist[src] = src_hist.get(src, 0) + 1

    payload = {
        "generated_at":   _dt.datetime.now().isoformat(timespec="seconds"),
        "schema":         "leaders.v1",
        "horizons":       HORIZONS,
        "sources":        SOURCES,
        "signals":        signals,
        "totalCalls":     len(signals),
        "edge_available": False,            # raw-return only in v1; SPY-edge is increment 1b
        "_diag": {
            "month_hist":  dict(sorted(month_hist.items())),
            "source_hist": dict(sorted(src_hist.items(), key=lambda kv: -kv[1])),
        },
    }
    return payload


def main() -> None:
    payload = build()
    OUT.write_text(json.dumps(payload, separators=(",", ":")))
    d = payload["_diag"]
    print(f"[build_leaders] wrote {OUT.name}: {payload['totalCalls']} signals")
    print(f"[build_leaders] months : {d['month_hist']}")
    print(f"[build_leaders] sources: {d['source_hist']}")
    # acceptance guard: no empty-bucket regression
    if "" in d["month_hist"]:
        raise SystemExit("FAIL: empty month bucket present — date coalescer not wired")
    print("[build_leaders] OK — month axis populated, no empty bucket")


if __name__ == "__main__":
    main()

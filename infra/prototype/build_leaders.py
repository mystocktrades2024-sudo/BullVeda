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
SCORE_HIST   = ROOT / "cache" / "score_history.json"
DESK_LOG     = ROOT / "data"  / "desk_signal_log.jsonl"   # Screener Desk engine calls
OHLCV_DIR    = ROOT / "data"  / "ohlcv"                    # cached bars (0 EODHD grid scoring)
OUT          = Path(__file__).resolve().parent / "data_leaders.json"

DESK_LABELS = {"mom": "Momentum Desk", "bo": "Breakout Desk", "pb": "Pullback Desk",
               "qf": "Quant Desk", "cat": "Catalyst Desk", "mr": "Mean-Rev Desk",
               "val": "Value Desk", "smart": "Smart-Money Desk", "qual": "Quality Desk",
               "def": "Defensive Desk", "short": "Short Desk"}

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
    {"id": "desks",     "label": "Screener Desks"},
]

# setup → engine. audit_ledger setups seen: pullback, momentum, bounce, breakout,
# ema_pullback, vcp, insider_cluster, EMA21 Pullback, breakdown, mean_reversion, …
def _setup_to_source(setup: str, family: str) -> str:
    s = (setup or "").strip().lower()
    f = (family or "").strip().lower()
    if "insider" in s:                                   return "insiders"
    # Earnings / catalyst engine FIRST — PEAD/ESP/gap setups OR the Impulse Catalyst
    # family. Checked before momentum so a catalyst play that happens to carry a
    # trend-continuation setup is attributed to its driving engine (earnings), not
    # mislabeled momentum.
    if any(k in s for k in ("pead", "gap", "earnings", "esp")) or "impulse" in f or "catalyst" in f:
        return "earnings"
    # Momentum engine — the momentum-continuation sleeve's setups (audit 2026-06-03).
    # These were falling through to the 'screeners' catch-all, leaving the Momentum
    # source EMPTY despite being the largest engine: "Trend Continuation" alone = 1,609
    # calls, plus EMA21/50 pullbacks, Pocket Pivot, 10-Week Pullback, RS New High.
    if (any(k in s for k in ("momentum", "trend continuation", "continuation",
                             "ema21 pullback", "ema50 pullback", "ema pullback",
                             "pocket pivot", "rs new high", "10-week pullback", "10 week pullback"))
            or "trend continuation" in f or "momentum" in f):
        return "momentum"
    if any(k in s for k in ("vcp", "breakout", "52w", "cup", "squeeze", "spring")):
        return "smc"
    if any(k in s for k in ("uoa", "option")):           return "options"
    # family fallback
    if "breakout" in f:                                  return "smc"
    if "special" in f:                                   return "insiders"
    # bounce / mean_reversion / breakdown / rebreak / SAR / … → general screener pool
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


# ── Screener Desk engine calls → same ledger schema (forward grid from cached bars) ──
_BARS_CACHE: dict = {}

def _bars_close(ticker: str):
    if ticker in _BARS_CACHE:
        return _BARS_CACHE[ticker]
    df = None
    p = OHLCV_DIR / f"{ticker}.parquet"
    if p.exists():
        try:
            import pandas as pd
            df = pd.read_parquet(p)[["Close"]].copy()
            df.index = pd.to_datetime(df.index)
        except Exception:
            df = None
    _BARS_CACHE[ticker] = df
    return df


def _desk_grid(ticker: str, date_str: str, entry: float, short: bool) -> dict:
    """Direction-aligned forward-return grid for a desk call, from cached daily bars
    (0 EODHD). None where not enough forward bars yet (maturing)."""
    df = _bars_close(ticker)
    if df is None or not entry or entry <= 0:
        return {h["id"]: None for h in HORIZONS}
    import pandas as pd
    fwd = df[df.index > pd.to_datetime(date_str)]
    out: dict = {}
    for h in HORIZONS:
        nd = h["days"]
        if len(fwd) >= nd:
            c = float(fwd["Close"].iloc[nd - 1])
            ret = (c - entry) / entry * 100.0
            out[h["id"]] = round(-ret if short else ret, 3)
        else:
            out[h["id"]] = None
    return out


def _desk_signals(today: _dt.date, start_sid: int):
    """Every Screener Desk BUY/SHORT call → ledger signals under source='desks'."""
    if not DESK_LOG.exists():
        return [], 0
    out: list[dict] = []
    sid = start_sid
    for line in DESK_LOG.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except Exception:
            continue
        ds = (e.get("date") or "")[:10]
        if not ds:
            continue
        age = _age_days(ds, today)
        if age is None:
            continue
        entry = float(e.get("entry") or 0)
        short = (e.get("dir") == "short")
        out.append({
            "id":        f"s{sid}",
            "source":    "desks",
            "sym":       e.get("ticker"),
            "dir":       "short" if short else "long",
            "regime":    _regime_bucket(e.get("regime")),
            "age":       age,
            "date":      ds,
            "refPrice":  entry or None,
            "predProb":  None,
            "verdict":   e.get("verdict"),
            "setup":     DESK_LABELS.get(e.get("desk"), e.get("desk")),
            "score":     None,
            "scoreSeries": [],
            "ret":       _desk_grid(e.get("ticker"), ds, entry, short),
        })
        sid += 1
    return out, len(out)


# ── score history (per-ticker daily composite score) ─────────────────────────
# cache/score_history.json: { "TICKER": [{date, score, verdict}, ...] }. The scan
# appends on every re-run, so COALESCE to one score per day (last write = end-of-
# day state) for a clean "today 80 → tomorrow 90" series. Joined onto each signal
# as score@pick + scoreSeries (pick date onward).
def _load_score_history() -> dict:
    try:
        return json.loads(SCORE_HIST.read_text()) or {}
    except Exception:
        return {}

_SCORE_HIST = _load_score_history()
_SCORE_COALESCED: dict = {}

def _score_series(sym: str) -> list:
    if sym in _SCORE_COALESCED:
        return _SCORE_COALESCED[sym]
    by_date: dict = {}
    for e in (_SCORE_HIST.get(sym) or []):
        d, s = (e or {}).get("date"), (e or {}).get("score")
        if d and s is not None:
            try:
                by_date[d[:10]] = int(round(float(s)))   # last write wins = EOD
            except (TypeError, ValueError):
                pass
    series = [{"date": d, "score": by_date[d]} for d in sorted(by_date)]
    _SCORE_COALESCED[sym] = series
    return series

def _score_at_and_series(sym: str, since: str):
    """(score_at_pick, series_from_pick). score@pick = coalesced score on the pick
    date (or the first on/after it); series = that date onward. ([] / None when no
    score history exists for the ticker)."""
    series = _score_series(sym or "")
    if not series:
        return None, []
    cut = (since or "")[:10]
    fwd = [e for e in series if e["date"] >= cut] if cut else series
    if not fwd:
        fwd = series          # pick predates the recorded history → show full series
    return fwd[0]["score"], fwd


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
            _score_pick, _score_fwd = _score_at_and_series(r.get("ticker"), ds)
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
                "score":     _score_pick,          # composite score at pick (None if no history)
                "scoreSeries": _score_fwd,         # [{date, score}] one-per-day from pick onward
                "ret":       grid,                 # REAL grid; null entry = maturing
            }
            signals.append(sig)
            sid += 1
            month_hist[ds[:7]] = month_hist.get(ds[:7], 0) + 1
            src_hist[src] = src_hist.get(src, 0) + 1

    # ── Screener Desk engine calls (source='desks') — its own forward track record ──
    desk_sigs, n_desk = _desk_signals(today, sid)
    signals.extend(desk_sigs)
    for s in desk_sigs:
        month_hist[s["date"][:7]] = month_hist.get(s["date"][:7], 0) + 1
    if n_desk:
        src_hist["desks"] = src_hist.get("desks", 0) + n_desk

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

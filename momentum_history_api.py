"""
momentum_history_api.py — predicted-vs-realized calibration for Momentum tab.

Backs the GET /api/momentum-history endpoint. For each snapshot ≥5 days old,
pulls forward 5d adjusted-close returns via EODHD, compares to SPY, computes
alpha. Aggregates by sleeve + alpha_flag for the HISTORY sub-view.

CLAUDE.md principles enforced:
  1  statistical rigor:   n surfaced on every aggregate; (low n) flag at n<10
  11 edge erosion:        calibration evolves daily as snapshots roll forward
  16 sub-strategy attrib: by_sleeve + by_alpha_flag breakdowns
  20 process > outcome:   predicted_verdict + composite are surfaced alongside
                          realized 5d/SPY-rel return — no P&L attribution
"""
from __future__ import annotations
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo("America/Los_Angeles")
except Exception:  # pragma: no cover
    _TZ = timezone(timedelta(hours=-8))

BASE_DIR = Path(__file__).resolve().parent
SNAPSHOTS_PATH = BASE_DIR / "data" / "momentum_snapshots.jsonl"
HORIZON_DAYS = 5

# In-process cache (1 hour). Re-computed on a fresh process.
_CACHE: dict = {"ts": 0.0, "value": None}
_CACHE_TTL = 3600  # 1hr


def _today_pt() -> datetime:
    return datetime.now(_TZ)


def _date_str(d: datetime) -> str:
    return d.strftime("%Y-%m-%d")


def _parse(d: str) -> datetime | None:
    try:
        return datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=_TZ)
    except Exception:
        return None


def _load_snapshots() -> list[dict]:
    if not SNAPSHOTS_PATH.exists():
        return []
    out: list[dict] = []
    try:
        with open(SNAPSHOTS_PATH) as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    out.append(json.loads(ln))
                except Exception:
                    continue
    except Exception:
        return []
    return out


def _fetch_eod(ticker: str, from_date: str, to_date: str) -> list[dict] | None:
    """Wrapper around eodhd_client.eod — silent failure returns None."""
    try:
        import eodhd_client as _eod
        return _eod.eod(ticker, from_date=from_date, to_date=to_date, cache_ttl=86400)
    except Exception:
        return None


def _forward_5d_return(ticker: str, snap_date: str) -> tuple[float | None, dict]:
    """
    Compute the close-to-close % change from the first trading day AFTER
    snap_date through 5 trading days later (or the last available bar).

    Returns (pct_change_or_None, {first_date, last_date, bars_used}).
    """
    sd = _parse(snap_date)
    if sd is None:
        return None, {"reason": "bad date"}
    # Pull a 10-day window after the snapshot date so we get >=5 trading days.
    start = (sd + timedelta(days=1)).strftime("%Y-%m-%d")
    end = (sd + timedelta(days=15)).strftime("%Y-%m-%d")
    bars = _fetch_eod(ticker, start, end)
    if not bars:
        return None, {"reason": "no bars"}
    # Use adjusted_close where available, else close
    def _ac(b):
        v = b.get("adjusted_close")
        if v is None:
            v = b.get("close")
        return v
    bars = sorted([b for b in bars if isinstance(b, dict) and b.get("date")], key=lambda b: b["date"])
    if not bars:
        return None, {"reason": "no usable bars"}
    take = bars[:HORIZON_DAYS]
    first = take[0]
    last = take[-1]
    p0 = _ac(first)
    p1 = _ac(last)
    try:
        if p0 is None or p1 is None or float(p0) == 0:
            return None, {"reason": "missing price"}
        pct = (float(p1) / float(p0) - 1.0) * 100.0
    except Exception:
        return None, {"reason": "math err"}
    return pct, {"first_date": first["date"], "last_date": last["date"], "bars_used": len(take)}


def _spy_5d_cache_for_dates(dates: list[str]) -> dict[str, float]:
    """Pre-fetch SPY 5d returns for all unique snapshot dates."""
    out: dict[str, float] = {}
    for d in dates:
        pct, _ = _forward_5d_return("SPY", d)
        if pct is not None:
            out[d] = pct
    return out


def _classify_status(alpha_pp: float | None, days_since: int) -> str:
    if days_since < HORIZON_DAYS or alpha_pp is None:
        return "PENDING"
    if alpha_pp >= 5.0: return "MASSIVE_WIN"
    if alpha_pp <= -5.0: return "MASSIVE_LOSS"
    if alpha_pp > 0:    return "PROFIT"
    return "UNDER"


def _safe_mean(xs: list[float]) -> float | None:
    return (sum(xs) / len(xs)) if xs else None


def build_momentum_history() -> dict:
    """
    Public entry: returns the dict shape documented in CLAUDE.md ask.
    """
    # Cache hit?
    now = time.time()
    if _CACHE["value"] is not None and (now - _CACHE["ts"]) < _CACHE_TTL:
        return _CACHE["value"]

    snaps = _load_snapshots()
    if not snaps:
        result = {
            "snapshots": [],
            "calibration": None,
            "status": "no_history_yet",
            "message": ("snapshot file empty — momentum_snapshot.py needs to run "
                        "for 5+ days to build calibration"),
        }
        _CACHE.update({"ts": now, "value": result})
        return result

    today = _today_pt()
    unique_dates = sorted({s.get("date") for s in snaps if s.get("date")})
    distinct_n = len(unique_dates)

    # Pre-fetch SPY baselines for all snapshot dates that are old enough.
    eligible_dates = [
        d for d in unique_dates
        if d and (_parse(d) is not None) and (today - _parse(d)).days >= HORIZON_DAYS
    ]
    spy_cache = _spy_5d_cache_for_dates(eligible_dates)

    # Build per-snapshot enriched records.
    enriched: list[dict] = []
    for s in snaps:
        d = s.get("date")
        dt = _parse(d) if d else None
        days_since = (today - dt).days if dt else 0
        rec = {
            "date": d,
            "ticker": s.get("ticker"),
            "rank": s.get("rank"),
            "predicted": {
                "composite": s.get("composite"),
                "sleeve": s.get("sleeve"),
                "alpha_flag": s.get("alpha_flag"),
                "verdict": s.get("verdict"),
                "score": s.get("score"),
                "sharpe_126d": s.get("sharpe_126d"),
                "rs_rank": s.get("rs_rank"),
                "setup": s.get("setup"),
                "sector": s.get("sector"),
                "price": s.get("price"),
                "ema_signal": s.get("ema_signal"),
            },
            "realized": None,
            "days_since": days_since,
        }
        if days_since >= HORIZON_DAYS and d:
            pct, meta = _forward_5d_return(s.get("ticker") or "", d)
            spy_pct = spy_cache.get(d)
            alpha = (pct - spy_pct) if (pct is not None and spy_pct is not None) else None
            rec["realized"] = {
                "pct_5d": round(pct, 3) if pct is not None else None,
                "spy_pct_5d": round(spy_pct, 3) if spy_pct is not None else None,
                "alpha_pp": round(alpha, 3) if alpha is not None else None,
                "status": _classify_status(alpha, days_since),
                "first_date": meta.get("first_date"),
                "last_date": meta.get("last_date"),
            }
        enriched.append(rec)

    # Sort newest snapshots first
    enriched.sort(key=lambda r: (r["date"] or "", -(r.get("rank") or 0)), reverse=True)

    # Calibration aggregates — only over snapshots that have 5d data
    with_data = [r for r in enriched if r.get("realized") and r["realized"].get("alpha_pp") is not None]
    total = len(enriched)
    n_data = len(with_data)

    if n_data == 0:
        # Have snapshots but no realized yet (everything still pending)
        result = {
            "snapshots": enriched,
            "calibration": None,
            "status": "no_history_yet" if distinct_n < 2 else "pending",
            "message": (f"have {total} snapshot picks across {distinct_n} day(s) — "
                        f"need ≥{HORIZON_DAYS} trading days after each snapshot to compute "
                        f"realized 5d return"),
            "distinct_dates": distinct_n,
        }
        _CACHE.update({"ts": now, "value": result})
        return result

    alphas = [r["realized"]["alpha_pp"] for r in with_data]
    pcts = [r["realized"]["pct_5d"] for r in with_data]
    spys = [r["realized"]["spy_pct_5d"] for r in with_data]
    wins = sum(1 for a in alphas if a > 0)
    wr = wins / n_data if n_data else 0.0

    # by_sleeve
    by_sleeve: dict[str, dict] = {}
    for r in with_data:
        sl = (r["predicted"].get("sleeve") or "Unknown")
        b = by_sleeve.setdefault(sl, {"n": 0, "wins": 0, "alphas": [], "pcts": []})
        b["n"] += 1
        b["alphas"].append(r["realized"]["alpha_pp"])
        b["pcts"].append(r["realized"]["pct_5d"])
        if r["realized"]["alpha_pp"] > 0:
            b["wins"] += 1
    for sl, b in by_sleeve.items():
        b["wr"] = round(b["wins"] / b["n"], 4) if b["n"] else 0
        b["avg_alpha"] = round(_safe_mean(b["alphas"]), 3) if b["alphas"] else None
        b["avg_pct"] = round(_safe_mean(b["pcts"]), 3) if b["pcts"] else None
        b["low_n"] = b["n"] < 10
        del b["alphas"]; del b["pcts"]

    # by_alpha_flag
    by_flag: dict[str, dict] = {}
    for r in with_data:
        f = (r["predicted"].get("alpha_flag") or "neutral")
        b = by_flag.setdefault(f, {"n": 0, "wins": 0, "alphas": []})
        b["n"] += 1
        b["alphas"].append(r["realized"]["alpha_pp"])
        if r["realized"]["alpha_pp"] > 0:
            b["wins"] += 1
    for f, b in by_flag.items():
        b["wr"] = round(b["wins"] / b["n"], 4) if b["n"] else 0
        b["avg_alpha"] = round(_safe_mean(b["alphas"]), 3) if b["alphas"] else None
        b["low_n"] = b["n"] < 10
        del b["alphas"]

    # Best / worst pick by alpha
    best = max(with_data, key=lambda r: r["realized"]["alpha_pp"])
    worst = min(with_data, key=lambda r: r["realized"]["alpha_pp"])

    calibration = {
        "total_picks": total,
        "with_5d_data": n_data,
        "distinct_dates": distinct_n,
        "win_rate": round(wr, 4),
        "avg_alpha_pp": round(_safe_mean(alphas), 3) if alphas else None,
        "avg_realized_pct": round(_safe_mean(pcts), 3) if pcts else None,
        "avg_spy_pct": round(_safe_mean(spys), 3) if spys else None,
        "by_sleeve": by_sleeve,
        "by_alpha_flag": by_flag,
        "best_pick": {
            "date": best["date"], "ticker": best["ticker"],
            "alpha_pp": best["realized"]["alpha_pp"],
        },
        "worst_pick": {
            "date": worst["date"], "ticker": worst["ticker"],
            "alpha_pp": worst["realized"]["alpha_pp"],
        },
    }

    result = {
        "snapshots": enriched,
        "calibration": calibration,
        "status": "ok",
        "horizon_days": HORIZON_DAYS,
        "generated_at": datetime.now(_TZ).isoformat(timespec="seconds"),
        "data_source": "data/momentum_snapshots.jsonl × eodhd cache",
    }
    _CACHE.update({"ts": now, "value": result})
    return result

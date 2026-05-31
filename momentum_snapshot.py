#!/usr/bin/env python3
"""
momentum_snapshot.py — Daily snapshot writer for Momentum-tab calibration.

Appends today's top-20 momentum candidates to data/momentum_snapshots.jsonl so
the HISTORY sub-view (kairos.html / QuantMomentum) can compare predicted vs
realized 5-day returns. Idempotent per date (will not double-write today).

The filter + composite + sleeve + alpha-flag logic mirrors the JS in
QuantMomentum so the two stay in sync. Any change to either side must be
mirrored in the other or the calibration drifts off-spec.

Per CLAUDE.md principle 1 (statistical rigor), 11 (edge erosion), 16
(performance attribution by sub-strategy), 20 (process > outcome).

Run standalone:  python3 momentum_snapshot.py
Auto-invoked:    end of swing_trade.py via try/except (best-effort, never raises).
"""

from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Pacific time for the snapshot date (matches the rest of the system)
try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo("America/Los_Angeles")
except Exception:  # pragma: no cover
    _TZ = timezone(timedelta(hours=-8))

BASE_DIR = Path(__file__).resolve().parent
# Primary source: V2 dashboard build (carries `above_21ema/50ema` + `sharpe_1y`
# fields the QuantMomentum module actually consumes; these are dropped from
# cache/last_bundle.json's `all_scored`).
TICKERS_PATH = BASE_DIR / "infra" / "prototype" / "tickers.json"
# Fallback: cache/last_bundle.json (used only if tickers.json is missing).
BUNDLE_PATH = BASE_DIR / "cache" / "last_bundle.json"
OUT_PATH = BASE_DIR / "data" / "momentum_snapshots.jsonl"
TOP_N = 20  # we snapshot the top-20 to keep calibration meaningful

# ── Setup-level alpha attribution (mirrors kairos.html _ZERO_ALPHA_SETUPS) ──
_ZERO_ALPHA_SETUPS = ["Trend Continuation", "Breakout Expansion"]
_ALPHA_SETUPS = ["VCP", "52w Breakout", "52wk Breakout", "10WP", "10 Week Pullback"]


# ── Mirror of QuantMomentum._isMomentumCandidate ──────────────────────────
def _is_momentum_candidate(r: dict) -> bool:
    rs = float(r.get("rs_rank") or 0)
    s126 = float(r.get("sharpe_126d") or 0)
    up21 = bool(r.get("above_21ema"))
    up50 = bool(r.get("above_50ema"))
    return (rs >= 60 and up21) or (s126 >= 1.0 and up50)


# ── Mirror of QuantMomentum._trendOf / _compositeScore ────────────────────
def _trend_of(s126, s1y) -> str:
    if s126 is None or s1y is None:
        return "flat"
    d = s126 - s1y
    if d >= 0.4:
        return "accel"
    if d <= -0.4:
        return "decay"
    return "flat"


def _composite_score(r: dict) -> float:
    s126 = float(r.get("sharpe_126d") or 0)
    s_norm = ((max(-3.0, min(5.0, s126)) + 3.0) / 8.0) * 100
    adx = float(r.get("adx") or 0)
    adx_norm = min(60.0, max(0.0, adx)) / 60.0 * 100
    s1y_raw = r.get("sharpe_1y")
    s1y = float(s1y_raw) if s1y_raw is not None else None
    trend = _trend_of(s126, s1y)
    trend_bonus = 20 if trend == "accel" else (-20 if trend == "decay" else 0)
    return max(0.0, min(100.0, s_norm * 0.60 + adx_norm * 0.40 + trend_bonus * 0.15))


# ── Mirror of QuantMomentum._sleeveOf ─────────────────────────────────────
def _sleeve_of(raw: dict) -> dict:
    if not isinstance(raw, dict):
        return {"code": "pb", "label": "Pullback to Value"}

    def _fired(a):
        return isinstance(a, dict) and a.get("fired") is True

    if _fired(raw.get("defrot_audit")):
        return {"code": "def", "label": "Defensive Rotation"}
    if _fired(raw.get("esp_play_audit")):
        return {"code": "esp", "label": "ESP Play"}
    if _fired(raw.get("insider_cluster_audit")):
        return {"code": "ins", "label": "Insider Cluster"}
    if _fired(raw.get("meanrev_audit")):
        return {"code": "mrv", "label": "Mean Reversion"}
    if _fired(raw.get("pead_audit")):
        return {"code": "esp", "label": "PEAD"}

    sf = str(raw.get("setup_family") or raw.get("setup") or "")
    has_mom_runtime = raw.get("_runtime_qqq_spy_momentum_21d") is not None
    if has_mom_runtime and any(k in sf for k in ("Trend", "Momentum", "trend", "momentum")):
        return {"code": "mom", "label": "Mom Continuation"}
    return {"code": "pb", "label": "Pullback to Value"}


def _alpha_flag(raw: dict) -> str:
    sf = str(raw.get("setup_family") or raw.get("setup") or "").lower()
    if any(z.lower() in sf for z in _ZERO_ALPHA_SETUPS):
        return "zero_alpha"
    if any(a.lower() in sf for a in _ALPHA_SETUPS):
        return "alpha"
    return "neutral"


def _verdict_of(raw: dict) -> str:
    d = raw.get("decision")
    if isinstance(d, dict):
        return str(d.get("verdict") or "").upper()
    return str(d or raw.get("verdict") or "").upper()


def _today_pt() -> str:
    return datetime.now(_TZ).strftime("%Y-%m-%d")


def _load_existing_dates() -> set[str]:
    """Return the set of snapshot dates already in OUT_PATH (idempotency)."""
    if not OUT_PATH.exists():
        return set()
    dates: set[str] = set()
    try:
        with open(OUT_PATH) as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    obj = json.loads(ln)
                    d = obj.get("date")
                    if d:
                        dates.add(d)
                except Exception:
                    continue
    except Exception:
        pass
    return dates


def _load_rows() -> list[dict]:
    """Load rows from tickers.json (primary) or last_bundle.json (fallback)."""
    if TICKERS_PATH.exists():
        try:
            with open(TICKERS_PATH) as f:
                t = json.load(f)
            # tickers.json is a dict {TICKER: {row}} in current build.
            if isinstance(t, dict):
                rows = []
                for tk, row in t.items():
                    if not isinstance(row, dict):
                        continue
                    row = dict(row)
                    row.setdefault("ticker", tk)
                    rows.append(row)
                return rows
            if isinstance(t, list):
                return [r for r in t if isinstance(r, dict)]
        except Exception:
            pass
    # Fallback
    if BUNDLE_PATH.exists():
        try:
            with open(BUNDLE_PATH) as f:
                bundle = json.load(f)
            arr = (bundle.get("all_scored")
                   or bundle.get("scored")
                   or bundle.get("signals")
                   or [])
            return [r for r in arr if isinstance(r, dict)]
        except Exception:
            pass
    return []


def write_snapshot(out_path: Path | None = None,
                   override_date: str | None = None,
                   force: bool = False) -> dict:
    """
    Append today's top-20 momentum candidates to OUT_PATH.

    Returns a dict {status, date, written, total_candidates, reason?} so the
    caller can log a one-line summary.
    """
    op = Path(out_path) if out_path else OUT_PATH
    today = override_date or _today_pt()

    if not force:
        existing = _load_existing_dates()
        if today in existing:
            return {"status": "skip", "reason": "date already snapshotted", "date": today, "written": 0}

    arr = _load_rows()
    if not arr:
        return {"status": "skip", "reason": "no rows loaded (tickers.json + last_bundle.json both empty/missing)", "written": 0}

    # Filter momentum candidates, compute composite, sort desc
    mom = []
    for r in arr:
        if not _is_momentum_candidate(r):
            continue
        comp = _composite_score(r)
        mom.append((comp, r))

    if not mom:
        return {"status": "skip", "reason": "no momentum candidates", "written": 0, "date": today}

    mom.sort(key=lambda x: x[0], reverse=True)
    top = mom[:TOP_N]

    op.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    # Single append-write per row (jsonl). Add a small in-memory dup-guard
    # against (date,ticker) collisions within the same write.
    seen: set[tuple[str, str]] = set()
    with open(op, "a") as f:
        for rank, (comp, r) in enumerate(top, start=1):
            tk = str(r.get("ticker") or r.get("symbol") or "").upper()
            if not tk or (today, tk) in seen:
                continue
            seen.add((today, tk))
            sleeve = _sleeve_of(r)
            row = {
                "date": today,
                "ticker": tk,
                "rank": rank,
                "composite": round(comp, 4),
                "sharpe_126d": float(r.get("sharpe_126d") or 0),
                "sharpe_1y": float(r["sharpe_1y"]) if r.get("sharpe_1y") is not None else None,
                "rs_rank": float(r.get("rs_rank") or 0),
                "score": float(r.get("score") or 0),
                "verdict": _verdict_of(r),
                "sleeve": sleeve["label"],
                "sleeve_code": sleeve["code"],
                "alpha_flag": _alpha_flag(r),
                "setup": str(r.get("setup_family") or r.get("setup") or ""),
                "sector": str(r.get("sector") or "Other"),
                "price": float(r.get("price") or 0),
                "ema_signal": str(r.get("ema_signal") or ""),
                "adx": float(r["adx"]) if r.get("adx") is not None else None,
                "trend": _trend_of(
                    float(r["sharpe_126d"]) if r.get("sharpe_126d") is not None else None,
                    float(r["sharpe_1y"]) if r.get("sharpe_1y") is not None else None,
                ),
                "_written_at": datetime.now(_TZ).isoformat(timespec="seconds"),
            }
            f.write(json.dumps(row, default=str) + "\n")
            written += 1

    return {
        "status": "ok",
        "date": today,
        "written": written,
        "total_candidates": len(mom),
        "out_path": str(op),
    }


def main(argv: list[str]) -> int:
    force = "--force" in argv
    override = None
    for a in argv:
        if a.startswith("--date="):
            override = a.split("=", 1)[1]
    res = write_snapshot(override_date=override, force=force)
    print(json.dumps(res, indent=2))
    # exit 0 for success AND idempotent skip ("already snapshotted" is a healthy no-op,
    # not a failure — returning 1 made launchd/dashboard flag the job degraded every day).
    # Reserve non-zero for a genuine error status.
    return 1 if res.get("status") == "error" else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

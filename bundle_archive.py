"""
bundle_archive.py — Per-date snapshot of each scan bundle for time-travel.

On every scan, save a TRIMMED copy of the bundle to cache/bundles/YYYY-MM-DD.json.
Trimmed = only the fields the Screener/time-travel UI needs (ticker, score,
verdict, setup, key indicators). Full news/enrichment payloads are dropped so
each file is ~1-3 MB instead of 60 MB.

Overwrite-per-day: if multiple scans run on the same date, the latest wins.
Retention: keep last N days (default 90); older files auto-pruned.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).parent
BUNDLES_DIR = BASE / "cache" / "bundles"
RETAIN_DAYS = 90


_KEEP_TICKER_FIELDS = {
    "ticker", "name", "price", "score", "rs_rank",
    "direction", "setup_type", "sector", "industry",
    "bear_type", "mtf_conflict", "days_to_earnings", "trend_age_bars",
    "grade_value", "grade_growth", "grade_momentum", "grade_vgm",
    "star_rating",
}


def _trim_ticker(r: dict) -> dict:
    if not isinstance(r, dict):
        return {}
    out = {k: r[k] for k in _KEEP_TICKER_FIELDS if k in r}
    # Decision — keep verdict and reason only
    d = r.get("decision") or {}
    out["decision"] = {
        "verdict": d.get("verdict", ""),
        "reason":  d.get("reason", ""),
    }
    # State (forward-looking message) if present
    state = r.get("state") or {}
    if isinstance(state, dict):
        out["state"] = {
            "action":   state.get("action"),
            "phase":    state.get("phase"),
            "location": state.get("location"),
            "edge":     state.get("edge"),
            "setup_quality":     state.get("setup_quality"),
            "dashboard_message": state.get("dashboard_message"),
        }
    # Pillar scores for screener table
    out["fundamentals"] = {"score": (r.get("fundamentals") or {}).get("score", 0)}
    out["technicals"]   = {"score": (r.get("technicals") or {}).get("score", 0)}
    out["optionality"]  = {"score": (r.get("optionality") or {}).get("score", 0)}
    out["sentiment"]    = {"score": (r.get("sentiment") or {}).get("score", 0)}
    out["trade_plan"]   = {
        "entry":     (r.get("trade_plan") or {}).get("entry"),
        "stop":      (r.get("trade_plan") or {}).get("stop"),
        "target1":   (r.get("trade_plan") or {}).get("target1"),
        "rr_ratio":  (r.get("trade_plan") or {}).get("rr_ratio"),
    }
    # Gate — just passed/reasons, not the full object
    g = r.get("gate") or {}
    out["gate"] = {
        "passed":  g.get("passed", True),
        "reasons": (g.get("reasons") or [])[:3],
    }
    out["bear_setup"] = {"score": (r.get("bear_setup") or {}).get("score", 0)}
    return out


def save_snapshot(bundle: dict, active_profile: str | None = None) -> Path | None:
    """Save a trimmed snapshot of the bundle for today's date. Returns path."""
    try:
        BUNDLES_DIR.mkdir(parents=True, exist_ok=True)
        today = datetime.now().strftime("%Y-%m-%d")
        path = BUNDLES_DIR / f"{today}.json"

        all_scored = bundle.get("all_scored", []) or []
        killed     = bundle.get("killed", []) or []

        trimmed = {
            "date":        today,
            "saved_at":    datetime.now().isoformat(timespec="seconds"),
            "profile":     active_profile,
            "regime":      (bundle.get("regime") or {}).get("regime"),
            "regime4":     (bundle.get("regime") or {}).get("regime4"),
            "spy_price":   (bundle.get("regime") or {}).get("spy_price"),
            "vix":         (bundle.get("regime") or {}).get("vix_current") or (bundle.get("regime") or {}).get("vix", {}).get("vix_current") if isinstance(bundle.get("regime"), dict) else None,
            "breadth_50":  (bundle.get("market_breadth") or {}).get("pct_above_50d"),
            "counts": {
                "buy":    len(bundle.get("buy_candidates", []) or []),
                "watch":  len(bundle.get("watch_list", []) or []),
                "short":  len(bundle.get("sell_candidates", []) or []),
                "near_short_blocked": len(bundle.get("near_short_blocked", []) or []),
                "killed": len(killed),
                "all_scored": len(all_scored),
            },
            "all_scored": [_trim_ticker(r) for r in all_scored],
            "killed":     [_trim_ticker(r) for r in killed],
        }
        path.write_text(json.dumps(trimmed, default=str))
        _prune()
        return path
    except Exception:
        return None


def _prune(days: int = RETAIN_DAYS) -> None:
    """Keep only the most recent N files, sorted by filename (date)."""
    if not BUNDLES_DIR.exists():
        return
    files = sorted(BUNDLES_DIR.glob("*.json"), key=lambda p: p.name)
    if len(files) > days:
        for p in files[:-days]:
            try:
                p.unlink()
            except Exception:
                pass


def list_snapshots() -> list[dict]:
    """Return snapshot metadata (date, counts) for every archived day."""
    if not BUNDLES_DIR.exists():
        return []
    out = []
    for p in sorted(BUNDLES_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(p.read_text())
            out.append({
                "date":     data.get("date", p.stem),
                "saved_at": data.get("saved_at"),
                "profile":  data.get("profile"),
                "regime":   data.get("regime"),
                "regime4":  data.get("regime4"),
                "counts":   data.get("counts", {}),
                "size_kb":  round(p.stat().st_size / 1024),
            })
        except Exception:
            continue
    return out


def load_snapshot(date: str) -> dict | None:
    """Load a snapshot by date (YYYY-MM-DD). Returns None if missing."""
    path = BUNDLES_DIR / f"{date}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None

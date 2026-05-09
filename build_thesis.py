"""
build_thesis.py — generate per-ticker thesis card for the V2 dashboard.

Path C (deterministic auto-thesis): pulls structured data from a scored ticker
row (as found in cache/last_bundle.json["all_scored"]) and emits a thesis dict
with four sections: score_breakdown, why_bullish, risks, trade_plan, plus a
one-line narrative (template-driven; can be replaced by an LLM line via
narrate_thesis.py if available).

This module has no I/O — `build_thesis(row)` is pure. Hook it from build_data.py
when bundling the V2 data.json.
"""
from __future__ import annotations

from typing import Any


_PILLAR_MAP = [
    # (display, breakdown_key, max_score, threshold_for_check)
    ("Technical",   "tech_score",     40, 28),
    ("Catalyst",    "cat_score",      20, 12),
    ("Rel. Strength", "rs_score",     25, 18),
    ("Smart Money", "sm_score",       10,  6),
    ("Quality+Growth", "qg_score",    10,  6),
    ("Entry · R:R", "entry_rr_score", 10,  6),
]


def _safe(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _verdict_glyph(pts: float, max_pts: int, ok: int) -> str:
    if pts >= ok:
        return "check"
    if pts >= ok * 0.6:
        return "warn"
    return "weak"


def _score_breakdown(row: dict) -> list[dict]:
    sb = row.get("scoring_breakdown") or {}
    out: list[dict] = []
    for label, key, mx, ok in _PILLAR_MAP:
        pts = _safe(sb.get(key))
        out.append({
            "pillar": label,
            "pts": round(pts, 1),
            "max": mx,
            "verdict": _verdict_glyph(pts, mx, ok),
        })
    # WR multiplier and bonus tail
    wr_mult = _safe(sb.get("wr_multiplier"), 1.0)
    bonus = _safe(sb.get("bonus_total"))
    if wr_mult and wr_mult != 1.0:
        out.append({
            "pillar": "WR adjust",
            "pts": round(wr_mult, 2),
            "max": "×",
            "verdict": "check" if wr_mult >= 1.0 else "warn",
            "note": f"setup-history multiplier",
        })
    if bonus:
        out.append({
            "pillar": "Bonuses",
            "pts": round(bonus, 1),
            "max": "+",
            "verdict": "check" if bonus > 0 else "weak",
        })
    return out


def _why_bullish(row: dict) -> list[str]:
    """Concrete, evidence-backed bullish bullets."""
    bullets: list[str] = []

    # Trend / EMA stack
    ind = (row.get("technicals") or {}).get("indicators") or {}
    ema_signal = row.get("ema_signal") or ""
    if "BULLISH" in str(ema_signal).upper():
        bullets.append(f"EMA stack bullish ({ema_signal})")
    if ind.get("above_20ema") and ind.get("above_50ema") and ind.get("above_200ema"):
        bullets.append("Trading above all key MAs (20/50/200)")

    # Relative strength
    rs = _safe(row.get("rs_rank"))
    if rs >= 80:
        bullets.append(f"RS rank {int(rs)} — top {max(1, 100 - int(rs))}% of universe")
    elif rs >= 65:
        bullets.append(f"RS rank {int(rs)} — relative strength positive")

    # MACD / momentum
    macd = str(row.get("macd_signal") or "").upper()
    if "GOLDEN" in macd or "BULL" in macd:
        bullets.append(f"MACD signal: {row.get('macd_signal')}")

    # Setup family
    setup = row.get("setup_family") or row.get("setup_type") or ""
    if setup and setup not in ("Trend Continuation",):
        bullets.append(f"Setup: {setup}")

    # Catalysts
    tags = row.get("catalyst_tags") or []
    if tags:
        bullets.append(f"Catalysts: {', '.join(tags[:3])}")

    # News sentiment
    news = row.get("news_sentiment_score") or {}
    ns = _safe(news.get("score"))
    if ns >= 6:
        bullets.append(f"News sentiment positive ({int(ns)}/10)")

    # Fundamentals bull drivers (top 2)
    fund_bulls = (row.get("fundamentals") or {}).get("bull_drivers") or []
    for b in fund_bulls[:2]:
        bullets.append(b)

    # Options skew
    opt = row.get("options_data") or {}
    pcr = _safe(opt.get("put_call_ratio"))
    if 0 < pcr < 0.5:
        bullets.append(f"Options skew bullish (P/C {pcr:.2f})")
    iv_rank = _safe(opt.get("iv_rank"))
    if iv_rank >= 60:
        bullets.append(f"IV rank {int(iv_rank)} — elevated, options pricing in a move")

    # Insider buying
    ins = row.get("insider_data") or {}
    if _safe(ins.get("buys")) > _safe(ins.get("sells")) and ins.get("ceo_buy"):
        bullets.append("Insider buying: CEO purchase on file")

    # Monte Carlo profit probability
    mcpp = _safe(row.get("mc_p_profit"))
    if mcpp >= 0.6:
        bullets.append(f"Monte Carlo P(profit) {int(mcpp*100)}%")

    return bullets[:8]


def _risks(row: dict) -> list[str]:
    """Concrete risk bullets — what could break the trade."""
    risks: list[str] = []

    # Entry quality
    eq = row.get("entry_quality") or ""
    if eq == "EXTENDED":
        risks.append("Entry EXTENDED — chase risk; wait for pullback")
    elif eq == "INVALID":
        risks.append("Entry quality INVALID — outside value zone")

    # Earnings risk
    e = row.get("earnings") or {}
    eday = e.get("days_to_earnings")
    if isinstance(eday, (int, float)) and 0 < eday <= 5:
        risks.append(f"Earnings in {int(eday)} days — gap risk")
    if e.get("earnings_risk") in ("HIGH", "ELEVATED"):
        risks.append(f"Earnings risk flag: {e.get('earnings_risk')}")

    # Volatility
    atrp = _safe(row.get("atr_pct"))
    if atrp >= 5:
        risks.append(f"High volatility (ATR {atrp:.1f}%) — wider stops needed")

    # Fundamentals bear risks (top 2)
    fund_bears = (row.get("fundamentals") or {}).get("bear_risks") or []
    for b in fund_bears[:2]:
        risks.append(b)

    # Analyst upside negative
    a = row.get("analyst") or {}
    upside = _safe(a.get("upside_pct"))
    if upside < 0:
        risks.append(f"Analyst PTs {upside:.1f}% below price — limited sell-side support")

    # Options skew risk
    opt = row.get("options_data") or {}
    pcr = _safe(opt.get("put_call_ratio"))
    if pcr >= 1.5:
        risks.append(f"Options bearish (P/C {pcr:.2f})")

    # Gate caveats
    for c in (row.get("caveats") or [])[:2]:
        risks.append(c)

    # Squeeze
    if row.get("squeeze"):
        risks.append("Volatility squeeze — direction unresolved")

    # Beta
    beta = _safe(row.get("beta"))
    if beta >= 2.0:
        risks.append(f"Beta {beta:.1f} — moves harder than market in either direction")

    # Distance from 52w high
    kpi = row.get("kpi") or {}
    dh = _safe(kpi.get("dist_from_52wk_high_pct"))
    if -3 <= dh <= 0:
        risks.append("Within 3% of 52w high — resistance overhead")

    return risks[:7]


def _trade_plan(row: dict) -> dict:
    tp = row.get("trade_plan") or {}
    if not tp:
        return {}
    entry_low = tp.get("entry_low")
    entry_high = tp.get("entry_high")
    stop = tp.get("stop")
    t1 = tp.get("target1")
    t2 = tp.get("target2")
    hold = tp.get("max_hold_days") or row.get("hold_period_guide", "5-10d")
    direction = tp.get("direction", "long")

    # R:R from prices
    rr = None
    try:
        if entry_low and entry_high and stop and t1:
            mid = (float(entry_low) + float(entry_high)) / 2
            risk = abs(mid - float(stop))
            reward = abs(float(t1) - mid)
            if risk:
                rr = round(reward / risk, 1)
    except Exception:
        pass

    sizing = (row.get("kelly_size") or {}).get("final_alloc_pct")
    return {
        "direction": direction,
        "entry_low": entry_low,
        "entry_high": entry_high,
        "stop": stop,
        "target1": t1,
        "target2": t2,
        "rr_ratio": rr,
        "max_hold_days": hold,
        "size_pct": sizing,
        "setup_type": tp.get("setup_type"),
        "entry_quality_adj": tp.get("entry_quality_adj"),
    }


def _narrative(row: dict, breakdown: list[dict], bullish: list[str], risks: list[str]) -> str:
    """One-line summary, template-driven. Replace with LLM via narrate_thesis if available."""
    ticker = row.get("ticker", "?")
    score = int(_safe(row.get("score")))
    verdict = row.get("verdict", "?")
    setup = row.get("setup_family") or row.get("setup_type") or "no setup"
    sector = row.get("sector") or "—"

    # Strongest pillar
    top_pillar = max(
        (p for p in breakdown if isinstance(p.get("max"), (int, float))),
        key=lambda p: (p["pts"] / p["max"]) if p["max"] else 0,
        default=None,
    )
    weakest_pillar = min(
        (p for p in breakdown if isinstance(p.get("max"), (int, float))),
        key=lambda p: (p["pts"] / p["max"]) if p["max"] else 1,
        default=None,
    )
    strong_part = f"{top_pillar['pillar']} {int(top_pillar['pts'])}/{top_pillar['max']}" if top_pillar else ""
    weak_part = f"{weakest_pillar['pillar']} {int(weakest_pillar['pts'])}/{weakest_pillar['max']}" if weakest_pillar else ""

    sentence = (
        f"{ticker} ({sector}) is a {score}-score {verdict} backed by {setup}; "
        f"strongest pillar is {strong_part}, weakest is {weak_part}."
    )
    return sentence


def build_thesis(row: dict) -> dict:
    """
    Return a thesis dict for one scored ticker row. Pure function — no I/O.

    Output schema:
      {
        "ticker": str,
        "score": int,
        "verdict": str,
        "narrative": str,                 # 1-line summary
        "score_breakdown": [{pillar, pts, max, verdict}, ...],
        "why_bullish": [str, ...],        # max 8 bullets
        "risks":       [str, ...],        # max 7 bullets
        "trade_plan":  {...} | {},
        "decision_reason": str,
      }
    """
    breakdown = _score_breakdown(row)
    bullish = _why_bullish(row)
    risks = _risks(row)
    plan = _trade_plan(row)
    narrative = _narrative(row, breakdown, bullish, risks)
    decision = row.get("decision") or {}

    return {
        "ticker": row.get("ticker"),
        "score": int(_safe(row.get("score"))),
        "verdict": row.get("verdict") or decision.get("verdict") or "?",
        "narrative": narrative,
        "score_breakdown": breakdown,
        "why_bullish": bullish,
        "risks": risks,
        "trade_plan": plan,
        "decision_reason": decision.get("reason") or row.get("reject_reason") or "",
        "tier": (row.get("conviction") or {}).get("label") or "",
        "regime": row.get("regime4") or "",
        "sector": row.get("sector") or "",
        "industry": row.get("industry") or "",
    }


if __name__ == "__main__":
    # Smoke test against last_bundle
    import json, sys
    from pathlib import Path
    p = Path(__file__).resolve().parent / "cache" / "last_bundle.json"
    b = json.loads(p.read_text())
    sample = next(
        (s for s in b.get("all_scored", []) if s.get("score", 0) >= 80),
        b.get("all_scored", [None])[0],
    )
    if not sample:
        print("no rows"); sys.exit(1)
    print(json.dumps(build_thesis(sample), indent=2, default=str))

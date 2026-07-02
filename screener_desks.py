"""screener_desks.py — build the 11 archetype "desk" books from a scan bundle.

DISPLAY LAYER ONLY. This module re-presents existing scanner output (all_scored /
buy_candidates / watch_list / near_short_blocked) into eleven trader-archetype books.
It adds NO new trading signal, mutates NO score, and gates NO verdict — it only sorts
the names the scan already produced into books and attaches the per-setup edge stats
the tracker already computed. Consumed by /api/screener_desks (server.py) and by the
Schwab live-overlay writer (run_screener_desks_live.py).

Desks (regime-aware): momentum · breakout · pullback · quant-factor · catalyst ·
mean-reversion · value · smart-money · quality · defensive · short.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).parent

VGM = {"Strong Buy": 92, "Buy": 74, "Watch": 52, "Hold": 50,
       "Sell": 30, "Strong Sell": 15, "Avoid": 34}

DEFENSIVE_WL = {"XLU", "GLD", "JNJ", "PG", "KO", "PEP", "WMT", "COST",
                "MRK", "ABBV", "DUK", "SO", "NEE"}

STATE_RANK = {"AT_ZONE": 100, "FRESH": 95, "AT_SHALLOW_ZONE": 90,
              "APPROACHING": 75, "PULLBACK": 70, "VALID": 60}

DLBL = {"mom": "Momentum", "bo": "Breakout", "pb": "Pullback", "qf": "Quant",
        "cat": "Catalyst", "mr": "Mean-Rev", "val": "Value",
        "smart": "Smart-Money", "qual": "Quality", "def": "Defensive", "short": "Short"}

# Static per-desk presentation metadata. `edge_family` (if set) pulls real Wilson
# stats from setup_stats.json; otherwise `edge_fallback` is used verbatim.
DESK_META = [
    ("pb",   "SWING · PULLBACK",     "Swing trader — strong stock dipping into a buy zone",
     "Rank by entry location: at-zone / fresh beats extended. 3:1 R:R.",           "var(--dk-pb)",
     "Trend Continuation", None),
    ("qf",   "QUANT · FACTOR",       "Hedge fund — multi-factor cross-sectional rank",
     "Blend momentum + quality + trend + value + catalyst, ranked vs peers.",       "var(--dk-qf)",
     None, {"class": "e-unp", "text": "BLEND · IC validation pending · gate ≥60 composite"}),
    ("cat",  "CATALYST · EVENT",     "Event desk — PEAD · UOA · insider · ESP",
     "Post-earnings / options-flow drift. Regime-independent.",                     "var(--dk-cat)",
     "Impulse Catalyst", None),
    ("mom",  "MOMENTUM",             "Momentum trader — buys the strongest names",
     "Rank by relative strength + risk-adjusted trend. New highs welcome.",         "var(--dk-mom)",
     None, {"class": "e-unp", "text": "PAPER · momentum sleeve n<10 · edge pending"}),
    ("bo",   "BREAKOUT",             "Breakout trader — coil firing through a pivot",
     "Volatility contraction → rank by volume expansion at the trigger.",           "var(--dk-bo)",
     "Breakout Expansion", None),
    ("mr",   "MEAN-REVERSION",       "Reversion — oversold bounce, uptrend intact",
     "RSI<38 + quality-gated. Own eligibility (full universe).",                    "var(--dk-mr)",
     None, {"class": "e-unp", "text": "PAPER · RSI<30 + >EMA200 · edge pending"}),
    ("val",  "VALUE · CONTRARIAN",   "Value investor — cheap on P/E · EV/EBITDA · FCF",
     "Cheap-decile, quality-gated. Reversion to fair value.",                       "var(--dk-val)",
     None, {"class": "e-unp", "text": "BLEND · cheap-decile, quality-gated"}),
    ("smart", "SMART MONEY",         "Coattail — insider clusters + Congress buys",
     "Follow ≥3-insider $200K clusters + congressional buys.",                      "var(--dk-smart)",
     "Insider Cluster", None),
    ("qual", "QUALITY · COMPOUNDER", "GARP — high ROIC, durable margins",
     "ROE + gross-margin blend. Invest-horizon anchor.",                            "var(--dk-qual)",
     None, {"class": "e-unp", "text": "BLEND · quality factor · Invest anchor"}),
    ("def",  "DEFENSIVE",            "Rotation — XLU/GLD/staples when breadth breaks",
     "Whitelist, beta≤1. Arms when SPY<50EMA.",                                     "var(--dk-def)",
     None, {"class": "e-unp", "text": "Arms when SPY<50EMA"}),
    ("short", "SHORT · BREAKDOWN",   "Down book — distribution / RS-worst",
     "Bearish structure. Needs VIX>25 + bear regime.",                             "var(--dk-short)",
     None, {"class": "e-unp", "text": "Shorts need VIX>25 + bear regime"}),
]

SMART_EMPTY = ("No cluster today — 0 names hit ≥3 insiders / $200K in 30d; "
               "congressional feed unavailable. Desk populates when a cluster forms.")


def _n(x, d=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def _shp(s):
    return max(0.0, min(100.0, (_n(s) + 1) / 5 * 100))


def _val_score(xf):
    if not isinstance(xf, dict):
        return None
    parts = []
    pe, ps, ev = xf.get("fwd_pe"), xf.get("ps"), xf.get("ev_ebitda")
    if pe and _n(pe) > 0:
        parts.append(max(10, min(95, 110 - _n(pe) * 1.4)))
    if ps and _n(ps) > 0:
        parts.append(max(10, min(95, 95 - _n(ps) * 4)))
    if ev and _n(ev) > 0:
        parts.append(max(10, min(95, 100 - _n(ev) * 3)))
    return round(sum(parts) / len(parts), 0) if parts else None


def _enrich(r, live=None):
    """Turn a raw bundle row into a compact desk row, applying the Schwab live
    overlay (price / pct / live zone-state) when a quote is available."""
    xf = r.get("extra_fund") or {}
    fe = r.get("finviz_elite") or {}
    ctp = r.get("canonical_trade_plan") or {}
    e = ctp.get("entry") or {}
    tech = r.get("technicals") if isinstance(r.get("technicals"), dict) else {}
    o = dict(
        t=r.get("ticker"), price=r.get("price"), score=r.get("score"),
        rs=r.get("rs_rank"), rsi=r.get("rsi"), rvol=r.get("rvol"), atr=r.get("atr_pct"),
        sharpe=r.get("sharpe_126d"), sector=r.get("sector"), industry=r.get("industry"),
        setup=r.get("setup_family"), eq=r.get("entry_quality"),
        verdict=(r.get("verdict") or r.get("decision") or ""),
        state=(r.get("decision_state") or {}).get("state"), vgm=r.get("vgm_verdict"),
        cat=r.get("catalyst_tier"), mcp=r.get("mc_p_profit"),
        entry_lo=e.get("low"), entry_hi=e.get("high"), stop=ctp.get("stop"),
        t1=ctp.get("target1"),
        fwd_pe=xf.get("fwd_pe"), ps=xf.get("ps"),
        roe=(fe.get("roe_pct") or xf.get("roe")), gm=fe.get("gross_margin_pct"),
        short_float=fe.get("short_float_pct"),
    )
    # --- raw structural signals for the per-desk BUY checklists (from the scan) ---
    ind = tech.get("indicators") or {}
    sr = tech.get("sr") or {}
    o["adx"] = ind.get("adx")
    o["bull_stack"] = ind.get("bullish_stack")
    o["ema8"] = ind.get("ema8")
    o["ema21"] = ind.get("ema21")
    o["ema50i"] = ind.get("ema50")
    o["above50"] = ind.get("above_50ema")
    o["above200"] = ind.get("above_200sma")
    o["vcp"] = ind.get("vcp")
    o["near_vcp"] = ind.get("near_vcp")
    o["squeeze_on"] = ind.get("squeeze_on")
    o["squeeze_fired"] = ind.get("squeeze_fired")
    o["at_52wbo"] = ind.get("at_52w_breakout")
    o["near52h"] = ind.get("near_52w_high")
    o["vcp_pivot"] = ind.get("vcp_pivot")
    o["pocket_pivot"] = ind.get("pocket_pivot")
    o["bo_vol"] = ind.get("breakout_vol_ratio")
    o["resistance"] = ind.get("resistance") or sr.get("resistance")
    o["stoch_os"] = ind.get("stoch_oversold")
    o["bb_pct_b"] = ind.get("bb_pct_b")           # Bollinger position (top-of-band = stretched)
    o["stoch_ob"] = ind.get("stoch_overbought")   # StochRSI overbought
    o["cat_tags"] = r.get("catalyst_tags") or []
    o["est_rev"] = xf.get("estimate_revision")
    o["avg_volume"] = r.get("avg_volume")
    # horizon signals — weekly/monthly lookbacks so Position/Invest mean something
    o["perf_m"] = fe.get("perf_month_pct")
    o["perf_q"] = fe.get("perf_quarter_pct")
    o["perf_h"] = fe.get("perf_half_pct")
    o["perf_y"] = fe.get("perf_year_pct")
    o["weekly_bull"] = ind.get("weekly_ema_bullish")
    o["rs63"] = ind.get("rs_63d_pct")
    # pre-trade decision fields (trade ticket)
    o["beta"] = r.get("beta")
    earn = r.get("earnings") if isinstance(r.get("earnings"), dict) else {}
    o["ear_days"] = earn.get("days_to_earnings")
    o["ear_risk"] = earn.get("earnings_risk")
    o["_mom"] = _n(o["rs"])
    o["_qual"] = VGM.get(o["vgm"], 50)
    o["_trend"] = _shp(o["sharpe"])
    o["_val"] = _val_score(xf)
    o["_cat"] = {1: 90, 2: 65, 3: 45}.get(o["cat"], 40)
    vv = o["_val"] if o["_val"] is not None else 50
    o["_factor"] = round(0.24 * o["_mom"] + 0.22 * o["_qual"] + 0.20 * o["_trend"]
                         + 0.18 * vv + 0.16 * o["_cat"], 1)
    roe_norm = min(100, max(0, _n(o["roe"]) * 2.5))
    gm_norm = min(100, max(0, _n(o["gm"]) * 1.25))
    o["_qc"] = round(0.4 * roe_norm + 0.3 * gm_norm + 0.3 * o["_qual"], 1)
    try:
        ee, ss, tt = _n(o["entry_hi"]), _n(o["stop"]), _n(o["t1"])
        o["_rr"] = round((tt - ee) / (ee - ss), 1) if ee > ss else None
    except Exception:
        o["_rr"] = None
    # --- Schwab live overlay ---
    q = (live or {}).get((o["t"] or "").upper()) if live else None
    if q and q.get("price") is not None:
        lp = _n(q["price"])
        o["price"] = lp
        o["_livepx"] = True
        pc = q.get("prev_close")
        if pc:
            o["_chg"] = round((lp - _n(pc)) / _n(pc) * 100, 2)
        lv = q.get("volume")
        if lv is not None and _n(o.get("avg_volume")) > 0:
            frac = _n((live or {}).get("_dayfrac")) or 1.0
            o["_live_rvol"] = round(_n(lv) / (_n(o["avg_volume"]) * frac), 2)
        lo, hi = _n(o["entry_lo"]), _n(o["entry_hi"])
        if lo and hi:
            if lo <= lp <= hi:
                o["_livestate"] = "AT_ZONE"
            elif lp < lo:
                o["_livestate"] = "BELOW_ZONE"
            elif lp > hi * 1.02:
                o["_livestate"] = "EXTENDED"
            else:
                o["_livestate"] = "APPROACHING"
    return o


def _scrub(o):
    """Replace non-finite floats (NaN/Inf) with None so the payload is strict-JSON
    compliant — FastAPI's encoder rejects them with allow_nan=False."""
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {k: _scrub(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_scrub(v) for v in o]
    return o


def _top(pool, key, k=7):
    return sorted(pool, key=key, reverse=True)[:k]


def _pct_threshold(vals, p):
    xs = sorted(v for v in vals if v is not None)
    if not xs:
        return None
    idx = min(len(xs) - 1, max(0, int(math.ceil(p / 100.0 * len(xs))) - 1))
    return xs[idx]


def _day_fraction():
    """Fraction of the 9:30-16:00 ET session elapsed (for time-adjusted live RVOL).
    Returns 1.0 pre-open / after-close / weekend so RVOL isn't over-inflated."""
    from datetime import datetime
    try:
        import zoneinfo
        now = datetime.now(zoneinfo.ZoneInfo("America/New_York"))
    except Exception:
        return 1.0
    if now.weekday() >= 5:
        return 1.0
    mins = (now.hour * 60 + now.minute) - (9 * 60 + 30)
    total = 6 * 60 + 30
    if mins <= 0 or mins >= total:
        return 1.0
    return max(0.05, mins / total)


def _eff_rvol(r):
    """Live time-adjusted RVOL when Schwab volume is present, else the scan's RVOL."""
    lr = r.get("_live_rvol")
    return _n(lr) if lr is not None else _n(r.get("rvol"))


def _hmom(r, hz):
    """Horizon-appropriate momentum: RS-rank (swing), 3-mo perf (position), 12-mo (invest)."""
    if hz == "position":
        return _n(r.get("perf_q"))
    if hz == "invest":
        return _n(r.get("perf_y"))
    return _n(r.get("rs"))


def _extended(r):
    """Technical chase gate — is the stock a bad entry RIGHT NOW (current bars only,
    no history)? Returns (is_extended, reasons). Two 'strong' disqualifiers or two
    'minor' ones flag it. This is what would demote CGNX/GTX from BUY to WATCH."""
    px = _n(r.get("price")); ema21 = _n(r.get("ema21")); atrp = _n(r.get("atr"))
    strong, minor = [], []
    if px and ema21 and atrp > 0:
        ea = (px - ema21) / px * 100 / atrp     # extension above EMA21 in ATR units
        if ea > 1.5:
            strong.append(f"{ea:.1f}ATR>EMA21")   # clear blow-off extension
        elif ea > 1.0:
            minor.append(f"{ea:.1f}ATR>EMA21")
    if r.get("near52h") and not r.get("at_52wbo"):
        minor.append("52w-high, no breakout")     # consolidating-at-high alone is OK
    bbb = _n(r.get("bb_pct_b"))
    if bbb and bbb > 0.92:
        minor.append("%b>0.92")
    if r.get("stoch_ob"):
        minor.append("StochRSI OB")
    if _n(r.get("rsi")) >= 72:
        minor.append(f"RSI{_n(r.get('rsi')):.0f}")
    ext = len(strong) >= 1 or len(minor) >= 2      # a blow-off, or 2+ warning signs
    return ext, (strong + minor)


def _extended_breakout(r):
    """Breakout-specific: a fresh trigger is fine, but if price has already run >1.5 ATR
    PAST the pivot you're buying it late. Returns (is_late, reason)."""
    px = _n(r.get("price")); atrp = _n(r.get("atr"))
    trig = _n(r.get("vcp_pivot")) or _n(r.get("resistance"))
    if px and trig and atrp > 0 and px > trig:
        past = (px - trig) / px * 100 / atrp
        if past > 1.5:
            return True, f"{past:.1f}ATR past pivot"
    return False, ""


def _over_bounced(r):
    """Short-specific (inverse extension): don't short a name that's already oversold /
    bouncing / stretched to the downside. Returns (bad_short, reasons)."""
    px = _n(r.get("price")); ema21 = _n(r.get("ema21")); atrp = _n(r.get("atr")); rsi = _n(r.get("rsi"))
    reasons = []
    if rsi and rsi < 35:
        reasons.append(f"RSI{rsi:.0f}<35 oversold")
    if r.get("stoch_os"):
        reasons.append("StochRSI oversold")
    if px and ema21 and atrp > 0:
        below = (ema21 - px) / px * 100 / atrp
        if below > 1.5:
            reasons.append(f"{below:.1f}ATR<EMA21 stretched-down")
    return (len(reasons) >= 1, reasons)


def _ck(cond, label):
    return ("✓ " if cond else "✗ ") + label


def _desk_verdict(desk, r, ctx, hz="swing"):
    """Each desk's OWN BUY call from raw signals (NOT the scanner's composite verdict),
    horizon-aware. Returns (verdict, why) where `why` lists the checklist conditions.
    px is the live Schwab price when present, so structural checks re-evaluate intraday."""
    px = _n(r.get("price"))
    rs = _n(r.get("rs"))
    adx = _n(r.get("adx"))
    sharpe = _n(r.get("sharpe"))
    rvol = _eff_rvol(r)
    rsi = _n(r.get("rsi"))
    ema8 = _n(r.get("ema8"))

    if desk == "mom":  # Minervini/O'Neil trend leadership (horizon-scaled)
        px_ok = (not px or not ema8 or px > ema8)
        if hz == "swing":
            c = [rs >= 90, r.get("bull_stack"), adx >= 25, sharpe >= 1.5, rvol >= 1.2, px_ok]
            why = [_ck(c[0], f"RS{int(rs)}≥90"), _ck(c[1], "EMA stack"), _ck(c[2], f"ADX{adx:.0f}≥25"),
                   _ck(c[3], f"Sharpe{sharpe:.1f}≥1.5"), _ck(c[4], f"RVOL{rvol:.1f}≥1.2"), _ck(c[5], "px>EMA8")]
            watch = rs >= 85 and r.get("bull_stack")
        elif hz == "position":
            pq = _n(r.get("perf_q"))
            c = [r.get("weekly_bull"), pq >= 15, r.get("above50"), adx >= 20]
            why = [_ck(c[0], "weekly EMA↑"), _ck(c[1], f"3mo{pq:+.0f}%≥15"), _ck(c[2], ">EMA50"), _ck(c[3], f"ADX{adx:.0f}≥20")]
            watch = r.get("weekly_bull") and pq >= 8
        else:  # invest
            py, ph = _n(r.get("perf_y")), _n(r.get("perf_h"))
            c = [r.get("above200"), py >= 20, ph >= 0]
            why = [_ck(c[0], ">200EMA"), _ck(c[1], f"12mo{py:+.0f}%≥20"), _ck(c[2], f"6mo{ph:+.0f}%>0")]
            watch = r.get("above200") and py >= 10
        # even momentum shouldn't chase a blow-off extension — demote to WATCH
        ext, exr = _extended(r) if hz == "swing" else (False, [])
        why.append(_ck(not ext, "not extended" + ((" — " + ", ".join(exr)) if ext else "")))
        if all(c) and not ext:
            return "BUY", why
        return ("WATCH", why) if (watch or all(c)) else ("PASS", why)

    if desk == "bo":  # VCP / squeeze breakout through pivot on volume
        trig = _n(r.get("vcp_pivot")) or _n(r.get("resistance"))
        at_trigger = bool(r.get("at_52wbo")) or (px and trig and px >= trig * 0.99)
        setup = r.get("vcp") or r.get("squeeze_fired") or r.get("at_52wbo") or r.get("pocket_pivot")
        volx = _n(r.get("bo_vol")) >= 1.3 or rvol >= 1.5
        late, lr = _extended_breakout(r)   # already run past the pivot = buying late
        why = [_ck(setup, "VCP/squeeze/pivot"), _ck(at_trigger, "at trigger"),
               _ck(volx, f"vol {rvol:.1f}×"), _ck(not late, "fresh trigger" + ((" — " + lr) if late else ""))]
        if setup and at_trigger and volx and not late:
            return "BUY", why
        if r.get("near_vcp") or r.get("squeeze_on") or r.get("near52h"):
            return "WATCH", why
        return "PASS", why

    if desk == "pb":  # pullback to value zone in an uptrend, 3:1 R:R
        lo, hi = _n(r.get("entry_lo")), _n(r.get("entry_hi"))
        inzone = (px and lo and hi and lo <= px <= hi) or r.get("_livestate") == "AT_ZONE" or r.get("state") == "AT_ZONE" or r.get("eq") == "FRESH"
        rr = _n(r.get("_rr"))
        up = r.get("above50") if hz != "invest" else r.get("above200")
        why = [_ck(up, ">EMA50" if hz != "invest" else ">200EMA"), _ck(inzone, "in buy-zone"), _ck(rr >= 3, f"R:R {rr:.1f}≥3")]
        if up and inzone and rr >= 3:
            return "BUY", why
        if up and r.get("state") in ("APPROACHING", "AT_ZONE", "PULLBACK"):
            return "WATCH", why
        return "PASS", why

    if desk == "qf":  # top-decile factor blend + TIMING confirmation
        f = r.get("_factor")
        p90 = ctx.get("factor_p90")
        p75 = ctx.get("factor_p75")
        top = p90 is not None and f is not None and f >= p90 and _n(r.get("_qual")) >= 60
        ext, exr = _extended(r)
        why = [_ck(top, f"factor {f:.0f}≥p90 {(_n(p90)):.0f}"),
               _ck(not ext, "not extended" + ((" — " + ", ".join(exr)) if ext else ""))]
        if top and not ext:
            return "BUY", why
        if top or (p75 is not None and f is not None and f >= p75):
            return "WATCH", why  # ranks high but timing unconfirmed
        return "PASS", why

    if desk == "cat":  # catalyst present + holding above EMA21 + NOT a chase entry
        tags = set(r.get("cat_tags") or [])
        cat_present = bool(tags & {"PEAD", "UOA", "VCP", "POCKET_PIVOT"}) or r.get("cat") == 1 or r.get("_pcr") is not None
        ema21 = _n(r.get("ema21"))
        above = (not px or not ema21 or px > ema21)
        ext, exr = _extended(r)
        why = [_ck(cat_present, "catalyst present"), _ck(above, ">EMA21"),
               _ck(not ext, "not extended" + ((" — " + ", ".join(exr)) if ext else ""))]
        if cat_present and above and not ext:
            return "BUY", why
        if cat_present or tags:
            return "WATCH", why    # good name, but chasing → wait for pullback
        return "PASS", why

    if desk == "mr":  # oversold bounce with the long-term trend intact
        why = [_ck(rsi and rsi < 30, f"RSI{rsi:.0f}<30"), _ck(r.get("above200"), ">200EMA")]
        if rsi and rsi < 30 and r.get("above200"):
            return "BUY", why
        if rsi and rsi < 38 and r.get("above200"):
            return "WATCH", why
        return "PASS", why

    if desk == "val":  # cheap-decile, quality-gated, revisions not falling
        vv = _n(r.get("_val"))
        quality = _n(r.get("roe")) > 0
        not_down = r.get("est_rev") != "down"
        why = [_ck(vv >= 70, f"cheap {vv:.0f}≥70"), _ck(quality, "ROE>0"), _ck(not_down, "revisions not falling")]
        if vv >= 70 and quality and not_down:
            return "BUY", why
        if vv >= 60 and quality:
            return "WATCH", why
        return "PASS", why

    if desk == "qual":  # GARP — high ROE + durable margins + not a chase entry
        qc, roe, gm = _n(r.get("_qc")), _n(r.get("roe")), _n(r.get("gm"))
        ext, exr = _extended(r)
        why = [_ck(qc >= 70, f"qual {qc:.0f}≥70"), _ck(roe >= 15, f"ROE{roe:.0f}≥15"),
               _ck(gm >= 40, f"GM{gm:.0f}≥40"), _ck(not ext, "not extended" + ((" — " + ", ".join(exr)) if ext else ""))]
        if qc >= 70 and roe >= 15 and gm >= 40 and not ext:
            return "BUY", why
        if qc >= 55:
            return "WATCH", why
        return "PASS", why

    if desk == "smart":  # membership = a cluster / congressional buy fired
        return "BUY", [_ck(True, "insider/congress cluster")]

    if desk == "def":  # only a BUY when the regime actually calls for defense
        armed = ctx.get("regime") in ("risk_off_trending", "risk_off", "panic")
        why = [_ck(armed, "regime risk-off"), _ck(rs >= 50, f"RS{int(rs)}≥50")]
        if armed and rs >= 50:
            return "BUY", why
        return "WATCH", why

    if desk == "short":  # bearish structure + relative weakness — but not into a bounce
        ema50 = _n(r.get("ema50i"))
        c = [px and ema50 and px < ema50, adx >= 20, rs <= 30]
        bounce, br = _over_bounced(r)   # inverse extension: don't short an oversold bounce
        why = [_ck(c[0], "px<EMA50"), _ck(c[1], f"ADX{adx:.0f}≥20"), _ck(c[2], f"RS{int(rs)}≤30"),
               _ck(not bounce, "not over-bounced" + ((" — " + ", ".join(br)) if bounce else ""))]
        return ("SHORT", why) if (all(c) and not bounce) else ("AVOID", why)

    return "PASS", []


def _ticket(desk, r, ctx):
    """Pro pre-trade layer, all SELF-COMPUTED (never the old scanner's kelly/mc):
    probability + expectancy from the desk's OWN R:R × its measured win-rate,
    vol-targeted size from a fixed risk budget ÷ ATR-stop, plus $ADV / earnings /
    short-float / beta straight from market data."""
    de = (ctx.get("desk_edge") or {}).get(desk) or {}
    wr = de.get("wilson_lb") or de.get("wr")          # conservative: Wilson lower bound
    wr = _n(wr) if wr else 0.45                        # neutral prior when unmeasured
    rr = _n(r.get("_rr")) or 2.4                       # ATR-implied 3:1.25 fallback
    ev = round(wr * rr - (1 - wr) * 1.0, 2)            # expectancy in R
    atrp = _n(r.get("atr"))
    stop_dist = max(2.0, 1.25 * atrp) if atrp else None
    RISK_BUDGET = 0.75                                 # % of account risked per trade
    size = maxloss = None
    if stop_dist:
        size = round(RISK_BUDGET / (stop_dist / 100.0), 1)
        size = min(size, 15.0, _n(ctx.get("max_size")) or 100.0)  # vol + regime capped
        maxloss = round(size * stop_dist / 100.0, 2)
    adv = None
    if _n(r.get("price")) > 0 and _n(r.get("avg_volume")) > 0:
        adv = _n(r.get("price")) * _n(r.get("avg_volume"))
    return {
        "ev": ev, "p": round(wr, 2), "rr": round(rr, 1),
        "size": size, "maxloss": maxloss, "risk": RISK_BUDGET,
        "adv": adv, "thin": (adv is not None and adv < 20e6),
        "ear_days": r.get("ear_days"), "ear_risk": r.get("ear_risk"),
        "short_float": r.get("short_float"), "beta": r.get("beta"),
        "measured": bool(de.get("n") and not de.get("pending")),
    }


def _tag(desk, rows, ctx, hz):
    """Attach each desk's own verdict (`_dv`), reasons (`_why`), and trade-ticket
    (`_tkt`) on shallow row copies (verdict + ticket are per-desk)."""
    out = []
    for r in rows:
        v, why = _desk_verdict(desk, r, ctx, hz)
        out.append(dict(r, _dv=v, _why=" · ".join(why), _tkt=_ticket(desk, r, ctx)))
    return out


def _edge(desk_edge, key, fallback):
    """Edge header from the desk's OWN measured stats (cache/desk_edge_stats.json —
    ground-truth R-multiple attribution), not the old scanner's setup families."""
    s = (desk_edge or {}).get(key)
    if not s or s.get("pending") or not s.get("n"):
        return fallback or {"class": "e-unp", "text": "edge pending — needs signal-replay"}
    nn = s["n"]; wr = _n(s.get("wr")); pf = _n(s.get("pf")); pfh = _n(s.get("pf_haircut")); er = _n(s.get("expectancy_R"))
    if s.get("low_sample") or nn < 20:
        cls, lab = "e-unp", "LOW-N"
    elif pfh >= 1.10:
        cls, lab = "e-good", "EDGE ✓"
    elif pfh >= 1.0:
        cls, lab = "e-mid", "MARGINAL"
    else:
        cls, lab = "e-bad", "NO EDGE"
    approx = " ~approx" if s.get("approximate") else ""
    txt = f"{lab}{approx} · n={nn} · WR {wr*100:.0f}% · PF {pf:.2f}→{pfh:.2f} · E[R] {er:+.2f}"
    return {"class": cls, "text": txt}


def _desk_states(regime4):
    """Which desks LEAD / are ACTIVE / go DORMANT under the current regime."""
    r = (regime4 or "risk_on_choppy").lower()
    if r in ("risk_off_trending", "risk_off", "panic"):
        lead, dorm = {"def", "qual", "short"}, {"mom", "bo", "pb"}
    elif r in ("risk_on_trending", "bull"):
        lead, dorm = {"mom", "bo", "pb"}, {"def", "short", "mr"}
    else:  # risk_on_choppy / neutral / unknown
        lead, dorm = {"pb", "qf", "cat"}, {"def", "short"}
    out = {}
    for k in DLBL:
        out[k] = "lead" if k in lead else "dorm" if k in dorm else "act"
    return out


SHOW_N = 12  # per-desk display cap (surfaced honestly as "N of M")


def _book(desk, cands, key, ctx, hz, n=SHOW_N):
    """Rank a desk's candidate pool, tag the top-N with the desk-native verdict,
    and report the full candidate count so the UI can show 'N of M scanned'."""
    ranked = sorted(cands, key=key, reverse=True)
    return {"rows": _tag(desk, ranked[:n], ctx, hz), "n": len(cands)}


def _build_pool(universe, flow, ctx, hz, insider, congress):
    """Build all 11 desk books for one horizon from the FULL universe only (no
    old-scanner buy/watch buckets). Each desk applies its own domain filter +
    horizon-aware ranking; the verdict engine then calls BUY/WATCH/PASS."""
    for r in universe:
        if r["t"] in flow:
            r["_pcr"] = (flow.get(r["t"]) or {}).get("put_call_ratio")
    umap = {r["t"]: r for r in universe}
    hm = lambda r: _hmom(r, hz)
    n_ = _n

    mom_c = [r for r in universe if r.get("bull_stack") or r.get("weekly_bull") or r.get("above200")]
    bo_c = [r for r in universe if r.get("vcp") or r.get("near_vcp") or r.get("squeeze_on")
            or r.get("squeeze_fired") or r.get("at_52wbo") or r.get("near52h") or r.get("pocket_pivot")]
    pb_c = [r for r in universe if r.get("above50") and (r.get("eq") in ("PULLBACK", "VALID", "FRESH")
            or r.get("state") in ("AT_ZONE", "APPROACHING", "AT_SHALLOW_ZONE", "PULLBACK"))]
    qf_c = list(universe)
    cat_c = [r for r in universe if r.get("cat") == 1 or r["t"] in flow
             or (set(r.get("cat_tags") or []) & {"PEAD", "UOA", "VCP", "POCKET_PIVOT"})]
    mr_c = [r for r in universe if r.get("rsi") is not None and n_(r.get("rsi")) < 38 and r.get("above200")]
    val_c = [r for r in universe if r.get("_val") is not None and n_(r.get("_val")) >= 60 and n_(r.get("roe")) > 0]
    qual_c = [r for r in universe if (n_(r.get("roe")) > 0 or n_(r.get("gm")) > 0) and n_(r.get("_qc")) >= 55]
    def_c = [r for r in universe if r["t"] in DEFENSIVE_WL]
    smart_syms = [c.get("ticker") for c in (insider or [])] + [c.get("ticker") for c in (congress or [])]
    smart_c = [umap.get(s) or {"t": s} for s in smart_syms if s]
    short_c = [r for r in universe if n_(r.get("price")) > 0 and n_(r.get("ema50i")) > 0
               and n_(r.get("price")) < n_(r.get("ema50i")) and n_(r.get("rs")) <= 40]

    S = STATE_RANK
    return {
        "mom":   _book("mom", mom_c, lambda r: (hm(r), n_(r.get("_trend"))), ctx, hz),
        "bo":    _book("bo", bo_c, lambda r: (_eff_rvol(r), hm(r)), ctx, hz),
        "pb":    _book("pb", pb_c, lambda r: (S.get(r.get("state"), 0) + S.get(r.get("eq"), 0), hm(r)), ctx, hz),
        "qf":    _book("qf", qf_c, lambda r: n_(r.get("_factor")), ctx, hz),
        "cat":   _book("cat", cat_c, lambda r: (1 if r["t"] in flow else 0, n_(r.get("_cat")), hm(r)), ctx, hz),
        "mr":    _book("mr", mr_c, lambda r: -n_(r.get("rsi")), ctx, hz),
        "val":   _book("val", val_c, lambda r: n_(r.get("_val")), ctx, hz),
        "qual":  _book("qual", qual_c, lambda r: n_(r.get("_qc")), ctx, hz),
        "def":   _book("def", def_c, lambda r: n_(r.get("rs")), ctx, hz),
        "smart": _book("smart", smart_c, lambda r: 0, ctx, hz),
        "short": _book("short", short_c, lambda r: -n_(r.get("rs")), ctx, hz),
    }


def _confluence(books):
    """Internal cross-desk agreement only (never an input to any desk's pick)."""
    membership = defaultdict(set)
    for k, bk in books.items():
        for r in bk["rows"]:
            if r.get("t"):
                membership[r["t"]].add(k)
    for k, bk in books.items():
        for r in bk["rows"]:
            ks = sorted(membership.get(r.get("t"), []))
            r["_across"] = len(ks)
            r["_acrosslbls"] = " · ".join(DLBL[x] for x in ks)


def _best_ideas(books, states):
    """Self-contained shortlist: names the desks' OWN engines call BUY, ranked by how
    many (non-dormant) desks agree, then leading-desk presence, then factor strength."""
    buys = defaultdict(list)
    meta = {}
    for dk, bk in books.items():
        if states.get(dk) == "dorm":
            continue
        for r in bk["rows"]:
            if r.get("_dv") == "BUY":
                buys[r["t"]].append(dk)
                meta[r["t"]] = r
    out = []
    for t, dks in buys.items():
        r = meta[t]
        out.append({
            "t": t, "price": r.get("price"), "sector": r.get("sector"),
            "desks": [DLBL[d] for d in dks], "n": len(dks),
            "factor": r.get("_factor"), "rr": r.get("_rr"),
            "chg": r.get("_chg"), "livepx": r.get("_livepx"),
            "lead": any(states.get(d) == "lead" for d in dks),
        })
    out.sort(key=lambda x: (x["n"], 1 if x["lead"] else 0, _n(x["factor"])), reverse=True)
    return out[:8]


def _concentration(rows):
    """Self-contained list concentration: if one sector dominates a desk's shown names,
    flag it (e.g., '5 of 12 Technology'). Uses only the desk's own rows."""
    secs = defaultdict(int)
    for r in rows:
        if r.get("sector"):
            secs[r["sector"]] += 1
    if not secs:
        return None
    sector, cnt = max(secs.items(), key=lambda kv: kv[1])
    total = len(rows)
    if total and cnt >= 3 and cnt / total >= 0.4:
        return {"sector": sector, "n": cnt, "of": total}
    return None


def build(bundle, setup_stats=None, live=None, insider=None, congress=None, desk_edge=None, desk_live=None):
    """Build the full /api/screener_desks payload from a scan bundle.

    bundle       : parsed cache/last_bundle.json
    setup_stats  : parsed cache/setup_stats.json (per-setup Wilson edge)
    live         : {TICKER: {price, prev_close}} Schwab overlay (optional)
    insider      : insider_cluster candidates list (optional)
    congress     : congressional candidates list (optional)
    """
    reg = bundle.get("regime") or {}
    regime4 = reg.get("regime4") or "risk_on_choppy"
    states = _desk_states(regime4)

    # stamp session day-fraction so _enrich can time-adjust live RVOL
    if isinstance(live, dict) and "_dayfrac" not in live:
        try:
            live["_dayfrac"] = _day_fraction()
        except Exception:
            pass

    flow = {r.get("ticker"): r for r in (bundle.get("options_flow_top30") or [])}
    all_scored = bundle.get("all_scored") or []
    fullrows = [_enrich(r, live) for r in all_scored if r.get("ticker")]

    ctx = {
        "regime": regime4,
        "desk_edge": desk_edge or {},
        "max_size": reg.get("max_size_pct"),
        "factor_p90": _pct_threshold([r["_factor"] for r in fullrows], 90),
        "factor_p75": _pct_threshold([r["_factor"] for r in fullrows], 75),
    }

    # Every horizon scans the SAME full universe (self-sustained — no old-scanner
    # buy/watch/medium/extended buckets). The horizon changes only each desk's
    # lookback + ranking, never the universe it may pick from.
    horizons = {}
    for hz in ("swing", "position", "invest"):
        books = _build_pool(fullrows, flow, ctx, hz, insider, congress)
        _confluence(books)
        for bk in books.values():
            bk["conc"] = _concentration(bk["rows"])
        horizons[hz] = {"books": books, "best": _best_ideas(books, states)}

    # assemble ordered desk descriptors with edge + state (shared across horizons)
    desk_descriptors = []
    dl_desks = (desk_live or {}).get("desks") or {}
    for key, name, who, how, color, fam, fb in DESK_META:
        d = {"key": key, "name": name, "who": who, "how": how, "color": color,
             "state": states.get(key, "act"), "edge": _edge(desk_edge, key, fb)}
        lv = dl_desks.get(key)
        if lv and lv.get("n"):
            d["live"] = {"n": lv["n"], "wr": lv.get("wr"), "pf": lv.get("pf"), "er": lv.get("expectancy_R")}
        if key == "smart":
            d["emptymsg"] = SMART_EMPTY
        desk_descriptors.append(d)

    vix = (reg.get("vix") or {}).get("vix_current") or reg.get("vix_current")
    return _scrub({
        "generated_at": bundle.get("run_timestamp") or bundle.get("run_date"),
        "live_at": (live or {}).get("_refreshed_at") if isinstance(live, dict) else None,
        "regime": {
            "regime4": regime4,
            "vix": vix,
            "breadth": reg.get("breadth_pct_50d"),
            "distribution_days": reg.get("distribution_days"),
            "distribution_state": reg.get("distribution_state"),
            "max_size_pct": reg.get("max_size_pct"),
        },
        "desks": desk_descriptors,
        "horizons": horizons,
        "live_track": {
            "n_resolved": ((desk_live or {}).get("_meta") or {}).get("n_resolved"),
            "n_open": ((desk_live or {}).get("_meta") or {}).get("n_open"),
            "updated": ((desk_live or {}).get("_meta") or {}).get("updated"),
        },
    })


# ---- convenience loaders (used by the live-overlay writer + CLI smoke test) ----
def _load_json(rel):
    try:
        return json.loads((BASE / rel).read_text())
    except Exception:
        return None


def build_from_disk(live=None):
    bundle = _load_json("cache/last_bundle.json") or {}
    stats = _load_json("cache/setup_stats.json") or {}
    ins = (_load_json("cache/insider_cluster.json") or {}).get("candidates") or []
    con = (_load_json("cache/congressional_picks.json") or {}).get("candidates") or []
    de = (_load_json("cache/desk_edge_stats.json") or {}).get("desks") or {}
    dl = _load_json("cache/desk_track_record.json") or {}
    return build(bundle, stats, live=live, insider=ins, congress=con, desk_edge=de, desk_live=dl)


def desk_tickers(payload):
    """Every ticker shown across all desks/horizons — for the Schwab batch."""
    syms = set()
    for hz in (payload.get("horizons") or {}).values():
        for bk in (hz.get("books") or {}).values():
            for r in bk.get("rows") or []:
                if r.get("t"):
                    syms.add(r["t"])
    return sorted(syms)


if __name__ == "__main__":
    import sys
    p = build_from_disk()
    sw = p["horizons"]["swing"]["books"]
    counts = {k: f"{len(v['rows'])}/{v['n']}" for k, v in sw.items()}
    print("regime:", p["regime"]["regime4"], "| swing desks (shown/scanned):", counts)
    print("best ideas:", [(b["t"], b["n"], b["desks"]) for b in p["horizons"]["swing"]["best"][:6]])
    print("total distinct tickers:", len(desk_tickers(p)))
    if "--json" in sys.argv:
        print(json.dumps(p, default=str)[:1500])
    if "--json" in sys.argv:
        print(json.dumps(p, default=str)[:2000])

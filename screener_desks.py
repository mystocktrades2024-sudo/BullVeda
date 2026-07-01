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
     "Rank by entry location: at-zone / fresh beats extended. 3:1 R:R.",           "var(--pb)",
     "Trend Continuation", None),
    ("qf",   "QUANT · FACTOR",       "Hedge fund — multi-factor cross-sectional rank",
     "Blend momentum + quality + trend + value + catalyst, ranked vs peers.",       "var(--qf)",
     None, {"class": "e-unp", "text": "BLEND · IC validation pending · gate ≥60 composite"}),
    ("cat",  "CATALYST · EVENT",     "Event desk — PEAD · UOA · insider · ESP",
     "Post-earnings / options-flow drift. Regime-independent.",                     "var(--cat)",
     "Impulse Catalyst", None),
    ("mom",  "MOMENTUM",             "Momentum trader — buys the strongest names",
     "Rank by relative strength + risk-adjusted trend. New highs welcome.",         "var(--mom)",
     None, {"class": "e-unp", "text": "PAPER · momentum sleeve n<10 · edge pending"}),
    ("bo",   "BREAKOUT",             "Breakout trader — coil firing through a pivot",
     "Volatility contraction → rank by volume expansion at the trigger.",           "var(--bo)",
     "Breakout Expansion", None),
    ("mr",   "MEAN-REVERSION",       "Reversion — oversold bounce, uptrend intact",
     "RSI<38 + quality-gated. Own eligibility (full universe).",                    "var(--mr)",
     None, {"class": "e-unp", "text": "PAPER · RSI<30 + >EMA200 · edge pending"}),
    ("val",  "VALUE · CONTRARIAN",   "Value investor — cheap on P/E · EV/EBITDA · FCF",
     "Cheap-decile, quality-gated. Reversion to fair value.",                       "var(--val)",
     None, {"class": "e-unp", "text": "BLEND · cheap-decile, quality-gated"}),
    ("smart", "SMART MONEY",         "Coattail — insider clusters + Congress buys",
     "Follow ≥3-insider $200K clusters + congressional buys.",                      "var(--smart)",
     "Insider Cluster", None),
    ("qual", "QUALITY · COMPOUNDER", "GARP — high ROIC, durable margins",
     "ROE + gross-margin blend. Invest-horizon anchor.",                            "var(--qual)",
     None, {"class": "e-unp", "text": "BLEND · quality factor · Invest anchor"}),
    ("def",  "DEFENSIVE",            "Rotation — XLU/GLD/staples when breadth breaks",
     "Whitelist, beta≤1. Arms when SPY<50EMA.",                                     "var(--def)",
     None, {"class": "e-unp", "text": "Arms when SPY<50EMA"}),
    ("short", "SHORT · BREAKDOWN",   "Down book — distribution / RS-worst",
     "Bearish structure. Needs VIX>25 + bear regime.",                             "var(--short)",
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
    o["cat_tags"] = r.get("catalyst_tags") or []
    o["est_rev"] = xf.get("estimate_revision")
    o["avg_volume"] = r.get("avg_volume")
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


def _desk_verdict(desk, r, ctx):
    """Each desk's OWN BUY call, computed from raw signals (NOT the scanner's
    composite verdict). px is the live Schwab price when present, else scan close —
    so structural checks (price vs EMA / pivot / zone) re-evaluate intraday."""
    px = _n(r.get("price"))
    rs = _n(r.get("rs"))
    adx = _n(r.get("adx"))
    sharpe = _n(r.get("sharpe"))
    rvol = _n(r.get("rvol"))
    ema8 = _n(r.get("ema8"))

    if desk == "mom":  # Minervini/O'Neil trend leadership
        px_ok = (not px or not ema8 or px > ema8)
        if rs >= 90 and r.get("bull_stack") and adx >= 25 and sharpe >= 1.5 and rvol >= 1.2 and px_ok:
            return "BUY"
        if rs >= 85 and r.get("bull_stack") and (adx >= 20 or sharpe >= 1.0):
            return "WATCH"
        return "PASS"

    if desk == "bo":  # VCP / squeeze breakout through pivot on volume
        trig = _n(r.get("vcp_pivot")) or _n(r.get("resistance"))
        at_trigger = bool(r.get("at_52wbo")) or (px and trig and px >= trig * 0.99)
        setup = r.get("vcp") or r.get("squeeze_fired") or r.get("at_52wbo") or r.get("pocket_pivot")
        volx = _n(r.get("bo_vol")) >= 1.3 or rvol >= 1.5
        if setup and at_trigger and volx:
            return "BUY"
        if r.get("near_vcp") or r.get("squeeze_on") or r.get("near52h"):
            return "WATCH"
        return "PASS"

    if desk == "pb":  # pullback to value zone in an uptrend, 3:1 R:R
        lo, hi = _n(r.get("entry_lo")), _n(r.get("entry_hi"))
        inzone = (px and lo and hi and lo <= px <= hi) or r.get("state") == "AT_ZONE" or r.get("eq") == "FRESH"
        if r.get("above50") and inzone and _n(r.get("_rr")) >= 3:
            return "BUY"
        if r.get("above50") and r.get("state") in ("APPROACHING", "AT_ZONE", "PULLBACK"):
            return "WATCH"
        return "PASS"

    if desk == "qf":  # top-decile cross-sectional factor blend
        f = r.get("_factor")
        if ctx.get("factor_p90") is not None and f is not None and f >= ctx["factor_p90"] and _n(r.get("_qual")) >= 60:
            return "BUY"
        if ctx.get("factor_p75") is not None and f is not None and f >= ctx["factor_p75"]:
            return "WATCH"
        return "PASS"

    if desk == "cat":  # confirmed catalyst (PEAD/UOA/pivot), holding above EMA21
        tags = set(r.get("cat_tags") or [])
        t1 = bool(tags & {"PEAD", "UOA", "VCP", "POCKET_PIVOT"}) or r.get("cat") == 1 or r.get("_pcr") is not None
        ema21 = _n(r.get("ema21"))
        if t1 and (not px or not ema21 or px > ema21):
            return "BUY"
        if tags:
            return "WATCH"
        return "PASS"

    if desk == "mr":  # oversold bounce with the long-term trend intact
        rsi = _n(r.get("rsi"))
        if rsi and rsi < 30 and r.get("above200"):
            return "BUY"
        if rsi and rsi < 38 and r.get("above200"):
            return "WATCH"
        return "PASS"

    if desk == "val":  # cheap-decile, quality-gated, revisions not falling
        cheap = _n(r.get("_val")) >= 70
        quality = _n(r.get("roe")) > 0
        not_down = r.get("est_rev") != "down"
        if cheap and quality and not_down:
            return "BUY"
        if _n(r.get("_val")) >= 60 and quality:
            return "WATCH"
        return "PASS"

    if desk == "qual":  # GARP — high ROE + durable margins
        if _n(r.get("_qc")) >= 70 and _n(r.get("roe")) >= 15 and _n(r.get("gm")) >= 40:
            return "BUY"
        if _n(r.get("_qc")) >= 55:
            return "WATCH"
        return "PASS"

    if desk == "smart":  # membership = a cluster / congressional buy fired
        return "BUY"

    if desk == "def":  # only a BUY when the regime actually calls for defense
        if ctx.get("regime") in ("risk_off_trending", "risk_off", "panic") and rs >= 50:
            return "BUY"
        return "WATCH"

    if desk == "short":  # bearish structure + relative weakness
        ema50 = _n(r.get("ema50i"))
        if px and ema50 and px < ema50 and adx >= 20 and rs <= 30:
            return "SHORT"
        return "AVOID"

    return "PASS"


def _tag(desk, rows, ctx):
    """Attach each desk's own verdict as `_dv` on shallow row copies (a ticker can
    be BUY on one desk and PASS on another — the verdict is per-desk)."""
    return [dict(r, _dv=_desk_verdict(desk, r, ctx)) for r in rows]


def _edge(setup_stats, family, fallback):
    s = ((setup_stats or {}).get("setups") or {}).get(family or "")
    if not s or not s.get("n"):
        return fallback or {"class": "e-unp", "text": "edge pending"}
    nn = s.get("n"); wr = _n(s.get("wr")); pf = _n(s.get("pf")); pfh = _n(s.get("pf_haircut"))
    if nn < 30:
        cls, lab = "e-unp", "UNPROVEN"
    elif pfh >= 1.10:
        cls, lab = "e-good", "EDGE ✓"
    elif pfh >= 1.0:
        cls, lab = "e-mid", "MARGINAL"
    else:
        cls, lab = "e-bad", "NO EDGE"
    txt = f"{lab} · {family} n={nn} · WR {wr*100:.0f}% · PF {pf:.2f}→{pfh:.2f}"
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


def _build_pool(rows, fullrows, flow, short_rows, byt, insider, congress, ctx):
    """Return {desk_key: [rows]} for one horizon pool, each row tagged with its
    desk-native verdict (`_dv`)."""
    mom = _top(rows, lambda r: (r["_mom"], r["_trend"], _n(r["score"])))
    bo = _top([r for r in rows if r["setup"] == "Breakout Expansion"],
              lambda r: (_n(r["rvol"]), r["_mom"]))
    pb = _top([r for r in rows if r["eq"] in ("PULLBACK", "VALID", "FRESH")
               or r["state"] in ("AT_ZONE", "APPROACHING", "AT_SHALLOW_ZONE")],
              lambda r: (STATE_RANK.get(r["state"], 0) + STATE_RANK.get(r["eq"], 0), r["_mom"]))
    qf = _top(rows, lambda r: r["_factor"])
    cat_pool = [r for r in rows if r["cat"] == 1 or r["t"] in flow]
    for r in cat_pool:
        f = flow.get(r["t"]) or {}
        r["_pcr"] = f.get("put_call_ratio")
    cat = _top(cat_pool, lambda r: (1 if r["t"] in flow else 0, r["_cat"], r["_mom"]))
    mr = _top([r for r in fullrows if (r["rsi"] is not None and _n(r["rsi"]) < 38 and r["_qual"] >= 45)],
              lambda r: (-(_n(r["rsi"])), r["_qual"]))
    val = _top([r for r in fullrows if r["_val"] is not None and r["_qual"] >= 45],
               lambda r: r["_val"])
    qual = _top([r for r in fullrows if (r["roe"] or r["gm"])], lambda r: r["_qc"])
    dfd = [r for r in fullrows if r["t"] in DEFENSIVE_WL][:7]
    smart_syms = [c.get("ticker") for c in (insider or [])] + [c.get("ticker") for c in (congress or [])]
    smart = [(byt.get(s) or {"t": s}) for s in smart_syms if s][:7]
    sh = []
    for r in short_rows:
        o = byt.get(r.get("ticker")) or {
            "t": r.get("ticker"), "price": r.get("price"), "score": r.get("score"),
            "sector": r.get("sector"), "rs": r.get("rs_rank"), "rsi": r.get("rsi")}
        o = dict(o)
        bt = r.get("bear_type")
        o["_bear"] = bt if isinstance(bt, str) and bt else "breakdown"
        sh.append(o)
    raw = {"mom": mom, "bo": bo, "pb": pb, "qf": qf, "cat": cat, "mr": mr,
           "val": val, "smart": smart, "qual": qual, "def": dfd, "short": sh}
    return {k: _tag(k, v, ctx) for k, v in raw.items()}


def _confluence(desks):
    membership = defaultdict(set)
    for k, lst in desks.items():
        for r in lst:
            if r.get("t"):
                membership[r["t"]].add(k)
    for k, lst in desks.items():
        for r in lst:
            ks = sorted(membership.get(r.get("t"), []))
            r["_across"] = len(ks)
            r["_acrosslbls"] = " · ".join(DLBL[x] for x in ks)


def build(bundle, setup_stats=None, live=None, insider=None, congress=None):
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

    flow = {r.get("ticker"): r for r in (bundle.get("options_flow_top30") or [])}
    all_scored = bundle.get("all_scored") or []
    fullrows = [_enrich(r, live) for r in all_scored if r.get("ticker")]

    # cross-sectional context for the quant desk + regime for the defensive desk
    ctx = {
        "regime": regime4,
        "factor_p90": _pct_threshold([r["_factor"] for r in fullrows], 90),
        "factor_p75": _pct_threshold([r["_factor"] for r in fullrows], 75),
    }

    # per-horizon actionable pools
    swing_src = (bundle.get("buy_candidates") or []) + (bundle.get("watch_list") or [])
    pos_src = bundle.get("medium_term_picks") or []
    inv_src = bundle.get("extended_leaders") or []
    short_rows = bundle.get("near_short_blocked") or []

    horizons = {}
    for hz, src in (("swing", swing_src), ("position", pos_src), ("invest", inv_src)):
        rows = [_enrich(r, live) for r in src if r.get("ticker")]
        byt = {r["t"]: r for r in rows}
        desks = _build_pool(rows, fullrows, flow, short_rows, byt, insider, congress, ctx)
        _confluence(desks)
        horizons[hz] = desks

    # assemble ordered desk descriptors with edge + state (shared across horizons)
    desk_descriptors = []
    for key, name, who, how, color, fam, fb in DESK_META:
        d = {"key": key, "name": name, "who": who, "how": how, "color": color,
             "state": states.get(key, "act"), "edge": _edge(setup_stats, fam, fb)}
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
    return build(bundle, stats, live=live, insider=ins, congress=con)


def desk_tickers(payload):
    """Every ticker shown across all desks/horizons — for the Schwab batch."""
    syms = set()
    for desks in (payload.get("horizons") or {}).values():
        for lst in desks.values():
            for r in lst:
                if r.get("t"):
                    syms.add(r["t"])
    return sorted(syms)


if __name__ == "__main__":
    import sys
    p = build_from_disk()
    counts = {k: len(v) for k, v in (p["horizons"]["swing"]).items()}
    print("regime:", p["regime"]["regime4"], "| swing desk counts:", counts)
    print("total distinct tickers:", len(desk_tickers(p)))
    if "--json" in sys.argv:
        print(json.dumps(p, default=str)[:2000])

#!/usr/bin/env python3
"""schwab_real_buy_validator.py — LIVE "real buy" re-validation of candidate BUYs.

Most desk/scanner BUYs are not real buys: the composite score is anti-correlated with
forward return, the momentum gate is broken, and the weak desks (Smart-Money, Value,
Breakout, Catalyst) launder bearish / low-RS / extended / dead names into a BUY label.

This validator ignores the composite verdict and re-decides each candidate off LIVE
Schwab data: live price vs the live EMA8/21/50 stack, live RSI(14) + ADX(14), live
time-adjusted RVOL, today's move, and halt/tradability — cross-checked against the
scan's bias, entry zone (ATR), and the desk's *validated* forward-edge tier.

One Schwab batch quote covers every candidate (≤500/call) → ~0 marginal API cost, same
pattern as run_screener_desks_live.py. Intraday RSI/EMA/ADX are recomputed locally from
cached daily bars + today's live bar (no per-ticker history calls).

Verdict per ticker:
  REAL BUY  — live-bullish structure, in/near entry zone, real participation, clean momentum
  MARGINAL  — bullish but one soft flaw (extended entry, thin RVOL, weak ADX, unproven desk)
  NOT REAL  — hard fail: halted, bearish/AVOID, price below live EMA21, dumping, or broken RSI

Usage:
  python3 schwab_real_buy_validator.py                 # today's desk BUYs (+ scanner BUYs)
  python3 schwab_real_buy_validator.py NVDA BLMN CDNS  # explicit tickers
  python3 schwab_real_buy_validator.py --json          # machine-readable to stdout
Writes cache/real_buy_validation.json regardless.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, date
from pathlib import Path

BASE = Path(__file__).parent
BUNDLE = BASE / "cache" / "last_bundle.json"
DESK_LOG = BASE / "data" / "desk_signal_log.jsonl"
OUT = BASE / "cache" / "real_buy_validation.json"

# Gate thresholds live in real_buy_gate.py (shared) → config.json "real_buy_gate".
# Tune them THERE, not here — this CLI delegates every decision to the shared gate.

# ---- desk forward-edge tiers (from cache/desk_edge_stats.json + track record) -------
# validated = clears PF-haircut >=1.10 with n>=30; no_edge = FAILED the bar; unmeasured = n=0
DESK_EDGE = {
    "pb": ("validated", "Pullback  PF-haircut 1.38 (n=2699)"),
    "mr": ("validated", "Mean-Rev  PF-haircut 1.12 (n=1342)"),
    "mom": ("marginal", "Momentum  PF-haircut 1.02"),
    "qf": ("marginal", "Quant     PF-haircut ~0.99"),
    "val": ("unmeasured", "Value     n=0 backtest — UNPROVEN"),
    "qual": ("unmeasured", "Quality   n=0 backtest — UNPROVEN"),
    "smart": ("no_edge", "Smart-Money  FAILED PF-haircut 0.41"),
    "bo": ("no_edge", "Breakout     FAILED PF-haircut 0.79"),
    "cat": ("no_edge", "Catalyst     FAILED PF-haircut 0.75"),
    "def": ("no_edge", "Defensive    FAILED PF-haircut 0.14"),
    "short": ("no_edge", "Short (not a long desk)"),
}
EDGE_RANK = {"validated": 0, "marginal": 1, "unmeasured": 2, "no_edge": 3}


def _num(x, d=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def _load_bundle_index():
    """ticker -> all_scored row."""
    try:
        b = json.loads(BUNDLE.read_text())
    except Exception:
        return {}
    al = b.get("all_scored") or b.get("all") or []
    idx = {}
    for r in al:
        t = (r.get("ticker") or r.get("symbol") or "").upper()
        if t:
            idx[t] = r
    return idx


def _todays_desk_buys():
    """[(ticker, desk)] BUY longs logged for today; falls back to any BUY longs in the log."""
    today = date.today().isoformat()
    rows, any_buy = [], []
    try:
        for ln in DESK_LOG.read_text().splitlines():
            if not ln.strip():
                continue
            try:
                r = json.loads(ln)
            except Exception:
                continue
            if r.get("verdict") != "BUY" or r.get("dir") not in (None, "long", "LONG"):
                continue
            rec = ((r.get("ticker") or "").upper(), (r.get("desk") or "?").lower())
            any_buy.append((rec, r.get("date", "")))
            if str(r.get("date", ""))[:10] == today:
                rows.append(rec)
    except Exception:
        return []
    if rows:
        return rows
    # no rows for today — use the most recent logged date
    if any_buy:
        last_date = max(d[:10] for _, d in any_buy)
        return [rec for rec, d in any_buy if d[:10] == last_date]
    return []


def _gather_candidates(argv):
    """Returns {ticker: set(desks)}. CLI tickers override; else today's desk BUYs + scanner BUYs."""
    cli = [a.upper() for a in argv if a and not a.startswith("-")]
    cand = {}
    if cli:
        for t in cli:
            cand.setdefault(t, set())
        return cand
    for t, desk in _todays_desk_buys():
        if t:
            cand.setdefault(t, set()).add(desk)
    # add any scanner BUYs from the bundle (verdict/action == BUY)
    for t, r in _load_bundle_index().items():
        v = str(r.get("verdict") or (r.get("decision") or {}).get("verdict") or r.get("action") or "").upper()
        if v == "BUY":
            cand.setdefault(t, set()).add("scanner")
    return cand


def _best_desk(desks):
    """Pick the highest-edge desk among a candidate's desks."""
    ds = [d for d in desks if d in DESK_EDGE]
    if not ds:
        return None, ("unknown", "no desk")
    best = min(ds, key=lambda d: EDGE_RANK.get(DESK_EDGE[d][0], 9))
    return best, DESK_EDGE[best]


def _live_quotes(tickers):
    """One Schwab batch quote → {TICKER: {price, prev_close, volume, rsi, ema8, ema21, ema50, adx}}."""
    try:
        import schwab_client as sc
        from run_screener_desks_live import _intraday_tech
    except Exception as e:
        return None, f"import failed: {e}"
    raw = sc.get_quotes_batch(list(tickers)[:500]) or {}
    out = {}
    for sym, blob in raw.items():
        if not isinstance(blob, dict):
            continue
        qb = blob.get("quote") or {}
        last = _num(qb.get("lastPrice"))
        if last is None or last <= 0:
            continue
        rec = {"price": round(last, 2),
               "prev_close": _num(qb.get("closePrice")),
               "volume": _num(qb.get("totalVolume")),
               "net_pct": _num(qb.get("netPercentChange")),
               "status": qb.get("securityStatus") or blob.get("securityStatus")}
        tech = _intraday_tech(sym.upper(), _num(qb.get("openPrice")), _num(qb.get("highPrice")),
                              _num(qb.get("lowPrice")), last, _num(qb.get("totalVolume")))
        if tech:
            rec.update({k: v for k, v in tech.items() if v is not None})
        out[sym.upper()] = rec
    return out, None


def _validate(t, desks, row, q):
    """Build the normalized signal dict and delegate to the SHARED gate
    (real_buy_gate.evaluate) so this CLI and the desk cards never diverge."""
    import real_buy_gate as rbg
    price = q.get("price")
    prev = q.get("prev_close")
    net_pct = q.get("net_pct")
    if net_pct is None and price and prev:
        net_pct = (price - prev) / prev * 100.0
    # bear_setup is a {score,max} sub-score dict (0..15), NOT a boolean flag
    _bs = (row or {}).get("bear_setup")
    bear_ratio = (_num(_bs.get("score")) / max(_num(_bs.get("max"), 15) or 15, 1)) if isinstance(_bs, dict) else None
    # live time-adjusted RVOL
    live_rvol = None
    vol, avgv = q.get("volume"), _num((row or {}).get("avg_volume"))
    if vol and avgv:
        frac = _day_fraction()
        live_rvol = round(vol / (avgv * frac), 2) if avgv * frac > 0 else None
    best_desk = _best_desk(desks)[0]

    sig = {
        "desk": best_desk, "price": price,
        "ema8": q.get("ema8"), "ema21": q.get("ema21"), "ema50": q.get("ema50"),
        "rsi": q.get("rsi"), "adx": q.get("adx"), "live_rvol": live_rvol,
        "atr_pct": _num((row or {}).get("atr_pct")), "net_pct": net_pct,
        "bias": (row or {}).get("bias"), "bear_ratio": bear_ratio,
        "scan_action": (row or {}).get("action") or (row or {}).get("verdict"),
        "reason_class": (row or {}).get("reason_class"),
        "entry_quality": (row or {}).get("entry_quality"),
        "rs": _num((row or {}).get("rs_rank")), "sharpe": _num((row or {}).get("sharpe_126d")),
        "status": q.get("status"),
    }
    res = rbg.evaluate(sig, rbg.DESK_EDGE_TIER.get(best_desk))
    return {
        "ticker": t, "verdict": res["verdict"], "tier": res["tier"],
        "desk": best_desk, "desk_edge": res["edge_tier"], "desk_desc": _best_desk(desks)[1][1],
        "price": price, "chg_pct": round(net_pct, 2) if net_pct is not None else None,
        "live_rsi": q.get("rsi"), "live_adx": q.get("adx"),
        "live_rvol": live_rvol, "ext_atr_vs_ema21": res.get("ext_atr_vs_ema21"),
        "rs_rank": sig["rs"], "sharpe_126d": sig["sharpe"],
        "entry_quality": str((row or {}).get("entry_quality") or "").upper(),
        "bias": str((row or {}).get("bias") or "").lower() or None,
        "fails": res["fails"], "warns": res["warns"],
    }


def _day_fraction():
    """Fraction of the RTH session elapsed (0.05..1.0), for time-adjusting RVOL."""
    now = datetime.now()
    mins = now.hour * 60 + now.minute
    open_m, close_m = 6 * 60 + 30, 13 * 60  # PT market hours
    if mins <= open_m:
        return 0.05
    if mins >= close_m:
        return 1.0
    return max(0.05, min(1.0, (mins - open_m) / (close_m - open_m)))


def main():
    argv = sys.argv[1:]
    as_json = "--json" in argv
    argv = [a for a in argv if a != "--json"]

    # auth guard — degrade gracefully if the refresh token is dead
    try:
        import schwab_auth
        health = schwab_auth.check_token_health()
    except Exception as e:
        health = {"status": "unknown", "message": str(e)}
    if health.get("status") == "dead":
        print(f"❌ Schwab token DEAD — re-auth required: python3 schwab_auth.py oauth\n   {health.get('message','')}")
        return 2

    cand = _gather_candidates(argv)
    if not cand:
        print("No candidate BUYs found (no desk BUYs logged today, no scanner BUYs). "
              "Pass tickers explicitly: python3 schwab_real_buy_validator.py NVDA BLMN")
        return 1

    bundle = _load_bundle_index()
    quotes, err = _live_quotes(cand.keys())
    if quotes is None:
        print(f"❌ Schwab fetch failed: {err}")
        return 2
    if not quotes:
        print("❌ No Schwab quotes returned (market closed / token). Overlay may be stale.")
        return 2

    results = []
    for t, desks in cand.items():
        q = quotes.get(t)
        if not q:
            results.append({"ticker": t, "verdict": "NO DATA", "tier": "",
                            "desk": _best_desk(desks)[0], "fails": ["no live Schwab quote"], "warns": []})
            continue
        results.append(_validate(t, desks, bundle.get(t), q))

    order = {"REAL BUY": 0, "MARGINAL": 1, "UNVERIFIED": 2, "NOT REAL": 3, "NO DATA": 4}
    results.sort(key=lambda r: (order.get(r["verdict"], 9),
                                EDGE_RANK.get(r.get("desk_edge"), 9),
                                -(r.get("rs_rank") or 0)))

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "token_status": health.get("status"),
        "n_candidates": len(results),
        "counts": {v: sum(1 for r in results if r["verdict"] == v) for v in order},
        "results": results,
    }
    OUT.write_text(json.dumps(payload, indent=2))

    if as_json:
        print(json.dumps(payload, indent=2))
        return 0

    _print_report(payload)
    return 0


def _print_report(p):
    c = p["counts"]
    print("=" * 78)
    print(f"  LIVE SCHWAB 'REAL BUY' VALIDATION — {p['generated_at']}  (token: {p['token_status']})")
    print(f"  {p['n_candidates']} candidates → "
          f"REAL BUY {c.get('REAL BUY',0)} · MARGINAL {c.get('MARGINAL',0)} · "
          f"UNVERIFIED {c.get('UNVERIFIED',0)} · NOT REAL {c.get('NOT REAL',0)} · NO DATA {c.get('NO DATA',0)}")
    print("=" * 78)
    icon = {"REAL BUY": "✅", "MARGINAL": "⚠️ ", "UNVERIFIED": "❓", "NOT REAL": "❌", "NO DATA": "· "}
    for r in p["results"]:
        head = f"{icon.get(r['verdict'],'  ')} {r['verdict']:<8} {r['ticker']:<6}"
        if r.get("tier"):
            head += f"[{r['tier']}] "
        bits = []
        if r.get("price") is not None:
            bits.append(f"${r['price']}")
        if r.get("chg_pct") is not None:
            bits.append(f"{r['chg_pct']:+.1f}%")
        if r.get("desk"):
            bits.append(f"desk={r['desk']}({r.get('desk_edge','?')})")
        if r.get("live_rsi") is not None:
            bits.append(f"RSI{r['live_rsi']:.0f}")
        if r.get("live_adx") is not None:
            bits.append(f"ADX{r['live_adx']:.0f}")
        if r.get("live_rvol") is not None:
            bits.append(f"RVOL{r['live_rvol']:.2f}")
        if r.get("ext_atr_vs_ema21") is not None:
            bits.append(f"{r['ext_atr_vs_ema21']:+.1f}ATR/EMA21")
        print(head + "  " + " ".join(bits))
        for f in r.get("fails", []):
            print(f"        ✗ {f}")
        for w in r.get("warns", [])[:4]:
            print(f"        · {w}")
    print("=" * 78)
    print(f"  wrote {OUT}")


if __name__ == "__main__":
    sys.exit(main())

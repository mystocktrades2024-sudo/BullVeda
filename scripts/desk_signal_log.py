#!/usr/bin/env python3
"""desk_signal_log.py — forward track record for the Screener Desks.

Three stages (the daily launchd job runs all three in order):
  1. LOG      — snapshot each desk's BUY/SHORT calls for today to data/desk_signal_log.jsonl
                (self-sustained: the desks' OWN verdicts, not the old scanner's).
  2. RESOLVE  — for entries old enough (≥HOLD trading days), score the forward outcome
                from cached OHLCV parquets (0 EODHD): stop hit = −1R, target hit = +Rtgt,
                else exit at HOLD-day close. Writes result + r_multiple back into the log.
  3. AGGREGATE— roll resolved entries into a LIVE per-desk track record (Wilson WR/PF/E[R])
                → cache/desk_track_record.json, which the desk tab surfaces alongside the
                historical backtest edge.

Usage: python3 scripts/desk_signal_log.py            # log + resolve + aggregate
       python3 scripts/desk_signal_log.py --resolve  # resolve + aggregate only
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(BASE))
import screener_desks as sd  # noqa: E402

LOG = BASE / "data" / "desk_signal_log.jsonl"
OHLCV = BASE / "data" / "ohlcv"
OUT = BASE / "cache" / "desk_track_record.json"

HOLD = 5           # swing forward-outcome window (trading days)
ATR_STOP = 1.25
PF_HAIRCUT = 0.10
WR_HAIRCUT = 0.03


def _n(x, d=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def _read_log():
    if not LOG.exists():
        return []
    out = []
    for line in LOG.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def _write_log(entries):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text("\n".join(json.dumps(e) for e in entries) + "\n")


# ── 1. LOG ────────────────────────────────────────────────────────────────
def log_today():
    payload = sd.build_from_disk()
    date = payload.get("generated_at") or ""
    date = str(date)[:10]  # YYYY-MM-DD
    if not date:
        print("no scan date — skip log")
        return 0
    existing = {(e["date"], e["horizon"], e["desk"], e["ticker"]) for e in _read_log()}
    new = []
    for hz, hzobj in (payload.get("horizons") or {}).items():
        if hz != "swing":
            continue  # forward window is 5d — track the swing horizon
        for desk, bk in (hzobj.get("books") or {}).items():
            for r in bk.get("rows") or []:
                if r.get("_dv") not in ("BUY", "SHORT"):
                    continue
                key = (date, hz, desk, r.get("t"))
                if key in existing or not r.get("t"):
                    continue
                t = r.get("_tkt") or {}
                entry = _n(r.get("price"))
                stop = _n(r.get("stop"))
                atrp = _n(r.get("atr"))
                if stop <= 0 and entry > 0 and atrp > 0:  # ATR fallback stop
                    stop = round(entry * (1 - ATR_STOP * atrp / 100), 4)
                new.append({
                    "date": date, "horizon": hz, "desk": desk, "ticker": r.get("t"),
                    "dir": "short" if r.get("_dv") == "SHORT" else "long",
                    "verdict": r.get("_dv"), "entry": entry, "stop": stop,
                    "t1": _n(r.get("t1")) or None, "atr_pct": atrp,
                    "ev": t.get("ev"), "size": t.get("size"), "p": t.get("p"),
                    "sector": r.get("sector"), "regime": (payload.get("regime") or {}).get("regime4"),
                    "logged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "resolved": False,
                })
    if new:
        with LOG.open("a") as f:
            for e in new:
                f.write(json.dumps(e) + "\n")
    print(f"logged {len(new)} new desk signals for {date}")
    return len(new)


# ── 2. RESOLVE ────────────────────────────────────────────────────────────
_PARQUET_CACHE = {}


def _bars(ticker):
    if ticker in _PARQUET_CACHE:
        return _PARQUET_CACHE[ticker]
    p = OHLCV / f"{ticker}.parquet"
    df = None
    if p.exists():
        try:
            df = pd.read_parquet(p)
            df = df[["Open", "High", "Low", "Close"]].copy()
            df.index = pd.to_datetime(df.index)
        except Exception:
            df = None
    _PARQUET_CACHE[ticker] = df
    return df


def _resolve_one(e):
    df = _bars(e["ticker"])
    if df is None:
        return None
    entry = _n(e.get("entry"))
    stop = _n(e.get("stop"))
    if entry <= 0 or stop <= 0:
        return None
    d0 = pd.to_datetime(e["date"])
    fwd = df[df.index > d0]                 # bars strictly AFTER the signal day
    if len(fwd) < HOLD:
        return None                         # not matured yet
    win = fwd.iloc[:HOLD]
    short = e.get("dir") == "short"
    stop_dist = abs(entry - stop) / entry * 100
    if stop_dist <= 0:
        return None
    t1 = _n(e.get("t1"))
    result = None
    r_mult = None
    if short:
        if (win["High"] >= stop).any():
            result, r_mult = "STOPPED", -1.0
        elif t1 and (win["Low"] <= t1).any():
            result, r_mult = "TARGET_HIT", round(abs(entry - t1) / entry * 100 / stop_dist, 2)
        else:
            ret = (entry - win["Close"].iloc[-1]) / entry * 100
            result, r_mult = ("WIN_EXPIRED" if ret > 0 else "LOSS_EXPIRED"), round(ret / stop_dist, 2)
    else:
        if (win["Low"] <= stop).any():
            result, r_mult = "STOPPED", -1.0
        elif t1 and (win["High"] >= t1).any():
            result, r_mult = "TARGET_HIT", round(abs(t1 - entry) / entry * 100 / stop_dist, 2)
        else:
            ret = (win["Close"].iloc[-1] - entry) / entry * 100
            result, r_mult = ("WIN_EXPIRED" if ret > 0 else "LOSS_EXPIRED"), round(ret / stop_dist, 2)
    return {"result": result, "r_multiple": r_mult,
            "resolved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "resolved": True}


def resolve():
    entries = _read_log()
    n = 0
    for e in entries:
        if e.get("resolved"):
            continue
        r = _resolve_one(e)
        if r:
            e.update(r)
            n += 1
    if n:
        _write_log(entries)
    print(f"resolved {n} matured desk signals")
    return n


# ── 3. AGGREGATE ──────────────────────────────────────────────────────────
def _wilson_lb(w, n, z=1.96):
    if n == 0:
        return 0.0
    p = w / n
    return max(0.0, (p + z * z / (2 * n) - z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)) / (1 + z * z / n))


def aggregate():
    entries = [e for e in _read_log() if e.get("resolved") and e.get("r_multiple") is not None]
    by = {}
    for e in entries:
        by.setdefault(e["desk"], []).append(_n(e["r_multiple"]))
    desks = {}
    for d, rms in by.items():
        nn = len(rms)
        w = sum(1 for r in rms if r > 0)
        pos = sum(r for r in rms if r > 0)
        neg = abs(sum(r for r in rms if r < 0))
        pf = pos / neg if neg > 0 else (pos if pos > 0 else 0.0)
        desks[d] = {
            "n": nn, "wr": round(w / nn, 4) if nn else 0.0,
            "wilson_lb": round(_wilson_lb(w, nn), 4),
            "pf": round(pf, 3), "pf_haircut": round(max(0.0, pf - PF_HAIRCUT), 3),
            "expectancy_R": round(sum(rms) / nn, 3) if nn else 0.0,
            "source": "live forward track record",
        }
    out = {"_meta": {"n_resolved": len(entries), "n_open": len(_read_log()) - len(entries),
                     "hold_days": HOLD, "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                     "eodhd_calls": 0}, "desks": desks}
    OUT.write_text(json.dumps(out, indent=2))
    print(f"aggregated live track record: {len(entries)} resolved across {len(desks)} desks -> {OUT.name}")
    for d in ("pb", "mr", "mom", "bo", "cat", "qf", "val", "qual", "smart", "def", "short"):
        s = desks.get(d)
        if s:
            print(f"  {d:5s} n={s['n']:4d}  WR {s['wr']*100:4.1f}%  PF {s['pf']:.2f}->{s['pf_haircut']:.2f}  E[R] {s['expectancy_R']:+.2f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--resolve", action="store_true", help="resolve + aggregate only (skip logging)")
    args = ap.parse_args()
    if not args.resolve:
        log_today()
    resolve()
    aggregate()


if __name__ == "__main__":
    main()

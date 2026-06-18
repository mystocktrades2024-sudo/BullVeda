#!/usr/bin/env python3
"""Build the historical audit ledger.

Walks cache/picks_history.json (every scan run's picks) + augments with
data/signal_log.json (MAE/MFE/status/result), then fetches EODHD price
history for each unique ticker and computes forward returns at D1-D7 +
W1-W8 + M1-M12 horizons, plus MAE/MFE/days-to-T1/days-to-stop/outcome/
realized R-multiple.

Output: cache/audit_ledger.json — flat list of pick records.

Incremental: re-running only fetches price history for new (ticker, date)
pairs or refreshes existing records when more horizons can be filled
(i.e., more time has passed since the pick).

Usage:
  python3 infra/prototype/build_audit_ledger.py             # incremental
  python3 infra/prototype/build_audit_ledger.py --rebuild   # force full rebuild
"""
from __future__ import annotations
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

PICKS_HISTORY = ROOT / "cache/picks_history.json"
SIGNAL_LOG = ROOT / "data/signal_log.json"
OUT_LEDGER = ROOT / "cache/audit_ledger.json"

REBUILD = "--rebuild" in sys.argv

# Horizon definitions in TRADING-DAY offsets
HORIZONS = {}
for k in range(1, 8):   HORIZONS[f"d{k}"] = k                     # D1..D7
for k in range(1, 9):   HORIZONS[f"w{k}"] = k * 5                 # W1..W8 (5 trading days)
for k in range(1, 13):  HORIZONS[f"m{k}"] = k * 21                # M1..M12 (21 trading days)
MAX_HORIZON = max(HORIZONS.values())  # 252 (~M12)


def _load_existing():
    if not OUT_LEDGER.exists() or REBUILD:
        return {}
    try:
        data = json.loads(OUT_LEDGER.read_text())
        return {(r["ticker"], r["pick_date"]): r for r in data.get("records", [])}
    except Exception as e:
        print(f"warning: existing ledger unreadable ({e}) — starting fresh")
        return {}


def _merge_pick_sources():
    """Merge picks_history.runs + signal_log → dict[(ticker, date) → base record]."""
    out = {}
    if PICKS_HISTORY.exists():
        ph = json.loads(PICKS_HISTORY.read_text())
        for run in (ph.get("runs") or []):
            d = run.get("run_date")
            if not d: continue
            for pick in (run.get("picks") or []):
                tkr = pick.get("ticker")
                if not tkr: continue
                key = (tkr, d)
                if key in out: continue
                out[key] = {
                    "ticker": tkr,
                    "pick_date": d,
                    "price_at_pick": pick.get("entry_price"),
                    "verdict": pick.get("verdict"),
                    "direction": pick.get("direction", "long"),
                    "setup": pick.get("setup_type"),
                    "setup_family": pick.get("setup_family"),
                    "conviction_tier": pick.get("conviction_tier"),
                    "entry_quality": pick.get("entry_quality"),
                    "entry_subtype": pick.get("entry_subtype"),
                    "score": pick.get("score"),
                    "stop": pick.get("stop"),
                    "target1": pick.get("target1"),
                    "target2": pick.get("target2"),
                    "rr_ratio": pick.get("rr_ratio") or pick.get("rr"),
                    "regime4": pick.get("regime4"),
                    "sector": pick.get("sector"),
                    "industry": pick.get("industry"),
                    "catalyst_tier": pick.get("catalyst_tier"),
                    "rs_rank": pick.get("rs_rank"),
                    "rvol": pick.get("rvol"),
                    "rsi": pick.get("rsi"),
                    "weekly_bull": pick.get("weekly_bull"),
                    "mode": _infer_mode(pick.get("setup_family")),
                    # forward returns + outcomes filled later
                    "mae_pct": None,
                    "mfe_pct": None,
                    "days_to_t1": None,
                    "days_to_stop": None,
                    "outcome": None,
                    "realized_r": None,
                    "_source": "picks_history",
                }
                for h in HORIZONS:
                    out[key][h] = None
        # Also pull matured trades — these already have outcomes
        for tr in (ph.get("trades") or []):
            tkr = tr.get("ticker"); d = tr.get("run_date")
            if not tkr or not d: continue
            key = (tkr, d)
            if key not in out: continue
            out[key]["mae_pct"] = out[key].get("mae_pct")  # keep as-is, recompute later
            out[key]["matured"] = True
            out[key]["mature_pct_chg"] = tr.get("pct_chg")
            out[key]["mature_hold_days"] = tr.get("hold_days")
            out[key]["matured_win"] = tr.get("win")

    # Augment with signal_log records (more outcome data)
    if SIGNAL_LOG.exists():
        sl = json.loads(SIGNAL_LOG.read_text())
        for s in (sl or []):
            tkr = s.get("ticker"); d = s.get("date")
            if not tkr or not d: continue
            key = (tkr, d)
            rec = out.get(key)
            if not rec:
                # signal_log has it but picks_history doesn't — create a record
                rec = {
                    "ticker": tkr,
                    "pick_date": d,
                    "price_at_pick": s.get("entry_price"),
                    "verdict": _verdict_from_status(s),
                    "direction": s.get("direction", "long"),
                    "setup": s.get("strategy"),
                    "setup_family": s.get("strategy"),
                    "score": s.get("score"),
                    "stop": s.get("stop"),
                    "target1": s.get("target1"),
                    "target2": s.get("target2"),
                    "rr_ratio": s.get("rr"),
                    "rs_rank": s.get("rs_rank"),
                    # signal_log DOES carry these — map them (was dropped, so every
                    # swing/signal_log row logged tier/EQ/Cat as null). NB the field is
                    # `conviction_label` in signal_log, not `conviction_tier`.
                    "conviction_tier": s.get("conviction_label"),
                    "entry_quality": s.get("entry_quality"),
                    "catalyst_tier": s.get("catalyst_tier"),
                    "regime4": s.get("regime4"),
                    "rvol": s.get("rvol"),
                    "rsi": s.get("rsi"),
                    "weekly_bull": s.get("weekly_bull"),
                    "mode": "swing",  # signal_log defaults to swing
                    "mae_pct": None,
                    "mfe_pct": None,
                    "days_to_t1": None,
                    "days_to_stop": None,
                    "outcome": None,
                    "realized_r": None,
                    "_source": "signal_log",
                }
                for h in HORIZONS:
                    rec[h] = None
                out[key] = rec
            # Augment / overwrite with signal_log fields when present
            if s.get("mae_pct") is not None: rec["mae_pct"] = s.get("mae_pct")
            if s.get("mfe_pct") is not None: rec["mfe_pct"] = s.get("mfe_pct")
            if s.get("status"):              rec["signal_status"] = s.get("status")
            if s.get("result"):              rec["signal_result"] = s.get("result")
            if s.get("actual_pnl_pct") is not None: rec["signal_pnl_pct"] = s.get("actual_pnl_pct")
            # stars
            if s.get("stars") is not None:   rec["stars"] = s.get("stars")
            # Backfill tier/EQ/Cat from signal_log when the existing record (e.g. a
            # picks_history row) is missing them — signal_log is the richer source for
            # swing names. conviction_label → conviction_tier (name differs).
            if rec.get("conviction_tier") is None and s.get("conviction_label"):
                rec["conviction_tier"] = s.get("conviction_label")
            if rec.get("entry_quality") is None and s.get("entry_quality"):
                rec["entry_quality"] = s.get("entry_quality")
            if rec.get("catalyst_tier") is None and s.get("catalyst_tier") is not None:
                rec["catalyst_tier"] = s.get("catalyst_tier")
    return out


def _verdict_from_status(s):
    """Map signal_log status to a verdict-like label."""
    st = (s.get("status") or "").upper()
    r = (s.get("result") or "").upper()
    if "TARGET_HIT" in r: return "BUY"
    if "WIN" in r: return "BUY"
    if "STOPPED" in r or "LOSS" in r: return "BUY"  # was a BUY signal that lost
    return "BUY"


def _infer_mode(setup_family):
    """Map setup_family to canonical mode (Swing/Position/Invest)."""
    if not setup_family: return "swing"
    sf = setup_family.lower()
    if "impulse" in sf or "scalp" in sf or "intraday" in sf: return "swing"
    if "vcp" in sf or "52w" in sf or "breakout" in sf or "trend continuation" in sf: return "position"
    if "long_term" in sf or "invest" in sf or "fundamental" in sf: return "invest"
    return "position"


def _fetch_history(ticker, from_date, to_date):
    """Wrapper around eodhd_client.eod with simple error handling."""
    try:
        import eodhd_client
        rows = eodhd_client.eod(ticker, from_date=from_date, to_date=to_date)
        if not rows: return None
        # Normalize: list of {date, open, high, low, close, adjusted_close, volume}
        return rows
    except Exception as e:
        print(f"  fetch {ticker} {from_date}→{to_date}: {e}")
        return None


def _compute_returns_for_ticker(ticker, ticker_records, today):
    """Fetch price history for one ticker and fill forward returns + outcomes."""
    # Date range needed: earliest pick − 5 days → latest pick + 252 trading days (~1 year)
    pick_dates = [r["pick_date"] for r in ticker_records]
    min_pd = min(pick_dates)
    max_pd = max(pick_dates)
    try:
        from_d = (datetime.strptime(min_pd, "%Y-%m-%d") - timedelta(days=10)).strftime("%Y-%m-%d")
        to_d_dt = datetime.strptime(max_pd, "%Y-%m-%d") + timedelta(days=400)
        # Cap at today — we don't have future prices
        to_d_dt = min(to_d_dt, datetime.strptime(today, "%Y-%m-%d"))
        to_d = to_d_dt.strftime("%Y-%m-%d")
    except Exception:
        return

    hist = _fetch_history(ticker, from_d, to_d)
    if not hist:
        return

    # Build date → close map (sorted)
    prices = {}
    for row in hist:
        d = row.get("date")
        close = row.get("close") or row.get("adjusted_close")
        if d and close is not None and close > 0:
            prices[d] = float(close)
    if not prices:
        return
    sorted_dates = sorted(prices.keys())
    date_idx = {d: i for i, d in enumerate(sorted_dates)}

    for rec in ticker_records:
        pd = rec["pick_date"]
        # 2026-05-19 · Weekend pick_dates (Sat/Sun) come from manual scans
        # run on weekends. Snap them forward to the next trading day for
        # display + math consistency. This stops the audit ledger from
        # showing "2026-05-17 Sun" as a pick_date when EODHD has no Sunday
        # close — the actual entry is the Monday following.
        if pd not in date_idx:
            forward = [d for d in sorted_dates if d >= pd]
            if not forward: continue
            snapped = forward[0]
            if snapped != pd:
                rec["pick_date_orig"] = pd     # preserve original for audit
                rec["pick_date"] = snapped     # display + math use trading day
            pd = snapped
        i = date_idx[pd]
        anchor = prices[sorted_dates[i]]
        if not anchor or anchor <= 0: continue

        direction = (rec.get("direction") or "long").lower()
        sign = 1 if direction == "long" else -1

        # 2026-05-18 · INTRADAY D0 — same-day return from entry price to that
        # day's close. For TODAY's picks where price_at_pick was captured
        # intraday (typically at open or scan time), this is the actionable
        # "how did the pick perform today?" number. Without this, today's
        # picks all show "—" until tomorrow's close, even though the close
        # of the same day IS available and meaningful.
        entry_price = rec.get("price_at_pick")
        if entry_price and entry_price > 0 and anchor and anchor > 0:
            d0_ret = sign * (anchor / entry_price - 1) * 100
            # Only stamp if there's a meaningful difference (>= 0.05%) from
            # the close. If price_at_pick == close, this is just 0 noise.
            if abs(d0_ret) >= 0.05:
                rec["d0"] = round(d0_ret, 2)

        # Forward returns at each horizon
        for label, offset in HORIZONS.items():
            tgt_i = i + offset
            if tgt_i >= len(sorted_dates): continue
            p = prices[sorted_dates[tgt_i]]
            if p:
                rec[label] = round(sign * (p / anchor - 1) * 100, 2)

        # MAE / MFE over next ~60 trading days
        mae, mfe = 0.0, 0.0
        for j in range(i + 1, min(i + 60, len(sorted_dates))):
            p = prices[sorted_dates[j]]
            ret = sign * (p / anchor - 1) * 100
            if ret < mae: mae = ret
            if ret > mfe: mfe = ret
        if rec.get("mae_pct") is None: rec["mae_pct"] = round(mae, 2)
        if rec.get("mfe_pct") is None: rec["mfe_pct"] = round(mfe, 2)

        # Walk forward to find days-to-T1 vs days-to-stop, outcome
        stop = rec.get("stop")
        t1 = rec.get("target1")
        days_to_t1 = days_to_stop = None
        for j in range(i + 1, min(i + 60, len(sorted_dates))):
            p = prices[sorted_dates[j]]
            if direction == "long":
                if days_to_t1 is None and t1 and p >= t1: days_to_t1 = j - i
                if days_to_stop is None and stop and p <= stop: days_to_stop = j - i
            else:
                if days_to_t1 is None and t1 and p <= t1: days_to_t1 = j - i
                if days_to_stop is None and stop and p >= stop: days_to_stop = j - i
            if days_to_t1 is not None and days_to_stop is not None: break
        rec["days_to_t1"] = days_to_t1
        rec["days_to_stop"] = days_to_stop
        # Outcome
        if days_to_t1 is not None and (days_to_stop is None or days_to_t1 < days_to_stop):
            rec["outcome"] = "WIN_T1"
        elif days_to_stop is not None and (days_to_t1 is None or days_to_stop < days_to_t1):
            rec["outcome"] = "LOSS_STOP"
        elif rec.get("d5") is not None or rec.get("w1") is not None:
            r5 = rec.get("w1") if rec.get("w1") is not None else rec.get("d5")
            if r5 is not None:
                if r5 > 2: rec["outcome"] = "WIN_EXPIRED"
                elif r5 < -2: rec["outcome"] = "LOSS_EXPIRED"
                else: rec["outcome"] = "BREAKEVEN"

        # Realized R-multiple from MFE/MAE + outcome
        if stop and rec.get("price_at_pick") and rec["price_at_pick"] > 0:
            risk = abs(rec["price_at_pick"] - stop)
            if risk > 0:
                ref_pct = None
                if rec.get("outcome") == "WIN_T1" and t1:
                    ref_pct = sign * (t1 / rec["price_at_pick"] - 1) * 100
                elif rec.get("outcome") == "LOSS_STOP":
                    ref_pct = sign * (stop / rec["price_at_pick"] - 1) * 100
                elif rec.get("w4") is not None:
                    ref_pct = rec["w4"]
                elif rec.get("w1") is not None:
                    ref_pct = rec["w1"]
                if ref_pct is not None:
                    final_p = rec["price_at_pick"] * (1 + ref_pct / 100)
                    gain = sign * (final_p - rec["price_at_pick"])
                    rec["realized_r"] = round(gain / risk, 2)


def main():
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"build_audit_ledger · today={today} · rebuild={REBUILD}")
    existing = _load_existing()
    print(f"  existing ledger: {len(existing)} records")

    merged = _merge_pick_sources()
    print(f"  merged source: {len(merged)} unique (ticker, date) keys")

    # Merge in existing values for non-changing fields, but RE-COMPUTE forward returns
    # for records whose pick_date is less than MAX_HORIZON days old (more time = more horizons).
    today_dt = datetime.strptime(today, "%Y-%m-%d")
    fresh_count = 0
    for key, base in merged.items():
        if key in existing:
            # Refresh ONLY forward returns / MAE/MFE if the pick is recent enough that
            # new horizons could be filled
            pd_dt = datetime.strptime(base["pick_date"], "%Y-%m-%d")
            age_days = (today_dt - pd_dt).days
            if age_days > MAX_HORIZON + 30 and not REBUILD:
                # Old record — keep existing forward returns, just sync metadata
                old = existing[key]
                for k in HORIZONS:
                    if old.get(k) is not None: base[k] = old[k]
                for k in ("mae_pct", "mfe_pct", "days_to_t1", "days_to_stop", "outcome", "realized_r"):
                    if old.get(k) is not None: base[k] = old[k]
                continue
        fresh_count += 1
    print(f"  fresh records to compute: {fresh_count}")

    # Group by ticker for batched EODHD calls
    by_ticker = {}
    for rec in merged.values():
        by_ticker.setdefault(rec["ticker"], []).append(rec)
    print(f"  unique tickers: {len(by_ticker)}")

    t0 = time.time()
    done = 0
    for ticker, records in sorted(by_ticker.items()):
        try:
            _compute_returns_for_ticker(ticker, records, today)
        except Exception as e:
            print(f"  {ticker} failed: {e}")
        done += 1
        if done % 25 == 0:
            print(f"    progress: {done}/{len(by_ticker)} tickers · elapsed {time.time()-t0:.0f}s")
        time.sleep(0.03)  # gentle pacing for EODHD
    elapsed = time.time() - t0
    print(f"  ✓ price-history pass complete · {elapsed:.0f}s")

    # Output sorted by pick_date desc, then ticker
    records_out = sorted(merged.values(), key=lambda r: (r["pick_date"], r["ticker"]), reverse=True)
    payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "n_records": len(records_out),
        "horizons": {
            "trading_days": list(HORIZONS.keys()),
            "definition": "D=1 trading day, W=5 trading days, M=21 trading days, close-to-close return.",
        },
        "records": records_out,
    }
    OUT_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    OUT_LEDGER.write_text(json.dumps(payload, default=str))
    print(f"  wrote {OUT_LEDGER} · {OUT_LEDGER.stat().st_size:,} bytes · {len(records_out)} records")

    # Mirror to infra/prototype/ so /v2/audit_ledger.json serves it via FastAPI
    served = ROOT / "infra/prototype/audit_ledger.json"
    served.write_text(json.dumps(payload, default=str))
    print(f"  mirrored to {served}")


if __name__ == "__main__":
    main()

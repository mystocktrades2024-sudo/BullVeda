#!/usr/bin/env python3
"""SMC scanner — server-side Smart Money Concepts confluence across the universe.

Runs smc_engine.detect_smc_zones on each ticker's CACHED daily bars (reuses the
scan's warm OHLCV cache → 0 EODHD network in normal operation), scores a bullish
SMC confluence, and writes cache/smc_scan.json for the Slack digest + dashboard.

Confluence (long bias):
  + nearest LIVE bull order block near price (the entry zone) — closer = stronger
  + recent BoS-up (continuation) / CHoCH-up (reversal)
  + recent SSL sweep (stop-run below → liquidity grab, bullish)
  + multi-TF daily/weekly bullish structure (HH/HL)
  + live bull OB / bullish FVG count

Cadence: once/day after the morning scan — SMC is computed from DAILY bars, so it
is daily-stable; intraday only price-vs-zone moves (handled by the live layer).
Cost: pure CPU on cached bars, ~5-10s for ~600 tickers, ZERO EODHD in steady state.
"""
from __future__ import annotations
import json
import sys
import datetime
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))
OUT = BASE / "cache" / "smc_scan.json"
TOP_N_UNIVERSE = 600   # top-ranked names by scan score (bounds runtime)
MAX_OUT = 40


def _universe() -> list[str]:
    last = BASE / "cache" / "last_bundle.json"
    if last.exists():
        try:
            b = json.loads(last.read_text())
            rows = sorted((b.get("all_scored") or []), key=lambda r: -(r.get("score") or 0))
            tks = [r.get("ticker") for r in rows if r.get("ticker")]
            if tks:
                return tks[:TOP_N_UNIVERSE]
        except Exception:
            pass
    tj = BASE / "infra" / "prototype" / "tickers.json"
    if tj.exists():
        try:
            d = json.loads(tj.read_text())
            if isinstance(d, dict):
                return sorted(d.keys())[:TOP_N_UNIVERSE]
        except Exception:
            pass
    return []


def _last_close(df) -> float | None:
    for col in ("Close", "close", "Adj Close"):
        if col in df:
            try:
                return float(df[col].iloc[-1])
            except Exception:
                continue
    return None


def _bullish_mtf(mtf: dict) -> int:
    s = 0
    for tf in ("weekly", "daily"):
        v = str(mtf.get(tf, "")).upper()
        if any(k in v for k in ("HH", "HL", "UP", "BULL")):
            s += 1
    return s


def _score(smc: dict) -> tuple[float, list[str]]:
    obs = smc.get("order_blocks") or []
    fvgs = smc.get("fvgs") or []
    events = smc.get("structure_events") or []
    nearest = smc.get("nearest_live_ob")
    mtf = smc.get("multi_tf") or {}
    score = 0.0
    factors: list[str] = []
    # nearest LIVE bull OB near price (the entry-timing read)
    if nearest and nearest.get("kind") == "bull_ob":
        d = abs(nearest.get("dist_from_price_pct") or 99)
        if d <= 5:
            score += max(0.0, 30 - d * 4)      # 0% → 30pts, 5% → 10pts
            factors.append(f"live bull OB {d:.1f}% away")
    # recent structure events (last 4)
    for e in (events[-4:] if events else []):
        k = e.get("kind", "")
        if k == "bos_up":
            score += 12; factors.append("BoS↑")
        elif k == "choch_up":
            score += 14; factors.append("CHoCH↑")
        elif k == "ssl_sweep":
            score += 10; factors.append("SSL sweep")
    # live bull OBs + bullish FVGs
    n_bull_ob = sum(1 for z in obs if z.get("kind") == "bull_ob" and z.get("is_live"))
    n_up_fvg = sum(1 for z in fvgs if z.get("kind") == "fvg_up" and z.get("is_live"))
    score += min(10, n_bull_ob * 3) + min(6, n_up_fvg * 2)
    if n_bull_ob:
        factors.append(f"{n_bull_ob} live bull OB")
    # multi-TF bullish structure
    mt = _bullish_mtf(mtf)
    score += mt * 6
    if mt:
        factors.append(f"MTF bull×{mt}")
    # dedup factors, preserve order (a ticker can have repeat BoS↑/CHoCH↑ events)
    seen, uniq = set(), []
    for f in factors:
        if f not in seen:
            seen.add(f); uniq.append(f)
    return round(score, 1), uniq[:5]


def main() -> int:
    from data_fetcher import fetch_ohlcv_with_failover
    import smc_engine

    uni = _universe()
    if not uni:
        print("[smc_scan] empty universe", file=sys.stderr)
        return 1
    print(f"[smc_scan] scanning {len(uni)} tickers (cached bars, 0 EODHD steady-state)…", file=sys.stderr)

    out = []
    for i, tk in enumerate(uni):
        if i % 150 == 0 and i:
            print(f"  [smc_scan] {i}/{len(uni)} · candidates={len(out)}", file=sys.stderr)
        try:
            df, _src = fetch_ohlcv_with_failover(tk, days=300)
        except Exception:
            continue
        if df is None or len(df) < 30:
            continue
        try:
            smc = smc_engine.detect_smc_zones(df)
        except Exception:
            continue
        sc, factors = _score(smc)
        if sc <= 0:
            continue
        out.append({
            "ticker": tk,
            "smc_score": sc,
            "price": _last_close(df),
            "factors": factors,
            "nearest_ob": smc.get("nearest_live_ob"),
        })

    out.sort(key=lambda r: -r["smc_score"])
    out = out[:MAX_OUT]
    payload = {
        "_meta": {
            "generated_at": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "n": len(out),
            "universe": len(uni),
            "source": "smc_engine.detect_smc_zones (cached daily bars)",
        },
        "candidates": out,
        "tickers": [r["ticker"] for r in out],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2))
    print(f"[smc_scan] wrote {OUT} · {len(out)} SMC candidates · 0 EODHD")
    return 0


if __name__ == "__main__":
    sys.exit(main())

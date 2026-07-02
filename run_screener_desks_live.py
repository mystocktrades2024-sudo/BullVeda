#!/usr/bin/env python3
"""run_screener_desks_live.py — Schwab live-quote overlay for the Screener Desks tab.

Runs every 5 min via launchd (com.swingtrade.screener-desks-live). Self-gates to
market hours; one Schwab batch quote covers every ticker shown across all desks →
ZERO EODHD quota cost. Writes infra/prototype/screener_desks_live.json, which
/api/screener_desks merges as the live price/zone overlay (its file-mtime is folded
into the endpoint cache key, so a new overlay invalidates the cached books).

Overlay shape:
  {"refreshed_at": "<UTC ISO>", "n": <int>, "quotes": {TICKER: {price, prev_close}}}
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).parent
OUT = BASE / "infra" / "prototype" / "screener_desks_live.json"
OHLCV = BASE / "data" / "ohlcv"


def _intraday_tech(sym, o, h, l, c, v):
    """Recompute RSI/EMA/ADX INTRADAY = cached daily history + today's LIVE bar (from
    the Schwab quote). Zero extra API calls. Returns {rsi,ema8,ema21,ema50,adx} or None."""
    p = OHLCV / f"{sym}.parquet"
    if not p.exists() or c is None or c <= 0:
        return None
    try:
        import pandas as pd
        import numpy as np
        df = pd.read_parquet(p)[["Open", "High", "Low", "Close"]].copy()
        df.index = pd.to_datetime(df.index)
        today = pd.Timestamp(datetime.now().date())
        df = df[df.index < today]                       # drop any stale today row
        live = pd.DataFrame([{"Open": o or c, "High": max(h or c, c), "Low": min(l or c, c), "Close": c}],
                            index=[today])
        df = pd.concat([df, live])
        if len(df) < 60:
            return None
        cl, hi, lo = df["Close"], df["High"], df["Low"]
        # RSI(14)
        dl = cl.diff()
        up = dl.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
        dn = (-dl.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
        rsi = 100 - 100 / (1 + up / dn.replace(0, np.nan))
        # ADX(14)
        pc = cl.shift(1)
        tr = pd.concat([(hi - lo), (hi - pc).abs(), (lo - pc).abs()], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1 / 14, adjust=False).mean()
        um, dm = hi.diff(), -lo.diff()
        pdm = ((um > dm) & (um > 0)) * um
        ndm = ((dm > um) & (dm > 0)) * dm
        pdi = 100 * pdm.ewm(alpha=1 / 14, adjust=False).mean() / atr
        ndi = 100 * ndm.ewm(alpha=1 / 14, adjust=False).mean() / atr
        dx = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)
        adx = dx.ewm(alpha=1 / 14, adjust=False).mean()
        def _last(s):
            x = s.iloc[-1]
            return round(float(x), 2) if x == x else None  # NaN guard
        return {"rsi": _last(rsi), "ema8": _last(cl.ewm(span=8, adjust=False).mean()),
                "ema21": _last(cl.ewm(span=21, adjust=False).mean()),
                "ema50": _last(cl.ewm(span=50, adjust=False).mean()), "adx": _last(adx)}
    except Exception:
        return None


def main() -> None:
    try:
        from position_alerts import _is_market_hours, _get_schwab_batch
    except Exception as e:  # pragma: no cover
        print(f"import failed: {e}")
        return

    force = False
    import sys
    if "--force" in sys.argv:  # for manual testing off-hours
        force = True
    if not force and not _is_market_hours():
        print("off-hours — no-op")
        return

    try:
        import screener_desks as sd
        payload = sd.build_from_disk()
        tickers = sd.desk_tickers(payload)
    except Exception as e:
        print(f"desk build failed: {e}")
        return
    if not tickers:
        print("no desk tickers")
        return

    # Richer extraction than _get_schwab_batch: also grab totalVolume so the desks
    # can compute a time-adjusted LIVE RVOL (Breakout/Momentum volume checks).
    quotes = {}
    try:
        import schwab_client as _sc
        raw = _sc.get_quotes_batch(tickers[:500]) or {}
        for sym, blob in raw.items():
            if not isinstance(blob, dict):
                continue
            qb = blob.get("quote") or {}
            last = qb.get("lastPrice")
            if last is None:
                continue
            try:
                c = float(last)
                rec = {"price": round(c, 2)}
                pc = qb.get("closePrice")
                if pc is not None:
                    rec["prev_close"] = round(float(pc), 2)
                tv = qb.get("totalVolume")
                if tv is not None:
                    rec["volume"] = float(tv)
                # today's live bar from the same quote (no extra API call)
                def _f(k):
                    x = qb.get(k)
                    try:
                        return float(x) if x is not None else None
                    except (TypeError, ValueError):
                        return None
                tech = _intraday_tech(sym.upper(), _f("openPrice"), _f("highPrice"), _f("lowPrice"), c, tv)
                if tech:
                    rec.update({k: v for k, v in tech.items() if v is not None})
                quotes[sym.upper()] = rec
            except (TypeError, ValueError):
                continue
    except Exception as e:
        print(f"schwab fetch failed ({e}); falling back to price-only")
        quotes = _get_schwab_batch(tickers) or {}
    if not quotes:
        print("no Schwab quotes (market closed / token?)")
        return

    out = {
        "refreshed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n": len(quotes),
        "quotes": quotes,
    }
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(out))
    tmp.replace(OUT)  # atomic swap
    print(f"wrote {len(quotes)}/{len(tickers)} live quotes → {OUT.name}")


if __name__ == "__main__":
    main()

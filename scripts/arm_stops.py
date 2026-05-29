#!/usr/bin/env python3
"""arm_stops.py — guarantee every open Alpaca paper position has a live
protective stop, regardless of how the entry filled.

WHY THIS EXISTS (2026-05-28):
  The auto-executor submits BRACKET buy orders with TIF=DAY. When the limit
  entry doesn't fill same-session, Alpaca cancels the ENTIRE bracket at the
  close — including the stop-loss + take-profit legs. Positions that filled on
  prior days were left running naked (no protective stop at the broker). Audit
  found all 9 open positions with zero stop legs. CLAUDE.md principle 3 ("risk
  first") and 17 ("hard close-based stops, no emotional override — the system
  does this so the human cannot") demand every position carry a live stop.

WHAT IT DOES:
  1. Pull open positions + open orders from Alpaca paper.
  2. Identify positions WITHOUT a protective sell-stop (long) / buy-stop (short).
  3. For each naked position, submit a standalone GTC stop order at the intended
     stop level from data/portfolio_state.json — clamped so the stop is always
     on the correct side of the current price (Alpaca rejects an immediately-
     triggerable stop). Longs: stop <= last*0.995. Shorts: stop >= last*1.005.
  4. GTC time-in-force so the stop survives overnight (unlike the DAY brackets).

SAFETY:
  - Dry-run by default. Must pass --submit to place real (paper) orders.
  - paper=True is non-negotiable (reuses executor._make_client).
  - Never touches positions that already have a protective stop.

USAGE:
  python3 scripts/arm_stops.py            # dry-run — show what WOULD be armed
  python3 scripts/arm_stops.py --submit   # arm GTC stops on naked positions
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

STATE_PATH = BASE_DIR / "data" / "portfolio_state.json"
LOG_DIR = BASE_DIR / "cache" / "logs"


def _load_intended_stops() -> dict:
    """ticker -> intended stop price from portfolio_state.json (may be synthetic)."""
    if not STATE_PATH.exists():
        return {}
    try:
        ps = json.loads(STATE_PATH.read_text())
    except Exception:
        return {}
    return {p["ticker"]: p.get("stop") for p in ps.get("positions", []) if p.get("ticker")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--submit", action="store_true",
                    help="Place real (paper) GTC stop orders. Default is dry-run.")
    ap.add_argument("--default-stop-pct", type=float, default=0.06,
                    help="Fallback stop distance (fraction) when no intended stop exists. Default 6%%.")
    args = ap.parse_args()
    dry = not args.submit

    from executor import _make_client
    from alpaca.trading.requests import GetOrdersRequest, StopOrderRequest
    from alpaca.trading.enums import QueryOrderStatus, OrderSide, TimeInForce

    client, account = _make_client()
    positions = client.get_all_positions()
    opens = client.get_orders(filter=GetOrdersRequest(status=QueryOrderStatus.OPEN, limit=300))

    # Symbols that already have a protective STOP leg open
    protected = set()
    for o in opens:
        otype = (o.order_type.value if getattr(o, "order_type", None) and hasattr(o.order_type, "value") else "")
        if otype and "stop" in otype.lower():
            protected.add(o.symbol)

    intended = _load_intended_stops()

    mode = "DRY-RUN" if dry else "SUBMIT"
    print(f"=== arm_stops ({mode}) — {len(positions)} positions · {len(protected)} already protected ===")
    print(f"Alpaca paper: equity=${float(account.equity):,.2f}")

    armed = skipped = failed = 0
    for p in positions:
        sym = p.symbol
        qty = abs(int(float(p.qty)))
        last = float(p.current_price)
        is_long = int(float(p.qty)) > 0

        if sym in protected:
            print(f"  SKIP {sym:<6} — already has a protective stop")
            skipped += 1
            continue

        # Intended stop (may be synthetic 3%); fall back to default-stop-pct band.
        want = intended.get(sym)
        if want is None or want <= 0:
            want = round(last * (1 - args.default_stop_pct), 2) if is_long else round(last * (1 + args.default_stop_pct), 2)

        # Clamp so the stop is on the correct side of market (Alpaca rejects
        # an immediately-triggerable stop). Longs: stop below last. Shorts: above.
        if is_long:
            stop_price = min(float(want), round(last * 0.995, 2))
        else:
            stop_price = max(float(want), round(last * 1.005, 2))
        stop_price = round(stop_price, 2)

        side = OrderSide.SELL if is_long else OrderSide.BUY
        clamped = "" if abs(stop_price - float(want)) < 0.005 else f" (clamped from ${float(want):.2f} — already breached)"
        print(f"  ARM  {sym:<6} {qty}x {side.value} STOP @ ${stop_price:.2f} (last ${last:.2f}){clamped}")

        if dry:
            armed += 1
            continue

        try:
            req = StopOrderRequest(
                symbol=sym, qty=qty, side=side,
                time_in_force=TimeInForce.GTC, stop_price=stop_price,
            )
            resp = client.submit_order(req)
            print(f"       -> order_id {resp.id}")
            armed += 1
        except Exception as e:
            print(f"       FAILED: {e}")
            failed += 1

    verb = "would arm" if dry else "armed"
    print(f"\n{mode}: {armed} {verb} · {skipped} already-protected · {failed} failed")
    if dry and armed:
        print("Run with --submit to place the GTC protective stops.")

    # Append to log
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with (LOG_DIR / f"arm_stops_{datetime.now():%Y-%m-%d}.log").open("a") as f:
            f.write(f"{datetime.now().isoformat()} {mode}: {armed} {verb}, {skipped} protected, {failed} failed\n")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())

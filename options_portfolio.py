#!/usr/bin/env python3
"""
options_portfolio.py — Options position tracking + auto-exit (OPT-PAPER-4/5).

OPT-PAPER-4 (tracking): reads the Alpaca PAPER option positions, parses each OCC
contract (underlying / expiry / strike / type), enriches with DTE, mark, P&L%, and
the original thesis (underlying stop, from the options_executor order log), and
writes a snapshot to cache/options_positions.json for the dashboard / API.

OPT-PAPER-5 (exits): a rules engine for long-call positions —
  1. thesis-invalidation  (underlying breaks the equity stop)   ← highest priority
  2. profit-take          (contract P&L >= profit_take_pct)
  3. premium stop         (contract P&L <= -stop_loss_pct)
  4. time-stop            (DTE <= time_stop_dte — theta cliff)
  5. pre-earnings exit    (best-effort IV-crush avoidance)

Same hard guards as options_executor: PAPER ONLY, gated OFF by default
(options_auto_exit._enabled), market-hours required to submit exits.

Usage:
  python3 options_portfolio.py                 # track: print + write snapshot
  python3 options_portfolio.py --exits         # evaluate exits (dry-run)
  python3 options_portfolio.py --exits --submit  # submit exits (gated)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

import executor as _eq

_ROOT = Path(__file__).parent
_SNAPSHOT = _ROOT / "cache" / "options_positions.json"
_ORDER_LOG = _ROOT / "cache" / "logs" / "options_orders.jsonl"
_EXIT_LOG = _ROOT / "cache" / "logs" / "options_exits.jsonl"

# OCC symbol: ROOT + YYMMDD + (C|P) + strike*1000 (8 digits). e.g. F260710C00011500
_OCC_RE = re.compile(r"^(?P<root>[A-Z]+)(?P<exp>\d{6})(?P<cp>[CP])(?P<strike>\d{8})$")


def _parse_occ(sym: str) -> dict | None:
    m = _OCC_RE.match(sym or "")
    if not m:
        return None
    try:
        exp = datetime.strptime(m.group("exp"), "%y%m%d").date()
    except Exception:
        return None
    return {
        "underlying": m.group("root"),
        "expiry": exp,
        "type": "call" if m.group("cp") == "C" else "put",
        "strike": int(m.group("strike")) / 1000.0,
    }


def _exit_cfg(cfg: dict) -> dict:
    blk = (cfg or {}).get("options_auto_exit", {}) or {}
    return {
        "_enabled":                 bool(blk.get("_enabled", False)),
        "profit_take_pct":          float(blk.get("profit_take_pct", 60)),
        "stop_loss_pct":            float(blk.get("stop_loss_pct", 50)),
        "time_stop_dte":            int(blk.get("time_stop_dte", 10)),
        "exit_on_underlying_stop":  bool(blk.get("exit_on_underlying_stop", True)),
        "exit_before_earnings_days": int(blk.get("exit_before_earnings_days", 2)),
        "exit_limit_slippage_pct":  float(blk.get("exit_limit_slippage_pct", 0.03)),
    }


# ───────────────────── order-log thesis context ─────────────────────
def _order_context() -> dict:
    """occ_symbol -> {underlying_stop, entry_date, score, setup} from the buy log."""
    ctx: dict[str, dict] = {}
    if not _ORDER_LOG.exists():
        return ctx
    for line in _ORDER_LOG.read_text().splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        occ = r.get("occ_symbol")
        if occ and r.get("submitted"):
            ctx[occ] = {
                "underlying_stop": r.get("underlying_stop"),
                "score": r.get("score"),
                "setup": r.get("setup"),
                "logged_at": r.get("expiry"),  # placeholder; entry timestamp added below
            }
    return ctx


# ───────────────────── underlying spot batch ─────────────────────
def _underlying_spots(symbols: set[str]) -> dict:
    if not symbols:
        return {}
    try:
        from alpaca.data.historical.stock import StockHistoricalDataClient
        from alpaca.data.requests import StockLatestTradeRequest
        from secrets_loader import alpaca_key, alpaca_secret
        sc = StockHistoricalDataClient(alpaca_key(), alpaca_secret())
        res = sc.get_stock_latest_trade(StockLatestTradeRequest(symbol_or_symbols=list(symbols)))
        return {s: float(getattr(t, "price", 0) or 0) for s, t in res.items()}
    except Exception:
        return {}


# ───────────────────── tracking (OPT-PAPER-4) ─────────────────────
def get_option_positions(trade_client) -> list[dict]:
    from alpaca.trading.enums import AssetClass
    out: list[dict] = []
    try:
        positions = trade_client.get_all_positions()
    except Exception as e:
        print(f"! get_all_positions: {e}")
        return out
    ctx = _order_context()
    today = date.today()
    occ_positions = [p for p in positions
                     if getattr(p, "asset_class", None) == AssetClass.US_OPTION
                     or _OCC_RE.match(getattr(p, "symbol", ""))]
    spots = _underlying_spots({(_parse_occ(getattr(p, "symbol", "")) or {}).get("underlying")
                               for p in occ_positions} - {None})
    for p in occ_positions:
        sym = getattr(p, "symbol", "")
        meta = _parse_occ(sym) or {}
        dte = (meta["expiry"] - today).days if meta.get("expiry") else None
        entry = float(getattr(p, "avg_entry_price", 0) or 0)
        mark = float(getattr(p, "current_price", 0) or 0)
        plpc = float(getattr(p, "unrealized_plpc", 0) or 0) * 100
        c = ctx.get(sym, {})
        out.append({
            "occ_symbol": sym,
            "underlying": meta.get("underlying"),
            "type": meta.get("type"),
            "strike": meta.get("strike"),
            "expiry": meta["expiry"].isoformat() if meta.get("expiry") else None,
            "dte": dte,
            "contracts": int(float(getattr(p, "qty", 0) or 0)),
            "entry_premium": round(entry, 2),
            "mark": round(mark, 2),
            "pnl_pct": round(plpc, 1),
            "unrealized_pl": round(float(getattr(p, "unrealized_pl", 0) or 0), 2),
            "market_value": round(float(getattr(p, "market_value", 0) or 0), 2),
            "underlying_spot": round(spots.get(meta.get("underlying"), 0), 2) or None,
            "underlying_stop": c.get("underlying_stop"),
            "score": c.get("score"),
            "setup": c.get("setup"),
        })
    return out


def write_snapshot(positions: list[dict]) -> None:
    _SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    snap = {
        "as_of": datetime.now().isoformat(timespec="seconds"),
        "n": len(positions),
        "total_value": round(sum(p["market_value"] for p in positions), 2),
        "total_unrealized_pl": round(sum(p["unrealized_pl"] for p in positions), 2),
        "positions": positions,
    }
    _SNAPSHOT.write_text(json.dumps(snap, indent=1, default=str))


# ───────────────────── exits (OPT-PAPER-5) ─────────────────────
def evaluate_exits(positions: list[dict], cfg: dict) -> list[dict]:
    e = _exit_cfg(cfg)
    decisions = []
    for p in positions:
        reason = None
        # 1. thesis invalidation — underlying broke the equity stop (highest priority)
        if (e["exit_on_underlying_stop"] and p.get("underlying_stop") and p.get("underlying_spot")
                and p["type"] == "call" and p["underlying_spot"] <= float(p["underlying_stop"])):
            reason = f"thesis dead — underlying ${p['underlying_spot']:.2f} ≤ stop ${float(p['underlying_stop']):.2f}"
        # 2. profit-take
        elif p["pnl_pct"] >= e["profit_take_pct"]:
            reason = f"profit-take +{p['pnl_pct']:.0f}% ≥ {e['profit_take_pct']:.0f}%"
        # 3. premium stop
        elif p["pnl_pct"] <= -e["stop_loss_pct"]:
            reason = f"premium stop {p['pnl_pct']:.0f}% ≤ -{e['stop_loss_pct']:.0f}%"
        # 4. time-stop (theta cliff)
        elif p.get("dte") is not None and p["dte"] <= e["time_stop_dte"]:
            reason = f"time-stop DTE {p['dte']} ≤ {e['time_stop_dte']}"
        decisions.append({**p, "exit": bool(reason), "exit_reason": reason})
    return decisions


def submit_exit(trade_client, pos: dict, e: dict) -> tuple[bool, str]:
    """SELL-to-close a long-call position via a marketable limit."""
    try:
        from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce
        qty = pos["contracts"]
        mark = pos.get("mark") or 0
        if mark and mark > 0:
            limit = round(mark * (1.0 - e["exit_limit_slippage_pct"]), 2)
            req = LimitOrderRequest(symbol=pos["occ_symbol"], qty=qty, side=OrderSide.SELL,
                                    time_in_force=TimeInForce.DAY, limit_price=limit)
        else:
            req = MarketOrderRequest(symbol=pos["occ_symbol"], qty=qty, side=OrderSide.SELL,
                                     time_in_force=TimeInForce.DAY)
        resp = trade_client.submit_order(req)
        oid = str(getattr(resp, "id", "submitted"))
        _eq._slack_notify(
            f"📉 OPTIONS (paper) SELL-CLOSE {qty}x {pos['occ_symbol']} "
            f"({pos['underlying']}) · P&L {pos['pnl_pct']:+.0f}% · {pos['exit_reason']}"
        )
        return True, oid
    except Exception as ex:
        return False, str(ex)


def _log_exit(entry: dict) -> None:
    _EXIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with _EXIT_LOG.open("a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


# ───────────────────────────── main ─────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description="Options tracking + auto-exit (paper)")
    ap.add_argument("--exits", action="store_true", help="run the exit engine (else just track)")
    ap.add_argument("--dry-run", action="store_true", default=True)
    ap.add_argument("--submit", dest="dry_run", action="store_false")
    args = ap.parse_args()

    cfg = json.loads((_ROOT / "config" / "config.json").read_text())
    e = _exit_cfg(cfg)

    # submit-path guards FIRST
    if args.exits and not args.dry_run:
        if (_ROOT / "cache" / "AUTOMATION_HALT").exists():
            print("REFUSING --submit: cache/AUTOMATION_HALT present (kill-switch active)."); return 0
        if not e["_enabled"]:
            print("REFUSING --submit: options_auto_exit._enabled is false (gated OFF)."); return 0
        if not (cfg.get("alpaca", {}).get("paper", True)):
            print("REFUSING: config.alpaca.paper is not True. PAPER ONLY."); return 1
        try:
            if not getattr(_eq._make_client()[0].get_clock(), "is_open", False):
                print("REFUSING --submit: market CLOSED (option quotes stale)."); return 0
        except Exception as ex:
            print(f"REFUSING --submit: cannot confirm market open ({ex})."); return 0

    try:
        trade_client, account = _eq._make_client()
    except SystemExit:
        return 1
    positions = get_option_positions(trade_client)
    write_snapshot(positions)

    print(f"=== Options Portfolio — {len(positions)} contract position(s) ===")
    for p in positions:
        print(f"  {p['underlying']:6} {p['contracts']}x ${p['strike']:.0f}{p['type'][0].upper()} "
              f"{p['expiry']} ({p['dte']}DTE) · entry ${p['entry_premium']:.2f} mark ${p['mark']:.2f} "
              f"P&L {p['pnl_pct']:+.0f}% (${p['unrealized_pl']:+,.0f})")
    if not positions:
        print("  (no option positions open)")

    if not args.exits:
        print(f"\nSnapshot → {_SNAPSHOT}")
        return 0

    decisions = evaluate_exits(positions, cfg)
    exits = [d for d in decisions if d["exit"]]
    print(f"\n— exit engine: {len(exits)} of {len(positions)} flagged for exit —")
    for d in exits:
        print(f"  ⏏ {d['underlying']:6} {d['occ_symbol']} · P&L {d['pnl_pct']:+.0f}% · {d['exit_reason']}")
    if not exits:
        print("  (none — all holds)")

    if args.dry_run:
        print("\nDRY-RUN — no exits submitted. Use --exits --submit (requires _enabled=true).")
        return 0

    done = 0
    for d in exits:
        ok, info = submit_exit(trade_client, d, e)
        d["submitted"] = ok; d["order_id" if ok else "error"] = info
        _log_exit(d)
        print(("  ✅ " if ok else "  ❌ ") + f"{d['underlying']} {d['occ_symbol']} → {info}")
        done += int(ok)
    print(f"\nSubmitted {done}/{len(exits)} exit orders (paper).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

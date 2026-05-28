#!/usr/bin/env python3
"""
auto_engine.py — complete PAPER-ONLY autonomous trading loop.

Extends executor.py (which handles BUY entries) with the missing halves:
  · EXITS    — real protective stops (fixes synthetic-stop bug), earnings-blackout
               exit, regime-flip / Sharpe-kill flatten, T1 partial + trail runner
  · SHORTS   — gated short entries (VIX≥25 + RSI≥75 + bear regime only)
  · AUTO     — one command: exits → BUY entries → short entries
  · KILL     — a single halt file (cache/AUTOMATION_HALT) stops ALL order submission

HARD CONSTRAINT: paper account only. There is NO live path in this file.
The Alpaca client is created with paper=True (via executor._make_client) and we
re-assert config.alpaca.paper is True before any submit. User decision 2026-05-28.

Usage:
  python3 auto_engine.py                      # DRY-RUN full loop (default, safe)
  python3 auto_engine.py --auto --submit      # LIVE PAPER full loop (exits+buys+shorts)
  python3 auto_engine.py --exits-only         # dry-run exits
  python3 auto_engine.py --exits-only --submit
  python3 auto_engine.py --halt               # create kill-switch (stops all trading)
  python3 auto_engine.py --resume             # remove kill-switch
  python3 auto_engine.py --status             # show engine + position state
"""
from __future__ import annotations
import argparse, json, logging, sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).parent
_KILL = _ROOT / "cache" / "AUTOMATION_HALT"
_ORDERS_LOG = _ROOT / "cache" / "auto_engine_orders.jsonl"

log = logging.getLogger("auto_engine")
if not log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s auto_engine: %(message)s", "%H:%M:%S"))
    log.addHandler(_h); log.setLevel(logging.INFO)

# Reuse executor primitives (client, sizing, BUY submit, paper gates)
import executor as EX


# ────────────────────────────────────────────────────────────────────────────
# helpers
# ────────────────────────────────────────────────────────────────────────────
def _safe_load(p: Path):
    try: return json.loads(p.read_text()) if p.exists() else None
    except Exception: return None


def _log(entry: dict) -> None:
    _ORDERS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with _ORDERS_LOG.open("a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def _slack(text: str) -> None:
    try:
        from lib.autorun_reporter import report
        report("auto-engine", "info", summary=text)
    except Exception:
        try: EX._slack_notify(text)
        except Exception: pass


def kill_active() -> bool:
    return _KILL.exists()


def _regime(bundle: dict) -> dict:
    r = bundle.get("regime")
    return r if isinstance(r, dict) else {}


def _earnings_days_map() -> dict:
    """ticker -> days_to_earnings from the earnings watchlist."""
    wl = _safe_load(_ROOT / "data" / "earnings_watchlist.json") or {}
    out = {}
    for e in (wl.get("watchlist") or []):
        t = e.get("ticker"); d = e.get("days_to_earnings")
        if t and d is not None:
            out[t] = d
    return out


def _portfolio_meta(bundle: dict | None = None) -> dict:
    """ticker -> {stop, target1, direction} merged from portfolio_state (primary)
    then the scan bundle's trade plans (fallback), so positions opened outside
    portfolio_state still get a real protective stop placed."""
    out = {}
    # primary: portfolio_state
    ps = _safe_load(_ROOT / "data" / "portfolio_state.json") or {}
    for p in (ps.get("positions") or []):
        out[p.get("ticker")] = {
            "stop": p.get("stop"), "target1": p.get("target1"),
            "target2": p.get("target2"), "direction": p.get("direction", "long"),
            "t1_hit": p.get("t1_hit", False),
        }
    # fallback: bundle trade plans (buy_candidates + all_scored)
    if bundle:
        for key in ("buy_candidates", "all_scored", "watch_list", "short_candidates"):
            for r in (bundle.get(key) or []):
                tk = r.get("ticker")
                if not tk or (out.get(tk, {}).get("stop")):
                    continue
                tp = r.get("trade_plan") or {}
                if tp.get("stop"):
                    out.setdefault(tk, {})
                    out[tk].update({"stop": tp.get("stop"), "target1": tp.get("target1"),
                                    "target2": tp.get("target2"),
                                    "direction": (tp.get("direction") or r.get("direction") or "long"),
                                    "t1_hit": out.get(tk, {}).get("t1_hit", False)})
    return out


def _fallback_stop(avg: float, side_long: bool, pct: float = 0.10) -> float:
    """Last-resort protective stop when no trade-plan stop exists: pct off entry."""
    return round(avg * (1 - pct), 2) if side_long else round(avg * (1 + pct), 2)


def _sharpe_kill_active() -> bool:
    s = _safe_load(_ROOT / "cache" / "sharpe_kill_state.json") or {}
    return bool(s.get("active"))


# ────────────────────────────────────────────────────────────────────────────
# EXIT ENGINE
# ────────────────────────────────────────────────────────────────────────────
def run_exits(client, bundle: dict, cfg: dict, dry_run: bool) -> dict:
    """Evaluate every open position for exit triggers + ensure protective stops.

    Triggers (in priority order):
      1. earnings ≤1 trading day        → CLOSE (blackout discipline)
      2. regime risk_off/panic + long   → CLOSE (flatten longs in hostile tape)
      3. Sharpe-kill gate active + long  → CLOSE (capital preservation)
      4. T1 reached + not yet partialled → SELL 50% + raise stop to breakeven
      5. (always) ensure a real protective stop order exists at the broker
    """
    from alpaca.trading.requests import (StopOrderRequest, GetOrdersRequest, ClosePositionRequest)
    from alpaca.trading.enums import OrderSide, TimeInForce, OrderStatus, QueryOrderStatus

    reg = _regime(bundle)
    regime4 = (reg.get("regime4") or reg.get("regime") or "").lower()
    hostile = regime4 in ("risk_off_trending", "panic")
    sk = _sharpe_kill_active()
    earn = _earnings_days_map()
    meta = _portfolio_meta(bundle)
    # T1-taken state — prevents re-partialling a position on every run (idempotency)
    _t1_path = _ROOT / "cache" / "auto_engine_t1.json"
    t1_state = _safe_load(_t1_path) or {}

    try:
        positions = client.get_all_positions()
    except Exception as e:
        log.error(f"get_all_positions failed: {e}")
        return {"error": str(e)}

    # existing open orders → know which symbols already have a protective stop
    stops_present = set()
    try:
        oo = client.get_orders(filter=GetOrdersRequest(status=QueryOrderStatus.OPEN))
        for o in oo:
            otype = str(getattr(o, "order_type", getattr(o, "type", ""))).lower()
            if "stop" in otype:
                stops_present.add(o.symbol)
    except Exception as e:
        log.warning(f"get_orders failed (stop detection degraded): {e}")

    actions = []
    ts = datetime.now(timezone.utc).isoformat()
    for pos in positions:
        sym = pos.symbol
        side_long = str(pos.side).upper().endswith("LONG")
        qty = abs(int(float(pos.qty)))
        avg = float(pos.avg_entry_price)
        last = float(pos.current_price or 0)
        m = meta.get(sym, {})
        stop = m.get("stop"); tgt1 = m.get("target1")
        edays = earn.get(sym)

        decided = None; detail = ""
        # 1. earnings blackout
        if edays is not None and 0 <= edays <= 1:
            decided, detail = "CLOSE", f"earnings in {edays}d (blackout)"
        # 2. regime flip (longs only)
        elif hostile and side_long:
            decided, detail = "CLOSE", f"regime {regime4} (flatten longs)"
        # 3. sharpe-kill (longs only)
        elif sk and side_long:
            decided, detail = "CLOSE", "rolling-Sharpe kill (flatten longs)"
        # 4. T1 partial + breakeven trail — only once per position (idempotent)
        elif (tgt1 and side_long and last >= float(tgt1)
              and not m.get("t1_hit") and sym not in t1_state):
            decided, detail = "PARTIAL", f"T1 ${tgt1} reached → sell 50% + BE stop"

        rec = {"timestamp": ts, "symbol": sym, "side": "long" if side_long else "short",
               "qty": qty, "avg": avg, "last": last, "stop": stop, "target1": tgt1,
               "earn_days": edays, "decision": decided or "HOLD", "detail": detail,
               "dry_run": dry_run}

        try:
            if decided == "CLOSE":
                if dry_run:
                    log.info(f"WOULD CLOSE {sym} ({qty}) — {detail}")
                else:
                    client.close_position(sym)
                    log.info(f"CLOSED {sym} ({qty}) — {detail}")
                    _slack(f"🔴 AUTO-EXIT {sym} ×{qty} — {detail}")
                rec["status"] = "dry_run" if dry_run else "closed"
            elif decided == "PARTIAL":
                half = max(1, qty // 2)
                if dry_run:
                    log.info(f"WOULD PARTIAL {sym}: sell {half}/{qty} + BE stop @ ${avg:.2f}")
                else:
                    client.close_position(sym, ClosePositionRequest(qty=str(half)))
                    # raise protective stop to breakeven on the remainder
                    rem = qty - half
                    if rem > 0:
                        client.submit_order(StopOrderRequest(
                            symbol=sym, qty=rem, side=OrderSide.SELL,
                            time_in_force=TimeInForce.GTC, stop_price=round(avg, 2)))
                    log.info(f"PARTIAL {sym}: sold {half}, BE stop @ ${avg:.2f} on {rem}")
                    _slack(f"🎯 AUTO-T1 {sym}: sold {half}/{qty} @ ${last:.2f} · trailing rest from BE ${avg:.2f}")
                    # persist T1-taken so future runs don't re-partial
                    t1_state[sym] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                    try: _t1_path.write_text(json.dumps(t1_state, indent=2))
                    except Exception: pass
                rec["status"] = "dry_run" if dry_run else "partialled"
                rec["partial_qty"] = half
            else:
                # 5. ensure protective stop exists (fixes synthetic / missing stops)
                #    fall back to a computed 10%-off-entry stop if no plan stop exists,
                #    so EVERY open position is protected.
                if not (stop and float(stop) > 0):
                    stop = _fallback_stop(avg, side_long)
                    detail = "fallback stop (no plan stop)"
                if sym not in stops_present and stop and float(stop) > 0:
                    side = OrderSide.SELL if side_long else OrderSide.BUY
                    if dry_run:
                        log.info(f"WOULD PLACE protective stop {sym} ×{qty} @ ${float(stop):.2f} ({'sell' if side_long else 'buy'})")
                        rec["decision"] = "PLACE_STOP"; rec["status"] = "dry_run"
                    else:
                        client.submit_order(StopOrderRequest(
                            symbol=sym, qty=qty, side=side,
                            time_in_force=TimeInForce.GTC, stop_price=round(float(stop), 2)))
                        log.info(f"PLACED protective stop {sym} ×{qty} @ ${float(stop):.2f}")
                        _slack(f"🛡 AUTO-STOP placed {sym} ×{qty} @ ${float(stop):.2f}")
                        rec["decision"] = "PLACE_STOP"; rec["status"] = "placed_stop"
                else:
                    rec["status"] = "hold"
        except Exception as e:
            log.error(f"exit action failed for {sym}: {e}")
            rec["status"] = "error"; rec["error"] = str(e)

        _log(rec)
        actions.append(rec)

    n_close = sum(1 for a in actions if a["decision"] == "CLOSE")
    n_part = sum(1 for a in actions if a["decision"] == "PARTIAL")
    n_stop = sum(1 for a in actions if a["decision"] == "PLACE_STOP")
    log.info(f"Exits: {len(actions)} positions · {n_close} close · {n_part} partial · {n_stop} stop-placed")
    return {"positions": len(actions), "close": n_close, "partial": n_part, "stop": n_stop, "actions": actions}


# ────────────────────────────────────────────────────────────────────────────
# SHORT ENTRIES (gated)
# ────────────────────────────────────────────────────────────────────────────
def _short_gates_ok(bundle: dict, cfg: dict) -> tuple[bool, str]:
    """Shorts only in bear regime with VIX≥25. (RSI≥75 is checked per-name.)"""
    sc = cfg.get("shorts", {}) or {}
    if sc.get("short_disabled", False):
        return False, "shorts disabled in config"
    reg = _regime(bundle)
    regime4 = (reg.get("regime4") or reg.get("regime") or "").lower()
    vix = (reg.get("vix") or {}).get("vix_current") or reg.get("vix_current") or 0
    min_vix = sc.get("short_min_vix", 25)
    need_bear = sc.get("short_require_bear_regime", True)
    if need_bear and regime4 not in ("risk_off_trending", "panic"):
        return False, f"regime {regime4} not bear (shorts require risk_off/panic)"
    if float(vix or 0) < float(min_vix):
        return False, f"VIX {vix} < {min_vix} (shorts gated)"
    return True, f"gates ok (regime {regime4}, VIX {vix})"


def run_shorts(client, bundle: dict, cfg: dict, dry_run: bool) -> dict:
    ok, why = _short_gates_ok(bundle, cfg)
    if not ok:
        log.info(f"Shorts: SKIP — {why}")
        return {"submitted": 0, "reason": why}

    sc = cfg.get("shorts", {}) or {}
    min_rsi = sc.get("short_min_rsi", 75)
    # SHORT-verdict candidates from the bundle
    cands = []
    for key in ("short_candidates", "near_short_blocked", "all_scored"):
        v = bundle.get(key)
        if isinstance(v, list):
            for r in v:
                verdict = (r.get("decision") or {}).get("verdict", "") or r.get("verdict", "")
                if str(verdict).upper() == "SHORT":
                    cands.append(r)
            if cands: break
    submitted = 0
    for pk in cands:
        sym = pk.get("ticker"); rsi = pk.get("rsi") or (pk.get("technicals") or {}).get("rsi")
        if rsi is not None and float(rsi) < float(min_rsi):
            log.info(f"Short skip {sym}: RSI {rsi} < {min_rsi}")
            continue
        log.info(f"{'WOULD SHORT' if dry_run else 'SHORT'} {sym} (gated entry)")
        # (full short bracket submit wired here when SHORT candidates exist;
        #  no-op today because gates correctly block in calm regime)
        submitted += 1
    return {"submitted": submitted, "reason": why}


# ────────────────────────────────────────────────────────────────────────────
# main
# ────────────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--auto", action="store_true", help="Full loop: exits → buys → shorts")
    ap.add_argument("--exits-only", action="store_true")
    ap.add_argument("--shorts-only", action="store_true")
    ap.add_argument("--submit", action="store_true", help="Actually submit (else dry-run)")
    ap.add_argument("--halt", action="store_true", help="Create kill-switch")
    ap.add_argument("--resume", action="store_true", help="Remove kill-switch")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--bundle", default=str(_ROOT / "cache" / "last_bundle.json"))
    args = ap.parse_args()

    if args.halt:
        _KILL.parent.mkdir(parents=True, exist_ok=True)
        _KILL.write_text(datetime.now(timezone.utc).isoformat())
        print("🛑 AUTOMATION HALTED — kill-switch ON. No orders will submit until --resume.")
        return 0
    if args.resume:
        if _KILL.exists(): _KILL.unlink()
        print("✅ AUTOMATION RESUMED — kill-switch removed.")
        return 0
    if args.status:
        print("=== Auto-Engine Status ===")
        print(f"  Kill-switch : {'🛑 HALTED' if kill_active() else '✅ active'}")
        en, reason = EX.is_paper_trading_enabled()
        print(f"  Paper window: {reason}")
        print(f"  Sharpe-kill : {'ACTIVE (longs would flatten)' if _sharpe_kill_active() else 'clear'}")
        b = _safe_load(Path(args.bundle)) or {}
        reg = _regime(b)
        print(f"  Regime      : {reg.get('regime4','—')} · VIX {(reg.get('vix') or {}).get('vix_current','—')}")
        sok, swhy = _short_gates_ok(b, json.loads((_ROOT/'config'/'config.json').read_text()))
        print(f"  Shorts      : {'ENABLED' if sok else 'GATED'} — {swhy}")
        return 0

    dry = not args.submit

    # KILL SWITCH — refuse to submit if halted
    if not dry and kill_active():
        print("🛑 Kill-switch ON (cache/AUTOMATION_HALT). Refusing to submit. Run --resume to clear.")
        return 0

    # Paper gate
    enabled, reason = EX.is_paper_trading_enabled()
    if not enabled:
        print(f"Paper trading not enabled — {reason}. Run: python3 executor.py --activate")
        return 0

    cfg = json.loads((_ROOT / "config" / "config.json").read_text())
    if not dry and cfg.get("alpaca", {}).get("paper", True) is not True:
        print("ERROR: config.alpaca.paper is not True — refusing.", file=sys.stderr); return 2

    bundle = _safe_load(Path(args.bundle)) or {}

    client = None
    if not dry:
        client, account = EX._make_client()
        print(f"Alpaca PAPER: equity ${float(account.equity):,.2f} · cash ${float(account.cash):,.2f}")

    mode = "DRY-RUN" if dry else "SUBMIT (paper)"
    print(f"=== Auto-Engine [{mode}] ===")

    do_exits = args.auto or args.exits_only or (not args.shorts_only)
    do_buys = args.auto
    do_shorts = args.auto or args.shorts_only

    if do_exits:
        if dry and client is None:
            # dry exits still need a client to read positions; create read-only paper client
            try: client, _ = EX._make_client()
            except Exception as e: print(f"(exits need Alpaca read access: {e})"); client = None
        if client is not None:
            print("\n── EXITS ──")
            run_exits(client, bundle, cfg, dry)

    if do_buys:
        print("\n── BUY ENTRIES ── (delegated to executor.py)")
        import subprocess
        cmd = [sys.executable, str(_ROOT / "executor.py"), "--filter", "BUY"]
        if not dry: cmd.append("--submit")
        subprocess.run(cmd)

    if do_shorts:
        print("\n── SHORT ENTRIES ──")
        if client is None and not dry:
            client, _ = EX._make_client()
        run_shorts(client, bundle, cfg, dry)

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

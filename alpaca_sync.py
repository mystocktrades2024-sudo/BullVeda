"""
alpaca_sync.py — reconcile Alpaca paper account → local state stores.

Promoted from server.py:1075 endpoint into a callable module so it can fire:
  - From swing_trade.py Step 0 (every scan reconciles before scoring)
  - From executor.py post-submit (immediate reflection of new fills)
  - From scripts/sync_alpaca.py (ad-hoc CLI / cron)
  - From the existing /api/portfolio/sync_alpaca endpoint (thin wrapper)

v1 (this file) syncs: positions (open + close), filled-order reconciliation
into closed_trades, account equity/cash, equity_curve daily snapshot. Pick
attribution back to original setup × regime is v2 (orders.jsonl walk).

Why separate module: the original server.py endpoint mixed HTTP concerns
with state-sync logic, so other paths (executor, swing_trade) couldn't call
it without imports of FastAPI / urllib boilerplate. This pulls the logic
out clean.

Gaps the module closes (from 2026-05-10 audit):
  - portfolio_state.json showed 0 positions while Alpaca had 14 round-trips
  - SQLite positions / closed_trades / equity_curve all 0-row
  - kelly_size.drawdown_mult (74cb3b208) reads equity_curve — silently 1.0
    until this populates real data
  - tracker.compute_stats_by_setup can't learn from actual paper outcomes
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any

log = logging.getLogger("swingtrade.alpaca_sync")

BASE_DIR = Path(__file__).resolve().parent
STATE_PATH = BASE_DIR / "data" / "portfolio_state.json"

# Rate-limit guard: minimum seconds between syncs (Alpaca paper = 200 req/min)
_LAST_SYNC_TS = 0.0
_MIN_SYNC_INTERVAL_SECONDS = 30


def _get_client():
    """Return an alpaca-py TradingClient (paper). Raises on missing creds."""
    from alpaca.trading.client import TradingClient
    from secrets_loader import alpaca_key, alpaca_secret
    key = (alpaca_key() or "").strip()
    sec = (alpaca_secret() or "").strip()
    if not key or not sec or "YOUR_" in key:
        raise RuntimeError("Alpaca credentials missing or placeholder in .env")
    return TradingClient(key, sec, paper=True)


def _to_dict_position(p) -> dict:
    """Normalize alpaca-py Position object to a plain dict."""
    return {
        "symbol": p.symbol,
        "qty": int(float(p.qty)),
        "side": (p.side.value if hasattr(p.side, "value") else str(p.side)).lower(),
        "avg_entry_price": float(p.avg_entry_price),
        "current_price": float(p.current_price or 0),
        "market_value": float(p.market_value or 0),
        "unrealized_pl": float(p.unrealized_pl or 0),
        "unrealized_plpc": float(p.unrealized_plpc or 0) * 100.0,
    }


def _to_dict_order(o) -> dict:
    """Normalize alpaca-py Order to a plain dict (only fields we use)."""
    return {
        "id": str(o.id),
        "symbol": o.symbol,
        "side": (o.side.value if hasattr(o.side, "value") else str(o.side)).lower(),
        "qty": int(float(o.qty or 0)) if o.qty else 0,
        "filled_qty": int(float(o.filled_qty or 0)) if o.filled_qty else 0,
        "filled_avg_price": float(o.filled_avg_price) if o.filled_avg_price else None,
        "status": (o.status.value if hasattr(o.status, "value") else str(o.status)).lower(),
        "created_at": o.created_at.isoformat() if o.created_at else None,
        "filled_at": o.filled_at.isoformat() if getattr(o, "filled_at", None) else None,
        "order_class": (o.order_class.value if getattr(o, "order_class", None) and hasattr(o.order_class, "value") else None),
        # 2026-05-27 — capture bracket exit-leg prices so positions can show the
        # REAL stop/target instead of a synthetic 3% placeholder.
        "order_type": (o.order_type.value if getattr(o, "order_type", None) and hasattr(o.order_type, "value") else (o.type.value if getattr(o, "type", None) and hasattr(o.type, "value") else None)),
        "stop_price": float(o.stop_price) if getattr(o, "stop_price", None) else None,
        "limit_price": float(o.limit_price) if getattr(o, "limit_price", None) else None,
    }


def _pull_alpaca_state(client, since: datetime | None = None) -> dict:
    """One shot pull: account, positions, orders since `since` (default 30d back)."""
    from alpaca.trading.requests import GetOrdersRequest
    from alpaca.trading.enums import QueryOrderStatus

    if since is None:
        since = datetime.now() - timedelta(days=30)

    account = client.get_account()
    positions = [ _to_dict_position(p) for p in client.get_all_positions() ]
    req = GetOrdersRequest(status=QueryOrderStatus.ALL, limit=500, after=since)
    orders = [ _to_dict_order(o) for o in client.get_orders(filter=req) ]
    return {
        "account": {
            "equity": float(account.equity),
            "cash": float(account.cash),
            "buying_power": float(account.buying_power),
            "account_number": str(account.account_number),
            "status": (account.status.value if hasattr(account.status, "value") else str(account.status)),
        },
        "positions": positions,
        "orders": orders,
    }


def _reconcile_positions(state: dict, alpaca_positions: list[dict],
                         account_equity: float,
                         alpaca_orders: list[dict] | None = None) -> tuple[list[str], list[str], list[str]]:
    """Apply local-vs-Alpaca position diff. Mutates state.

    Returns (inserted, updated, closed) lists of tickers.
    """
    import portfolio_tracker as pt  # use existing helpers so SQLite+JSON stay in sync

    local_positions = state.get("positions", [])
    local_by_t = {p["ticker"]: p for p in local_positions}
    alpaca_by_t = {p["symbol"]: p for p in alpaca_positions}

    # 2026-05-27 — build a ticker→{stop,target} map from OPEN bracket exit legs.
    # A bracket buy leaves an OCO of an open SELL stop + open SELL limit; their
    # stop_price / limit_price ARE the real stop/target (vs the synthetic 3%).
    _bracket: dict[str, dict] = {}
    for o in (alpaca_orders or []):
        if (o.get("side") or "").lower() != "sell":
            continue
        st = (o.get("status") or "").lower()
        if st in ("filled", "canceled", "expired", "rejected", "replaced"):
            continue  # only OPEN exit legs reflect the live bracket
        sym = (o.get("symbol") or "").upper()
        if not sym:
            continue
        leg = _bracket.setdefault(sym, {})
        otype = (o.get("order_type") or "").lower()
        if "stop" in otype and o.get("stop_price") is not None:
            leg["stop"] = round(float(o["stop_price"]), 2)
        elif "limit" in otype and o.get("limit_price") is not None:
            leg["target"] = round(float(o["limit_price"]), 2)

    inserted: list[str] = []
    updated: list[str] = []
    closed:  list[str] = []

    # 1. Local-only → Alpaca already closed it (stop/T1/T2 fired externally)
    for tk, lp in list(local_by_t.items()):
        if tk not in alpaca_by_t:
            exit_px = float(lp.get("current_price") or lp.get("entry_price") or 0)
            try:
                pt.close_position(tk, exit_px, "alpaca_external_close")
                closed.append(tk)
            except Exception as e:
                log.warning(f"close_position({tk}) failed: {e}")

    # Reload state after closes mutated it
    state.clear()
    state.update(json.loads(STATE_PATH.read_text()))
    local_by_t = {p["ticker"]: p for p in state.get("positions", [])}

    # 2. Both-sided → update current_price + unrealized_pnl in place
    # 3. Alpaca-only → insert with sane defaults (setup_type='alpaca_sync' placeholder; v2 attributes back to scan)
    today = date.today().isoformat()
    now_ts = datetime.now().strftime('%Y-%m-%d %H:%M')
    for sym, ap in alpaca_by_t.items():
        avg = ap["avg_entry_price"]
        cur = ap["current_price"]
        qty = abs(int(ap["qty"]))
        side = ap["side"]

        if sym in local_by_t:
            # NOTE: in-place edits here are DISCARDED by the state reload at the end
            # of this function. The authoritative both-sided reconcile (shares /
            # direction / entry / price / stop-target) runs in the persistent
            # post-reload loop below, which is what actually gets written to disk.
            updated.append(sym)
        else:
            # 2026-05-27 — prefer the REAL bracket exit-leg prices over a
            # synthetic 3% placeholder. Open SELL stop order → stop; open SELL
            # limit order → target. _bracket_legs built once below.
            legs = _bracket.get(sym, {})
            real_stop = legs.get("stop")
            real_target = legs.get("target")
            synthetic = (real_stop is None)
            stop = real_stop if real_stop is not None else round(avg * (0.97 if side == "long" else 1.03), 2)
            target = real_target if real_target is not None else round(avg * (1.05 if side == "long" else 0.95), 2)
            alloc = round(qty * avg / max(1.0, account_equity) * 100, 1)
            # Pull fill timestamp from most recent matching BUY order (added 2026-05-15)
            # 2026-05-27 fix: `filled` was referenced but never defined here — the
            # variable was only local to _reconcile_filled_orders. Plumb orders
            # through as a parameter and filter inline.
            entry_dt = None
            _filled = [o for o in (alpaca_orders or []) if o.get("status") == "filled"]
            for o in sorted(_filled, key=lambda x: x.get("filled_at") or x.get("created_at") or "", reverse=True):
                if (o.get("symbol") or "").upper() == sym and (o.get("side") or "").lower() == "buy":
                    entry_dt = o.get("filled_at") or o.get("created_at")
                    break
            try:
                pt.add_position(
                    ticker=sym, entry_price=avg, shares=qty,
                    stop=stop, target1=target, target2=None,
                    setup_type="alpaca_sync", direction=side,
                    allocation_pct=alloc,
                    notes="Synced from Alpaca paper account (v1 — pick attribution pending v2)",
                    entry_datetime=entry_dt,
                )
                inserted.append(sym)
            except Exception as e:
                log.warning(f"add_position({sym}) failed: {e}")

    # Reload again so caller sees the latest state
    state.clear()
    state.update(json.loads(STATE_PATH.read_text()))

    # Backfill live marks on any position missing a current price. add_position()
    # records only entry_price/shares, so a just-synced fill shows current_price=None
    # → the dashboard renders "—" for LAST/MKT VAL/P&L. (The in-place update loop
    # above also sets current_price, but those edits are on `local_by_t` refs that
    # get discarded by the state reload right above — so persist it here, after the
    # reload, for every position Alpaca can price.) (2026-06-01)
    # 2026-06-01 — FULL both-sided reconcile to Alpaca truth, AFTER the reload so
    # the edits persist (the in-place loop above runs on refs the reload discards).
    # Shares / direction / avg-entry can all change intraday (partial closes, adds,
    # flips) — previously only missing prices were backfilled, so the dashboard kept
    # stale share counts (IONQ showed 87 while Alpaca held 1; NEM long vs short).
    _now = datetime.now().strftime("%Y-%m-%d %H:%M")
    _patched = False
    for lp in state.get("positions", []):
        ap = alpaca_by_t.get(lp.get("ticker"))
        if not ap:
            continue
        try:
            qv = abs(int(ap["qty"])); side = ap["side"]; avg = float(ap["avg_entry_price"]); cur = float(ap["current_price"])
        except Exception:
            continue
        lp["shares"] = qv
        lp["signed_qty"] = qv if side == "long" else -qv
        lp["direction"] = side
        lp["entry_price"] = round(avg, 2)
        lp["current_price"] = round(cur, 2)
        lp["position_size"] = round(abs(ap.get("market_value") or qv * cur), 2)
        lp["allocation_pct"] = round(qv * avg / max(1.0, account_equity) * 100, 1)
        lp["unrealized_pnl_dollars"] = round(ap.get("unrealized_pl") or 0.0, 2)
        lp["unrealized_pnl_pct"] = round(ap.get("unrealized_plpc") or 0.0, 2)
        lp["highest_price"] = round(max(lp.get("highest_price") or avg, cur), 2)
        lp["last_updated"] = _now
        _legs = _bracket.get(lp.get("ticker"), {})
        if _legs.get("stop") is not None:
            lp["stop"] = _legs["stop"]; lp["_synthetic_stop"] = False
        if _legs.get("target") is not None:
            lp["target1"] = _legs["target"]
        _patched = True
    if _patched:
        STATE_PATH.write_text(json.dumps(state, indent=2, default=str))

    return inserted, updated, closed


def _mirror_closed_trade_to_sqlite(ct: dict) -> None:
    """Insert one closed_trade row into SQLite. Idempotent via alpaca_sell_order_id check."""
    try:
        import db
        with db.transaction() as conn:
            # Dedupe by alpaca_sell_order_id stored in raw_json
            existing = conn.execute(
                "SELECT id FROM closed_trades WHERE ticker=? AND entry_date=? AND exit_date=? AND shares=?",
                (ct.get("ticker"), ct.get("entry_date"), ct.get("exit_date"), ct.get("shares")),
            ).fetchone()
            if existing:
                return
            conn.execute(
                "INSERT INTO closed_trades "
                "(ticker, direction, entry_date, exit_date, entry_price, exit_price, "
                "shares, pnl_dollars, pnl_pct, win, setup_type, exit_reason, hold_days, raw_json) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    ct.get("ticker"), ct.get("direction") or "long",
                    ct.get("entry_date"), ct.get("exit_date"),
                    float(ct.get("entry_price") or 0), float(ct.get("exit_price") or 0),
                    int(ct.get("shares") or 0),
                    float(ct.get("pnl_dollars") or 0), float(ct.get("pnl_pct") or 0),
                    int(ct.get("win") or 0),
                    ct.get("setup_type") or "alpaca_sync",
                    ct.get("exit_reason") or "alpaca_external_close",
                    ct.get("hold_days"),
                    json.dumps(ct, default=str),
                ),
            )
    except Exception as e:
        log.warning(f"SQLite closed_trades mirror failed for {ct.get('ticker')}: {e}")


def _reconcile_filled_orders(state: dict, alpaca_orders: list[dict]) -> int:
    """Build closed_trades entries from filled SELL orders that aren't already recorded.

    Matches filled BUY+SELL pairs by ticker to estimate round-trip P&L. Tags
    each new closed_trade with the Alpaca order_id so duplicate syncs are
    idempotent. Mirrors each new row into SQLite closed_trades table too.

    Returns count of newly-recorded closed_trades.
    """
    # Existing closed_trades — key by alpaca_order_id (sell side) to detect duplicates
    closed_trades = state.setdefault("closed_trades", [])
    existing_sell_ids = {
        ct.get("alpaca_sell_order_id") for ct in closed_trades if ct.get("alpaca_sell_order_id")
    }

    # Group filled orders by ticker; pair BUYs with subsequent SELLs (FIFO)
    filled = [o for o in alpaca_orders if o.get("status") == "filled" and o.get("filled_avg_price")]
    by_ticker: dict[str, list[dict]] = {}
    for o in sorted(filled, key=lambda x: x.get("filled_at") or x.get("created_at") or ""):
        by_ticker.setdefault(o["symbol"], []).append(o)

    new_count = 0
    for ticker, orders in by_ticker.items():
        buys = [o for o in orders if o["side"] == "buy"]
        sells = [o for o in orders if o["side"] == "sell"]
        # FIFO pairing — each sell closes the earliest open buy
        for i, sell in enumerate(sells):
            if sell["id"] in existing_sell_ids:
                continue  # already recorded
            if i >= len(buys):
                continue  # orphan sell (e.g., position opened pre-sync window) — skip
            buy = buys[i]
            entry_px = buy["filled_avg_price"]
            exit_px = sell["filled_avg_price"]
            shares = min(sell["filled_qty"], buy["filled_qty"])
            pnl_dollars = round((exit_px - entry_px) * shares, 2)
            pnl_pct = round((exit_px / entry_px - 1.0) * 100, 2) if entry_px else 0.0
            entry_dt = (buy.get("filled_at") or buy.get("created_at") or "")[:10]
            exit_dt = (sell.get("filled_at") or sell.get("created_at") or "")[:10]
            try:
                d_entry = datetime.strptime(entry_dt, "%Y-%m-%d")
                d_exit = datetime.strptime(exit_dt, "%Y-%m-%d")
                hold_days = (d_exit - d_entry).days
            except Exception:
                hold_days = None

            new_ct = {
                "ticker": ticker,
                "direction": "long",  # paper buy_only filter, all are long
                "entry_date": entry_dt,
                "exit_date": exit_dt,
                "entry_price": entry_px,
                "exit_price": exit_px,
                "shares": shares,
                "pnl_dollars": pnl_dollars,
                "pnl_pct": pnl_pct,
                "win": int(pnl_dollars > 0),
                "setup_type": "alpaca_sync",  # v2 will attribute back to original pick
                "exit_reason": "alpaca_external_close",  # v2 will tag from eod_actions.jsonl
                "hold_days": hold_days,
                "alpaca_buy_order_id": buy["id"],
                "alpaca_sell_order_id": sell["id"],
                "_synced_at": datetime.now().isoformat(),
            }
            closed_trades.append(new_ct)
            _mirror_closed_trade_to_sqlite(new_ct)
            new_count += 1

    return new_count


def _append_equity_curve(state: dict, equity: float) -> bool:
    """Append today's equity snapshot if not already present. Returns True if appended."""
    today = date.today().isoformat()
    curve = state.setdefault("equity_curve", [])
    if curve and curve[-1].get("date") == today:
        curve[-1]["equity"] = round(equity, 2)
        return False
    curve.append({"date": today, "equity": round(equity, 2)})
    # Cap retention at 365 entries (defensive)
    if len(curve) > 400:
        state["equity_curve"] = curve[-365:]
    return True


def sync_alpaca_to_local(*, force: bool = False, verbose: bool = False) -> dict:
    """Reconcile Alpaca paper account → local state stores.

    Returns summary dict with: synced_at, equity, cash, buying_power, inserted,
    updated, closed, new_closed_trades, errors. Idempotent — safe to call
    repeatedly. Rate-limited to one call per ~30s unless force=True.
    """
    global _LAST_SYNC_TS

    now_ts = time.time()
    if not force and (now_ts - _LAST_SYNC_TS) < _MIN_SYNC_INTERVAL_SECONDS:
        return {"ok": False, "skipped": "rate_limit",
                "next_eligible_in": round(_MIN_SYNC_INTERVAL_SECONDS - (now_ts - _LAST_SYNC_TS), 1)}

    try:
        client = _get_client()
    except Exception as e:
        return {"ok": False, "error": f"alpaca_auth: {e}"}

    # Determine since-date — pull orders since last sync (with 1d buffer) or 30d back
    state = json.loads(STATE_PATH.read_text())
    last_sync_str = state.get("last_alpaca_sync")
    since = None
    if last_sync_str:
        try:
            since = datetime.fromisoformat(last_sync_str.replace("Z", "")) - timedelta(days=1)
        except Exception:
            since = None

    try:
        pulled = _pull_alpaca_state(client, since=since)
    except Exception as e:
        return {"ok": False, "error": f"alpaca_pull: {e}"}

    account = pulled["account"]
    equity = account["equity"]

    # 1. Position reconciliation
    inserted, updated, closed = _reconcile_positions(state, pulled["positions"], equity, alpaca_orders=pulled.get("orders") or [])

    # 2. Filled-order → closed_trades reconciliation
    new_closed_trades = _reconcile_filled_orders(state, pulled["orders"])

    # 3. Account-level updates
    state["equity"] = round(equity, 2)
    state["cash"] = round(account["cash"], 2)
    state["buying_power"] = round(account["buying_power"], 2)
    state["last_alpaca_sync"] = datetime.now().isoformat()
    state["alpaca_account"] = (account["account_number"] or "")[:6] + "***"

    # 4. equity_curve daily snapshot
    appended_curve = _append_equity_curve(state, equity)

    # 5. Write back
    STATE_PATH.write_text(json.dumps(state, indent=2, default=str))

    # 6. SQLite mirror — sync equity_curve + portfolio_state (positions/closed_trades
    #    already handled by pt.add_position / pt.close_position above)
    try:
        import db
        with db.transaction() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO equity_curve (date, equity) VALUES (?, ?)",
                (date.today().isoformat(), round(equity, 2)),
            )
            conn.execute(
                "INSERT OR REPLACE INTO portfolio_state (id, equity, cash, margin_reserved, updated_at) "
                "VALUES (1, ?, ?, ?, ?)",
                (round(equity, 2), round(account["cash"], 2),
                 round(state.get("margin_reserved", 0) or 0, 2),
                 datetime.now().isoformat()),
            )
    except Exception as e:
        log.warning(f"SQLite mirror update failed: {e}")

    _LAST_SYNC_TS = now_ts

    result = {
        "ok": True,
        "synced_at": state["last_alpaca_sync"],
        "equity": state["equity"],
        "cash": state["cash"],
        "buying_power": state["buying_power"],
        "alpaca_account": state["alpaca_account"],
        "alpaca_position_count": len(pulled["positions"]),
        "alpaca_order_count": len(pulled["orders"]),
        "inserted": inserted,
        "updated": updated,
        "closed": closed,
        "new_closed_trades": new_closed_trades,
        "equity_curve_appended": appended_curve,
        "since": since.isoformat() if since else None,
    }

    if verbose:
        log.info(
            f"alpaca_sync: equity=${result['equity']:,.2f} "
            f"positions(alpaca={result['alpaca_position_count']}) "
            f"local: +{len(inserted)} ~{len(updated)} -{len(closed)} | "
            f"new_closed_trades={new_closed_trades}"
        )

    return result


if __name__ == "__main__":
    # CLI: python3 alpaca_sync.py [--force] [--quiet]
    import argparse
    p = argparse.ArgumentParser(description="Sync Alpaca paper account → local state")
    p.add_argument("--force", action="store_true", help="bypass 30s rate-limit")
    p.add_argument("--quiet", action="store_true", help="suppress info log")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    result = sync_alpaca_to_local(force=args.force, verbose=not args.quiet)
    print(json.dumps(result, indent=2, default=str))

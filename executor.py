#!/usr/bin/env python3
"""AI-16: Alpaca paper-trade auto-executor (v1).

Reads cache/last_bundle.json and submits bracket orders to Alpaca paper account.
Mechanical execution removes discretionary skip bias (the single biggest retail
P&L leak per Phase 4 memory).

Safety:
  - Hardcoded paper=True; refuses to submit if config says paper=False
  - Dry-run by default (`--dry-run`); must explicitly pass `--submit` for real orders
  - Skips tickers already open in the Alpaca account
  - Skips if account cash insufficient for the computed size
  - Every attempted order logged to cache/orders.jsonl with timestamp + rationale

Usage:
  python3 executor.py                              # dry-run, BUY only
  python3 executor.py --dry-run --filter BUY,WATCH # dry-run, include WATCH
  python3 executor.py --submit                     # real paper orders
  python3 executor.py --bundle cache/last_bundle.json --max-positions 4
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).parent
_ORDERS_LOG = _ROOT / "cache" / "orders.jsonl"

log = logging.getLogger("executor")
if not log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s executor: %(message)s",
                                      datefmt="%Y-%m-%d %H:%M:%S"))
    log.addHandler(_h)
    log.setLevel(logging.INFO)

# Paper-trading gates (activation window + daily cap). Imported lazily so that
# `import executor` doesn't trigger portfolio_tracker side effects during tests.
try:
    from portfolio_tracker import (
        is_paper_trading_enabled,
        can_take_new_trade,
        daily_trades_taken_today,
        activate_paper_trading,
        disable_paper_trading,
        paper_trading_status,
        MAX_DAILY_TRADES,
    )
except Exception as _pt_exc:  # pragma: no cover — keep importable for --help
    log.warning(f"portfolio_tracker gates unavailable: {_pt_exc}")
    def is_paper_trading_enabled(): return False, "portfolio_tracker import failed"
    def can_take_new_trade(): return False, "portfolio_tracker import failed"
    def daily_trades_taken_today(): return 0
    def activate_paper_trading(duration_days: int = 60): raise RuntimeError("unavailable")
    def disable_paper_trading(): raise RuntimeError("unavailable")
    def paper_trading_status(): return {"enabled": False, "reason": "unavailable"}
    MAX_DAILY_TRADES = 4


def _fail_fast(msg: str, code: int = 2) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def _load_bundle(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        _fail_fast(f"Bundle not found: {p}")
    return json.loads(p.read_text())


def _make_client():
    """Initialize Alpaca v2 TradingClient. Returns (client, account) or fail-fast."""
    try:
        from alpaca.trading.client import TradingClient
    except ImportError:
        _fail_fast(
            "alpaca-py SDK not installed. Install with:\n"
            "  pip install alpaca-py"
        )
    try:
        from secrets_loader import alpaca_key, alpaca_secret
        key = alpaca_key()
        secret = alpaca_secret()
    except Exception as e:
        _fail_fast(f"secrets_loader failed: {e}")
    if not key or not secret:
        _fail_fast("ALPACA_API_KEY / ALPACA_SECRET_KEY not set in .env")

    # HARD SAFETY: paper=True non-negotiable in v1
    client = TradingClient(key, secret, paper=True)
    try:
        account = client.get_account()
    except Exception as e:
        _fail_fast(f"Alpaca auth/connection failed: {e}")
    return client, account


def _existing_position_tickers(client) -> set[str]:
    try:
        positions = client.get_all_positions()
        return {p.symbol for p in positions}
    except Exception:
        return set()


def _log_order(entry: dict) -> None:
    _ORDERS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with _ORDERS_LOG.open("a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def _slack_notify(text: str) -> None:
    try:
        from secrets_loader import get_secret
        url = get_secret("SLACK_WEBHOOK_URL", default="")
        if not url:
            return
        import urllib.request
        req = urllib.request.Request(
            url, data=json.dumps({"text": text}).encode(),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=8)
    except Exception:
        pass


def _pick_size_shares(pick: dict, equity: float, cfg_pct: float, cash: float,
                      max_size_pct: float = 100.0) -> tuple[int, str]:
    entry = float(pick.get("price") or pick.get("trade_plan", {}).get("entry_low") or 0)
    if entry <= 0:
        return 0, "no entry price"

    ticker = pick.get("ticker", "?")
    cash_budget = cash * 0.95  # leave 5% cash buffer

    # Normalize / clamp the regime multiplier (0–100 → 0.0–1.0)
    try:
        msp = float(max_size_pct)
    except (TypeError, ValueError):
        msp = 100.0
    msp = max(0.0, min(100.0, msp))
    regime_mult = msp / 100.0
    if msp < 100.0:
        log.info(f"Position size scaled by regime: {msp:g}% of base")

    # Hard-stop: panic regime (max_size_pct == 0) blocks new longs
    if regime_mult <= 0.0:
        return 0, f"regime max_size_pct=0 (panic): no new longs"

    # Try Kelly sizing first (audit item #6)
    ks = pick.get("kelly_size", {}) or {}
    kelly_shares = ks.get("suggested_shares")
    kelly_confidence = ks.get("confidence", ks.get("n_trades", 0))
    if kelly_shares and kelly_confidence and kelly_confidence >= 10:
        # Safety cap: Kelly position value never exceeds 2x flat sizing
        max_value = equity * cfg_pct * 2.0
        max_shares = int(max_value // entry)
        shares = min(int(kelly_shares), max_shares)
        # Apply regime max_size_pct multiplier
        shares = max(0, int(shares * regime_mult))
        if shares * entry > cash_budget:
            shares = int(cash_budget // entry)
        if shares <= 0:
            return 0, f"kelly shares<=0 after caps (entry ${entry:.2f}, cash ${cash:.0f}, regime={msp:g}%)"
        log.info(f"Kelly sizing for {ticker}: {shares} shares "
                 f"(kelly_suggested={kelly_shares}, conf={kelly_confidence}, "
                 f"cap={max_shares}, regime={msp:g}%)")
        return shares, "kelly"

    # Flat sizing fallback
    target_value = equity * cfg_pct * regime_mult
    shares = int(target_value // entry)
    if shares <= 0:
        return 0, f"computed 0 shares (target ${target_value:.0f} / entry ${entry:.2f}, regime={msp:g}%)"
    if shares * entry > cash_budget:
        shares = int(cash_budget // entry)
    if shares <= 0:
        return 0, f"insufficient cash (${cash:.0f} for {entry:.2f}/share)"
    log.info(f"Flat sizing for {ticker}: {shares} shares (Kelly unavailable, regime={msp:g}%)")
    return shares, "flat"


def build_order_plan(picks: list[dict], equity: float, cash: float, cfg: dict,
                      existing: set[str], max_positions: int,
                      market_snapshot: dict | None = None) -> list[dict]:
    plan = []
    pct = float(cfg.get("portfolio", {}).get("config_e", {}).get("pct_per_trade", 0.2))
    # Regime-adaptive position sizing (wave 2A: checklist 1.7).
    # `market_snapshot` is the bundle["regime"] dict populated by data_fetcher.py.
    # Missing key → default 100 (backward-compat no-op).
    _ms = market_snapshot or {}
    max_size_pct = float(_ms.get("max_size_pct", 100))
    # Paper-trading hard cap: remaining trade slots for today.
    # BUY-only for the 60-day paper window; SHORTs documented to re-enable later.
    already_today = daily_trades_taken_today()
    remaining_today = max(0, MAX_DAILY_TRADES - already_today)
    orders_in_plan = 0
    skipped = 0
    for pk in picks:
        ticker = pk.get("ticker", "")
        if not ticker:
            continue
        # BUY-only gate (direction + verdict).
        verdict = (pk.get("decision") or {}).get("verdict", "") or pk.get("verdict", "")
        direction = (pk.get("direction") or pk.get("trade_plan", {}).get("direction") or "long").lower()
        if verdict and verdict.upper() != "BUY":
            plan.append({"ticker": ticker, "action": "skip", "reason": f"verdict {verdict} (BUY-only window)"})
            skipped += 1
            continue
        if direction == "short":
            plan.append({"ticker": ticker, "action": "skip", "reason": "SHORT skipped (BUY-only paper window)"})
            skipped += 1
            continue
        if ticker in existing:
            plan.append({"ticker": ticker, "action": "skip", "reason": "already open"})
            skipped += 1
            continue
        if orders_in_plan >= max_positions:
            plan.append({"ticker": ticker, "action": "skip", "reason": f"max_positions {max_positions} reached"})
            continue
        # Daily cap — hard stop before planning a 5th order for today.
        if orders_in_plan >= remaining_today:
            plan.append({
                "ticker": ticker,
                "action": "skip",
                "reason": f"daily cap: {already_today}+{orders_in_plan}/{MAX_DAILY_TRADES} taken",
            })
            continue
        tp = pk.get("trade_plan") or {}
        entry = float(pk.get("price") or tp.get("entry_low") or 0)
        stop = float(tp.get("stop") or 0)
        tgt1 = float(tp.get("target1") or 0)
        if not (entry > 0 and stop > 0 and tgt1 > 0):
            plan.append({"ticker": ticker, "action": "skip", "reason": "missing entry/stop/target"})
            continue
        if stop >= entry:
            plan.append({"ticker": ticker, "action": "skip", "reason": f"stop {stop} >= entry {entry} (long only v1)"})
            continue
        shares, why = _pick_size_shares(pk, equity, pct, cash, max_size_pct=max_size_pct)
        if shares <= 0:
            plan.append({"ticker": ticker, "action": "skip", "reason": why})
            continue
        # `why` is the sizing method ("kelly" or "flat") when shares > 0
        plan.append({
            "ticker":       ticker,
            "action":       "order",
            "side":         "buy",
            "qty":          shares,
            "entry_limit":  round(entry, 2),
            "stop":         round(stop, 2),
            "target":       round(tgt1, 2),
            "setup":        tp.get("setup_type", ""),
            "score":        pk.get("score"),
            "verdict":      (pk.get("decision") or {}).get("verdict", ""),
            "sizing_method": why,
        })
        orders_in_plan += 1
    return plan


def submit_bracket(client, order: dict) -> tuple[bool, str]:
    """Submit a BUY bracket order. Returns (ok, order_id_or_error)."""
    try:
        from alpaca.trading.requests import LimitOrderRequest, TakeProfitRequest, StopLossRequest
        from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass
        req = LimitOrderRequest(
            symbol=order["ticker"],
            qty=order["qty"],
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
            limit_price=order["entry_limit"],
            order_class=OrderClass.BRACKET,
            take_profit=TakeProfitRequest(limit_price=order["target"]),
            stop_loss=StopLossRequest(stop_price=order["stop"]),
        )
        resp = client.submit_order(req)
        return True, str(getattr(resp, "id", "submitted"))
    except Exception as e:
        return False, str(e)


def _print_status() -> int:
    status = paper_trading_status()
    print("=== Paper Trading Status ===")
    if status["enabled"]:
        print(f"  State       : ENABLED · {status['reason']}")
    else:
        print(f"  State       : DISABLED · {status['reason']}")
    print(f"  Today       : {status['daily_count']}/{status['daily_cap']} trades taken")
    if status.get("marker"):
        m = status["marker"]
        print(f"  Start date  : {m.get('start_date', '—')}")
        print(f"  Duration    : {m.get('duration_days', '—')}d")
        print(f"  Direction   : {m.get('direction_filter', 'buy_only')}")
    else:
        print("  Marker file : (absent)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", default=str(_ROOT / "cache" / "last_bundle.json"))
    ap.add_argument("--dry-run", action="store_true", default=True,
                    help="Preview only (default)")
    ap.add_argument("--submit", action="store_true",
                    help="Actually submit to Alpaca paper")
    ap.add_argument("--filter", default="BUY",
                    help="Comma-separated verdict list (e.g. BUY or BUY,WATCH)")
    ap.add_argument("--max-positions", type=int, default=None)
    ap.add_argument("--activate", action="store_true",
                    help="Activate paper trading (60-day window, BUY-only)")
    ap.add_argument("--disable", action="store_true",
                    help="Disable paper trading")
    ap.add_argument("--status", action="store_true",
                    help="Show paper-trading status and exit")
    ap.add_argument("--duration-days", type=int, default=60,
                    help="Duration for --activate (default 60)")
    args = ap.parse_args()

    # Admin sub-commands short-circuit the execution flow.
    if args.status:
        return _print_status()
    if args.activate:
        payload = activate_paper_trading(duration_days=args.duration_days)
        print(f"Paper trading ACTIVATED — start {payload['start_date']}, "
              f"duration {payload['duration_days']}d, BUY-only, cap {payload['max_daily_trades']}/day")
        return 0
    if args.disable:
        disable_paper_trading()
        print("Paper trading DISABLED")
        return 0

    if args.submit:
        args.dry_run = False

    # Activation gate — refuse to run if paper trading is not enabled.
    enabled, reason = is_paper_trading_enabled()
    if not enabled:
        log.info(f"Skip execution: {reason}")
        print(f"Paper trading not enabled — {reason}")
        print("Run `python3 executor.py --activate` to enable.")
        return 0
    log.info(f"Paper trading ON — {reason}")

    cfg_path = _ROOT / "config" / "config.json"
    cfg = json.loads(cfg_path.read_text())

    # Hard safety: verify config.alpaca.paper is True before we ever consider --submit.
    _alpaca_cfg = cfg.get("alpaca", {})
    _paper_flag = _alpaca_cfg.get("paper", True)
    if args.submit and _paper_flag is not True:
        _fail_fast("config.alpaca.paper is not True — refusing to submit live orders.")

    max_pos = args.max_positions or cfg.get("portfolio", {}).get("config_e", {}).get("max_positions", 4)
    verdicts = [v.strip().upper() for v in args.filter.split(",")]

    # Load bundle + pick candidates
    bundle = _load_bundle(args.bundle)
    picks: list[dict] = []
    # primary BUY candidates
    for key in ("buy_candidates", "top_picks", "buy_list"):
        if key in bundle and isinstance(bundle[key], list):
            picks.extend(bundle[key])
            break
    # fallback: scan all_scored filtered by verdict
    if not picks and "all_scored" in bundle:
        picks = [r for r in bundle["all_scored"]
                 if (r.get("decision") or {}).get("verdict", "") in verdicts]

    if not picks:
        print(f"No picks in bundle matching filter {verdicts}. Nothing to do.")
        return 0

    mode = "DRY-RUN" if args.dry_run else "SUBMIT"
    print(f"=== Executor ({mode}) — {len(picks)} picks, filter={verdicts}, max={max_pos} ===")

    equity = cash = 0.0
    existing: set[str] = set()
    client = None
    if not args.dry_run:
        client, account = _make_client()
        equity = float(account.equity)
        cash = float(account.cash)
        existing = _existing_position_tickers(client)
        print(f"Alpaca paper: equity=${equity:,.2f} · cash=${cash:,.2f} · open={len(existing)}")
    else:
        # Dry-run: use config equity, assume cash=equity, no existing
        equity = float(cfg.get("portfolio", {}).get("account_equity", 5000))
        cash = equity
        print(f"Dry-run: using config equity=${equity:,.2f}")

    # Market snapshot flows from data_fetcher.py → bundle["regime"] (contains max_size_pct)
    market_snapshot = bundle.get("regime") if isinstance(bundle.get("regime"), dict) else {}
    order_plan = build_order_plan(picks, equity, cash, cfg, existing, max_pos,
                                   market_snapshot=market_snapshot)

    submitted, skipped, failed = 0, 0, 0
    ts = datetime.now(timezone.utc).isoformat()
    for entry in order_plan:
        log_entry = {"timestamp": ts, "dry_run": args.dry_run, **entry}
        if entry["action"] == "skip":
            print(f"  SKIP {entry['ticker']:6s} — {entry['reason']}")
            log.info(f"skip {entry['ticker']}: {entry['reason']}")
            skipped += 1
        else:
            # Defense-in-depth: re-check daily cap right before each submit so a
            # concurrent run or mid-loop fill can't push us past 4/day.
            can_trade, cap_reason = can_take_new_trade()
            if not can_trade:
                log.info(f"Daily cap reached mid-loop: {cap_reason} — stopping after {submitted} orders")
                print(f"  CAP  {entry['ticker']:6s} — {cap_reason}")
                log_entry["action"] = "skip"
                log_entry["reason"] = cap_reason
                log_entry["status"] = "skipped_daily_cap"
                _log_order(log_entry)
                skipped += 1
                break
            print(f"  {'WOULD ORDER' if args.dry_run else 'ORDER'} {entry['ticker']:6s} "
                  f"{entry['qty']}x @ ${entry['entry_limit']} "
                  f"stop ${entry['stop']} tgt ${entry['target']} ({entry['setup']})")
            log.info(f"attempt {entry['ticker']} qty={entry['qty']} "
                     f"entry={entry['entry_limit']} stop={entry['stop']} tgt={entry['target']} "
                     f"mode={'dry' if args.dry_run else 'live'}")
            if args.dry_run:
                log_entry["alpaca_order_id"] = None
                log_entry["status"] = "dry_run"
                submitted += 1
            else:
                ok, result = submit_bracket(client, entry)
                log_entry["alpaca_order_id"] = result if ok else None
                log_entry["status"] = "submitted" if ok else "failed"
                if not ok:
                    log_entry["error"] = result
                    print(f"    FAILED: {result}")
                    log.error(f"submit failed {entry['ticker']}: {result}")
                    failed += 1
                else:
                    print(f"    → order_id {result}")
                    log.info(f"submit ok {entry['ticker']} order_id={result}")
                    submitted += 1
        _log_order(log_entry)

    summary = f"{mode}: {submitted} submitted · {skipped} skipped · {failed} failed"
    print("\n" + summary)
    if not args.dry_run and submitted > 0:
        _slack_notify(f"*SwingTrade executor* — {summary}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

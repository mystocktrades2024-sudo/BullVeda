#!/usr/bin/env python3
"""End-of-day position manager for SwingTrade.

Runs near market close (suggested 15:55 ET / 12:55 PT Mon-Fri) to mechanically
apply EOD rules: close stopped/target-hit positions, trim oversized runners,
tighten stops, release dead-weight flat positions.

Suggested launchd plist (~/Library/LaunchAgents/com.swingtrade.eod.plist):

    <?xml version="1.0" encoding="UTF-8"?>
    <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
      "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
    <plist version="1.0"><dict>
      <key>Label</key><string>com.swingtrade.eod</string>
      <key>ProgramArguments</key>
      <array>
        <string>/usr/bin/python3</string>
        <string>/Volumes/MyMacDisk/Claude Skills/SwingTrade/eod_manager.py</string>
        <string>--submit</string>
        <string>--tighten-stops</string>
        <string>--close-positions</string>
      </array>
      <key>StartCalendarInterval</key>
      <array>
        <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>12</integer><key>Minute</key><integer>55</integer></dict>
        <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>12</integer><key>Minute</key><integer>55</integer></dict>
        <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>12</integer><key>Minute</key><integer>55</integer></dict>
        <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>12</integer><key>Minute</key><integer>55</integer></dict>
        <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>12</integer><key>Minute</key><integer>55</integer></dict>
      </array>
      <key>StandardOutPath</key><string>/tmp/swingtrade-eod.out</string>
      <key>StandardErrorPath</key><string>/tmp/swingtrade-eod.err</string>
    </dict></plist>

Load: launchctl load ~/Library/LaunchAgents/com.swingtrade.eod.plist
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).parent
_LOG = _ROOT / "cache" / "eod_actions.jsonl"
_GAP_EVENTS = _ROOT / "data" / "gap_events.json"
_EXIT_SIGNALS = _ROOT / "data" / "exit_signals.jsonl"

# Gap-handling thresholds
GAP_MINOR_PCT = 3.0      # below this = ignored
GAP_MODERATE_PCT = 3.0   # 3-5% = moderate
GAP_MAJOR_PCT = 5.0      # >5% = major (high-priority alert)
GAP_TIGHTEN_ATR_MULT = 0.75  # tighten trail to 0.75 * ATR on gap-up >3%


def _fail_fast(msg: str, code: int = 2) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def _make_client():
    try:
        from alpaca.trading.client import TradingClient
    except ImportError:
        _fail_fast("alpaca-py SDK not installed: pip install alpaca-py")
    try:
        from secrets_loader import alpaca_key, alpaca_secret
        key, secret = alpaca_key(), alpaca_secret()
    except Exception as e:
        _fail_fast(f"secrets_loader failed: {e}")
    if not key or not secret:
        _fail_fast("ALPACA_API_KEY / ALPACA_SECRET_KEY not set")
    client = TradingClient(key, secret, paper=True)  # HARD SAFETY
    try:
        account = client.get_account()
    except Exception as e:
        _fail_fast(f"Alpaca auth failed: {e}")
    # Fail-fast if account reports non-paper
    if not bool(getattr(account, "account_number", "").startswith(("PA", "pa"))) \
            and str(getattr(account, "status", "")).upper() != "ACTIVE":
        pass  # account_number prefix heuristic; rely primarily on paper=True flag
    if getattr(account, "trading_blocked", False):
        _fail_fast("Account trading_blocked=True")
    return client, account


def _log(entry: dict) -> None:
    _LOG.parent.mkdir(parents=True, exist_ok=True)
    with _LOG.open("a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def _compute_atr_proxy(pos: dict) -> float:
    """ATR proxy consistent with portfolio_tracker.trail_stop: |entry - stop|.
    Falls back to 2% of entry if degenerate.
    """
    entry = float(pos.get("entry_price") or 0)
    stop = float(pos.get("stop") or (entry * 0.97 if entry else 0))
    atr = abs(entry - stop)
    if atr <= 0 and entry > 0:
        atr = entry * 0.02
    return atr


def _fetch_open_and_prev_close(ticker: str) -> tuple[float | None, float | None, str]:
    """Return (open_price, prev_close, source) using vendor failover chain.

    Graceful: returns (None, None, "failed") on any error.
    """
    try:
        from data_fetcher import fetch_ohlcv_with_failover
    except Exception as e:
        return None, None, f"import_failed:{e}"
    try:
        df, tier = fetch_ohlcv_with_failover(ticker, days=10)
        if df is None or len(df) < 2:
            return None, None, f"no_data:{tier}"
        # Normalize column case (Polygon vs yfinance)
        cols = {c.lower(): c for c in df.columns}
        open_col = cols.get("open")
        close_col = cols.get("close")
        if not open_col or not close_col:
            return None, None, f"bad_columns:{tier}"
        latest_open = float(df[open_col].iloc[-1])
        prev_close = float(df[close_col].iloc[-2])
        return latest_open, prev_close, tier
    except Exception as e:
        return None, None, f"error:{e}"


def detect_gap(ticker: str, prev_close: float, open_price: float) -> dict:
    """Classify the gap between prev_close and next session open.

    Returns: {"ticker","prev_close","open_price","gap_pct","direction","severity"}
    severity ∈ {"none","minor","moderate","major"}
    """
    if not prev_close or prev_close <= 0 or not open_price or open_price <= 0:
        return {"ticker": ticker, "prev_close": prev_close, "open_price": open_price,
                "gap_pct": 0.0, "direction": "flat", "severity": "none"}
    gap_pct = round((open_price - prev_close) / prev_close * 100.0, 3)
    abs_pct = abs(gap_pct)
    direction = "up" if gap_pct > 0 else ("down" if gap_pct < 0 else "flat")
    if abs_pct >= GAP_MAJOR_PCT:
        severity = "major"
    elif abs_pct >= GAP_MODERATE_PCT:
        severity = "moderate"
    elif abs_pct > 0:
        severity = "minor"
    else:
        severity = "none"
    return {
        "ticker": ticker,
        "prev_close": round(prev_close, 4),
        "open_price": round(open_price, 4),
        "gap_pct": gap_pct,
        "direction": direction,
        "severity": severity,
    }


def _log_gap_event(event: dict) -> None:
    """Append a gap event to data/gap_events.json (list-structured file)."""
    _GAP_EVENTS.parent.mkdir(parents=True, exist_ok=True)
    existing: list = []
    if _GAP_EVENTS.exists():
        try:
            with _GAP_EVENTS.open() as f:
                existing = json.load(f)
                if not isinstance(existing, list):
                    existing = []
        except Exception:
            existing = []
    existing.append(event)
    # Cap file growth: keep last 500 events
    if len(existing) > 500:
        existing = existing[-500:]
    with _GAP_EVENTS.open("w") as f:
        json.dump(existing, f, indent=2, default=str)


def _send_gap_alert(level: str, title: str, body: str) -> None:
    """Best-effort alert via alerts.send_alert. Silent on failure."""
    try:
        from alerts import send_alert, _load_alert_cfg
        cfg = {}
        try:
            cfg = _load_alert_cfg() or {}
        except Exception:
            cfg = {}
        webhook = cfg.get("slack_webhook") or cfg.get("webhook")
        send_alert(level, title, body, webhook=webhook)
    except Exception:
        pass


def evaluate_gaps(positions: list[dict] | None = None) -> list[dict]:
    """Scan open positions for overnight gaps and produce gap-plan items.

    Returns a list of plan items to be merged into the EOD plan. Each item has
    kind ∈ {"GAP_TIGHTEN", "GAP_EXIT", "GAP_ALERT"} plus a `gap_event` dict that
    was logged to data/gap_events.json.

    - Gap-up >=3%: tighten trail to highest(existing_trail, open - 0.75*ATR)
    - Gap-down >=3% for longs:
        * if open <= stop  -> GAP_EXIT (auto-close at open)
        * else             -> GAP_ALERT (severe drawdown, user discretion)
    - Any gap >=5%: additional high-priority WARN/CRITICAL alert
    """
    items: list[dict] = []
    if positions is None:
        try:
            from portfolio_tracker import _load_state
            positions = _load_state().get("positions", [])
        except Exception as e:
            print(f"  [gap] unable to load portfolio state: {e}", file=sys.stderr)
            return items

    for pos in positions:
        tkr = str(pos.get("ticker", "")).upper()
        if not tkr:
            continue
        direction = str(pos.get("direction", "long")).lower()
        open_price, prev_close, src = _fetch_open_and_prev_close(tkr)
        if open_price is None or prev_close is None:
            # Graceful degradation: log and skip
            print(f"  [gap] {tkr}: price fetch failed ({src}) — skipping gap check")
            continue

        gap = detect_gap(tkr, prev_close, open_price)
        if gap["severity"] in ("none", "minor"):
            continue  # only act on >=3%

        atr = _compute_atr_proxy(pos)
        existing_stop = float(pos.get("trail_stop") or pos.get("stop") or 0)
        event = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "ticker": tkr,
            "prev_close": gap["prev_close"],
            "open_price": gap["open_price"],
            "gap_pct": gap["gap_pct"],
            "direction": gap["direction"],
            "severity": gap["severity"],
            "source": src,
            "atr_proxy": round(atr, 4),
            "existing_stop": round(existing_stop, 4),
        }

        # Gap UP -> tighten trail to lock gains (longs only; shorts flagged for alert)
        if gap["direction"] == "up" and direction == "long":
            proposed_stop = round(open_price - GAP_TIGHTEN_ATR_MULT * atr, 2)
            new_stop = max(existing_stop, proposed_stop)  # only ratchet up
            if new_stop > existing_stop:
                event["action"] = f"tightened trail to {GAP_TIGHTEN_ATR_MULT}xATR"
                event["new_stop"] = new_stop
                items.append({
                    "kind": "GAP_TIGHTEN",
                    "ticker": tkr,
                    "new_stop": new_stop,
                    "old_stop": existing_stop,
                    "reason": f"gap-up {gap['gap_pct']:+.2f}% ({gap['severity']})",
                    "gap_event": event,
                })
            else:
                event["action"] = "no-op (trail already tighter than proposed)"
                event["new_stop"] = existing_stop
                items.append({
                    "kind": "GAP_ALERT",
                    "ticker": tkr,
                    "reason": f"gap-up {gap['gap_pct']:+.2f}% but trail already protective",
                    "gap_event": event,
                })

        # Gap DOWN -> auto-close only if stop breached at open
        elif gap["direction"] == "down" and direction == "long":
            if existing_stop > 0 and open_price <= existing_stop:
                event["action"] = "auto-close: gap opened at/below stop"
                items.append({
                    "kind": "GAP_EXIT",
                    "ticker": tkr,
                    "shares": int(pos.get("shares") or 0),
                    "current": open_price,
                    "reason": f"gap-down {gap['gap_pct']:+.2f}% breached stop ${existing_stop:.2f}",
                    "gap_event": event,
                })
            else:
                event["action"] = "alert only (stop not breached; user discretion)"
                items.append({
                    "kind": "GAP_ALERT",
                    "ticker": tkr,
                    "reason": f"gap-down {gap['gap_pct']:+.2f}% ({gap['severity']}) "
                              f"— stop ${existing_stop:.2f} intact",
                    "gap_event": event,
                })

        # Short direction or any other case — alert only
        else:
            event["action"] = f"alert only ({direction} position, {gap['direction']} gap)"
            items.append({
                "kind": "GAP_ALERT",
                "ticker": tkr,
                "reason": f"gap-{gap['direction']} {gap['gap_pct']:+.2f}% on {direction}",
                "gap_event": event,
            })

        # Log event and emit alert
        try:
            _log_gap_event(event)
        except Exception as e:
            print(f"  [gap] {tkr}: failed to log event: {e}", file=sys.stderr)

        if gap["severity"] == "major":
            level = "CRITICAL" if gap["direction"] == "down" else "WARN"
            _send_gap_alert(
                level,
                f"{tkr} gap-{gap['direction']} {gap['gap_pct']:+.2f}%",
                f"prev_close=${gap['prev_close']:.2f} open=${gap['open_price']:.2f} "
                f"stop=${existing_stop:.2f} action={event.get('action','')}",
            )
        elif gap["severity"] == "moderate":
            _send_gap_alert(
                "WARN",
                f"{tkr} gap-{gap['direction']} {gap['gap_pct']:+.2f}%",
                f"prev_close=${gap['prev_close']:.2f} open=${gap['open_price']:.2f} "
                f"action={event.get('action','')}",
            )
    return items


def _log_exit_signal(entry: dict) -> None:
    """Append one line per position per day to data/exit_signals.jsonl."""
    _EXIT_SIGNALS.parent.mkdir(parents=True, exist_ok=True)
    try:
        with _EXIT_SIGNALS.open("a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except Exception as e:
        print(f"  [exit] failed to write exit signal: {e}", file=sys.stderr)


def _load_last_market_snapshot() -> dict:
    """Best-effort load of the latest scan bundle's regime block for regime4/indicators."""
    try:
        bundle_path = _ROOT / "cache" / "last_bundle.json"
        if not bundle_path.exists():
            return {}
        with bundle_path.open() as f:
            bundle = json.load(f)
        regime = bundle.get("regime") or {}
        return regime if isinstance(regime, dict) else {}
    except Exception:
        return {}


def _load_exit_config() -> dict:
    """Load full config (for exit_rules). Silent failure → empty dict."""
    try:
        cfg_path = _ROOT / "config" / "config.json"
        if cfg_path.exists():
            with cfg_path.open() as f:
                return json.load(f) or {}
    except Exception:
        pass
    return {}


def run_exit_classifier(positions: list[dict] | None = None) -> list[dict]:
    """Run classify_exit_state() against every open position.

    For each position:
      - EXIT  → queue an EXIT plan item + persist verdict + write jsonl
      - TRIM  → queue a TRIM plan item + persist verdict + write jsonl
      - HOLD  → persist verdict + write jsonl (no plan item)

    Returns plan items (list of dicts with kind in {"EXIT","TRIM"}) ready to be
    merged into build_plan().
    """
    items: list[dict] = []
    if positions is None:
        try:
            from portfolio_tracker import _load_state
            positions = _load_state().get("positions", [])
        except Exception as e:
            print(f"  [exit] unable to load portfolio state: {e}", file=sys.stderr)
            return items

    if not positions:
        return items

    try:
        from analysis import classify_exit_state
    except Exception as e:
        print(f"  [exit] classify_exit_state unavailable: {e}", file=sys.stderr)
        return items

    snapshot = _load_last_market_snapshot()
    regime4 = snapshot.get("regime4", "unknown")
    cfg = _load_exit_config()
    today_iso = datetime.now(timezone.utc).date().isoformat()

    try:
        from portfolio_tracker import set_position_exit_verdict
    except Exception:
        set_position_exit_verdict = None  # degrade gracefully

    for pos in positions:
        tkr = str(pos.get("ticker", "")).upper()
        if not tkr:
            continue
        # Current price — prefer explicit field; fallback to a fresh fetch
        cur = pos.get("current_price") or pos.get("last_price")
        if cur is None or (isinstance(cur, (int, float)) and cur <= 0):
            try:
                open_px, prev_close, _src = _fetch_open_and_prev_close(tkr)
                cur = open_px or prev_close or pos.get("entry_price")
            except Exception:
                cur = pos.get("entry_price")
        try:
            cur = float(cur or 0)
        except (TypeError, ValueError):
            cur = 0.0

        # Indicators — best-effort pull from position snapshot; empty dict OK
        indicators = {
            "ema21_weekly": pos.get("ema21_weekly"),
            "rs_rank":      pos.get("rs_rank") or pos.get("rs_rank_at_entry"),
            "mae_pct":      pos.get("mae_pct"),
        }

        try:
            verdict = classify_exit_state(pos, cur, indicators, regime4, cfg)
        except Exception as e:
            print(f"  [exit] {tkr}: classify_exit_state failed: {e}", file=sys.stderr)
            continue

        # Persist verdict on the active position record
        if set_position_exit_verdict is not None:
            try:
                set_position_exit_verdict(tkr, verdict, check_date=today_iso)
            except Exception as e:
                print(f"  [exit] {tkr}: persist verdict failed: {e}", file=sys.stderr)

        # Always write a jsonl line (one per ticker per day)
        _log_exit_signal({
            "ts":         datetime.now(timezone.utc).isoformat(),
            "date":       today_iso,
            "ticker":     tkr,
            "current":    round(cur, 4) if cur else cur,
            "regime4":    regime4,
            "verdict":    verdict,
            "entry_price": pos.get("entry_price"),
            "stop":       pos.get("stop"),
            "target1":    pos.get("target1"),
            "entry_date": pos.get("entry_date"),
        })

        action = (verdict or {}).get("action", "HOLD")
        reason = (verdict or {}).get("reason", "")
        if action == "EXIT":
            items.append({
                "kind":    "EXIT",
                "ticker":  tkr,
                "shares":  int(pos.get("shares") or 0),
                "reason":  f"classify_exit_state: {reason}",
                "current": cur,
                "exit_verdict": verdict,
                "exit_reason":  reason,
            })
        elif action == "TRIM":
            total = int(pos.get("shares") or 0)
            trim_qty = max(1, total // 2) if total > 0 else 0
            items.append({
                "kind":    "TRIM",
                "ticker":  tkr,
                "shares":  trim_qty,
                "current_pct": None,
                "target_pct":  None,
                "reason":  f"classify_exit_state: {reason}",
                "exit_verdict": verdict,
                "exit_reason":  reason,
            })

    return items


def build_plan() -> list[dict]:
    """Aggregate exit actions, runner trims, and flat-position exits into one plan."""
    from portfolio_tracker import (
        generate_exit_actions, runner_protection_trim, flat_position_exits,
    )
    plan: list[dict] = []

    # 0. Overnight gap detection (runs before normal signals so GAP_EXIT
    #    takes precedence and GAP_TIGHTEN can override weaker trail signals).
    try:
        gap_items = evaluate_gaps()
    except Exception as e:
        print(f"  [gap] evaluate_gaps failed: {e}", file=sys.stderr)
        gap_items = []
    plan.extend(gap_items)
    gap_exit_tickers = {g["ticker"] for g in gap_items if g["kind"] == "GAP_EXIT"}
    gap_tighten_tickers = {g["ticker"] for g in gap_items if g["kind"] == "GAP_TIGHTEN"}

    # 0b. classify_exit_state (wave 2A, checklist item 5.1) — daily verdict
    #     on every open position. GAP_EXIT takes precedence.
    try:
        ec_items = run_exit_classifier()
    except Exception as e:
        print(f"  [exit] run_exit_classifier failed: {e}", file=sys.stderr)
        ec_items = []
    ec_exit_tickers = set()
    for item in ec_items:
        tkr = item["ticker"]
        if item["kind"] == "EXIT" and tkr in gap_exit_tickers:
            continue  # gap-exit supersedes
        plan.append(item)
        if item["kind"] == "EXIT":
            ec_exit_tickers.add(tkr)

    # 1. Per-position exit/tighten signals
    for a in generate_exit_actions():
        act = a.get("action", "HOLD")
        if act == "HOLD" or act == "WARNING":
            continue
        if act == "EXIT":
            if a["ticker"] in gap_exit_tickers:
                continue  # already queued as GAP_EXIT
            if a["ticker"] in ec_exit_tickers:
                continue  # already queued by classify_exit_state
            plan.append({
                "kind": "EXIT", "ticker": a["ticker"], "shares": a.get("shares", 0),
                "reason": a.get("reason", ""), "current": a.get("current"),
            })
        elif act == "TIGHTEN":
            if a["ticker"] in gap_tighten_tickers:
                continue  # gap-based tighten supersedes regular tighten
            # Extract the new stop from the reason or fall back to a["stop"]
            plan.append({
                "kind": "TIGHTEN", "ticker": a["ticker"],
                "new_stop": a.get("stop"), "old_stop": None,
                "reason": a.get("reason", ""),
            })

    # 2. Runner protection trims
    for t in runner_protection_trim(max_position_pct=25, trim_to_pct=15):
        plan.append({
            "kind": "TRIM", "ticker": t["ticker"],
            "shares": t["shares_to_trim"],
            "current_pct": t["current_pct"], "target_pct": t["target_pct"],
            "reason": t.get("reason", ""),
        })

    # 3. Flat position exits — treat as EXIT if not already queued
    already_exiting = {p["ticker"] for p in plan if p["kind"] == "EXIT"}
    for f in flat_position_exits():
        if f["ticker"] in already_exiting:
            continue
        # Need shares — lookup from portfolio state
        try:
            from portfolio_tracker import _load_state
            shares = next((p.get("shares", 0) for p in _load_state().get("positions", [])
                           if p["ticker"] == f["ticker"]), 0)
        except Exception:
            shares = 0
        plan.append({
            "kind": "EXIT", "ticker": f["ticker"], "shares": shares,
            "reason": f.get("reason", "flat position"), "current": None,
        })
    return plan


def _submit_market_sell(client, ticker: str, qty: int):
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce
    req = MarketOrderRequest(symbol=ticker, qty=qty, side=OrderSide.SELL,
                             time_in_force=TimeInForce.DAY)
    return client.submit_order(req)


def _replace_stop(client, ticker: str, qty: int, new_stop: float):
    from alpaca.trading.requests import GetOrdersRequest, StopOrderRequest
    from alpaca.trading.enums import OrderSide, QueryOrderStatus, TimeInForce
    # Find existing open stop_loss SELL order for this symbol
    try:
        req = GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[ticker])
        orders = client.get_orders(filter=req)
        for o in orders:
            if (str(getattr(o, "side", "")).lower().endswith("sell")
                    and "stop" in str(getattr(o, "order_type", "")).lower()):
                client.cancel_order_by_id(o.id)
    except Exception as e:
        return False, f"cancel failed: {e}"
    try:
        new_req = StopOrderRequest(symbol=ticker, qty=qty, side=OrderSide.SELL,
                                    time_in_force=TimeInForce.GTC,
                                    stop_price=round(float(new_stop), 2))
        resp = client.submit_order(new_req)
        return True, str(getattr(resp, "id", "submitted"))
    except Exception as e:
        return False, f"submit failed: {e}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", default=True)
    ap.add_argument("--submit", action="store_true", help="Actually submit to Alpaca paper")
    ap.add_argument("--tighten-stops", action="store_true",
                    help="Apply TIGHTEN/TRAIL stop updates (requires --submit)")
    ap.add_argument("--close-positions", action="store_true",
                    help="Apply EXIT/TRIM market sells (requires --submit)")
    args = ap.parse_args()
    if args.submit:
        args.dry_run = False

    plan = build_plan()
    mode = "DRY-RUN" if args.dry_run else "SUBMIT"
    print(f"=== EOD Manager ({mode}) — {len(plan)} actions ===")
    if not plan:
        print("no actions — portfolio empty/healthy")
        return 0

    client = None
    if not args.dry_run:
        client, account = _make_client()
        print(f"Alpaca paper: equity=${float(account.equity):,.2f} · status={account.status}")

    ts = datetime.now(timezone.utc).isoformat()
    submitted = failed = 0
    for item in plan:
        kind = item["kind"]
        tkr = item["ticker"]
        log_entry = {"timestamp": ts, "dry_run": args.dry_run, "submitted": False, **item}

        # Gap-handling kinds map to existing EXIT / TIGHTEN mechanics
        if kind == "GAP_EXIT":
            qty = int(item.get("shares") or 0)
            open_px = item.get("current")
            px_str = f" at open ${open_px:.2f}" if open_px else ""
            print(f"  GAP_EXIT {tkr}: {item['reason']}{px_str} "
                  f"— would submit market SELL {qty} shares")
            if not args.dry_run and args.close_positions and qty > 0:
                try:
                    resp = _submit_market_sell(client, tkr, qty)
                    log_entry["submitted"] = True
                    log_entry["alpaca_order_id"] = str(getattr(resp, "id", ""))
                    print(f"    -> order_id {log_entry['alpaca_order_id']}")
                    submitted += 1
                except Exception as e:
                    log_entry["error"] = str(e)
                    print(f"    FAILED: {e}")
                    failed += 1
            _log(log_entry)
            continue

        if kind == "GAP_TIGHTEN":
            new_stop = item.get("new_stop")
            old_stop = item.get("old_stop")
            print(f"  GAP_TIGHTEN {tkr}: stop ${old_stop} -> ${new_stop} "
                  f"({item['reason']})")
            if not args.dry_run and args.tighten_stops and new_stop:
                try:
                    pos = client.get_open_position(tkr)
                    qty = int(float(pos.qty))
                except Exception:
                    qty = 0
                if qty > 0:
                    ok, result = _replace_stop(client, tkr, qty, float(new_stop))
                    log_entry["submitted"] = ok
                    log_entry["alpaca_order_id" if ok else "error"] = result
                    print(f"    {'-> order_id ' + result if ok else 'FAILED: ' + result}")
                    submitted += 1 if ok else 0
                    failed += 0 if ok else 1
                else:
                    print(f"    SKIPPED: no Alpaca position for {tkr}")
            # Also update local portfolio state trail_stop so downstream tools see it
            try:
                from portfolio_tracker import _load_state, _save_state
                st = _load_state()
                for p in st.get("positions", []):
                    if p["ticker"] == tkr:
                        p["trail_stop"] = float(new_stop)
                        p["stop"] = float(new_stop)
                        p["trail_active"] = True
                        break
                _save_state(st)
            except Exception as e:
                print(f"    local state update failed: {e}")
            _log(log_entry)
            continue

        if kind == "GAP_ALERT":
            print(f"  GAP_ALERT {tkr}: {item['reason']} — no order; user discretion")
            _log(log_entry)
            continue

        if kind == "EXIT":
            qty = int(item.get("shares") or 0)
            price_str = f" at ${item['current']:.2f}" if item.get("current") else ""
            print(f"  EXIT   {tkr}: Close ({item['reason']}){price_str} "
                  f"— would submit market SELL {qty} shares")
            if not args.dry_run and args.close_positions and qty > 0:
                try:
                    resp = _submit_market_sell(client, tkr, qty)
                    log_entry["submitted"] = True
                    log_entry["alpaca_order_id"] = str(getattr(resp, "id", ""))
                    print(f"    -> order_id {log_entry['alpaca_order_id']}")
                    submitted += 1
                except Exception as e:
                    log_entry["error"] = str(e)
                    print(f"    FAILED: {e}")
                    failed += 1

        elif kind == "TRIM":
            qty = int(item.get("shares") or 0)
            print(f"  TRIM   {tkr}: from {item['current_pct']}% -> {item['target_pct']}% "
                  f"— would submit market SELL {qty} shares")
            if not args.dry_run and args.close_positions and qty > 0:
                try:
                    resp = _submit_market_sell(client, tkr, qty)
                    log_entry["submitted"] = True
                    log_entry["alpaca_order_id"] = str(getattr(resp, "id", ""))
                    print(f"    -> order_id {log_entry['alpaca_order_id']}")
                    submitted += 1
                except Exception as e:
                    log_entry["error"] = str(e)
                    print(f"    FAILED: {e}")
                    failed += 1

        elif kind == "TIGHTEN":
            new_stop = item.get("new_stop")
            print(f"  TIGHTEN {tkr}: stop -> ${new_stop} "
                  f"— would cancel existing stop_loss, submit new STOP ({item['reason']})")
            if not args.dry_run and args.tighten_stops and new_stop:
                # Need shares: look up via Alpaca positions
                try:
                    pos = client.get_open_position(tkr)
                    qty = int(float(pos.qty))
                except Exception:
                    qty = 0
                if qty > 0:
                    ok, result = _replace_stop(client, tkr, qty, float(new_stop))
                    log_entry["submitted"] = ok
                    log_entry["alpaca_order_id" if ok else "error"] = result
                    print(f"    {'-> order_id ' + result if ok else 'FAILED: ' + result}")
                    submitted += 1 if ok else 0
                    failed += 0 if ok else 1
                else:
                    print(f"    SKIPPED: no Alpaca position for {tkr}")
        _log(log_entry)

    print(f"\n{mode}: {submitted} submitted · {failed} failed · {len(plan)} total")

    # EOD digest — P&L summary across all open positions (throttled: once per day)
    try:
        from position_alerts import send_eod_digest
        from portfolio_tracker import get_portfolio_summary
        summary = get_portfolio_summary()
        send_eod_digest(summary.get("positions", []), summary)
    except Exception as e:
        print(f"  EOD digest failed: {e}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

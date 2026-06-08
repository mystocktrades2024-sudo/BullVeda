#!/usr/bin/env python3
"""
options_executor.py — Options auto-buy (paper, defined-risk) — the translation layer.

Maps the engine's directional EQUITY BUY signals into a defined-risk options
expression (long call MVP) and submits it to the Alpaca PAPER account.

This is OPT-PAPER-1/2/3 from docs/scope_options_paper.md:
  1. Signal -> structure   (long call; debit-spread is a future extension)
  2. Contract selection    (DTE window + slightly-ITM strike from Alpaca chain)
  3. Alpaca paper order     (single-leg long call LimitOrder)

HARD CONSTRAINTS (non-negotiable):
  - PAPER ONLY. Reuses executor._make_client() which pins paper=True; we also
    re-assert config.alpaca.paper before any --submit.
  - DEFINED-RISK ONLY. Long calls (max loss = premium paid). No naked/short legs.
  - PREMIUM-AT-RISK <= options_auto_buy.premium_risk_pct of equity per name.
  - GATED OFF by default: config.options_auto_buy._enabled must be true to submit.

Usage:
  python3 options_executor.py --dry-run     # preview structures (default)
  python3 options_executor.py --submit      # paper-submit (requires _enabled=true)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

# Reuse the equity executor's vetted plumbing (paper-pinned client, bundle load,
# order log, Slack). We do NOT touch its equity path.
import executor as _eq

_ROOT = Path(__file__).parent
_OPT_LOG = _ROOT / "cache" / "logs" / "options_orders.jsonl"


# ────────────────────────── config ──────────────────────────
def _opt_cfg(cfg: dict) -> dict:
    """options_auto_buy block with crash-safe defaults (all conservative)."""
    blk = (cfg or {}).get("options_auto_buy", {}) or {}
    return {
        "_enabled":             bool(blk.get("_enabled", False)),
        "structure":            str(blk.get("structure", "long_call")),
        "min_dte":              int(blk.get("min_dte", 30)),
        "max_dte":              int(blk.get("max_dte", 45)),
        "itm_pct":              float(blk.get("itm_pct", 0.03)),   # target strike ~3% ITM (≈delta 0.62-0.68)
        "strike_window_pct":    float(blk.get("strike_window_pct", 0.08)),
        "premium_risk_pct":     float(blk.get("premium_risk_pct", 1.0)),  # <=1% equity premium-at-risk
        "max_contracts_per_name": int(blk.get("max_contracts_per_name", 10)),
        "max_new_positions":    int(blk.get("max_new_positions", 3)),
        "min_premium":          float(blk.get("min_premium", 0.20)),  # skip illiquid sub-20c
        "limit_slippage_pct":   float(blk.get("limit_slippage_pct", 0.02)),  # marketable limit = ask*(1+x)
        # ── liquidity / quote-sanity guards (reject stale/wide/garbage quotes) ──
        "max_spread_ratio":     float(blk.get("max_spread_ratio", 1.6)),   # skip if ask > bid * this
        "max_time_value_pct":   float(blk.get("max_time_value_pct", 0.35)),  # skip if (ask-intrinsic) > spot*this
        # ── small-mode sizing ──
        "fixed_contracts":      int(blk.get("fixed_contracts", 0)),        # 0 = %-sized; N = always N contracts/name
        "max_premium_per_contract": float(blk.get("max_premium_per_contract", 750)),  # absolute $ cap per contract (keeps it small)
    }


# ────────────────────── Alpaca options data ─────────────────────
def _data_client():
    from alpaca.data.historical.option import OptionHistoricalDataClient
    from secrets_loader import alpaca_key, alpaca_secret
    return OptionHistoricalDataClient(alpaca_key(), alpaca_secret())


def _latest_premium(data_client, occ_symbol: str) -> dict | None:
    """Return {'ask','bid','mid'} for an OCC option symbol, or None."""
    try:
        from alpaca.data.requests import OptionLatestQuoteRequest
        q = data_client.get_option_latest_quote(
            OptionLatestQuoteRequest(symbol_or_symbols=[occ_symbol])
        )
        qd = q.get(occ_symbol)
        if not qd:
            return None
        ask = float(getattr(qd, "ask_price", 0) or 0)
        bid = float(getattr(qd, "bid_price", 0) or 0)
        if ask <= 0 and bid <= 0:
            return None
        mid = (ask + bid) / 2 if (ask > 0 and bid > 0) else (ask or bid)
        return {"ask": ask, "bid": bid, "mid": round(mid, 2)}
    except Exception:
        return None


def _select_call_contract(trade_client, data_client, ticker: str, spot: float,
                          o: dict) -> dict | None:
    """OPT-PAPER-2 — pick a slightly-ITM long call in the DTE window.

    Returns {symbol, strike, expiry, dte, ask, mid} or None if no good contract.
    """
    try:
        from alpaca.trading.requests import GetOptionContractsRequest
        try:
            from alpaca.trading.enums import ContractType, AssetStatus
            _call = ContractType.CALL
            _active = AssetStatus.ACTIVE
        except Exception:
            _call, _active = "call", "active"

        today = date.today()
        target_strike = spot * (1.0 - o["itm_pct"])          # ~3% ITM
        lo = spot * (1.0 - o["strike_window_pct"] - o["itm_pct"])
        hi = spot * (1.0 + o["strike_window_pct"])
        req = GetOptionContractsRequest(
            underlying_symbols=[ticker],
            type=_call,
            status=_active,
            expiration_date_gte=(today + timedelta(days=o["min_dte"])).isoformat(),
            expiration_date_lte=(today + timedelta(days=o["max_dte"])).isoformat(),
            strike_price_gte=str(round(lo, 2)),
            strike_price_lte=str(round(hi, 2)),
            limit=200,
        )
        resp = trade_client.get_option_contracts(req)
        contracts = list(getattr(resp, "option_contracts", None) or [])
        if not contracts:
            return None

        # Rank by closeness to (target strike) then nearest-to-min_dte expiry.
        def _key(c):
            strike = float(getattr(c, "strike_price", 0) or 0)
            exp = getattr(c, "expiration_date", None)
            dte = (exp - today).days if exp else 999
            return (abs(strike - target_strike), abs(dte - o["min_dte"]))
        contracts.sort(key=_key)

        # Walk the ranked list, take the first with a live, LIQUID, SANE quote.
        # Garbage one-sided / stale quotes (common after hours) must be rejected —
        # sizing on a bad ask either oversizes risk or buys at a terrible price.
        for c in contracts[:12]:
            occ = getattr(c, "symbol", None)
            if not occ:
                continue
            prem = _latest_premium(data_client, occ)
            if not prem:
                continue
            ask, bid = prem["ask"], prem["bid"]
            strike = float(getattr(c, "strike_price", 0) or 0)
            # (1) two-sided + min premium
            if ask < o["min_premium"] or bid <= 0:
                continue
            # (2) spread guard — wide market = stale/illiquid
            if ask > bid * o["max_spread_ratio"]:
                continue
            # (3) intrinsic sanity — a call can't sanely cost more than spot, and
            #     time-value beyond spot*max_tv_pct for 30-45 DTE is a broken quote
            intrinsic = max(0.0, spot - strike)
            if ask >= spot or (ask - intrinsic) > spot * o["max_time_value_pct"]:
                continue
            exp = getattr(c, "expiration_date", None)
            return {
                "symbol": occ,
                "strike": strike,
                "expiry": exp.isoformat() if exp else None,
                "dte": (exp - today).days if exp else None,
                "ask": ask,
                "mid": prem["mid"],
            }
        return None
    except Exception as e:
        _eq._log_order  # touch to keep import meaningful
        print(f"   ! contract-select {ticker}: {e}")
        return None


# ─────────────────────── plan + submit ───────────────────────
def build_options_plan(picks: list[dict], equity: float, cfg: dict,
                       existing_underlyings: set[str],
                       trade_client, data_client) -> list[dict]:
    """OPT-PAPER-1 — map each equity BUY into a defined-risk long-call ticket."""
    o = _opt_cfg(cfg)
    plan: list[dict] = []
    budget_per_name = equity * (o["premium_risk_pct"] / 100.0)
    opened = 0
    for pk in picks:
        ticker = pk.get("ticker", "")
        if not ticker:
            continue
        verdict = (pk.get("decision") or {}).get("verdict", "") or pk.get("verdict", "")
        direction = (pk.get("direction") or (pk.get("trade_plan") or {}).get("direction") or "long").lower()
        if verdict and verdict.upper() != "BUY":
            plan.append({"ticker": ticker, "action": "skip", "reason": f"verdict {verdict} (BUY-only)"}); continue
        if direction == "short":
            plan.append({"ticker": ticker, "action": "skip", "reason": "short — no defined-risk long-call expression"}); continue
        if ticker in existing_underlyings:
            plan.append({"ticker": ticker, "action": "skip", "reason": "already hold options/equity on this name"}); continue
        if opened >= o["max_new_positions"]:
            plan.append({"ticker": ticker, "action": "skip", "reason": f"max_new_positions {o['max_new_positions']} reached"}); continue
        spot = float(pk.get("price") or (pk.get("trade_plan") or {}).get("entry_low") or 0)
        if spot <= 0:
            plan.append({"ticker": ticker, "action": "skip", "reason": "no spot price"}); continue

        contract = _select_call_contract(trade_client, data_client, ticker, spot, o)
        if not contract:
            plan.append({"ticker": ticker, "action": "skip", "reason": "no liquid call in DTE/strike window (or not optionable)"}); continue

        per_contract_cost = contract["ask"] * 100.0
        if o["fixed_contracts"]:
            # SMALL MODE — always exactly N contracts/name (default 1), bounded by an
            # absolute $ cap so a single contract can never be large.
            n = min(o["fixed_contracts"], o["max_contracts_per_name"])
            if per_contract_cost > o["max_premium_per_contract"]:
                plan.append({"ticker": ticker, "action": "skip",
                             "reason": f"1 contract (${per_contract_cost:,.0f}) > max_premium_per_contract (${o['max_premium_per_contract']:,.0f})"}); continue
        else:
            # %-sized: contracts * premium * 100 <= premium-at-risk budget.
            n = min(int(budget_per_name // per_contract_cost), o["max_contracts_per_name"])
            if n < 1:
                plan.append({"ticker": ticker, "action": "skip",
                             "reason": f"1 contract (${per_contract_cost:,.0f}) > {o['premium_risk_pct']}% budget (${budget_per_name:,.0f})"}); continue

        limit = round(contract["ask"] * (1.0 + o["limit_slippage_pct"]), 2)
        premium_at_risk = round(n * contract["ask"] * 100.0, 2)
        plan.append({
            "ticker": ticker,
            "action": "order",
            "structure": "long_call",
            "occ_symbol": contract["symbol"],
            "strike": contract["strike"],
            "expiry": contract["expiry"],
            "dte": contract["dte"],
            "spot": round(spot, 2),
            "contracts": n,
            "ask": contract["ask"],
            "limit_price": limit,
            "premium_at_risk": premium_at_risk,
            "premium_risk_pct": round(100 * premium_at_risk / max(equity, 1), 2),
            "score": pk.get("score"),
            "setup": (pk.get("trade_plan") or {}).get("setup_type", ""),
            "underlying_stop": (pk.get("trade_plan") or {}).get("stop"),  # thesis invalidation
        })
        opened += 1
    return plan


def submit_call(trade_client, order: dict) -> tuple[bool, str]:
    """OPT-PAPER-3 — submit a single-leg long-call LimitOrder (paper)."""
    try:
        from alpaca.trading.requests import LimitOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce
        req = LimitOrderRequest(
            symbol=order["occ_symbol"],
            qty=order["contracts"],
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
            limit_price=order["limit_price"],
        )
        resp = trade_client.submit_order(req)
        oid = str(getattr(resp, "id", "submitted"))
        # Per-order Slack omitted — a single consolidated morning summary is posted
        # by _post_buy_summary() at the end of the run (see main()).
        return True, oid
    except Exception as e:
        return False, str(e)


def _post_buy_summary(filled: list[dict], attempted: list[dict], skips: list[dict]) -> None:
    """One consolidated Slack post per morning options auto-buy run."""
    try:
        if filled:
            total = sum(p.get("premium_at_risk", 0) for p in filled)
            lines = "\n".join(
                f"• {p['ticker']} 1x ${p['strike']:.0f}C {p['expiry']} ({p['dte']}DTE) "
                f"@ ${p['limit_price']:.2f} · risk ${p['premium_at_risk']:,.0f}"
                for p in filled
            )
            msg = (f"📈 *Options auto-buy (paper)* — {len(filled)}/{len(attempted)} filled · "
                   f"${total:,.0f} total premium-at-risk\n{lines}")
        elif attempted:
            failed = ", ".join(f"{p['ticker']} ({p.get('error','?')})" for p in attempted)
            msg = f"📈 *Options auto-buy (paper)* — 0 filled · {len(attempted)} attempted, all failed: {failed}"
        else:
            msg = (f"📈 *Options auto-buy (paper)* — no fills today "
                   f"({len(skips)} candidate(s) skipped: too pricey / illiquid / no BUYs)")
        _eq._slack_notify(msg)
    except Exception:
        pass


def _log(entry: dict) -> None:
    _OPT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with _OPT_LOG.open("a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


# ────────────────────────────── main ──────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description="Options auto-buy (paper, defined-risk)")
    ap.add_argument("--bundle", default=str(_ROOT / "cache" / "last_bundle.json"))
    ap.add_argument("--dry-run", action="store_true", default=True)
    ap.add_argument("--submit", dest="dry_run", action="store_false")
    ap.add_argument("--filter", default="BUY")
    args = ap.parse_args()

    cfg = json.loads((_ROOT / "config" / "config.json").read_text())
    o = _opt_cfg(cfg)

    # ── submit-path hard guards (asserted FIRST, before any work) ──
    if not args.dry_run:
        if (_ROOT / "cache" / "AUTOMATION_HALT").exists():
            print("REFUSING --submit: cache/AUTOMATION_HALT present (kill-switch active)."); return 0
        if not o["_enabled"]:
            print("REFUSING --submit: config.options_auto_buy._enabled is false (gated OFF).")
            print("Flip it to true to go live-on-paper. Staying inert.")
            return 0
        if not (cfg.get("alpaca", {}).get("paper", True)):
            print("REFUSING: config.alpaca.paper is not True. Options auto-buy is PAPER ONLY."); return 1
        try:
            _clk = _eq._make_client()[0].get_clock()
            if not getattr(_clk, "is_open", False):
                print("REFUSING --submit: market is CLOSED (option quotes stale). Run during RTH."); return 0
        except Exception as _e:
            print(f"REFUSING --submit: could not confirm market open ({_e})."); return 0

    # Load BUY picks (same contract as the equity executor).
    bundle = _eq._load_bundle(args.bundle)
    picks: list[dict] = []
    for key in ("buy_candidates", "top_picks", "buy_list"):
        if isinstance(bundle.get(key), list):
            picks = bundle[key]; break
    if not picks and isinstance(bundle.get("all_scored"), list):
        verdicts = [v.strip().upper() for v in args.filter.split(",")]
        picks = [r for r in bundle["all_scored"]
                 if (r.get("decision") or {}).get("verdict", "") in verdicts]
    if not picks:
        print("No BUY picks in bundle. Nothing to do.")
        if not args.dry_run:
            _post_buy_summary([], [], [])  # confirm the job ran on a quiet day
        return 0

    mode = "DRY-RUN" if args.dry_run else "SUBMIT"
    print(f"=== Options Executor ({mode}) — {len(picks)} BUY picks · structure={o['structure']} ===")
    print(f"    gate: options_auto_buy._enabled = {o['_enabled']} · premium-at-risk ≤{o['premium_risk_pct']}%/name · DTE {o['min_dte']}-{o['max_dte']}")

    # client + equity
    trade_client = None
    data_client = _data_client()
    existing: set[str] = set()
    if not args.dry_run:
        trade_client, account = _eq._make_client()   # paper-pinned
        equity = float(account.equity)
        existing = _eq._existing_position_tickers(trade_client)
        print(f"Alpaca paper: equity=${equity:,.2f} · existing names={len(existing)}")
    else:
        equity = float(cfg.get("portfolio", {}).get("account_equity", 5000))
        # dry-run still needs a trade_client for the (read-only) contract lookup
        try:
            trade_client, _ = _eq._make_client()
        except Exception as e:
            print(f"(dry-run) could not init Alpaca read client: {e}"); return 1
        print(f"Dry-run: using equity=${equity:,.2f}")

    plan = build_options_plan(picks, equity, cfg, existing, trade_client, data_client)
    orders = [p for p in plan if p["action"] == "order"]
    skips = [p for p in plan if p["action"] == "skip"]

    print(f"\n— {len(orders)} option ticket(s), {len(skips)} skipped —")
    for p in orders:
        print(f"  ✓ {p['ticker']:6} {p['contracts']}x ${p['strike']:.0f}C {p['expiry']} ({p['dte']}DTE) "
              f"@ ${p['limit_price']:.2f}  risk ${p['premium_at_risk']:,.0f} ({p['premium_risk_pct']}%)  {p['occ_symbol']}")
    for p in skips[:12]:
        print(f"  · skip {p['ticker']:6} — {p['reason']}")

    if args.dry_run:
        print("\nDRY-RUN — no orders submitted. Use --submit (requires _enabled=true) to paper-execute.")
        return 0

    submitted = 0
    for p in orders:
        ok, info = submit_call(trade_client, p)
        p["submitted"] = ok; p["order_id" if ok else "error"] = info
        _log(p)
        print(("  ✅ " if ok else "  ❌ ") + f"{p['ticker']} {p['occ_symbol']} → {info}")
        submitted += int(ok)
    print(f"\nSubmitted {submitted}/{len(orders)} option orders (paper).")
    _post_buy_summary([p for p in orders if p.get("submitted")], orders, skips)
    return 0


if __name__ == "__main__":
    sys.exit(main())

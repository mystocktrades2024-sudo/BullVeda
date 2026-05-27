#!/usr/bin/env python3
"""
options_flow_outcomes.py — Daily/scheduled outcome tracker for options-flow picks.

Reads cache/options_flow_history.jsonl (one line per pick logged by
refresh_options_flow.py at snapshot time) and walks each pick's price
history after the pick date to determine the realized outcome:

  - target_hit  : price >= target within HORIZON_DAYS (default 21)
  - stop_hit    : price <= stop within horizon (only counts if hit BEFORE target)
  - expired     : neither — pick stays open past horizon, treat as flat
  - open        : not enough days elapsed yet (snap_date + horizon > today)

Computes per-pick:
  - outcome (str)
  - days_to_outcome (int)
  - realized_return_pct (final close vs entry price)
  - mfe_pct  (max favorable excursion)
  - mae_pct  (max adverse excursion)

Writes cache/options_flow_outcomes.jsonl (append-only; idempotent — skips
picks already resolved).

Run via launchd nightly OR on-demand:
    python3 scripts/options_flow_outcomes.py [--horizon 21] [--rebuild]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))


def _load_history(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def _load_outcomes(path: Path) -> dict:
    """key = snap_date + '|' + ticker → outcome row."""
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            k = (row.get("snap_date") or "") + "|" + (row.get("ticker") or "")
            out[k] = row
        except Exception:
            continue
    return out


def _norm_cdf(x: float) -> float:
    """Cumulative normal distribution via erf — no scipy dependency."""
    import math
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _bsm_price(S: float, K: float, sigma: float, T_years: float,
               r: float = 0.05, is_call: bool = True) -> float:
    """Black-Scholes-Merton European option price. Returns 0 for expired/invalid."""
    import math
    if T_years <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        # Expired → intrinsic value
        return max(S - K, 0.0) if is_call else max(K - S, 0.0)
    d1 = (math.log(S / K) + (r + sigma * sigma / 2) * T_years) / (sigma * math.sqrt(T_years))
    d2 = d1 - sigma * math.sqrt(T_years)
    if is_call:
        return S * _norm_cdf(d1) - K * math.exp(-r * T_years) * _norm_cdf(d2)
    return K * math.exp(-r * T_years) * _norm_cdf(-d2) - S * _norm_cdf(-d1)


def _compute_option_r(pick: dict, exit_spot: float, days_to_outcome: int) -> dict:
    """Compute option-trade premium-based R using BSM on entry + exit.

    Honest single-leg approximation:
      · Long Call (bull) at entry; same contract priced at exit.
      · Long Put (bear) symmetric.
      · For Bull/Bear *Spread* picks the real PnL is capped vs single-leg, but
        we don't carry the second strike. Spread approx ≈ 0.65× of single-leg
        return-pct (debit spread typical haircut). Mark conservatively.

    Requires snapshot to have: atm_strike, atm_iv, atm_dte. If any missing,
    returns null fields and the caller falls back to spot-equivalent R.
    """
    K  = pick.get("atm_strike")
    iv = pick.get("atm_iv")
    dte_entry = pick.get("atm_dte")
    entry_spot = pick.get("price")
    if K is None or iv is None or dte_entry is None or not entry_spot:
        return {"option_entry_prem": None, "option_exit_prem": None,
                "option_realized_pct": None, "option_realized_r": None}
    try:
        K  = float(K)
        iv = float(iv)  # already fraction (post-fix)
        dte_entry = float(dte_entry)
        entry_spot = float(entry_spot)
        days_to_outcome = float(days_to_outcome or 0)
    except Exception:
        return {"option_entry_prem": None, "option_exit_prem": None,
                "option_realized_pct": None, "option_realized_r": None}
    is_call = (pick.get("direction") or "long").lower() == "long"
    # Entry premium — full DTE
    T_entry = dte_entry / 365.0
    entry_prem = _bsm_price(entry_spot, K, iv, T_entry, is_call=is_call)
    # Exit premium — remaining DTE
    T_exit = max(0, (dte_entry - days_to_outcome)) / 365.0
    exit_prem = _bsm_price(exit_spot, K, iv, T_exit, is_call=is_call)
    if entry_prem <= 0:
        return {"option_entry_prem": round(entry_prem, 2),
                "option_exit_prem":  round(exit_prem, 2),
                "option_realized_pct": None, "option_realized_r": None}
    # Single-leg return
    raw_pct = (exit_prem - entry_prem) / entry_prem * 100
    # Spread haircut: if strategy is a defined-risk debit spread, the realized
    # return is capped. Approximate by scaling raw single-leg return × 0.65.
    strategy = (pick.get("strategy") or "").lower()
    is_spread = "spread" in strategy
    final_pct = raw_pct * 0.65 if is_spread else raw_pct
    # Option-trade R = (premium delta) / (entry premium at risk).
    # For long premium, R = realized_pct / 100 (loss capped at -100%).
    realized_r = round(final_pct / 100, 3)
    return {
        "option_entry_prem":   round(entry_prem, 2),
        "option_exit_prem":    round(exit_prem,  2),
        "option_realized_pct": round(final_pct, 2),
        "option_realized_r":   realized_r,
    }


def _resolve_outcome(pick: dict, bars: list, horizon_days: int) -> dict | None:
    """Walk OHLCV bars from snap_date forward up to horizon_days. Return outcome."""
    entry = float(pick.get("price") or 0)
    target = float(pick.get("target") or 0)
    stop = float(pick.get("stop") or 0)
    if not entry or not target or not stop:
        return None
    snap_date = pick.get("snap_date") or ""
    if not snap_date:
        return None
    # Filter bars after snap_date, sorted asc
    forward = sorted(
        [b for b in bars if isinstance(b, dict) and (b.get("date") or "") > snap_date],
        key=lambda x: x.get("date") or ""
    )[:horizon_days]
    if not forward:
        return {"outcome": "open", "days_elapsed": 0}
    mfe = 0.0  # max favorable
    mae = 0.0  # max adverse
    outcome = None
    days_to = None
    last_close = entry
    exit_spot = entry  # spot price where the outcome triggered
    for i, bar in enumerate(forward):
        h = float(bar.get("high") or 0)
        l = float(bar.get("low") or 0)
        c = float(bar.get("close") or 0)
        if h > 0:
            mfe = max(mfe, (h - entry) / entry * 100)
        if l > 0:
            mae = min(mae, (l - entry) / entry * 100)
        # Check stop first (conservative — if both touched in same session, stop counts)
        if stop > 0 and l > 0 and l <= stop and outcome is None:
            outcome = "stop_hit"
            days_to = i + 1
            exit_spot = stop
        # Then target
        if target > 0 and h > 0 and h >= target and outcome is None:
            outcome = "target_hit"
            days_to = i + 1
            exit_spot = target
        last_close = c or last_close
        if outcome:
            break
    if outcome is None:
        # No level touched in horizon — treat as expired
        if len(forward) >= horizon_days:
            outcome = "expired"
            days_to = horizon_days
            exit_spot = last_close
        else:
            outcome = "open"
            days_to = len(forward)
            exit_spot = last_close
    realized_return = (last_close - entry) / entry * 100 if entry else 0.0
    out = {
        "outcome": outcome,
        "days_to_outcome": days_to,
        "realized_return_pct": round(realized_return, 2),
        "mfe_pct": round(mfe, 2),
        "mae_pct": round(mae, 2),
        "horizon_days": horizon_days,
        "exit_spot": round(exit_spot, 2),
    }
    # 2026-05-26 · OPTIONS-FINAL-4-PART-2 · BSM option-trade R when snapshot has
    # the option-fields (atm_strike/atm_iv/atm_dte). For pre-2026-05-26 backfill
    # rows these are absent; the fallback returns null and the journal/UI
    # gracefully degrades to spot-equivalent R.
    out.update(_compute_option_r(pick, exit_spot, days_to or 0))
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, default=21,
                        help="Days to wait before declaring 'expired' (default 21)")
    parser.add_argument("--rebuild", action="store_true",
                        help="Re-resolve already-tracked outcomes (default skips)")
    parser.add_argument("--max-age-days", type=int, default=180,
                        help="Skip picks older than this (default 180)")
    args = parser.parse_args()

    hist_path = BASE / "cache" / "options_flow_history.jsonl"
    out_path = BASE / "cache" / "options_flow_outcomes.jsonl"

    history = _load_history(hist_path)
    if not history:
        print(f"No history at {hist_path} — nothing to resolve")
        return 0

    existing = _load_outcomes(out_path) if not args.rebuild else {}
    print(f"Loaded {len(history)} history rows, {len(existing)} already resolved")

    # Group picks by ticker so we fetch OHLCV once per ticker
    by_ticker: dict[str, list[dict]] = {}
    for p in history:
        tk = (p.get("ticker") or "").upper()
        if not tk: continue
        # Skip already-resolved picks unless rebuild
        k = (p.get("snap_date") or "") + "|" + tk
        if k in existing and existing[k].get("outcome") not in ("open", None):
            continue
        # Skip too-old picks
        try:
            d = datetime.strptime(p.get("snap_date") or "", "%Y-%m-%d")
            if (datetime.now() - d).days > args.max_age_days: continue
        except Exception:
            continue
        by_ticker.setdefault(tk, []).append(p)

    print(f"To resolve: {sum(len(v) for v in by_ticker.values())} picks across {len(by_ticker)} tickers")

    try:
        import eodhd_client as eod
    except ImportError:
        print("ERROR: eodhd_client not importable")
        return 1

    resolved_rows = []
    today = datetime.now().strftime("%Y-%m-%d")
    for tk, picks in by_ticker.items():
        earliest = min(p.get("snap_date") or today for p in picks)
        try:
            bars = eod.eod(tk, from_date=earliest, to_date=today, period="d") or []
        except Exception as e:
            print(f"  {tk}: eod fetch failed — {type(e).__name__}: {str(e)[:80]}")
            continue
        if not bars:
            continue
        for p in picks:
            res = _resolve_outcome(p, bars, args.horizon)
            if not res: continue
            row = {**p, **res, "resolved_at": datetime.now(timezone.utc).isoformat()}
            resolved_rows.append(row)

    # Append-only write — re-write the whole file with non-stale + new rows
    print(f"Resolved {len(resolved_rows)} picks")
    if resolved_rows:
        all_rows = list(existing.values()) if not args.rebuild else []
        for r in resolved_rows:
            k = (r.get("snap_date") or "") + "|" + (r.get("ticker") or "")
            # Drop any prior version of this key
            all_rows = [x for x in all_rows
                        if (x.get("snap_date") or "") + "|" + (x.get("ticker") or "") != k]
            all_rows.append(r)
        all_rows.sort(key=lambda x: (x.get("snap_date") or "", x.get("ticker") or ""))
        out_path.write_text("\n".join(json.dumps(r, default=str) for r in all_rows) + "\n")
        print(f"Wrote {len(all_rows)} rows to {out_path}")

        # Summary
        from collections import Counter
        outcomes = Counter(r.get("outcome") for r in all_rows)
        print(f"\nOutcome summary:")
        for k, v in sorted(outcomes.items(), key=lambda x: -x[1]):
            pct = v / len(all_rows) * 100 if all_rows else 0
            print(f"  {k}: {v} ({pct:.1f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

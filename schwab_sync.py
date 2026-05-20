"""
schwab_sync.py — pull live positions + account state from Schwab Trader API
and cache them as data/schwab_state.json for the dashboard's Portfolio tab.

Architectural rationale (Option C from 2026-05-19 audit):
  - Alpaca paper sync runs only at scan time + post-fill → portfolio P&L
    in the dashboard is stale most of the day.
  - Polling EODHD per-ticker every 60s for the position-watch path eats
    the 100K/day EODHD quota.
  - Schwab is the broker-of-truth for real-money positions. Schwab Trader
    API returns positions + live mark-to-market in ONE call, doesn't
    touch EODHD budget, and Schwab's own rate limit (~120/min) is
    untouched by other surfaces.

Architecture
  this script (every 60s during market hours via launchd)
      ↓ Schwab Trader API
      ↓
  data/schwab_state.json
      ↓ /api/portfolio/live route in server.py
      ↓
  kairos.html Portfolio tab (5s browser-side poll)

API endpoints used (Schwab Trader v1):
  GET /trader/v1/accounts/accountNumbers
      → returns [{ accountNumber, hashValue }, ...]
      Account hash is the encrypted identifier used by all other Trader
      API calls. Cache it after first fetch to data/schwab_account.json.
  GET /trader/v1/accounts/{accountHash}?fields=positions
      → returns full account snapshot incl. positions, current value,
        intraday P&L, margin/cash balances.

Output schema (data/schwab_state.json):
  {
    "generated_at": "2026-05-19T11:34:22-07:00",
    "account_value": 98421.18,
    "cash": 12340.55,
    "buying_power": 24681.10,
    "day_pnl": 318.42,
    "day_pnl_pct": 0.32,
    "positions": [
      {
        "ticker": "NEM",
        "shares": 100,
        "entry_price": 104.61,
        "current_price": 105.81,
        "market_value": 10581.00,
        "cost_basis": 10461.00,
        "pnl_dollar": 120.00,
        "pnl_pct": 1.15,
        "day_pnl_dollar": 24.50,
        "day_pnl_pct": 0.23,
        "direction": "long"
      }, ...
    ],
    "_meta": {
      "source": "schwab.trader.v1",
      "account_hash_cached_at": "2026-05-19T06:30:00",
      "elapsed_ms": 420,
      "n_positions": 2
    }
  }

Run modes:
  python3 schwab_sync.py               # one-shot sync, exit code 0/1
  python3 schwab_sync.py --force       # sync even if outside market hours
  python3 schwab_sync.py --diagnose    # dump full Schwab response for debug

Called by:
  - infra/launchd/com.swingtrade.schwab-sync.plist (every 60s mkt hours)
  - server.py /api/portfolio/sync_schwab (manual refresh button)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

# Local imports — schwab_auth handles OAuth lifecycle, _headers, API_BASE
sys.path.insert(0, str(Path(__file__).resolve().parent))
from schwab_auth import _headers, API_BASE  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent
ACCOUNT_HASH_PATH = BASE_DIR / "data" / "schwab_account.json"
STATE_PATH = BASE_DIR / "data" / "schwab_state.json"
LOG_DIR = BASE_DIR / "cache" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

log = logging.getLogger("swingtrade.schwab_sync")
if not log.handlers:
    h = logging.FileHandler(LOG_DIR / "schwab_sync.log")
    h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    log.addHandler(h)
    log.addHandler(logging.StreamHandler(sys.stdout))
    log.setLevel(logging.INFO)


# ─────────────────────────────────────────────────────────────────────────────
# Market hours guard
# ─────────────────────────────────────────────────────────────────────────────

def _in_market_hours(force: bool = False) -> bool:
    """Return True if NYSE is open right now (Mon-Fri 9:30-16:30 ET).

    Holiday calendar deliberately NOT enforced — the cost of a few
    out-of-session API calls on holidays is trivial vs the engineering
    cost of maintaining a holiday list. Schwab returns the same snapshot
    on holidays anyway.
    """
    if force:
        return True
    now_et = datetime.now(ZoneInfo("America/New_York"))
    if now_et.weekday() >= 5:  # 5=Sat, 6=Sun
        return False
    open_t  = now_et.replace(hour=9,  minute=30, second=0, microsecond=0)
    close_t = now_et.replace(hour=16, minute=30, second=0, microsecond=0)  # 30min buffer after close for late prints
    return open_t <= now_et <= close_t


# ─────────────────────────────────────────────────────────────────────────────
# Account hash — one-time fetch, cached
# ─────────────────────────────────────────────────────────────────────────────

def fetch_account_hash(force_refresh: bool = False) -> str | None:
    """Get the encrypted account hash used by all Trader API calls.

    Schwab requires this hash (not the raw account number) for security.
    We cache it to data/schwab_account.json after first fetch — it's
    stable across sessions, only changes if the user adds/removes
    accounts in the brokerage UI.
    """
    if not force_refresh and ACCOUNT_HASH_PATH.exists():
        try:
            d = json.loads(ACCOUNT_HASH_PATH.read_text())
            cached = d.get("primary_hash")
            if cached:
                return cached
        except Exception as e:
            log.warning(f"hash cache unreadable ({e}); re-fetching")

    log.info("fetching account hash from Schwab /trader/v1/accounts/accountNumbers")
    try:
        r = requests.get(
            f"{API_BASE}/trader/v1/accounts/accountNumbers",
            headers=_headers(), timeout=10,
        )
    except Exception as e:
        log.error(f"network error fetching account hash: {e}")
        return None
    if r.status_code != 200:
        log.error(f"Schwab returned {r.status_code} for accountNumbers: {r.text[:200]}")
        return None

    accounts = r.json()
    if not accounts:
        log.error("Schwab returned empty account list")
        return None
    # Primary is first (Schwab's convention). Cache all hashes so we can
    # extend to multi-account later without re-fetching.
    primary = accounts[0]
    payload = {
        "primary_hash": primary.get("hashValue"),
        "primary_account_number_masked": (primary.get("accountNumber") or "")[-4:],  # ...XXXX
        "all_accounts": [{"masked": a.get("accountNumber", "")[-4:],
                          "hash": a.get("hashValue")} for a in accounts],
        "cached_at": datetime.now(timezone.utc).isoformat(),
    }
    ACCOUNT_HASH_PATH.parent.mkdir(parents=True, exist_ok=True)
    ACCOUNT_HASH_PATH.write_text(json.dumps(payload, indent=2))
    log.info(f"cached primary account hash (masked …{payload['primary_account_number_masked']})")
    return payload["primary_hash"]


# ─────────────────────────────────────────────────────────────────────────────
# Position fetch + normalization
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_position(p: dict) -> dict:
    """Convert Schwab's nested position shape to the flat dict the
    dashboard reads. Schwab's response (per their docs):
        { instrument: { symbol, ... },
          longQuantity, shortQuantity,
          averagePrice, marketValue, currentDayProfitLoss,
          currentDayProfitLossPercentage, ...
        }
    """
    inst = p.get("instrument") or {}
    sym  = (inst.get("symbol") or "").upper()
    longQ  = float(p.get("longQuantity")  or 0)
    shortQ = float(p.get("shortQuantity") or 0)
    shares = longQ if longQ > 0 else -shortQ  # negative for short
    direction = "long" if shares > 0 else ("short" if shares < 0 else "flat")

    avg_px  = float(p.get("averagePrice") or 0)
    mkt_val = float(p.get("marketValue") or 0)
    # Schwab doesn't always expose current_price directly — derive from
    # marketValue / abs(shares). Fall back to averagePrice on degenerate
    # rows (shouldn't happen for live positions).
    cur_px = (mkt_val / abs(shares)) if shares else avg_px

    cost_basis = avg_px * abs(shares)
    pnl_dollar = mkt_val - cost_basis if direction == "long" else cost_basis - mkt_val
    pnl_pct = (pnl_dollar / cost_basis * 100) if cost_basis else 0.0

    return {
        "ticker": sym,
        "shares": int(shares),
        "direction": direction,
        "entry_price": round(avg_px, 4),
        "current_price": round(cur_px, 4),
        "market_value": round(mkt_val, 2),
        "cost_basis": round(cost_basis, 2),
        "pnl_dollar": round(pnl_dollar, 2),
        "pnl_pct": round(pnl_pct, 2),
        "day_pnl_dollar": round(float(p.get("currentDayProfitLoss") or 0), 2),
        "day_pnl_pct": round(float(p.get("currentDayProfitLossPercentage") or 0), 2),
        "asset_type": inst.get("assetType") or "",
    }


def fetch_positions(account_hash: str) -> dict | None:
    """Hit /trader/v1/accounts/{hash}?fields=positions. Returns the
    raw Schwab account dict or None on failure."""
    log.info(f"fetching positions for hash …{account_hash[-8:]}")
    try:
        r = requests.get(
            f"{API_BASE}/trader/v1/accounts/{account_hash}",
            params={"fields": "positions"},
            headers=_headers(), timeout=15,
        )
    except Exception as e:
        log.error(f"network error fetching positions: {e}")
        return None
    if r.status_code != 200:
        log.error(f"Schwab returned {r.status_code}: {r.text[:300]}")
        return None
    return r.json()


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def sync_to_local(force: bool = False, diagnose: bool = False) -> dict:
    """Fetch positions from Schwab and write data/schwab_state.json.

    Returns the state dict that was written. Empty positions list +
    error field on failure.

    Off-hours: skip the API call (returns previous state with
    `_meta.skipped_off_hours=True`) unless force=True.
    """
    t_start = time.time()
    if not _in_market_hours(force=force):
        # Don't burn API budget off-hours. The cached state remains valid
        # (positions don't change off-hours). Update the meta timestamp
        # so the dashboard's freshness chip stays accurate.
        if STATE_PATH.exists():
            try:
                prior = json.loads(STATE_PATH.read_text())
                prior.setdefault("_meta", {})
                prior["_meta"]["skipped_off_hours"] = True
                prior["_meta"]["checked_at"] = datetime.now(timezone.utc).isoformat()
                STATE_PATH.write_text(json.dumps(prior, indent=2))
                log.info("off-hours: skipped Schwab API; bumped checked_at on existing state")
                return prior
            except Exception:
                pass
        log.info("off-hours: no prior state to bump; skipping")
        return {"_meta": {"skipped_off_hours": True}, "positions": []}

    account_hash = fetch_account_hash()
    if not account_hash:
        err = "could not fetch account hash"
        log.error(err)
        return {"error": err, "positions": [], "_meta": {"elapsed_ms": int((time.time() - t_start) * 1000)}}

    raw = fetch_positions(account_hash)
    if not raw:
        err = "fetch_positions returned None"
        log.error(err)
        return {"error": err, "positions": [], "_meta": {"elapsed_ms": int((time.time() - t_start) * 1000)}}

    if diagnose:
        diag_path = LOG_DIR / f"schwab_diagnose_{int(time.time())}.json"
        diag_path.write_text(json.dumps(raw, indent=2))
        log.info(f"diagnostic raw dump → {diag_path}")

    # Schwab response shape: {"securitiesAccount": {...}} OR top-level account
    acct = raw.get("securitiesAccount") or raw
    positions_raw = acct.get("positions") or []
    positions = [_normalize_position(p) for p in positions_raw if p.get("instrument")]

    # Aggregate account values from currentBalances
    bal = acct.get("currentBalances") or {}
    init_bal = acct.get("initialBalances") or {}
    day_pnl = sum(p.get("day_pnl_dollar", 0) for p in positions)
    total_mkt_val = sum(p.get("market_value", 0) for p in positions)
    starting_acct_val = float(init_bal.get("liquidationValue") or init_bal.get("accountValue") or 0)
    day_pnl_pct = (day_pnl / starting_acct_val * 100) if starting_acct_val else 0.0

    state = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "account_value": round(float(bal.get("liquidationValue") or bal.get("accountValue") or 0), 2),
        "cash": round(float(bal.get("cashBalance") or bal.get("totalCash") or 0), 2),
        "buying_power": round(float(bal.get("buyingPower") or 0), 2),
        "day_pnl": round(day_pnl, 2),
        "day_pnl_pct": round(day_pnl_pct, 2),
        "total_market_value": round(total_mkt_val, 2),
        "positions": positions,
        "_meta": {
            "source": "schwab.trader.v1",
            "elapsed_ms": int((time.time() - t_start) * 1000),
            "n_positions": len(positions),
            "account_hash_cached_at": json.loads(ACCOUNT_HASH_PATH.read_text()).get("cached_at") if ACCOUNT_HASH_PATH.exists() else None,
        },
    }

    STATE_PATH.write_text(json.dumps(state, indent=2))
    log.info(f"✓ wrote {STATE_PATH.name}: {len(positions)} positions · day P&L ${day_pnl:+,.2f} · "
             f"acct ${state['account_value']:,.2f} · {state['_meta']['elapsed_ms']}ms")
    return state


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true",
                    help="Sync even if outside market hours (testing / weekend).")
    ap.add_argument("--diagnose", action="store_true",
                    help="Dump raw Schwab response to cache/logs/schwab_diagnose_<ts>.json.")
    ap.add_argument("--refresh-hash", action="store_true",
                    help="Force re-fetch the account hash (e.g. after adding a new brokerage account).")
    args = ap.parse_args()

    if args.refresh_hash:
        h = fetch_account_hash(force_refresh=True)
        print(f"account hash refreshed: …{(h or '')[-8:]}")

    result = sync_to_local(force=args.force, diagnose=args.diagnose)
    if "error" in result:
        print(f"FAIL: {result['error']}", file=sys.stderr)
        return 1
    if result.get("_meta", {}).get("skipped_off_hours"):
        print("off-hours · no Schwab API call")
        return 0
    n = result["_meta"]["n_positions"]
    print(f"OK · {n} positions · day P&L ${result['day_pnl']:+,.2f} · "
          f"acct ${result['account_value']:,.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

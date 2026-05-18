"""
Portfolio state tracker for SwingTrade — Config E defaults.

Maintains data/portfolio_state.json with equity curve, open/closed positions,
trailing stops, and monthly P&L.  Zero external dependencies (json/pathlib/datetime only).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, date, timedelta
from pathlib import Path

log = logging.getLogger("portfolio_tracker")

BASE_DIR = Path(__file__).parent
STATE_PATH = BASE_DIR / "data" / "portfolio_state.json"
CONFIG_PATH = BASE_DIR / "config" / "config.json"

# ── Schema versioning ───────────────────────────────────────────────────────
# Bump when the on-disk shape of portfolio_state.json changes.
PORTFOLIO_SCHEMA_VERSION = 2


# ── Config E defaults (loaded from config.json if available) ────────────────

def _load_config_e() -> dict:
    """Return config_e block from config.json, falling back to hardcoded defaults."""
    defaults = {
        "max_positions": 50,
        "pct_per_trade": 0.30,
        "hold_days": 5,
        "max_hold_days": 10,
        "trail_activate_pct": 2.0,
        "trail_atr_mult": 1.25,
        "time_stop_flat_pct": 1.0,
        "exclude_setups": ["52wk Breakout"],
        "verdict_filter": ["BUY"],
        "starting_equity": 5000,
    }
    try:
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
        portfolio_cfg = cfg.get("portfolio", {})
        # Merge: config_e block, then top-level portfolio keys, then defaults
        merged = dict(defaults)
        merged.update(portfolio_cfg.get("config_e", {}))
        # Top-level portfolio keys override config_e
        for k in ("max_positions", "account_size", "starting_equity"):
            if k in portfolio_cfg:
                merged[k] = portfolio_cfg[k]
        return merged
    except (FileNotFoundError, json.JSONDecodeError):
        return defaults


CFG = _load_config_e()


# ── Undo-close queue (in-memory, TTL-bound) ────────────────────────────────
_UNDO_QUEUE: dict = {}  # {undo_id: {"closed_trade": ..., "timestamp": ...}}
UNDO_WINDOW_SECONDS = 60


# ── State persistence ───────────────────────────────────────────────────────

def _empty_state() -> dict:
    today = date.today().isoformat()
    equity = CFG.get("starting_equity", 5000)
    return {
        "_schema_version": PORTFOLIO_SCHEMA_VERSION,
        "equity": equity,
        "cash": equity,
        "positions": [],
        "closed_trades": [],
        "monthly_pnl": {},
        "equity_curve": [{"date": today, "equity": equity}],
        "margin_reserved": 0,
        "equity_audit": [],
    }


def _default_state() -> dict:
    """Fresh default state at the current schema version."""
    return {
        "_schema_version": PORTFOLIO_SCHEMA_VERSION,
        "equity": 5000,
        "cash": 5000,
        "positions": [],
        "closed_trades": [],
        "monthly_pnl": {},
        "margin_reserved": 0,
        "equity_audit": [],
    }


def _migrate_state(state: dict, from_version: int) -> dict:
    """Apply sequential, idempotent migrations from `from_version` to
    PORTFOLIO_SCHEMA_VERSION.  Additive only — never deletes data."""
    if from_version < 1:
        # v0 → v1: unify naming and ensure base keys exist
        if "closed" in state and "closed_trades" not in state:
            state["closed_trades"] = state.pop("closed")
        state.setdefault("closed_trades", [])
        state.setdefault("monthly_pnl", {})
        state.setdefault("positions", [])
        state.setdefault("equity", 5000)
        state.setdefault("cash", 5000)
    if from_version < 2:
        # v1 → v2: margin accounting + equity audit + per-position direction
        state.setdefault("margin_reserved", 0)
        state.setdefault("equity_audit", [])
        state.setdefault("equity_curve", [])
        for p in state.get("positions", []):
            p.setdefault("direction", "long")
    # Future migrations: add further `if from_version < N:` branches here.
    return state


_LEGACY_CHECKED = False
_LEGACY_PATH = BASE_DIR / "cache" / "portfolio.json"
_LEGACY_MARKER = BASE_DIR / "data" / "_legacy_migration_checked.marker"


def _check_legacy_migration():
    """One-time check: warn if cache/portfolio.json has data not in current state."""
    if _LEGACY_MARKER.exists() or not _LEGACY_PATH.exists():
        return
    try:
        with open(_LEGACY_PATH) as f:
            legacy = json.load(f)
        legacy_positions = legacy.get("positions", [])
        legacy_closed = legacy.get("closed_trades", legacy.get("closed", []))
        if legacy_positions or legacy_closed:
            log.warning(
                "\u26a0\ufe0f  Legacy portfolio data detected in cache/portfolio.json "
                f"({len(legacy_positions)} open positions, {len(legacy_closed)} closed). "
                "This file is NOT being read. If you want to preserve these trades, "
                "run: python3 -c 'from portfolio_tracker import migrate_legacy; "
                "print(migrate_legacy())'"
            )
        # Mark as checked regardless (one-time warning)
        _LEGACY_MARKER.parent.mkdir(parents=True, exist_ok=True)
        _LEGACY_MARKER.write_text(datetime.now().isoformat())
    except Exception as e:
        log.debug(f"Legacy migration check failed: {e}")


def _load_state() -> dict:
    """Read canonical portfolio state.

    Phase B.1 (2026-05-08): goes through state_layer.load_portfolio_state()
    which today reads JSON (Mode 1) but in Mode 2 will read from Supabase
    with JSON fallback. Adds a 5-sec LRU cache that collapses the 25+
    _load_state() calls per scan in this file into a single read.
    """
    global _LEGACY_CHECKED
    if not _LEGACY_CHECKED:
        _check_legacy_migration()
        _LEGACY_CHECKED = True
    if not STATE_PATH.exists():
        return _default_state()

    try:
        from state_layer import load_portfolio_state
        state = load_portfolio_state()
    except Exception:
        # Defensive fallback — never let the shim break a scan
        with open(STATE_PATH) as f:
            state = json.load(f)

    current = state.get("_schema_version", 0)
    if current < PORTFOLIO_SCHEMA_VERSION:
        state = _migrate_state(state, from_version=current)
        _save_state(state)
        log.info(
            "Migrated portfolio_state from v%s to v%s",
            current, PORTFOLIO_SCHEMA_VERSION,
        )
    return state


def migrate_legacy() -> dict:
    """Manually migrate positions from cache/portfolio.json to data/portfolio_state.json.

    Non-destructive: never deletes the legacy file.
    Idempotent: running twice produces the same state (tickers/closed trades are deduped).
    Merges: skips tickers already in current open positions; skips closed trades
    matching on (ticker, entry_date, exit_date).
    Returns {migrated, skipped, errors, migrated_closed, skipped_closed, errors_closed}.
    """
    if not _LEGACY_PATH.exists():
        return {"error": "No legacy file to migrate"}

    try:
        with open(_LEGACY_PATH) as f:
            legacy = json.load(f)
    except Exception as e:
        return {"error": f"Failed to read legacy: {e}"}

    state = _load_state()
    existing_tickers = {p.get("ticker", "").upper() for p in state.get("positions", [])}

    migrated, skipped, errors = [], [], []
    for leg_pos in legacy.get("positions", []):
        ticker = (leg_pos.get("ticker") or "").upper()
        if not ticker:
            errors.append({"pos": leg_pos, "reason": "no ticker"})
            continue
        if ticker in existing_tickers:
            skipped.append(ticker)
            continue
        try:
            entry = float(leg_pos.get("entry", leg_pos.get("entry_price", 0)))
            shares = int(leg_pos.get("shares", 0))
            current_price = float(leg_pos.get("current_price", entry))
            mapped = {
                "ticker": ticker,
                "direction": leg_pos.get("direction", "long"),
                "entry_price": entry,
                "shares": shares,
                "stop": float(leg_pos.get("stop", 0)),
                "target1": float(leg_pos.get("target1", 0)),
                "target2": leg_pos.get("target2"),
                "setup_type": leg_pos.get("setup", leg_pos.get("setup_type", "")),
                "entry_date": leg_pos.get(
                    "entry_date", datetime.now().strftime("%Y-%m-%d")
                ),
                "allocation_pct": float(leg_pos.get("allocation_pct", 7.5)),
                "notes": leg_pos.get("notes") or "(migrated from legacy)",
                "current_price": current_price,
                "position_size": entry * shares,
                "trail_stop": float(leg_pos.get("stop", 0)),
                "trail_active": False,
                "highest_price": current_price,
            }
            state["positions"].append(mapped)
            existing_tickers.add(ticker)
            migrated.append(ticker)
        except Exception as e:
            errors.append({"ticker": ticker, "reason": str(e)})

    # Closed trades — dedupe by (ticker, entry_date, exit_date)
    existing_closed_keys = {
        (
            (c.get("ticker") or "").upper(),
            c.get("entry_date", ""),
            c.get("exit_date", ""),
        )
        for c in state.get("closed_trades", [])
    }
    legacy_closed = legacy.get("closed_trades", legacy.get("closed", []))
    migrated_closed, skipped_closed, errors_closed = [], [], []
    for leg_c in legacy_closed:
        ticker = (leg_c.get("ticker") or "").upper()
        if not ticker:
            errors_closed.append({"pos": leg_c, "reason": "no ticker"})
            continue
        key = (ticker, leg_c.get("entry_date", ""), leg_c.get("exit_date", ""))
        if key in existing_closed_keys:
            skipped_closed.append(ticker)
            continue
        try:
            entry = float(leg_c.get("entry", leg_c.get("entry_price", 0)))
            exit_price = float(leg_c.get("exit", leg_c.get("exit_price", 0)))
            shares = int(leg_c.get("shares", 0))
            mapped_c = dict(leg_c)
            mapped_c["ticker"] = ticker
            mapped_c.setdefault("direction", "long")
            mapped_c["entry_price"] = entry
            mapped_c["exit_price"] = exit_price
            mapped_c["shares"] = shares
            mapped_c.setdefault(
                "setup_type", leg_c.get("setup", leg_c.get("setup_type", ""))
            )
            mapped_c.setdefault("notes", "(migrated from legacy)")
            state.setdefault("closed_trades", []).append(mapped_c)
            existing_closed_keys.add(key)
            migrated_closed.append(ticker)
        except Exception as e:
            errors_closed.append({"ticker": ticker, "reason": str(e)})

    if migrated or migrated_closed:
        _save_state(state)
        log.info(
            "Legacy migration: %d open, %d closed migrated (skipped %d open, %d closed)",
            len(migrated), len(migrated_closed), len(skipped), len(skipped_closed),
        )

    return {
        "migrated": migrated,
        "skipped": skipped,
        "errors": errors,
        "migrated_closed": migrated_closed,
        "skipped_closed": skipped_closed,
        "errors_closed": errors_closed,
    }


def _save_state(state: dict):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["_schema_version"] = PORTFOLIO_SCHEMA_VERSION
    state["_last_saved"] = datetime.now().isoformat()
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2, default=str)
    # Invalidate state_layer cache so the next _load_state sees fresh data.
    try:
        from state_layer import cache_invalidate
        cache_invalidate("portfolio_state")
    except Exception:
        pass
    # Dual-write to Supabase (no-op when SUPABASE_MODE=0; never raises).
    try:
        from supabase_sync import sync_portfolio_state
        sync_portfolio_state(state)
    except Exception:
        pass


# ── Mechanical paper-trading gates (BUY-only, 4/day, 60-day window) ─────────
# Introduced for the Phase-4 paper-trading activation. Policy:
#   - BUY-only for the 60-day window; SHORTs will be re-enabled later.
#   - Hard cap of MAX_DAILY_TRADES trades opened in a single calendar day.
#   - Auto-disable after PAPER_TRADING_DURATION_DAYS so the user can't forget.
#   - Activation is explicit: call activate_paper_trading() or run
#     `python3 executor.py --activate`. No implicit enable.

PAPER_TRADING_MARKER = BASE_DIR / "data" / "paper_trading_start.json"
PAPER_TRADING_DURATION_DAYS = 60
MAX_DAILY_TRADES = 8  # 2026-05-18 bumped 4→8 to capture more of 177 profitable signals/19d


def compute_current_drawdown_pct(lookback_days: int = 90) -> dict:
    """
    Return current account drawdown vs peak equity in the last `lookback_days`.

    Reads `equity_curve` from portfolio state. Peak is the max equity over the
    window. Current is the most recent point. Drawdown is positive % below peak.

    Returns dict with:
      - drawdown_pct: float (0 if no history or above peak)
      - peak_equity: float (or None if no history)
      - current_equity: float (or None if no history)
      - peak_date: ISO date of peak (or None)
      - n_points: number of equity_curve points considered

    Used by analysis.kelly_position_size via config.portfolio_vol_targeting._runtime_drawdown_pct
    to scale position size during drawdowns (1.0× / 0.85× / 0.65× / 0.40× / 0.20×).
    """
    state = _load_state()
    ec = state.get("equity_curve") or []
    if not ec:
        return {"drawdown_pct": 0.0, "peak_equity": None, "current_equity": None,
                "peak_date": None, "n_points": 0}

    # Sort by date then trim to lookback
    ec_sorted = sorted(ec, key=lambda p: p.get("date") or "")
    if lookback_days and lookback_days > 0:
        try:
            from datetime import timedelta
            cutoff = (date.today() - timedelta(days=lookback_days)).isoformat()
            ec_sorted = [p for p in ec_sorted if (p.get("date") or "") >= cutoff]
        except Exception:
            pass
    if not ec_sorted:
        return {"drawdown_pct": 0.0, "peak_equity": None, "current_equity": None,
                "peak_date": None, "n_points": 0}

    peak_pt = max(ec_sorted, key=lambda p: float(p.get("equity") or 0))
    peak_eq = float(peak_pt.get("equity") or 0)
    cur_eq  = float(ec_sorted[-1].get("equity") or 0)
    if peak_eq <= 0:
        dd_pct = 0.0
    else:
        dd_pct = max(0.0, round((peak_eq - cur_eq) / peak_eq * 100, 2))
    return {
        "drawdown_pct":   dd_pct,
        "peak_equity":    round(peak_eq, 2),
        "current_equity": round(cur_eq, 2),
        "peak_date":      peak_pt.get("date"),
        "n_points":       len(ec_sorted),
    }


def daily_trades_taken_today() -> int:
    """Count how many trades opened today (open + closed) in portfolio state."""
    state = _load_state()
    today = date.today().isoformat()
    open_today = sum(
        1 for p in state.get("positions", [])
        if str(p.get("entry_date", ""))[:10] == today
    )
    closed_today = sum(
        1 for t in state.get("closed_trades", [])
        if str(t.get("entry_date", ""))[:10] == today
    )
    return open_today + closed_today


def can_take_new_trade() -> tuple[bool, str]:
    """Return (ok, reason). False when today's trade count >= MAX_DAILY_TRADES."""
    count = daily_trades_taken_today()
    if count >= MAX_DAILY_TRADES:
        return False, f"Daily trade limit reached ({count}/{MAX_DAILY_TRADES})"
    return True, f"{count}/{MAX_DAILY_TRADES} trades taken today"


def is_paper_trading_enabled() -> tuple[bool, str]:
    """Return (enabled, reason). Reads the marker file; auto-expires after duration."""
    if not PAPER_TRADING_MARKER.exists():
        return False, "Not activated. Run activate_paper_trading() to enable."
    try:
        with open(PAPER_TRADING_MARKER) as f:
            d = json.load(f)
        if not d.get("enabled", False):
            return False, "Paper trading disabled"
        start = date.fromisoformat(d["start_date"])
        elapsed = (date.today() - start).days
        duration = int(d.get("duration_days", PAPER_TRADING_DURATION_DAYS))
        if elapsed >= duration:
            return False, f"Paper trading period ended ({elapsed}d since {start.isoformat()})"
        return True, f"Day {elapsed + 1}/{duration}"
    except Exception as e:
        return False, f"Error reading marker: {e}"


def activate_paper_trading(duration_days: int = PAPER_TRADING_DURATION_DAYS) -> dict:
    """Create the marker file with today's date. Idempotent — overwrites start_date."""
    PAPER_TRADING_MARKER.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "start_date": date.today().isoformat(),
        "duration_days": int(duration_days),
        "enabled": True,
        "direction_filter": "buy_only",
        "max_daily_trades": MAX_DAILY_TRADES,
    }
    with open(PAPER_TRADING_MARKER, "w") as f:
        json.dump(payload, f, indent=2)
    log.info(f"Paper trading ACTIVATED — {duration_days}d duration, BUY-only, cap {MAX_DAILY_TRADES}/day")
    return payload


def disable_paper_trading() -> dict:
    """Flip enabled=False in the marker file. Preserves start_date for audit."""
    if not PAPER_TRADING_MARKER.exists():
        log.info("Paper trading marker missing — nothing to disable")
        return {"enabled": False, "reason": "marker missing"}
    with open(PAPER_TRADING_MARKER) as f:
        d = json.load(f)
    d["enabled"] = False
    d["disabled_at"] = datetime.now().isoformat()
    with open(PAPER_TRADING_MARKER, "w") as f:
        json.dump(d, f, indent=2)
    log.info("Paper trading DISABLED")
    return d


def paper_trading_status() -> dict:
    """Structured status dict for CLI / HTML consumption."""
    enabled, reason = is_paper_trading_enabled()
    marker = {}
    if PAPER_TRADING_MARKER.exists():
        try:
            with open(PAPER_TRADING_MARKER) as f:
                marker = json.load(f)
        except Exception:
            marker = {}
    return {
        "enabled": enabled,
        "reason": reason,
        "daily_count": daily_trades_taken_today(),
        "daily_cap": MAX_DAILY_TRADES,
        "marker": marker,
    }


# ── Diagnostics ─────────────────────────────────────────────────────────────

def get_schema_info() -> dict:
    """Return schema versions of all tracked state files for diagnostics."""
    info: dict = {}
    candidates = [
        ("portfolio", STATE_PATH, None),
        ("signal_log", BASE_DIR / "data" / "signal_log.json",
         BASE_DIR / "data" / "signal_log.meta.json"),
    ]
    for name, path, meta_path in candidates:
        if not path.exists():
            info[name] = {"exists": False}
            continue
        try:
            with open(path) as f:
                data = json.load(f)
            if isinstance(data, list):
                entry: dict = {"count": len(data)}
                # Read sidecar meta file if present (signal_log uses external meta)
                if meta_path and meta_path.exists():
                    try:
                        with open(meta_path) as mf:
                            meta = json.load(mf)
                        entry["current"] = meta.get("schema_version") or meta.get("_schema_version", 0)
                        entry["last_saved"] = meta.get("last_saved") or meta.get("_last_saved", "unknown")
                    except Exception as me:
                        entry["current"] = "list (meta unreadable)"
                        entry["meta_error"] = str(me)
                else:
                    entry["current"] = "list (no version)"
                info[name] = entry
            else:
                info[name] = {
                    "current": data.get("_schema_version", 0),
                    "last_saved": data.get("_last_saved", "unknown"),
                }
        except Exception as e:
            info[name] = {"error": str(e)}
    return info


# ── Public API ──────────────────────────────────────────────────────────────

def add_position(ticker: str, entry_price: float, shares: int,
                 stop: float, target1: float,
                 target2: float | None = None,
                 setup_type: str = "",
                 direction: str = "long",
                 allocation_pct: float = 7.5,
                 notes: str = "",
                 entry_date: str | None = None,
                 entry_datetime: str | None = None) -> dict:
    """
    Open a new position.  Deducts cost from cash (treated as collateral
    for shorts in this paper-trading model — no separate margin handling).
    Returns the new position dict or raises ValueError.
    """
    state = _load_state()
    max_pos = CFG.get("max_positions", 999)

    if len(state["positions"]) >= max_pos:
        raise ValueError(f"Max {max_pos} concurrent positions — close one first.")

    # Prevent duplicate open positions for same ticker
    existing = [p for p in state["positions"] if p.get("ticker", "").upper() == ticker.upper()]
    if existing:
        raise ValueError(f"{ticker.upper()} already has an open position (entered {existing[0].get('entry_date', '?')})")

    # Reject excluded setups (e.g. 52wk Breakout unless overridden)
    excluded = CFG.get("exclude_setups", [])
    if setup_type in excluded:
        raise ValueError(f"Setup '{setup_type}' is excluded by Config E.")

    position_value = round(entry_price * shares, 2)

    # entry_datetime — full ISO timestamp (YYYY-MM-DDTHH:MM:SS PT)
    # added 2026-05-15 so dashboards can show fill time, not just date.
    # entry_date kept for backwards compat with picks_history/closed_trades.
    from datetime import datetime as _dt
    if entry_datetime is None:
        entry_datetime = _dt.now().isoformat(timespec="seconds")
    if entry_date is None:
        entry_date = entry_datetime[:10] if entry_datetime else date.today().isoformat()

    # Signed quantity: long = +abs(shares), short = -abs(shares)
    # (added 2026-05-15 — disambiguates direction at the qty level so any
    # consumer can sum signed_qty across a portfolio for net exposure)
    _abs_shares = abs(int(shares))
    _signed_qty = _abs_shares if direction == "long" else -_abs_shares

    pos = {
        "ticker": ticker.upper(),
        "entry_date": entry_date,
        "entry_datetime": entry_datetime,
        "entry_price": round(entry_price, 2),
        "shares": _abs_shares,            # legacy: always positive (magnitude only)
        "signed_qty": _signed_qty,        # signed: + for long, − for short
        "position_size": position_value,
        "stop": round(stop, 2),
        "trail_stop": round(stop, 2),
        "trail_active": False,
        "highest_price": round(entry_price, 2),
        "setup_type": setup_type,
        "target1": round(target1, 2),
        "target2": round(target2, 2) if target2 else None,
        "direction": direction,
        "allocation_pct": allocation_pct,
        "notes": notes,
    }

    if direction == "long":
        if position_value > state["cash"]:
            raise ValueError(f"Insufficient cash: need ${position_value:.2f}, have ${state['cash']:.2f}")
        state["cash"] = round(state["cash"] - position_value, 2)
    else:  # short — reserve 50% margin, no cash movement
        margin = round(position_value * 0.5, 2)
        available = round(state["cash"] - state.get("margin_reserved", 0), 2)
        if margin > available:
            raise ValueError(
                f"Insufficient margin: need ${margin:.2f} (50% of ${position_value:.2f}), "
                f"available ${available:.2f}"
            )
        state["margin_reserved"] = round(state.get("margin_reserved", 0) + margin, 2)
        pos["margin_reserved"] = margin

    state["positions"].append(pos)
    _save_state(state)
    return pos


def calculate_position_size(equity: float, entry_price: float,
                            pct_per_trade: float | None = None,
                            market_snapshot: dict | None = None) -> tuple[int, dict]:
    """Regime-aware base position sizer used outside the Alpaca path (e.g. manual
    book-keeping, backtests, dashboards).

    `market_snapshot` may carry `max_size_pct` (from data_fetcher.py:2394–2413).
    Missing key → default 100 (no scaling, backward-compat).

    Returns (shares, meta) where meta includes the applied max_size_pct and
    regime multiplier for audit.
    """
    if entry_price is None or entry_price <= 0:
        return 0, {"reason": "no entry price", "max_size_pct": 100}
    pct = float(pct_per_trade if pct_per_trade is not None
                else CFG.get("pct_per_trade", 0.20))
    ms = market_snapshot or {}
    try:
        msp = float(ms.get("max_size_pct", 100))
    except (TypeError, ValueError):
        msp = 100.0
    msp = max(0.0, min(100.0, msp))
    regime_mult = msp / 100.0
    if msp < 100.0:
        log.info(f"Position size scaled by regime: {msp:g}% of base")
    if regime_mult <= 0.0:
        return 0, {"reason": "regime max_size_pct=0 (panic)", "max_size_pct": msp}
    target_value = float(equity) * pct * regime_mult
    shares = max(0, int(target_value // float(entry_price)))
    return shares, {
        "max_size_pct":    msp,
        "regime_mult":     regime_mult,
        "target_value":    round(target_value, 2),
        "pct_per_trade":   pct,
        "base_pct_value":  round(float(equity) * pct, 2),
    }


def set_position_exit_verdict(ticker: str, verdict: dict,
                              check_date: str | None = None) -> bool:
    """Persist a daily classify_exit_state() verdict on an open position.

    Stored as `last_exit_verdict` + `last_exit_check_date`. Returns True iff
    the ticker was found and updated.
    """
    state = _load_state()
    ticker_u = ticker.upper()
    today = check_date or date.today().isoformat()
    for p in state.get("positions", []):
        if (p.get("ticker") or "").upper() == ticker_u:
            p["last_exit_verdict"] = dict(verdict) if isinstance(verdict, dict) else {"raw": verdict}
            p["last_exit_check_date"] = today
            _save_state(state)
            return True
    return False


def close_position(ticker: str, exit_price: float,
                   exit_reason: str | None = "manual") -> dict:
    """
    Close an open position by ticker.  Credits proceeds to cash,
    records the trade in closed_trades and updates monthly P&L.
    Returns the closed-trade record.
    """
    state = _load_state()
    ticker = ticker.upper()
    # Normalize exit_reason: None → "unknown", empty → "manual" (backward-compat)
    if exit_reason is None:
        exit_reason = "unknown"
    elif not str(exit_reason).strip():
        exit_reason = "manual"
    idx = None
    for i, p in enumerate(state["positions"]):
        if p["ticker"] == ticker:
            idx = i
            break
    if idx is None:
        raise ValueError(f"No open position for {ticker}")

    pos = state["positions"].pop(idx)
    direction = pos.get("direction", "long")
    shares = pos["shares"]
    entry_price = pos["entry_price"]
    position_value = pos.get("position_size", round(entry_price * shares, 2))

    if direction == "long":
        proceeds = round(exit_price * shares, 2)
        state["cash"] = round(state["cash"] + proceeds, 2)
        pnl_dollars = round((exit_price - entry_price) * shares, 2)
    else:  # short — no cash moved on open, credit P&L delta only, release margin
        pnl_dollars = round((entry_price - exit_price) * shares, 2)
        state["cash"] = round(state["cash"] + pnl_dollars, 2)
        margin_held = pos.get("margin_reserved", round(position_value * 0.5, 2))
        state["margin_reserved"] = max(
            0, round(state.get("margin_reserved", 0) - margin_held, 2)
        )

    denom = entry_price * shares
    pnl_pct = round((pnl_dollars / denom) * 100, 2) if denom > 0 else 0.0

    today = date.today().isoformat()
    month_key = today[:7]  # e.g. "2026-04"

    trade = {
        "ticker": pos["ticker"],
        "entry_date": pos["entry_date"],
        "exit_date": today,
        "entry_price": pos["entry_price"],
        "exit_price": round(exit_price, 2),
        "shares": shares,
        "direction": direction,
        "pnl_dollars": pnl_dollars,
        "pnl_pct": pnl_pct,
        "exit_reason": exit_reason,
        "setup_type": pos.get("setup_type", ""),
    }

    if "closed_trades" not in state:
        state["closed_trades"] = []
    state["closed_trades"].append(trade)

    # Monthly P&L
    if "monthly_pnl" not in state:
        state["monthly_pnl"] = {}
    state["monthly_pnl"][month_key] = round(
        state["monthly_pnl"].get(month_key, 0) + pnl_dollars, 2
    )

    # Update equity = cash + invested value of remaining LONG positions (shorts are liabilities, tracked separately)
    invested = sum(
        p["entry_price"] * p["shares"]
        for p in state["positions"]
        if p.get("direction", "long") == "long"
    )
    state["equity"] = round(state["cash"] + invested, 2)

    # Equity curve (auto-create if missing)
    if "equity_curve" not in state:
        state["equity_curve"] = []
    state["equity_curve"].append({"date": today, "equity": state["equity"]})

    _save_state(state)

    # ── Register undo entry (in-memory, TTL-bound) ─────────────────────────
    import uuid as _uuid, time as _time
    undo_id = str(_uuid.uuid4())[:8]
    # Preserve original open-position details so we can reconstruct on undo
    undo_snapshot = dict(trade)
    undo_snapshot["stop"] = pos.get("stop")
    undo_snapshot["target1"] = pos.get("target1")
    undo_snapshot["target2"] = pos.get("target2")
    undo_snapshot["allocation_pct"] = pos.get("allocation_pct", 7.5)
    undo_snapshot["notes"] = pos.get("notes", "")
    undo_snapshot["trail_stop"] = pos.get("trail_stop")
    undo_snapshot["margin_reserved"] = pos.get("margin_reserved")
    _UNDO_QUEUE[undo_id] = {
        "closed_trade": undo_snapshot,
        "timestamp": _time.time(),
    }
    # Cleanup expired entries (>120s)
    _now = _time.time()
    for _k in [k for k, v in _UNDO_QUEUE.items() if _now - v["timestamp"] > 120]:
        _UNDO_QUEUE.pop(_k, None)

    trade["undo_id"] = undo_id
    return trade


def undo_close(undo_id: str) -> dict:
    """Re-open a recently-closed position. Must be called within UNDO_WINDOW_SECONDS."""
    import time
    entry = _UNDO_QUEUE.get(undo_id)
    if not entry:
        raise ValueError("Undo ID not found or expired")
    if time.time() - entry["timestamp"] > UNDO_WINDOW_SECONDS:
        _UNDO_QUEUE.pop(undo_id, None)
        raise ValueError(f"Undo window expired ({UNDO_WINDOW_SECONDS}s)")

    closed = entry["closed_trade"]
    state = _load_state()

    # Remove from closed_trades
    ct = state.get("closed_trades", [])
    state["closed_trades"] = [t for t in ct if not (
        t.get("ticker") == closed["ticker"] and
        t.get("exit_date") == closed.get("exit_date") and
        t.get("exit_price") == closed.get("exit_price")
    )]

    entry_price = closed.get("entry_price", closed.get("entry"))
    shares = closed["shares"]
    # Reconstruct open position
    pos = {
        "ticker": closed["ticker"],
        "direction": closed.get("direction", "long"),
        "entry_price": entry_price,
        "shares": shares,
        "stop": closed.get("stop") if closed.get("stop") is not None else entry_price * 0.95,
        "target1": closed.get("target1") if closed.get("target1") is not None else entry_price * 1.1,
        "target2": closed.get("target2"),
        "setup_type": closed.get("setup_type", closed.get("setup", "")),
        "entry_date": closed.get("entry_date"),
        "allocation_pct": closed.get("allocation_pct", 7.5),
        "notes": closed.get("notes", ""),
        "trail_stop": closed.get("trail_stop") if closed.get("trail_stop") is not None else (closed.get("stop") if closed.get("stop") is not None else entry_price * 0.95),
        "trail_active": False,
        "highest_price": entry_price,
        "current_price": entry_price,
        "position_size": round((entry_price or 0) * (shares or 0), 2),
    }
    state["positions"].append(pos)

    # Restore cash / margin state based on direction
    direction = pos["direction"]
    pnl = closed.get("pnl_dollars", 0)
    if direction == "long":
        # On close we credited proceeds = exit_price * shares to cash.
        # Reverse the full proceeds to restore pre-close cash.
        proceeds = round(closed.get("exit_price", 0) * shares, 2)
        state["cash"] = round(state.get("cash", 0) - proceeds, 2)
    else:  # short — on close we credited pnl to cash and released margin
        margin = closed.get("margin_reserved") or round(pos["position_size"] * 0.5, 2)
        state["margin_reserved"] = round(state.get("margin_reserved", 0) + margin, 2)
        state["cash"] = round(state.get("cash", 0) - pnl, 2)

    # Reverse monthly P&L credit
    exit_date = closed.get("exit_date", "")
    month_key = exit_date[:7] if exit_date else ""
    if month_key and month_key in state.get("monthly_pnl", {}):
        state["monthly_pnl"][month_key] = round(
            state["monthly_pnl"].get(month_key, 0) - pnl, 2
        )

    # Recompute equity
    invested = sum(
        p["entry_price"] * p["shares"]
        for p in state["positions"]
        if p.get("direction", "long") == "long"
    )
    state["equity"] = round(state.get("cash", 0) + invested, 2)

    _save_state(state)
    _UNDO_QUEUE.pop(undo_id, None)

    return {"ok": True, "position": pos, "message": f"Re-opened {pos['ticker']}"}


def update_notes(ticker: str, notes: str) -> dict:
    """Update the notes field on an open position. Returns updated position."""
    state = _load_state()
    ticker = ticker.upper()
    for p in state["positions"]:
        if p["ticker"] == ticker:
            p["notes"] = str(notes)[:500]  # cap at 500 chars
            _save_state(state)
            return {"ticker": ticker, "notes": p["notes"]}
    raise ValueError(f"No open position for {ticker}")


def move_stop_to_breakeven(ticker: str) -> dict:
    """Set the stop (and trail_stop) of the given open position to entry price."""
    state = _load_state()
    ticker = ticker.upper()
    for p in state["positions"]:
        if p["ticker"] == ticker:
            p["stop"] = round(float(p["entry_price"]), 2)
            p["trail_stop"] = max(p.get("trail_stop", 0) or 0, p["stop"])
            _save_state(state)
            return {"ok": True, "ticker": ticker, "new_stop": p["stop"]}
    raise ValueError(f"No open position for {ticker}")


def trail_stop(ticker: str, atr_mult: float = 1.5) -> dict:
    """Move stop to current_price - atr_mult * ATR proxy. Only ratchets up."""
    state = _load_state()
    ticker = ticker.upper()
    for p in state["positions"]:
        if p["ticker"] == ticker:
            cur = float(p.get("current_price") or p["entry_price"])
            atr = abs(float(p["entry_price"]) - float(p.get("stop", p["entry_price"] * 0.97)))
            if atr <= 0:
                atr = float(p["entry_price"]) * 0.02
            new_stop = round(cur - atr_mult * atr, 2)
            prev = float(p.get("trail_stop") or p.get("stop") or 0)
            if new_stop > prev:
                p["trail_stop"] = new_stop
                p["stop"] = new_stop
                p["trail_active"] = True
            _save_state(state)
            return {"ok": True, "ticker": ticker, "new_stop": p.get("trail_stop", p["stop"])}
    raise ValueError(f"No open position for {ticker}")


def partial_close(ticker: str, pct: float = 0.5, exit_price: float | None = None) -> dict:
    """Close ``pct`` fraction of the open position. Remaining shares stay open.

    Records a closed-trade entry for the sold shares and credits cash.
    """
    state = _load_state()
    ticker = ticker.upper()
    for p in state["positions"]:
        if p["ticker"] == ticker:
            total_shares = int(p["shares"])
            close_shares = max(1, int(total_shares * float(pct)))
            if close_shares >= total_shares:
                # Full close — delegate
                return close_position(ticker, float(exit_price or p.get("current_price") or p["entry_price"]), "partial_full")
            px = float(exit_price) if exit_price else float(p.get("current_price") or p["entry_price"])
            proceeds = round(px * close_shares, 2)
            cost_basis = round(float(p["entry_price"]) * close_shares, 2)
            pnl_dollars = round(proceeds - cost_basis, 2)
            pnl_pct = round((px / float(p["entry_price"]) - 1) * 100, 2) if p["entry_price"] else 0.0
            today = date.today().isoformat()
            month_key = today[:7]
            trade = {
                "ticker": ticker,
                "entry_date": p["entry_date"],
                "exit_date": today,
                "entry_price": p["entry_price"],
                "exit_price": round(px, 2),
                "shares": close_shares,
                "pnl_dollars": pnl_dollars,
                "pnl_pct": pnl_pct,
                "exit_reason": "partial_t1",
                "setup_type": p.get("setup_type", ""),
            }
            state["closed_trades"].append(trade)
            state["cash"] = round(state["cash"] + proceeds, 2)
            state["monthly_pnl"][month_key] = round(state["monthly_pnl"].get(month_key, 0) + pnl_dollars, 2)
            # Reduce position in place
            p["shares"] = total_shares - close_shares
            p["position_size"] = round(float(p["entry_price"]) * p["shares"], 2)
            _save_state(state)
            return {"ok": True, "ticker": ticker, "closed_shares": close_shares,
                    "remaining_shares": p["shares"], "pnl_dollars": pnl_dollars}
    raise ValueError(f"No open position for {ticker}")


def adjust_stop(ticker: str, new_stop: float) -> dict:
    """Set an explicit new stop price for an open position."""
    state = _load_state()
    ticker = ticker.upper()
    new_stop = round(float(new_stop), 2)
    if new_stop <= 0:
        raise ValueError("new_stop must be > 0")
    for p in state["positions"]:
        if p["ticker"] == ticker:
            p["stop"] = new_stop
            if new_stop > (p.get("trail_stop") or 0):
                p["trail_stop"] = new_stop
            _save_state(state)
            return {"ok": True, "ticker": ticker, "new_stop": new_stop}
    raise ValueError(f"No open position for {ticker}")


def update_prices(price_map: dict[str, float]) -> list[dict]:
    """
    Update current prices for open positions.  Adjusts trailing stops
    and returns a list of positions whose trail stop was hit.

    price_map: {"FCX": 69.50, "AAPL": 195.20, ...}
    """
    state = _load_state()
    stopped_out = []
    trail_activate_pct = CFG.get("trail_activate_pct", 2.0)
    trail_atr_mult = CFG.get("trail_atr_mult", 1.25)

    for pos in state["positions"]:
        ticker = pos["ticker"]
        if ticker not in price_map:
            continue

        current = price_map[ticker]
        entry = pos["entry_price"]

        # Track highest price
        if current > pos.get("highest_price", entry):
            pos["highest_price"] = round(current, 2)

        # Activate trailing stop once gain >= threshold
        gain_pct = ((current / entry) - 1) * 100 if entry else 0
        if gain_pct >= trail_activate_pct and not pos.get("trail_active", False):
            pos["trail_active"] = True

        # Update trailing stop if active
        if pos.get("trail_active", False):
            # Simple trailing: highest - trail_atr_mult * (entry - original_stop) as ATR proxy
            atr_proxy = abs(entry - pos["stop"])
            new_trail = round(pos["highest_price"] - trail_atr_mult * atr_proxy, 2)
            if new_trail > pos.get("trail_stop", pos["stop"]):
                pos["trail_stop"] = new_trail

        # Check if stop was hit
        effective_stop = pos.get("trail_stop", pos["stop"])
        if current <= effective_stop:
            stopped_out.append(pos)

    # Recalculate equity = cash + invested value of LONG positions only
    # (shorts are liabilities, margin is held separately — matches close_position invariant)
    invested = 0
    for pos in state["positions"]:
        if pos.get("direction", "long") != "long":
            continue
        ticker = pos["ticker"]
        px = price_map.get(ticker, pos["entry_price"])
        invested += px * pos["shares"]
    state["equity"] = round(state["cash"] + invested, 2)

    today = date.today().isoformat()
    curve = state.get("equity_curve", [])
    if not curve or curve[-1]["date"] != today:
        curve.append({"date": today, "equity": state["equity"]})
    else:
        curve[-1]["equity"] = state["equity"]
    state["equity_curve"] = curve

    _save_state(state)
    return stopped_out


def cross_mode_aggregate() -> dict:
    """
    P2.24 — Cross-mode position awareness.

    Aggregates exposure by ticker across all modes (Swing/Position/Invest)
    so the system can warn about contradictory signals OR concentration.

    Returns:
      {
        by_ticker: {SYM: {modes: ['swing','position'], total_shares: int,
                          total_value: float, sectors: ['Energy'], directions: ['long']}},
        sector_exposure: {Energy: 25_000, Tech: 12_000, ...},
        total_exposure: float,
        contradictions: [{ticker, modes, issue}],
        sector_concentration: [{sector, pct, threshold_breach}],
      }
    """
    state = _load_state()
    positions = state.get("positions") or []

    by_ticker: dict = {}
    sector_exposure: dict = {}
    total_value = 0.0
    contradictions: list = []

    for p in positions:
        sym = p.get("ticker", "").upper()
        if not sym:
            continue
        mode = p.get("mode") or "swing"
        direction = p.get("direction", "long")
        shares = p.get("shares", 0) or 0
        entry = p.get("entry_price", 0) or 0
        value = shares * entry
        sector = p.get("sector") or p.get("info", {}).get("sector", "Unknown")

        if sym not in by_ticker:
            by_ticker[sym] = {
                "modes": [], "total_shares": 0, "total_value": 0,
                "sectors": [], "directions": [],
            }
        bt = by_ticker[sym]
        bt["modes"].append(mode)
        bt["total_shares"] += shares
        bt["total_value"] += value
        if sector not in bt["sectors"]:
            bt["sectors"].append(sector)
        if direction not in bt["directions"]:
            bt["directions"].append(direction)

        sector_exposure[sector] = sector_exposure.get(sector, 0) + value
        total_value += value

    # Detect contradictions: same ticker long+short, or same ticker in 3+ modes
    for sym, bt in by_ticker.items():
        if "long" in bt["directions"] and "short" in bt["directions"]:
            contradictions.append({
                "ticker": sym, "modes": bt["modes"],
                "issue": "Long + short positions on same ticker — net out before scaling",
            })
        if len(bt["modes"]) >= 3:
            contradictions.append({
                "ticker": sym, "modes": bt["modes"],
                "issue": "Held in 3+ modes — concentration risk",
            })

    # Sector concentration — flag any sector >30% of book
    sector_concentration = []
    for sec, val in sector_exposure.items():
        pct = (val / total_value * 100) if total_value > 0 else 0
        sector_concentration.append({
            "sector": sec, "value": round(val, 2), "pct": round(pct, 2),
            "threshold_breach": pct > 30,
        })
    sector_concentration.sort(key=lambda x: -x["pct"])

    return {
        "by_ticker": by_ticker,
        "sector_exposure": sector_exposure,
        "total_exposure": round(total_value, 2),
        "contradictions": contradictions,
        "sector_concentration": sector_concentration,
    }


def wash_sale_check(ticker: str, action: str = "buy") -> dict:
    """
    P2.25 — Wash-sale warning.

    Returns flag indicating whether opening or closing a position on `ticker`
    triggers a wash-sale concern under IRS rules:
    - Sold at loss within last 30 days, now buying back → wash-sale violation
    - Same ticker exists in another mode → cross-mode tracking
    - Identical lot sizes within 30 days → potentially substantially identical

    Returns: {risk: bool, severity: 'none|low|medium|high', reasons: [...]}
    """
    state = _load_state()
    closed = state.get("closed_trades") or []
    positions = state.get("positions") or []
    ticker = ticker.upper()
    today = date.today()
    reasons: list = []
    severity = "none"

    if action == "buy":
        # Look for losses on this ticker in last 30 days
        for trade in closed[-50:]:  # last 50 closed trades
            if trade.get("ticker", "").upper() != ticker:
                continue
            exit_date_str = trade.get("exit_date") or ""
            try:
                ed = datetime.strptime(exit_date_str[:10], "%Y-%m-%d").date()
            except Exception:
                continue
            days_since = (today - ed).days
            if 0 <= days_since <= 30 and (trade.get("pnl_dollars") or 0) < 0:
                reasons.append(
                    f"Closed {ticker} at ${abs(trade.get('pnl_dollars', 0)):.0f} loss "
                    f"on {exit_date_str[:10]} ({days_since}d ago) — wash-sale window active"
                )
                severity = "high"

    # Cross-mode: ticker held in another mode
    held_modes = [p.get("mode", "swing") for p in positions if p.get("ticker", "").upper() == ticker]
    if len(held_modes) > 0:
        reasons.append(f"Already held in mode(s): {', '.join(held_modes)}")
        if severity == "none":
            severity = "low"

    return {
        "risk": severity != "none",
        "severity": severity,
        "reasons": reasons,
    }


def check_circuit_breaker() -> dict:
    """
    P2.22 — Drawdown circuit breaker.

    Inspects recent closed_trades and equity_curve. Returns risk-adjustment
    state for downstream sizing decisions:
      {
        "active": bool,
        "level":  "normal" | "size_50pct" | "pause_3d" | "risk_off" | "stop_new_trades",
        "reasons": [...],
        "consecutive_losers": int,
        "drawdown_pct": float,
        "drawdown_10d_pct": float,
        "next_unlock_date": str | None,  # YYYY-MM-DD if paused
      }

    Triggers (per Phase 2 feedback item #22):
      3 consecutive losers       → reduce new size by 50%
      5 consecutive losers       → pause new entries 3 trading days
      drawdown > 4% in 10 days   → risk-off mode
      drawdown > 8% from peak    → stop new trades until manual review
    """
    state = _load_state()
    closed = state.get("closed_trades") or []
    curve = state.get("equity_curve") or []
    reasons: list[str] = []
    level = "normal"

    # Consecutive losers — count back from latest closed trade
    consecutive_losers = 0
    for trade in reversed(closed):
        pnl = trade.get("pnl_dollars", 0) or 0
        if pnl < 0:
            consecutive_losers += 1
        else:
            break

    # Tier 1A (2026-05-07): institutional-standard drawdown calculation.
    # Hard halt uses REALIZED drawdown (closed trades only) to prevent paper-gain
    # volatility from halting all trading. MTM drawdown still tracked for soft
    # warnings + progressive sizing.
    starting_eq = float(state.get("starting_equity") or 100000)
    realized_pnl = sum(float(t.get("pnl_dollars") or 0) for t in closed)
    realized_eq = starting_eq + realized_pnl
    realized_peak = max(starting_eq, realized_eq)  # peak = high-water mark of realized
    realized_dd_pct = max(0.0, (realized_peak - realized_eq) / realized_peak * 100) if realized_peak > 0 else 0.0

    # MTM drawdown — kept for size scaling + soft warnings only, NOT for hard halt
    peak = 0.0
    cur_eq = state.get("equity") or 0
    for pt in curve:
        eq = pt.get("equity") or 0
        if eq > peak:
            peak = eq
    drawdown_pct = ((peak - cur_eq) / peak * 100) if peak > 0 else 0.0

    # Drawdown over last 10 trading days (MTM, used for risk-off mode)
    drawdown_10d_pct = 0.0
    if len(curve) >= 11:
        recent = curve[-11:]
        recent_peak = max(pt.get("equity", 0) for pt in recent)
        recent_now = recent[-1].get("equity") or 0
        if recent_peak > 0:
            drawdown_10d_pct = (recent_peak - recent_now) / recent_peak * 100

    # Apply rules from least-restrictive to most-restrictive (later overwrites earlier)
    if consecutive_losers >= 3 and consecutive_losers < 5:
        level = "size_50pct"
        reasons.append(f"{consecutive_losers} consecutive losers — reduce new size 50%")
    if consecutive_losers >= 5:
        level = "pause_3d"
        reasons.append(f"{consecutive_losers} consecutive losers — pause new entries 3 trading days")
    if drawdown_10d_pct > 4 and level not in ("pause_3d", "stop_new_trades"):
        level = "risk_off"
        reasons.append(f"MTM drawdown {drawdown_10d_pct:.1f}% in last 10d > 4% — risk-off mode (sizing reduced)")
    # Hard halt uses REALIZED drawdown only — paper-gain volatility doesn't trigger this
    if realized_dd_pct > 8:
        level = "stop_new_trades"
        reasons.append(f"realized drawdown {realized_dd_pct:.1f}% > 8% — stop new trades until review")

    next_unlock = None
    if level == "pause_3d":
        last_close = closed[-1] if closed else {}
        last_date = last_close.get("exit_date")
        if last_date:
            try:
                d = datetime.fromisoformat(last_date) + timedelta(days=3)
                next_unlock = d.isoformat()[:10]
            except Exception:
                pass

    return {
        "active": level != "normal",
        "level": level,
        "reasons": reasons,
        "consecutive_losers": consecutive_losers,
        "drawdown_pct": round(drawdown_pct, 2),                # MTM (mark-to-market, includes paper)
        "realized_drawdown_pct": round(realized_dd_pct, 2),     # closed trades only — used for hard halt
        "drawdown_10d_pct": round(drawdown_10d_pct, 2),
        "next_unlock_date": next_unlock,
    }


def get_open_slots() -> int:
    """Return number of available position slots."""
    state = _load_state()
    max_pos = CFG.get("max_positions", 999)
    return max(0, max_pos - len(state["positions"]))


def set_equity(new_equity: float, reason: str = "") -> dict:
    """Set portfolio equity. Adjusts cash = new_equity - invested_amount."""
    state = _load_state()
    new_equity = round(float(new_equity), 2)
    if new_equity <= 0:
        raise ValueError("Equity must be positive")

    invested = round(sum(
        p.get("shares", 0) * p.get("entry_price", 0)
        for p in state.get("positions", [])
        if p.get("direction", "long") == "long"
    ), 2)

    if new_equity < invested:
        raise ValueError(f"Equity ${new_equity} less than invested ${invested}. Close positions first.")

    new_cash = round(new_equity - invested, 2)
    margin_held = round(state.get("margin_reserved", 0), 2)
    if new_cash - margin_held < 0:
        raise ValueError(
            f"Equity ${new_equity} would leave cash ${new_cash} below margin reserved ${margin_held} for short positions. "
            f"Close shorts first or set higher equity."
        )
    old_equity = state.get("equity", 0)
    old_cash = state.get("cash", 0)

    state["equity"] = new_equity
    state["cash"] = new_cash

    # Audit log
    audit = state.setdefault("equity_audit", [])
    audit.append({
        "timestamp": datetime.now().isoformat(),
        "old_equity": old_equity,
        "new_equity": new_equity,
        "old_cash": old_cash,
        "new_cash": new_cash,
        "invested": invested,
        "reason": reason or "manual edit",
    })

    _save_state(state)
    return {"equity": new_equity, "cash": new_cash, "invested": invested}


def get_equity_audit_log(limit: int = 50) -> list[dict]:
    """Return recent equity change audit entries, newest first."""
    state = _load_state()
    audit = state.get("equity_audit", [])
    return list(reversed(audit[-limit:]))


def _add_earnings_context(summary: dict) -> dict:
    """Enrich open positions with ``days_to_earnings`` / ``earnings_date``.

    Uses ``data_fetcher.get_earnings_date`` (which is itself @_mem_cached for 2h,
    so repeated render calls within a scan hit the in-process cache rather than
    re-fetching). Graceful: any failure is swallowed and the position is left
    un-annotated.

    ``get_earnings_date`` returns ``{"earnings_date": "...", "days_to_earnings": N,
    "earnings_risk": bool}`` — we normalize that, and also accept a raw date /
    datetime / ISO string for forward-compat.
    """
    try:
        from data_fetcher import get_earnings_date
    except Exception:
        return summary

    from datetime import date as _d, datetime as _dt
    today = _d.today()
    for p in summary.get("positions", []) or []:
        try:
            tkr = str(p.get("ticker", "") or "").upper()
            if not tkr:
                continue
            res = get_earnings_date(tkr)
            ed_date = None
            delta = None
            if isinstance(res, dict):
                dte = res.get("days_to_earnings")
                raw = res.get("earnings_date")
                if dte is not None:
                    try:
                        delta = int(dte)
                    except Exception:
                        delta = None
                if raw:
                    try:
                        ed_date = _dt.strptime(str(raw)[:10], "%Y-%m-%d").date()
                    except Exception:
                        ed_date = None
            elif isinstance(res, str):
                try:
                    ed_date = _dt.strptime(res[:10], "%Y-%m-%d").date()
                except Exception:
                    ed_date = None
            elif hasattr(res, "year"):
                ed_date = res if not hasattr(res, "date") else res.date() if hasattr(res, "hour") else res
            if delta is None and ed_date is not None:
                delta = (ed_date - today).days
            if delta is not None and 0 <= delta <= 30:
                p["days_to_earnings"] = delta
                if ed_date is not None:
                    p["earnings_date"] = ed_date.isoformat()
        except Exception:
            continue
    return summary


def get_portfolio_summary() -> dict:
    """
    Return a summary dict for the dashboard:
      equity, cash, invested, positions, open_slots, open_pnl,
      closed_pnl, monthly_pnl, equity_curve, win_rate
    """
    state = _load_state()
    max_pos = CFG.get("max_positions", 999)

    # Calculate days_held for each position
    from datetime import date as _date
    _today = _date.today()
    for p in state["positions"]:
        try:
            _entry = _date.fromisoformat(str(p.get("entry_date", ""))[:10])
            p["days_held"] = (_today - _entry).days
        except Exception:
            p["days_held"] = 0

    # Invested = cash committed to longs only (shorts move no cash on open)
    invested = sum(
        p["position_size"] for p in state["positions"]
        if p.get("direction", "long") == "long"
    )
    # Short exposure shown separately for risk display
    short_exposure = sum(
        p["position_size"] for p in state["positions"]
        if p.get("direction", "long") == "short"
    )
    open_count = len(state["positions"])
    closed = state.get("closed_trades", [])
    closed_pnl = sum(t.get("pnl_dollars", 0) for t in closed)
    wins = sum(1 for t in closed if t.get("pnl_dollars", 0) > 0)
    losses = sum(1 for t in closed if t.get("pnl_dollars", 0) <= 0)
    win_rate = round(wins / len(closed) * 100, 1) if closed else 0.0

    _summary = {
        "equity": state.get("equity", CFG.get("starting_equity", 5000)),
        "cash": state.get("cash", 0),
        "invested": round(invested, 2),
        "short_exposure": round(short_exposure, 2),
        "margin_reserved": round(state.get("margin_reserved", 0), 2),
        "positions": state["positions"],
        "open_count": open_count,
        "max_positions": max_pos,
        "open_slots": max(0, max_pos - open_count),
        "closed_pnl": round(closed_pnl, 2),
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "monthly_pnl": state.get("monthly_pnl", {}),
        "equity_curve": state.get("equity_curve", []),
        "closed_trades": closed,
        "config_label": CFG.get("label", "Config E"),
    }
    # Enrich each open position with days_to_earnings for dashboard badges.
    # Guarded inside the helper; silent no-op if data_fetcher unavailable.
    try:
        _add_earnings_context(_summary)
    except Exception:
        pass
    return _summary


def check_gap_down(ticker: str, threshold: float = -3.0) -> dict | None:
    """AI-46: Detect a gap-down open for a single ticker.

    Compares today's OPEN against the prior day's CLOSE. If the gap is at or
    below ``threshold`` (default -3.0 %), return an EXIT action dict; otherwise
    return ``None``. Uses Polygon snapshot first, then falls back to OHLCV bars.

    Returns: ``{"ticker", "action": "EXIT", "reason", "gap_pct"}`` or ``None``.
    """
    today_open: float | None = None
    prev_close: float | None = None
    try:
        from data_fetcher import get_polygon_snapshot
        snap = get_polygon_snapshot([ticker]) or {}
        data = snap.get(ticker, {}) or {}
        o = data.get("open")
        pc = data.get("prev_close")
        if o and pc:
            today_open = float(o)
            prev_close = float(pc)
    except Exception:
        pass

    if today_open is None or prev_close is None:
        try:
            from data_fetcher import get_polygon_ohlcv
            df = get_polygon_ohlcv(ticker, days=5)
            if df is not None and len(df) >= 2:
                today_open = float(df["Open"].iloc[-1])
                prev_close = float(df["Close"].iloc[-2])
        except Exception:
            return None

    if not today_open or not prev_close or prev_close <= 0:
        return None

    gap_pct = (today_open / prev_close - 1) * 100
    if gap_pct <= threshold:
        return {
            "ticker": ticker,
            "action": "EXIT",
            "reason": f"Gap down {gap_pct:.1f}% at open — binary bad news",
            "gap_pct": round(gap_pct, 2),
        }
    return None


def generate_exit_actions(price_map: dict[str, float] | None = None) -> list[dict]:
    """
    Check all open positions and generate actionable exit/hold/tighten signals.
    Called during each scan to tell the user what to do with existing positions.

    Returns list of actions:
    [
        {"ticker": "NOV", "action": "HOLD", "reason": "Up +3.2%, trail stop moved to $19.20",
         "entry": 18.70, "current": 19.30, "pnl_pct": 3.2, "stop": 19.20, "days_held": 3},
        {"ticker": "FCX", "action": "EXIT", "reason": "Hit T1 target $73.50",
         "entry": 67.80, "current": 73.60, "pnl_pct": 8.5, "stop": 71.00, "days_held": 5},
        {"ticker": "ROIV", "action": "TIGHTEN", "reason": "At breakeven, move stop to $28.50",
         "entry": 28.40, "current": 28.55, "pnl_pct": 0.5, "stop": 28.50, "days_held": 4},
    ]
    """
    state = _load_state()
    positions = state.get("positions", [])
    if not positions:
        return []

    # Fetch live prices if not provided
    gap_map: dict[str, dict] = {}  # ticker -> {"open": float, "prev_close": float}
    if price_map is None:
        try:
            from data_fetcher import get_polygon_snapshot
            tickers = [p["ticker"] for p in positions]
            snap = get_polygon_snapshot(tickers)
            price_map = {}
            for t, data in snap.items():
                px = data.get("price") or data.get("close")
                if px:
                    price_map[t] = float(px)
                o = data.get("open")
                pc = data.get("prev_close")
                if o and pc:
                    gap_map[t] = {"open": float(o), "prev_close": float(pc)}
        except Exception:
            price_map = {}

    GAP_DOWN_THRESHOLD = -3.0  # percent

    trail_activate_pct = CFG.get("trail_activate_pct", 2.0)
    trail_atr_mult = CFG.get("trail_atr_mult", 1.25)
    max_hold_days = CFG.get("max_hold_days", 10)
    hold_days = CFG.get("hold_days", 5)

    actions = []
    today = date.today()

    for pos in positions:
        ticker = pos["ticker"]
        entry = pos["entry_price"]
        current = price_map.get(ticker)
        if current is None:
            current = pos.get("highest_price", entry)

        # Days held
        try:
            entry_dt = date.fromisoformat(pos["entry_date"])
            days_held = (today - entry_dt).days
        except Exception:
            days_held = 0

        pnl_pct = round((current / entry - 1) * 100, 2) if entry else 0.0
        effective_stop = pos.get("trail_stop", pos.get("stop", 0))
        target1 = pos.get("target1", 0)
        atr_proxy = abs(entry - pos.get("stop", entry * 0.97))

        action = None
        reason = ""

        # ── EXIT conditions ──
        # 1. Stop hit
        if current <= effective_stop:
            action = "EXIT"
            reason = f"Stop hit at ${effective_stop:.2f}"
        # 2. Target hit
        elif target1 and current >= target1:
            action = "EXIT"
            reason = f"Hit T1 target ${target1:.2f}"
        # 3. Max hold days exceeded
        elif days_held >= max_hold_days:
            action = "EXIT"
            if pnl_pct >= 0:
                reason = f"Max hold {max_hold_days}d reached — take profit"
            else:
                reason = f"Max hold {max_hold_days}d reached — time stop"

        # ── Gap-down auto-close (AI-46) ──
        # Runs AFTER stop/target/max-hold EXIT checks (so it won't override a known EXIT reason),
        # but BEFORE WARNING/TIGHTEN/TRAIL so binary bad news takes priority.
        if action is None:
            gi = gap_map.get(ticker)
            today_open = gi.get("open") if gi else None
            prev_close = gi.get("prev_close") if gi else None
            if (today_open is None or prev_close is None):
                try:
                    from data_fetcher import get_polygon_ohlcv
                    df = get_polygon_ohlcv(ticker, days=5)
                    if df is not None and len(df) >= 2:
                        today_open = float(df["Open"].iloc[-1])
                        prev_close = float(df["Close"].iloc[-2])
                except Exception:
                    pass
            if today_open and prev_close and prev_close > 0:
                gap_pct = (today_open / prev_close - 1) * 100
                if gap_pct <= GAP_DOWN_THRESHOLD:
                    action = "EXIT"
                    reason = f"Gap down {gap_pct:.1f}% at open — binary bad news"

        # ── WARNING: approaching stop ──
        if action is None and effective_stop > 0 and current > effective_stop:
            stop_distance_pct = (current - effective_stop) / current * 100
            if stop_distance_pct < 1.5:
                action = "WARNING"
                reason = f"Only {stop_distance_pct:.1f}% above stop ${effective_stop:.2f}"

        # ── TIGHTEN: profitable but trail not yet active → suggest moving stop to breakeven ──
        if action is None and pnl_pct > 0 and pnl_pct < trail_activate_pct:
            if effective_stop < entry:
                action = "TIGHTEN"
                new_stop = round(entry + atr_proxy * 0.1, 2)  # just above breakeven
                reason = f"At breakeven, move stop to ${new_stop:.2f}"
                effective_stop = new_stop
            elif days_held >= hold_days and not pos.get("trail_active", False):
                action = "TIGHTEN"
                new_stop = round(current - atr_proxy * 0.5, 2)
                reason = f"Day {days_held} of {hold_days}, tighten stop to ${new_stop:.2f}"
                effective_stop = new_stop

        # ── HOLD: everything on track ──
        if action is None:
            action = "HOLD"
            if pos.get("trail_active", False):
                reason = f"Up {pnl_pct:+.1f}%, trail stop moved to ${effective_stop:.2f}"
            elif pnl_pct >= 0:
                reason = f"Up {pnl_pct:+.1f}% (${current:.2f}), on track"
            else:
                reason = f"Down {pnl_pct:.1f}% (${current:.2f}), stop ${effective_stop:.2f} intact"

        actions.append({
            "ticker": ticker,
            "action": action,
            "reason": reason,
            "entry": entry,
            "current": round(current, 2),
            "pnl_pct": pnl_pct,
            "stop": round(effective_stop, 2),
            "target1": round(target1, 2) if target1 else None,
            "days_held": days_held,
            "max_hold_days": max_hold_days,
            "setup_type": pos.get("setup_type", ""),
            "shares": pos.get("shares", 0),
            "trail_active": pos.get("trail_active", False),
        })

    # Sort: EXIT first, then WARNING, TIGHTEN, HOLD
    _action_order = {"EXIT": 0, "WARNING": 1, "TRIM": 1, "TIGHTEN": 2, "HOLD": 3}
    actions.sort(key=lambda a: _action_order.get(a["action"], 9))
    return actions


def runner_protection_trim(max_position_pct: float = 25.0,
                            trim_to_pct: float = 15.0) -> list[dict]:
    """Suggest TRIM actions when any position exceeds max_position_pct of equity.

    Returns list of {ticker, current_pct, target_pct, shares_to_trim, proceeds}.
    Called by EOD manager; surfaces in dashboard Portfolio tab.
    """
    state = _load_state()
    equity = float(state.get("equity", 5000) or 5000)
    positions = state.get("positions", [])
    trims = []
    for p in positions:
        current_px = float(p.get("current_price") or p.get("entry_price", 0))
        shares = int(p.get("shares", 0))
        value = current_px * shares
        if equity <= 0 or value <= 0:
            continue
        pct = value / equity * 100
        if pct > max_position_pct:
            target_value = equity * (trim_to_pct / 100)
            target_shares = max(1, int(target_value / current_px))
            trim_shares = max(0, shares - target_shares)
            if trim_shares > 0:
                trims.append({
                    "ticker": p["ticker"],
                    "current_pct": round(pct, 1),
                    "target_pct": round(trim_to_pct, 1),
                    "shares_to_trim": trim_shares,
                    "proceeds": round(trim_shares * current_px, 0),
                    "reason": f"Position at {pct:.0f}% of equity exceeds {max_position_pct:.0f}% cap — trim to {trim_to_pct:.0f}%",
                })
    return trims


def flat_position_exits(flat_threshold_pct: float = 1.5,
                        flat_max_days: int = 3) -> list[dict]:
    """Surface positions that are flat (within ±flat_threshold_pct) for too long.

    Capital parked in non-moving positions is dead weight — release it.
    Returns list of tickers to consider closing.
    """
    from datetime import date as _date
    state = _load_state()
    positions = state.get("positions", [])
    today = _date.today()
    flats = []
    for p in positions:
        try:
            entry = float(p.get("entry_price", 0))
            current = float(p.get("current_price") or entry)
            if entry <= 0:
                continue
            pct = abs(current - entry) / entry * 100
            entry_dt = _date.fromisoformat(str(p.get("entry_date", ""))[:10])
            days = (today - entry_dt).days
        except Exception:
            continue
        if days >= flat_max_days and pct < flat_threshold_pct:
            flats.append({
                "ticker": p["ticker"],
                "pct_chg": round((current - entry) / entry * 100, 2),
                "days_held": days,
                "reason": f"Flat {pct:.1f}% after {days} days — release capital",
            })
    return flats


def get_monthly_pnl() -> dict[str, float]:
    """Return monthly P&L history: {"2026-04": -25.50, "2026-05": 340.00, ...}"""
    state = _load_state()
    return state.get("monthly_pnl", {})


# ─────────────────────────────────────────────────────────────────────────────
# Backward-compatibility shims ported from the deprecated portfolio.py module.
# portfolio_tracker.py is now the single source of truth for portfolio state.
# These helpers adapt the previous portfolio.py public API to the
# portfolio_state.json schema (entry_price / closed_trades / position_size).
# ─────────────────────────────────────────────────────────────────────────────

import logging as _logging
from datetime import timedelta as _timedelta

_log_compat = _logging.getLogger("swingtrade.portfolio_tracker.compat")

# Alias so legacy callers that imported PORTFOLIO_PATH keep working.
PORTFOLIO_PATH = STATE_PATH


def load_portfolio() -> dict:
    """
    Return the raw portfolio state dict.

    Legacy callers expect keys 'positions' and 'closed' — we provide both
    'closed_trades' (native) and a 'closed' alias for compatibility.
    """
    state = _load_state()
    if "closed" not in state:
        state["closed"] = state.get("closed_trades", [])
    return state


def refresh_prices() -> list[dict]:
    """
    Fetch current prices for all open positions via yfinance and update P&L.

    Mirrors the legacy portfolio.refresh_prices() behaviour but operates on
    portfolio_state.json (entry_price / position_size fields).
    """
    try:
        from data_fetcher import yf  # _YfStub (yfinance removed 2026-04-25)
    except ImportError:
        _log_compat.warning("yfinance not available - refresh_prices is a no-op")
        return []

    state = _load_state()
    positions = state.get("positions", [])
    if not positions:
        # P0 (2026-05-10): even with no open positions, snapshot today's
        # equity (= cash) so the curve is dense enough for drawdown lookback.
        today = date.today().isoformat()
        curve = state.get("equity_curve") or []
        eq = round(state.get("cash", state.get("equity", 0)), 2)
        if not curve or curve[-1].get("date") != today:
            curve.append({"date": today, "equity": eq})
        else:
            curve[-1]["equity"] = eq
        state["equity"] = eq
        state["equity_curve"] = curve
        _save_state(state)
        return []

    tickers = [p["ticker"] for p in positions]
    prices: dict[str, float] = {}
    try:
        raw = yf.download(tickers if len(tickers) > 1 else tickers[0],
                          period="1d", interval="1m", progress=False)
        if len(tickers) == 1:
            if not raw.empty:
                prices[tickers[0]] = float(raw["Close"].iloc[-1])
        else:
            for t in tickers:
                try:
                    prices[t] = float(raw["Close"][t].dropna().iloc[-1])
                except Exception:
                    pass
    except Exception as e:
        _log_compat.warning(f"refresh_prices download failed: {e}")
        # P0 (2026-05-10): even on price-fetch failure, snapshot today's
        # equity using last-known prices so the curve doesn't go stale.
        today = date.today().isoformat()
        invested = 0.0
        for pos in positions:
            if pos.get("direction", "long") != "long":
                continue
            px = float(pos.get("current_price") or pos.get("entry_price") or 0)
            invested += px * pos.get("shares", 0)
        state["equity"] = round(state.get("cash", 0) + invested, 2)
        curve = state.get("equity_curve") or []
        if not curve or curve[-1].get("date") != today:
            curve.append({"date": today, "equity": state["equity"]})
        state["equity_curve"] = curve
        _save_state(state)
        return positions

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    for pos in positions:
        t = pos["ticker"]
        if t not in prices:
            continue
        cur = prices[t]
        entry = float(pos.get("entry_price", 0) or 0)
        if entry <= 0:
            continue
        direction = pos.get("direction", "long")
        if direction == "long":
            pnl_pct = (cur - entry) / entry * 100
        else:
            pnl_pct = (entry - cur) / entry * 100
        pnl_dollars = pnl_pct / 100 * entry * pos.get("shares", 0)
        pos["current_price"] = round(cur, 2)
        pos["unrealized_pnl_pct"] = round(pnl_pct, 2)
        pos["unrealized_pnl_dollars"] = round(pnl_dollars, 2)
        pos["last_updated"] = now

        stop = pos.get("stop", 0) or 0
        t1 = pos.get("target1", 0) or 0
        t2 = pos.get("target2")
        if direction == "long":
            pos["stop_hit"] = cur <= stop
            pos["t1_hit"] = cur >= t1 if t1 else False
            pos["t2_hit"] = bool(t2 and cur >= t2)
        else:
            pos["stop_hit"] = cur >= stop
            pos["t1_hit"] = cur <= t1 if t1 else False
            pos["t2_hit"] = bool(t2 and cur <= t2)

        # Move stop to breakeven only after T1 is confirmed hit.
        try:
            if pos.get("t1_hit"):
                if direction == "long":
                    be_stop = round(entry * 1.005, 2)
                    if pos.get("stop", 0) < be_stop:
                        pos["stop"] = be_stop
                        pos["stop_note"] = "Moved to breakeven after T1"
                elif direction == "short":
                    be_stop = round(entry * 0.995, 2)
                    if pos.get("stop", 9999) > be_stop:
                        pos["stop"] = be_stop
                        pos["stop_note"] = "Moved to breakeven after T1"
            if pos.get("t1_hit") and not pos.get("t1_partial_taken"):
                pos["t1_partial_alert"] = True
        except Exception:
            pass

    # P0 (2026-05-10): daily equity_curve snapshot from mark-to-market.
    # Without this, equity_curve only gets a point on close_position(), so
    # compute_current_drawdown_pct stays stale → kelly_size.drawdown_mult is
    # a no-op. Append/update today's point using current cash + invested
    # value of LONG positions only (shorts are liabilities tracked
    # separately, matches close_position invariant).
    invested = 0.0
    for pos in state["positions"]:
        if pos.get("direction", "long") != "long":
            continue
        t = pos["ticker"]
        px = float(prices.get(t, pos.get("current_price") or pos.get("entry_price") or 0) or 0)
        invested += px * pos.get("shares", 0)
    state["equity"] = round(state.get("cash", 0) + invested, 2)
    today = date.today().isoformat()
    curve = state.get("equity_curve") or []
    if not curve or curve[-1].get("date") != today:
        curve.append({"date": today, "equity": state["equity"]})
    else:
        curve[-1]["equity"] = state["equity"]
    state["equity_curve"] = curve

    _save_state(state)
    return positions


# --- Correlation helpers (ported from portfolio.py) --------------------------
_corr_cache: dict = {}
_CORR_CACHE_TTL_MINUTES = 30


def _get_returns(tickers: list[str], period: str = "3mo"):
    """Download daily returns for tickers; cached for 30 min."""
    try:
        import pandas as pd  # type: ignore
        from data_fetcher import yf  # _YfStub (yfinance removed 2026-04-25)
    except ImportError:
        _log_compat.warning("pandas/yfinance unavailable - correlation disabled")
        return None

    if not tickers:
        return pd.DataFrame()

    cache_key = f"{sorted(tickers)}|{period}"
    now = datetime.now()
    if cache_key in _corr_cache:
        cached_at, cached_df = _corr_cache[cache_key]
        if now - cached_at < _timedelta(minutes=_CORR_CACHE_TTL_MINUTES):
            return cached_df

    try:
        raw = yf.download(
            tickers if len(tickers) > 1 else tickers[0],
            period=period, interval="1d", progress=False, auto_adjust=True,
        )
        if raw.empty:
            return pd.DataFrame()
        if len(tickers) == 1:
            close = raw["Close"].squeeze().rename(tickers[0])
            prices = pd.DataFrame({tickers[0]: close})
        else:
            prices = raw["Close"] if raw.columns.nlevels > 1 else raw[["Close"]]
        returns = prices.pct_change().dropna(how="all")
        _corr_cache[cache_key] = (now, returns)
        return returns
    except Exception as e:
        _log_compat.warning(f"_get_returns failed for {tickers}: {e}")
        return pd.DataFrame()


def compute_pairwise_correlation(tickers: list[str], period: str = "3mo") -> dict:
    """Pairwise Pearson correlation between tickers using daily returns."""
    try:
        import pandas as pd  # type: ignore
    except ImportError:
        return {}
    if len(tickers) < 2:
        return {}
    returns = _get_returns(tickers, period)
    if returns is None or returns.empty or returns.shape[1] < 2:
        return {}
    available = [t for t in tickers if t in returns.columns]
    if len(available) < 2:
        return {}
    corr_matrix = returns[available].corr(method="pearson")
    pairs: dict = {}
    for i, t1 in enumerate(available):
        for t2 in available[i + 1:]:
            overlap = returns[[t1, t2]].dropna()
            if len(overlap) < 20:
                continue
            val = corr_matrix.loc[t1, t2]
            if pd.isna(val):
                continue
            pair = tuple(sorted([t1, t2]))
            pairs[pair] = round(float(val), 4)
    return pairs


def check_correlation_risk(candidate: str, open_positions: list[str],
                           threshold: float = 0.80, period: str = "3mo",
                           sector_map: dict | None = None) -> dict:
    """Check whether candidate is highly correlated with any open position."""
    candidate = candidate.upper()
    open_positions = [t.upper() for t in open_positions]
    if not open_positions:
        return {
            "has_risk": False, "correlated_with": [],
            "max_correlation": 0.0, "sector_count": {},
            "sector_risk": False,
            "message": "No open positions to compare against",
        }
    all_tickers = [candidate] + open_positions
    pairs = compute_pairwise_correlation(all_tickers, period=period)
    correlated_with = []
    for (t1, t2), corr in pairs.items():
        other = t2 if t1 == candidate else (t1 if t2 == candidate else None)
        if other and corr >= threshold:
            correlated_with.append({"ticker": other, "correlation": corr})
    correlated_with.sort(key=lambda x: x["correlation"], reverse=True)
    max_corr = correlated_with[0]["correlation"] if correlated_with else 0.0

    sector_count: dict[str, int] = {}
    if sector_map is None:
        sector_map = {}
        try:
            from data_fetcher import yf  # _YfStub (yfinance removed 2026-04-25)
            for t in all_tickers:
                try:
                    info = yf.Ticker(t).info
                    sector_map[t] = info.get("sector") or "Unknown"
                except Exception:
                    sector_map[t] = "Unknown"
        except ImportError:
            sector_map = {t: "Unknown" for t in all_tickers}
    for t in all_tickers:
        sec = sector_map.get(t, "Unknown")
        sector_count[sec] = sector_count.get(sec, 0) + 1
    sector_risk = any(v > 2 for v in sector_count.values())

    return {
        "has_risk": bool(correlated_with) or sector_risk,
        "correlated_with": correlated_with,
        "max_correlation": round(max_corr, 4),
        "sector_count": sector_count,
        "sector_risk": sector_risk,
    }


def get_portfolio_correlation_matrix(period: str = "3mo") -> dict:
    """Full Pearson correlation matrix for all currently open positions."""
    try:
        import numpy as np  # type: ignore
    except ImportError:
        return {"tickers": [], "matrix": [], "high_pairs": [],
                "message": "numpy unavailable"}
    state = _load_state()
    positions = state.get("positions", [])
    tickers = [p["ticker"] for p in positions if p.get("ticker")]
    if len(tickers) < 2:
        return {
            "tickers": tickers,
            "matrix": [[1.0]] if len(tickers) == 1 else [],
            "high_pairs": [],
            "message": "Need at least 2 open positions for a correlation matrix",
        }
    returns = _get_returns(tickers, period)
    if returns is None:
        return {"tickers": tickers, "matrix": [], "high_pairs": [],
                "message": "pandas/yfinance unavailable"}
    available = [t for t in tickers if t in returns.columns]
    if len(available) < 2:
        return {"tickers": tickers, "matrix": [], "high_pairs": [],
                "message": "Insufficient price data for open positions"}
    corr_df = returns[available].corr(method="pearson")
    matrix = []
    for row_t in available:
        row = []
        for col_t in available:
            val = corr_df.loc[row_t, col_t]
            try:
                row.append(None if np.isnan(float(val)) else round(float(val), 4))
            except (TypeError, ValueError):
                row.append(None)
        matrix.append(row)
    HIGH_THRESHOLD = 0.70
    high_pairs = []
    for i, t1 in enumerate(available):
        for t2 in available[i + 1:]:
            val = corr_df.loc[t1, t2]
            try:
                val_f = float(val)
            except (TypeError, ValueError):
                continue
            if not np.isnan(val_f) and val_f >= HIGH_THRESHOLD:
                high_pairs.append({"t1": t1, "t2": t2, "corr": round(val_f, 4)})
    high_pairs.sort(key=lambda x: x["corr"], reverse=True)
    return {"tickers": available, "matrix": matrix, "high_pairs": high_pairs}


# ── CLI convenience ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    summary = get_portfolio_summary()
    print(f"Config: {summary['config_label']}")
    print(f"Equity: ${summary['equity']:,.2f}  |  Cash: ${summary['cash']:,.2f}  |  Invested: ${summary['invested']:,.2f}")
    print(f"Open: {summary['open_count']}/{summary['max_positions']} positions  |  Slots: {summary['open_slots']}")
    print(f"Closed P&L: ${summary['closed_pnl']:+,.2f}  |  W/L: {summary['wins']}W/{summary['losses']}L  ({summary['win_rate']}%)")
    if summary["positions"]:
        print("\nOpen positions:")
        for p in summary["positions"]:
            print(f"  {p['ticker']:6s}  entry ${p['entry_price']:.2f}  x{p['shares']}  "
                  f"stop ${p['stop']:.2f}  trail_stop ${p.get('trail_stop', p['stop']):.2f}  "
                  f"trail_active={p.get('trail_active', False)}  setup={p.get('setup_type', '')}")
    if summary["monthly_pnl"]:
        print("\nMonthly P&L:")
        for month, pnl in sorted(summary["monthly_pnl"].items()):
            print(f"  {month}: ${pnl:+,.2f}")

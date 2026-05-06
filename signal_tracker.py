"""
Signal Tracker — auto-logs BUY signals and tracks outcomes over time.

On every scan run, BUY signals are logged to data/signal_log.json.
Outcomes are backfilled when signals age past 5/10 days.

Usage:
    from signal_tracker import log_signals, update_outcomes, get_track_record, get_summary_stats
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, date, timedelta
from pathlib import Path

log = logging.getLogger("signal_tracker")

BASE_DIR = Path(__file__).parent
SIGNAL_LOG_PATH = BASE_DIR / "data" / "signal_log.json"
SIGNAL_LOG_META_PATH = BASE_DIR / "data" / "signal_log.meta.json"

# Bump when the per-entry shape of signal_log.json changes.
SIGNAL_LOG_SCHEMA_VERSION = 3


def _read_meta_version() -> int:
    """Read schema version from sidecar meta file (list-typed log can't
    carry its own version)."""
    if SIGNAL_LOG_META_PATH.exists():
        try:
            meta = json.loads(SIGNAL_LOG_META_PATH.read_text(encoding="utf-8"))
            return int(meta.get("_schema_version", 0))
        except (json.JSONDecodeError, IOError, ValueError):
            return 0
    return 0


def _write_meta_version() -> None:
    SIGNAL_LOG_META_PATH.parent.mkdir(parents=True, exist_ok=True)
    SIGNAL_LOG_META_PATH.write_text(
        json.dumps(
            {
                "_schema_version": SIGNAL_LOG_SCHEMA_VERSION,
                "_last_saved": datetime.now().isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _migrate_signal_log(entries: list[dict], from_version: int) -> list[dict]:
    """Apply idempotent, additive migrations to each signal-log entry."""
    if from_version < 1:
        # v0 → v1: ensure mae_pct / mfe_pct exist (None if not yet computed)
        for e in entries:
            e.setdefault("mae_pct", None)
            e.setdefault("mfe_pct", None)
    if from_version < 2:
        # v1 → v2: ensure direction + outcome placeholders exist
        for e in entries:
            e.setdefault("direction", "long")
            e.setdefault("outcome_5d", None)
            e.setdefault("outcome_10d", None)
    if from_version < 3:
        # v2 → v3: add is_new_buy (cross-day dedup marker). Historical entries
        # are backfilled to None — we cannot retroactively tell which were
        # first-time BUYs vs repeats.
        for e in entries:
            e.setdefault("is_new_buy", None)
    return entries


def _load_log() -> list[dict]:
    """Load the persistent signal log from disk, auto-migrating legacy entries."""
    if not SIGNAL_LOG_PATH.exists():
        return []
    try:
        entries = json.loads(SIGNAL_LOG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError):
        log.warning("Corrupt signal_log.json — starting fresh")
        return []
    if not isinstance(entries, list):
        log.warning("signal_log.json is not a list — starting fresh")
        return []
    current = _read_meta_version()
    if current < SIGNAL_LOG_SCHEMA_VERSION:
        entries = _migrate_signal_log(entries, from_version=current)
        _save_log(entries)
        log.info(
            "Migrated signal_log from v%s to v%s",
            current, SIGNAL_LOG_SCHEMA_VERSION,
        )
    return entries


def _save_log(entries: list[dict]) -> None:
    """Persist signal log to disk."""
    SIGNAL_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    SIGNAL_LOG_PATH.write_text(json.dumps(entries, indent=2, default=str), encoding="utf-8")
    _write_meta_version()


def _mae_mfe_from_ohlc(hist, entry_price: float, direction: str) -> tuple[float, float]:
    """Given an OHLC frame with High/Low columns, compute (mae_pct, mfe_pct)."""
    low_min = float(hist["Low"].min())
    high_max = float(hist["High"].max())
    if direction.lower() == "short":
        mae = (high_max - entry_price) / entry_price * 100.0
        mfe = (low_min - entry_price) / entry_price * 100.0
    else:
        mae = (low_min - entry_price) / entry_price * 100.0
        mfe = (high_max - entry_price) / entry_price * 100.0
    return (round(mae, 2), round(mfe, 2))


def compute_mae_mfe(
    ticker: str,
    entry_date: str,
    entry_price: float,
    direction: str = "long",
    exit_date: str | None = None,
) -> tuple[float | None, float | None]:
    """Return (mae_pct, mfe_pct) for a ticker from entry_date to exit_date (or today).

    Primary source: data_archive parquet (cached, no network). Fallback: yfinance.
    Returns (None, None) on failure or when no bars are available.
    """
    try:
        if not entry_price or entry_price <= 0:
            return (None, None)

        try:
            start = datetime.strptime(entry_date, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return (None, None)
        end = (
            datetime.strptime(exit_date, "%Y-%m-%d").date()
            if exit_date else date.today()
        )
        if end < start:
            return (None, None)

        direction = (direction or "long").lower()

        # Full vendor failover: archive → Polygon → yfinance.
        # Archive is primary (fast, cached, populated by Polygon on each scan).
        # Polygon is secondary (covers fresh tickers not yet in archive).
        # yfinance is last-resort (rate-limited, less reliable).

        # --- 1. Local data_archive parquet (fast, cached) ---
        try:
            from data_archive import load_ticker as _load_ticker
            df = _load_ticker(ticker)
            if df is not None and len(df) > 0 and {"High", "Low"}.issubset(df.columns):
                idx_dates = df.index.tz_localize(None).normalize() if df.index.tz is not None else df.index.normalize()
                mask = (idx_dates >= _to_ts(start)) & (idx_dates <= _to_ts(end))
                sub = df.loc[mask]
                if len(sub) > 0:
                    return _mae_mfe_from_ohlc(sub, entry_price, direction)
        except Exception as exc:
            log.debug(f"archive MAE/MFE lookup failed for {ticker}: {exc}")

        # --- 2. Polygon via vendor failover chain ---
        try:
            from data_fetcher import fetch_ohlcv_with_failover
            days_span = max((end - start).days + 5, 10)
            df_p, _tier = fetch_ohlcv_with_failover(ticker, days=days_span)
            if df_p is not None and len(df_p) > 0 and {"High", "Low"}.issubset(df_p.columns):
                idx_dates = df_p.index.tz_localize(None).normalize() if df_p.index.tz is not None else df_p.index.normalize()
                mask = (idx_dates >= _to_ts(start)) & (idx_dates <= _to_ts(end))
                sub = df_p.loc[mask]
                if len(sub) > 0:
                    return _mae_mfe_from_ohlc(sub, entry_price, direction)
        except Exception as exc:
            log.debug(f"Polygon MAE/MFE lookup failed for {ticker}: {exc}")

        # --- 3. yfinance (last resort — rate-limited) ---
        try:
            from data_fetcher import yf  # _YfStub (yfinance removed 2026-04-25)
            end_plus = end + timedelta(days=1)
            t = yf.Ticker(ticker)
            hist = t.history(start=start.isoformat(), end=end_plus.isoformat())
            if hist is not None and len(hist) > 0:
                return _mae_mfe_from_ohlc(hist, entry_price, direction)
        except Exception as exc:
            log.debug(f"yfinance MAE/MFE lookup failed for {ticker}: {exc}")

        return (None, None)
    except Exception as exc:
        log.warning(f"compute_mae_mfe failed for {ticker}: {exc}")
        return (None, None)


def _to_ts(d):
    """Convert a date to a pandas Timestamp at midnight (tz-naive)."""
    import pandas as pd
    return pd.Timestamp(d)


def log_signals(picks: list[dict], run_date: str | None = None) -> int:
    """
    Append today's top picks to the signal log.
    Skips duplicates (same ticker + date).
    Returns count of newly logged signals.
    """
    if not picks:
        return 0

    today = run_date or date.today().isoformat()
    entries = _load_log()

    # Build set of existing (ticker, date, mode) pairs for dedup.
    # Same ticker can appear in Swing + Position + Invest on same day — log each.
    existing = {(e["ticker"], e["date"], e.get("mode", "Swing")) for e in entries}

    added = 0
    for c in picks:
        ticker = c.get("ticker", "")
        if not ticker:
            continue
        c_mode = c.get("mode", "Swing")
        if (ticker, today, c_mode) in existing:
            continue

        # Audit ranking flaw #16/#17: capture per-pillar breakdown
        breakdown = c.get("scoring_breakdown", {}) or {}
        entry = {
            "ticker": ticker,
            "date": today,
            "strategy": c.get("strategy", "Core Swing"),
            "entry_price": round(c.get("price", 0), 2),
            "stop": round(c.get("stop", 0), 2),
            "target1": round(c.get("target1", 0), 2),
            "target2": round(c.get("target1", 0) * 1.07, 2) if c.get("target1") else 0,
            "rr": round(c.get("rr", 0), 2),
            "stars": c.get("star_rating", 0),
            "score": round(c.get("score", 0), 1),
            "rs_rank": c.get("rs_rank", 0),
            "status": "OPEN",
            # Phase 2 logging fix (2026-04-30): capture WHAT the signal was
            # (BUY / WATCH / SHORT) and direction, so audit trail shows alert type
            "verdict":   c.get("verdict", "BUY"),
            "direction": c.get("direction", "long"),
            # 2026-05-04: mode (Swing / Position / Invest) so audit trail can filter by horizon.
            "mode":      c.get("mode", "Swing"),
            # ── Tier A audit fields (2026-05-04) ──
            # Regime context at signal time
            "regime4":          c.get("regime4"),
            "regime_name":      c.get("regime_name"),
            "vix_at_signal":    c.get("vix_at_signal"),
            "hmm_p_bull":       c.get("hmm_p_bull"),
            "hmm_p_neutral":    c.get("hmm_p_neutral"),
            "hmm_p_bear":       c.get("hmm_p_bear"),
            # Conviction + setup
            "conviction_label": c.get("conviction_label"),
            "entry_quality":    c.get("entry_quality"),
            "setup_family":     c.get("setup_family"),
            "tail_filter_demoted": c.get("tail_filter_demoted", False),
            # Forward predictions (V-1 Monte Carlo + V-3 forward dist)
            "mc_p_profit":         c.get("mc_p_profit"),
            "mc_p_target_first":   c.get("mc_p_target_first"),
            "mc_p_stop_first":     c.get("mc_p_stop_first"),
            "fd_var_95_pct":       c.get("fd_var_95_pct"),
            "fd_cvar_975_pct":     c.get("fd_cvar_975_pct"),
            # Exit details — populated by signal_tracker.update_outcomes when trade closes
            "exit_reason":              None,   # target_hit / stop_hit / time_stop / earnings / manual
            "days_to_first_target_hit": None,
            "days_to_stop_hit":         None,
            "actual_r_multiple":        None,
            "spy_return_over_hold":     None,
            "alpha_vs_spy":             None,
            "day5_price": None,
            "day10_price": None,
            "actual_pnl_pct": None,
            "result": None,
            "mae_pct": None,
            "mfe_pct": None,
            # Per-pillar breakdown (audit #16/#17)
            "tech_score":    breakdown.get("tech_score"),
            "cat_score":     breakdown.get("cat_score"),
            "rs_score":      breakdown.get("rs_score"),
            "sm_score":      breakdown.get("sm_score"),
            "qg_score":      breakdown.get("qg_score"),
            "raw_total":     breakdown.get("raw_total"),
            "wr_multiplier": breakdown.get("wr_multiplier"),
            "bonus_total":   breakdown.get("bonus_total"),
            # Profile attribution (2026-04-15): tag every signal with the
            # active config profile so we can compute per-profile win rate / P&L.
            "profile":       _active_profile_name(),
        }
        entries.append(entry)
        existing.add((ticker, today, c_mode))
        added += 1

    if added:
        _save_log(entries)
        log.info(f"Signal tracker: logged {added} new signals for {today}")
        # Unified audit log (2026-04-15)
        try:
            import audit
            for e in entries[-added:]:
                audit.log("signal", {"ticker": e["ticker"], "date": e["date"],
                                     "score": e.get("score"), "rs_rank": e.get("rs_rank"),
                                     "strategy": e.get("strategy"), "rr": e.get("rr")},
                          profile=e.get("profile"))
        except Exception:
            pass

    return added


def _active_profile_name() -> str | None:
    """Best-effort lookup of the currently active config profile."""
    try:
        p = BASE_DIR / "config" / "history" / "active_profile.txt"
        if p.exists():
            name = p.read_text().strip()
            return name or None
    except Exception:
        pass
    return None


def update_outcomes() -> int:
    """
    For signals older than 5 days, fetch current price and compute actual P&L.
    Updates day5_price, day10_price, actual_pnl_pct, result, and status.

    Additionally (Bug C fix): refresh mae_pct/mfe_pct for ALL entries — both
    OPEN and CLOSED — that have a valid entry_date and entry_price, regardless
    of age. For OPEN entries MAE/MFE is tracked to today; for CLOSED entries
    it is bounded by exit_date when present.

    Returns count of updated signals.
    """
    entries = _load_log()
    if not entries:
        return 0

    today = date.today()
    updated = 0

    # --- Bug C: Refresh MAE/MFE for every entry with a usable entry ---
    # This runs independently of the price-snapshot logic below so MAE/MFE
    # populates even on day 0 (signal logged today has its first bar already).
    mae_updates = 0
    for e in entries:
        try:
            entry_date = e.get("date")
            entry_price = e.get("entry_price", 0) or 0
            if not entry_date or entry_price <= 0:
                continue
            direction = e.get("direction") or "long"
            exit_date = e.get("exit_date")  # optional on CLOSED entries
            mae, mfe = compute_mae_mfe(
                e["ticker"], entry_date, entry_price,
                direction=direction, exit_date=exit_date,
            )
            changed = False
            if mae is not None and e.get("mae_pct") != mae:
                e["mae_pct"] = mae
                changed = True
            if mfe is not None and e.get("mfe_pct") != mfe:
                e["mfe_pct"] = mfe
                changed = True
            # Ensure keys exist on legacy entries even if computation failed
            e.setdefault("mae_pct", None)
            e.setdefault("mfe_pct", None)
            if changed:
                mae_updates += 1
        except Exception as exc:
            log.debug(f"MAE/MFE refresh skipped for {e.get('ticker')}: {exc}")

    # Collect tickers that need price updates
    tickers_to_check = set()
    for e in entries:
        if e.get("status") != "OPEN":
            continue
        try:
            sig_date = datetime.strptime(e["date"], "%Y-%m-%d").date()
        except (ValueError, KeyError):
            continue
        age = (today - sig_date).days
        if age >= 5:
            tickers_to_check.add(e["ticker"])

    if not tickers_to_check:
        # No price-snapshot work needed, but we may still have MAE/MFE
        # updates from the loop above — persist them before returning.
        if mae_updates:
            _save_log(entries)
            log.info(f"Signal tracker: {mae_updates} MAE/MFE refreshes persisted")
        return mae_updates

    # Fetch current prices
    current_prices = {}
    try:
        from data_fetcher import get_polygon_snapshot
        for ticker in tickers_to_check:
            try:
                snap = get_polygon_snapshot(ticker)
                if snap and snap.get("price"):
                    current_prices[ticker] = float(snap["price"])
            except Exception:
                pass
    except ImportError:
        log.warning("Cannot import data_fetcher for price updates")
        # Fallback: try yfinance
        try:
            from data_fetcher import yf  # _YfStub (yfinance removed 2026-04-25)
            for ticker in tickers_to_check:
                try:
                    t = yf.Ticker(ticker)
                    hist = t.history(period="1d")
                    if len(hist) > 0:
                        current_prices[ticker] = float(hist["Close"].iloc[-1])
                except Exception:
                    pass
        except ImportError:
            log.warning("Cannot fetch prices — yfinance not available")
            return 0

    # Update entries
    for e in entries:
        if e.get("status") != "OPEN":
            continue
        ticker = e["ticker"]
        if ticker not in current_prices:
            continue

        try:
            sig_date = datetime.strptime(e["date"], "%Y-%m-%d").date()
        except (ValueError, KeyError):
            continue

        age = (today - sig_date).days
        cur_price = current_prices[ticker]
        entry_price = e.get("entry_price", 0)
        stop = e.get("stop", 0)
        target1 = e.get("target1", 0)

        if entry_price <= 0:
            continue

        # Set day5/day10 prices
        if age >= 5 and e.get("day5_price") is None:
            e["day5_price"] = round(cur_price, 2)
        if age >= 10 and e.get("day10_price") is None:
            e["day10_price"] = round(cur_price, 2)

        # Compute P&L
        pnl_pct = round((cur_price - entry_price) / entry_price * 100, 2)
        e["actual_pnl_pct"] = pnl_pct

        # MAE/MFE already refreshed at top of function (Bug C fix)

        # Determine result + Tier A exit attribution
        # exit_reason: target_hit / stop_hit / time_stop_win / time_stop_loss
        # EMA21 Pullback 2-day no-move exit (per 2026-05-06 signal_tracker analysis):
        # losers without a Day-2 gain rarely recover and avg MAE -7.47%.
        if e.get("strategy") == "EMA21 Pullback" and age >= 2 and pnl_pct <= 0:
            e["result"] = "STOPPED"
            e["status"] = "CLOSED"
            e.setdefault("exit_reason", "ema21_no_move_2d")
            if e.get("days_to_stop_hit") is None:
                e["days_to_stop_hit"] = age
        elif stop > 0 and cur_price <= stop:
            e["result"] = "STOPPED"
            e["status"] = "CLOSED"
            e.setdefault("exit_reason", "stop_hit")
            if e.get("days_to_stop_hit") is None:
                e["days_to_stop_hit"] = age
        elif target1 > 0 and cur_price >= target1:
            e["result"] = "TARGET_HIT"
            e["status"] = "CLOSED"
            e.setdefault("exit_reason", "target_hit")
            if e.get("days_to_first_target_hit") is None:
                e["days_to_first_target_hit"] = age
        elif age >= 10:
            # Auto-close after 10 days
            if pnl_pct >= 0:
                e["result"] = "WIN_EXPIRED"
                e.setdefault("exit_reason", "time_stop_win")
            else:
                e["result"] = "LOSS_EXPIRED"
                e.setdefault("exit_reason", "time_stop_loss")
            e["status"] = "CLOSED"

        # Tier A: actual R-multiple + alpha-vs-SPY when trade is now CLOSED
        if e["status"] == "CLOSED":
            if e.get("actual_r_multiple") is None and entry_price > 0 and stop > 0:
                risk_per_share = abs(entry_price - stop)
                if risk_per_share > 0:
                    pnl_per_share = cur_price - entry_price
                    if e.get("direction") == "short":
                        pnl_per_share = -pnl_per_share
                    e["actual_r_multiple"] = round(pnl_per_share / risk_per_share, 2)
            # SPY alpha — fetch SPY return over hold period
            if e.get("alpha_vs_spy") is None:
                try:
                    from datetime import timedelta as _td
                    import pandas as _pd
                    from pathlib import Path as _P
                    spy_p = _P(__file__).parent / "data/ohlcv/SPY.parquet"
                    if spy_p.exists():
                        spy_df = _pd.read_parquet(spy_p).sort_index()
                        sig_ts = _pd.to_datetime(e["date"])
                        spy_after = spy_df[spy_df.index >= sig_ts]
                        if len(spy_after) >= age + 1:
                            spy_entry = float(spy_after["Close"].iloc[0])
                            spy_now   = float(spy_after["Close"].iloc[min(age, len(spy_after)-1)])
                            spy_ret = round((spy_now / spy_entry - 1) * 100, 2)
                            e["spy_return_over_hold"] = spy_ret
                            e["alpha_vs_spy"] = round(pnl_pct - spy_ret, 2)
                except Exception:
                    pass

        updated += 1

    if updated or mae_updates:
        _save_log(entries)
        log.info(
            f"Signal tracker: updated {updated} signal outcomes, "
            f"{mae_updates} MAE/MFE refreshes"
        )

    return updated + mae_updates


def get_track_record(n: int = 30) -> list[dict]:
    """Return last n signals with outcomes, most recent first."""
    entries = _load_log()
    # Sort by date descending
    entries.sort(key=lambda e: e.get("date", ""), reverse=True)
    return entries[:n]


def get_summary_stats() -> dict:
    """
    Return aggregate stats: win rate, avg P&L, total P&L, profit factor.
    Only considers CLOSED signals with actual_pnl_pct.
    """
    entries = _load_log()
    closed = [e for e in entries if e.get("status") == "CLOSED" and e.get("actual_pnl_pct") is not None]

    if not closed:
        return {
            "total_signals": len(entries),
            "closed_signals": 0,
            "open_signals": len([e for e in entries if e.get("status") == "OPEN"]),
            "win_rate": 0,
            "avg_pnl_pct": 0,
            "total_pnl_pct": 0,
            "profit_factor": 0,
            "wins": 0,
            "losses": 0,
            "best_trade": None,
            "worst_trade": None,
        }

    wins = [e for e in closed if (e.get("actual_pnl_pct") or 0) > 0]
    losses = [e for e in closed if (e.get("actual_pnl_pct") or 0) <= 0]
    total_gain = sum(e.get("actual_pnl_pct", 0) for e in wins)
    total_loss = abs(sum(e.get("actual_pnl_pct", 0) for e in losses))
    profit_factor = round(total_gain / total_loss, 2) if total_loss > 0 else float("inf")

    all_pnl = [e.get("actual_pnl_pct", 0) for e in closed]
    best = max(closed, key=lambda e: e.get("actual_pnl_pct", 0))
    worst = min(closed, key=lambda e: e.get("actual_pnl_pct", 0))

    return {
        "total_signals": len(entries),
        "closed_signals": len(closed),
        "open_signals": len([e for e in entries if e.get("status") == "OPEN"]),
        "win_rate": round(len(wins) / len(closed) * 100, 1) if closed else 0,
        "avg_pnl_pct": round(sum(all_pnl) / len(all_pnl), 2) if all_pnl else 0,
        "total_pnl_pct": round(sum(all_pnl), 2),
        "profit_factor": profit_factor,
        "wins": len(wins),
        "losses": len(losses),
        "best_trade": {"ticker": best["ticker"], "pnl": best.get("actual_pnl_pct", 0)},
        "worst_trade": {"ticker": worst["ticker"], "pnl": worst.get("actual_pnl_pct", 0)},
    }


def get_mae_mfe_stats(n: int = 100) -> dict:
    """Summary stats over last n closed trades: avg_mae, avg_mfe, worst_mae, best_mfe,
    profit-give-back (mfe - exit_pct), and pain-to-gain ratio (avg_mae / avg_mfe)."""
    entries = _load_log()
    closed = [
        e for e in entries
        if e.get("status") == "CLOSED"
        and e.get("mae_pct") is not None
        and e.get("mfe_pct") is not None
    ]
    # Sort by date desc, take most recent n
    closed.sort(key=lambda e: e.get("date", ""), reverse=True)
    closed = closed[:n]

    if not closed:
        return {
            "count": 0,
            "avg_mae": 0,
            "avg_mfe": 0,
            "worst_mae": 0,
            "best_mfe": 0,
            "avg_profit_give_back": 0,
            "pain_to_gain_ratio": 0,
        }

    maes = [e["mae_pct"] for e in closed]
    mfes = [e["mfe_pct"] for e in closed]
    avg_mae = sum(maes) / len(maes)
    avg_mfe = sum(mfes) / len(mfes)
    worst_mae = min(maes)  # most negative for longs
    best_mfe = max(mfes)

    # Profit give-back: MFE minus realized exit P&L (how much peak profit was surrendered)
    give_backs = []
    for e in closed:
        exit_pct = e.get("actual_pnl_pct")
        if exit_pct is not None:
            give_backs.append(e["mfe_pct"] - exit_pct)
    avg_give_back = sum(give_backs) / len(give_backs) if give_backs else 0.0

    pain_to_gain = (avg_mae / avg_mfe) if avg_mfe not in (0, 0.0) else 0.0

    return {
        "count": len(closed),
        "avg_mae": round(avg_mae, 2),
        "avg_mfe": round(avg_mfe, 2),
        "worst_mae": round(worst_mae, 2),
        "best_mfe": round(best_mfe, 2),
        "avg_profit_give_back": round(avg_give_back, 2),
        "pain_to_gain_ratio": round(pain_to_gain, 3),
    }


# ---------------------------------------------------------------------------
# Cross-day dedup helpers (HARDENING 3.2)
# ---------------------------------------------------------------------------

def is_first_time_buy(ticker: str, setup: str, lookback_days: int = 3) -> bool:
    """Return True if (ticker, setup) was NOT recorded as a BUY in the prior
    `lookback_days` days.

    A "BUY" here is any signal_log entry with a matching ticker + strategy —
    the log only captures BUY-tier picks, so mere presence counts as a repeat.
    Today's entries are ignored (we're checking whether this would be the
    first-time signal today).
    """
    if not ticker:
        return False
    ticker = ticker.upper()
    setup_norm = (setup or "").strip().lower()
    entries = _load_log()
    today = date.today()
    cutoff = today - timedelta(days=max(lookback_days, 0))

    for e in entries:
        if (e.get("ticker") or "").upper() != ticker:
            continue
        est = (e.get("strategy") or "").strip().lower()
        # Setup is optional — if caller doesn't specify, any prior BUY counts.
        if setup_norm and est and est != setup_norm:
            continue
        try:
            d = datetime.strptime(e.get("date", ""), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
        if d >= cutoff and d < today:
            return False  # repeat within lookback window
    return True


def log_signals_deduped(
    picks: list[dict],
    run_date: str | None = None,
    lookback_days: int = 3,
) -> int:
    """Wrapper around log_signals that annotates each pick with `is_new_buy`
    based on cross-day dedup, then delegates persistence to the existing
    log_signals. Returns the count newly appended.

    Mutates the input picks list by adding the `is_new_buy` key to each dict
    (safe — additive). Post-write, the flag is also stamped onto the persisted
    entry so downstream analytics can read it directly.
    """
    if not picks:
        return 0

    today = run_date or date.today().isoformat()

    # Mark picks with is_new_buy prior to logging
    new_buy_by_ticker: dict[str, bool] = {}
    for p in picks:
        ticker = (p.get("ticker") or "").upper()
        if not ticker:
            continue
        setup = p.get("strategy") or p.get("setup_type") or ""
        flag = is_first_time_buy(ticker, setup, lookback_days=lookback_days)
        p["is_new_buy"] = flag
        new_buy_by_ticker[ticker] = flag

    added = log_signals(picks, run_date=today)

    # Stamp is_new_buy onto the persisted entries (log_signals doesn't know
    # about this field). Only touch entries for today that lack the flag.
    if added:
        try:
            entries = _load_log()
            changed = False
            for e in entries:
                if e.get("date") != today:
                    continue
                tk = (e.get("ticker") or "").upper()
                if tk in new_buy_by_ticker and e.get("is_new_buy") is None:
                    e["is_new_buy"] = new_buy_by_ticker[tk]
                    changed = True
            if changed:
                _save_log(entries)
        except Exception as exc:
            log.debug(f"Failed to stamp is_new_buy on persisted entries: {exc}")

    return added

"""
audit.py — Unified append-only audit log.

Every material event writes one line to data/audit.jsonl. Join surfaces:
  - config/profile changes (profile_manager, settings UI)
  - scan runs (swing_trade.py start + finish, counts, regime, active profile)
  - signals emitted (via signal_tracker.log_signals)
  - trades opened/closed (via portfolio_tracker)

Format: one JSON object per line, with fields:
  ts        : ISO8601 UTC timestamp
  type      : "config_change" | "profile_switch" | "scan_run" | "signal" | "trade_open" | "trade_close"
  profile   : active profile name at event time (best effort)
  payload   : event-specific dict
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).parent
AUDIT_PATH = BASE_DIR / "data" / "audit.jsonl"
ACTIVE_PROFILE_PATH = BASE_DIR / "config" / "history" / "active_profile.txt"


def active_profile() -> str | None:
    """Best-effort read of the currently active profile name."""
    try:
        if ACTIVE_PROFILE_PATH.exists():
            name = ACTIVE_PROFILE_PATH.read_text().strip()
            return name or None
    except Exception:
        pass
    return None


def log(event_type: str, payload: dict[str, Any], profile: str | None = None) -> None:
    """Append one audit event. Safe — errors are swallowed."""
    try:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            "profile": profile if profile is not None else active_profile(),
            "payload": payload,
        }
        AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with AUDIT_PATH.open("a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except Exception:
        pass  # never let audit failure break the caller


def tail(limit: int = 100, type_filter: str | None = None) -> list[dict]:
    """Return the last N audit entries, optionally filtered by type."""
    if not AUDIT_PATH.exists():
        return []
    entries: list[dict] = []
    with AUDIT_PATH.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
                if type_filter and e.get("type") != type_filter:
                    continue
                entries.append(e)
            except json.JSONDecodeError:
                continue
    return entries[-limit:]


def profile_attribution() -> list[dict]:
    """
    Aggregate signal outcomes by profile. Reads signal_log.json.
    Returns per-profile stats: count, wins, losses, win_rate, avg_pnl_pct, net_pnl_pct, profit_factor.
    """
    signal_log = BASE_DIR / "data" / "signal_log.json"
    if not signal_log.exists():
        return []
    try:
        entries = json.loads(signal_log.read_text())
    except Exception:
        return []
    if not isinstance(entries, list):
        return []

    buckets: dict[str, list[dict]] = {}
    for e in entries:
        prof = e.get("profile") or "unknown"
        buckets.setdefault(prof, []).append(e)

    out: list[dict] = []
    for prof, rows in buckets.items():
        closed = [r for r in rows if r.get("actual_pnl_pct") is not None]
        wins   = [r for r in closed if (r.get("actual_pnl_pct") or 0) > 0]
        losses = [r for r in closed if (r.get("actual_pnl_pct") or 0) <= 0]
        total_win  = sum((r.get("actual_pnl_pct") or 0) for r in wins)
        total_loss = sum((r.get("actual_pnl_pct") or 0) for r in losses)
        wr = (len(wins) / len(closed) * 100) if closed else None
        avg_win  = (total_win / len(wins)) if wins else None
        avg_loss = (total_loss / len(losses)) if losses else None
        net      = total_win + total_loss
        pf       = (total_win / abs(total_loss)) if total_loss else None
        out.append({
            "profile": prof,
            "total_signals": len(rows),
            "closed":        len(closed),
            "open":          len(rows) - len(closed),
            "wins":          len(wins),
            "losses":        len(losses),
            "win_rate_pct":  round(wr, 1) if wr is not None else None,
            "avg_win_pct":   round(avg_win, 2) if avg_win is not None else None,
            "avg_loss_pct":  round(avg_loss, 2) if avg_loss is not None else None,
            "net_pnl_pct":   round(net, 2),
            "profit_factor": round(pf, 2) if pf is not None else None,
        })
    # Sort by net_pnl desc
    out.sort(key=lambda x: (x.get("net_pnl_pct") or 0), reverse=True)
    return out

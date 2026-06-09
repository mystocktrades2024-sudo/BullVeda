#!/usr/bin/env python3
"""Delisted-ticker tombstone registry — Open Risk #9 (a).

The track-record guarantee (always-include set in swing_trade.py) keeps every
name the system ever PICKED or HELD in-universe forever so a holder always gets
a fresh stop/target/exit read. The downside: a genuinely *delisted* ticker keeps
failing OHLCV fetches across all failover tiers (EODHD → Schwab → archive) every
single scan, burning cycles and quota indefinitely.

This module records a consecutive-failure streak per ticker. After N straight
all-tier failures (default 5) the ticker is *tombstoned*: the universe assembly
SKIPS it for fetching so it stops burning cycles. Crucially this is ADDITIVE and
SAFE — it only stops re-fetching. It NEVER touches picks_history / signal_log /
audit_ledger, so the historical track record stays fully intact.

A tombstone auto-expires after `retry_after_days` (default 7) so a transient
delisting / EODHD outage self-heals on the next weekly retry window. Manual
un-tombstone is also supported (`untombstone()` / CLI `revive`).

Registry file: data/delisted_tickers.json

    {
      "_meta": {"version": 1, "updated": "<iso-utc>"},
      "tickers": {
        "BITF": {
          "first_failed":  "2026-06-01T14:03:11Z",   # first fail in current streak
          "last_checked":  "2026-06-09T14:03:11Z",   # most recent fail
          "fail_streak":   6,                          # consecutive all-tier failures
          "tombstoned":    true,                       # streak >= threshold
          "tombstoned_at": "2026-06-05T14:03:11Z",
          "reason":        "5 consecutive all-tier OHLCV fetch failures"
        },
        ...
      }
    }

Thread-safety: a process-level lock guards read-modify-write. Cross-process
contention is not a concern (one scan runs at a time); writes are atomic
(tmp + os.replace).
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent
REGISTRY_PATH = BASE_DIR / "data" / "delisted_tickers.json"

# Defaults — overridable from config.universe.* (read lazily, never hardcoded
# into call sites). See _cfg().
_DEFAULT_THRESHOLD = 5        # consecutive all-tier failures before tombstoning
_DEFAULT_RETRY_DAYS = 7       # auto-retry a tombstoned ticker after this many days

_LOCK = threading.RLock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except Exception:
        try:
            # tolerate fractional / offset forms
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None


def _cfg() -> dict:
    """Read universe tombstone config. Fail-open to defaults; never raise."""
    try:
        import data_fetcher as _df
        cfg = _df.load_config() or {}
        return (cfg.get("universe") or {})
    except Exception:
        return {}


def is_enabled() -> bool:
    """Master flag — config.universe.tombstone_delisted (default True).

    Set False to fully disable: no recording, no skipping. Reversible.
    """
    u = _cfg()
    return bool(u.get("tombstone_delisted", True))


def _threshold() -> int:
    u = _cfg()
    try:
        return int(u.get("tombstone_fail_threshold", _DEFAULT_THRESHOLD))
    except Exception:
        return _DEFAULT_THRESHOLD


def _retry_days() -> int:
    u = _cfg()
    try:
        return int(u.get("tombstone_retry_after_days", _DEFAULT_RETRY_DAYS))
    except Exception:
        return _DEFAULT_RETRY_DAYS


# ── low-level load / save ──────────────────────────────────────────────────
def _load() -> dict:
    if not REGISTRY_PATH.exists():
        return {"_meta": {"version": 1, "updated": _now_iso()}, "tickers": {}}
    try:
        d = json.loads(REGISTRY_PATH.read_text())
        if not isinstance(d, dict):
            return {"_meta": {"version": 1, "updated": _now_iso()}, "tickers": {}}
        d.setdefault("tickers", {})
        d.setdefault("_meta", {"version": 1, "updated": _now_iso()})
        return d
    except Exception:
        return {"_meta": {"version": 1, "updated": _now_iso()}, "tickers": {}}


def _save(d: dict) -> None:
    d["_meta"] = {"version": 1, "updated": _now_iso()}
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = REGISTRY_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, indent=2))
    os.replace(tmp, REGISTRY_PATH)


# ── public API ─────────────────────────────────────────────────────────────
def record_failure(ticker: str) -> bool:
    """Record one all-tier OHLCV fetch failure for `ticker`.

    Increments the consecutive-failure streak. Once the streak reaches the
    threshold the ticker is tombstoned. Returns True if (and only if) THIS call
    flipped the ticker into the tombstoned state (useful for one-shot logging).

    No-op (returns False) when tombstoning is disabled.
    """
    if not is_enabled() or not ticker:
        return False
    t = ticker.upper()
    thr = _threshold()
    now = _now_iso()
    with _LOCK:
        d = _load()
        rec = d["tickers"].get(t) or {}
        if not rec:
            rec = {"first_failed": now, "fail_streak": 0, "tombstoned": False}
        rec["last_checked"] = now
        rec["fail_streak"] = int(rec.get("fail_streak", 0)) + 1
        newly = False
        if rec["fail_streak"] >= thr and not rec.get("tombstoned"):
            rec["tombstoned"] = True
            rec["tombstoned_at"] = now
            rec["reason"] = f"{thr} consecutive all-tier OHLCV fetch failures"
            newly = True
        d["tickers"][t] = rec
        _save(d)
    return newly


def record_success(ticker: str) -> None:
    """Record a successful fetch — clears any in-progress failure streak.

    If the ticker was tombstoned and now resolves (transient delisting / vendor
    outage healed), it is auto-revived. Pure cleanup; never raises.
    """
    if not ticker:
        return
    t = ticker.upper()
    with _LOCK:
        d = _load()
        if t in d["tickers"]:
            del d["tickers"][t]
            _save(d)


def is_tombstoned(ticker: str) -> bool:
    """True if `ticker` is currently tombstoned AND not yet due for retry.

    A tombstoned ticker becomes eligible for retry (returns False here) once
    `retry_after_days` have elapsed since `tombstoned_at`, so a transient
    delisting self-heals on the next scan after the retry window. Returns False
    when tombstoning is disabled.
    """
    if not is_enabled() or not ticker:
        return False
    t = ticker.upper()
    d = _load()
    rec = d["tickers"].get(t)
    if not rec or not rec.get("tombstoned"):
        return False
    ts = _parse_iso(rec.get("tombstoned_at") or rec.get("last_checked") or "")
    if ts is None:
        return True
    if datetime.now(timezone.utc) - ts >= timedelta(days=_retry_days()):
        # Past the retry window — let it be re-fetched. (Streak resets on the
        # next success; another threshold run of failures re-tombstones it.)
        return False
    return True


def tombstoned_set() -> set[str]:
    """Set of tickers currently tombstoned AND not yet due for retry.

    This is what the universe-assembly skip uses. Empty when disabled.
    """
    if not is_enabled():
        return set()
    return {t for t in _load().get("tickers", {}) if is_tombstoned(t)}


def untombstone(ticker: str) -> bool:
    """Manually revive a ticker — drop it from the registry entirely.

    Returns True if it was present. Used by the CLI `revive` and by any
    operator action when a name re-lists or was tombstoned in error.
    """
    if not ticker:
        return False
    t = ticker.upper()
    with _LOCK:
        d = _load()
        if t in d["tickers"]:
            del d["tickers"][t]
            _save(d)
            return True
    return False


def list_all() -> dict:
    """Full registry tickers map (for diagnostics / CLI `list`)."""
    return _load().get("tickers", {})


# ── CLI ────────────────────────────────────────────────────────────────────
def _main(argv: list[str]) -> int:
    import sys
    cmd = argv[1] if len(argv) > 1 else "list"
    if cmd == "list":
        recs = list_all()
        if not recs:
            print("delisted registry empty")
            return 0
        active = tombstoned_set()
        print(f"{'TICKER':10} {'STREAK':>6}  {'TOMB':5}  {'RETRY-DUE':9}  REASON")
        for t in sorted(recs):
            r = recs[t]
            print(f"{t:10} {r.get('fail_streak',0):>6}  "
                  f"{'YES' if r.get('tombstoned') else 'no':5}  "
                  f"{'no' if t in active else 'yes':9}  "
                  f"{r.get('reason','')}")
        print(f"\n{len(active)} actively skipped · {len(recs)} tracked · "
              f"threshold={_threshold()} retry_after={_retry_days()}d · "
              f"enabled={is_enabled()}")
        return 0
    if cmd == "revive":
        if len(argv) < 3:
            print("usage: delisted_registry.py revive TICKER [TICKER...]")
            return 2
        for t in argv[2:]:
            print(f"revive {t.upper()}: {'removed' if untombstone(t) else 'not present'}")
        return 0
    if cmd in ("fail", "_fail"):  # test helper: simulate a failure
        if len(argv) < 3:
            print("usage: delisted_registry.py fail TICKER")
            return 2
        newly = record_failure(argv[2])
        print(f"fail {argv[2].upper()}: streak recorded · newly_tombstoned={newly}")
        return 0
    print(f"unknown command: {cmd}\nusage: delisted_registry.py [list|revive TICKER|fail TICKER]")
    return 2


if __name__ == "__main__":
    import sys
    sys.exit(_main(sys.argv))

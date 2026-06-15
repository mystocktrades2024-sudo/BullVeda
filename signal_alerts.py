"""signal_alerts.py — daily Slack alerts for engine state changes.

Two event types (built 2026-06-15 per owner request):
  1. WATCH->BUY flips — a name's per-mode verdict upgrades to BUY day-over-day
  2. New Elite Picks   — a name newly enters the top-conviction BUY set per mode

Both are day-over-day diffs against a stored snapshot (data/signal_alert_snapshot.json).
First run seeds the snapshot and fires nothing. These surface the SAME engine
verdicts the morning briefing already sends live, just event-driven — so unlike
the entry-watcher (a novel unvalidated signal, kept in shadow) these fire LIVE
to the owner Slack. Honest caveat: per our audits composite score is anti-
predictive, so these are convenience notifications, not high-edge signals — the
footer says so. Runs once daily AFTER the morning scan rewrites last_bundle.json.

Reuses the alerts.send_alert dispatcher; no new data sources, zero EODHD.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger("signal_alerts")
BASE_DIR = Path(__file__).parent
BUNDLE_PATH = BASE_DIR / "cache" / "last_bundle.json"
SNAPSHOT_PATH = BASE_DIR / "data" / "signal_alert_snapshot.json"

# Per-mode BUY source lists in the bundle. decisions_by_mode.verdict only ever
# holds WATCH/AVOID (never BUY) — the canonical BUY decision lives in these
# curated per-mode lists (verdict=='BUY') and the row-level verdict.
MODE_LISTS = {"swing": "buy_candidates", "position": "medium_term_picks", "invest": "long_term_picks"}
# Catalyst-driven strategy sleeves — fired flag lives in <field>.fired on each
# all_scored row. These are the higher-mechanism signals (principle 14) and fire
# rarely, so a dedicated daily "new signal" alert is high-value + low-noise.
SLEEVES = {
    "pead_audit": "PEAD (post-earnings drift)",
    "insider_cluster_audit": "Insider Cluster",
    "esp_play_audit": "ESP Play",
    "meanrev_audit": "Mean Reversion",
    "momentum_audit": "Momentum Continuation",
    "defrot_audit": "Defensive Rotation",
}
RULE = "—" * 21
CAVEAT = "⚠️ Score-based heads-up — not vetted edge"
SLEEVE_NOTE = "🧬 Catalyst signal · Phase-1 paper validation"


def _send(level: str, title: str, body: str):
    try:
        from alerts import send_alert
        send_alert(level=level, title=title, body=body, force_slack=True)
    except Exception as e:
        log.debug(f"alert dispatch failed: {e}")


def _load_snapshot() -> dict:
    if not SNAPSHOT_PATH.exists():
        return {}
    try:
        return json.load(open(SNAPSHOT_PATH))
    except Exception:
        return {}


def _save_snapshot(snap: dict):
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    json.dump(snap, open(SNAPSHOT_PATH, "w"), indent=2, default=str)


def _conv_tier(row: dict):
    """Conviction tier from a row. dict {tier:..} or bare value. -1 == AVOID."""
    c = row.get("conviction")
    return c.get("tier") if isinstance(c, dict) else c


def _actionable(row: dict) -> bool:
    """A genuine, actionable BUY: conviction T1/T2/T3 (not AVOID/-1 or None).

    Guards against the FRT-class bug — the engine sometimes stamps verdict=BUY on
    conviction-AVOID names ("Pass — weak score"); surfacing those as a 'new BUY'
    alert is misleading. Only tiers 1/2/3 are real.
    """
    return _conv_tier(row) in (1, 2, 3)


def _current_state(bundle: dict) -> dict:
    """Build {buys: {mode: [tickers]}, elite: [tickers]} from the bundle.

    buys[mode] = verdict=='BUY' AND actionable conviction (T1/T2/T3) in that mode.
    elite      = bundle.elite_picks, filtered to actionable-conviction names
                 (elite rows carry no conviction, so cross-ref all_scored).
    """
    buys = {}
    for mode, key in MODE_LISTS.items():
        lst = bundle.get(key) or []
        buys[mode] = sorted({r.get("ticker") for r in lst
                             if isinstance(r, dict) and r.get("verdict") == "BUY"
                             and _actionable(r) and r.get("ticker")})
    rows = bundle.get("all_scored") or []
    conv_map = {r.get("ticker"): r for r in rows if isinstance(r, dict)}
    elite = sorted({r.get("ticker") for r in (bundle.get("elite_picks") or [])
                    if isinstance(r, dict) and r.get("ticker")
                    and _actionable(conv_map.get(r.get("ticker"), {}))})
    # Catalyst sleeves: tickers where the sleeve detector fired today.
    sleeves = {}
    for field, label in SLEEVES.items():
        fired = sorted({r.get("ticker") for r in rows
                        if isinstance(r.get(field), dict) and r[field].get("fired") and r.get("ticker")})
        if fired:
            sleeves[label] = fired
    return {"buys": buys, "elite": elite, "sleeves": sleeves}


def run_signal_alerts(dry_run: bool = False) -> dict:
    if not BUNDLE_PATH.exists():
        return {"error": "no_bundle"}
    bundle = json.load(open(BUNDLE_PATH))
    cur = _current_state(bundle)
    prev = _load_snapshot()

    emit = (lambda *_a: None) if dry_run else _send
    flips, new_elite, new_sleeves = [], [], []
    seeded = not bool(prev)

    # --- #2: WATCH->BUY flips = new entrants to a mode's BUY list ---
    prev_buys = prev.get("buys") or {}
    if prev_buys:  # skip on first run (seed only)
        for mode, tickers in cur["buys"].items():
            before = set(prev_buys.get(mode) or [])
            for tk in tickers:
                if tk not in before:
                    flips.append({"ticker": tk, "mode": mode})

    # --- #3: new entrants to the curated top-conviction Elite set ---
    prev_elite = set(prev.get("elite") or [])
    if prev.get("elite") is not None and "elite" in prev:
        for tk in cur["elite"]:
            if tk not in prev_elite:
                new_elite.append({"ticker": tk})

    # --- #4: newly-fired catalyst sleeve signals (PEAD/insider/ESP/...) ---
    prev_sleeves = prev.get("sleeves") or {}
    if "sleeves" in prev:  # skip on first run (seed only)
        for label, tickers in cur["sleeves"].items():
            before = set(prev_sleeves.get(label) or [])
            for tk in tickers:
                if tk not in before:
                    new_sleeves.append({"ticker": tk, "sleeve": label})

    # Emit — clean scannable cards (match the entry-alert card style).
    if flips:
        by_m = {}
        for f in flips:
            by_m.setdefault(f["mode"], []).append(f["ticker"])
        lines = [RULE]
        for m in MODE_LISTS:                         # stable swing/position/invest order
            if by_m.get(m):
                lines.append(f"{m.upper():9}{', '.join(by_m[m])}")
        lines.append(CAVEAT)
        emit("INFO", f"⬆️  New BUYs today  ·  {len(flips)}", "\n".join(lines))
    if new_elite:
        ts = ", ".join(e["ticker"] for e in new_elite)
        emit("INFO", f"⭐  New Elite Picks today  ·  {len(new_elite)}",
             f"{RULE}\n{ts}\n{CAVEAT}")
    if new_sleeves:
        by_s = {}
        for e in new_sleeves:
            by_s.setdefault(e["sleeve"], []).append(e["ticker"])
        lines = [RULE] + [f"{s}\n  {', '.join(ts)}" for s, ts in by_s.items()] + [SLEEVE_NOTE]
        emit("INFO", f"🧬  New catalyst signal(s)  ·  {len(new_sleeves)}", "\n".join(lines))

    if not dry_run:
        _save_snapshot(cur)

    return {
        "mode": "dry_run" if dry_run else "live",
        "flips": flips,
        "new_elite": new_elite,
        "new_sleeves": new_sleeves,
        "seeded": seeded,
    }


if __name__ == "__main__":
    import sys
    r = run_signal_alerts(dry_run=("--send" not in sys.argv))
    if "--send" not in sys.argv:
        print("[DRY-RUN — no Slack. Pass --send to fire + save snapshot.]")
    print(json.dumps(r, indent=2, default=str))

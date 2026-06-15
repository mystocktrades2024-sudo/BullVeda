"""entry_watch.py — intraday entry-zone watcher for bullish-bias names.

The gap this fills (2026-06-15): the morning briefing only pushes actionable
BUY candidates. A WATCH name that is bullish but *extended* (e.g. VIRT — score
84, RS 100, but 2.5 ATR above EMA21) never gets surfaced again, and nothing
watches it intraday to ping when price pulls back into a buyable zone. So you
silently miss the entry. This module closes that loop.

Scope: EVERY bullish-bias name in the latest scan (cache/last_bundle.json),
not just the custom watchlist. ~250 names — one Schwab batch quote call covers
all of them, so there is ZERO EODHD quota cost (Schwab market-data is free with
the brokerage and works 24/7).

Two-tier alerts (per user request 2026-06-15):
  Tier 1 — SOFT  "entering zone"  : price has pulled into the buy zone band.
                                     Heads-up; verify on dashboard.
  Tier 2 — FIRM  "BUY confirmed"  : price in zone AND entry was the SOLE
                                     blocker (reason_class == 'extended') AND
                                     live R:R (price→T1 vs price→stop) clears
                                     the mode's buy_min_rr. This is a genuine
                                     WATCH→BUY flip without re-running the engine.

Names blocked for OTHER reasons (fundamentals/regime/etc.) only ever get the
Tier-1 soft ping — entering the zone does not clear those gates, so we say so
rather than fake a BUY.

Buy zone is computed offline from the morning bundle (EMA8/21/50, ATR, pivot,
support + the swing entry_quality_gate), so the intraday pass needs nothing but
a live price. Mirrors classify_entry_quality:
  FRESH    : within 0.75 ATR of pivot/support
  PULLBACK : within 1.25 ATR of EMA8/21/50

v1 watches the SWING-mode zone (shortest hold, most timing-sensitive — the case
that actually bites). position/invest zones can be added the same way.

Throttle + Slack dispatch + Schwab batch are reused from position_alerts.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from position_alerts import (
    _already_sent_today,
    _mark_sent,
    _send,
    _is_market_hours,
    _get_schwab_batch,
)

log = logging.getLogger("entry_watch")
BASE_DIR = Path(__file__).parent
BUNDLE_PATH = BASE_DIR / "cache" / "last_bundle.json"
CONFIG_PATH = BASE_DIR / "config" / "config.json"
SHADOW_LOG = BASE_DIR / "cache" / "entry_watch_shadow.jsonl"

MODE = "swing"  # v1 — entry timing is most acute for swings

# Setup families allowed through the entry-zone gate. Derived from a zero-EODHD
# forward-return analysis of 4,790 audit-ledger signals (2026-06-15): the
# zone-entry cohort (long + FRESH/PULLBACK) by family @ d3:
#   Trend Continuation  PF 1.6-1.9 (n=65)   <- KEEP
#   Breakout Expansion  PF 0.78-0.92 (n=85) <- DROP (a "breakout" entering a
#                                               pullback zone = failed breakout)
#   Impulse Catalyst    PF 0.15-0.19 (n=18) <- DROP
# In-sample, mostly risk_on_choppy regime. Edge is a 2-5 day event (decays by d7).
# Override via config.json -> entry_watch.family_allowlist.
FAMILY_ALLOWLIST = {"Trend Continuation"}


def _send_enabled() -> bool:
    """Slack alerts are OFF until the entry-zone event is validated (principle 1).

    Default False => SHADOW MODE: the watcher runs, logs every candidate it
    WOULD have alerted (with regime/family/mc_p stamped) to entry_watch_shadow.jsonl
    for out-of-sample forward scoring, but sends nothing. Flip via config:
    config.json -> {"entry_watch": {"send_enabled": true}} only after the
    backtest + shadow record show the filtered cohort clears the PF floor.
    """
    try:
        cfg = json.load(open(CONFIG_PATH))
        return bool((cfg.get("entry_watch") or {}).get("send_enabled", False))
    except Exception:
        return False


def _shadow_slack_enabled() -> bool:
    """Whether to ALSO mirror shadow candidates to Slack (observation feed).

    Distinct from send_enabled: this does NOT mean validated/live. It just lets
    the owner watch what the watcher detects during the validation window. Every
    message is stamped SHADOW and annotates the validated-family status, so it is
    never mistaken for a vetted BUY. config: entry_watch.shadow_slack (default False).
    """
    try:
        cfg = json.load(open(CONFIG_PATH))
        return bool((cfg.get("entry_watch") or {}).get("shadow_slack", False))
    except Exception:
        return False


def _current_regime() -> str:
    try:
        b = json.load(open(BUNDLE_PATH))
        return (b.get("regime") or {}).get("regime4") or "unknown"
    except Exception:
        return "unknown"


def _shadow_record(rec: dict):
    """Append one would-fire candidate to the shadow log (no Slack)."""
    try:
        SHADOW_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(SHADOW_LOG, "a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
    except Exception as e:
        log.debug(f"shadow log write failed: {e}")


def _f(v):
    """Coerce to float or None."""
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def compute_buy_zone(row: dict) -> dict | None:
    """Derive the swing buy zone for one bullish bundle row.

    Returns {zone_low, zone_high, stop, t1, buy_min_rr, reason_class,
             sole_blocker_is_entry} or None if the row lacks the inputs.

    zone_high = the highest price that would still classify as FRESH or
                PULLBACK (i.e. price has come back down far enough to buy).
    zone_low  = the swing stop — below it the setup is broken, not a buy.
    """
    sw = (row.get("decisions_by_mode") or {}).get(MODE) or {}
    ind = ((row.get("technicals") or {}).get("indicators")) or {}
    sr = ((row.get("technicals") or {}).get("sr")) or {}

    atr = _f(ind.get("atr"))
    price = _f(row.get("price"))
    if not atr or not price:
        return None

    ema8 = _f(ind.get("ema8"))
    ema21 = _f(ind.get("ema21"))
    ema50 = _f(ind.get("ema50"))
    pivot = _f(sr.get("pivot"))
    support = _f(sr.get("support"))

    gate = sw.get("entry_quality_gate") or ["FRESH", "PULLBACK"]
    emas = [e for e in (ema8, ema21, ema50) if e]
    if not emas:
        return None
    ema_lo, ema_hi = min(emas), max(emas)

    # The buy zone is the PULLBACK band — where price has come back DOWN to the
    # EMAs. Anchor to the EMAs themselves, NOT the morning swing stop: that stop
    # is a 1.25xATR stop computed from today's *extended* price and often sits
    # ABOVE the EMAs, which would clip out the entire real pullback zone.
    zone_high = ema_hi + 0.5 * atr          # shallow pullback to the top EMA
    zone_low = ema_lo - 0.75 * atr          # deep pullback below the bottom EMA
    # FRESH gate: extend the band down to a pivot/support that sits lower.
    if ("FRESH" in gate or "VALID" in gate):
        for lvl in (support, pivot):
            if lvl:
                zone_low = min(zone_low, lvl - 0.75 * atr)

    # Structural pullback stop: just below the support/lowest-EMA shelf. This is
    # the stop you'd actually use entering on the pullback — NOT the stale
    # chase-entry stop. Used for live R:R on the firm (Tier-2) alert.
    shelf = min([x for x in (support, ema_lo) if x] or [ema_lo])
    pullback_stop = shelf - 0.5 * atr
    zone_low = max(zone_low, pullback_stop)  # never buy below your own stop
    t1 = _f(sw.get("t1"))

    return {
        "zone_low": round(zone_low, 2),
        "zone_high": round(zone_high, 2),
        "stop": round(pullback_stop, 2),
        "t1": round(t1, 2) if t1 else None,
        "buy_min_rr": _f(sw.get("buy_min_rr")) or 3.0,
        "reason_class": sw.get("reason_class") or "",
        "sole_blocker_is_entry": (sw.get("reason_class") == "extended"),
        "verdict": sw.get("verdict"),
        "score": _f(row.get("score")),
        "rs_rank": _f(row.get("rs_rank")),
        "setup_family": row.get("setup_family"),
        "catalyst_tier": row.get("catalyst_tier"),
        "mc_p_profit": _f(row.get("mc_p_profit")),
        "atr": round(atr, 2),
    }


def build_targets() -> dict:
    """Read latest bundle, compute buy zones for the bullish names we're WAITING
    on — i.e. currently EXTENDED above their pullback ceiling.

    A bullish name already trading at/below its zone ceiling isn't "an entry that
    just appeared" — it's either already actionable (a BUY, surfaced by the
    morning briefing) or blocked for a non-entry reason (where a pullback ping
    wouldn't change anything). We watch the still-extended names and fire when
    they pull DOWN into the zone. That's the exact case VIRT is in.
    """
    if not BUNDLE_PATH.exists():
        return {}
    bundle = json.load(open(BUNDLE_PATH))
    rows = bundle.get("all_scored") or []
    targets = {}
    for r in rows:
        if r.get("bias") != "bullish":
            continue
        # NOTE: the family allowlist is a SEND-time gate (applied in the live
        # path), NOT here. build_targets logs ALL bullish-extended families so
        # shadow mode keeps collecting the out-of-sample record needed to confirm
        # which families have edge. Filters belong at send-time, not collect-time.
        # Already actionable BUYs are surfaced by the morning briefing — skip.
        v = ((r.get("decisions_by_mode") or {}).get(MODE) or {}).get("verdict")
        if v == "BUY":
            continue
        z = compute_buy_zone(r)
        if not z:
            continue
        price = _f(r.get("price"))
        # Only watch names still EXTENDED above the zone — the entry hasn't
        # arrived yet. Names already in-zone fire nothing (avoids first-run flood).
        if price is None or price <= z["zone_high"]:
            continue
        targets[r.get("ticker")] = z
    return targets


def _live_rr(price: float, t1: float, stop: float) -> float | None:
    """R:R from a live entry at `price` to t1 against stop."""
    if not (price and t1 and stop) or price <= stop or t1 <= price:
        return None
    return (t1 - price) / (price - stop)


def run_entry_watch_pass(dry_run: bool = False) -> dict:
    """Main entry — called every cycle by run_entry_watch.sh during market hours.

    dry_run=True computes everything and returns what WOULD fire without sending
    Slack/Mac notifications or touching the throttle log. Use for testing.
    """
    if not _is_market_hours():
        return {"skipped": True, "reason": "outside_market_hours"}

    targets = build_targets()
    if not targets:
        return {"skipped": True, "reason": "no_bullish_targets"}

    sent = _already_sent_today
    mark = _mark_sent
    emit = _send
    # SHADOW MODE: validation not complete -> never Slack, just log candidates.
    shadow = (not _send_enabled()) and (not dry_run)
    if dry_run or shadow:
        sent = lambda *_a: False          # noqa: E731 — never suppress in preview
        mark = lambda *_a: None           # noqa: E731 — never write throttle log
        emit = lambda *_a: None           # noqa: E731 — never hit Slack

    # Validated SEND-time gate (live only): family allowlist from the zero-EODHD
    # forward-return analysis. Shadow logs everything; live alerts only the
    # families with confirmed edge.
    try:
        cfg = json.load(open(CONFIG_PATH))
        allow = set((cfg.get("entry_watch") or {}).get("family_allowlist") or FAMILY_ALLOWLIST)
    except Exception:
        allow = FAMILY_ALLOWLIST

    regime = _current_regime()
    quotes = _get_schwab_batch(list(targets.keys()))
    if not quotes:
        return {"error": "no_schwab_quotes", "note": "Schwab token may be expired — run: python3 schwab_auth.py oauth"}

    alerts_sent = []
    shadow_logged = []
    in_zone = 0
    for ticker, z in targets.items():
        q = quotes.get(ticker)
        price = _f(q.get("price")) if q else None
        if not price:
            continue
        if not (z["zone_low"] <= price <= z["zone_high"]):
            continue
        in_zone += 1

        # Determine which tier this candidate would be (for both shadow + live).
        rr_live = _live_rr(price, z["t1"], z["stop"]) if (z["stop"] and z["t1"]) else None
        would_buy = bool(z["sole_blocker_is_entry"] and rr_live and rr_live >= z["buy_min_rr"])

        # SHADOW MODE: log the candidate with every filter dimension stamped, so
        # we can score forward outcomes by regime/family/mc_p/rank later. No Slack.
        # Throttle to one record per ticker per tier per day (else ~78 fires/day
        # would write the same candidate 78×). Reuses the alert_sent_log throttle.
        if shadow:
            stier = "shadow_buy" if would_buy else "shadow_zone"
            if _already_sent_today(ticker, stier):
                continue
            _mark_sent(ticker, stier)
            rec = {
                "ticker": ticker, "price": price, "tier": "buy" if would_buy else "zone",
                "regime": regime, "setup_family": z.get("setup_family"),
                "catalyst_tier": z.get("catalyst_tier"), "mc_p_profit": z.get("mc_p_profit"),
                "score": z.get("score"), "rs_rank": z.get("rs_rank"),
                "rr_live": round(rr_live, 2) if rr_live else None,
                "zone": [z["zone_low"], z["zone_high"]], "stop": z["stop"], "t1": z["t1"],
            }
            _shadow_record(rec)
            shadow_logged.append({"ticker": ticker, "tier": rec["tier"]})

            # Optional: mirror to Slack as a clearly-labeled OBSERVATION feed.
            if _shadow_slack_enabled():
                fam = z.get("setup_family") or "?"
                fam_ok = fam in allow
                fam_tag = "✓ validated family" if fam_ok else "✗ family historically loses (drop at go-live)"
                mcp = z.get("mc_p_profit")
                bits = [f"{fam} — {fam_tag}", f"regime {regime}"]
                if mcp is not None:
                    bits.append(f"mc_p {mcp:.2f}")
                if rr_live:
                    bits.append(f"R:R {rr_live:.1f}")
                if would_buy:
                    # Firm BUY-candidate — pulled deep enough that entry + R:R clear.
                    _send(
                        "INFO",
                        f"🎯 SHADOW BUY-CANDIDATE · {ticker}",
                        f"*${price:.2f} pulled into buy zone [{z['zone_low']:.2f}–{z['zone_high']:.2f}] — entry + R:R clear.*\n"
                        f"{' · '.join(bits)} · stop ${z['stop']:.2f} → T1 ${z['t1']:.2f}\n"
                        f"_Observation-only — NOT a validated signal (shadow until OOS confirms edge)._",
                    )
                else:
                    _send(
                        "INFO",
                        f"🔬 SHADOW · {ticker} in zone",
                        f"${price:.2f} in zone [{z['zone_low']:.2f}–{z['zone_high']:.2f}] · "
                        f"{' · '.join(bits)}\n"
                        f"_Observation-only — NOT a validated signal. Entry-watcher is in shadow "
                        f"until out-of-sample data confirms edge._",
                    )
            continue

        # LIVE path — apply the validated family gate before alerting.
        if z.get("setup_family") not in allow:
            continue

        # Tier 2 — firm BUY: entry was the sole blocker AND live R:R clears floor.
        if z["sole_blocker_is_entry"] and z["stop"] and z["t1"]:
            rr = _live_rr(price, z["t1"], z["stop"])
            if rr and rr >= z["buy_min_rr"]:
                if not sent(ticker, "entry_buy"):
                    extras = []
                    if z.get("score"):
                        extras.append(f"score {z['score']:.0f}")
                    if z.get("rs_rank"):
                        extras.append(f"RS {z['rs_rank']:.0f}")
                    if z.get("setup_family"):
                        extras.append(z["setup_family"])
                    emit(
                        "INFO",
                        f"✅ {ticker} BUY zone — entry confirmed",
                        f"${price:.2f} pulled into buy zone "
                        f"[{z['zone_low']:.2f}–{z['zone_high']:.2f}]. "
                        f"Live R:R {rr:.1f} ≥ {z['buy_min_rr']:.0f} "
                        f"(stop ${z['stop']:.2f}, T1 ${z['t1']:.2f}). "
                        f"{' · '.join(extras)}. Entry-quality block cleared — was a WATCH only because it was extended.",
                    )
                    mark(ticker, "entry_buy")
                    # Suppress the soft ping once we've sent the firm one.
                    mark(ticker, "entry_zone")
                    alerts_sent.append({"ticker": ticker, "type": "entry_buy", "price": price, "rr": round(rr, 2)})
                continue  # don't also send Tier-1 for the same name

        # Tier 1 — soft: in zone, but other gates may still apply.
        if not sent(ticker, "entry_zone"):
            blk = "" if z["sole_blocker_is_entry"] else " (other gates still apply — verify on dashboard)"
            emit(
                "WARN",
                f"\U0001f440 {ticker} entering buy zone",
                f"${price:.2f} pulled into zone "
                f"[{z['zone_low']:.2f}–{z['zone_high']:.2f}]"
                f"{blk}. Stop ${z['stop'] or 0:.2f}, T1 ${z['t1'] or 0:.2f}. "
                f"Watch closely.",
            )
            mark(ticker, "entry_zone")
            alerts_sent.append({"ticker": ticker, "type": "entry_zone", "price": price})

    return {
        "mode": "shadow" if shadow else ("dry_run" if dry_run else "live"),
        "regime": regime,
        "alerts_sent": alerts_sent,
        "shadow_logged": shadow_logged,
        "bullish_watched": len(targets),
        "quotes_returned": len(quotes),
        "in_zone": in_zone,
    }


if __name__ == "__main__":
    import sys
    if "build" in sys.argv:
        t = build_targets()
        print(f"{len(t)} bullish targets")
        for k, v in list(t.items())[:15]:
            print(f"  {k}: zone [{v['zone_low']}–{v['zone_high']}] "
                  f"stop {v['stop']} t1 {v['t1']} sole_entry_block={v['sole_blocker_is_entry']} ({v['reason_class']})")
    else:
        # Smoke test — force market-hours so it runs anytime.
        # ALWAYS dry-run from the CLI unless --send is passed, so testing never
        # spams Slack (the throttle log is also left untouched).
        import entry_watch as _ew
        _ew._is_market_hours = lambda: True
        dry = "--send" not in sys.argv
        r = _ew.run_entry_watch_pass(dry_run=dry)
        if dry:
            print("[DRY-RUN — no Slack sent. Pass --send to actually alert.]")
        print(json.dumps(r, indent=2, default=str))

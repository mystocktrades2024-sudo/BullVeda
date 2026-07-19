"""Signal-layer edge-erosion brake (2026-07-13).

Principle 11 (edge erosion): the system fired 2,200+ BUY signals into the
June–July 2026 chop with NEGATIVE average forward returns (w1 by month:
Apr +1.85% → May +1.35% → Jun −0.56% → Jul −1.87%) and nothing throttled it —
the rolling-Sharpe kill was intentionally decoupled from the signal path by
the portfolio-blind flag (2026-06-07) and no signal-level brake replaced it.

This module IS that replacement, and it is PORTFOLIO-BLIND by construction:
it reads only cache/audit_ledger.json — the UNIVERSAL system pick record
(identical for every user; rebuilt daily by scripts/audit_signal_to_ledger.py)
— never signal_log.json or portfolio_state.json (see
feedback/signal_layer_portfolio_blind invariant).

Mechanism: compute the average 5-trading-day forward return (w1) of the BUY
cohort picked in the trailing `lookback_days` calendar window. When the
trailing cohort is net-negative on adequate n, raise the effective
buy_min_score by a tiered delta so marginal signals stop firing while the
tape is eating the edge. The brake NEVER lowers the bar and caps its own
delta — it throttles, it does not halt (catalyst sleeves keep their own
bypass economics; a full halt would repeat the QUANT-1 starvation failure).

State is cached to cache/edge_brake_state.json (recomputed at most once per
calendar day) so per-ticker scoring does zero extra I/O beyond one small read.

Config block (config/config.json → signal_edge_brake):
  _enabled       : master switch (rollback = false)
  lookback_days  : trailing calendar window for the cohort (default 28)
  min_n          : minimum resolved-w1 BUY signals to act on (default 150)
  tiers          : [{"below": 0.0, "delta": 8}, {"below": -1.0, "delta": 15}]
                   — deepest matching tier wins; delta adds to buy_min_score
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path

log = logging.getLogger("edge_brake")

BASE_DIR = Path(__file__).resolve().parent
LEDGER_PATH = BASE_DIR / "cache" / "audit_ledger.json"
STATE_PATH = BASE_DIR / "cache" / "edge_brake_state.json"

DEFAULT_CFG = {
    "_enabled": True,
    "lookback_days": 28,
    "min_n": 150,
    "tiers": [{"below": 0.0, "delta": 8}, {"below": -1.0, "delta": 15}],
}

_state_cache: dict | None = None  # per-process memo of the state file


def _cfg(config: dict | None) -> dict:
    out = dict(DEFAULT_CFG)
    out.update((config or {}).get("signal_edge_brake") or {})
    return out


def recompute_state(config: dict | None = None) -> dict:
    """Rebuild brake state from the audit ledger and persist it.

    Called from scan startup (swing_trade.py). Failure-safe: any error returns
    a delta-0 state so a broken ledger can never block the scan.
    """
    cfg = _cfg(config)
    today = date.today()
    state = {
        "as_of": today.isoformat(),
        "computed_at": datetime.now().isoformat(timespec="seconds"),
        "enabled": bool(cfg.get("_enabled", True)),
        "delta": 0,
        "n": 0,
        "avg_w1": None,
        "wr": None,
        "lookback_days": cfg["lookback_days"],
        "note": "",
    }
    try:
        ledger = json.loads(LEDGER_PATH.read_text())
        cutoff = (today - timedelta(days=int(cfg["lookback_days"]))).isoformat()
        vals = [
            r["w1"]
            for r in (ledger.get("records") or [])
            if r.get("verdict") == "BUY"
            and str(r.get("pick_date") or "") >= cutoff
            and isinstance(r.get("w1"), (int, float))
        ]
        state["n"] = len(vals)
        if len(vals) >= int(cfg["min_n"]):
            avg = sum(vals) / len(vals)
            state["avg_w1"] = round(avg, 3)
            state["wr"] = round(sum(1 for v in vals if v > 0) / len(vals), 3)
            delta = 0
            for tier in sorted(cfg["tiers"], key=lambda t: t["below"], reverse=True):
                if avg < float(tier["below"]):
                    delta = int(tier["delta"])
            state["delta"] = delta if state["enabled"] else 0
            state["note"] = (
                f"trailing {cfg['lookback_days']}d BUY cohort n={len(vals)} "
                f"avg_w1={avg:+.2f}% WR={state['wr']:.0%} → buy_min {delta:+d}"
            )
        else:
            state["note"] = f"n={len(vals)} < min_n={cfg['min_n']} — brake inert"
    except Exception as e:
        state["note"] = f"recompute failed ({e}) — brake inert"
        log.warning(state["note"])

    try:
        STATE_PATH.write_text(json.dumps(state, indent=2))
    except Exception as e:
        log.warning(f"edge_brake state write failed: {e}")
    global _state_cache
    _state_cache = state
    if state["delta"]:
        log.info(f"EDGE BRAKE ON: {state['note']}")
    return state


def get_delta(config: dict | None = None) -> tuple[int, dict]:
    """Return (buy_min delta, state). Zero-delta on any staleness/failure.

    Reads the cached state file; recomputes if missing or from a prior day.
    Cheap enough for the per-ticker scoring path (memoized per process).
    """
    global _state_cache
    state = _state_cache
    if state is None:
        try:
            state = json.loads(STATE_PATH.read_text())
            _state_cache = state
        except Exception:
            state = None
    if state is None or state.get("as_of") != date.today().isoformat():
        state = recompute_state(config)
    if not _cfg(config).get("_enabled", True):
        return 0, state
    return int(state.get("delta") or 0), state

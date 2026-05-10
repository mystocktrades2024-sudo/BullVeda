"""
signal_filter.py — declarative whitelist gate for BUY verdicts (A2).

Demotes BUY → WATCH for any (setup_type × regime × score_band × entry_quality)
combination NOT in the whitelist. Off by default; flip
`config["signal_filter"]["_enabled"] = true` to activate.

Pattern follows decision_engine.py:258-277 — silent fallback on exceptions,
returns dict-shaped results, never raises.

Whitelist schema (in config.json["signal_filter"]):
    {
      "_enabled": false,
      "_validations": {
        "<rule_id>": {
          "n": 47, "wr": 0.52, "wr_lb": 0.45, "pf": 1.8,
          "source": "750d_backtest_2026-05-09",
          "validated_at": "2026-05-09"
        }
      },
      "whitelist": [
        {
          "id": "pp_70_79_fresh_bull",
          "setup_type": "Pocket Pivot",
          "regimes": ["risk_on_trending", "risk_on_choppy"],
          "score_band": [70, 79],          # inclusive
          "entry_quality": ["FRESH", "PULLBACK"]
        },
        ...
      ]
    }

Each rule must have a matching `_validations[rule_id]` entry with
n >= 20 AND wr_lb >= 0.40 OR the rule is silently rejected (defense
against adding speculative whitelist entries).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger("signal_filter")

ROOT = Path(__file__).parent
CONFIG_PATH = ROOT / "config" / "config.json"

# Validation gates for whitelist entries (defense against speculative rules)
RULE_MIN_N = 20
RULE_MIN_WR_LB = 0.40

SCORE_BANDS = ["<60", "60-69", "70-79", "80-89", "90-100"]


def _score_band(score: float | int | None) -> str:
    """Bucket numeric score into band label matching whitelist rule format."""
    if score is None:
        return "<60"
    s = float(score)
    if s >= 90:
        return "90-100"
    if s >= 80:
        return "80-89"
    if s >= 70:
        return "70-79"
    if s >= 60:
        return "60-69"
    return "<60"


def _band_in_range(score: float | int | None, band_range: list[int] | None) -> bool:
    """Check if score falls within [low, high] inclusive."""
    if not band_range or score is None:
        return False
    try:
        low, high = int(band_range[0]), int(band_range[1])
        return low <= float(score) <= high
    except (TypeError, ValueError, IndexError):
        return False


def _load_filter_config() -> dict:
    """Read config["signal_filter"] block, defaulting to disabled if missing."""
    try:
        cfg = json.loads(CONFIG_PATH.read_text())
        return cfg.get("signal_filter") or {"_enabled": False, "whitelist": [], "_validations": {}}
    except Exception as e:
        log.debug(f"signal_filter config load failed: {e}")
        return {"_enabled": False, "whitelist": [], "_validations": {}}


def _rule_is_validated(rule: dict, validations: dict) -> bool:
    """A rule only takes effect if its _validations entry passes statistical gates."""
    rule_id = rule.get("id")
    if not rule_id:
        return False
    v = validations.get(rule_id) or {}
    n = int(v.get("n") or 0)
    wr_lb = float(v.get("wr_lb") or 0.0)
    return n >= RULE_MIN_N and wr_lb >= RULE_MIN_WR_LB


def _rule_matches(rule: dict, setup_type: str, regime: str,
                   score: float | int | None, entry_quality: str) -> bool:
    """Check if a ticker's classification matches a whitelist rule."""
    if rule.get("setup_type") and rule["setup_type"] != setup_type:
        return False
    regimes = rule.get("regimes") or []
    if regimes and regime not in regimes:
        return False
    if not _band_in_range(score, rule.get("score_band")):
        return False
    eq_list = rule.get("entry_quality") or []
    if eq_list and entry_quality not in eq_list:
        return False
    return True


def is_tradeable(setup_type: str | None, regime: str | None,
                 score: float | int | None, entry_quality: str | None,
                 config_override: dict | None = None) -> tuple[bool, str, str | None]:
    """Main gate. Returns (allow: bool, reason: str, matched_rule_id: str | None).

    allow=True means the BUY verdict stays. allow=False means demote to WATCH.

    config_override is for tests; in production, reads from config.json.

    Behavior matrix:
      filter disabled                → (True, "filter_disabled", None)
      empty whitelist                → (True, "no_whitelist", None) — fail-open
      no rule matches                → (False, "no_matching_rule", None)
      rule matches but unvalidated   → continues searching; if none validated, (False, "no_validated_match", None)
      rule matches AND validated     → (True, "whitelisted", rule_id)
    """
    fcfg = config_override if config_override is not None else _load_filter_config()

    if not fcfg.get("_enabled"):
        return (True, "filter_disabled", None)

    whitelist = fcfg.get("whitelist") or []
    if not whitelist:
        # Fail-open: don't block all BUYs just because nobody filled the whitelist
        return (True, "no_whitelist", None)

    validations = fcfg.get("_validations") or {}

    # Coerce inputs to safe defaults
    setup_type = setup_type or ""
    regime = regime or ""
    entry_quality = entry_quality or ""

    matched_unvalidated_id = None
    for rule in whitelist:
        if not isinstance(rule, dict):
            continue
        if not _rule_matches(rule, setup_type, regime, score, entry_quality):
            continue
        # Match found — but is it validated?
        if _rule_is_validated(rule, validations):
            return (True, "whitelisted", rule.get("id"))
        if matched_unvalidated_id is None:
            matched_unvalidated_id = rule.get("id")

    if matched_unvalidated_id:
        # We had a syntactic match but it lacked statistical backing
        return (False, f"matched_unvalidated_rule:{matched_unvalidated_id}", matched_unvalidated_id)

    band = _score_band(score)
    return (False, f"no_matching_rule:setup={setup_type}|regime={regime}|band={band}|eq={entry_quality}", None)


def evaluate(ticker_row: dict, config_override: dict | None = None) -> dict:
    """Convenience wrapper. Takes the analyzed-ticker dict, returns filter result dict.

    Expected ticker_row fields:
      setup_type, regime (or regime4), score, entry_quality

    Returns:
      {
        "allow": bool,
        "reason": str,
        "matched_rule_id": str | None,
        "score_band": str,
      }
    """
    setup = ticker_row.get("setup_type") or (ticker_row.get("plan") or {}).get("setup_type")
    regime = ticker_row.get("regime") or ticker_row.get("regime4") or ticker_row.get("regime_label")
    score = ticker_row.get("score")
    eq = ticker_row.get("entry_quality") or (ticker_row.get("plan") or {}).get("entry_quality")

    allow, reason, rule_id = is_tradeable(setup, regime, score, eq, config_override=config_override)
    return {
        "allow": allow,
        "reason": reason,
        "matched_rule_id": rule_id,
        "score_band": _score_band(score),
        # echo inputs for debug/audit
        "_input": {"setup_type": setup, "regime": regime, "score": score, "entry_quality": eq},
    }


def healthcheck() -> dict:
    """Diagnostic: report current filter state."""
    fcfg = _load_filter_config()
    whitelist = fcfg.get("whitelist") or []
    validations = fcfg.get("_validations") or {}
    n_validated = sum(1 for r in whitelist if isinstance(r, dict) and _rule_is_validated(r, validations))
    return {
        "enabled": bool(fcfg.get("_enabled")),
        "n_rules": len(whitelist),
        "n_validated_rules": n_validated,
        "validations_count": len(validations),
    }


if __name__ == "__main__":
    print(json.dumps(healthcheck(), indent=2))

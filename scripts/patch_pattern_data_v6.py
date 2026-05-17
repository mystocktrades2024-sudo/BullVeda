#!/usr/bin/env python3
"""
patch_pattern_data_v6.py — One-shot: augment every ticker's pattern_data
in infra/prototype/data*.json with the new v6 fields (elliott_wave,
key_levels, action_ladder, scenarios, execution_ticket, composite.narrative)
WITHOUT re-fetching OHLCV. Uses helpers from pattern_engine that operate
on existing detector outputs.

For wyckoff sub_phase / transition_triggers / vps_series — these need fresh
OHLCV so they'll be added on the next real scan (left as None/[]).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pattern_engine import (
    build_key_levels, build_action_ladder, compute_scenarios,
    build_entry_zone_and_narrative, _build_composite_narrative,
)


def _patch_one_ticker(item: dict) -> bool:
    pd_dict = item.get("pattern_data")
    if not isinstance(pd_dict, dict) or "wyckoff" not in pd_dict:
        return False
    spot = item.get("price") or item.get("close")
    try:
        spot = float(spot) if spot else 0.0
    except (TypeError, ValueError):
        spot = 0.0

    # Inject placeholder Elliott Wave (full detector requires OHLCV)
    if "elliott_wave" not in pd_dict:
        pd_dict["elliott_wave"] = {
            "vote": "NEUTRAL",
            "discretionary": True,
            "category": "discretionary",
            "current_wave": None,
            "rules_passed": 0,
            "rules_total": 3,
            "wave_points": {},
            "w5_target_low": None,
            "w5_target_high": None,
            "invalidation_level": None,
            "rationale": "Elliott Wave detector requires fresh OHLCV — will populate on next scan.",
            "falsification": "Daily close below W4-overlap level invalidates count; re-count required.",
            "confidence": 0.0,
        }

    # Augment wyckoff with sub_phase + triggers + vps if missing
    wy = pd_dict.get("wyckoff") or {}
    if "sub_phase" not in wy:
        wy["sub_phase"] = None
        wy["sub_phase_rationale"] = ""
        wy["transition_triggers"] = []
        wy["vps_series"] = []
        pd_dict["wyckoff"] = wy

    # Run derived helpers
    try:
        pd_dict["key_levels"] = build_key_levels(pd_dict, spot)
    except Exception as e:
        pd_dict["key_levels"] = []
    try:
        pd_dict["action_ladder"] = build_action_ladder(pd_dict, spot)
    except Exception as e:
        pd_dict["action_ladder"] = []
    try:
        pd_dict["scenarios"] = compute_scenarios(pd_dict, spot, None)
    except Exception as e:
        pd_dict["scenarios"] = {}
    try:
        pd_dict["execution_ticket"] = build_entry_zone_and_narrative(pd_dict, spot, None)
    except Exception as e:
        pd_dict["execution_ticket"] = {}

    # Compose narrative on composite + discretionary_count
    comp = pd_dict.get("composite") or {}
    method_details = {
        "wyckoff": pd_dict.get("wyckoff", {}),
        "classical": pd_dict.get("classical", {}),
        "volume_profile": pd_dict.get("volume_profile", {}),
        "fibonacci": pd_dict.get("fibonacci", {}),
        "ichimoku": pd_dict.get("ichimoku", {}),
        "sr_levels": pd_dict.get("sr_levels", {}),
        "trendlines": pd_dict.get("trendlines", {}),
        "elliott_wave": pd_dict.get("elliott_wave", {}),
    }
    counts = {"BULLISH": comp.get("bull_count", 0),
              "BEARISH": comp.get("bear_count", 0),
              "NEUTRAL": comp.get("neutral_count", 0)}
    disc_counts = {"BULLISH": 0, "BEARISH": 0, "NEUTRAL": 1}  # EW placeholder = NEUTRAL
    comp["discretionary_count"] = 1
    comp["discretionary_bull"] = 0
    comp["discretionary_bear"] = 0
    if "narrative" not in comp:
        comp["narrative"] = _build_composite_narrative(
            comp.get("verdict", "NEUTRAL"), comp.get("conviction", "LOW"),
            counts, disc_counts, method_details,
        )
    pd_dict["composite"] = comp
    return True


def _walk(obj):
    if isinstance(obj, dict):
        if isinstance(obj.get("pattern_data"), dict):
            yield obj
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for x in obj:
            yield from _walk(x)


def main():
    files = list((ROOT / "infra" / "prototype").glob("data*.json"))
    print(f"Found {len(files)} data*.json files")
    for f in files:
        try:
            j = json.loads(f.read_text())
        except Exception as e:
            print(f"  {f.name}: parse err {e}")
            continue
        patched = 0
        for ticker_item in _walk(j):
            if _patch_one_ticker(ticker_item):
                patched += 1
        if patched:
            f.write_text(json.dumps(j))
            print(f"  {f.name}: patched {patched} tickers")
        else:
            print(f"  {f.name}: no pattern_data found")


if __name__ == "__main__":
    main()

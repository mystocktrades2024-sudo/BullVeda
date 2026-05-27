"""
backfill_smc_stops.py — re-walk every ticker in infra/prototype/tickers.json,
recompute SMC-aware stop fields using canonical_trade_plan.compute_smc_stop_fields,
and patch the trade_plan dict in-place.

Run after the canonical_trade_plan.py SMC-stop layer ships so the static
tickers.json snapshot has the new fields immediately (rather than waiting
for the next scan to rewrite them).

Real-world driver (2026-05-26): CORZ's canonical stop $21.65 sits INSIDE
the Bull Order Block at $20.81-$23.00. Sweep takes out the stop before
the bounce. The SMC-stop layer detects + alternative-suggests for the
whole universe so the trap doesn't reappear silently elsewhere.

Output: tickers.json patched in-place with a .bak.<ts> backup.

Reports:
  - how many tickers had stop_inside_ob = true (system-wide trap count)
  - how many tickers got a stop_smc_suggested computed
  - per-ticker check for CORZ + IONQ
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

# Ensure project root is on the path so `import canonical_trade_plan` works
_THIS = Path(__file__).resolve()
_ROOT = _THIS.parent.parent
sys.path.insert(0, str(_ROOT))

from canonical_trade_plan import compute_smc_stop_fields  # noqa: E402


def _patch_one(ticker_key: str, entry: dict) -> tuple[bool, dict | None]:
    """Patch a single ticker entry in-place. Returns (changed, smc_fields)."""
    if not isinstance(entry, dict):
        return False, None

    # OB source: prefer t.smc.order_blocks (production schema), fall back to smc_data
    smc = entry.get("smc") or {}
    smc_data = entry.get("smc_data") or {}
    obs = smc.get("order_blocks") or smc_data.get("order_blocks") or []

    tp = entry.get("trade_plan") or {}
    direction = (entry.get("direction") or tp.get("direction") or "long").lower()

    entry_low = tp.get("entry_low") or entry.get("entry_lo")
    entry_high = tp.get("entry_high") or entry.get("entry_hi")
    entry_mid = None
    if entry_low and entry_high:
        try:
            entry_mid = (float(entry_low) + float(entry_high)) / 2.0
        except (TypeError, ValueError):
            entry_mid = None

    legacy_stop = tp.get("stop") or entry.get("stop")
    target1 = tp.get("target1") or entry.get("t1") or entry.get("target1")
    spot = entry.get("price") or tp.get("price")
    fractal_low = entry.get("fractal_low") or tp.get("fractal_low")

    # 2026-05-26 SHIP 2 — sleeve resolution for catalyst suppression.
    # Priority order matches canonical_trade_plan.from_analysis_result:
    # explicit fired-audit > setup_family token.
    sleeve_hint = None
    if isinstance(entry.get("pead_audit"), dict) and entry["pead_audit"].get("fired"):
        sleeve_hint = "pead"
    elif isinstance(entry.get("esp_play_audit"), dict) and entry["esp_play_audit"].get("fired"):
        sleeve_hint = "esp_play"
    elif isinstance(entry.get("insider_cluster_audit"), dict) and entry["insider_cluster_audit"].get("fired"):
        sleeve_hint = "insider_cluster"
    else:
        sleeve_hint = entry.get("setup_family") or tp.get("setup_family") or entry.get("sleeve")

    smc_fields = compute_smc_stop_fields(
        order_blocks=obs,
        direction=direction,
        entry_mid=entry_mid,
        legacy_stop=legacy_stop,
        target1=target1,
        spot=spot,
        fractal_low=fractal_low,
        sleeve=sleeve_hint,
    )

    # ── write into trade_plan dict (UI reads from here) ──
    # Also mirror into top-level for older UI bindings.
    if tp:
        for k, v in smc_fields.items():
            tp[k] = v
        entry["trade_plan"] = tp
    # Mirror top-level for v1/v2 UI bindings that haven't been refactored
    for k, v in smc_fields.items():
        entry[k] = v

    return True, smc_fields


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--path",
        default=str(_ROOT / "infra" / "prototype" / "tickers.json"),
        help="path to tickers.json",
    )
    parser.add_argument(
        "--no-backup", action="store_true", help="skip .bak file"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="report only, do not write"
    )
    parser.add_argument(
        "--ticker", default=None, help="only process this ticker (debug)"
    )
    args = parser.parse_args()

    p = Path(args.path)
    if not p.exists():
        print(f"FATAL: {p} does not exist")
        return 1

    print(f"Loading {p} ...")
    t0 = time.time()
    with open(p) as fh:
        data = json.load(fh)
    print(f"  loaded in {time.time() - t0:.1f}s")

    if not isinstance(data, dict):
        print(f"FATAL: tickers.json is not a dict (got {type(data).__name__})")
        return 1

    if not args.no_backup and not args.dry_run:
        bak = p.with_suffix(f".json.bak.{int(time.time())}")
        print(f"  backing up to {bak.name} ...")
        shutil.copy(p, bak)

    # ── process ──
    counts = {
        "total": 0,
        "processed": 0,
        "had_obs": 0,
        "smc_stop_computed": 0,
        "stop_inside_ob_true": 0,
        "smc_wider_than_legacy": 0,
        "smc_tighter_than_legacy": 0,
        "skipped_no_entry_or_stop": 0,
        # 2026-05-26 SHIP 1 + SHIP 2
        "severity_HIGH": 0,
        "severity_MED": 0,
        "severity_LOW": 0,
        "suppressed_catalyst_sleeve": 0,
        "effective_alerts": 0,  # traps − suppressed
    }
    trap_tickers: list[tuple[str, float, float, str]] = []
    smc_wider: list[tuple[str, float, float]] = []

    for ticker_key, entry in data.items():
        counts["total"] += 1
        if args.ticker and ticker_key.upper() != args.ticker.upper():
            continue

        if not isinstance(entry, dict):
            continue

        smc = entry.get("smc") or {}
        smc_data = entry.get("smc_data") or {}
        had_obs = bool(smc.get("order_blocks") or smc_data.get("order_blocks"))
        if had_obs:
            counts["had_obs"] += 1

        changed, fields = _patch_one(ticker_key, entry)
        if not changed:
            continue
        counts["processed"] += 1

        if fields is None:
            continue
        if fields.get("stop_smc_suggested") is not None:
            counts["smc_stop_computed"] += 1
        if fields.get("stop_inside_ob"):
            counts["stop_inside_ob_true"] += 1
            tp = entry.get("trade_plan") or {}
            legacy = tp.get("stop") or entry.get("stop") or 0
            smc = fields.get("stop_smc_suggested") or 0
            trap_tickers.append(
                (ticker_key, float(legacy), float(smc), fields.get("stop_inside_ob_zone") or "")
            )
            sev = fields.get("stop_inside_ob_severity")
            if sev == "HIGH":  counts["severity_HIGH"] += 1
            elif sev == "MED": counts["severity_MED"] += 1
            elif sev == "LOW": counts["severity_LOW"] += 1
            if fields.get("stop_inside_ob_suppressed"):
                counts["suppressed_catalyst_sleeve"] += 1
            else:
                counts["effective_alerts"] += 1
        # Wider check
        legacy = (entry.get("trade_plan") or {}).get("stop") or entry.get("stop")
        smc = fields.get("stop_smc_suggested")
        if legacy and smc:
            try:
                if float(smc) < float(legacy):
                    counts["smc_wider_than_legacy"] += 1
                    smc_wider.append((ticker_key, float(legacy), float(smc)))
                elif float(smc) > float(legacy):
                    counts["smc_tighter_than_legacy"] += 1
            except (TypeError, ValueError):
                pass

    # ── report ──
    print()
    print("=" * 72)
    print("SMC STOP BACKFILL — SUMMARY")
    print("=" * 72)
    for k, v in counts.items():
        print(f"  {k:<32s} {v}")
    print()
    if trap_tickers:
        print(f"⚠ STOP-INSIDE-OB TRAPS DETECTED: {len(trap_tickers)} tickers")
        print(f"  (legacy stop sits inside an active Bull Order Block — sweep risk)")
        for tkr, legacy, smc_stop, zone in trap_tickers[:25]:
            print(f"    {tkr:<8s}  legacy ${legacy:>7.2f}  →  smc ${smc_stop:>7.2f}  ({zone})")
        if len(trap_tickers) > 25:
            print(f"    ... + {len(trap_tickers) - 25} more")
    else:
        print("✓ No stop-inside-ob traps detected.")
    print()
    if smc_wider:
        print(f"ℹ SMC stop is WIDER than legacy stop for {len(smc_wider)} tickers")
        print(f"  (SMC clears deeper structure than 1.25× ATR)")
        for tkr, legacy, smc_stop in smc_wider[:10]:
            delta_pct = (legacy - smc_stop) / legacy * 100
            print(f"    {tkr:<8s}  legacy ${legacy:>7.2f}  →  smc ${smc_stop:>7.2f}  (−{delta_pct:.1f}%)")
        if len(smc_wider) > 10:
            print(f"    ... + {len(smc_wider) - 10} more")

    # ── write ──
    if not args.dry_run:
        print()
        print(f"Writing patched {p} ...")
        t0 = time.time()
        with open(p, "w") as fh:
            json.dump(data, fh, separators=(",", ":"))
        print(f"  wrote in {time.time() - t0:.1f}s")
    else:
        print()
        print("DRY RUN — no file written.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

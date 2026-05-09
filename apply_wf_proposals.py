"""
apply_wf_proposals.py — turn walk-forward results into config updates.

The walk-forward harness writes cache/wf_multiplier_proposals.json with the
multipliers that passed 3-of-4-fold consensus + test-fold validation. This
script:

  1. Diffs proposed multipliers vs config["setup_score_multiplier"] currents.
  2. Diffs proposed _validations vs config["_validations"].
  3. Shows a colored diff in the terminal (dry-run by default).
  4. With --apply, writes config.json — preserving all other keys.
  5. Backs up config.json to config/config.json.backup-YYYYMMDD-HHMMSS first.

Usage:
    python3 apply_wf_proposals.py            # dry-run preview
    python3 apply_wf_proposals.py --apply    # write changes to config.json
    python3 apply_wf_proposals.py --setups "Trend Continuation,EMA21 Pullback"
                                              # apply only specific setups

Safety:
  - Refuses to apply if proposals are >7 days old (likely stale)
  - Refuses to apply if proposed mult is < 0.50 or > 1.50 (sanity bounds)
  - Always backs up config.json before writing
  - Idempotent: re-running --apply with the same proposals is a no-op
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
PROPOSALS_PATH = ROOT / "cache" / "wf_multiplier_proposals.json"
CONFIG_PATH = ROOT / "config" / "config.json"

# Sanity bounds — refuse to write multipliers outside this range without --force
MIN_MULT = 0.50
MAX_MULT = 1.50
MAX_PROPOSAL_AGE_DAYS = 7


# ANSI colors for terminal diff
class C:
    R = "\033[0m"
    GREEN = "\033[32m"
    RED = "\033[31m"
    YELLOW = "\033[33m"
    CYAN = "\033[36m"
    BOLD = "\033[1m"
    DIM = "\033[2m"


def _color(s: str, c: str) -> str:
    if not sys.stdout.isatty():
        return s
    return f"{c}{s}{C.R}"


def load_proposals() -> dict:
    if not PROPOSALS_PATH.exists():
        return {"error": f"No proposals at {PROPOSALS_PATH}. Run walk_forward_v2.py --tune-multipliers first."}
    try:
        d = json.loads(PROPOSALS_PATH.read_text())
        # Check freshness
        gen = d.get("generated_at")
        if gen:
            try:
                age = datetime.now() - datetime.fromisoformat(gen)
                if age.days > MAX_PROPOSAL_AGE_DAYS:
                    d["_stale_warning"] = f"Proposals are {age.days} days old"
            except Exception:
                pass
        return d
    except Exception as e:
        return {"error": f"Failed to parse {PROPOSALS_PATH}: {e}"}


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text())


def diff_multipliers(current: dict, proposed: dict) -> list[dict]:
    """Per-setup diff. Returns list of {setup, current_mult, proposed_mult, change}."""
    cur_mults = {k: v for k, v in (current.get("setup_score_multiplier") or {}).items()
                 if not k.startswith("_") and isinstance(v, (int, float))}
    out = []
    for setup, prop_mult in (proposed.get("shipped_multipliers") or {}).items():
        if setup.startswith("_"):
            continue
        if not isinstance(prop_mult, (int, float)):
            continue
        cur = cur_mults.get(setup, 1.0)
        out.append({
            "setup": setup,
            "current": cur,
            "proposed": prop_mult,
            "delta": prop_mult - cur,
            "direction": "boost" if prop_mult > cur else ("demote" if prop_mult < cur else "no-op"),
        })
    return sorted(out, key=lambda r: -abs(r["delta"]))


def diff_validations(current: dict, proposed: dict) -> dict:
    """Per-setup _validations diff. Returns dict: {setup: {action: 'add'/'update'/'unchanged', current, proposed}}."""
    cur_v = (current.get("setup_score_multiplier") or {}).get("_validations") or {}
    prop_v = (proposed.get("shipped_multipliers") or {}).get("_validations") or {}
    out = {}
    for setup, prop_entry in prop_v.items():
        cur_entry = cur_v.get(setup)
        if cur_entry is None:
            out[setup] = {"action": "add", "current": None, "proposed": prop_entry}
        elif cur_entry == prop_entry:
            out[setup] = {"action": "unchanged", "current": cur_entry, "proposed": prop_entry}
        else:
            out[setup] = {"action": "update", "current": cur_entry, "proposed": prop_entry}
    return out


def print_diff(mult_diff: list[dict], val_diff: dict, proposals: dict) -> None:
    print()
    print(_color("═══════════════════════════════════════════════════════════════", C.CYAN))
    print(_color(f"  Walk-forward proposals: apply preview", C.BOLD))
    print(_color("═══════════════════════════════════════════════════════════════", C.CYAN))
    gen = proposals.get("generated_at")
    if gen:
        print(f"  Generated: {gen}")
    if "_stale_warning" in proposals:
        print(_color(f"  ⚠ {proposals['_stale_warning']}", C.YELLOW))
    print()

    print(_color("Setup multiplier changes:", C.BOLD))
    if not mult_diff:
        print(_color("  (no shipped multipliers — WF didn't pass 3-of-4-fold consensus on any setup)", C.DIM))
    else:
        print(f"  {'Setup':<28} {'Current':>10} {'Proposed':>12} {'Δ':>10}  Direction")
        print(f"  {'-' * 28} {'-' * 10:>10} {'-' * 12:>12} {'-' * 10:>10}  ---------")
        for d in mult_diff:
            color = C.GREEN if d["direction"] == "boost" else (C.RED if d["direction"] == "demote" else C.DIM)
            arrow = _color(f"{d['delta']:+.3f}", color)
            print(f"  {d['setup']:<28} {d['current']:>10.3f} {d['proposed']:>12.3f} {arrow:>20}  {_color(d['direction'], color)}")

    print()
    print(_color("_validations entries:", C.BOLD))
    if not val_diff:
        print(_color("  (no _validations in proposals)", C.DIM))
    else:
        for setup, info in val_diff.items():
            action = info["action"]
            if action == "unchanged":
                print(f"  {setup:<28}  {_color('unchanged', C.DIM)}")
            elif action == "add":
                p = info["proposed"]
                print(f"  {setup:<28}  {_color('+ ADD', C.GREEN)}  n={p.get('n')} wr_lb={p.get('wr_lb', 0):.3f} source={p.get('source')}")
            elif action == "update":
                c, p = info["current"], info["proposed"]
                print(f"  {setup:<28}  {_color('~ UPDATE', C.YELLOW)}  n={c.get('n')}→{p.get('n')} wr_lb={c.get('wr_lb', 0):.3f}→{p.get('wr_lb', 0):.3f}")

    print()


def validate_proposals(mult_diff: list[dict], proposals: dict) -> list[str]:
    """Return list of error messages. Empty list = safe to apply."""
    errors = []
    for d in mult_diff:
        if d["proposed"] < MIN_MULT or d["proposed"] > MAX_MULT:
            errors.append(f"{d['setup']}: proposed mult {d['proposed']:.3f} outside sanity bounds [{MIN_MULT}, {MAX_MULT}]")
    if "_stale_warning" in proposals:
        errors.append(proposals["_stale_warning"])
    return errors


def apply_changes(current: dict, proposals: dict, setups_filter: set | None) -> dict:
    """Return updated config dict. Caller writes it."""
    new = json.loads(json.dumps(current))  # deep copy
    sm = new.setdefault("setup_score_multiplier", {})

    # Apply multiplier changes
    for setup, mult in (proposals.get("shipped_multipliers") or {}).items():
        if setup.startswith("_"):
            continue
        if setups_filter and setup not in setups_filter:
            continue
        if not isinstance(mult, (int, float)):
            continue
        sm[setup] = round(float(mult), 3)

    # Apply _validations
    val = sm.setdefault("_validations", {})
    prop_val = (proposals.get("shipped_multipliers") or {}).get("_validations") or {}
    for setup, entry in prop_val.items():
        if setups_filter and setup not in setups_filter:
            continue
        val[setup] = entry

    # Update _comment to reflect last apply
    sm["_comment"] = (
        f"Validations populated by apply_wf_proposals.py at {datetime.now().isoformat()} "
        f"from cache/wf_multiplier_proposals.json. Wilson gates in analysis.py:8503 enforce "
        f"n>=30 AND wr_lb<0.30 for any demotion to take effect."
    )

    return new


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="Actually write changes to config.json (default: dry-run preview)")
    parser.add_argument("--setups", default="",
                        help="Comma-separated subset of setups to apply (default: all)")
    parser.add_argument("--force", action="store_true",
                        help="Override sanity bounds (DANGEROUS — bypass [0.5, 1.5] mult range)")
    args = parser.parse_args()

    proposals = load_proposals()
    if "error" in proposals:
        print(_color(f"ERROR: {proposals['error']}", C.RED))
        return 2

    config = load_config()
    mult_diff = diff_multipliers(config, proposals)
    val_diff = diff_validations(config, proposals)
    print_diff(mult_diff, val_diff, proposals)

    errors = validate_proposals(mult_diff, proposals)
    if errors and not args.force:
        print(_color("Refusing to apply (use --force to override):", C.RED))
        for e in errors:
            print(_color(f"  ✗ {e}", C.RED))
        return 1
    elif errors and args.force:
        print(_color("⚠ FORCE MODE — proceeding despite warnings:", C.YELLOW))
        for e in errors:
            print(_color(f"  ! {e}", C.YELLOW))

    if not args.apply:
        print(_color("Dry-run mode. Re-run with --apply to write to config.json.", C.DIM))
        return 0

    if not mult_diff and not any(v["action"] != "unchanged" for v in val_diff.values()):
        print(_color("Nothing to apply (no changes vs current config). Idempotent.", C.DIM))
        return 0

    setups_filter = set(s.strip() for s in args.setups.split(",") if s.strip()) or None
    new_config = apply_changes(config, proposals, setups_filter)

    # Backup
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = CONFIG_PATH.parent / f"config.json.backup-{ts}"
    shutil.copy2(CONFIG_PATH, backup_path)
    print(_color(f"  Backed up config.json → {backup_path.name}", C.CYAN))

    CONFIG_PATH.write_text(json.dumps(new_config, indent=2) + "\n")
    print(_color(f"✓ Wrote {CONFIG_PATH}", C.GREEN))
    print(_color(f"  Run python3 apply_wf_proposals.py to verify (should now show 'idempotent')", C.DIM))

    return 0


if __name__ == "__main__":
    sys.exit(main())

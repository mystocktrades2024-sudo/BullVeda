#!/usr/bin/env python3
"""
build_tier_roles.py — Phase 1 of the Kairos commercial-tier rollout.

Single source of truth for the tier → surface mapping. Running this script:
  1. Injects a `tier` field (0-4) into every entry in
     data/capability_registry.json  (tabs / sub_tabs / actions).
  2. Regenerates 5 CUMULATIVE tier-roles in data/roles.json:
        free(0) ⊂ starter(1) ⊂ core(2) ⊂ pro(3) ⊂ elite(4)
     Each role gets every surface whose tier <= the role's tier.
  3. Leaves the existing OPERATOR roles (admin / trader / viewer / minimum)
     untouched — commercial `plan` is orthogonal to operator `role`
     (effective perms = role ∪ plan; union resolved in auth.py).

Internal / owner-only surfaces (Settings, Users, Roles, System Status, Fields,
and the operator write-actions) get tier = null and are EXCLUDED from every
tier-role — they stay gated to operator roles regardless of what a user pays.

The mapping below is the audit trail (CLAUDE.md principle 7). Reference:
infra/prototype/kairos_tier_mapping.html — the reviewed visual board.

Idempotent. Re-run any time the mapping changes. Pass --dry-run to preview.
"""
from __future__ import annotations
import json, sys, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "data" / "capability_registry.json"
ROLES = ROOT / "data" / "roles.json"

# ── TIER MAP — lowest tier (0=Free … 4=Elite) that unlocks each surface ──
# `None` = internal/operator-only, excluded from the commercial ladder.
TIER = {
    "tabs": {
        # Free (0)
        "scanner": 0, "watchlist": 0, "portfolio": 0, "leaders": 0,
        "playbook": 0, "reference": 0,
        # Starter (1)
        "alerts": 1, "market": 1, "industries": 1, "screener": 1,
        "premarket": 1, "events": 1, "macro": 1, "optionsflow": 1,
        # Core (2)
        "elite": 2, "strategies": 2, "themes": 2, "killed": 2, "earnings": 2,
        "performance": 2, "risklab": 2, "pairs": 2, "leveraged": 2,
        "crypto": 2, "positionAnalysis": 2, "analysis": 2, "thesis": 2,
        # Pro (3)
        "accuracy": 3, "audit": 3, "research": 3,
        # Internal / operator-only
        "status": None, "settings": None, "settings_visibility": None,
        "settings_config": None, "settings_admin": None, "settings_users": None,
        "settings_roles": None, "fields": None,
    },
    "sub_tabs": {
        "overview": 0, "news": 0, "tv": 0,
        "technicals": 1, "sentiment": 1, "options": 1,
        "fundamentals": 2, "plan": 2, "smc": 2, "insider": 2,
        "ruleengine": 2, "ml_edge": 2, "models": 2, "thesis": 2,
        "institutional": 3, "research": 3,
    },
    "actions": {
        "edit_watchlist": 0, "pos_move_to_be": 0, "pos_trail_stop": 0, "pos_close": 0,
        "set_alerts": 1, "approve_alert": 1,
        "edit_sizing": 2, "ai_chat": 2, "edit_thesis": 2, "force_rescan": 2,
        "submit_trade": 3, "trigger_backtest": 3, "export_data": 3, "schwab_reauth": 3,
        # Internal / operator-only
        "edit_config": None, "override_breaker": None, "edit_kill_list": None,
        "edit_users": None, "edit_roles": None, "view_audit_log": None,
    },
}

TIER_ROLES = [
    ("free",    0, "Kairos Free",    "Free tier — basic signals, paper trading, leaderboard.", "#7e8a9e"),
    ("starter", 1, "Tier 1 · Starter", "$19.99/mo — real-time alerts, regime, sector heatmap.",  "#68d391"),
    ("core",    2, "Tier 2 · Core",    "$49.99/mo — full composite intelligence + analytics.",   "#d69e2e"),
    ("pro",     3, "Tier 3 · Pro",     "$149/mo — verified track record, accuracy, live exec.",  "#ed8936"),
    ("elite",   4, "Tier 4 · Elite",   "$330/mo — institutional surfaces (roadmap).",            "#e2e8f0"),
]


def build(dry_run: bool = False) -> None:
    reg = json.loads(REGISTRY.read_text())
    roles_doc = json.loads(ROLES.read_text())

    # 1. inject tier into registry + sanity-check every entry is mapped
    missing = []
    for perm_type in ("tabs", "sub_tabs", "actions"):
        for key, entry in reg.get(perm_type, {}).items():
            if key not in TIER[perm_type]:
                missing.append(f"{perm_type}.{key}")
                continue
            entry["tier"] = TIER[perm_type][key]
    if missing:
        print("ERROR — surfaces in registry not present in TIER map:")
        for m in missing:
            print("   ", m)
        sys.exit(1)

    # 2. build cumulative permission lists per tier
    def surfaces_up_to(perm_type: str, max_tier: int) -> list[str]:
        return sorted(
            k for k, t in TIER[perm_type].items()
            if t is not None and t <= max_tier and k in reg.get(perm_type, {})
        )

    roles_doc.setdefault("roles", {})
    # Base operator role for commercial customers: grants NOTHING on its own, so
    # effective perms come solely from the user's `plan` (tier-role).
    # Convention: a paying customer = role:"customer" + plan:"free|starter|core|pro|elite".
    roles_doc["roles"]["customer"] = {
        "name": "Customer (commercial)",
        "description": "Base role for paying users — all access derives from their plan/tier.",
        "color": "#4a5568",
        "builtin": True,
        "permissions": {"tabs": [], "sub_tabs": [], "actions": []},
    }
    for rid, tier, name, desc, color in TIER_ROLES:
        roles_doc["roles"][rid] = {
            "name": name,
            "description": desc,
            "color": color,
            "builtin": True,
            "tier": tier,
            "permissions": {
                "tabs":     surfaces_up_to("tabs", tier),
                "sub_tabs": surfaces_up_to("sub_tabs", tier),
                "actions":  surfaces_up_to("actions", tier),
            },
        }

    stamp = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    reg.setdefault("_meta", {})["tier_axis_built_at"] = stamp
    roles_doc["_tier_roles_built_at"] = stamp

    # report
    print("Tier-role permission counts (cumulative):")
    for rid, tier, *_ in TIER_ROLES:
        p = roles_doc["roles"][rid]["permissions"]
        print(f"  {rid:8s} (tier {tier}) → tabs {len(p['tabs']):2d} · "
              f"sub_tabs {len(p['sub_tabs']):2d} · actions {len(p['actions']):2d}")
    internal = [f"{pt}.{k}" for pt in TIER for k, v in TIER[pt].items() if v is None]
    print(f"Internal/operator-only (excluded from ladder): {len(internal)} surfaces")

    if dry_run:
        print("\n--dry-run — no files written.")
        return

    REGISTRY.write_text(json.dumps(reg, indent=2) + "\n")
    ROLES.write_text(json.dumps(roles_doc, indent=2) + "\n")
    print(f"\nWrote {REGISTRY.relative_to(ROOT)} + {ROLES.relative_to(ROOT)}")


if __name__ == "__main__":
    build(dry_run="--dry-run" in sys.argv)

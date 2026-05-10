#!/usr/bin/env python3
"""migrate_role_capabilities.py — CapStudio Phase F.

One-time migration: backfill role permissions in data/roles.json from the
master capability registry (data/capability_registry.json). Existing role
permissions are PRESERVED — only missing entries are added so no role gets
narrower access than it had before.

Idempotent: safe to re-run after editing the registry. New functions/tabs added
to the registry will be granted to roles listed in their `default_roles` array,
but never revoke existing grants.

Usage:
    python3 scripts/migrate_role_capabilities.py            # apply
    python3 scripts/migrate_role_capabilities.py --dry-run  # preview only
    python3 scripts/migrate_role_capabilities.py --reset    # nuke + re-seed
                                                              from registry defaults

(2026-05-09 — initial.)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
REG_PATH   = ROOT / "data" / "capability_registry.json"
ROLES_PATH = ROOT / "data" / "roles.json"


def load_json(p: Path) -> dict:
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception as e:
        print(f"  ✗ Failed to parse {p}: {e}", file=sys.stderr)
        return {}


def save_json(p: Path, data: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, sort_keys=False))


def migrate(dry_run: bool = False, reset: bool = False) -> int:
    reg = load_json(REG_PATH)
    if not reg:
        print(f"✗ Registry not found or empty: {REG_PATH}", file=sys.stderr)
        return 1

    roles = load_json(ROLES_PATH)
    if not roles:
        print(f"⚠ Roles file empty/missing — will create fresh: {ROLES_PATH}")
        roles = {"version": 1, "roles": {}}

    # Roles dict can be either flat {role_id: {...}} or wrapped {version, roles: {...}}
    if "roles" in roles and isinstance(roles["roles"], dict):
        roles_by_id = roles["roles"]
        wrapped = True
    else:
        roles_by_id = roles
        wrapped = False

    # Collect every (perm_type, perm_id, default_roles) tuple from the registry
    grants = []
    for perm_type in ("tabs", "sub_tabs", "actions"):
        for perm_id, meta in (reg.get(perm_type) or {}).items():
            grants.append((perm_type, perm_id, meta.get("default_roles") or []))

    print(f"Registry: {len(grants)} total functions across tabs/sub_tabs/actions")
    print(f"Roles    : {len(roles_by_id)} found ({list(roles_by_id.keys())})")
    print()

    changes = []
    for role_id, role in roles_by_id.items():
        perms = role.setdefault("permissions", {})
        for key in ("tabs", "sub_tabs", "actions"):
            perms.setdefault(key, [])

        if reset:
            # Clear and re-seed from registry defaults
            old = {k: list(perms[k]) for k in ("tabs", "sub_tabs", "actions")}
            for k in ("tabs", "sub_tabs", "actions"):
                perms[k] = []
            for perm_type, perm_id, default_roles in grants:
                if role_id in default_roles or "*" in default_roles:
                    if perm_id not in perms[perm_type]:
                        perms[perm_type].append(perm_id)
            for k in ("tabs", "sub_tabs", "actions"):
                added = set(perms[k]) - set(old[k])
                removed = set(old[k]) - set(perms[k])
                if added:    changes.append(f"  {role_id}.{k}: +{sorted(added)}")
                if removed:  changes.append(f"  {role_id}.{k}: -{sorted(removed)}")
        else:
            # Additive: only ADD missing defaults
            for perm_type, perm_id, default_roles in grants:
                if role_id in default_roles and perm_id not in perms[perm_type]:
                    perms[perm_type].append(perm_id)
                    changes.append(f"  {role_id}.{perm_type}: +{perm_id}")

    if not changes:
        print("✓ No changes needed — all roles already have their default capabilities.")
        return 0

    print(f"{'DRY-RUN — not writing.' if dry_run else 'Applying'} {len(changes)} change(s):")
    for c in changes:
        print(c)

    if dry_run:
        return 0

    # Stamp metadata
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if wrapped:
        roles["_capstudio_migrated_at"] = now
        roles["_capstudio_migration"] = "reset" if reset else "additive"
        out = roles
    else:
        out = {"version": 1, "_capstudio_migrated_at": now,
               "_capstudio_migration": "reset" if reset else "additive",
               "roles": roles_by_id}

    save_json(ROLES_PATH, out)
    print(f"\n✓ Wrote {ROLES_PATH}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="Print changes without writing")
    ap.add_argument("--reset",   action="store_true", help="Clear all role perms and re-seed from registry defaults (DESTRUCTIVE)")
    args = ap.parse_args()
    return migrate(dry_run=args.dry_run, reset=args.reset)


if __name__ == "__main__":
    sys.exit(main())

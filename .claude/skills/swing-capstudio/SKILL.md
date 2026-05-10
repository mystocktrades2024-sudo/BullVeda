---
name: swing-capstudio
description: CapStudio — RBAC matrix system. Manages role × function permissions across 60+ tabs/sub-tabs/actions in the V2 dashboard. Use when adding new functions to the registry, debugging permission denials, or wiring new gates.
---

# CapStudio — Capabilities Studio

The single source of truth for function-level RBAC. Admins assign which roles get which functions via a matrix UI in Settings → CapStudio.

## Architecture

```
data/capability_registry.json          ← master function list (data only, edited by hand)
data/roles.json                         ← per-role grants (managed by UI; edit via PATCH /api/roles/:id)
auth.py user_has_permission(u, t, p)    ← server-side gate (supports tabs/sub_tabs/actions)
/api/me                                 ← returns user's tabs_allowed/sub_tabs_allowed/actions_allowed
/api/capability-registry                ← read-only registry, consumed by matrix UI
/api/roles, /api/roles/{id}             ← CRUD on role definitions (admin-only)
infra/prototype/settings_capstudio.html ← matrix UI (iframe in Settings → CapStudio)
scripts/migrate_role_capabilities.py    ← idempotent backfill of registry defaults into roles.json
```

## How to add a new gateable function

1. Edit `data/capability_registry.json` — add an entry under `tabs`, `sub_tabs`, or `actions`:
   ```json
   "my_new_action": {"label": "My New Action", "category": "trading", "default_roles": ["admin","trader"]}
   ```
2. Run `python3 scripts/migrate_role_capabilities.py` — backfills the new entry to roles.json with default grants
3. Wire the gate in your code:
   - **Tab**: `_applyVisibility()` reads `tabs_allowed` automatically
   - **Sub-tab**: `fdSwitchTab()` checks `sub_tabs_allowed` automatically
   - **Action**: wrap the click handler: `if (!window.capHasAction('my_new_action')) return;`
4. Refresh dashboard — admin sees new row in CapStudio matrix immediately

## Common scenarios

- **"User says 'no permission'"** → check `data/roles.json`. Their role's `permissions.{tabs,sub_tabs,actions}` arrays list what they can access. `*` = wildcard (everything).
- **"Admin can see things they shouldn't"** → admin role likely has `["*"]` in one of the perm arrays. That's by design (admins always have full access). Remove the `*` to make admin gating respect specific grants.
- **"New tab not showing in matrix"** → re-fetch `/api/capability-registry` (the matrix UI cache the response on load). Hard-refresh in the iframe.
- **"Saved changes didn't persist"** → check `_save_roles()` write succeeded in server logs. Check file perms on `data/roles.json`.
- **"Sub-tabs missing from elite-detail"** → `fdSwitchTab` blocks based on `sub_tabs_allowed`. Check `/api/me` response for the user.

## Reset to defaults
```
python3 scripts/migrate_role_capabilities.py --reset
```
Clears all role grants and re-seeds from `default_roles` in the registry. Existing custom grants are LOST.

## Audit
Currently no audit log on role permission changes. To add: hook `/api/roles/{id}` PATCH endpoint with an audit-log entry to `cache/audit_log.jsonl`.

## Phase E (deferred)
The original ask was "modular per function." Phases A-D + F build the gating + admin UI + module-path manifest in the registry. **Phase E** (per-function code extraction — moving each renderXxx body into its own .js file) is multi-day work, deferred. The 8 dashboard tabs already extracted in the prior modularization (Portfolio, OptionsFlow, Audit, Earnings, Strategies, Playbook, Elite, Performance) live in `infra/prototype/tabs/<tab>/<tab>.js` but are NOT yet wired (the prior wiring was reverted after the broken render bug). 15 elite-detail sub-tabs + 22 remaining dashboard tabs still inline in the HTML.

Per-function modularization plan:
1. Each function gets a JS file at the path in `capability_registry.json[*][id].module`
2. Module exports `{render(), dispose?(), id}`
3. Module's `render()` first checks `window.capHas{Tab,SubTab,Action}(id)` — gate at module boundary
4. Shell installs override in `window.TAB_RENDERERS[id]` or `FD_TAB_MAP_RENDERERS[id]`
5. Browser-test after EACH extraction (lesson learned from prior batch-delete failure)

# Section-Level Role Gating · Architecture

**Status:** Design doc · 2026-05-13 · pending Phase 2 implementation
**Owner:** UI architecture
**Related:** `data/capability_registry.json` · `settings_capstudio.html` · `subtabs/*/`

---

## Problem statement

Today: CapStudio gates at the **tab** level. A role either sees the Options tab or doesn't.

Needed: gate at the **section within a tab** level. Examples:
- Free user · Options tab visible · but **STRATEGY MATRIX** + **PAYOFF DIAGRAMS** + **3D VOL SURFACE** hidden
- Trader-pro · all of the above hidden EXCEPT **STRATEGY MATRIX** visible
- Quant · all visible EXCEPT **3D VOL SURFACE**
- Admin · all visible
- Per-user override: a quant who doesn't want IV Smile can hide it personally without affecting other quants

This applies across all tabs (Value · Risk · ER Lab · Portfolio · Macro · News · Insider · Options · etc.) and needs to scale as we add sections.

---

## Design overview

Three layers · each enforces visibility independently · defense in depth:

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 1 · capability_registry.json                          │
│   - declarative · single source of truth                    │
│   - sections list per tab, with role requirements per section│
│   - admin edits via CapStudio UI                            │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 2 · Frontend (kairos.html · subtab modules)           │
│   - read registry on page load                              │
│   - render only sections allowed for user's role            │
│   - hidden sections never appear in DOM                     │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 3 · Backend (server.py endpoints)                     │
│   - each section's data endpoint checks role                │
│   - returns 403 for unauthorized sections                   │
│   - cannot be bypassed by editing JS                        │
└─────────────────────────────────────────────────────────────┘
```

---

## Schema · capability_registry.json extension

Current schema (tab-only):
```json
{
  "roles": ["admin", "quant", "trader", "viewer"],
  "tabs": {
    "options": ["admin", "quant", "trader"],
    "value": ["admin", "quant", "trader", "viewer"]
  }
}
```

Extended schema (tab + sections):
```json
{
  "roles": ["admin", "quant", "trader_pro", "trader", "viewer", "free"],
  "tabs": {
    "options": {
      "default_roles": ["admin", "quant", "trader_pro", "trader", "free"],
      "sections": {
        "iv_smile": {
          "label": "IV Smile · vol surface",
          "roles": ["all"],
          "default_visible": true
        },
        "max_pain": {
          "label": "Max Pain · OI concentration",
          "roles": ["all"],
          "default_visible": true
        },
        "uoa_flow": {
          "label": "Unusual Options Activity",
          "roles": ["trader", "trader_pro", "quant", "admin"],
          "default_visible": true
        },
        "strategy_matrix": {
          "label": "Strategy Matrix · Greeks · POP · BE · margin",
          "roles": ["trader_pro", "quant", "admin"],
          "default_visible": true,
          "premium": true
        },
        "payoff_diagrams": {
          "label": "Payoff Diagrams · visual P&L curves",
          "roles": ["admin"],
          "default_visible": true,
          "premium": true
        },
        "term_structure": {
          "label": "Vol Term Structure",
          "roles": ["quant", "admin"],
          "default_visible": true
        },
        "skew_3d": {
          "label": "3D Volatility Surface",
          "roles": ["admin"],
          "default_visible": true,
          "premium": true,
          "experimental": true
        }
      }
    }
  }
}
```

Field reference:
- `default_roles` — who sees the tab at all
- `sections.{id}.roles` — array of role names; `"all"` means everyone with tab access
- `sections.{id}.default_visible` — default state when role allows it (user can override)
- `sections.{id}.premium` — flag for paid-tier features (cosmetic / billing hint)
- `sections.{id}.experimental` — flag for beta features (warning UI)

---

## Frontend pattern

Each tab's render function consults the registry:

```js
// subtabs/options/index.js (or inline in kairos.html)
function renderOptionsTab(t) {
  const userRole = window.__userRole;           // set by /api/me on auth
  const userPrefs = window.__userPrefs || {};    // personal overrides per user
  const registry = window.__capRegistry;        // loaded once on page load
  const cfg = registry.tabs.options;

  const sections = Object.entries(cfg.sections);
  let html = '<div class="qopt-root">';

  for (const [sectionId, sectionCfg] of sections) {
    // Layer-1 filter: registry role check
    const roleAllowed = sectionCfg.roles.includes('all')
                     || sectionCfg.roles.includes(userRole);
    if (!roleAllowed) continue;

    // Layer-2 filter: per-user preference (opt-out)
    const userHidden = userPrefs.hidden_sections?.[`options.${sectionId}`];
    if (userHidden) continue;

    // Layer-3 render: dispatch to section function
    html += renderSection_options(sectionId, t);
  }

  return html + '</div>';
}

function renderSection_options(id, t) {
  switch(id) {
    case 'iv_smile':         return renderOpt_IVSmile(t);
    case 'max_pain':         return renderOpt_MaxPain(t);
    case 'uoa_flow':         return renderOpt_UOAFlow(t);
    case 'strategy_matrix':  return renderOpt_StrategyMatrix(t);
    case 'payoff_diagrams':  return renderOpt_PayoffDiagrams(t);
    case 'term_structure':   return renderOpt_TermStructure(t);
    case 'skew_3d':          return renderOpt_Skew3D(t);
    default:                 return '';
  }
}
```

### Naming convention

```
renderXxxTab(t)                        — top-level tab render function
  ↓
renderSection_xxx(sectionId, t)        — dispatcher (called once per visible section)
  ↓
renderXxx_<section_name>(t)            — individual section renderer (one per section)
```

Example for the Risk tab:
```
renderRiskTab(t)
  → renderSection_risk('var', t)            → renderRisk_VaR(t)
  → renderSection_risk('drawdown', t)       → renderRisk_Drawdown(t)
  → renderSection_risk('kelly', t)          → renderRisk_Kelly(t)
  → renderSection_risk('tail_risk', t)      → renderRisk_TailRisk(t)
  → ...
```

---

## Backend enforcement

Each section that has its own data endpoint MUST also enforce role on the server side:

```python
# server.py
from auth import current_user_role, can_see_section

@app.get("/api/options/strategy_matrix/{ticker}")
async def options_strategy_matrix(ticker: str, user=Depends(_check_auth)):
    if not can_see_section(current_user_role(user), "options.strategy_matrix"):
        raise HTTPException(403, "Section not available for your role")
    return _compute_strategy_matrix(ticker)


@app.get("/api/options/payoff_diagrams/{ticker}")
async def options_payoff(ticker: str, user=Depends(_check_auth)):
    if not can_see_section(current_user_role(user), "options.payoff_diagrams"):
        raise HTTPException(403, "Section not available for your role")
    return _compute_payoffs(ticker)
```

Helper:
```python
# auth.py
import json
from pathlib import Path

_REGISTRY = json.load(open(Path("data/capability_registry.json")))

def can_see_section(role: str, section_path: str) -> bool:
    """section_path format: 'tab.section_id', e.g. 'options.strategy_matrix'"""
    tab_id, section_id = section_path.split(".", 1)
    tab_cfg = _REGISTRY["tabs"].get(tab_id, {})
    section_cfg = tab_cfg.get("sections", {}).get(section_id, {})
    allowed = section_cfg.get("roles", [])
    return role in allowed or "all" in allowed
```

This means even if a malicious user edits the JS to remove the frontend check, the backend refuses to send the data.

---

## CapStudio admin UI extension

Current CapStudio UI shows a tab × role matrix (rows = tabs, columns = roles, cells = checkbox).

Extended UI: expandable tab rows. Click a tab → see its sections. Toggle each section per role.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ TAB                  │ free   │ trader  │ trader-pro │ quant   │ admin   │
├──────────────────────┼────────┼─────────┼────────────┼─────────┼─────────┤
│ ▶ Options            │   ✓    │   ✓     │     ✓      │   ✓     │   ✓     │
│ ▼ Options (expanded) │        │         │            │         │         │
│   ├ IV Smile         │   ✓    │   ✓     │     ✓      │   ✓     │   ✓     │
│   ├ Max Pain         │   ✓    │   ✓     │     ✓      │   ✓     │   ✓     │
│   ├ UOA Flow         │        │   ✓     │     ✓      │   ✓     │   ✓     │
│   ├ Strategy Matrix  │        │         │     ✓      │   ✓     │   ✓     │
│   ├ Payoff Diagrams  │        │         │            │         │   ✓     │
│   ├ Term Structure   │        │         │            │   ✓     │   ✓     │
│   └ 3D Vol Surface   │        │         │            │         │   ✓     │
│ ▶ Value Lab          │   ✓    │   ✓     │     ✓      │   ✓     │   ✓     │
│ ▶ Risk Lab           │        │   ✓     │     ✓      │   ✓     │   ✓     │
│ ...                  │        │         │            │         │         │
└──────────────────────────────────────────────────────────────────────────┘
```

Each cell is a checkbox. Click → updates `capability_registry.json` server-side. Page reload for affected users picks up new permissions.

---

## Per-user overrides

Layer on top of role-based defaults: each user can hide sections they personally don't want to see.

Storage: `data/users/{username}_preferences.json`
```json
{
  "hidden_sections": {
    "options.iv_smile": true,
    "value.dcf_sensitivity": true
  }
}
```

UI: each section has a small ⨯ button (visible only to logged-in users) that adds the section to the hidden list. A "Show hidden" toggle in user settings restores them.

This gives users curation power without admin involvement.

---

## Migration plan · in order

| Phase | What | Effort |
|---|---|---|
| **1** | Document architecture (this doc) | done |
| **2** | Build prototype demonstrating the pattern (1 tab · 7 sections · role switcher) | 0.5 day |
| **3** | Extend `capability_registry.json` schema · add `sections` per tab | 1 day |
| **4** | Port 1 priority tab inline (e.g., Options) from iframe to native using section dispatcher pattern | 2-3 days |
| **5** | Extend CapStudio UI for section-level toggles (expandable rows per tab) | 2 days |
| **6** | Backend enforcement helper (`can_see_section(role, path)`) + apply to existing endpoints | 1-2 days |
| **7** | Port remaining tabs (Risk · ER Lab · Portfolio · Macro · News · Insider · Value) one at a time | 1 day each = 7 days |
| **8** | Per-user preferences layer | 2 days |

Total: ~3-4 weeks of focused work to convert the iframe-wired tabs to native + add section gating.

---

## Why not React / Vue / Web Components?

The codebase has chosen vanilla JS + ESM modules for `subtabs/`. The existing pattern (Overview V2 / SMC) demonstrates it works at scale. Switching frameworks would mean rewriting everything · disproportionate cost.

Web Components could provide better encapsulation in a future v3, but isn't required for section gating. The dispatcher pattern is framework-agnostic.

---

## Decision checklist · for new tabs going forward

When adding a new tab or section:

- [ ] Define section in `capability_registry.json` with role requirements
- [ ] Implement `renderXxx_<section>(t)` function
- [ ] Wire into `renderSection_xxx(id, t)` dispatcher
- [ ] If section has its own API endpoint: add server-side `can_see_section` check
- [ ] CapStudio UI auto-picks up new section from registry
- [ ] Add to migration plan if section requires backend data not yet available

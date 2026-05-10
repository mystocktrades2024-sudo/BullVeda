# 📋 SwingTrade — Open Item Tracker

> **Last updated:** 2026-05-09 (PT)
> **Update cadence:** every working session — mark `✅ done`, `🔄 in progress`, `⏸ blocked`, `🟡 pending` (with priority), `❌ won't do` (with reason)
> **Single source of truth.** When in doubt, this file wins over conversation memory.

---

## 🟢 Status snapshot

| Stream | Health | Notes |
|--------|--------|-------|
| **Modularization (V2 dashboard)** | ✅ shipped | -42% line count, 60+ ES modules, all wired |
| **CapStudio (RBAC)** | ✅ shipped | 35 tabs + 15 subtabs + 20 actions gated end-to-end |
| **Test coverage** | ✅ working | Python smoke + Playwright no-auth pass; auth tests need `SWING_USER`/`SWING_PASS` |
| **Quant / backtest** | 🟡 work in progress | 750-day shows PF 0.70 — alpha work needed |
| **Mobile** | ⏸ desktop-only | Phase-0 viewport added, full mobile work deferred |
| **Live operations** | ✅ healthy | 18 launchd cron jobs running |

---

## 🔄 In progress

| ID | Item | Owner | Notes |
|----|------|-------|-------|
| P13 | Playwright suite + pixel-diff baseline | Claude | Tests written + Chromium installed. No-auth tests pass. Auth tests need `SWING_USER` + `SWING_PASS` env vars to run end-to-end. |

---

## 🟡 Pending — modularization polish

| ID | Item | Effort | Priority | Notes |
|----|------|--------|----------|-------|
| MOD-1 | **Scanner deep refactor** | 1-2 hrs | low | 6 mutable `let` state vars + 12 helpers + 20+ inline call-sites. Saves ~250 lines. Currently a documented exception — Scanner works perfectly inline. Skip unless symmetry matters. |
| MOD-2 | **Pixel-diff regression** | 2-3 hrs | medium | Build on Playwright. Baseline screenshots per tab + sub-tab. Fails on visual delta. |
| MOD-3 | **Auth-required Playwright tests** | 5 min | medium | Tests are written; just need creds via env. `SWING_USER=foo SWING_PASS=bar npx playwright test`. Once we run them clean, capture as the baseline. |

---

## 🟡 Pending — performance (initial-load brainstorm)

| ID | Item | Effort | Estimated win | Priority |
|----|------|--------|---------------|----------|
| ~~PERF-1~~ | ~~Add `performance.mark()` perf marks + `?perf=1` URL flag → console table~~ ✅ DONE 2026-05-09 — both `dashboard.html` and `elite-detail.html` instrumented; `window.__perfReport(true)` works any time | done | done | done |
| PERF-2 | **Defer Plotly.js** in elite-detail (only load on first chart) | 1 hr | -500ms cold per-ticker | high |
| PERF-3 | **Lazy-render elite-detail sub-tabs** (only active, not all 25 at init) | 2 hrs | -300-500ms first-paint | high |
| PERF-4 | **Brotli compression** (currently Gzip) | 30 min | -15% transfer | medium |
| PERF-5 | **`requestIdleCallback` for `_capScanAndDisableButtons`** | 15 min | -50ms FCP | low |
| PERF-6 | **Critical CSS extraction** (split 775-line `<style>` to above-fold + lazy) | 1 hr | -100ms FCP | medium |
| PERF-7 | **Split data.json** into `data-critical.json` + `data-deferred.json` | 4 hrs | -300-800ms first-paint | medium |
| PERF-8 | **Service worker** for static asset cache | 4 hrs | -200ms repeat-visit | low (only worth it for repeat use) |
| PERF-9 | **Web worker offload** for factor heatmap + cross-mode exposure | 4 hrs | -50-100ms responsiveness | low |
| PERF-10 | **HTTP/2 server push** for `core/shell.js` + `data.json` | 2 hrs | -100ms first-paint | low |
| PERF-11 | **Skeleton screens** during data load | 6 hrs | perceptual win | medium |
| PERF-12 | **Stream data.json (NDJSON)** for big tables | 1-2 days | dramatic TTI win for Audit/Performance | low (only worth it if scrolling >5k rows) |
| PERF-13 | **SSR or pre-rendered HTML** | multi-day | eliminates initial fetch | low (architectural shift) |

**My top 3:** PERF-1 (measure first) → PERF-2 (Plotly defer) → PERF-3 (lazy subtabs).

---

## 🟡 Pending — quant / backtest

| ID | Item | Effort | Priority |
|----|------|--------|----------|
| QUANT-1 | **Act on 750-day backtest findings** — system PF 0.70 | days | high (real P&L impact) |
| QUANT-2 | **Cap Trend Continuation share** in scoring | 1-2 hrs | high |
| QUANT-3 | **Score-band filters** (e.g., min 70 in choppy regime) | 2-4 hrs | medium |
| QUANT-4 | **Walk-forward fold persistence** (Supabase dual-write for `walk_forward_folds`) | 1 hr | low |
| QUANT-5 | **Mover predictor v3** — NLP earnings tone, options flow features | days | research bet |
| QUANT-6 | **Regime-conditional entries** (rule changes per regime band) | 4-6 hrs | medium |

---

## 🟡 Pending — mobile

| ID | Item | Effort | Priority |
|----|------|--------|----------|
| MOB-0 | ✅ DONE 2026-05-09 — viewport meta added to dashboard.html + elite-detail.html | — | — |
| MOB-1 | **Tablet portrait (≥768px)** — hamburger sidebar, 2-up tile grid, larger tap targets | 4-6 hrs | low (only if tablet usage) |
| MOB-2 | **Phone (≤480px)** — single column, bottom nav, card-based tables | 8-12 hrs | low (only if phone becomes core) |

See `tests/MOBILE_REVIEW.md` for the full audit.

---

## 🟡 Pending — operational hygiene

| ID | Item | Effort | Notes |
|----|------|--------|-------|
| OPS-1 | **Snapshot cleanup** | 2 min | Run `scripts/cleanup_after_2026_05_16.sh` after one week of stable production. |
| OPS-2 | **Uptime monitoring** | 1-2 hrs | Beyond `tunnel-healthcheck`. Could be a launchd ping every 5 min posting to a dashboard. |
| OPS-3 | **Admin endpoint for registry edits** | 2-3 hrs | Currently `data/capability_registry.json` requires manual edit + migrate-script run. Could expose `POST /api/capability-registry/items` for in-UI add/remove. |
| OPS-4 | **CapStudio audit log UI** | 2 hrs | `data/audit_log.jsonl` is captured but no UI to view. Could add a Settings → Audit Log sub-tab. |
| OPS-5 | **Reduce backtest report stale window** | 5 min | Already auto-regens after each backtest. Could add a manual "regen" button in Settings → Admin. |
| OPS-6 | **EODHD WebSocket re-enable** | n/a | Silenced (REST polling). Re-enable via `?ws=1` if you ever subscribe to the WS add-on. |

---

## 🟡 Pending — Phase-2 audit (from earlier session)

| ID | Item | Effort | Notes |
|----|------|--------|-------|
| LEGACY-1 | **Phase 2: Audit borderline dead code** (Task #5) | days | Originally tagged for review after Phase 1 cleanup. Probably moot now post-modularization. Re-audit in 2 weeks. |

---

## ✅ Recently completed (current session)

| Date | ID | Item |
|------|----|------|
| 2026-05-09 | PERF-1 | Boot-timing instrumentation: dashboard + elite-detail + shell + detail-shell. `window.__perfReport(true)` dumps 3-section console.table any time. |
| 2026-05-09 | P13 | Playwright suite (3 spec files) + no-auth route test (passes) |
| 2026-05-09 | P12 | Audit log on PATCH /api/roles + lazy-load metering + action gating UX |
| 2026-05-09 | P11 | Fix elite-detail T accessor naming + render-all-after-T-ready |
| 2026-05-09 | P10 | Fix orphan _startAuditPolling() top-level call |
| 2026-05-09 | P9 | Fix orphan window.X assignments + actions.js octal escape |
| 2026-05-09 | P8 | Sub-helpers fold (26 helpers → modules, 526 lines saved) |
| 2026-05-09 | P7 | Action gating + 35 CLAUDE.md files batch-generated |
| 2026-05-09 | P6 | Extract action handlers to core/actions.js (514 lines saved) |
| 2026-05-09 | P5 | Delete inline bodies in elite-detail.html (4,761 lines saved) |
| 2026-05-09 | P4 | Wire elite-detail subtab modules |
| 2026-05-09 | P3 | 29 tabs wired + 25 subtabs created |
| 2026-05-09 | P2 | Delete inline bodies of 8 modular tabs |
| 2026-05-09 | P1 | Registry-driven Playbook PoC |
| 2026-05-09 | CS-A..F | CapStudio: registry + auth + matrix UI + enforcement + migration script |
| 2026-05-09 | MOB-0 | Viewport meta added to both HTML pages |
| 2026-05-09 | OPS-bt | Backtest report 404 fixed (regenerated cache file) |

---

## 📊 Final scoreboard (this session)

```
                       BEFORE     AFTER      REDUCTION
dashboard.html         10,328     5,920      -4,408 (-43%)
elite-detail.html      11,259     6,547      -4,712 (-41%)
COMBINED               21,587     12,467     -9,120 (-42%)
```

| Layer | Count |
|-------|-------|
| **Core ES modules** | 6 (shell, shared, drawer, actions, widgets, elite-detail-shell) |
| **Tab modules** | 29 (28 wired + Scanner inline exception) |
| **Subtab modules** | 25 (all wired) |
| **TOTAL ES modules** | 60 |
| **Skills** | 44 |
| **Specialist agents** | 44 |
| **Per-folder CLAUDE.md** | 44 |
| **Smoke test** | `scripts/smoke_test_modules.py` — 8 sections, all passing |
| **Playwright suite** | 4 spec files (1 no-auth passing, 3 auth-required ready) |

---

## How to use this file

- **Add an item**: under the right section, give it an ID like `PERF-14`, set status (`🟡 pending` / `🔄 in progress` / `⏸ blocked`), effort estimate, priority.
- **Update on each change**: bump "Last updated" at top, move items between sections (`Pending` → `In progress` → `Recently completed`).
- **Stale items**: anything pending >2 weeks should get re-evaluated — either downgrade priority or `❌ won't do` with reason.
- **Reference from skills**: per-folder `CLAUDE.md` and `.claude/skills/swing-*/SKILL.md` files reference items by ID (e.g., "see OpenItemTracker PERF-2").

---

*Generated by the modular-loader session of 2026-05-09. Update freely.*

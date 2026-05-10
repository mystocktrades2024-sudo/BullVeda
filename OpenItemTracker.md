# 📋 SwingTrade — Open Item Tracker

> **Last updated:** 2026-05-10 (overnight perf + modularization + quant session)
> **Canonical registry:** `data/open_items.json` (script-driven; this MD is the human-readable companion)
> **Update cadence:** every working session — mark `✅ done`, `🔄 in progress`, `⏸ blocked`, `🟡 pending` (with priority), `❌ won't do` (with reason)

---

## 🟢 Status snapshot

| Stream | Health | Notes |
|--------|--------|-------|
| **Modularization (V2 dashboard)** | ✅ deeper split done | Phase A (5 main tabs → 28 sub-files) + Phase B (5 subtabs → 17 sub-files) + Scanner module activated (MOD-1). 92 module .js files across 45 folders, 1:1 agentic mapping. |
| **Boot performance** | ✅ 91% reduction | data.json 5.29 MB → critical 462 KB (PERF-7 + PERF-7b). Inline CSS 1029 → 734 lines (PERF-6). |
| **CapStudio (RBAC)** | ✅ shipped | 35 tabs + 15 subtabs + 20 actions gated end-to-end |
| **Test coverage** | ✅ scaffold + smoke | Playwright scaffold + smoke spec shipped (MOD-2 in progress); pixel-diff baseline pending CI integration |
| **Quant / backtest** | 🟡 verification pending | Q1-step5 250d FAILED (0 BUYs). Variant F regime-conditional TC kill awaiting 250d verification. Q1-step6 buy_max_score:90 cap shipped with explicit override (n=19 noise risk acknowledged). |
| **Mobile / iPad** | ✅ split-view PWA | iPad shell shipped (IPAD-1) — list+iframe-detail, PWA-installable, iframe-aware sidebar hide |
| **Live operations** | ✅ healthy | 18 launchd cron jobs running |

---

## 🔄 In progress (1)

| ID | Item | Owner | Notes |
|----|------|-------|-------|
| MOD-2 | Pixel-diff regression baseline | Claude | Playwright scaffold + smoke spec shipped (commit `5df6b9ef8`). Full baseline (capture all 30 tab screenshots, store in `tests/baseline/`, regression-check each PR) still pending — needs CI integration. |

---

## 🟡 Still pending (5)

| ID | Priority | Item | Why blocked |
|----|----------|------|-------------|
| QUANT-3 | P1 | Score-band filters per regime (e.g., min 70 in choppy) | Needs n≥30 backtest evidence (Principle 1) |
| QUANT-5 | P1 | Mover predictor v3 — NLP earnings tone + options flow features | Multi-day ML research, not a slam-dunk |
| QUANT-6 | P1 | Regime-conditional entries (rules vary per regime) | Needs backtest validation per regime |
| OPS-1   | P1 | Snapshot cleanup script (`scripts/cleanup_after_2026_05_16.sh`) | Date-gated to 2026-05-16 |
| CLEAN-4 | P2 | `scripts/migrate_role_capabilities.py` cleanup | Date-gated to 2026-05-16 |

---

## ✅ Shipped 2026-05-10 (this session — 14 items)

| ID | Item | Commit |
|----|------|--------|
| **PERF-7**       | data.json 5.29 MB → 1.55 MB critical (Phase 1, 5 lazy chunks) | `114646f23` |
| **PERF-6**       | Below-fold CSS extracted (Audit/Accuracy/Settings/mobile media queries) | `450572d28` |
| **PERF-7b**      | Critical 1.55 MB → 462 KB (Phase 2: lazy mt/lt + misc) — **91% boot reduction** | `cf30df858` |
| **MOD-A** (×5)   | Phase A: split 5 main tabs into 28 sub-modules (performance/audit/elite/earnings/strategies) | `9517bbbe9` … `7229d4ccb` |
| **MOD-B** (×5)   | Phase B: split 5 elite-detail subtabs into 17 sub-modules (ruleengine/smc/insider/options/sentiment) | `18ef1002e` … `388c316c4` |
| **MOD-1**        | Scanner module activated (`tabs/scanner/scanner.js`) + 5-file deep split | `42c36ef91` |
| **Q1-step6**     | `buy_max_score: 90` cap across 3 active regimes (override-shipped, verification pending) | `f47958fc9` |
| **VAR-F**        | Variant F: regime-conditional Trend Continuation kill (bull regime only) | `f0a66543e + 363984181` |
| **B3-WEEKLY-FIX**| Backtest now builds `weekly_df` from daily for `weekly_bull` gate | `985cd182b` |
| **PERF-OPT**     | Backtest 4× speedup (PERF-OPT-1..4: parallel OHLCV, fund memo, regime precompute) | `94c0c5a01` |
| **RULE-8GATE**   | 8-gate decision-engine cascade visualization in Why-this-is-X tab | `40f8452b8` |
| **IPAD-1**       | iPad split-view PWA shell + iframe-aware detail page | `4b49cb93e + b0e5ef6a1 + 79fa01a75` |

**Bug fixes folded in along the way** (5 latent ReferenceErrors caught during the MOD-A/B splits): audit `DATA` bare ref, smc/options/sentiment bare-`$`, sentiment `_renderShortPressureCard` guard, scanner `FS_STATE` let-binding fix, ruleengine pipeline 8-gate cascade was already broken in extraction. All fixed in their respective MOD commits.

---

## ❌ Failed acceptance / reverted

| ID | Item | Outcome |
|----|------|---------|
| Q1-step5 | 250d backtest after Q1 multipliers + thresholds | **FAILED** — 0 BUYs across 3+ simulated months. Sibling commit `a18282d28` logged the failure. Recovery path = Variant F (above). |

---

## 🟡 Pending — performance (initial-load brainstorm)

| ID | Item | Effort | Estimated win | Priority |
|----|------|--------|---------------|----------|
| ~~PERF-1~~ | ~~Add `performance.mark()` perf marks~~ ✅ DONE 2026-05-09 | done | done | done |
| ~~PERF-1a~~ | ~~Promise.all drawer/widgets/actions in shell.js~~ ✅ DONE 2026-05-09 PM | done | -317ms | done |
| ~~PERF-1b~~ | ~~Combined `/api/v2-bootstrap` endpoint~~ ✅ DONE 2026-05-09 PM | done | -341ms | done |
| ~~PERF-1c~~ | ~~`<link rel="preload">` for critical fetches~~ ✅ DONE 2026-05-09 PM | done | -134ms shell-loader | done |
| ~~PERF-1d~~ | ~~Preload + credentials mode match for data/tickers JSON~~ ✅ DONE 2026-05-09 PM | done | -62ms init | done |
| ~~PERF-2~~ | ~~Defer Plotly.js~~ ✅ DONE 2026-05-09 PM (3.5MB CDN no longer blocks parse) | done | done | done |
| ~~PERF-2b~~ | ~~Parallel data.json/tickers.json fetch in elite-detail init()~~ ✅ DONE 2026-05-09 PM | done | done | done |
| ~~PERF-3~~ | ~~Lazy-render elite-detail sub-tabs~~ ✅ DONE 2026-05-09 PM | done | done | done |
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
| ~~QUANT-1 (Fix 1+3)~~ | ~~Kill Trend Continuation + restore VCP Breakout~~ ✅ SHIPPED 2026-05-09 PM, validation backtest running (PID 25081, ETA ~60min) | done | — |
| QUANT-1b | **Fix 2: add `buy_max_score: 80` cap** — held conditional on Fix 1+3 backtest validation | 30 min | conditional on backtest result |
| ~~QUANT-2~~ | ~~Cap Trend Continuation share~~ — MOOTED by QUANT-1 Fix 1 (killed entirely) | done | — |
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
| 2026-05-09 PM | QUANT-1 (Fix 1+3) | Killed Trend Continuation (multiplier 0.7→0.0 + static_setup_kill_list dict entry: n=264, wr_lb=0.195). Restored VCP Breakout (0.0→1.2). Validation backtest running (PID 25081). Fix 2 (buy_max_score=80) HELD pending validation. |
| 2026-05-09 PM | Elite Picks v2 | Full redesign — hero band (top 3 picks across all 9 cells) + per-mode tracks + plain-English thesis. Replaced dense 3×3 grid that wasted space on empty cells. Tier colors fixed (MARGINAL no longer yellow-on-yellow). |
| 2026-05-09 PM | PERF-3 | Lazy-render elite-detail sub-tabs. Was: 25 module renders on init. Now: only active sub-tab on boot, others render on first fdSwitchTab. |
| 2026-05-09 PM | PERF-2/2b | Defer Plotly (3.5MB CDN no longer blocks parse) + parallel data.json/tickers.json fetch in elite-detail init(). |
| 2026-05-09 PM | PERF-1d | Match credentials mode on preload AND fetch (5 fetch sites updated to `credentials: 'include'`). Eliminated browser warning + duplicate fetch. |
| 2026-05-09 PM | PERF-1c | `<link rel="preload" as="fetch">` for /api/v2-bootstrap, /api/me, data.json, tickers.json. Warms responses during HTML parse. shell-loader-start dropped 143ms→9.7ms. |
| 2026-05-09 PM | PERF-1b | Combined endpoint `/api/v2-bootstrap` returns {version, registry} in 1 RTT. shell-modules-installed dropped 381ms→40ms (-341ms). |
| 2026-05-09 PM | PERF-1a | Promise.all parallel load of drawer/widgets/actions in shell.js. shell-core-modules-all dropped 551ms→234ms. |
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

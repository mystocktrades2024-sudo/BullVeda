# 📋 SwingTrade Open Items Tracker

**Branch:** `feature/decision-engine-v2` (not yet merged to main)
**Last updated:** 2026-04-14
**Last backtest:** in progress (PID 39149)

**Legend:** ✅ done · 🔄 in-progress · 🟢 P0/must · 🟠 P1/high · 🟡 P2/medium · 🔵 P3/later · ⚪ blocked

---

## 🔑 Secrets rotation — OWNED BY USER

| Item | Status | Owner | Notes |
|---|---|---|---|
| AI-2e Rotate all compromised API keys at providers | ✅ user-owned | Phani | Polygon, Finnhub, FMP, Finviz, Alpaca, Massive, Gmail, Slack — treat all prior keys as compromised; regenerate at each provider UI, paste new values into `.env` |

## 🟢 P0 — Core correctness (all done this sprint)

| # | Item | Status | Notes |
|---|---|---|---|
| 9 | short_min_bear_score math (16 unreachable, max 15) | ✅ | Lowered to 12 in commit 039fd25 |
| 13 | $5K sizing: 5×20%=100% gross, no cash buffer | ✅ | Changed to 4×20% in commit 039fd25 |
| 15 | Setup precedence: VCP > 52wk Breakout | ✅ | Verified already correct |
| 20 | Earnings blackout direction (pre not post) | ✅ | Verified already correct |
| 23 | Schema version-lock | ✅ | _meta block added |
| 25 | Document max_enrichment_tickers=1200 | ✅ | _max_enrichment_note added |
| 29 | Catalyst freshness decay | ✅ | PEAD bonus 1.0→0.25 over 5d |
| 30 | Pre-market gap filter | ✅ | Gap >3% demotes BUY→WATCH |
| — | 5 Vinod decision-engine fixes (EMA8 gate, cloud, divergence, size×zone, labels) | ✅ | Commit 3283dab |
| — | 4 short-side filters (inverse-RS, earnings, sector, float) | ✅ | Commit 3283dab |
| — | Removed short_allow_override foot-gun | ✅ | Commit 3283dab |
| — | Tracker long vs short P&L separation | ✅ | Commit 3283dab |

---

## 🟠 P1 — Architectural consolidation (next 1-2 sessions)

| # | Item | Status | Effort | Notes |
|---|---|---|---|---|
| 2  | Consolidate 4 conflicting threshold configs | 🟠 | 2h | `decisions` vs `regime_thresholds` vs `regime4_thresholds`; pick regime4, delete 3-regime |
| 21 | Delete dead regime_thresholds (3-regime) schema | 🟠 | 30m | After #2 |
| 24 | Deduplicate `_classify_setup_type` vs `classify_setup_family` | 🟠 | 1h | Canonicalize one, migrate callers |
| 22 | Integration test for `make_decision` (10 scenarios) | 🟠 | 1-2h | Create `tests/test_make_decision.py` |
| 19 | Verify `distribution_days_no_new` gate fires | 🟠 | 30m | Test case + grep |

---

## 🟠 P1 — User-facing features (UI)

| # | Item | Status | Effort | Where |
|---|---|---|---|---|
|    | 🛠 System Status tab | ⚪ BLOCKED | 1h | Tab/content/JS all correct on paper — content still renders blank in browser. Needs DevTools inspection to find runtime CSS/JS cause. Revisit after other P1 items. |
|    | Dashboard footer — schema + last-backtested | 🔄 | 5m | Replace generic footer |
|    | Catalyst freshness badge | 🔄 | 20m | Overview tab → PEAD chip |
|    | Pre-market gap badge | 🔄 | 20m | Tile + Overview tab |
|    | PDT rule monitor pill | 🟠 | 30m | Portfolio tab header |
|    | Industry cap warning banner | 🟠 | 30m | Top Picks banner |

---

## 🟡 P2 — Medium lifts

| # | Item | Status | Effort | Notes |
|---|---|---|---|---|
| 11 | Industry cap (vs sector) — 2 per industry | 🟡 | 1h | Needs industry taxonomy beyond sector |
| 12 | Unify VIX tightening (score bar + position size) | 🟡 | 1h | Cross-cutting refactor |
| 14 | Beta/sector factor correlation gate | 🟡 | 2h | 60d correlation matrix per pair |
| 16 | Per-setup live WR with drift alerts | 🟡 | 1h | Extend `signal_tracker` with setup_type |
| — | Setup-WR-weighted sizing | 🟡 | 2h | Auto-downsize underperforming setups |
| — | News-event block (SEC/lawsuit/recall filter) | 🟡 | 2h | Needs news NLP beyond Polygon |
| — | Secrets management (config.json → .env) | 🟡 | 30m | Extract all API keys |

---

## 🔵 P3 — Strategic / observability

| # | Item | Status | Effort | Blocker |
|---|---|---|---|---|
| 17 | Monte Carlo equity curve (1000× randomized) | 🔵 | 2h | Needs backtest trade list |
| 18 | Kelly check documentation | 🔵 | 30m | Write in `docs/SIZING_RATIONALE.md` |
| 26 | Trade journal auto-logger full context (VIX/breadth/regime) | 🔵 | 1h | Extend `tracker.record_run` |
| 28 | Weekly review report (Friday cron) | 🔵 | 1.5h | Script + launchd entry |
| — | Walk-forward backtest (multiple windows) | 🔵 | 3h | Backtest refactor |
| — | 2022 bear-market stress test | 🔵 | 2h | After walk-forward |
| — | Alpaca auto-executor | 🔵 | 6h | Broker integration |
| — | End-of-day position manager (time stops) | 🔵 | 2h | After Alpaca or paper-portfolio polish |
| — | Regime transition auto-exit (shrink exposure) | 🔵 | 2h | After portfolio_tracker handles batch trims |
| — | PDT rule monitor (full enforcement, not just pill) | 🔵 | 1h | |
| — | Options overlay (covered calls on high-conviction) | 🔵 | 4h | Need IV rank + UOA convergence |
| — | Tax-lot optimizer (LT vs ST) | 🔵 | 2h | Need per-trade lot tracking |
| — | Runner protection (auto-trim 25% at +10%) | 🔵 | 1h | Portfolio tracker |

---

## ⚪ Blocked / needs decision

| Item | Blocker |
|---|---|
| Scoring sum normalization (140 → 100 mystery) | Need audit to find where 100-cap is applied — design pass needed |
| Backtest rigor: walk-forward + slippage + commission verification | Need to finish current backtest first (PID 39149) |

---

## 📦 Shipped commits on this branch

- `3283dab` — Vinod review batch 1: 5 decision fixes + 4 short filters + tracker + UI
- `039fd25` — Vinod review batch 2: fix #3 #9 #13 #23 #25 #27 #29 #30
- `TBD`     — System Status tab + footer + UI badges (pending this commit)

---

## 🚀 Merge plan

Before `feature/decision-engine-v2` → `main`:

1. Finish current backtest (PID 39149)
2. Verify WR stays ≥70% on historical sample with new thresholds
3. Run `/Swing-Trade` once; visually inspect: BUY count, SHORT section, regime alert, System Status tab
4. 1 week of clean scheduled runs (starting 2026-04-14 hourly)
5. `git checkout main && git merge feature/decision-engine-v2`

---

## 📅 Scheduled runs (LIVE NOW)

Plist: `~/Library/LaunchAgents/com.swingtrade.daily.plist`
Schedule: Hourly Mon–Fri, 1am–5pm PT (pre-market through after-hours)
Runner: `run_daily_scan.sh` → `python3 swing_trade.py`
Logs: `cache/logs/scan_YYYY-MM-DD.log`

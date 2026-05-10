"""
generate_open_items_xlsx.py — multi-sheet Excel workbook of all SwingTrade open items.

Reads the canonical item list embedded below (54 items across 10 categories)
and produces:
  - Sheet 1: Summary    — counts by category and priority
  - Sheet 2: All Items  — sortable/filterable master list with conditional fmt
  - Sheet 3: Critical Path — sequenced items in execution order
  - Sheet 4: Done       — audit trail of 26 items already shipped

Output: OpenItems.xlsx at the project root.

Re-run anytime to refresh — single source of truth is the ITEMS tuple below.
Edit there, re-run, commit.
"""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.formatting.rule import CellIsRule
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).parent
OUT_PATH = ROOT / "OpenItems.xlsx"

# Priority codes for sortability: 0=done, 1=critical, 2=high, 3=medium, 4=low
PRIORITY_LABEL = {0: "✅ done", 1: "🔴 critical", 2: "🟠 high", 3: "🟡 medium", 4: "🟢 low"}
PRIORITY_FILL = {
    0: PatternFill("solid", fgColor="D3D3D3"),  # grey
    1: PatternFill("solid", fgColor="FFB3B3"),  # red
    2: PatternFill("solid", fgColor="FFD9B3"),  # orange
    3: PatternFill("solid", fgColor="FFF2B3"),  # yellow
    4: PatternFill("solid", fgColor="C8F7C5"),  # green
}

# ─────────────────────────────────────────────────────────────────────
# CANONICAL ITEM LIST — single source of truth.
# Tuple: (id, category, priority, item_description, effort, files, notes,
#         critical_path, owner, blocking, commit_or_source)
# ─────────────────────────────────────────────────────────────────────
ITEMS = [
    # ── A. Lock in working config + guards ──────────────────────────
    ("A1", "A. Lock in working config", 1,
     "Promote A/B variant to production default (min_score=75, hold=7d)",
     "1h", "config/config.json",
     "60d backtest validates WR≥40%, PF≥1.4. A/B variant achieved PF 1.41 / +6.8% return.",
     "Yes", "me", "A4", ""),
    ("A2", "A. Lock in working config", 2,
     "Build signal_filter.py with declarative whitelist gate",
     "2h", "signal_filter.py (NEW), decision_engine.py:626",
     "Gates BUY→WATCH on (setup_type × regime × score_band × entry_quality). Whitelist seeded from current _validations.",
     "Yes", "me", "A4", ""),
    ("A3", "A. Lock in working config", 2,
     "Regime gate in compute_final_verdict",
     "30m", "decision_engine.py",
     "Refuse BUY when regime is risk_off_trending or panic. Strategy is bull-only per 750d data.",
     "Yes", "me", "A4", ""),
    ("A4", "A. Lock in working config", 2,
     "Walk-forward validate the locked-in A/B config",
     "1h + 6h WF", "backtest/walk_forward_v2.py (run only)",
     "Confirm test-fold PF ≥ 1.0 in ≥3 of 4 folds. Blocked by B1 fix.",
     "Yes", "me", "A6, I3", ""),
    ("A5", "A. Lock in working config", 3,
     "Catalyst-conditional analysis (per mover_predictor v2 conclusion)",
     "4h", "decompose_catalyst_trades.py (NEW)",
     "Subset 384-trade ledger to (earnings × insider × UOA × analyst-upgrade) buckets. Find WR > 60%.",
     "Yes", "me", "", ""),
    ("A6", "A. Lock in working config", 3,
     "Entry-time feature logger in swing_trade.py",
     "2h", "swing_trade.py",
     "Log volume_surge, atr_expansion, breakout_clean, options_skew, catalyst_density per signal. Per d3e6127ff: ML failed because features weren't logged.",
     "Yes", "me", "", ""),
    ("A7", "A. Lock in working config", 4,
     "Drift dashboard tile in V2 dashboard",
     "2h", "infra/prototype/tabs/status.js (or new sub-tab)",
     "Surface output of LaunchAgents/com.swingtrade.driftalert.plist (cron exists, UI doesn't).",
     "Yes", "me", "", ""),
    # ── B. Critical bugs ─────────────────────────────────────────────
    ("B1", "B. Bugs", 1,
     "--as-of-membership produces n_trades=0 in WF subprocesses",
     "2-4h", "backtest.py (universe filter or analysis pipeline)",
     "Universe lookup returns 1002 valid tickers but pipeline drops to 0 signals. Standalone repro: backtest.py --portfolio --days 250 --as-of-membership --min-score 60 --min-rs 60",
     "Yes", "me", "A4, D3", ""),
    ("B2", "B. Bugs", 3,
     "Backtest enrich trade records with regime, entry_quality, sector",
     "1h verify + 1h add", "backtest.py",
     "Possibly already done by cb1f5a010 (backtest persistence) — verify before re-implementing.",
     "No", "me", "A5", ""),
    ("B3", "B. Bugs", 0,
     "WF subprocess timeout 3600s → 14400s",
     "done", "backtest/walk_forward_v2.py",
     "Bumped to 4h to avoid premature kills under CPU contention.",
     "No", "me", "", "6222e4947"),
    ("B4", "B. Bugs", 3,
     "Verify backtest persistence prevents silent overwrites",
     "30m", "(verify only, no code change)",
     "I observed cache/portfolio_backtest.json overwritten between reads. Confirm cb1f5a010 fixes this.",
     "No", "me", "", ""),
    # ── C. Phase B (Supabase Mode 2 cutover) ────────────────────────
    ("C1", "C. Phase B (Supabase)", 0, "state_layer.py shim built + 3 hot-path readers wired",
     "done", "state_layer.py, portfolio_tracker.py, signal_tracker.py, decision_engine.py",
     "", "No", "me", "", "310d91c34"),
    ("C2", "C. Phase B (Supabase)", 0, "2 more readers wired (swing_trade + build_data)",
     "done", "swing_trade.py:3376, infra/prototype/build_data.py", "",
     "No", "me", "", "ec9bb006b"),
    ("C3", "C. Phase B (Supabase)", 0, "2 more readers in decision_engine",
     "done", "decision_engine.py", "",
     "No", "me", "", "c55118c43"),
    ("C4", "C. Phase B (Supabase)", 3,
     "Wire server.py alpaca-sync (read-modify-write)",
     "2h", "server.py:802,824,860,866",
     "Complex pattern needs cache invalidation between reads + pt._save_state() for the write.",
     "No", "me", "", ""),
    ("C5", "C. Phase B (Supabase)", 3,
     "Wire ~30 remaining cold-path readers",
     "4-6h", "audit.py, audit_360.py, accuracy_framework.py, position_alerts.py, custom_tracker.py, etc.",
     "Incremental low-value work. Defer until C4 + C6 done.",
     "No", "me", "C6", ""),
    ("C6", "C. Phase B (Supabase)", 2,
     "Phase B.2 — flip SUPABASE_MODE=2",
     "1h code + 1wk obs", ".env",
     "Run for 7 days. Monitor cache/state_layer_metrics.jsonl for fallback rate. Critical milestone toward cloud-canonical.",
     "No", "me", "C5, C7", ""),
    ("C7", "C. Phase B (Supabase)", 3,
     "Phase B.3 — stop JSON write, Supabase canonical",
     "2-3h", "portfolio_tracker.py, signal_tracker.py, supabase_sync.py",
     "Update state_backup.py to dump from Supabase nightly.",
     "No", "me", "C8", ""),
    ("C8", "C. Phase B (Supabase)", 3,
     "Phase B.4 — delete legacy JSON read paths",
     "2h", "state_layer.py, migrate_sqlite_to_supabase.py",
     "Convert migrate_sqlite_to_supabase.py → export_supabase_to_json.py (reverse direction for backup).",
     "No", "me", "", ""),
    # ── D. Walk-forward ──────────────────────────────────────────────
    ("D1", "D. Walk-forward", 0,
     "tune_setup_multipliers + validate_multipliers_on_test + write_validations_from_folds",
     "done", "backtest/walk_forward_v2.py", "", "No", "me", "", "53ad7eb3d"),
    ("D2", "D. Walk-forward", 0, "--config-override CLI on backtest.py",
     "done", "backtest.py", "", "No", "me", "", "53ad7eb3d"),
    ("D3", "D. Walk-forward", 1,
     "Clean WF run end-to-end (blocked by B1)",
     "6h WF", "backtest/walk_forward_v2.py (run only)",
     "Last run died before fold 1 finished due to --as-of-membership bug.",
     "No", "me", "", ""),
    ("D4", "D. Walk-forward", 0, "apply_wf_proposals.py exists",
     "done", "apply_wf_proposals.py", "Ready when D3 produces output.",
     "No", "me", "", "e5c7f0a14"),
    # ── E. Wilson CI / gates ─────────────────────────────────────────
    ("E1", "E. Wilson CI / gates", 0,
     "Wilson CI gate on compute_setup_kill_list",
     "done", "decision_engine.py:240", "", "No", "me", "", "3418ea745"),
    ("E2", "E. Wilson CI / gates", 0,
     "static_setup_kill_list requires n≥10 + override flag",
     "done", "decision_engine.py", "", "No", "me", "", "3418ea745"),
    ("E3", "E. Wilson CI / gates", 0,
     "setup_score_multiplier <1.0 reverts unless _validations declares n≥30",
     "done", "analysis.py:8508", "", "No", "me", "", "3418ea745"),
    ("E4", "E. Wilson CI / gates", 0,
     "_validations populated for EMA21 (n=59) + 52wk (n=114)",
     "done", "config/config.json", "Later expanded to all 6 setups by parallel session (d18cd5886).",
     "No", "me", "", "7d544c205"),
    ("E5", "E. Wilson CI / gates", 3,
     "Wilson CI on setup_score_band_kills + _rejected_static audit visibility",
     "30m", "decision_engine.py",
     "Add LB check parallel to compute_setup_kill_list.",
     "No", "me", "", ""),
    # ── F. Reports + tooling (all done) ──────────────────────────────
    ("F1", "F. Reports + tooling", 0, "generate_session_report.py (8-section narrative)",
     "done", "generate_session_report.py", "", "No", "me", "", "079c2ac74"),
    ("F2", "F. Reports + tooling", 0, "elite_research_note.py (institutional verdict)",
     "done", "elite_research_note.py", "", "No", "me", "", "3f56b6ce8"),
    ("F3", "F. Reports + tooling", 0, "hedge_fund_report.py (12-section quant analytics)",
     "done", "hedge_fund_report.py", "Auto-runs after every --portfolio backtest.",
     "No", "parallel", "", "4361c59a0"),
    ("F4", "F. Reports + tooling", 0, "morning_briefing.py (priority-ordered action plan)",
     "done", "morning_briefing.py", "", "No", "me", "", "e5c7f0a14"),
    ("F5", "F. Reports + tooling", 0, "apply_wf_proposals.py (close the WF→config loop)",
     "done", "apply_wf_proposals.py", "", "No", "me", "", "e5c7f0a14"),
    ("F6", "F. Reports + tooling", 0, "check_schema_drift.py (JSON↔Postgres divergence)",
     "done", "check_schema_drift.py", "", "No", "me", "", "32c9e608f"),
    ("F7", "F. Reports + tooling", 0, "mover_predictor v1 + v2 (definitive negative result)",
     "done", "mover_predictor.py, train_mover_predictor_v2.py",
     "AUC 0.546 — pure technical features at entry-time DO NOT predict mover success at 5d horizon.",
     "No", "parallel", "", "67b012ec2, d3e6127ff"),
    ("F8", "F. Reports + tooling", 0, "hedge_fund_report train/test/holdout + k-fold + per-quarter",
     "done", "hedge_fund_report.py",
     "Surfaced the PF 1.41 holdout finding — the pivotal insight.",
     "No", "parallel", "", "08c481198"),
    ("F9", "F. Reports + tooling", 0, "Backtest persistence (parameterized snapshots)",
     "done", "backtest.py",
     "Every --portfolio run writes both stable + parameterized snapshot. No more silent overwrites.",
     "No", "parallel", "", "cb1f5a010"),
    ("F10", "F. Reports + tooling", 0, "Daily drift alert cron",
     "done", "LaunchAgents/com.swingtrade.driftalert.plist",
     "Runs model_drift_alert.py at 4:30pm PT. Slack alert when live WR diverges from backtest by >5pp.",
     "No", "parallel", "A7", "d18cd5886"),
    ("F11", "F. Reports + tooling", 4,
     "Add check_schema_drift.py --strict to pre-commit hook",
     "30m", ".git/hooks/pre-commit", "",
     "No", "me", "", ""),
    # ── G. Supabase migrations ───────────────────────────────────────
    ("G1", "G. Supabase migrations", 0, "001_initial_schema.sql (17 tables)",
     "done", "migrations/001_initial_schema.sql", "", "No", "me", "", "079c2ac74"),
    ("G2", "G. Supabase migrations", 0, "002_backtest_runs.sql (3 tables)",
     "done", "migrations/002_backtest_runs.sql",
     "backtest_runs, backtest_trades, walk_forward_folds.",
     "No", "me", "", "079c2ac74"),
    ("G3", "G. Supabase migrations", 3,
     "003_signal_filter_audit.sql (signal_filter_rejections table)",
     "30m", "migrations/003_signal_filter_audit.sql (NEW)",
     "Live audit trail for filter demotions. Goes with A2.",
     "No", "me", "A2", ""),
    # ── H. Strategy issues from elite research note ──────────────────
    ("H1", "H. Strategy issues", 2,
     "Russell 1000 historical membership (Sharadar SF1)",
     "$$ + 1d", "data/membership/r1000_*.csv",
     "Wikipedia doesn't have R1000 history. Sharadar SF1 ~$60/mo is the cleanest source. Cost-gated.",
     "No", "me", "", ""),
    ("H2", "H. Strategy issues", 0,
     "Live-vs-backtest drift dashboard (cron exists)",
     "done", "model_drift_alert.py + LaunchAgents/com.swingtrade.driftalert.plist",
     "Cron part done. UI surfacing is A7.",
     "No", "parallel", "", "d18cd5886"),
    ("H3", "H. Strategy issues", 3,
     "Phase 2 drawdown-aware sizing",
     "1d", "portfolio_tracker.py, analysis.py",
     "kelly_size.drawdown_mult is currently a no-op (multiplier=1.0). Wire equity history → sizing reduction during drawdown.",
     "No", "me", "", ""),
    ("H4", "H. Strategy issues", 3,
     "Earnings ESP scanner (data already arrives, unused)",
     "4h", "earnings_esp_scanner.py (NEW)",
     "Per CLAUDE.md P0 priority. ESP data flows through but isn't acted on.",
     "No", "me", "", ""),
    ("H5", "H. Strategy issues", 3,
     "Reconnect StockTwits / WSB / Congressional scrapers",
     "1d", "data_fetcher.py",
     "P0-3 partially shipped. Congressional Stock Watcher S3 endpoint dead.",
     "No", "me", "", ""),
    # ── I. Operational ───────────────────────────────────────────────
    ("I1", "I. Operational", 0,
     "Paper trading enabled (Day 9/60, started 2026-04-30)",
     "done", "data/paper_trading_start.json", "Auto-disables 2026-06-29.",
     "No", "user", "", ""),
    ("I2", "I. Operational", 1,
     "Decide before Day 60 (~2026-06-29): extend / live / shut down",
     "decision", "executor.py",
     "Hard deadline. Strategy will auto-disable.",
     "No", "user", "", ""),
    ("I3", "I. Operational", 2,
     "After A1+A2+A4 ship, safe to consider live with validated A/B config",
     "decision", "executor.py --activate-live (NEW flag)",
     "Gate: requires A1 (config promote), A2 (signal_filter), A4 (WF validation) all green.",
     "No", "user", "I2", ""),
    ("I4", "I. Operational", 4,
     "Verify state_backup.py post-Mode-1 dual-write",
     "15m", "state_backup.py", "", "No", "me", "", ""),
    # ── J. Documentation ─────────────────────────────────────────────
    ("J1", "J. Documentation", 3,
     "Update CLAUDE.md with new tools",
     "30m", "CLAUDE.md",
     "signal_filter, mover_predictor, drift_alert, train/test/holdout, apply_wf_proposals, morning_briefing, check_schema_drift, OpenItems.xlsx.",
     "No", "me", "", ""),
    ("J2", "J. Documentation", 4,
     "docs/signal_filter_v1.md (whitelist source + retraining cadence)",
     "30m", "docs/signal_filter_v1.md (NEW)", "Goes with A2.",
     "No", "me", "A2", ""),
    ("J3", "J. Documentation", 3,
     "Set git committer.email globally",
     "5m", "git config --global", "Currently auto-derived as phanirajgarimella@PhaniRajs-MacBook-Pro.local — affects GitHub commit attribution.",
     "No", "me", "", ""),
    # ── K. Vinod's feedback on HPE (2026-05-09) — 10 items + 1 meta arch fix
    # Categorized per analysis: Cat 1 = engine rule gaps (do now), Cat 2 =
    # output-consistency / single-source-of-truth (architectural fix), Cat 3 =
    # product scope (V2 backlog) + EW classification rule (do now).
    ("K1", "K. Vinod feedback (HPE)", 2,
     "Engine rule: Stop = Fibonacci + EMA 50 confluence (Rule P-new)",
     "3h", "analysis.py (stop calc), config (gate G1)",
     "Cat 1 — engine rule gap. Currently stop is engine-defined but confluence logic isn't specified. Becomes Gate G1 + scoring sub-rule.",
     "Yes", "me", "", ""),
    ("K2", "K. Vinod feedback (HPE)", 2,
     "Engine rule: VWAP & AVWAP below stop loss = flag (Gate G1 sub-check)",
     "1h", "analysis.py (stop validation), decision_engine.py (gates)",
     "Cat 1 — hard check. If VWAP < stop loss, stop placement is likely wrong. Add as entry validation rule.",
     "Yes", "me", "", ""),
    ("K3", "K. Vinod feedback (HPE)", 2,
     "Engine rule: stop placement at/below nearest fractal low (confirmed by Fib level)",
     "2h", "analysis.py (stop calculation)",
     "Cat 1 — missing from rulebook entirely. Stop should ALWAYS align with nearest fractal low.",
     "Yes", "me", "", ""),
    ("K4", "K. Vinod feedback (HPE)", 3,
     "Decide: add EMA 5 & EMA 13 to Technical pillar (5/13/21/50 vs current 8/21/50)",
     "1h decision + 2h impl", "analysis.py (technicals scoring), infra/prototype/tabs/technicals.js",
     "Cat 1 — decide yes/no first, then implement. Changes Technical pillar scoring. Need to backtest before lock.",
     "Yes", "me", "", ""),
    ("K5", "K. Vinod feedback (HPE)", 2,
     "Engine rule: EW classification + target derivation (Wave 3 Impulse → T1/T2 Fib extensions)",
     "4h", "analysis.py (EW model), infra/prototype/tabs/models.js",
     "Cat 3 + EW gap. HPE example: Wave 3 Impulse, T1=$50.37, T2=$55.75 derived from Fib extensions of that wave. Wave 3 impulse = bullish. Fills one of the 7 design gaps.",
     "Yes", "me", "", ""),
    ("K6", "K. Vinod feedback (HPE)", 1,
     "Architectural fix: single canonical trade-plan output object — all tabs read from it",
     "1d", "decision_engine.py (compute_final_verdict), infra/prototype/* (all tab modules)",
     "Cat 2 META-FIX — resolves K7+K8+K9. Engine outputs ONE canonical {entry_zone, stop, T1, T2, shares}. Every tab reads from that single output. No tab does independent calculation. Per the 2026-05-06 audit (7 independent decision engines) — that audit was supposed to fix this but didn't propagate to per-tab display.",
     "Yes", "me", "K7, K8, K9", ""),
    ("K7", "K. Vinod feedback (HPE)", 2,
     "Output consistency: SMC trade plan must equal Overview tab's plan",
     "(covered by K6)", "infra/prototype/tabs/smc.js, plan.js",
     "Cat 2 — single-source-of-truth problem. Auto-resolves when K6 ships.",
     "Yes", "me", "", ""),
    ("K8", "K. Vinod feedback (HPE)", 2,
     "Output consistency: Bear & Severe scenario cases must align with Plan/Thesis",
     "(covered by K6)", "infra/prototype/tabs/models.js (scenarios)",
     "Cat 2 — scenario model outputs derived from same entry/stop/target as main plan. Auto-resolves with K6.",
     "Yes", "me", "", ""),
    ("K9", "K. Vinod feedback (HPE)", 2,
     "Output consistency: Thesis tab T1/T2 must match outlook numbers (no manual entry)",
     "(covered by K6)", "infra/prototype/tabs/plan.js, infra/prototype/tabs/overview.js",
     "Cat 2 — same single-source fix. No tab should have its own independently calculated plan.",
     "Yes", "me", "", ""),
    ("K10", "K. Vinod feedback (HPE)", 4,
     "V2 backlog: mid-term fundamentals (4Q earnings + forward guidance + sector tailwind)",
     "1-2d (V2)", "analysis.py (fund scoring), config (horizon profiles)",
     "Cat 3 — product-scope decision. Means different score weights, macro inputs, exit rules per horizon. Current engine is implicitly swing (weeks-to-months). V2.",
     "No", "me", "", ""),
    ("K11", "K. Vinod feedback (HPE)", 4,
     "V2 backlog: long-term fundamentals (6Q + YoY comparison + forward guidance + sector tailwind)",
     "1-2d (V2)", "analysis.py (fund scoring), config (horizon profiles)",
     "Cat 3 — same V2 scope decision as K10. Long-term horizon variant.",
     "No", "me", "", ""),
]


def _header_style(ws, row=1):
    """Bold + grey background for header row."""
    fill = PatternFill("solid", fgColor="2C3E50")
    font = Font(color="FFFFFF", bold=True, size=11)
    for cell in ws[row]:
        cell.fill = fill
        cell.font = font
        cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)


def _autosize_columns(ws, widths: dict):
    for col_letter, w in widths.items():
        ws.column_dimensions[col_letter].width = w


def _build_summary_sheet(wb: Workbook):
    ws = wb.create_sheet("Summary", 0)
    ws.append(["SwingTrade Open Items — Summary"])
    ws["A1"].font = Font(size=18, bold=True)
    ws.append([])

    # Per-category counts
    headers = ["Category", "Total", "Done", "Critical", "High", "Medium", "Low", "Open Effort (hrs)"]
    ws.append(headers)
    _header_style(ws, row=3)

    # Aggregate
    from collections import defaultdict
    by_cat = defaultdict(lambda: {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, "effort": 0.0})
    for it in ITEMS:
        cat = it[1]
        prio = it[2]
        by_cat[cat][prio] += 1
        # Rough effort parse — sum hours from the effort field for OPEN items only
        if prio != 0:
            eff = it[4].lower()
            for token in eff.replace(",", " ").split():
                token = token.strip().lower()
                if token.endswith("h") and token[:-1].replace(".", "").replace("-", "").isdigit():
                    try:
                        by_cat[cat]["effort"] += float(token[:-1].split("-")[-1])
                    except ValueError:
                        pass
                elif token in ("1d", "1day"):
                    by_cat[cat]["effort"] += 8.0

    grand_total = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, "effort": 0.0}
    for cat in sorted(by_cat.keys()):
        d = by_cat[cat]
        total = sum(d[p] for p in (0, 1, 2, 3, 4))
        ws.append([cat, total, d[0], d[1], d[2], d[3], d[4], round(d["effort"], 1)])
        for p in (0, 1, 2, 3, 4):
            grand_total[p] += d[p]
        grand_total["effort"] += d["effort"]

    grand_row = ws.max_row + 1
    ws.append([
        "TOTAL",
        sum(grand_total[p] for p in (0, 1, 2, 3, 4)),
        grand_total[0], grand_total[1], grand_total[2], grand_total[3], grand_total[4],
        round(grand_total["effort"], 1),
    ])
    for cell in ws[grand_row]:
        cell.font = Font(bold=True, size=12)
        cell.fill = PatternFill("solid", fgColor="EAECEE")

    _autosize_columns(ws, {"A": 38, "B": 8, "C": 8, "D": 10, "E": 8, "F": 10, "G": 8, "H": 18})
    ws.freeze_panes = "A4"

    # Critical Path mini-section
    ws.append([])
    ws.append([])
    ws.append(["Critical Path (sequenced execution order)"])
    ws.cell(row=ws.max_row, column=1).font = Font(bold=True, size=14)
    cp_header_row = ws.max_row + 1
    ws.append(["#", "ID", "Item", "Effort", "Status"])
    _header_style(ws, row=cp_header_row)
    cp_items = [it for it in ITEMS if it[7] == "Yes"]
    # Order: A1 → A2/A3 → A4 → A6 → A5 → A7 (per critical path)
    cp_order = ["K6", "K1", "K2", "K3", "K5", "A1", "A2", "A3", "K4", "A4", "A6", "A5", "A7"]
    cp_dict = {it[0]: it for it in cp_items}
    for i, item_id in enumerate(cp_order, 1):
        if item_id in cp_dict:
            it = cp_dict[item_id]
            ws.append([i, it[0], it[3], it[4], PRIORITY_LABEL.get(it[2], "")])

    # Generated stamp
    from datetime import datetime
    ws.append([])
    ws.append([])
    ws.append([f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M %Z')}  ·  Source: generate_open_items_xlsx.py  ·  {len(ITEMS)} items"])
    ws.cell(row=ws.max_row, column=1).font = Font(italic=True, color="7F8C8D")


def _build_all_items_sheet(wb: Workbook):
    ws = wb.create_sheet("All Items")
    headers = ["ID", "Category", "Status", "Priority", "Item", "Effort", "Files Modified",
               "Notes", "Critical Path?", "Owner", "Blocks", "Commit / Source"]
    ws.append(headers)
    _header_style(ws, row=1)

    for it in ITEMS:
        item_id, cat, prio, desc, eff, files, notes, cp, owner, blocking, commit = it
        ws.append([
            item_id, cat, PRIORITY_LABEL.get(prio, ""), prio, desc, eff,
            files, notes, cp, owner, blocking, commit,
        ])

    # Conditional formatting on Priority column (D)
    n_rows = len(ITEMS) + 1  # +1 for header
    rng = f"D2:D{n_rows}"
    ws.conditional_formatting.add(rng,
        CellIsRule(operator="equal", formula=["0"], fill=PRIORITY_FILL[0]))
    ws.conditional_formatting.add(rng,
        CellIsRule(operator="equal", formula=["1"], fill=PRIORITY_FILL[1]))
    ws.conditional_formatting.add(rng,
        CellIsRule(operator="equal", formula=["2"], fill=PRIORITY_FILL[2]))
    ws.conditional_formatting.add(rng,
        CellIsRule(operator="equal", formula=["3"], fill=PRIORITY_FILL[3]))
    ws.conditional_formatting.add(rng,
        CellIsRule(operator="equal", formula=["4"], fill=PRIORITY_FILL[4]))

    # Wrap text on long columns + height
    for row_cells in ws.iter_rows(min_row=2):
        for c in row_cells:
            c.alignment = Alignment(vertical="top", wrap_text=True)

    _autosize_columns(ws, {
        "A": 6, "B": 24, "C": 12, "D": 8, "E": 50, "F": 14,
        "G": 32, "H": 50, "I": 12, "J": 9, "K": 12, "L": 22,
    })
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = f"A1:L{n_rows}"


def _build_critical_path_sheet(wb: Workbook):
    ws = wb.create_sheet("Critical Path")
    ws.append(["Critical Path — sequenced execution order"])
    ws["A1"].font = Font(size=16, bold=True)
    ws.append([])

    headers = ["Step", "ID", "Item", "Effort", "Files", "Verification", "Blocks"]
    ws.append(headers)
    _header_style(ws, row=3)

    cp_order = ["K6", "K1", "K2", "K3", "K5", "A1", "A2", "A3", "K4", "A4", "A6", "A5", "A7"]
    by_id = {it[0]: it for it in ITEMS}
    verifications = {
        "K6": "Open HPE elite-detail.html → Plan, Thesis, SMC, Models tabs all show identical entry/stop/T1/T2",
        "K1": "Stop value matches confluence of Fib retracement + EMA 50 within ±1%",
        "K2": "Test ticker with VWAP < stop → gate emits flag; pre-trade gate blocks BUY",
        "K3": "Stop value ≤ nearest 5-bar fractal low for every BUY in next scan",
        "K5": "HPE Models tab shows Wave 3 Impulse with T1≈$50.37, T2≈$55.75 (Fib extensions)",
        "A1": "60d backtest WR≥40%, PF≥1.4 (matches A/B variant)",
        "A2": "python3 swing_trade.py — flip _enabled and verify BUY count drops",
        "A3": "Run scan during simulated risk_off regime — confirm zero BUYs",
        "K4": "Backtest with new EMA stack improves Technical pillar correlation to PnL by ≥5%, then lock",
        "A4": "≥3 of 4 test folds show PF ≥ 1.0",
        "A6": "data/signal_log.json shows entry-time feature fields populated",
        "A5": "cache/catalyst_decomposition_*.html shows N catalyst-buckets with WR > 60%, n ≥ 20",
        "A7": "Drift status tile renders in V2 dashboard Status tab",
    }
    for i, item_id in enumerate(cp_order, 1):
        if item_id not in by_id:
            continue
        it = by_id[item_id]
        ws.append([i, item_id, it[3], it[4], it[5], verifications.get(item_id, ""), it[10]])

    for row_cells in ws.iter_rows(min_row=4):
        for c in row_cells:
            c.alignment = Alignment(vertical="top", wrap_text=True)

    _autosize_columns(ws, {"A": 6, "B": 6, "C": 50, "D": 16, "E": 36, "F": 50, "G": 12})
    ws.freeze_panes = "A4"


def _build_done_sheet(wb: Workbook):
    ws = wb.create_sheet("Done (audit trail)")
    ws.append(["Already shipped — audit trail"])
    ws["A1"].font = Font(size=16, bold=True)
    ws.append([])

    headers = ["ID", "Category", "Item", "Files", "Commit", "Notes"]
    ws.append(headers)
    _header_style(ws, row=3)

    for it in ITEMS:
        if it[2] != 0:
            continue
        item_id, cat, prio, desc, eff, files, notes, cp, owner, blocking, commit = it
        ws.append([item_id, cat, desc, files, commit, notes])

    for row_cells in ws.iter_rows(min_row=4):
        for c in row_cells:
            c.alignment = Alignment(vertical="top", wrap_text=True)

    _autosize_columns(ws, {"A": 6, "B": 24, "C": 50, "D": 36, "E": 22, "F": 50})
    ws.freeze_panes = "A4"


def build_workbook() -> Workbook:
    wb = Workbook()
    # Remove default empty sheet
    wb.remove(wb.active)
    _build_summary_sheet(wb)
    _build_all_items_sheet(wb)
    _build_critical_path_sheet(wb)
    _build_done_sheet(wb)
    return wb


def main():
    wb = build_workbook()
    wb.save(OUT_PATH)
    n_items = len(ITEMS)
    n_done = sum(1 for it in ITEMS if it[2] == 0)
    n_open = n_items - n_done
    n_critical = sum(1 for it in ITEMS if it[2] == 1)
    print(f"Wrote {OUT_PATH}")
    print(f"  {n_items} items total ({n_done} done, {n_open} open)")
    print(f"  {n_critical} critical")
    print(f"  Sheets: Summary, All Items, Critical Path, Done (audit trail)")
    print(f"  Open: open '{OUT_PATH}'")


if __name__ == "__main__":
    main()

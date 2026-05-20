# Per-mode decisions roadmap (Option A)

**Status:** Phase 1 + Phase 2 + Phase 3 shipped 2026-05-19 (Phase 3 INTUITION-BASED weights, flag-gated · validation pending). Phase 4 deferred.

## Background

Pre-2026-05-19, the SWING / POSITION / INVEST pills in the kairos detail
header were **cosmetic** — toggling them updated URL + UI highlights but
the underlying `t.decision` and `t.canonical_trade_plan` were single
strategy-agnostic fields. Users would click POSITION and see the same
BUY ribbon, same stop, same T1/T2, same R:R as SWING. The toggle was a
lie.

Per user direction 2026-05-19, made the toggle real. Each mode applies
its own rulebook end-to-end.

## The three rulebooks

| Field | SWING (2-10d) | POSITION (2w-6mo) | INVESTMENT (1-5yr) |
|---|---|---|---|
| Stop | 1.25× ATR | 1.75× ATR | −15% drawdown |
| R:R floor | 3.0 | 2.5 | 2.0 |
| Entry quality | FRESH / PULLBACK | FRESH / PULLBACK / VALID | any (MoS-driven) |
| Earnings blackout | 14 days | none (holds through prints) | irrelevant |
| Size multiplier | ×1.0 | ×1.3 | ×1.5 |

Source of truth: `analysis.py:_MODE_RULEBOOK`.

## Phase 1 — Per-mode verdicts + trade plans (SHIPPED 3e812743)

- New `compute_decisions_by_mode()` in `analysis.py`
- New `_make_mode_config()` helper to shallow-copy + override base config
- Wired into `analyze_ticker()` between the main `make_decision()` call
  and the gate-failure override
- Output: `t.decisions_by_mode = {swing, position, investment}` per
  ticker, each with `{verdict, reason, color, stop, t1, t2, rr_ratio,
  entry_mid, size_mult, horizon_days, stop_basis, rulebook}`
- Backward compat: legacy `t.decision` + `t.canonical_trade_plan`
  preserved
- Frontend: `renderQuickActionBar` + `renderPlanTab` + Overview plan
  strip all read `t.decisions_by_mode[_qdStrategyCurrent().toLowerCase()]`
  when present, fall back to legacy fields otherwise

## Phase 2 — Per-mode sizing + verdict-divergence explanation (SHIPPED this commit)

- `compute_decisions_by_mode()` accepts `base_alloc_pct` (from
  `kelly_size.final_alloc_pct`) and `legacy_decision` (the single-pass
  result for divergence comparison)
- Per-mode `final_alloc_pct = base_alloc_pct × mode.size_mult` capped
  at 5% NAV single-name (per CLAUDE.md principle 10)
- New `diverge_note` field surfaces the specific rule that caused the
  verdict to differ from the legacy single-decision (e.g., "R:R 2.4 <
  3.0 mode floor" or "entry VALID not in mode gate ['FRESH','PULLBACK']")
- Frontend: detail-bar shows `size 5.5% NAV (1.3×)` chip + amber
  `⚠ R:R 2.4 < 3.0 mode floor` chip when verdict diverges from legacy

## Phase 3 — Per-mode pillar reweighting (SHIPPED 2026-05-19 · flag-gated · validation pending)

**⚠ Important:** Phase 3 ships INTUITION-BASED pillar weights. CLAUDE.md
principle 7 normally requires walk-forward backtest evidence before any
config change. **The user explicitly overrode that requirement to ship
the per-mode UX immediately**, with the following safety rails:

1. **Flag-gated for rollback** — set
   `config.per_mode_pillar_reweight._enabled = false` to revert to
   the legacy single-composite behavior. Code path stays in place;
   only the toggle changes.
2. **UI-only impact** — the per-mode composite affects only the
   verdict chip + `decisions_by_mode[mode].verdict` shown in the
   detail page. The **legacy single composite `t.score` still drives
   the primary `decision_log` entry, all automated alerts, the
   morning briefing, and the kill-list / Wilson-LB pipelines**.
3. **Transparency** — when the mode score diverges from the legacy
   score by ≥5pts, the chip shows BOTH (e.g., "score 58 (legacy 45)")
   so the user sees the reweighting at work.

### Weights shipped (each set sums to 1.0)

Source of truth: `analysis.py:_MODE_PILLAR_WEIGHTS`.

| Pillar | SWING | POSITION | INVEST |
|---|---|---|---|
| trend | 0.30 | 0.25 | 0.15 |
| rs | 0.25 | 0.20 | 0.15 |
| catalyst | 0.25 | 0.20 | 0.10 |
| smart_money | 0.10 | 0.15 | 0.10 |
| fundamentals | 0.05 | 0.15 | 0.45 |
| entry_rr | 0.05 | 0.05 | 0.05 |

Per-mode composite = Σ (pillar_pct × mode_weight × 100).

### Mandatory follow-up validation (DO NOT SKIP)

These weights ship as **a Phase-3 starting point**. Walk-forward
validation is still required to confirm they're not actively hurting:

1. Snapshot current single-weight backtest (252d, min_score=50) — call
   this baseline.
2. Run 3 separate backtests with the per-mode weights, simulating each
   mode as if the system always operated in that mode.
3. Compare per-mode WR, PF, max-DD, Sharpe vs baseline.
4. **If any mode shows ≤1.0× PF or ≤−5pp WR vs baseline → revert** by
   flipping `per_mode_pillar_reweight._enabled = false`.

**Estimated effort:** 1-2 days of backtest compute + analysis.

### Where Phase 3 lives in code

- `analysis.py:_MODE_PILLAR_WEIGHTS` — the 3 weight sets
- `analysis.py:compute_decisions_by_mode` — accepts `pillar_pcts` kwarg;
  when phase-3 is enabled, computes mode_score = Σ (pct × weight × 100)
  per mode and passes that to `make_decision()` instead of the legacy
  composite
- `analysis.py:analyze_ticker` — call site assembles `pillar_pcts` from
  tech/fund/opt/sent/rs/plan sub-scores
- `kairos.html:renderQuickActionBar` — surfaces mode composite + shows
  "(legacy 45)" annotation when divergence ≥5pts so user sees the
  reweight visually

### Output schema additions

Each `t.decisions_by_mode[mode]` entry now also carries:
- `composite_score` — the mode-specific composite (or legacy when
  phase-3 disabled)
- `phase3_active` — bool
- `pillar_pcts` — raw pillar pct (0-100) per pillar (debug/inspection)
- `pillar_weighted` — pct × mode weight (debug/inspection)
- `pillar_weights` — the active weight set per pillar

## Phase 4 — Per-mode setup family routing (DEFERRED — needs evidence)

Some setup families are mode-native:

- **PEAD** is intrinsically SWING (1-3 day post-earnings drift)
- **VCP** is intrinsically POSITION (8-12 week breakout base)
- **52wk Breakout** is mode-agnostic
- **Cup-and-Handle** is POSITION

The system could refuse to surface PEAD signals in INVEST mode (the
horizon mismatch makes it nonsense), and could downsize VCP signals in
SWING mode.

**Deferred for the same reason as Phase 3** — needs evidence that
mode-conditional routing produces better outcomes than the current
unified routing.

## Where this code lives

- `analysis.py:_MODE_RULEBOOK` — the 3 rulebooks
- `analysis.py:_make_mode_config()` — config-override helper
- `analysis.py:compute_decisions_by_mode()` — main per-mode loop
- `analysis.py:analyze_ticker()` — call site (after `make_decision()`)
- `infra/prototype/kairos.html:renderQuickActionBar()` — detail-bar reader
- `infra/prototype/kairos.html:renderPlanTab()` — Plan-tab reader
- `infra/prototype/kairos.html:renderOverviewV2()` (PLAN strip) — Overview reader

## How to verify locally

```bash
cd "/Volumes/MyMacDisk/Claude Skills/SwingTrade"
python3 swing_trade.py   # regenerate data with per-mode decisions
# Then hard-refresh kairos.html and toggle SWING / POS / INV pills
# on any detail page — verdict, stop, T1, R:R, size chip should all change.
```

The detail-bar should show a different verdict chip per mode and a
size-NAV chip that scales with the mode multiplier. If the verdict
diverges from the legacy single-decision, an amber `⚠` chip surfaces
the specific rule mismatch.

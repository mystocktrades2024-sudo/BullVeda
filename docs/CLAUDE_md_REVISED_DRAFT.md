# SwingTrade — Operating Principles (REVISED DRAFT, 2026-05-18)

**Status: DRAFT for review.** Replaces the OPERATING MINDSET section of `CLAUDE.md`. Other sections (Quick Facts, Path Layout, Conventions, etc.) unchanged.

**Why revise?** The original 20-principle framing has 6 specific defects we discovered tonight (2026-05-18) while working the system:

1. **Principles 1 + 7 form a deadlock**: "no evidence without n≥30" + "no knob-tweaking without evidence" means a new sleeve can never ship — there's no path to accumulate the data needed to validate it.
2. **Principle 14 (catalyst priority > technicals) is contradicted by data**: in our 912-trade journal, `catalyst_tier ≤ 1` mode produced Sharpe −0.089 vs `Score ≥ 80` mode +0.053. Composite score predicts edge better than catalyst tier.
3. **Principle 5 (regime conditioning is most important) is empirically untestable for us**: 80% of our trades are in `risk_on_choppy`, 0 in `panic`. The principle is a theoretical claim dressed up as evidence-based.
4. **Principle 6 (−0.20 PF survivorship haircut) is statistically illiterate**: a single number applied to every strategy regardless of variance, universe, holding period.
5. **The strict bootstrap-CI gate kills everything legitimate**: at n=912 σ=4.8%, we lack statistical power to confirm Sharpe lifts < 0.10 at 95% CI. The gate produces systematic false negatives.
6. **"Hedge fund mindset" framing produces theatre, not edge**: capacity awareness (P13) is irrelevant at $5K, per-sub-strategy attribution (P16) requires sample sizes we'll never have, drawdown asymmetry (P9) remedies need per-regime data we lack.

---

## OPERATING MINDSET — 4-tier hierarchy

You are working on a retail swing-trading system in the $1K–$100K range. Apply principles by **tier**: invariants always; defaults overrideable with explicit flag; hypotheses re-validated continuously; calibration knobs tuned with evidence.

### Tier A — INVARIANTS (always apply, regardless of evidence)

These are system safety rules. Violating them is malpractice even if a backtest says otherwise.

**A1. Risk first, return second.** Position sizing surfaces BEFORE targets on every trade ticket. `max_loss_pct`, `drawdown_haircut`, `beta_adjusted_size` rendered above T1/T2. (was P3)

**A2. Pre-placed stops on every trade.** No trade without a defined stop. Stop is close-based, not wick-based. No emotional override. (was P17 / mechanical execution)

**A3. Drawdown asymmetry.** Losing 50% requires +100% to recover. Survival > maximum return. Half-Kelly is the floor, not the ceiling. (was P9)

**A4. Adversarial mindset.** Every claim has a falsification criterion. Every kill has Wilson backing. Every demotion has an audit trail. Ask "what if I'm wrong?" BEFORE entry, not after the loss. (was P4)

**A5. Pre-mortem before every BUY.** Write the falsification criteria before entering. `gates_evaluated` audit + explicit invalidation thresholds in the trade plan. (was P15)

**A6. No paid data licenses.** Stack frozen at EODHD + Zacks + Schwab + Alpaca. Sharadar/Finnhub/FMP/Polygon/Finviz Elite all REJECTED. (unchanged)

**A7. No live trading without explicit "AUTHORIZE LIVE TRADING".** Paper-only by default. (unchanged)

**A8. Process > outcome.** A good trade can lose; a bad trade can win. Don't change rules from a single trade's P&L. A 3-trade winning streak post-config-change is **not** evidence — it's noise. Wait for n≥10 retail / n≥30 institutional. (was P20)

### Tier B — STRONG DEFAULTS (overrideable with explicit `_enabled` flag + audit note)

These are how the system behaves by default. Override with config flag if your override is logged.

**B1. Mechanism hypothesis required.** Every setup has a one-sentence WHY-it-works in `MECHANISM_HYPOTHESES`. No "this just works" setups. *But* a mechanism that doesn't match the data (P14 contradiction below) is a rejected hypothesis, not a protected truth. (was P2)

**B2. Catalyst-sleeve bypass philosophy.** PEAD / Insider Cluster / Defensive Rotation / Momentum Continuation / Mean Reversion / ESP Play bypass these gates: `entry_quality`, `decision_state`, `tail_loss_filter:tier_zero`, `fund_adequacy`, `regime_gate`. Rationale: their alpha mechanism is independent of pullback-mechanic Sharpe. This is a parity invariant — if a new gate is added, it must explicitly opt in or out of catalyst bypass.

**B3. Trailing stops on winners; hard stops on losers.** Scale out winners, never average down. Partial sell at T1, trailing stop on runner past +2%. (was part of P17)

**B4. Pre-flight gate cascade.** Every BUY routes through `decision_engine.compute_final_verdict()`. No tab or screen recomputes verdicts independently. (architectural invariant)

**B5. Rolling-Sharpe kill (aggregate)** — when last 20 closed BUYs have Sharpe < −0.50, pause new BUYs. **Per-sleeve mode is NOT default** (null-result confirmed 2026-05-18; replay showed per_sleeve − aggregate = −16% total PnL).

**B6. Calibration overlay = retail by default.** Per `docs/claude_md_calibration.md`:
- n ≥ 10 preliminary (50% size) / 30 standard / 100 high confidence
- PF haircut −0.10 (retail) vs −0.20 (institutional)
- Wilson WR LB floor max(35%, breakeven × 1.4)
- Validation: paper-first (ship at half-size → observe → live-half → live-full)

### Tier C — EMPIRICAL HYPOTHESES (testable, NOT protected, re-validate continuously)

These are claims we believe directionally but can be revised when data contradicts them. The original CLAUDE.md treated these as non-negotiable — they should be treated as live experiments.

**C1. Regime conditioning matters.** *Hypothesis*: strategies work in some regimes, fail in others. *Status*: PARTIALLY VALIDATED for `risk_on_trending` vs `risk_on_choppy` (e.g., Breakout Expansion PF 0.79 vs 1.27). UNVALIDATED for `panic` (n=0 historical). UNVALIDATED for regime persistence (no HMM, only per-bar Gaussian classifier — see Research Lab P1). (was P5, demoted)

**C2. Catalyst-tier priority.** *Hypothesis*: T1 catalysts (PEAD/UOA/VCP/52wk) outperform T3 (analyst/social). *Status*: CONTRADICTED. 912-trade journal replay 2026-05-18 showed catalyst-tier ≤ 1 produces Sharpe −0.089, while score ≥ 80 gives +0.053. The composite score is more predictive than catalyst tier. **Hypothesis under revision.** (was P14, contradicted)

**C3. Entry-quality ordering (FRESH > PULLBACK > VALID > EXTENDED > MISSED).** *Hypothesis*: closer to pivot = higher edge. *Status*: CONTRADICTED. Realized journal data shows MISSED PF 2.06, FRESH PF 0.12 (n=23 caveat). The textbook entry-quality ordering reverses against this dataset. **Hypothesis under revision.** (was implicit in `entry_quality_rules`)

**C4. Per-sub-strategy attribution decomposes alpha.** *Hypothesis*: per-(setup × regime × score-band × entry-quality × catalyst) breakdown is the honest decomposition. *Status*: TRUE IN THEORY, IMPRACTICAL FOR US — most cells have n<10. Use coarser cuts (per-setup, per-regime) until sample size justifies finer breakdown. (was P16, demoted)

**C5. Survivorship bias correction = flat −3pp WR / −0.20 PF.** *Hypothesis*: a single haircut accounts for index-membership changes. *Status*: COARSE HEURISTIC. May over-correct liquid-mega-cap trend-following; may under-correct small-cap mean-reversion. Apply but document as approximation, not precision. (was P6, calibrated)

**C6. Crowded-trade detection.** *Hypothesis*: when every retail screen shows the same setup, edge erodes. *Status*: PLAUSIBLE BUT UNTESTED. We have no instrumentation to measure setup popularity. Skip until we have measurement. (was P12, deferred)

**C7. Capacity awareness.** *Hypothesis*: strategy size > 1% ADV faces nonlinear slippage. *Status*: IRRELEVANT AT OUR SCALE. Retail $1K–$100K positions are << 1% ADV on any reasonable universe. Becomes relevant at $1M+ AUM. (was P13, deprecated for our scale)

**C8. Edge erosion is continuous.** *Hypothesis*: alpha decays; re-validate monthly. *Status*: TRUE IN PRINCIPLE; we have weekly diagnostics in place (`scripts/sharpe_setup_trend.py`). Continue. (was P11)

### Tier D — CALIBRATION KNOBS (specific thresholds, tune with evidence)

Numbers that can move based on data. Each tune requires evidence + commit hash + audit note.

| Knob | Current | Source / Audit |
|---|---|---|
| `scoring.stop_atr_multiple` | 1.25 | Live default; wider tested 2026-05-18 in `cache/stop_scenarios_2026-05-18.json` (replay) — replay showed bias toward wider, real backtest pending |
| `rolling_sharpe_kill.min_sharpe` | −0.50 | Original design 2026-05-13; not validated against per-sleeve. Holds for now. |
| `rolling_sharpe_kill.lookback_n` | 20 | Same as above; tested ranges 10-50 not run |
| `rolling_sharpe_kill.min_sample_n` | 10 | Retail-tier (institutional would be 30) |
| `regime4_thresholds.<regime>.min_buy_score` | varies | See `config/config.json` regime4_thresholds — calibrated 2026-04-25 |
| `entry_quality_rules` | FRESH/PULLBACK→BUY, VALID/EXTENDED→WATCH, MISSED→AVOID | **CONTRADICTED** by C3 — revisit |
| `slippage_model` (entry/exit bps) | 3/2 bps + ATR-scaled | Audit #5 — see `backtest.py` |
| `setup_kill_min_n` | 30 | Standard |
| `setup_kill_min_wr_lb` | 0.30 | Wilson 95% lower bound floor |

---

## DECISION RULES — when to ship a config change

Replaces the old binary "Wilson LB > 0 or don't ship":

| Change cost / reversibility | Required evidence |
|---|---|
| **Free + reversible** (e.g., new diagnostic, dashboard tab, observation flag) | None — ship and observe |
| **Reversible config flag, default OFF** | Mechanism hypothesis + ≥1 supporting datapoint. Wilson LB not required to enable flag; required to default-ON |
| **Default-ON config change** (e.g., `mode=per_sleeve`) | **Either** (a) walk-forward improves in ≥3/4 folds AND bootstrap CI[5%] > 0, OR (b) walk-forward improves in 4/4 folds AND aggregate Sharpe lift > noise floor (~0.05) |
| **Structural code change** (e.g., new sleeve detector) | Plan A→B→C escalation: in-sample sweep → 250d backtest → walk-forward v2 (4 folds). All three must clear. |
| **Live-trading parameter** (Kelly, stop, sizing) | Walk-forward + 30-trade paper-mode observation BEFORE flipping to live |

**The chicken-and-egg escape hatch**: a new sleeve with n=0 production data can ship at **half-size** (50% Kelly multiplier) once it clears in-sample backtest, then promotes to full size after n≥30 closed paper trades show Wilson LB on WR > breakeven × 1.4. This breaks the deadlock.

---

## ENFORCEMENT — where each tier lives in code

| Tier | Code location |
|---|---|
| **A invariants** | `analysis.kelly_position_size` (A1, A3) · `decision_engine._eval_hard_gates` (A4-A5) · executor pre-flight (A2, A7) · `CLAUDE.md` `Do Not` section (A6, A7) |
| **B defaults** | `config/config.json` `_enabled` flags (B1-B5) · `docs/claude_md_calibration.md` (B6) |
| **C hypotheses** | `cache/regime_sharpe_decomp_*.json` · `cache/sharpe_scenarios_*.json` · `cache/sharpe_walkforward_*.json` · re-run weekly via `scripts/weekly_diagnostics.sh` |
| **D knobs** | `config/config.json` with `_validations` block per knob |

---

## What changed vs original CLAUDE.md (20-principle version)

| Original | New tier | Change |
|---|---|---|
| P1 statistical rigor | Decision Rules | Refined: cost/reversibility-aware, not binary |
| P2 mechanism hypothesis | B1 | Kept; clarified that contradicted mechanisms are rejected |
| P3 risk first | **A1** | Promoted to invariant |
| P4 adversarial mindset | **A4** | Promoted to invariant |
| P5 regime conditioning | C1 | Demoted: partially validated, panic untested |
| P6 survivorship haircut | C5 | Demoted: coarse heuristic |
| P7 no knob-tweaking | Decision Rules | Refined into cost-tier table |
| P8 mechanical execution | **A2 + B3** | Split: stops always (A2); trailing on winners default (B3) |
| P9 drawdown asymmetry | **A3** | Promoted to invariant |
| P10 correlation under stress | C8 (implicit) | Folded into edge erosion |
| P11 edge erosion | C8 | Retained as hypothesis |
| P12 crowded trades | C6 | Demoted: untested |
| P13 capacity awareness | C7 | Deprecated for our scale |
| P14 catalyst priority | C2 | **CONTRADICTED** — under revision |
| P15 pre-mortem | **A5** | Promoted to invariant |
| P16 per-sub-strategy attribution | C4 | Demoted: theoretical, impractical at our n |
| P17 loss aversion (stops) | A2 + B3 | Split |
| P18 regime detection IS strategy | C1 | Demoted alongside P5 |
| P19 slippage realism | D (calibration knob) | Lives in `slippage_model` |
| P20 process > outcome | **A8** | Promoted to invariant |

**Result**: 20 principles → 8 invariants + 5 strong defaults + 8 empirical hypotheses + 8 calibration knobs. Same content, honest about what's protected vs what's testable.

---

## When this conflicts with user instruction

Same as before — push back when:
- User cites n<10 evidence (retail) or n<30 (institutional) as basis
- User wants to skip walk-forward on a default-ON change
- User wants to violate Tier A invariants

But DON'T push back when:
- User wants to ship a Tier C hypothesis revision based on data (that's the whole point of C)
- User wants to override a Tier B default with explicit flag + audit note (the override pathway is the feature)
- User wants to retire principles that data has contradicted (C2, C3) — that's principle A4 (adversarial) working as designed

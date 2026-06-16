# Comparison Notes — `virattt/ai-hedge-fund` vs SwingTrade

**Date:** 2026-06-14 · **Status:** notes only, no code changes · **Source read:** GitHub `virattt/ai-hedge-fund` (`src/agents/*`, `risk_manager.py`, `portfolio_manager.py`, `warren_buffett.py`)

Purpose: capture what was inspected, what (if anything) is worth porting, and — more importantly — why most of it is the *wrong shape* for a multi-user, statistically-disciplined system. Written after an aborted attempt to port correlation-aware sizing (reverted; see "What was tried and reverted").

---

## 1. What the repo is

An **educational proof-of-concept**. It runs an ensemble of LLM "agents" over a ticker and prints buy/sell/hold signals. It does **not** trade, and the README is explicit that it is research/education only.

**19 agents, three groups:**
- **13 investor personas** (Buffett, Munger, Burry, Wood, Lynch, Ackman, Graham, Fisher, Damodaran, Pabrai, Druckenmiller, Taleb, Jhunjhunwala) — each reasons in one investor's style.
- **4 analytical agents** — Valuation, Sentiment, Fundamentals, Technicals.
- **2 management agents** — Risk Manager (position limits) → Portfolio Manager (final decision).

**Stack:** Python + TypeScript web app, Poetry, Financial Datasets API for data, LLM via OpenAI / Anthropic / Groq / DeepSeek / Ollama.

---

## 2. How its decisions are actually made (the important part)

Reading the code rather than the README:

- **Persona agents** (e.g. `warren_buffett.py`) compute a **deterministic rule-based score first** (ROE>15% +2, D/E<0.5 +2, op-margin>15% +2, moat/consistency points, book-value CAGR, etc.), then hand that score to an LLM as a *facts dict*. **The final bullish/bearish call and the confidence number are LLM-decided, not rule-derived.**
- **Portfolio Manager** (`portfolio_manager.py`) does **not** weight or vote. It compacts every agent's `{sig, conf}` into a prompt, adds the Risk Manager's allowed-actions/max-quantities, and lets **the LLM pick the action + share quantity per ticker**. Output schema: `{action ∈ buy/sell/short/cover/hold, quantity:int, confidence:0-100, reasoning:~100 chars}`.
- **Risk Manager** (`risk_manager.py`) is the only fully-deterministic piece: a 20% base position cap scaled by **annualized volatility** (≤15% vol → 1.25×, >50% vol → 0.5×, bounded 0.25–1.25×) and by **average correlation to other held positions** (≥0.80 → 0.70×, <0.20 → 1.10×), then floored by cash and existing exposure. Needs ≥5 aligned-return days for the correlation step.

**One-line summary:** deterministic facts → **LLM makes the call**. The numbers exist mainly to feed the prompt.

---

## 3. How SwingTrade differs (and why the difference matters)

| Dimension | ai-hedge-fund | SwingTrade |
|---|---|---|
| Final decision | LLM picks action + quantity | Deterministic `decision_engine` (Wilson-gated kills, regime gate, sleeve bypasses) |
| Signal/confidence | LLM-assigned | Rule-based 5-pillar score → conviction tier; no LLM in the verdict path |
| Validation | None (point estimates, no CI) | Wilson 95% LB, walk-forward, survivorship + slippage haircuts, n≥30 floor |
| Sizing | vol + correlation cap, LLM-bounded | `kelly_position_size` multiplier stack (regime × vix × drawdown × earnings × VaR × Sharpe) |
| Regime | implicit per-agent (macro persona) | explicit 4-regime model = the core of the system (principle 18) |
| Data | Financial Datasets API (paid) | EODHD + Zacks + Schwab (no new licenses — hard constraint) |
| Audience | single hypothetical book | **500+ users**, signals must be portfolio-blind |
| Attribution | none | per-(setup × regime × band × entry-quality × catalyst) |

The gap is philosophical: ai-hedge-fund is **LLM-narrative signal generation**; SwingTrade is **mechanical, statistically-validated, multi-user signal generation**. They optimize opposite things.

---

## 4. Verdict — what's worth porting

**Almost nothing, and that's the honest finding.**

| Idea | Port? | Why |
|---|---|---|
| LLM-as-portfolio-manager (picks action+quantity) | ❌ No | Violates mechanical-execution (P8) + Wilson gating (P1). SwingTrade's deterministic verdict is strictly better; this would be a regression. |
| LLM-decided signal/confidence | ❌ No | Un-backtestable, un-attributable confidence. Breaks P1/P4/P7. |
| Persona agents as **scoring inputs** | ❌ No | Re-skins factors SwingTrade already computes; adds LLM noise to the score path. |
| Financial Datasets API | ❌ No | New paid license — auto-rejected by the hard data-constraint. |
| Vol-bucket sizing | ❌ Already have it | `kelly_position_size` vix/drawdown/VaR multipliers are more sophisticated. |
| **Correlation-aware sizing** | ⚠️ Per-user only | Conceptually matches principle 10. **But** it must run on each user's own book, client-side — NOT baked into the universal signal/sizing path. See §6. |
| Persona "lens" as a **read-only display** | ⚠️ Cosmetic | Could re-frame existing deterministic outputs (Buffett=quality gate, Burry=mean-rev/short-interest, Druckenmiller=regime/macro, Taleb=CVaR/tail) as a per-ticker view. Adds zero edge; pure presentation. Low priority. |

---

## 5. Why the persona ensemble is weaker than it looks

It feels rigorous (13 famous investors!) but:
- The "edge" is the **deterministic factor scores**, which SwingTrade already has — the persona wrapper just adds an LLM that can hallucinate a verdict from them.
- No persona is validated. There is no Wilson CI, no walk-forward, no regime conditioning, no attribution. Under SwingTrade's principles 1/4/7 none of these would clear the bar to influence a live number.
- 13 correlated value/growth lenses ≈ one momentum/quality factor wearing 13 hats — not 13 independent signals.

It's a good **agent-design** reference (how to structure deterministic-facts-into-LLM, clean output schema). It is **not** an edge reference.

---

## 6. What was tried and reverted (cautionary record)

Attempted to port the Risk Manager's **correlation multiplier** into `kelly_position_size` (a `correlation_mult` reading `data/portfolio_state.json`). Built flag-OFF, tested, then **reverted in full** because it violates the system's defining constraint:

> **Signals must be portfolio-blind** (memory `feedback_signal_layer_portfolio_blind`, `project_signal_layer_portfolio_blind_2026_06_07`): never add a signal/sizing-path gate that reads `portfolio_state.json` — it's the owner's book, and the same signal feeds 500+ users. Shrinking everyone's suggested size because of *one owner's* NEM position is exactly the coupling the portfolio-blind flag exists to prevent.

Correlation-aware sizing is legitimate, but it belongs in a **per-user portfolio layer** that operates on each user's own positions — never in the universal scan. Logged here so the idea isn't re-attempted in the wrong place.

---

## 7. Bottom line

ai-hedge-fund is a clean, readable **multi-agent architecture demo**. As a source of *trading edge* or *system design for a validated multi-user product*, there is little to take — its core mechanisms (LLM-decided verdicts, owner-portfolio-aware sizing, unvalidated personas) are the opposite of what this codebase is built to enforce. Keep it as an agent-orchestration reference; do not port its decision logic.

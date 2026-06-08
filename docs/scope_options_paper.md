# Scope — Options Paper Trading

**Status:** SCOPED / NOT STARTED · **Owner:** phanirajgarimella · **Created:** 2026-06-08
**Registry:** `OPT-PAPER-1..5` in `data/open_items.json`
**Priority:** P2 — **gated** (see "Why P2, not now")

---

## Problem / today's state

The engine is a directional **equity** swing system. Every BUY/SELL/SHORT is a *stock*
plan (share-based entry/stop/T1/T2). We **use** options as a *signal input* (UOA / options
flow / IV rank / gamma → Catalyst pillar) but we never **hold contracts**. Concretely:

- `executor.py` has **zero** options code — it submits Alpaca **equity** bracket orders only.
- **Schwab is market-data-only** (trader endpoints removed; never re-add). So our options
  *data* source can't execute.

It is a **missing layer, not a blocker** — both halves already exist:
- **Data:** `schwab_client.get_chains` / `extract_chain_greeks` / `aggregate_greeks`.
- **Execution:** Alpaca paper supports options (`OptionLegRequest`,
  `GetOptionContractsRequest` in the SDK).

## Why P2, not now (the discipline gate)

1. **Equity signals aren't validated yet** — the 7 sleeves are in Phase-1 paper observation
   (and the 2026-06-08 audit found long-only PF only 1.13, with recent edge erosion).
   Expressing unvalidated direction through options compounds *two* unknowns: the signal
   edge **and** the options-structure choice.
2. **Options is where retail P&L dies** — not on direction, on **theta decay / IV crush**.
   The risk/reward of adding it before the underlying signal is proven is poor.
3. **Sequence:** validate equity sleeves out of Phase 1 → *then* add options as an
   *expression* of a proven signal.

## Hard constraints

- **PAPER ONLY** — never live (`feedback_paper_only_automation`, 2026-05-28). Alpaca paper
  is the venue.
- **Defined-risk ONLY** — long calls / debit (vertical) spreads. **No naked options, no
  undefined-risk shorts.** Premium-at-risk sized ≤ 1% of equity per position.
- **No new data license** — Schwab (already paid) supplies chains + Greeks.
- Three-horizon aware (`feedback_three_horizon_system`): swing → short-DTE calls/spreads;
  position/invest → longer-DTE / LEAPS. Don't gate by horizon, design for all three.

## Dependency

- **SCHWAB-REAUTH-PENDING** (registry, OPEN) — option Greeks freshness depends on Schwab
  re-auth. Contract selection (OPT-PAPER-2) needs live Greeks.

## Phases

| ID | P | Phase | Scope |
|---|---|---|---|
| OPT-PAPER-1 | P2 | Signal → structure mapper | Map an equity plan to a defined-risk options structure by setup family / R:R / IV rank (e.g. high-conviction 3:1 → debit call spread; clean trend → long call ~30–45 DTE). Underlying stop drives the thesis-invalidation, not the premium. |
| OPT-PAPER-2 | P2 | Contract selection | From the Schwab chain pick by delta / DTE / spread width; size on **premium-at-risk ≤1%**. Needs fresh Greeks (dep: SCHWAB-REAUTH). |
| OPT-PAPER-3 | P2 | Alpaca options orders | Construct + submit `OptionLegRequest` (single + vertical) in `executor.py`, PAPER only, behind the same `config.alpaca.paper` hard guard. |
| OPT-PAPER-4 | P2 | Options position tracking + P&L | Extend the portfolio tracker for contracts: premium, Greeks, theta decay, IV, DTE, mark-to-market. Today the tracker is share-P&L only. |
| OPT-PAPER-5 | P2 | Options-specific exits | IV-crush-around-earnings rule, time-stop before expiry, profit-take on the **contract** (not the underlying), assignment handling. |

## What this does NOT cover

- **Options backtesting** — needs historical options chains (expensive/heavy; EODHD options
  history is limited). This scope is **forward paper only** (we have live Schwab chains, so
  no history needed). A historical-options-backtest is a separate, much larger effort and is
  **not** in scope here.

## Acceptance criteria

1. A top-conviction equity BUY produces a **defined-risk** options ticket (structure +
   contract + premium-at-risk) — long call or debit spread, never naked.
2. The ticket submits to **Alpaca paper** and appears in the portfolio with live
   contract-level P&L (Greeks, theta, DTE).
3. Exits fire on the options-specific rules (time-stop / IV / contract profit-take), not
   just the underlying stop.
4. Live trading remains **impossible** (paper hard-guard intact).

## Recommended first slice (if/when un-gated)

Defined-risk only, on the **top-conviction T1/T2 names**, ≤1% premium-at-risk: OPT-PAPER-1
+ 2 + 3 as an MVP (map → select → paper-submit), with 4/5 fast-following so positions are
actually trackable and exitable. Do **not** start until equity sleeves promote out of
Phase 1.

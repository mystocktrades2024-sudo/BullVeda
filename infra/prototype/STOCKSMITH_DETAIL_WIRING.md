# Stocksmith V2 — Per-Ticker Detail Panel: Wiring Report

**File:** `infra/prototype/Stocksmith.html` · **Updated:** 2026-05-29
**Scope:** the 14-lens per-ticker detail panel ported from the Claude Design handoff
(`design_handoff_swingtrade_v2` / `src/lens-*.jsx`).

This documents **what is wired to live data and what is still illustrative, and why** — so the
next pass knows exactly which backend feed each placeholder is waiting on.

---

## 1. What shipped

- **Interaction model** matches the prototype: clicking a ticker (scanner row *or* home card) opens
  an **in-layout master·detail** view — the main pane becomes the `DetailPanel`, with a collapsible
  `ScanColumn` beside it (TOP/BUY/WATCH/ALL tabs, S/M/L/XL width, active-row highlight). **Focus** (`F`)
  collapses the scan column; `Esc`/◀ closes; breadcrumb + SWING/POSITION/INVESTMENT mode toggle live in
  the command bar. Keyboard `1–9 / t·o·i·m` switch lenses. It is **not** a modal overlay.
- **Typography** now matches the prototype exactly: `--mono` and `--sans` are both **Inter**; `.mono`
  is Inter + tabular numerals (the design never used a real monospace face).
- **All 14 lenses render:** Overview · Plan · Chart · Patterns · Technicals · SMC · Risk · Investment ·
  Earnings · Options · Portfolio · Tape · Track Record · ML Edge.
- **Verification:** full Babel compile + `renderToString` smoke-test pass for every lens across
  SWING/POSITION/INVESTMENT × radar/gauge/cone.

## 2. The data contract — `toDetailTicker()`

Every lens receives one `ticker` object built by `toDetailTicker(scannerRow, sym)`. It maps the **live
scan-universe row** (`mapScannerRows` → `data_screener.json`) into the shape the lenses consume.

**Fields that are LIVE (bound to the real scan row):**

| Field | Source |
|---|---|
| `symbol, name, sector` | scan row |
| `price, chg, chgAbs` | scan row (`price`, `pct_chg`) |
| `score, verdict, setupFamily, mechanism, cat` | scan row (`score`, `stage`, `setup`, `catalyst_tier`) |
| `pivot, stop, t1, t2` | scan row (`entry_lo`, `stop`, `t1`; `t2` extrapolated) |
| `rMultiple` | scan row (`rr`) |
| `pillars.technical / .fundamental` | scan row T·F·S·N dots |
| `pillars.catalyst` | derived from catalyst tier |
| `setupStats.{winRate, wilsonLB, n, pf}` | scan row (`regWR`, `wlb`, `n`, `pf` → setup-family stats) |
| `earnings.days` | scan row (`earn_days`); `earnings.date` derived |

**Fields that are DERIVED / ILLUSTRATIVE on the ticker object itself** (no field in the scan feed):
`exchange, industry, mcap, vol, avgVol, rsi, beta, shortFloat, insiderOwn, pe, fwdPe,
pillars.risk, pillars.edge, ml.magnitude.{lo,mid,hi}`. These carry sensible placeholder values so the
lenses render; they are **not** real per-ticker data yet.

> Everything below inherits from this contract: a lens cell is "LIVE" only if it traces back to a LIVE
> field above. Most lens content is **illustrative** because the underlying engine output
> (options chains, IV surface, order-block detector, MC VaR, 13F, ML model heads, 5y financials, …) is
> **not present in the scan feed**.

## 3. Per-lens status

### ✅ Mostly wired
| Lens | Wired | Illustrative (why) |
|---|---|---|
| **Overview** | verdict, score, 5 pillars, entry/stop/T1/T2, R-multiple, Wilson LB/n/PF, ER days, desk-read expectancy/edge, confluence pass-count, sleeve/gate cascade derived from real score+stats | Company blurb, valuation peers, ER beat-history, 24h deltas, pre-mortem text (no per-ticker fundamentals / bundle-diff feed) |
| **Plan** | full trade blueprint (entry/stop/T1/T2/R payoff curve), live sizing workbench (Kelly + size sliders → shares/NAV%/max-loss/R recompute), decision gates from Wilson LB + ER, time anatomy from holdDays+ER | Audit-log fill/post-fill rows, playbook IF/THEN tree (static rulebook), ATR (implied from stop distance) |
| **Risk** | ER pill, loss-cone σ labels (ml.magnitude), risk-cone $ ranges (price×σ), book β, Plan/Earnings cross-lens | VaR/CVaR/Sharpe table, Kelly tiles, 6×5 stress heatmap, liquidity ladder (need MC VaR + scenario + portfolio_state engines) |
| **Track Record** | edge KPIs + Wilson pill (setupStats.n/winRate/wilsonLB/pf), setup family, PF haircut | forward expectancy, edge-decay series, walk-forward holdout, forward MC dist (need rolling-window backtest keyed by setup) |
| **ML Edge** | magnitude cone P10/P50/P90 (ml.magnitude) | direction head, hit-net, calibration/Brier/ECE, SHAP features (need 3-head model output on ticker) |

### ◐ Partially wired (live anchors, illustrative detail)
| Lens | Wired | Illustrative (why) |
|---|---|---|
| **Technicals** | hero score, RSI(14), price rows in MA-stack + S/R ladder, statistical backbone (setupStats), the Call (pivot/stop/R) | all other indicators (MACD/Stoch/ADX/MFI/CMF/ATR/BB), MA levels, S/R confluence levels, RVOL/OBV, volume histogram, regime-edge matrix — **no indicator fields on the ticker shape** |
| **SMC** | hero liquidity (t2), order-block & sweep zones anchored to stop/pivot/t2, the Call | OB types/states, structure log (BoS/FVG/CHoCH), MTF screener — **no order-block detector / structure aggregator / LuxAlgo feed** |
| **Investment** | hero score, current price (value-scale marker + pullback), current peer row (symbol/name/pe/fwdPe/mcap) | value-gap DCF anchors, quality scorecard, 5y statements, cap-allocation, bull/bear, catalyst calendar — **need EODHD Fundamentals/Financials_5y + DCF engine** |
| **Earnings** | countdown days, ER date, implied move (ml.magnitude.hi), implied 1-day band | ESP, beat-probability, 8-quarter table, IV-at-ATM, IV crush — **need Zacks ESP + EODHD earnings-history** |
| **Portfolio** | hero sector, position-sim notional/max-loss (price+stop) | book equity curve, held positions, correlation matrix, factor exposure, sleep-test — **need portfolio_state.json wired into the panel** |
| **Tape** | short-float + insider-own hero pills, first catalyst row (ER days) | net-insider, sentiment dial, news timeline, Form-4 insider table, 13F holders — **need news/sentiment + insider + 13F feeds** |

### ○ Visual-only (illustrative throughout, one live anchor)
| Lens | Wired | Illustrative (why) |
|---|---|---|
| **Chart** | Monte-Carlo cone base + median seed from `ticker.price` | OHLC bars, EMA 9/21/50, HTF bias rows, annotations, 52w hi/lo — **need EODHD daily bars (6mo) + multi-TF aggregator** |
| **Patterns** | — | pattern-method matrix, Wyckoff, Elliott, MC tiles — **need pattern-detector ensemble + EW labeler** |
| **Options** | hero symbol/price/score/R:R, NBBO spot | IV rank, IV-HV, expected-move table, OI-by-strike, gamma profile, full chain, strategy/payoff/scenario — **need Schwab options chains + IV surface + Greeks** |

## 4. Why so much is illustrative (root cause)

The detail panel is fed **only** by the scan-universe row (`data_screener.json` via `mapScannerRows`).
That row carries the decision-critical numbers (score, verdict, plan levels, R:R, Wilson stats, ER days,
T·F·S·N) but **none of the deeper per-ticker engine payloads**. Each illustrative section is already
structured to consume its real feed the moment that feed is present on the `ticker` object — the work to
"wire" it is (a) add the field to the panel's data source and (b) replace the placeholder constant with
that field. No layout/visual rework is needed.

## 5. Recommended wiring order (highest ROI first)

1. **Fundamentals block → Investment + Overview valuation** — EODHD `Highlights`/`Fundamentals`/
   `Financials` already paid-for; populates pe/fwdPe/mcap/margins/ROIC/statements + value-gap.
2. **Portfolio lens → `data/portfolio_state.json`** — real book equity, held positions, correlation,
   factor exposure. This is local data already on disk.
3. **OHLC → Chart/Technicals** — EODHD daily bars (already the OHLCV source) → real candles, EMAs,
   RSI/MACD/ATR, S/R, RVOL/OBV. Unlocks the two "visual-only" technical lenses.
4. **ML heads → ML Edge / Risk cones / Track forward-expectancy** — surface the existing model's
   direction/hit-net/magnitude + rolling-window backtest per setup family.
5. **Insider / news / 13F → Tape** — reconnect the StockTwits/WSB/Congressional/Form-4 scrapers
   (already on the roadmap) + EODHD news sentiment.
6. **Options (Schwab chains + IV) → Options/Earnings** — largest surface, lowest urgency for swing;
   needs the Schwab options endpoints + an IV-surface builder.

> Per the no-new-data-license policy: every feed above is already in the paid stack
> (EODHD + Zacks + Schwab) or local — **no new subscription required**.

## 6. Implementation notes / guardrails honored

- All lens internals are namespaced per-lens (`Tch*/Cpt*/Smr*/Inv*/Eo*/Pt*/Tml*`) — no global collisions.
- Every `.toFixed()` is guarded; a ticker missing any field renders the placeholder, never crashes.
- No `Date.now()` / `Math.random()` in render (deterministic SVG ids + series), so renders are stable.
- ~960 lines of deduped lens CSS appended (75 base-class duplicates dropped against the existing shell).
- Shared atoms (SectionHeader/KpiTile/CrossLens/StateWrap/Gauge/Radar/Cone/WilsonPill/Pill/Sparkline)
  are reused, never redefined.

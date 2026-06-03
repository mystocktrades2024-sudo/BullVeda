// surface-help.jsx — Help & Documentation.
// Searchable reference for every surface, sub-tab, section, field, how to use it,
// and how it's computed. Left nav (grouped) + content pane with anchored cards.

const { useState: useHlp, useMemo: useHlpm } = React;

// ── documentation model ────────────────────────────────────────
// each entry: { id, group, title, what, use, computed, fields:[{k,d}], sub:[{t,d}] }
const HELP_DOCS = [
  // ===== GETTING STARTED =====
  { id: "start", group: "Getting Started", title: "How the terminal works",
    what: "A swing-trading research terminal. The left rail switches surfaces (market-wide views); clicking any ticker opens a 14-lens detail panel for that name.",
    use: "Start at Home for today's ranked scan → open a name → read its Bias → confirm across lenses → size in Risk → execute in Plan·Ticket.",
    computed: "All data is computed locally from your EODHD entitlement (history, fundamentals, news, calendar) + Schwab API (live quotes, options chains, greeks). No third-party signal feeds.",
    sub: [
      { t: "The decision flow", d: "Bias (should I look closer?) → Gate Cascade (is it ready?) → Plan·Ticket (how) → Risk (how much)." },
      { t: "Tiers", d: "Surfaces & lenses unlock by subscription tier (Free → Admin). Locked items show an upgrade gate. Admins set gating in User Management." },
      { t: "Kairos AI (⌘J)", d: "A context-aware assistant that reads your current screen/ticker and answers questions. Wired to a local Ollama model." },
    ] },
  { id: "buy", group: "Getting Started", title: "How do I read a candidate?",
    what: "Conviction converges across engines — a high-conviction name lights up on the scan, AI Predictions, SMC/Patterns, and Insider all at once.",
    use: "Home scan ranks Bullish-bias names → open a name → confirm Bias + 14-Lens Confluence → check AI Predictions (score ≥66, P(up) ≥55%) + SMC/Patterns (composite ≥72) → ensure R:R ≥2 and no earnings in-window → size from Risk.",
    computed: "Each engine publishes a bias; the cross-lens confluence heatmap (Overview §1) counts agreement. Every engine has a 1-year Track Record so you trust the ones with real edge.",
    fields: [
      { k: "Bias", d: "Bullish / Neutral / Bearish — the per-name rollup of all 14 lenses." },
      { k: "Edge score", d: "0–100 forward-edge; ≥66 = strongest bullish bias." },
      { k: "Composite", d: "SMC/Patterns 7-method confluence; ≥72 = GO." },
      { k: "R:R", d: "Reward-to-risk; the floor for a clean setup is 2.0." },
    ] },

  { id: "decide-combined", group: "Getting Started", title: "Decide: buy, sell or avoid — the combined read",
    what: "The whole terminal funnels to one decision. The rule is CONFLUENCE: you want several lenses agreeing before you act — one green signal is a watch, not a trade. A name leans BUY when bias, technicals, edge and structure line up with reward ≥ risk; it leans SELL / AVOID when those invert.",
    use: "Run the 5-step funnel: ① FIND (Scanner — filter Bullish, sort READY/EDGE) → ② JUDGE (Overview — Composite Bias ≥66, Thesis, Entry Checklist N/8) → ③ CONFIRM (Technicals + Patterns/SMC ≥60-72, AI P(up) ≥55%, Track Record Wilson LB ≥45% n≥30) → ④ READY (Plan — gates pass, R:R ≥2, no earnings in window, realistic fill holds) → ⑤ SIZE (Risk — half-Kelly, loss ≤ ~0.75% NAV). The Entry Checklist card shows this live; COMPLETE = clear, FORMING = watch.",
    computed: "The Composite Bias reconciles all 14 lenses into one 0-100 score with per-lens agreement and dissent. Entry Checklist passes a criterion when its lens clears the threshold. A SELL/AVOID is the mirror image — bearish bias, lenses dissenting, price below structure, edge unproven.",
    fields: [
      { k: "Lean BUY when", d: "Bias Bullish (≥66) · 3+ lenses agree · price above pivot/MAs · R:R ≥2 · setup edge proven (Wilson LB ≥45%) · no earnings inside the hold window." },
      { k: "Lean SELL / AVOID when", d: "Bias Bearish/Neutral · lenses dissent or break down · price below structure (BOS down, lost EMA stack) · R:R <2 · edge unproven (low Wilson / small n) · extended past entry (EQ = MISSED/EXTENDED)." },
      { k: "WATCH (don't act) when", d: "Mixed — some greens, some reds (Entry Checklist FORMING). Wait for the missing criteria to clear; set an alert instead of forcing it." },
      { k: "The shortcut", d: "Overview → Thesis 'Write the full thesis' and Kairos (⌘J) synthesize all of the above in plain English. Use them to confirm, then verify the 1-2 fields that matter most for that name." },
    ] },

  // ===== MARKETS =====
  { id: "home", group: "Markets", title: "Home · Today's Scan",
    what: "The cockpit: regime tape, the day's opportunity funnel, and the top ranked setups across the universe.",
    use: "Scan the TOP SETUPS list (ranked by edge) for a Bullish bias; click any row to open its detail.",
    computed: "Universe filtered → edge-ranked via the composite scan model (momentum × structure × confluence), regime-adjusted. Wilson lower-bound used so small-sample setups aren't over-ranked." },
  { id: "calendar", group: "Markets", title: "Calendar (Economic · Catalyst)",
    what: "Macro releases + earnings reporters in one calendar — the events that gate swing entries.",
    use: "Economic Releases tab = macro/FOMC; Earnings Catalysts tab = who reports this week with beat-prob tiers. Avoid entering right before a name's print unless intentional.",
    computed: "Macro from Trading Economics/FRED + CME FedWatch rate odds. Earnings from EODHD calendar → 6-signal beat model (history, run-up, volume, analyst, options, cohort) bucketed STRONG/SOLID/MODERATE.",
    sub: [
      { t: "Economic Releases", d: "Importance ●●●, actual vs forecast, FOMC implied odds, regime dashboard (yields/DXY/credit)." },
      { t: "Earnings Catalysts", d: "Reporter table (est/whisper/implied move/history/beat-prob) + the 6-signal model weights + tier calibration." },
    ] },
  { id: "internals", group: "Markets", title: "Market Internals",
    what: "Breadth and the risk regime — adv/decline, %>DMA, new highs-lows, and the VIX term structure.",
    use: "Confirm the tape supports your bias; a contango VIX = calm, a flip to backwardation = de-risk swing books.",
    computed: "Breadth computed across the EODHD /eod universe; VIX term from CBOE; regime tiles from yields/credit/USD." },

  // ===== DISCOVER =====
  { id: "signal-scanner", group: "Discover", title: "Signal Scanner · columns & sorting",
    what: "The full universe in one Eikon-style grid — every name scored across all pillars in 40+ columns. EVERY column header is clickable to sort (click again to reverse); the active column shows ▲/▼.",
    use: "Filter to Bullish, then sort by READY or EDGE to surface the most complete setups. The READY column (N/6) is the entry checklist at a glance — 6/6 = all criteria met. ★ a row to add it to your Watchlist; click a row to open its 14-lens detail; select rows for the bulk bar (watchlist, playbook, basket, CSV).",
    computed: "Each column is one signal. READY counts how many of 6 entry criteria pass: bias ≥66 · R:R ≥2.0 · RVOL ≥1.3× · Wilson LB ≥45% · RS ≥60 · earnings outside the hold window. EDGE = the composite factor grade.",
    fields: [
      { k: "Sorting", d: "Click any header to sort; click again to flip ascending/descending. Works on every column including BIAS, READY, SQ, T.F.S.N, MTF and SIGNALS." },
      { k: "READY (N/6)", d: "Entry-checklist score — green 6/6 (complete), amber 4–5 (forming), red <4. Sort by it to find the names closest to a clean entry." },
      { k: "EDGE · GRADES", d: "Composite A–F grade + 6 factor grades (Trend/Momentum/Setup/R:R/Value/Growth). Sort by the EDGE composite." },
      { k: "BIAS", d: "Bullish / Neutral / Bearish — the directional read. Informational, not advice." },
      { k: "Filters", d: "Result tabs + quick-filter pills + sector/setup dropdowns + search narrow the grid before you sort." },
    ] },
  { id: "screener-pick", group: "Discover", title: "Screener · how to pick the right stock",
    what: "The Signal Scanner is step 1 of the funnel — it narrows the whole universe (600+ names) to a handful worth opening. The goal isn't one 'best' metric; it's finding names where several signals already line up.",
    use: "A repeatable recipe: (1) set the side filter to BULLISH (or BEARISH to hunt shorts/avoids); (2) stack quick-filter pills — ★ Top 20% Score, 🔥 Breakout, ⚡ T1 Catalyst, 📅 ER ≤14D, 💰 Insider, 🔥 RVOL ≥1.5×; (3) narrow by Sector/Setup if you have a thesis; (4) sort by READY (most complete setups) or EDGE (best composite grade); (5) eyeball the key columns on the top rows, ★ the ones that pass to your Watchlist, then open them for the 14-lens detail.",
    computed: "Every name is scored nightly across all pillars; the grid is the raw output before presentation filtering. READY = how many of 6 entry criteria already pass; EDGE = composite factor grade.",
    fields: [
      { k: "Filter to a side", d: "BULLISH for longs, BEARISH for shorts/avoids — points the whole grid at the direction you're hunting." },
      { k: "Stack quick-filters", d: "Pills + sector/setup dropdowns narrow fast. A short list of strong names beats scrolling 600 rows." },
      { k: "Sort READY then EDGE", d: "READY 6/6 = all entry criteria met; EDGE A/B = strongest factor grades. The top rows are your shortlist." },
      { k: "Eyeball before opening", d: "On the shortlist scan Score (≥70) · R:R (≥2) · RVOL (≥1.3×) · W%LB (≥45) · ER (outside window) · SQ (FIRED/ON). Two+ greens makes it worth opening." },
      { k: "Don't over-filter", d: "If nothing passes, the tape may be weak — loosen one filter rather than force a marginal name. No setup is also a decision." },
    ] },
  { id: "momentum", group: "Discover", title: "Momentum",
    what: "Ranked leaderboard of the strongest names by relative strength vs SPY, with persistence & acceleration.",
    use: "RS Leaders = current strongest; Accelerating = earliest movers; Persistent = most durable. Click for detail.",
    computed: "126-day RS rank vs SPY, multi-timeframe (1W/1M/3M/6M); acceleration = RS slope; Sharpe-ranked." },
  { id: "ai", group: "Discover", title: "ML Predictions",
    what: "Multi-model ML forecast — a 3-head ensemble that produces a forward-edge Bullish/Neutral/Bearish per name.",
    use: "Ranked Board: sort by Edge / P(up) / Ensemble. Cross-Mode compares swing/position/invest P(up). Open a name for the mode-aware projection (targets/R:R/EV), price cone, feature importances & analogs. Track Record audits past calls.",
    computed: "Ensemble = 0.40·GradientBoost + 0.35·SequenceModel + 0.25·RegimeModel. P(up) is a calibrated classifier (Platt/isotonic). Price cone = Monte-Carlo. Backtest: AUC/hit/Brier/Sharpe out-of-sample.",
    fields: [
      { k: "Edge score", d: "0–100 forward edge. ≥66 = Bullish, ≤40 = Bearish, else Neutral." },
      { k: "P(up)", d: "Calibrated probability the name is higher in 21 days. ≥55% supports a long." },
      { k: "Ensemble vote", d: "3 dots = the 3 model heads; all green = unanimous direction." },
      { k: "Price cone", d: "Monte-Carlo P10–P90 band over 1W/1M/3M — the realistic range, not a point guess." },
      { k: "Feature importance", d: "Signed SHAP values: what's pushing the call up (green) or down (red)." },
      { k: "Analogs", d: "Closest historical setups and how they resolved over 21d." },
      { k: "AUC / Brier", d: "Backtest quality: AUC>0.5 = real discrimination; lower Brier = better calibration." },
    ],
    sub: [
      { t: "Ranked Board", d: "All names by ML edge; bias, score, P(up), ensemble vote, 3M target, confidence." },
      { t: "Forecast detail", d: "Bias hero, Monte-Carlo price cone, 3 model heads, SHAP feature importances, historical analogs." },
      { t: "Track Record", d: "1-year resolved predictions marked hit/fail at +21d." },
      { t: "Model Accuracy", d: "Calibration (predicted vs realized) + backtest grid." },
    ] },
  { id: "earnings-ai", group: "Discover", title: "Earnings AI",
    what: "Beat-probability predictions for every upcoming earnings call, with a transparent track record.",
    use: "Predictions view = active calls by tier; Track Record = 1-year hit/miss scorecard + calibration.",
    computed: "6-signal composite (historical beat rate 25 · price run-up 20 · volume accumulation 15 · analyst positioning 15 · options flow 15 · sector co-movers 10) → 0-100 → STRONG/SOLID/MODERATE; outcomes logged for calibration." },
  { id: "options", group: "Discover", title: "Options Flow",
    what: "Smart-money options tape + ranked option trade ideas + a 1-year track record.",
    use: "Flow = unusual activity tape; Ideas = ranked tickets (set account size + Kelly fraction for auto-sizing); Track Record = resolved hot/failed.",
    computed: "Flow from Schwab chains (volume vs OI, sweeps, P/C, IV-rank). Ideas score conviction × R:R × IV-regime; size = fractional-Kelly capped 5%/idea.",
    fields: [
      { k: "IV-Rank", d: "Where current implied vol sits in its 1y range. <45 = buy premium; 45–70 = spread; >70 = don't buy naked." },
      { k: "Debit / Max loss", d: "What you pay = your defined risk. Never average down a long option." },
      { k: "POP", d: "Probability of profit at expiry from the option's delta." },
      { k: "Why-not", d: "The single biggest disqualifier per idea: earnings-in-window, below-R:R, IV-crush, wide spread." },
      { k: "Size", d: "Auto-sized contracts from each idea's Kelly edge × your fraction, hard-capped 5%/idea. Set account size in the bar." },
      { k: "Conviction", d: "1–5 dots; the strongest are ≥4 with R:R ≥ 2." },
    ],
    sub: [
      { t: "Options Flow", d: "Unusual-activity tape: sweeps, blocks, P/C, IV-rank per print." },
      { t: "Options Ideas", d: "Ranked tickets with structure, debit, R:R, POP, IV-rank, catalyst, Why-not, Kelly size." },
      { t: "Track Record", d: "1-year resolved tickets marked hot / failed / flat with net R." },
    ] },
  { id: "insider", group: "Discover", title: "Insider Trading",
    what: "Form-4 cluster analysis — open-market insider buys/sells, C-suite weighted, with a track record.",
    use: "Sort by Conviction; cluster buys & C-suite buys are the strongest tells. Track Record shows 1-year hit rate.",
    computed: "EODHD /insider-transactions (SEC Form 4). Conviction 0-100 = role seniority × cluster corroboration × Δ-held × $ size × buying-into-weakness. 10b5-1 planned sells scored as noise." },
  { id: "smc-patterns", group: "Discover", title: "SMC / Patterns",
    what: "Market-wide structure scanner — names with active SMC + multi-method pattern confluence.",
    use: "Structure Board ranks by composite (7 methods aligned); ≥72 = GO. Click → the per-ticker Patterns lens. Track Record audits the confluence edge.",
    computed: "Composite 0-100 = how many of 7 methods (Wyckoff·Elliott·Fibonacci·Volume Profile·SMC·Classical·Harmonic) agree on direction. High-confluence (6+) cohort tracked separately.",
    fields: [
      { k: "Composite", d: "0–100 confluence score. ≥72 = GO, 55–71 = WATCH, <55 = PASS." },
      { k: "Methods (7)", d: "Dots show how many of the 7 theories align on the same direction. 6+ = stacked." },
      { k: "SMC tag", d: "The active smart-money structure: Bull BOS, CHoCH, OB retest, FVG fill, liquidity sweep, OTE zone." },
      { k: "Pattern", d: "The detected classical/harmonic pattern (VCP, cup & handle, Gartley, Wolfe…)." },
      { k: "R:R", d: "Reward-to-risk from the structure's target and invalidation." },
    ],
    sub: [
      { t: "Structure Board", d: "All names with active structure, ranked by composite; columns for Wyckoff/Elliott/SMC/Pattern." },
      { t: "Track Record", d: "1-year resolved setups marked hit/fail; high-confluence (6+) cohort hit-rate highlighted." },
    ] },

  // ===== MANAGE =====
  { id: "myportfolios", group: "Manage", title: "My Portfolios",
    what: "Your own editable, multi-portfolio book — track holdings, P&L, risk, performance and a trade journal.",
    use: "Add holdings (ticker/qty/cost/date/notes), switch portfolios via the dropdown, set your risk profile. Five tabs: Holdings · Allocation · Risk Analytics · Performance · Journal.",
    computed: "Prices simulated (overridable per holding); P&L = mark vs cost; risk gauges vs your tolerance caps; Performance equity walks realized closes → marks open positions; saved to browser localStorage.",
    fields: [
      { k: "Add holding", d: "Ticker, qty, avg cost, buy date, type, target/stop, account, notes. Inline-edit qty/cost/price in the table." },
      { k: "Risk profile", d: "Conservative / Moderate / Aggressive — sets the caps your holdings are gauged against." },
      { k: "Expectancy (R)", d: "Average R-multiple per closed trade; positive = a real edge." },
      { k: "HHI", d: "Concentration index; >0.25 = too concentrated in one name." },
    ],
    sub: [
      { t: "Holdings", d: "Editable positions table with live P&L, weight, inline price override, cash balance." },
      { t: "Allocation", d: "Sector / asset-type / position-weight breakdown bars with a concentration flag." },
      { t: "Risk Analytics", d: "Beta, top-weight, volatility vs your profile caps; VaR/CVaR, drawdown, HHI, sector exposure." },
      { t: "Performance", d: "Total return, realized/unrealized, win rate, expectancy, equity curve, monthly returns, R-distribution, sector attribution." },
      { t: "Journal", d: "Structured trade log (buy/sell, R-multiple) + free-form notes." },
    ] },
  { id: "automated", group: "Manage", title: "Automated Trade",
    what: "The firm/strategy book cockpit — six sub-tabs consolidating the book's operations.",
    use: "Positions = open book; the rest are the book's analytics, journal, watchlist, risk and alerts in one place.",
    computed: "Realized fills + marked-open positions (Schwab quotes); analytics per the underlying sections.",
    sub: [
      { t: "Positions", d: "Open book with P&L, R-multiple, heat per position, equity curve." },
      { t: "Performance", d: "Equity vs SPY, drawdown, monthly returns, sleeve & sector attribution, R-distribution." },
      { t: "Trade Journal", d: "Trade log with R-analytics and behavioral attribution." },
      { t: "Watchlist", d: "Starred + manually-added names with bias reads." },
      { t: "Risk · Exposure", d: "Book-level loss cones, Kelly, VaR/CVaR, 6×5 stress, liquidity ladder." },
      { t: "Alerts", d: "Real-time triggered conditions (price / signal / earnings)." },
    ] },

  // ===== REVIEW =====
  { id: "track-record", group: "Review", title: "Track Record",
    what: "System-wide signal accountability — did our calls work? Audits all 8 sources across 23 horizons.",
    use: "Heatmap shows which engine has edge at which holding period (the Peak column = optimal hold). Leaderboard ranks sources; Ledger lists every call; Calibration/Regime/Equity views add depth.",
    computed: "Every published call logged at signal time, scored forward (D1–M12), direction-aligned, edge-vs-SPY. Only matured horizons enter stats; t-stat flags whether edge is real vs noise.",
    fields: [
      { k: "Edge vs SPY", d: "Return of the call minus SPY over the same window — the true alpha, not just up/down." },
      { k: "Peak / optimal hold", d: "The horizon where a source's edge is largest — how long to hold its signals." },
      { k: "t-stat", d: "≥2 ≈ the edge is statistically distinguishable from luck at this sample size." },
      { k: "Half-life", d: "Where the decay curve crosses zero — hold past it and the edge is gone." },
      { k: "Matured vs maturing", d: "Only calls old enough for a horizon to complete enter the stats; younger ones show partial paths." },
    ],
    sub: [
      { t: "Heatmap", d: "Source × horizon grid (green→red) with the optimal-hold Peak column." },
      { t: "Leaderboard", d: "Sources ranked by edge with hit-rate, profit factor, best/worst, significance." },
      { t: "Decay / Ledger / Calibration / Regime / Equity", d: "Edge-by-horizon curves · every call · predicted-vs-realized · bull/chop/bear · cumulative equity if followed." },
    ] },
  { id: "performance", group: "Review", title: "Performance",
    what: "The firm book's P&L performance — equity vs SPY, drawdown, monthly returns, attribution, R-distribution.",
    use: "Review realized + open P&L and what's driving it (by sleeve & sector).",
    computed: "Equity from realized fills + marked positions; Sharpe/Sortino on daily returns (rf 4.3%); attribution net of slippage. (Your-data version is in My Portfolios → Performance.)" },
  { id: "journal", group: "Review", title: "Trade Journal & Playbook",
    what: "Trade log with R-analytics & behavioral attribution (Journal) and the regime-activation rulebook (Playbook).",
    use: "Log trades and lessons; the Playbook defines which setups activate in which regime, with hard gates & sizing.",
    computed: "R-multiples vs your risk; behavioral tags aggregated; Playbook gates are rule-based on regime + setup stats." },

  // ===== THE 14 LENSES =====
  { id: "lens-signals", group: "The 14 Lenses (per ticker)", title: "Per-lens signals · lean buy vs lean sell",
    what: "What each lens tells you and the specific reading that leans bullish (consider buy) vs bearish (consider sell/avoid). Use this to CONFIRM the Overview bias — no single lens decides; you want agreement across several.",
    use: "Open any name → step the lenses (or read the 14-Lens Confluence heatmap on Overview). Count the greens vs reds. The Entry Checklist + Composite Bias already roll these up, but this is what's underneath each one.",
    computed: "Each lens scores 0-100 from its own real signals (EODHD / Schwab / computed). The Composite Bias weights them; dissenting lenses are flagged.",
    fields: [
      { k: "1 · Overview · Bias", d: "BUY-lean: composite ≥66, broad green confluence, gates passing. SELL-lean: ≤45, lenses dissent, gates blocked." },
      { k: "2 · Plan · Ticket", d: "BUY-lean: R:R ≥2, entry just above pivot, realistic fill still ≥2R. SELL-lean: R:R <2, price extended past entry (EQ MISSED), or stop too wide." },
      { k: "3 · Chart", d: "BUY-lean: higher-highs/higher-lows, price above the EMA stack, holding support. SELL-lean: lower-highs/lower-lows, below the stack, breaking support." },
      { k: "4 · Technicals", d: "BUY-lean: EMA 8>21>50>200, RSI 50-70, MACD+, RVOL ≥1.3×. SELL-lean: stack inverting, RSI <45 or >80 (exhausted), MACD−, volume drying up." },
      { k: "5 · Patterns", d: "BUY-lean: bullish confluence ≥72 (Wyckoff accumulation, Elliott wave 3, VCP). SELL-lean: distribution, completed 5-wave/ending diagonal, failed pattern." },
      { k: "6 · SMC", d: "BUY-lean: bullish BOS, demand order-block holding, FVG support, price in discount. SELL-lean: bearish CHoCH, supply OB rejecting, price in premium." },
      { k: "7 · Investment · Value", d: "BUY-lean: positive margin-of-safety, quality A/B, reasonable valuation. SELL/avoid-lean: trades well above fair value, deteriorating quality." },
      { k: "8 · Earnings", d: "BUY-lean: report OUTSIDE the hold window, positive ESP/beat-probability. SELL/caution-lean: print inside the window (gap + IV-crush risk) — size down or wait." },
      { k: "9 · Risk", d: "GO-lean: stop ≤ ~0.75% NAV, half-Kelly size fits, low correlation to book. NO-lean: VaR/drawdown too large, position would over-concentrate the book." },
      { k: "10 · Options", d: "BUY-lean: IV cheap (long-premium edge), positive dealer GEX = stable, price above the put wall. SELL/caution-lean: IV rich, negative GEX = whippy, below the γ-flip." },
      { k: "11 · Tape · Flow", d: "BUY-lean: insider cluster buys, rising institutional ownership, positive news sentiment. SELL-lean: insider selling, 13F distribution, negative/again-priced news." },
      { k: "12 · AI Edge", d: "BUY-lean: P(up) ≥55% with tight CI, positive hit-net, calibrated. SELL-lean: P(up) <50%, negative hit-net, low confidence / high disagreement." },
      { k: "Cross-mode tell", d: "A name bullish on Swing but bearish on Invest (or vice-versa) is a TRADE, not an investment — match the lens read to your chosen mode." },
    ] },

  { id: "lens-overview", group: "The 14 Lenses (per ticker)", title: "Overview · Bias",
    what: "The single per-name decision: Bullish/Neutral/Bearish with a confidence score and the cross-lens confluence.",
    use: "Read the bias → §1 14-Lens Confluence heatmap (how many lenses agree) → §3 Gate Cascade (is it ready?).",
    computed: "Bias = weighted rollup of all 14 lenses; gate cascade is a pass/block checklist on entry conditions.",
    fields: [
      { k: "Bias badge", d: "Bullish, Neutral, or Bearish — the headline directional read. Informational, not advice." },
      { k: "Confidence", d: "0–100, how strongly the lenses agree. >70 = high conviction." },
      { k: "§0 Company Snapshot", d: "Who they are, why it matters now — the quant read in one line." },
      { k: "§1 14-Lens Confluence", d: "Heatmap of all 14 lenses' votes; green column = broad agreement = trust the bias." },
      { k: "§2 Sleeve Attribution", d: "Which strategy sleeve (Continuation BO, Pullback, Range…) this setup belongs to." },
      { k: "§3 Gate Cascade", d: "The entry-readiness checklist — each gate (close > pivot, RVOL, no earnings) shows pass/block." },
      { k: "§4 24h Delta", d: "What changed in the bias/score since yesterday." },
      { k: "§5 Pre-Mortem", d: "The single biggest way this trade fails — read before entering." },
    ] },
  { id: "lens-plan", group: "The 14 Lenses (per ticker)", title: "Plan · Ticket",
    what: "The execution-ready ticket: exact entry, stop, targets, and the Schwab order.",
    use: "When the bias is Bullish and gates clear, the pre-filled ticket and a sizing cascade are here for your review.",
    computed: "Entry/stop from structure; size = half-Kelly × regime × VIX scalar; targets from measured move.",
    fields: [
      { k: "Entry", d: "Trigger price — usually a close above the pivot with volume confirmation." },
      { k: "Stop", d: "Invalidation level (below structure / last higher-low). Defines your 1R risk." },
      { k: "T1 / T2", d: "Targets from the measured move; T1 is the conservative objective." },
      { k: "Sizing cascade", d: "Half-Kelly base × regime scalar × VIX adjustment → share count. Never overrides the per-trade risk cap." },
      { k: "Order ticket", d: "The exact Schwab order (STOP-LIMIT / OCO) ready to send." },
      { k: "R:R", d: "Reward-to-risk = (target − entry) ÷ (entry − stop). Floor is 2.0 for a clean setup." },
    ] },
  { id: "lens-patterns", group: "The 14 Lenses (per ticker)", title: "Patterns (14 theory sub-tabs)",
    what: "14 pattern-theory sub-tabs: Confluence cockpit + Wyckoff, Elliott, Fibonacci, Volume Profile, Ichimoku, TD Sequential, Classical, Harmonic, Wolfe, Candlesticks, Alt-charts, Gann, Monte Carlo.",
    use: "Start on Confluence (the weighted composite + price map). Use the layout switch (Chart-led / Split / Dossier) and the section jump-nav. Drill into any theory tab to see it annotated on real bars.",
    computed: "Confluence engine = 0.40 Wyckoff + 0.35 Elliott + 0.25 Fibonacci, gated at a signal threshold; each theory annotates real OHLCV bars.",
    sub: [
      { t: "Confluence", d: "Bias hero + clickable theory board + true-to-scale price map + weighted composite + MTF consensus + ML probability." },
      { t: "Wyckoff", d: "Accumulation/distribution events (PS·SC·AR·ST·Spring·SOS·LPS) on bars, A–E phase track, P&F targets." },
      { t: "Elliott Wave", d: "Impulse 1-5 + A-B-C, the 9 degrees, 3 hard rules + guidelines, fib targets, alternate counts. Degree buttons redraw." },
      { t: "Fibonacci", d: "Retracement grid + extensions + confluence clusters where levels stack with structure." },
      { t: "Volume Profile", d: "POC / VAH / VAL value area, HVN/LVN nodes, auction acceptance targets." },
      { t: "Ichimoku", d: "Tenkan/Kijun, forward-projected Kumo cloud, Chikou span, 5-signal checklist." },
      { t: "TD Sequential", d: "Setup (1–9) + Countdown (1–13) exhaustion timing, TDST levels." },
      { t: "Classical / Harmonic / Wolfe", d: "Chart patterns w/ measured moves · Gartley XABCD w/ fib validation · Wolfe 5-point + EPA line." },
      { t: "Candlesticks / Alt-charts / Gann / Monte Carlo", d: "Reversal candles w/ reliability · Renko/Kagi/Heikin-Ashi · Gann fan + Sq-9 · simulated outcome cone." },
    ] },
  { id: "lens-risk", group: "The 14 Lenses (per ticker)", title: "Risk (per-ticker)",
    what: "Per-ticker risk: §1 Loss-Distribution Cones · §2 Live Kelly · §3 VaR·CVaR·Sharpe · §4 Stress 6×5 · §5 Liquidity Ladder.",
    use: "Size the position and know the downside before entry. Read the Kelly section for share count, the cone for the realistic loss range.",
    computed: "Cones from 60d vol; Kelly from current edge + portfolio_state; VaR/CVaR 1d/10d; stress = scenario × outcome MoS grid.",
    fields: [
      { k: "§1 Loss-Distribution Cones", d: "1σ/2σ/3σ projected loss range over 1 day, from 60-day realized volatility." },
      { k: "§2 Live Kelly", d: "Optimal position fraction from current edge; the terminal uses HALF-Kelly for survival." },
      { k: "§3 VaR · CVaR · Sharpe", d: "VaR = normal-bad-day loss (95%); CVaR = average loss beyond VaR (tail); Sharpe = risk-adjusted return." },
      { k: "§4 Stress 6×5 Heatmap", d: "6 shock scenarios × 5 outcomes; each cell = margin-of-safety in that scenario." },
      { k: "§5 Liquidity Ladder", d: "Bid/ask depth + ADV slippage estimate + book-beta after the fill." },
    ] },
  { id: "lens-others", group: "The 14 Lenses (per ticker)", title: "Other lenses",
    what: "Chart (full OHLC + indicators), Technicals (10-section discipline), SMC (order blocks/FVG/BOS), Investment·Value (intrinsic value, margin of safety), Earnings (ER countdown + implied-move cone + PEAD), Options (IV/flow/payoff), Tape·Flow (prints/blocks/13F), AI Edge (3-head model forecast).",
    use: "Each answers one question; the Bias lens rolls them up. Use the section jump-nav at the top of every lens.",
    computed: "Per the source noted in each section header (EODHD, Schwab, computed factor proxies)." },

  { id: "gex", group: "The 14 Lenses (per ticker)", title: "Dealer Gamma (GEX) · plain English",
    what: "Options dealers (the 'house' that sells options) must hedge by trading the actual stock — and that hedging moves price in predictable ways. The GEX panel (Options lens → Context tab) reads which way they're being forced to trade, so you know whether today is a range day or a trend day.",
    use: "10-second read for a STOCK trader: (1) Green 'NET GEX' = range day → fade the edges, breakouts tend to fail. Red = trend day → breakouts run, don't fade. (2) Trade between the Put wall (support) and Call wall (resistance). (3) Watch the γ-flip — cross below it and calm flips to volatile. You never trade TO max pain — use the mode (fade vs follow) and the walls (support/resistance).",
    computed: "Computed from the option chain: net dealer gamma = Σ(open interest × gamma) per strike (Schwab chain in production). Max pain = strike where the most option premium expires worthless. Walls = the biggest open-interest strikes. Informational only — a tendency strongest into Friday/monthly expiry, not a guarantee; news & earnings override it.",
    fields: [
      { k: "NET GEX", d: "The headline. Green/positive = dealers DAMPEN moves (buy dips, sell rips) → choppy, range-bound. Red/negative = dealers AMPLIFY moves → trendy, breakouts run." },
      { k: "Call wall", d: "The biggest call open-interest strike — acts as RESISTANCE/ceiling (dealers sell into it). A take-profit / short-the-rip zone." },
      { k: "Put wall", d: "The biggest put open-interest strike — acts as SUPPORT/floor (dealers buy to cushion). A dip-buy / stop-below zone." },
      { k: "γ-flip", d: "The strike where the regime flips. Above it = stabilizing (fade-friendly); a decisive break below = amplifying (expect bigger, faster moves)." },
      { k: "Max pain", d: "The price where the most options expire worthless. Near expiry price tends to drift toward it — a weak magnet, NOT a target or a price ceiling." },
    ] },

  // ===== ADMIN =====
  { id: "admin", group: "Admin", title: "Settings · Users · Status",
    what: "Settings (your prefs + capabilities + session audit), User Management (users + tier-access matrices), System Status (data-pipeline + Supabase health).",
    use: "Set personal preferences in Settings; admins gate surfaces/lenses/sections per tier in User Management; monitor feeds in System Status.",
    computed: "Preferences persist to localStorage; capabilities from the RBAC matrix; pipeline/health metrics from status endpoints." },
];

const HELP_GROUPS = [...new Set(HELP_DOCS.map(d => d.group))];

function SurfaceHelp() {
  const [q, setQ] = useHlp("");
  const [active, setActive] = useHlp("start");
  const ql = q.trim().toLowerCase();
  const matches = useHlpm(() => !ql ? HELP_DOCS : HELP_DOCS.filter(d =>
    (d.title + " " + d.what + " " + (d.use || "") + " " + (d.computed || "") + " " + (d.sub || []).map(s => s.t + s.d).join(" ") + " " + (d.fields || []).map(f => f.k + f.d).join(" ")).toLowerCase().includes(ql)
  ), [ql]);
  const shown = ql ? matches : HELP_DOCS;
  const cur = HELP_DOCS.find(d => d.id === active) || HELP_DOCS[0];

  const jump = (id) => {
    setActive(id);
    const el = document.getElementById("help-" + id);
    const body = el && el.closest(".help-content");
    if (el && body) { const t = el.offsetTop - 12; const start = body.scrollTop, dist = t - start; let t0 = null; const step = ts => { if (t0 === null) t0 = ts; const p = Math.min(1, (ts - t0) / 280); body.scrollTop = start + dist * (p < .5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2); if (p < 1) requestAnimationFrame(step); }; requestAnimationFrame(step); setTimeout(() => { body.scrollTop = t; }, 320); }
  };

  return (
    <div className="surface wsx wsx--cy help">
      <div className="wsx-hdr">
        <div className="wsx-hdr-l">
          <div className="wsx-eyebrow mono">HELP · DOCUMENTATION</div>
          <h1 className="wsx-title mono">Help &amp; Reference</h1>
          <div className="wsx-sub mono dim2">every surface, sub-tab, section &amp; field · how to use it · how it's computed · search anything</div>
        </div>
        <div className="wsx-hdr-r"><span className="mono dim2">⌘J · ask Kairos for anything not here</span></div>
      </div>

      <div className="help-search">
        <svg viewBox="0 0 16 16" width="14" height="14" fill="none"><circle cx="7" cy="7" r="4" stroke="currentColor" strokeWidth="1.4" /><line x1="10" y1="10" x2="14" y2="14" stroke="currentColor" strokeWidth="1.4" /></svg>
        <input placeholder="Search docs — e.g. 'Kelly', 'VaR', 'composite', 'how to read'…" value={q} onChange={e => setQ(e.target.value)} />
        {q && <button className="help-clear" onClick={() => setQ("")}>✕</button>}
      </div>

      <div className="help-layout">
        <div className="help-nav">
          {HELP_GROUPS.map(g => {
            const items = shown.filter(d => d.group === g);
            if (!items.length) return null;
            return (
              <div key={g} className="help-nav-grp">
                <div className="help-nav-h mono">{g}</div>
                {items.map(d => (
                  <button key={d.id} className={`help-nav-i ${!ql && active === d.id ? "is-on" : ""}`} onClick={() => jump(d.id)}>{d.title}</button>
                ))}
              </div>
            );
          })}
          {ql && shown.length === 0 && <div className="help-nav-empty mono dim2">No matches.</div>}
        </div>

        <div className="help-content">
          {shown.length === 0 && <div className="help-empty mono dim2">Nothing matches "{q}". Try a feature name, metric, or "how to…".</div>}
          {shown.map(d => (
            <div key={d.id} id={"help-" + d.id} className="help-card">
              <div className="help-card-grp mono dim2">{d.group}</div>
              <h2 className="help-card-t">{d.title}</h2>
              <div className="help-row"><span className="help-row-l mono">WHAT</span><span className="help-row-d">{d.what}</span></div>
              {d.use && <div className="help-row"><span className="help-row-l mono">HOW TO USE</span><span className="help-row-d">{d.use}</span></div>}
              {d.computed && <div className="help-row"><span className="help-row-l mono help-row-l--c">HOW IT'S COMPUTED</span><span className="help-row-d">{d.computed}</span></div>}
              {d.fields && <div className="help-fields">{d.fields.map((f, i) => <div key={i} className="help-field"><span className="help-field-k mono">{f.k}</span><span className="help-field-d">{f.d}</span></div>)}</div>}
              {d.sub && <div className="help-subs">{d.sub.map((s, i) => <div key={i} className="help-sub"><span className="help-sub-t">{s.t}</span><span className="help-sub-d dim2">{s.d}</span></div>)}</div>}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

window.SurfaceHelp = SurfaceHelp;
window.HELP_DOCS = HELP_DOCS;

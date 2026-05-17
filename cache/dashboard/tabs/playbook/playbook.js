// tabs/playbook/playbook.js — Static playbook rendering (rules of the system).
// Extracted from dashboard.html:8632-8890 (2026-05-09).
// 100% static markup — no DATA reads. Pure documentation surface.

import { $ } from '../../core/shared.js';

export function render() {
  const sec = (icon, title, sub, body) => `
    <div class="pb-section">
      <div class="pb-sec-h"><span class="pb-ico">${icon}</span><div class="pb-sec-t"><div class="pb-sec-name">${title}</div>${sub ? `<div class="pb-sec-sub">${sub}</div>` : ''}</div></div>
      <div class="pb-sec-body">${body}</div>
    </div>`;

  const hero = `
    <div class="pb-hero">
      <div class="pb-hero-l">
        <div class="pb-hero-tag">SWINGTRADE PLAYBOOK · v2026-05</div>
        <div class="pb-hero-h">The complete rulebook — every gate, score, and tier the engine evaluates.</div>
        <div class="pb-hero-narr">Three horizons (Swing 2-14d · Position 3-8w · Invest 12-24mo) sharing a 5-pillar score (max 100), 4-regime classification, conviction tiers, and 6 strategy enhancements. Rules are config-driven — see <code>config/config.json</code>.</div>
      </div>
      <div class="pb-hero-r">
        <div class="pb-hero-stat"><div class="v">5</div><div class="lbl">Pillars</div></div>
        <div class="pb-hero-stat"><div class="v">4</div><div class="lbl">Regimes</div></div>
        <div class="pb-hero-stat"><div class="v">6</div><div class="lbl">Tier 1 Sigs</div></div>
        <div class="pb-hero-stat"><div class="v">3</div><div class="lbl">Horizons</div></div>
      </div>
    </div>`;

  const pillars = sec('📊', '5-Pillar Scoring',
    `Each ticker scored 0-100 from five independent pillars. Regime weights and setup-family shifts apply on top.`,
    `<table class="pb-tbl">
       <thead><tr><th>Pillar</th><th class="r">Max</th><th>What it measures</th></tr></thead>
       <tbody>
         <tr><td><b style="color:var(--pass)">Technicals</b></td><td class="r mono">35</td><td>EMA stack 8/21/50/200 · ADX trend strength · RSI/MACD/StochRSI/MFI · S/R structure · weekly bonus · TTM squeeze breakout</td></tr>
         <tr><td><b style="color:var(--info)">Catalyst &amp; R:R</b></td><td class="r mono">20</td><td>Catalyst tier (T1 PEAD/UOA/VCP/52wk · T2 squeeze/EMA pullback/insider · T3 social) · entry R:R · scenario expectancy</td></tr>
         <tr><td><b style="color:var(--accent)">RS + Sector</b></td><td class="r mono">20</td><td>Relative strength rank (63d vs SPX) · sector outperformance · weekly EMA alignment</td></tr>
         <tr><td><b style="color:var(--warn)">Smart Money</b></td><td class="r mono">15</td><td>News momentum (EODHD NLP) · insider net + cluster · short interest / squeeze risk · institutional flow</td></tr>
         <tr><td><b style="color:var(--ink-1)">Quality Gate</b></td><td class="r mono">10</td><td>Revenue growth · margins · ROE/ROA · PEG · debt/equity · gate fails block long-term BUY</td></tr>
       </tbody>
     </table>
     <div class="pb-callout">Bonus cap: ±5 pts (Elliott Wave + squeeze breakout + weekly alignment). Final score normalized to 0-100.</div>`);

  const regimes = sec('🌐', '4-Regime Classification',
    `Detected nightly from SPY/QQQ vs EMA50/200 + VIX + market breadth. Drives BUY threshold, position size cap, and pillar weight shifts.`,
    `<table class="pb-tbl">
       <thead><tr><th>Regime</th><th>Trigger</th><th class="r">BUY ≥</th><th class="r">Max Size</th><th>Pillar shift</th></tr></thead>
       <tbody>
         <tr><td><b class="pb-pill bull">Risk-On Trending</b></td><td>SPY+QQQ above EMA50/200 · VIX&lt;18 · breadth&gt;65%</td><td class="r mono">58</td><td class="r mono">100%</td><td>Tech +3 / QG -3</td></tr>
         <tr><td><b class="pb-pill warn">Risk-On Choppy</b></td><td>SPY above EMA50, other criteria mixed</td><td class="r mono">60</td><td class="r mono">70%</td><td>0 / 0</td></tr>
         <tr><td><b class="pb-pill amber">Risk-Off Trending</b></td><td>SPY below EMA50</td><td class="r mono">78</td><td class="r mono">35%</td><td>Tech -5 / QG +5</td></tr>
         <tr><td><b class="pb-pill bear">Panic</b></td><td>VIX&gt;35 OR breadth&lt;20%</td><td class="r mono">—</td><td class="r mono">0%</td><td>Tech -8 / QG +8</td></tr>
       </tbody>
     </table>
     <div class="pb-callout">Regime weight shifts are <b>config-driven</b> as of 2026-05-01 — <code>config.regime_weight_shifts</code>. Walk-forward optimal weights paste directly into config.</div>`);

  const setups = sec('🎯', 'Setup Families &amp; Catalyst Tiers',
    `Setup determines hold-period guide and pillar weight shifts. Catalyst tier feeds into conviction tier assignment.`,
    `<div class="pb-grid-2">
       <div class="pb-card">
         <div class="pb-card-h">SETUP FAMILIES</div>
         <table class="pb-tbl">
           <tbody>
             <tr><td><b>Impulse Catalyst</b></td><td>5-8d hold · PEAD, UOA, gap-and-go</td></tr>
             <tr><td><b>Breakout Expansion</b></td><td>7-21d hold · VCP, 52wk breakout, squeeze release</td></tr>
             <tr><td><b>Trend Continuation</b></td><td>7-21d hold · EMA21/50 pullback, bounce, rebreak</td></tr>
             <tr><td><b>Special Situation</b></td><td>5-15d hold · insider cluster, float rotation, short squeeze</td></tr>
           </tbody>
         </table>
       </div>
       <div class="pb-card">
         <div class="pb-card-h">CATALYST TIERS</div>
         <table class="pb-tbl">
           <tbody>
             <tr><td><b class="pb-pill bull">T1</b></td><td>PEAD · UOA · VCP · 52wk breakout</td></tr>
             <tr><td><b class="pb-pill warn">T2</b></td><td>Squeeze · EMA21/50 pullback · momentum · insider cluster</td></tr>
             <tr><td><b class="pb-pill amber">T3</b></td><td>Analyst headlines · social mentions (default)</td></tr>
           </tbody>
         </table>
       </div>
     </div>`);

  const conviction = sec('🎚', 'Conviction Tier Assignment',
    `Final sizing tier — combines regime + score + RS + R:R + catalyst tier + entry quality.`,
    `<table class="pb-tbl">
       <thead><tr><th>Tier</th><th>Required conditions</th><th class="r">Sizing</th></tr></thead>
       <tbody>
         <tr><td><b class="pb-pill bull">T1</b></td><td>regime = Risk-On Trending · score≥88 · RS≥85 · R:R≥3.5 · cat tier 1 · entry FRESH/PULLBACK</td><td class="r"><b>Full size</b> (1.0×)</td></tr>
         <tr><td><b class="pb-pill info">T2</b></td><td>regime ≠ Panic · score≥78 · RS≥75 · R:R≥3.0 · cat tier ≤2</td><td class="r">Half size (0.5×)</td></tr>
         <tr><td><b class="pb-pill warn">T3</b></td><td>score≥70 · R:R≥3.0</td><td class="r">Quarter size (0.25×)</td></tr>
         <tr><td><b class="pb-pill amber">WATCH</b></td><td>score 60-69 — no capital, monitor only</td><td class="r">0%</td></tr>
       </tbody>
     </table>`);

  const entryq = sec('📍', 'Entry Quality Classification',
    `ATR-based proximity to setup pivot — determines whether entry is actionable now.`,
    `<table class="pb-tbl">
       <thead><tr><th>State</th><th>Distance from pivot</th><th>Action</th></tr></thead>
       <tbody>
         <tr><td><b class="pb-pill bull">FRESH</b></td><td>within 0.75 ATR of pivot/support</td><td>Optimal entry — full conviction</td></tr>
         <tr><td><b class="pb-pill bull">PULLBACK</b></td><td>within 1.25 ATR of EMA8/21/50</td><td>Acceptable entry — pullback into trend</td></tr>
         <tr><td><b class="pb-pill info">VALID</b></td><td>within 1.25 ATR of any key level</td><td>Conditional entry — watch for confirmation candle</td></tr>
         <tr><td><b class="pb-pill warn">EXTENDED</b></td><td>1.25-2.0 ATR above pivot</td><td>Reduce size · wait for retracement preferred</td></tr>
         <tr><td><b class="pb-pill bear">MISSED</b></td><td>beyond 2.0 ATR</td><td>Skip — re-entry blocked until pullback</td></tr>
       </tbody>
     </table>`);

  const phases = sec('⚡', 'Strategy Enhancements (Phase 1-3 · 2026-05-01)',
    `Three additive layers shipped 2026-05-01 — all opt-in via config flags.`,
    `<div class="pb-grid-3">
       <div class="pb-card">
         <div class="pb-card-h pass">PHASE 1 · Regime Weights</div>
         <div class="pb-card-body">Per-regime tech/qg pillar shifts now config-driven (was hardcoded). Walk-forward optimal weights paste directly into <code>config.regime_weight_shifts</code>.</div>
       </div>
       <div class="pb-card">
         <div class="pb-card-h info">PHASE 2 · Vol-Targeted Sizing</div>
         <div class="pb-card-body">Drawdown bands shrink size: 3-5% DD → 0.85× · 5-10% → 0.65× · 10-15% → 0.40× · &gt;15% → 0.20×. Currently no-op until equity history wires.</div>
       </div>
       <div class="pb-card">
         <div class="pb-card-h warn">PHASE 3 · Sector Ranking</div>
         <div class="pb-card-body">Cross-sectional percentile within sector. BUY → WATCH if &lt;60th percentile of sector (min 3 candidates). Forces relative-strength selection.</div>
       </div>
     </div>`);

  const tier1 = sec('🎯', 'Tier 1 Strategy Signals (6 Detectors)',
    `Additive scoring layer — each detector returns ±points. Currently <b>informational only</b> (apply_to_score=false). Flip to true after validation.`,
    `<table class="pb-tbl">
       <thead><tr><th>#</th><th>Detector</th><th>Trigger</th><th class="r">Points</th></tr></thead>
       <tbody>
         <tr><td class="mono">1</td><td><b>Insider Cluster</b></td><td>3+ insiders in 30d · CEO/CFO bonus · urgency bonus</td><td class="r mono">up to +12</td></tr>
         <tr><td class="mono">2</td><td><b>Beat-and-Raise</b></td><td>EPS beat + revenue beat + raised guidance</td><td class="r mono">+8 / -3</td></tr>
         <tr><td class="mono">3</td><td><b>NR7 / Inside Day</b></td><td>Today's range = narrowest of last 7 OR inside yesterday's</td><td class="r mono">up to +6</td></tr>
         <tr><td class="mono">4</td><td><b>Volume Dry-Up</b></td><td>5d vol &lt; 0.7× 20d AND price near EMA21/50 AND not declining</td><td class="r mono">+3</td></tr>
         <tr><td class="mono">5</td><td><b>OBV Divergence</b></td><td>Bull/bear divergence over 20-day window</td><td class="r mono">+5 / -5</td></tr>
         <tr><td class="mono">6</td><td><b>Mean Reversion</b></td><td>RSI&lt;35 + above 200SMA + fund≥4 + ATR&lt;6% + not falling-knife</td><td class="r mono">up to +10</td></tr>
       </tbody>
     </table>
     <div class="pb-callout">Cap: ±8 net points when applied. Per-detector results surface in <code>tier1_signals</code> field of the bundle.</div>`);

  const risk = sec('🛡', 'Risk Management Rules',
    `Hard limits on size, heat, and concentration.`,
    `<div class="pb-grid-2">
       <div class="pb-card">
         <div class="pb-card-h">SIZING FORMULA</div>
         <table class="pb-tbl">
           <tbody>
             <tr><td>Risk per share</td><td class="r mono">Entry − Stop</td></tr>
             <tr><td>Risk dollars</td><td class="r mono">0.75% × equity</td></tr>
             <tr><td>Raw shares</td><td class="r mono">Risk $ ÷ Risk/share</td></tr>
             <tr><td>× Conviction multiplier</td><td class="r mono">T1: 1.0× · T2: 0.5× · T3: 0.25×</td></tr>
             <tr><td>× Beta adjustment</td><td class="r mono">β&gt;1.5: ×0.7 · β&lt;0.7: ×1.2 · else 1×</td></tr>
             <tr><td>× Regime cap</td><td class="r mono">Risk-On: 1.0 · Choppy: 0.7 · Off: 0.35</td></tr>
             <tr><td>× VIX cap</td><td class="r mono">VIX&lt;18: 1.0 · 18-22: 0.9 · 22-25: 0.75 · 25-30: 0.5 · &gt;30: 0.2</td></tr>
             <tr><td>× Drawdown cap (Phase 2)</td><td class="r mono">0-3% DD: 1.0 · 3-5%: 0.85 · 5-10%: 0.65 · &gt;10%: 0.4</td></tr>
           </tbody>
         </table>
       </div>
       <div class="pb-card">
         <div class="pb-card-h">PORTFOLIO LIMITS</div>
         <table class="pb-tbl">
           <tbody>
             <tr><td>Max active positions</td><td class="r mono">3-5</td></tr>
             <tr><td>Per-position allocation</td><td class="r mono">5-10%</td></tr>
             <tr><td>Per-trade risk</td><td class="r mono">0.75% account</td></tr>
             <tr><td>Hard heat cap</td><td class="r mono">6% portfolio</td></tr>
             <tr><td>Sector concentration</td><td class="r mono">max 3 per sector</td></tr>
             <tr><td>Industry concentration</td><td class="r mono">max 3 per industry</td></tr>
             <tr><td>Stop loss</td><td class="r mono">1.25× ATR (no trade without stop)</td></tr>
             <tr><td>R:R minimum</td><td class="r mono">3:1 (4:1 in Risk-Off)</td></tr>
             <tr><td>Liquidity floor</td><td class="r mono">$5M daily $-volume</td></tr>
           </tbody>
         </table>
       </div>
     </div>`);

  const theory = sec('📚', 'Theory Confluence + Methodology Gate',
    `Soft gate — needs ≥2 bullish theories aligned for STRONG verdict.`,
    `<div class="pb-grid-2">
       <div class="pb-card">
         <div class="pb-card-h">THEORY CONFLUENCE</div>
         <table class="pb-tbl">
           <tbody>
             <tr><td><b>Dow Theory</b></td><td>HH+HL on weekly (BULLISH) / no HH+HL (BEARISH)</td></tr>
             <tr><td><b>Wyckoff Phase</b></td><td>MARKUP/ACCUMULATION (bull) · MARKDOWN/DISTRIBUTION (bear)</td></tr>
             <tr><td><b>Elliott Wave</b></td><td>EARLY_IMPULSE/wave 3 (bull) · LATE_IMPULSE/wave 5 (caution) · CORRECTIVE (bear)</td></tr>
             <tr><td><b>Gann Timing</b></td><td>Module not yet implemented — UNAVAILABLE</td></tr>
           </tbody>
         </table>
       </div>
       <div class="pb-card">
         <div class="pb-card-h">METHODOLOGY CHECKLIST (5)</div>
         <table class="pb-tbl">
           <tbody>
             <tr><td><b>Dow uptrend</b></td><td>SPY higher-highs + higher-lows</td></tr>
             <tr><td><b>Wyckoff markup</b></td><td>Rising price on supporting volume</td></tr>
             <tr><td><b>MA alignment</b></td><td>Price &gt; 50d &gt; 200d</td></tr>
             <tr><td><b>Sector strength</b></td><td>Sector outperforming SPY</td></tr>
             <tr><td><b>No late wave</b></td><td>Not in Elliott Wave 4/5 ending</td></tr>
           </tbody>
         </table>
         <div class="pb-callout">≥4/5 = STRONG · 3/5 = OK · ≤2/5 = WEAK</div>
       </div>
     </div>`);

  const macro = sec('⚠', 'Macro Calendar &amp; Earnings Blackout',
    `Soft and hard gates protecting against binary-event volatility.`,
    `<table class="pb-tbl">
       <thead><tr><th>Event</th><th>Gate type</th><th>Window</th></tr></thead>
       <tbody>
         <tr><td><b>FOMC · CPI · NFP · PCE</b></td><td>Soft advisory (configurable hard)</td><td>Day-of + morning-after</td></tr>
         <tr><td><b>Earnings (within 3d)</b></td><td>HARD BLOCK</td><td>3 days before report</td></tr>
         <tr><td><b>Earnings (within 5d)</b></td><td>Soft advisory + score penalty</td><td>5-day blackout window</td></tr>
         <tr><td><b>VIX spike</b></td><td>VIX &gt; 5d avg × 1.4 = kill switch (no new longs)</td><td>Day-of</td></tr>
         <tr><td><b>VIX tighten mode</b></td><td>VIX 25-30 raises BUY threshold by 10 pts</td><td>While in band</td></tr>
       </tbody>
     </table>`);

  const exits = sec('🚪', 'Exit Rules',
    `Pre-defined exit logic — no discretionary holds.`,
    `<table class="pb-tbl">
       <thead><tr><th>Trigger</th><th>Action</th></tr></thead>
       <tbody>
         <tr><td>Reach <b>T1</b> target (≈2× risk)</td><td>Sell 33-50% · trail rest to break-even</td></tr>
         <tr><td>Reach <b>T2</b> target (≈3-5× risk)</td><td>Sell remaining or trail 1× ATR</td></tr>
         <tr><td>Stop hit on close</td><td>Exit full position next bar — no overnight</td></tr>
         <tr><td>Time stop (max hold reached)</td><td>Exit at market — setup didn't work</td></tr>
         <tr><td>Setup invalidation</td><td>Pattern fails (e.g., breakout → re-enters base) — exit immediately</td></tr>
         <tr><td>Earnings approaching</td><td>Trim 50% within 5 days, full exit within 3 days</td></tr>
         <tr><td>Regime flip to Panic</td><td>Exit all longs · system goes flat</td></tr>
       </tbody>
     </table>`);

  const workflow = sec('📋', 'Daily Trading Workflow',
    `What to do each morning.`,
    `<ol class="pb-ol">
       <li><b>Check the macro banner</b> — FOMC/CPI/NFP/PCE blackout? Earnings calendar today?</li>
       <li><b>Confirm regime</b> — Risk-On Trending? Choppy? Off? Panic? Sets the bar.</li>
       <li><b>Review BUY signals</b> — sort by score · check entry quality · top R:R</li>
       <li><b>Click Full Analysis →</b> on candidates — Rule Engine tab shows the why-trail · all 12 tabs give independent verdicts (Per-Tab Consensus)</li>
       <li><b>Verify each pillar</b> — Tech aligned? Catalyst clean? RS strong? Smart money flowing? Quality OK?</li>
       <li><b>Check sector rank</b> — top 40% within sector?</li>
       <li><b>Compute size</b> — Risk &amp; Sizing tab shows shares · respect heat cap · respect drawdown band</li>
       <li><b>Set stop on entry</b> — never trade without one · 1.25× ATR default</li>
       <li><b>Monitor WATCH list</b> — alerts at entry zone · revisit daily</li>
       <li><b>Close week with journal</b> — Plan tab → Journal · log thesis, sizing rationale, invalidation conditions</li>
     </ol>`);

  $('playbookBody').innerHTML = hero + pillars + regimes + setups + conviction + entryq + phases + tier1 + risk + theory + macro + exits + workflow + `
    <div class="pb-foot">
      <b>Source of truth:</b> All thresholds in this Playbook live in <code>config/config.json</code> · scoring logic in <code>analysis.py</code> · Tier 1 detectors in <code>tier1_signals.py</code>. Last rebuild: 2026-05-03.
    </div>`;
}

export function dispose() { /* no-op */ }

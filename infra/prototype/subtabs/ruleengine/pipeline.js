// subtabs/ruleengine/pipeline.js — 10-stage decision pipeline renderer.
// Returns the HTML string for the .re-pipeline section: Universe → Gate →
// 5-Pillar Scoring → Setup Classification → Theory & Methodology → Sector
// Ranking → Tier 1 Signals → Conviction & Sizing → Macro → Final Verdict.

import { fmtScore, pct, toneFromPct, stateBadge } from './helpers.js';

export function buildPipeline(T, ctx) {
  const { tone, verdict, narrative,
          gatePass, gateReasons,
          tech, techMax, cat, catMax, rs, rsMax, sm, smMax, qg, qgMax,
          rawTotal, bonusTot,
          setupFamily, catalystTier, catalystTags, conviction, entryQ,
          tcStates, tcDir, mcChecks, mcPasses,
          sectorPctRank, sectorN, sectorDemoted,
          tier1Sigs, tier1ActiveCt, tier1Points,
          macroBlock } = ctx;

  return `
    <div class="re-pipeline">

      <!-- STAGE 1: Universe + price/vol filter -->
      <div class="re-stage pass">
        <div class="re-stage-h">
          <span class="re-stage-num">1</span>
          <span class="re-stage-title">Universe Inclusion</span>
          <span class="re-stage-pill pass">QUALIFIED</span>
        </div>
        <div class="re-stage-body">
          ${T.ticker} passed price ($${(T.price||0).toFixed(2)}), liquidity, and S&P 500 / Russell 1000 / custom watchlist filters. ${T.zacks_rank1 ? '<b>Zacks Rank #1</b> — guaranteed inclusion.' : ''}
        </div>
      </div>

      <!-- STAGE 2: Pre-trade gate -->
      <div class="re-stage ${gatePass ? 'pass' : 'fail'}">
        <div class="re-stage-h">
          <span class="re-stage-num">2</span>
          <span class="re-stage-title">Pre-trade Gate</span>
          <span class="re-stage-pill ${gatePass ? 'pass' : 'fail'}">${gatePass ? 'PASSED' : 'KILLED'}</span>
        </div>
        <div class="re-stage-body">
          ${gatePass
            ? `All hard gates cleared (liquidity · earnings blackout · regime · entry quality).`
            : `Gate failed with ${gateReasons.length} reason${gateReasons.length===1?'':'s'}:`}
          ${gateReasons.length ? `<div class="re-stage-checks">${gateReasons.map(r => `
            <div class="re-check ${String(r).startsWith('HARD') ? 'fail' : 'warn'}">
              <span class="mark">${String(r).startsWith('HARD') ? '✗' : '⚠'}</span>
              <span class="name">${r}</span>
              <span class="val"></span>
            </div>`).join('')}</div>` : ''}
        </div>
      </div>

      <!-- STAGE 3: 5-Pillar Scoring -->
      <div class="re-stage info">
        <div class="re-stage-h">
          <span class="re-stage-num">3</span>
          <span class="re-stage-title">5-Pillar Scoring</span>
          <span class="re-stage-pill info">${rawTotal.toFixed(0)}/100 raw</span>
        </div>
        <div class="re-stage-body">
          Each pillar scored independently · regime weights applied · setup-family shifts · bonus cap ±5.
          <div class="re-pillars">
            <div class="re-pillar ${toneFromPct(tech, techMax)}"><div class="lbl">Tech</div><div class="v ${tech >= techMax*0.7 ? 'pass' : tech >= techMax*0.4 ? 'warn' : 'fail'}">${fmtScore(tech, techMax)}</div><div class="frac">${pct(tech, techMax)}</div></div>
            <div class="re-pillar ${toneFromPct(cat, catMax)}"><div class="lbl">Catalyst</div><div class="v ${cat >= catMax*0.7 ? 'pass' : cat >= catMax*0.4 ? 'warn' : 'fail'}">${fmtScore(cat, catMax)}</div><div class="frac">${pct(cat, catMax)}</div></div>
            <div class="re-pillar ${toneFromPct(rs, rsMax)}"><div class="lbl">RS+Sector</div><div class="v ${rs >= rsMax*0.7 ? 'pass' : rs >= rsMax*0.4 ? 'warn' : 'fail'}">${fmtScore(rs, rsMax)}</div><div class="frac">${pct(rs, rsMax)}</div></div>
            <div class="re-pillar ${toneFromPct(sm, smMax)}"><div class="lbl">Smart Money</div><div class="v ${sm >= smMax*0.7 ? 'pass' : sm >= smMax*0.4 ? 'warn' : 'fail'}">${fmtScore(sm, smMax)}</div><div class="frac">${pct(sm, smMax)}</div></div>
            <div class="re-pillar ${toneFromPct(qg, qgMax)}"><div class="lbl">Quality</div><div class="v ${qg >= qgMax*0.7 ? 'pass' : qg >= qgMax*0.4 ? 'warn' : 'fail'}">${fmtScore(qg, qgMax)}</div><div class="frac">${pct(qg, qgMax)}</div></div>
          </div>
          <div class="re-stage-checks" style="margin-top:8px">
            <div class="re-check"><span class="mark">∑</span><span class="name">Raw pillar total</span><span class="val">${rawTotal.toFixed(1)}</span></div>
            <div class="re-check"><span class="mark">+</span><span class="name">Bonuses (Elliott Wave, squeeze breakout, weekly bonus)</span><span class="val">${bonusTot >= 0 ? '+' : ''}${bonusTot.toFixed(1)}</span></div>
          </div>
        </div>
      </div>

      <!-- STAGE 4: Setup classification -->
      <div class="re-stage ${setupFamily !== '—' ? 'pass' : 'info'}">
        <div class="re-stage-h">
          <span class="re-stage-num">4</span>
          <span class="re-stage-title">Setup Classification</span>
          <span class="re-stage-pill ${catalystTier === 1 ? 'pass' : catalystTier === 2 ? 'warn' : 'info'}">T${catalystTier || '?'}</span>
        </div>
        <div class="re-stage-body">
          Family: <b>${setupFamily}</b> · Catalyst tier <b>T${catalystTier || '?'}</b> · Entry quality <b>${entryQ}</b>.
          ${catalystTags.length ? `<div class="re-stage-checks">${catalystTags.slice(0,5).map(c => `
            <div class="re-check pass"><span class="mark">⚡</span><span class="name">${c}</span><span class="val"></span></div>`).join('')}</div>` : ''}
        </div>
      </div>

      <!-- STAGE 5: Theory confluence + methodology -->
      <div class="re-stage ${tcDir === 'BULLISH' ? 'pass' : tcDir === 'BEARISH' ? 'fail' : 'warn'}">
        <div class="re-stage-h">
          <span class="re-stage-num">5</span>
          <span class="re-stage-title">Theory &amp; Methodology Check</span>
          <span class="re-stage-pill ${tcDir === 'BULLISH' ? 'pass' : tcDir === 'BEARISH' ? 'fail' : 'warn'}">${tcDir || 'NEUTRAL'} · ${mcPasses != null ? mcPasses : '—'}/5</span>
        </div>
        <div class="re-stage-body">
          Dow / Wyckoff / Elliott / Gann states + 5-check methodology sanity.
          <div class="re-stage-checks" style="margin-top:8px">
            ${['dow','wyckoff','elliott','gann'].map(k => {
              const s = tcStates[k] || 'UNKNOWN';
              const cls = stateBadge(s);
              return `<div class="re-check ${cls === 'pass' || cls === 'fail' || cls === 'warn' ? cls : 'info'}">
                <span class="mark">${cls === 'pass' ? '✓' : cls === 'fail' ? '✗' : '·'}</span>
                <span class="name">${k.toUpperCase()}</span>
                <span class="val">${s}</span>
              </div>`;
            }).join('')}
            ${Object.entries(mcChecks).slice(0, 5).map(([key, v]) => {
              const passed = (v && (v.pass === true || v === true));
              return `<div class="re-check ${passed ? 'pass' : 'fail'}">
                <span class="mark">${passed ? '✓' : '✗'}</span>
                <span class="name">${key.replace(/_/g, ' ')}</span>
                <span class="val">${typeof v === 'object' ? (v.reason || '').slice(0, 50) : ''}</span>
              </div>`;
            }).join('')}
          </div>
        </div>
      </div>

      <!-- STAGE 6: Sector ranking -->
      <div class="re-stage ${sectorDemoted ? 'fail' : sectorPctRank != null ? 'pass' : 'info'}">
        <div class="re-stage-h">
          <span class="re-stage-num">6</span>
          <span class="re-stage-title">Cross-Sectional Sector Ranking</span>
          <span class="re-stage-pill ${sectorDemoted ? 'fail' : sectorPctRank != null ? 'pass' : 'info'}">${sectorDemoted ? 'DEMOTED' : sectorPctRank != null ? `${sectorPctRank.toFixed(0)}th %ile` : 'SKIPPED'}</span>
        </div>
        <div class="re-stage-body">
          ${sectorPctRank != null
            ? `Ranked <b>${sectorPctRank.toFixed(0)}th percentile</b> within <b>${T.sector || 'sector'}</b> (${sectorN || '?'} candidates). ${sectorDemoted ? `<br><span style="color:var(--fail)">${sectorDemoted}</span>` : 'Top decile of sector — relative-strength selection.'}`
            : 'Insufficient sector candidates (<3) — ranking skipped, no demotion possible.'}
        </div>
      </div>

      <!-- STAGE 7: Tier 1 strategy signals -->
      <div class="re-stage ${tier1ActiveCt > 0 ? 'pass' : 'info'}">
        <div class="re-stage-h">
          <span class="re-stage-num">7</span>
          <span class="re-stage-title">Tier 1 Strategy Signals</span>
          <span class="re-stage-pill ${tier1Points > 5 ? 'pass' : tier1Points > 0 ? 'warn' : tier1Points < 0 ? 'fail' : 'info'}">${tier1ActiveCt} active · ${tier1Points >= 0 ? '+' : ''}${tier1Points} pts</span>
        </div>
        <div class="re-stage-body">
          6 additive detectors: Insider Cluster · NR7 · Vol Dry-Up · OBV Div · Mean Reversion · Beat&amp;Raise. <em>Currently informational (apply_to_score=false)</em>.
          ${tier1ActiveCt > 0 ? `<div class="re-stage-checks">${Object.entries(tier1Sigs).filter(([k,v]) => v && v.detected).slice(0, 6).map(([k, v]) => `
            <div class="re-check ${v.points > 0 ? 'pass' : v.points < 0 ? 'fail' : 'warn'}">
              <span class="mark">${v.points > 0 ? '+' : v.points < 0 ? '−' : '·'}</span>
              <span class="name">${k.replace(/_/g, ' ')}</span>
              <span class="val">${v.points >= 0 ? '+' : ''}${v.points} · ${(v.narrative || '').slice(0, 60)}</span>
            </div>`).join('')}</div>` : '<div style="color:var(--ink-1);font-style:italic;margin-top:6px">No detectors fired — not unusual for non-catalyst setups.</div>'}
        </div>
      </div>

      <!-- STAGE 8: Conviction tier + sizing -->
      <div class="re-stage ${conviction === 'T1' ? 'pass' : conviction === 'T2' ? 'warn' : 'info'}">
        <div class="re-stage-h">
          <span class="re-stage-num">8</span>
          <span class="re-stage-title">Conviction Tier &amp; Sizing</span>
          <span class="re-stage-pill ${conviction === 'T1' ? 'pass' : conviction === 'T2' ? 'warn' : 'info'}">${conviction}</span>
        </div>
        <div class="re-stage-body">
          ${conviction === 'T1' ? '<b>Full size (T1)</b> — score ≥88, RS ≥85, R:R ≥3.5, T1 catalyst, entry FRESH/PULLBACK.'
            : conviction === 'T2' ? '<b>Half size (T2)</b> — score ≥78, RS ≥75, R:R ≥3.0, T1-T2 catalyst.'
            : conviction === 'T3' ? '<b>Quarter size (T3)</b> — minimum bar (score ≥70, R:R ≥3.0).'
            : conviction === 'WATCH' ? '<b>WATCH</b> — score 60–69, no capital allocated yet.'
            : 'Conviction tier not assigned (typically because gate failed).'}
          <div class="re-stage-checks" style="margin-top:8px">
            <div class="re-check info"><span class="mark">$</span><span class="name">Suggested allocation</span><span class="val">${T.alloc_pct ? T.alloc_pct.toFixed(1) + '%' : '—'}</span></div>
            <div class="re-check info"><span class="mark">∽</span><span class="name">Sizing multiplier</span><span class="val">${T.sizing_multiplier ? T.sizing_multiplier.toFixed(2) + '×' : '—'}</span></div>
            <div class="re-check info"><span class="mark">📊</span><span class="name">Half-Kelly</span><span class="val">${(T.kelly_size || {}).half_kelly_pct ? (T.kelly_size.half_kelly_pct).toFixed(1) + '%' : '—'}</span></div>
          </div>
        </div>
      </div>

      <!-- STAGE 9: Macro context -->
      ${macroBlock.blackout_today ? `
      <div class="re-stage warn">
        <div class="re-stage-h">
          <span class="re-stage-num">9</span>
          <span class="re-stage-title">Macro Calendar Override</span>
          <span class="re-stage-pill warn">ADVISORY</span>
        </div>
        <div class="re-stage-body">
          <b>${macroBlock.blackout_reason || 'Macro event today'}</b> — soft advisory active. New entries should be cautious; gate is informational unless <code>gates.macro_blackout_hard=true</code>.
        </div>
      </div>` : ''}

      <!-- STAGE 10: Final Verdict -->
      <div class="re-stage ${tone === 'buy' ? 'pass' : tone === 'short' ? 'fail' : 'warn'}">
        <div class="re-stage-h">
          <span class="re-stage-num">${macroBlock.blackout_today ? '10' : '9'}</span>
          <span class="re-stage-title">Final Verdict</span>
          <span class="re-stage-pill ${tone === 'buy' ? 'pass' : tone === 'short' ? 'fail' : 'warn'}">${verdict}</span>
        </div>
        <div class="re-stage-body">
          ${narrative}
          ${(typeof T.thesis === 'string' && T.thesis) ? `<div style="margin-top:8px;padding:8px 10px;background:var(--bg-2);border-radius:4px;font-size:11.5px;color:var(--ink-1);font-style:italic">${T.thesis.slice(0, 280)}</div>` : ''}
        </div>
      </div>

    </div><!-- /.re-pipeline -->`;
}

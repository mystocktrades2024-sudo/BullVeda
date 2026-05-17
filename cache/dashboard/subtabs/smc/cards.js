// subtabs/smc/cards.js — Verdict banner + Structure cards + OB/FVG tables
// + SMC-driven trade plan + Horizon impact. Returns one big HTML chunk.

export function buildBody(ctx) {
  const { px, smc, tone, arrow, hLabel, hEm, narr,
          obs, fvgs, openFVGs, closedFVGs, liquidity,
          fracHi, fracLo, vwap, zq,
          freshOBs, testedOBs, mitigatedOBs, bullOBs, bearOBs, topOBs, maxStrength,
          lastStruct, bosBars, chochBars, bosEvent, chochEvent,
          ladderSVG,
          bestBullOB, bullishCandidates, bearishAbove,
          planEntry, planStop, planTarget, planRR,
          hzImpact } = ctx;

  return `
    <!-- VERDICT BANNER -->
    <div class="smc-verdict ${tone}">
      <div class="smc-v-arrow">${arrow}</div>
      <div class="smc-v-mid">
        <div class="tag">SMC STRUCTURE · ${(smc.smc_direction || 'neutral').toUpperCase()}</div>
        <div class="h">${hLabel} <span class="em">${hEm}</span></div>
        <div class="narr">${narr}</div>
      </div>
      <div class="smc-v-r">
        <div class="smc-v-score">${(+(smc.score || 0)).toFixed(1)}</div>
        <div class="smc-v-score-lbl">SMC Score</div>
      </div>
    </div>

    <!-- PRICE LADDER + RIGHT COLUMN -->
    <div class="smc-main">
      <div class="smc-ladder">
        <div class="smc-ladder-h"><span class="ico">📊</span>PRICE LADDER · LEVELS AROUND $${px.toFixed(2)}</div>
        ${ladderSVG}
        <div class="smc-ladder-legend">
          <span class="item"><span class="swatch" style="background:rgba(74,222,128,0.5);border:1px solid rgba(74,222,128,0.85)"></span>Bullish OB</span>
          <span class="item"><span class="swatch" style="background:rgba(248,113,113,0.5);border:1px solid rgba(248,113,113,0.85)"></span>Bearish OB</span>
          <span class="item"><span class="swatch" style="background:rgba(74,222,128,0.3);border:1px dashed rgba(74,222,128,0.7)"></span>Bull FVG</span>
          <span class="item"><span class="swatch" style="background:rgba(248,113,113,0.3);border:1px dashed rgba(248,113,113,0.7)"></span>Bear FVG</span>
          <span class="item"><span class="swatch" style="background:#a78bfa"></span>VWAP</span>
          <span class="item"><span class="swatch" style="background:#fbbf24"></span>NOW</span>
        </div>
      </div>

      <div class="smc-rcol">
        <div class="smc-pgrid">
          <div class="smc-card">
            <div class="smc-card-h"><span class="ico">🏗</span>MARKET STRUCTURE</div>
            <div class="smc-card-row"><span class="l">Last swing</span><span class="r ${lastStruct === 'HH' || lastStruct === 'HL' ? 'pass' : lastStruct === 'LH' || lastStruct === 'LL' ? 'fail' : ''}">${lastStruct}</span></div>
            <div class="smc-card-row"><span class="l">Break of Structure</span><span class="r ${ctx.smc.bos_choch?.bos_bullish ? 'pass' : ctx.smc.bos_choch?.bos_bearish ? 'fail' : ''}">${bosEvent}${bosBars != null ? ` · ${bosBars}b ago` : ''}</span></div>
            <div class="smc-card-row"><span class="l">Change of Character</span><span class="r ${ctx.smc.bos_choch?.choch_bullish ? 'pass' : ctx.smc.bos_choch?.choch_bearish ? 'fail' : ''}">${chochEvent}${chochBars != null ? ` · ${chochBars}b ago` : ''}</span></div>
            <div class="smc-card-row"><span class="l">Direction</span><span class="r ${tone === 'bull' ? 'pass' : tone === 'bear' ? 'fail' : ''}">${(smc.smc_direction || 'neutral').toUpperCase()}</span></div>
          </div>
          <div class="smc-card">
            <div class="smc-card-h"><span class="ico">📍</span>VWAP & FRACTALS</div>
            <div class="smc-card-row"><span class="l">VWAP 20d</span><span class="r ${vwap.above_vwap ? 'pass' : 'fail'}">${vwap.vwap_20d ? '$' + (+vwap.vwap_20d).toFixed(2) : '—'}${vwap.above_vwap != null ? (vwap.above_vwap ? ' · ABOVE' : ' · BELOW') : ''}</span></div>
            <div class="smc-card-row"><span class="l">AVWAP swing-low</span><span class="r ${vwap.above_avwap ? 'pass' : 'fail'}">${vwap.avwap_swing_low ? '$' + (+vwap.avwap_swing_low).toFixed(2) : '—'}</span></div>
            <div class="smc-card-row"><span class="l">Fractal high</span><span class="r">${fracHi > 0 ? '$' + fracHi.toFixed(2) : '—'}${fracHi > 0 ? ` · +${((fracHi-px)/px*100).toFixed(1)}%` : ''}</span></div>
            <div class="smc-card-row"><span class="l">Fractal low</span><span class="r">${fracLo > 0 ? '$' + fracLo.toFixed(2) : '—'}${fracLo > 0 ? ` · ${((fracLo-px)/px*100).toFixed(1)}%` : ''}</span></div>
          </div>
        </div>
        <div class="smc-pgrid">
          <div class="smc-card">
            <div class="smc-card-h"><span class="ico">🟩</span>ORDER BLOCKS<span class="meta">${obs.length} total</span></div>
            <div class="smc-bigstat"><span class="v ${freshOBs > 0 ? 'pass' : ''}">${freshOBs}</span><span class="u">fresh · active demand zones</span></div>
            <div class="smc-card-row"><span class="l">Bullish OBs</span><span class="r pass">${bullOBs}</span></div>
            <div class="smc-card-row"><span class="l">Bearish OBs</span><span class="r fail">${bearOBs}</span></div>
            <div class="smc-status-pills">
              <span class="smc-status-pill fresh">${freshOBs} fresh</span>
              <span class="smc-status-pill tested">${testedOBs} tested</span>
              <span class="smc-status-pill mitigated">${mitigatedOBs} mitigated</span>
            </div>
          </div>
          <div class="smc-card">
            <div class="smc-card-h"><span class="ico">⚡</span>FAIR VALUE GAPS<span class="meta">${fvgs.length} total</span></div>
            <div class="smc-bigstat"><span class="v ${openFVGs.length > 0 ? 'pass' : ''}">${openFVGs.length}</span><span class="u">open · unfilled magnets</span></div>
            <div class="smc-card-row"><span class="l">Open</span><span class="r pass">${openFVGs.length}</span></div>
            <div class="smc-card-row"><span class="l">Closed</span><span class="r">${closedFVGs.length}</span></div>
            <div class="smc-card-row"><span class="l">Liquidity sweeps</span><span class="r ${liquidity.length > 0 ? 'warn' : ''}">${liquidity.length}</span></div>
          </div>
        </div>
        ${zq.label ? `
        <div class="smc-card">
          <div class="smc-card-h"><span class="ico">⭐</span>ZONE QUALITY<span class="meta">${zq.points || 0} confluence pts</span></div>
          <div class="smc-bigstat"><span class="v ${zq.label === 'Strong' ? 'pass' : zq.label === 'Weak' ? 'fail' : ''}">${zq.label}</span><span class="u">at the demand zone</span></div>
          <div class="smc-zq-reasons">${(zq.reasons || []).map(r => `<span class="chip">${r}</span>`).join('')}</div>
        </div>` : ''}
      </div>
    </div>

    <!-- TOP ORDER BLOCKS TABLE -->
    ${topOBs.length ? `
    <div class="smc-card" style="padding:0; margin-bottom:14px;">
      <div class="smc-card-h" style="padding:14px 16px 8px"><span class="ico">📋</span>TOP ORDER BLOCKS BY STRENGTH</div>
      <table class="smc-table">
        <thead><tr><th>Type</th><th class="r">Price</th><th class="r">Range</th><th>Status</th><th>Freshness</th><th>Strength</th><th class="r">Bars ago</th></tr></thead>
        <tbody>
          ${topOBs.map(o => {
            const isBull      = o.type === 'bullish';
            const sCls        = o.status === 'mitigated' ? 'mitigated' : o.status === 'tested' ? 'tested' : 'fresh';
            const strengthPct = ((o.strength_score || 0) / maxStrength) * 100;
            return `<tr>
              <td><span class="ob-pill ${isBull ? 'demand' : 'supply'}">${isBull ? 'DEMAND' : 'SUPPLY'}</span></td>
              <td class="num px">$${(+o.price_level).toFixed(2)}</td>
              <td class="num">$${(+o.low).toFixed(2)} – $${(+o.high).toFixed(2)}</td>
              <td><span class="smc-status-pill ${sCls}">${(o.status || 'fresh').toUpperCase()}</span></td>
              <td>${(o.freshness * 100).toFixed(0)}%</td>
              <td><div class="strength-bar"><div class="strength-bar-f ${isBull ? '' : 'bear'}" style="width:${strengthPct.toFixed(0)}%"></div></div></td>
              <td class="num">${o.bars_since}</td>
            </tr>`;
          }).join('')}
        </tbody>
      </table>
    </div>` : ''}

    <!-- TOP FVG TABLE -->
    ${openFVGs.length ? `
    <div class="smc-card" style="padding:0; margin-bottom:14px;">
      <div class="smc-card-h" style="padding:14px 16px 8px"><span class="ico">⚡</span>OPEN FAIR VALUE GAPS — UNFILLED MAGNETS</div>
      <table class="smc-table">
        <thead><tr><th>Type</th><th class="r">Top</th><th class="r">Bottom</th><th class="r">Size</th><th class="r">Distance</th><th class="r">Age</th></tr></thead>
        <tbody>
          ${openFVGs.slice(0, 8).map(f => {
            const mid     = (f.top + f.bottom) / 2;
            const distPct = ((mid - px) / px * 100);
            return `<tr>
              <td><span class="ob-pill ${f.type === 'bullish' ? 'demand' : 'supply'}">${(f.type || '').toUpperCase()}</span></td>
              <td class="num px">$${(+f.top).toFixed(2)}</td>
              <td class="num px">$${(+f.bottom).toFixed(2)}</td>
              <td class="num">${(f.size_pct * 100).toFixed(2)}%</td>
              <td class="num" style="color:${Math.abs(distPct) < 2 ? 'var(--warn)' : 'var(--ink-1)'}">${distPct >= 0 ? '+' : ''}${distPct.toFixed(1)}%</td>
              <td class="num">${f.age_bars}b</td>
            </tr>`;
          }).join('')}
        </tbody>
      </table>
    </div>` : ''}

    <!-- SMC-DRIVEN TRADE PLAN -->
    ${tone !== 'neutral' && bestBullOB ? `
    <div class="smc-plan">
      <div class="smc-plan-h">SMC-DRIVEN TRADE PLAN — ${tone === 'bull' ? 'LONG SETUP' : 'SHORT SETUP'}</div>
      <div class="smc-plan-grid">
        <div class="smc-plan-tile entry"><div class="lbl">Entry</div><div class="v">$${planEntry.toFixed(2)}</div><div class="sub">Bull OB · strength ${bestBullOB.strength_score.toFixed(1)}</div></div>
        <div class="smc-plan-tile stop"><div class="lbl">Stop</div><div class="v">$${planStop.toFixed(2)}</div><div class="sub">Below OB low or fractal low</div></div>
        <div class="smc-plan-tile target"><div class="lbl">Target</div><div class="v">$${planTarget.toFixed(2)}</div><div class="sub">${bearishAbove ? 'Nearest bearish OB' : 'Fractal high · 2× risk'}</div></div>
        <div class="smc-plan-tile rr"><div class="lbl">R:R</div><div class="v">${planRR.toFixed(1)}×</div><div class="sub">${planRR >= 3 ? 'Strong' : planRR >= 2 ? 'Acceptable' : 'Sub-par'}</div></div>
      </div>
    </div>
    ` : ''}

    <!-- HORIZON IMPACT -->
    <div class="ins-pat" style="margin-top:14px;">
      <div class="smc-card-h"><span class="ico">🎯</span>SMC IMPACT BY HORIZON</div>
      <div class="ins-hz-grid">
        <div class="ins-hz ${tone === 'bull' && openFVGs.filter(f => f.bottom < px).length > 0 ? 'major' : tone === 'neutral' ? 'minor' : 'medium'}">
          <div class="ins-hz-h">⚡ SWING<span class="impact">${tone === 'bull' && openFVGs.filter(f => f.bottom < px).length > 0 ? 'MAJOR' : tone === 'neutral' ? 'MINOR' : 'MEDIUM'}</span></div>
          <div class="ins-hz-t">${hzImpact.swing}</div>
        </div>
        <div class="ins-hz ${tone === 'bull' && bullishCandidates.filter(o => o.freshness >= 0.7).length > 0 ? 'major' : tone === 'neutral' ? 'minor' : 'medium'}">
          <div class="ins-hz-h">📈 POSITION<span class="impact">${tone === 'bull' && bullishCandidates.filter(o => o.freshness >= 0.7).length > 0 ? 'MAJOR' : tone === 'neutral' ? 'MINOR' : 'MEDIUM'}</span></div>
          <div class="ins-hz-t">${hzImpact.position}</div>
        </div>
        <div class="ins-hz ${tone === 'bull' ? 'major' : tone === 'bear' ? 'major' : 'minor'}">
          <div class="ins-hz-h">🚀 INVEST<span class="impact">${tone === 'bull' ? 'MAJOR' : tone === 'bear' ? 'MAJOR' : 'MINOR'}</span></div>
          <div class="ins-hz-t">${hzImpact.invest}</div>
        </div>
      </div>
    </div>`;
}

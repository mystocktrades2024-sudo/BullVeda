// subtabs/ml_edge/cone.js — §3 "Drilldown" section.
//
// Layout: split-1-2-1
//   LEFT:  direction tiles + skew bar + quantile table + per-horizon table
//   MIDDLE: large forecast cone with T1/T2/Stop/ER overlays
//   RIGHT: level-hit ladder + headline trade-probability table
//
// Cone is computed dynamically from payload.magnitude with Brownian sqrt(t) scaling.

const _fmt$ = (v) => v == null ? '—' : '$' + Number(v).toFixed(2);
const fmtSgn = (v, d=2) => v == null ? '—' : (v >= 0 ? '+' : '') + Number(v).toFixed(d) + '%';

export function buildDrilldown(ctx) {
  const { T, payload } = ctx;
  const mag = payload.magnitude || {};
  const hit = payload.hit_net || {};
  const dir = payload.direction || {};

  // Trade plan levels
  const plan = T.canonical_trade_plan || T.trade_plan || {};
  const spot = +(T.price ?? T.entry_price ?? plan.entry ?? plan.entry_price ?? 0) || 100;
  const stop = +(plan.stop ?? plan.stop_price ?? (spot * 0.96));
  const t1   = +(plan.t1   ?? plan.target1   ?? (spot * 1.04));
  const t2   = +(plan.t2   ?? plan.target2   ?? (spot * 1.08));
  const rr   = T.rr_ratio || plan.rr_ratio;
  const score = T.score;
  const setup = T.setup_family || T.setup_type;
  const entryQuality = T.entry_quality;

  // Quantile → price at 5d
  const q10_5 = mag.q10 != null ? spot * (1 + mag.q10 / 100) : spot * 0.95;
  const q25_5 = mag.q25 != null ? spot * (1 + mag.q25 / 100) : spot * 0.97;
  const q50_5 = mag.q50 != null ? spot * (1 + mag.q50 / 100) : spot;
  const q75_5 = mag.q75 != null ? spot * (1 + mag.q75 / 100) : spot * 1.03;
  const q90_5 = mag.q90 != null ? spot * (1 + mag.q90 / 100) : spot * 1.05;

  // y-axis: span all critical levels with a small pad
  const allY = [q10_5, q25_5, q50_5, q75_5, q90_5, stop, t1, t2, spot].filter(Number.isFinite);
  const yMin = Math.min(...allY) * 0.985;
  const yMax = Math.max(...allY) * 1.015;
  const yFor = (px) => 30 + (yMax - px) / (yMax - yMin) * 230; // 30..260

  // Brownian-scaled horizons
  const hzns = [
    { h: '0d',  x: 70,  s: 0 },
    { h: '1d',  x: 175, s: Math.sqrt(0.2) },
    { h: '3d',  x: 280, s: Math.sqrt(0.6) },
    { h: '5d',  x: 385, s: 1.0 },
    { h: '10d', x: 555, s: Math.sqrt(2.0) },
  ];
  const bandAt = (s, q) => s === 0 ? spot : q50_5 + (q - q50_5) * s;
  const medAt  = (s) => s === 0 ? spot : spot + (q50_5 - spot) * s;

  const upperHi = hzns.map(p => `${p.x},${yFor(bandAt(p.s, q90_5))}`).join(' ');
  const lowerHi = hzns.slice().reverse().map(p => `${p.x},${yFor(bandAt(p.s, q10_5))}`).join(' ');
  const upperLo = hzns.map(p => `${p.x},${yFor(bandAt(p.s, q75_5))}`).join(' ');
  const lowerLo = hzns.slice().reverse().map(p => `${p.x},${yFor(bandAt(p.s, q25_5))}`).join(' ');
  const medPath = hzns.map(p => `${p.x},${yFor(medAt(p.s))}`).join(' ');

  // y-axis labels (5 evenly-spaced)
  const yLabels = [];
  for (let i = 0; i < 5; i++) {
    const p = yMax - (yMax - yMin) * (i / 4);
    yLabels.push({ y: 30 + (230 * i / 4) + 4, label: '$' + p.toFixed(0) });
  }

  // ----- Hit-prob ladder -----
  const pT1   = hit.p_t1_first;
  const pStop = hit.p_stop_first != null ? hit.p_stop_first : (pT1 != null ? 1 - pT1 : null);
  const roundUp = Math.ceil(spot / 5) * 5;
  const ema21 = +(T.ema21 || T.ema_21 || spot * 0.985);

  const levels = [
    { name: 'T2 · BSL',           px: t2,      side: 'up', prob: pT1 != null ? Math.max(0, pT1 - 0.30) : null },
    { name: 'T1 · HVN',           px: t1,      side: 'up', prob: pT1 },
    { name: `Round $${roundUp}`,  px: roundUp, side: 'up', prob: pT1 != null ? Math.min(0.95, pT1 + 0.10) : null },
    { name: 'Spot',               px: spot,    side: 'neutral', prob: null },
    { name: 'EMA21',              px: ema21,   side: 'dn', prob: pStop != null ? Math.max(0.10, pStop + 0.20) : null },
    { name: 'AVWAP-lo',           px: spot * 0.965, side: 'dn', prob: pStop != null ? Math.max(0.05, pStop * 0.7) : null },
    { name: 'Stop',               px: stop,    side: 'dn', prob: pStop },
  ];

  const levelRow = (lv) => {
    const cls = lv.side === 'up' ? 'gn' : lv.side === 'dn' ? 'rd' : 'dim';
    const probPct = lv.prob != null ? (lv.prob * 100).toFixed(0) + '%' : '—';
    const barW = lv.prob != null ? (lv.prob * 100).toFixed(0) : 0;
    return `
      <div class="rk-lvl-row">
        <div class="rk-lvl-label ${cls}">${lv.name}</div>
        <div class="rk-lvl-px">${_fmt$(lv.px)}</div>
        <div class="rk-lvl-track"><div class="rk-lvl-fill ${cls}" style="width:${lv.side === 'neutral' ? 100 : barW}%"></div></div>
        <div class="rk-lvl-val ${cls}">${lv.side === 'neutral' ? '—' : probPct}</div>
      </div>`;
  };

  // ----- Direction tiles -----
  const pUp = dir.p_up != null ? (dir.p_up * 100).toFixed(0) : null;
  const pDn = dir.p_dn != null ? (dir.p_dn * 100).toFixed(0) : null;

  // ----- Skew interpretation -----
  const skew = mag.skew;
  const upMass = skew != null ? Math.max(0.5, Math.min(0.9, 0.5 + skew / 2)) : 0.5;
  const skewText = skew != null
    ? skew > 0.2 ? `+${skew.toFixed(2)} strongly up-skewed`
      : skew < -0.2 ? `${skew.toFixed(2)} strongly down-skewed`
      : `${skew >= 0 ? '+' : ''}${skew.toFixed(2)} near-symmetric`
    : '—';
  const skewColor = skew == null ? 'var(--ink-3)' : skew > 0.2 ? 'var(--gn)' : skew < -0.2 ? 'var(--rd)' : 'var(--am)';

  // ----- Per-horizon table -----
  const horizons = [
    { h: '1 day',  pUp: dir.p_up_1d   ?? Math.max(0.15, (dir.p_up || 0.5) * 0.4),  mean: q50_5 != null ? (mag.q50 || 0) * 0.20 : 0, sigma: 1.4 },
    { h: '3 day',  pUp: dir.p_up_3d   ?? Math.max(0.30, (dir.p_up || 0.5) * 0.75), mean: (mag.q50 || 0) * 0.55, sigma: 2.6 },
    { h: '5 day',  pUp: dir.p_up      ?? 0.5,                                       mean: (mag.q50 || 0),        sigma: 3.4 },
    { h: '10 day', pUp: dir.p_up_10d  ?? Math.min(0.85, (dir.p_up || 0.5) * 1.1),   mean: (mag.q50 || 0) * 1.4,  sigma: 5.1 },
  ];

  // ----- Headline trade probabilities -----
  const erDays = (T.earnings || {}).days_to_earnings;
  const erX = erDays != null && erDays >= 0 && erDays <= 10
    ? 70 + (erDays / 10) * 485
    : null;

  return `
    <section class="rk-section">
      <div class="rk-section-head">
        <div>
          <div class="rk-section-title"><span class="num">§3</span>${(T.ticker || ctx.sym)} Drilldown · Per-Horizon</div>
          <div class="rk-section-sub">Direction probabilities · quantile range · level-touch ladder · per-horizon decay</div>
        </div>
        <span class="rk-pill gn">${score != null ? `Composite ${score}` : ''}${rr != null ? ` · R:R ${rr.toFixed(1)}` : ''}${setup ? ` · ${setup}` : ''}${entryQuality ? ` × ${entryQuality}` : ''}</span>
      </div>
      <div class="rk-section-body">
        <div class="rk-split-1-2-1">

          <!-- LEFT: direction tiles + skew + quantile + per-horizon -->
          <div>
            <div class="rk-dir-tiles">
              <div class="rk-dir-tile up">
                <div class="rk-dir-tile-k">▲ P(UP ≥ 5%)</div>
                <div class="rk-dir-tile-v">${pUp != null ? pUp + '%' : '—'}</div>
                <div class="rk-dir-tile-sub">${dir.p_up_lo != null ? `CI [${(dir.p_up_lo*100).toFixed(0)}–${(dir.p_up_hi*100).toFixed(0)}]` : '5d horizon'}</div>
              </div>
              <div class="rk-dir-tile dn">
                <div class="rk-dir-tile-k">▼ P(DN ≥ 5%)</div>
                <div class="rk-dir-tile-v">${pDn != null ? pDn + '%' : '—'}</div>
                <div class="rk-dir-tile-sub">${dir.p_dn_lo != null ? `CI [${(dir.p_dn_lo*100).toFixed(0)}–${(dir.p_dn_hi*100).toFixed(0)}]` : '5d horizon'}</div>
              </div>
            </div>

            <div class="rk-skew">
              <div class="rk-skew-row">
                <span class="lbl-inline">Asymmetry · skew</span>
                <span style="color:${skewColor}; font-weight:700">${skewText}</span>
              </div>
              <div class="rk-skew-track">
                <div class="rk-skew-up" style="width:${(upMass * 100).toFixed(0)}%"></div>
                <div class="rk-skew-dn" style="width:${((1-upMass) * 100).toFixed(0)}%"></div>
                <div class="rk-skew-mid"></div>
              </div>
              <div class="rk-skew-note">${skew != null && skew > 0 ? `${(upMass*100).toFixed(0)}% of return mass above zero` : skew != null && skew < 0 ? `${((1-upMass)*100).toFixed(0)}% of return mass below zero` : 'symmetric distribution'}</div>
            </div>

            <div class="rk-coltitle">Quantile range · 5d</div>
            <table class="rk-tbl">
              <thead><tr><th>Quantile</th><th class="r">Δ%</th><th class="r">Price</th></tr></thead>
              <tbody>
                <tr><td style="color:var(--rd)">q10</td><td class="r"><b class="rd">${fmtSgn(mag.q10)}</b></td><td class="r">${_fmt$(q10_5)}</td></tr>
                <tr><td>q25</td><td class="r">${fmtSgn(mag.q25)}</td><td class="r">${_fmt$(q25_5)}</td></tr>
                <tr><td><b class="ink">q50 median</b></td><td class="r"><b class="${(mag.q50 || 0) >= 0 ? 'gn' : 'rd'}">${fmtSgn(mag.q50)}</b></td><td class="r"><b class="ink">${_fmt$(q50_5)}</b></td></tr>
                <tr><td>q75</td><td class="r"><b class="gn">${fmtSgn(mag.q75)}</b></td><td class="r">${_fmt$(q75_5)}</td></tr>
                <tr><td style="color:var(--gn)">q90</td><td class="r"><b class="gn">${fmtSgn(mag.q90)}</b></td><td class="r">${_fmt$(q90_5)}</td></tr>
              </tbody>
            </table>

            <div class="rk-coltitle" style="margin-top:14px">Per-horizon</div>
            <table class="rk-tbl">
              <thead><tr><th>Horizon</th><th class="r">P(up)</th><th class="r">μ Δ%</th><th class="r">σ Δ%</th></tr></thead>
              <tbody>
                ${horizons.map(r => `
                  <tr>
                    <td>${r.h}</td>
                    <td class="r">${(r.pUp * 100).toFixed(0)}%</td>
                    <td class="r"><b class="${r.mean >= 0 ? 'gn' : 'rd'}">${(r.mean >= 0 ? '+' : '') + r.mean.toFixed(2)}%</b></td>
                    <td class="r">${r.sigma.toFixed(1)}%</td>
                  </tr>`).join('')}
              </tbody>
            </table>
          </div>

          <!-- MIDDLE: large forecast cone -->
          <div>
            <div class="rk-coltitle">Forecast cone · spot → 10d · q10/25/50/75/90 bands · T1/T2/Stop overlays</div>
            <div class="rk-chart-card" style="padding:10px 14px;">
              <svg viewBox="0 0 600 320" style="width:100%; height:300px;">
                ${yLabels.map((_, i) => `<line class="grid" x1="50" y1="${30 + (230 * i / 4)}" x2="585" y2="${30 + (230 * i / 4)}"/>`).join('')}
                ${yLabels.map(l => `<text class="lbl" x="44" y="${l.y}" text-anchor="end">${l.label}</text>`).join('')}

                <text class="lbl" x="50"  y="288" text-anchor="start">T+0</text>
                <text class="lbl" x="175" y="288" text-anchor="middle">1d</text>
                <text class="lbl" x="280" y="288" text-anchor="middle">3d</text>
                <text class="lbl" x="385" y="288" text-anchor="middle">5d</text>
                <text class="lbl" x="555" y="288" text-anchor="end">10d</text>

                <!-- envelopes -->
                <polygon points="${upperHi} ${lowerHi}" fill="var(--info)" opacity="0.10"/>
                <polygon points="${upperLo} ${lowerLo}" fill="var(--info)" opacity="0.22"/>
                <polyline points="${medPath}" fill="none" stroke="var(--info)" stroke-width="2.4"/>

                <!-- Spot line -->
                <line x1="50" y1="${yFor(spot)}" x2="585" y2="${yFor(spot)}" stroke="var(--copper)" stroke-width="1" stroke-dasharray="2,3" opacity="0.45"/>
                <circle cx="50" cy="${yFor(spot)}" r="4" fill="var(--copper)"/>
                <text class="vlbl" x="58" y="${yFor(spot) - 4}" fill="var(--copper)">${_fmt$(spot)} spot</text>

                <!-- T1 -->
                <line x1="50" y1="${yFor(t1)}" x2="585" y2="${yFor(t1)}" stroke="var(--gn)" stroke-width="1" stroke-dasharray="3,3" opacity="0.7"/>
                <text class="vlbl" x="585" y="${yFor(t1) - 4}" text-anchor="end" fill="var(--gn)">T1 ${_fmt$(t1)}${pT1 != null ? ` · P ${(pT1*100).toFixed(0)}%` : ''}</text>

                <!-- T2 -->
                <line x1="50" y1="${yFor(t2)}" x2="585" y2="${yFor(t2)}" stroke="var(--gn)" stroke-width="1" stroke-dasharray="3,3" opacity="0.55"/>
                <text class="vlbl" x="585" y="${yFor(t2) - 4}" text-anchor="end" fill="var(--gn)">T2 ${_fmt$(t2)}${hit.p_t2_first != null ? ` · P ${(hit.p_t2_first*100).toFixed(0)}%` : ''}</text>

                <!-- Stop -->
                <line x1="50" y1="${yFor(stop)}" x2="585" y2="${yFor(stop)}" stroke="var(--rd)" stroke-width="1" stroke-dasharray="3,3" opacity="0.7"/>
                <text class="vlbl" x="585" y="${yFor(stop) + 12}" text-anchor="end" fill="var(--rd)">Stop ${_fmt$(stop)}${pStop != null ? ` · P ${(pStop*100).toFixed(0)}%` : ''}</text>

                <!-- Earnings vertical (if upcoming) -->
                ${erX != null ? `
                  <line x1="${erX}" y1="20" x2="${erX}" y2="280" stroke="var(--amb)" stroke-width="1.2" stroke-dasharray="4,3" opacity="0.6"/>
                  <text class="vlbl" x="${erX + 6}" y="30" fill="var(--amb)">⚠ ER ${erDays}d · close T2 by T-1</text>
                ` : ''}

                <!-- median marker @ 5d -->
                ${q50_5 != null ? `
                  <circle cx="385" cy="${yFor(q50_5)}" r="4" fill="var(--info)"/>
                  <text class="vlbl" x="391" y="${yFor(q50_5) - 4}" fill="var(--info)">μ 5d ${fmtSgn(mag.q50)}</text>
                ` : ''}

                <!-- Legend -->
                <g font-size="9" font-family="JetBrains Mono">
                  <rect x="60" y="12" width="14" height="6" fill="var(--info)" opacity="0.22"/>
                  <text class="vlbl" x="80" y="18">25–75 band</text>
                  <rect x="170" y="12" width="14" height="6" fill="var(--info)" opacity="0.10"/>
                  <text class="vlbl" x="190" y="18">10–90 band</text>
                  <line x1="280" y1="15" x2="300" y2="15" stroke="var(--info)" stroke-width="2"/>
                  <text class="vlbl" x="306" y="18">median</text>
                </g>
              </svg>
              <div style="display:flex; justify-content:space-between; font:600 10px var(--mono); color:var(--ink-3); margin-top:4px;">
                <span>Brownian σ · cone widens with √t</span>
                <span>Levels via <code style="color:var(--copper); font-family:var(--mono)">canonical_trade_plan</code></span>
              </div>
            </div>
          </div>

          <!-- RIGHT: level-hit ladder + headline probs -->
          <div>
            <div class="rk-coltitle">Hit probability · touch before any other level</div>
            ${levels.map(levelRow).join('')}

            <div class="rk-coltitle" style="margin-top:14px">Headline trade probabilities</div>
            <table class="rk-tbl">
              <thead><tr><th>Event</th><th class="r">P</th><th class="r">E[days]</th></tr></thead>
              <tbody>
                <tr><td><b class="gn">Hit T1 before stop</b></td><td class="r"><b class="gn">${pT1 != null ? (pT1*100).toFixed(0)+'%' : '—'}</b></td><td class="r">${hit.e_days_t1 != null ? hit.e_days_t1.toFixed(1) : '—'}</td></tr>
                <tr><td><b class="gn">Hit T2 before stop</b></td><td class="r"><b class="gn">${hit.p_t2_first != null ? (hit.p_t2_first*100).toFixed(0)+'%' : '—'}</b></td><td class="r">${hit.e_days_t2 != null ? hit.e_days_t2.toFixed(1) : '—'}</td></tr>
                <tr><td><b class="rd">Hit stop before T1</b></td><td class="r"><b class="rd">${pStop != null ? (pStop*100).toFixed(0)+'%' : '—'}</b></td><td class="r">${hit.e_days_stop != null ? hit.e_days_stop.toFixed(1) : '—'}</td></tr>
                <tr><td>Range-bound 5d</td><td class="r">${hit.p_range != null ? (hit.p_range*100).toFixed(0)+'%' : '—'}</td><td class="r">—</td></tr>
              </tbody>
            </table>
          </div>

        </div>
      </div>
    </section>`;
}

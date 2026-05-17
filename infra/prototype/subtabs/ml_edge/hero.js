// subtabs/ml_edge/hero.js — .rk-hero (risk-redesign aesthetic).
//
// Layout: banner (badge + question + ticker) → body (cone | 3 gauges | conviction
// matrix) → foot ribbon. Border-left color tints from verdict (gn / rd / am / info).

const fmtPct = (v, d=0) => v == null ? '—' : (v >= 0 ? '+' : '') + (v * 100).toFixed(d) + '%';
const fmtSgn = (v, d=2) => v == null ? '—' : (v >= 0 ? '+' : '') + Number(v).toFixed(d) + '%';
const fmt$   = (v, d=2) => v == null ? '—' : '$' + Number(v).toFixed(d);
const fmtNum = (v, d=2) => v == null ? '—' : Number(v).toFixed(d);

// Map verdict.color to hero flavor (border-left + banner-bg)
const FLAVOR = { pass: 'gn', fail: 'rd', warn: 'am', info: 'info' };

// Map raw color token to .rk-hero / .rk-pill / .rk-cap-val class
const VCLS = { pass: 'gn', fail: 'rd', warn: 'am', info: 'info' };

export function buildHero(ctx) {
  const { sym, payload, T, model } = ctx;
  const v        = payload.verdict || {};
  const flavor   = FLAVOR[v.color] || 'info';
  const conf     = v.confidence || 'LOW';
  const edge     = v.edge != null ? v.edge : null;
  const confluences = v.confluences || [];

  const dir = payload.direction || {};
  const mag = payload.magnitude || {};
  const hit = payload.hit_net || {};
  const pUp = dir.p_up != null ? (dir.p_up * 100).toFixed(0) : null;
  const pDn = dir.p_dn != null ? (dir.p_dn * 100).toFixed(0) : null;
  const pChop = dir.p_chop != null ? (dir.p_chop * 100).toFixed(0) : null;
  const q50 = mag.q50;
  const q10 = mag.q10;
  const q90 = mag.q90;
  const skew = mag.skew;
  const pT1 = hit.p_t1_first != null ? (hit.p_t1_first * 100).toFixed(0) : null;
  const pT2 = hit.p_t2_first != null ? (hit.p_t2_first * 100).toFixed(0) : null;
  const pStop = hit.p_stop_first != null ? (hit.p_stop_first * 100).toFixed(0) : (pT1 != null ? (100 - pT1).toFixed(0) : null);

  // ---- Trade plan levels for the cone overlay ----
  const plan = T.canonical_trade_plan || T.trade_plan || {};
  const spot = +(T.price ?? T.entry_price ?? plan.entry ?? plan.entry_price ?? 0) || 100;
  const stop = +(plan.stop ?? plan.stop_price ?? (spot * 0.96));
  const t1   = +(plan.t1   ?? plan.target1   ?? (spot * 1.04));
  const t2   = +(plan.t2   ?? plan.target2   ?? (spot * 1.08));
  const atr  = T.atr20 != null ? T.atr20.toFixed(2) : (T.atr14 != null ? T.atr14.toFixed(2) : null);
  const ivRank = T.iv_rank != null ? T.iv_rank.toFixed(0) : null;
  const erDays = (T.earnings || {}).days_to_earnings;

  // ---- Cone SVG: spot → 5d → 10d with q10/q25/q50/q75/q90 bands ----
  const q10_5 = mag.q10 != null ? spot * (1 + mag.q10 / 100) : spot * 0.95;
  const q25_5 = mag.q25 != null ? spot * (1 + mag.q25 / 100) : spot * 0.97;
  const q50_5 = mag.q50 != null ? spot * (1 + mag.q50 / 100) : spot;
  const q75_5 = mag.q75 != null ? spot * (1 + mag.q75 / 100) : spot * 1.03;
  const q90_5 = mag.q90 != null ? spot * (1 + mag.q90 / 100) : spot * 1.05;

  const allY = [q10_5, q25_5, q50_5, q75_5, q90_5, stop, t1, t2, spot].filter(Number.isFinite);
  const yMin = Math.min(...allY) * 0.985;
  const yMax = Math.max(...allY) * 1.015;
  const yFor = (px) => 20 + (yMax - px) / (yMax - yMin) * 170; // 20..190 (leave 30 for x-axis labels)

  // Brownian scaling: cone widens with sqrt(t)
  const hzns = [
    { h: '0d', x: 70,  s: 0 },
    { h: '1d', x: 185, s: Math.sqrt(0.2) },
    { h: '3d', x: 305, s: Math.sqrt(0.6) },
    { h: '5d', x: 420, s: 1.0 },
    { h: '10d', x: 575, s: Math.sqrt(2.0) },
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
    yLabels.push({ y: 20 + (170 * i / 4) + 4, label: '$' + p.toFixed(0) });
  }

  // ---- Gauge state helpers ----
  const dirState = dir.p_up == null ? 'info' : dir.p_up >= 0.55 ? 'pass' : dir.p_dn >= 0.55 ? 'fail' : 'warn';
  const magState = mag.q50 == null ? 'info' : mag.q50 >= 1.5 ? 'pass' : mag.q50 <= -1.5 ? 'fail' : 'warn';
  const hitState = hit.p_t1_first == null ? 'info' : hit.p_t1_first >= 0.60 ? 'pass' : hit.p_t1_first >= 0.40 ? 'warn' : 'fail';
  const stateText = { pass: 'CONFIRMED', warn: 'CAUTIONED', fail: 'NEGATIVE', info: 'PRELIM' };

  // Tagline question
  const question = `What is <b>${sym}</b>'s 5-day forward distribution across <span class="copper">all 3 model heads</span>?`;

  // Banner header chips
  const tickerChips = [];
  tickerChips.push(fmt$(spot));
  if (atr) tickerChips.push(`ATR $${atr}`);
  if (ivRank != null) tickerChips.push(`IV-rank ${ivRank}`);
  if (erDays != null && erDays >= 0 && erDays <= 21) tickerChips.push(`ER ${erDays}d`);

  // Cone legend overlays
  const t1Y = yFor(t1), t2Y = yFor(t2), stopY = yFor(stop), spotY = yFor(spot);

  return `
    <section class="rk-hero ${flavor}">
      <div class="rk-hero-banner">
        <div class="rk-hero-badge">ML EDGE</div>
        <div class="rk-hero-q">${question}</div>
        <div class="rk-hero-tk">${sym} <small>${tickerChips.join(' · ')}</small></div>
      </div>

      <div class="rk-hero-body">

        <!-- LEFT: Forecast cone -->
        <div class="rk-hero-cone">
          <div class="rk-hero-cone-h">
            <span>Forecast Cone · spot → 10 trading days · heteroscedastic σ</span>
            <span class="legend">
              <i style="background:rgba(96,165,250,0.18)"></i>25–75 ·
              <i style="background:rgba(96,165,250,0.08)"></i>10–90 ·
              <i style="background:var(--info)"></i>median
            </span>
          </div>
          <svg viewBox="0 0 600 220" preserveAspectRatio="none">
            ${yLabels.map((_, i) => `<line class="grid" x1="50" y1="${20 + (170 * i / 4)}" x2="585" y2="${20 + (170 * i / 4)}"/>`).join('')}
            ${yLabels.map(l => `<text class="lbl" x="44" y="${l.y}" text-anchor="end">${l.label}</text>`).join('')}

            <!-- x-axis labels -->
            <text class="lbl" x="50"  y="208" text-anchor="start">T+0</text>
            <text class="lbl" x="185" y="208" text-anchor="middle">1d</text>
            <text class="lbl" x="305" y="208" text-anchor="middle">3d</text>
            <text class="lbl" x="420" y="208" text-anchor="middle">5d</text>
            <text class="lbl" x="575" y="208" text-anchor="end">10d</text>

            ${(() => {
              // ER vertical line — drawn at the earnings horizon if ER is within
              // 10 trading days. Anchor on the same √t x-scale as the cone bands.
              if (erDays == null || erDays < 0 || erDays > 10) return '';
              // Map erDays → x: 0d=50, 1d=185, 3d=305, 5d=420, 10d=575 (interpolate)
              const xPos =
                erDays <= 1  ? 50  + (erDays / 1)        * (185 - 50)  :
                erDays <= 3  ? 185 + ((erDays - 1) / 2)  * (305 - 185) :
                erDays <= 5  ? 305 + ((erDays - 3) / 2)  * (420 - 305) :
                              420 + ((erDays - 5) / 5)  * (575 - 420);
              return `
                <line x1="${xPos.toFixed(1)}" y1="20" x2="${xPos.toFixed(1)}" y2="190"
                      stroke="var(--amb)" stroke-width="1.5" stroke-dasharray="4,3" opacity="0.7"/>
                <text class="vlbl" x="${(xPos + 4).toFixed(1)}" y="32" fill="var(--amb)">⚡ ER ${erDays}d</text>
                <text class="lbl" x="${(xPos + 4).toFixed(1)}" y="42" fill="var(--amb)" style="font-size:9px;">implied move 2.4× cone</text>`;
            })()}

            <!-- 10-90 envelope -->
            <polygon points="${upperHi} ${lowerHi}" fill="var(--info)" opacity="0.10"/>
            <!-- 25-75 envelope -->
            <polygon points="${upperLo} ${lowerLo}" fill="var(--info)" opacity="0.22"/>
            <!-- Median path -->
            <polyline points="${medPath}" fill="none" stroke="var(--info)" stroke-width="2.2"/>

            <!-- Spot line -->
            <line x1="50" y1="${spotY}" x2="585" y2="${spotY}" stroke="var(--copper)" stroke-width="1" opacity="0.4" stroke-dasharray="2,3"/>
            <circle cx="50" cy="${spotY}" r="4" fill="var(--copper)"/>
            <text class="vlbl" x="58" y="${spotY - 4}" fill="var(--copper)">${fmt$(spot)} spot</text>

            <!-- T1 line -->
            <line x1="50" y1="${t1Y}" x2="585" y2="${t1Y}" stroke="var(--gn)" stroke-width="1" stroke-dasharray="3,3" opacity="0.7"/>
            <text class="vlbl" x="585" y="${t1Y - 4}" text-anchor="end" fill="var(--gn)">T1 ${fmt$(t1)}${pT1 ? ` · P ${pT1}%` : ''}</text>

            <!-- T2 line -->
            <line x1="50" y1="${t2Y}" x2="585" y2="${t2Y}" stroke="var(--gn)" stroke-width="1" stroke-dasharray="3,3" opacity="0.55"/>
            <text class="vlbl" x="585" y="${t2Y - 4}" text-anchor="end" fill="var(--gn)">T2 ${fmt$(t2)}${pT2 ? ` · P ${pT2}%` : ''}</text>

            <!-- Stop line -->
            <line x1="50" y1="${stopY}" x2="585" y2="${stopY}" stroke="var(--rd)" stroke-width="1" stroke-dasharray="3,3" opacity="0.7"/>
            <text class="vlbl" x="585" y="${stopY + 12}" text-anchor="end" fill="var(--rd)">Stop ${fmt$(stop)}${pStop ? ` · P ${pStop}%` : ''}</text>

            <!-- Median tail marker -->
            ${q50 != null ? `
              <circle cx="420" cy="${yFor(q50_5)}" r="3.5" fill="var(--info)"/>
              <text class="vlbl" x="426" y="${yFor(q50_5) - 4}" fill="var(--info)">μ 5d ${fmtSgn(q50)}</text>
            ` : ''}
          </svg>
        </div>

        <!-- MIDDLE: 3 head gauges -->
        <div class="rk-hero-gauges">
          <div class="rk-hero-gauges-h">3 Model Heads · 5d horizon</div>
          <div class="rk-hero-gauges-grid">

            <div class="rk-gauge dir">
              <div class="rk-gauge-head">
                <div class="rk-gauge-k">▲ Direction · P(UP)</div>
                <span class="rk-gauge-status ${dirState}">${stateText[dirState]}</span>
              </div>
              <div class="rk-gauge-row">
                <div class="rk-gauge-v">${pUp != null ? pUp + '%' : '—'}</div>
                <div class="rk-gauge-sub">${pChop != null ? `chop ${pChop} · dn ${pDn}` : '3-class'}</div>
              </div>
              <div class="rk-gauge-bar"><div style="width:${pUp || 0}%"></div></div>
              <div class="rk-gauge-foot">${dir.edge != null ? `Edge ${fmtSgn(dir.edge * 100, 1)}` : '3-class · isotonic'}</div>
            </div>

            <div class="rk-gauge mag">
              <div class="rk-gauge-head">
                <div class="rk-gauge-k">μ Magnitude · median 5d</div>
                <span class="rk-gauge-status ${magState}">${stateText[magState]}</span>
              </div>
              <div class="rk-gauge-row">
                <div class="rk-gauge-v">${q50 != null ? fmtSgn(q50) : '—'}</div>
                <div class="rk-gauge-sub">${skew != null ? `skew ${skew >= 0 ? '+' : ''}${skew.toFixed(2)}` : 'quantile'}</div>
              </div>
              <div class="rk-gauge-bar"><div style="width:${Math.min(100, Math.max(0, 50 + (q50 || 0) * 5))}%"></div></div>
              <div class="rk-gauge-foot">${q10 != null && q90 != null ? `q10 ${fmtSgn(q10)} · q90 ${fmtSgn(q90)}` : 'q10/q25/q50/q75/q90'}</div>
            </div>

            <div class="rk-gauge hit">
              <div class="rk-gauge-head">
                <div class="rk-gauge-k">◎ Hit-Net · P(T1 first)</div>
                <span class="rk-gauge-status ${hitState}">${stateText[hitState]}</span>
              </div>
              <div class="rk-gauge-row">
                <div class="rk-gauge-v">${pT1 != null ? pT1 + '%' : '—'}</div>
                <div class="rk-gauge-sub">${hit.target_thr_pct != null ? `for +${hit.target_thr_pct.toFixed(1)}% → ${fmt$(t1)}` : pStop != null ? `stop first ${pStop}%` : 'level-touch'}</div>
              </div>
              <div class="rk-gauge-bar"><div style="width:${pT1 || 0}%"></div></div>
              <div class="rk-gauge-foot">${hit.conditional ? '◆ conditional on trade plan · ' : ''}${hit.model_auc != null ? `AUC ${hit.model_auc.toFixed(2)} · Kelly thr 60%` : 'Kelly threshold 60%'}</div>
            </div>

          </div>
        </div>

        <!-- RIGHT: Conviction matrix -->
        <div class="rk-cap-matrix">
          <div class="rk-cap-h">Conviction Matrix</div>

          <div class="rk-cap-row">
            <span class="rk-cap-lbl">Edge score</span>
            <span class="rk-cap-val info">${edge != null ? edge.toFixed(1) + ' / 10' : '—'}</span>
            <div class="rk-cap-bar"><div class="info" style="width:${edge != null ? Math.min(100, edge * 10) : 0}%"></div></div>
          </div>

          <div class="rk-cap-row">
            <span class="rk-cap-lbl">Confidence</span>
            <span class="rk-cap-val ${conf === 'HIGH' ? 'gn' : conf === 'MED' ? 'am' : 'rd'}">${conf}</span>
            <div class="rk-cap-bar"><div class="${conf === 'HIGH' ? 'gn' : conf === 'MED' ? 'am' : 'rd'}" style="width:${conf === 'HIGH' ? 90 : conf === 'MED' ? 55 : 25}%"></div></div>
          </div>

          <div class="rk-cap-row">
            <span class="rk-cap-lbl">Confluences</span>
            <span class="rk-cap-val info">${confluences.length}</span>
            <div class="rk-cap-bar"><div class="info" style="width:${Math.min(100, confluences.length * 12)}%"></div></div>
          </div>

          <div class="rk-cap-row">
            <span class="rk-cap-lbl">Asymmetry (skew)</span>
            <span class="rk-cap-val ${skew == null ? '' : skew > 0.2 ? 'gn' : skew < -0.2 ? 'rd' : 'am'}">${skew != null ? (skew >= 0 ? '+' : '') + skew.toFixed(2) : '—'}</span>
            <div class="rk-cap-bar"><div class="${skew == null ? '' : skew > 0.2 ? 'gn' : skew < -0.2 ? 'rd' : 'am'}" style="width:${skew != null ? Math.min(100, Math.max(10, Math.abs(skew) * 100 + 30)) : 0}%"></div></div>
          </div>

          <div class="rk-cap-row">
            <span class="rk-cap-lbl">Health</span>
            <span class="rk-cap-val ${model.calibration_health === 'ok' ? 'gn' : 'am'}">${(model.calibration_health || 'unknown').toUpperCase()}</span>
            <div class="rk-cap-bar"><div class="${model.calibration_health === 'ok' ? 'gn' : 'am'}" style="width:${model.calibration_health === 'ok' ? 80 : 40}%"></div></div>
          </div>

          ${erDays != null && erDays >= 0 && erDays <= 21 ? `
          <div class="rk-cap-row">
            <span class="rk-cap-lbl">ER overhang</span>
            <span class="rk-cap-val am">${erDays}d</span>
            <div class="rk-cap-bar"><div class="am" style="width:${Math.max(10, 100 - erDays * 5)}%"></div></div>
          </div>` : ''}
        </div>
      </div>

      <div class="rk-hero-foot">
        <span>Verdict: <b class="${VCLS[v.color] || 'info'}">${v.text || 'NEUTRAL'}</b></span>
        ${edge != null ? `<span>Edge: <b class="info">${edge.toFixed(1)} / 10</b></span>` : ''}
        <span>Confidence: <b class="${conf === 'HIGH' ? 'gn' : conf === 'MED' ? 'am' : 'rd'}">${conf}</b></span>
        <span>Confluences: <b>${confluences.length}</b></span>
        ${pT1 != null && +pT1 >= 60 ? `<span>P(T1) clears Kelly 60% threshold by <b class="gn">+${(+pT1 - 60).toFixed(0)}pp</b></span>` : pT1 != null ? `<span>P(T1) <b class="am">${pT1}%</b> below Kelly 60% threshold</span>` : ''}
        ${erDays != null && erDays >= 0 && erDays <= 14 ? `<span class="am">⚠ ER ${erDays}d — close T2 by EOD T-1</span>` : ''}
        ${model.preliminary ? `<span class="am">⚠ Preliminary model · n=${model.n_total || '?'}</span>` : ''}
      </div>
    </section>

    ${_buildCrossHorizonStrip(ctx)}`;
}

// Cross-horizon strip — shows swing/position/invest predictions side-by-side for
// THIS ticker so the user can see horizon-dependent edge without leaving the page.
// Reads from window.__mlEdgeCache, which the orchestrator populated; falls back
// to a single-mode strip if the cache only has one mode (legacy v1).
function _buildCrossHorizonStrip(ctx) {
  const { sym } = ctx;
  const cache = window.__mlEdgeCache;
  if (!cache || !cache.predictions) return '';
  const preds = cache.predictions;
  if (preds.direction) return '';  // v1 flat schema — no per-mode split
  const modes = [
    { k: 'swing',    label: '⚡ Swing · 5d',     days: 5 },
    { k: 'position', label: '📈 Position · 21d', days: 21 },
    { k: 'invest',   label: '🏛 Invest · 126d',  days: 126 },
  ];
  const colTone = c => c === 'pass' ? 'gn' : c === 'fail' ? 'rd' : c === 'warn' ? 'am' : 'info';
  const cards = modes.map(m => {
    const p = (preds[m.k] || {})[sym];
    if (!p || !p.direction) {
      return `<div class="rk-cross-card empty"><div class="rk-cross-h">${m.label}</div><div class="rk-cross-empty">no prediction</div></div>`;
    }
    const d = p.direction, mg = p.magnitude || {}, h = p.hit_net || {};
    const tone = colTone((p.verdict || {}).color);
    const pUpV = (d.p_up * 100).toFixed(0);
    const pDnV = (d.p_dn * 100).toFixed(0);
    const q50V = mg.q50 != null ? (mg.q50 >= 0 ? '+' : '') + mg.q50.toFixed(1) + '%' : '—';
    const pT1V = h.p_t1_first != null ? (h.p_t1_first * 100).toFixed(0) + '%' : '—';
    return `
      <div class="rk-cross-card ${tone}">
        <div class="rk-cross-h">${m.label}</div>
        <div class="rk-cross-verdict ${tone}">${(p.verdict || {}).text || 'NEUTRAL'}</div>
        <div class="rk-cross-row"><span>P(up)</span><b class="gn">${pUpV}%</b></div>
        <div class="rk-cross-row"><span>P(dn)</span><b class="rd">${pDnV}%</b></div>
        <div class="rk-cross-row"><span>μ ${m.days}d</span><b class="${(mg.q50 || 0) >= 0 ? 'gn' : 'rd'}">${q50V}</b></div>
        <div class="rk-cross-row"><span>P(T1)</span><b class="${(h.p_t1_first || 0) >= 0.6 ? 'gn' : 'am'}">${pT1V}</b></div>
      </div>`;
  }).join('');
  // Detect horizon flip / alignment
  const colors = modes.map(m => ((preds[m.k] || {})[sym] || {}).verdict?.color).filter(Boolean);
  const uniq = new Set(colors);
  const aligned = uniq.size === 1 && colors.length === 3;
  const flipped = uniq.has('pass') && uniq.has('fail');
  let banner = '';
  if (aligned) {
    const tone = colTone(colors[0]);
    banner = `<div class="rk-cross-banner ${tone}">✓ ALL 3 HORIZONS ALIGNED · cross-horizon ${colors[0] === 'pass' ? 'BULLISH' : colors[0] === 'fail' ? 'BEARISH' : 'NEUTRAL'} — high-conviction signal</div>`;
  } else if (flipped) {
    banner = `<div class="rk-cross-banner am">⚠ HORIZON FLIP · swing &amp; invest disagree on direction — edge is horizon-specific, size to the winning horizon</div>`;
  } else {
    banner = `<div class="rk-cross-banner info">◐ HORIZON-DEPENDENT · modes agree on direction but conviction strength varies — see which mode's pill is strongest above</div>`;
  }
  return `
    <section class="rk-cross-section">
      ${banner}
      <div class="rk-cross-grid">${cards}</div>
    </section>`;
}

// subtabs/models/multimethod.js — extracted from elite-detail.html (renderMultiMethod 2026-05-09)
// CapStudio modular loader for the per-ticker detail page.
// T (current ticker) accessed via window.__getDetailTicker() — NOT yet wired
// in elite-detail.html. This module is created as a candidate for future
// activation; calling render() before wiring requires window.T to be set.

const _T = () => (window.__getDetailTicker ? window.__getDetailTicker() : window.T);

export function render() {
  const T = _T();
  // ─── Cross-method consensus & method-confidence — elite analyzer hero ───
  const tc = T.theory_confluence || {};
  const tcStates = tc.states || {};
  const tcDetails = tc.details || {};
  const wyState = tcStates.wyckoff || 'UNKNOWN';
  const ewState = tcStates.elliott || 'UNKNOWN';
  const dowState = tcStates.dow || 'UNKNOWN';
  const wyUnclear = ['UNKNOWN','UNAVAILABLE','INVALID','NEUTRAL'].includes(wyState);
  const ewUnclear = ['UNKNOWN','UNAVAILABLE','INVALID','CORRECTIVE'].includes(ewState);

  // Map states → bias for each method
  const bullStates = ['BULLISH','MARKUP','ACCUMULATION','EARLY_IMPULSE'];
  const bearStates = ['BEARISH','MARKDOWN','DISTRIBUTION','LATE_IMPULSE'];
  const biasOf = state => bullStates.includes(state) ? 'bull' : bearStates.includes(state) ? 'bear' : 'neut';
  const ew = T.elliott_wave || {};
  const wyBias = biasOf(wyState);
  const ewBias = ewState === 'CORRECTIVE' ? 'bear' : biasOf(ewState);
  // Monte Carlo bias inferred from setup_quality / score / momentum (no model run yet at hero render time)
  const mcBiasFromScore = T.score >= 75 ? 'bull' : T.score <= 50 ? 'bear' : 'neut';
  const mcBias = mcBiasFromScore;

  // Confidence per method
  const confLevel = c => c === 'HIGH' ? 'high' : c === 'MED' ? 'med' : 'low';
  const wyConf = confLevel((tcDetails.wyckoff || {}).confidence || 'LOW');
  const ewConf = ew.confidence === 'high' ? 'high' : ew.confidence === 'medium' ? 'med' : 'low';
  const mcConf = T.score >= 75 ? 'high' : T.score >= 60 ? 'med' : 'low';

  // Composite
  const biases = [wyBias, ewBias, mcBias];
  const bullCt = biases.filter(b => b === 'bull').length;
  const bearCt = biases.filter(b => b === 'bear').length;
  let composite, compArrow, compLabel;
  if (bullCt >= 2) { composite = 'bull'; compArrow = '▲'; compLabel = bullCt === 3 ? 'STRONG BULLISH' : 'BULLISH'; }
  else if (bearCt >= 2) { composite = 'bear'; compArrow = '▼'; compLabel = bearCt === 3 ? 'STRONG BEARISH' : 'BEARISH'; }
  else { composite = 'mixed'; compArrow = '◆'; compLabel = 'MIXED'; }

  // Composite confidence
  const sameDir = composite === 'bull' ? bullCt : composite === 'bear' ? bearCt : 0;
  const compConf = sameDir === 3 ? 'high' : sameDir === 2 ? 'med' : 'low';

  // K6 (2026-05-09): canonical_trade_plan first; fall back to legacy fields.
  // The Bear/Severe scenario derivations now anchor on the same stop/T1/T2
  // numbers as Plan/Thesis/SMC/Overview — Vinod's "Bear case & Severe Case
  // doesn't align with overall Plan and Thesis" complaint resolved here.
  const _ctp = T?.canonical_trade_plan;
  const _ctpStop = _ctp?.stop;
  const _ctpT1   = _ctp?.target1;
  const _ctpEW   = _ctp?.setup?.elliott_wave;

  // Synthesized levels per method (rough — actual computation inside _drawExpertMM)
  const px0 = +(T.price || 0);
  const atr = (T.atr_pct || 0) / 100 * px0;
  // EW Wave-3 target: prefer canonical Fib-extension T2 (1.618), then T1 (1.272),
  // then legacy fib_levels['161.8%'], then 8% above price.
  const ewW3target = (_ctpEW?.t2_extension) || (_ctpEW?.t1_extension)
    || (ew.fib_levels && ew.fib_levels['161.8%'] ? +ew.fib_levels['161.8%'] : (_ctpT1 || T.t1 || px0 * 1.08));
  const ewBaseStop = (_ctpEW?.swing_low ? +_ctpEW.swing_low * 0.97 : null)
    ?? (ew.swing_base ? +ew.swing_base * 0.97 : (_ctpStop || T.stop || px0 * 0.95));
  const wyT1 = T.fractal_high || px0 * 1.06;
  const wySpring = T.fractal_low ? +T.fractal_low * 0.96 : px0 * 0.92;
  const mcTarget = _ctpT1 || T.t1 || px0 * 1.05;
  const mcStop = _ctpStop || T.stop || px0 * 0.96;

  // Method evidence — short narrative per method
  const wyEvidence = (tcDetails.wyckoff || {}).evidence || '—';
  const ewEvidence = (tcDetails.elliott || {}).evidence || (ew.wave_label || '—');
  const mcEvidence = `Score ${T.score || 0} · ${T.setup_family || 'no setup'} · RR ${T.rr_ratio ? T.rr_ratio.toFixed(1) + '×' : '—'}`;

  // Cross-method narrative
  const methodWords = (b) => b === 'bull' ? 'long' : b === 'bear' ? 'short' : 'neutral';
  let narrative = '';
  if (composite === 'bull') {
    const bullMethods = [['Wyckoff', wyBias], ['Elliott', ewBias], ['Monte Carlo', mcBias]].filter(m => m[1] === 'bull').map(m => m[0]);
    const dissenter = [['Wyckoff', wyBias], ['Elliott', ewBias], ['Monte Carlo', mcBias]].find(m => m[1] !== 'bull');
    narrative = `<b>${bullMethods.join(' + ')}</b> align bullish.${dissenter ? ` <em>${dissenter[0]} ${methodWords(dissenter[1])} — possible due to ${dissenter[1] === 'neut' ? 'unclear pattern in this method' : 'weight on different signals'}.</em>` : ' All three methods agree — high-confidence setup.'} Trade with ${compConf === 'high' ? 'full' : 'moderate'} edge sizing.`;
  } else if (composite === 'bear') {
    const bearMethods = [['Wyckoff', wyBias], ['Elliott', ewBias], ['Monte Carlo', mcBias]].filter(m => m[1] === 'bear').map(m => m[0]);
    const dissenter = [['Wyckoff', wyBias], ['Elliott', ewBias], ['Monte Carlo', mcBias]].find(m => m[1] !== 'bear');
    narrative = `<b>${bearMethods.join(' + ')}</b> align bearish.${dissenter ? ` <em>${dissenter[0]} ${methodWords(dissenter[1])} dissents.</em>` : ' Full bearish alignment.'} Avoid longs or trade short pullbacks.`;
  } else {
    narrative = `Methods disagree — <b>${biases.filter(b=>b==='bull').length} bull · ${biases.filter(b=>b==='bear').length} bear · ${biases.filter(b=>b==='neut').length} neutral</b>. <em>No clear edge — wait for confluence to emerge or trade smaller size.</em>`;
  }

  const conf2pct = c => c === 'high' ? 90 : c === 'med' ? 60 : 30;
  const stateLabel = s => (s || '—').replace(/_/g, ' ');

  // Confidence banner — kept for synthesized-pattern warning
  const unclearList = [];
  if (wyUnclear) unclearList.push(`Wyckoff: <b style="color:#fff8d0">${wyState}</b>`);
  if (ewUnclear) unclearList.push(`Elliott: <b style="color:#fff8d0">${ewState}</b>`);
  const synthBanner = unclearList.length ? `
    <div style="background:linear-gradient(90deg,#3a3414,#2a2510);border:1px solid #5a4d1a;border-left:3px solid #e8c860;border-radius:6px;padding:10px 14px;margin-bottom:12px;display:flex;gap:10px;align-items:flex-start">
      <span style="color:#e8c860;font-size:14px;line-height:1">⚠</span>
      <div style="flex:1;font-size:11.5px;color:var(--ink-1);line-height:1.45">
        <b style="color:#fff8d0">Synthesized visualization warning:</b> ${unclearList.join(' · ')}. Method anchors below default to current price — treat as scenario planning, not a detected pattern.
      </div>
    </div>` : '';

  // ── Hero HTML ──
  const heroHtml = `
    <div class="mmh-hero">
      <div class="mmh-consensus ${composite}">
        <div class="mmh-c-tag">CROSS-METHOD CONSENSUS</div>
        <div style="display:flex;align-items:center;gap:14px">
          <div class="mmh-c-arrow">${compArrow}</div>
          <div style="flex:1">
            <div class="mmh-c-label">${compLabel}</div>
            <div class="mmh-c-agree"><b>${sameDir}</b>/3 methods agree</div>
          </div>
        </div>
        <div class="mmh-c-conf ${compConf}">Confidence ${compConf.toUpperCase()}</div>
      </div>
      <div class="mmh-methods">
        <div class="mmh-method ${mcBias}">
          <div class="mmh-m-h"><span class="ico">📈</span><span class="name">Monte Carlo</span><span class="pill ${mcBias}">${mcBias === 'bull' ? 'BULL' : mcBias === 'bear' ? 'BEAR' : 'NEUT'}</span></div>
          <div class="mmh-m-state">GBM ${T.score || 0}/100 score</div>
          <div class="mmh-m-conf-bar"><div class="mmh-m-conf-fill ${mcConf}" style="width:${conf2pct(mcConf)}%"></div></div>
          <div class="mmh-m-evidence">${mcEvidence}</div>
          <div class="mmh-m-target"><span class="l">P50 target</span><span class="r">$${mcTarget.toFixed(2)}</span></div>
          <div class="mmh-m-target"><span class="l">P10 floor</span><span class="r">$${mcStop.toFixed(2)}</span></div>
        </div>
        <div class="mmh-method ${ewBias}">
          <div class="mmh-m-h"><span class="ico">🌊</span><span class="name">Elliott Wave</span><span class="pill ${ewBias}">${ewBias === 'bull' ? 'BULL' : ewBias === 'bear' ? 'BEAR' : 'NEUT'}</span></div>
          <div class="mmh-m-state">${ew.wave_number && ew.wave_number !== '?' ? `Wave ${ew.wave_number} · ${stateLabel(ewState)}` : stateLabel(ewState)}</div>
          <div class="mmh-m-conf-bar"><div class="mmh-m-conf-fill ${ewConf}" style="width:${conf2pct(ewConf)}%"></div></div>
          <div class="mmh-m-evidence">${ewEvidence}</div>
          <div class="mmh-m-target"><span class="l">W3 target</span><span class="r">$${ewW3target.toFixed(2)}</span></div>
          <div class="mmh-m-target"><span class="l">Stop (swing base)</span><span class="r">$${ewBaseStop.toFixed(2)}</span></div>
        </div>
        <div class="mmh-method ${wyBias}">
          <div class="mmh-m-h"><span class="ico">⛏</span><span class="name">Wyckoff</span><span class="pill ${wyBias}">${wyBias === 'bull' ? 'BULL' : wyBias === 'bear' ? 'BEAR' : 'NEUT'}</span></div>
          <div class="mmh-m-state">${stateLabel(wyState)}</div>
          <div class="mmh-m-conf-bar"><div class="mmh-m-conf-fill ${wyConf}" style="width:${conf2pct(wyConf)}%"></div></div>
          <div class="mmh-m-evidence">${wyEvidence}</div>
          <div class="mmh-m-target"><span class="l">T1 target</span><span class="r">$${wyT1.toFixed(2)}</span></div>
          <div class="mmh-m-target"><span class="l">Spring/stop</span><span class="r">$${wySpring.toFixed(2)}</span></div>
        </div>
      </div>
    </div>
    <div class="mmh-narr">
      <span class="mmh-narr-i">▸</span>
      <div class="mmh-narr-t">${narrative}</div>
    </div>`;

  $('multimethodBody').innerHTML = heroHtml + synthBanner + `
    <div class="mmh-utility">
      <span class="lbl">Horizon</span>
      <select id="mmDays"><option value="30">30d</option><option value="60">60d</option><option value="90" selected>90d</option><option value="180">180d</option><option value="365">1y</option></select>
      <span class="lbl">Sims</span>
      <select id="mmSims"><option value="200">200</option><option value="500" selected>500</option><option value="1000">1000</option><option value="2000">2000</option></select>
      <div class="strip" id="mmStrip" style="display:flex;gap:8px"></div>
      <button class="rerun" onclick="renderMultiMethod()">↻ RE-RUN MODEL</button>
    </div>
    <div class="mm-tabs">
      <div class="mm-tab on" data-mm="mc">📈 Monte Carlo</div>
      <div class="mm-tab" data-mm="ew">🌊 Elliott Wave</div>
      <div class="mm-tab" data-mm="wy">⛏ Wyckoff</div>
      <div class="mm-tab" data-mm="ex">🧠 Expert View</div>
      <div class="mm-tab" data-mm="sc">🎯 Scenarios</div>
      <div class="mm-tab" data-mm="cfg">⚙ TICKER_CONFIG</div>
    </div>
    <div class="mm-pane on" data-mm-pane="mc">
      <div class="mm-mctab">
        <div class="opt on" data-mc="paths">Paths</div>
        <div class="opt" data-mc="dist">Distribution</div>
        <div class="opt" data-mc="levels">Levels</div>
      </div>
      <div id="mcPathsPane"><svg id="mcPathsSvg" class="mm-canvas"></svg></div>
      <div id="mcDistPane" style="display:none"><svg id="mcDistSvg" class="mm-canvas"></svg></div>
      <div id="mcLevelsPane" style="display:none"><div style="background:var(--bg-1);border:1px solid var(--rule);border-radius:8px;padding:18px"><div style="font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--ink-1);margin-bottom:12px;font-weight:700">GBM Percentile Table</div><div id="mcLevelsBody"></div></div></div>
    </div>
    <div class="mm-pane" data-mm-pane="ew">
      <div class="mm-controls">
        <span class="lbl">Degree</span>
        <span class="seg" id="ewDegreeMM">
          <span class="opt" data-d="major">Major Ⅰ–Ⅴ</span>
          <span class="opt on" data-d="intermediate">Intermediate ①–⑤</span>
          <span class="opt" data-d="minor">Minor 1–5</span>
        </span>
        <span class="lbl" style="margin-left:8px">Mode</span>
        <span class="seg" id="ewModeMM">
          <span class="opt on" data-m="impulse">Impulse</span>
          <span class="opt" data-m="corrective">Corrective A-B-C</span>
        </span>
        <span class="lbl" style="margin-left:8px">W0</span>
        <input id="mmW0" type="number" step="0.01" placeholder="auto" style="width:80px;background:var(--bg-1);border:1px solid var(--rule);color:var(--text);font-family:inherit;font-size:11px;padding:4px 7px;border-radius:4px" oninput="mmSetEwAnchor()">
        <span class="lbl">W1</span>
        <input id="mmW1" type="number" step="0.01" placeholder="auto" style="width:80px;background:var(--bg-1);border:1px solid var(--rule);color:var(--text);font-family:inherit;font-size:11px;padding:4px 7px;border-radius:4px" oninput="mmSetEwAnchor()">
        <span class="lbl">W2</span>
        <input id="mmW2" type="number" step="0.01" placeholder="auto" style="width:80px;background:var(--bg-1);border:1px solid var(--rule);color:var(--text);font-family:inherit;font-size:11px;padding:4px 7px;border-radius:4px" oninput="mmSetEwAnchor()">
        <button class="btn" onclick="mmClearEwAnchors()" style="padding:4px 10px;font-size:10px">Auto</button>
      </div>
      <svg id="ewSvgMM" class="mm-canvas" style="aspect-ratio:16/7"></svg>
      <div class="mm-grid-2" style="margin-top:12px">
        <div style="background:var(--bg-1);border:1px solid var(--rule);border-radius:8px;padding:14px"><div style="font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--ink-1);margin-bottom:10px;font-weight:700">Validation</div><div id="ewValidateMM"></div></div>
        <div style="background:var(--bg-1);border:1px solid var(--rule);border-radius:8px;padding:14px"><div style="font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--ink-1);margin-bottom:10px;font-weight:700">Fibonacci Targets</div><div id="ewFibsMM"></div></div>
      </div>
    </div>
    <div class="mm-pane" data-mm-pane="wy">
      <div class="mm-controls">
        <span class="lbl">Phase</span>
        <span class="seg" id="wyPhaseMM">
          <span class="opt on" data-p="accumulation">Accumulation</span>
          <span class="opt" data-p="distribution">Distribution</span>
        </span>
        <span class="lbl" style="margin-left:8px">Current</span>
        <span class="seg" id="wyCurrentMM">
          <span class="opt" data-c="A">A</span><span class="opt" data-c="B">B</span><span class="opt on" data-c="C">C</span><span class="opt" data-c="D">D</span><span class="opt" data-c="E">E</span>
        </span>
        <span class="lbl" style="margin-left:8px">SC</span>
        <input id="mmSC" type="number" step="0.01" placeholder="auto" style="width:75px;background:var(--bg-1);border:1px solid var(--rule);color:var(--text);font-family:inherit;font-size:11px;padding:4px 7px;border-radius:4px" oninput="mmSetWyAnchor()">
        <span class="lbl">AR</span>
        <input id="mmAR" type="number" step="0.01" placeholder="auto" style="width:75px;background:var(--bg-1);border:1px solid var(--rule);color:var(--text);font-family:inherit;font-size:11px;padding:4px 7px;border-radius:4px" oninput="mmSetWyAnchor()">
        <span class="lbl">Creek</span>
        <input id="mmCreek" type="number" step="0.01" placeholder="auto" style="width:75px;background:var(--bg-1);border:1px solid var(--rule);color:var(--text);font-family:inherit;font-size:11px;padding:4px 7px;border-radius:4px" oninput="mmSetWyAnchor()">
        <span class="lbl">Spring</span>
        <input id="mmSpring" type="number" step="0.01" placeholder="auto" style="width:75px;background:var(--bg-1);border:1px solid var(--rule);color:var(--text);font-family:inherit;font-size:11px;padding:4px 7px;border-radius:4px" oninput="mmSetWyAnchor()">
        <button class="btn" onclick="mmClearWyAnchors()" style="padding:4px 10px;font-size:10px">Auto</button>
      </div>
      <svg id="wySvgMM" class="mm-canvas" style="aspect-ratio:16/7"></svg>
      <div class="mm-grid-2" style="margin-top:12px">
        <div style="background:var(--bg-1);border:1px solid var(--rule);border-radius:8px;padding:14px"><div style="font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--ink-1);margin-bottom:10px;font-weight:700">Targets (P&amp;F method)</div><div id="wyTargetsMM"></div></div>
        <div style="background:var(--bg-1);border:1px solid var(--rule);border-radius:8px;padding:14px"><div style="font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--ink-1);margin-bottom:10px;font-weight:700">Phase Guide</div><div id="wyGuideMM" style="font-size:11.5px;color:var(--ink-2);line-height:1.55"></div></div>
      </div>
    </div>
    <div class="mm-pane" data-mm-pane="ex">
      <div style="background:var(--bg-1);border:1px solid var(--rule);border-radius:8px;padding:14px;margin-bottom:14px"><div style="font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--ink-1);margin-bottom:10px;font-weight:700">Composite Bias</div><div id="exBiasMM" style="font-size:14px;font-weight:700"></div></div>
      <div class="mm-horizons" id="exHorizonsMM"></div>
      <div style="background:var(--bg-1);border:1px solid var(--rule);border-radius:8px;padding:14px;margin-top:14px"><div style="font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--ink-1);margin-bottom:10px;font-weight:700">Signal Matrix</div><div id="exMatrixMM"></div></div>
    </div>

    <div class="mm-pane" data-mm-pane="sc"><div id="scBody"></div></div>

    <div class="mm-pane" data-mm-pane="cfg">
      <div style="background:var(--bg-1);border:1px solid var(--rule);border-radius:8px;padding:16px;margin-bottom:14px">
        <div style="font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--ink-1);font-weight:700;margin-bottom:10px">Load TICKER_CONFIG — paste content from <code style="background:var(--bg-2);padding:2px 6px;border-radius:3px">TICKER_CONFIG.js</code> to analyse any ticker (MSTR, SBET, TSLA, custom)</div>
        <textarea id="mmConfigInput" placeholder="Paste TICKER_CONFIG.js here&#10;Supports: btc_treasury · eth_treasury · earnings · commodity · rate_sensitive · value&#10;Elliott Wave + Wyckoff anchors pre-loaded from config defaults." style="width:100%;height:180px;background:var(--bg-0);border:1px solid var(--rule-2);color:var(--text);font-family:monospace;font-size:11px;padding:10px;border-radius:4px;resize:vertical;line-height:1.5"></textarea>
        <div style="display:flex;gap:8px;margin-top:10px;align-items:center">
          <button class="btn primary" onclick="mmLoadConfig()" style="padding:8px 16px">▶ Load &amp; Run</button>
          <button class="btn" onclick="mmClearConfig()" style="padding:8px 12px">✕ Clear (use bundle)</button>
          <span id="mmConfigStatus" style="font-size:11px;color:var(--ink-3)">Using bundle data for ${T ? T.ticker : '—'}</span>
        </div>
      </div>
      <div style="background:var(--bg-1);border:1px solid var(--rule);border-radius:8px;padding:16px">
        <div style="font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--ink-1);font-weight:700;margin-bottom:12px">Driver Types — drift (μ) formula used per asset class</div>
        ${[['btc_treasury','MSTR · COIN · MARA · RIOT','NAV-implied drift: (BTC_holdings/shares × btc_price × mNAV − S0) / S0 × 252/days + macro_adj − dilution − debt_penalty'],
           ['eth_treasury','SBET · ETHE','NAV + staking APR compound: ETH/share grows passively via 3.8% APR'],
           ['earnings','TSLA · NVDA · AAPL · any equity','Fund drift = epsG×0.004 + revG×0.002 − max(0,(pe−20)×0.001) + technicals + macro'],
           ['commodity','XOM · FCX · AA · SLB','(commodity_price − breakeven) / breakeven × commodity_beta + macro_adj'],
           ['rate_sensitive','BAC · JPM · BRK · WFC','earnings_drift + max(0,rates−3) × NIM_sensitivity × 0.5 + macro_adj'],
           ['value','Low P/E · cyclicals','Mean-reversion toward fair-value P/E + dividend yield'],
          ].map(([t,eg,desc]) => `<div style="padding:9px 0;border-bottom:1px dashed var(--rule)">
            <div style="display:flex;gap:10px;align-items:baseline;flex-wrap:wrap">
              <code style="background:color-mix(in oklch,var(--info) 14%,transparent);color:var(--info);padding:2px 8px;border-radius:3px;font-size:11px;font-weight:700">${t}</code>
              <span style="font-size:11px;color:var(--ink-3)">${eg}</span>
            </div>
            <div style="font-size:11px;color:var(--ink-2);margin-top:3px;line-height:1.5;font-family:monospace">${desc}</div>
          </div>`).join('')}
      </div>
    </div>`;

  // Wire handlers
  if ($('mmDays')) { $('mmDays').value = MM_STATE.days; $('mmSims').value = MM_STATE.sims;
    $('mmDays').addEventListener('change', () => { MM_STATE.days = +$('mmDays').value; renderMultiMethod(); });
    $('mmSims').addEventListener('change', () => { MM_STATE.sims = +$('mmSims').value; renderMultiMethod(); }); }
  document.querySelectorAll('.mm-tab').forEach(t => t.addEventListener('click', () => {
    const tab = t.dataset.mm;
    document.querySelectorAll('.mm-tab').forEach(x => x.classList.toggle('on', x === t));
    document.querySelectorAll('.mm-pane').forEach(p => p.classList.toggle('on', p.dataset.mmPane === tab)); }));
  document.querySelectorAll('.mm-mctab .opt').forEach(o => o.addEventListener('click', () => {
    const v = o.dataset.mc;
    document.querySelectorAll('.mm-mctab .opt').forEach(x => x.classList.toggle('on', x === o));
    $('mcPathsPane').style.display = v === 'paths' ? 'block' : 'none';
    $('mcDistPane').style.display = v === 'dist' ? 'block' : 'none';
    $('mcLevelsPane').style.display = v === 'levels' ? 'block' : 'none'; }));
  document.querySelectorAll('#ewDegreeMM .opt').forEach(o => o.addEventListener('click', () => {
    document.querySelectorAll('#ewDegreeMM .opt').forEach(x => x.classList.toggle('on', x === o));
    MM_STATE.ewDegree = o.dataset.d; _drawEwMM(); _drawExpertMM(); }));
  document.querySelectorAll('#ewModeMM .opt').forEach(o => o.addEventListener('click', () => {
    document.querySelectorAll('#ewModeMM .opt').forEach(x => x.classList.toggle('on', x === o));
    MM_STATE.ewMode = o.dataset.m; _drawEwMM(); _drawExpertMM(); }));
  document.querySelectorAll('#wyPhaseMM .opt').forEach(o => o.addEventListener('click', () => {
    document.querySelectorAll('#wyPhaseMM .opt').forEach(x => x.classList.toggle('on', x === o));
    MM_STATE.wyPhase = o.dataset.p; _drawWyMM(); _drawExpertMM(); }));
  document.querySelectorAll('#wyCurrentMM .opt').forEach(o => o.addEventListener('click', () => {
    document.querySelectorAll('#wyCurrentMM .opt').forEach(x => x.classList.toggle('on', x === o));
    MM_STATE.wyCurrent = o.dataset.c; _drawWyMM(); }));

  // Anchor input helpers
  window.mmSetEwAnchor = function() {
    const w0 = parseFloat($('mmW0').value), w1 = parseFloat($('mmW1').value), w2 = parseFloat($('mmW2').value);
    if (!isNaN(w0) && !isNaN(w1) && !isNaN(w2)) {
      MM_STATE.ewAnchors[MM_STATE.ewDegree] = { w0, w1, w2 };
      _drawEwMM(); _drawExpertMM();
    }
  };
  window.mmClearEwAnchors = function() {
    MM_STATE.ewAnchors = { major: null, intermediate: null, minor: null };
    ['mmW0','mmW1','mmW2'].forEach(id => { const el = $(id); if (el) el.value = ''; });
    _drawEwMM(); _drawExpertMM();
  };
  window.mmSetWyAnchor = function() {
    const sc = parseFloat($('mmSC').value), ar = parseFloat($('mmAR').value);
    const creek = parseFloat($('mmCreek').value), spring = parseFloat($('mmSpring').value);
    if (!isNaN(sc) && !isNaN(ar)) {
      MM_STATE.wyAnchors = { sc, ar, creek: isNaN(creek) ? null : creek, spring: isNaN(spring) ? null : spring };
      _drawWyMM(); _drawExpertMM();
    }
  };
  window.mmClearWyAnchors = function() {
    MM_STATE.wyAnchors = { sc: null, ar: null, creek: null, spring: null };
    ['mmSC','mmAR','mmCreek','mmSpring'].forEach(id => { const el = $(id); if (el) el.value = ''; });
    _drawWyMM(); _drawExpertMM();
  };
  // TICKER_CONFIG load/clear
  window.mmLoadConfig = function() {
    try {
      const raw = ($('mmConfigInput') || {}).value || '';
      // Extract the object literal — strip const TICKER_CONFIG = ... and export default
      const cleaned = raw.replace(/^\s*const\s+TICKER_CONFIG\s*=\s*/,'').replace(/;\s*export\s+default.*$/,'').replace(/export\s+default\s+.*$/,'').trim();
      const cfg = (new Function('return (' + cleaned + ')'))();
      if (!cfg || !cfg.price || !cfg.price.current) throw new Error('Missing price.current');
      MM_STATE.customConfig = cfg;
      MM_STATE.accentColor = cfg.accentColor || null;
      MM_STATE.tickerIcon  = cfg.icon || null;
      // Reset manual anchors so config anchors take effect
      mmClearEwAnchors(); mmClearWyAnchors();
      // Build synthetic T from config
      const syntheticT = {
        ticker: cfg.ticker, name: cfg.name, sector: cfg.sector,
        price: cfg.price.current, atr_pct: cfg.technicals?.atr_pct,
        rsi: cfg.technicals?.rsi_14, rvol: null,
        above_50ema: cfg.technicals?.sma_50 && cfg.price.current > cfg.technicals.sma_50,
        above_200sma: cfg.technicals?.sma_200 && cfg.price.current > cfg.technicals.sma_200,
        entry_low: cfg.horizons?.swing?.entry_low || cfg.price.current * 0.96,
        entry_high: cfg.horizons?.swing?.entry_high || cfg.price.current * 1.01,
        stop: cfg.horizons?.swing?.entry_low ? cfg.horizons.swing.entry_low * 0.93 : cfg.price.current * 0.93,
        target1: cfg.driver?.earnings?.analyst_pt_avg || cfg.price.current * 1.15,
        target2: null, rr_ratio: null,
        fund_real: { rev_growth_pct: cfg.fundamentals?.revenue_growth_pct, peg: cfg.fundamentals?.fwd_pe ? cfg.fundamentals.fwd_pe / 18 : null },
        week52_high: cfg.price?.week52_high, week52_low: cfg.price?.week52_low,
        beta: cfg.technicals?.beta,
        earn_days: cfg.fundamentals?.earnings_date ? Math.round((new Date(cfg.fundamentals.earnings_date) - new Date()) / 86400000) : null,
        elliott_wave: {}, wyckoff: {},
      };
      MM_STATE.model = _mmBuildModel(syntheticT, MM_STATE.days, MM_STATE.sims);
      MM_STATE.model.t = syntheticT;
      const status = $('mmConfigStatus');
      if (status) status.textContent = `Loaded: ${cfg.ticker} · ${cfg.driver?.type || 'earnings'} driver · ${(MM_STATE.model.mu*100).toFixed(1)}% μ`;
      _drawMcPaths(); _drawMcDist(); _drawMcLevels();
      _drawEwMM(); _drawWyMM(); _drawExpertMM();
      renderScenariosMM();
    } catch (e) {
      const status = $('mmConfigStatus');
      if (status) status.textContent = `Error: ${e.message}`;
      console.error('TICKER_CONFIG parse error:', e);
    }
  };
  window.mmClearConfig = function() {
    MM_STATE.customConfig = null; MM_STATE.accentColor = null; MM_STATE.tickerIcon = null;
    const status = $('mmConfigStatus');
    if (status) status.textContent = `Using bundle data for ${T ? T.ticker : '—'}`;
    const inp = $('mmConfigInput');
    if (inp) inp.value = '';
    renderMultiMethod();
  };

  // Build model and render
  const t0 = performance.now();
  MM_STATE.model = _mmBuildModel(T, MM_STATE.days, MM_STATE.sims);
  const elapsed = (performance.now() - t0).toFixed(0);
  const m = MM_STATE.model;
  $('mmStrip').innerHTML = `
    <span class="pill-stat">Price <b>$${m.S0.toFixed(2)}</b></span>
    <span class="pill-stat">μ <b>${(m.mu*100).toFixed(1)}%</b></span>
    <span class="pill-stat">σ <b>${(m.sigma*100).toFixed(1)}%</b></span>
    <span class="pill-stat">VIX <b>${m.vix.toFixed(1)}</b></span>
    <span class="pill-stat">P(profit) <b style="color:${m.stats.probProfit > 0.55 ? 'var(--pass)' : m.stats.probProfit < 0.45 ? 'var(--fail)' : 'var(--warn)'}">${(m.stats.probProfit*100).toFixed(0)}%</b></span>
    <span class="pill-stat">Sharpe <b style="color:${m.sharpe > 0.5 ? 'var(--pass)' : m.sharpe > 0 ? 'var(--warn)' : 'var(--fail)'}">${m.sharpe.toFixed(2)}</b></span>
    <span class="pill-stat" style="color:var(--ink-3)">${elapsed}ms</span>
  `;
  _drawMcPaths(); _drawMcDist(); _drawMcLevels();
  _drawEwMM(); _drawWyMM(); _drawExpertMM();
  renderScenariosMM();
}

export function dispose() { /* no-op */ }

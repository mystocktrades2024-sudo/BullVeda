// lens-bullalgo.jsx — BullAlgo lens (in-house, fully-inspectable replacement for
// the removed TradingView `tv` lens). A faithful native-React port of the
// standalone prototype infra/prototype/bullveda/bullalgo-test.html.
//
// Shows a LuxAlgo-style Price-Action chart + MCDX money-flow subchart + a
// Confirmation panel + a multi-timeframe Signals/PAC screener, all driven by the
// existing /api/bullalgo/* endpoints. Display-only · never a scoring source.
//
// Imperative lightweight-charts code (custom primitives + render logic) is copied
// VERBATIM from the prototype, relocated into the React lifecycle (useRef chart
// instances created in useEffect, chart.remove() in the cleanup). The alignment
// fix (rightPriceScale.minimumWidth:64 on both charts + syncCharts) is preserved.

const { useState: useBAs, useEffect: useBAe, useRef: useBAr } = React;

// ── prototype globals → module constants ──
const BA_TF_LABELS = { 'SWING_1H': '1H', 'SWING_4H': '4H', 'SWING': '1D', 'POSITION': '1W', 'INVESTMENT': '1M' };
// overlay toggle defaults match the LuxAlgo Inputs panel
const BA_OVERLAYS = [
  { key: 'trail', label: 'Smart Trail', color: '#3b82f6' },
  { key: 'catcher', label: 'Trend Catcher', color: '#34e3a4' },
  { key: 'tracer', label: 'Trend Tracer', color: '#e8a04b' },
  { key: 'neo', label: 'Neo Cloud', color: '#2dd4bf' },
  { key: 'rz', label: 'Reversal Zones', color: '#ff5d6c' },
];
const BA_OVERLAY_DEFAULT = { trail: false, catcher: true, tracer: true, neo: false, rz: true };

// mode (swing/position/invest) → prototype MODE string + default chart timeframe
const BA_MODE_MAP = { swing: 'SWING', position: 'POSITION', invest: 'INVESTMENT', investment: 'INVESTMENT' };
const BA_DEFAULT_TF = { SWING: 'SWING_4H', POSITION: 'POSITION', INVESTMENT: 'INVESTMENT' };

// ── small read helpers (verbatim from prototype) ──
const baSigClass = (s) => {
  const t = (s || '').toLowerCase();
  if (t.includes('bull')) return 'bull'; if (t.includes('bear')) return 'bear'; return 'neu';
};
const baBullbear = (s) => (s === 'Bullish' || s === 'Strong Bullish') ? 'bull' : (s === 'Bearish' || s === 'Strong Bearish') ? 'bear' : 'neu';

// ── custom lightweight-charts primitives — copied VERBATIM from the prototype ──

// custom primitive: fill the polygon between each band's top & bot edges (true cloud)
function baBandPrimitive(points, fill) {
  let _series = null, _chart = null, _req = null, _visible = true;
  const renderer = {
    draw(target) {
      if (!_visible || !points || !points.length) return;
      target.useBitmapCoordinateSpace(scope => {
        const ctx = scope.context, ts = _chart.timeScale();
        const pr = scope.horizontalPixelRatio, vr = scope.verticalPixelRatio;
        ctx.fillStyle = fill; ctx.beginPath();
        let started = false;
        for (const p of points) { const x = ts.timeToCoordinate(p.time), y = _series.priceToCoordinate(p.top);
          if (x == null || y == null) continue; if (!started) { ctx.moveTo(x * pr, y * vr); started = true; } else ctx.lineTo(x * pr, y * vr); }
        for (let i = points.length - 1; i >= 0; i--) { const p = points[i], x = ts.timeToCoordinate(p.time), y = _series.priceToCoordinate(p.bot);
          if (x == null || y == null) continue; ctx.lineTo(x * pr, y * vr); }
        ctx.closePath(); ctx.fill();
      });
    }
  };
  const view = { renderer() { return renderer; } };
  return {
    attached(p) { _series = p.series; _chart = p.chart; _req = p.requestUpdate; },
    updateAllViews() { }, paneViews() { return [view]; },
    setVisible(v) { _visible = v; if (_req) _req(); },
  };
}

// ONE continuous line that changes color at the flip (per-segment stroke)
function baDirLinePrimitive(points, upColor, dnColor, width) {
  let _series = null, _chart = null, _req = null, _visible = true; width = width || 2;
  const renderer = {
    draw(target) {
      if (!_visible || !points || points.length < 2) return;
      target.useBitmapCoordinateSpace(scope => {
        const ctx = scope.context, ts = _chart.timeScale();
        const pr = scope.horizontalPixelRatio, vr = scope.verticalPixelRatio;
        ctx.lineJoin = 'round'; ctx.lineCap = 'round'; ctx.lineWidth = width * vr;
        for (let i = 1; i < points.length; i++) {
          const a = points[i - 1], b = points[i];
          if (a.value == null || b.value == null) continue;
          const x1 = ts.timeToCoordinate(a.time), y1 = _series.priceToCoordinate(a.value);
          const x2 = ts.timeToCoordinate(b.time), y2 = _series.priceToCoordinate(b.value);
          if (x1 == null || x2 == null || y1 == null || y2 == null) continue;
          ctx.strokeStyle = b.up ? upColor : dnColor;
          ctx.beginPath(); ctx.moveTo(x1 * pr, y1 * vr); ctx.lineTo(x2 * pr, y2 * vr); ctx.stroke();
        }
      });
    }
  };
  const view = { renderer() { return renderer; } };
  return {
    attached(p) { _series = p.series; _chart = p.chart; _req = p.requestUpdate; },
    updateAllViews() { }, paneViews() { return [view]; },
    setVisible(v) { _visible = v; if (_req) _req(); },
  };
}

// direction-colored filled ribbon: fills each contiguous same-`up` run with up/dn color
function baDirBandPrimitive(points, upColor, dnColor) {
  let _series = null, _chart = null, _req = null, _visible = true;
  const renderer = {
    draw(target) {
      if (!_visible || !points || !points.length) return;
      target.useBitmapCoordinateSpace(scope => {
        const ctx = scope.context, ts = _chart.timeScale();
        const pr = scope.horizontalPixelRatio, vr = scope.verticalPixelRatio;
        let i = 0;
        while (i < points.length) {
          const up = points[i].up; let j = i; const run = [];
          while (j < points.length && points[j].up === up) { run.push(points[j]); j++; }
          if (run.length >= 2) {
            ctx.fillStyle = up ? upColor : dnColor; ctx.beginPath(); let started = false;
            for (const p of run) { const x = ts.timeToCoordinate(p.time), y = _series.priceToCoordinate(p.top);
              if (x == null || y == null) continue; if (!started) { ctx.moveTo(x * pr, y * vr); started = true; } else ctx.lineTo(x * pr, y * vr); }
            for (let k = run.length - 1; k >= 0; k--) { const p = run[k], x = ts.timeToCoordinate(p.time), y = _series.priceToCoordinate(p.bot);
              if (x == null || y == null) continue; ctx.lineTo(x * pr, y * vr); }
            ctx.closePath(); ctx.fill();
          }
          i = j;
        }
      });
    }
  };
  const view = { renderer() { return renderer; } };
  return {
    attached(p) { _series = p.series; _chart = p.chart; _req = p.requestUpdate; },
    updateAllViews() { }, paneViews() { return [view]; },
    setVisible(v) { _visible = v; if (_req) _req(); },
  };
}

// filled rectangle order-block zones (extend right) + volume label
function baBoxPrimitive(boxes) {
  let _s = null, _c = null, _req = null, _vis = true;
  const renderer = {
    draw(target) {
      if (!_vis || !boxes || !boxes.length) return;
      target.useBitmapCoordinateSpace(scope => {
        const ctx = scope.context, ts = _c.timeScale(), pr = scope.horizontalPixelRatio, vr = scope.verticalPixelRatio;
        for (const b of boxes) {
          const x1 = ts.timeToCoordinate(b.time), x2 = ts.timeToCoordinate(b.time_right);
          const y1 = _s.priceToCoordinate(b.top), y2 = _s.priceToCoordinate(b.bot);
          if (x1 == null || x2 == null || y1 == null || y2 == null) continue;
          const bull = b.kind === 'bull';
          const X = x1 * pr, Y = Math.min(y1, y2) * vr, W = (x2 - x1) * pr, H = Math.abs(y2 - y1) * vr;
          ctx.fillStyle = bull ? 'rgba(52,227,164,0.15)' : 'rgba(255,93,108,0.15)';
          ctx.fillRect(X, Y, W, H);
          ctx.strokeStyle = bull ? 'rgba(52,227,164,0.55)' : 'rgba(255,93,108,0.55)';
          ctx.lineWidth = 1 * vr; ctx.strokeRect(X, Y, W, H);
          ctx.fillStyle = bull ? 'rgba(140,240,200,0.95)' : 'rgba(255,160,170,0.95)';
          ctx.font = `${9.5 * vr}px monospace`; ctx.textBaseline = 'middle'; ctx.textAlign = 'left';
          ctx.fillText(b.vol_label, X + 5 * pr, Y + H / 2);   // label at box's left edge → spreads across time
        }
      });
    }
  };
  const view = { renderer() { return renderer; } };
  return { attached(p) { _s = p.series; _c = p.chart; _req = p.requestUpdate; }, updateAllViews() { }, paneViews() { return [view]; }, setVisible(v) { _vis = v; if (_req) _req(); } };
}

// ── gauge (SVG arc 0..1) — returns a React element ──
function BAGauge({ v }) {
  const r = 52, c = Math.PI * r; // semicircle
  const frac = Math.max(0, Math.min(1, v));
  const col = frac >= .6 ? 'var(--bull)' : frac <= .4 ? 'var(--bear)' : 'var(--warn)';
  const dash = c * frac;
  return (
    <svg width="128" height="84" viewBox="0 0 128 84">
      <path d="M12 70 A52 52 0 0 1 116 70" fill="none" stroke="#18221f" strokeWidth="11" strokeLinecap="round" />
      <path d="M12 70 A52 52 0 0 1 116 70" fill="none" stroke={col} strokeWidth="11" strokeLinecap="round"
        strokeDasharray={`${dash} 999`} style={{ transition: 'stroke-dasharray .6s ease' }} />
      <text x="64" y="60" textAnchor="middle" fill={col} fontFamily="var(--mono)" fontSize="22" fontWeight="800">{frac.toFixed(2)}</text>
      <text x="64" y="76" textAnchor="middle" fill="var(--ink-3)" fontFamily="var(--mono)" fontSize="9" letterSpacing="1">CONF</text>
    </svg>
  );
}

// ── Confirmation card ──
function BAConfirmation({ c, meta }) {
  meta = meta || {};
  if (!c) return (
    <div className="card"><div className="lbl"><span>Confirmation</span></div>
      <div className="na">— {meta && meta.error ? ('unavailable: ' + meta.error) : 'no data'} —</div></div>
  );
  const sc = baSigClass(c.signal_label);
  const vcol = sc === 'bull' ? 'var(--bull)' : sc === 'bear' ? 'var(--bear)' : 'var(--ink-2)';
  return (
    <div className="card">
      <div className="lbl"><span>Confirmation · {meta.tf || ''}</span><span>{(meta.tier || '').toUpperCase()}</span></div>
      <div className="gaugewrap">
        <BAGauge v={c.conf_feature} />
        <div className="verdict" style={{ color: vcol }}>{c.signal_label}</div>
        {c.strength ? <span className={`pill ${c.strength}`}>{c.strength}</span> : null}
        <div className="feat">trend: {c.trend} · RSI {c.rsi}</div>
      </div>
    </div>
  );
}

// ── Layered breakdown card ──
function BALayers({ c }) {
  if (!c) return null;
  const emaUp = c.ema_fast > c.ema_slow, slopeUp = c.slope > 0;
  const trendChip = (emaUp && slopeUp) ? <span className="chip bull">▲ UP</span>
    : (!emaUp && !slopeUp) ? <span className="chip bear">▼ DOWN</span>
      : <span className="chip neu">— FLAT</span>;
  const rsiPos = Math.max(0, Math.min(100, c.rsi));
  const trigChip = c.signal > 0 ? <span className="chip bull">LONG TRIGGER</span>
    : c.signal < 0 ? <span className="chip bear">SHORT TRIGGER</span>
      : <span className="chip neu">no trigger</span>;
  const aligned = c.close > c.ema_slow;
  const exitTxt = c.exit_long ? <span className="chip bear">↘ momentum fading (exit-long hint)</span>
    : c.exit_short ? <span className="chip bull">↗ momentum turning (exit-short hint)</span>
      : <span className="chip neu">no exit signal</span>;
  return (
    <div className="card">
      <div className="lbl"><span>Layered breakdown</span><span>non-repainting</span></div>
      <div className="layers">
        <div className="layer">
          <div className="lh"><span className="ln">Layer 1 · Trend Filter</span><span className="lnum">EMA20 / EMA50 + slope</span></div>
          <div className="ld">EMA20 <b>{c.ema_fast}</b> {emaUp ? '>' : '<'} EMA50 <b>{c.ema_slow}</b> · slope {c.slope >= 0 ? '+' : ''}{c.slope} &nbsp; {trendChip}</div>
        </div>
        <div className="layer">
          <div className="lh"><span className="ln">Layer 2 · Adaptive Trigger</span><span className="lnum">vol-adaptive RSI</span></div>
          <div className="ld">RSI <b>{c.rsi}</b> vs long-thr <b>{c.rsi_thr_long}</b> / short-thr <b>{c.rsi_thr_short}</b> &nbsp; {trigChip}</div>
          <div className="bar"><i style={{ width: rsiPos + '%', background: rsiPos > 55 ? 'var(--bull)' : rsiPos < 45 ? 'var(--bear)' : 'var(--warn)' }}></i></div>
        </div>
        <div className="layer">
          <div className="lh"><span className="ln">Layer 3 · Alignment</span><span className="lnum">price vs EMA50</span></div>
          <div className="ld">close <b>{c.close}</b> {aligned ? 'above' : 'below'} EMA50 → {aligned ? <span className="chip bull">strong zone</span> : <span className="chip neu">pullback zone</span>}</div>
        </div>
        <div className="layer">
          <div className="lh"><span className="ln">Exit Monitor</span><span className="lnum">RSI ↔ 50 midline</span></div>
          <div className="ld">{exitTxt}</div>
        </div>
        {c.recent && c.recent.length ? (
          <div className="layer">
            <div className="lh"><span className="ln">Recent fired signals</span><span className="lnum">last {c.recent.length}</span></div>
            <div className="markers">{c.recent.map((m, i) => (
              <span key={i} className={`mk ${m.signal > 0 ? 'b' : 's'}`}>{m.signal > 0 ? '▲' : '▼'} {m.date} @ {m.price}{m.strength === 'strong' ? ' ★' : ''}</span>
            ))}</div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

// ── grid cell helpers ──
function BAGridCell({ label }) {
  const bb = baBullbear(label);
  if (label === '—' || label == null) return <span className="na">—</span>;
  const dot = (bb === 'bull' || bb === 'bear') ? <span className={`dot ${bb}`}></span> : null;
  return <span className={`cell ${bb}`}>{dot}{label}</span>;
}
function BAMiniBar({ v, col }) {
  const p = Math.round(Math.max(0, Math.min(1, v)) * 100);
  return <span className="minibar"><i style={{ width: p + '%', background: col }}></i></span>;
}

// ── Signals & Overlays screener card ──
function BAScreener({ rows }) {
  const head = ['TF', 'Signal', 'Smart Trail', 'Reversal Zone', 'Catcher', 'Tracer', 'NeoCloud', 'Trend Str', 'Volatility', 'Squeeze', 'Vol Sent', 'Confluence'];
  return (
    <div className="card screen">
      <div className="lbl"><span>Signals &amp; Overlays · multi-timeframe screener</span><span>4H → 1M</span></div>
      <table>
        <thead><tr>{head.map((h, i) => <th key={i} className={i === 0 ? 'tf' : ''}>{h}</th>)}</tr></thead>
        <tbody>
          {(rows || []).map((r, ri) => {
            if (!r.available) return (
              <tr key={ri} className="muted"><td className="tf"><span className="tfbadge">{r.timeframe}</span></td>
                <td colSpan="11"><span className="na">— {r.tier ? ('no ' + r.tier + ' bars') : 'unavailable'} —</span></td></tr>
            );
            const volCol = r.volatility === 'High' ? 'cell bear' : r.volatility === 'Low' ? 'cell bull' : 'cell warn';
            const cf = r.confluence;
            const cfCol = cf >= .6 ? 'var(--bull)' : cf <= .4 ? 'var(--bear)' : 'var(--warn)';
            return (
              <tr key={ri}>
                <td className="tf"><span className="tfbadge">{r.timeframe}</span><span className="tfsub">{(r.tier || '').toUpperCase()}</span></td>
                <td><BAGridCell label={r.signal} />{r.strength === 'strong' ? <span style={{ color: 'var(--gold)' }}> ★</span> : null}</td>
                <td><BAGridCell label={r.smart_trail} /></td>
                <td><span className={`cell ${r.reversal_zone === 'Near support' ? 'bull' : r.reversal_zone === 'Near resistance' ? 'bear' : 'neu'}`}>{r.reversal_zone}</span></td>
                <td><BAGridCell label={r.catcher} /></td>
                <td><BAGridCell label={r.tracer} /></td>
                <td><BAGridCell label={r.neo_cloud} /></td>
                <td><span className="cell">{r.trend_strength}</span><br /><BAMiniBar v={r.trend_strength / 100} col="var(--neo)" /></td>
                <td><span className={volCol}>{r.volatility}</span></td>
                <td><span className="cell warn">{r.squeeze}%</span><br /><BAMiniBar v={r.squeeze / 100} col="var(--gold)" /></td>
                <td><span className={`cell ${r.volume_sentiment >= 0 ? 'bull' : 'bear'}`}>{r.volume_sentiment > 0 ? '+' : ''}{r.volume_sentiment}</span></td>
                <td><span className="conf-big" style={{ color: cfCol }}>{cf.toFixed(2)}</span><br /><BAMiniBar v={cf} col={cfCol} /></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Price Action Concepts (SMC) screener card ──
function BAPac({ rows }) {
  const head = ['TF', 'Structure', 'Order Block', 'Buy OB Vol', 'Sell OB Vol', 'FVG', 'Premium/Discount', 'Liquidity Grab', 'Equal H/L', 'SMC Confluence'];
  return (
    <div className="card screen" style={{ marginTop: 18 }}>
      <div className="lbl"><span>Price Action Concepts (SMC) · multi-timeframe screener</span><span>swings → structure → OB → FVG → P/D → liquidity</span></div>
      <table>
        <thead><tr>{head.map((h, i) => <th key={i} className={i === 0 ? 'tf' : ''}>{h}</th>)}</tr></thead>
        <tbody>
          {(rows || []).map((r, ri) => {
            if (!r.available) return (
              <tr key={ri} className="muted"><td className="tf"><span className="tfbadge">{r.timeframe}</span></td>
                <td colSpan="9"><span className="na">— {r.tier ? ('no ' + r.tier + ' bars') : 'unavailable'} —</span></td></tr>
            );
            const ss = r.structure_score != null ? r.structure_score : 0.5;
            const structCol = ss > 0.55 ? 'cell bull' : ss < 0.45 ? 'cell bear' : 'cell neu';
            const pdCol = r.pd_zone === 'Discount' ? 'cell bull' : r.pd_zone === 'Premium' ? 'cell bear' : 'cell neu';
            const obCol = r.order_block === 'Within' ? 'cell warn' : 'cell neu';
            const fvgCol = r.fvg === 'Within' ? 'cell warn' : 'cell neu';
            const eqCol = r.eqhl === '—' ? 'cell neu' : 'cell warn';
            const cf = r.smc_confluence, cfCol = cf >= .6 ? 'var(--bull)' : cf <= .4 ? 'var(--bear)' : 'var(--warn)';
            return (
              <tr key={ri}>
                <td className="tf"><span className="tfbadge">{r.timeframe}</span><span className="tfsub">{(r.tier || '').toUpperCase()}</span></td>
                <td><span className={structCol}>{r.structure}</span></td>
                <td><span className={obCol}>{r.order_block}</span><br /><BAMiniBar v={r.ob_buy_score} col={r.ob_buy_score >= .5 ? 'var(--bull)' : 'var(--bear)'} /></td>
                <td><span className="cell bull">{r.buy_ob_vol}</span></td>
                <td><span className="cell bear">{r.sell_ob_vol}</span></td>
                <td><span className={fvgCol}>{r.fvg}</span></td>
                <td><span className={pdCol}>{r.pd_zone}</span></td>
                <td><BAGridCell label={r.liquidity_grab} /></td>
                <td><span className={eqCol}>{r.eqhl}</span></td>
                <td><span className="conf-big" style={{ color: cfCol }}>{cf.toFixed(2)}</span><br /><BAMiniBar v={cf} col={cfCol} /></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── chart card (price-action / signals) + MCDX subchart, native React ──
// Holds two lightweight-charts instances; re-renders on ticker/tf/view change.
// Overlay visibility toggled imperatively without re-creating the chart.
function BACharts({ ticker, chartTf, setChartTf, view, setView, overlayOn, setOverlayOn }) {
  const chartBoxRef = useBAr(null);
  const statsRef = useBAr(null);
  const mcdxBoxRef = useBAr(null);
  // refs holding the live chart instances + attached band primitives
  const chartRef = useBAr(null);
  const mcdxChartRef = useBAr(null);
  const bandsRef = useBAr({});

  const tk = (ticker || 'NVDA').toUpperCase();
  const tfVisible = chartTf === 'SWING_4H' || chartTf === 'SWING_1H';

  // apply overlay visibility imperatively (no chart re-create)
  function applyOverlayVis() {
    const b = bandsRef.current;
    const sv = (p, on) => { if (p) p.setVisible(on); };
    sv(b.catcher, overlayOn.catcher);
    sv(b.tracer, overlayOn.tracer);
    sv(b.trail, overlayOn.trail);
    sv(b.neo, overlayOn.neo);
    sv(b.res, overlayOn.rz);
    sv(b.sup, overlayOn.rz);
  }

  function syncCharts() {
    const _chart = chartRef.current, _mcdxChart = mcdxChartRef.current;
    if (!_chart || !_mcdxChart) return;
    const a = _chart.timeScale(), b = _mcdxChart.timeScale();
    let lock = false;
    a.subscribeVisibleLogicalRangeChange(r => { if (lock || !r) return; lock = true; try { b.setVisibleLogicalRange(r); } catch (e) { } lock = false; });
    b.subscribeVisibleLogicalRangeChange(r => { if (lock || !r) return; lock = true; try { a.setVisibleLogicalRange(r); } catch (e) { } lock = false; });
  }

  async function renderSignals() {
    const _chart = chartRef.current; if (!_chart) return;
    const stats = statsRef.current; if (stats) stats.innerHTML = '<div class="sr"><span>loading…</span></div>';
    try {
      const r = await (await fetch(`/api/bullalgo/${tk}/chart?tf=${chartTf}`, { credentials: 'same-origin' })).json();
      if (!r.available) { if (stats) stats.innerHTML = `<div class="sr"><span>— ${r.message || ('no ' + (r.tier || '') + ' bars')} —</span></div>`; return; }
      const candle = _chart.addCandlestickSeries({
        upColor: '#26a37a', downColor: '#d9485a',
        borderUpColor: '#34e3a4', borderDownColor: '#ff5d6c', wickUpColor: '#34e3a4', wickDownColor: '#ff5d6c'
      });
      candle.setData(r.bars);
      const _bands = {};
      // Trend Catcher = fast supertrend, ONE line green↔red on flip
      _bands.catcher = baDirLinePrimitive(r.catcher, '#34e3a4', '#ff5d6c', 2); candle.attachPrimitive(_bands.catcher);
      // Trend Tracer = slower supertrend, ONE line green↔orange on flip
      _bands.tracer = baDirLinePrimitive(r.tracer, '#34e3a4', '#e8a04b', 2); candle.attachPrimitive(_bands.tracer);
      // Smart Trail = filled ribbon, blue(bull)/red(bear)
      _bands.trail = baDirBandPrimitive(r.smart_trail, 'rgba(59,130,246,0.30)', 'rgba(255,93,108,0.26)'); candle.attachPrimitive(_bands.trail);
      // Neo Cloud = slower filled band, teal(bull)/maroon(bear)
      _bands.neo = baDirBandPrimitive(r.neo_band, 'rgba(45,212,191,0.20)', 'rgba(150,40,60,0.34)'); candle.attachPrimitive(_bands.neo);
      // Reversal Zones = static resistance(red)/support(green) clouds
      _bands.res = baBandPrimitive(r.rz_res, 'rgba(255,93,108,0.16)'); candle.attachPrimitive(_bands.res);
      _bands.sup = baBandPrimitive(r.rz_sup, 'rgba(52,227,164,0.16)'); candle.attachPrimitive(_bands.sup);
      bandsRef.current = _bands;
      applyOverlayVis();
      if (r.markers && r.markers.length) candle.setMarkers(r.markers);
      _chart.timeScale().fitContent();
      // stats panel
      const st = r.stats || {};
      const tsCol = st.trend_label === 'Trending' ? 'var(--bull)' : 'var(--warn)';
      const vCol = st.volatility === 'High' ? 'var(--bear)' : st.volatility === 'Low' ? 'var(--bull)' : 'var(--warn)';
      if (stats) stats.innerHTML = `
        <div class="sr"><span>⚙ Trend Strength</span><b style="color:${tsCol}">${st.trend_label} (${st.trend_strength}%)</b></div>
        <div class="sr"><span>⚠ Volatility</span><b style="color:${vCol}">${st.volatility}</b></div>
        <div class="sr"><span>◇ Squeeze</span><b style="color:var(--gold)">${st.squeeze}%</b></div>
        <div class="sr"><span>≈ Volume Sentiment</span><b style="color:${st.volume_sentiment >= 0 ? 'var(--bull)' : 'var(--bear)'}">${st.volume_sentiment > 0 ? '+' : ''}${st.volume_sentiment}%</b></div>
        <div class="sr"><span>· Timeframe</span><b style="color:var(--ink-2)">${r.tf} · ${(r.tier || '').toUpperCase()}</b></div>`;
    } catch (e) { if (stats) stats.innerHTML = `<div class="sr"><span>⚠️ ${e}</span></div>`; }
  }

  async function renderPac() {
    const _chart = chartRef.current; if (!_chart) return;
    const stats = statsRef.current; if (stats) stats.innerHTML = '<div class="sr"><span>loading…</span></div>';
    try {
      const r = await (await fetch(`/api/bullalgo/${tk}/pac-chart?tf=${chartTf}`, { credentials: 'same-origin' })).json();
      if (!r.available) { if (stats) stats.innerHTML = `<div class="sr"><span>— ${r.message || ('no ' + (r.tier || '') + ' bars')} —</span></div>`; return; }
      const candle = _chart.addCandlestickSeries({
        upColor: '#26a37a', downColor: '#d9485a',
        borderUpColor: '#34e3a4', borderDownColor: '#ff5d6c', wickUpColor: '#34e3a4', wickDownColor: '#ff5d6c'
      });
      candle.setData(r.bars);
      const _bands = {};
      // premium / discount / equilibrium zones (faint horizontal bands)
      const z = r.zones || {};
      if (z.high != null) {
        const span = (top, bot) => [{ time: z.t_left, top, bot }, { time: z.t_right, top, bot }];
        _bands.prem = baBandPrimitive(span(z.high, z.eq), 'rgba(255,93,108,0.07)'); candle.attachPrimitive(_bands.prem);
        _bands.disc = baBandPrimitive(span(z.eq, z.low), 'rgba(52,227,164,0.07)'); candle.attachPrimitive(_bands.disc);
        candle.createPriceLine({ price: z.eq, color: 'rgba(159,179,172,.5)', lineWidth: 1, lineStyle: 2, title: 'Equilibrium' });
        candle.createPriceLine({ price: z.high, color: 'rgba(255,93,108,.4)', lineWidth: 1, lineStyle: 0, title: 'Premium' });
        candle.createPriceLine({ price: z.low, color: 'rgba(52,227,164,.4)', lineWidth: 1, lineStyle: 0, title: 'Discount' });
      }
      // order-block boxes
      _bands.obs = baBoxPrimitive(r.order_blocks || []); candle.attachPrimitive(_bands.obs);
      bandsRef.current = _bands;
      // structure labels HH/HL/LH/LL
      if (r.markers && r.markers.length) candle.setMarkers(r.markers);
      _chart.timeScale().fitContent();
      const nb = (r.order_blocks || []).filter(o => o.kind === 'bull').length, ns = (r.order_blocks || []).length - nb;
      if (stats) stats.innerHTML = `
        <div class="sr"><span>▦ Order Blocks</span><b style="color:var(--ink)">${(r.order_blocks || []).length}</b></div>
        <div class="sr"><span>· bullish</span><b style="color:var(--bull)">${nb}</b></div>
        <div class="sr"><span>· bearish</span><b style="color:var(--bear)">${ns}</b></div>
        <div class="sr"><span>⬍ Equilibrium</span><b style="color:var(--ink-2)">${z.eq}</b></div>
        <div class="sr"><span>· Timeframe</span><b style="color:var(--ink-2)">${r.tf} · ${(r.tier || '').toUpperCase()}</b></div>`;
    } catch (e) { if (stats) stats.innerHTML = `<div class="sr"><span>⚠️ ${e}</span></div>`; }
  }

  async function renderMcdx() {
    const box = mcdxBoxRef.current; if (!box || !window.LightweightCharts) return;
    if (mcdxChartRef.current) { try { mcdxChartRef.current.remove(); } catch (e) { } mcdxChartRef.current = null; }
    box.innerHTML = '';
    const _mcdxChart = window.LightweightCharts.createChart(box, {
      layout: { background: { type: 'solid', color: 'transparent' }, textColor: '#9fb3ac', fontFamily: "'SF Mono',monospace" },
      grid: { vertLines: { color: 'rgba(30,43,39,.35)' }, horzLines: { color: 'rgba(30,43,39,.35)' } },
      rightPriceScale: { borderColor: '#1e2b27', minimumWidth: 64 }, timeScale: { borderColor: '#1e2b27', timeVisible: tfVisible },
      crosshair: { mode: 0 },
    });
    mcdxChartRef.current = _mcdxChart;
    try {
      const r = await (await fetch(`/api/bullalgo/${tk}/mcdx?tf=${chartTf}`, { credentials: 'same-origin' })).json();
      if (!r.available) return;
      // per-bar colored money-flow histogram (green accum / yellow neutral / red distribution)
      const hist = _mcdxChart.addHistogramSeries({ priceLineVisible: false, lastValueVisible: false });
      hist.setData(r.hist);   // each point carries its own color
      // blue banker line
      const bl = _mcdxChart.addLineSeries({ color: '#5b9bd5', lineWidth: 2, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
      bl.setData(r.banker_line);
      _mcdxChart.timeScale().fitContent();
      syncCharts();   // link pan/zoom to the main chart above
    } catch (e) { }
  }

  async function renderChart() {
    // (re)create the main price chart, then render the active view
    const box = chartBoxRef.current;
    if (!box || !window.LightweightCharts) return;
    if (chartRef.current) { try { chartRef.current.remove(); } catch (e) { } chartRef.current = null; }
    box.innerHTML = ''; bandsRef.current = {};
    chartRef.current = window.LightweightCharts.createChart(box, {
      layout: { background: { type: 'solid', color: 'transparent' }, textColor: '#9fb3ac', fontFamily: "'SF Mono',monospace" },
      grid: { vertLines: { color: 'rgba(30,43,39,.5)' }, horzLines: { color: 'rgba(30,43,39,.5)' } },
      rightPriceScale: { borderColor: '#1e2b27', minimumWidth: 64 }, timeScale: { borderColor: '#1e2b27', timeVisible: chartTf === 'SWING_4H' },
      crosshair: { mode: 0 },
    });
    if (view === 'pac') return renderPac();
    return renderSignals();
  }

  // full (re)render of both charts on ticker / tf / view change
  useBAe(() => {
    let killed = false;
    (async () => {
      if (killed) return;
      await renderChart();
      if (killed) return;
      await renderMcdx();
    })();
    return () => {
      killed = true;
      if (chartRef.current) { try { chartRef.current.remove(); } catch (e) { } chartRef.current = null; }
      if (mcdxChartRef.current) { try { mcdxChartRef.current.remove(); } catch (e) { } mcdxChartRef.current = null; }
      bandsRef.current = {};
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tk, chartTf, view]);

  // overlay visibility — imperative, no chart re-create
  useBAe(() => { applyOverlayVis(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [overlayOn]);

  const toggleOverlay = (key) => setOverlayOn(s => ({ ...s, [key]: !s[key] }));

  return (
    <React.Fragment>
      <div className="card chartcard">
        <div className="charthead">
          <div className="tftoggle">
            <button className={view === 'signals' ? 'on' : ''} onClick={() => setView('signals')}>Signals &amp; Overlays</button>
            <button className={view === 'pac' ? 'on' : ''} onClick={() => setView('pac')}>Price Action</button>
          </div>
          <div className="tftoggle">
            {Object.entries(BA_TF_LABELS).map(([m, l]) => (
              <button key={m} className={m === chartTf ? 'on' : ''} onClick={() => setChartTf(m)}>{l}</button>
            ))}
          </div>
          <div className="ovks" style={{ display: view === 'pac' ? 'none' : 'flex' }}>
            {BA_OVERLAYS.map(o => (
              <div key={o.key} className={`ovk ${overlayOn[o.key] ? 'on' : ''}`} style={{ '--c': o.color }} onClick={() => toggleOverlay(o.key)}>
                <span className="sw"></span>{o.label}
              </div>
            ))}
          </div>
        </div>
        <div className="chartbox"><div ref={chartBoxRef} id="ba-lwchart"></div><div className="statspanel" ref={statsRef}></div></div>
      </div>

      <div className="card chartcard">
        <div className="charthead">
          <span className="t">🏦 MCDX · Money Flow</span>
          <div className="mcdxlegend">
            <span><i style={{ background: '#16c784' }}></i>Accumulation</span>
            <span><i style={{ background: '#e8c170' }}></i>Neutral</span>
            <span><i style={{ background: '#ff5d6c' }}></i>Distribution</span>
            <span><i style={{ background: '#5b9bd5' }}></i>Banker line</span>
          </div>
        </div>
        <div className="mcdxbox"><div ref={mcdxBoxRef} id="ba-mcdxchart"></div></div>
        <div className="mcdxnote">⚠️ Interpretive only — MCDX "banker/smart money" labels are momentum math (stochastic RSV smoothed at 3 speeds), NOT real order flow.</div>
      </div>
    </React.Fragment>
  );
}

// ── REAL institutional footprint — the honest, attributable counterpart to the
//    interpretive MCDX panel above. MCDX is momentum math wearing a "banker"
//    costume (no order-flow feed exists for ANY retail source). These three
//    blocks are GENUINELY observable from the existing stack (EODHD + SEC) —
//    accumulation (OBV/AD, live), insider Form 4 (real $, ~2d), 13F (real, 45d).
function BAMoney(v) {
  if (v == null || isNaN(v)) return '—';
  const a = Math.abs(v), s = v < 0 ? '-' : '+';
  if (a >= 1e9) return s + '$' + (a / 1e9).toFixed(2) + 'B';
  if (a >= 1e6) return s + '$' + (a / 1e6).toFixed(1) + 'M';
  if (a >= 1e3) return s + '$' + (a / 1e3).toFixed(0) + 'K';
  return s + '$' + a.toFixed(0);
}
function BAFootprint({ sym, mode }) {
  const [fp, setFp] = useBAs(null);
  useBAe(() => {
    if (!sym) return;
    let on = true; setFp(null);
    fetch(`/api/bullalgo/${sym}/footprint?mode=${mode}`, { credentials: 'same-origin' })
      .then(r => r.json()).then(d => { if (on) setFp(d || {}); })
      .catch(() => { if (on) setFp({ _err: true }); });
    return () => { on = false; };
  }, [sym, mode]);
  const acc = (fp && fp.accumulation) || {};
  const ins = (fp && fp.insider) || {};
  const inst = (fp && fp.institutional) || {};
  const tone = (s) => (s === 'Accumulation' || s === 'Adding') ? 'var(--bull)'
    : (s === 'Distribution' || s === 'Trimming') ? 'var(--bear)' : 'var(--warn)';
  const pctTone = (v) => v == null ? 'var(--ink-2)' : v >= 0 ? 'var(--bull)' : 'var(--bear)';
  return (
    <div className="card fpcard">
      <div className="lbl"><span>🛰️ Real Institutional Footprint</span>
        <span style={{ color: 'var(--ink-3)' }}>observable · attributable · no order-flow fiction</span></div>
      {fp === null ? <div className="fpempty">loading footprint…</div> : (
        <div className="fpgrid">
          <div className="fpcol">
            <div className="fphead">Accumulation <span className="fpsrc">OBV + A/D · live</span></div>
            {acc.available ? (<React.Fragment>
              <div className="fpbig" style={{ color: tone(acc.state) }}>{acc.state}</div>
              <div className="fprow"><span>OBV trend</span><b style={{ color: pctTone(acc.obv_trend_pct) }}>{acc.obv_trend_pct == null ? '—' : (acc.obv_trend_pct > 0 ? '+' : '') + acc.obv_trend_pct + '%'}</b></div>
              <div className="fprow"><span>A/D trend</span><b style={{ color: pctTone(acc.ad_trend_pct) }}>{acc.ad_trend_pct == null ? '—' : (acc.ad_trend_pct > 0 ? '+' : '') + acc.ad_trend_pct + '%'}</b></div>
              <div className="fpnote">The legitimate volume-accumulation read MCDX only imitates.</div>
            </React.Fragment>) : <div className="fpempty">— insufficient bars</div>}
          </div>
          <div className="fpcol">
            <div className="fphead">Insider · Form 4 <span className="fpsrc">SEC · {ins.window_days || 90}d</span></div>
            {ins.available ? (<React.Fragment>
              <div className="fpbig" style={{ color: ins.net_value >= 0 ? 'var(--bull)' : 'var(--bear)' }}>{BAMoney(ins.net_value)}<span className="fpsub"> net</span></div>
              <div className="fprow"><span>buys / sells</span><b><span style={{ color: 'var(--bull)' }}>{ins.buys}</span> / <span style={{ color: 'var(--bear)' }}>{ins.sells}</span></b></div>
              {(ins.top || []).slice(0, 3).map((x, i) => (
                <div className="fprow sm" key={i}><span title={x.name}>{x.name}</span><b style={{ color: x.side === 'BUY' ? 'var(--bull)' : 'var(--bear)' }}>{x.side} {BAMoney(x.side === 'BUY' ? x.value : -x.value)}</b></div>
              ))}
            </React.Fragment>) : <div className="fpempty">no Form 4 in window</div>}
          </div>
          <div className="fpcol">
            <div className="fphead">Institutional · 13F <span className="fpsrc">EODHD · ~45d lag</span></div>
            {inst.available ? (<React.Fragment>
              <div className="fpbig">{inst.own_pct != null ? inst.own_pct.toFixed(1) + '%' : '—'} <span className="fpsub" style={{ color: tone(inst.net_state) }}>{inst.net_state}</span></div>
              <div className="fprow"><span>13F holders</span><b>{inst.n_holders}</b></div>
              {(inst.top || []).slice(0, 3).map((x, i) => (
                <div className="fprow sm" key={i}><span title={x.name}>{x.name}</span><b style={{ color: pctTone(x.change_p) }}>{x.pct}% ({x.change_p > 0 ? '+' : ''}{x.change_p}%)</b></div>
              ))}
            </React.Fragment>) : <div className="fpempty">no 13F data</div>}
          </div>
        </div>
      )}
      <div className="fpfoot">Unlike MCDX above, every figure here is an <b>observed SEC filing or a volume computation</b> — real, attributable footprints with their latency disclosed.</div>
    </div>
  );
}

// ── main lens ──
function LensBullAlgo(props) {
  const t = props.ticker || {};
  const sym = (t.sym || t.symbol || (typeof t === 'string' ? t : '') || '').toUpperCase();
  const MODE = BA_MODE_MAP[(props.mode || 'swing').toLowerCase()] || 'SWING';

  const [chartTf, setChartTf] = useBAs(BA_DEFAULT_TF[MODE] || 'SWING_4H');
  const [view, setView] = useBAs('signals');
  const [overlayOn, setOverlayOn] = useBAs(BA_OVERLAY_DEFAULT);
  const [data, setData] = useBAs(null);   // null=loading | {message} | {confirmation,...}

  // when the active mode changes, reset the chart timeframe to that mode's default
  useBAe(() => { setChartTf(BA_DEFAULT_TF[MODE] || 'SWING_4H'); }, [MODE]);

  // fetch the confirmation + screener + pac payload on ticker/mode change
  useBAe(() => {
    if (!sym) { setData({ message: 'No ticker selected.' }); return; }
    let on = true; setData(null);
    fetch(`/api/bullalgo/${sym}?mode=${MODE}`, { credentials: 'same-origin' })
      .then(r => r.json())
      .then(d => { if (on) setData(d || { message: 'no data' }); })
      .catch(e => { if (on) setData({ message: String(e) }); });
    return () => { on = false; };
  }, [sym, MODE]);

  return (
    <div className="lens-bullalgo">
      <div className="disc">⚗️ <span><b>Transparent</b> reproduction of the LuxAlgo Signals &amp; Overlays read — every layer is a standard, auditable indicator. <b>Display-only</b> · not a trade trigger · shadow feature pending out-of-sample validation.</span></div>

      {data === null ? (
        <div className="loading">computing {sym || '—'} · {MODE} …</div>
      ) : data.message ? (
        <div className="loading">⚠️ {data.message}</div>
      ) : (
        <React.Fragment>
          <BACharts
            ticker={sym} chartTf={chartTf} setChartTf={setChartTf}
            view={view} setView={setView}
            overlayOn={overlayOn} setOverlayOn={setOverlayOn}
          />
          <BAFootprint sym={sym} mode={MODE} />
          <div className="grid-top">
            <BAConfirmation c={data.confirmation} meta={data.confirmation_meta || {}} />
            <BALayers c={data.confirmation} />
          </div>
          <BAScreener rows={data.screener || []} />
          <BAPac rows={data.pac || []} />
        </React.Fragment>
      )}
    </div>
  );
}

window.LensBullAlgo = LensBullAlgo;

/* global React, window */
const { useState, useEffect, useMemo, useRef } = React;
const { MACRO, TAPE, SECTORS, INTEL, WATCHLIST, PILLARS, genSpark, genCandles } = window.ST_DATA;

/* ─── Sparkline SVG ─── */
function Sparkline({ pts, w = 80, h = 22, color = 'currentColor', fill = false }) {
  const min = Math.min(...pts), max = Math.max(...pts);
  const span = Math.max(0.001, max - min);
  const path = pts.map((p, i) => {
    const x = (i / (pts.length - 1)) * w;
    const y = h - ((p - min) / span) * (h - 2) - 1;
    return `${i === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`;
  }).join(' ');
  const area = path + ` L ${w} ${h} L 0 ${h} Z`;
  return (
    <svg className="spark-svg" viewBox={`0 0 ${w} ${h}`} width={w} height={h}>
      {fill && <path d={area} fill={color} fillOpacity="0.12" />}
      <path d={path} fill="none" stroke={color} strokeWidth="1.2" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}
window.Sparkline = Sparkline;

/* ─── Mini ruler (used inline in rows) ─── */
function MiniRuler({ lo, hi, stop, entry, t1, t2, px }) {
  const span = Math.max(0.0001, hi - lo);
  const pp = v => Math.max(0, Math.min(100, ((v - lo) / span) * 100));
  return (
    <div className="ruler-track ruler-mini" style={{ height: 14 }}>
      <div className="ruler-zone ruler-stop"   style={{ left: 0,                 width: `${pp(stop)}%` }} />
      <div className="ruler-zone ruler-entry"  style={{ left: `${pp(entry[0])}%`,width: `${pp(entry[1]) - pp(entry[0])}%` }} />
      <div className="ruler-zone ruler-runway" style={{ left: `${pp(entry[1])}%`,width: `${100 - pp(entry[1])}%` }} />
      <span className="ruler-tick t1" style={{ left: `${pp(t1)}%` }} />
      <span className="ruler-tick t2" style={{ left: `${pp(t2)}%` }} />
      <span className="ruler-now" style={{ left: `calc(${pp(px)}% - 1px)` }} />
    </div>
  );
}
window.MiniRuler = MiniRuler;

/* ─── Big ruler with labels ─── */
function BigRuler({ lo, hi, stop, entry, t1, t2, px }) {
  const span = Math.max(0.0001, hi - lo);
  const pp = v => Math.max(0, Math.min(100, ((v - lo) / span) * 100));
  return (
    <div className="ruler-wrap">
      <div className="ruler-track" style={{ height: 26 }}>
        <div className="ruler-zone ruler-stop"   style={{ left: 0, width: `${pp(stop)}%` }} />
        <div className="ruler-zone ruler-entry"  style={{ left: `${pp(entry[0])}%`, width: `${pp(entry[1]) - pp(entry[0])}%` }} />
        <div className="ruler-zone ruler-runway" style={{ left: `${pp(entry[1])}%`, width: `${100 - pp(entry[1])}%` }} />
        <span className="ruler-tick t1" style={{ left: `${pp(t1)}%` }} />
        <span className="ruler-tick t2" style={{ left: `${pp(t2)}%` }} />
        <span className="ruler-now"  style={{ left: `calc(${pp(px)}% - 1px)` }} />
      </div>
      <div className="ruler-labels">
        <div><span className="lbl down">STOP</span><span className="v num down">${stop.toFixed(2)}</span></div>
        <div><span className="lbl up">ENTRY</span><span className="v num up">${entry[0]}–${entry[1]}</span></div>
        <div><span className="lbl" style={{color:'var(--accent)'}}>T1</span><span className="v num" style={{color:'var(--accent)'}}>${t1.toFixed(2)}</span></div>
        <div><span className="lbl" style={{color:'var(--accent-2)'}}>T2</span><span className="v num" style={{color:'var(--accent-2)'}}>${t2.toFixed(2)}</span></div>
      </div>
    </div>
  );
}
window.BigRuler = BigRuler;

/* ─── Score arc gauge (SVG) ─── */
function Gauge({ val = 80, label = "BAP", size = 64 }) {
  const r = size * 0.42, c = size / 2;
  const start = -130, end = 130;
  const arc = (s, e) => {
    const sr = (s - 90) * Math.PI / 180, er = (e - 90) * Math.PI / 180;
    const x1 = c + r * Math.cos(sr), y1 = c + r * Math.sin(sr);
    const x2 = c + r * Math.cos(er), y2 = c + r * Math.sin(er);
    const large = Math.abs(e - s) > 180 ? 1 : 0;
    return `M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`;
  };
  const span = end - start;
  const valEnd = start + (val / 100) * span;
  const color = val >= 75 ? 'var(--green)' : val >= 50 ? 'var(--accent)' : 'var(--red)';
  return (
    <div className="gauge">
      <svg className="gauge-svg" viewBox={`0 0 ${size} ${size}`}>
        <path d={arc(start, end)} fill="none" stroke="var(--bg-3)" strokeWidth="4" strokeLinecap="round" />
        <path d={arc(start, valEnd)} fill="none" stroke={color} strokeWidth="4" strokeLinecap="round" style={{ filter: `drop-shadow(0 0 6px ${color.includes('var')?'currentColor':color})`, color }} />
        <text x={c} y={c+2} textAnchor="middle" dominantBaseline="middle" className="gauge-num" fill={color} fontSize={size*0.30} fontWeight="700" fontFamily="JetBrains Mono">{val}</text>
      </svg>
      <span className="gauge-lbl">{label}</span>
    </div>
  );
}
window.Gauge = Gauge;

/* ─── Hero candle chart (lightweight SVG) ─── */
function HeroChart({ candles, levels }) {
  const w = 720, h = 240, pad = { l: 8, r: 50, t: 14, b: 30 };
  const inner = { w: w - pad.l - pad.r, h: h - pad.t - pad.b };
  const lows = candles.map(c => c.low), highs = candles.map(c => c.high);
  const min = Math.min(...lows, levels.stop) * 0.998;
  const max = Math.max(...highs, levels.t2) * 1.002;
  const yScale = v => pad.t + ((max - v) / (max - min)) * inner.h;
  const cw = inner.w / candles.length;

  const last = candles[candles.length - 1].close;

  /* horizontal grid */
  const gridLines = [];
  for (let i = 1; i < 5; i++) {
    const y = pad.t + (inner.h / 5) * i;
    gridLines.push(<line key={i} x1={pad.l} x2={w - pad.r} y1={y} y2={y} stroke="var(--grid)" strokeDasharray="2 4" />);
  }

  /* level lines */
  const levelLines = [
    { v: levels.stop,   c: 'var(--red)',    lbl: `STOP $${levels.stop.toFixed(2)}` },
    { v: levels.entry[0], c: 'var(--green)', lbl: `ENT $${levels.entry[0]}` },
    { v: levels.entry[1], c: 'var(--green)', lbl: `ENT $${levels.entry[1]}`, dash: '3 3' },
    { v: levels.t1,     c: 'var(--accent)', lbl: `T1 $${levels.t1.toFixed(2)}` },
    { v: levels.t2,     c: 'var(--accent-2)', lbl: `T2 $${levels.t2.toFixed(2)}` },
  ];

  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{ width:'100%', height:'100%', display:'block' }}>
      {gridLines}
      {/* candles */}
      {candles.map((c, i) => {
        const x = pad.l + i * cw + cw * 0.5;
        const yo = yScale(c.open), yc = yScale(c.close);
        const yh = yScale(c.high), yl = yScale(c.low);
        const up = c.close >= c.open;
        const col = up ? 'var(--green)' : 'var(--red)';
        return (
          <g key={i}>
            <line x1={x} x2={x} y1={yh} y2={yl} stroke={col} strokeWidth="1" />
            <rect x={x - cw*0.34} y={Math.min(yo,yc)} width={Math.max(1, cw*0.68)} height={Math.max(1, Math.abs(yc-yo))} fill={col} fillOpacity={up?0.85:1} />
          </g>
        );
      })}
      {/* level lines */}
      {levelLines.map((l, i) => {
        const y = yScale(l.v);
        return (
          <g key={i}>
            <line x1={pad.l} x2={w - pad.r} y1={y} y2={y} stroke={l.c} strokeWidth="1" strokeDasharray={l.dash || '0'} opacity="0.7" />
            <rect x={w - pad.r + 2} y={y - 7} width={pad.r - 4} height={14} fill={l.c} opacity="0.18" />
            <text x={w - pad.r + 4} y={y + 3} fill={l.c} fontSize="9" fontFamily="JetBrains Mono" fontWeight="600">{l.lbl}</text>
          </g>
        );
      })}
      {/* current price marker */}
      <line x1={pad.l} x2={w - pad.r} y1={yScale(last)} y2={yScale(last)} stroke="var(--ink-0)" strokeWidth="1" strokeDasharray="1 2" opacity="0.5" />
      <rect x={w - pad.r + 2} y={yScale(last) - 8} width={pad.r - 4} height={16} fill="var(--ink-0)" />
      <text x={w - pad.r + 4} y={yScale(last) + 4} fill="var(--bg-0)" fontSize="10" fontWeight="700" fontFamily="JetBrains Mono">{last.toFixed(2)}</text>
      {/* x labels */}
      <text x={pad.l} y={h - 8} fontSize="9" fill="var(--ink-3)" fontFamily="JetBrains Mono">3M</text>
      <text x={w/2} y={h - 8} fontSize="9" fill="var(--ink-3)" fontFamily="JetBrains Mono" textAnchor="middle">1M</text>
      <text x={w - pad.r} y={h - 8} fontSize="9" fill="var(--ink-3)" fontFamily="JetBrains Mono" textAnchor="end">NOW</text>
    </svg>
  );
}
window.HeroChart = HeroChart;

/* ─── Tape (top-bar ticker tape) ─── */
function Tape() {
  const items = [...TAPE, ...TAPE];
  return (
    <div className="ticker-tape">
      <div className="ticker-tape-inner">
        {items.map((t, i) => (
          <span key={i} className="tt-item num">
            <span className="tt-sym">{t[0]}</span>
            <span>{typeof t[1] === 'number' ? t[1].toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : t[1]}</span>
            <span className={t[2] >= 0 ? 'up' : 'down'}>{t[2] >= 0 ? '+' : ''}{t[2].toFixed(2)}%</span>
            <span className="tt-sep">·</span>
          </span>
        ))}
      </div>
    </div>
  );
}
window.Tape = Tape;

/* ─── Macro strip ─── */
function MacroStrip() {
  return (
    <div className="macro">
      {MACRO.map((m, i) => {
        const trend = m.spark === 'up' ? 0.4 : m.spark === 'down' ? -0.4 : 0;
        const pts = useMemo(() => genSpark(i + 7, 20, trend), [i]);
        const sparkColor = m.invert
          ? (m.chg < 0 ? 'var(--green)' : 'var(--red)')
          : (m.chg >= 0 ? 'var(--green)' : 'var(--red)');
        return (
          <div className="macro-cell" key={m.sym}>
            <span className="macro-cell-lbl">{m.sym}</span>
            <span className="macro-cell-val">{m.val}</span>
            <span className={`macro-cell-chg ${m.invert ? (m.chg < 0 ? 'up' : 'down') : (m.chg >= 0 ? 'up' : 'down')}`}>
              {m.chg >= 0 ? '+' : ''}{m.chg.toFixed(2)}%
            </span>
            <span className="macro-spark"><Sparkline pts={pts} w={50} h={16} color={sparkColor} /></span>
          </div>
        );
      })}
      <div className="regime macro-cell" style={{borderRight:'none'}}>
        <span className="regime-dot" />
        <span className="regime-name">RISK ON</span>
        <span className="regime-meta">BREADTH 68 · VIX↓</span>
      </div>
    </div>
  );
}
window.MacroStrip = MacroStrip;

/* ─── Sector heatmap ─── */
function Heatmap({ onPick }) {
  return (
    <div className="heatmap">
      {SECTORS.map((s, i) => {
        const intensity = Math.min(1, Math.abs(s.pct) / 2);
        const bg = s.pct >= 0
          ? `color-mix(in oklch, var(--green) ${15 + intensity * 50}%, var(--bg-2))`
          : `color-mix(in oklch, var(--red) ${15 + intensity * 50}%, var(--bg-2))`;
        const fg = s.pct >= 0 ? 'var(--green)' : 'var(--red)';
        return (
          <div key={i} className="heat-cell" style={{ background: bg }} onClick={() => onPick && onPick(s.name)}>
            <div>
              <div className="heat-cell-name">{s.name}</div>
              <div className="heat-cell-meta">VOL {s.vol} · {s.winners}/{s.losers}</div>
            </div>
            <div className="heat-cell-pct" style={{ color: fg }}>
              {s.pct >= 0 ? '+' : ''}{s.pct.toFixed(2)}%
            </div>
          </div>
        );
      })}
    </div>
  );
}
window.Heatmap = Heatmap;

/* ─── Intel feed ─── */
function IntelFeed({ rows, max }) {
  return (
    <div>
      {rows.slice(0, max || 9).map((r, i) => (
        <div key={i} className="intel-row">
          <span className="intel-time">{r.t}</span>
          <span className="intel-text">
            <span className="num" style={{ color: 'var(--accent)' }}>{r.sym}</span>
            <span className="dim2">  ·  </span>
            <span dangerouslySetInnerHTML={{ __html: r.text }} />
          </span>
          <span className={`intel-tag ${r.sent}`}>
            {r.sent === 'up' ? '▲ BULL' : r.sent === 'dn' ? '▼ BEAR' : '◆ NEUT'}
          </span>
        </div>
      ))}
    </div>
  );
}
window.IntelFeed = IntelFeed;

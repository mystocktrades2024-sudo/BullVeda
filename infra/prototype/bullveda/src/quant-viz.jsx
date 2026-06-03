// quant-viz.jsx — shared SVG visualization primitives for the quant workspace tabs.
// All read CSS vars at runtime so theme + Tweaks just work. Exported to window.
// QEquity · QUnderwater · QHist · QMonths · QDiverge · QGaugeBar · QSpark

const { useMemo: useQV, useRef: useQVr, useState: useQVs, useEffect: useQVe } = React;

// ── cumulative equity curve: book area + benchmark line + last marker ──
function QEquity({ book, bench, w = 640, h = 150, tone = "gn" }) {
  const all = [...book, ...(bench || [])];
  const min = Math.min(...all, 0), max = Math.max(...all, 1);
  const pad = (max - min) * 0.08 || 1;
  const lo = min - pad, hi = max + pad;
  const x = i => (i / (book.length - 1)) * w;
  const y = v => h - ((v - lo) / (hi - lo)) * h;
  const line = arr => arr.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const gid = `qe-${Math.random().toString(36).slice(2, 7)}`;
  const last = book[book.length - 1];
  return (
    <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{ display: "block", overflow: "visible" }}>
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={`var(--${tone})`} stopOpacity="0.28" />
          <stop offset="100%" stopColor={`var(--${tone})`} stopOpacity="0" />
        </linearGradient>
      </defs>
      <line x1="0" y1={y(0)} x2={w} y2={y(0)} stroke="var(--glass-line)" strokeDasharray="2 3" />
      <path d={`M 0 ${y(0)} L ${line(book)} L ${w} ${y(0)} Z`} fill={`url(#${gid})`} />
      {bench && <polyline points={line(bench)} fill="none" stroke="var(--ink-3)" strokeWidth="1.4" strokeDasharray="4 3" opacity="0.8" />}
      <polyline points={line(book)} fill="none" stroke={`var(--${tone})`} strokeWidth="2" style={{ filter: `drop-shadow(0 0 5px var(--${tone}))` }} />
      <circle cx={x(book.length - 1)} cy={y(last)} r="3.4" fill={`var(--${tone})`} style={{ filter: `drop-shadow(0 0 6px var(--${tone}))` }} />
    </svg>
  );
}

// ── underwater drawdown curve (always ≤ 0, red fill downward) ──
function QUnderwater({ dd, w = 640, h = 70 }) {
  const min = Math.min(...dd, -1);
  const x = i => (i / (dd.length - 1)) * w;
  const y = v => (v / min) * (h - 4);
  const gid = `uw-${Math.random().toString(36).slice(2, 7)}`;
  return (
    <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{ display: "block" }}>
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--rd)" stopOpacity="0.05" />
          <stop offset="100%" stopColor="var(--rd)" stopOpacity="0.35" />
        </linearGradient>
      </defs>
      <path d={`M 0 0 L ${dd.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" L ")} L ${w} 0 Z`} fill={`url(#${gid})`} />
      <polyline points={dd.map((v, i) => `${x(i)},${y(v)}`).join(" ")} fill="none" stroke="var(--rd)" strokeWidth="1.3" opacity="0.8" />
    </svg>
  );
}

// ── R-multiple distribution histogram (losers red left, winners green right) ──
function QHist({ bins, w = 320, h = 130 }) {
  // bins: [{ label, count, win }]
  const max = Math.max(...bins.map(b => b.count), 1);
  const bw = w / bins.length;
  return (
    <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{ display: "block", overflow: "visible" }}>
      {bins.map((b, i) => {
        const bh = (b.count / max) * (h - 22);
        return (
          <g key={i}>
            <rect x={i * bw + 1.5} y={h - 18 - bh} width={bw - 3} height={bh}
              fill={b.win ? "var(--gn)" : "var(--rd)"} opacity={b.count ? 0.6 : 0.12} rx="1.5" />
            <text x={i * bw + bw / 2} y={h - 6} textAnchor="middle" fontSize="8" className="mono" fill="var(--ink-3)">{b.label}</text>
            {b.count > 0 && <text x={i * bw + bw / 2} y={h - 22 - bh} textAnchor="middle" fontSize="8.5" className="mono" fill="var(--ink-2)">{b.count}</text>}
          </g>
        );
      })}
    </svg>
  );
}

// ── monthly returns strip (colored cells) ──
function QMonths({ months }) {
  // months: [{ m, r }]  r in %
  const cap = Math.max(...months.map(x => Math.abs(x.r)), 1);
  return (
    <div className="q-months">
      {months.map((x, i) => {
        const t = Math.min(1, Math.abs(x.r) / cap);
        const c = x.r >= 0 ? `color-mix(in oklab, var(--gn) ${10 + t * 55}%, transparent)` : `color-mix(in oklab, var(--rd) ${10 + t * 55}%, transparent)`;
        return (
          <div key={i} className="q-month" style={{ background: c }}>
            <span className="q-month-m mono dim2">{x.m}</span>
            <span className={`q-month-r mono ${x.r >= 0 ? "up" : "dn"}`}>{x.r >= 0 ? "+" : ""}{x.r.toFixed(1)}</span>
          </div>
        );
      })}
    </div>
  );
}

// ── diverging horizontal bar list (attribution etc) ──
function QDiverge({ rows, fmt }) {
  // rows: [{ label, value, tone }]  value is signed; bar width scaled to max abs
  const cap = Math.max(...rows.map(r => Math.abs(r.value)), 1);
  return (
    <div className="q-div">
      {rows.map((r, i) => {
        const pct = Math.min(48, (Math.abs(r.value) / cap) * 48);
        const tone = r.tone || (r.value >= 0 ? "gn" : "rd");
        return (
          <div key={i} className="q-div-row">
            <span className="q-div-l">{r.label}</span>
            <div className="q-div-bar">
              <div className="q-div-ax" />
              <div className="q-div-f" style={{ width: `${pct}%`, marginLeft: r.value >= 0 ? "50%" : `${50 - pct}%`, background: `var(--${tone})` }} />
            </div>
            <span className={`q-div-v mono kpi-tone--${tone}`}>{fmt ? fmt(r.value) : r.value}</span>
          </div>
        );
      })}
    </div>
  );
}

// ── horizontal gauge bar with cap marker (0..1 fill, optional cap) ──
function QGaugeBar({ pct, cap, tone = "gn" }) {
  return (
    <div className="q-gauge">
      <div className="q-gauge-f" style={{ width: `${Math.min(100, pct)}%`, background: `var(--${tone})` }} />
      {cap != null && <div className="q-gauge-cap" style={{ left: `${Math.min(100, cap)}%` }} />}
    </div>
  );
}

// ── tiny inline sparkline for table cells (edge decay etc) ──
function QSpark({ data, tone = "gn", w = 70, h = 20 }) {
  if (!data || !data.length) return null;
  const min = Math.min(...data), max = Math.max(...data), r = max - min || 1;
  const x = i => (i / (data.length - 1)) * w;
  const y = v => h - ((v - min) / r) * (h - 3) - 1.5;
  const down = data[data.length - 1] < data[0];
  const c = down ? "amb" : tone;
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ display: "block" }}>
      <polyline points={data.map((v, i) => `${x(i)},${y(v)}`).join(" ")} fill="none" stroke={`var(--${c})`} strokeWidth="1.3" />
      <circle cx={x(data.length - 1)} cy={y(data[data.length - 1])} r="1.8" fill={`var(--${c})`} />
    </svg>
  );
}

Object.assign(window, { QEquity, QUnderwater, QHist, QMonths, QDiverge, QGaugeBar, QSpark });

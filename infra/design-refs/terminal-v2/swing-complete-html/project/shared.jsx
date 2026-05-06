// Shared components used by all three design directions

/* ──────────────────────────────────────────
   Tooltip helper — wraps any element
   ────────────────────────────────────────── */
function Tip({ text, children, color = "rgba(15, 23, 42, 0.98)", textColor = "#cbd5e1", border = "rgba(148, 163, 184, 0.2)" }) {
  const [show, setShow] = React.useState(false);
  const [pos, setPos] = React.useState({ x: 0, y: 0 });
  const ref = React.useRef(null);
  return (
    <span
      ref={ref}
      onMouseEnter={(e) => {
        const r = e.currentTarget.getBoundingClientRect();
        setPos({ x: r.left + r.width / 2, y: r.top - 8 });
        setShow(true);
      }}
      onMouseLeave={() => setShow(false)}
      style={{ display: 'inline-flex', alignItems: 'center', position: 'relative' }}
    >
      {children}
      {show && ReactDOM.createPortal(
        <div className="metric-tooltip" style={{
          left: pos.x, top: pos.y,
          transform: 'translate(-50%, -100%)',
          background: color, color: textColor,
          border: `1px solid ${border}`,
          boxShadow: '0 12px 40px rgba(0,0,0,0.6)',
        }}>{text}</div>,
        document.body
      )}
    </span>
  );
}

/* ──────────────────────────────────────────
   Sparkline — reusable mini chart
   ────────────────────────────────────────── */
function Sparkline({ candles, width = 100, height = 28, color = '#4ade80', fill = false }) {
  if (!candles?.length) return null;
  const closes = candles.map(c => c.close);
  const min = Math.min(...closes), max = Math.max(...closes);
  const range = max - min || 1;
  const pts = closes.map((c, i) => {
    const x = (i / (closes.length - 1)) * width;
    const y = height - ((c - min) / range) * height;
    return [x, y];
  });
  const d = pts.map((p, i) => (i === 0 ? `M${p[0]},${p[1]}` : `L${p[0]},${p[1]}`)).join(' ');
  const area = `${d} L${width},${height} L0,${height} Z`;
  return (
    <svg width={width} height={height} style={{ display: 'block' }}>
      {fill && <path d={area} fill={color} fillOpacity="0.12" />}
      <path d={d} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

/* ──────────────────────────────────────────
   Candlestick chart — full chart for the Chart tab
   ────────────────────────────────────────── */
function CandleChart({ candles, plan, width = 880, height = 360, theme }) {
  const padL = 50, padR = 60, padT = 20, padB = 40;
  const chartW = width - padL - padR;
  const chartH = height - padT - padB;

  const min = Math.min(...candles.map(c => c.low)) * 0.995;
  const max = Math.max(...candles.map(c => c.high)) * 1.005;
  const yScale = (v) => padT + ((max - v) / (max - min)) * chartH;
  const xScale = (i) => padL + (i / (candles.length - 1)) * chartW;
  const cw = (chartW / candles.length) * 0.6;

  // SMA20
  const sma20 = candles.map((_, i) => {
    if (i < 19) return null;
    const slice = candles.slice(i - 19, i + 1);
    return slice.reduce((s, c) => s + c.close, 0) / 20;
  });

  // EMA21
  const ema21 = [];
  const k = 2 / (21 + 1);
  candles.forEach((c, i) => {
    if (i === 0) ema21.push(c.close);
    else ema21.push(c.close * k + ema21[i - 1] * (1 - k));
  });

  const yTicks = 5;
  const ticks = Array.from({ length: yTicks + 1 }, (_, i) => min + (i / yTicks) * (max - min));

  return (
    <svg width={width} height={height} style={{ display: 'block', overflow: 'visible' }}>
      {/* Grid */}
      {ticks.map((t, i) => (
        <g key={i}>
          <line x1={padL} y1={yScale(t)} x2={width - padR} y2={yScale(t)}
                stroke={theme.grid} strokeWidth="1" strokeDasharray="2 4" />
          <text x={padL - 8} y={yScale(t) + 3} fontSize="10" fill={theme.muted} textAnchor="end" fontFamily="JetBrains Mono, monospace">
            {t.toFixed(0)}
          </text>
        </g>
      ))}

      {/* Plan zones */}
      {plan && (
        <>
          <rect x={padL} y={yScale(plan.entryZone[1])} width={chartW}
                height={yScale(plan.entryZone[0]) - yScale(plan.entryZone[1])}
                fill={theme.bull} fillOpacity="0.08" />
          <line x1={padL} y1={yScale(plan.target1)} x2={width - padR} y2={yScale(plan.target1)}
                stroke={theme.bull} strokeWidth="1" strokeDasharray="6 4" opacity="0.7" />
          <line x1={padL} y1={yScale(plan.target2)} x2={width - padR} y2={yScale(plan.target2)}
                stroke={theme.bull} strokeWidth="1" strokeDasharray="6 4" opacity="0.5" />
          <line x1={padL} y1={yScale(plan.stop)} x2={width - padR} y2={yScale(plan.stop)}
                stroke={theme.bear} strokeWidth="1" strokeDasharray="6 4" opacity="0.8" />
          <text x={width - padR + 6} y={yScale(plan.target1) + 3} fontSize="10" fill={theme.bull} fontFamily="JetBrains Mono, monospace">T1 {plan.target1}</text>
          <text x={width - padR + 6} y={yScale(plan.target2) + 3} fontSize="10" fill={theme.bull} fontFamily="JetBrains Mono, monospace">T2 {plan.target2}</text>
          <text x={width - padR + 6} y={yScale(plan.stop) + 3} fontSize="10" fill={theme.bear} fontFamily="JetBrains Mono, monospace">SL {plan.stop}</text>
        </>
      )}

      {/* SMA20 line */}
      <path d={sma20.map((v, i) => v == null ? '' : `${i === 19 ? 'M' : 'L'}${xScale(i)},${yScale(v)}`).join(' ')}
            fill="none" stroke={theme.line2} strokeWidth="1.5" opacity="0.7" />
      {/* EMA21 line */}
      <path d={ema21.map((v, i) => `${i === 0 ? 'M' : 'L'}${xScale(i)},${yScale(v)}`).join(' ')}
            fill="none" stroke={theme.line1} strokeWidth="1.5" opacity="0.85" />

      {/* Candles */}
      {candles.map((c, i) => {
        const up = c.close >= c.open;
        const x = xScale(i);
        const color = up ? theme.bull : theme.bear;
        return (
          <g key={i}>
            <line x1={x} y1={yScale(c.high)} x2={x} y2={yScale(c.low)} stroke={color} strokeWidth="1" />
            <rect x={x - cw / 2} y={yScale(Math.max(c.open, c.close))}
                  width={cw} height={Math.max(1, Math.abs(yScale(c.open) - yScale(c.close)))}
                  fill={up ? color : color} fillOpacity={up ? 0.85 : 1} />
          </g>
        );
      })}

      {/* X axis date labels */}
      {[0, Math.floor(candles.length * 0.33), Math.floor(candles.length * 0.66), candles.length - 1].map(i => (
        <text key={i} x={xScale(i)} y={height - padB + 18} fontSize="10" fill={theme.muted}
              textAnchor="middle" fontFamily="JetBrains Mono, monospace">
          {candles[i].date.slice(5)}
        </text>
      ))}

      {/* Last price line */}
      <line x1={padL} y1={yScale(candles[candles.length - 1].close)} x2={width - padR}
            y2={yScale(candles[candles.length - 1].close)} stroke={theme.accent} strokeWidth="1" strokeDasharray="2 2" opacity="0.6" />
      <rect x={width - padR} y={yScale(candles[candles.length - 1].close) - 9} width={padR - 4} height={18} fill={theme.accent} rx="2" />
      <text x={width - padR + (padR - 4) / 2} y={yScale(candles[candles.length - 1].close) + 4} fontSize="11" fontWeight="700" fill="#0b1220" textAnchor="middle" fontFamily="JetBrains Mono, monospace">
        {candles[candles.length - 1].close.toFixed(2)}
      </text>
    </svg>
  );
}

/* ──────────────────────────────────────────
   Stylized chart (clean version)
   ────────────────────────────────────────── */
function StylizedChart({ candles, plan, width = 880, height = 360, theme }) {
  const padL = 50, padR = 60, padT = 20, padB = 40;
  const chartW = width - padL - padR;
  const chartH = height - padT - padB;

  const min = Math.min(...candles.map(c => c.low)) * 0.995;
  const max = Math.max(...candles.map(c => c.high)) * 1.005;
  const yScale = (v) => padT + ((max - v) / (max - min)) * chartH;
  const xScale = (i) => padL + (i / (candles.length - 1)) * chartW;

  const linePath = candles.map((c, i) => `${i === 0 ? 'M' : 'L'}${xScale(i)},${yScale(c.close)}`).join(' ');
  const areaPath = `${linePath} L${xScale(candles.length - 1)},${padT + chartH} L${padL},${padT + chartH} Z`;

  return (
    <svg width={width} height={height} style={{ display: 'block', overflow: 'visible' }}>
      <defs>
        <linearGradient id="areaGrad" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={theme.accent} stopOpacity="0.4" />
          <stop offset="100%" stopColor={theme.accent} stopOpacity="0" />
        </linearGradient>
      </defs>

      {/* Plan zones */}
      {plan && (
        <>
          <rect x={padL} y={yScale(plan.target2)} width={chartW}
                height={yScale(plan.entryZone[1]) - yScale(plan.target2)}
                fill={theme.bull} fillOpacity="0.04" />
          <rect x={padL} y={yScale(plan.entryZone[1])} width={chartW}
                height={yScale(plan.entryZone[0]) - yScale(plan.entryZone[1])}
                fill={theme.bull} fillOpacity="0.16" />
          <rect x={padL} y={yScale(plan.entryZone[0])} width={chartW}
                height={yScale(plan.stop) - yScale(plan.entryZone[0])}
                fill={theme.bear} fillOpacity="0.06" />
          <line x1={padL} y1={yScale(plan.target1)} x2={width - padR} y2={yScale(plan.target1)}
                stroke={theme.bull} strokeWidth="1" strokeDasharray="2 4" />
          <line x1={padL} y1={yScale(plan.target2)} x2={width - padR} y2={yScale(plan.target2)}
                stroke={theme.bull} strokeWidth="1" strokeDasharray="2 4" opacity="0.6" />
          <line x1={padL} y1={yScale(plan.stop)} x2={width - padR} y2={yScale(plan.stop)}
                stroke={theme.bear} strokeWidth="1" strokeDasharray="2 4" />
          <text x={width - padR + 6} y={yScale(plan.target1) + 3} fontSize="10" fill={theme.bull} fontFamily="JetBrains Mono, monospace" fontWeight="600">T1 {plan.target1}</text>
          <text x={width - padR + 6} y={yScale(plan.target2) + 3} fontSize="10" fill={theme.bull} fontFamily="JetBrains Mono, monospace">T2 {plan.target2}</text>
          <text x={width - padR + 6} y={yScale(plan.stop) + 3} fontSize="10" fill={theme.bear} fontFamily="JetBrains Mono, monospace" fontWeight="600">SL {plan.stop}</text>
          <text x={padL + 8} y={yScale(plan.entry) - 6} fontSize="10" fill={theme.text} fontFamily="JetBrains Mono, monospace" fontWeight="700">ENTRY {plan.entry}</text>
        </>
      )}

      {/* Y grid */}
      {[0, 0.25, 0.5, 0.75, 1].map((p, i) => (
        <line key={i} x1={padL} y1={padT + p * chartH} x2={width - padR} y2={padT + p * chartH}
              stroke={theme.grid} strokeWidth="1" />
      ))}

      <path d={areaPath} fill="url(#areaGrad)" />
      <path d={linePath} fill="none" stroke={theme.accent} strokeWidth="2" strokeLinejoin="round" />

      {/* Last point */}
      <circle cx={xScale(candles.length - 1)} cy={yScale(candles[candles.length - 1].close)} r="5" fill={theme.accent} />
      <circle cx={xScale(candles.length - 1)} cy={yScale(candles[candles.length - 1].close)} r="10" fill={theme.accent} fillOpacity="0.2" />

      {[0, Math.floor(candles.length * 0.5), candles.length - 1].map(i => (
        <text key={i} x={xScale(i)} y={height - padB + 18} fontSize="10" fill={theme.muted}
              textAnchor="middle" fontFamily="JetBrains Mono, monospace">
          {candles[i].date.slice(5)}
        </text>
      ))}
      {[min, (min + max) / 2, max].map((v, i) => (
        <text key={i} x={padL - 8} y={yScale(v) + 3} fontSize="10" fill={theme.muted} textAnchor="end" fontFamily="JetBrains Mono, monospace">
          {v.toFixed(0)}
        </text>
      ))}
    </svg>
  );
}

/* ──────────────────────────────────────────
   Animated score arc / ring
   ────────────────────────────────────────── */
function ScoreArc({ value, max = 100, size = 120, stroke = 8, color, bg, label, sublabel, valueColor }) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const pct = Math.min(1, value / max);
  const [animated, setAnimated] = React.useState(0);
  React.useEffect(() => {
    let raf;
    const start = performance.now();
    const dur = 1200;
    const step = (t) => {
      const p = Math.min(1, (t - start) / dur);
      const eased = 1 - Math.pow(1 - p, 3);
      setAnimated(eased);
      if (p < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [value]);
  const dash = c * pct * animated;
  return (
    <div style={{ position: 'relative', width: size, height: size, display: 'inline-block' }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={bg} strokeWidth={stroke} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color}
                strokeWidth={stroke} strokeLinecap="round"
                strokeDasharray={`${dash} ${c}`} />
      </svg>
      <div style={{
        position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center', textAlign: 'center',
      }}>
        <div style={{ fontSize: size * 0.28, fontWeight: 700, color: valueColor || color, fontFamily: 'JetBrains Mono, monospace', lineHeight: 1 }}>
          {Math.round(value * animated)}
        </div>
        {label && <div style={{ fontSize: 10, fontWeight: 600, color: 'currentColor', opacity: 0.7, marginTop: 4, letterSpacing: '0.08em' }}>{label}</div>}
        {sublabel && <div style={{ fontSize: 9, opacity: 0.5, marginTop: 2 }}>{sublabel}</div>}
      </div>
    </div>
  );
}

/* ──────────────────────────────────────────
   Horizontal score bar
   ────────────────────────────────────────── */
function ScoreBar({ value, max = 100, color, bg = 'rgba(255,255,255,0.06)', label, sublabel, hint, height = 6, valueColor }) {
  const [animated, setAnimated] = React.useState(0);
  React.useEffect(() => {
    let raf;
    const start = performance.now();
    const dur = 900;
    const step = (t) => {
      const p = Math.min(1, (t - start) / dur);
      setAnimated(1 - Math.pow(1 - p, 3));
      if (p < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [value]);
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6 }}>
        <Tip text={hint || label}>
          <span style={{ fontSize: 11, fontWeight: 600, color: 'currentColor', opacity: 0.75, letterSpacing: '0.05em', textTransform: 'uppercase', cursor: 'help', borderBottom: '1px dotted currentColor' }}>{label}</span>
        </Tip>
        <span style={{ fontSize: 13, fontWeight: 700, fontFamily: 'JetBrains Mono, monospace', color: valueColor || color }}>
          {Math.round(value * animated)}<span style={{ opacity: 0.4, fontWeight: 400, fontSize: 10 }}>/{max}</span>
        </span>
      </div>
      <div style={{ width: '100%', height, background: bg, borderRadius: height / 2, overflow: 'hidden' }}>
        <div style={{ width: `${(value / max) * 100 * animated}%`, height: '100%', background: color, borderRadius: height / 2 }} />
      </div>
      {sublabel && <div style={{ fontSize: 10, opacity: 0.5, marginTop: 4 }}>{sublabel}</div>}
    </div>
  );
}

/* Expose */
Object.assign(window, { Tip, Sparkline, CandleChart, StylizedChart, ScoreArc, ScoreBar });

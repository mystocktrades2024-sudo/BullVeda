// ELITE COCKPIT — Swing Desk
// Three-column layout: Pulse (left 280px) · Focus (center flex) · Plan (right 340px)
// Color system
const C = {
  bg:       '#080c14',
  s1:       '#0d1320',
  s2:       '#131b2e',
  s3:       '#1a2540',
  border:   'rgba(148,163,184,0.09)',
  div:      'rgba(148,163,184,0.05)',
  text:     '#e8eef8',
  sub:      '#8fa3c8',
  muted:    '#4e637e',
  gold:     '#d4a847',
  goldDim:  '#9a7a35',
  cyan:     '#38bdf8',
  bull:     '#4ade80',
  bear:     '#f87171',
  warn:     '#fbbf24',
};

const mono = 'JetBrains Mono, monospace';
const sans = 'Inter, system-ui, sans-serif';

const D = window.TICKR_DATA;
const SCAN = window.SCANNER_DATA;

function pct(n) { return `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`; }
function money(n) { return `$${n.toFixed(2)}`; }

// ── Label ──────────────────────────────────────────────────────
function Label({ children, color = C.muted }) {
  return (
    <div style={{
      fontSize: 9, fontWeight: 700, letterSpacing: '0.18em',
      textTransform: 'uppercase', color, fontFamily: mono,
    }}>
      {children}
    </div>
  );
}

// ── Divider ─────────────────────────────────────────────────────
function Div({ my = 20 }) {
  return <div style={{ height: 1, background: C.border, margin: `${my}px 0` }} />;
}

// ── Metric cell ─────────────────────────────────────────────────
function Metric({ label, value, sub, valueColor = C.text, large }) {
  return (
    <div>
      <Label>{label}</Label>
      <div style={{ fontSize: large ? 28 : 18, fontWeight: 800, color: valueColor, fontFamily: mono, lineHeight: 1, marginTop: 5 }}>{value}</div>
      {sub && <div style={{ fontSize: 10, color: C.sub, marginTop: 3 }}>{sub}</div>}
    </div>
  );
}

// ── Verdict badge ───────────────────────────────────────────────
function VerdictBadge({ v }) {
  const map = { BUY: C.bull, WAIT: C.warn, HOLD: C.cyan, AVOID: C.bear };
  const c = map[v] || C.sub;
  return (
    <div style={{
      display: 'inline-flex', alignItems: 'center', gap: 8,
      padding: '6px 14px', border: `1px solid ${c}50`,
      background: `${c}12`, borderRadius: 3,
    }}>
      <div style={{ width: 6, height: 6, borderRadius: '50%', background: c }} />
      <span style={{ fontSize: 11, fontWeight: 800, color: c, letterSpacing: '0.18em', fontFamily: mono }}>{v}</span>
    </div>
  );
}

// ── Score ring (mini) ───────────────────────────────────────────
function MiniRing({ value, color, size = 52, stroke = 4 }) {
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  const [anim, setAnim] = React.useState(0);
  React.useEffect(() => {
    let raf;
    const t0 = performance.now();
    const run = (t) => {
      const p = Math.min(1, (t - t0) / 900);
      setAnim(1 - Math.pow(1 - p, 3));
      if (p < 1) raf = requestAnimationFrame(run);
    };
    raf = requestAnimationFrame(run);
    return () => cancelAnimationFrame(raf);
  }, [value]);
  return (
    <div style={{ position: 'relative', width: size, height: size, flexShrink: 0 }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={C.s3} strokeWidth={stroke} />
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color}
          strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={`${circ * (value / 100) * anim} ${circ}`} />
      </svg>
      <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <span style={{ fontSize: 13, fontWeight: 800, color, fontFamily: mono }}>
          {Math.round(value * anim)}
        </span>
      </div>
    </div>
  );
}

// ── Pill ────────────────────────────────────────────────────────
function Pill({ label, active, color, onClick }) {
  return (
    <button onClick={onClick} style={{
      padding: '5px 12px', fontSize: 10, fontWeight: 700, letterSpacing: '0.1em',
      fontFamily: mono, border: `1px solid ${active ? color + '60' : C.border}`,
      background: active ? `${color}14` : 'transparent',
      color: active ? color : C.muted, borderRadius: 3, cursor: 'pointer', transition: 'all 150ms',
    }}>{label}</button>
  );
}

// ──────────────────────────────────────────────────────────────────
// LEFT: PULSE
// ──────────────────────────────────────────────────────────────────
function Pulse({ focused, onSelect }) {
  const byScore = [...SCAN].sort((a, b) => b.score - a.score).slice(0, 8);
  return (
    <div style={{
      width: 264, flexShrink: 0,
      background: C.s1, borderRight: `1px solid ${C.border}`,
      display: 'flex', flexDirection: 'column', overflow: 'hidden',
    }}>
      {/* Brand */}
      <div style={{ padding: '20px 20px 14px', borderBottom: `1px solid ${C.border}` }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            width: 28, height: 28, borderRadius: 4,
            background: `linear-gradient(135deg, ${C.gold}, ${C.cyan})`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 13, fontWeight: 900, color: C.bg,
          }}>S</div>
          <div>
            <div style={{ fontSize: 12, fontWeight: 800, letterSpacing: '0.14em', color: C.text, fontFamily: mono }}>SWING DESK</div>
            <div style={{ fontSize: 9, color: C.muted, marginTop: 1, fontFamily: mono, letterSpacing: '0.1em' }}>LIVE · {D.asOf.slice(0, 10)}</div>
          </div>
        </div>
      </div>

      {/* Regime */}
      <div style={{ padding: '14px 20px', borderBottom: `1px solid ${C.border}` }}>
        <Label color={C.bull}>Market Regime</Label>
        <div style={{ fontSize: 16, fontWeight: 800, color: C.text, marginTop: 6, letterSpacing: '-0.01em' }}>Risk-On · Trending</div>
        <div style={{ display: 'flex', gap: 14, marginTop: 8 }}>
          {[['SPY', '+0.84%', C.bull], ['VIX', '14.8', C.bull], ['BRD', '72%', C.cyan]].map(([k, v, c]) => (
            <div key={k}>
              <div style={{ fontSize: 8, color: C.muted, fontFamily: mono, letterSpacing: '0.12em' }}>{k}</div>
              <div style={{ fontSize: 13, fontWeight: 700, color: c, fontFamily: mono, marginTop: 2 }}>{v}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Conviction list */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '14px 0' }} className="dashboard-scroll">
        <div style={{ padding: '0 20px 10px' }}>
          <Label color={C.gold}>Conviction List</Label>
        </div>
        {byScore.map((r, i) => {
          const active = r.ticker === focused;
          return (
            <div key={r.ticker} onClick={() => onSelect(r.ticker)}
              style={{
                padding: '10px 20px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 10,
                background: active ? C.s3 : 'transparent',
                borderLeft: `2px solid ${active ? C.gold : 'transparent'}`,
                transition: 'all 150ms',
              }}
              onMouseEnter={e => { if (!active) e.currentTarget.style.background = C.s2; }}
              onMouseLeave={e => { if (!active) e.currentTarget.style.background = 'transparent'; }}
            >
              <div style={{ fontSize: 10, fontFamily: mono, color: C.muted, width: 18 }}>{String(i + 1).padStart(2, '0')}</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: C.text, fontFamily: mono }}>{r.ticker}</div>
                <div style={{ fontSize: 10, color: C.muted, marginTop: 1, overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' }}>{r.setup}</div>
              </div>
              <div style={{ textAlign: 'right', flexShrink: 0 }}>
                <div style={{ fontSize: 14, fontWeight: 800, color: C.gold, fontFamily: mono }}>{r.score}</div>
                <div style={{ fontSize: 10, fontFamily: mono, color: r.changePct >= 0 ? C.bull : C.bear, fontWeight: 600 }}>{pct(r.changePct)}</div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Footer stats */}
      <div style={{ padding: '12px 20px', borderTop: `1px solid ${C.border}` }}>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <div><Label>Positions</Label><div style={{ fontSize: 13, fontWeight: 700, color: C.text, fontFamily: mono, marginTop: 3 }}>8</div></div>
          <div><Label>Heat</Label><div style={{ fontSize: 13, fontWeight: 700, color: C.warn, fontFamily: mono, marginTop: 3 }}>3.2%</div></div>
          <div><Label>Day P&amp;L</Label><div style={{ fontSize: 13, fontWeight: 700, color: C.bull, fontFamily: mono, marginTop: 3 }}>+$2,847</div></div>
        </div>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────
// CENTER: FOCUS — full analysis of the focused ticker
// ──────────────────────────────────────────────────────────────────
const TABS = ['Overview', 'Technicals', 'Fundamentals', 'Chart', 'Smart Money', 'News', 'Trade Plan', 'Risk', 'Backtest', 'Notes'];

function Focus({ ticker, scenario, setScenario }) {
  const [tab, setTab] = React.useState('Overview');
  const d = D;
  const sc = d.scenarios[scenario];

  return (
    <div style={{ flex: 1, minWidth: 0, background: C.bg, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {/* Header */}
      <div style={{ padding: '20px 32px 0', borderBottom: `1px solid ${C.border}` }}>
        {/* Top row */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14, gap: 16 }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 5, flexWrap: 'wrap' }}>
              <Label color={C.gold}>{d.sector}</Label>
              <VerdictBadge v={d.verdict} />
            </div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
              <span style={{ fontSize: 36, fontWeight: 900, color: C.text, fontFamily: mono, letterSpacing: '-0.03em', lineHeight: 1 }}>{ticker}</span>
              <span style={{ fontSize: 13, color: C.sub, fontStyle: 'italic', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 220 }}>{d.company}</span>
            </div>
          </div>
          <div style={{ textAlign: 'right', flexShrink: 0 }}>
            <div style={{ fontSize: 30, fontWeight: 900, color: C.text, fontFamily: mono, letterSpacing: '-0.02em', lineHeight: 1 }}>{money(d.price)}</div>
            <div style={{ fontSize: 12, fontFamily: mono, fontWeight: 700, marginTop: 5, color: d.changePct >= 0 ? C.bull : C.bear, whiteSpace: 'nowrap' }}>
              +${d.change.toFixed(2)} · {pct(d.changePct)}
            </div>
          </div>
        </div>

        {/* Scenario toggle */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
          <Label>Scenario:</Label>
          {['bull', 'base', 'bear'].map(id => {
            const colors = { bull: C.bull, base: C.gold, bear: C.bear };
            return <Pill key={id} label={id.toUpperCase()} active={scenario === id} color={colors[id]} onClick={() => setScenario(id)} />;
          })}
          <span style={{ fontSize: 11, color: C.sub, marginLeft: 8 }}>
            Target <span style={{ color: scenario === 'bear' ? C.bear : C.bull, fontFamily: mono, fontWeight: 700 }}>${sc.target}</span>
            <span style={{ color: C.muted }}> · </span>
            <span style={{ fontFamily: mono }}>{sc.probability}%</span>
          </span>
        </div>

        {/* Tab bar */}
        <div style={{ display: 'flex', gap: 0, overflowX: 'auto', scrollbarWidth: 'none' }}>
          {TABS.map(t => (
            <button key={t} onClick={() => setTab(t)} style={{
              padding: '8px 14px', fontSize: 11, fontWeight: tab === t ? 700 : 500,
              color: tab === t ? C.text : C.muted, background: 'transparent', border: 'none',
              borderBottom: `2px solid ${tab === t ? C.gold : 'transparent'}`,
              cursor: 'pointer', whiteSpace: 'nowrap', letterSpacing: '0.02em',
              transition: 'all 150ms', marginBottom: -1, flexShrink: 0,
            }}>{t}</button>
          ))}
        </div>
      </div>

      {/* Tab content */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '24px 32px' }} className="dashboard-scroll">
        {tab === 'Overview' && <OverviewTab d={d} sc={sc} scenario={scenario} />}
        {tab === 'Technicals' && <TechnicalsTab d={d} />}
        {tab === 'Fundamentals' && <FundamentalsTab d={d} />}
        {tab === 'Chart' && <ChartTab d={d} />}
        {tab === 'Smart Money' && <SmcTab d={d} />}
        {tab === 'News' && <NewsTab d={d} />}
        {tab === 'Trade Plan' && <PlanTab d={d} />}
        {tab === 'Risk' && <RiskTab d={d} />}
        {tab === 'Backtest' && <BacktestTab d={d} />}
        {tab === 'Notes' && <NotesTab d={d} />}
      </div>
    </div>
  );
}

// ── Overview ───────────────────────────────────────────────────
function OverviewTab({ d, sc, scenario }) {
  const scoreColor = (s) => s >= 75 ? C.bull : s >= 60 ? C.gold : s >= 45 ? C.warn : C.bear;
  return (
    <div>
      {/* Thesis */}
      <div style={{ padding: '18px 24px', background: C.s1, borderRadius: 6, border: `1px solid ${C.border}`, marginBottom: 24 }}>
        <Label color={C.gold}>Setup · {d.setup}</Label>
        <p style={{ fontSize: 15, color: C.text, lineHeight: 1.65, marginTop: 10, marginBottom: 0 }}>
          "{sc.thesis}"
        </p>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 14 }}>
          {sc.catalysts.map(c => (
            <span key={c} style={{ fontSize: 11, padding: '4px 10px', background: C.s3, border: `1px solid ${C.border}`, borderRadius: 100, color: C.sub }}>{c}</span>
          ))}
        </div>
      </div>

      {/* Score cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 14, marginBottom: 24 }}>
        {[
          ['COMPOSITE', d.scores.composite],
          ['TECHNICAL', d.scores.technical],
          ['FUNDAMENTAL', d.scores.fundamental],
          ['SMART MONEY', d.scores.smc],
          ['SENTIMENT', d.scores.sentiment],
        ].map(([l, s]) => {
          const c = scoreColor(s);
          return (
            <div key={l} style={{ padding: '16px', background: C.s1, border: `1px solid ${C.border}`, borderRadius: 6 }}>
              <Label>{l}</Label>
              <div style={{ fontSize: 36, fontWeight: 900, color: c, fontFamily: mono, lineHeight: 1, marginTop: 8 }}>{s}</div>
              <div style={{ height: 3, background: C.s3, borderRadius: 2, marginTop: 10 }}>
                <div style={{ width: `${s}%`, height: '100%', background: c, borderRadius: 2, transition: 'width 800ms cubic-bezier(0.4,0,0.2,1)' }} />
              </div>
            </div>
          );
        })}
      </div>

      {/* Key metrics grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14 }}>
        {[
          ['PRICE', money(d.price)],
          ['TODAY', pct(d.changePct), d.changePct >= 0 ? C.bull : C.bear],
          ['MKT CAP', d.marketCap],
          ['BETA', d.beta.toFixed(2)],
          ['RSI 14', d.metrics.rsi14.toFixed(1)],
          ['ADX 14', d.metrics.adx14.toFixed(1)],
          ['ATR 14', money(d.metrics.atr14)],
          ['VS SPY', `×${d.metrics.relStrength.toFixed(2)}`],
          ['EMA 21', money(d.metrics.ema21)],
          ['SMA 50', money(d.metrics.sma50)],
          ['SMA 200', money(d.metrics.sma200)],
          ['VWAP', money(d.metrics.vwap)],
        ].map(([l, v, col]) => (
          <div key={l} style={{ padding: '12px 14px', background: C.s1, border: `1px solid ${C.border}`, borderRadius: 5 }}>
            <Label>{l}</Label>
            <div style={{ fontSize: 16, fontWeight: 700, color: col || C.text, fontFamily: mono, marginTop: 5 }}>{v}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Technicals ─────────────────────────────────────────────────
function TechnicalsTab({ d }) {
  const m = d.metrics;
  const scoreColor = (s) => s >= 75 ? C.bull : s >= 60 ? C.gold : s >= 45 ? C.warn : C.bear;
  const rows = [
    ['RSI 14', m.rsi14.toFixed(1), m.rsi14 > 70 ? 'Overbought' : m.rsi14 < 30 ? 'Oversold' : 'Neutral range — momentum healthy', m.rsi14 > 60 ? C.bull : m.rsi14 < 40 ? C.bear : C.gold],
    ['MACD', m.macd.toFixed(2), `Signal ${m.macdSignal.toFixed(2)} — bullish crossover held`, C.bull],
    ['ADX 14', m.adx14.toFixed(1), m.adx14 > 25 ? 'Strong trend — directional bias valid' : 'Weak trend', m.adx14 > 25 ? C.bull : C.warn],
    ['ATR 14', `$${m.atr14.toFixed(2)}`, 'Daily range — calibrate stops accordingly', C.cyan],
    ['EMA 21', `$${m.ema21.toFixed(2)}`, 'Price above — trend intact', C.bull],
    ['SMA 20', `$${m.sma20.toFixed(2)}`, 'Price above — near-term support', C.bull],
    ['SMA 50', `$${m.sma50.toFixed(2)}`, 'Strong support below, $23 gap', C.bull],
    ['SMA 200', `$${m.sma200.toFixed(2)}`, 'Long-term uptrend confirmed', C.bull],
    ['VWAP', `$${m.vwap.toFixed(2)}`, 'Trading above — institutional buy zone', C.cyan],
    ['Rel Str', `×${m.relStrength.toFixed(2)}`, 'Outperforming SPY — sector leadership', C.gold],
  ];
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 24 }}>
        <div style={{ fontSize: 52, fontWeight: 900, color: scoreColor(d.scores.technical), fontFamily: mono, lineHeight: 1 }}>{d.scores.technical}</div>
        <div>
          <Label color={scoreColor(d.scores.technical)}>Technical Score</Label>
          <div style={{ fontSize: 13, color: C.sub, marginTop: 6, lineHeight: 1.5 }}>Trend intact above all key MAs. RSI in healthy range, MACD bullish crossover. ADX confirms directional strength.</div>
        </div>
      </div>
      <div style={{ border: `1px solid ${C.border}`, borderRadius: 6, overflow: 'hidden' }}>
        {rows.map(([indicator, value, note, color], i) => (
          <div key={indicator} style={{
            display: 'grid', gridTemplateColumns: '100px 100px 1fr',
            padding: '12px 16px', gap: 16, alignItems: 'center',
            background: i % 2 === 0 ? C.s1 : 'transparent',
            borderBottom: i < rows.length - 1 ? `1px solid ${C.div}` : 'none',
          }}>
            <Tip text={`${indicator}: ${note}`}>
              <span style={{ fontSize: 11, fontWeight: 700, fontFamily: mono, color: C.sub, cursor: 'help', borderBottom: `1px dotted ${C.muted}` }}>{indicator}</span>
            </Tip>
            <span style={{ fontSize: 15, fontWeight: 800, fontFamily: mono, color }}>{value}</span>
            <span style={{ fontSize: 11, color: C.muted }}>{note}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Fundamentals ───────────────────────────────────────────────
function FundamentalsTab({ d }) {
  const f = d.fundamentals;
  const scoreColor = (s) => s >= 75 ? C.bull : s >= 60 ? C.gold : s >= 45 ? C.warn : C.bear;
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 24 }}>
        <div style={{ fontSize: 52, fontWeight: 900, color: scoreColor(d.scores.fundamental), fontFamily: mono, lineHeight: 1 }}>{d.scores.fundamental}</div>
        <div>
          <Label color={scoreColor(d.scores.fundamental)}>Fundamental Score</Label>
          <div style={{ fontSize: 13, color: C.sub, marginTop: 6, lineHeight: 1.5 }}>Quality compounder at reasonable valuation. Revenue acceleration + margin expansion thesis intact.</div>
        </div>
      </div>

      {/* Valuation */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14, marginBottom: 24 }}>
        {[
          ['P/E TTM', f.pe.toFixed(1), 'vs sector 28.4', C.gold],
          ['Fwd P/E', f.forwardPe.toFixed(1), 'vs sector 22.1', C.bull],
          ['PEG Ratio', f.pegRatio.toFixed(2), '< 1.5 attractive', C.gold],
          ['P/S', f.priceToSales.toFixed(1), 'TTM revenue multiple', C.sub],
          ['P/B', f.priceToBook.toFixed(1), 'Asset-light premium', C.sub],
          ['EV/EBITDA', (f.pe * 0.82).toFixed(1), 'Enterprise value', C.sub],
        ].map(([l, v, h, c]) => (
          <div key={l} style={{ padding: '14px', background: C.s1, border: `1px solid ${C.border}`, borderRadius: 5 }}>
            <Tip text={`${l}: ${h}`}>
              <Label>{l}</Label>
            </Tip>
            <div style={{ fontSize: 24, fontWeight: 800, color: c, fontFamily: mono, marginTop: 8 }}>{v}</div>
            <div style={{ fontSize: 10, color: C.muted, marginTop: 4 }}>{h}</div>
          </div>
        ))}
      </div>

      {/* Earnings history */}
      <Label color={C.gold}>Earnings History · Last 4 Quarters</Label>
      <div style={{ marginTop: 12, border: `1px solid ${C.border}`, borderRadius: 6, overflow: 'hidden' }}>
        {d.fundamentals.earningsHistory.map((e, i) => (
          <div key={i} style={{
            display: 'grid', gridTemplateColumns: '100px repeat(4, 1fr)',
            padding: '12px 16px', gap: 12, alignItems: 'center',
            background: i % 2 === 0 ? C.s1 : 'transparent',
            borderBottom: i < d.fundamentals.earningsHistory.length - 1 ? `1px solid ${C.div}` : 'none',
          }}>
            <span style={{ fontSize: 11, fontFamily: mono, color: C.sub }}>{e.quarter}</span>
            <div>
              <div style={{ fontSize: 9, color: C.muted, letterSpacing: '0.1em' }}>EPS EST</div>
              <div style={{ fontSize: 13, fontFamily: mono, color: C.text }}>${e.epsEst.toFixed(2)}</div>
            </div>
            <div>
              <div style={{ fontSize: 9, color: C.muted, letterSpacing: '0.1em' }}>EPS ACT</div>
              <div style={{ fontSize: 13, fontFamily: mono, color: e.epsActual > e.epsEst ? C.bull : C.bear, fontWeight: 700 }}>${e.epsActual.toFixed(2)}</div>
            </div>
            <div>
              <div style={{ fontSize: 9, color: C.muted, letterSpacing: '0.1em' }}>SURPRISE</div>
              <div style={{ fontSize: 13, fontFamily: mono, color: e.surprise >= 0 ? C.bull : C.bear, fontWeight: 700 }}>
                {e.surprise >= 0 ? '+' : ''}{e.surprise.toFixed(1)}%
              </div>
            </div>
            <div>
              <div style={{ fontSize: 9, color: C.muted, letterSpacing: '0.1em' }}>REACTION</div>
              <div style={{ fontSize: 13, fontFamily: mono, color: e.priceReaction >= 0 ? C.bull : C.bear, fontWeight: 700 }}>
                {e.priceReaction >= 0 ? '+' : ''}{e.priceReaction.toFixed(1)}%
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Growth */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14, marginTop: 20 }}>
        {[
          ['Rev Growth YoY', `+${f.revenueGrowth}%`, C.bull],
          ['EPS Growth YoY', `+${f.epsGrowthYoY}%`, C.bull],
          ['Gross Margin', `${f.grossMargin}%`, C.gold],
          ['EBITDA Margin', `${f.ebitdaMargin}%`, C.gold],
          ['ROE', `${f.roe}%`, C.bull],
          ['Debt / Equity', f.debtToEquity.toFixed(2), C.sub],
        ].map(([l, v, c]) => (
          <div key={l} style={{ padding: '12px 14px', background: C.s1, border: `1px solid ${C.border}`, borderRadius: 5 }}>
            <Label>{l}</Label>
            <div style={{ fontSize: 20, fontWeight: 800, color: c, fontFamily: mono, marginTop: 6 }}>{v}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Chart tab ──────────────────────────────────────────────────
function ChartTab({ d }) {
  const [mode, setMode] = React.useState('candle');
  const theme = { bull: C.bull, bear: C.bear, grid: C.div, muted: C.muted, text: C.text, accent: C.cyan, line1: C.gold, line2: C.cyan };
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
        <Label color={C.gold}>Price Chart · 90 Days</Label>
        <div style={{ marginLeft: 16, display: 'flex', gap: 6 }}>
          <Pill label="CANDLES" active={mode === 'candle'} color={C.gold} onClick={() => setMode('candle')} />
          <Pill label="LINE" active={mode === 'line'} color={C.cyan} onClick={() => setMode('line')} />
        </div>
        <div style={{ marginLeft: 'auto', fontSize: 10, color: C.muted, fontFamily: mono }}>
          EMA21 <span style={{ color: C.gold }}>■</span> &nbsp; SMA20 <span style={{ color: C.cyan }}>■</span> &nbsp; Entry zone <span style={{ color: C.bull }}>■</span> &nbsp; Stop <span style={{ color: C.bear }}>■</span>
        </div>
      </div>
      <div style={{ background: C.s1, border: `1px solid ${C.border}`, borderRadius: 6, padding: '16px', overflowX: 'auto' }}>
        {mode === 'candle'
          ? <CandleChart candles={d.candles} plan={d.plan} width={720} height={380} theme={theme} />
          : <StylizedChart candles={d.candles} plan={d.plan} width={720} height={380} theme={theme} />
        }
      </div>
    </div>
  );
}

// ── Smart Money ────────────────────────────────────────────────
function SmcTab({ d }) {
  const smc = d.smc;
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 24 }}>
        <div style={{ fontSize: 52, fontWeight: 900, color: C.bull, fontFamily: mono, lineHeight: 1 }}>{d.scores.smc}</div>
        <div>
          <Label color={C.bull}>Smart Money Score</Label>
          <div style={{ fontSize: 13, color: C.sub, marginTop: 6, lineHeight: 1.5 }}>Strong institutional footprint. Bullish BOS confirmed, demand OB defending, untapped FVG below price.</div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        {/* Structure */}
        <div style={{ background: C.s1, border: `1px solid ${C.border}`, borderRadius: 6, padding: 18 }}>
          <Label color={C.gold}>Market Structure</Label>
          <div style={{ marginTop: 14 }}>
            {smc.marketStructure.map((ms, i) => (
              <div key={i} style={{ padding: '8px 0', borderBottom: `1px solid ${C.div}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: 11, color: C.sub }}>{ms.level}</span>
                <span style={{ fontSize: 13, fontFamily: mono, fontWeight: 700, color: ms.type === 'BOS' ? C.bull : ms.type === 'CHoCH' ? C.warn : C.cyan }}>${ms.price} · {ms.type}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Order blocks */}
        <div style={{ background: C.s1, border: `1px solid ${C.border}`, borderRadius: 6, padding: 18 }}>
          <Label color={C.gold}>Order Blocks</Label>
          <div style={{ marginTop: 14 }}>
            {smc.orderBlocks.map((ob, i) => (
              <div key={i} style={{ padding: '10px 12px', borderRadius: 4, marginBottom: 8, background: ob.type === 'demand' ? `${C.bull}10` : `${C.bear}10`, border: `1px solid ${ob.type === 'demand' ? C.bull + '30' : C.bear + '30'}` }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ fontSize: 10, fontWeight: 700, color: ob.type === 'demand' ? C.bull : C.bear, letterSpacing: '0.1em' }}>{ob.type.toUpperCase()}</span>
                  <span style={{ fontSize: 10, color: C.muted }}>{ob.timeframe}</span>
                </div>
                <div style={{ fontSize: 13, fontFamily: mono, color: C.text, marginTop: 4 }}>
                  ${ob.low} — ${ob.high}
                </div>
                <div style={{ fontSize: 10, color: C.muted, marginTop: 2 }}>{ob.status} · {ob.mitigation}</div>
              </div>
            ))}
          </div>
        </div>

        {/* FVGs */}
        <div style={{ background: C.s1, border: `1px solid ${C.border}`, borderRadius: 6, padding: 18 }}>
          <Label color={C.gold}>Fair Value Gaps</Label>
          <div style={{ marginTop: 14 }}>
            {smc.fairValueGaps.map((fg, i) => (
              <div key={i} style={{ padding: '8px 0', borderBottom: `1px solid ${C.div}`, display: 'flex', justifyContent: 'space-between' }}>
                <div>
                  <div style={{ fontSize: 13, fontFamily: mono, color: fg.type === 'bullish' ? C.bull : C.bear }}>${fg.low} — ${fg.high}</div>
                  <div style={{ fontSize: 10, color: C.muted }}>{fg.timeframe} · {fg.status}</div>
                </div>
                <span style={{ fontSize: 10, fontWeight: 700, color: fg.type === 'bullish' ? C.bull : C.bear }}>{fg.type.toUpperCase()}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Liquidity */}
        <div style={{ background: C.s1, border: `1px solid ${C.border}`, borderRadius: 6, padding: 18 }}>
          <Label color={C.gold}>Liquidity Pools</Label>
          <div style={{ marginTop: 14 }}>
            {smc.liquidity.map((lq, i) => (
              <div key={i} style={{ padding: '8px 0', borderBottom: `1px solid ${C.div}`, display: 'flex', justifyContent: 'space-between' }}>
                <div>
                  <div style={{ fontSize: 13, fontFamily: mono, color: lq.type === 'buy-side' ? C.bull : C.bear }}>${lq.level}</div>
                  <div style={{ fontSize: 10, color: C.muted }}>{lq.type} · {lq.status}</div>
                </div>
                <span style={{ fontSize: 10, color: C.muted }}>{lq.timeframe}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── News ───────────────────────────────────────────────────────
function NewsTab({ d }) {
  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <Label color={C.gold}>News & Sentiment · Filtered to {d.ticker}</Label>
      </div>
      {d.news.map((n, i) => (
        <div key={i} style={{
          padding: '16px 18px', marginBottom: 10,
          background: C.s1, border: `1px solid ${C.border}`, borderRadius: 6,
          display: 'flex', gap: 16, alignItems: 'flex-start',
          borderLeft: `3px solid ${n.sentiment === 'bullish' ? C.bull : n.sentiment === 'bearish' ? C.bear : C.muted}`,
        }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 14, color: C.text, lineHeight: 1.45, fontWeight: 500 }}>{n.title}</div>
            <div style={{ display: 'flex', gap: 12, marginTop: 8 }}>
              <span style={{ fontSize: 10, color: C.muted, fontFamily: mono, letterSpacing: '0.08em' }}>{n.source.toUpperCase()}</span>
              <span style={{ fontSize: 10, color: C.muted }}>{n.time}</span>
              <span style={{ fontSize: 10, fontWeight: 700, color: n.sentiment === 'bullish' ? C.bull : n.sentiment === 'bearish' ? C.bear : C.muted, letterSpacing: '0.08em' }}>{n.sentiment.toUpperCase()}</span>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Trade Plan ─────────────────────────────────────────────────
function PlanTab({ d }) {
  const p = d.plan;
  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        {/* Price ladder */}
        <div>
          <Label color={C.gold}>Price Ladder</Label>
          <div style={{ marginTop: 14 }}>
            {[
              ['T3', p.target3, '+5.99R', C.bull],
              ['T2', p.target2, '+3.88R', C.bull],
              ['T1', p.target1, '+1.97R', C.bull],
              ['NOW', d.price, '', C.text],
              ['ENTRY', p.entry, '', C.cyan],
              ['STOP', p.stop, '−1.0R', C.bear],
            ].map(([l, v, r, c]) => (
              <div key={l} style={{
                padding: '12px 16px', marginBottom: 6, borderRadius: 4,
                background: l === 'NOW' ? C.s3 : C.s1,
                border: `1px solid ${l === 'NOW' ? C.text + '20' : C.border}`,
                borderLeft: `3px solid ${c}`,
                display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
              }}>
                <span style={{ fontSize: 10, fontWeight: 700, color: c, fontFamily: mono, letterSpacing: '0.1em', width: 50 }}>{l}</span>
                <span style={{ fontSize: 20, fontWeight: 900, color: C.text, fontFamily: mono }}>${v}</span>
                {r ? <span style={{ fontSize: 12, fontWeight: 700, color: c, fontFamily: mono }}>{r}</span> : <span style={{ width: 48 }} />}
              </div>
            ))}
          </div>
        </div>

        {/* Sizing + details */}
        <div>
          <Label color={C.gold}>Execution Details</Label>
          <div style={{ marginTop: 14 }}>
            {[
              ['Shares', p.sharesSuggested.toString()],
              ['Notional', `$${p.notional.toLocaleString()}`],
              ['Risk amt', `$${(p.riskPctAccount * 250000 / 100).toFixed(0)}`],
              ['% of book', `${p.riskPctAccount.toFixed(2)}%`],
              ['Risk:Reward', `${p.riskReward.toFixed(2)}:1`],
              ['Hold target', `${p.holdDays} days`],
              ['Order type', p.orderType],
              ['Entry zone', `$${p.entryZone[0]}–$${p.entryZone[1]}`],
            ].map(([l, v]) => (
              <div key={l} style={{ display: 'flex', justifyContent: 'space-between', padding: '9px 0', borderBottom: `1px solid ${C.div}` }}>
                <span style={{ fontSize: 11, color: C.muted }}>{l}</span>
                <span style={{ fontSize: 13, fontWeight: 700, fontFamily: mono, color: C.text }}>{v}</span>
              </div>
            ))}
          </div>

          <div style={{ marginTop: 16, padding: 14, background: `${C.bear}08`, borderLeft: `3px solid ${C.bear}`, borderRadius: 4 }}>
            <Label color={C.bear}>Invalidation</Label>
            <p style={{ fontSize: 12, color: C.sub, lineHeight: 1.5, marginTop: 6, marginBottom: 0 }}>{p.invalidation}</p>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Risk & Greeks ──────────────────────────────────────────────
function RiskTab({ d }) {
  const r = d.risk;
  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14, marginBottom: 24 }}>
        {[
          ['Portfolio Heat', `${r.portfolioHeat}%`, C.warn, 'Current open-risk as % of account'],
          ['Heat After', `${(r.portfolioHeat + 0.75).toFixed(2)}%`, C.warn, 'If TICKR added at suggested size'],
          ['Max Heat', '6.00%', C.muted, 'Hard cap — do not exceed'],
          ['VaR 1-day 95%', `$${r.var95.toLocaleString()}`, C.bear, 'Expected max 1-day loss, 95% confidence'],
          ['Avg Corr', r.avgCorrelation.toFixed(2), C.sub, 'Avg correlation to existing book'],
          ['Largest Corr', '0.71 vs RTX', C.warn, 'Highest correlated existing position'],
        ].map(([l, v, c, h]) => (
          <div key={l} style={{ padding: 16, background: C.s1, border: `1px solid ${C.border}`, borderRadius: 6 }}>
            <Tip text={h}><Label>{l}</Label></Tip>
            <div style={{ fontSize: 22, fontWeight: 800, color: c, fontFamily: mono, marginTop: 8 }}>{v}</div>
            <div style={{ fontSize: 10, color: C.muted, marginTop: 4 }}>{h}</div>
          </div>
        ))}
      </div>

      <Label color={C.gold}>Correlation Matrix · Open Positions</Label>
      <div style={{ marginTop: 14, border: `1px solid ${C.border}`, borderRadius: 6, overflow: 'hidden' }}>
        {r.correlations.map((row, i) => (
          <div key={row.ticker} style={{ display: 'grid', gridTemplateColumns: '80px 1fr 80px', padding: '11px 16px', background: i % 2 === 0 ? C.s1 : 'transparent', borderBottom: `1px solid ${C.div}` }}>
            <span style={{ fontFamily: mono, fontWeight: 700, color: C.text, fontSize: 12 }}>{row.ticker}</span>
            <div style={{ display: 'flex', alignItems: 'center' }}>
              <div style={{ flex: 1, height: 4, background: C.s3, borderRadius: 2 }}>
                <div style={{ width: `${Math.abs(row.correlation) * 100}%`, height: '100%', background: Math.abs(row.correlation) > 0.6 ? C.warn : C.cyan, borderRadius: 2 }} />
              </div>
            </div>
            <span style={{ textAlign: 'right', fontFamily: mono, fontSize: 13, fontWeight: 700, color: Math.abs(row.correlation) > 0.6 ? C.warn : C.sub }}>{row.correlation.toFixed(2)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Backtest ───────────────────────────────────────────────────
function BacktestTab({ d }) {
  const bt = d.backtest;
  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, marginBottom: 24 }}>
        {[
          ['Win Rate', `${bt.winRate}%`, bt.winRate >= 60 ? C.bull : C.warn],
          ['Expectancy', `+${bt.expectancy}R`, C.bull],
          ['Profit Factor', bt.profitFactor.toFixed(2), C.bull],
          ['Sharpe Ratio', bt.sharpeRatio.toFixed(2), C.gold],
          ['Samples', bt.totalTrades.toString(), C.text],
          ['Avg Hold', `${bt.avgHoldDays}d`, C.sub],
          ['Avg Win', `+${bt.avgWinR}R`, C.bull],
          ['Avg Loss', `−${bt.avgLossR}R`, C.bear],
        ].map(([l, v, c]) => (
          <div key={l} style={{ padding: '14px', background: C.s1, border: `1px solid ${C.border}`, borderRadius: 5 }}>
            <Label>{l}</Label>
            <div style={{ fontSize: 26, fontWeight: 900, color: c, fontFamily: mono, marginTop: 8 }}>{v}</div>
          </div>
        ))}
      </div>

      <Label color={C.gold}>Monthly Returns · Last 12 Months</Label>
      <div style={{ marginTop: 14, display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 10 }}>
        {bt.monthlyReturns.map((m, i) => (
          <div key={i} style={{ padding: '12px', background: m.return >= 0 ? `${C.bull}12` : `${C.bear}12`, border: `1px solid ${m.return >= 0 ? C.bull + '30' : C.bear + '30'}`, borderRadius: 4, textAlign: 'center' }}>
            <div style={{ fontSize: 9, color: C.muted, letterSpacing: '0.1em' }}>{m.month}</div>
            <div style={{ fontSize: 18, fontWeight: 800, color: m.return >= 0 ? C.bull : C.bear, fontFamily: mono, marginTop: 4 }}>
              {m.return >= 0 ? '+' : ''}{m.return}%
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Notes ──────────────────────────────────────────────────────
function NotesTab({ d }) {
  const key = `notes_${d.ticker}`;
  const [entries, setEntries] = React.useState(() => {
    try { return JSON.parse(localStorage.getItem(key) || '[]'); } catch { return []; }
  });
  const [draft, setDraft] = React.useState('');

  const save = () => {
    if (!draft.trim()) return;
    const next = [{ ts: new Date().toISOString(), text: draft.trim() }, ...entries];
    setEntries(next);
    localStorage.setItem(key, JSON.stringify(next));
    setDraft('');
  };

  return (
    <div>
      <Label color={C.gold}>Trade Journal · {d.ticker}</Label>
      <div style={{ marginTop: 14 }}>
        <textarea value={draft} onChange={e => setDraft(e.target.value)}
          placeholder="Why this trade? Why this size? What must happen for you to be wrong?"
          style={{
            width: '100%', minHeight: 90, padding: '12px', fontSize: 13, lineHeight: 1.6,
            fontFamily: sans, background: C.s1, color: C.text,
            border: `1px solid ${C.border}`, borderRadius: 5, resize: 'vertical', outline: 'none',
            boxSizing: 'border-box',
          }}
          onKeyDown={e => { if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') save(); }}
        />
        <button onClick={save} style={{
          marginTop: 8, padding: '9px 18px', fontSize: 11, fontWeight: 800, letterSpacing: '0.1em',
          background: C.gold, color: C.bg, border: 'none', borderRadius: 4, cursor: 'pointer', fontFamily: mono,
        }}>SAVE NOTE ⌘↵</button>
      </div>
      <div style={{ marginTop: 24 }}>
        {entries.map((e, i) => (
          <div key={i} style={{ padding: '14px 16px', marginBottom: 10, background: C.s1, border: `1px solid ${C.border}`, borderRadius: 5 }}>
            <div style={{ fontSize: 9, color: C.muted, fontFamily: mono, letterSpacing: '0.1em', marginBottom: 8 }}>
              {new Date(e.ts).toLocaleString()}
            </div>
            <div style={{ fontSize: 13, color: C.text, lineHeight: 1.6 }}>{e.text}</div>
          </div>
        ))}
        {entries.length === 0 && <div style={{ fontSize: 13, color: C.muted, fontStyle: 'italic' }}>No notes yet. Add your first trade journal entry above.</div>}
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────
// RIGHT: PLAN — always-visible execution panel
// ──────────────────────────────────────────────────────────────────
function Plan() {
  const p = D.plan;
  const levels = [
    { l: 'T3', v: p.target3, r: '+5.99R', c: C.bull },
    { l: 'T2', v: p.target2, r: '+3.88R', c: C.bull },
    { l: 'T1', v: p.target1, r: '+1.97R', c: C.bull },
    { l: 'NOW', v: D.price, r: '', c: C.text },
    { l: 'ENTRY', v: p.entry, r: '', c: C.cyan },
    { l: 'STOP', v: p.stop, r: '−1R', c: C.bear },
  ];

  return (
    <div style={{
      width: 300, flexShrink: 0,
      background: C.s1, borderLeft: `1px solid ${C.border}`,
      display: 'flex', flexDirection: 'column', overflow: 'hidden',
    }}>
      <div style={{ padding: '20px 20px 14px', borderBottom: `1px solid ${C.border}` }}>
        <Label color={C.gold}>Execution Plan</Label>
        <div style={{ fontSize: 14, fontWeight: 700, color: C.text, marginTop: 6 }}>Long · {p.holdDays}-day horizon</div>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px' }} className="dashboard-scroll">
        {/* Levels */}
        <div style={{ marginBottom: 18 }}>
          {levels.map(({ l, v, r, c }) => (
            <div key={l} style={{
              padding: '10px 12px', marginBottom: 5, borderRadius: 4,
              background: l === 'NOW' ? C.s3 : C.s2,
              border: `1px solid ${l === 'NOW' ? C.text + '20' : C.border}`,
              borderLeft: `3px solid ${c}`,
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            }}>
              <span style={{ fontSize: 9, fontWeight: 800, color: c, fontFamily: mono, letterSpacing: '0.14em', width: 44 }}>{l}</span>
              <span style={{ fontSize: 17, fontWeight: 800, color: C.text, fontFamily: mono }}>${v}</span>
              <span style={{ fontSize: 11, fontWeight: 700, color: c, fontFamily: mono, width: 44, textAlign: 'right' }}>{r}</span>
            </div>
          ))}
        </div>

        {/* Sizing */}
        <div style={{ padding: 14, background: `${C.gold}10`, border: `1px solid ${C.gold}30`, borderRadius: 5, marginBottom: 16 }}>
          <Label color={C.gold}>Position Size</Label>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginTop: 8 }}>
            <span style={{ fontSize: 32, fontWeight: 900, color: C.gold, fontFamily: mono, lineHeight: 1 }}>{p.sharesSuggested}</span>
            <span style={{ fontSize: 12, color: C.muted }}>shares</span>
          </div>
          <div style={{ fontSize: 10, color: C.sub, fontFamily: mono, marginTop: 6 }}>
            ${p.notional.toLocaleString()} · 0.75% risk
          </div>
          <button style={{
            width: '100%', marginTop: 12, padding: '10px 0',
            background: C.gold, color: C.bg,
            border: 'none', borderRadius: 4, fontSize: 11, fontWeight: 900,
            letterSpacing: '0.12em', cursor: 'pointer', fontFamily: mono,
          }}>STAGE ORDER →</button>
        </div>

        {/* Edge */}
        <div style={{ marginBottom: 16 }}>
          <Label>Historical Edge · 142 Samples</Label>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 10 }}>
            {[
              ['WIN RATE', '64.8%', C.bull],
              ['EXPECT.', '+0.78R', C.bull],
              ['PF', '1.84', C.gold],
              ['SHARPE', '1.62', C.gold],
            ].map(([l, v, c]) => (
              <div key={l} style={{ padding: '10px', background: C.s2, border: `1px solid ${C.border}`, borderRadius: 4 }}>
                <div style={{ fontSize: 8, color: C.muted, letterSpacing: '0.14em', fontFamily: mono }}>{l}</div>
                <div style={{ fontSize: 18, fontWeight: 800, color: c, fontFamily: mono, marginTop: 4 }}>{v}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Heat */}
        <div style={{ marginBottom: 16 }}>
          <Label>Book Heat After Entry</Label>
          <div style={{ marginTop: 10 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, fontFamily: mono, color: C.sub, marginBottom: 5 }}>
              <span>3.20% → 3.95%</span>
              <span style={{ color: C.muted }}>cap 6.0%</span>
            </div>
            <div style={{ height: 6, background: C.s3, borderRadius: 3, overflow: 'hidden' }}>
              <div style={{ width: '65.8%', height: '100%', background: `linear-gradient(90deg, ${C.bull}, ${C.gold})` }} />
            </div>
          </div>
        </div>

        {/* Corr warning */}
        <div style={{ padding: '10px 12px', background: `${C.warn}08`, border: `1px solid ${C.warn}30`, borderRadius: 4, fontSize: 11, color: C.sub, lineHeight: 1.5 }}>
          <span style={{ color: C.warn, fontWeight: 700 }}>⚠ Corr 0.71 vs RTX</span><br />
          Consider trimming RTX 25% before entry.
        </div>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────
// COMMAND BAR — bottom strip
// ──────────────────────────────────────────────────────────────────
function CommandBar({ onSelect, onPanel }) {
  const [q, setQ] = React.useState('');
  const matches = q.length > 0 ? SCAN.filter(r =>
    r.ticker.toLowerCase().startsWith(q.toLowerCase()) ||
    r.name.toLowerCase().includes(q.toLowerCase())
  ).slice(0, 6) : [];

  return (
    <div style={{
      height: 48, background: C.s1, borderTop: `1px solid ${C.border}`,
      display: 'flex', alignItems: 'center', padding: '0 20px', gap: 16, position: 'relative', flexShrink: 0,
    }}>
      {/* Search */}
      <div style={{ position: 'relative', width: 380 }}>
        <span style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', fontSize: 10, color: C.muted, fontFamily: mono }}>⌘K</span>
        <input value={q} onChange={e => setQ(e.target.value)} onBlur={() => setTimeout(() => setQ(''), 200)}
          placeholder="Jump to ticker..."
          style={{ width: '100%', padding: '7px 10px 7px 40px', fontSize: 12, background: C.s2, color: C.text, border: `1px solid ${C.border}`, borderRadius: 4, outline: 'none', boxSizing: 'border-box' }} />
        {matches.length > 0 && (
          <div style={{ position: 'absolute', bottom: 'calc(100% + 4px)', left: 0, right: 0, background: C.s2, border: `1px solid ${C.border}`, borderRadius: 4, boxShadow: '0 -12px 32px rgba(0,0,0,.5)', zIndex: 50 }}>
            {matches.map(r => (
              <div key={r.ticker} onMouseDown={() => { onSelect(r.ticker); setQ(''); }}
                style={{ padding: '9px 12px', cursor: 'pointer', display: 'flex', justifyContent: 'space-between', borderBottom: `1px solid ${C.div}` }}
                onMouseEnter={e => e.currentTarget.style.background = C.s3}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
                <span style={{ fontFamily: mono, fontWeight: 700, color: C.text, fontSize: 12 }}>{r.ticker}</span>
                <span style={{ fontSize: 11, color: C.muted }}>{r.verdict} · {r.score}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Nav pills */}
      {['Scanner', 'Portfolio', 'Themes', 'Performance', 'Journal'].map(l => (
        <button key={l} onClick={() => onPanel(l.toLowerCase())} style={{
          padding: '6px 12px', fontSize: 10, fontWeight: 600, letterSpacing: '0.06em',
          color: C.muted, background: 'transparent', border: `1px solid ${C.border}`, borderRadius: 3, cursor: 'pointer',
        }}>{l}</button>
      ))}

      {/* Live status */}
      <div style={{ marginLeft: 'auto', display: 'flex', gap: 18, fontSize: 11, fontFamily: mono, color: C.muted, alignItems: 'center' }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <span style={{ width: 6, height: 6, borderRadius: '50%', background: C.bull }} className="pulse-dot" />
          LIVE
        </span>
        <span>DAY P&amp;L <span style={{ color: C.bull }}>+$2,847</span></span>
        <span>HEAT <span style={{ color: C.warn }}>3.2%</span></span>
        <span>SPY <span style={{ color: C.bull }}>+0.84%</span></span>
        <span>VIX <span style={{ color: C.bull }}>14.8</span></span>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────
// SCANNER OVERLAY
// ──────────────────────────────────────────────────────────────────
function ScannerOverlay({ onSelect, onClose }) {
  const [q, setQ] = React.useState('');
  const [sort, setSort] = React.useState('score');
  const filtered = q ? SCAN.filter(r => r.ticker.toLowerCase().includes(q.toLowerCase()) || r.name.toLowerCase().includes(q.toLowerCase()) || r.sector.toLowerCase().includes(q.toLowerCase())) : SCAN;
  const sorted = [...filtered].sort((a, b) => sort === 'score' ? b.score - a.score : b.changePct - a.changePct);

  return (
    <div style={{ position: 'absolute', inset: 0, background: 'rgba(8,12,20,0.88)', backdropFilter: 'blur(8px)', zIndex: 100, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 32 }}
      onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{ width: '100%', maxWidth: 1100, height: '100%', maxHeight: 720, background: C.s1, border: `1px solid ${C.border}`, borderRadius: 8, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Header */}
        <div style={{ padding: '16px 24px', borderBottom: `1px solid ${C.border}`, display: 'flex', alignItems: 'center', gap: 14 }}>
          <Label color={C.gold}>Universe Scanner · {filtered.length} stocks</Label>
          <input value={q} onChange={e => setQ(e.target.value)} placeholder="Filter tickers, names, sectors..." autoFocus
            style={{ flex: 1, padding: '7px 12px', fontSize: 12, background: C.s2, color: C.text, border: `1px solid ${C.border}`, borderRadius: 4, outline: 'none' }} />
          <div style={{ display: 'flex', gap: 6 }}>
            <Pill label="SCORE" active={sort === 'score'} color={C.gold} onClick={() => setSort('score')} />
            <Pill label="CHG%" active={sort === 'chg'} color={C.cyan} onClick={() => setSort('chg')} />
          </div>
          <button onClick={onClose} style={{ padding: '6px 14px', fontSize: 10, fontWeight: 700, fontFamily: mono, letterSpacing: '0.1em', color: C.muted, background: 'transparent', border: `1px solid ${C.border}`, borderRadius: 3, cursor: 'pointer' }}>ESC ✕</button>
        </div>

        {/* Table */}
        <div style={{ flex: 1, overflowY: 'auto' }} className="dashboard-scroll">
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead style={{ position: 'sticky', top: 0, background: C.s1 }}>
              <tr>
                {['TICKER', 'NAME', 'SECTOR', 'PRICE', 'CHG%', 'SCORE', 'VERDICT', 'SETUP'].map(h => (
                  <th key={h} style={{ padding: '12px 16px', fontSize: 9, fontWeight: 700, color: C.muted, textAlign: 'left', letterSpacing: '0.15em', fontFamily: mono, borderBottom: `1px solid ${C.border}` }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sorted.map((r, i) => (
                <tr key={r.ticker} onClick={() => { onSelect(r.ticker); onClose(); }}
                  style={{ borderBottom: `1px solid ${C.div}`, cursor: 'pointer' }}
                  onMouseEnter={e => e.currentTarget.style.background = C.s2}
                  onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
                  <td style={{ padding: '11px 16px', fontFamily: mono, fontWeight: 700, color: C.text, fontSize: 12 }}>{r.ticker}</td>
                  <td style={{ padding: '11px 16px', fontSize: 11, color: C.sub }}>{r.name}</td>
                  <td style={{ padding: '11px 16px', fontSize: 11, color: C.muted }}>{r.sector}</td>
                  <td style={{ padding: '11px 16px', fontFamily: mono, fontSize: 12, color: C.text }}>${r.price.toFixed(2)}</td>
                  <td style={{ padding: '11px 16px', fontFamily: mono, fontSize: 12, fontWeight: 700, color: r.changePct >= 0 ? C.bull : C.bear }}>{pct(r.changePct)}</td>
                  <td style={{ padding: '11px 16px', fontFamily: mono, fontSize: 14, fontWeight: 900, color: C.gold }}>{r.score}</td>
                  <td style={{ padding: '11px 16px', fontSize: 10, fontWeight: 800, letterSpacing: '0.1em', fontFamily: mono, color: r.verdict === 'BUY' ? C.bull : r.verdict === 'AVOID' ? C.bear : C.warn }}>{r.verdict}</td>
                  <td style={{ padding: '11px 16px', fontSize: 11, color: C.muted }}>{r.setup}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────
// ROOT
// ──────────────────────────────────────────────────────────────────
function App() {
  const [focused, setFocused] = React.useState('TICKR');
  const [scenario, setScenario] = React.useState('base');
  const [panel, setPanel] = React.useState(null);

  React.useEffect(() => {
    const h = e => {
      if (e.key === 'Escape') setPanel(null);
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, []);

  return (
    <div style={{ width: '100vw', height: '100vh', display: 'flex', flexDirection: 'column', overflow: 'hidden', background: C.bg, color: C.text, fontFamily: sans, position: 'relative' }}>
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden', minHeight: 0 }}>
        <Pulse focused={focused} onSelect={setFocused} />
        <Focus ticker={focused} scenario={scenario} setScenario={setScenario} />
        <Plan />
      </div>
      <CommandBar onSelect={setFocused} onPanel={setPanel} />

      {panel === 'scanner' && <ScannerOverlay onSelect={setFocused} onClose={() => setPanel(null)} />}
      {panel && panel !== 'scanner' && (
        <div style={{ position: 'absolute', inset: 0, background: 'rgba(8,12,20,0.88)', backdropFilter: 'blur(8px)', zIndex: 100, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={() => setPanel(null)}>
          <div onClick={e => e.stopPropagation()} style={{ padding: 40, background: C.s1, border: `1px solid ${C.border}`, borderRadius: 8, maxWidth: 600, width: '100%' }}>
            <Label color={C.gold}>{panel.toUpperCase()}</Label>
            <div style={{ fontSize: 22, fontWeight: 700, color: C.text, marginTop: 10, marginBottom: 10 }}>{panel.charAt(0).toUpperCase() + panel.slice(1)}</div>
            <p style={{ fontSize: 13, color: C.sub, lineHeight: 1.6 }}>This panel slides in over the cockpit. The core three-column layout remains the home base — other tools are focused, dismissable surfaces so attention stays centred.</p>
            <button onClick={() => setPanel(null)} style={{ marginTop: 16, padding: '9px 18px', fontSize: 11, fontWeight: 800, fontFamily: mono, background: C.gold, color: C.bg, border: 'none', borderRadius: 4, cursor: 'pointer', letterSpacing: '0.1em' }}>BACK TO COCKPIT</button>
          </div>
        </div>
      )}
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);

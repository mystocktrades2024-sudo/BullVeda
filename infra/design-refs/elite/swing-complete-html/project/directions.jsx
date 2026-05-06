// All three design directions wrapped as artboards

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'technicals', label: 'Technicals' },
  { id: 'fundamentals', label: 'Fundamentals' },
  { id: 'chart', label: 'Chart' },
  { id: 'smc', label: 'Smart Money' },
  { id: 'news', label: 'News & Sentiment' },
  { id: 'plan', label: 'Trade Plan' },
  { id: 'risk', label: 'Risk & Greeks' },
  { id: 'backtest', label: 'Backtest' },
  { id: 'notes', label: 'Notes' },
];

function renderTab(id, theme, ctx) {
  switch (id) {
    case 'overview': return <OverviewTab theme={theme} scenario={ctx.scenario} />;
    case 'technicals': return <TechnicalsTab theme={theme} />;
    case 'fundamentals': return <FundamentalsTab theme={theme} />;
    case 'chart': return <ChartTab theme={theme} chartStyle={ctx.chartStyle} setChartStyle={ctx.setChartStyle} scenario={ctx.scenario} />;
    case 'smc': return <SMCTab theme={theme} />;
    case 'news': return <NewsTab theme={theme} />;
    case 'plan': return <PlanTab theme={theme} />;
    case 'risk': return <RiskTab theme={theme} />;
    case 'backtest': return <BacktestTab theme={theme} />;
    case 'notes': return <NotesTab theme={theme} />;
    default: return null;
  }
}

/* ──────────────────────────────────────────
   Animated tab bar — shared logic, different visuals per direction
   ────────────────────────────────────────── */
function TabBar({ active, setActive, theme, variant = 'underline' }) {
  const refs = React.useRef({});
  const [indicator, setIndicator] = React.useState({ left: 0, width: 0 });
  React.useEffect(() => {
    const el = refs.current[active];
    if (el) {
      setIndicator({ left: el.offsetLeft, width: el.offsetWidth });
    }
  }, [active]);

  if (variant === 'pill') {
    return (
      <div style={{ display: 'flex', gap: 4, padding: 4, background: theme.surface2, border: `1px solid ${theme.border}`, borderRadius: 8, position: 'relative', overflow: 'auto' }}>
        {TABS.map(t => (
          <button key={t.id} ref={el => refs.current[t.id] = el} onClick={() => setActive(t.id)}
            style={{
              padding: '8px 14px', fontSize: 13, fontWeight: 600, letterSpacing: '0.01em',
              background: active === t.id ? theme.surface3 : 'transparent',
              color: active === t.id ? theme.text : theme.muted,
              border: 'none', borderRadius: 6, whiteSpace: 'nowrap', transition: 'color 200ms, background 200ms',
            }}>{t.label}</button>
        ))}
      </div>
    );
  }

  if (variant === 'rail') {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        {TABS.map(t => (
          <button key={t.id} onClick={() => setActive(t.id)}
            style={{
              padding: '11px 14px', fontSize: 13, fontWeight: 500, textAlign: 'left',
              background: active === t.id ? theme.accent + '15' : 'transparent',
              color: active === t.id ? theme.accent : theme.subtext,
              border: 'none',
              borderLeft: `2px solid ${active === t.id ? theme.accent : 'transparent'}`,
              transition: 'all 200ms',
            }}>{t.label}</button>
        ))}
      </div>
    );
  }

  // underline
  return (
    <div style={{ display: 'flex', gap: 0, borderBottom: `1px solid ${theme.border}`, position: 'relative', overflowX: 'auto' }}>
      {TABS.map(t => (
        <button key={t.id} ref={el => refs.current[t.id] = el} onClick={() => setActive(t.id)}
          style={{
            padding: '14px 18px', fontSize: 13, fontWeight: 600, letterSpacing: '0.01em',
            background: 'transparent',
            color: active === t.id ? theme.text : theme.muted,
            border: 'none', whiteSpace: 'nowrap', transition: 'color 200ms',
          }}>{t.label}</button>
      ))}
      <div className="tab-indicator" style={{
        position: 'absolute', bottom: -1, height: 2, background: theme.accent,
        left: indicator.left, width: indicator.width,
      }} />
    </div>
  );
}

/* ──────────────────────────────────────────
   ScenarioToggle — bull/base/bear
   ────────────────────────────────────────── */
function ScenarioToggle({ scenario, setScenario, theme }) {
  return (
    <div style={{ display: 'inline-flex', background: theme.surface2, border: `1px solid ${theme.border}`, borderRadius: 6, padding: 3 }}>
      {[
        { id: 'bear', label: 'BEAR', color: theme.bear },
        { id: 'base', label: 'BASE', color: theme.accent },
        { id: 'bull', label: 'BULL', color: theme.bull },
      ].map(s => (
        <button key={s.id} onClick={() => setScenario(s.id)}
          style={{
            padding: '6px 14px', fontSize: 11, fontWeight: 700, letterSpacing: '0.08em',
            background: scenario === s.id ? s.color + '20' : 'transparent',
            color: scenario === s.id ? s.color : theme.muted,
            border: 'none', borderRadius: 4, transition: 'all 200ms',
          }}>{s.label}</button>
      ))}
    </div>
  );
}

/* ──────────────────────────────────────────
   Header — ticker, price, change
   ────────────────────────────────────────── */
function TickerHeader({ theme }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 24 }}>
      <div>
        <div style={{ fontSize: 11, color: theme.muted, fontWeight: 600, letterSpacing: '0.12em', marginBottom: 4 }}>
          {D.sector.toUpperCase()}
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
          <span style={{ fontSize: 28, fontWeight: 800, color: theme.text, letterSpacing: '-0.02em', fontFamily: 'JetBrains Mono, monospace' }}>{D.ticker}</span>
          <span style={{ fontSize: 14, color: theme.subtext, fontWeight: 500 }}>{D.company}</span>
        </div>
      </div>
      <div style={{ width: 1, height: 40, background: theme.divider }} />
      <div>
        <div style={{ fontSize: 11, color: theme.muted, fontWeight: 600, letterSpacing: '0.12em', marginBottom: 4 }}>LAST · {D.asOf}</div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
          <span style={{ fontSize: 28, fontWeight: 800, color: theme.text, fontFamily: 'JetBrains Mono, monospace', letterSpacing: '-0.02em' }}>${D.price}</span>
          <span style={{ fontSize: 14, color: theme.bull, fontWeight: 700, fontFamily: 'JetBrains Mono, monospace' }}>+${D.change} ({pct(D.changePct)})</span>
        </div>
      </div>
    </div>
  );
}

/* ──────────────────────────────────────────
   DIRECTION A — Hedge Fund Classic
   Deep navy, restrained accents, generous whitespace, underline tabs
   ────────────────────────────────────────── */
const themeA = {
  surface: '#0a1220',
  surface2: '#101a2c',
  surface3: '#1a2540',
  border: 'rgba(148, 163, 184, 0.12)',
  divider: 'rgba(148, 163, 184, 0.08)',
  text: '#e6edf7',
  subtext: '#b8c3d6',
  muted: '#7a8aa6',
  accent: '#7cc4ff',
  accent2: '#c4a8ff',
  bull: '#5dd99c',
  bear: '#f87171',
  line1: '#7cc4ff',
  line2: '#c4a8ff',
  grid: 'rgba(148, 163, 184, 0.08)',
  chip: 'rgba(124, 196, 255, 0.08)',
  radius: 6,
};

function DirectionA() {
  const [active, setActive] = React.useState('overview');
  const [scenario, setScenario] = React.useState('base');
  const [chartStyle, setChartStyle] = React.useState('candle');
  return (
    <div style={{ width: '100%', height: '100%', background: themeA.surface, color: themeA.text, fontFamily: 'Inter, system-ui, sans-serif', display: 'flex', flexDirection: 'column' }}>
      {/* Top bar */}
      <div style={{ padding: '20px 32px', borderBottom: `1px solid ${themeA.border}`, display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: themeA.surface }}>
        <TickerHeader theme={themeA} />
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <div style={{ display: 'flex', gap: 16 }}>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: 10, color: themeA.muted, letterSpacing: '0.1em', fontWeight: 600 }}>MKT CAP</div>
              <div style={{ fontSize: 13, fontFamily: 'JetBrains Mono, monospace', color: themeA.text, fontWeight: 600 }}>{D.marketCap}</div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: 10, color: themeA.muted, letterSpacing: '0.1em', fontWeight: 600 }}>AVG VOL</div>
              <div style={{ fontSize: 13, fontFamily: 'JetBrains Mono, monospace', color: themeA.text, fontWeight: 600 }}>{D.avgVol}</div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: 10, color: themeA.muted, letterSpacing: '0.1em', fontWeight: 600 }}>BETA</div>
              <div style={{ fontSize: 13, fontFamily: 'JetBrains Mono, monospace', color: themeA.text, fontWeight: 600 }}>{D.beta}</div>
            </div>
          </div>
          <ScenarioToggle scenario={scenario} setScenario={setScenario} theme={themeA} />
        </div>
      </div>

      {/* Tabs */}
      <div style={{ padding: '0 32px', background: themeA.surface }}>
        <TabBar active={active} setActive={setActive} theme={themeA} variant="underline" />
      </div>

      {/* Content */}
      <div className="dashboard-scroll" style={{ flex: 1, padding: '24px 32px', overflowY: 'auto' }}>
        <div className="tab-pane" key={active}>
          {renderTab(active, themeA, { scenario, chartStyle, setChartStyle })}
        </div>
      </div>
    </div>
  );
}

/* ──────────────────────────────────────────
   DIRECTION B — Tactical Grid (high contrast, dense, sharp)
   Pure black, sharp white type, amber + cyan accents, mono-heavy
   ────────────────────────────────────────── */
const themeB = {
  surface: '#050608',
  surface2: '#0c0e12',
  surface3: '#161a22',
  border: 'rgba(255, 255, 255, 0.08)',
  divider: 'rgba(255, 255, 255, 0.05)',
  text: '#ffffff',
  subtext: '#cdd2dc',
  muted: '#6b7280',
  accent: '#fbbf24',
  accent2: '#22d3ee',
  bull: '#34d399',
  bear: '#fb7185',
  line1: '#fbbf24',
  line2: '#22d3ee',
  grid: 'rgba(255, 255, 255, 0.04)',
  chip: 'rgba(251, 191, 36, 0.06)',
  radius: 2,
};

function DirectionB() {
  const [active, setActive] = React.useState('overview');
  const [scenario, setScenario] = React.useState('base');
  const [chartStyle, setChartStyle] = React.useState('candle');
  return (
    <div style={{ width: '100%', height: '100%', background: themeB.surface, color: themeB.text, fontFamily: 'Inter, system-ui, sans-serif', display: 'flex', flexDirection: 'column' }}>
      {/* Top header — terminal style */}
      <div style={{ padding: '14px 24px', borderBottom: `1px solid ${themeB.border}`, display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: themeB.surface2 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ width: 28, height: 28, border: `1.5px solid ${themeB.accent}`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <div style={{ width: 8, height: 8, background: themeB.accent }} />
            </div>
            <span style={{ fontSize: 13, fontWeight: 700, fontFamily: 'JetBrains Mono, monospace', letterSpacing: '0.15em' }}>SWING.OPS</span>
          </div>
          <div style={{ width: 1, height: 24, background: themeB.divider }} />
          <span style={{ fontSize: 11, color: themeB.muted, fontFamily: 'JetBrains Mono, monospace', letterSpacing: '0.12em' }}>SESSION_LIVE · {D.asOf}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontSize: 10, color: themeB.bull, fontFamily: 'JetBrains Mono, monospace', display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: themeB.bull }} className="pulse-dot" />
            FEED OK
          </span>
          <ScenarioToggle scenario={scenario} setScenario={setScenario} theme={themeB} />
        </div>
      </div>

      {/* Ticker bar — bigger, terminal */}
      <div style={{ padding: '20px 24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: `1px solid ${themeB.border}` }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 24 }}>
          <div>
            <div style={{ fontSize: 10, color: themeB.muted, fontFamily: 'JetBrains Mono, monospace', letterSpacing: '0.15em' }}>TICKER</div>
            <div style={{ fontSize: 36, fontWeight: 800, color: themeB.text, fontFamily: 'JetBrains Mono, monospace', letterSpacing: '-0.02em', lineHeight: 1 }}>{D.ticker}</div>
          </div>
          <div>
            <div style={{ fontSize: 10, color: themeB.muted, fontFamily: 'JetBrains Mono, monospace', letterSpacing: '0.15em' }}>LAST · USD</div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
              <span style={{ fontSize: 36, fontWeight: 800, color: themeB.text, fontFamily: 'JetBrains Mono, monospace', lineHeight: 1 }}>{D.price}</span>
              <span style={{ fontSize: 14, color: themeB.bull, fontFamily: 'JetBrains Mono, monospace', fontWeight: 700 }}>▲ {D.change} / {pct(D.changePct)}</span>
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 32 }}>
          {[
            ['VERDICT', D.verdict, themeB.bull],
            ['CONVICTION', D.scores.composite, themeB.accent],
            ['SETUP', 'EMA21·PB', themeB.accent2],
            ['SECTOR', 'INDS', themeB.muted],
          ].map(([l, v, c], i) => (
            <div key={i}>
              <div style={{ fontSize: 10, color: themeB.muted, fontFamily: 'JetBrains Mono, monospace', letterSpacing: '0.15em' }}>{l}</div>
              <div style={{ fontSize: 18, fontWeight: 700, color: c, fontFamily: 'JetBrains Mono, monospace' }}>{v}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Tabs */}
      <div style={{ padding: '14px 24px 0', background: themeB.surface, borderBottom: `1px solid ${themeB.border}` }}>
        <TabBar active={active} setActive={setActive} theme={themeB} variant="underline" />
      </div>

      <div className="dashboard-scroll" style={{ flex: 1, padding: '24px', overflowY: 'auto' }}>
        <div className="tab-pane" key={active}>
          {renderTab(active, themeB, { scenario, chartStyle, setChartStyle })}
        </div>
      </div>
    </div>
  );
}

/* ──────────────────────────────────────────
   DIRECTION C — Editorial Quant
   Side rail navigation, refined spacing, near-black with warm accents
   ────────────────────────────────────────── */
const themeC = {
  surface: '#0e1014',
  surface2: '#161a20',
  surface3: '#21262e',
  border: 'rgba(232, 226, 215, 0.1)',
  divider: 'rgba(232, 226, 215, 0.06)',
  text: '#f5f1e8',
  subtext: '#c9c2b3',
  muted: '#8b8678',
  accent: '#d4a574',
  accent2: '#a8c4b0',
  bull: '#a8c4b0',
  bear: '#d97757',
  line1: '#d4a574',
  line2: '#a8c4b0',
  grid: 'rgba(232, 226, 215, 0.05)',
  chip: 'rgba(212, 165, 116, 0.08)',
  radius: 4,
};

function DirectionC() {
  const [active, setActive] = React.useState('overview');
  const [scenario, setScenario] = React.useState('base');
  const [chartStyle, setChartStyle] = React.useState('candle');
  return (
    <div style={{ width: '100%', height: '100%', background: themeC.surface, color: themeC.text, fontFamily: 'Inter, system-ui, sans-serif', display: 'grid', gridTemplateColumns: '220px 1fr' }}>
      {/* Side rail */}
      <div style={{ borderRight: `1px solid ${themeC.border}`, background: themeC.surface2, padding: '24px 0', display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '0 20px 20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 20 }}>
            <div style={{ width: 10, height: 10, background: themeC.accent, borderRadius: 1 }} />
            <span style={{ fontSize: 12, fontWeight: 700, letterSpacing: '0.18em', color: themeC.text, fontFamily: 'JetBrains Mono, monospace' }}>QUANT/DESK</span>
          </div>
          <div>
            <div style={{ fontSize: 28, fontWeight: 800, fontFamily: 'JetBrains Mono, monospace', color: themeC.text, letterSpacing: '-0.02em' }}>{D.ticker}</div>
            <div style={{ fontSize: 11, color: themeC.muted, marginTop: 2 }}>{D.company}</div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginTop: 14 }}>
              <span style={{ fontSize: 22, fontWeight: 700, color: themeC.text, fontFamily: 'JetBrains Mono, monospace' }}>${D.price}</span>
              <span style={{ fontSize: 12, color: themeC.bull, fontFamily: 'JetBrains Mono, monospace', fontWeight: 700 }}>{pct(D.changePct)}</span>
            </div>
          </div>
        </div>
        <div style={{ height: 1, background: themeC.divider, margin: '0 20px' }} />
        <div style={{ padding: '16px 0 0 12px' }}>
          <div style={{ fontSize: 10, color: themeC.muted, letterSpacing: '0.15em', fontWeight: 700, padding: '0 8px 8px' }}>ANALYSIS</div>
          <TabBar active={active} setActive={setActive} theme={themeC} variant="rail" />
        </div>
        <div style={{ flex: 1 }} />
        <div style={{ padding: '0 20px' }}>
          <div style={{ fontSize: 10, color: themeC.muted, letterSpacing: '0.15em', fontWeight: 700, marginBottom: 8 }}>SCENARIO</div>
          <ScenarioToggle scenario={scenario} setScenario={setScenario} theme={themeC} />
        </div>
      </div>

      {/* Main area */}
      <div style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div style={{ padding: '20px 36px', borderBottom: `1px solid ${themeC.border}`, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <div style={{ fontSize: 11, color: themeC.muted, letterSpacing: '0.18em', fontWeight: 600 }}>{D.asOf}</div>
            <div style={{ fontSize: 24, fontWeight: 700, color: themeC.text, marginTop: 4, letterSpacing: '-0.01em' }}>
              {TABS.find(t => t.id === active).label}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 28 }}>
            <div>
              <div style={{ fontSize: 10, color: themeC.muted, letterSpacing: '0.12em', fontWeight: 600 }}>VERDICT</div>
              <div style={{ fontSize: 16, fontWeight: 700, color: themeC.bull, fontFamily: 'JetBrains Mono, monospace' }}>{D.verdict} · {D.scores.composite}</div>
            </div>
            <div>
              <div style={{ fontSize: 10, color: themeC.muted, letterSpacing: '0.12em', fontWeight: 600 }}>SETUP</div>
              <div style={{ fontSize: 14, fontWeight: 600, color: themeC.text }}>EMA21 Pullback</div>
            </div>
            <div>
              <div style={{ fontSize: 10, color: themeC.muted, letterSpacing: '0.12em', fontWeight: 600 }}>NEXT EARN</div>
              <div style={{ fontSize: 14, fontWeight: 600, color: themeC.accent, fontFamily: 'JetBrains Mono, monospace' }}>{D.fundamentals.nextEarnings}</div>
            </div>
          </div>
        </div>
        <div className="dashboard-scroll" style={{ flex: 1, padding: '28px 36px', overflowY: 'auto' }}>
          <div className="tab-pane" key={active}>
            {renderTab(active, themeC, { scenario, chartStyle, setChartStyle })}
          </div>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { DirectionA, DirectionB, DirectionC });

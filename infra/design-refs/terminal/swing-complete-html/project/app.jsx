// Main app shell — left sidebar nav, dashboard with rich tiles + heatmap,
// click a ticker → opens analysis page. Hedge Fund Classic theme only.

const T = {
  surface: '#0a1220',
  surface2: '#101a2c',
  surface3: '#1a2540',
  surface4: '#243151',
  border: 'rgba(148, 163, 184, 0.12)',
  divider: 'rgba(148, 163, 184, 0.08)',
  text: '#e6edf7',
  subtext: '#b8c3d6',
  muted: '#7a8aa6',
  accent: '#7cc4ff',
  accent2: '#c4a8ff',
  bull: '#5dd99c',
  bear: '#f87171',
  warn: '#fbbf24',
  line1: '#7cc4ff',
  line2: '#c4a8ff',
  grid: 'rgba(148, 163, 184, 0.08)',
  chip: 'rgba(124, 196, 255, 0.08)',
  radius: 6,
};

const NAV = [
  { id: 'trades', label: 'Trades', icon: '◎' },
  { id: 'strategies', label: 'Strategies', icon: '◈' },
  { id: 'portfolio', label: 'Portfolio', icon: '◇' },
  { id: 'performance', label: 'Performance', icon: '▲' },
  { id: 'screener', label: 'Screener', icon: '⊞' },
  { id: 'themes', label: 'Themes', icon: '◐' },
  { id: 'research', label: 'Research', icon: '◌' },
  { id: 'analysis', label: 'Analysis', icon: '◉' },
  { id: 'leveraged', label: 'Leveraged', icon: '⚡' },
  { id: 'industries', label: 'Industries', icon: '◫' },
  { id: 'market', label: 'Market', icon: '◍' },
  { id: 'crypto', label: 'Crypto', icon: '◈' },
  { id: 'playbook', label: 'Playbook', icon: '☰' },
  { id: 'guide', label: 'Guide', icon: '⊟' },
  { id: 'reference', label: 'Reference', icon: '⊠' },
  { id: 'status', label: 'Status', icon: '●' },
  { id: 'settings', label: 'Settings', icon: '⚙' },
];

const SCAN = window.SCANNER_DATA;
const fmt2 = (n, d = 2) => (typeof n === 'number' ? n.toFixed(d) : n);
const pct2 = (n) => `${n > 0 ? '+' : ''}${n.toFixed(2)}%`;

/* ─── Verdict pill ─── */
function VerdictPill({ v }) {
  const map = { BUY: T.bull, HOLD: T.warn, WAIT: T.accent, AVOID: T.bear };
  const c = map[v] || T.muted;
  return (
    <span style={{ fontSize: 10, fontWeight: 800, letterSpacing: '0.1em', padding: '3px 8px', borderRadius: 3, color: c, background: c + '18', border: `1px solid ${c}40` }}>{v}</span>
  );
}

/* ─── Ticker tile ─── */
function TickerTile({ row, onOpen }) {
  return (
    <div onClick={() => onOpen(row.ticker)} style={{
      padding: 14, background: T.surface2, border: `1px solid ${T.border}`, borderRadius: T.radius,
      cursor: 'pointer', transition: 'border-color 200ms, transform 200ms',
    }}
      onMouseEnter={(e) => { e.currentTarget.style.borderColor = T.accent + '88'; e.currentTarget.style.transform = 'translateY(-1px)'; }}
      onMouseLeave={(e) => { e.currentTarget.style.borderColor = T.border; e.currentTarget.style.transform = 'translateY(0)'; }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
        <div>
          <div style={{ fontSize: 16, fontWeight: 800, fontFamily: 'JetBrains Mono, monospace', color: T.text, letterSpacing: '-0.01em' }}>{row.ticker}</div>
          <div style={{ fontSize: 10, color: T.muted, marginTop: 2 }}>{row.sector}</div>
        </div>
        <VerdictPill v={row.verdict} />
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 10 }}>
        <span style={{ fontSize: 18, fontWeight: 700, color: T.text, fontFamily: 'JetBrains Mono, monospace' }}>${fmt2(row.price)}</span>
        <span style={{ fontSize: 11, fontWeight: 700, fontFamily: 'JetBrains Mono, monospace', color: row.changePct >= 0 ? T.bull : T.bear }}>{pct2(row.changePct)}</span>
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 10, color: T.muted, marginBottom: 6 }}>
        <span>SCORE</span>
        <span style={{ fontFamily: 'JetBrains Mono, monospace', fontWeight: 700, color: T.text }}>{row.score}</span>
      </div>
      <div style={{ height: 4, background: T.surface3, borderRadius: 2, overflow: 'hidden' }}>
        <div style={{ width: `${row.score}%`, height: '100%', background: row.score >= 70 ? T.bull : row.score >= 50 ? T.warn : T.bear }} />
      </div>
      <div style={{ marginTop: 10, paddingTop: 10, borderTop: `1px solid ${T.divider}`, fontSize: 10, color: T.subtext }}>
        {row.setup}
      </div>
    </div>
  );
}

/* ─── Heatmap ─── */
function Heatmap({ rows, onOpen }) {
  const sectors = {};
  rows.forEach(r => { (sectors[r.sector] = sectors[r.sector] || []).push(r); });
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14 }}>
      {Object.entries(sectors).map(([sector, items]) => (
        <div key={sector} style={{ background: T.surface2, border: `1px solid ${T.border}`, borderRadius: T.radius, padding: 12 }}>
          <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.12em', color: T.muted, marginBottom: 10 }}>{sector.toUpperCase()}</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 4 }}>
            {items.map(r => {
              const s = r.score;
              const bg = s >= 80 ? '#0d4f2e' : s >= 70 ? '#155e3a' : s >= 60 ? '#1f4a3d' : s >= 50 ? '#3a3f2a' : s >= 40 ? '#3a2f2a' : s >= 30 ? '#5a2a2a' : '#6e1f1f';
              const fg = s >= 60 ? T.bull : s >= 40 ? T.warn : T.bear;
              return (
                <div key={r.ticker} onClick={() => onOpen(r.ticker)} style={{
                  padding: '8px 6px', background: bg, borderRadius: 3, cursor: 'pointer', textAlign: 'center',
                  border: `1px solid ${fg}30`, transition: 'transform 150ms',
                }}
                  onMouseEnter={(e) => { e.currentTarget.style.transform = 'scale(1.05)'; }}
                  onMouseLeave={(e) => { e.currentTarget.style.transform = 'scale(1)'; }}>
                  <div style={{ fontSize: 11, fontWeight: 700, fontFamily: 'JetBrains Mono, monospace', color: T.text }}>{r.ticker}</div>
                  <div style={{ fontSize: 10, color: fg, fontFamily: 'JetBrains Mono, monospace', fontWeight: 700 }}>{r.score}</div>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

/* ─── Scanner table ─── */
function ScannerTable({ rows, onOpen, sortKey, setSortKey, sortDir, setSortDir, query }) {
  const filtered = query
    ? rows.filter(r => r.ticker.toLowerCase().includes(query.toLowerCase()) || r.name.toLowerCase().includes(query.toLowerCase()) || r.sector.toLowerCase().includes(query.toLowerCase()))
    : rows;
  const sorted = [...filtered].sort((a, b) => {
    const av = a[sortKey], bv = b[sortKey];
    const r = typeof av === 'number' ? av - bv : String(av).localeCompare(String(bv));
    return sortDir === 'asc' ? r : -r;
  });
  const cols = [
    { k: 'ticker', l: 'Ticker', w: 80 },
    { k: 'name', l: 'Name', w: null },
    { k: 'sector', l: 'Sector', w: 120 },
    { k: 'price', l: 'Price', w: 90, num: true },
    { k: 'changePct', l: 'Chg %', w: 80, num: true, color: true },
    { k: 'score', l: 'Score', w: 100, bar: true },
    { k: 'verdict', l: 'Verdict', w: 80, pill: true },
    { k: 'technical', l: 'Tech', w: 70, num: true },
    { k: 'smc', l: 'SMC', w: 70, num: true },
    { k: 'setup', l: 'Setup', w: 160 },
  ];
  return (
    <div style={{ background: T.surface2, border: `1px solid ${T.border}`, borderRadius: T.radius, overflow: 'hidden' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: 'Inter, sans-serif' }}>
        <thead>
          <tr style={{ background: T.surface3 }}>
            {cols.map(c => (
              <th key={c.k} onClick={() => {
                if (sortKey === c.k) setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
                else { setSortKey(c.k); setSortDir('desc'); }
              }} style={{
                fontSize: 10, fontWeight: 700, color: T.muted, padding: '12px 14px', textAlign: c.num ? 'right' : 'left',
                letterSpacing: '0.1em', cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap',
                width: c.w, borderBottom: `1px solid ${T.border}`,
              }}>{c.l.toUpperCase()} {sortKey === c.k && (sortDir === 'asc' ? '↑' : '↓')}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((r, i) => (
            <tr key={r.ticker} onClick={() => onOpen(r.ticker)} style={{
              borderBottom: `1px solid ${T.divider}`, cursor: 'pointer', transition: 'background 150ms',
            }}
              onMouseEnter={(e) => { e.currentTarget.style.background = T.surface3; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}>
              {cols.map(c => {
                const v = r[c.k];
                let content = v;
                if (c.k === 'ticker') content = <span style={{ fontFamily: 'JetBrains Mono, monospace', fontWeight: 700, color: T.text, fontSize: 13 }}>{v}</span>;
                else if (c.k === 'price') content = <span style={{ fontFamily: 'JetBrains Mono, monospace' }}>${fmt2(v)}</span>;
                else if (c.color) content = <span style={{ fontFamily: 'JetBrains Mono, monospace', fontWeight: 700, color: v >= 0 ? T.bull : T.bear }}>{pct2(v)}</span>;
                else if (c.bar) content = (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ flex: 1, height: 4, background: T.surface3, borderRadius: 2 }}>
                      <div style={{ width: `${v}%`, height: '100%', background: v >= 70 ? T.bull : v >= 50 ? T.warn : T.bear, borderRadius: 2 }} />
                    </div>
                    <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11, color: T.text, fontWeight: 700, minWidth: 22 }}>{v}</span>
                  </div>
                );
                else if (c.pill) content = <VerdictPill v={v} />;
                else if (c.num) content = <span style={{ fontFamily: 'JetBrains Mono, monospace' }}>{v}</span>;
                else content = <span style={{ color: T.subtext }}>{v}</span>;
                return (
                  <td key={c.k} style={{ fontSize: 12, color: T.text, padding: '12px 14px', textAlign: c.num ? 'right' : 'left' }}>
                    {content}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ─── Top stats ribbon ─── */
function StatsRibbon() {
  const stats = [
    { l: 'Account', v: '$250,000', c: T.text, sub: 'Equity' },
    { l: 'Day P&L', v: '+$2,847', c: T.bull, sub: '+1.14%' },
    { l: 'Open Positions', v: '8 / 12', c: T.text, sub: 'Capacity' },
    { l: 'Portfolio Heat', v: '3.2%', c: T.warn, sub: 'of 6% cap' },
    { l: 'Buying Power', v: '$184k', c: T.text, sub: 'Cash + 2x' },
    { l: 'SPY', v: '538.42', c: T.bull, sub: '+0.84%' },
    { l: 'VIX', v: '14.8', c: T.bull, sub: '−2.1%' },
    { l: 'Breadth', v: '72%', c: T.bull, sub: 'Adv/Decl' },
    { l: 'Regime', v: 'RISK-ON', c: T.bull, sub: 'Bull trend' },
  ];
  return (
    <div style={{ display: 'grid', gridTemplateColumns: `repeat(${stats.length}, 1fr)`, gap: 0, background: T.surface2, border: `1px solid ${T.border}`, borderRadius: T.radius, overflow: 'hidden' }}>
      {stats.map((s, i) => (
        <div key={i} style={{ padding: '12px 16px', borderRight: i < stats.length - 1 ? `1px solid ${T.divider}` : 'none' }}>
          <div style={{ fontSize: 10, color: T.muted, fontWeight: 600, letterSpacing: '0.1em', marginBottom: 4 }}>{s.l.toUpperCase()}</div>
          <div style={{ fontSize: 16, fontWeight: 700, color: s.c, fontFamily: 'JetBrains Mono, monospace', lineHeight: 1.1 }}>{s.v}</div>
          <div style={{ fontSize: 10, color: T.muted, marginTop: 2 }}>{s.sub}</div>
        </div>
      ))}
    </div>
  );
}

/* ─── Trades dashboard (main) ─── */
function TradesDashboard({ onOpen }) {
  const [sortKey, setSortKey] = React.useState('score');
  const [sortDir, setSortDir] = React.useState('desc');
  const [query, setQuery] = React.useState('');
  const [view, setView] = React.useState('tiles'); // tiles | table | heatmap
  const [verdictFilter, setVerdictFilter] = React.useState('ALL');
  const [sectorFilter, setSectorFilter] = React.useState('ALL');

  let rows = SCAN;
  if (verdictFilter !== 'ALL') rows = rows.filter(r => r.verdict === verdictFilter);
  if (sectorFilter !== 'ALL') rows = rows.filter(r => r.sector === sectorFilter);
  if (query) rows = rows.filter(r =>
    r.ticker.toLowerCase().includes(query.toLowerCase()) ||
    r.name.toLowerCase().includes(query.toLowerCase()) ||
    r.sector.toLowerCase().includes(query.toLowerCase())
  );
  const tilesRows = [...rows].sort((a, b) => b.score - a.score);

  const sectors = ['ALL', ...Array.from(new Set(SCAN.map(r => r.sector)))];
  const verdicts = ['ALL', 'BUY', 'HOLD', 'WAIT', 'AVOID'];

  return (
    <div style={{ padding: '20px 24px' }}>
      <StatsRibbon />

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', margin: '24px 0 16px' }}>
        <div>
          <div style={{ fontSize: 22, fontWeight: 700, color: T.text, letterSpacing: '-0.01em' }}>Trade Candidates</div>
          <div style={{ fontSize: 12, color: T.muted, marginTop: 2 }}>{rows.length} tickers · sorted by composite score · click any to open analysis</div>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <input value={query} onChange={(e) => setQuery(e.target.value)}
            placeholder="Search ticker, name, sector…"
            style={{
              padding: '8px 14px', fontSize: 13, fontFamily: 'Inter, sans-serif',
              background: T.surface2, color: T.text, border: `1px solid ${T.border}`, borderRadius: T.radius,
              width: 280, outline: 'none',
            }}
            onFocus={(e) => e.target.style.borderColor = T.accent}
            onBlur={(e) => e.target.style.borderColor = T.border}
          />
          <div style={{ display: 'flex', background: T.surface2, border: `1px solid ${T.border}`, borderRadius: T.radius, overflow: 'hidden' }}>
            {['tiles', 'table', 'heatmap'].map(v => (
              <button key={v} onClick={() => setView(v)} style={{
                padding: '8px 14px', fontSize: 11, fontWeight: 700, letterSpacing: '0.08em',
                background: view === v ? T.surface3 : 'transparent',
                color: view === v ? T.text : T.muted, border: 'none', textTransform: 'uppercase',
              }}>{v}</button>
            ))}
          </div>
        </div>
      </div>

      {/* Filter bar */}
      <div style={{ display: 'flex', gap: 16, alignItems: 'center', marginBottom: 16, padding: '10px 14px', background: T.surface2, border: `1px solid ${T.border}`, borderRadius: T.radius }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ fontSize: 10, color: T.muted, letterSpacing: '0.1em', fontWeight: 700 }}>VERDICT</span>
          {verdicts.map(v => (
            <button key={v} onClick={() => setVerdictFilter(v)} style={{
              padding: '4px 10px', fontSize: 10, fontWeight: 700, letterSpacing: '0.05em',
              background: verdictFilter === v ? T.accent + '20' : 'transparent',
              color: verdictFilter === v ? T.accent : T.subtext,
              border: `1px solid ${verdictFilter === v ? T.accent + '60' : T.border}`, borderRadius: 3,
            }}>{v}</button>
          ))}
        </div>
        <div style={{ width: 1, height: 20, background: T.divider }} />
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          <span style={{ fontSize: 10, color: T.muted, letterSpacing: '0.1em', fontWeight: 700 }}>SECTOR</span>
          {sectors.map(s => (
            <button key={s} onClick={() => setSectorFilter(s)} style={{
              padding: '4px 10px', fontSize: 10, fontWeight: 700, letterSpacing: '0.05em',
              background: sectorFilter === s ? T.accent + '20' : 'transparent',
              color: sectorFilter === s ? T.accent : T.subtext,
              border: `1px solid ${sectorFilter === s ? T.accent + '60' : T.border}`, borderRadius: 3,
            }}>{s.toUpperCase()}</button>
          ))}
        </div>
      </div>

      {/* Content */}
      {view === 'tiles' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12 }}>
          {tilesRows.map(r => <TickerTile key={r.ticker} row={r} onOpen={onOpen} />)}
        </div>
      )}
      {view === 'table' && (
        <ScannerTable rows={rows} onOpen={onOpen}
          sortKey={sortKey} setSortKey={setSortKey} sortDir={sortDir} setSortDir={setSortDir} query="" />
      )}
      {view === 'heatmap' && (
        <Heatmap rows={rows} onOpen={onOpen} />
      )}
    </div>
  );
}

/* ─── Placeholder section ─── */
function Placeholder({ title, blurb }) {
  return (
    <div style={{ padding: '40px 24px' }}>
      <div style={{ fontSize: 22, fontWeight: 700, color: T.text, letterSpacing: '-0.01em' }}>{title}</div>
      <div style={{ fontSize: 13, color: T.muted, marginTop: 8, maxWidth: 600 }}>{blurb}</div>
      <div style={{ marginTop: 24, padding: 24, background: T.surface2, border: `1px dashed ${T.border}`, borderRadius: T.radius, color: T.muted, fontSize: 13, lineHeight: 1.6 }}>
        Section scaffold ready. The full content layout follows the same Hedge Fund Classic design language: dark navy surfaces, muted accents, Inter + JetBrains Mono. Once direction is locked, this section will be filled with live data wired the same way as Trades.
      </div>
    </div>
  );
}

/* ─── Portfolio (lightweight version) ─── */
function PortfolioSection({ onOpen }) {
  const positions = [
    { t: 'TICKR', entry: 244.10, shares: 124, stop: 238.40, last: 247.83, pnl: 462.52, dir: 'long', setup: 'EMA21 PB' },
    { t: 'NVRA', entry: 398.20, shares: 28, stop: 388.00, last: 412.60, pnl: 403.20, dir: 'long', setup: 'Breakout' },
    { t: 'AURA', entry: 192.40, shares: 60, stop: 186.20, last: 198.40, pnl: 360.00, dir: 'long', setup: 'Flag' },
    { t: 'KAIO', entry: 62.10, shares: 200, stop: 60.00, last: 64.18, pnl: 416.00, dir: 'long', setup: 'Cup&Handle' },
    { t: 'SOMA', entry: 470.00, shares: 22, stop: 458.00, last: 482.40, pnl: 272.80, dir: 'long', setup: 'Breakout' },
    { t: 'PRYM', entry: 178.20, shares: 60, stop: 172.00, last: 184.20, pnl: 360.00, dir: 'long', setup: 'Trend Cont' },
    { t: 'VRTX', entry: 312.00, shares: 32, stop: 304.00, last: 318.91, pnl: 221.12, dir: 'long', setup: 'Trend Cont' },
    { t: 'CLAR', entry: 162.00, shares: 80, stop: 156.50, last: 168.40, pnl: 512.00, dir: 'long', setup: 'Flag' },
  ];
  const totalPnL = positions.reduce((s, p) => s + p.pnl, 0);
  const cols = ['Sym', 'Dir', 'Entry', 'Shares', 'Stop', 'Last', '$ P&L', '% P&L', 'Setup', ''];
  return (
    <div style={{ padding: '20px 24px' }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12, marginBottom: 24 }}>
        {[
          ['Open Positions', `${positions.length}`, T.text],
          ['Day P&L', `+$${fmt2(totalPnL)}`, T.bull],
          ['Total Exposure', '$184,420', T.text],
          ['Heat Used', '3.2%', T.warn],
          ['Win Rate (30d)', '68%', T.bull],
        ].map(([l, v, c], i) => (
          <div key={i} style={{ padding: 16, background: T.surface2, border: `1px solid ${T.border}`, borderRadius: T.radius }}>
            <div style={{ fontSize: 10, color: T.muted, letterSpacing: '0.1em', fontWeight: 700 }}>{l.toUpperCase()}</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: c, fontFamily: 'JetBrains Mono, monospace', marginTop: 6 }}>{v}</div>
          </div>
        ))}
      </div>
      <div style={{ background: T.surface2, border: `1px solid ${T.border}`, borderRadius: T.radius, overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ background: T.surface3 }}>
              {cols.map(c => (
                <th key={c} style={{ fontSize: 10, fontWeight: 700, color: T.muted, padding: '12px 14px', textAlign: 'left', letterSpacing: '0.1em' }}>{c.toUpperCase()}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {positions.map(p => {
              const pnlPct = ((p.last - p.entry) / p.entry) * 100;
              return (
                <tr key={p.t} style={{ borderBottom: `1px solid ${T.divider}`, cursor: 'pointer' }} onClick={() => onOpen(p.t)}>
                  <td style={{ padding: '12px 14px', fontFamily: 'JetBrains Mono, monospace', fontWeight: 700, color: T.text }}>{p.t}</td>
                  <td style={{ padding: '12px 14px', fontSize: 11, color: T.bull, fontWeight: 700 }}>{p.dir.toUpperCase()}</td>
                  <td style={{ padding: '12px 14px', fontFamily: 'JetBrains Mono, monospace', color: T.subtext }}>${fmt2(p.entry)}</td>
                  <td style={{ padding: '12px 14px', fontFamily: 'JetBrains Mono, monospace', color: T.subtext }}>{p.shares}</td>
                  <td style={{ padding: '12px 14px', fontFamily: 'JetBrains Mono, monospace', color: T.bear }}>${fmt2(p.stop)}</td>
                  <td style={{ padding: '12px 14px', fontFamily: 'JetBrains Mono, monospace', color: T.text, fontWeight: 700 }}>${fmt2(p.last)}</td>
                  <td style={{ padding: '12px 14px', fontFamily: 'JetBrains Mono, monospace', color: p.pnl >= 0 ? T.bull : T.bear, fontWeight: 700 }}>+${fmt2(p.pnl)}</td>
                  <td style={{ padding: '12px 14px', fontFamily: 'JetBrains Mono, monospace', color: pnlPct >= 0 ? T.bull : T.bear, fontWeight: 700 }}>{pct2(pnlPct)}</td>
                  <td style={{ padding: '12px 14px', fontSize: 11, color: T.subtext }}>{p.setup}</td>
                  <td style={{ padding: '12px 14px', fontSize: 10, color: T.accent }}>OPEN →</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ─── Analysis page wrapper — uses the existing DirectionA tab system ─── */
function AnalysisPage({ ticker, onBack }) {
  const [active, setActive] = React.useState('overview');
  const [scenario, setScenario] = React.useState('base');
  const [chartStyle, setChartStyle] = React.useState('candle');
  return (
    <div style={{ width: '100%', height: '100%', background: T.surface, color: T.text, display: 'flex', flexDirection: 'column' }}>
      <div style={{ padding: '14px 24px', borderBottom: `1px solid ${T.border}`, display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: T.surface }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <button onClick={onBack} style={{
            padding: '6px 12px', fontSize: 11, fontWeight: 700, letterSpacing: '0.08em',
            background: 'transparent', color: T.subtext, border: `1px solid ${T.border}`, borderRadius: 4,
          }}>← BACK TO TRADES</button>
          <TickerHeader theme={T} />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <div style={{ display: 'flex', gap: 16 }}>
            {[['MKT CAP', D.marketCap], ['AVG VOL', D.avgVol], ['BETA', D.beta]].map(([l, v], i) => (
              <div key={i} style={{ textAlign: 'right' }}>
                <div style={{ fontSize: 10, color: T.muted, letterSpacing: '0.1em', fontWeight: 600 }}>{l}</div>
                <div style={{ fontSize: 13, fontFamily: 'JetBrains Mono, monospace', color: T.text, fontWeight: 600 }}>{v}</div>
              </div>
            ))}
          </div>
          <ScenarioToggle scenario={scenario} setScenario={setScenario} theme={T} />
        </div>
      </div>
      <div style={{ padding: '0 24px', background: T.surface }}>
        <TabBar active={active} setActive={setActive} theme={T} variant="underline" />
      </div>
      <div className="dashboard-scroll" style={{ flex: 1, padding: '24px', overflowY: 'auto' }}>
        <div className="tab-pane" key={active}>
          {renderTab(active, T, { scenario, chartStyle, setChartStyle })}
        </div>
      </div>
    </div>
  );
}

/* ─── Sidebar ─── */
function Sidebar({ active, setActive }) {
  return (
    <div style={{ width: 200, background: T.surface2, borderRight: `1px solid ${T.border}`, display: 'flex', flexDirection: 'column', padding: '20px 0' }}>
      <div style={{ padding: '0 20px 20px', display: 'flex', alignItems: 'center', gap: 8 }}>
        <div style={{ width: 26, height: 26, borderRadius: 4, background: `linear-gradient(135deg, ${T.accent}, ${T.accent2})`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 14, color: '#0a1220' }}>S</div>
        <div>
          <div style={{ fontSize: 12, fontWeight: 800, color: T.text, letterSpacing: '0.1em' }}>SWING</div>
          <div style={{ fontSize: 9, color: T.muted, letterSpacing: '0.18em', fontWeight: 600 }}>TERMINAL</div>
        </div>
      </div>
      <div style={{ height: 1, background: T.divider, margin: '0 20px 10px' }} />
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {NAV.map(n => (
          <button key={n.id} onClick={() => setActive(n.id)} style={{
            width: '100%', padding: '10px 20px', fontSize: 13, fontWeight: 500, textAlign: 'left',
            display: 'flex', alignItems: 'center', gap: 10,
            background: active === n.id ? T.accent + '12' : 'transparent',
            color: active === n.id ? T.accent : T.subtext,
            border: 'none', borderLeft: `2px solid ${active === n.id ? T.accent : 'transparent'}`,
            transition: 'all 200ms',
          }}>
            <span style={{ fontSize: 12, opacity: 0.8, width: 14, textAlign: 'center' }}>{n.icon}</span>
            <span>{n.label}</span>
          </button>
        ))}
      </div>
      <div style={{ padding: '14px 20px', borderTop: `1px solid ${T.divider}`, fontSize: 10, color: T.muted, fontFamily: 'JetBrains Mono, monospace', letterSpacing: '0.05em' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
          <span style={{ width: 6, height: 6, borderRadius: '50%', background: T.bull }} className="pulse-dot" />
          <span>FEED LIVE · v2.4.1</span>
        </div>
        <div>SESSION 14:32 ET</div>
      </div>
    </div>
  );
}

/* ─── App shell ─── */
function App() {
  const [section, setSection] = React.useState('trades');
  const [analyzeTicker, setAnalyzeTicker] = React.useState(null);

  const open = (t) => setAnalyzeTicker(t);
  const back = () => setAnalyzeTicker(null);

  if (analyzeTicker) {
    return (
      <div style={{ width: '100vw', height: '100vh', display: 'grid', gridTemplateColumns: '200px 1fr', background: T.surface, fontFamily: 'Inter, system-ui, sans-serif' }}>
        <Sidebar active="analysis" setActive={(id) => { setAnalyzeTicker(null); setSection(id); }} />
        <AnalysisPage ticker={analyzeTicker} onBack={back} />
      </div>
    );
  }

  const sectionMap = {
    trades: <TradesDashboard onOpen={open} />,
    portfolio: <PortfolioSection onOpen={open} />,
    analysis: <AnalysisPage ticker="TICKR" onBack={() => setSection('trades')} />,
    strategies: <Placeholder title="Strategies" blurb="Curated strategy playbooks: TAZR, BBT, Coiled Spring, Hidden Tide, AEI, BCI, TI." />,
    performance: <Placeholder title="Performance" blurb="Mark-to-market tracking, equity curve, drawdown, Sharpe, hit rate, R-distribution." />,
    screener: <Placeholder title="Screener" blurb="Live results from the multi-criterion scanner — score >70, ADX >25, RSI 40-65." />,
    themes: <Placeholder title="Themes" blurb="Sector & macro themes scanner — AI infrastructure, defense, reshoring, biotech catalysts." />,
    research: <Placeholder title="Research" blurb="Index, sector and idea research notes by week." />,
    leveraged: <Placeholder title="Leveraged ETFs" blurb="3x leveraged ETF dashboard — TQQQ, SOXL, FAS, SPXL etc." />,
    industries: <Placeholder title="Industries" blurb="Industry rotation, sector ETF relative strength vs SPY (63-day window)." />,
    market: <Placeholder title="Market" blurb="Macro intel — rates, dollar, breadth, sentiment, regime indicators." />,
    crypto: <Placeholder title="Crypto" blurb="BTC, ETH, SOL plus high-beta alts." />,
    playbook: <Placeholder title="Playbook" blurb="Setup definitions, entry/stop rules, scaling, journaling." />,
    guide: <Placeholder title="Guide" blurb="How to read each panel; what each score means." />,
    reference: <Placeholder title="Reference" blurb="Glossary, formulas, data definitions." />,
    status: <Placeholder title="System Status" blurb="Data feeds, cron jobs, queue depth, errors." />,
    settings: <Placeholder title="Settings" blurb="Account, alerts, theme, API keys." />,
  };

  return (
    <div style={{ width: '100vw', height: '100vh', display: 'grid', gridTemplateColumns: '200px 1fr', background: T.surface, fontFamily: 'Inter, system-ui, sans-serif', color: T.text }}>
      <Sidebar active={section} setActive={setSection} />
      <div className="dashboard-scroll" style={{ overflowY: 'auto' }}>
        <div className="tab-pane" key={section}>
          {sectionMap[section]}
        </div>
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);

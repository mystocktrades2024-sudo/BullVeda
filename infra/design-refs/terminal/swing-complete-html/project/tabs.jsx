// Tab content panes — themed via the `theme` prop. Used by all three directions.

const D = window.TICKR_DATA;

const fmt = (n, d = 2) => (typeof n === 'number' ? n.toFixed(d) : n);
const pct = (n) => `${n > 0 ? '+' : ''}${n.toFixed(2)}%`;

/* ────── Stat row helpers ────── */
function StatCell({ label, value, hint, color, theme, mono = true }) {
  return (
    <div style={{ padding: '14px 16px', borderRight: `1px solid ${theme.divider}`, minWidth: 120 }}>
      <Tip text={hint || label}>
        <div style={{ fontSize: 10, fontWeight: 600, color: theme.muted, letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 6, cursor: 'help', borderBottom: `1px dotted ${theme.muted}`, display: 'inline-block' }}>{label}</div>
      </Tip>
      <div style={{ fontSize: 18, fontWeight: 700, color: color || theme.text, fontFamily: mono ? 'JetBrains Mono, monospace' : 'Inter, sans-serif', lineHeight: 1.1 }}>{value}</div>
    </div>
  );
}

function KV({ k, v, theme, vColor, hint, mono = true }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 0', borderBottom: `1px solid ${theme.divider}` }}>
      <Tip text={hint || k}>
        <span style={{ fontSize: 12, color: theme.muted, cursor: hint ? 'help' : 'default', borderBottom: hint ? `1px dotted ${theme.muted}` : 'none' }}>{k}</span>
      </Tip>
      <span style={{ fontSize: 13, fontWeight: 600, color: vColor || theme.text, fontFamily: mono ? 'JetBrains Mono, monospace' : 'Inter' }}>{v}</span>
    </div>
  );
}

/* ────── OVERVIEW ────── */
function OverviewTab({ theme, scenario }) {
  const sc = D.scenarios[scenario];
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 20 }}>
      {/* Verdict block */}
      <div style={{ gridColumn: '1 / 3', padding: 24, background: theme.surface2, border: `1px solid ${theme.border}`, borderRadius: theme.radius }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 24 }}>
          <ScoreArc value={D.scores.composite} size={120} stroke={9} color={theme.bull} bg={theme.surface3} valueColor={theme.bull} label="CONVICTION" />
          <div style={{ flex: 1 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
              <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: theme.bull }} className="pulse-dot" />
              <span style={{ fontSize: 11, fontWeight: 700, color: theme.bull, letterSpacing: '0.12em' }}>VERDICT</span>
            </div>
            <div style={{ fontSize: 36, fontWeight: 800, color: theme.text, letterSpacing: '-0.02em', lineHeight: 1, marginBottom: 8 }}>
              {D.verdict} <span style={{ color: theme.muted, fontWeight: 400, fontSize: 14 }}>· {D.setup}</span>
            </div>
            <p style={{ fontSize: 13, lineHeight: 1.5, color: theme.subtext, margin: '0 0 14px 0', maxWidth: 520 }}>
              Strong technical alignment (82) with confirmed bullish BOS and untapped FVG below. Setup has 64.8% historical hit rate over 142 occurrences. Catalyst window opens with Q1 earnings on May 14.
            </p>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {['Trend Continuation', 'EMA21 holding', 'BOS confirmed', 'Volume expansion', 'Sector tailwind'].map(t => (
                <span key={t} style={{ fontSize: 11, padding: '4px 10px', borderRadius: 4, background: theme.chip, color: theme.subtext, border: `1px solid ${theme.border}` }}>{t}</span>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Score breakdown */}
      <div style={{ padding: 20, background: theme.surface2, border: `1px solid ${theme.border}`, borderRadius: theme.radius }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: theme.muted, letterSpacing: '0.12em', marginBottom: 16 }}>SCORE COMPONENTS</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14, color: theme.text }}>
          <ScoreBar label="TECHNICAL" value={D.scores.technical} color={theme.bull} bg={theme.surface3} hint="Trend, momentum, MAs, RSI" valueColor={theme.text} />
          <ScoreBar label="FUNDAMENTAL" value={D.scores.fundamental} color={theme.accent} bg={theme.surface3} hint="Earnings, growth, valuation" valueColor={theme.text} />
          <ScoreBar label="SENTIMENT" value={D.scores.sentiment} color={theme.accent2} bg={theme.surface3} hint="Analyst, social, options" valueColor={theme.text} />
          <ScoreBar label="SMART MONEY" value={D.scores.smc} color={theme.bull} bg={theme.surface3} hint="Order blocks, liquidity, structure" valueColor={theme.text} />
          <ScoreBar label="RISK / REWARD" value={D.scores.risk} color={theme.accent} bg={theme.surface3} hint="R:R quality, position size fit" valueColor={theme.text} />
        </div>
      </div>

      {/* Scenario */}
      <div style={{ gridColumn: '1 / 4', padding: 20, background: theme.surface2, border: `1px solid ${theme.border}`, borderRadius: theme.radius }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: theme.muted, letterSpacing: '0.12em' }}>
            SCENARIO · <span style={{ color: scenario === 'bull' ? theme.bull : scenario === 'bear' ? theme.bear : theme.accent }}>{scenario.toUpperCase()}</span>
          </div>
          <div style={{ fontSize: 11, color: theme.muted }}>Toggle scenarios via the panel control →</div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr 1fr', gap: 24 }}>
          <div>
            <div style={{ fontSize: 10, fontWeight: 600, color: theme.muted, letterSpacing: '0.08em', marginBottom: 6 }}>THESIS</div>
            <p style={{ fontSize: 13, lineHeight: 1.6, color: theme.text, margin: 0 }}>{sc.thesis}</p>
          </div>
          <div>
            <div style={{ fontSize: 10, fontWeight: 600, color: theme.muted, letterSpacing: '0.08em', marginBottom: 6 }}>CATALYSTS</div>
            <ul style={{ margin: 0, padding: 0, listStyle: 'none' }}>
              {sc.catalysts.map(c => (
                <li key={c} style={{ fontSize: 12, color: theme.subtext, padding: '4px 0', borderBottom: `1px solid ${theme.divider}` }}>· {c}</li>
              ))}
            </ul>
          </div>
          <div>
            <div style={{ fontSize: 10, fontWeight: 600, color: theme.muted, letterSpacing: '0.08em', marginBottom: 6 }}>OUTCOME</div>
            <div style={{ fontSize: 28, fontWeight: 800, color: scenario === 'bear' ? theme.bear : theme.bull, fontFamily: 'JetBrains Mono, monospace', lineHeight: 1 }}>${sc.target}</div>
            <div style={{ fontSize: 12, color: theme.muted, marginTop: 4 }}>Probability {sc.probability}%</div>
            <div style={{ marginTop: 10, height: 6, background: theme.surface3, borderRadius: 3, overflow: 'hidden' }}>
              <div style={{ width: `${sc.probability}%`, height: '100%', background: scenario === 'bear' ? theme.bear : theme.bull }} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ────── TECHNICALS ────── */
function TechnicalsTab({ theme }) {
  const m = D.metrics;
  const Indicator = ({ label, value, status, hint, range }) => {
    const colors = { bullish: theme.bull, bearish: theme.bear, neutral: theme.accent };
    return (
      <div style={{ padding: 16, background: theme.surface2, border: `1px solid ${theme.border}`, borderRadius: theme.radius }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 10 }}>
          <Tip text={hint}><div style={{ fontSize: 10, fontWeight: 700, color: theme.muted, letterSpacing: '0.1em', cursor: 'help', borderBottom: `1px dotted ${theme.muted}` }}>{label}</div></Tip>
          <span style={{ fontSize: 9, padding: '2px 6px', borderRadius: 3, background: colors[status] + '20', color: colors[status], fontWeight: 700, letterSpacing: '0.08em' }}>{status.toUpperCase()}</span>
        </div>
        <div style={{ fontSize: 28, fontWeight: 700, color: theme.text, fontFamily: 'JetBrains Mono, monospace', lineHeight: 1 }}>{value}</div>
        {range && (
          <div style={{ marginTop: 12 }}>
            <div style={{ position: 'relative', height: 4, background: theme.surface3, borderRadius: 2 }}>
              <div style={{ position: 'absolute', left: `${range[2]}%`, top: -3, width: 2, height: 10, background: colors[status] }} />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4, fontSize: 9, color: theme.muted, fontFamily: 'JetBrains Mono, monospace' }}>
              <span>{range[0]}</span><span>{range[1]}</span>
            </div>
          </div>
        )}
      </div>
    );
  };
  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, marginBottom: 20 }}>
        <Indicator label="RSI (14)" value={fmt(m.rsi14, 1)} status="neutral" range={[0, 100, m.rsi14]} hint="14-period Relative Strength Index. Above 70 = overbought, below 30 = oversold. 58 sits in healthy uptrend territory." />
        <Indicator label="MACD" value={fmt(m.macd, 2)} status="bullish" hint={`MACD ${fmt(m.macd, 2)} > Signal ${fmt(m.macdSignal, 2)} — bullish crossover holding`} />
        <Indicator label="ADX (14)" value={fmt(m.adx14, 1)} status="bullish" range={[0, 60, m.adx14 / 60 * 100]} hint="Average Directional Index. Above 25 = strong trend. 28.7 confirms a developing trend." />
        <Indicator label="ATR (14)" value={`$${fmt(m.atr14, 2)}`} status="neutral" hint="Average True Range. Normal volatility for this ticker. Used to size stop distance." />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <div style={{ padding: 20, background: theme.surface2, border: `1px solid ${theme.border}`, borderRadius: theme.radius }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: theme.muted, letterSpacing: '0.12em', marginBottom: 14 }}>MOVING AVERAGES</div>
          <KV k="Price" v={`$${fmt(D.price)}`} theme={theme} vColor={theme.text} />
          <KV k="EMA 21" v={`$${fmt(m.ema21)}`} theme={theme} vColor={theme.bull} hint="Stock 3.2% above EMA21 — bullish" />
          <KV k="SMA 20" v={`$${fmt(m.sma20)}`} theme={theme} vColor={theme.bull} />
          <KV k="SMA 50" v={`$${fmt(m.sma50)}`} theme={theme} vColor={theme.bull} hint="Stock 10.5% above SMA50 — strong trend" />
          <KV k="SMA 200" v={`$${fmt(m.sma200)}`} theme={theme} vColor={theme.bull} hint="Stock 25% above SMA200 — long-term bull" />
          <KV k="VWAP" v={`$${fmt(m.vwap)}`} theme={theme} vColor={theme.bull} />
        </div>

        <div style={{ padding: 20, background: theme.surface2, border: `1px solid ${theme.border}`, borderRadius: theme.radius }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: theme.muted, letterSpacing: '0.12em', marginBottom: 14 }}>RELATIVE STRENGTH</div>
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 36, fontWeight: 800, color: theme.bull, fontFamily: 'JetBrains Mono, monospace', lineHeight: 1 }}>+34%</div>
            <div style={{ fontSize: 11, color: theme.muted, marginTop: 4 }}>vs SPY (90 days)</div>
          </div>
          <KV k="Sector rank" v="3 of 28" theme={theme} vColor={theme.bull} />
          <KV k="Industry rank" v="1 of 11" theme={theme} vColor={theme.bull} />
          <KV k="IBD RS line" v="98" theme={theme} vColor={theme.bull} hint="Top 2% of all stocks by relative strength" />
          <KV k="Beta" v={fmt(D.beta, 2)} theme={theme} hint="Higher than SPY — moves 24% more than market" />
        </div>
      </div>
    </div>
  );
}

/* ────── FUNDAMENTALS ────── */
function FundamentalsTab({ theme }) {
  const f = D.fundamentals;
  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 0, background: theme.surface2, border: `1px solid ${theme.border}`, borderRadius: theme.radius, marginBottom: 16, overflow: 'hidden' }}>
        <StatCell label="P/E (TTM)" value={fmt(f.pe, 1)} theme={theme} hint="Below industrial sector median of 26.4" />
        <StatCell label="FWD P/E" value={fmt(f.forwardPe, 1)} theme={theme} hint="Forward 12-month earnings multiple" />
        <StatCell label="PEG" value={fmt(f.pegRatio, 2)} theme={theme} hint="P/E to earnings growth — under 2 considered reasonable" color={theme.bull} />
        <StatCell label="P/S" value={fmt(f.priceToSales, 1)} theme={theme} />
        <StatCell label="P/B" value={fmt(f.priceToBook, 1)} theme={theme} />
        <StatCell label="DEBT/EQUITY" value={fmt(f.debtToEquity, 2)} theme={theme} color={theme.bull} hint="Conservative leverage" />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1.3fr 1fr', gap: 16 }}>
        <div style={{ padding: 20, background: theme.surface2, border: `1px solid ${theme.border}`, borderRadius: theme.radius }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: theme.muted, letterSpacing: '0.12em' }}>EARNINGS HISTORY</div>
            <div style={{ fontSize: 11, color: theme.bull, fontWeight: 600 }}>{f.earningsBeats}</div>
          </div>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: 'JetBrains Mono, monospace' }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${theme.divider}` }}>
                {['QTR', 'EPS EST', 'EPS ACT', 'SURPRISE', 'REV EST', 'REV ACT'].map(h => (
                  <th key={h} style={{ fontSize: 10, color: theme.muted, fontWeight: 700, padding: '8px 0', textAlign: 'left', letterSpacing: '0.08em' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {D.earnings.map(e => (
                <tr key={e.q} style={{ borderBottom: `1px solid ${theme.divider}` }}>
                  <td style={{ fontSize: 12, color: theme.text, padding: '10px 0', fontWeight: 600 }}>{e.q}</td>
                  <td style={{ fontSize: 12, color: theme.subtext, padding: '10px 0' }}>{fmt(e.epsEst)}</td>
                  <td style={{ fontSize: 12, color: theme.text, padding: '10px 0', fontWeight: 600 }}>{fmt(e.epsAct)}</td>
                  <td style={{ fontSize: 12, color: theme.bull, padding: '10px 0', fontWeight: 700 }}>+{fmt(e.surprise, 1)}%</td>
                  <td style={{ fontSize: 12, color: theme.subtext, padding: '10px 0' }}>{fmt(e.revEst)}B</td>
                  <td style={{ fontSize: 12, color: theme.text, padding: '10px 0', fontWeight: 600 }}>{fmt(e.revAct)}B</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{ marginTop: 16, padding: 12, background: theme.surface3, borderRadius: 4, fontSize: 12, color: theme.subtext }}>
            <span style={{ color: theme.accent, fontWeight: 700 }}>Next earnings: {f.nextEarnings}</span> · Implied move ±8.2% · Bias: positive based on 4-quarter trend
          </div>
        </div>

        <div style={{ padding: 20, background: theme.surface2, border: `1px solid ${theme.border}`, borderRadius: theme.radius }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: theme.muted, letterSpacing: '0.12em', marginBottom: 14 }}>QUALITY & GROWTH</div>
          <KV k="EPS growth (YoY)" v={`+${fmt(f.epsGrowth, 1)}%`} theme={theme} vColor={theme.bull} />
          <KV k="Revenue growth" v={`+${fmt(f.revenueGrowth, 1)}%`} theme={theme} vColor={theme.bull} />
          <KV k="Gross margin" v={`${fmt(f.grossMargin, 1)}%`} theme={theme} />
          <KV k="Operating margin" v={`${fmt(f.operatingMargin, 1)}%`} theme={theme} vColor={theme.bull} />
          <KV k="Net margin" v={`${fmt(f.netMargin, 1)}%`} theme={theme} />
          <KV k="ROE" v={`${fmt(f.roe, 1)}%`} theme={theme} vColor={theme.bull} hint="Return on Equity — top quartile" />
          <KV k="ROIC" v={`${fmt(f.roic, 1)}%`} theme={theme} vColor={theme.bull} />
          <KV k="FCF yield" v={`${fmt(f.fcfYield, 1)}%`} theme={theme} />
        </div>
      </div>
    </div>
  );
}

/* ────── CHART ────── */
function ChartTab({ theme, chartStyle, setChartStyle, scenario }) {
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
        <div style={{ display: 'flex', gap: 6 }}>
          {['1D', '5D', '1M', '3M', '6M', 'YTD', '1Y'].map(t => (
            <button key={t} style={{
              padding: '6px 12px', fontSize: 11, fontWeight: 600, letterSpacing: '0.05em',
              background: t === '3M' ? theme.accent : 'transparent',
              color: t === '3M' ? theme.surface : theme.subtext,
              border: `1px solid ${t === '3M' ? theme.accent : theme.border}`, borderRadius: 4,
            }}>{t}</button>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 0, border: `1px solid ${theme.border}`, borderRadius: 4, overflow: 'hidden' }}>
          {['candle', 'line'].map(s => (
            <button key={s} onClick={() => setChartStyle(s)} style={{
              padding: '6px 14px', fontSize: 11, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase',
              background: chartStyle === s ? theme.surface3 : 'transparent',
              color: chartStyle === s ? theme.text : theme.muted, border: 'none',
            }}>{s === 'candle' ? 'Candle' : 'Line'}</button>
          ))}
        </div>
      </div>

      <div style={{ padding: 16, background: theme.surface2, border: `1px solid ${theme.border}`, borderRadius: theme.radius }}>
        {chartStyle === 'candle'
          ? <CandleChart candles={D.candles} plan={D.plan} theme={theme} />
          : <StylizedChart candles={D.candles} plan={D.plan} theme={theme} />}
        <div style={{ display: 'flex', gap: 16, marginTop: 12, paddingTop: 12, borderTop: `1px solid ${theme.divider}`, fontSize: 11, color: theme.muted }}>
          <span><span style={{ display: 'inline-block', width: 12, height: 2, background: theme.bull, marginRight: 6, verticalAlign: 'middle' }} />EMA 21</span>
          <span><span style={{ display: 'inline-block', width: 12, height: 2, background: theme.line2, marginRight: 6, verticalAlign: 'middle' }} />SMA 20</span>
          <span><span style={{ display: 'inline-block', width: 12, height: 6, background: theme.bull, opacity: 0.16, marginRight: 6, verticalAlign: 'middle' }} />Entry zone</span>
          <span><span style={{ display: 'inline-block', width: 12, height: 2, background: theme.bear, marginRight: 6, verticalAlign: 'middle' }} />Stop loss</span>
        </div>
      </div>
    </div>
  );
}

/* ────── SMC ────── */
function SMCTab({ theme }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
      <div style={{ padding: 20, background: theme.surface2, border: `1px solid ${theme.border}`, borderRadius: theme.radius }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: theme.muted, letterSpacing: '0.12em', marginBottom: 14 }}>MARKET STRUCTURE</div>
        <div style={{ padding: 14, background: theme.surface3, borderRadius: 4, marginBottom: 14, borderLeft: `3px solid ${theme.bull}` }}>
          <div style={{ fontSize: 10, color: theme.muted, fontWeight: 600, letterSpacing: '0.08em', marginBottom: 4 }}>CURRENT STATE</div>
          <div style={{ fontSize: 14, color: theme.text, fontWeight: 600 }}>{D.smc.structure}</div>
        </div>
        <KV k="Trend (HTF)" v="Bullish" theme={theme} vColor={theme.bull} hint="Higher Timeframe — Daily/Weekly aligned bullish" />
        <KV k="Trend (LTF)" v="Bullish" theme={theme} vColor={theme.bull} />
        <KV k="Premium / Discount" v={D.smc.premium_discount} theme={theme} hint="Where price sits in current dealing range" />
        <KV k="Last BOS" v="244.10 ↑" theme={theme} vColor={theme.bull} hint="Break of Structure — confirms trend continuation" />
        <KV k="Last CHoCH" v="227.40 ↑" theme={theme} vColor={theme.bull} hint="Change of Character — last trend reversal point" />
      </div>

      <div style={{ padding: 20, background: theme.surface2, border: `1px solid ${theme.border}`, borderRadius: theme.radius }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: theme.muted, letterSpacing: '0.12em', marginBottom: 14 }}>ORDER BLOCKS</div>
        {D.smc.orderBlocks.map((ob, i) => (
          <div key={i} style={{ padding: 12, background: theme.surface3, borderRadius: 4, marginBottom: 10, borderLeft: `3px solid ${ob.type === 'demand' ? theme.bull : theme.bear}` }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <div>
                <span style={{ fontSize: 10, fontWeight: 700, color: ob.type === 'demand' ? theme.bull : theme.bear, letterSpacing: '0.1em' }}>
                  {ob.type === 'demand' ? '↑ DEMAND' : '↓ SUPPLY'}
                </span>
                <span style={{ fontSize: 10, color: theme.muted, marginLeft: 8 }}>· {ob.strength}</span>
              </div>
              <div style={{ fontSize: 10, color: theme.muted }}>{ob.date}</div>
            </div>
            <div style={{ fontSize: 16, fontWeight: 700, color: theme.text, fontFamily: 'JetBrains Mono, monospace', marginTop: 4 }}>
              ${ob.low} <span style={{ color: theme.muted }}>—</span> ${ob.high}
            </div>
          </div>
        ))}
      </div>

      <div style={{ padding: 20, background: theme.surface2, border: `1px solid ${theme.border}`, borderRadius: theme.radius }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: theme.muted, letterSpacing: '0.12em', marginBottom: 14 }}>FAIR VALUE GAPS</div>
        {D.smc.fvgs.map((fvg, i) => (
          <div key={i} style={{ padding: 12, background: theme.surface3, borderRadius: 4, marginBottom: 10 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 4 }}>
              <span style={{ fontSize: 10, fontWeight: 700, color: theme.text, letterSpacing: '0.08em' }}>FVG {fvg.direction.toUpperCase()}</span>
              <span style={{ fontSize: 10, fontWeight: 700, color: fvg.status === 'unfilled' ? theme.accent : theme.muted, padding: '2px 6px', background: fvg.status === 'unfilled' ? theme.accent + '22' : 'transparent', borderRadius: 2 }}>
                {fvg.status.toUpperCase()}
              </span>
            </div>
            <div style={{ fontSize: 14, fontWeight: 700, color: theme.text, fontFamily: 'JetBrains Mono, monospace' }}>
              ${fvg.low} <span style={{ color: theme.muted }}>—</span> ${fvg.high}
            </div>
          </div>
        ))}
      </div>

      <div style={{ padding: 20, background: theme.surface2, border: `1px solid ${theme.border}`, borderRadius: theme.radius }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: theme.muted, letterSpacing: '0.12em', marginBottom: 14 }}>LIQUIDITY POOLS</div>
        {D.smc.liquidity.map((l, i) => (
          <div key={i} style={{ padding: 12, background: theme.surface3, borderRadius: 4, marginBottom: 10, borderLeft: `3px solid ${l.type === 'buy-side' ? theme.accent : theme.bear}` }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <span style={{ fontSize: 10, fontWeight: 700, color: l.type === 'buy-side' ? theme.accent : theme.bear, letterSpacing: '0.1em' }}>
                {l.type === 'buy-side' ? '↑ BUY-SIDE' : '↓ SELL-SIDE'}
              </span>
              <span style={{ fontSize: 16, fontWeight: 700, color: theme.text, fontFamily: 'JetBrains Mono, monospace' }}>${l.level}</span>
            </div>
            <div style={{ fontSize: 11, color: theme.muted, marginTop: 4 }}>{l.note}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ────── NEWS & SENTIMENT ────── */
function NewsTab({ theme }) {
  const s = D.sentiment;
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1.3fr 1fr', gap: 16 }}>
      <div style={{ padding: 20, background: theme.surface2, border: `1px solid ${theme.border}`, borderRadius: theme.radius }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: theme.muted, letterSpacing: '0.12em', marginBottom: 14 }}>HEADLINES</div>
        {D.news.map((n, i) => (
          <div key={i} style={{ padding: '14px 0', borderBottom: i < D.news.length - 1 ? `1px solid ${theme.divider}` : 'none', display: 'flex', gap: 14 }}>
            <div style={{ width: 4, alignSelf: 'stretch', background: n.sentiment === 'bullish' ? theme.bull : theme.bear, borderRadius: 2 }} />
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', gap: 10, fontSize: 10, color: theme.muted, marginBottom: 6, letterSpacing: '0.05em' }}>
                <span style={{ fontWeight: 700, color: theme.subtext }}>{n.source.toUpperCase()}</span>
                <span>·</span>
                <span>{n.time}</span>
                <span>·</span>
                <span style={{ color: n.impact === 'high' ? theme.accent : theme.muted, fontWeight: 600 }}>{n.impact.toUpperCase()} IMPACT</span>
              </div>
              <div style={{ fontSize: 14, color: theme.text, lineHeight: 1.4, fontWeight: 500 }}>{n.title}</div>
            </div>
          </div>
        ))}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ padding: 20, background: theme.surface2, border: `1px solid ${theme.border}`, borderRadius: theme.radius }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: theme.muted, letterSpacing: '0.12em', marginBottom: 14 }}>ANALYST CONSENSUS</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 14 }}>
            <ScoreArc value={s.analystBuy / (s.analystBuy + s.analystHold + s.analystSell) * 100} size={86} stroke={7} color={theme.bull} bg={theme.surface3} valueColor={theme.text} label="% BUY" />
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6, color: theme.text }}>
              <div style={{ fontSize: 10, color: theme.muted }}>BUY <span style={{ float: 'right', color: theme.bull, fontFamily: 'JetBrains Mono, monospace', fontWeight: 700 }}>{s.analystBuy}</span></div>
              <div style={{ height: 4, background: theme.surface3, borderRadius: 2 }}><div style={{ width: `${s.analystBuy / 25 * 100}%`, height: '100%', background: theme.bull, borderRadius: 2 }} /></div>
              <div style={{ fontSize: 10, color: theme.muted, marginTop: 4 }}>HOLD <span style={{ float: 'right', color: theme.accent, fontFamily: 'JetBrains Mono, monospace', fontWeight: 700 }}>{s.analystHold}</span></div>
              <div style={{ height: 4, background: theme.surface3, borderRadius: 2 }}><div style={{ width: `${s.analystHold / 25 * 100}%`, height: '100%', background: theme.accent, borderRadius: 2 }} /></div>
              <div style={{ fontSize: 10, color: theme.muted, marginTop: 4 }}>SELL <span style={{ float: 'right', color: theme.bear, fontFamily: 'JetBrains Mono, monospace', fontWeight: 700 }}>{s.analystSell}</span></div>
              <div style={{ height: 4, background: theme.surface3, borderRadius: 2 }}><div style={{ width: `${s.analystSell / 25 * 100}%`, height: '100%', background: theme.bear, borderRadius: 2 }} /></div>
            </div>
          </div>
          <div style={{ paddingTop: 14, borderTop: `1px solid ${theme.divider}` }}>
            <div style={{ fontSize: 10, color: theme.muted, fontWeight: 600, letterSpacing: '0.08em' }}>AVG PRICE TARGET</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: theme.bull, fontFamily: 'JetBrains Mono, monospace', marginTop: 4 }}>${fmt(s.avgPriceTarget)}</div>
            <div style={{ fontSize: 11, color: theme.muted, marginTop: 2 }}>+{fmt((s.avgPriceTarget / D.price - 1) * 100, 1)}% upside</div>
          </div>
        </div>

        <div style={{ padding: 20, background: theme.surface2, border: `1px solid ${theme.border}`, borderRadius: theme.radius }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: theme.muted, letterSpacing: '0.12em', marginBottom: 14 }}>SOCIAL · OPTIONS</div>
          <KV k="Bullish posts" v={`${s.socialBullish}%`} theme={theme} vColor={theme.bull} />
          <KV k="Bearish posts" v={`${s.socialBearish}%`} theme={theme} vColor={theme.bear} />
          <KV k="Put/Call ratio" v={fmt(s.putCallRatio, 2)} theme={theme} vColor={theme.bull} hint="Below 0.7 = bullish options skew" />
          <KV k="Short interest" v={`${fmt(s.shortInterest, 1)}%`} theme={theme} hint="Of float — moderate" />
        </div>
      </div>
    </div>
  );
}

/* ────── TRADE PLAN ────── */
function PlanTab({ theme }) {
  const p = D.plan;
  const TargetRow = ({ n, target, rr, alloc }) => (
    <div style={{ display: 'grid', gridTemplateColumns: '60px 1fr 80px 100px', alignItems: 'center', gap: 12, padding: '12px 0', borderBottom: `1px solid ${theme.divider}` }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: theme.bull, letterSpacing: '0.1em' }}>T{n}</div>
      <div style={{ fontSize: 18, fontWeight: 700, color: theme.text, fontFamily: 'JetBrains Mono, monospace' }}>${target}</div>
      <div style={{ fontSize: 12, color: theme.bull, fontFamily: 'JetBrains Mono, monospace', fontWeight: 600 }}>{rr}R</div>
      <div style={{ fontSize: 11, color: theme.muted, textAlign: 'right' }}>Sell {alloc}</div>
    </div>
  );
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: 16 }}>
      <div style={{ padding: 20, background: theme.surface2, border: `1px solid ${theme.border}`, borderRadius: theme.radius }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: theme.muted, letterSpacing: '0.12em', marginBottom: 14 }}>EXECUTION PLAN · LONG</div>

        <div style={{ padding: 16, background: theme.surface3, borderRadius: 6, marginBottom: 16 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <div>
              <div style={{ fontSize: 10, color: theme.muted, fontWeight: 600, letterSpacing: '0.08em' }}>ENTRY</div>
              <div style={{ fontSize: 26, fontWeight: 800, color: theme.text, fontFamily: 'JetBrains Mono, monospace', marginTop: 4 }}>${p.entry}</div>
              <div style={{ fontSize: 11, color: theme.muted, marginTop: 2 }}>Zone: ${p.entryZone[0]}–${p.entryZone[1]}</div>
            </div>
            <div>
              <div style={{ fontSize: 10, color: theme.muted, fontWeight: 600, letterSpacing: '0.08em' }}>STOP LOSS</div>
              <div style={{ fontSize: 26, fontWeight: 800, color: theme.bear, fontFamily: 'JetBrains Mono, monospace', marginTop: 4 }}>${p.stop}</div>
              <div style={{ fontSize: 11, color: theme.muted, marginTop: 2 }}>−${fmt(p.entry - p.stop)} ({fmt((p.entry - p.stop) / p.entry * 100, 2)}%)</div>
            </div>
          </div>
        </div>

        <div style={{ fontSize: 10, color: theme.muted, fontWeight: 600, letterSpacing: '0.08em', marginBottom: 4 }}>TARGETS · SCALE OUT</div>
        <TargetRow n={1} target={p.target1} rr={p.rr1} alloc="33%" />
        <TargetRow n={2} target={p.target2} rr={p.rr2} alloc="33%" />
        <TargetRow n={3} target={p.target3} rr={p.rr3} alloc="34%" />

        <div style={{ marginTop: 16, padding: 12, background: theme.surface3, borderLeft: `3px solid ${theme.bear}`, borderRadius: 4 }}>
          <div style={{ fontSize: 10, color: theme.bear, fontWeight: 700, letterSpacing: '0.1em', marginBottom: 4 }}>INVALIDATION</div>
          <div style={{ fontSize: 12, color: theme.subtext, lineHeight: 1.5 }}>{p.invalidation}</div>
        </div>
      </div>

      <div style={{ padding: 20, background: theme.surface2, border: `1px solid ${theme.border}`, borderRadius: theme.radius }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: theme.muted, letterSpacing: '0.12em', marginBottom: 14 }}>POSITION SIZING</div>
        <KV k="Account size" v={`$${p.notional ? '250,000' : ''}`} theme={theme} />
        <KV k="Account risk" v={`${fmt(p.riskPctAccount, 2)}%`} theme={theme} vColor={theme.accent} hint="0.75% of account on this trade" />
        <KV k="$ at risk" v={`$${(p.riskPctAccount * 250000 / 100).toLocaleString()}`} theme={theme} vColor={theme.bear} />
        <KV k="Suggested shares" v={p.sharesSuggested.toString()} theme={theme} vColor={theme.text} />
        <KV k="Notional exposure" v={`$${p.notional.toLocaleString()}`} theme={theme} />
        <KV k="Hold duration" v={`${p.holdDays} days`} theme={theme} />

        <div style={{ marginTop: 16, padding: 14, background: theme.surface3, borderRadius: 4 }}>
          <div style={{ fontSize: 10, color: theme.muted, fontWeight: 600, letterSpacing: '0.08em', marginBottom: 8 }}>EXPECTED R MULTIPLE</div>
          <div style={{ fontSize: 32, fontWeight: 800, color: theme.bull, fontFamily: 'JetBrains Mono, monospace', lineHeight: 1 }}>+1.42R</div>
          <div style={{ fontSize: 11, color: theme.muted, marginTop: 4 }}>Based on 142 historical setups · 64.8% win rate</div>
        </div>
      </div>
    </div>
  );
}

/* ────── RISK & GREEKS ────── */
function RiskTab({ theme }) {
  const r = D.risk;
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
      <div style={{ padding: 20, background: theme.surface2, border: `1px solid ${theme.border}`, borderRadius: theme.radius }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: theme.muted, letterSpacing: '0.12em', marginBottom: 14 }}>PORTFOLIO HEAT</div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 16 }}>
          <div style={{ fontSize: 32, fontWeight: 800, color: theme.text, fontFamily: 'JetBrains Mono, monospace', lineHeight: 1 }}>{fmt(r.portfolioHeat, 1)}%</div>
          <div style={{ fontSize: 13, color: theme.muted }}>/ {fmt(r.maxHeat, 1)}% cap</div>
        </div>
        <div style={{ height: 10, background: theme.surface3, borderRadius: 5, overflow: 'hidden', marginBottom: 16 }}>
          <div style={{ width: `${(r.portfolioHeat / r.maxHeat) * 100}%`, height: '100%', background: `linear-gradient(90deg, ${theme.bull}, ${theme.accent})` }} />
        </div>
        <KV k="Account size" v={`$${r.accountSize.toLocaleString()}`} theme={theme} />
        <KV k="This trade risk" v={`$${r.positionRisk.toLocaleString()}`} theme={theme} vColor={theme.bear} />
        <KV k="VaR (95%)" v={`$${r.var95.toLocaleString()}`} theme={theme} hint="Value at Risk — 95% chance loss won't exceed this in 1 day" />
        <KV k="Expected shortfall" v={`$${r.expectedShortfall.toLocaleString()}`} theme={theme} hint="Average loss in worst 5% of cases" />
        <KV k="Kelly fraction" v={fmt(r.kellyFraction, 3)} theme={theme} hint="Optimal bet size per Kelly criterion" />
      </div>

      <div style={{ padding: 20, background: theme.surface2, border: `1px solid ${theme.border}`, borderRadius: theme.radius }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: theme.muted, letterSpacing: '0.12em', marginBottom: 14 }}>CORRELATIONS · 60D</div>
        <div style={{ fontSize: 11, color: theme.muted, marginBottom: 12, lineHeight: 1.5 }}>
          Existing positions correlated with TICKR. High correlation = position adds to existing exposure.
        </div>
        {r.correlations.map(c => {
          const pct = c.corr * 100;
          const color = c.corr > 0.7 ? theme.bear : c.corr > 0.5 ? theme.accent : theme.bull;
          return (
            <div key={c.ticker} style={{ marginBottom: 14 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <span style={{ fontSize: 13, fontWeight: 700, color: theme.text, fontFamily: 'JetBrains Mono, monospace' }}>{c.ticker}</span>
                <span style={{ fontSize: 13, fontWeight: 700, color: color, fontFamily: 'JetBrains Mono, monospace' }}>{fmt(c.corr, 2)}</span>
              </div>
              <div style={{ height: 6, background: theme.surface3, borderRadius: 3 }}>
                <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 3 }} />
              </div>
            </div>
          );
        })}
        <div style={{ marginTop: 16, padding: 12, background: theme.surface3, borderRadius: 4, fontSize: 12, color: theme.subtext, lineHeight: 1.5 }}>
          <span style={{ color: theme.accent, fontWeight: 700 }}>Suggestion:</span> RTX correlation (0.71) is high — consider reducing TICKR position by 25% if RTX position remains open.
        </div>
      </div>
    </div>
  );
}

/* ────── BACKTEST ────── */
function BacktestTab({ theme }) {
  const b = D.backtest;
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
      <div style={{ padding: 20, background: theme.surface2, border: `1px solid ${theme.border}`, borderRadius: theme.radius }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: theme.muted, letterSpacing: '0.12em', marginBottom: 6 }}>SETUP · {b.setupName.toUpperCase()}</div>
        <div style={{ fontSize: 11, color: theme.muted, marginBottom: 18 }}>Across all tickers, last 5 years</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, marginBottom: 20 }}>
          <div style={{ padding: 14, background: theme.surface3, borderRadius: 4 }}>
            <div style={{ fontSize: 10, color: theme.muted, fontWeight: 600, letterSpacing: '0.08em' }}>WIN RATE</div>
            <div style={{ fontSize: 24, fontWeight: 800, color: theme.bull, fontFamily: 'JetBrains Mono, monospace', marginTop: 4 }}>{fmt(b.winRate, 1)}%</div>
          </div>
          <div style={{ padding: 14, background: theme.surface3, borderRadius: 4 }}>
            <div style={{ fontSize: 10, color: theme.muted, fontWeight: 600, letterSpacing: '0.08em' }}>EXPECTANCY</div>
            <div style={{ fontSize: 24, fontWeight: 800, color: theme.bull, fontFamily: 'JetBrains Mono, monospace', marginTop: 4 }}>+{fmt(b.expectancy, 2)}R</div>
          </div>
          <div style={{ padding: 14, background: theme.surface3, borderRadius: 4 }}>
            <div style={{ fontSize: 10, color: theme.muted, fontWeight: 600, letterSpacing: '0.08em' }}>SAMPLES</div>
            <div style={{ fontSize: 24, fontWeight: 800, color: theme.text, fontFamily: 'JetBrains Mono, monospace', marginTop: 4 }}>{b.historical}</div>
          </div>
        </div>
        <KV k="Avg win" v={`+${fmt(b.avgWin, 2)}R`} theme={theme} vColor={theme.bull} />
        <KV k="Avg loss" v={`${fmt(b.avgLoss, 2)}R`} theme={theme} vColor={theme.bear} />
        <KV k="Avg hold" v={`${fmt(b.avgHoldDays, 1)} days`} theme={theme} />
        <KV k="Best month" v={`+${fmt(b.bestMonth, 1)}%`} theme={theme} vColor={theme.bull} />
        <KV k="Worst month" v={`${fmt(b.worstMonth, 1)}%`} theme={theme} vColor={theme.bear} />
      </div>

      <div style={{ padding: 20, background: theme.surface2, border: `1px solid ${theme.border}`, borderRadius: theme.radius }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: theme.muted, letterSpacing: '0.12em', marginBottom: 14 }}>RECENT MATCHES · TICKR</div>
        {b.similarSetups.map((s, i) => {
          const win = s.outcome.startsWith('+');
          return (
            <div key={i} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 80px', gap: 12, padding: '14px 0', borderBottom: i < b.similarSetups.length - 1 ? `1px solid ${theme.divider}` : 'none', alignItems: 'center' }}>
              <div style={{ fontSize: 12, fontFamily: 'JetBrains Mono, monospace', color: theme.subtext }}>{s.date}</div>
              <div style={{ fontSize: 16, fontFamily: 'JetBrains Mono, monospace', color: win ? theme.bull : theme.bear, fontWeight: 700 }}>{s.outcome}</div>
              <div style={{ fontSize: 11, color: theme.muted, textAlign: 'right' }}>{s.days} days</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ────── NOTES / JOURNAL ────── */
function NotesTab({ theme }) {
  const [notes, setNotes] = React.useState(D.notes);
  const [draft, setDraft] = React.useState('');
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
      <div style={{ padding: 20, background: theme.surface2, border: `1px solid ${theme.border}`, borderRadius: theme.radius }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: theme.muted, letterSpacing: '0.12em', marginBottom: 14 }}>JOURNAL · TICKR</div>
        {notes.map((n, i) => (
          <div key={i} style={{ padding: '14px 0', borderBottom: i < notes.length - 1 ? `1px solid ${theme.divider}` : 'none' }}>
            <div style={{ fontSize: 10, color: theme.muted, fontFamily: 'JetBrains Mono, monospace', letterSpacing: '0.05em', marginBottom: 6 }}>{n.date}</div>
            <div style={{ fontSize: 13, color: theme.text, lineHeight: 1.5 }}>{n.text}</div>
          </div>
        ))}
      </div>
      <div style={{ padding: 20, background: theme.surface2, border: `1px solid ${theme.border}`, borderRadius: theme.radius }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: theme.muted, letterSpacing: '0.12em', marginBottom: 14 }}>NEW ENTRY</div>
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="What's the thesis? What would invalidate? Risk size?"
          style={{
            width: '100%', minHeight: 140, padding: 12, fontFamily: 'Inter, sans-serif', fontSize: 13,
            background: theme.surface3, color: theme.text, border: `1px solid ${theme.border}`,
            borderRadius: 4, resize: 'vertical', lineHeight: 1.5,
          }}
        />
        <button
          onClick={() => {
            if (!draft.trim()) return;
            setNotes([{ date: new Date().toISOString().slice(0, 10), text: draft.trim() }, ...notes]);
            setDraft('');
          }}
          style={{
            marginTop: 12, padding: '10px 18px', fontSize: 12, fontWeight: 700,
            background: theme.accent, color: theme.surface, border: 'none', borderRadius: 4,
            letterSpacing: '0.05em',
          }}
        >SAVE ENTRY</button>
      </div>
    </div>
  );
}

Object.assign(window, {
  OverviewTab, TechnicalsTab, FundamentalsTab, ChartTab, SMCTab,
  NewsTab, PlanTab, RiskTab, BacktestTab, NotesTab,
});

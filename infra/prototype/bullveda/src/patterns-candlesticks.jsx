// patterns-candlesticks.jsx — Japanese candlestick patterns theory sub-tab.
// Detected reversal/continuation patterns with mini-glyphs, location vs S/R,
// volume confirmation, and HISTORICAL reliability (win-rate + sample) — the
// quant honesty layer that separates a real edge from chart folklore.

const { useMemo: useMemoCs } = React;

// tiny candlestick glyph (1–3 candles) drawn into a small box
function CandleGlyph({ candles, w = 44, h = 30 }) {
  const vals = candles.flatMap(c => [c.h, c.l]);
  const mn = Math.min(...vals), mx = Math.max(...vals);
  const y = v => 4 + (h - 8) * (1 - (v - mn) / ((mx - mn) || 1));
  const slot = (w - 8) / candles.length;
  const cw = Math.min(8, slot - 2);
  return (
    <svg width={w} height={h} style={{ display: "block" }}>
      {candles.map((c, i) => {
        const x = 4 + i * slot + slot / 2;
        const up = c.c >= c.o;
        const col = up ? "var(--gn)" : "var(--rd)";
        return (
          <g key={i}>
            <line x1={x} y1={y(c.h)} x2={x} y2={y(c.l)} stroke={col} strokeWidth="1" />
            <rect x={x - cw / 2} y={y(Math.max(c.o, c.c))} width={cw} height={Math.max(1.2, Math.abs(y(c.o) - y(c.c)))} fill={up ? "var(--bg-1)" : col} stroke={col} strokeWidth="1" />
          </g>
        );
      })}
    </svg>
  );
}

// canonical candle shapes per pattern
const CS_GLYPH = {
  engulf: [{ o: 8, c: 6, h: 8.6, l: 5.4 }, { o: 5.6, c: 9, h: 9.6, l: 5 }],
  hammer: [{ o: 7.4, c: 8, h: 8.4, l: 3 }],
  morning: [{ o: 9, c: 6.4, h: 9.4, l: 6 }, { o: 5.6, c: 5.8, h: 6, l: 5.2 }, { o: 6.2, c: 9, h: 9.4, l: 6 }],
  soldiers: [{ o: 4, c: 5.6, h: 5.9, l: 3.8 }, { o: 5.4, c: 7.2, h: 7.5, l: 5.2 }, { o: 7, c: 8.8, h: 9.1, l: 6.8 }],
  harami: [{ o: 9, c: 5.2, h: 9.3, l: 5 }, { o: 6.2, c: 7.2, h: 7.5, l: 6 }],
  tweezer: [{ o: 7, c: 4.2, h: 7.4, l: 3.6 }, { o: 4.6, c: 7.4, h: 7.8, l: 3.6 }],
  doji: [{ o: 6, c: 6.15, h: 9, l: 3 }],
  shooting: [{ o: 4.4, c: 4, h: 9, l: 3.8 }],
};

const CS_SIGNALS = [
  { name: "Bullish Engulfing", glyph: "engulf", kind: "Reversal ↑", date: "May 28", loc: "at $176 support", vol: "1.8× ✓", rel: 0.63, status: "CONFIRMED", tone: "gn" },
  { name: "Hammer", glyph: "hammer", kind: "Reversal ↑", date: "May 22", loc: "spring low retest", vol: "1.4× ✓", rel: 0.59, status: "CONFIRMED", tone: "gn" },
  { name: "Three White Soldiers", glyph: "soldiers", kind: "Continuation ↑", date: "May 15", loc: "off the base", vol: "1.3× ✓", rel: 0.61, status: "CONFIRMED", tone: "gn" },
  { name: "Bullish Harami", glyph: "harami", kind: "Reversal ↑", date: "May 09", loc: "mid-range", vol: "0.7× ✗", rel: 0.53, status: "WEAK", tone: "amb" },
  { name: "Doji", glyph: "doji", kind: "Indecision", date: "May 06", loc: "at resistance", vol: "0.9×", rel: 0.50, status: "NEUTRAL", tone: "ink" },
];

const CS_REL = [
  { p: "Three White Soldiers", glyph: "soldiers", wr: 0.61, n: 142, ff: "+2.1%", note: "strong with volume" },
  { p: "Bullish Engulfing", glyph: "engulf", wr: 0.63, n: 318, ff: "+1.8%", note: "best at support" },
  { p: "Morning Star", glyph: "morning", wr: 0.65, n: 96, ff: "+2.4%", note: "highest reliability" },
  { p: "Hammer", glyph: "hammer", wr: 0.59, n: 261, ff: "+1.3%", note: "needs confirmation bar" },
  { p: "Tweezer Bottom", glyph: "tweezer", wr: 0.55, n: 88, ff: "+1.0%", note: "weak alone" },
  { p: "Doji", glyph: "doji", wr: 0.50, n: 540, ff: "±0.4%", note: "context-only · no edge alone" },
];

function CsSignals({ dense }) {
  return (
    <table className={`pv-table ${dense ? "is-dense" : ""}`}>
      <thead><tr>
        <th className="label-cap"></th><th className="label-cap">Pattern</th><th className="label-cap">Type</th>
        <th className="label-cap">Location</th><th className="label-cap">Vol</th>
        <th className="label-cap" style={{ textAlign: "right" }}>Reliability</th><th className="label-cap" style={{ textAlign: "right" }}>Status</th>
      </tr></thead>
      <tbody>
        {CS_SIGNALS.map((s, i) => (
          <tr key={i}>
            <td style={{ width: 48 }}><CandleGlyph candles={CS_GLYPH[s.glyph]} /></td>
            <td><b>{s.name}</b><br /><span className="dim2 mono" style={{ fontSize: 10 }}>{s.date}</span></td>
            <td className="mono" style={{ color: `var(--${s.tone === "ink" ? "ink-2" : s.tone})`, fontSize: 11 }}>{s.kind}</td>
            <td className="dim2" style={{ fontSize: 11 }}>{s.loc}</td>
            <td className="mono" style={{ fontSize: 11 }}>{s.vol}</td>
            <td style={{ textAlign: "right" }}><ConfBar value={s.rel} tone={s.tone === "ink" ? "ink-3" : s.tone} width={44} /></td>
            <td style={{ textAlign: "right" }}><Pill tone={s.tone} small>{s.status}</Pill></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function CsReliability({ dense }) {
  return (
    <table className={`pv-table ${dense ? "is-dense" : ""}`}>
      <thead><tr>
        <th className="label-cap"></th><th className="label-cap">Pattern</th>
        <th className="label-cap" style={{ textAlign: "right" }}>Win rate</th><th className="label-cap" style={{ textAlign: "right" }}>n</th>
        <th className="label-cap" style={{ textAlign: "right" }}>Avg 5d</th><th className="label-cap">Note</th>
      </tr></thead>
      <tbody>
        {CS_REL.map((r, i) => (
          <tr key={i}>
            <td style={{ width: 48 }}><CandleGlyph candles={CS_GLYPH[r.glyph]} /></td>
            <td><b>{r.p}</b></td>
            <td style={{ textAlign: "right" }}><span className="mono" style={{ color: `var(--${r.wr >= 0.6 ? "gn" : r.wr >= 0.55 ? "amb" : "ink-2"})`, fontWeight: 700 }}>{(r.wr * 100).toFixed(0)}%</span></td>
            <td className="mono dim2" style={{ textAlign: "right" }}>{r.n}</td>
            <td className="mono up" style={{ textAlign: "right" }}>{r.ff}</td>
            <td className="dim2" style={{ fontSize: 11 }}>{r.note}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function CsStat() {
  return (
    <div className="pv-stat">
      <div className="pv-stat-cell"><div className="label-cap">Active signal</div><div className="pv-stat-v mono gn-c" style={{ color: "var(--gn)" }}>Bull Engulfing</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Location</div><div className="pv-stat-v mono">at $176 support</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Confirmation</div><div className="pv-stat-v mono up">vol 1.8× ✓</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Reliability</div><div className="pv-stat-v mono">63% · n=318</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Confidence</div><div className="pv-stat-v"><ConfBar value={0.63} tone="gn" width={72} /></div></div>
    </div>
  );
}

function CsNote() {
  return (
    <div className="pv-invalid" style={{ border: "1px solid var(--line)", background: "var(--bg-1)", margin: "0 16px 14px" }}>
      <span className="label-cap">Read</span>
      <span className="mono">Candlesticks are a <b>confirmation layer, not a signal alone</b> — a bullish engulfing at the $176 support shelf on 1.8× volume is high-quality; the same candle mid-range is noise. Always pair the glyph with location + volume, and weight by the pattern's historical win-rate.</span>
    </div>
  );
}

function CandlestickView({ ticker, dir }) {
  if (dir === "B") {
    return (
      <div className="pv-view">
        <CsStat />
        <div className="pv-split">
          <div className="pv-split-main">
            <SectionHeader n={1} title="Detected signals" sub="recent candlestick patterns · location + volume" style="minimal" />
            <div className="pv-pad"><CsSignals dense /></div>
          </div>
          <div className="pv-split-side">
            <SectionHeader n={2} title="Reliability reference" style="minimal" />
            <div className="pv-pad"><CsReliability dense /></div>
          </div>
        </div>
        <CsNote />
      </div>
    );
  }
  return (
    <div className="pv-view">
      <CsStat />
      <SectionHeader n={1} title="Detected candlestick signals" sub="pattern · location vs S/R · volume confirmation · status" style="minimal" />
      <div className="pv-pad"><CsSignals /></div>
      <SectionHeader n={2} title="Historical reliability" sub="win-rate + sample size + average 5-day follow-through — weight every glyph by its real edge" style="minimal" />
      <div className="pv-pad"><CsReliability /></div>
      <CsNote />
    </div>
  );
}

Object.assign(window, { CandlestickView });

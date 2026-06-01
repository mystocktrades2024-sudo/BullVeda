// companion-core.jsx — primitives, list, detail shell, responsive controller.
// Reads the REAL data layer (window.TICKER / WATCHLIST / LENSES / secBias / WatchStore).
const { useState, useEffect, useRef, useLayoutEffect } = React;

/* ───────────────────────── helpers ───────────────────────── */
const clamp = (n, lo = 18, hi = 96) => Math.max(lo, Math.min(hi, Math.round(n)));
const hash = (s) => { let h = 0; for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0; return Math.abs(h); };
// tone from a 0-100 score
const scoreTone = (v) => (v >= 67 ? "gn" : v >= 48 ? "amb" : "rd");
const toneVar = (t) => `var(--${t})`;
const fmt = (n, d = 2) => Number(n).toFixed(d);
const sign = (n) => (n >= 0 ? "+" : "");

// Build a full TICKER-shaped object for any scan row, so every lens renders.
function makeTicker(row) {
  const h = hash(row.sym);
  const price = row.price, s = row.score;
  const pivot = +(price * 0.992).toFixed(2);
  const stop = +(price * (0.93 + (h % 4) / 100)).toFixed(2);
  const t1 = +(price * 1.08).toFixed(2);
  const t2 = +(price * 1.16).toFixed(2);
  const risk = price - stop, reward = t1 - price;
  const sectors = ["Technology", "Healthcare", "Financials", "Energy", "Materials", "Consumer", "Industrials"];
  return {
    symbol: row.sym, name: row.name || row.sym,
    exchange: h % 2 ? "NASDAQ" : "NYSE",
    sector: row.sector || sectors[h % sectors.length], industry: "—",
    mcap: (0.6 + (h % 90) / 10) * 1e9,
    price, chg: row.chg, chgAbs: +(price * row.chg / 100).toFixed(2), prev: +(price / (1 + row.chg / 100)).toFixed(2),
    vol: (0.8 + (h % 30) / 10) * 1e6, avgVol: (0.7 + (h % 20) / 10) * 1e6,
    rsi: clamp(42 + (s - 50) * 0.6 + (h % 8), 22, 82),
    beta: +(0.7 + (h % 90) / 100).toFixed(2),
    shortFloat: +(3 + (h % 12)).toFixed(1), insiderOwn: +(2 + (h % 8)).toFixed(1),
    pe: +(14 + (h % 24)).toFixed(1), fwdPe: +(11 + (h % 18)).toFixed(1), divYield: +((h % 25) / 10).toFixed(1),
    earnings: { days: 4 + (h % 40), date: "Jun " + (2 + (h % 26)) },
    setupFamily: row.setup || "Continuation Breakout", pivot, stop, t1, t2,
    trail: "ATR(14) × 2.2", holdDays: 8 + (h % 14),
    rMultiple: +(reward / risk).toFixed(2),
    pillars: {
      technical: clamp(s + 4 + (h % 6) - 3), fundamental: clamp(s - 6 + (h % 8) - 4),
      catalyst: clamp(s - 12 + (h % 10)), risk: clamp(s - 8 + (h % 6) - 3), edge: clamp(s + 2 + (h % 5) - 2),
    },
    verdict: row.verdict, score: s,
    ml: {
      direction: +(0.5 + (s - 50) / 130).toFixed(2),
      hitNet: +((s - 52) / 160).toFixed(2),
      magnitude: { lo: -(3 + (h % 4)), mid: +(2 + (s - 50) / 14).toFixed(1), hi: +(8 + (h % 7)).toFixed(1) },
    },
    setupStats: {
      n: 28 + (h % 40), winRate: +(0.42 + s / 280).toFixed(3),
      wilsonLB: +(0.34 + s / 360).toFixed(3), pf: +(1.2 + s / 90).toFixed(2), medianR: +(0.4 + s / 260).toFixed(2),
    },
  };
}
function buildRow(sym) {
  const w = (window.WATCHLIST || []).find((x) => x.sym === sym);
  if (w) return w;
  const hm = (window.HEATMAP || []).find((x) => x[0] === sym);
  if (hm) {
    const [s, sector, , chg] = hm, h = hash(s);
    const price = +(20 + (h % 280) + (h % 100) / 100).toFixed(2);
    const score = clamp(52 + chg * 4 + (h % 8) - 4, 28, 92);
    const verdict = score >= 66 ? "BUY" : score >= 48 ? "WATCH" : "AVOID";
    return { sym: s, name: s, sector, price, chg, score, verdict, setup: "—" };
  }
  return null;
}
function resolveTicker(sym) {
  if (window.TICKER && sym === window.TICKER.symbol) return window.TICKER;
  const row = buildRow(sym);
  return row ? makeTicker(row) : window.TICKER;
}

/* ───────────────────────── icons ───────────────────────── */
const Ico = {
  chevL: <svg viewBox="0 0 24 24" fill="none" width="20" height="20"><path d="M15 5l-7 7 7 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>,
  chevR: <svg viewBox="0 0 24 24" fill="none" width="16" height="16"><path d="M9 5l7 7-7 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>,
  star: <svg viewBox="0 0 24 24" fill="none" width="18" height="18"><path d="M12 3l2.6 5.5 6 .8-4.4 4.1 1.1 5.9L12 16.9 6.7 19.3l1.1-5.9L3.4 9.3l6-.8z" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/></svg>,
  starFill: <svg viewBox="0 0 24 24" fill="currentColor" width="18" height="18"><path d="M12 3l2.6 5.5 6 .8-4.4 4.1 1.1 5.9L12 16.9 6.7 19.3l1.1-5.9L3.4 9.3l6-.8z"/></svg>,
  dots: <svg viewBox="0 0 24 24" fill="currentColor" width="18" height="18"><circle cx="5" cy="12" r="1.9"/><circle cx="12" cy="12" r="1.9"/><circle cx="19" cy="12" r="1.9"/></svg>,
  bell: <svg viewBox="0 0 24 24" fill="none" width="18" height="18"><path d="M18 8a6 6 0 10-12 0c0 7-3 8-3 8h18s-3-1-3-8" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/><path d="M13.7 21a2 2 0 01-3.4 0" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/></svg>,
  copy: <svg viewBox="0 0 24 24" fill="none" width="18" height="18"><rect x="9" y="9" width="11" height="11" rx="2" stroke="currentColor" strokeWidth="1.7"/><path d="M5 15V5a2 2 0 012-2h10" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/></svg>,
  ext: <svg viewBox="0 0 24 24" fill="none" width="18" height="18"><path d="M14 4h6v6M20 4l-9 9" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/><path d="M18 14v4a2 2 0 01-2 2H6a2 2 0 01-2-2V8a2 2 0 012-2h4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/></svg>,
  check: <svg viewBox="0 0 24 24" fill="none" width="16" height="16"><path d="M5 12l4.5 4.5L19 7" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"/></svg>,
  bolt: <svg viewBox="0 0 24 24" fill="currentColor" width="12" height="12"><path d="M13 2L4 14h6l-1 8 9-12h-6z"/></svg>,
  share: <svg viewBox="0 0 24 24" fill="none" width="18" height="18"><circle cx="18" cy="5" r="2.6" stroke="currentColor" strokeWidth="1.7"/><circle cx="6" cy="12" r="2.6" stroke="currentColor" strokeWidth="1.7"/><circle cx="18" cy="19" r="2.6" stroke="currentColor" strokeWidth="1.7"/><path d="M8.3 10.7l7.4-4.4M8.3 13.3l7.4 4.4" stroke="currentColor" strokeWidth="1.7"/></svg>,
  search: <svg viewBox="0 0 24 24" fill="none" width="46" height="46"><circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="1.6"/><path d="M16.5 16.5L21 21" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/></svg>,
};

/* ───────────────────────── primitives ───────────────────────── */
function GaugeRing({ value, size = 92, stroke = 6, tone }) {
  const t = tone || scoreTone(value);
  const r = (size - stroke) / 2, c = 2 * Math.PI * r, off = c * (1 - value / 100);
  return (
    <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="var(--bg-4)" strokeWidth={stroke} />
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={toneVar(t)} strokeWidth={stroke}
        strokeDasharray={c} strokeDashoffset={off} strokeLinecap="round"
        style={{ transition: "stroke-dashoffset .6s cubic-bezier(.2,.8,.2,1)" }} />
    </svg>
  );
}

function SecBadge({ verdict }) {
  const label = window.secBias(verdict), tone = window.secBiasTone(verdict);
  return <span className={`cmp-bias bg-${tone}`}><i/>{label}</span>;
}

function Pillars({ pillars }) {
  return (
    <div className="cmp-pillars">
      {Object.entries(pillars).map(([k, v]) => (
        <div className="cmp-pill-row" key={k}>
          <span className="cmp-pill-label">{k}</span>
          <span className="cmp-pill-track"><i className="cmp-pill-fill" style={{ width: v + "%", background: toneVar(scoreTone(v)) }} /></span>
          <span className="cmp-pill-val mono">{v}</span>
        </div>
      ))}
    </div>
  );
}

function Sec({ n, title, sub, children }) {
  return (
    <section className="cmp-sec">
      <div className="cmp-sec-hd">
        {n != null && <span className="cmp-sec-n mono">{String(n).padStart(2, "0")}</span>}
        <span className="cmp-sec-title">{title}</span>
        {sub && <span className="cmp-sec-sub">{sub}</span>}
      </div>
      {children}
    </section>
  );
}
const Panel = ({ children, style }) => <div className="cmp-panel" style={style}>{children}</div>;

function KpiGrid({ cols = 2, items }) {
  return (
    <div className={`cmp-kpis cmp-kpis-${cols}`}>
      {items.map((it, i) => (
        <div className="cmp-kpi" key={i}>
          <div className="cmp-kpi-l">{it.label}</div>
          <div className="cmp-kpi-v" style={{ color: it.tone ? toneVar(it.tone) : undefined }}>{it.value}</div>
          {it.sub && <div className="cmp-kpi-s">{it.sub}</div>}
        </div>
      ))}
    </div>
  );
}

const Chip = ({ tone = "amb", children }) => <span className={`cmp-chip bg-${tone}`}>{children}</span>;

function Row({ name, sub, value, valTone, chip, chipTone, meter, meterTone }) {
  return (
    <div className="cmp-row">
      <div className="cmp-row-l">
        <div className="cmp-row-name">{name}</div>
        {sub && <div className="cmp-row-sub">{sub}</div>}
        {meter != null && <div className="cmp-meter"><i style={{ width: meter + "%", background: toneVar(meterTone || scoreTone(meter)) }} /></div>}
      </div>
      {value != null && <div className="cmp-row-v" style={{ color: valTone ? toneVar(valTone) : undefined }}>{value}</div>}
      {chip && <Chip tone={chipTone}>{chip}</Chip>}
    </div>
  );
}

function Read({ mode, children }) {
  return <div className="cmp-read"><span className="cmp-cap">The Read{mode ? " · " + mode : ""}</span>{children}</div>;
}

// implied-move cone
function Cone({ lo, mid, hi }) {
  const span = Math.max(Math.abs(lo), Math.abs(hi)) * 1.15;
  const x = (v) => 50 + (v / span) * 48;
  return (
    <div className="cmp-cone">
      <svg viewBox="0 0 100 56" preserveAspectRatio="none">
        <defs><linearGradient id="cmpcone" x1="0" x2="1"><stop offset="0" stopColor="var(--rd)" stopOpacity="0.5"/><stop offset="0.5" stopColor="var(--amb)" stopOpacity="0.5"/><stop offset="1" stopColor="var(--gn)" stopOpacity="0.5"/></linearGradient></defs>
        <polygon points={`50,28 ${x(hi)},6 ${x(hi)},50`} fill="var(--gn-bg)"/>
        <polygon points={`50,28 ${x(lo)},6 ${x(lo)},50`} fill="var(--rd-bg)"/>
        <line x1="50" y1="4" x2="50" y2="52" stroke="var(--ink-4)" strokeWidth="1" strokeDasharray="2 2"/>
        <line x1={x(lo)} y1="28" x2={x(hi)} y2="28" stroke="url(#cmpcone)" strokeWidth="2.5"/>
        <circle cx={x(mid)} cy="28" r="3.4" fill="var(--copper)"/>
        <circle cx={x(lo)} cy="28" r="2.4" fill="var(--rd)"/>
        <circle cx={x(hi)} cy="28" r="2.4" fill="var(--gn)"/>
      </svg>
    </div>
  );
}

function StatStrip({ items }) {
  return (
    <div className="cmp-statstrip">
      {items.map((it, i) => (
        <div key={i}><div className="v mono" style={{ color: it.tone ? toneVar(it.tone) : undefined }}>{it.v}</div><div className="l">{it.l}</div></div>
      ))}
    </div>
  );
}

function Sparkbars({ data, baseline = 0 }) {
  const max = Math.max(...data.map(Math.abs), 1);
  return (
    <div className="cmp-sparkbars">
      {data.map((v, i) => <i key={i} style={{ height: (Math.abs(v) / max) * 100 + "%", background: toneVar(v >= baseline ? "gn" : "rd") }} />)}
    </div>
  );
}

Object.assign(window, {
  cmpHelpers: { clamp, hash, scoreTone, toneVar, fmt, sign, resolveTicker, buildRow },
  GaugeRing, SecBadge, Pillars, Sec, Panel, KpiGrid, Chip, Row, Read, Cone, StatStrip, Sparkbars, Ico,
});

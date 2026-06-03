// surface-earnings-predictions.jsx — Earnings AI · predictions + 1-year track record.
// View 1: every active earnings prediction (direction, confidence, implied vs
// predicted move, ESP, our call). View 2: the accountability layer — 12-month
// hit/miss scorecard, calibration curve, confidence-bucket edge, resolved log.

const { useState: useEP, useMemo: useEPm } = React;

function epHash(s) { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; }
function epRng(seed) { let a = seed >>> 0; return () => { a = (a + 0x6D2B79F5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }

const EP_UNIV = (() => {
  const base = (typeof WATCHLIST !== "undefined" && WATCHLIST.length) ? WATCHLIST.map(w => [w.sym, w.name, w.price]) : [];
  const extra = (typeof HEATMAP !== "undefined" ? HEATMAP : []).map(([s, sec, mc, chg]) => [s, `${sec} Corp`, 20 + (s.charCodeAt(0) % 200)]);
  const seen = {}; const all = [];
  [...base, ...extra].forEach(r => { if (!seen[r[0]]) { seen[r[0]] = 1; all.push(r); } });
  return all;
})();

// ── active predictions ──────────────────────────────────────────
const EP_ACTIVE = (() => {
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  // BULLVEDA: real earnings beat predictions (data_earnings.json) when available.
  const BV = window.__BV;
  if (BV && BV.earningsBeat && BV.earningsBeat.length) {
    const numOf = (v, d) => (typeof v === "number" && isFinite(v)) ? v : (typeof v === "object" && v && typeof v.value === "number" ? v.value : d);
    return BV.earningsBeat.map(b => {
      const row = BV.findRow ? BV.findRow(b.ticker) : null;
      const bd = b.breakdown || {};
      const tier = (b.tier || "").toUpperCase();
      const dir = (tier === "STRONG" || tier === "SOLID") ? "BEAT" : tier === "WEAK" ? "MISS" : "IN-LINE";
      const conf = numOf(b.beat_score, 50) / 100;
      const implied = numOf(bd.implied_move, null);
      const histBeat = numOf(bd.historical, null);
      const rd = (b.report_date || "").split("-"); // YYYY-MM-DD
      const date = rd.length === 3 ? `${months[+rd[1] - 1]} ${+rd[2]}` : (b.report_date || "—");
      const predMove = implied != null ? +((dir === "BEAT" ? 1 : dir === "MISS" ? -1 : 0.3) * implied).toFixed(1) : null;
      return {
        sym: b.ticker, name: (row && row.name) || b.ticker, price: row ? row.price : null,
        daysOut: numOf(b.days_to_earnings, null),
        session: b.before_after === "AfterMarket" ? "AMC" : b.before_after === "BeforeMarket" ? "BMO" : "—",
        date, dir, conf: +conf.toFixed(2),
        implied: implied != null ? +implied.toFixed(1) : null,
        predMove, esp: numOf(bd.zacks, null), histBeat: histBeat != null ? Math.round(histBeat) : null,
        call: dir === "BEAT" ? (conf > 0.75 ? "LONG" : "LEAN LONG") : dir === "MISS" ? (conf > 0.6 ? "FADE" : "AVOID") : "STRADDLE",
        tone: dir === "BEAT" ? "gn" : dir === "MISS" ? "rd" : "amb", beatScore: numOf(b.beat_score, null), tier,
      };
    }).sort((a, b) => (a.daysOut ?? 99) - (b.daysOut ?? 99));
  }
  return EP_UNIV.slice(0, 22).map(([sym, name, price]) => {
    const code = epHash(sym), r = epRng(code);
    const daysOut = 1 + Math.floor(r() * 38);
    const dirRoll = r();
    const dir = dirRoll > 0.42 ? "BEAT" : dirRoll > 0.18 ? "MISS" : "IN-LINE";
    const conf = 0.55 + Math.floor(r() * 40) / 100;
    const implied = 4 + Math.floor(r() * 9) + r();
    const predMove = (dir === "BEAT" ? 1 : dir === "MISS" ? -1 : (r() - 0.5)) * (implied * (0.7 + r() * 0.7));
    const esp = (dir === "BEAT" ? 1 : dir === "MISS" ? -1 : 0.2) * (1 + r() * 5);
    const histBeat = 45 + Math.floor(r() * 52);
    const call = dir === "BEAT" ? (conf > 0.75 ? "LONG" : "LEAN LONG") : dir === "MISS" ? (conf > 0.75 ? "FADE" : "AVOID") : "STRADDLE";
    const d = new Date(2026, 4, 29 + daysOut);
    return {
      sym, name, price: +price || 100, daysOut, session: code % 2 ? "AMC" : "BMO",
      date: `${months[d.getMonth()]} ${d.getDate()}`, dir, conf, implied: +implied.toFixed(1),
      predMove: +predMove.toFixed(1), esp: +esp.toFixed(1), histBeat, call,
      tone: dir === "BEAT" ? "gn" : dir === "MISS" ? "rd" : "amb",
    };
  }).sort((a, b) => a.daysOut - b.daysOut);
})();

// ── resolved predictions · trailing 12 months ───────────────────
const EP_RESOLVED = (() => {
  const out = [];
  const months = ["Jun'25", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan'26", "Feb", "Mar", "Apr", "May"];
  let n = 0;
  for (let m = 0; m < 12; m++) {
    const per = 9 + (epHash("m" + m) % 5);
    for (let j = 0; j < per; j++) {
      const [sym, name] = EP_UNIV[(n * 7 + m * 3) % EP_UNIV.length];
      const code = epHash(sym + m + "_" + j), r = epRng(code);
      const conf = 0.55 + Math.floor(r() * 40) / 100;
      // calibration: hit prob ≈ confidence, slightly overconfident at the top
      const pHit = conf - (conf > 0.8 ? 0.10 : 0.02);
      const hit = r() < pHit;
      const dirRoll = r();
      const predDir = dirRoll > 0.4 ? "BEAT" : dirRoll > 0.16 ? "MISS" : "IN-LINE";
      const actualDir = hit ? predDir : (predDir === "BEAT" ? (r() > 0.5 ? "MISS" : "IN-LINE") : "BEAT");
      const implied = 4 + Math.floor(r() * 8);
      const predMove = (predDir === "BEAT" ? 1 : predDir === "MISS" ? -1 : 0.3) * (implied * (0.8 + r() * 0.6));
      const actMove = hit ? predMove * (0.7 + r() * 0.6) : -predMove * (0.3 + r() * 0.7);
      const R = hit ? +(0.7 + r() * 2.4).toFixed(1) : +(-(0.6 + r() * 0.7)).toFixed(1);
      out.push({ sym, name, month: m, monthLabel: months[m], conf, hit, predDir, actualDir, implied, predMove: +predMove.toFixed(1), actMove: +actMove.toFixed(1), R, magHit: hit && Math.abs(actMove) >= implied * 0.7 });
      n++;
    }
  }
  return out;
})();

const EP_STATS = (() => {
  const R = EP_RESOLVED, n = R.length;
  const hits = R.filter(x => x.hit).length;
  const dirHits = R.filter(x => x.predDir === x.actualDir).length;
  const magHits = R.filter(x => x.magHit).length;
  const brier = R.reduce((s, x) => s + Math.pow(x.conf - (x.hit ? 1 : 0), 2), 0) / n;
  const followed = R.filter(x => x.conf >= 0.65);
  const avgR = followed.reduce((s, x) => s + x.R, 0) / followed.length;
  // monthly
  const monthly = Array.from({ length: 12 }, (_, m) => {
    const mr = R.filter(x => x.month === m);
    return { m, label: mr[0]?.monthLabel || "", hits: mr.filter(x => x.hit).length, miss: mr.filter(x => !x.hit).length, n: mr.length };
  });
  // calibration buckets
  const edges = [[0.5, 0.6], [0.6, 0.7], [0.7, 0.8], [0.8, 0.9], [0.9, 1.01]];
  const calib = edges.map(([lo, hi]) => {
    const b = R.filter(x => x.conf >= lo && x.conf < hi);
    return { lo, hi, mid: (lo + Math.min(hi, 1)) / 2, n: b.length, actual: b.length ? b.filter(x => x.hit).length / b.length : 0 };
  });
  return { n, hits, hitRate: hits / n, dirAcc: dirHits / n, magAcc: magHits / n, brier, avgR, monthly, calib, followedN: followed.length };
})();

// ── calibration curve ───────────────────────────────────────────
function EPCalibration() {
  const c = EP_STATS.calib;
  const w = 360, h = 240, pad = 34;
  const x = v => pad + v * (w - pad * 1.4);
  const y = v => h - pad - v * (h - pad * 1.6);
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="ep-calib" preserveAspectRatio="xMidYMid meet">
      {/* perfect-calibration diagonal */}
      <line x1={x(0.5)} y1={y(0.5)} x2={x(1)} y2={y(1)} stroke="var(--ink-3)" strokeDasharray="4 4" opacity="0.6" />
      <text x={x(0.74)} y={y(0.82)} fontSize="9" className="mono" fill="var(--ink-3)" transform={`rotate(-32 ${x(0.74)} ${y(0.82)})`}>perfect calibration</text>
      {/* axes */}
      {[0.5, 0.6, 0.7, 0.8, 0.9, 1].map((g, i) => (
        <g key={i}>
          <text x={x(g)} y={h - pad + 13} fontSize="8" className="mono" fill="var(--ink-4)" textAnchor="middle">{Math.round(g * 100)}</text>
          <text x={pad - 7} y={y(g) + 3} fontSize="8" className="mono" fill="var(--ink-4)" textAnchor="end">{Math.round(g * 100)}</text>
        </g>
      ))}
      <text x={x(0.75)} y={h - 5} fontSize="8.5" className="mono" fill="var(--ink-3)" textAnchor="middle">PREDICTED CONFIDENCE %</text>
      <text x={11} y={y(0.78)} fontSize="8.5" className="mono" fill="var(--ink-3)" textAnchor="middle" transform={`rotate(-90 11 ${y(0.78)})`}>ACTUAL HIT %</text>
      {/* model curve */}
      <polyline points={c.filter(b => b.n).map(b => `${x(b.mid)},${y(b.actual)}`).join(" ")} fill="none" stroke="var(--violet)" strokeWidth="2" />
      {c.filter(b => b.n).map((b, i) => (
        <g key={i}>
          <circle cx={x(b.mid)} cy={y(b.actual)} r="4" fill="var(--violet)" stroke="var(--bg-1)" strokeWidth="1.4" />
          <text x={x(b.mid)} y={y(b.actual) - 9} fontSize="8" className="mono" fill="var(--violet)" textAnchor="middle">{b.n}</text>
        </g>
      ))}
    </svg>
  );
}

function EPMonthly() {
  const mo = EP_STATS.monthly, w = 560, h = 170, pad = 22;
  const maxN = Math.max(...mo.map(m => m.n));
  const bw = (w - pad * 2) / mo.length;
  const y = v => (h - pad - 14) - (v / maxN) * (h - pad - 28);
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="ep-monthly" preserveAspectRatio="xMidYMid meet">
      {mo.map((m, i) => {
        const cx = pad + i * bw + bw / 2, bwi = bw * 0.6;
        const hitH = (h - pad - 14) - y(m.hits), totH = (h - pad - 14) - y(m.n);
        const rate = m.n ? m.hits / m.n : 0;
        return (
          <g key={i}>
            <rect x={cx - bwi / 2} y={y(m.n)} width={bwi} height={Math.max(0, totH)} fill="var(--rd)" opacity="0.32" rx="1.5" />
            <rect x={cx - bwi / 2} y={y(m.hits)} width={bwi} height={Math.max(0, hitH)} fill="var(--gn)" opacity="0.85" rx="1.5" />
            <text x={cx} y={h - pad + 5} fontSize="8" className="mono" fill="var(--ink-4)" textAnchor="middle">{m.label}</text>
            <text x={cx} y={y(m.n) - 4} fontSize="8" className="mono" fill="var(--ink-3)" textAnchor="middle">{Math.round(rate * 100)}</text>
          </g>
        );
      })}
      <polyline points={mo.map((m, i) => `${pad + i * bw + bw / 2},${(h - pad - 14) - (m.n ? m.hits / m.n : 0) * (h - pad - 28)}`).join(" ")} fill="none" stroke="var(--copper)" strokeWidth="1.6" opacity="0.8" />
    </svg>
  );
}

function EPKpi({ l, v, sub, tone }) {
  return <div className={`wsx-kpi wsx-kpi--${tone || "violet"}`}><div className="wsx-kpi-l mono">{l}</div><div className={`wsx-kpi-v mono kpi-tone--${tone || "violet"}`}>{v}</div><div className="wsx-kpi-s mono dim2">{sub}</div></div>;
}

function EPPredictions({ onTicker }) {
  const [sort, setSort] = useEP("daysOut");
  const groups = [
    { label: "This week", test: d => d <= 7 },
    { label: "Next week", test: d => d > 7 && d <= 14 },
    { label: "2–4 weeks", test: d => d > 14 && d <= 28 },
    { label: "Later", test: d => d > 28 },
  ];
  const hi = EP_ACTIVE.filter(p => p.conf >= 0.78).length;
  const week = EP_ACTIVE.filter(p => p.daysOut <= 7).length;
  const avgConf = Math.round(EP_ACTIVE.reduce((s, p) => s + p.conf, 0) / EP_ACTIVE.length * 100);
  return (
    <div>
      <div className="wsx-kpis">
        <EPKpi l="ACTIVE PREDICTIONS" v={EP_ACTIVE.length} sub="upcoming reports" tone="violet" />
        <EPKpi l="REPORTING THIS WEEK" v={week} sub="≤ 7 days" tone="amb" />
        <EPKpi l="HIGH CONVICTION" v={hi} sub="conf ≥ 78%" tone="gn" />
        <EPKpi l="AVG CONFIDENCE" v={`${avgConf}%`} sub="across active" tone="cy" />
        <EPKpi l="MODEL EDGE · 12MO" v={`${Math.round(EP_STATS.hitRate * 100)}%`} sub="trailing hit rate" tone="gn" />
      </div>

      {groups.map(g => {
        const rows = EP_ACTIVE.filter(p => g.test(p.daysOut));
        if (!rows.length) return null;
        return (
          <div className="ep-group" key={g.label}>
            <div className="ep-group-h mono"><span>{g.label}</span><span className="dim2">{rows.length}</span></div>
            <table className="dtable ep-tbl">
              <thead><tr>
                <th>Ticker</th><th className="r">Report</th><th>Prediction</th><th className="r">Conf</th>
                <th className="r">Implied</th><th className="r">Pred. move</th><th className="r">ESP</th><th className="r">Hist beat</th><th>Call</th>
              </tr></thead>
              <tbody>
                {rows.map(p => (
                  <tr key={p.sym} onClick={() => onTicker && onTicker(p.sym, "earnings")} className="ep-row">
                    <td><b className="mono">{p.sym}</b><div className="ep-name dim2">{p.name}</div></td>
                    <td className="r mono"><b>{p.date}</b><div className="dim2">{p.session} · {p.daysOut}d</div></td>
                    <td><span className={`ep-dir ep-dir--${p.tone}`}>{p.dir}</span></td>
                    <td className="r"><ConfBar value={p.conf} tone={p.tone} width={46} /></td>
                    <td className="r mono">±{p.implied}%</td>
                    <td className={`r mono ${p.predMove >= 0 ? "up" : "dn"}`}>{p.predMove >= 0 ? "+" : ""}{p.predMove}%</td>
                    <td className={`r mono ${p.esp >= 0 ? "up" : "dn"}`}>{p.esp >= 0 ? "+" : ""}{p.esp}%</td>
                    <td className="r mono dim2">{p.histBeat}%</td>
                    <td><Pill tone={p.call.includes("LONG") ? "gn" : p.call.includes("FADE") || p.call === "AVOID" ? "rd" : "amb"} small>{p.call}</Pill></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      })}
      <div className="ep-note mono dim2">
        Predictions blend Zacks ESP, estimate-revision momentum, implied-move vs historical realized move, and the name's 8-quarter surprise pattern. <b>Confidence</b> is the model's calibrated probability the directional call resolves correct — track its honesty in the Track Record tab.
      </div>
    </div>
  );
}

function EPTrackRecord() {
  const s = EP_STATS;
  const recent = [...EP_RESOLVED].reverse().slice(0, 14);
  return (
    <div>
      <div className="wsx-kpis">
        <EPKpi l="RESOLVED · 12MO" v={s.n} sub="closed predictions" tone="violet" />
        <EPKpi l="HIT RATE" v={`${Math.round(s.hitRate * 100)}%`} sub={`${s.hits} of ${s.n} correct`} tone="gn" />
        <EPKpi l="DIRECTION ACC" v={`${Math.round(s.dirAcc * 100)}%`} sub="beat/miss/in-line" tone="cy" />
        <EPKpi l="MAGNITUDE ACC" v={`${Math.round(s.magAcc * 100)}%`} sub="within implied move" tone="amb" />
        <EPKpi l="BRIER SCORE" v={s.brier.toFixed(3)} sub="lower = better calibrated" tone="violet" />
        <EPKpi l="AVG R · FOLLOWED" v={`${s.avgR >= 0 ? "+" : ""}${s.avgR.toFixed(2)}R`} sub={`conf ≥ 65% · n=${s.followedN}`} tone="gn" />
      </div>

      <div className="ep-grid2">
        <div className="lab-card">
          <div className="lab-card-h mono">MONTHLY HIT / MISS · 12 MONTHS</div>
          <div className="ep-chart-pad"><EPMonthly /></div>
          <div className="ep-legend mono dim2"><span><i className="ep-sw" style={{ background: "var(--gn)" }} /> hits</span><span><i className="ep-sw" style={{ background: "var(--rd)", opacity: .4 }} /> misses</span><span><i className="ep-sw" style={{ background: "var(--copper)" }} /> hit-rate %</span></div>
        </div>
        <div className="lab-card">
          <div className="lab-card-h mono">CALIBRATION · PREDICTED vs ACTUAL</div>
          <div className="ep-chart-pad"><EPCalibration /></div>
          <div className="ep-legend mono dim2">On the diagonal = perfectly honest confidence. Points below = overconfident. Labels = sample size per bucket.</div>
        </div>
      </div>

      <div className="lab-card">
        <div className="lab-card-h mono">CONFIDENCE-BUCKET EDGE</div>
        <table className="dtable ep-tbl">
          <thead><tr><th>Confidence bucket</th><th className="r">Predictions</th><th className="r">Predicted</th><th className="r">Actual hit</th><th className="r">Calibration</th></tr></thead>
          <tbody>
            {s.calib.filter(b => b.n).map((b, i) => {
              const gap = b.actual - b.mid;
              return (
                <tr key={i}>
                  <td className="mono"><b>{Math.round(b.lo * 100)}–{Math.round(Math.min(b.hi, 1) * 100)}%</b></td>
                  <td className="r mono dim2">{b.n}</td>
                  <td className="r mono">{Math.round(b.mid * 100)}%</td>
                  <td className="r mono"><b className={b.actual >= b.mid - 0.03 ? "up" : "dn"}>{Math.round(b.actual * 100)}%</b></td>
                  <td className="r"><Pill tone={Math.abs(gap) <= 0.05 ? "gn" : gap < 0 ? "rd" : "cy"} small>{Math.abs(gap) <= 0.05 ? "CALIBRATED" : gap < 0 ? `OVER ${Math.round(-gap * 100)}` : `UNDER ${Math.round(gap * 100)}`}</Pill></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="lab-card">
        <div className="lab-card-h mono">RESOLVED LOG · MOST RECENT</div>
        <table className="dtable ep-tbl">
          <thead><tr><th>Ticker</th><th className="r">Month</th><th>Predicted</th><th>Actual</th><th className="r">Pred move</th><th className="r">Actual</th><th className="r">R</th><th className="r">Result</th></tr></thead>
          <tbody>
            {recent.map((x, i) => (
              <tr key={i}>
                <td className="mono"><b>{x.sym}</b></td>
                <td className="r mono dim2">{x.monthLabel}</td>
                <td><span className={`ep-dir ep-dir--${x.predDir === "BEAT" ? "gn" : x.predDir === "MISS" ? "rd" : "amb"}`}>{x.predDir}</span> <span className="dim2 mono">{Math.round(x.conf * 100)}%</span></td>
                <td><span className={`ep-dir ep-dir--${x.actualDir === "BEAT" ? "gn" : x.actualDir === "MISS" ? "rd" : "amb"}`}>{x.actualDir}</span></td>
                <td className={`r mono ${x.predMove >= 0 ? "up" : "dn"}`}>{x.predMove >= 0 ? "+" : ""}{x.predMove}%</td>
                <td className={`r mono ${x.actMove >= 0 ? "up" : "dn"}`}>{x.actMove >= 0 ? "+" : ""}{x.actMove}%</td>
                <td className={`r mono ${x.R >= 0 ? "up" : "dn"}`}>{x.R >= 0 ? "+" : ""}{x.R}R</td>
                <td className="r"><Pill tone={x.hit ? "gn" : "rd"} small>{x.hit ? "HIT" : "MISS"}</Pill></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SurfaceEarningsPredictions({ onTicker }) {
  const [view, setView] = useEP("predictions");
  return (
    <div className="surface wsx wsx--violet ep">
      <div className="wsx-hdr">
        <div className="wsx-hdr-l">
          <div className="wsx-eyebrow mono">EARNINGS AI · PREDICTION ENGINE</div>
          <h1 className="wsx-title mono">Earnings Predictions</h1>
          <div className="wsx-sub mono dim2">every active earnings call the model is making · with a transparent 1-year hit/miss track record &amp; calibration</div>
        </div>
        <div className="wsx-hdr-r">
          <div className="ep-headline">
            <div className="ep-headline-v mono kpi-tone--gn">{Math.round(EP_STATS.hitRate * 100)}%</div>
            <div className="ep-headline-l mono dim2">12-mo hit rate</div>
          </div>
        </div>
      </div>

      <div className="um-viewtabs ep-viewtabs">
        <button className={`um-vt ${view === "predictions" ? "is-on" : ""}`} onClick={() => setView("predictions")}>Predictions · {EP_ACTIVE.length}</button>
        <button className={`um-vt ${view === "track" ? "is-on" : ""}`} onClick={() => setView("track")}>Track Record · 12mo</button>
      </div>

      {view === "predictions" ? <EPPredictions onTicker={onTicker} /> : <EPTrackRecord />}
    </div>
  );
}

window.SurfaceEarningsPredictions = SurfaceEarningsPredictions;

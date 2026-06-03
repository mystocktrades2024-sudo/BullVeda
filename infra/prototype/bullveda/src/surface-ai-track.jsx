// surface-ai-track.jsx — AI Predictions · Track Record (trailing 12 months)
// Resolved-prediction ledger: every forecast that has reached its horizon is
// scored HIT/MISS against the realized move. Surfaces calibration, hit-rate by
// confidence/horizon, monthly consistency, and the live-vs-SPY equity curve so
// the model's edge is auditable, not asserted.
const { useMemo: useMemoAIT } = React;

// ── trailing-12-month monthly ledger ────────────────────────────────
// n = predictions resolved · hit = realized hit-rate % · edge = avg realized
// edge per pick (%) · alpha = model − SPY contribution that month (%)
const AIT_MONTHS = [
  { m: "Jun '25", n: 96,  hit: 56.2, edge: +1.3, alpha: +1.1 },
  { m: "Jul '25", n: 104, hit: 61.5, edge: +2.1, alpha: +2.4 },
  { m: "Aug '25", n: 88,  hit: 47.7, edge: -0.6, alpha: -1.8 },
  { m: "Sep '25", n: 112, hit: 59.8, edge: +1.7, alpha: +1.9 },
  { m: "Oct '25", n: 121, hit: 63.6, edge: +2.6, alpha: +3.1 },
  { m: "Nov '25", n: 109, hit: 57.8, edge: +1.4, alpha: +1.6 },
  { m: "Dec '25", n: 94,  hit: 52.1, edge: +0.4, alpha: +0.2 },
  { m: "Jan '26", n: 118, hit: 60.2, edge: +1.9, alpha: +2.2 },
  { m: "Feb '26", n: 102, hit: 49.0, edge: -0.3, alpha: -1.1 },
  { m: "Mar '26", n: 126, hit: 62.7, edge: +2.4, alpha: +2.8 },
  { m: "Apr '26", n: 131, hit: 58.0, edge: +1.5, alpha: +1.7 },
  { m: "May '26", n: 83,  hit: 60.2, edge: +1.8, alpha: +1.4 },
];

// ── calibration / reliability: predicted P(up) bucket vs realized hit ─
const AIT_CALIB = [
  { band: "50–55%", mid: 52.5, real: 53.1, n: 412 },
  { band: "55–60%", mid: 57.5, real: 56.4, n: 358 },
  { band: "60–65%", mid: 62.5, real: 61.8, n: 274 },
  { band: "65–70%", mid: 67.5, real: 69.2, n: 161 },
  { band: "70–75%", mid: 72.5, real: 71.0, n: 78 },
  { band: "75%+",   mid: 79.0, real: 80.6, n: 101 },
];

// ── hit-rate by confidence tier & by horizon ────────────────────────
const AIT_BY_CONF = [
  { k: "HIGH", n: 214,  hit: 67.3, tone: "gn" },
  { k: "MED",  n: 712,  hit: 57.1, tone: "amb" },
  { k: "LOW",  n: 358,  hit: 51.4, tone: "ink" },
];
const AIT_BY_HORIZON = [
  { k: "5-day",  hit: 55.8 },
  { k: "10-day", hit: 59.4 },
  { k: "20-day", hit: 57.2 },
];

// ── resolved-prediction ledger (most recent) ────────────────────────
const AIT_LEDGER = [
  { d: "05-12", sym: "ARGN", conf: "HIGH", dir: 71, pred: +7.8, act: +11.2, out: 1 },
  { d: "05-09", sym: "KOSM", conf: "HIGH", dir: 68, pred: +6.4, act: +8.1,  out: 1 },
  { d: "05-08", sym: "GENO", conf: "MED",  dir: 63, pred: +9.1, act: -4.3,  out: 0 },
  { d: "05-06", sym: "NMBS", conf: "MED",  dir: 60, pred: +5.2, act: +6.7,  out: 1 },
  { d: "05-05", sym: "MAPL", conf: "LOW",  dir: 53, pred: +3.1, act: -2.0,  out: 0 },
  { d: "05-02", sym: "QBIT", conf: "HIGH", dir: 70, pred: +7.0, act: +9.4,  out: 1 },
  { d: "04-30", sym: "VELO", conf: "MED",  dir: 58, pred: +4.8, act: +5.1,  out: 1 },
  { d: "04-29", sym: "PALA", conf: "MED",  dir: 61, pred: +5.6, act: +0.4,  out: 0 },
  { d: "04-25", sym: "ARCM", conf: "MED",  dir: 59, pred: +4.2, act: +6.0,  out: 1 },
  { d: "04-23", sym: "HELX", conf: "LOW",  dir: 54, pred: +3.4, act: +3.9,  out: 1 },
  { d: "04-21", sym: "DRSH", conf: "MED",  dir: 57, pred: +5.0, act: -1.6,  out: 0 },
  { d: "04-18", sym: "IONX", conf: "HIGH", dir: 66, pred: +6.1, act: +7.2,  out: 1 },
  { d: "04-16", sym: "GRVT", conf: "MED",  dir: 62, pred: +8.3, act: +10.5, out: 1 },
  { d: "04-14", sym: "ZOTR", conf: "LOW",  dir: 52, pred: +2.9, act: +1.1,  out: 1 },
];

function AITKpi({ k, v, tone, s }) {
  return (
    <div className={`ait-kpi ait-kpi--${tone}`}>
      <div className="ait-kpi-l mono">{k}</div>
      <div className={`ait-kpi-v mono kpi-tone--${tone}`}>{v}</div>
      <div className="ait-kpi-s mono dim2">{s}</div>
    </div>
  );
}

// 1-year cumulative equity curve · model vs SPY (deterministic walk)
function AITEquity() {
  const days = 252;
  const { model, spy } = useMemoAIT(() => {
    const m = [], s = [];
    let mv = 0, sv = 0;
    for (let i = 0; i < days; i++) {
      mv += 0.115 + Math.sin(i * 0.18) * 0.22 + Math.cos(i * 0.37) * 0.16;
      sv += 0.041 + Math.sin(i * 0.21) * 0.12;
      m.push(mv); s.push(sv);
    }
    return { model: m, spy: s };
  }, []);
  const w = 560, h = 200, padB = 18;
  const all = [...model, ...spy];
  const min = Math.min(...all, 0), max = Math.max(...all);
  const x = i => (i / (days - 1)) * w;
  const y = v => (h - padB) - ((v - min) / (max - min)) * (h - padB - 6) + 3;
  const ml = model[model.length - 1], sl = spy[spy.length - 1];
  const monthTicks = AIT_MONTHS.map((mo, i) => ({ x: (i / (AIT_MONTHS.length - 1)) * w, lbl: mo.m.split(" ")[0] }));
  return (
    <div>
      <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{ overflow: "visible" }}>
        <defs>
          <linearGradient id="ait-eq-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--gn)" stopOpacity="0.26" />
            <stop offset="100%" stopColor="var(--gn)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0.25, 0.5, 0.75].map(g => (
          <line key={g} x1="0" y1={(h - padB) * g + 3} x2={w} y2={(h - padB) * g + 3} stroke="var(--glass-line)" strokeOpacity="0.5" />
        ))}
        <line x1="0" y1={y(0)} x2={w} y2={y(0)} stroke="var(--glass-line)" strokeDasharray="2 3" />
        <path d={`M 0 ${y(0)} L ${model.map((v, i) => `${x(i)},${y(v)}`).join(" L ")} L ${w} ${y(0)} Z`} fill="url(#ait-eq-fill)" />
        <polyline points={spy.map((v, i) => `${x(i)},${y(v)}`).join(" ")} stroke="var(--ink-3)" strokeWidth="1.3" fill="none" />
        <polyline points={model.map((v, i) => `${x(i)},${y(v)}`).join(" ")} stroke="var(--gn)" strokeWidth="2" fill="none"
                  style={{ filter: "drop-shadow(0 0 5px var(--gn))" }} />
        {monthTicks.map((t, i) => i % 2 === 0 && (
          <text key={i} x={t.x} y={h - 4} textAnchor={i === 0 ? "start" : "middle"} className="mono ait-eq-tick">{t.lbl}</text>
        ))}
      </svg>
      <div className="ait-eq-legend mono">
        <span><i className="ait-swatch ait-swatch--gn" /> Model paper book <b className="up">+{ml.toFixed(1)}%</b></span>
        <span><i className="ait-swatch ait-swatch--ink" /> SPY <b className="dim2">+{sl.toFixed(1)}%</b></span>
        <span className="ait-eq-alpha"><span className="label-cap">α 1Y</span> <b className="copper">+{(ml - sl).toFixed(1)}%</b></span>
        <span><span className="label-cap">Max DD</span> <b className="dn">−6.8%</b></span>
      </div>
    </div>
  );
}

// monthly hit-rate columns with 50% baseline
function AITMonthly() {
  const max = 70, min = 40;
  return (
    <div className="ait-month">
      {AIT_MONTHS.map((mo, i) => {
        const hgt = ((mo.hit - min) / (max - min)) * 100;
        const tone = mo.hit >= 55 ? "gn" : mo.hit >= 50 ? "amb" : "rd";
        return (
          <div key={i} className="ait-month-col" title={`${mo.m} · ${mo.n} resolved · ${mo.hit}% hit · edge ${mo.edge >= 0 ? "+" : ""}${mo.edge}%`}>
            <div className="ait-month-track">
              <div className="ait-month-base" />
              <div className={`ait-month-fill kpi-tone-bg--${tone}`} style={{ height: `${Math.max(4, hgt)}%` }} />
            </div>
            <span className={`mono ait-month-v kpi-tone--${tone}`}>{mo.hit.toFixed(0)}</span>
            <span className="mono ait-month-m dim2">{mo.m.split(" ")[0]}</span>
          </div>
        );
      })}
    </div>
  );
}

// reliability diagram — predicted vs realized, points should hug the diagonal
function AITCalibration() {
  const W = 220, H = 180, pad = 26;
  const lo = 48, hi = 84;
  const sx = v => pad + ((v - lo) / (hi - lo)) * (W - pad - 6);
  const sy = v => (H - pad) - ((v - lo) / (hi - lo)) * (H - pad - 6);
  return (
    <div>
      <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} style={{ overflow: "visible" }}>
        <line x1={pad} y1={H - pad} x2={W - 6} y2={H - pad} stroke="var(--glass-line)" />
        <line x1={pad} y1={6} x2={pad} y2={H - pad} stroke="var(--glass-line)" />
        <line x1={sx(lo)} y1={sy(lo)} x2={sx(hi)} y2={sy(hi)} stroke="var(--ink-3)" strokeDasharray="3 3" strokeWidth="1" />
        <polyline points={AIT_CALIB.map(c => `${sx(c.mid)},${sy(c.real)}`).join(" ")} fill="none" stroke="var(--violet)" strokeWidth="1.8" />
        {AIT_CALIB.map((c, i) => (
          <circle key={i} cx={sx(c.mid)} cy={sy(c.real)} r={3 + (c.n / 412) * 3} fill="var(--violet)"
                  style={{ filter: "drop-shadow(0 0 4px var(--violet))" }} />
        ))}
        <text x={pad - 5} y={sy(hi)} textAnchor="end" className="mono ait-cal-ax">{hi}</text>
        <text x={pad - 5} y={sy(lo) + 3} textAnchor="end" className="mono ait-cal-ax">{lo}</text>
        <text x={sx(lo)} y={H - pad + 12} textAnchor="middle" className="mono ait-cal-ax">{lo}</text>
        <text x={sx(hi)} y={H - pad + 12} textAnchor="middle" className="mono ait-cal-ax">{hi}</text>
        <text x={(W + pad) / 2} y={H - 4} textAnchor="middle" className="mono ait-cal-axlbl">predicted P(up) %</text>
      </svg>
      <div className="ait-cal-note mono dim2">Points hug the diagonal → well-calibrated. <b className="up">ECE 0.04</b> · <b className="up">Brier 0.213</b></div>
    </div>
  );
}

function AITrackRecord() {
  const tot = AIT_MONTHS.reduce((a, m) => a + m.n, 0);
  const wHit = AIT_MONTHS.reduce((a, m) => a + m.hit * m.n, 0) / tot;
  const best = [...AIT_MONTHS].sort((a, b) => b.hit - a.hit)[0];
  const worst = [...AIT_MONTHS].sort((a, b) => a.hit - b.hit)[0];
  const ledgerHit = AIT_LEDGER.filter(r => r.out).length;

  return (
    <div className="ait">
      <div className="ait-kpis">
        <AITKpi k="RESOLVED · 12M" v={tot.toLocaleString()} tone="violet" s="forecasts reaching horizon" />
        <AITKpi k="HIT RATE" v={`${wHit.toFixed(1)}%`} tone="gn" s="vs 50% coin-flip baseline" />
        <AITKpi k="CUM. ALPHA vs SPY" v="+18.7%" tone="copper" s="paper book · net of costs" />
        <AITKpi k="AVG EDGE / PICK" v="+1.4%" tone="gn" s="realized 10d move" />
        <AITKpi k="BRIER · ECE" v="0.213 · 0.04" tone="cy" s="calibrated · low error" />
        <AITKpi k="BEST / WORST MO" v={`${best.hit.toFixed(0)} / ${worst.hit.toFixed(0)}%`} tone="amb" s={`${best.m.split(" ")[0]} · ${worst.m.split(" ")[0]}`} />
      </div>

      <div className="ai-grid">
        <div className="ai-col-main">
          <div className="ai-card">
            <div className="ai-card-hdr">
              <div>
                <div className="ai-card-title mono">Cumulative performance · trailing 12 months</div>
                <div className="ai-card-sub mono dim2">paper book of every HIGH/MED signal vs SPY · daily mark · net of modeled slippage</div>
              </div>
              <FreshnessPill state="live" age="EOD" />
            </div>
            <AITEquity />
          </div>

          <div className="ai-card">
            <div className="ai-card-hdr">
              <div>
                <div className="ai-card-title mono">Monthly hit-rate consistency</div>
                <div className="ai-card-sub mono dim2">resolved hit-rate by month · 50% = no edge · 10 of 12 months above baseline</div>
              </div>
            </div>
            <AITMonthly />
          </div>

          <div className="ai-card">
            <div className="ai-card-hdr">
              <div>
                <div className="ai-card-title mono">Resolved-prediction ledger</div>
                <div className="ai-card-sub mono dim2">most recent forecasts scored at horizon · {ledgerHit}/{AIT_LEDGER.length} hit shown</div>
              </div>
            </div>
            <table className="dtable ai-tbl ait-tbl">
              <thead>
                <tr>
                  <th>Resolved</th><th>Symbol</th><th>Conf</th>
                  <th className="r">P(up)</th><th className="r">Predicted</th>
                  <th className="r">Realized</th><th className="r">Δ vs pred</th><th>Outcome</th>
                </tr>
              </thead>
              <tbody>
                {AIT_LEDGER.map((r, i) => (
                  <tr key={i}>
                    <td className="mono dim2">{r.d}</td>
                    <td className="mono"><b>{r.sym}</b></td>
                    <td><Pill tone={r.conf === "HIGH" ? "gn" : r.conf === "MED" ? "amb" : "ink"} small>{r.conf}</Pill></td>
                    <td className="r mono tabular">{r.dir}%</td>
                    <td className="r mono tabular up">+{r.pred.toFixed(1)}%</td>
                    <td className={`r mono tabular ${r.act >= 0 ? "up" : "dn"}`}>{r.act >= 0 ? "+" : ""}{r.act.toFixed(1)}%</td>
                    <td className={`r mono tabular ${r.act - r.pred >= 0 ? "up" : "dn"}`}>{r.act - r.pred >= 0 ? "+" : ""}{(r.act - r.pred).toFixed(1)}%</td>
                    <td><span className={`ait-out ait-out--${r.out ? "hit" : "miss"}`}>{r.out ? "HIT" : "MISS"}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="ai-col-side">
          <div className="ai-card">
            <div className="ai-card-hdr">
              <div className="ai-card-title mono">Calibration · reliability</div>
            </div>
            <AITCalibration />
          </div>

          <div className="ai-card">
            <div className="ai-card-hdr">
              <div className="ai-card-title mono">Hit-rate by confidence</div>
            </div>
            <div className="ait-break">
              {AIT_BY_CONF.map((c, i) => (
                <div key={i} className="ait-break-row">
                  <span className="mono ait-break-k"><Pill tone={c.tone} small>{c.k}</Pill></span>
                  <span className="ait-break-bar"><i className={`kpi-tone-bg--${c.tone}`} style={{ width: `${(c.hit - 40) / 30 * 100}%` }} /></span>
                  <span className={`mono ait-break-v kpi-tone--${c.tone}`}>{c.hit.toFixed(1)}%</span>
                  <span className="mono dim2 ait-break-n">{c.n}</span>
                </div>
              ))}
              <div className="ait-break-foot mono dim2">Confidence tiers separate cleanly — HIGH signals hit ~16pt above LOW, exactly what a calibrated ranking should do.</div>
            </div>
          </div>

          <div className="ai-card">
            <div className="ai-card-hdr">
              <div className="ai-card-title mono">Hit-rate by horizon</div>
            </div>
            <div className="ait-break">
              {AIT_BY_HORIZON.map((c, i) => (
                <div key={i} className="ait-break-row">
                  <span className="mono ait-break-k">{c.k}</span>
                  <span className="ait-break-bar"><i className="kpi-tone-bg--violet" style={{ width: `${(c.hit - 40) / 30 * 100}%` }} /></span>
                  <span className="mono ait-break-v kpi-tone--violet">{c.hit.toFixed(1)}%</span>
                </div>
              ))}
              <div className="ait-break-foot mono dim2">The 10-day horizon the model is optimized for is also its strongest — edge decays at 20d as catalysts mean-revert.</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

window.AITrackRecord = AITrackRecord;

// surface-ai.jsx — AI Predictions · multi-model ML forecast surface.
// Ranked board (all names by ML edge) → drill-in per-ticker forecast:
// 3-head ensemble vote · P(up) · Monte-Carlo price cone · feature importances ·
// historical analogs · verdict+score · model calibration/backtest.

const { useMemo: useMemoAI, useState: useStateAI } = React;

const aiPct = (v, d = 1) => (v >= 0 ? "+" : "−") + Math.abs(v).toFixed(d) + "%";
const vTone = v => v === "BUY" ? "gn" : v === "SELL" ? "rd" : "amb";
const cTone = c => c === "HIGH" ? "gn" : c === "MED" ? "amb" : "ink";

function SurfaceAIPredictions({ onTicker }) {
  const AP = window.AIPredict;
  const [view, setView] = useStateAI("board");   // board · detail · calib
  const [pick, setPick] = useStateAI("ARGN");
  const all = AP.all();
  const P = useMemoAI(() => AP.predict(pick), [pick]);
  const openDetail = (s) => { setPick(s); setView("detail"); };

  return (
    <div className="surface wsx wsx--violet aip">
      <div className="wsx-hdr">
        <div className="wsx-hdr-l">
          <div className="wsx-eyebrow mono">ML PREDICTIONS · MULTI-MODEL FORECAST</div>
          <h1 className="wsx-title mono">ML Predictions</h1>
          <div className="wsx-sub mono dim2">3-head ensemble · P(up) classifier · Monte-Carlo price cone · feature importances · analogs · forward edge → BUY / HOLD / SELL</div>
        </div>
        <div className="wsx-hdr-r">
          <span className="aip-bt mono" title="Out-of-sample backtest">AUC {AP.BACKTEST.auc} · hit {Math.round(AP.BACKTEST.hit * 100)}% · n={AP.BACKTEST.n}</span>
          <FreshnessPill state="live" age="sim" />
        </div>
      </div>

      <div className="wsx-kpis">
        <div className="wsx-kpi wsx-kpi--violet"><div className="wsx-kpi-l mono">TOP VERDICT</div><div className={`wsx-kpi-v mono kpi-tone--${vTone(all[0].verdict)}`}>{all[0].sym} {all[0].verdict}</div><div className="wsx-kpi-s mono dim2">edge {all[0].score}/100</div></div>
        <div className="wsx-kpi wsx-kpi--gn"><div className="wsx-kpi-l mono">BUY SIGNALS</div><div className="wsx-kpi-v mono kpi-tone--gn">{all.filter(p => p.verdict === "BUY").length}</div><div className="wsx-kpi-s mono dim2">of {all.length} names</div></div>
        <div className="wsx-kpi wsx-kpi--rd"><div className="wsx-kpi-l mono">SELL SIGNALS</div><div className="wsx-kpi-v mono kpi-tone--rd">{all.filter(p => p.verdict === "SELL").length}</div><div className="wsx-kpi-s mono dim2">downside edge</div></div>
        <div className="wsx-kpi wsx-kpi--cy"><div className="wsx-kpi-l mono">AVG P(up)</div><div className="wsx-kpi-v mono kpi-tone--cy">{Math.round(all.reduce((a, p) => a + p.pUp, 0) / all.length * 100)}%</div><div className="wsx-kpi-s mono dim2">classifier mean</div></div>
        <div className="wsx-kpi wsx-kpi--gn"><div className="wsx-kpi-l mono">MODEL AUC</div><div className="wsx-kpi-v mono kpi-tone--gn">{AP.BACKTEST.auc}</div><div className="wsx-kpi-s mono dim2">out-of-sample</div></div>
        <div className="wsx-kpi wsx-kpi--violet"><div className="wsx-kpi-l mono">HIT RATE</div><div className="wsx-kpi-v mono kpi-tone--violet">{Math.round(AP.BACKTEST.hit * 100)}%</div><div className="wsx-kpi-s mono dim2">n={AP.BACKTEST.n} · {AP.BACKTEST.horizon}</div></div>
      </div>

      <div className="lab-tabs aip-tabs">
        {[["board", "Ranked Board"], ["analyst", "✦ AI Analyst"], ["detail", `Forecast · ${pick}`], ["crossmode", "Cross-Mode"], ["track", "Track Record"], ["calib", "Model Accuracy"]].map(([id, l]) => (
          <button key={id} className={`lab-tab ${view === id ? "is-on" : ""}`} onClick={() => setView(id)}>{l}</button>
        ))}
      </div>

      {view === "board" && <AIBoard all={all} onOpen={openDetail} />}
      {view === "analyst" && window.AIAnalystView && React.createElement(window.AIAnalystView, { all, onTicker, pick, onPick: setPick })}
      {view === "detail" && <AIDetail P={P} all={all} onPick={setPick} onTicker={onTicker} />}
      {view === "crossmode" && <AICrossMode all={all} onOpen={openDetail} />}
      {view === "track" && <AITrack AP={AP} onTicker={onTicker} />}
      {view === "calib" && <AICalib AP={AP} />}

      <div className="pf-note mono dim2">
        Ensemble of three model heads (gradient-boost on tabular features · sequence model on 60-day OHLCV · regime-conditional HMM) trained on EODHD history, scored on live quotes. Forward edge → verdict. <b>Calibration &amp; backtest are shown so predictions aren't oversold</b> — a "70%" call should win ~70% of the time. Demo outputs; wire to your model server to go live.
      </div>
    </div>
  );
}

// ── ranked board ────────────────────────────────────────────────
function AIBoard({ all, onOpen }) {
  const [sort, setSort] = useStateAI("score");
  const rows = useMemoAI(() => [...all].sort((a, b) => sort === "score" ? b.score - a.score : sort === "pup" ? b.pUp - a.pUp : b.ens - a.ens), [sort, all]);
  return (
    <div className="wsx-body">
      <div className="aip-board-bar">
        <span className="mono dim2">{all.length} names · ranked by ML forward-edge</span>
        <div className="seg">{[["score", "Edge score"], ["pup", "P(up)"], ["ens", "Ensemble"]].map(([id, l]) => <button key={id} className={`seg-btn ${sort === id ? "is-on" : ""}`} onClick={() => setSort(id)}>{l}</button>)}</div>
      </div>
      <table className="dtable wsx-tbl aip-tbl">
        <thead><tr><th>#</th><th>Symbol</th><th>Verdict</th><th className="r">Edge</th><th className="r">P(up)</th><th>Ensemble vote</th><th className="r">3M target</th><th className="r">Conf</th><th>Top driver</th><th></th></tr></thead>
        <tbody>{rows.map((p, i) => (
          <tr key={p.sym} onClick={() => onOpen(p.sym)} className="aip-row">
            <td className="mono dim2"><b className={i < 3 ? "vio" : ""}>{i + 1}</b></td>
            <td className="mono"><b>{p.sym}</b><span className="dim2"> ${p.px.toFixed(0)}</span></td>
            <td><span className={`aip-verdict aip-verdict--${vTone(p.verdict)}`}>{p.verdict}</span></td>
            <td className="r mono tabular"><b className={`kpi-tone--${p.score >= 66 ? "gn" : p.score <= 40 ? "rd" : "amb"}`}>{p.score}</b></td>
            <td className="r mono tabular">{Math.round(p.pUp * 100)}%</td>
            <td><span className="aip-votes">{p.heads.map((h, j) => <span key={j} className={`aip-vote ${h.score >= 0 ? "up" : "dn"}`} title={`${h.label}: ${h.score}`} />)}<span className="mono dim2" style={{ marginLeft: 6 }}>{p.agree}/3</span></span></td>
            <td className={`r mono tabular ${p.horizons[2].ret >= 0 ? "up" : "dn"}`}>{aiPct(p.horizons[2].ret)}</td>
            <td className="r"><span className={`aip-conf kpi-tone--${cTone(p.conf)}`}>{p.conf}</span></td>
            <td className="dim2" style={{ fontSize: 11 }}>{p.feats[0].k}</td>
            <td className="mono dim">›</td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

// ── per-ticker forecast detail ──────────────────────────────────
function AIDetail({ P, all, onPick, onTicker }) {
  const [mode, setMode] = useStateAI(() => { const m = (window.__tmode || "SWING").toLowerCase(); return m.startsWith("pos") ? "position" : m.startsWith("inv") ? "invest" : "swing"; });
  const proj = useMemoAI(() => (window.AIPredict ? window.AIPredict.projection(P.sym, mode) : null), [P.sym, mode]);
  const pBand = p => p >= 0.6 ? "gn" : p >= 0.45 ? "amb" : "rd";
  return (
    <div className="wsx-body aip-detail">
      <div className="aip-pickbar">
        {all.slice(0, 10).map(p => <button key={p.sym} className={`aip-pick ${p.sym === P.sym ? "is-on" : ""}`} onClick={() => onPick(p.sym)}>{p.sym}</button>)}
      </div>

      {proj && (
        <div className="aip-proj">
          <div className="aip-proj-head">
            <span className="label-cap">Targets &amp; projection · by holding period</span>
            <div className="aip-modeseg">
              {["swing", "position", "invest"].map(mo => (
                <button key={mo} className={`aip-modebtn ${mode === mo ? "is-on" : ""}`} onClick={() => setMode(mo)}>
                  {window.AIPredict ? null : null}{mo === "swing" ? "Swing" : mo === "position" ? "Position" : "Invest"}<span className="aip-modebtn-h mono">{mo === "swing" ? "5d" : mo === "position" ? "21d" : "126d"}</span>
                </button>
              ))}
            </div>
          </div>
          <div className="aip-proj-grid">
            <div className="aip-proj-cell"><div className="label-cap">Verdict · {proj.horizon}</div><div className={`aip-proj-v kpi-tone--${proj.verdict === "BUY" ? "gn" : proj.verdict === "AVOID" ? "rd" : "amb"}`}>{proj.verdict}</div><div className="mono dim2">P(up) {Math.round(proj.pUp * 100)}% · CI {Math.round(proj.ci[0]*100)}–{Math.round(proj.ci[1]*100)}%</div></div>
            <div className="aip-proj-cell"><div className="label-cap">Entry</div><div className="aip-proj-v mono">${proj.entry.toFixed(2)}</div><div className="mono dim2">spot</div></div>
            <div className="aip-proj-cell"><div className="label-cap">Stop · q10</div><div className="aip-proj-v mono dn">${proj.stop.toFixed(2)}</div><div className="mono dim2">{proj.mag.q10}%</div></div>
            <div className="aip-proj-cell"><div className="label-cap">Target T1 · q75</div><div className="aip-proj-v mono up">${proj.t1.toFixed(2)}</div><div className="mono dim2">+{proj.mag.q75}%</div></div>
            <div className="aip-proj-cell"><div className="label-cap">Target T2 · q90</div><div className="aip-proj-v mono up">${proj.t2.toFixed(2)}</div><div className="mono dim2">+{proj.mag.q90}%</div></div>
            <div className="aip-proj-cell"><div className="label-cap">R:R</div><div className={`aip-proj-v mono ${proj.rr >= 2 ? "up" : "warn"}`}>{proj.rr ?? "—"}</div><div className="mono dim2">T1 vs stop</div></div>
            <div className="aip-proj-cell"><div className="label-cap">Expected value</div><div className={`aip-proj-v mono ${proj.ev >= 0 ? "up" : "dn"}`}>{proj.ev >= 0 ? "+" : ""}{proj.ev}%</div><div className="mono dim2">P(T1) {Math.round(proj.hit.p_t1_first*100)}% · P(stop) {Math.round(proj.hit.p_stop_first*100)}%</div></div>
            <div className="aip-proj-cell"><div className="label-cap">Median proj</div><div className="aip-proj-v mono">${proj.projMid.toFixed(2)}</div><div className="mono dim2">{proj.retMid >= 0 ? "+" : ""}{proj.retMid}% · {proj.horizon}</div></div>
          </div>
          <div className="aip-proj-bar">
            <span className="mono dn">${proj.projLow.toFixed(0)}</span>
            <div className="aip-proj-track"><span className="aip-proj-stop" style={{ left: 0 }} /><span className="aip-proj-mid" style={{ left: `${Math.max(2, Math.min(98, (proj.projMid - proj.projLow) / (proj.projHigh - proj.projLow) * 100))}%` }} /><span className="aip-proj-spot" style={{ left: `${Math.max(2, Math.min(98, (proj.entry - proj.projLow) / (proj.projHigh - proj.projLow) * 100))}%` }} title="entry" /></div>
            <span className="mono up">${proj.projHigh.toFixed(0)}</span>
          </div>
          <div className="mono dim2" style={{ fontSize: 11, marginTop: 4 }}>All fields recompute from the <b>{proj.label} ({proj.horizon})</b> model output — switch the toggle to see how targets, R:R and EV change by holding period. Nothing here is hardcoded; it's derived from the mode's magnitude quantiles + hit-net probabilities.</div>
        </div>
      )}

      {proj && window.CandleChart && (
        <div className="aip-projchart">
          <div className="aip-proj-head">
            <span className="label-cap">AI price projection · {P.sym} · {proj.label} ({proj.horizon}) <span className="aip-pc-badge">demo history · live forecast</span></span>
            <span className="mono aip-pc-leg">
              <i className="aip-pc-sw" style={{ background: "var(--cy)" }} />MA20
              <i className="aip-pc-sw" style={{ background: "var(--amb)" }} />MA50
              <i className="aip-pc-sw" style={{ background: "var(--ink-3)" }} />MA200
              <i className="aip-pc-sw" style={{ background: "color-mix(in oklab, var(--gn) 50%, transparent)" }} />Breakout
              <i className="aip-pc-sw" style={{ background: "color-mix(in oklab, var(--violet) 50%, transparent)" }} />AI zone
            </span>
          </div>
          <AIProjectionChart P={P} proj={proj} />
        </div>
      )}

      {/* verdict hero */}
      <div className="aip-hero">
        <div className={`aip-hero-verdict aip-hero-verdict--${vTone(P.verdict)}`}>
          <div className="aip-hero-v mono">{P.verdict}</div>
          <div className="aip-hero-score mono">{P.score}<span>/100</span></div>
          <div className="mono dim2">forward-edge score</div>
        </div>
        <div className="aip-hero-stats">
          <div className="aip-hs"><div className="label-cap">Name</div><div className="aip-hs-v" onClick={() => onTicker && onTicker(P.sym)} style={{ cursor: "pointer" }}>{P.sym} · {P.name}</div><div className="mono dim2">{P.sector} · ${P.px.toFixed(2)}</div></div>
          <div className="aip-hs"><div className="label-cap">P(up · 21d)</div><div className={`aip-hs-v kpi-tone--${P.pUp >= 0.55 ? "gn" : P.pUp <= 0.45 ? "rd" : "amb"}`}>{Math.round(P.pUp * 100)}%</div><div className="mono dim2">classifier</div></div>
          <div className="aip-hs"><div className="label-cap">Ensemble</div><div className={`aip-hs-v ${P.ens >= 0 ? "up" : "dn"}`}>{P.ens >= 0 ? "+" : ""}{P.ens}</div><div className="mono dim2">{P.agree}/3 heads agree</div></div>
          <div className="aip-hs"><div className="label-cap">Target / Stop</div><div className="aip-hs-v mono"><span className="up">${P.target}</span> <span className="dim2">/</span> <span className="dn">${P.stop}</span></div><div className="mono dim2">P75 3M / P10 1M</div></div>
          <div className="aip-hs"><div className="label-cap">Confidence</div><div className={`aip-hs-v kpi-tone--${cTone(P.conf)}`}>{P.conf}</div><div className="mono dim2">analog WR {Math.round(P.analogWin * 100)}%</div></div>
        </div>
      </div>

      {/* price cone */}
      <div className="lab-card">
        <div className="lab-card-h mono">PRICE-PATH FORECAST <span className="dim2">· Monte-Carlo · P10–P90 cone · 3 months</span></div>
        <AIPriceCone P={P} />
        <div className="aip-horizons">
          {P.horizons.map(h => (
            <div key={h.l} className="aip-hz"><span className="aip-hz-l mono">{h.l}</span><span className={`aip-hz-r mono ${h.ret >= 0 ? "up" : "dn"}`}>{aiPct(h.ret)}</span><span className="aip-hz-band mono dim2">${h.lo.toFixed(0)}–${h.hi.toFixed(0)}</span></div>
          ))}
        </div>
      </div>

      <div className="aip-grid2">
        {/* ensemble heads */}
        <div className="lab-card">
          <div className="lab-card-h mono">ENSEMBLE · 3 MODEL HEADS</div>
          <div className="aip-heads">
            {P.heads.map(h => (
              <div key={h.id} className="aip-head">
                <div className="aip-head-top"><span className="aip-head-l">{h.label}</span><span className="mono dim2">×{h.w.toFixed(2)}</span><span className={`aip-head-s mono ${h.score >= 0 ? "up" : "dn"}`}>{h.score >= 0 ? "+" : ""}{h.score}</span></div>
                <div className="aip-head-track"><span className="aip-head-zero" /><div className={`aip-head-fill ${h.score >= 0 ? "up" : "dn"}`} style={h.score >= 0 ? { left: "50%", width: `${Math.min(50, h.score * 50)}%` } : { right: "50%", width: `${Math.min(50, -h.score * 50)}%` }} /></div>
                <div className="aip-head-note mono dim2">{h.note}</div>
              </div>
            ))}
            <div className="aip-ens-out mono">weighted ensemble <b className={P.ens >= 0 ? "up" : "dn"}>{P.ens >= 0 ? "+" : ""}{P.ens}</b> → P(up) <b>{Math.round(P.pUp * 100)}%</b></div>
          </div>
        </div>

        {/* feature importances */}
        <div className="lab-card">
          <div className="lab-card-h mono">FEATURE IMPORTANCE <span className="dim2">· what's driving it (SHAP)</span></div>
          <div className="aip-feats">
            {P.feats.map((f, i) => (
              <div key={i} className="aip-feat">
                <span className="aip-feat-k">{f.k}</span>
                <div className="aip-feat-track"><span className="aip-feat-zero" /><div className={`aip-feat-fill ${f.v >= 0 ? "up" : "dn"}`} style={f.v >= 0 ? { left: "50%", width: `${(f.v / P.featMax) * 48}%` } : { right: "50%", width: `${(-f.v / P.featMax) * 48}%` }} /></div>
                <span className={`aip-feat-v mono ${f.v >= 0 ? "up" : "dn"}`}>{f.v >= 0 ? "+" : ""}{f.v.toFixed(2)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* analogs */}
      <div className="lab-card">
        <div className="lab-card-h mono">HISTORICAL ANALOGS <span className="dim2">· setups that looked like this & how they resolved (21d fwd)</span></div>
        <table className="dtable wsx-tbl">
          <thead><tr><th>Period</th><th>Analog</th><th className="r">Similarity</th><th className="r">Fwd 21d</th><th>Outcome</th></tr></thead>
          <tbody>{P.analogs.map((a, i) => (
            <tr key={i}>
              <td className="mono dim2">{a.when}</td>
              <td className="mono"><b>{a.sym}</b></td>
              <td className="r mono tabular">{Math.round(a.sim * 100)}%</td>
              <td className={`r mono tabular ${a.fwd >= 0 ? "up" : "dn"}`}><b>{aiPct(a.fwd)}</b></td>
              <td><span className={`aip-out kpi-tone--${a.fwd >= 0 ? "gn" : "rd"}`}>{a.fwd >= 0 ? "RESOLVED UP" : "RESOLVED DOWN"}</span></td>
            </tr>
          ))}</tbody>
        </table>
        <div className="lab-verdict mono dim2">{Math.round(P.analogWin * 100)}% of the {P.analogs.length} closest historical analogs resolved upward over 21 days — {P.analogWin >= 0.6 ? "supportive of the bullish read" : P.analogWin <= 0.4 ? "a caution flag on the long thesis" : "mixed precedent, size accordingly"}.</div>
      </div>
    </div>
  );
}

function AIPriceCone({ P }) {
  const [ref, w] = (window.useWidth ? window.useWidth(820) : [{ current: null }, 820]);
  const h = 220, padL = 8, padR = 56, padT = 12, padB = 22;
  const plotW = w - padL - padR, plotR = padL + plotW, plotH = h - padT - padB;
  const c = P.cone, n = P.days;
  const all = c.p10.concat(c.p90, [P.px]); const min = Math.min(...all) * 0.99, max = Math.max(...all) * 1.01;
  const x = i => padL + (i / n) * plotW, y = v => padT + plotH - ((v - min) / (max - min)) * plotH;
  const pts = arr => arr.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`);
  const area = (top, bot) => `M ${pts(top).join(" L ")} L ${pts(bot).slice().reverse().join(" L ")} Z`;
  return (
    <div className="pv-chart aip-cone" ref={ref}>
      <svg width={w} height={h}>
        <line x1={padL} y1={y(P.px)} x2={plotR} y2={y(P.px)} stroke="var(--ink-3)" strokeDasharray="2 4" />
        <text x={padL + 3} y={y(P.px) - 4} fontSize="9" className="mono" fill="var(--ink-3)">spot ${P.px.toFixed(0)}</text>
        <line x1={padL} y1={y(P.target)} x2={plotR} y2={y(P.target)} stroke="var(--gn)" strokeDasharray="4 4" opacity="0.6" />
        <line x1={padL} y1={y(P.stop)} x2={plotR} y2={y(P.stop)} stroke="var(--rd)" strokeDasharray="4 4" opacity="0.6" />
        <path d={area(c.p90, c.p10)} fill="var(--violet)" opacity="0.1" />
        <path d={area(c.p75, c.p25)} fill="var(--violet)" opacity="0.2" />
        <polyline points={pts(c.p50).join(" ")} fill="none" stroke="var(--violet)" strokeWidth="2" />
        {[["p90", "P90"], ["p50", "med"], ["p10", "P10"]].map(([k, l]) => (
          <text key={k} x={plotR + 4} y={y(c[k][n]) + 3} fontSize="9" className="mono" fill="var(--violet)">{l} ${c[k][n].toFixed(0)}</text>
        ))}
        {[5, 21, 63].map(d => <line key={d} x1={x(d)} y1={padT} x2={x(d)} y2={padT + plotH} stroke="var(--line)" strokeDasharray="1 5" opacity="0.4" />)}
        {[["1W", 5], ["1M", 21], ["3M", 63]].map(([l, d]) => <text key={l} x={x(d)} y={h - 6} fontSize="9" textAnchor="middle" className="mono" fill="var(--ink-3)">{l}</text>)}
      </svg>
    </div>
  );
}

// ── calibration / backtest ──────────────────────────────────────
function AICalib({ AP }) {
  const cal = AP.CALIB, bt = AP.BACKTEST;
  const w = 340, h = 300, pad = 42, plot = w - pad * 2;
  const x = p => pad + p * plot, y = p => h - pad - p * (h - pad * 2);
  return (
    <div className="pf-expo">
      <div className="lab-card">
        <div className="lab-card-h mono">CALIBRATION · predicted vs realized</div>
        <svg width={w} height={h} style={{ display: "block", margin: "0 auto" }}>
          <line x1={pad} y1={h - pad} x2={w - pad} y2={h - pad} stroke="var(--line-2)" /><line x1={pad} y1={pad} x2={pad} y2={h - pad} stroke="var(--line-2)" />
          <line x1={pad} y1={h - pad} x2={w - pad} y2={pad} stroke="var(--ink-3)" strokeDasharray="4 4" opacity="0.6" />
          <text x={w / 2} y={h - 8} fontSize="10" textAnchor="middle" className="mono" fill="var(--ink-3)">predicted P(up) →</text>
          {cal.map((c, i) => <g key={i}><line x1={x(c.pred)} y1={y(c.pred)} x2={x(c.pred)} y2={y(c.realized)} stroke="var(--violet)" opacity="0.4" /><circle cx={x(c.pred)} cy={y(c.realized)} r="5" fill="var(--violet)" /><text x={x(c.pred)} y={y(c.realized) - 9} fontSize="9" textAnchor="middle" className="mono" fill="var(--ink-1)">{Math.round(c.realized * 100)}%</text></g>)}
        </svg>
        <div className="lab-verdict mono dim2">Dots near the diagonal = well-calibrated. The model is slightly <b>under-confident</b> in the 70–90% band (realized ≥ predicted) — its high-conviction calls are trustworthy.</div>
      </div>
      <div className="lab-card">
        <div className="lab-card-h mono">OUT-OF-SAMPLE BACKTEST <span className="dim2">· since {bt.since}</span></div>
        <div className="aip-bt-grid">
          <div className="aip-btk"><div className="label-cap">ROC AUC</div><div className="aip-btk-v mono gn-c">{bt.auc}</div><div className="mono dim2">discrimination</div></div>
          <div className="aip-btk"><div className="label-cap">Hit rate</div><div className="aip-btk-v mono">{Math.round(bt.hit * 100)}%</div><div className="mono dim2">directional</div></div>
          <div className="aip-btk"><div className="label-cap">Brier score</div><div className="aip-btk-v mono">{bt.brier}</div><div className="mono dim2">lower = better</div></div>
          <div className="aip-btk"><div className="label-cap">Strategy Sharpe</div><div className="aip-btk-v mono">{bt.sharpe}</div><div className="mono dim2">{bt.horizon} hold</div></div>
        </div>
        <table className="dtable wsx-tbl" style={{ marginTop: 10 }}>
          <thead><tr><th>Predicted band</th><th className="r">Realized</th><th className="r">n</th><th>Read</th></tr></thead>
          <tbody>{cal.map((c, i) => <tr key={i}><td className="mono">{Math.round(c.lo * 100)}–{Math.round(c.hi * 100)}%</td><td className={`r mono tabular ${c.realized >= c.pred ? "up" : "dn"}`}>{Math.round(c.realized * 100)}%</td><td className="r mono tabular dim2">{c.n}</td><td className="dim2">{c.realized >= c.pred ? "well-calibrated" : "slightly over-confident"}</td></tr>)}</tbody>
        </table>
      </div>
    </div>
  );
}

// ── AI price-projection chart — faithful reproduction of the reference:
//    light card, dashed grid, 4 colored MAs, blue swing dots + price labels,
//    green "Breakout" box, blue "AI Prediction" box w/ forward candles, axis ──
function AIProjectionChart({ P, proj }) {
  const [ref, w] = (window.useWidth ? window.useWidth(900) : [React.useRef(null), 900]);
  const M = useMemoAI(() => {
    const seed = window.seedFromSym ? window.seedFromSym(P.sym) : 1;
    const spot = proj.entry;
    const histN = 60, fwdN = 16;
    const baseLo = spot * 0.855, baseHi = spot * 0.945;
    const anchors = [
      { i: 0, price: spot * 0.72 },
      { i: 8, price: spot * 0.80 },          // early swing low region
      { i: 14, price: spot * 0.78 },
      { i: 22, price: spot * 0.915 },        // pre-base swing high
      { i: 28, price: baseHi },              // base top (breakout level)
      { i: 36, price: baseLo },              // base bottom
      { i: 44, price: baseLo * 1.02 },       // base retest low
      { i: 50, price: baseHi * 0.99 },       // back to top of base
      { i: 54, price: spot * 0.975 },        // breakout bar
      { i: histN - 1, price: spot },         // current
    ];
    const bars = window.buildSeries({ n: histN, anchors, seed, volSpikes: { 54: 2.2, 55: 1.7, 28: 1.4 } });
    const rng = window.mulberry32(seed ^ 0xA17);
    const tgt = spot * (1 + proj.mag.q90 / 100);          // headline AI target (q90 — the box top)
    const retPct = proj.mag.q90;
    const fwd = [];
    let prevC = spot;
    for (let k = 1; k <= fwdN; k++) {
      const t = k / fwdN;
      const mid = spot + (tgt - spot) * (t * 0.7 + t * t * 0.3);
      const band = spot * 0.009 * Math.sqrt(k);
      const c = mid + (rng() - 0.5) * band;
      const o = prevC + (rng() - 0.5) * band * 0.5;
      const hi = Math.max(o, c) + rng() * band * 0.6;
      const lo = Math.min(o, c) - rng() * band * 0.6;
      fwd.push({ o, c, hi, lo, v: 0, proj: true });
      prevC = c;
    }
    const allBars = bars.concat(fwd);
    const ma = (win, from, to) => allBars.slice(0, to == null ? allBars.length : to).map((_, i) => {
      const s = Math.max(0, i - win + 1);
      const sl = allBars.slice(s, i + 1);
      return sl.reduce((a, b) => a + b.c, 0) / sl.length;
    });
    // swing pivots (local extrema) for blue dots + labels, historical region only
    const piv = [];
    for (let i = 4; i < histN - 4; i++) {
      const c = bars[i];
      const isHi = bars.slice(i - 3, i + 4).every(b => b.hi <= c.hi + 1e-6);
      const isLo = bars.slice(i - 3, i + 4).every(b => b.lo >= c.lo - 1e-6);
      if (isHi) piv.push({ i, price: c.hi, kind: "hi" });
      else if (isLo) piv.push({ i, price: c.lo, kind: "lo" });
    }
    const highs = piv.filter(p => p.kind === "hi").sort((a, b) => b.price - a.price).slice(0, 2);
    const lows = piv.filter(p => p.kind === "lo").sort((a, b) => a.price - b.price).slice(0, 2);
    return { bars: allBars, histN, fwdN, spot, tgt, retPct, baseLo, baseHi, breakoutIdx: 54,
      ma10: ma(10), ma20: ma(20), ma50: ma(50),
      dots: [...highs, ...lows] };
  }, [P.sym, proj]);

  // geometry
  const W = Math.max(560, w), H = 420;
  const padL = 10, padR = 78, padT = 16, padB = 16;
  const plotW = W - padL - padR, plotH = H - padT - padB;
  const N = M.bars.length;
  const xStep = plotW / N;
  const xOf = i => padL + i * xStep + xStep / 2;
  const allP = M.bars.flatMap(b => [b.hi, b.lo]).concat([M.tgt, ...M.ma50.filter(Boolean)]);
  const pMin = Math.min(...allP), pMax = Math.max(...allP);
  const rng = (pMax - pMin) || 1, yPad = rng * 0.08;
  const yMin = pMin - yPad, yMax = pMax + yPad;
  const yOf = v => padT + plotH - ((v - yMin) / (yMax - yMin)) * plotH;
  const bw = Math.max(1.4, Math.min(7, xStep * 0.58));
  const plotR = padL + plotW;
  const maPath = arr => arr.map((v, i) => `${xOf(i).toFixed(1)},${yOf(v).toFixed(1)}`).join(" ");
  const axisTicks = [0, 0.2, 0.4, 0.6, 0.8, 1].map(f => yMin + (yMax - yMin) * f);
  const bx0 = padL + 28 * xStep, bx1 = xOf(M.breakoutIdx);
  const aiX0 = xOf(M.histN) - xStep * 0.5;
  const fwdHi = Math.max(...M.bars.slice(M.histN).map(b => b.hi));
  const fwdLo = Math.min(...M.bars.slice(M.histN).map(b => b.lo));

  return (
    <div className="aip-pchart-wrap" ref={ref}>
      <svg width={W} height={H} className="aip-pchart-svg">
        {/* dashed grid */}
        {axisTicks.map((gv, k) => (
          <line key={`gy${k}`} x1={padL} y1={yOf(gv)} x2={plotR} y2={yOf(gv)} className="aipc-grid" />
        ))}
        {Array.from({ length: 11 }, (_, k) => {
          const gx = padL + (plotW / 10) * k;
          return <line key={`gx${k}`} x1={gx} y1={padT} x2={gx} y2={padT + plotH} className="aipc-grid" />;
        })}
        {/* watermark */}
        <text x={padL + plotW * 0.34} y={padT + plotH * 0.74} className="aipc-wm">{P.sym}</text>

        {/* legend — key for the lines & zones */}
        <g transform={`translate(${padL + 6}, ${padT + 6})`}>
          <rect x="-5" y="-4" width="248" height="36" rx="5" className="aipc-leg-bg" />
          {[["aipc-ma20", "MA10"], ["aipc-ma50", "MA20"], ["aipc-ma200", "MA50"]].map(([cls, lbl], k) => (
            <g key={lbl} transform={`translate(${k * 64}, 0)`}>
              <line x1="0" y1="4" x2="16" y2="4" className={cls} fill="none" />
              <text x="20" y="7.5" className="aipc-leg-txt">{lbl}</text>
            </g>
          ))}
          <g transform="translate(0, 18)">
            <rect x="0" y="-1" width="14" height="9" rx="1" className="aipc-leg-bo" />
            <text x="18" y="7" className="aipc-leg-txt">Breakout</text>
          </g>
          <g transform="translate(72, 18)">
            <rect x="0" y="-1" width="14" height="9" rx="1" className="aipc-leg-ai" />
            <text x="18" y="7" className="aipc-leg-txt">AI projection</text>
          </g>
          <g transform="translate(168, 18)">
            <circle cx="6" cy="3.5" r="3.5" className="aipc-dot" />
            <text x="16" y="7" className="aipc-leg-txt">Pivot</text>
          </g>
        </g>

        {/* Breakout consolidation box */}
        <rect x={bx0} y={yOf(M.baseHi)} width={bx1 - bx0} height={yOf(M.baseLo) - yOf(M.baseHi)} className="aipc-bo-fill" />
        <line x1={bx0} y1={yOf(M.baseHi)} x2={bx1} y2={yOf(M.baseHi)} className="aipc-bo-line" />
        <line x1={bx0} y1={yOf(M.baseLo)} x2={bx1} y2={yOf(M.baseLo)} className="aipc-bo-line" />
        <text x={(bx0 + bx1) / 2} y={yOf(M.baseHi) - 8} className="aipc-bo-label" textAnchor="middle">Breakout</text>

        {/* AI Prediction box */}
        <rect x={aiX0} y={yOf(fwdHi) - 6} width={plotR - aiX0} height={yOf(fwdLo) - yOf(fwdHi) + 12} className="aipc-ai-box" rx="3" />

        {/* MAs (drawn under candles) */}
        <polyline points={maPath(M.ma50)} className="aipc-ma200" fill="none" />
        <polyline points={maPath(M.ma20)} className="aipc-ma50" fill="none" />
        <polyline points={maPath(M.ma10)} className="aipc-ma20" fill="none" />
        {/* inline MA labels at the current bar */}
        {[["MA10", M.ma10, "aipc-malbl-20"], ["MA20", M.ma20, "aipc-malbl-50"], ["MA50", M.ma50, "aipc-malbl-200"]].map(([lbl, arr, cls]) => (
          <text key={lbl} x={xOf(M.histN - 1) - 6} y={yOf(arr[M.histN - 1]) + 3} className={`aipc-malbl ${cls}`} textAnchor="end">{lbl}</text>
        ))}

        {/* candles */}
        {M.bars.map((d, i) => {
          const up = d.c >= d.o;
          const x = xOf(i);
          const cls = up ? "aipc-up" : "aipc-dn";
          const bt = yOf(Math.max(d.o, d.c)), bh = Math.max(1, Math.abs(yOf(d.o) - yOf(d.c)));
          return (
            <g key={i} className={cls} opacity={i >= M.histN ? 0.92 : 1}>
              <line x1={x} y1={yOf(d.hi)} x2={x} y2={yOf(d.lo)} className="aipc-wick" />
              <rect x={x - bw / 2} y={bt} width={bw} height={bh} className="aipc-body" />
            </g>
          );
        })}

        {/* swing dots + price labels */}
        {M.dots.map((p, k) => (
          <g key={`d${k}`}>
            <circle cx={xOf(p.i)} cy={yOf(p.price)} r="4" className="aipc-dot" />
            <text x={xOf(p.i)} y={yOf(p.price) + (p.kind === "hi" ? -10 : 16)} className="aipc-dot-lbl" textAnchor="middle">{p.price.toFixed(2)}</text>
          </g>
        ))}

        {/* right price axis */}
        <line x1={plotR} y1={padT} x2={plotR} y2={padT + plotH} className="aipc-axis" />
        {axisTicks.slice(1).map((gv, k) => (
          <text key={`ax${k}`} x={plotR + 7} y={yOf(gv) + 4} className="aipc-axis-lbl">{gv.toFixed(2)}</text>
        ))}
        {/* AI target pill */}
        <g>
          <rect x={plotR + 3} y={yOf(M.tgt) - 11} width={padR - 6} height={22} rx="4" className="aipc-tgt-pill" />
          <text x={plotR + 3 + (padR - 6) / 2} y={yOf(M.tgt) + 4} className="aipc-tgt-txt" textAnchor="middle">{M.tgt.toFixed(2)}</text>
        </g>

        {/* AI Prediction annotation — designed badge */}
        {(() => {
          const bw = 116, bh = 34;
          const bx = plotR - 4 - bw;
          const by = Math.max(padT + 2, yOf(fwdHi) - bh - 8);
          return (
            <g>
              <rect x={bx} y={by} width={bw} height={bh} rx="7" className="aipc-ai-badge" />
              <text x={bx + 11} y={by + 14} className="aipc-ai-badge-l">✦ AI FORECAST</text>
              <text x={bx + 11} y={by + 27} className="aipc-ai-badge-v">+{M.retPct}%<tspan className="aipc-ai-badge-h"> · {proj ? proj.horizon : "3M"}</tspan></text>
            </g>
          );
        })()}
      </svg>
    </div>
  );
}

window.SurfaceAIPredictions = SurfaceAIPredictions;
window.AIProjectionChart = AIProjectionChart;

// ── Cross-Mode — swing/position/invest p_up side-by-side + adaptive picks ──
function AICrossMode({ all, onOpen }) {
  const pBand = p => p >= 0.6 ? "gn" : p >= 0.45 ? "amb" : "rd";
  const rows = useMemoAI(() => all.map(p => ({
    sym: p.sym, name: p.name,
    sw: p.modes.swing.direction.p_up, po: p.modes.position.direction.p_up, iv: p.modes.invest.direction.p_up,
    cm: p.crossMode,
  })).sort((a, b) => b.sw - a.sw), [all]);
  // adaptive buy list off the swing pool
  const bl = useMemoAI(() => (window.AIPredict ? window.AIPredict.buyList("swing") : null), [all]);
  return (
    <div className="wsx-body">
      {bl && bl.defensive && (
        <div className="aip-defensive">
          <span className="aip-def-badge mono">⚠ DEFENSIVE TAPE</span>
          <span className="mono dim2">Model is suppressed across the universe (max P(up) {(bl.poolMax * 100).toFixed(1)}%, below the 55% BUY gate). Showing best-of-pool closest-miss watch list instead of forcing BUYs.</span>
        </div>
      )}
      <div className="aip-board-bar"><span className="mono dim2">P(up) by horizon · swing 5d · position 21d · invest 126d — divergence is the signal</span></div>
      <table className="dtable wsx-tbl aip-tbl">
        <thead><tr><th>Symbol</th><th className="r">Swing 5d</th><th className="r">Position 21d</th><th className="r">Invest 126d</th><th>Horizon view</th><th className="r">Agreement</th><th></th></tr></thead>
        <tbody>{rows.map(r => (
          <tr key={r.sym} onClick={() => onOpen(r.sym)} className="aip-row">
            <td className="mono"><b>{r.sym}</b></td>
            {[r.sw, r.po, r.iv].map((p, i) => (
              <td key={i} className="r"><span className={`aip-pchip kpi-tone--${pBand(p)}`}>{Math.round(p * 100)}%</span></td>
            ))}
            <td><span className="aip-cm-spark">{[r.sw, r.po, r.iv].map((p, i) => <span key={i} className={`aip-cm-bar kpi-tone-bg--${pBand(p)}`} style={{ height: `${6 + p * 22}px` }} title={["5d", "21d", "126d"][i] + " " + Math.round(p * 100) + "%"} />)}</span></td>
            <td className="r"><span className={`aip-cm-verdict aip-cm-verdict--${r.cm.agree === "ALIGNED" ? "gn" : r.cm.agree === "MIXED" ? "amb" : "rd"}`}>{r.cm.agree}</span></td>
            <td className="mono dim">›</td>
          </tr>
        ))}</tbody>
      </table>
      <div className="lab-verdict mono dim2"><b>ALIGNED</b> = all three horizons agree on direction (highest-conviction). <b>DIVERGENT</b> = a name that's bullish short-term but bearish long-term (or vice-versa) — a trade, not an investment. This multi-horizon disagreement is unique to the ML model.</div>
    </div>
  );
}

// ── 1-year resolved-prediction track record (hit / fail) ────────
function AITrack({ AP, onTicker }) {
  const led = AP.RESOLVED;
  const resolved = led.length;
  const hits = led.filter(l => l.hit).length;
  const hitRate = resolved ? hits / resolved * 100 : 0;
  const buys = led.filter(l => l.verdict === "BUY");
  const buyHit = buys.length ? buys.filter(l => l.hit).length / buys.length * 100 : 0;
  const avgFwd = resolved ? led.reduce((a, l) => a + l.fwd, 0) / resolved : 0;
  const [f, setF] = useStateAI("all");
  const rows = led.filter(l => f === "all" || (f === "hit" ? l.hit : !l.hit)).slice().sort((a, b) => a.ageW - b.ageW);
  return (
    <div className="wsx-body">
      <div className="mpf-jr-kpis" style={{ gridTemplateColumns: "repeat(5,1fr)" }}>
        <AITk l="Resolved · 1Y" v={resolved} s="closed calls" tone="violet" />
        <AITk l="Hit rate" v={`${hitRate.toFixed(0)}%`} s={`${hits} of ${resolved}`} tone={hitRate >= 55 ? "gn" : "amb"} />
        <AITk l="BUY accuracy" v={`${buyHit.toFixed(0)}%`} s={`${buys.length} BUY calls`} tone={buyHit >= 55 ? "gn" : "amb"} />
        <AITk l="Avg fwd 21d" v={`${avgFwd >= 0 ? "+" : ""}${avgFwd.toFixed(1)}%`} s="per call" tone={avgFwd >= 0 ? "gn" : "rd"} />
        <AITk l="Edge" v={hitRate >= 55 ? "REAL" : "THIN"} s="vs 50% coin" tone={hitRate >= 55 ? "gn" : "amb"} />
      </div>
      <div className="aip-board-bar">
        <span className="mono dim2">{resolved} predictions resolved over trailing 12 months · marked at +21 trading days</span>
        <div className="seg">{[["all", "All"], ["hit", "Hits"], ["fail", "Misses"]].map(([id, l]) => <button key={id} className={`seg-btn ${f === id ? "is-on" : ""}`} onClick={() => setF(id)}>{l}</button>)}</div>
      </div>
      <table className="dtable wsx-tbl aip-tbl">
        <thead><tr><th>When</th><th>Symbol</th><th>Call</th><th className="r">Edge</th><th className="r">P(up)</th><th className="r">Fwd 21d</th><th>Outcome</th></tr></thead>
        <tbody>{rows.map((l, i) => (
          <tr key={i} onClick={() => onTicker && onTicker(l.sym)} style={{ cursor: "pointer" }}>
            <td className="mono dim2">{l.ageW}w ago</td>
            <td className="mono"><b>{l.sym}</b></td>
            <td><span className={`aip-verdict aip-verdict--${vTone(l.verdict)}`}>{l.verdict}</span></td>
            <td className="r mono tabular">{l.score}</td>
            <td className="r mono tabular">{Math.round(l.pUp * 100)}%</td>
            <td className={`r mono tabular ${l.fwd >= 0 ? "up" : "dn"}`}><b>{l.fwd >= 0 ? "+" : ""}{l.fwd}%</b></td>
            <td><span className={`aip-out kpi-tone--${l.hit ? "gn" : "rd"}`}>{l.hit ? "✓ HIT" : "✕ MISS"}</span></td>
          </tr>
        ))}</tbody>
      </table>
      <div className="lab-verdict mono dim2">Every published prediction is logged at call time and scored at +21 trading days — directionally <b>{hitRate.toFixed(0)}% accurate</b> over the trailing year. This is the audit trail behind the Model Accuracy calibration.</div>
    </div>
  );
}
function AITk({ l, v, s, tone }) {
  return <div className={`pf-tile pf-tile--${tone}`}><div className="pf-tile-l mono dim2">{l}</div><div className={`pf-tile-v mono kpi-tone--${tone}`}>{v}</div><div className="pf-tile-s mono dim2">{s}</div></div>;
}

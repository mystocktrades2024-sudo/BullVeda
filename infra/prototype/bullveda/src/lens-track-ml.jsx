// lens-track.jsx + lens-mledge.jsx — Track Record + AI Edge

// ────────────────────────────────────────────────────────────
// TRACK RECORD — Wilson CI per setup, PF, median R, edge decay
// ────────────────────────────────────────────────────────────
// Real system track record from the closed-trade ledger + model card +
// forward-return buckets. All three endpoints read LOCAL files (no quota):
//   /api/performance            → WR / Wilson LB / PF / expectancy / avg win-loss
//   /api/calibration-history    → model accuracy / AUC / Brier / log-loss (by mode)
//   /api/ml-edge-stress-buckets → forward-return quantiles (by mode + scenario)
function useTrackData() {
  const [d, setD] = React.useState(null);
  React.useEffect(() => {
    let live = true;
    const J = u => fetch(u).then(r => (r.ok ? r.json() : null)).catch(() => null);
    Promise.all([J("/api/performance"), J("/api/calibration-history"), J("/api/ml-edge-stress-buckets")])
      .then(([perf, calib, buckets]) => { if (live) setD({ perf, calib, buckets }); });
    return () => { live = false; };
  }, []);
  return d;
}

function LensTrack({ ticker, mode, sizeCat, headerStyle, kpiStyle, heroStyle }) {
  const s1 = useStateToggle("tr-1"); const s2 = useStateToggle("tr-2");
  const s3 = useStateToggle("tr-3"); const s4 = useStateToggle("tr-4");
  const s5 = useStateToggle("tr-5");
  const td = useTrackData();
  const mk = mode === "POSITION" ? "position" : mode === "INVESTMENT" ? "invest" : "swing";
  const perf = td && td.perf;
  const ss = ticker.setupStats || {};
  const hasSetup = ss.n != null && ss.n > 0;
  const calSeries = (td && td.calib && Array.isArray(td.calib.series)) ? td.calib.series.filter(x => (x.mode || "swing") === mk) : [];
  const card = calSeries.length ? calSeries[calSeries.length - 1] : null;
  const bkt = (td && td.buckets && td.buckets[mk] && td.buckets[mk].base) ? td.buckets[mk].base : null;
  const nObs = (td && td.buckets && td.buckets._meta && td.buckets._meta.n_total) || null;
  const pctd = v => (v == null ? "—" : (v >= 0 ? "+" : "") + (v * 100).toFixed(1) + "%");   // decimal→%
  const num = (v, d) => (v == null ? "—" : v.toFixed(d == null ? 2 : d));

  if (!perf && !card && !bkt) {
    return (
      <div className="lens lens--track"><div className="lens-section"><div className="lens-pad">
        <div className="smc-empty mono dim2" style={{ padding: 16 }}>
          Track-record stats not loaded — the system edge comes from the closed-trade ledger
          (<span className="mono">/api/performance</span>). {td ? "No data returned." : "Loading…"}
        </div>
      </div></div></div>
    );
  }

  const wr = perf && perf.win_rate, lb = perf && perf.wilson_lb_pct, pf = perf && perf.pf;
  const lbTone = lb == null ? "ink" : lb >= 45 ? "gn" : lb >= 40 ? "amb" : "rd";
  const expR = perf && (perf.expectancy != null ? perf.expectancy : perf.avg_r);

  return (
    <div className="lens lens--track">
      <div className="hero track-hero">
        <div className="th-left">
          <div className="label-cap">System track record · {(perf && perf.closed) != null ? perf.closed.toLocaleString() : "—"} closed trades</div>
          <div className="th-score">
            <div className="th-score-num mono">{lb != null ? lb.toFixed(1) + "%" : "—"}</div>
            <Pill tone={lbTone} dot>Wilson 95% LB</Pill>
            {pf != null && <Pill tone={pf >= 1.3 ? "gn" : pf >= 1.1 ? "amb" : "rd"} small>PF {pf.toFixed(2)}</Pill>}
            {expR != null && <Pill tone={expR > 0 ? "gn" : "rd"} small>expectancy {expR >= 0 ? "+" : ""}{expR.toFixed(2)}R</Pill>}
          </div>
          {hasSetup && (
            <div style={{ marginTop: 12 }}>
              <div className="label-cap" style={{ marginBottom: 4 }}>This setup · "{ticker.setupFamily}"</div>
              <WilsonPill n={ss.n} winRate={ss.winRate} lb={ss.wilsonLB} />
            </div>
          )}
        </div>
        <div className="th-right">
          <EdgeDecayChart series={calSeries} />
        </div>
      </div>

      <div className="lens-section">
        <SectionHeader n={1} title="Headline Edge · System"
          sub="Wilson CI · profit factor · expectancy · all closed trades"
          style={headerStyle} right={<StateToggle name="tr-1" />} />
        <StateWrap state={s1.value} source="/api/performance · closed-trade ledger">
          <div className="lens-pad">
            <div className="kpi-row" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
              <KpiTile label="Win rate" value={wr != null ? wr.toFixed(1) + "%" : "—"} tone={wr >= 50 ? "gn" : "amb"} sub={`n=${(perf && perf.closed) != null ? perf.closed.toLocaleString() : "—"}`} />
              <KpiTile label="Wilson 95% LB" value={lb != null ? lb.toFixed(1) + "%" : "—"} tone={lbTone} sub={lb >= 45 ? "above 45% gate" : "below 45% gate"} />
              <KpiTile label="Profit factor" value={pf != null ? pf.toFixed(2) : "—"} tone={pf >= 1.3 ? "gn" : pf >= 1.1 ? "amb" : "rd"} sub="gross win / gross loss" />
              <KpiTile label="Expectancy" value={expR != null ? (expR >= 0 ? "+" : "") + expR.toFixed(2) + "R" : "—"} tone={expR > 0 ? "gn" : "rd"} sub="per closed trade" />
            </div>
          </div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={2} title="Outcome Quality"
          sub="average win vs loss · realized R:R · excursions"
          style={headerStyle} right={<StateToggle name="tr-2" />} />
        <StateWrap state={s2.value} source="/api/performance · closed-trade ledger">
          <div className="lens-pad">
            <div className="kpi-row" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
              <KpiTile label="Avg win" value={perf && perf.avg_win_pct != null ? "+" + perf.avg_win_pct.toFixed(1) + "%" : "—"} tone="gn" />
              <KpiTile label="Avg loss" value={perf && perf.avg_loss_pct != null ? perf.avg_loss_pct.toFixed(1) + "%" : "—"} tone="rd" />
              <KpiTile label="Realized R:R" value={perf && perf.rr_avg != null ? perf.rr_avg.toFixed(2) : "—"} tone={perf && perf.rr_avg >= 2.5 ? "gn" : "amb"} sub="planned" />
              <KpiTile label="MFE / MAE" value={perf && perf.mfe_avg != null ? `+${perf.mfe_avg.toFixed(1)} / ${perf.mae_avg.toFixed(1)}` : "—"} tone="ink" sub="avg excursion %" />
            </div>
          </div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={3} title="Model Calibration · Latest Card"
          sub="classifier accuracy · AUC · Brier · log-loss"
          style={headerStyle} right={<StateToggle name="tr-3" />} />
        <StateWrap state={s3.value} source="/api/calibration-history · model card">
          <div className="lens-pad">
            {card ? (
              <div className="kpi-row" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
                <KpiTile label="Accuracy" value={card.accuracy != null ? (card.accuracy * 100).toFixed(1) + "%" : "—"} tone={card.accuracy >= 0.5 ? "gn" : "amb"} sub={`${mk} · n=${((card.n_ok || 0) + (card.n_fail || 0)).toLocaleString()}`} />
                <KpiTile label="AUC" value={num(card.auc, 3)} tone={card.auc >= 0.6 ? "gn" : "amb"} sub="rank quality" />
                <KpiTile label="Brier" value={num(card.brier, 3)} tone={card.brier <= 0.2 ? "gn" : "amb"} sub="lower = better" />
                <KpiTile label="Log-loss" value={num(card.log_loss, 3)} tone="ink" sub={card.date || ""} />
              </div>
            ) : <div className="smc-empty mono dim2">— no calibration card for {mk}</div>}
          </div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={4} title="Forward Return Distribution"
          sub={`realized ${mk} forward returns · quantile profile`}
          style={headerStyle} right={<StateToggle name="tr-4" />} />
        <StateWrap state={s4.value} source="/api/ml-edge-stress-buckets · base scenario">
          <div className="lens-pad"><DistributionBars bkt={bkt} nObs={nObs} mk={mk} td={td} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={5} title="Cross-Lens Confluence" style={headerStyle} />
        <div className="lens-pad">
          <CrossLens lead="gn" cells={[
            { lens: "Track Rec.", verdict: lb != null ? lb.toFixed(0) + "%" : "—", tone: lbTone, note: pf != null ? `Wilson LB · PF ${pf.toFixed(2)}` : "Wilson LB" },
            { lens: "Expectancy", verdict: expR != null ? (expR >= 0 ? "+" : "") + expR.toFixed(2) + "R" : "—", tone: expR > 0 ? "gn" : "rd", note: "per closed trade" },
            { lens: "Model", verdict: card && card.accuracy != null ? (card.accuracy * 100).toFixed(0) + "%" : "—", tone: card && card.accuracy >= 0.5 ? "gn" : "amb", note: card ? `AUC ${num(card.auc, 2)}` : "accuracy" },
            { lens: "Fwd median", verdict: bkt ? pctd(bkt.q50) : "—", tone: bkt && bkt.q50 >= 0 ? "gn" : "rd", note: `${mk} base` },
            { lens: "This setup", verdict: hasSetup ? `n=${ss.n}` : "—", tone: hasSetup ? "gn" : "ink", note: hasSetup ? ticker.setupFamily : "no per-setup sample" },
          ]} />
        </div>
      </div>

      <div className="lens-call">
        <span className="label-cap">The Read · Track Record</span>
        <span className="mono">
          System: n=<b>{(perf && perf.closed) != null ? perf.closed.toLocaleString() : "—"}</b> closed,
          Wilson LB <b className={lbTone === "gn" ? "up" : lbTone === "rd" ? "dn" : "warn"}>{lb != null ? lb.toFixed(1) + "%" : "—"}</b>,
          PF <b className={pf >= 1.3 ? "up" : "warn"}>{pf != null ? pf.toFixed(2) : "—"}</b>,
          expectancy <b className={expR > 0 ? "up" : "dn"}>{expR != null ? (expR >= 0 ? "+" : "") + expR.toFixed(2) + "R" : "—"}</b> per trade.
          {lb != null && lb < 45 ? <> Edge is <b className="warn">modest</b> — below the 45% Wilson gate; size conservatively.</> : <> Edge clears the Wilson gate.</>}
        </span>
      </div>
    </div>
  );
}

// Real model-accuracy trend from /api/calibration-history (filtered to the mode).
function EdgeDecayChart({ series }) {
  const w = 240, h = 90;
  const data = (Array.isArray(series) ? series : []).map(s => s.accuracy).filter(v => typeof v === "number");
  if (data.length < 2) {
    return <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`}><text x={w/2} y={h/2} textAnchor="middle" fontSize="10" className="mono" fill="var(--ink-3)">accuracy trend · n/a</text></svg>;
  }
  const lo = Math.min(0.40, ...data) - 0.02, hi = Math.max(0.70, ...data) + 0.02;
  const xStep = (w - 24) / (data.length - 1);
  const y = v => h - 14 - ((v - lo) / (hi - lo)) * (h - 24);
  const pts = data.map((v, i) => [12 + i * xStep, y(v)]);
  const last = data[data.length - 1];
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
      <line x1="0" y1={y(0.50)} x2={w} y2={y(0.50)} stroke="var(--rd-dim)" strokeDasharray="3 3" />
      <text x="2" y={y(0.50) - 3} fontSize="9" className="mono" fill="var(--ink-3)">50% coin-flip</text>
      <polyline points={pts.map(p => p.join(",")).join(" ")} stroke="var(--gn)" strokeWidth="1.6" fill="none" />
      {pts.map((p, i) => <circle key={i} cx={p[0]} cy={p[1]} r="2" fill={i === pts.length-1 ? "var(--copper)" : "var(--gn)"} />)}
      <text x={w - 2} y="12" fontSize="9" className="mono" textAnchor="end" fill={last >= 0.5 ? "var(--gn)" : "var(--amb)"}>{(last * 100).toFixed(0)}% acc</text>
    </svg>
  );
}

// Real forward-return distribution from /api/ml-edge-stress-buckets (base scenario):
// q10/q25/q50/q75/q90 as decimals → quantile-box viz + median/IQR stats.
function DistributionBars({ bkt, nObs, mk, td }) {
  if (!bkt || bkt.q50 == null) {
    return <div className="smc-empty mono dim2">— forward-return buckets not loaded{td ? "" : " (loading…)"}</div>;
  }
  const qs = [bkt.q10, bkt.q25, bkt.q50, bkt.q75, bkt.q90];
  const lo = Math.min(...qs), hi = Math.max(...qs), span = (hi - lo) || 1;
  const x = v => ((v - lo) / span) * 100;
  const fmt = v => (v >= 0 ? "+" : "") + (v * 100).toFixed(1) + "%";
  const pos = v => v >= 0 ? "up" : "dn";
  return (
    <div className="dist-block">
      <div style={{ position: "relative", height: 56, margin: "6px 4px 2px" }}>
        {/* zero line */}
        {lo < 0 && hi > 0 && <div style={{ position: "absolute", left: `${x(0)}%`, top: 0, bottom: 18, width: 1, background: "var(--ink-3)" }} />}
        {/* q10–q90 whisker */}
        <div style={{ position: "absolute", left: `${x(bkt.q10)}%`, width: `${x(bkt.q90) - x(bkt.q10)}%`, top: 24, height: 2, background: "var(--line)" }} />
        {/* q25–q75 box */}
        <div style={{ position: "absolute", left: `${x(bkt.q25)}%`, width: `${x(bkt.q75) - x(bkt.q25)}%`, top: 16, height: 18, background: "color-mix(in oklab, var(--gn) 22%, transparent)", border: "1px solid var(--gn)", borderRadius: 3 }} />
        {/* median */}
        <div style={{ position: "absolute", left: `${x(bkt.q50)}%`, top: 12, height: 26, width: 2, background: "var(--copper)" }} />
        {[["q10", bkt.q10], ["q50", bkt.q50], ["q90", bkt.q90]].map(([k, v], i) => (
          <div key={i} className="mono dim2" style={{ position: "absolute", left: `${x(v)}%`, top: 40, fontSize: 9, transform: "translateX(-50%)" }}>{fmt(v)}</div>
        ))}
      </div>
      <div className="dist-stats">
        <span className="mono">Median <b className={pos(bkt.q50)}>{fmt(bkt.q50)}</b></span>
        <span className="mono">P25 <b className={pos(bkt.q25)}>{fmt(bkt.q25)}</b></span>
        <span className="mono">P75 <b className={pos(bkt.q75)}>{fmt(bkt.q75)}</b></span>
        <span className="mono dim2">{nObs ? nObs.toLocaleString() + " obs" : ""} · {mk} base</span>
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────
// ML EDGE — direction, magnitude cone, hit-net probability (REAL)
// ────────────────────────────────────────────────────────────
// Real per-ticker model forecast from /api/ml/{sym}?mode= (the same file the
// AI Predictions surface reads — direction / magnitude quantiles / hit-net /
// SHAP / model card). Mode-aware. Honest empty when the name isn't in the
// model universe. + /api/calibration-history for the system model card.
function useMlEdge(sym, mode) {
  const mk = mode === "POSITION" ? "position" : mode === "INVESTMENT" ? "invest" : "swing";
  const [d, setD] = React.useState(null);
  React.useEffect(() => {
    if (!sym) { setD({ loading: false, me: null, card: null }); return; }
    let live = true; setD(null);
    const J = u => fetch(u).then(r => (r.ok ? r.json() : null)).catch(() => null);
    Promise.all([J(`/api/ml/${encodeURIComponent(sym)}?mode=${mk}`), J("/api/calibration-history")])
      .then(([me, calib]) => {
        if (!live) return;
        const found = me && me.direction && typeof me.direction.p_up === "number";
        const series = (calib && Array.isArray(calib.series)) ? calib.series.filter(x => (x.mode || "swing") === mk) : [];
        setD({ loading: false, me: found ? me : null, card: series.length ? series[series.length - 1] : null });
      });
    return () => { live = false; };
  }, [sym, mk]);
  return d;
}

function LensML({ ticker, mode, sizeCat, headerStyle, kpiStyle, heroStyle }) {
  const s1 = useStateToggle("ml-1"); const s2 = useStateToggle("ml-2");
  const s3 = useStateToggle("ml-3"); const s4 = useStateToggle("ml-4");
  const data = useMlEdge(ticker && ticker.symbol, mode);
  const me = data && data.me;
  const card = data && data.card;

  if (!data) {
    return <div className="lens lens--ml"><div className="lens-section"><div className="lens-pad"><div className="smc-empty mono dim2" style={{ padding: 16 }}>Loading ML forecast…</div></div></div></div>;
  }
  if (!me) {
    return (
      <div className="lens lens--ml"><div className="lens-section"><div className="lens-pad">
        <div className="smc-empty mono dim2" style={{ padding: 16 }}>
          No ML-edge forecast for <b className="copper">{(ticker && ticker.symbol) || "this name"}</b> ({mode.toLowerCase()}) —
          it isn't in the model universe yet. The 3-head model scores ~1,100 liquid names per horizon.
        </div>
      </div></div></div>
    );
  }

  const hz = (me.horizon_days != null ? me.horizon_days : "—") + "d";
  const dir = me.direction || {}, mag = me.magnitude || {}, hit = me.hit_net || {};
  const pUp = dir.p_up;
  const hitNet = (hit.p_t1_first != null && hit.p_stop_first != null) ? +(hit.p_t1_first - hit.p_stop_first).toFixed(2) : null;
  const dirTone = pUp >= 0.6 ? "gn" : pUp >= 0.45 ? "amb" : "rd";
  const vColor = { pass: "gn", warn: "amb", fail: "rd" }[me.verdict && me.verdict.color] || "ink";
  const health = me.model_meta && me.model_meta.calibration_health;
  const auc = hit.model_auc != null ? hit.model_auc : (card && card.auc);
  const fmt = v => v == null ? "—" : (v >= 0 ? "+" : "") + v.toFixed(1) + "%";

  return (
    <div className="lens lens--ml">
      <div className="hero ml-hero">
        <div className="th-left">
          <div className="label-cap">ML forecast · {me.mode_label || hz} · {mode}</div>
          <div className="th-score">
            <div className="th-score-num mono">{hitNet == null ? "—" : (hitNet >= 0 ? "+" : "") + hitNet.toFixed(2)}</div>
            <Pill tone={hitNet == null ? "ink" : hitNet >= 0 ? "gn" : "rd"} dot>hit-net edge</Pill>
            <Pill tone={dirTone} small>P(up) {pUp != null ? Math.round(pUp * 100) + "%" : "—"}</Pill>
            {me.verdict && me.verdict.text && <Pill tone={vColor} small>{me.verdict.text}</Pill>}
          </div>
          <div className="th-pill-row">
            {health && <Pill tone={health === "ok" ? "gn" : "amb"} small>Calibration {health}</Pill>}
            {auc != null && <Pill tone={auc >= 0.6 ? "gn" : "amb"} small>Model AUC {auc.toFixed(2)}</Pill>}
            {me.verdict && me.verdict.confidence && <Pill tone="ink" small>Conf {me.verdict.confidence}</Pill>}
          </div>
        </div>
        <div className="th-right">
          <MLConeChart mag={mag} hz={hz} />
        </div>
      </div>

      <div className="lens-section">
        <SectionHeader n={1} title="Direction · P(up)"
          sub={`classifier · over next ${hz}`}
          style={headerStyle} right={<StateToggle name="ml-1" />} />
        <StateWrap state={s1.value} source="/api/ml · direction head">
          <div className="lens-pad">
            <ProbBar v={pUp} label={`P(up · ${hz})`} />
            <div className="kpi-row" style={{ gridTemplateColumns: "repeat(3, 1fr)", marginTop: 10 }}>
              <KpiTile label="P(up)" value={pUp != null ? (pUp * 100).toFixed(0) + "%" : "—"} tone={dirTone} />
              <KpiTile label="P(chop)" value={dir.p_chop != null ? (dir.p_chop * 100).toFixed(0) + "%" : "—"} tone="ink" />
              <KpiTile label="P(down)" value={dir.p_dn != null ? (dir.p_dn * 100).toFixed(0) + "%" : "—"} tone={dir.p_dn > 0.4 ? "rd" : "ink"} />
            </div>
          </div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={2} title="Magnitude Cone"
          sub={`quantile regression · ${hz} return distribution`}
          style={headerStyle} right={<StateToggle name="ml-2" />} />
        <StateWrap state={s2.value} source="/api/ml · quantile head">
          <div className="lens-pad">
            <div className="kpi-row" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
              <KpiTile label="P10" value={fmt(mag.q10)} tone="rd" />
              <KpiTile label="P50 (median)" value={fmt(mag.q50)} tone={mag.q50 < 0 ? "rd" : "gn"} />
              <KpiTile label="P90" value={fmt(mag.q90)} tone="gn" />
              <KpiTile label="Skew" value={mag.skew != null ? (mag.skew >= 0 ? "+" : "") + mag.skew.toFixed(2) : "—"} tone={mag.skew >= 0 ? "gn" : "rd"} sub={mag.skew >= 0 ? "right-skewed" : "left-skewed"} />
            </div>
          </div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={3} title="Hit-Net (T1 vs Stop)"
          sub="P(T1 first) − P(stop first) — the actionable edge"
          style={headerStyle} right={<StateToggle name="ml-3" />} />
        <StateWrap state={s3.value} source="/api/ml · hit-net head">
          <div className="lens-pad"><HitNetBar hit={hit} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={4} title="Calibration · Feature Importance"
          sub="model card metrics + top SHAP drivers"
          style={headerStyle} right={<StateToggle name="ml-4" />} />
        <StateWrap state={s4.value} source="/api/ml · SHAP + /api/calibration-history">
          <div className="lens-pad"><CalibrationPanel shap={me.shap} card={card} auc={auc} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={5} title="Cross-Lens Confluence" style={headerStyle} />
        <div className="lens-pad">
          <CrossLens lead="violet" cells={[
            { lens: "AI Edge", verdict: hitNet == null ? "—" : `${hitNet >= 0 ? "+" : ""}${hitNet.toFixed(2)}`, tone: hitNet == null ? "ink" : hitNet >= 0 ? "gn" : "rd", note: `hit-net · ${hz}` },
            { lens: "Direction", verdict: pUp != null ? `${Math.round(pUp * 100)}%` : "—", tone: dirTone, note: `P(up) ${hz}` },
            { lens: "Magnitude", verdict: fmt(mag.q50), tone: mag.q50 >= 0 ? "gn" : "rd", note: `q10 ${fmt(mag.q10)} / q90 ${fmt(mag.q90)}` },
            { lens: "Verdict", verdict: me.verdict ? me.verdict.text : "—", tone: vColor, note: me.verdict ? me.verdict.confidence + " conf" : "" },
            { lens: "Model", verdict: auc != null ? `AUC ${auc.toFixed(2)}` : "—", tone: auc >= 0.6 ? "gn" : "amb", note: health ? "calib " + health : "" },
          ]} />
        </div>
      </div>

      <div className="lens-call">
        <span className="label-cap">The Read · AI Edge · {mode}</span>
        <span className="mono">
          P(up) <b className={dirTone === "gn" ? "up" : dirTone === "rd" ? "dn" : "warn"}>{pUp != null ? Math.round(pUp * 100) + "%" : "—"}</b>,
          hit-net <b className={hitNet > 0 ? "up" : "dn"}>{hitNet == null ? "—" : (hitNet >= 0 ? "+" : "") + hitNet.toFixed(2)}</b> (P(T1) {hit.p_t1_first != null ? Math.round(hit.p_t1_first * 100) + "%" : "—"} vs P(stop) {hit.p_stop_first != null ? Math.round(hit.p_stop_first * 100) + "%" : "—"}),
          median <b className={mag.q50 >= 0 ? "up" : "dn"}>{fmt(mag.q50)}</b> over {hz}.
          {hitNet != null && hitNet <= 0 ? <> Path edge is <b className="warn">negative</b> — stop likely hit before target; no long edge here.</> : <> Verdict: <b className={vColor === "gn" ? "up" : "warn"}>{me.verdict ? me.verdict.text : "—"}</b>.</>}
        </span>
      </div>
    </div>
  );
}

function ProbBar({ v, label }) {
  const have = typeof v === "number";
  const pts = have ? Math.round((v - 0.5) * 100) : 0;
  return (
    <div className="probbar">
      <div className="probbar-label mono dim2">{label}</div>
      <div className="probbar-bar">
        <div className="probbar-fill" style={{ width: `${(have ? v : 0) * 100}%` }} />
        <div className="probbar-mid" />
      </div>
      <div className="probbar-val mono"><b>{have ? (v * 100).toFixed(0) + "%" : "—"}</b></div>
      <div className="probbar-meta mono dim">vs 50% baseline · {pts >= 0 ? "+" : ""}{pts}pt edge</div>
    </div>
  );
}

function HitNetBar({ hit }) {
  const pT1 = (hit && hit.p_t1_first != null) ? hit.p_t1_first : null;
  const pStop = (hit && hit.p_stop_first != null) ? hit.p_stop_first : null;
  if (pT1 == null || pStop == null) return <div className="smc-empty mono dim2">— hit-net not available</div>;
  return (
    <div className="hitnet">
      <div className="hn-row">
        <span className="hn-label mono">P(T1 first)</span>
        <div className="hn-bar"><div className="hn-fill hn-gn" style={{ width: `${pT1 * 100}%` }} /></div>
        <span className="hn-val mono up">{(pT1 * 100).toFixed(0)}%</span>
      </div>
      <div className="hn-row">
        <span className="hn-label mono">P(stop first)</span>
        <div className="hn-bar"><div className="hn-fill hn-rd" style={{ width: `${pStop * 100}%` }} /></div>
        <span className="hn-val mono dn">{(pStop * 100).toFixed(0)}%</span>
      </div>
      <div className="hn-row hn-final">
        <span className="hn-label mono">Hit-net</span>
        <div className="hn-bar"><div className="hn-fill" style={{
          width: `${(pT1 - pStop) * 100}%`,
          background: "linear-gradient(90deg, var(--copper), var(--violet))",
        }} /></div>
        <span className="hn-val mono copper"><b>+{((pT1 - pStop) * 100).toFixed(0)}%</b></span>
      </div>
    </div>
  );
}

function MLConeChart({ mag, hz }) {
  const q90 = mag && mag.q90 != null ? +mag.q90.toFixed(1) : 0;
  const q50 = mag && mag.q50 != null ? +mag.q50.toFixed(1) : 0;
  const q10 = mag && mag.q10 != null ? +mag.q10.toFixed(1) : 0;
  return (
    <svg viewBox="0 0 300 120" width="300" height="120" style={{ overflow: "visible" }}>
      <defs>
        <linearGradient id="mlc-gn" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--gn)" stopOpacity="0.35" />
          <stop offset="100%" stopColor="var(--gn)" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="mlc-rd" x1="0" y1="1" x2="0" y2="0">
          <stop offset="0%" stopColor="var(--rd)" stopOpacity="0.30" />
          <stop offset="100%" stopColor="var(--rd)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <line x1="20" y1="60" x2="280" y2="60" stroke="var(--line)" strokeDasharray="3 3" />
      <path d="M 20 60 Q 150 24 280 16 L 280 60 L 20 60 Z" fill="url(#mlc-gn)" />
      <path d="M 20 60 Q 150 88 280 104 L 280 60 L 20 60 Z" fill="url(#mlc-rd)" />
      <path d="M 20 60 Q 150 24 280 16" stroke="var(--gn)" strokeWidth="1.4" fill="none" opacity="0.55" />
      <path d="M 20 60 Q 150 38 280 38" stroke="var(--gn)" strokeWidth="1.8" fill="none"
            style={{ filter: "drop-shadow(0 0 6px var(--gn))" }} />
      <path d="M 20 60 Q 150 88 280 104" stroke="var(--rd)" strokeWidth="1.4" fill="none" opacity="0.55" />
      <circle cx="20" cy="60" r="4" fill="var(--copper)"
              style={{ filter: "drop-shadow(0 0 8px var(--copper))" }} />
      <text x="276" y="13" fontSize="9.5" className="mono" textAnchor="end" fill="var(--gn)">P90 +{q90}%</text>
      <text x="276" y="35" fontSize="9.5" className="mono" textAnchor="end" fill="var(--gn)" fontWeight="500">P50 {q50 >= 0 ? "+" : ""}{q50}%</text>
      <text x="276" y="113" fontSize="9.5" className="mono" textAnchor="end" fill="var(--rd)">P10 {q10}%</text>
      <text x="20" y="113" fontSize="9" className="mono" fill="var(--ink-3)">T+0</text>
      <text x="276" y="60" fontSize="9" className="mono" textAnchor="end" fill="var(--ink-3)">{hz}</text>
    </svg>
  );
}

// Real SHAP (me.shap.dir_top) + real model card (calibration-history: accuracy /
// AUC / Brier / log-loss). No fabricated reliability scatter — we don't have
// per-bin reliability data, so we surface the real scalar metrics instead.
function CalibrationPanel({ shap, card, auc }) {
  const feats = (shap && Array.isArray(shap.dir_top)) ? shap.dir_top.slice(0, 7) : [];
  const maxAbs = feats.length ? Math.max(...feats.map(f => Math.abs(f.shap || 0))) || 1 : 1;
  const num = (v, d) => v == null ? "—" : v.toFixed(d == null ? 3 : d);
  return (
    <div className="cal-grid">
      <div className="cal-block">
        <div className="label-cap" style={{ marginBottom: 6 }}>Model card</div>
        {(card || auc != null) ? (
          <div className="kpi-row" style={{ gridTemplateColumns: "repeat(2, 1fr)", gap: 8 }}>
            <KpiTile label="Accuracy" value={card && card.accuracy != null ? (card.accuracy * 100).toFixed(1) + "%" : "—"} tone={card && card.accuracy >= 0.5 ? "gn" : "amb"} />
            <KpiTile label="AUC" value={num(auc != null ? auc : (card && card.auc), 3)} tone={(auc || (card && card.auc)) >= 0.6 ? "gn" : "amb"} />
            <KpiTile label="Brier" value={num(card && card.brier, 3)} tone={card && card.brier <= 0.2 ? "gn" : "amb"} sub="lower better" />
            <KpiTile label="Log-loss" value={num(card && card.log_loss, 3)} tone="ink" />
          </div>
        ) : <div className="smc-empty mono dim2">— model card not loaded</div>}
        {card && card.date && <div className="cal-note mono dim2" style={{ marginTop: 6 }}>as of {card.date} · n={((card.n_ok || 0) + (card.n_fail || 0)).toLocaleString()}</div>}
      </div>
      <div className="cal-block">
        <div className="label-cap" style={{ marginBottom: 6 }}>Top features · SHAP</div>
        {feats.length ? (
          <div className="feat-list">
            {feats.map((f, i) => {
              const w = Math.abs(f.shap || 0) / maxAbs;
              const neg = (f.shap || 0) < 0;
              return (
                <div key={i} className="feat-row">
                  <span className="mono" style={{ fontSize: 11 }}>{f.feature}</span>
                  <div className="feat-bar"><div className="feat-fill" style={{ width: `${w * 100}%`, background: neg ? "var(--rd)" : "var(--gn)" }} /></div>
                  <span className={`mono dim ${neg ? "dn" : "up"}`}>{neg ? "−" : "+"}{Math.abs(f.shap).toFixed(2)}</span>
                </div>
              );
            })}
          </div>
        ) : <div className="smc-empty mono dim2">— SHAP drivers not available</div>}
      </div>
    </div>
  );
}

window.LensTrack = LensTrack;
window.LensML = LensML;

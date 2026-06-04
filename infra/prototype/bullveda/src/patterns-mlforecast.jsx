// patterns-mlforecast.jsx — "ML Forecast" sub-tab for the Patterns lens.
// Treats theory signals + price/volume features as MODEL FEATURES and runs a
// transparent logistic-style meta-model: weighted-sum → sigmoid → P(up) →
// directional verdict + confidence band.
//
// REAL DATA: fetched via /api/pattern/mlforecast/{sym}?mode={mode}.
// The Python engine (engines/mlforecast.py) computes 8 bar features + up to 6
// sibling theory votes deterministically from live EODHD bars.
// Fallback: the seeded-RNG fixture below renders in standalone showcase / no-server.

const { useMemo: useMemoMlf } = React;

// ── fixture model (fallback only — used in standalone showcase) ──────────────
// These seven theory feature readers use a seeded RNG keyed to (sym, theory)
// so the standalone showcase renders stable, name-specific stances.
const MLF_FIXTURE_FEATURES = [
  { id: "wyckoff", w: 0.20, tone: "copper",
    read: (r) => { const ph = ["Phase A (stopping)", "Phase B (building)", "Phase C (spring)", "Phase D (markup)", "Phase E (trend)"][Math.floor(r() * 5)]; const bull = /C|D|E/.test(ph); return { label: `Wyckoff · ${ph}`, p: bull ? 0.6 + r() * 0.32 : 0.3 + r() * 0.25 }; } },
  { id: "elliott", w: 0.18, tone: "violet",
    read: (r) => { const wn = ["Wave 1", "Wave 2", "Wave 3", "Wave 4", "Wave 5", "Wave A", "Wave C"][Math.floor(r() * 7)]; const bull = /1|3|5/.test(wn); return { label: `Elliott · ${wn}`, p: bull ? 0.58 + r() * 0.34 : 0.28 + r() * 0.26 }; } },
  { id: "fib", w: 0.16, tone: "amb",
    read: (r) => { const z = r(); const at = z > 0.6 ? "at .618 support" : z > 0.3 ? "mid-range" : "below .786"; return { label: `Fibonacci · ${at}`, p: z > 0.6 ? 0.62 + r() * 0.3 : z > 0.3 ? 0.45 + r() * 0.15 : 0.25 + r() * 0.2 }; } },
  { id: "vp", w: 0.14, tone: "cy",
    read: (r) => { const a = ["above VAH (accept)", "at POC (fair)", "below VAL (reject)"][Math.floor(r() * 3)]; return { label: `Volume Profile · ${a}`, p: a[0] === "a" ? 0.6 + r() * 0.28 : a[0] === "a" ? 0.5 : a.includes("below") ? 0.3 + r() * 0.2 : 0.48 + r() * 0.1 }; } },
  { id: "smc", w: 0.12, tone: "gn",
    read: (r) => { const s = ["Bull BOS", "CHoCH↑", "OB retest", "Liq sweep ↓", "Bear BOS"][Math.floor(r() * 5)]; const bull = !/Bear|↓/.test(s); return { label: `SMC · ${s}`, p: bull ? 0.58 + r() * 0.32 : 0.26 + r() * 0.24 }; } },
  { id: "classical", w: 0.12, tone: "cy",
    read: (r) => { const c = ["VCP base", "Asc. triangle", "Bull flag", "Falling wedge", "H&S top", "Range"][Math.floor(r() * 6)]; const bull = !/H&S|Range/.test(c); return { label: `Classical · ${c}`, p: bull ? 0.56 + r() * 0.32 : 0.32 + r() * 0.22 }; } },
  { id: "harmonic", w: 0.08, tone: "violet",
    read: (r) => { const h = ["Gartley (bull)", "Bat (bull)", "Crab (bull)", "Bearish Gartley", "no pattern"][Math.floor(r() * 5)]; const bull = /bull/.test(h); return { label: `Harmonic · ${h}`, p: bull ? 0.6 + r() * 0.3 : h === "no pattern" ? 0.46 + r() * 0.08 : 0.3 + r() * 0.2 }; } },
];

function _buildFixtureModel(ticker) {
  const sym = (ticker && ticker.symbol) || "ARGN";
  const px  = (ticker && ticker.price)  || 213.4;
  const mk = (salt) => {
    let s = 0; const k = sym + salt;
    for (let i = 0; i < k.length; i++) s = (s * 31 + k.charCodeAt(i)) & 0x7fffffff;
    return () => { s = (s * 1103515245 + 12345) & 0x7fffffff; return s / 0x7fffffff; };
  };
  const feats = MLF_FIXTURE_FEATURES.map((f) => {
    const stance = f.read(mk(f.id));
    const p      = Math.max(0.05, Math.min(0.97, stance.p));
    return { name: stance.label, value: p, contribution: +((p - 0.5) * f.w * 2).toFixed(3), note: `weight ${Math.round(f.w * 100)}%`, tone: f.tone, w: f.w };
  });
  const ens    = feats.reduce((a, f) => a + f.contribution, 0);
  const pUp    = Math.max(0.05, Math.min(0.95, 0.5 + ens * 0.9));
  const score  = Math.round(Math.max(2, Math.min(99, 50 + ens * 95)));
  const verdict = score >= 66 ? "BUY" : score <= 40 ? "AVOID" : "HOLD";
  const confV   = Math.abs(ens) > 0.32 ? 0.78 : Math.abs(ens) > 0.16 ? 0.55 : 0.35;
  const agree  = feats.filter(f => f.contribution >= 0).length;
  const vol    = 0.02 + (sym.charCodeAt(0) % 7) / 600;
  const band   = {
    lo:  +((ens * vol * 10 - vol * Math.sqrt(10)) * 100).toFixed(2),
    mid: +((ens * vol * 10) * 100).toFixed(2),
    hi:  +((ens * vol * 10 + vol * Math.sqrt(10)) * 100).toFixed(2),
  };
  const hz_label = "10-day";
  const fmax   = Math.max(...feats.map(f => Math.abs(f.contribution)));
  // votes from feature labels
  const votes  = feats.map(f => {
    const [theory] = (f.name || "").split(" · ");
    return { theory, bias: f.contribution > 0 ? 0.5 : -0.5, label: f.name, weight: f.w };
  });
  const read   = agree >= 5
    ? `Pattern theories stacked bullish (${agree}/${feats.length}) — meta-model P(up) ${Math.round(pUp * 100)}%. Treat as ${Math.abs(ens) > 0.32 ? "HIGH" : "MEDIUM"} conviction.`
    : `Mixed pattern evidence (${agree}/${feats.length} aligned) — wait for confluence before sizing. P(up) ${Math.round(pUp * 100)}%.`;
  return { feats, ens: +ens.toFixed(2), pUp: +pUp.toFixed(2), score, verdict,
           confidence: confV, agree, band, hz_label, fmax, votes, read,
           calibration: "Illustrative fixture — connect to server for live bars.", bars: [] };
}

// ── data hook: real → fixture fallback ──────────────────────────────────────
function useMLForecastModel(ticker, mode) {
  const { real, state, sym } = usePatternModel("mlforecast", ticker, mode);
  const tf      = (real && real.meta && real.meta.tf) || null;
  const fixture = useMemoMlf(() => _buildFixtureModel(ticker), [sym]);

  const usable = (
    state === "loaded" &&
    real && real.ok &&
    real.state === "real" &&
    real.pUp != null &&
    real.features && real.features.length > 0
  );

  if (usable) {
    // Map real payload → shape the sub-components expect.
    // Real features come as {name, value, contribution, note} arrays.
    // Real votes come as {theory, bias, label, weight, contribution}.
    const featsRaw = real.features || [];
    const votesRaw = real.votes    || [];
    const allContribs = featsRaw.map(f => f.contribution || 0).concat(votesRaw.map(v => v.contribution || 0));
    const fmax = Math.max(...allContribs.map(Math.abs), 0.001);

    return {
      model: {
        feats:       featsRaw,
        ens:         real.stat  && typeof real.stat.raw_ens !== "undefined" ? +real.stat.raw_ens.toFixed(2) : 0,
        pUp:         real.pUp,
        score:       Math.round(Math.max(2, Math.min(99, real.pUp * 100))),
        verdict:     real.verdict || "HOLD",
        confidence:  real.confidence,
        agree:       real.stat && real.stat.agree  != null ? real.stat.agree  : 0,
        n_theories:  real.stat && real.stat.n_theories != null ? real.stat.n_theories : votesRaw.length,
        band:        real.band  || { lo: 0, mid: 0, hi: 0 },
        hz_label:    (real.stat && real.stat.hz_label) || (real.meta && real.meta.horizon) || tf || "",
        fmax,
        votes:       votesRaw,
        bars:        real.bars  || [],
        read:        real.read  || "",
        calibration: real.calibration || "",
      },
      state: "real", sym, tf, usable: true,
    };
  }

  if (state === "loaded" && real && real.ok) {
    return {
      model: fixture,
      state: "none", sym, tf, usable: false,
      message: (real && real.message) || "No usable bar history for ML Forecast.",
    };
  }

  return {
    model: fixture,
    state: state === "loading" ? "loading" : "mock",
    sym, tf, usable: false,
  };
}

// ── feature waterfall chart ──────────────────────────────────────────────────
// Shows price/vol features (raw bars side) and theory votes side-by-side.
function MLFFeatureRows({ feats, fmax, isVotes }) {
  const maxAbs = fmax || 0.001;
  return (
    <div className="mlf-feats">
      <div className="mlf-feat mlf-feat--head">
        <span className="mlf-feat-k">{isVotes ? "Theory · stance" : "Feature"}</span>
        <span className="mlf-feat-p">{isVotes ? "Bias" : "Value"}</span>
        <span className="mlf-feat-track-h">bearish ◂ contribution ▸ bullish</span>
        <span className="mlf-feat-w">weight</span>
      </div>
      {(feats || []).map((f, i) => {
        const contrib = f.contribution || 0;
        const bull    = contrib >= 0;
        const pct     = Math.abs(contrib) / maxAbs;
        const val     = isVotes ? (f.bias != null ? f.bias : contrib) : (f.value != null ? f.value : contrib);
        const pTone   = bull ? "gn" : "rd";
        const [label, ...rest] = (f.name || f.label || "").split(" · ");
        const sub     = rest.join(" · ") || (f.note || "");
        const wPct    = f.weight != null ? Math.round(f.weight * 100) : 0;
        return (
          <div key={i} className="mlf-feat">
            <span className="mlf-feat-k">
              <b className="mlf-feat-theory">{label}</b>
              {sub && <span className="mlf-feat-stance">{sub}</span>}
            </span>
            <span className={`mlf-feat-p mono kpi-tone--${pTone}`}>
              {isVotes ? (val >= 0 ? "+" : "") + val.toFixed(2) : (typeof val === "number" ? val.toFixed(2) : val)}
            </span>
            <span className="mlf-feat-track">
              <span className="mlf-feat-zero" />
              <span className={`mlf-feat-fill ${bull ? "is-bull" : "is-bear"}`}
                    style={bull
                      ? { left: "50%", width: `${pct * 50}%` }
                      : { right: "50%", width: `${pct * 50}%` }} />
              <span className={`mlf-feat-val mono ${bull ? "up" : "dn"}`}
                    style={bull ? { left: "calc(50% + 4px)" } : { right: "calc(50% + 4px)" }}>
                {bull ? "+" : ""}{contrib.toFixed(3)}
              </span>
            </span>
            <span className="mlf-feat-w mono dim2">{wPct}%</span>
          </div>
        );
      })}
    </div>
  );
}

// ── stat strip ───────────────────────────────────────────────────────────────
function MLFStat({ model, tf }) {
  const vt     = (model.verdict || "HOLD") === "BUY" ? "gn" : (model.verdict || "HOLD") === "AVOID" ? "rd" : "amb";
  const conf   = typeof model.confidence === "number" ? model.confidence : 0;
  const band   = model.band   || {};
  const agree  = model.agree  != null  ? model.agree  : 0;
  const total  = model.n_theories != null ? model.n_theories : (model.votes || []).length;
  return (
    <div className="pv-stat">
      <div className="pv-stat-cell">
        <div className="label-cap">ML verdict</div>
        <div className={`pv-stat-v mono ${vt === "gn" ? "up" : vt === "rd" ? "dn" : "warn"}`}>{model.verdict || "HOLD"}</div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">P(up · {model.hz_label || tf || ""})</div>
        <div className={`pv-stat-v mono ${model.pUp >= 0.55 ? "up" : model.pUp <= 0.45 ? "dn" : "warn"}`}>
          {Math.round((model.pUp || 0) * 100)}%
        </div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">Theories agree</div>
        <div className="pv-stat-v mono">{agree}/{total}</div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">Band ({model.hz_label || ""})</div>
        <div className="pv-stat-v mono">
          <span className="dn">{band.lo != null ? (band.lo >= 0 ? "+" : "") + band.lo.toFixed(1) + "%" : "—"}</span>
          <span className="dim2"> / </span>
          <span className={band.mid >= 0 ? "up" : "dn"}>{band.mid != null ? (band.mid >= 0 ? "+" : "") + band.mid.toFixed(1) + "%" : "—"}</span>
          <span className="dim2"> / </span>
          <span className="up">{band.hi != null ? (band.hi >= 0 ? "+" : "") + band.hi.toFixed(1) + "%" : "—"}</span>
        </div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">Confidence</div>
        <div className="pv-stat-v"><ConfBar value={conf} tone={vt} width={72} /></div>
      </div>
    </div>
  );
}

// ── ensemble summary row ─────────────────────────────────────────────────────
function MLFEnsembleLine({ model }) {
  const ens = model.ens || 0;
  const vt  = (model.verdict || "HOLD") === "BUY" ? "gn" : (model.verdict || "HOLD") === "AVOID" ? "rd" : "amb";
  return (
    <div className="mlf-ens mono">
      <span className="dim2">weighted ensemble</span>{" "}
      <b className={ens >= 0 ? "up" : "dn"}>{ens >= 0 ? "+" : ""}{ens.toFixed(3)}</b>
      <span className="mlf-ens-arrow dim2"> → </span>
      <span className="dim2">P(up)</span>{" "}
      <b>{Math.round((model.pUp || 0) * 100)}%</b>
      <span className="mlf-ens-arrow dim2"> → </span>
      <b className={`mlf-ens-verdict kpi-tone--${vt}`}>{model.verdict || "HOLD"}</b>
    </div>
  );
}

// ── projection band table ────────────────────────────────────────────────────
function MLFBandTable({ model, cur }) {
  const band = model.band || {};
  const hz   = model.hz_label || "";
  const cur_close = cur || 0;
  const toPrice = (pct) => cur_close ? +(cur_close * (1 + pct / 100)).toFixed(2) : null;
  const rows = [
    { q: "High case",  ret: band.hi,  tone: "gn"  },
    { q: "Mid (expected)", ret: band.mid, tone: band.mid >= 0 ? "up" : "dn" },
    { q: "Low case",   ret: band.lo,  tone: "amb" },
  ].filter(x => x.ret != null);
  return (
    <MiniTable
      cols={[
        { h: "Scenario",  k: "q" },
        ...(cur_close ? [{ h: "Price", k: "price", mono: true, align: "right" }] : []),
        { h: `Return (${hz})`, k: "ret", mono: true, align: "right" },
      ]}
      rows={rows.map(x => ({
        q:     <b>{x.q}</b>,
        price: cur_close ? <span className="dim2">${toPrice(x.ret)}</span> : null,
        ret:   <span className={x.ret >= 0 ? "up" : "dn"}>{x.ret >= 0 ? "+" : ""}{x.ret.toFixed(1)}%</span>,
      }))}
    />
  );
}

// ── read box ─────────────────────────────────────────────────────────────────
function MLFRead({ model, state }) {
  const text = (state === "real" && model.read) ? model.read : null;
  const fallback = (model.agree || 0) >= Math.ceil(((model.n_theories || 0) || (model.votes || []).length) * 0.6)
    ? <>Pattern theories <b className="up">stacked bullish</b> — meta-model P(up) <b>{Math.round((model.pUp || 0) * 100)}%</b>. Treat as {model.confidence > 0.65 ? "HIGH" : "MEDIUM"} conviction.</>
    : <>Mixed pattern evidence — <b className="warn">wait for confluence</b> before sizing. P(up) <b>{Math.round((model.pUp || 0) * 100)}%</b>.</>;
  return (
    <div className="pv-invalid" style={{ border: "1px solid var(--line)", background: "var(--bg-1)" }}>
      <span className="label-cap">Read</span>
      <span className="mono">{text || fallback}</span>
    </div>
  );
}

// ── candlestick chart (bars from the real engine) ────────────────────────────
function MLFChart({ model, height }) {
  if (!model.bars || !model.bars.length) return null;
  return (
    <CandleChart
      bars={model.bars}
      height={height || 260}
      accent="violet"
    />
  );
}

// ── calibration note ─────────────────────────────────────────────────────────
function MLFCalibration({ model, state }) {
  const note = (state === "real" && model.calibration) ? model.calibration : null;
  if (!note) return null;
  return (
    <div className="pv-pad">
      <div className="mono dim2" style={{ fontSize: 11, lineHeight: 1.5 }}>{note}</div>
    </div>
  );
}

// ── main view (3 layout directions) ─────────────────────────────────────────
function MLForecastView({ ticker, dir, mode }) {
  const { model, state, message, sym, tf, usable } = useMLForecastModel(ticker, mode);

  const SrcBar = (
    <div className="pv-srcbar">
      <PatternSrcBadge state={state} usable={usable} sym={sym} tf={tf} />
    </div>
  );

  const cur_close = (ticker && ticker.price) || 0;

  // ── honest empty state ───────────────────────────────────────────────────
  if (state === "none") {
    return (
      <div className="pv-view">
        {SrcBar}
        <div className="pv-empty">
          <div className="pv-empty-i mono">— no ML Forecast data</div>
          <div className="pv-empty-msg">{message || `Insufficient bar history to run the meta-model for ${sym || "this asset"}.`}</div>
          <div className="pv-empty-sub mono dim2">The engine requires ≥30 historical bars. When data is available it will populate automatically.</div>
        </div>
      </div>
    );
  }

  // ── feature section (price/vol) ──────────────────────────────────────────
  const FeatureSection = (
    <>
      <SectionHeader n={1}
        title="Price &amp; volume features"
        sub="8 bar-derived signals — trend, momentum, volume, volatility"
        style="minimal" />
      <div className="pv-pad">
        <MLFFeatureRows feats={model.feats || []} fmax={model.fmax || 0.001} isVotes={false} />
      </div>
    </>
  );

  // ── theory votes section ────────────────────────────────────────────────
  const VoteSection = (model.votes && model.votes.length > 0) ? (
    <>
      <SectionHeader n={2}
        title="Theory votes"
        sub="sibling engines distilled to directional bias · weighted ensemble pool"
        style="minimal" />
      <div className="pv-pad">
        <MLFFeatureRows feats={model.votes || []} fmax={model.fmax || 0.001} isVotes={true} />
        <MLFEnsembleLine model={model} />
      </div>
    </>
  ) : (
    <>
      <SectionHeader n={2} title="Theory votes" sub="no sibling theory votes available" style="minimal" />
      <div className="pv-pad"><div className="mono dim2" style={{ fontSize: 12 }}>Theory engines returned no usable structure for this name/timeframe.</div></div>
    </>
  );

  // ── chart section ────────────────────────────────────────────────────────
  const ChartSection = model.bars && model.bars.length ? (
    <>
      <SectionHeader n={3} title="Price bars" sub="windowed OHLCV used for feature computation" style="minimal" />
      <div className="pv-pad"><MLFChart model={model} height={240} /></div>
    </>
  ) : null;

  // ── band + read ──────────────────────────────────────────────────────────
  const BandRead = (
    <div className="pv-2col">
      <div>
        <div className="pv-block-h label-cap">Confidence band · {model.hz_label || tf || ""}</div>
        <MLFBandTable model={model} cur={cur_close || (model.bars && model.bars.length && model.bars[model.bars.length - 1].c)} />
      </div>
      <div>
        <div className="pv-block-h label-cap">Cross-check · AI Predictions</div>
        {(typeof window !== "undefined" && window.AIPredict) ? (() => {
          const ap = window.AIPredict.predict(sym);
          const apVt = ap && (ap.verdict === "BUY" ? "gn" : ap.verdict === "SELL" ? "rd" : "amb");
          const myVt = (model.verdict || "HOLD") === "BUY" ? "gn" : (model.verdict || "HOLD") === "AVOID" ? "rd" : "amb";
          return (
            <MiniTable
              cols={[{ h: "Model", k: "m" }, { h: "Verdict", k: "v" }, { h: "P(up)", k: "p", align: "right" }]}
              rows={[
                { m: "Pattern meta-model", v: <Pill tone={myVt} small>{model.verdict || "HOLD"}</Pill>, p: `${Math.round((model.pUp || 0) * 100)}%` },
                { m: "AI ensemble (3-head)", v: <Pill tone={apVt} small>{ap && ap.verdict}</Pill>, p: ap ? `${Math.round((ap.pUp || 0) * 100)}%` : "—" },
              ]} />
          );
        })() : <div className="mono dim2" style={{ fontSize: 12, padding: 8 }}>AI Predictions engine not loaded.</div>}
        <div style={{ marginTop: 10 }}><MLFRead model={model} state={state} /></div>
      </div>
    </div>
  );

  // ── dir C — dossier (compact, data-dense) ───────────────────────────────
  if (dir === "C") {
    return (
      <div className="pv-view pv-view--dossier">
        {SrcBar}
        <MLFStat model={model} tf={tf} />
        <div className="pv-2col">
          <div>
            {FeatureSection}
          </div>
          <div>
            {VoteSection}
          </div>
        </div>
        {ChartSection}
        {BandRead}
        <MLFCalibration model={model} state={state} />
      </div>
    );
  }

  // ── dir B — split (chart left, analysis right) ───────────────────────────
  if (dir === "B") {
    return (
      <div className="pv-view">
        {SrcBar}
        <MLFStat model={model} tf={tf} />
        <div className="pv-split">
          <div className="pv-split-main">
            {FeatureSection}
            {VoteSection}
          </div>
          <div className="pv-split-side">
            {ChartSection}
            <SectionHeader n={4} title="Band &amp; read" style="minimal" />
            <div className="pv-pad">
              <MLFBandTable model={model} cur={cur_close || (model.bars && model.bars.length && model.bars[model.bars.length - 1].c)} />
            </div>
            <div className="pv-pad"><MLFRead model={model} state={state} /></div>
          </div>
        </div>
        <MLFCalibration model={model} state={state} />
      </div>
    );
  }

  // ── dir A — chart-led (default) ──────────────────────────────────────────
  return (
    <div className="pv-view">
      {SrcBar}
      <MLFStat model={model} tf={tf} />
      {FeatureSection}
      {VoteSection}
      {ChartSection}
      {BandRead}
      <MLFCalibration model={model} state={state} />
    </div>
  );
}

// ── dynamic read line (for lens summary / overview) ──────────────────────────
function MLForecastReadLine({ ticker, mode }) {
  const { model, state } = useMLForecastModel(ticker, mode);
  if (state !== "real") {
    const pct = Math.round((model.pUp || 0) * 100);
    return (
      <span className="mono">
        ML Forecast (illustrative): P(up) <b className={pct >= 55 ? "up" : pct <= 45 ? "dn" : "warn"}>{pct}%</b>,
        {model.agree != null && ` ${model.agree}/${(model.n_theories || (model.votes || []).length)} theories aligned — `}
        connect to live data for asset-specific model.
      </span>
    );
  }
  const vt   = (model.verdict || "HOLD") === "BUY" ? "up" : (model.verdict || "HOLD") === "AVOID" ? "dn" : "warn";
  const pct  = Math.round((model.pUp || 0) * 100);
  const band = model.band || {};
  return (
    <span className="mono">
      ML meta-model: P(up · {model.hz_label || ""}) <b className={vt}>{pct}%</b>
      {model.agree != null && `, ${model.agree}/${model.n_theories || (model.votes || []).length} theories aligned`} —
      band <span className="dn">{band.lo != null ? (band.lo >= 0 ? "+" : "") + band.lo.toFixed(1) + "%" : "—"}</span>
      {" / "}<b className={vt}>{band.mid != null ? (band.mid >= 0 ? "+" : "") + band.mid.toFixed(1) + "%" : "—"}</b>
      {" / "}<span className="up">{band.hi != null ? (band.hi >= 0 ? "+" : "") + band.hi.toFixed(1) + "%" : "—"}</span>,{" "}
      <b className={vt}>{model.verdict || "HOLD"}</b> bias.
    </span>
  );
}

Object.assign(window, { MLForecastView, MLForecastReadLine });

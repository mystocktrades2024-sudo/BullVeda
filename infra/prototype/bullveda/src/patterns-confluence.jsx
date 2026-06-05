// patterns-confluence.jsx — the Confluence Engine cockpit (first sub-tab).
//
// REAL DATA: calls engines/confluence.py server-side; that engine runs every
// sibling theory (Wyckoff, Elliott, Fibonacci, Volume Profile, Ichimoku, TD,
// Classical, Candlesticks, Monte Carlo) on the SAME fetched bars and returns:
//   methods[]    — one row per theory: {method, bias +1/0/-1, conf, note, active}
//   composite    — {score, threshold, bull_count, bear_count, bias, pct_agree}
//   level_map[]  — confluence price map: {price, sources[], strength, kind}
//   p_success    — float 0-1
//   stat         — header strip fields
//   bars[]       — windowed bars for the CandleChart
//   read, confidence, cur_close
//
// When the server is absent or returns insufficient data the EXISTING fixture
// below is used verbatim and the source badge says "◑ illustrative".
//
// Mechanism: no single method is reliable alone; multi-theory directional
// agreement suppresses method-specific noise — confluence IS the edge signal.

const { useMemo: useMemoCe } = React;

// ──────────────────────────────────────────────────────────────────────────────
// FIXTURE MODEL (fallback only — labelled clearly in the UI)
// ──────────────────────────────────────────────────────────────────────────────

const _FIX_METHODS = [
  { method: "Wyckoff",       engine: "wyckoff",    bias: +1, conf: 0.88, note: "Spring + SOS · accumulating",     active: true,  weight: 0.18 },
  { method: "Elliott Wave",  engine: "elliott",    bias: +1, conf: 0.82, note: "impulse W3 · target 214.6",       active: true,  weight: 0.16 },
  { method: "Fibonacci",     engine: "fibonacci",  bias: +1, conf: 0.81, note: "223–225 cluster · 3-hit",         active: true,  weight: 0.14 },
  { method: "Volume Profile",engine: "volprofile", bias: +1, conf: 0.66, note: "above VAH · value migrating up",  active: true,  weight: 0.12 },
  { method: "Ichimoku",      engine: "ichimoku",   bias: +1, conf: 0.74, note: "TK cross · above cloud",          active: true,  weight: 0.14 },
  { method: "TD Sequential", engine: "td",         bias:  0, conf: 0.57, note: "Sell 8/9 · exhaustion near",      active: true,  weight: 0.08 },
  { method: "Classical",     engine: "classical",  bias: +1, conf: 0.64, note: "VCP breakout · pivot 205",        active: true,  weight: 0.10 },
  { method: "Candlesticks",  engine: "candles",    bias:  0, conf: 0.52, note: "no confirmed reversal signal",    active: true,  weight: 0.08 },
  { method: "Monte Carlo",   engine: "montecarlo", bias: +1, conf: 0.61, note: "P(T1 first) 64% vs P(stop) 36%", active: true,  weight: 0.10 },
];

const _FIX_COMPOSITE = {
  score: 87, threshold: 60, contributing: 9,
  bull_count: 7, bear_count: 0, neutral_count: 2,
  bias: +1, pct_agree: 0.78,
};

const _FIX_LEVEL_MAP = [
  { price: 224,   sources: ["Fibonacci 1.272", "Elliott W5", "Wyckoff P&F"], strength: 0.83, kind: "target"  },
  { price: 236,   sources: ["Fibonacci 1.618", "Classical T2"],               strength: 0.52, kind: "target"  },
  { price: 213.4, sources: ["current"],                                        strength: 0,    kind: "current" },
  { price: 209,   sources: ["Volume Profile VAH", "TD TDST"],                  strength: 0.40, kind: "support" },
  { price: 205,   sources: ["Classical pivot", "VP POC", "Ichimoku Kijun"],    strength: 0.62, kind: "support" },
  { price: 191,   sources: ["Fibonacci 0.618", "Wyckoff ST"],                  strength: 0.86, kind: "support" },
];

const _FIX_P_SUCCESS = 0.84;
const _FIX_CUR_CLOSE = 213.4;
const _FIX_STAT = {
  composite: 87, threshold: 60,
  theories_aligned: "7/9", consensus: 78,
  p_success: _FIX_P_SUCCESS, bias: +1,
  contributing: 9, bull_count: 7, bear_count: 0,
};
const _FIX_READ = "Context → structure → projection all align. TD flags exhaustion near $214–216 — enter on the trigger, trail stops.";
const _FIX_INV  = { price: 206.0, note: "Close below $206.00 LPS / VAL (breakout fails) — stand aside." };

// Fixture model assembled in the shape the view consumes
var FIXTURE_MODEL = {
  isReal: false, source: "illustrative",
  methods:   _FIX_METHODS,
  composite: _FIX_COMPOSITE,
  level_map: _FIX_LEVEL_MAP,
  p_success: _FIX_P_SUCCESS,
  stat:      _FIX_STAT,
  read:      _FIX_READ,
  invalidation: _FIX_INV,
  cur_close: _FIX_CUR_CLOSE,
  confidence: _FIX_P_SUCCESS,
  bars: [],
};

// CE_COMPOSITE / CE_THRESHOLD / CE_CONSENSUS — preserved for backward-compat
// (lens-patterns-v2.jsx reads these globals)
const CE_THRESHOLD = FIXTURE_MODEL.composite.threshold;
const CE_COMPOSITE = FIXTURE_MODEL.composite.score;
const CE_CONSENSUS = Math.round(FIXTURE_MODEL.composite.pct_agree * 100);

// ──────────────────────────────────────────────────────────────────────────────
// DATA HOOK
// ──────────────────────────────────────────────────────────────────────────────

function useEnsembleModel(ticker, mode) {
  const { real, state, sym } = usePatternModel("ensemble", ticker, mode);
  const tf = (real && real.meta && real.meta.tf) || null;

  const usable = (
    state === "loaded" &&
    real && real.ok &&
    real.state === "real" &&
    real.methods && real.methods.length &&
    real.composite && real.composite.contributing > 0
  );

  if (usable) {
    const m = real;
    return {
      model: {
        isReal: true, source: "real", tf,
        methods:      m.methods      || [],
        composite:    m.composite    || {},
        level_map:    m.level_map    || [],
        p_success:    m.p_success    != null ? m.p_success : 0,
        stat:         m.stat         || {},
        read:         m.read         || "",
        invalidation: m.invalidation || {},
        cur_close:    m.cur_close    || 0,
        confidence:   m.confidence   || m.p_success || 0,
        bars:         m.bars         || [],
      },
      state: "real", sym, tf, usable: true,
    };
  }

  if (state === "loaded" && real && real.ok) {
    return {
      model: { ...FIXTURE_MODEL, tf },
      state: "none", sym, tf, usable: false,
      message: (real && real.message) || "Insufficient data for ensemble consensus.",
    };
  }

  return {
    model: { ...FIXTURE_MODEL },
    state: state === "loading" ? "loading" : "mock", sym, tf, usable: false,
  };
}

// ──────────────────────────────────────────────────────────────────────────────
// HELPERS
// ──────────────────────────────────────────────────────────────────────────────

function _biasTone(bias) {
  return bias === +1 ? "gn" : bias === -1 ? "rd" : "amb";
}

function _biasLabel(bias) {
  return bias === +1 ? "BULL" : bias === -1 ? "BEAR" : "NEUTRAL";
}

function _methodTone(m) {
  if (!m.active) return "ink-3";
  if (m.bias === +1) return "gn";
  if (m.bias === -1) return "rd";
  return "amb";
}

// ──────────────────────────────────────────────────────────────────────────────
// COCKPIT (verdict hero strip)
// ──────────────────────────────────────────────────────────────────────────────

function ConfCockpit({ model }) {
  const comp    = model.composite || {};
  const stat    = model.stat      || {};
  const score   = comp.score   != null ? Math.round(comp.score)   : 0;
  const thresh  = comp.threshold != null ? comp.threshold           : 60;
  const isGo    = score >= thresh;
  const bias    = comp.bias   != null ? comp.bias                   : 0;
  const bTone   = _biasTone(bias);
  const bLabel  = _biasLabel(bias);
  const bull    = comp.bull_count    || 0;
  const bear    = comp.bear_count    || 0;
  const contrib = comp.contributing  || 0;
  const agree   = Math.round((comp.pct_agree || 0) * 100);
  const psucc   = model.p_success != null ? (model.p_success).toFixed(2) : "—";
  const cur     = model.cur_close   ? `$${(+model.cur_close).toFixed(2)}` : "—";

  return (
    <div className="pv-cockpit">
      <div className="pv-ck-score">
        <div className="label-cap">Composite</div>
        <div className="pv-ck-num mono">{score}<span>/100</span></div>
        <div className={`pv-gate ${isGo ? "is-go" : "is-no"}`}>
          {isGo ? `SIGNAL ✓ ≥${thresh}` : `BELOW ${thresh}`}
        </div>
      </div>
      <div className="pv-ck-stats">
        <div className="pv-ck-stat">
          <div className="label-cap">Direction</div>
          <div className={`pv-ck-v mono ${bTone}`}>{bLabel}</div>
        </div>
        <div className="pv-ck-stat">
          <div className="label-cap">Bull / Bear</div>
          <div className="pv-ck-v mono">
            <span className="up">{bull}↑</span>
            <span className="dim2"> / </span>
            <span className="dn">{bear}↓</span>
            <span className="dim2"> of {contrib}</span>
          </div>
        </div>
        <div className="pv-ck-stat">
          <div className="label-cap">Agreement</div>
          <div className={`pv-ck-v mono ${agree >= 70 ? "up" : agree >= 50 ? "warn" : "dn"}`}>{agree}%</div>
        </div>
        <div className="pv-ck-stat">
          <div className="label-cap">P(success)</div>
          <div className={`pv-ck-v mono ${(model.p_success || 0) >= 0.65 ? "up" : "warn"}`}>{psucc}</div>
        </div>
        <div className="pv-ck-stat">
          <div className="label-cap">Price</div>
          <div className="pv-ck-v mono copper">{cur}</div>
        </div>
        <div className="pv-ck-verdict mono">{model.read || "—"}</div>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// THEORY BOARD — one card per engine, clickable to jump to its sub-tab
// ──────────────────────────────────────────────────────────────────────────────

function TheoryBoard({ methods, onTab }) {
  const list = (methods && methods.length) ? methods : _FIX_METHODS;
  return (
    <div className="pv-board">
      {list.map((m, k) => {
        const tone = _methodTone(m);
        const variant = !m.active ? "off" : m.bias === +1 ? "ok" : m.bias === -1 ? "warn" : "neu";
        return (
          <button key={k} className={`pv-bcard pv-bcard--${variant}`}
                  onClick={() => onTab && onTab(m.engine || m.method.toLowerCase())}
                  title={`${m.method} — ${m.note}`}>
            <div className="pv-bcard-top">
              <span className="pv-bcard-name">{m.method}</span>
              <span className="pv-bcard-arrow mono">→</span>
            </div>
            <div className="pv-bcard-verdict mono" style={{ color: `var(--${tone})` }}>
              {!m.active ? "—" : _biasLabel(m.bias)}
            </div>
            <div className="pv-bcard-bar">
              <span style={{ width: `${(m.conf || 0) * 100}%`, background: `var(--${tone})` }} />
            </div>
            <div className="pv-bcard-line">{m.note || "—"}</div>
          </button>
        );
      })}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// CONFLUENCE PRICE MAP (true-to-scale)
// ──────────────────────────────────────────────────────────────────────────────

const CE_KIND_TONE = { target: "gn", current: "copper", res: "amb", pivot: "cy", support: "cy" };

function ConfluenceMap({ levelMap, curClose }) {
  const list = (levelMap && levelMap.length) ? levelMap : _FIX_LEVEL_MAP;
  if (!list.length) return null;

  const prices = list.map(l => l.price);
  const rawLo = Math.min(...prices);
  const rawHi = Math.max(...prices);
  const pad   = (rawHi - rawLo) * 0.12 || 5;
  const lo = rawLo - pad;
  const hi = rawHi + pad;
  const rng = hi - lo || 1;

  const yPct = p => (1 - (p - lo) / rng) * 100;

  // grid lines
  const step = Math.max(1, Math.round((rawHi - rawLo) / 5));
  const gridBase = Math.round(rawLo / step) * step;
  const gridLines = [];
  for (let g = gridBase; g <= rawHi + step; g += step) {
    if (g > lo && g < hi) gridLines.push(g);
  }

  return (
    <div className="pv-map">
      <div className="pv-map-track">
        {gridLines.slice(0, 6).map(t => (
          <div key={t} className="pv-map-grid" style={{ top: `${yPct(t)}%` }}>
            <span className="mono">{(+t).toFixed(0)}</span>
          </div>
        ))}
        {list.map((lv, k) => {
          const tone = CE_KIND_TONE[lv.kind] || "ink-2";
          const chips = lv.sources || lv.chips || [];
          const strength = lv.strength || 0;
          const label = lv.label || (lv.kind === "current" ? "Current price" : `${lv.kind} cluster`);
          return (
            <div key={k} className={`pv-map-row pv-map-row--${lv.kind}`}
                 style={{ top: `${yPct(lv.price)}%` }}>
              <span className="pv-map-px mono" style={{ color: `var(--${tone})` }}>
                ${(+lv.price).toFixed(2)}
              </span>
              <span className="pv-map-line" style={{ background: `var(--${tone})` }} />
              <span className="pv-map-label">{label}</span>
              <span className="pv-map-chips">
                {chips.slice(0, 4).map((c, j) => (
                  <span key={j} className="pv-chip mono">{c}</span>
                ))}
                {strength > 0 && (
                  <span className="pv-map-strength mono" style={{ color: `var(--${tone})` }}>
                    {Math.round(strength * 100)}%
                  </span>
                )}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// PATTERN MATRIX — one row per theory, showing bias/conf/note
// ──────────────────────────────────────────────────────────────────────────────

function PatternMatrix({ methods }) {
  const list = (methods && methods.length) ? methods : _FIX_METHODS;
  return (
    <MiniTable
      cols={[
        { h: "Theory",    k: "name"  },
        { h: "Bias",      k: "bias",  align: "center" },
        { h: "Conf",      k: "conf",  align: "right"  },
        { h: "Note",      k: "note"  },
      ]}
      rows={list.map(m => {
        const tone = _methodTone(m);
        return {
          name: <b style={{ color: `var(--${tone})` }}>{m.method}</b>,
          bias: (
            <span className={`pv-badge mono pv-badge--${tone}`}
                  style={{ color: `var(--${tone})`, fontWeight: 700, fontSize: 11 }}>
              {m.active ? (m.bias === +1 ? "▲ BULL" : m.bias === -1 ? "▼ BEAR" : "◆ NEUT") : "—"}
            </span>
          ),
          conf: m.conf > 0
            ? <ConfBar value={m.conf} tone={tone} width={52} />
            : <span className="dim mono">—</span>,
          note: <span className="dim2" style={{ fontSize: 11 }}>{m.note || "—"}</span>,
        };
      })}
    />
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// COMPOSITE PANEL — score breakdown + gate verdict
// ──────────────────────────────────────────────────────────────────────────────

function CompositePanel({ composite, methods }) {
  const comp  = composite || _FIX_COMPOSITE;
  const score = comp.score != null ? Math.round(comp.score) : 87;
  const thresh = comp.threshold || 60;
  const isGo  = score >= thresh;
  const bias  = comp.bias || 0;
  const bTone = _biasTone(bias);

  // Build "pillars" from the top-3 highest-confidence active methods
  const active = (methods || _FIX_METHODS).filter(m => m.active && m.bias === bias);
  const topPillars = active.sort((a, b) => b.conf - a.conf).slice(0, 3);

  const PILLAR_TONES = ["copper", "violet", "amb"];

  return (
    <div className="pv-comp">
      <div className="pv-comp-pillars">
        {topPillars.map((p, k) => (
          <div key={k} className="pv-pillar">
            <div className="pv-pillar-top">
              <span className="pv-pillar-name">{p.method}</span>
              <span className="pv-pillar-score mono"
                    style={{ color: `var(--${PILLAR_TONES[k]})` }}>
                {Math.round((p.conf || 0) * 100)}
              </span>
            </div>
            <div className="pv-pillar-bar">
              <span style={{ width: `${(p.conf || 0) * 100}%`,
                             background: `var(--${PILLAR_TONES[k]})` }} />
            </div>
            <div className="pv-pillar-role label-cap">
              {p.note ? p.note.slice(0, 40) : "—"} · wt ×{(p.weight || 0).toFixed(2)}
            </div>
          </div>
        ))}
        {topPillars.length === 0 && (
          <div className="pv-empty-sub mono dim2">No high-confidence active theories.</div>
        )}
      </div>
      <div className="pv-comp-out">
        <div className="label-cap">Composite</div>
        <div className="pv-comp-num mono" style={{ color: `var(--${bTone})` }}>
          {score}<span className="pv-comp-den">/100</span>
        </div>
        <div className="pv-comp-formula mono dim2">
          {comp.bull_count}↑ bull · {comp.bear_count}↓ bear · {comp.neutral_count}◆ neut
        </div>
        <div className={`pv-gate ${isGo ? "is-go" : "is-no"}`}>
          {isGo ? `SIGNAL ✓ ≥${thresh}` : `BELOW ${thresh}`}
        </div>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// CONSENSUS TABLE (shows per-theory summary in table form)
// ──────────────────────────────────────────────────────────────────────────────

function ConsensusTable({ composite, methods }) {
  const comp  = composite || _FIX_COMPOSITE;
  const agree = Math.round((comp.pct_agree || 0) * 100);
  const tone  = _biasTone(comp.bias || 0);
  const label = _biasLabel(comp.bias || 0);

  return (
    <div>
      <PatternMatrix methods={methods} />
      <div className="pv-consensus">
        <span className="label-cap">Ensemble direction</span>
        <span className={`pv-consensus-num mono ${tone}`}>{label}</span>
        <Pill tone={tone} small>
          {agree}% AGREE · {comp.bull_count || 0}b / {comp.bear_count || 0}s
        </Pill>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// P(SUCCESS) PANEL — simple probability display
// ──────────────────────────────────────────────────────────────────────────────

function ProbPanel({ pSuccess, composite, methods }) {
  const p     = pSuccess != null ? pSuccess : _FIX_P_SUCCESS;
  const comp  = composite || _FIX_COMPOSITE;
  const agree = Math.round((comp.pct_agree || 0) * 100);
  const score = Math.round(comp.score || 87);

  // build feature bars from the top active methods (by conf × weight)
  const active = (methods || _FIX_METHODS).filter(m => m.active);
  const feats = active
    .sort((a, b) => (b.conf * b.weight) - (a.conf * a.weight))
    .slice(0, 5)
    .map(m => ({
      f: m.method,
      v: +(m.conf * m.weight).toFixed(3),
      tone: _methodTone(m),
    }));
  const maxV = feats.length ? Math.max(...feats.map(f => f.v)) : 1;

  return (
    <div className="pv-prob">
      <div className="pv-prob-num">
        <div className="label-cap">P(success)</div>
        <div className={`pv-prob-v mono ${p >= 0.65 ? "up" : p >= 0.45 ? "warn" : "dn"}`}>
          {p.toFixed(2)}
        </div>
        <div className="pv-prob-sub mono dim2">
          composite {score}/100 · {agree}% agree · ensemble of {active.length} theories
        </div>
      </div>
      <div className="pv-feats">
        {feats.map((f, k) => (
          <div key={k} className="pv-feat">
            <span className="pv-feat-label mono">{f.f}</span>
            <span className="pv-feat-bar">
              <span style={{ width: `${(f.v / maxV) * 100}%`,
                             background: `var(--${f.tone})` }} />
            </span>
            <span className="pv-feat-v mono dim2">{f.v.toFixed(3)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// ACTION LADDER — derived from composite bias and invalidation
// ──────────────────────────────────────────────────────────────────────────────

function ActionLadder({ composite, invalidation, curClose }) {
  const comp = composite || _FIX_COMPOSITE;
  const inv  = invalidation || _FIX_INV;
  const cur  = curClose || _FIX_CUR_CLOSE;
  const bias = comp.bias || 0;
  const score = Math.round(comp.score || 0);
  const thresh = comp.threshold || 60;
  const isGo = score >= thresh && bias !== 0;

  const invPx = inv.price ? `$${(+inv.price).toFixed(2)}` : "—";

  if (bias === +1) {
    return (
      <div className="action-ladder">
        <div className={`al-row ${isGo ? "al-gn" : "al-amb"}`}>
          <span className="mono">
            Score {score}/{thresh} threshold · {Math.round((comp.pct_agree || 0) * 100)}% ensemble bull
          </span>
          <Pill tone={isGo ? "gn" : "amb"} small>
            {isGo ? "GO · confirmed" : "WATCH · below threshold"}
          </Pill>
        </div>
        <div className="al-row al-amb">
          <span className="mono">Score crosses {thresh}+ with ≥60% agreement</span>
          <Pill tone="amb" small>SIZE IN on confirmation</Pill>
        </div>
        <div className="al-row al-rd">
          <span className="mono">Close below {invPx} — confluence breaks</span>
          <Pill tone="rd" small>EXIT · skip</Pill>
        </div>
      </div>
    );
  }
  if (bias === -1) {
    return (
      <div className="action-ladder">
        <div className={`al-row ${isGo ? "al-rd" : "al-amb"}`}>
          <span className="mono">
            Score {score}/{thresh} threshold · {Math.round((comp.pct_agree || 0) * 100)}% ensemble bear
          </span>
          <Pill tone={isGo ? "rd" : "amb"} small>
            {isGo ? "SHORT · confirmed" : "WATCH · below threshold"}
          </Pill>
        </div>
        <div className="al-row al-amb">
          <span className="mono">Score crosses {thresh}+ with ≥60% bear agreement</span>
          <Pill tone="amb" small>SHORT on break</Pill>
        </div>
        <div className="al-row al-gn">
          <span className="mono">Close above {invPx} — bear confluence fails</span>
          <Pill tone="gn" small>COVER · exit short</Pill>
        </div>
      </div>
    );
  }
  // neutral / mixed
  return (
    <div className="action-ladder">
      <div className="al-row al-amb">
        <span className="mono">
          Mixed signals — {comp.bull_count || 0}↑ bull, {comp.bear_count || 0}↓ bear, score {score}
        </span>
        <Pill tone="amb" small>WAIT · no consensus</Pill>
      </div>
      <div className="al-row al-gn">
        <span className="mono">Bias resolves ≥{thresh} with ≥60% agreement</span>
        <Pill tone="gn" small>THEN size in</Pill>
      </div>
      <div className="al-row al-rd">
        <span className="mono">Below {invPx} — stand aside</span>
        <Pill tone="rd" small>AVOID</Pill>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// STAT STRIP
// ──────────────────────────────────────────────────────────────────────────────

function ConfStat({ stat, composite, p_success, tf }) {
  const s    = stat || _FIX_STAT;
  const comp = composite || _FIX_COMPOSITE;
  const p    = p_success != null ? p_success : _FIX_P_SUCCESS;
  const bTone = _biasTone(comp.bias || 0);

  return (
    <div className="pv-stat">
      <div className="pv-stat-cell">
        <div className="label-cap">Composite</div>
        <div className="pv-stat-v mono" style={{ color: `var(--${bTone})` }}>
          {Math.round(comp.score || 0)} / {comp.threshold || 60}
        </div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">Direction</div>
        <div className={`pv-stat-v mono ${bTone}`}>{_biasLabel(comp.bias || 0)}</div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">Aligned</div>
        <div className="pv-stat-v mono copper">{s.theories_aligned || "—"}</div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">Agreement</div>
        <div className="pv-stat-v mono">{Math.round((comp.pct_agree || 0) * 100)}%</div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">P(success)</div>
        <div className="pv-stat-v">
          <ConfBar value={p} tone={bTone} width={72} />
        </div>
      </div>
      {tf && (
        <div className="pv-stat-cell">
          <div className="label-cap">Timeframe</div>
          <div className="pv-stat-v mono dim2">{tf}</div>
        </div>
      )}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// CANDLESTICK CHART (bars + confluence hlines from level_map)
// ──────────────────────────────────────────────────────────────────────────────

function ConfChart({ model, height }) {
  const bars = (model && model.bars && model.bars.length) ? model.bars : null;
  if (!bars) return null;

  const levelMap = model.level_map || [];
  const hlines = levelMap
    .filter(lm => lm.strength >= 0.3)
    .slice(0, 8)
    .map(lm => {
      const tone = CE_KIND_TONE[lm.kind] || "ink-2";
      return {
        price: lm.price,
        label: `${(lm.sources || []).slice(0, 2).join(", ")} $${lm.price.toFixed(2)}`,
        tone,
        dash: lm.kind === "target" ? "5 4" : "4 4",
      };
    });

  const comp = model.composite || {};
  const accent = comp.bias === +1 ? "gn" : comp.bias === -1 ? "rd" : "copper";

  return <CandleChart bars={bars} height={height || 300} hlines={hlines} accent={accent} />;
}

// ──────────────────────────────────────────────────────────────────────────────
// HONEST EMPTY STATE
// ──────────────────────────────────────────────────────────────────────────────

function ConfNone({ sym, message }) {
  return (
    <div className="pv-view">
      <div className="pv-empty">
        <div className="pv-empty-i mono">— no ensemble consensus</div>
        <div className="pv-empty-msg">
          {message || `Insufficient bar history or fewer than 3 theories returned valid reads for ${sym || "this name"}. Ensemble consensus requires at least 3 active theory votes.`}
        </div>
        <div className="pv-empty-sub mono dim2">
          Connect to :7432 with a valid ticker and at least 30 bars of OHLCV history.
        </div>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// VIEW ASSEMBLER — three layout directions (A / B / C)
// ──────────────────────────────────────────────────────────────────────────────

function ConfluenceView({ ticker, dir, mode, onTab }) {
  const { model, state, message, sym, tf, usable } = useEnsembleModel(ticker, mode);

  if (state === "none") {
    return (
      <div className="pv-view">
        <div className="pv-srcbar">
          <PatternSrcBadge state={state} usable={false} sym={sym} tf={tf} />
        </div>
        <ConfNone sym={sym} message={message} />
      </div>
    );
  }

  const SrcBar = (
    <div className="pv-srcbar">
      <PatternSrcBadge state={state} usable={usable} sym={sym} tf={tf} />
    </div>
  );

  // ── Dir B: split layout — cockpit + map left, matrix + prob right
  if (dir === "B") {
    return (
      <div className="pv-view">
        {SrcBar}
        <ConfStat stat={model.stat} composite={model.composite}
                  p_success={model.p_success} tf={tf} />
        <ConfCockpit model={model} />
        <div className="pv-split">
          <div className="pv-split-main">
            <SectionHeader n={1} title="Confluence price map"
              sub="where every theory's levels stack — true to scale" style="minimal" />
            <div className="pv-pad"><ConfluenceMap levelMap={model.level_map} curClose={model.cur_close} /></div>
            {model.bars && model.bars.length > 0 && (
              <>
                <SectionHeader n={2} title="Price chart" sub="real bars · confluence hlines" style="minimal" />
                <div className="pv-pad"><ConfChart model={model} height={280} /></div>
              </>
            )}
          </div>
          <div className="pv-split-side">
            <SectionHeader n={3} title="Theory matrix" style="minimal" />
            <div className="pv-pad"><ConsensusTable composite={model.composite} methods={model.methods} /></div>
            <SectionHeader n={4} title="Composite score" style="minimal" />
            <div className="pv-pad"><CompositePanel composite={model.composite} methods={model.methods} /></div>
          </div>
        </div>
        <SectionHeader n={5} title="P(success)" sub="ensemble probability of reaching target before stop" style="minimal" />
        <div className="pv-pad"><ProbPanel pSuccess={model.p_success} composite={model.composite} methods={model.methods} /></div>
        <SectionHeader n={6} title="Action ladder" sub="bias-derived triggers + invalidation" style="minimal" />
        <div className="pv-pad"><ActionLadder composite={model.composite} invalidation={model.invalidation} curClose={model.cur_close} /></div>
      </div>
    );
  }

  // ── Dir C: dossier — compact, data-dense
  if (dir === "C") {
    return (
      <div className="pv-view pv-view--dossier">
        {SrcBar}
        <ConfStat stat={model.stat} composite={model.composite}
                  p_success={model.p_success} tf={tf} />
        <ConfCockpit model={model} />
        {model.bars && model.bars.length > 0 && (
          <div className="pv-pad"><ConfChart model={model} height={220} /></div>
        )}
        <div className="pv-2col">
          <div>
            <div className="pv-block-h label-cap">Theory matrix</div>
            <PatternMatrix methods={model.methods} />
          </div>
          <div>
            <div className="pv-block-h label-cap">Price map</div>
            <ConfluenceMap levelMap={model.level_map} curClose={model.cur_close} />
            <div className="pv-block-h label-cap" style={{ marginTop: 14 }}>P(success)</div>
            <ProbPanel pSuccess={model.p_success} composite={model.composite} methods={model.methods} />
          </div>
        </div>
        <div className="pv-pad" style={{ marginTop: 8 }}>
          <ActionLadder composite={model.composite} invalidation={model.invalidation} curClose={model.cur_close} />
        </div>
      </div>
    );
  }

  // ── Dir A: chart-led (default)
  return (
    <div className="pv-view">
      {SrcBar}
      <ConfStat stat={model.stat} composite={model.composite}
                p_success={model.p_success} tf={tf} />

      {/* verdict hero */}
      <ConfCockpit model={model} />

      <SectionHeader n={1} title="Theory board"
        sub="every discipline's current read — click to open sub-tab" style="minimal" />
      <div className="pv-pad"><TheoryBoard methods={model.methods} onTab={onTab} /></div>

      <SectionHeader n={2} title="Confluence price map"
        sub="where every theory's levels stack — true to scale" style="minimal" />
      <div className="pv-pad"><ConfluenceMap levelMap={model.level_map} curClose={model.cur_close} /></div>

      <SectionHeader n={3} title="Weighted composite score"
        sub="theory matrix · per-method bias · agreement" style="minimal" />
      <div className="pv-pad"><CompositePanel composite={model.composite} methods={model.methods} /></div>

      <div className="pv-2col">
        <div>
          <div className="pv-block-h label-cap">Theory matrix</div>
          <ConsensusTable composite={model.composite} methods={model.methods} />
        </div>
        <div>
          <div className="pv-block-h label-cap">P(success)</div>
          <ProbPanel pSuccess={model.p_success} composite={model.composite} methods={model.methods} />
        </div>
      </div>

      <SectionHeader n={4} title="Action ladder"
        sub="bias-derived triggers · sized to the base" style="minimal" />
      <div className="pv-pad">
        <ActionLadder composite={model.composite}
                      invalidation={model.invalidation}
                      curClose={model.cur_close} />
      </div>

      {model.bars && model.bars.length > 0 && (
        <>
          <SectionHeader n={5} title="Price chart" sub="real bars · confluence hlines overlay" style="minimal" />
          <div className="pv-pad"><ConfChart model={model} height={300} /></div>
        </>
      )}
    </div>
  );
}

Object.assign(window, { ConfluenceView, CE_COMPOSITE, CE_CONSENSUS, CE_THRESHOLD });

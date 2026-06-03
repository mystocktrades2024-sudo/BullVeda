// patterns-confluence.jsx — the Confluence Engine cockpit (first tab).
// Verdict hero · clickable theory board · true-to-scale confluence price map ·
// weighted composite (Wyckoff·Elliott·Fibonacci) · MTF consensus · ML probability.

const { useMemo: useMemoCe } = React;

// ── core weighted pillars (WEFCE: context · structure · projection) ──
const CE_PILLARS = [
  { name: "Wyckoff", role: "context", score: 88, w: 0.40, tone: "copper" },
  { name: "Elliott", role: "structure", score: 82, w: 0.35, tone: "violet" },
  { name: "Fibonacci", role: "projection", score: 91, w: 0.25, tone: "amb" },
];
const CE_COMPOSITE = Math.round(CE_PILLARS.reduce((s, p) => s + p.score * p.w, 0));
const CE_THRESHOLD = 70;

// ── every theory's current read (board + price-map source) ──
const CE_THEORIES = [
  { id: "wyckoff", name: "Wyckoff", verdict: "PHASE D", conf: 0.88, tone: "copper", line: "Spring + SOS · accumulating" },
  { id: "elliott", name: "Elliott Wave", verdict: "WAVE 3", conf: 0.82, tone: "violet", line: "impulse · target 214.6" },
  { id: "fibonacci", name: "Fibonacci", verdict: "CLUSTER", conf: 0.81, tone: "amb", line: "223–225 target · 3-hit" },
  { id: "volprofile", name: "Volume Profile", verdict: "ABOVE VAH", conf: 0.66, tone: "cy", line: "value migrating up · POC 204" },
  { id: "ichimoku", name: "Ichimoku", verdict: "ABOVE CLOUD", conf: 0.74, tone: "cy", line: "TK cross · green Kumo" },
  { id: "td", name: "TD Sequential", verdict: "SELL 8/9", conf: 0.57, tone: "amb", line: "exhaustion near · trail stops" },
  { id: "classical", name: "Classical", verdict: "VCP GO", conf: 0.64, tone: "cy", line: "5 contractions · pivot 205" },
  { id: "harmonic", name: "Harmonic", verdict: "GARTLEY", conf: 0.69, tone: "violet", line: "PRZ held · A retest" },
];
const CE_ALIGNED = CE_THEORIES.filter(t => t.tone !== "amb").length;

function TheoryBoard({ onTab }) {
  return (
    <div className="pv-board">
      {CE_THEORIES.map(t => (
        <button key={t.id} className={`pv-bcard pv-bcard--${t.tone === "amb" ? "warn" : "ok"}`} onClick={() => onTab && onTab(t.id)}>
          <div className="pv-bcard-top">
            <span className="pv-bcard-name">{t.name}</span>
            <span className="pv-bcard-arrow mono">→</span>
          </div>
          <div className="pv-bcard-verdict mono" style={{ color: `var(--${t.tone})` }}>{t.verdict}</div>
          <div className="pv-bcard-bar"><span style={{ width: `${t.conf * 100}%`, background: `var(--${t.tone})` }} /></div>
          <div className="pv-bcard-line">{t.line}</div>
        </button>
      ))}
    </div>
  );
}

// ── true-to-scale confluence price map ──────────────────────────
const CE_LO = 185, CE_HI = 240;
const CE_LEVELS = [
  { price: 236, kind: "target", label: "Extension cluster", chips: ["Fib 1.618", "Classical T2"], strength: 0.52 },
  { price: 224, kind: "target", label: "Primary target cluster", chips: ["Fib 1.272", "Elliott W5", "Wyckoff P&F", "VP ext"], strength: 0.83 },
  { price: 213.4, kind: "current", label: "Current price", chips: [], strength: 0 },
  { price: 209, kind: "res", label: "VAH / TDST resistance", chips: ["VP VAH", "TD res"], strength: 0.4 },
  { price: 205, kind: "pivot", label: "Pivot / POC", chips: ["Classical pivot", "VP POC", "Ichimoku Senkou A"], strength: 0.62 },
  { price: 191, kind: "support", label: "Support cluster", chips: ["Fib .618", "Wyckoff ST", "Gartley B"], strength: 0.86 },
];
const CE_KIND_TONE = { target: "gn", current: "copper", res: "amb", pivot: "cy", support: "gn" };
function ConfluenceMap() {
  const yPct = p => (1 - (p - CE_LO) / (CE_HI - CE_LO)) * 100;
  return (
    <div className="pv-map">
      <div className="pv-map-track">
        {[240, 225, 210, 195].map(t => (
          <div key={t} className="pv-map-grid" style={{ top: `${yPct(t)}%` }}><span className="mono">{t}</span></div>
        ))}
        {CE_LEVELS.map((lv, k) => {
          const tone = CE_KIND_TONE[lv.kind];
          return (
            <div key={k} className={`pv-map-row pv-map-row--${lv.kind}`} style={{ top: `${yPct(lv.price)}%` }}>
              <span className="pv-map-px mono" style={{ color: `var(--${tone})` }}>${lv.price}</span>
              <span className="pv-map-line" style={{ background: `var(--${tone})` }} />
              <span className="pv-map-label">{lv.label}</span>
              <span className="pv-map-chips">
                {lv.chips.map((c, j) => <span key={j} className="pv-chip mono">{c}</span>)}
                {lv.strength > 0 && <span className="pv-map-strength mono" style={{ color: `var(--${tone})` }}>{Math.round(lv.strength * 100)}%</span>}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function CompositePanel() {
  return (
    <div className="pv-comp">
      <div className="pv-comp-pillars">
        {CE_PILLARS.map((p, k) => (
          <div key={k} className="pv-pillar">
            <div className="pv-pillar-top">
              <span className="pv-pillar-name">{p.name}</span>
              <span className="pv-pillar-score mono" style={{ color: `var(--${p.tone})` }}>{p.score}</span>
            </div>
            <div className="pv-pillar-bar"><span style={{ width: `${p.score}%`, background: `var(--${p.tone})` }} /></div>
            <div className="pv-pillar-role label-cap">{p.role} · weight ×{p.w.toFixed(2)}</div>
          </div>
        ))}
      </div>
      <div className="pv-comp-out">
        <div className="label-cap">Composite</div>
        <div className="pv-comp-num mono">{CE_COMPOSITE}<span className="pv-comp-den">/100</span></div>
        <div className="pv-comp-formula mono dim2">.40·88 + .35·82 + .25·91</div>
        <div className={`pv-gate ${CE_COMPOSITE >= CE_THRESHOLD ? "is-go" : "is-no"}`}>
          {CE_COMPOSITE >= CE_THRESHOLD ? `SIGNAL ✓ ≥ ${CE_THRESHOLD}` : `BELOW ${CE_THRESHOLD}`}
        </div>
      </div>
    </div>
  );
}

const CE_MTF = [
  { tf: "Daily", w: 0.40, wy: "Phase D", ew: "W3", fb: ".618 held", score: 90, tone: "gn" },
  { tf: "4-Hour", w: 0.30, wy: "Markup", ew: "W3", fb: "above .382", score: 84, tone: "gn" },
  { tf: "1-Hour", w: 0.20, wy: "Re-accum", ew: "W(iii)", fb: "golden held", score: 71, tone: "gn" },
  { tf: "15-Min", w: 0.10, wy: "Pullback", ew: "W(iv)", fb: "testing .5", score: 58, tone: "amb" },
];
const CE_CONSENSUS = Math.round(CE_MTF.reduce((s, t) => s + t.score * t.w, 0));
function MtfTable() {
  return (
    <div>
      <MiniTable
        cols={[{ h: "Timeframe", k: "tf", mono: true }, { h: "Wt", k: "w", mono: true, align: "right" },
               { h: "Wyckoff", k: "wy" }, { h: "Elliott", k: "ew", mono: true }, { h: "Fib", k: "fb" },
               { h: "Score", k: "score", align: "right" }]}
        rows={CE_MTF.map(t => ({
          tf: <b>{t.tf}</b>, w: <span className="dim2">{t.w.toFixed(2)}</span>,
          wy: <span className="dim2" style={{ fontSize: 11 }}>{t.wy}</span>,
          ew: <span className="dim2" style={{ fontSize: 11 }}>{t.ew}</span>,
          fb: <span className="dim2" style={{ fontSize: 11 }}>{t.fb}</span>,
          score: <span className="pv-mtf-score mono" style={{ color: `var(--${t.tone})` }}>{t.score}</span>,
        }))} />
      <div className="pv-consensus">
        <span className="label-cap">Weighted consensus</span>
        <span className="pv-consensus-num mono up">{CE_CONSENSUS}</span>
        <Pill tone="gn" small>ALIGNED · bullish bias</Pill>
      </div>
    </div>
  );
}

const CE_FEATS = [
  { f: "Fib cluster confluence", v: 0.27, tone: "amb" },
  { f: "Wyckoff phase D", v: 0.22, tone: "copper" },
  { f: "Multi-TF alignment", v: 0.19, tone: "gn" },
  { f: "Elliott wave-3 position", v: 0.17, tone: "violet" },
  { f: "Relative volume (1.3×)", v: 0.15, tone: "cy" },
];
function ProbPanel() {
  const max = Math.max(...CE_FEATS.map(f => f.v));
  return (
    <div className="pv-prob">
      <div className="pv-prob-num">
        <div className="label-cap">P(success)</div>
        <div className="pv-prob-v mono up">0.84</div>
        <div className="pv-prob-sub mono dim2">gradient-boosted · 1,840 analogs · Wilson LB 0.71</div>
      </div>
      <div className="pv-feats">
        {CE_FEATS.map((f, k) => (
          <div key={k} className="pv-feat">
            <span className="pv-feat-label mono">{f.f}</span>
            <span className="pv-feat-bar"><span style={{ width: `${(f.v / max) * 100}%`, background: `var(--${f.tone})` }} /></span>
            <span className="pv-feat-v mono dim2">{f.v.toFixed(2)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ConfluenceView({ ticker, dir, onTab }) {
  return (
    <div className="pv-view">
      {/* verdict hero */}
      <div className="pv-cockpit">
        <div className="pv-ck-score">
          <div className="label-cap">Composite</div>
          <div className="pv-ck-num mono">{CE_COMPOSITE}<span>/100</span></div>
          <div className="pv-gate is-go">SIGNAL ✓ GO</div>
        </div>
        <div className="pv-ck-stats">
          <div className="pv-ck-stat"><div className="label-cap">Theories aligned</div><div className="pv-ck-v mono up">{CE_ALIGNED} / {CE_THEORIES.length}</div></div>
          <div className="pv-ck-stat"><div className="label-cap">MTF consensus</div><div className="pv-ck-v mono up">{CE_CONSENSUS}</div></div>
          <div className="pv-ck-stat"><div className="label-cap">P(success)</div><div className="pv-ck-v mono up">0.84</div></div>
          <div className="pv-ck-stat"><div className="label-cap">Trigger</div><div className="pv-ck-v mono copper">&gt;$213.40</div></div>
          <div className="pv-ck-verdict mono">Context → structure → projection all align. <b className="warn">TD flags exhaustion near $214–216</b> — enter on the trigger, trail stops.</div>
        </div>
      </div>

      <SectionHeader n={1} title="Theory board" sub="every discipline's current read — click to open" style="minimal" />
      <div className="pv-pad"><TheoryBoard onTab={onTab} /></div>

      <SectionHeader n={2} title="Confluence price map" sub="where every theory's levels stack — true to scale" style="minimal" />
      <div className="pv-pad"><ConfluenceMap /></div>

      <SectionHeader n={3} title="Weighted composite score" sub="Wyckoff context · Elliott structure · Fibonacci projection" style="minimal" />
      <div className="pv-pad"><CompositePanel /></div>

      <div className="pv-2col">
        <div>
          <div className="pv-block-h label-cap">Multi-timeframe consensus</div>
          <MtfTable />
        </div>
        <div>
          <div className="pv-block-h label-cap">ML probability of success</div>
          <ProbPanel />
        </div>
      </div>

      <SectionHeader n={4} title="Action ladder" sub="exact triggers · sized to the base" style="minimal" />
      <div className="pv-pad">
        <div className="action-ladder">
          <div className="al-row al-gn"><span className="mono">CLOSE &gt; $213.40 pivot + RVOL ≥ 1.30×</span><Pill tone="gn" small>GO · full size</Pill></div>
          <div className="al-row al-amb"><span className="mono">Intraday &gt; pivot, fades by close</span><Pill tone="amb" small>WAIT · half on retest</Pill></div>
          <div className="al-row al-rd"><span className="mono">Close &lt; $206.00 LPS / VAL (breakout fails)</span><Pill tone="rd" small>EXIT · skip</Pill></div>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { ConfluenceView, CE_COMPOSITE, CE_CONSENSUS, CE_THRESHOLD });

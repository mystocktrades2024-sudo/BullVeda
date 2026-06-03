// patterns-mlforecast.jsx — "ML Forecast" sub-tab for the Patterns lens.
// Treats the 7 pattern theories as MODEL FEATURES and runs an ML-style
// meta-model: per-theory feature contributions → ensemble probability →
// forward-edge verdict + a confidence-weighted price projection. Pairs the
// AIPredict ensemble (if present) with the live pattern composite.

const { useMemo: useMemoMlf } = React;

// the 7 pattern theories as ML features. Each derives a per-ticker STANCE
// (label + probability) so the meta-model reflects this name's actual structure,
// not a static base. In production each `read` calls the real theory detector.
const MLF_FEATURES = [
  { id: "wyckoff", w: 0.20, tone: "copper",
    read: (r) => { const ph = ["Phase A (stopping)", "Phase B (building)", "Phase C (spring)", "Phase D (markup)", "Phase E (trend)"][Math.floor(r() * 5)]; const bull = /C|D|E/.test(ph); return { label: `Wyckoff · ${ph}`, p: bull ? 0.6 + r() * 0.32 : 0.3 + r() * 0.25 }; } },
  { id: "elliott", w: 0.18, tone: "violet",
    read: (r) => { const w = ["Wave 1", "Wave 2", "Wave 3", "Wave 4", "Wave 5", "Wave A", "Wave C"][Math.floor(r() * 7)]; const bull = /1|3|5/.test(w); return { label: `Elliott · ${w}`, p: bull ? 0.58 + r() * 0.34 : 0.28 + r() * 0.26 }; } },
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

function MLForecastView({ ticker, dir }) {
  const sym = (ticker && ticker.symbol) || "ARGN";
  const px = (ticker && ticker.price) || 213.4;
  const M = useMemoMlf(() => {
    // per-theory seeded RNG keyed to (symbol, theory) → stable, name-specific stance
    const mk = (salt) => { let s = 0; const k = sym + salt; for (let i = 0; i < k.length; i++) s = (s * 31 + k.charCodeAt(i)) & 0x7fffffff; return () => { s = (s * 1103515245 + 12345) & 0x7fffffff; return s / 0x7fffffff; }; };
    const feats = MLF_FEATURES.map((f) => {
      const stance = f.read(mk(f.id));
      const p = Math.max(0.05, Math.min(0.97, stance.p));
      return { k: stance.label, w: f.w, tone: f.tone, p, contrib: +((p - 0.5) * f.w * 2).toFixed(3) };
    });
    const ens = feats.reduce((a, f) => a + f.contrib, 0);          // [-1,1]-ish
    const pUp = Math.max(0.05, Math.min(0.95, 0.5 + ens * 0.9));
    const score = Math.round(Math.max(2, Math.min(99, 50 + ens * 95)));
    const verdict = score >= 66 ? "BUY" : score <= 40 ? "SELL" : "HOLD";
    const conf = Math.abs(ens) > 0.32 ? "HIGH" : Math.abs(ens) > 0.16 ? "MED" : "LOW";
    const agree = feats.filter(f => f.p >= 0.5).length;
    // confidence-weighted projection over 1W/1M/3M
    const vol = 0.02 + (sym.charCodeAt(0) % 7) / 600;
    const horizons = [["1W", 5], ["1M", 21], ["3M", 63]].map(([l, d]) => {
      const drift = ens * vol * d * 0.42;
      const band = vol * Math.sqrt(d) * 1.0;
      return { l, med: +(px * (1 + drift)).toFixed(2), lo: +(px * (1 + drift - band)).toFixed(2), hi: +(px * (1 + drift + band)).toFixed(2), ret: +(drift * 100).toFixed(1) };
    });
    const fmax = Math.max(...feats.map(f => Math.abs(f.contrib)));
    // cross-check vs the standalone AI Predictions engine if available
    const ap = window.AIPredict ? window.AIPredict.predict(sym) : null;
    return { feats, ens: +ens.toFixed(2), pUp: +pUp.toFixed(2), score, verdict, conf, agree, horizons, fmax, ap };
  }, [sym, px]);

  const vt = M.verdict === "BUY" ? "gn" : M.verdict === "SELL" ? "rd" : "amb";

  return (
    <div className="pv-view">
      <div className="pv-stat">
        <div className="pv-stat-cell"><div className="label-cap">ML verdict</div><div className={`pv-stat-v mono ${vt === "gn" ? "up" : vt === "rd" ? "dn" : "warn"}`}>{M.verdict}</div></div>
        <div className="pv-stat-cell"><div className="label-cap">Edge score</div><div className="pv-stat-v mono">{M.score}/100</div></div>
        <div className="pv-stat-cell"><div className="label-cap">P(up · 21d)</div><div className="pv-stat-v mono up">{Math.round(M.pUp * 100)}%</div></div>
        <div className="pv-stat-cell"><div className="label-cap">Theories agree</div><div className="pv-stat-v mono">{M.agree}/7</div></div>
        <div className="pv-stat-cell"><div className="label-cap">Confidence</div><div className="pv-stat-v"><ConfBar value={M.conf === "HIGH" ? 0.85 : M.conf === "MED" ? 0.6 : 0.35} tone={vt} width={72} /></div></div>
      </div>

      <SectionHeader n={1} title="Pattern-theory feature model" sub="each theory is a model feature · signed contribution to the up-thesis · weighted ensemble" style="minimal" />
      <div className="pv-pad">
        <div className="mlf-feats">
          <div className="mlf-feat mlf-feat--head">
            <span className="mlf-feat-k">Theory · stance</span>
            <span className="mlf-feat-p">P(up)</span>
            <span className="mlf-feat-track-h">bearish ◂ contribution ▸ bullish</span>
            <span className="mlf-feat-w">weight</span>
          </div>
          {M.feats.map((f, i) => {
            const [theory, ...rest] = f.k.split(" · ");
            const stance = rest.join(" · ");
            const bull = f.contrib >= 0;
            const pTone = f.p >= 0.6 ? "gn" : f.p >= 0.45 ? "amb" : "rd";
            return (
              <div key={i} className="mlf-feat">
                <span className="mlf-feat-k">
                  <b className="mlf-feat-theory">{theory}</b>
                  <span className="mlf-feat-stance">{stance}</span>
                </span>
                <span className={`mlf-feat-p mono kpi-tone--${pTone}`}>{Math.round(f.p * 100)}%</span>
                <span className="mlf-feat-track">
                  <span className="mlf-feat-zero" />
                  <span className={`mlf-feat-fill ${bull ? "is-bull" : "is-bear"}`}
                        style={bull ? { left: "50%", width: `${(f.contrib / M.fmax) * 50}%` } : { right: "50%", width: `${(-f.contrib / M.fmax) * 50}%` }} />
                  <span className={`mlf-feat-val mono ${bull ? "up" : "dn"}`} style={bull ? { left: "calc(50% + 4px)" } : { right: "calc(50% + 4px)" }}>{bull ? "+" : ""}{f.contrib.toFixed(2)}</span>
                </span>
                <span className="mlf-feat-w mono dim2">{Math.round(f.w * 100)}%</span>
              </div>
            );
          })}
        </div>
        <div className="mlf-ens mono">
          <span className="dim2">weighted ensemble</span> <b className={M.ens >= 0 ? "up" : "dn"}>{M.ens >= 0 ? "+" : ""}{M.ens}</b>
          <span className="mlf-ens-arrow dim2">→</span> <span className="dim2">P(up)</span> <b>{Math.round(M.pUp * 100)}%</b>
          <span className="mlf-ens-arrow dim2">→</span> <b className={`mlf-ens-verdict kpi-tone--${vt}`}>{M.verdict}</b>
        </div>
      </div>

      <div className="pv-2col">
        <div>
          <div className="pv-block-h label-cap">Confidence-weighted projection</div>
          <MiniTable
            cols={[{ h: "Horizon", k: "l" }, { h: "Low", k: "lo", mono: true, align: "right" }, { h: "Median", k: "m", mono: true, align: "right" }, { h: "High", k: "hi", mono: true, align: "right" }, { h: "Exp.", k: "r", align: "right" }]}
            rows={M.horizons.map(h => ({ l: <b>{h.l}</b>, lo: <span className="dim2">${h.lo}</span>, m: <b>${h.med}</b>, hi: <span className="dim2">${h.hi}</span>, r: <span className={h.ret >= 0 ? "up" : "dn"}>{h.ret >= 0 ? "+" : ""}{h.ret}%</span> }))} />
        </div>
        <div>
          <div className="pv-block-h label-cap">Cross-check · AI Predictions engine</div>
          {M.ap ? (
            <MiniTable
              cols={[{ h: "Model", k: "m" }, { h: "Verdict", k: "v" }, { h: "Score", k: "s", align: "right" }, { h: "P(up)", k: "p", align: "right" }]}
              rows={[
                { m: "Pattern meta-model", v: <Pill tone={vt} small>{secBias(M.verdict)}</Pill>, s: <b>{M.score}</b>, p: `${Math.round(M.pUp * 100)}%` },
                { m: "AI ensemble (3-head)", v: <Pill tone={M.ap.verdict === "BUY" ? "gn" : M.ap.verdict === "SELL" ? "rd" : "amb"} small>{secBias(M.ap.verdict)}</Pill>, s: <b>{M.ap.score}</b>, p: `${Math.round(M.ap.pUp * 100)}%` },
              ]} />
          ) : <div className="mono dim2" style={{ fontSize: 12, padding: 8 }}>AI Predictions engine not loaded.</div>}
          <div className="pv-invalid" style={{ border: "1px solid var(--line)", background: "var(--bg-1)", marginTop: 10 }}>
            <span className="label-cap">Read</span>
            <span className="mono">{M.agree >= 5 ? <>Pattern theories are <b className="up">stacked bullish</b> ({M.agree}/7) — the meta-model and the AI ensemble {M.ap && M.ap.verdict === M.verdict ? "agree" : "diverge slightly"}. Treat as {M.conf} conviction.</> : <>Mixed pattern evidence ({M.agree}/7 aligned) — <b className="warn">wait for more confluence</b> before sizing.</>}</span>
          </div>
        </div>
      </div>

      <div className="pv-pad">
        <div className="mono dim2" style={{ fontSize: 11, lineHeight: 1.5 }}>
          This meta-model treats the 7 pattern theories as features, weights them, and blends into a single probability — then cross-checks the standalone AI Predictions ensemble. Demo computation; in production each feature is a trained detector and the weights are fit on forward outcomes (see the Track Record surface).
        </div>
      </div>
    </div>
  );
}

window.MLForecastView = MLForecastView;
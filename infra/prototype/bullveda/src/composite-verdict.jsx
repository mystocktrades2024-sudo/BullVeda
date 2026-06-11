// composite-verdict.jsx — reconciles all lenses into ONE weighted net call,
// names the dissenters, and reacts to ticker + mode. Resolves the audit's #1
// systemic finding ("confluence shown but never reconciled").
const { useMemo: useMemoCV } = React;

// memo cache — compositeVerdict is called ~6× per detail render (hero, horizon×3,
// thesis, checklist). Cache by identity so it computes once per (ticker, mode, data).
const _CV_CACHE = new Map();
// Insider "why" — prefer the real cluster-buy count from the feed; never print
// "undefined buyers" (2026-06-10). Falls through count → net → generic flow.
function _insiderWhy(ticker, ie) {
  const idd = ticker && (ticker.insider_data || (ticker._raw && ticker._raw.insider_data));
  let b = (idd && idd.buys != null) ? idd.buys : ((ie && ie.buyers != null) ? ie.buyers : null);
  if (b != null && isFinite(b)) return `${b} buyer${b === 1 ? "" : "s"}`;
  const net = ticker && (ticker.insNet != null ? ticker.insNet : null);
  if (net != null && isFinite(net)) return net > 0 ? `net +${net} insider` : net < 0 ? `net ${net} insider` : "balanced flow";
  return "insider flow";
}
const _cvImpl = function (ticker, mode) {
  const P = ticker.pillars || {};
  const moKey = mode === "POSITION" ? "position" : mode === "INVESTMENT" ? "invest" : "swing";
  const proj = (window.AIPredict && ticker.symbol) ? window.AIPredict.projection(ticker.symbol, moKey) : null;
  const adj  = window.modeAdjust ? window.modeAdjust(ticker, mode) : ticker;
  const ie   = window.insiderEdge ? window.insiderEdge(ticker.symbol) : null;
  const erDays = ticker.earnings ? ticker.earnings.days : 21;
  const aiPup  = proj ? proj.pUp * 100 : (ticker.pUp ? ticker.pUp * 100 : 55);
  const rrScore = Math.max(0, Math.min(100, ((adj.rMultiple || 1.7) / 3) * 100));
  const wilson  = ticker.setupStats ? ticker.setupStats.wilsonLB * 100 : 47;
  const tech = P.technical ?? 60, fund = P.fundamental ?? 55, cat = P.catalyst ?? 55,
        risk = P.risk ?? 60, edge = P.edge ?? 60;
  const cl = v => Math.round(Math.max(2, Math.min(99, v)));

  // each lens → a 0-100 stance derived from real per-ticker signals + a weight
  const lenses = [
    { k: "Overview",   w: 0.12, v: cl(ticker.score ?? 60), why: "5-pillar composite" },
    { k: "AI Edge",    w: 0.14, v: cl(aiPup),               why: `P(up) ${Math.round(aiPup)}% · ${proj ? proj.horizon : moKey}` },
    { k: "Technicals", w: 0.11, v: cl(tech),                why: "trend / momentum stack" },
    { k: "Patterns",   w: 0.10, v: cl(tech * 0.6 + edge * 0.4), why: "structure confluence" },
    { k: "SMC",        w: 0.08, v: cl(tech * 0.65 + cat * 0.35), why: "smart-money structure" },
    { k: "Value",      w: 0.09, v: cl(fund),                why: "intrinsic vs price" },
    { k: "Risk",       w: 0.09, v: cl(risk),                why: "VaR / sizing headroom" },
    { k: "Track Rec.", w: 0.08, v: cl(wilson),              why: `Wilson LB ${Math.round(wilson)}%` },
    { k: "Plan",       w: 0.07, v: cl(rrScore),             why: `R:R ${(adj.rMultiple || 1.7).toFixed(2)}` },
    // erDays == null means NO earnings date — score NEUTRAL (60), never the
    // imminent-earnings penalty (34), and never render "ER in nulld" (2026-06-10).
    { k: "Earnings",   w: 0.04, v: cl(erDays == null ? 60 : erDays <= 5 ? 34 : erDays <= 12 ? 48 : 70), why: (erDays == null ? "no ER date" : `ER in ${erDays}d`) },
    { k: "Options",    w: 0.04, v: cl(erDays == null ? 55 : erDays <= 10 ? 42 : 58), why: "IV richness" },
    // prefer the real insider buyer count (ticker.insider_data / insNet); guard
    // ie.buyers so the cell never prints "undefined buyers" (2026-06-10).
    { k: "Insider",    w: 0.04, v: cl(ie ? ie.score : 58),  why: _insiderWhy(ticker, ie) },
  ];
  // ── mode-conditional reweight (whitepaper P1): swing = technical-led,
  // investment = quality/insider-led, position = balanced. Normalized to 1.0. ──
  const MW = {
    swing:    { Overview: .10, "AI Edge": .14, Technicals: .16, Patterns: .12, SMC: .10, Value: .02, Risk: .08, "Track Rec.": .08, Plan: .08, Earnings: .04, Options: .04, Insider: .04 },
    position: { Overview: .11, "AI Edge": .12, Technicals: .10, Patterns: .09, SMC: .07, Value: .10, Risk: .09, "Track Rec.": .08, Plan: .07, Earnings: .06, Options: .05, Insider: .06 },
    invest:   { Overview: .10, "AI Edge": .08, Technicals: .04, Patterns: .04, SMC: .03, Value: .28, Risk: .08, "Track Rec.": .06, Plan: .04, Earnings: .07, Options: .03, Insider: .15 },
  };
  const prof = MW[moKey] || MW.swing;
  const wsum = lenses.reduce((a, l) => a + (prof[l.k] ?? l.w), 0) || 1;
  lenses.forEach(l => { l.w = (prof[l.k] ?? l.w) / wsum; });

  // ── reconcile to the engine (audit #6 + score consistency) ──
  // decisions_by_mode is the AUTHORITATIVE per-mode call. Use the engine's
  // composite_score as the headline NUMBER (so Overview matches Home/Scanner) and
  // its verdict as the LABEL; the lens-weighted recompute is only the fallback.
  const _dm = ticker.decisionsByMode || null;
  const _dmKey = moKey === "invest" ? "investment" : moKey;
  const _engRaw = _dm ? (_dm[_dmKey] != null ? _dm[_dmKey] : _dm[moKey]) : null;
  const _engVerdict = _engRaw ? (typeof _engRaw === "string" ? _engRaw : _engRaw.verdict) : null;
  const _engScore = (_engRaw && typeof _engRaw === "object" && typeof _engRaw.composite_score === "number") ? _engRaw.composite_score : null;
  const lensNet = Math.round(lenses.reduce((a, l) => a + l.w * l.v, 0));
  // SSOT (2026-06-09): the headline NUMBER binds the canonical 5-pillar score
  // (ticker.score — the SAME number as Scanner / Home / Overview). The
  // lens-weighted recompute (lensNet) is the AVT-case anti-pattern and survives
  // ONLY as the "why" breakdown below, never as a competing headline. Path B
  // (engine-computed per-mode score via decisions_by_mode.composite_score) is
  // tracked under OVERVIEW-VERDICT-RECON; until then _engScore is a fallback
  // ahead of the lens recompute.
  const net = (typeof ticker.score === "number" && isFinite(ticker.score))
    ? Math.round(ticker.score)
    : (_engScore != null ? Math.round(_engScore) : lensNet);
  const tone = v => v >= 62 ? "gn" : v >= 46 ? "amb" : "rd";
  lenses.forEach(l => { l.tone = tone(l.v); });
  const _vt = v => v === "BUY" ? "gn" : v === "WATCH" ? "amb" : "rd";
  // Prefer engine per-mode verdict, then the canonical swing verdict (stage),
  // and only recompute from the net as a last resort (kept consistent now that
  // net binds the canonical score).
  const _canonV = (ticker.verdict || ticker.stage || "").toString().toUpperCase() || null;
  const verdict = _engVerdict || _canonV || (net >= 66 ? "BUY" : net >= 50 ? "WATCH" : net >= 40 ? "AVOID" : "PASS");
  const verdictSource = _engVerdict ? "engine" : "derived";
  const vtone = _engVerdict ? _vt(_engVerdict) : (net >= 66 ? "gn" : net >= 50 ? "amb" : "rd");
  // ── market-gate awareness (fix b/c) ── a market-wide entry block isn't a
  // bearish stock: relabel the directional chip to Neutral/amber so the word
  // and the tone agree, and surface the engine reason for downstream notes.
  const _engReason = (_engRaw && typeof _engRaw === "object") ? (_engRaw.reason || null) : null;
  const _gated = window.isMarketGateBlock ? window.isMarketGateBlock(verdict, _engReason, net) : false;
  // Two-axis verdict (2026-06-10): the WORD is the DIRECTIONAL bias, NOT
  // secBias(verdict). An AVOID-by-extended-gate long is "Bullish · Wait", never
  // "Bearish". This card is PER-MODE, so prefer the per-mode bias/action/reason
  // from decisions_by_mode[mode] (_engRaw); fall back to the top-level row.
  const _perMode = (_engRaw && typeof _engRaw === "object")
    ? { bias: _engRaw.bias, action: _engRaw.action, reasonClass: _engRaw.reason_class } : {};
  const _biasSrc = _perMode.bias ? _perMode : ticker;
  const _br = (window.biasRead ? window.biasRead(_biasSrc) : null) || { label: (window.secBias ? window.secBias(verdict) : verdict), tone: vtone };
  const _act = window.actionRead ? window.actionRead(_perMode.action ? _perMode : ticker) : null;
  const biasLabel = _gated ? "Neutral" : _br.label;
  const vtoneFinal = _gated ? "amb" : (_br.tone || vtone);
  const actionLabel = _gated ? null : (_act ? _act.label : null);
  const reasonNoteTxt = window.reasonNote ? window.reasonNote(_perMode.reasonClass ? _perMode : ticker) : null;
  const agree   = lenses.filter(l => l.tone === "gn").length;
  const caution = lenses.filter(l => l.tone === "amb").length;
  const fail    = lenses.filter(l => l.tone === "rd").length;
  // dissenters = lenses pulling AGAINST the net direction
  const bullish = net >= 50;
  const dissenters = lenses
    .filter(l => bullish ? l.v < 50 : l.v >= 62)
    .sort((a, b) => bullish ? a.v - b.v : b.v - a.v);
  // confidence from spread of opinion (low spread = high conf)
  const mean = lenses.reduce((a, l) => a + l.v, 0) / lenses.length;
  const sd = Math.sqrt(lenses.reduce((a, l) => a + (l.v - mean) ** 2, 0) / lenses.length);
  const conf = sd < 12 ? "HIGH" : sd < 20 ? "MED" : "LOW";
  const disagree = sd < 12 ? "low" : sd < 20 ? "moderate" : "high";
  return { net, lensNet, verdict, verdictSource, vtone: vtoneFinal, biasLabel, actionLabel, reasonNote: reasonNoteTxt, gated: _gated, reason: _engReason, conf, disagree, lenses, agree, caution, fail, dissenters, mode };
};
function compositeVerdict(ticker, mode) {
  const key = (ticker && ticker.symbol || "") + "|" + mode + "|" + (ticker && ticker.score) + "|" + (ticker && ticker.ml && ticker.ml.direction) + "|" + (ticker && ticker._fund ? 1 : 0);
  const hit = _CV_CACHE.get(key);
  if (hit) return hit;
  const r = _cvImpl(ticker, mode);
  if (_CV_CACHE.size > 200) _CV_CACHE.clear();
  _CV_CACHE.set(key, r);
  return r;
}
window.compositeVerdict = compositeVerdict;

function CompositeVerdict({ ticker, mode, onLens }) {
  const cv = useMemoCV(() => compositeVerdict(ticker, mode), [ticker, mode, ticker && ticker.symbol]);
  const maxW = Math.max(...cv.lenses.map(l => l.w));
  const biasWord = cv.biasLabel || (window.secBias ? window.secBias(cv.verdict) : cv.verdict);
  const cvPrompt = () => `In plain English, explain to a beginner why ${ticker.symbol} has an overall ${biasWord} read (score ${cv.net} out of 100, ${mode} timeframe). 3-4 short sentences. Name the 2-3 strongest supporting areas and anything that disagrees, in everyday words.
Overall: ${biasWord}, score ${cv.net}/100 (canonical 5-pillar), lens agreement ${cv.disagree === "low" ? "high" : cv.disagree === "high" ? "low" : "moderate"}.
Strongest areas: ${cv.lenses.slice().sort((a, b) => b.v - a.v).slice(0, 3).map(l => `${l.k} ${l.v}/100 (${l.why})`).join("; ")}.
Weakest or disagreeing: ${cv.dissenters.length ? cv.dissenters.slice(0, 3).map(d => `${d.k} ${d.v}/100`).join("; ") : "none"}.`;
  return (
    <div className={`cv cv--${cv.vtone}`}>
      <div className="cv-left">
        <div className="cv-eyebrow mono">COMPOSITE BIAS · {cv.lenses.length} LENSES · <b className="copper">{mode}</b></div>
        <div className="cv-headline">
          <span className={`cv-verdict cv-verdict--${cv.vtone}`}>{cv.biasLabel || (window.secBias ? window.secBias(cv.verdict) : cv.verdict)}</span>
          {cv.actionLabel && <span className="cv-action mono" title="What to do — the ACTION axis, separate from the directional bias. 'Wait' = the thesis is intact but the entry is extended/blocked here.">· {cv.actionLabel}</span>}
          <span className="cv-net mono" title="Canonical 5-pillar composite score — the SAME number shown on the Scanner / Home / Overview. The lens bars below explain how each area contributes; they do not override this number.">{cv.net}<span className="cv-net-of">/100</span></span>
          {typeof ticker.score === "number" && Math.round(ticker.score) !== cv.net && (
            <span className="cv-net-alt mono dim2" style={{ fontSize: 12, alignSelf: "flex-end", marginBottom: 5 }} title="Generic, horizon-agnostic 5-pillar score (the number shown on the Scanner). It does NOT reweight catalyst / entry-quality for your timeframe, so it usually reads higher than the per-mode number.">· overall {Math.round(ticker.score)}</span>
          )}
          <span className="cv-conf mono dim2" title="How much the lenses agree with each other — NOT a confidence in the signal. High disagreement = the areas are split, which is why a high pillar score can still read WATCH/Neutral.">lens agreement <b className={cv.disagree === "low" ? "gn-c" : cv.disagree === "high" ? "rd-c" : "amb-c"}>{cv.disagree === "low" ? "high" : cv.disagree === "high" ? "low" : "moderate"}</b></span>
        </div>
        {cv.reasonNote && <div className="cv-reason-note mono dim2" style={{ marginTop: 4, fontSize: 12 }}>⚠ {cv.reasonNote}</div>}
        <div className="cv-counts mono">
          <span className="cv-cnt gn">{cv.agree} agree</span>
          <span className="cv-cnt amb">{cv.caution} caution</span>
          <span className="cv-cnt rd">{cv.fail} against</span>
        </div>
        <div className="cv-dissent mono">
          {cv.dissenters.length === 0
            ? <span className="dim2">No lens materially dissents — clean confluence.</span>
            : <><span className="dim2">Dissenting: </span>{cv.dissenters.slice(0, 4).map((d, i) => (
                <button key={d.k} className="cv-diss-pill" onClick={() => onLens && onLens(d.k)} title={d.why}>
                  {d.k} <span className="dim2">{d.v}</span>
                </button>
              ))}</>}
        </div>
        {window.AiExplain && <AiExplain build={cvPrompt} label="Why this rating?" />}
      </div>
      <div className="cv-right">
        <div className="cv-bar-lbl mono dim2">weighted contribution · click a lens to open it</div>
        <div className="cv-bars">
          {cv.lenses.map(l => (
            <button key={l.k} className="cv-bar-col" onClick={() => onLens && onLens(l.k)} title={`${l.k} · ${l.v}/100 · weight ${(l.w*100).toFixed(0)}% · ${l.why}`}>
              <span className="cv-bar-track" style={{ height: 46 }}>
                <span className={`cv-bar-fill kpi-tone-bg--${l.tone}`} style={{ height: `${l.v * 0.46}px`, opacity: 0.4 + (l.w / maxW) * 0.6 }} />
              </span>
              <span className="cv-bar-k mono">{l.k.replace(" Rec.", "")}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
window.CompositeVerdict = CompositeVerdict;

// one-time CSS inject
(function () {
  if (document.getElementById("cv-css")) return;
  const s = document.createElement("style"); s.id = "cv-css";
  s.textContent = `
  .cv{display:flex;gap:22px;align-items:stretch;background:var(--bg-1,#121515);border:1px solid var(--line,#262c2c);border-radius:8px;padding:16px 18px;margin-bottom:14px;flex-wrap:wrap;}
  .cv--gn{border-left:3px solid var(--gn);} .cv--amb{border-left:3px solid var(--amb);} .cv--rd{border-left:3px solid var(--rd);}
  .cv-left{flex:1;min-width:280px;display:flex;flex-direction:column;gap:8px;}
  .cv-eyebrow{font-size:10px;letter-spacing:.16em;color:var(--ink-3);}
  .cv-headline{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;}
  .cv-verdict{font-size:22px;font-weight:700;letter-spacing:.02em;}
  .cv-verdict--gn{color:var(--gn);} .cv-verdict--amb{color:var(--amb);} .cv-verdict--rd{color:var(--rd);}
  .cv-net{font-size:30px;font-weight:600;}
  .cv-net-of{font-size:14px;color:var(--ink-3);}
  .cv-conf{font-size:11px;}
  .gn-c{color:var(--gn);} .amb-c{color:var(--amb);} .rd-c{color:var(--rd);}
  .cv-counts{display:flex;gap:8px;}
  .cv-cnt{font-size:10px;font-weight:700;letter-spacing:.06em;padding:2px 9px;border-radius:20px;text-transform:uppercase;}
  .cv-cnt.gn{color:var(--gn);background:var(--gn-bg,rgba(95,174,126,.13));}
  .cv-cnt.amb{color:var(--amb);background:var(--amb-bg,rgba(214,164,90,.13));}
  .cv-cnt.rd{color:var(--rd);background:var(--rd-bg,rgba(210,104,95,.13));}
  .cv-dissent{font-size:11.5px;display:flex;flex-wrap:wrap;gap:6px;align-items:center;}
  .cv-diss-pill{font-family:var(--mono);font-size:11px;color:var(--ink-1);background:var(--bg-3,#1d2222);border:1px solid var(--line-2,#323a3a);border-radius:5px;padding:2px 8px;cursor:pointer;}
  .cv-diss-pill:hover{border-color:var(--copper);}
  .cv-right{flex:none;width:min(420px,100%);display:flex;flex-direction:column;gap:7px;}
  .cv-bar-lbl{font-size:9.5px;letter-spacing:.08em;}
  .cv-bars{display:flex;gap:4px;align-items:flex-end;}
  .cv-bar-col{flex:1;background:none;border:none;padding:0;cursor:pointer;display:flex;flex-direction:column;align-items:center;gap:4px;}
  .cv-bar-track{display:flex;align-items:flex-end;justify-content:center;width:100%;background:var(--bg-3,#1d2222);border-radius:3px 3px 0 0;overflow:hidden;}
  .cv-bar-fill{width:100%;border-radius:3px 3px 0 0;transition:height .25s;}
  .cv-bar-k{font-size:7.5px;letter-spacing:.02em;color:var(--ink-3);white-space:nowrap;transform:rotate(-32deg);transform-origin:center;height:26px;}
  .cv-bar-col:hover .cv-bar-k{color:var(--ink-1);}
  .kpi-tone-bg--gn{background:var(--gn);} .kpi-tone-bg--amb{background:var(--amb);} .kpi-tone-bg--rd{background:var(--rd);}
  `;
  document.head.appendChild(s);
})();

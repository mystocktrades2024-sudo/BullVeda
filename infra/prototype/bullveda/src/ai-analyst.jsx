// ai-analyst.jsx — genuinely AI-powered research read (calls window.claude).
// Grounds the LLM in the ticker's real engine signals and returns a structured
// analyst note: thesis · drivers · bull/bear · risks · suggested action.
// Complements (does not replace) the quant ML board — no fabricated numbers.

const { useState: useAIA, useMemo: useAIAm } = React;

function AIAnalystView({ all, onTicker, pick, onPick, single, sym: symProp, ticker }) {
  const AP = window.AIPredict;
  const allList = all || (AP ? AP.all() : []);
  const top = useAIAm(() => [...allList].sort((a, b) => b.score - a.score).slice(0, 8), [allList]);
  const sym = single ? (symProp || (ticker && (ticker.symbol || ticker.sym))) : (pick && allList.find(p => p.sym === pick) ? pick : (top[0] && top[0].sym));
  const [loading, setLoading] = useAIA(false);
  const [res, setRes] = useAIA(null);
  const [err, setErr] = useAIA(null);
  const [cacheBySym, setCache] = useAIA({});

  const P = useAIAm(() => { try { return sym && AP ? AP.predict(sym) : null; } catch (e) { return null; } }, [sym]);

  React.useEffect(() => { if (sym && cacheBySym[sym]) { setRes(cacheBySym[sym]); setErr(null); } else { setRes(null); setErr(null); } }, [sym]);

  function buildPrompt(P) {
    const heads = P.heads.map(h => `${h.label} ${h.score >= 0 ? "+" : ""}${h.score}`).join(", ");
    const feats = (P.feats || []).slice(0, 4).map(f => f.k).join(", ");
    const ctx = [
      `Ticker: ${P.sym} (${P.name}), sector ${P.sector}, price $${P.px}.`,
      `Quant engine read — composite score ${P.score}/100, verdict ${P.verdict}, P(up) ${Math.round(P.pUp * 100)}%, confidence ${P.conf}.`,
      `3-model ensemble heads: ${heads} (agree ${P.agree}/3).`,
      `Monte-Carlo 3M median return ${P.horizons[2].ret.toFixed(1)}%, target $${P.target}, modeled stop $${P.stop}.`,
      `Top model features: ${feats}. Historical analogs resolved up ${Math.round((P.analogWin || 0) * 100)}% of the time.`,
    ].join("\n");
    return `You are a disciplined swing-trading analyst. Using ONLY the quantitative signals below, write a concise, balanced read for a self-directed trader. Do NOT invent precise price predictions or probabilities beyond what's given; reason qualitatively about what the signals imply.

${ctx}

Respond with ONLY valid minified JSON (no markdown, no commentary) in this exact shape:
{"thesis":"1-2 sentence core read","drivers":["3-5 word bullet","..."],"bull":"1 sentence best case","bear":"1 sentence risk case","risks":["short risk","..."],"action":"one concrete next step (e.g. wait for trigger, size small, avoid)","conviction":"High|Medium|Low"}`;
  }

  async function generate() {
    if (!P || !window.claude || !window.claude.complete) { setErr("AI helper unavailable in this environment."); return; }
    setLoading(true); setErr(null); setRes(null);
    try {
      const out = await window.claude.complete({ messages: [{ role: "user", content: buildPrompt(P) }] });
      const json = String(out).replace(/```json|```/g, "").trim();
      const start = json.indexOf("{"), end = json.lastIndexOf("}");
      const parsed = JSON.parse(json.slice(start, end + 1));
      setRes(parsed);
      setCache(c => ({ ...c, [sym]: parsed }));
    } catch (e) {
      setErr("Couldn't parse the AI response — try again.");
    } finally { setLoading(false); }
  }

  const convTone = c => /high/i.test(c) ? "gn" : /low/i.test(c) ? "rd" : "amb";

  return (
    <div className="wsx-body aia">
      {!single && (
        <div className="aia-bar">
          <span className="mono dim2">AI analyst read · grounded in the quant engine · top names by edge</span>
          <div className="aia-picks">
            {top.map(p => (
              <button key={p.sym} className={`aia-pick ${p.sym === sym ? "is-on" : ""}`} onClick={() => onPick && onPick(p.sym)}>
                <b>{p.sym}</b><span className="mono dim2">{p.score}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {P && (
        <div className="aia-grid">
          {/* left: the grounding signals the AI is given */}
          <div className="lab-card aia-ctx">
            <div className="lab-card-h mono">SIGNALS GIVEN TO THE AI</div>
            <div className="aia-ctx-rows">
              <div className="aia-ctx-row"><span className="dim2">Score</span><b className={`kpi-tone--${P.score >= 66 ? "gn" : P.score <= 40 ? "rd" : "amb"}`}>{P.score}/100 · {P.verdict}</b></div>
              <div className="aia-ctx-row"><span className="dim2">P(up)</span><b>{Math.round(P.pUp * 100)}% · {P.conf}</b></div>
              <div className="aia-ctx-row"><span className="dim2">Ensemble</span><span className="aia-heads">{P.heads.map((h, i) => <span key={i} className={`aia-head ${h.score >= 0 ? "up" : "dn"}`} title={`${h.label}: ${h.score}`} />)}<span className="mono dim2"> {P.agree}/3</span></span></div>
              <div className="aia-ctx-row"><span className="dim2">3M median</span><b className={P.horizons[2].ret >= 0 ? "up" : "dn"}>{P.horizons[2].ret >= 0 ? "+" : ""}{P.horizons[2].ret.toFixed(1)}%</b></div>
              <div className="aia-ctx-row"><span className="dim2">Target / stop</span><b><span className="up">${P.target}</span> · <span className="dn">${P.stop}</span></b></div>
            </div>
            <button className="aia-gen" onClick={generate} disabled={loading}>{loading ? "✦ Thinking…" : res ? "↻ Regenerate" : "✦ Generate AI read"}</button>
            <div className="aia-disc mono dim2">AI-generated reasoning from the signals above — not a numeric forecast and not investment advice.</div>
          </div>

          {/* right: the AI output */}
          <div className="lab-card aia-out">
            <div className="lab-card-h mono">AI ANALYST · {sym}{res && <span className={`aia-conv kpi-tone--${convTone(res.conviction)}`}>{res.conviction} conviction</span>}</div>
            {!res && !loading && !err && <div className="aia-empty mono dim2">Pick a name and hit <b>Generate</b> — the AI will read the quant signals and write a balanced thesis, bull/bear, risks, and a suggested next step.</div>}
            {loading && <div className="aia-loading"><span className="aia-shimmer" /><span className="aia-shimmer" style={{ width: "82%" }} /><span className="aia-shimmer" style={{ width: "64%" }} /></div>}
            {err && <div className="aia-err mono">{err}</div>}
            {res && (
              <div className="aia-read">
                <div className="aia-thesis">{res.thesis}</div>
                <div className="aia-2col">
                  <div className="aia-case aia-case--bull"><span className="aia-case-l mono">BULL</span>{res.bull}</div>
                  <div className="aia-case aia-case--bear"><span className="aia-case-l mono">BEAR</span>{res.bear}</div>
                </div>
                <div className="aia-sec">
                  <span className="aia-sec-l mono dim2">DRIVERS</span>
                  <div className="aia-chips">{(res.drivers || []).map((d, i) => <span key={i} className="aia-chip aia-chip--gn">{d}</span>)}</div>
                </div>
                <div className="aia-sec">
                  <span className="aia-sec-l mono dim2">RISKS</span>
                  <div className="aia-chips">{(res.risks || []).map((d, i) => <span key={i} className="aia-chip aia-chip--rd">{d}</span>)}</div>
                </div>
                <div className="aia-action"><span className="aia-action-l mono">NEXT STEP</span>{res.action}</div>
              </div>
            )}
          </div>
        </div>
      )}
      {!P && single && <div className="lab-card aia-out"><div className="aia-empty mono dim2">AI analyst needs ML coverage for this name — not in the model universe yet.</div></div>}
    </div>
  );
}

window.AIAnalystView = AIAnalystView;

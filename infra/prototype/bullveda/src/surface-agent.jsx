// surface-agent.jsx — Kairos AI · global dockable assistant (⌘J).
// Context-aware of the current surface + open ticker. Wired to a LOCAL OLLAMA
// instance (http://localhost:11434) with streaming; falls back to a grounded
// scripted analyst when Ollama is unreachable (e.g. in the sandbox preview).

const { useState: useAg, useEffect: useAge, useRef: useAgr } = React;

const AG_LS = "agent_v1";
const OLLAMA_URL = "http://localhost:11434";
const OLLAMA_MODEL = "llama3.1";

const AG_SUGGEST = {
  base: [
    "What changed across the market since yesterday?",
    "Which of my holdings breach my risk profile?",
    "Summarize today's top BUY verdicts.",
  ],
  ticker: (s) => [
    `Summarize ${s}'s verdict across all 14 lenses`,
    `Why is ${s} rated the way it is? Cite the lens.`,
    `Draft a swing trade plan for ${s}`,
    `What's the biggest risk on ${s} right now?`,
  ],
};

// build a compact context string from the live app state
function buildContext(ctx) {
  const lines = [];
  lines.push(`Current surface: ${ctx.surfaceLabel || ctx.surface || "Home"}.`);
  if (ctx.ticker) {
    const t = ctx.ticker;
    const mode = ctx.mode || "SWING";
    lines.push(`Open ticker: ${t.symbol}${t.name ? " (" + t.name + ")" : ""}, current lens "${ctx.lensLabel || ctx.lensId}", mode ${mode}.`);
    // dump every available field on the ticker so Kairos can answer any data question
    const facts = [];
    const FMT = { price: v => `price $${(+v).toFixed(2)}`, verdict: v => `verdict ${v}`, score: v => `score ${v}`,
      chg: v => `day change ${v >= 0 ? "+" : ""}${v}%`, sector: v => `sector ${v}`, industry: v => `industry ${v}`,
      mcap: v => `market cap $${(v / 1e9).toFixed(1)}B`, setup: v => `setup ${v}`, setupFamily: v => `setup ${v}`,
      rs: v => `RS rank ${v}`, beta: v => `beta ${v}`, pivot: v => `pivot $${v}`, stop: v => `stop $${v}`, target: v => `target $${v}` };
    Object.keys(t).forEach(k => { if (t[k] != null && FMT[k]) facts.push(FMT[k](t[k])); });
    if (facts.length) lines.push("Known facts: " + facts.join(", ") + ".");
    // ── full cross-lens dossier from the live engines (so Kairos answers about
    //    ANY lens, not just what's on screen) ──
    if (t.pillars) lines.push("Pillars (0-100): " + Object.entries(t.pillars).map(([k, v]) => `${k} ${v}`).join(", ") + ".");
    if (t.setupStats) lines.push(`Setup stats: ${t.setupFamily || "setup"} · win-rate ${(t.setupStats.winRate * 100).toFixed(0)}% · Wilson LB ${(t.setupStats.wilsonLB * 100).toFixed(0)}% · n=${t.setupStats.n} · R ${(t.rMultiple || 0).toFixed(2)}.`);
    if (t.earnings) lines.push(`Earnings in ${t.earnings.days}d${t.earnings.date ? " (" + t.earnings.date + ")" : ""}.`);
    try {
      if (window.compositeVerdict) {
        const cv = window.compositeVerdict(t, mode);
        lines.push(`COMPOSITE VERDICT (reconciled across ${cv.lenses.length} lenses): ${cv.verdict} ${cv.net}/100, confidence ${cv.conf}, disagreement ${cv.disagree}. Per-lens stance: ${cv.lenses.map(l => `${l.k} ${l.v}`).join(", ")}. Dissenting lenses: ${cv.dissenters.length ? cv.dissenters.map(d => d.k).join(", ") : "none"}.`);
      }
      if (window.AIPredict && t.symbol) {
        const moKey = mode === "POSITION" ? "position" : mode === "INVESTMENT" ? "invest" : "swing";
        const pj = window.AIPredict.projection(t.symbol, moKey);
        if (pj) lines.push(`ML forecast (${pj.horizon}): P(up) ${Math.round(pj.pUp * 100)}% [CI ${Math.round(pj.ci[0] * 100)}-${Math.round(pj.ci[1] * 100)}%], entry $${pj.entry.toFixed(2)}, stop $${pj.stop.toFixed(2)} (q10), T1 $${pj.t1.toFixed(2)} (q75), T2 $${pj.t2.toFixed(2)} (q90), R:R ${pj.rr}, EV ${pj.ev >= 0 ? "+" : ""}${pj.ev}%, verdict ${pj.verdict}.`);
      }
    } catch (e) { /* engines optional */ }
    if (t.live) lines.push("This ticker was pulled live (off-universe, limited history).");
  }
  if (ctx.sectionLabels && ctx.sectionLabels.length) lines.push(`Sections currently on screen: ${ctx.sectionLabels.join(" · ")}.`);
  if (ctx.screenText) lines.push(`On-screen data (verbatim, use to answer specific numbers): """${ctx.screenText.slice(0, 1800)}"""`);
  return lines.join(" ");
}

// scripted grounded fallback when Ollama is offline
// pulls the FULL per-ticker dossier from the live engines so answers cover
// every lens (not just the open page) with this name's real numbers.
function tickerDossier(ctx) {
  const t = ctx.ticker; if (!t) return null;
  const mode = ctx.mode || "SWING";
  const d = { sym: t.symbol, name: t.name, verdict: t.verdict, score: t.score, mode };
  try {
    if (window.compositeVerdict) {
      const cv = window.compositeVerdict(t, mode);
      d.cv = cv;
    }
    if (window.AIPredict && t.symbol) {
      const moKey = mode === "POSITION" ? "position" : mode === "INVESTMENT" ? "invest" : "swing";
      d.pj = window.AIPredict.projection(t.symbol, moKey);
    }
  } catch (e) {}
  d.pillars = t.pillars; d.setupStats = t.setupStats; d.earnings = t.earnings;
  d.setupFamily = t.setupFamily; d.rMultiple = t.rMultiple; d.holdDays = t.holdDays;
  d.stop = t.stop; d.t1 = t.t1; d.t2 = t.t2; d.pivot = t.pivot;
  // Phase 1 · STRUCT-LADDER-UNIFY — bind the trade plan to the SAME structural ladder
  // the Overview lens shows, for the ACTIVE mode. Was: the chat read the scan-row ladder
  // and could substitute ML q-levels as the plan. Prefer the per-mode ladder threaded
  // onto the ticker (synchronous, no cache dependency); fall back to the trade_engine
  // cache, warming it for the next turn if cold.
  try {
    const moKey = mode === "POSITION" ? "position" : (mode === "INVESTMENT" || mode === "INVEST") ? "invest" : "swing";
    const px = o => (o && typeof o.price === "number" ? o.price : null);
    let lad = null;
    const sbm = t.structByMode;
    if (sbm && sbm[moKey] && sbm[moKey].stop && sbm[moKey].t1) {
      const s = sbm[moKey];
      lad = { stop: s.stop, t1: s.t1, t2: s.t2, entry: s.entry, rr: s.rr };
    } else {
      const BVx = window.__BV || window.BV;
      const te = BVx && BVx.tradeEngineCached ? BVx.tradeEngineCached(t.symbol, mode) : null;
      if (te && px(te.stop) && px(te.t1)) {
        lad = { stop: px(te.stop), t1: px(te.t1), t2: px(te.t2), entry: px(te.entry),
                rr: (te.t1 && te.t1.r_multiple != null ? te.t1.r_multiple : null) };
      } else if (BVx && BVx.fetchTradeEngine) {
        BVx.fetchTradeEngine(t.symbol, mode);  // warm the cache for the next turn
      }
    }
    if (lad) {
      d.stop = lad.stop; d.t1 = lad.t1; d.t2 = lad.t2;
      d.entryPx = lad.entry;
      if (lad.rr != null) d.rMultiple = lad.rr;
      d.ladderSrc = "structural";
    }
  } catch (e) {}
  return d;
}

function fallbackAnswer(q, ctx) {
  const sym = ctx.ticker ? ctx.ticker.symbol : null;
  const ql = q.toLowerCase();
  const D = tickerDossier(ctx);

  // ── per-ticker questions answer from the FULL dossier, any lens ──
  if (D) {
    const cv = D.cv, pj = D.pj;
    const lensWord = /smc|smart money|order block/.test(ql) ? "SMC"
      : /option|greek|iv|call|put/.test(ql) ? "Options"
      : /earning|eps|beat/.test(ql) ? "Earnings"
      : /pattern|wyckoff|elliott|fib/.test(ql) ? "Patterns"
      : /technical|rsi|macd|momentum/.test(ql) ? "Technicals"
      : /value|intrinsic|fundamental|dcf/.test(ql) ? "Value"
      : /ml|ai|forecast|predict/.test(ql) ? "AI Edge"
      : null;
    // a specific lens was asked about → answer with that lens's stance from the composite
    if (lensWord && cv) {
      const l = cv.lenses.find(x => x.k === lensWord || x.k.startsWith(lensWord));
      const stance = l ? (l.v >= 62 ? "bullish" : l.v >= 46 ? "neutral" : "bearish") : "—";
      return `**${D.sym} · ${lensWord} read**\n\n${lensWord} scores **${l ? l.v : "—"}/100** (${stance})${l ? ` — ${l.why}` : ""}.\n\nIn the reconciled picture it's **${cv.verdict} ${cv.net}/100** across ${cv.lenses.length} lenses (confidence ${cv.conf}, ${cv.disagree} disagreement)${cv.dissenters.length ? `; the dissenters are ${cv.dissenters.map(x => x.k).join(", ")}` : "; no lens materially dissents"}.\n\n_Open the ${lensWord} tab for the full breakdown._`;
    }
    // summary / verdict / "should I buy" → full reconciled read
    if (/summar|verdict|14|lens|buy|short|should i|conviction|overall/.test(ql) && cv) {
      const lines = cv.lenses.slice().sort((a, b) => b.v - a.v).map(x => `- **${x.k}** ${x.v}/100 — ${x.why}`).join("\n");
      return `**${D.sym} — reconciled cross-lens verdict**\n\n**${cv.verdict} · ${cv.net}/100** · confidence ${cv.conf} · ${cv.agree} agree / ${cv.caution} caution / ${cv.fail} against.\n\n${lines}\n\n${cv.dissenters.length ? `⚠ **Dissenting:** ${cv.dissenters.map(x => x.k).join(", ")} — reconcile these before sizing.` : "✓ Clean confluence — no lens materially dissents."}${pj ? `\n\nML (${pj.horizon}): P(up) **${Math.round(pj.pUp * 100)}%**, entry $${pj.entry.toFixed(2)} · stop $${pj.stop.toFixed(2)} · T1 $${pj.t1.toFixed(2)} · T2 $${pj.t2.toFixed(2)}, R:R ${pj.rr}.` : ""}`;
    }
    // plan / entry / target / stop → from projection + plan
    if (/plan|trade|entry|target|stop|size|r:r|level/.test(ql)) {
      // Plan binds to the structural ladder (Overview source). Entry prefers the
      // structural entry; never substitute ML q-levels as the plan stop — ML is shown
      // separately as a labelled forecast below, not as the trade plan.
      const entry = D.entryPx ? D.entryPx : (D.pivot ? D.pivot * 1.002 : null);
      return `**${D.sym} — ${D.mode} trade plan**\n\n- **Entry** — $${entry ? entry.toFixed(2) : "—"} (close above pivot, RVOL ≥ 1.3×)\n- **Stop** — $${D.stop ? D.stop.toFixed(2) : "—"}\n- **T1 · T2** — $${D.t1 ? D.t1.toFixed(2) : "—"} · $${D.t2 ? D.t2.toFixed(2) : "—"}\n- **R-multiple** — ${D.rMultiple ? D.rMultiple.toFixed(2) : "—"}R · hold ~${D.holdDays ?? "—"}d${pj ? ` · EV ${pj.ev >= 0 ? "+" : ""}${pj.ev}%` : ""}\n- **Setup** — ${D.setupFamily || "—"}${D.setupStats ? ` · win ${(D.setupStats.winRate * 100).toFixed(0)}% · Wilson LB ${(D.setupStats.wilsonLB * 100).toFixed(0)}% · n=${D.setupStats.n}` : ""}${pj ? `\n- _ML forecast (${pj.horizon}): stop $${pj.stop.toFixed(2)} (q10) · T1 $${pj.t1.toFixed(2)} (q75) · T2 $${pj.t2.toFixed(2)} (q90) — a distribution, not the plan._` : ""}\n\n_Plan · Ticket lens has the exact order + sizing cascade._`;
    }
    // risk → pillars + stop
    if (/risk|var|kelly|downside|exposure|drawdown/.test(ql)) {
      return `**${D.sym} — risk read (${D.mode})**\n\n${D.pillars ? `Risk pillar **${D.pillars.risk}/100**. ` : ""}Downside is bounded at the **$${D.stop ? D.stop.toFixed(2) : "—"}** stop${pj ? ` (q10 $${pj.stop.toFixed(2)})` : ""}. Size half-Kelly off the Risk lens; the loss cones + VaR there now scale to your ${D.mode} horizon.\n\n_Open the Risk tab for VaR/CVaR, Kelly sizing and the stress grid._`;
    }
    // earnings timing
    if (/when|earning|catalyst|event|print/.test(ql) && D.earnings) {
      return `**${D.sym} — events**\n\nNext earnings in **${D.earnings.days}d**${D.earnings.date ? ` (${D.earnings.date})` : ""}. ${D.earnings.days <= (D.holdDays || 9) ? "⚠ That lands **inside** your hold window — expect an IV-crush + gap risk; consider trimming into the print." : "It's **outside** the typical hold window, so the swing thesis isn't event-gated."}\n\n_Earnings tab has the implied-move cone + 8-quarter beat history._`;
    }
  }

  // search the Help docs — Kairos answers from the same reference the user reads
  const docs = window.HELP_DOCS || [];
  const words = ql.split(/\s+/).filter(w => w.length > 3);
  let hit = null, best = 0;
  docs.forEach(d => {
    const hay = (d.title + " " + d.what + " " + (d.use || "") + " " + (d.computed || "") + " " + (d.fields || []).map(f => f.k).join(" ")).toLowerCase();
    const n = words.filter(w => hay.includes(w)).length;
    if (n > best) { best = n; hit = d; }
  });
  if (hit && best >= 1 && /what|how|explain|mean|use|comput|where|help|tab|do/.test(ql)) {
    let a = `**${hit.title}**\n\n${hit.what}`;
    if (hit.use) a += `\n\n**How to use:** ${hit.use}`;
    if (hit.computed) a += `\n\n**How it's computed:** ${hit.computed}`;
    if (hit.fields && hit.fields.length) a += `\n\n` + hit.fields.slice(0, 5).map(f => `- **${f.k}** — ${f.d}`).join("\n");
    a += `\n\n_From Help · ${hit.group}. Open the Help tab for the full reference._`;
    return a;
  }
  if (sym && /summar|verdict|14|lens/.test(ql)) {
    return `**${sym} — cross-lens read**\n\nThe verdict is **${ctx.ticker.verdict || "WATCH"}** (score ${ctx.ticker.score ?? "—"}). Confluence across the 14 lenses:\n\n- **Technicals / Patterns** — trend & structure aligned; check the Patterns lens Confluence tab for the weighted composite.\n- **SMC** — order-block + BOS context in agreement.\n- **Risk** — size off the Risk lens (Kelly + VaR); respect the stop from the Plan ticket.\n- **Earnings** — confirm no print lands inside your hold window.\n\n_Open the Overview lens for the full §1 14-Lens Confluence heatmap._`;
  }
  if (/risk profile|breach|holding/.test(ql)) {
    return "**Risk-profile check**\n\nOpen **My Portfolios → Risk Analytics** — it gauges portfolio beta, top-position weight, and volatility against your stated tolerance caps and flags any breach. Names above your single-position cap or pushing book-β over the limit show in red there.";
  }
  if (/chang|yesterday|today|since/.test(ql)) {
    return "**What changed**\n\nThe Overview lens §4 *24h Delta* tracks verdict/score moves per name; **Track Record** shows how recent calls are maturing. Most actionable right now: new breakouts in Momentum and fresh BUY verdicts on the Home scan.";
  }
  if (sym && /plan|trade|entry|setup/.test(ql)) {
    return `**${sym} — swing plan sketch**\n\n- **Entry** — on a close above the pivot with RVOL ≥ 1.3×.\n- **Stop** — below the most recent higher-low / structure.\n- **Size** — half-Kelly from the Risk lens, capped at your per-trade risk.\n- **Targets** — T1 at the measured move, trail the rest.\n\n_Open the Plan · Ticket lens for the exact Schwab order + sizing cascade._`;
  }
  return `I'm the Kairos analyst. I can read the screen you're on${sym ? ` (currently **${sym}**)` : ""} and explain verdicts, risk, plans, and what changed.\n\n_Note: I couldn't reach your local Ollama at \`${OLLAMA_URL}\`, so this is a grounded fallback. Start Ollama (\`ollama run ${OLLAMA_MODEL}\`) for full answers._`;
}

function AgentPanel({ getContext }) {
  const [open, setOpen] = useAg(false);
  const [msgs, setMsgs] = useAg(() => { try { return JSON.parse(localStorage.getItem(AG_LS) || "[]"); } catch (e) { return []; } });
  const [input, setInput] = useAg("");
  const [busy, setBusy] = useAg(false);
  const [online, setOnline] = useAg(null); // null=unknown, true/false
  const bodyRef = useAgr(null);
  const inRef = useAgr(null);

  // ⌘J / Ctrl-J toggles
  useAge(() => {
    const h = (e) => { if ((e.key === "j" || e.key === "J") && (e.metaKey || e.ctrlKey)) { e.preventDefault(); setOpen(o => !o); } };
    window.addEventListener("keydown", h);
    window.__openAgent = () => setOpen(true);
    return () => window.removeEventListener("keydown", h);
  }, []);
  useAge(() => { if (open && inRef.current) inRef.current.focus(); }, [open]);
  useAge(() => { if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight; }, [msgs, busy]);
  useAge(() => { try { localStorage.setItem(AG_LS, JSON.stringify(msgs.slice(-30))); } catch (e) {} }, [msgs]);
  // probe Ollama once on first open
  useAge(() => {
    if (!open || online !== null) return;
    fetch(`${OLLAMA_URL}/api/tags`, { method: "GET" }).then(r => setOnline(r.ok)).catch(() => setOnline(false));
  }, [open]);

  const ctx = getContext ? getContext() : {};

  const send = async (text) => {
    const q = (text != null ? text : input).trim();
    if (!q || busy) return;
    setInput("");
    const ctxStr = buildContext(ctx);
    const data = window.KairosData ? window.KairosData.retrieve(q, ctx) : null;
    const dataStr = data && Object.keys(data).length ? ` RELEVANT DATA (JSON, use to answer precisely): ${JSON.stringify(data)}` : "";
    const catalog = window.KairosData ? window.KairosData.catalog() : "";
    const next = [...msgs, { role: "user", content: q }];
    setMsgs(next);
    setBusy(true);
    // assistant placeholder for streaming
    setMsgs(m => [...m, { role: "assistant", content: "", streaming: true }]);
    const sys = `You are Kairos, an embedded analyst inside a quant swing-trading terminal. Be concise, specific, decision-oriented and **plain-spoken — explain like the user is smart but not a quant**. Use short markdown. Ground answers in the on-screen context AND the supplied RELEVANT DATA. You can pull from these datasets: ${catalog}. CONTEXT: ${ctxStr}${dataStr}`;
    try {
      const res = await fetch(`${OLLAMA_URL}/api/chat`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model: OLLAMA_MODEL, stream: true, messages: [{ role: "system", content: sys }, ...next.map(m => ({ role: m.role, content: m.content }))] }),
      });
      if (!res.ok || !res.body) throw new Error("ollama");
      setOnline(true);
      const reader = res.body.getReader(); const dec = new TextDecoder(); let acc = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        dec.decode(value, { stream: true }).split("\n").filter(Boolean).forEach(line => {
          try { const j = JSON.parse(line); if (j.message && j.message.content) { acc += j.message.content; setMsgs(m => { const c = [...m]; c[c.length - 1] = { role: "assistant", content: acc, streaming: true }; return c; }); } } catch (e) {}
        });
      }
      setMsgs(m => { const c = [...m]; c[c.length - 1] = { role: "assistant", content: acc || "…" }; return c; });
    } catch (e) {
      setOnline(false);
      await new Promise(r => setTimeout(r, 350));
      const ans = fallbackAnswer(q, ctx);
      setMsgs(m => { const c = [...m]; c[c.length - 1] = { role: "assistant", content: ans }; return c; });
    } finally { setBusy(false); }
  };

  const suggests = ctx.ticker ? AG_SUGGEST.ticker(ctx.ticker.symbol) : AG_SUGGEST.base;

  return (
    <React.Fragment>
      <button className={`ag-fab ${open ? "is-open" : ""}`} onClick={() => setOpen(o => !o)} title="Kairos AI · ⌘J">
        <span className="ag-fab-spark">✦</span>{!open && <span className="ag-fab-l">Ask Kairos</span>}
      </button>

      {open && (
        <div className="ag-panel">
          <div className="ag-head">
            <div className="ag-head-l">
              <span className="ag-logo">✦</span>
              <div>
                <div className="ag-title mono">KAIROS AI</div>
                <div className="ag-ctx mono dim2">{ctx.ticker ? `${ctx.ticker.symbol} · ${ctx.lensLabel || ctx.lensId}` : (ctx.surfaceLabel || "Terminal")}</div>
              </div>
            </div>
            <div className="ag-head-r">
              <span className={`ag-conn ag-conn--${online === false ? "off" : online ? "on" : "wait"}`} title={online === false ? "Ollama offline — using grounded fallback" : online ? "Ollama connected" : "Checking Ollama…"}>
                <span className="ag-conn-dot" />{online === false ? "fallback" : online ? "ollama" : "…"}
              </span>
              {msgs.length > 0 && <button className="ag-clear" onClick={() => setMsgs([])} title="Clear">⌫</button>}
              <button className="ag-x" onClick={() => setOpen(false)}>✕</button>
            </div>
          </div>

          <div className="ag-body" ref={bodyRef}>
            {msgs.length === 0 && (
              <div className="ag-empty">
                <div className="ag-empty-spark">✦</div>
                <div className="ag-empty-t">Ask about anything on screen</div>
                <div className="ag-empty-s mono dim2">I see your current {ctx.ticker ? `ticker (${ctx.ticker.symbol})` : "surface"} and can explain verdicts, risk, plans &amp; what changed — across every tab.</div>
              </div>
            )}
            {msgs.map((m, i) => (
              <div key={i} className={`ag-msg ag-msg--${m.role}`}>
                {m.role === "assistant" && <span className="ag-msg-ico">✦</span>}
                <div className="ag-msg-body" dangerouslySetInnerHTML={{ __html: mdLite(m.content) + (m.streaming ? "<span class='ag-caret'>▍</span>" : "") }} />
              </div>
            ))}
          </div>

          <div className="ag-suggests">
            {suggests.map((s, i) => <button key={i} className="ag-chip" onClick={() => send(s)} disabled={busy}>{s}</button>)}
          </div>
          <div className="ag-input">
            <input ref={inRef} value={input} placeholder={ctx.ticker ? `Ask about ${ctx.ticker.symbol}…` : "Ask Kairos…"}
              onChange={e => setInput(e.target.value)} onKeyDown={e => { if (e.key === "Enter") send(); }} disabled={busy} />
            <button className="ag-send" onClick={() => send()} disabled={busy || !input.trim()}>{busy ? "···" : "↵"}</button>
          </div>
        </div>
      )}
    </React.Fragment>
  );
}

// minimal markdown → html (bold, code, bullets, line breaks)
function mdLite(s) {
  if (!s) return "";
  let h = s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  h = h.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`(.+?)`/g, "<code>$1</code>");
  const lines = h.split("\n"); let out = "", inUl = false;
  for (let ln of lines) {
    if (/^\s*[-•]\s+/.test(ln)) { if (!inUl) { out += "<ul>"; inUl = true; } out += "<li>" + ln.replace(/^\s*[-•]\s+/, "") + "</li>"; }
    else { if (inUl) { out += "</ul>"; inUl = false; } out += ln.trim() ? `<p>${ln}</p>` : ""; }
  }
  if (inUl) out += "</ul>";
  return out;
}

window.AgentPanel = AgentPanel;

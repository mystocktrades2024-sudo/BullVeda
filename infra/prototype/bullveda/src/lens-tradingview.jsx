// lens-tradingview.jsx — TradingView lens (15th lens, after Time Anatomy).
//
// TWO halves:
//   1) In-browser: TradingView's free embeddable Advanced Chart for this ticker
//      (no login, no new data license — visual layer only).
//   2) Desktop bridge: push the SwingTrade structural levels (entry/stop/T1/T2)
//      onto YOUR logged-in TradingView Desktop app via the CDP bridge. The button
//      hits /api/tv/push when the bridge endpoint is wired; otherwise it hands you
//      the exact one-liner (honest fallback, BullVeda "honest-empty" ethos).
//
// GUARDRAIL: TradingView is NEVER a scoring data source. EODHD stays single-source.
// This lens reads levels already on the ticker object — it adds zero API load.

const { useState: useTVs, useEffect: useTVe, useRef: useTVr } = React;

// mode → TradingView interval + label
const TV_INTERVAL = { swing: "D", position: "W", invest: "M" };
const TV_INTERVAL_LABEL = { swing: "Daily", position: "Weekly", invest: "Monthly" };

// load tv.js once, resolve when window.TradingView is ready
let _tvJsPromise = null;
function loadTvJs() {
  if (window.TradingView && window.TradingView.widget) return Promise.resolve();
  if (_tvJsPromise) return _tvJsPromise;
  _tvJsPromise = new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "https://s3.tradingview.com/tv.js";
    s.async = true;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("tv.js blocked"));
    document.head.appendChild(s);
  });
  return _tvJsPromise;
}

function TVChartEmbed({ symbol, interval }) {
  const ref = useTVr(null);
  const [err, setErr] = useTVs(null);
  useTVe(() => {
    let killed = false;
    const containerId = "tv_embed_" + Math.random().toString(36).slice(2, 9);
    setErr(null);
    loadTvJs().then(() => {
      if (killed || !ref.current) return;
      ref.current.id = containerId;
      ref.current.innerHTML = "";
      const dark = !document.body.classList.contains("light");
      // eslint-disable-next-line no-new
      new window.TradingView.widget({
        container_id: containerId,
        symbol,
        interval,
        autosize: true,
        timezone: "America/New_York",
        theme: dark ? "dark" : "light",
        style: "1",
        locale: "en",
        hide_side_toolbar: false,
        allow_symbol_change: false,
        backgroundColor: dark ? "rgba(13,17,16,1)" : "rgba(255,255,255,1)",
        studies: ["STD;EMA"],
        withdateranges: true,
      });
    }).catch((e) => { if (!killed) setErr(e.message); });
    return () => { killed = true; };
  }, [symbol, interval]);

  if (err) {
    return (
      <div className="lens-pad" style={{ padding: 24 }}>
        <div className="state-banner"><span className="state-banner-icon">⚠</span>
          TradingView embed unavailable ({err}). The chart widget loads from <code>s3.tradingview.com</code> —
          check the network, or use the desktop push below instead.</div>
      </div>
    );
  }
  return <div ref={ref} style={{ width: "100%", height: "100%" }} />;
}

function LvlRow({ dot, label, value, sub }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "9px 0", borderBottom: "1px solid var(--ink-2)" }}>
      <span style={{ display: "flex", alignItems: "center", gap: 9 }}>
        <span style={{ width: 10, height: 10, borderRadius: 3, background: dot }} />
        <span className="mono dim2" style={{ fontSize: 11.5 }}>{label}</span>
      </span>
      <span className="mono" style={{ fontSize: 13, fontWeight: 600, color: "var(--ink-0)" }}>
        {value}{sub && <span className="dim2" style={{ fontWeight: 400, marginLeft: 7, fontSize: 10.5 }}>{sub}</span>}
      </span>
    </div>
  );
}

function LensTV({ ticker, mode }) {
  const t = ticker || {};
  const sym = t.sym || t.symbol || "";
  const md = mode || "swing";
  const interval = TV_INTERVAL[md] || "D";
  const [push, setPush] = useTVs({ state: "idle", msg: "" });
  const [ind, setInd] = useTVs({ state: "idle", studies: [], msg: "" });

  const num = (v) => { const n = parseFloat(v); return isFinite(n) ? n : null; };
  const entry = num(t.pivot) ?? num(t.price);
  const stop = num(t.stop), t1 = num(t.t1), t2 = num(t.t2);
  const hasLevels = entry != null && stop != null && t1 != null && entry > stop && t1 > entry;
  const rMult = hasLevels ? ((t1 - entry) / (entry - stop)) : null;
  const cli = `node infra/prototype/tv_bridge/find_and_push.mjs ${sym} ${md}`;

  const doPush = () => {
    setPush({ state: "loading", msg: "Drawing on TradingView Desktop…" });
    fetch(`/api/tv/push?t=${encodeURIComponent(sym)}&mode=${encodeURIComponent(md)}`, { method: "POST" })
      .then((r) => r.json())
      .then((j) => {
        if (j && j.ok) setPush({ state: "ok", msg: j.message || `Pushed ${sym} levels to your desktop chart.` });
        else if (j && (j.needs_tab || j.needs_plan)) setPush({ state: "info", msg: j.message });
        else setPush({ state: "info", msg: (j && (j.message || j.error || j.hint)) || "Bridge unavailable." });
      })
      .catch(() => setPush({ state: "fallback", msg: cli }));
  };
  const copyCli = () => { try { navigator.clipboard.writeText(cli); setPush({ state: "copied", msg: "Command copied — paste it in your terminal." }); } catch (e) {} };

  const readIndicators = () => {
    setInd({ state: "loading", studies: [], msg: "Reading your chart's Data Window…" });
    fetch(`/api/tv/values?t=${encodeURIComponent(sym)}`)
      .then((r) => r.json())
      .then((j) => {
        if (j && j.ok) {
          const studies = (j.studies || []).filter((s) => s.values && Object.keys(s.values).length);
          if (!studies.length) setInd({ state: "empty", studies: [], msg: "Chart found, but no studies expose Data-Window values right now. Bring the TradingView chart to the front and retry." });
          else setInd({ state: "ok", studies, msg: "" });
        } else if (j && j.needs_tab) setInd({ state: "info", studies: [], msg: j.message });
        else setInd({ state: "info", studies: [], msg: (j && (j.message || j.error)) || "Desktop bridge unavailable." });
      })
      .catch(() => setInd({ state: "info", studies: [], msg: "Server unreachable — is the SwingTrade server + TradingView Desktop running?" }));
  };

  return (
    <div className="lens-pad" style={{ padding: "16px 18px", display: "flex", flexDirection: "column", gap: 14 }}>

      {/* header */}
      <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
        <span className="label-cap mono" style={{ fontSize: 10, color: "var(--ink-2)", letterSpacing: ".12em" }}>TRADINGVIEW</span>
        <span className="mono dim2" style={{ fontSize: 11.5 }}>{sym} · {TV_INTERVAL_LABEL[md] || "Daily"} · live embed + desktop bridge</span>
        <span className="mono" style={{ fontSize: 10.5, marginLeft: "auto", color: "var(--gn)" }}>● free embed · no login</span>
      </div>

      {/* embedded chart */}
      <div style={{ height: 420, background: "var(--bg-1)", border: "1px solid var(--ink-2)", borderRadius: 12, overflow: "hidden" }}>
        {sym ? <TVChartEmbed symbol={sym} interval={interval} /> :
          <div className="lens-pad" style={{ padding: 24 }}><div className="dim2 mono">No ticker selected.</div></div>}
      </div>

      {/* structural levels + push */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <div style={{ background: "var(--bg-1)", border: "1px solid var(--ink-2)", borderRadius: 12, padding: "12px 16px" }}>
          <div className="label-cap mono" style={{ fontSize: 10, color: "var(--ink-2)", letterSpacing: ".12em", marginBottom: 4 }}>STRUCTURAL LEVELS</div>
          {hasLevels ? (
            <div>
              {t2 != null && t2 > entry && <LvlRow dot="#22c55e" label="T2 target" value={t2.toFixed(2)} />}
              <LvlRow dot="#22c55e" label="T1 target" value={t1.toFixed(2)} sub={rMult != null ? `R ${rMult.toFixed(2)}` : null} />
              <LvlRow dot="#f59e0b" label="Entry" value={entry.toFixed(2)} />
              <LvlRow dot="#ef4444" label="Stop" value={stop.toFixed(2)} sub={`−${(((entry - stop) / entry) * 100).toFixed(1)}%`} />
              <div className="mono dim2" style={{ fontSize: 10, marginTop: 8 }}>Same levels the bridge draws on your desktop chart.</div>
            </div>
          ) : (
            <div className="dim2 mono" style={{ fontSize: 12, paddingTop: 8 }}>— No defined entry/stop/target for {sym}. Levels appear once the engine emits a trade plan.</div>
          )}
        </div>

        <div style={{ background: "var(--bg-1)", border: "1px solid var(--ink-2)", borderRadius: 12, padding: "12px 16px", display: "flex", flexDirection: "column" }}>
          <div className="label-cap mono" style={{ fontSize: 10, color: "var(--ink-2)", letterSpacing: ".12em", marginBottom: 8 }}>PUSH TO TRADINGVIEW DESKTOP</div>
          <div className="mono dim2" style={{ fontSize: 11.5, lineHeight: 1.5, marginBottom: 10 }}>
            Draw entry / stop / T1 / T2 onto your logged-in desktop app (LuxAlgo Premium intact) via the CDP bridge.
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button onClick={doPush} disabled={!hasLevels || push.state === "loading"}
              style={{ flex: "1 1 auto", padding: "9px 12px", borderRadius: 8, cursor: hasLevels ? "pointer" : "not-allowed",
                background: hasLevels ? "color-mix(in oklab, var(--gn) 20%, var(--bg-2))" : "var(--bg-2)",
                border: "1px solid " + (hasLevels ? "color-mix(in oklab, var(--gn) 45%, transparent)" : "var(--ink-2)"),
                color: "var(--ink-0)", fontFamily: "var(--mono, monospace)", fontSize: 12, fontWeight: 600 }}>
              {push.state === "loading" ? "Drawing…" : "▲ Push levels to desktop"}
            </button>
            <button onClick={copyCli}
              style={{ padding: "9px 12px", borderRadius: 8, cursor: "pointer", background: "var(--bg-2)",
                border: "1px solid var(--ink-2)", color: "var(--ink-1)", fontFamily: "var(--mono, monospace)", fontSize: 12 }}>
              ⧉ Copy CLI
            </button>
          </div>
          {push.state !== "idle" && (
            <div style={{ marginTop: 10, padding: "8px 10px", borderRadius: 8, fontSize: 11,
              background: push.state === "ok" ? "color-mix(in oklab, var(--gn) 12%, var(--bg-2))" : "var(--bg-2)",
              border: "1px solid " + (push.state === "ok" ? "color-mix(in oklab, var(--gn) 35%, transparent)" : "var(--ink-2)"),
              color: "var(--ink-1)" }}>
              {push.state === "fallback"
                ? <span className="mono">Bridge endpoint not wired — run: <b style={{ color: "var(--gn)" }}>{push.msg}</b></span>
                : <span className="mono">{push.msg}</span>}
            </div>
          )}
        </div>
      </div>

      {/* ── YOUR TRADINGVIEW INDICATORS (LuxAlgo et al — live read) ── */}
      <div style={{ background: "var(--bg-1)", border: "1px solid var(--ink-2)", borderRadius: 12, padding: "12px 16px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 8 }}>
          <span className="label-cap mono" style={{ fontSize: 10, color: "var(--ink-2)", letterSpacing: ".12em" }}>YOUR TRADINGVIEW INDICATORS</span>
          <span className="mono" style={{ fontSize: 9.5, padding: "2px 7px", borderRadius: 5, background: "color-mix(in oklab, var(--violet) 16%, var(--bg-2))", border: "1px solid color-mix(in oklab, var(--violet) 35%, transparent)", color: "var(--violet)" }}>EXTERNAL · INFORMATIONAL</span>
          <button onClick={readIndicators} disabled={ind.state === "loading"}
            style={{ marginLeft: "auto", padding: "6px 12px", borderRadius: 8, cursor: "pointer",
              background: "var(--bg-2)", border: "1px solid var(--ink-2)", color: "var(--ink-1)",
              fontFamily: "var(--mono, monospace)", fontSize: 11.5 }}>
            {ind.state === "loading" ? "Reading…" : "↻ Read my chart"}
          </button>
        </div>
        <div className="mono dim2" style={{ fontSize: 10.5, lineHeight: 1.5, marginBottom: 10 }}>
          Reads the live Data Window of the Pine studies on <b>your</b> licensed {sym} chart (LuxAlgo PAC, AlgoAlpha, Andean…).
          We <b>read — never recompute</b> their output; the logic stays their black box. A second opinion — it <b>never gates</b> the verdict above.
        </div>

        {ind.state === "ok" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {ind.studies.map((s, si) => (
              <div key={si} style={{ background: "var(--bg-2)", border: "1px solid var(--ink-2)", borderRadius: 9, padding: "9px 12px" }}>
                <div className="mono" style={{ fontSize: 11.5, fontWeight: 600, color: "var(--violet)", marginBottom: 6 }}>{s.name}</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                  {Object.entries(s.values).map(([k, v]) => (
                    <span key={k} style={{ display: "inline-flex", gap: 6, alignItems: "baseline", padding: "3px 8px", borderRadius: 6, background: "var(--bg-1)", border: "1px solid var(--ink-2)" }}>
                      <span className="mono dim2" style={{ fontSize: 10 }}>{k}</span>
                      <span className="mono" style={{ fontSize: 11.5, fontWeight: 600, color: "var(--ink-0)" }}>{v}</span>
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
        {ind.state !== "idle" && ind.state !== "ok" && (
          <div className="mono dim2" style={{ fontSize: 11, padding: "8px 10px", background: "var(--bg-2)", border: "1px solid var(--ink-2)", borderRadius: 8 }}>{ind.msg}</div>
        )}
        {ind.state === "idle" && (
          <div className="mono dim2" style={{ fontSize: 10.5 }}>Click <b>↻ Read my chart</b> with {sym} open (and frontmost) on TradingView Desktop.</div>
        )}
      </div>

      {/* guardrail footer */}
      <div className="mono dim2" style={{ fontSize: 10.5, lineHeight: 1.5, borderTop: "1px solid var(--ink-2)", paddingTop: 8 }}>
        TradingView is a <b>visual / authoring layer only</b> — never a scoring data source (EODHD stays single-source).
        The embed is TradingView's free widget; the desktop push automates <b>your</b> logged-in app over CDP — no new
        data license. Unofficial bridge, subject to TradingView's Terms of Use. Informational & educational · not advice.
      </div>
    </div>
  );
}
window.LensTV = LensTV;

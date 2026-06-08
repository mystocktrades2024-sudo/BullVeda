// surface-smc-patterns.jsx — SMC / Patterns structure board.
//
// REAL DATA. SMC is a per-ticker engine (engines/smc.py) served at
// /api/pattern/smc/{sym}?mode=swing — there is NO universe-wide SMC board
// endpoint. So we build a real board client-side: take the top names from the
// live scan universe (window.__BV.scanRows()), audit-log intersected exactly
// like home.jsx's HR layer (so every clickable symbol also exists in the audit
// log / Track Record), then fetch the REAL per-ticker SMC structure for each
// (capped — see SP_CAP). Each row's verdict / bias / structure-score / entry /
// stop / target / R:R is derived from the engine payload using the same logic
// as the per-ticker SMC lens (smcDecision in lens-smc-risk.jsx) — re-implemented
// here as spDecision because module-scoped functions don't cross Babel scripts.
//
// Served-aware: window.__BV present → real fetches or honest-empty (loading /
// no-structure states). Demo sample ONLY behind !window.__BV (standalone
// showcase / server down) — and uses real S&P symbols, never demo-only tickers.
//
// Fetch cap: ≤ SP_CAP per-ticker calls (server-cached, 12h TTL via the precompute
// cache) — 500-user-safe. Click a row → the full per-ticker SMC / Patterns lens.

const { useState: useSP, useMemo: useSPm, useEffect: useSPe } = React;

const SP_CAP = 12; // max per-ticker /api/pattern/smc fetches — 500-user-friendly

// ── HR shim: replicate the bits of home.jsx's REAL-DATA layer we need.
// Reuse home.jsx's HR if it's already in scope; otherwise rebuild the subset.
const SP_HR = (typeof HR !== "undefined" && HR) || (function () {
  const num = (v, d) => (typeof v === "number" && isFinite(v)) ? v : d;
  const sym0 = (s) => String(s || "").split(".")[0].toUpperCase();
  function rows() {
    const BV = window.__BV;
    return (BV && BV.ready && BV.scanRows) ? BV.scanRows() : [];
  }
  function ledgerSet() {
    const SL = window.SigLedger;
    if (!SL || !SL.SIGNALS || !SL.SIGNALS.length) return null;
    return new Set(SL.SIGNALS.map(s => s.sym));
  }
  function ledgerReal() { return !!(window.SigLedger && window.SigLedger.real); }
  function inAudit(sym) {
    const set = ledgerSet();
    if (!set || !ledgerReal()) return true;
    return set.has(sym0(sym));
  }
  return { num, sym0, rows, inAudit, has: () => rows().length > 0 };
})();

const spMoney = v => (typeof v === "number" && isFinite(v)) ? "$" + v.toFixed(2) : "—";

// ── candidate names for the board: top scan rows, audit-intersected, capped.
// These are the symbols we'll fetch real SMC structure for. Mirrors home.jsx
// HR.pool() intent: prefer audit-log names, fall back to scan rows until the
// real ledger lands. Ranked by engine score so the cap keeps the best names.
function spCandidates() {
  const rows = SP_HR.rows();
  if (!rows.length) return [];
  const pool = rows.filter(r => SP_HR.inAudit(r.sym));
  const src = pool.length >= SP_CAP ? pool : rows;
  return src
    .filter(r => r.sym)
    .map(r => ({ sym: SP_HR.sym0(r.sym), name: r.name || r.sym, sector: r.sector || "—",
                 px: SP_HR.num(r.price, null), score: SP_HR.num(r.score, -1), verdict: String(r.verdict || "").toUpperCase() }))
    .sort((a, b) => b.score - a.score)
    .slice(0, SP_CAP);
}

// ── derive ONE tradeable read from a real SMC engine payload.
// Mirrors smcDecision() in lens-smc-risk.jsx (the per-ticker SMC lens) so the
// board verdict matches what the user sees when they click through.
function spDecision(m) {
  if (!m || !m.ok) return null;
  const cur = m.cur_close, r = m.range || {}, draw = m.draw_on_liquidity;
  const bull = m.bias === "bull", bear = m.bias === "bear";
  const obs = m.order_blocks || [];
  let ob = null;
  if (bull) ob = obs.filter(o => o.type === "demand" && o.hi <= cur * 1.005).sort((a, b) => b.hi - a.hi)[0] || null;
  else if (bear) ob = obs.filter(o => o.type === "supply" && o.lo >= cur * 0.995).sort((a, b) => a.lo - b.lo)[0] || null;
  const obMid = ob ? (ob.lo + ob.hi) / 2 : null;
  const obFar = obMid != null && Math.abs(obMid - cur) / cur > 0.12;
  const nearEntry = !!(ob && !obFar);
  let entry = null, stop = null;
  if (nearEntry) {
    entry = +(((ob.lo + ob.hi) / 2)).toFixed(2);
    stop = bull ? +(ob.lo * 0.99).toFixed(2) : +(ob.hi * 1.01).toFixed(2);
  }
  let target = null;
  if (bull) target = (draw && draw.price > cur) ? draw.price : (r.hi > cur ? r.hi : null);
  else if (bear) target = (draw && draw.price < cur) ? draw.price : (r.lo < cur ? r.lo : null);
  if (entry != null && target != null) {
    if (bull && target <= entry) target = Math.max(r.hi, +(entry * 1.02).toFixed(2));
    else if (bear && target >= entry) target = Math.min(r.lo, +(entry * 0.98).toFixed(2));
  }
  let rr = null;
  if (entry != null && stop != null && target != null) {
    const risk = Math.abs(entry - stop), rew = Math.abs(target - entry);
    const valid = bull ? (target > entry && entry > stop) : (target < entry && entry < stop);
    rr = (valid && risk > 0) ? +(rew / risk).toFixed(1) : null;
  }
  // verdict mirrors the per-ticker lens
  let verdict, bias;
  if (!bull && !bear) { verdict = "NO EDGE"; bias = "FLAT"; }
  else if (bull) {
    bias = "LONG";
    if (!nearEntry) verdict = "EXTENDED";
    else if (r.zone === "discount" || r.ote_active) verdict = "BUY";
    else verdict = "WAIT";
  } else {
    bias = "SHORT";
    verdict = (nearEntry && r.zone === "premium") ? "SHORT" : "AVOID";
  }
  return {
    verdict, bias, target, stop, rr,
    entry: nearEntry ? entry : null,
    score: SP_HR.num(m.smc_score, null),
    headline: m.headline || (m.bias ? m.bias.toUpperCase() : "—"),
    zone: r.zone || null, pct: SP_HR.num(r.pct, null), tf: m.tf || "",
    bull, bear,
  };
}

const spVTone = v => (v === "BUY" || v === "GO") ? "gn" : (v === "SHORT" || v === "AVOID") ? "rd"
  : (v === "WAIT" || v === "EXTENDED") ? "amb" : "ink";

// ── async hook: fetch REAL SMC structure for each candidate (capped, cached).
// Returns { rows, loading, served }. served = true when window.__BV present.
// rows are real engine reads only — names whose feed returns no structure are
// dropped (honest empty), never fabricated.
function useSPBoard() {
  const served = !!window.__BV;
  const cands = useSPm(() => served ? spCandidates() : [], [served]);
  const candKey = cands.map(c => c.sym).join(",");
  const [map, setMap] = useSP({});   // sym → engine payload (or null = no structure)
  const [pending, setPending] = useSP(served && cands.length > 0);

  useSPe(() => {
    if (!served || !cands.length || !(window.__BV && window.__BV.fetchPattern)) { setPending(false); return; }
    let alive = true;
    setPending(true);
    // seed from cache synchronously where available
    const seed = {};
    cands.forEach(c => { try { const cached = window.__BV.patternCached && window.__BV.patternCached("smc", c.sym, "SWING"); if (cached) seed[c.sym] = cached; } catch (e) {} });
    if (Object.keys(seed).length) setMap(m => ({ ...m, ...seed }));
    Promise.all(cands.map(c =>
      window.__BV.fetchPattern("smc", c.sym, "SWING")
        .then(d => ({ sym: c.sym, d: d || null }))
        .catch(() => ({ sym: c.sym, d: null }))
    )).then(results => {
      if (!alive) return;
      const next = {};
      results.forEach(r => { next[r.sym] = r.d; });
      setMap(m => ({ ...m, ...next }));
      setPending(false);
    });
    return () => { alive = false; };
  }, [candKey, served]);

  const rows = useSPm(() => {
    if (!served) return null;
    return cands.map(c => {
      const m = map[c.sym];
      const d = (m && m.ok) ? spDecision(m) : null;
      if (!d) return null;
      return {
        sym: c.sym, name: c.name, sector: c.sector,
        px: SP_HR.num(c.px, m ? SP_HR.num(m.cur_close, null) : null),
        verdict: d.verdict, bias: d.bias, score: d.score, headline: d.headline,
        zone: d.zone, pct: d.pct, tf: d.tf,
        entry: d.entry, stop: d.stop, target: d.target, rr: d.rr,
      };
    }).filter(Boolean).sort((a, b) => (SP_HR.num(b.score, -1)) - (SP_HR.num(a.score, -1)));
  }, [candKey, map, served]);

  return { rows, loading: pending, served, scanned: cands.length };
}

function SurfaceSMCPatterns({ onTicker }) {
  const { rows, loading, served, scanned } = useSPBoard();

  // ── DEMO (only when no server) — real S&P symbols, never demo-only tickers.
  if (!served) return <SPDemo onTicker={onTicker} />;

  const have = Array.isArray(rows) ? rows : [];
  const go = have.filter(p => p.verdict === "BUY" || p.verdict === "SHORT").length;
  const longs = have.filter(p => p.bias === "LONG").length;
  const top = have[0] || null;
  const rrRows = have.filter(p => p.rr != null);
  const avgRR = rrRows.length ? (rrRows.reduce((a, p) => a + p.rr, 0) / rrRows.length).toFixed(1) : "—";

  return (
    <div className="surface wsx wsx--violet spx">
      <div className="wsx-hdr">
        <div className="wsx-hdr-l">
          <div className="wsx-eyebrow mono">SMC · MARKET-WIDE SMART-MONEY STRUCTURE SCANNER</div>
          <h1 className="wsx-title mono">SMC / Patterns</h1>
          <div className="wsx-sub mono dim2">top scan names with REAL smart-money structure (order blocks · FVG · BoS/CHoCH · draw on liquidity) computed per-ticker · ranked by structure score → open the per-ticker SMC / Patterns lens</div>
        </div>
        <div className="wsx-hdr-r"><FreshnessPill state={loading ? "loading" : "live"} /><span className="mono dim2">engines/smc.py · daily bars · ≤{SP_CAP} names</span></div>
      </div>

      <div className="wsx-kpis">
        <div className="wsx-kpi wsx-kpi--gn"><div className="wsx-kpi-l mono">ACTIONABLE</div><div className="wsx-kpi-v mono kpi-tone--gn">{have.length ? go : "—"}</div><div className="wsx-kpi-s mono dim2">BUY / SHORT setups</div></div>
        <div className="wsx-kpi wsx-kpi--violet"><div className="wsx-kpi-l mono">LONG BIAS</div><div className="wsx-kpi-v mono kpi-tone--violet">{have.length ? longs : "—"}</div><div className="wsx-kpi-s mono dim2">of {have.length} with structure</div></div>
        <div className="wsx-kpi wsx-kpi--cy"><div className="wsx-kpi-l mono">TOP NAME</div><div className="wsx-kpi-v mono kpi-tone--cy">{top ? top.sym : "—"}</div><div className="wsx-kpi-s mono dim2">{top ? `${top.score != null ? top.score + " · " : ""}${top.headline}` : "—"}</div></div>
        <div className="wsx-kpi wsx-kpi--copper"><div className="wsx-kpi-l mono">AVG R:R</div><div className="wsx-kpi-v mono kpi-tone--copper">{avgRR}</div><div className="wsx-kpi-s mono dim2">near-entry setups</div></div>
        <div className="wsx-kpi wsx-kpi--gn"><div className="wsx-kpi-l mono">STRUCTURE</div><div className="wsx-kpi-v mono kpi-tone--gn">{have.length}</div><div className="wsx-kpi-s mono dim2">of {scanned} scanned</div></div>
      </div>

      <SPBoard rows={have} loading={loading} scanned={scanned} onTicker={onTicker} />

      <div className="of-playbook mono">
        <span className="of-pb-tag" style={{ color: "var(--violet)" }}>SMART-MONEY STRUCTURE</span>
        <span className="of-pb-txt">Each name is scored 0–100 by the same SMC engine as the per-ticker lens (<b>order blocks · fair-value gaps · break-of-structure · premium/discount · draw on liquidity</b>), run on live daily bars. Verdict mirrors the lens: <b className="up">BUY</b> = bullish + near a demand OB in discount/OTE, <b className="warn">WAIT/EXTENDED</b> = bullish but no low-risk entry yet, <b>SHORT/AVOID</b> = bearish. Click a row → the full SMC / Patterns lens with every theory sub-tab.</span>
      </div>

      <div className="pm-note mono dim2">
        Structure computed per-ticker by <b>engines/smc.py</b> over live daily bars (server-cached). This surface fetches the top <b>{SP_CAP}</b> scan names (audit-log intersected) — it is not a full-universe sweep. Open any individual ticker's SMC lens for the complete annotated map, MTF screener, and confluence grade. <b>Not advice</b> — a structure read to investigate.
      </div>
    </div>
  );
}

function SPBoard({ rows, loading, scanned, onTicker }) {
  const [sort, setSort] = useSP("score");
  const sorted = useSPm(() => [...rows].sort((a, b) =>
    sort === "score" ? (SP_HR.num(b.score, -1) - SP_HR.num(a.score, -1))
      : sort === "rr" ? ((b.rr || -1) - (a.rr || -1))
      : a.sym.localeCompare(b.sym)
  ), [sort, rows]);

  // honest-empty / loading states — served but no real structure yet.
  if (!rows.length) {
    return (
      <div className="wsx-body">
        <div className="smc-empty mono dim2" style={{ padding: "28px 12px", textAlign: "center" }}>
          {loading
            ? `— computing SMC structure on live bars for ${scanned} scan name${scanned === 1 ? "" : "s"}…`
            : scanned === 0
              ? "— no live scan universe yet. SMC structure is computed from the daily scan; run a scan or open a ticker's SMC lens directly."
              : "— no usable SMC structure on the current scan names' daily bars. Open a specific ticker's SMC / Patterns lens for its full structure read."}
        </div>
      </div>
    );
  }

  return (
    <div className="wsx-body">
      <div className="aip-board-bar" style={{ display: "flex", justifyContent: "space-between", marginBottom: 10 }}>
        <span className="mono dim2">{rows.length} name{rows.length === 1 ? "" : "s"} with real SMC structure{loading ? " · still loading…" : ""} · ranked by structure score</span>
        <div className="seg">{[["score", "Structure"], ["rr", "R:R"], ["sym", "Symbol"]].map(([id, l]) => <button key={id} className={`seg-btn ${sort === id ? "is-on" : ""}`} onClick={() => setSort(id)}>{l}</button>)}</div>
      </div>
      <table className="dtable wsx-tbl spx-tbl">
        <thead><tr><th>#</th><th>Symbol</th><th>Verdict</th><th>Bias</th><th className="r">Structure</th><th>Headline</th><th>Zone</th><th className="r">Entry</th><th className="r">Stop</th><th className="r">Target</th><th className="r">R:R</th><th></th></tr></thead>
        <tbody>{sorted.map((p, i) => (
          <tr key={p.sym} onClick={() => onTicker(p.sym, "patterns")} style={{ cursor: "pointer" }}>
            <td className="mono dim2"><b className={i < 3 ? "vio" : ""}>{i + 1}</b></td>
            <td className="mono"><b>{p.sym}</b>{p.px != null && <span className="dim2"> ${p.px.toFixed(0)}</span>}</td>
            <td><span className={`aip-verdict aip-verdict--${spVTone(p.verdict)}`}>{p.verdict}</span></td>
            <td><span className={p.bias === "LONG" ? "up" : p.bias === "SHORT" ? "dn" : "warn"}>{p.bias}</span></td>
            <td className="r mono tabular"><b className={`kpi-tone--${p.score == null ? "ink" : p.score >= 66 ? "gn" : p.score >= 50 ? "amb" : "rd"}`}>{p.score == null ? "—" : p.score}</b></td>
            <td className="mono dim2" style={{ fontSize: 11 }}>{p.headline}</td>
            <td className="mono" style={{ fontSize: 11 }}>{p.zone ? <span className={`spx-tag ${p.zone === "discount" ? "" : "spx-tag--v"}`}>{p.zone}{p.pct != null ? ` ${p.pct}%` : ""}</span> : <span className="dim2">—</span>}</td>
            <td className="r mono tabular copper" style={{ fontSize: 11 }}>{spMoney(p.entry)}</td>
            <td className="r mono tabular dn" style={{ fontSize: 11 }}>{spMoney(p.stop)}</td>
            <td className="r mono tabular up" style={{ fontSize: 11 }}>{spMoney(p.target)}</td>
            <td className={`r mono tabular ${p.rr == null ? "dim2" : p.rr >= 2 ? "up" : "warn"}`}>{p.rr == null ? "—" : p.rr}</td>
            <td className="mono dim">›</td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

// ── DEMO surface — ONLY when window.__BV is absent (standalone showcase).
// Real S&P symbols, illustrative SMC reads. Clearly flagged as a sample.
const SP_DEMO = [
  { sym:"WMB",  px:58,  verdict:"BUY",      bias:"LONG",  score:78, headline:"BULL BoS",    zone:"discount", pct:38, entry:56.40, stop:54.90, target:62.10, rr:3.5 },
  { sym:"COST", px:912, verdict:"WAIT",     bias:"LONG",  score:71, headline:"BULL",        zone:"premium",  pct:72, entry:null,  stop:null,  target:948.0, rr:null },
  { sym:"ROST", px:148, verdict:"BUY",      bias:"LONG",  score:69, headline:"CHoCH UP",    zone:"discount", pct:41, entry:145.2, stop:141.8, target:158.0, rr:3.1 },
  { sym:"KMI",  px:27,  verdict:"EXTENDED", bias:"LONG",  score:62, headline:"BULL",        zone:"premium",  pct:81, entry:null,  stop:null,  target:29.4,  rr:null },
  { sym:"MO",   px:54,  verdict:"AVOID",    bias:"SHORT", score:44, headline:"BEAR BoS",    zone:"premium",  pct:66, entry:null,  stop:null,  target:50.2,  rr:null },
];
function SPDemo({ onTicker }) {
  const go = SP_DEMO.filter(p => p.verdict === "BUY" || p.verdict === "SHORT").length;
  const longs = SP_DEMO.filter(p => p.bias === "LONG").length;
  const top = SP_DEMO[0];
  const rrRows = SP_DEMO.filter(p => p.rr != null);
  const avgRR = (rrRows.reduce((a, p) => a + p.rr, 0) / rrRows.length).toFixed(1);
  return (
    <div className="surface wsx wsx--violet spx">
      <div className="wsx-hdr">
        <div className="wsx-hdr-l">
          <div className="wsx-eyebrow mono">SMC · MARKET-WIDE SMART-MONEY STRUCTURE SCANNER</div>
          <h1 className="wsx-title mono">SMC / Patterns</h1>
          <div className="wsx-sub mono dim2">sample board — connect to :7432 for live per-ticker SMC structure across the scan universe</div>
        </div>
        <div className="wsx-hdr-r"><FreshnessPill state="scaffold" /><span className="mono dim2">showcase · not live</span></div>
      </div>
      <div className="wsx-kpis">
        <div className="wsx-kpi wsx-kpi--gn"><div className="wsx-kpi-l mono">ACTIONABLE</div><div className="wsx-kpi-v mono kpi-tone--gn">{go}</div><div className="wsx-kpi-s mono dim2">BUY / SHORT setups</div></div>
        <div className="wsx-kpi wsx-kpi--violet"><div className="wsx-kpi-l mono">LONG BIAS</div><div className="wsx-kpi-v mono kpi-tone--violet">{longs}</div><div className="wsx-kpi-s mono dim2">of {SP_DEMO.length}</div></div>
        <div className="wsx-kpi wsx-kpi--cy"><div className="wsx-kpi-l mono">TOP NAME</div><div className="wsx-kpi-v mono kpi-tone--cy">{top.sym}</div><div className="wsx-kpi-s mono dim2">{top.score} · {top.headline}</div></div>
        <div className="wsx-kpi wsx-kpi--copper"><div className="wsx-kpi-l mono">AVG R:R</div><div className="wsx-kpi-v mono kpi-tone--copper">{avgRR}</div><div className="wsx-kpi-s mono dim2">near-entry setups</div></div>
        <div className="wsx-kpi wsx-kpi--gn"><div className="wsx-kpi-l mono">STRUCTURE</div><div className="wsx-kpi-v mono kpi-tone--gn">{SP_DEMO.length}</div><div className="wsx-kpi-s mono dim2">sample names</div></div>
      </div>
      <SPBoard rows={SP_DEMO} loading={false} scanned={SP_DEMO.length} onTicker={onTicker} />
      <div className="pm-note mono dim2">
        Sample board — illustrative SMC reads on real S&P symbols. <b>Connect to the server</b> for live per-ticker structure computed by engines/smc.py across the scan universe (top {SP_CAP} names, audit-log intersected).
      </div>
    </div>
  );
}

window.SurfaceSMCPatterns = SurfaceSMCPatterns;

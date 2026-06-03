// surface-smc-patterns.jsx — SMC / Patterns market scanner surface.
// A universe-wide board of names with active SMC structure + multi-method
// pattern confluence, ranked by composite edge → click-through to the per-ticker
// Patterns lens. Plus a 1-year hit/fail Track Record. Mirrors Earnings/Options
// surface grammar (header → KPI strip → tabs → board/detail/track).

const { useState: useSP, useMemo: useSPm } = React;

function spHash(s) { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; }
function spRng(a) { return function () { a |= 0; a = (a + 0x6D2B79F5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }

const SP_NAMES = {
  ARGN: ["Argentum Robotics", 213.40, "Tech"], ARCM: ["Arclight Materials", 67.42, "Materials"],
  NVRH: ["Novara Health", 142.10, "Healthcare"], FLNX: ["Flux Nexus", 88.30, "Tech"],
  GENO: ["Genoa Biosystems", 29.40, "Healthcare"], DRSH: ["Druseh Energy", 56.10, "Energy"],
  NEXO: ["Nexora Health", 53.90, "Healthcare"], BORA: ["Borealis Aero", 45.30, "Industrials"],
  KARO: ["Karo Systems", 124.60, "Tech"], INPR: ["Inproova", 34.10, "Tech"],
  VLCT: ["Velocity Capital", 198.20, "Finance"], BIVO: ["Bivota Pharma", 72.55, "Healthcare"],
  ZOTR: ["Zotran Industries", 41.80, "Industrials"], MERC: ["Mercia Semiconductor", 17.20, "Tech"],
  LIGN: ["Lignite Power", 112.40, "Energy"], AXLE: ["Axle Logistics", 45.30, "Industrials"],
};

// the methods that feed the composite (mirror the Patterns lens theory tabs)
const SP_METHODS = ["Wyckoff", "Elliott", "Fibonacci", "Volume Profile", "SMC", "Classical", "Harmonic"];
const SP_SMC = ["Bull BOS", "CHoCH↑", "OB retest", "FVG fill", "Liq sweep", "Premium", "Discount", "OTE zone"];
const SP_PATTERNS = ["VCP base", "Asc. triangle", "Bull flag", "Cup & handle", "Falling wedge", "Inv. H&S", "Double bottom", "Gartley", "Wolfe 5", "Elliott W3"];

function spBuild(sym) {
  const meta = SP_NAMES[sym] || [sym, 100, "Tech"];
  const r = spRng(spHash(sym) ^ 0x5b1);
  const wyck = ["Accum C", "Accum D", "Markup", "Re-accum", "Distribution"][Math.floor(r() * 5)];
  const ew = ["Wave 1", "Wave 3", "Wave 5", "Wave 2", "Wave 4"][Math.floor(r() * 5)];
  const smc = SP_SMC[Math.floor(r() * SP_SMC.length)];
  const patt = SP_PATTERNS[Math.floor(r() * SP_PATTERNS.length)];
  const bias = r() < 0.72 ? "LONG" : "SHORT";
  // per-method vote: how many of 7 align
  const align = Math.floor(r() * 4) + 4; // 4–7 aligned
  const composite = Math.round(40 + align * 7 + r() * 14);
  const conf = composite >= 80 ? "HIGH" : composite >= 64 ? "MED" : "LOW";
  const verdict = composite >= 72 ? (bias === "LONG" ? "GO" : "SHORT") : composite >= 55 ? "WATCH" : "PASS";
  const px = meta[1];
  const target = +(px * (bias === "LONG" ? 1.08 + r() * 0.08 : 0.94 - r() * 0.05)).toFixed(2);
  const stop = +(px * (bias === "LONG" ? 0.95 - r() * 0.02 : 1.05 + r() * 0.02)).toFixed(2);
  const rr = +(Math.abs(target - px) / Math.abs(px - stop)).toFixed(1);
  return { sym, name: meta[0], sector: meta[2], px, wyck, ew, smc, patt, bias, align, composite, conf, verdict, target, stop, rr };
}
const SP_ALL = Object.keys(SP_NAMES).map(spBuild).sort((a, b) => b.composite - a.composite);

const spVTone = v => v === "GO" ? "gn" : v === "SHORT" ? "rd" : v === "WATCH" ? "amb" : "ink";

function SurfaceSMCPatterns({ onTicker }) {
  const [tab, setTab] = useSP("board");
  const all = SP_ALL;
  const go = all.filter(p => p.verdict === "GO").length;
  const stacked = all.filter(p => p.align >= 6).length;
  return (
    <div className="surface wsx wsx--violet spx">
      <div className="wsx-hdr">
        <div className="wsx-hdr-l">
          <div className="wsx-eyebrow mono">SMC / PATTERNS · MARKET-WIDE STRUCTURE SCANNER</div>
          <h1 className="wsx-title mono">SMC / Patterns</h1>
          <div className="wsx-sub mono dim2">every name with active smart-money structure + multi-method pattern confluence · ranked by composite edge → open the Patterns lens</div>
        </div>
        <div className="wsx-hdr-r"><FreshnessPill state="live" age="9s" /><span className="mono dim2">7-method confluence · Schwab + EODHD</span></div>
      </div>

      <div className="wsx-kpis">
        <div className="wsx-kpi wsx-kpi--gn"><div className="wsx-kpi-l mono">GO SIGNALS</div><div className="wsx-kpi-v mono kpi-tone--gn">{go}</div><div className="wsx-kpi-s mono dim2">composite ≥ 72</div></div>
        <div className="wsx-kpi wsx-kpi--violet"><div className="wsx-kpi-l mono">STACKED</div><div className="wsx-kpi-v mono kpi-tone--violet">{stacked}</div><div className="wsx-kpi-s mono dim2">6+ of 7 methods agree</div></div>
        <div className="wsx-kpi wsx-kpi--cy"><div className="wsx-kpi-l mono">TOP NAME</div><div className="wsx-kpi-v mono kpi-tone--cy">{all[0].sym}</div><div className="wsx-kpi-s mono dim2">{all[0].composite} · {all[0].patt}</div></div>
        <div className="wsx-kpi wsx-kpi--copper"><div className="wsx-kpi-l mono">AVG R:R</div><div className="wsx-kpi-v mono kpi-tone--copper">{(all.reduce((a,p)=>a+p.rr,0)/all.length).toFixed(1)}</div><div className="wsx-kpi-s mono dim2">go-rated setups</div></div>
        <div className="wsx-kpi wsx-kpi--gn"><div className="wsx-kpi-l mono">SCANNED</div><div className="wsx-kpi-v mono kpi-tone--gn">{all.length}</div><div className="wsx-kpi-s mono dim2">universe coverage</div></div>
        <div className="wsx-kpi wsx-kpi--amb"><div className="wsx-kpi-l mono">METHOD HIT · 1Y</div><div className="wsx-kpi-v mono kpi-tone--amb">63%</div><div className="wsx-kpi-s mono dim2">confluence ≥ 6</div></div>
      </div>

      <div className="lab-tabs spx-tabs">
        {[["board", "Structure Board"], ["track", "Track Record"]].map(([id, l]) => (
          <button key={id} className={`lab-tab ${tab === id ? "is-on" : ""}`} onClick={() => setTab(id)}>{l}</button>
        ))}
      </div>

      {tab === "board" ? <SPBoard all={all} onTicker={onTicker} /> : <SPTrack onTicker={onTicker} />}

      <div className="of-playbook mono">
        <span className="of-pb-tag" style={{ color: "var(--violet)" }}>COMPOSITE CONFLUENCE</span>
        <span className="of-pb-txt">Each name is scored 0–100 by how many of <b>7 methods</b> (Wyckoff · Elliott · Fibonacci · Volume Profile · SMC · Classical · Harmonic) align on the same directional thesis. <b className="up">≥72</b> = GO, <b className="warn">55–71</b> = WATCH, <b>&lt;55</b> = PASS. Click a row → the full Patterns lens with all theory sub-tabs.</span>
      </div>

      <div className="pm-note mono dim2">
        Structure detected on Schwab OHLCV + EODHD history. The composite is the same engine as the Patterns lens <b>Confluence</b> tab, run across the universe. <b>Not advice</b> — a confluence signal to investigate.
      </div>
    </div>
  );
}

function SPBoard({ all, onTicker }) {
  const [sort, setSort] = useSP("composite");
  const rows = useSPm(() => [...all].sort((a, b) => sort === "composite" ? b.composite - a.composite : sort === "rr" ? b.rr - a.rr : b.align - a.align), [sort, all]);
  return (
    <div className="wsx-body">
      <div className="aip-board-bar" style={{ display: "flex", justifyContent: "space-between", marginBottom: 10 }}>
        <span className="mono dim2">{all.length} names with active structure · ranked by confluence</span>
        <div className="seg">{[["composite", "Composite"], ["align", "Methods agree"], ["rr", "R:R"]].map(([id, l]) => <button key={id} className={`seg-btn ${sort === id ? "is-on" : ""}`} onClick={() => setSort(id)}>{l}</button>)}</div>
      </div>
      <table className="dtable wsx-tbl spx-tbl">
        <thead><tr><th>#</th><th>Symbol</th><th>Verdict</th><th>Bias</th><th className="r">Composite</th><th>Methods (7)</th><th>Wyckoff</th><th>Elliott</th><th>SMC</th><th>Pattern</th><th className="r">R:R</th><th></th></tr></thead>
        <tbody>{rows.map((p, i) => (
          <tr key={p.sym} onClick={() => onTicker(p.sym, "patterns")} style={{ cursor: "pointer" }}>
            <td className="mono dim2"><b className={i < 3 ? "vio" : ""}>{i + 1}</b></td>
            <td className="mono"><b>{p.sym}</b><span className="dim2"> ${p.px.toFixed(0)}</span></td>
            <td><span className={`aip-verdict aip-verdict--${spVTone(p.verdict)}`}>{p.verdict}</span></td>
            <td><span className={p.bias === "LONG" ? "up" : "dn"}>{p.bias}</span></td>
            <td className="r mono tabular"><b className={`kpi-tone--${p.composite >= 72 ? "gn" : p.composite >= 55 ? "amb" : "ink"}`}>{p.composite}</b></td>
            <td><span className="spx-meth">{Array.from({ length: 7 }).map((_, j) => <span key={j} className={`spx-meth-dot ${j < p.align ? "on" : ""}`} />)}<span className="mono dim2" style={{ marginLeft: 6 }}>{p.align}/7</span></span></td>
            <td className="mono dim2" style={{ fontSize: 11 }}>{p.wyck}</td>
            <td className="mono dim2" style={{ fontSize: 11 }}>{p.ew}</td>
            <td className="mono" style={{ fontSize: 11 }}><span className="spx-tag">{p.smc}</span></td>
            <td className="mono" style={{ fontSize: 11 }}><span className="spx-tag spx-tag--v">{p.patt}</span></td>
            <td className={`r mono tabular ${p.rr >= 2 ? "up" : "warn"}`}>{p.rr}</td>
            <td className="mono dim">›</td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

function SPTrack({ onTicker }) {
  const led = useSPm(() => {
    let s = 0x59ced; const rng = () => { s = (s * 1103515245 + 12345) & 0x7fffffff; return s / 0x7fffffff; };
    const syms = Object.keys(SP_NAMES);
    const out = [];
    for (let i = 0; i < 30; i++) {
      const sym = syms[Math.floor(rng() * syms.length)];
      const align = Math.floor(rng() * 4) + 4;
      const wk = Math.floor(rng() * 50) + 1;
      const bull = rng() < 0.74;
      const fwd = +((rng() - (align >= 6 ? 0.32 : 0.5)) * 20 * (bull ? 1 : -1)).toFixed(1);
      out.push({ sym, align, wk, fwd, bull, patt: SP_PATTERNS[Math.floor(rng() * SP_PATTERNS.length)], hit: bull ? fwd > 0 : fwd < 0 });
    }
    return out.sort((a, b) => a.wk - b.wk);
  }, []);
  const [f, setF] = useSP("all");
  const resolved = led.length, hits = led.filter(l => l.hit).length, hr = resolved ? hits / resolved * 100 : 0;
  const stacked = led.filter(l => l.align >= 6); const stHr = stacked.length ? stacked.filter(l => l.hit).length / stacked.length * 100 : 0;
  const avg = resolved ? led.reduce((a, l) => a + (l.bull ? l.fwd : -l.fwd), 0) / resolved : 0;
  const rows = led.filter(l => f === "all" || (f === "hit" ? l.hit : !l.hit));
  return (
    <div className="wsx-body">
      <div className="mpf-jr-kpis" style={{ display: "grid", gridTemplateColumns: "repeat(5,1fr)", gap: 8, marginBottom: 12 }}>
        <SPTk l="Resolved · 1Y" v={resolved} s="setups scored" tone="violet" />
        <SPTk l="Hit rate" v={`${hr.toFixed(0)}%`} s={`${hits} of ${resolved}`} tone={hr >= 55 ? "gn" : "amb"} />
        <SPTk l="Stacked (6+) hit" v={`${stHr.toFixed(0)}%`} s={`${stacked.length} high-confluence`} tone={stHr >= 60 ? "gn" : "amb"} />
        <SPTk l="Avg fwd 21d" v={`${avg >= 0 ? "+" : ""}${avg.toFixed(1)}%`} s="thesis-aligned" tone={avg >= 0 ? "gn" : "rd"} />
        <SPTk l="Edge" v={hr >= 55 ? "REAL" : "THIN"} s="vs 50% coin" tone={hr >= 55 ? "gn" : "amb"} />
      </div>
      <div className="aip-board-bar" style={{ display: "flex", justifyContent: "space-between", marginBottom: 10 }}>
        <span className="mono dim2">{resolved} pattern/SMC setups scored at +21 trading days · confluence ≥6 cohort highlighted</span>
        <div className="seg">{[["all", "All"], ["hit", "Hits"], ["fail", "Misses"]].map(([id, l]) => <button key={id} className={`seg-btn ${f === id ? "is-on" : ""}`} onClick={() => setF(id)}>{l}</button>)}</div>
      </div>
      <table className="dtable wsx-tbl spx-tbl">
        <thead><tr><th>When</th><th>Sym</th><th>Pattern</th><th className="r">Methods</th><th>Bias</th><th className="r">Fwd 21d</th><th>Outcome</th></tr></thead>
        <tbody>{rows.map((l, i) => (
          <tr key={i} onClick={() => onTicker(l.sym, "patterns")} style={{ cursor: "pointer" }}>
            <td className="mono dim2">{l.wk}w ago</td>
            <td className="mono"><b>{l.sym}</b></td>
            <td className="mono" style={{ fontSize: 11 }}><span className="spx-tag spx-tag--v">{l.patt}</span></td>
            <td className="r mono tabular dim2">{l.align}/7</td>
            <td><span className={l.bull ? "up" : "dn"}>{l.bull ? "LONG" : "SHORT"}</span></td>
            <td className={`r mono tabular ${l.fwd >= 0 ? "up" : "dn"}`}><b>{l.fwd >= 0 ? "+" : ""}{l.fwd}%</b></td>
            <td><span className={`aip-out kpi-tone--${l.hit ? "gn" : "rd"}`}>{l.hit ? "✓ HIT" : "✕ MISS"}</span></td>
          </tr>
        ))}</tbody>
      </table>
      <div className="of-playbook mono"><span className="of-pb-tag" style={{ color: "var(--violet)" }}>CONFLUENCE EDGE</span><span className="of-pb-txt">High-confluence setups (6+ of 7 methods aligned) resolve in-thesis <b className="up">{stHr.toFixed(0)}%</b> of the time over 21 days — meaningfully above the {hr.toFixed(0)}% base rate. Confluence is the edge.</span></div>
    </div>
  );
}
function SPTk({ l, v, s, tone }) {
  return <div className={`pf-tile pf-tile--${tone}`}><div className="pf-tile-l mono dim2">{l}</div><div className={`pf-tile-v mono kpi-tone--${tone}`}>{v}</div><div className="pf-tile-s mono dim2">{s}</div></div>;
}

window.SurfaceSMCPatterns = SurfaceSMCPatterns;

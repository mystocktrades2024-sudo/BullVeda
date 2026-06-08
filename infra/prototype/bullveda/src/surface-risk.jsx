// surface-risk.jsx — Automated Book · Risk & Exposure (quant-grade).
// REAL exposure + concentration from the shared auto-traded paper book
// (window.__BV.portfolio / /api/portfolio): gross/net exposure, $-at-risk per
// position (entry−stop)×shares, name + sector concentration. Per-position vol /
// VaR / β enriched async from the real risk engine (/api/pattern/risk/{sym},
// engines/risk.py). Macro/regime risk from window.__BV.market. Honest "—" where
// a feed is absent; honest empty when the book is flat or unsynced. Demo book
// renders ONLY in standalone showcase (!window.__BV). No fabricated tickers.
const { useState: useRiskS, useMemo: useRiskM, useEffect: useRiskE } = React;

// ── served-aware accessors (mirror surface-portfolio.jsx) ──
const RK_SERVED = (typeof window !== "undefined" && !!window.__BV);
const rkN = (v) => { const n = Number(v); return Number.isFinite(n) ? n : null; };

// Standalone-showcase ONLY (no window.__BV). Never rendered in the served path.
// Neutral DEMO placeholders — never demo tickers.
const RK_DEMO_BOOK = {
  equity: 108420, cash: 84600, invested: 23820, short_exposure: 7164,
  open_count: 4, max_positions: 5, config_label: "showcase demo",
  positions: [
    { ticker:"DEMO1", direction:"long",  shares:240, entry_price:28.40, current_price:31.10, stop:27.20, setup_type:"Cont. BO", days_held:8,  unrealized_pnl_dollars:648 },
    { ticker:"DEMO2", direction:"long",  shares:60,  entry_price:162.0, current_price:168.4, stop:154.0, setup_type:"Pullback", days_held:12, unrealized_pnl_dollars:384 },
    { ticker:"DEMO3", direction:"long",  shares:120, entry_price:44.0,  current_price:46.2,  stop:41.0,  setup_type:"VCP",      days_held:5,  unrealized_pnl_dollars:264 },
    { ticker:"DEMO4", direction:"short", shares:180, entry_price:41.20, current_price:39.80, stop:43.40, setup_type:"Range",    days_held:4,  unrealized_pnl_dollars:252 },
  ],
};
// Standalone demo sector map for DEMO placeholders (served path uses BV.findRow real sectors).
const RK_DEMO_SECTORS = { DEMO1:"Industrials", DEMO2:"Software", DEMO3:"Semis", DEMO4:"Consumer" };

// Read the shared auto-traded paper book. Served → real or null. Standalone → demo.
function useRkBook() {
  const read = () => (window.__BV && (window.__BV.portfolio || window.__BV._bookCache)) || null;
  const [book, setBook] = useRiskS(RK_SERVED ? read : RK_DEMO_BOOK);
  useRiskE(() => {
    if (!RK_SERVED) return;
    let on = true;
    try {
      if (window.__BV && window.__BV.get) {
        window.__BV.get("/api/portfolio").then(d => {
          if (!on || !d) return;
          window.__BV._bookCache = d; window.__BV.portfolio = d; setBook(d);
        }).catch(() => {});
      }
    } catch (e) {}
    return () => { on = false; };
  }, []);
  return book;
}

// Per-position risk metrics (β / vol / VaR) from the real engine, keyed by symbol.
// engines/risk.py via /api/pattern/risk/{sym}?mode=swing. Served only — no fabrication.
function useRkRiskBySym(syms) {
  const [map, setMap] = useRiskS({});
  const key = (syms || []).join(",");
  useRiskE(() => {
    if (!RK_SERVED || !window.__BV || !window.__BV.get || !syms || !syms.length) return;
    let on = true;
    syms.forEach(sym => {
      try {
        window.__BV.get("/api/pattern/risk/" + encodeURIComponent(sym) + "?mode=swing")
          .then(d => { if (on && d && d.ok) setMap(m => Object.assign({}, m, { [sym]: d })); })
          .catch(() => {});
      } catch (e) {}
    });
    return () => { on = false; };
  }, [key]);
  return map;
}

function sectorOf(sym) {
  if (RK_SERVED) {
    try { const r = window.__BV.findRow && window.__BV.findRow(sym); if (r && r.sector) return r.sector; } catch (e) {}
    return "—";
  }
  return RK_DEMO_SECTORS[sym] || "—";
}

function RkKpi({ k, v, tone, s }) {
  return <div className={`wsx-kpi wsx-kpi--${tone}`}><div className="wsx-kpi-l mono">{k}</div><div className={`wsx-kpi-v mono kpi-tone--${tone}`}>{v}</div><div className="wsx-kpi-s mono dim2">{s}</div></div>;
}

function SurfaceRisk({ onTicker }) {
  const [sort, setSort] = useRiskS({ col:"riskDol", dir:-1 });
  const book = useRkBook();

  // ── real per-position rows from the book. No fabrication. ──
  const pos = useRiskM(() => {
    const raw = (book && Array.isArray(book.positions)) ? book.positions : [];
    return raw.map(p => {
      const sym = String(p.ticker || "").toUpperCase();
      const short = String(p.direction || "").toLowerCase() === "short" || rkN(p.signed_qty) < 0;
      const qty = Math.abs(rkN(p.shares) ?? 0);
      const entry = rkN(p.entry_price), last = rkN(p.current_price), stop = rkN(p.stop);
      const mv = (last != null) ? qty * last : null;              // market value (gross)
      const signedMv = (mv != null) ? (short ? -mv : mv) : null;  // net contribution
      // $ at risk to stop = (entry−stop)×shares (only when stop is on the protective side)
      let riskDol = null;
      if (entry != null && stop != null) {
        const adverse = short ? (stop - entry) : (entry - stop);
        riskDol = adverse > 0 ? adverse * qty : 0;
      }
      return { sym, short, qty, entry, last, stop, mv, signedMv, riskDol,
        sector: sectorOf(sym), sleeve: p.setup_type || "—" };
    }).filter(p => p.sym);
  }, [book]);

  const syms = useRiskM(() => pos.map(p => p.sym), [pos]);
  const riskBySym = useRkRiskBySym(syms);

  const equity = rkN(book && book.equity);
  // gross / net exposure off real market values, expressed as % of equity (NAV).
  const grossMv = pos.reduce((a, p) => a + (p.mv || 0), 0);
  const netMv = pos.reduce((a, p) => a + (p.signedMv || 0), 0);
  const longs = pos.filter(p => !p.short), shorts = pos.filter(p => p.short);
  const grossPct = (equity && equity > 0) ? grossMv / equity * 100 : null;
  const netPct = (equity && equity > 0) ? netMv / equity * 100 : null;
  const totalRisk = pos.reduce((a, p) => a + (p.riskDol || 0), 0);
  const riskNavPct = (equity && equity > 0) ? totalRisk / equity * 100 : null;
  const cash = rkN(book && book.cash);
  const cashPct = (equity && equity > 0 && cash != null) ? cash / equity * 100 : null;

  // top-5 name concentration (% of gross market value)
  const top5 = grossMv > 0
    ? [...pos].sort((a, b) => (b.mv || 0) - (a.mv || 0)).slice(0, 5).reduce((a, p) => a + (p.mv || 0), 0) / grossMv * 100
    : null;
  const largest = grossMv > 0 ? Math.max(...pos.map(p => (p.mv || 0))) / grossMv * 100 : null;

  // beta-adjusted net exposure — needs real per-position betas; if none loaded yet → null (honest "—")
  const betaNet = useRiskM(() => {
    if (!equity || equity <= 0 || !pos.length) return null;
    let any = false, acc = 0;
    pos.forEach(p => {
      const rm = riskBySym[p.sym];
      const b = rm && rm.ok ? rkN(rm.beta) : null;
      if (b != null && p.signedMv != null) { any = true; acc += (p.signedMv / equity) * b; }
    });
    return any ? acc : null;
  }, [pos, riskBySym, equity]);

  // sector net exposure (% NAV), signed long − short. Real sectors via BV.findRow.
  const sectors = useRiskM(() => {
    if (!equity || equity <= 0) return [];
    const m = {};
    pos.forEach(p => { if (p.signedMv != null && p.sector && p.sector !== "—") m[p.sector] = (m[p.sector] || 0) + p.signedMv; });
    return Object.entries(m)
      .map(([label, v]) => ({ label, value: v / equity * 100, tone: v >= 0 ? "gn" : "rd" }))
      .sort((a, b) => Math.abs(b.value) - Math.abs(a.value));
  }, [pos, equity]);

  // portfolio $-at-risk by position → "% of book risk" for the table risk bar
  const maxRisk = pos.reduce((a, p) => Math.max(a, p.riskDol || 0), 0) || 1;
  const rows = useRiskM(() => [...pos].sort((a, b) => {
    const va = a[sort.col], vb = b[sort.col];
    let v;
    if (typeof va === "number" || typeof vb === "number") v = (Math.abs(vb || 0)) - (Math.abs(va || 0));
    else v = String(va).localeCompare(String(vb));
    return v * (sort.dir < 0 ? 1 : -1);
  }), [sort, pos]);
  const setS = c => setSort(s => ({ col:c, dir:s.col === c ? -s.dir : -1 }));

  // macro / regime risk context (real when present)
  const mkt = (RK_SERVED && window.__BV && window.__BV.market) || null;
  const money = (v) => (v == null) ? "—" : (v < 0 ? "−$" : "$") + Math.abs(Math.round(v)).toLocaleString();

  const Header = () => (
    <div className="wsx-hdr">
      <div className="wsx-hdr-l">
        <div className="wsx-eyebrow mono">AUTOMATED BOOK · RISK &amp; EXPOSURE</div>
        <h1 className="wsx-title mono">Risk</h1>
        <div className="wsx-sub mono dim2">model book exposure · $-at-risk to stops · name &amp; sector concentration · per-position β/vol/VaR · regime risk</div>
      </div>
      <div className="wsx-hdr-r"><StaleStamp staleAfter={120} label="book sync" src="/api/portfolio (Alpaca paper) · β/vol/VaR engines/risk.py · regime /api/* market" /></div>
    </div>
  );

  // ── honest empty: served but book not synced yet ──
  if (RK_SERVED && !book) {
    return (
      <div className="surface wsx wsx--copper rkx">
        <Header />
        <div className="lab-verdict mono dim2" style={{ padding: 20 }}>
          Waiting on sync — loading the automated book's exposure from <b className="copper">/api/portfolio</b> (Alpaca paper)…
        </div>
      </div>
    );
  }

  // ── honest empty: served and book is flat (no exposure → no book risk) ──
  if (RK_SERVED && pos.length === 0) {
    return (
      <div className="surface wsx wsx--copper rkx">
        <Header />
        <div className="lab-verdict mono dim2" style={{ padding: 20 }}>
          Flat — the automated paper book holds no positions, so there is no book exposure or position risk to report.{cash != null ? ` Cash ${money(cash)}.` : ""}
        </div>
        {mkt && (
          <div className="wsx-card rkx-card" style={{ marginTop: 14 }}>
            <div className="rkx-card-h mono">REGIME RISK CONTEXT <span className="dim2">· market backdrop for new exposure</span></div>
            <div className="rkx-stress">
              <div className="rkx-stress-row"><span className="mono rkx-stress-l">Regime</span><span className="mono rkx-stress-v">{mkt.regimeLabel || "—"}{mkt.regimeTrend ? " · " + mkt.regimeTrend : ""}</span></div>
              {mkt.breadthPct != null && <div className="rkx-stress-row"><span className="mono rkx-stress-l">Breadth (% &gt; 50d)</span><span className={`mono rkx-stress-v ${mkt.breadthPct >= 50 ? "up" : "dn"}`}>{mkt.breadthPct.toFixed(0)}%</span></div>}
              {mkt.maxSize != null && <div className="rkx-stress-row"><span className="mono rkx-stress-l">Regime size cap</span><span className="mono rkx-stress-v">{mkt.maxSize.toFixed(0)}% / position</span></div>}
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="surface wsx wsx--copper rkx">
      <Header />

      <div className="wsx-kpis rkx-kpis">
        <RkKpi k="GROSS EXPOSURE" v={grossPct != null ? `${grossPct.toFixed(0)}%` : "—"} tone="copper" s={`${longs.length}L · ${shorts.length}S · ${money(grossMv)}`} />
        <RkKpi k="NET EXPOSURE" v={netPct != null ? `${netPct >= 0 ? "+" : ""}${netPct.toFixed(0)}%` : "—"} tone={netPct == null ? "ink" : netPct >= 0 ? "gn" : "rd"} s={netPct == null ? "—" : netPct >= 0 ? "long-biased" : "short-biased"} />
        <RkKpi k="BETA-ADJ NET" v={betaNet != null ? `${betaNet >= 0 ? "+" : ""}${betaNet.toFixed(2)}β` : "—"} tone="amb" s={betaNet != null ? "vs SPY · real β" : "β loading…"} />
        <RkKpi k="$ AT RISK" v={money(totalRisk)} tone="rd" s={riskNavPct != null ? `${riskNavPct.toFixed(2)}% NAV to stops` : "to stops"} />
        <RkKpi k="TOP-5 CONC." v={top5 != null ? `${top5.toFixed(0)}%` : "—"} tone="amb" s={largest != null ? `largest ${largest.toFixed(0)}%` : "name concentration"} />
        <RkKpi k="SLOTS" v={`${(book && book.open_count != null) ? book.open_count : pos.length}/${(book && book.max_positions != null) ? book.max_positions : "—"}`} tone="ink" s="positions used" />
        <RkKpi k="CASH" v={cashPct != null ? `${cashPct.toFixed(0)}%` : "—"} tone="cy" s={cash != null ? `${money(cash)} dry powder` : "dry powder"} />
      </div>

      <div className="rkx-grid">
        <div className="wsx-card rkx-card">
          <div className="rkx-card-h mono">SECTOR NET EXPOSURE <span className="dim2">· long − short, % NAV · sectors via scan feed</span></div>
          {sectors.length ? <QDiverge rows={sectors} fmt={v => `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`} />
            : <div className="smc-empty mono dim2">— no sector classification available for the held names</div>}
        </div>
        <div className="wsx-card rkx-card">
          <div className="rkx-card-h mono">REGIME RISK CONTEXT <span className="dim2">· market backdrop</span></div>
          {mkt ? (
            <div className="rkx-stress">
              <div className="rkx-stress-row"><span className="mono rkx-stress-l">Regime</span><span className={`mono rkx-stress-v ${mkt.regimeOn ? "up" : "dn"}`}>{mkt.regimeLabel || "—"}{mkt.regimeTrend ? " · " + mkt.regimeTrend : ""}</span></div>
              <div className="rkx-stress-row"><span className="mono rkx-stress-l">Breadth (% &gt; 50d)</span><span className={`mono rkx-stress-v ${mkt.breadthPct != null && mkt.breadthPct >= 50 ? "up" : "dn"}`}>{mkt.breadthPct != null ? mkt.breadthPct.toFixed(0) + "%" : "—"}</span></div>
              <div className="rkx-stress-row"><span className="mono rkx-stress-l">Regime size cap</span><span className="mono rkx-stress-v">{mkt.maxSize != null ? mkt.maxSize.toFixed(0) + "% / position" : "—"}</span></div>
              <div className="rkx-stress-row"><span className="mono rkx-stress-l">Put/Call</span><span className="mono rkx-stress-v">{mkt.putCall != null ? mkt.putCall.toFixed(2) : "—"}</span></div>
              <div className="rkx-note mono dim2">Net exposure {netPct != null ? `${netPct >= 0 ? "+" : ""}${netPct.toFixed(0)}% of NAV` : "—"} into a <b>{mkt.regimeLabel || "—"}</b> tape. Size caps and breadth define how much fresh risk the model book should add.</div>
            </div>
          ) : <div className="smc-empty mono dim2">— no live regime context (market feed absent)</div>}
        </div>
      </div>

      <div className="wsx-card rkx-card">
        <div className="rkx-card-h mono">POSITIONS · RISK CONTRIBUTION <span className="dim2">· $-at-risk to stop · β/vol/VaR from risk engine · click to open</span></div>
        <table className="dtable wsx-tbl rkx-tbl">
          <thead><tr>
            {[["sym","Sym"],["sector","Sector"],["mv","Mkt Val"],["wPct","% Gross"],["beta","β"],["vol","Vol"],["var95","VaR95"],["riskDol","$ at risk"]].map(([c, l]) => (
              <th key={c} className={["mv","wPct","beta","vol","var95","riskDol"].includes(c) ? "r" : ""} onClick={() => setS(c)} style={{ cursor:"pointer" }}>{l}{sort.col === c ? (sort.dir > 0 ? " ▲" : " ▼") : ""}</th>
            ))}
          </tr></thead>
          <tbody>
            {rows.map(p => {
              const rm = riskBySym[p.sym];
              const beta = rm && rm.ok ? rkN(rm.beta) : null;
              const vol = rm && rm.ok ? rkN(rm.vol_ann_pct) : null;
              const var95 = rm && rm.ok ? rkN(rm.var95_pct) : null;
              const wPct = grossMv > 0 && p.mv != null ? p.mv / grossMv * 100 : null;
              return (
                <tr key={p.sym} onClick={() => onTicker && onTicker(p.sym)} style={{ cursor:"pointer" }}>
                  <td className="mono"><b>{p.sym}</b> <span className={`rkx-side rkx-side--${p.short ? "s" : "l"}`}>{p.short ? "S" : "L"}</span></td>
                  <td className="dim">{p.sector}</td>
                  <td className="r mono">{p.mv != null ? money(p.mv) : "—"}</td>
                  <td className="r mono dim2">{wPct != null ? wPct.toFixed(0) + "%" : "—"}</td>
                  <td className="r mono">{beta != null ? beta.toFixed(2) : "—"}</td>
                  <td className="r mono dim2">{vol != null ? vol.toFixed(0) + "%" : "—"}</td>
                  <td className="r mono dim2">{var95 != null ? "−" + var95.toFixed(1) + "%" : "—"}</td>
                  <td className="r">
                    {p.riskDol != null
                      ? <><span className="rkx-risk-bar"><i style={{ width:`${Math.min(100, (p.riskDol / maxRisk) * 100)}%` }} /></span> <span className="mono">{money(p.riskDol)}</span></>
                      : <span className="mono dim2">—</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <div className="rkx-note mono dim2">
          <b>$ at risk</b> = (entry − stop) × shares — the realized loss if every stop fills. β / vol / 1-day 95% VaR are computed per name from real 126-day returns (<b>engines/risk.py</b>); "—" until the engine responds or when a name is off-universe. Concentration is % of gross market value.
        </div>
      </div>

      <div className="rkx-note mono dim2" style={{ marginTop: 14 }}>
        Shared model portfolio — auto-traded Alpaca paper account, same book for every viewer. Not your personal book.
        Exposure &amp; $-at-risk from <b>/api/portfolio</b>; per-position risk from <b>/api/pattern/risk</b>; regime context from the live market feed.
        {RK_SERVED ? "" : " (standalone showcase — demo book, no served data.)"}
      </div>
    </div>
  );
}
window.SurfaceRisk = SurfaceRisk;

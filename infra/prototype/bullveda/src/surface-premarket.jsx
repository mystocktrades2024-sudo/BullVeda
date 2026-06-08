// surface-premarket.jsx — Pre-Market cockpit (EODHD + Schwab shaped).
// Session clock + futures/risk tape + gap board with catalyst + gap taxonomy + PM levels.

const { useState: usePM, useMemo: usePMm } = React;

// ── served-aware real source ────────────────────────────────────────
// BULLVEDA: real pre-market data is in window.__BV.critical.premarket
// (critical.premarket: { _meta:{session_active,session_status}, gappers_up[],
// gappers_dn[], catalysts{} }). It is only populated during the 04:00–09:29 ET
// pre-market window; outside it, gappers are empty and we render an honest-empty
// state rather than fabricated gappers. Macro = critical.economic_events,
// headlines = critical.market_news, your book = window.__BV.portfolio.positions.
// The PM_ROWS_DEMO block below is the standalone-showcase fallback ONLY.
const PM_SERVED = (typeof window !== "undefined" && !!window.__BV);
const PM_CRIT = () => (PM_SERVED && window.__BV.critical) || null;
const pmNum = (v) => { const n = Number(v); return Number.isFinite(n) ? n : null; };

// Map a real gapper row (from critical.premarket.gappers_*) into the table shape.
function pmMapGapper(g, catalystsBySym) {
  const sym = String(g.ticker || g.sym || g.symbol || "").toUpperCase();
  const gap = pmNum(g.gap_pct != null ? g.gap_pct : g.gap);
  const last = pmNum(g.last != null ? g.last : g.pre_price);
  const prev = pmNum(g.prev_close != null ? g.prev_close : g.prevClose);
  const pmVol = pmNum(g.pm_volume_m != null ? g.pm_volume_m : g.pmVol);
  const adv = pmNum(g.adv_m != null ? g.adv_m : g.adv);
  const rvol = (pmVol != null && adv) ? pmVol / adv : pmNum(g.rvol);
  const cat = (catalystsBySym && catalystsBySym[sym]) || g.catalyst || null;
  const taxon = (gap == null || Math.abs(gap) < 1.5) ? "—"
    : (gap > 0 && (rvol || 0) >= 2.0) ? "GAP & GO"
    : (gap > 0 && (rvol || 99) < 1.2) ? "GAP FILL"
    : (gap < 0 && (rvol || 0) >= 2.0) ? "BREAKDOWN"
    : (Math.abs(gap) > 5 && (rvol || 99) < 1.5) ? "EXHAUSTION"
    : "WATCH";
  return {
    sym, sector: g.sector || "—", gap, prevClose: prev, last, pmVol, adv, rvol,
    cat: cat || "—", catType: cat ? "news" : "tech", catTone: cat ? "amb" : "ink",
    pmHigh: pmNum(g.pm_high), pmLow: pmNum(g.pm_low),
    fillProb: pmNum(g.fill_prob), taxon, halt: !!g.halted,
  };
}

const PM_ROWS_DEMO = (() => {
  const cats = [
    ["Earnings beat", "earnings", "gn"], ["Guidance cut", "earnings", "rd"],
    ["Analyst upgrade", "news", "gn"], ["FDA / data", "news", "amb"],
    ["M&A rumor", "news", "amb"], ["Downgrade", "news", "rd"],
    ["Sympathy move", "tech", "ink"], ["Technical gap", "tech", "ink"],
  ];
  return HEATMAP.slice(0, 18).map(([sym, sector, mcap, chg], i) => {
    const code = (sym.charCodeAt(0) || 65) + (sym.charCodeAt(1) || 66) + i * 7; // NaN-safe for 1-char real tickers
    const gap = (chg * 1.6) + ((code % 14) - 6) * 0.4;       // pre-market gap %
    const pmVol = (0.4 + (code % 40) / 10);                    // PM vol vs ADV
    const [cat, catType, catTone] = cats[code % cats.length] || cats[0];
    const w = WATCHLIST.find(x => x.sym === sym);
    const prevClose = (w?.price || (20 + code % 200));
    const last = prevClose * (1 + gap / 100);
    // gap taxonomy
    const taxon = Math.abs(gap) < 1.5 ? "—"
      : (gap > 0 && pmVol >= 2.0) ? "GAP & GO"
      : (gap > 0 && pmVol < 1.2) ? "GAP FILL"
      : (gap < 0 && pmVol >= 2.0) ? "BREAKDOWN"
      : (Math.abs(gap) > 5 && pmVol < 1.5) ? "EXHAUSTION"
      : "WATCH";
    return {
      sym, sector, cat, catType, catTone, gap, pmVol,
      prevClose, last,
      pmHigh: last * (1 + (code % 5) / 100),
      pmLow: last * (1 - (code % 4) / 100),
      fillProb: Math.max(18, Math.min(82, 50 - Math.round(gap * 2) + (code % 20))),
      adv: (0.6 + (code % 12) / 10),
      taxon,
      halt: code % 17 === 0,
    };
  }).sort((a, b) => Math.abs(b.gap) - Math.abs(a.gap));
})();

// Standalone-showcase futures tape ONLY (no window.__BV).
const PM_FUT_DEMO = [
  ["ES", "S&P fut", "+0.31%", "gn"], ["NQ", "Nasdaq fut", "+0.58%", "gn"],
  ["RTY", "Russell fut", "−0.12%", "rd"], ["VIX", "volatility", "16.1", "gn"],
  ["DXY", "dollar", "+0.08%", "ink"], ["CL", "crude", "−0.9%", "rd"],
];

// Real risk tape from critical.regime (SPY/QQQ daily chg + VIX). No futures
// feed in this deployment, so we show cash-index changes + VIX honestly.
function pmRealTape(crit) {
  const rg = (crit && crit.regime) || null;
  if (!rg) return null;
  const out = [];
  const spy = pmNum(rg.spy_daily_chg);
  if (spy != null) out.push(["SPY", "S&P (cash)", `${spy >= 0 ? "+" : ""}${spy.toFixed(2)}%`, spy >= 0 ? "gn" : "rd"]);
  const vix = rg.vix && pmNum(rg.vix.vix_current);
  if (vix != null) out.push(["VIX", "volatility", vix.toFixed(1), vix < 18 ? "gn" : vix < 25 ? "amb" : "rd"]);
  const breadth = pmNum(rg.breadth_pct_50d);
  if (breadth != null) out.push(["BREADTH", "% > 50-DMA", `${breadth.toFixed(0)}%`, breadth >= 55 ? "gn" : breadth >= 40 ? "amb" : "rd"]);
  return out.length ? out : null;
}

function SurfacePreMarket({ onTicker }) {
  const [filter, setFilter] = usePM("all");
  const crit = PM_CRIT();
  const pm = (crit && crit.premarket) || null;
  const sessionActive = !!(pm && pm._meta && pm._meta.session_active);

  // Real gapper rows from critical.premarket; demo only when not served.
  const PM_ROWS = usePMm(() => {
    if (!PM_SERVED) return PM_ROWS_DEMO;
    if (!pm) return [];
    const catsBySym = {};
    Object.entries(pm.catalysts || {}).forEach(([k, v]) => { catsBySym[String(k).toUpperCase()] = (typeof v === "string") ? v : (v && (v.headline || v.title)) || null; });
    return [...(pm.gappers_up || []), ...(pm.gappers_dn || [])]
      .map(g => pmMapGapper(g, catsBySym)).filter(r => r.sym && r.gap != null)
      .sort((a, b) => Math.abs(b.gap) - Math.abs(a.gap));
  }, [pm]);

  const gu = PM_ROWS.filter(r => r.gap > 1.5).length;
  const gd = PM_ROWS.filter(r => r.gap < -1.5).length;
  const news = PM_ROWS.filter(r => r.catType !== "tech").length;
  const rows = usePMm(() => {
    if (filter === "up") return PM_ROWS.filter(r => r.gap > 0);
    if (filter === "down") return PM_ROWS.filter(r => r.gap < 0);
    if (filter === "news") return PM_ROWS.filter(r => r.catType !== "tech");
    if (filter === "go") return PM_ROWS.filter(r => r.taxon === "GAP & GO");
    return PM_ROWS;
  }, [filter, PM_ROWS]);

  // Real risk tape / book / macro / news (served) — honest when feed is absent.
  const futTape = PM_SERVED ? (pmRealTape(crit) || []) : PM_FUT_DEMO;
  const book = (PM_SERVED && window.__BV.portfolio && Array.isArray(window.__BV.portfolio.positions)) ? window.__BV.portfolio.positions : null;
  const macroEv = (PM_SERVED && crit && Array.isArray(crit.economic_events)) ? crit.economic_events : null;
  const wire = (PM_SERVED && window.__BV.marketNews && window.__BV.marketNews.length) ? window.__BV.marketNews : null;

  // Served + no live pre-market session/gappers → honest-empty board.
  if (PM_SERVED && PM_ROWS.length === 0) {
    return (
      <div className="surface wsx wsx--violet pm2">
        <div className="wsx-hdr">
          <div className="wsx-hdr-l">
            <div className="wsx-eyebrow mono">PRE-MARKET COCKPIT · 04:00–09:29 ET</div>
            <h1 className="wsx-title mono">Pre-Market</h1>
            <div className="wsx-sub mono dim2">gap board · catalyst-tagged · gap taxonomy · PM levels</div>
          </div>
          <div className="wsx-hdr-r"><span className="mono dim2">src · critical.premarket</span></div>
        </div>
        {futTape.length > 0 && (
          <div className="pm-tape">
            {futTape.map(([s, l, v, t], i) => (
              <div key={i} className={`pm-fut pm-fut--${t}`}>
                <span className="pm-fut-s mono">{s}</span>
                <span className={`pm-fut-v mono kpi-tone--${t}`}>{v}</span>
                <span className="pm-fut-l mono dim2">{l}</span>
              </div>
            ))}
          </div>
        )}
        <div className="wsx-body"><div className="lab-verdict mono dim2" style={{ padding: 24, lineHeight: 1.7 }}>
          {sessionActive
            ? "Pre-market session is live but no names are gapping > 1.5% right now — nothing to show. This board only renders real gappers from the scan; it stays empty rather than fabricate movers."
            : <>No pre-market session active ({(pm && pm._meta && pm._meta.session_status) || "outside 04:00–09:29 ET"}). The gap board populates with real movers during the pre-market window. No fabricated gappers are shown.</>}
          {macroEv && macroEv.length > 0 && <><br /><br />Today/upcoming macro prints are still live below.</>}
        </div></div>
        {macroEv && macroEv.length > 0 && (
          <div className="pm-panels">
            <div className="lab-card">
              <div className="lab-card-h mono">⚠ MACRO CALENDAR · upcoming US prints</div>
              <div className="pm-macro">
                {macroEv.slice(0, 6).map((m, i) => (
                  <div key={i} className={`pm-macro-row pm-macro--${m._impact === "HIGH" ? "rd" : m._impact === "MED" ? "amb" : "ink"}`}>
                    <span className="mono pm-macro-t">{String(m.date || "").slice(5, 16)}</span>
                    <span className="mono pm-macro-e">{m.type}{m.comparison ? " (" + m.comparison + ")" : ""}</span>
                    <Pill tone={m._impact === "HIGH" ? "rd" : m._impact === "MED" ? "amb" : "ink"} small>{m._impact || "LOW"}</Pill>
                    <span className="mono dim2 pm-macro-f">{m.estimate != null ? "fcst " + m.estimate : ""}{m.previous != null ? " · prior " + m.previous : ""}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
        <div className="pm-note mono dim2">
          Gap board sourced from <b>critical.premarket</b> (Schwab pre-session quotes when the window is open). Macro from <b>EODHD /calendar</b> (critical.economic_events). Empty by design outside the pre-market window — no fabricated movers.
        </div>
      </div>
    );
  }

  return (
    <div className="surface wsx wsx--violet pm2">
      <div className="wsx-hdr">
        <div className="wsx-hdr-l">
          <div className="wsx-eyebrow mono">PRE-MARKET COCKPIT · 04:00–09:29 ET</div>
          <h1 className="wsx-title mono">Pre-Market</h1>
          <div className="wsx-sub mono dim2">gap board · catalyst-tagged · gap taxonomy · PM levels{!PM_SERVED ? " · futures tape" : ""}</div>
        </div>
        <div className="wsx-hdr-r">
          {!PM_SERVED && <div className="pm-clock mono"><span className="pm-clock-dot" />OPENS IN <b>00:42:18</b></div>}
          {PM_SERVED ? <span className="mono dim2">src · critical.premarket</span> : <FreshnessPill state="live" age="5s" />}
        </div>
      </div>

      {/* Pre-Market Read — standalone-showcase narrative only (served path is data-driven below). */}
      {!PM_SERVED && (
      <div className="pm-read">
        <div className="pm-read-l">
          <span className="pm-read-tag mono">PRE-MARKET READ</span>
          <span className="pm-read-stance mono">STAND ASIDE · WAIT FOR 09:45</span>
        </div>
        <div className="pm-read-body mono">
          Futures firm, <b className="up">risk-on tilt</b> (Tech +1.4% / Energy +2.1%) — but <b className="warn">CPI prints 08:30</b> and
          can override every single-name thesis, so keep risk light into the number. No clean pre-market <b>buy</b>: the big movers
          are <b className="warn">earnings-gap blackout</b> — no fresh swing entries. <b className="cop">Action:</b> watch, don't chase; let CPI + the 09:45 range print, then revisit Signal Scanner.
        </div>
        <div className="pm-read-chips">
          <span className="pm-read-chip pm-read-chip--gn">REGIME · RISK-ON</span>
          <span className="pm-read-chip pm-read-chip--rd">MACRO · CPI 08:30</span>
          <span className="pm-read-chip">DEMO SHOWCASE</span>
        </div>
      </div>
      )}
      {PM_SERVED && (
      <div className="pm-read">
        <div className="pm-read-l">
          <span className="pm-read-tag mono">PRE-MARKET READ</span>
          <span className="pm-read-stance mono">{gu + gd} GAPPER{gu + gd === 1 ? "" : "S"} · &gt; 1.5%</span>
        </div>
        <div className="pm-read-body mono">
          {gu + gd} name{gu + gd === 1 ? "" : "s"} gapping &gt; 1.5% from the scan — {gu} up, {gd} down, {news} news-driven.
          {book && book.length > 0 ? <> Your book holds {book.length} position{book.length === 1 ? "" : "s"}; check the exposure panel for overnight moves.</> : <> No open positions in the book.</>}
          {" "}Don't chase gaps in the first 5 minutes — let the 09:45 range set first.
        </div>
        <div className="pm-read-chips">
          <span className="pm-read-chip pm-read-chip--gn">{gu} GAP UP</span>
          <span className="pm-read-chip pm-read-chip--rd">{gd} GAP DOWN</span>
          {book && <span className="pm-read-chip pm-read-chip--cy">{book.length} HELD</span>}
        </div>
      </div>
      )}

      {/* Risk tape — cash indices + VIX (served) or demo futures (standalone) */}
      {futTape.length > 0 && (
      <div className="pm-tape">
        {futTape.map(([s, l, v, t], i) => (
          <div key={i} className={`pm-fut pm-fut--${t}`}>
            <span className="pm-fut-s mono">{s}</span>
            <span className={`pm-fut-v mono kpi-tone--${t}`}>{v}</span>
            <span className="pm-fut-l mono dim2">{l}</span>
          </div>
        ))}
      </div>
      )}

      <div className="wsx-kpis">
        <div className="wsx-kpi wsx-kpi--violet"><div className="wsx-kpi-l mono">GAPPERS</div><div className="wsx-kpi-v mono kpi-tone--violet">{gu + gd}</div><div className="wsx-kpi-s mono dim2">&gt; 1.5% gap</div></div>
        <div className="wsx-kpi wsx-kpi--gn"><div className="wsx-kpi-l mono">GAP UP</div><div className="wsx-kpi-v mono kpi-tone--gn">{gu}</div><div className="wsx-kpi-s mono dim2">{PM_ROWS.filter(r=>r.taxon==="GAP & GO").length} gap-and-go</div></div>
        <div className="wsx-kpi wsx-kpi--rd"><div className="wsx-kpi-l mono">GAP DOWN</div><div className="wsx-kpi-v mono kpi-tone--rd">{gd}</div><div className="wsx-kpi-s mono dim2">{PM_ROWS.filter(r=>r.taxon==="BREAKDOWN").length} breakdown</div></div>
        <div className="wsx-kpi wsx-kpi--amb"><div className="wsx-kpi-l mono">NEWS-DRIVEN</div><div className="wsx-kpi-v mono kpi-tone--amb">{news}</div><div className="wsx-kpi-s mono dim2">vs {PM_ROWS.length-news} technical</div></div>
      </div>

      <div className="lab-tabs">
        {[["all","All gaps"],["up","Gap up"],["down","Gap down"],["news","News-driven"],["go","Gap & Go"]].map(([id,l])=>(
          <button key={id} className={`lab-tab ${filter===id?"is-on":""}`} onClick={()=>setFilter(id)}>{l}</button>
        ))}
      </div>

      <div className="wsx-body">
        <table className="dtable wsx-tbl pm-tbl">
          <thead><tr>
            <th>Sym</th><th>Sector</th><th className="r">Prev</th><th className="r">PM Last</th><th className="r">Gap %</th>
            <th className="r">PM Vol</th><th className="r">vs ADV</th><th>Catalyst</th><th>Taxonomy</th>
            <th className="r">Fill Prob</th><th className="r">PM Range</th><th></th>
          </tr></thead>
          <tbody>{rows.map((t,i)=>(
            <tr key={t.sym+i} onClick={()=>onTicker(t.sym)}>
              <td className="mono"><b>{t.sym}</b>{t.halt && <span className="pm-halt mono">HALT</span>}</td>
              <td className="mono dim2">{t.sector}</td>
              <td className="r mono tabular dim">{t.prevClose != null ? "$" + t.prevClose.toFixed(2) : "—"}</td>
              <td className="r mono tabular">{t.last != null ? "$" + t.last.toFixed(2) : "—"}</td>
              <td className={`r mono tabular ${t.gap>=0?"up":"dn"}`} data-field="schwab.quote.pre.gap_pct"><b>{t.gap>=0?"+":""}{t.gap.toFixed(1)}%</b></td>
              <td className="r mono tabular" data-field="schwab.quote.pre.volume">{t.pmVol != null ? t.pmVol.toFixed(1) + "M" : "—"}</td>
              <td className={`r mono tabular ${(t.rvol||0)>=2?"up":"dim"}`}>{t.rvol != null ? t.rvol.toFixed(1) + "×" : "—"}</td>
              <td><Pill tone={t.catTone} small>{t.cat}</Pill></td>
              <td><span className={`pm-taxon pm-tax--${t.taxon==="GAP & GO"?"gn":t.taxon==="BREAKDOWN"?"rd":t.taxon==="EXHAUSTION"?"amb":"ink"}`}>{t.taxon}</span></td>
              <td className={`r mono tabular ${(t.fillProb||0)>=60?"amb":"dim"}`}>{t.fillProb != null ? t.fillProb + "%" : "—"}</td>
              <td className="r mono tabular dim">{(t.pmLow != null && t.pmHigh != null) ? `$${t.pmLow.toFixed(0)}–$${t.pmHigh.toFixed(0)}` : "—"}</td>
              <td className="r mono dim">›</td>
            </tr>
          ))}</tbody>
        </table>
      </div>

      {/* High-value cockpit panels */}
      <div className="pm-panels">
        {/* MACRO — real economic_events (served) or demo */}
        <div className="lab-card">
          <div className="lab-card-h mono">⚠ MACRO CALENDAR · {PM_SERVED ? "upcoming US prints" : "pre-open prints"}</div>
          <div className="pm-macro">
            {(PM_SERVED
              ? (macroEv && macroEv.length
                  ? macroEv.slice(0, 6).map(m => [String(m.date || "").slice(5, 16), m.type + (m.comparison ? " (" + m.comparison + ")" : ""), m._impact || "LOW", m.estimate != null ? String(m.estimate) : "—", m.previous != null ? String(m.previous) : "—", m._impact === "HIGH" ? "rd" : m._impact === "MED" ? "amb" : "ink"])
                  : [])
              : [
                  ["08:30","CPI Core MoM","HIGH","+0.3%","+0.3%","amb"],
                  ["08:30","Jobless Claims","MED","218k","221k","ink"],
                  ["10:00","FOMC Speak · Powell","HIGH","—","—","amb"],
                  ["—","NFP (Fri)","HIGH","185k","175k","rd"],
                ]
            ).map((m,i)=>(
              <div key={i} className={`pm-macro-row pm-macro--${m[5]}`}>
                <span className="mono pm-macro-t">{m[0]}</span>
                <span className="mono pm-macro-e">{m[1]}</span>
                <Pill tone={m[2]==="HIGH"?"rd":m[2]==="MED"?"amb":"ink"} small>{m[2]}</Pill>
                <span className="mono dim2 pm-macro-f">fcst {m[3]} · prior {m[4]}</span>
              </div>
            ))}
            {PM_SERVED && (!macroEv || !macroEv.length) && <div className="mono dim2" style={{ padding: 8 }}>No scheduled US macro prints in the calendar window.</div>}
          </div>
        </div>

        {/* EARNINGS REPORTERS — no dedicated pre-market reporter feed wired; demo-only */}
        {!PM_SERVED && (
        <div className="lab-card">
          <div className="lab-card-h mono">📊 EARNINGS REPORTERS · overnight + BMO</div>
          <table className="dtable wsx-tbl pm-mini-tbl">
            <thead><tr><th>Sym</th><th>When</th><th className="r">EPS</th><th className="r">Surprise</th><th className="r">React</th></tr></thead>
            <tbody>{[
              ["DEMO1","AMC","$0.91","+8.3%","+9.2%","gn"],
              ["DEMO2","BMO","$1.04","+3.8%","+4.0%","gn"],
            ].map((r,i)=>(
              <tr key={i} onClick={()=>onTicker(r[0])}>
                <td className="mono"><b>{r[0]}</b></td><td className={`mono ${r[1]==="BMO"?"cy":"amb"}`}>{r[1]}</td>
                <td className="r mono tabular">{r[2]}</td>
                <td className={`r mono tabular ${r[3].startsWith("+")?"up":"dn"}`}>{r[3]}</td>
                <td className={`r mono tabular ${r[5]==="gn"?"up":"dn"}`}>{r[4]}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
        )}

        {/* YOUR BOOK — real open positions (served) or demo */}
        {(book && book.length > 0) ? (
        <div className="lab-card">
          <div className="lab-card-h mono">💼 YOUR BOOK · open positions</div>
          <div className="pm-book">
            {book.map((p,i)=>{
              const sym = String(p.ticker || "").toUpperCase();
              const pnlPct = pmNum(p.unrealized_pnl_pct);
              const pnl = pmNum(p.unrealized_pnl_dollars);
              const tone = (pnl != null ? pnl : (pnlPct || 0)) >= 0 ? "up" : "dn";
              return (
              <div key={i} className="pm-book-row" onClick={()=>onTicker(sym)}>
                <span className="mono"><b>{sym}</b></span>
                <span className={`mono ${tone}`}>{pnlPct != null ? (pnlPct >= 0 ? "+" : "") + pnlPct.toFixed(1) + "%" : "—"}</span>
                <span className={`mono ${tone}`}>{pnl != null ? (pnl >= 0 ? "+$" : "−$") + Math.abs(Math.round(pnl)).toLocaleString() : "—"}</span>
                <span className="mono dim2">{p.setup_type || "held"}</span>
              </div>
            );})}
          </div>
        </div>
        ) : (!PM_SERVED && (
        <div className="lab-card">
          <div className="lab-card-h mono">💼 YOUR BOOK · pre-market exposure</div>
          <div className="pm-book">
            {[["DEMO1","+1.8%","+$311","held","gn"],["DEMO2","−0.4%","−$40","held","rd"]].map((p,i)=>(
              <div key={i} className="pm-book-row">
                <span className="mono"><b>{p[0]}</b></span>
                <span className={`mono ${p[1].startsWith("+")?"up":"dn"}`}>{p[1]}</span>
                <span className={`mono ${p[2].startsWith("+")?"up":"dn"}`}>{p[2]}</span>
                <span className="mono dim2">{p[3]}</span>
              </div>
            ))}
          </div>
        </div>
        ))}

        {/* SECTOR PRE-MARKET HEAT — no real PM-sector feed wired; demo-only */}
        {!PM_SERVED && (
        <div className="lab-card">
          <div className="lab-card-h mono">🔥 SECTOR PRE-MARKET HEAT</div>
          <div className="pm-secheat">
            {[["Tech","+1.4%","gn",4],["Energy","+2.1%","gn",2],["Materials","+0.9%","gn",3],["Healthcare","−0.8%","rd",2]].map((s,i)=>(
              <div key={i} className={`pm-sec pm-sec--${s[2]}`}><span className="mono pm-sec-n">{s[0]}</span><span className={`mono kpi-tone--${s[2]}`}>{s[1]}</span><span className="mono dim2">{s[3]} gappers</span></div>
            ))}
          </div>
        </div>
        )}

        {/* GAP STATISTICS — illustrative study; demo-only to avoid an unverifiable claim */}
        {!PM_SERVED && (
        <div className="lab-card">
          <div className="lab-card-h mono">📈 GAP STATISTICS · illustrative</div>
          <table className="dtable wsx-tbl pm-mini-tbl">
            <thead><tr><th>Gap bucket</th><th className="r">Fill rate</th><th className="r">Hold rate</th><th className="r">Median day</th><th className="r">n</th></tr></thead>
            <tbody>{[
              ["Up 2–5%","52%","48%","+1.2%","842"],
              ["Up >5%","38%","62%","+3.4%","318"],
              ["Down 2–5%","58%","42%","−1.0%","760"],
              ["Down >5%","44%","56%","−2.8%","281"],
            ].map((r,i)=>(
              <tr key={i}>
                <td className="mono">{r[0]}</td>
                <td className={`r mono tabular ${parseInt(r[1])>=55?"amb":"dim"}`}>{r[1]}</td>
                <td className="r mono tabular">{r[2]}</td>
                <td className={`r mono tabular ${r[3].startsWith("+")?"up":"dn"}`}>{r[3]}</td>
                <td className="r mono tabular dim">{r[4]}</td>
              </tr>
            ))}</tbody>
          </table>
          <div className="lab-verdict mono dim2">Illustrative gap-statistics (showcase) — big up-gaps tend to run, big down-gaps fill more often.</div>
        </div>
        )}

        {/* NEWS WIRE — real market_news (served) or demo */}
        {(PM_SERVED ? (wire ? wire.slice(0, 6) : null) : [
          ["06:42","DEMO1","Beats Q1, raises FY guide","gn"],
          ["06:18","DEMO2","Endpoint missed; shares slide","rd"],
        ]) && (
        <div className="lab-card">
          <div className="lab-card-h mono">📰 NEWS WIRE · market headlines</div>
          <div className="pm-wire">
            {(PM_SERVED
              ? (wire || []).slice(0, 6).map(n => {
                  const sym = (Array.isArray(n.symbols) && n.symbols[0]) ? String(n.symbols[0]).replace(/\.US$/, "") : "";
                  const tone = n.sentiment === "positive" ? "gn" : n.sentiment === "negative" ? "rd" : "ink";
                  return [String(n.date || "").slice(11, 16), sym, n.title || n.summary || "", tone];
                })
              : [["06:42","DEMO1","Beats Q1, raises FY guide","gn"],["06:18","DEMO2","Endpoint missed; shares slide","rd"]]
            ).map((n,i)=>(
              <div key={i} className={`pm-wire-row pm-wire--${n[3]}`} onClick={()=>n[1] && onTicker(n[1])}>
                <span className="mono dim2 pm-wire-t">{n[0]}</span>
                <span className="mono pm-wire-s">{n[1]}</span>
                <span className="mono pm-wire-h">{n[2]}</span>
              </div>
            ))}
          </div>
        </div>
        )}
      </div>

      <div className="pm-gameplan mono">
        <span className="pm-gp-tag">OPEN GAMEPLAN</span>
        <span className="pm-gp-txt">Don't chase gaps &gt;3% in the first 5 min — wait for the 09:45 range to set. Earnings-gap names = no fresh swing entries (blackout). Size pre-market fills at half; spreads are wide before 09:30. Macro at 08:30 (CPI) can override every single-name thesis — flat risk into the print if unsure.</span>
      </div>

      <div className="pm-note mono dim2">
        {PM_SERVED
          ? <>Gap board from <b>critical.premarket</b> (Schwab pre-session quotes, populated only 04:00–09:29 ET) · macro from <b>critical.economic_events</b> · headlines from <b>critical.market_news</b> (EODHD) · your book from <b>/api/portfolio</b>. Taxonomy = gap size × PM-RVOL × range. No fabricated movers — empty outside the pre-market window.</>
          : <>Gap % &amp; PM volume from <b>Schwab /markets/quotes</b> (pre-session, 5s poll) · catalyst tags + news from <b>EODHD /news + /calendar</b> · gap taxonomy from gap size × PM-RVOL × range · earnings-gap names blocked (blackout). <b>Showcase demo data.</b></>}
      </div>
    </div>
  );
}

window.SurfacePreMarket = SurfacePreMarket;

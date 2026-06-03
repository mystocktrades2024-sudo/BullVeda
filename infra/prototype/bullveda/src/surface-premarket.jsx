// surface-premarket.jsx — Pre-Market cockpit (EODHD + Schwab shaped).
// Session clock + futures/risk tape + gap board with catalyst + gap taxonomy + PM levels.

const { useState: usePM, useMemo: usePMm } = React;

const PM_ROWS = (() => {
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

const PM_FUT = [
  ["ES", "S&P fut", "+0.31%", "gn"], ["NQ", "Nasdaq fut", "+0.58%", "gn"],
  ["RTY", "Russell fut", "−0.12%", "rd"], ["VIX", "volatility", "16.1", "gn"],
  ["DXY", "dollar", "+0.08%", "ink"], ["CL", "crude", "−0.9%", "rd"],
];

function SurfacePreMarket({ onTicker }) {
  const [filter, setFilter] = usePM("all");
  const gu = PM_ROWS.filter(r => r.gap > 1.5).length;
  const gd = PM_ROWS.filter(r => r.gap < -1.5).length;
  const news = PM_ROWS.filter(r => r.catType !== "tech").length;
  const rows = usePMm(() => {
    if (filter === "up") return PM_ROWS.filter(r => r.gap > 0);
    if (filter === "down") return PM_ROWS.filter(r => r.gap < 0);
    if (filter === "news") return PM_ROWS.filter(r => r.catType !== "tech");
    if (filter === "go") return PM_ROWS.filter(r => r.taxon === "GAP & GO");
    return PM_ROWS;
  }, [filter]);

  return (
    <div className="surface wsx wsx--violet pm2">
      <div className="wsx-hdr">
        <div className="wsx-hdr-l">
          <div className="wsx-eyebrow mono">PRE-MARKET COCKPIT · 04:00–09:29 ET</div>
          <h1 className="wsx-title mono">Pre-Market</h1>
          <div className="wsx-sub mono dim2">gap board · catalyst-tagged · gap taxonomy · PM levels · futures tape</div>
        </div>
        <div className="wsx-hdr-r">
          <div className="pm-clock mono"><span className="pm-clock-dot" />OPENS IN <b>00:42:18</b></div>
          <FreshnessPill state="live" age="5s" />
        </div>
      </div>

      {/* Pre-Market Read — the one-glance "so what do I do?" */}
      <div className="pm-read">
        <div className="pm-read-l">
          <span className="pm-read-tag mono">PRE-MARKET READ</span>
          <span className="pm-read-stance mono">STAND ASIDE · WAIT FOR 09:45</span>
        </div>
        <div className="pm-read-body mono">
          Futures firm, <b className="up">risk-on tilt</b> (Tech +1.4% / Energy +2.1%) — but <b className="warn">CPI prints 08:30</b> and
          can override every single-name thesis, so keep risk light into the number. No clean pre-market <b>buy</b>: the big movers
          (CRWV +9%, GENO −6%) are <b className="warn">earnings-gap blackout</b> — no fresh swing entries. Your held <b className="cop">BORA</b> reports BMO
          and gaps +1.8% — that's today's first risk to manage. <b className="cop">Action:</b> watch, don't chase; let CPI + the 09:45 range print, then revisit Signal Scanner.
        </div>
        <div className="pm-read-chips">
          <span className="pm-read-chip pm-read-chip--gn">REGIME · RISK-ON</span>
          <span className="pm-read-chip pm-read-chip--rd">MACRO · CPI 08:30</span>
          <span className="pm-read-chip pm-read-chip--amb">2 EARNINGS BLACKOUT</span>
          <span className="pm-read-chip pm-read-chip--cy">1 BOOK REPORTER · BORA</span>
          <span className="pm-read-chip">0 FRESH BUYS</span>
        </div>
      </div>

      {/* Futures / risk tape */}
      <div className="pm-tape">
        {PM_FUT.map(([s, l, v, t], i) => (
          <div key={i} className={`pm-fut pm-fut--${t}`}>
            <span className="pm-fut-s mono">{s}</span>
            <span className={`pm-fut-v mono kpi-tone--${t}`}>{v}</span>
            <span className="pm-fut-l mono dim2">{l}</span>
          </div>
        ))}
      </div>

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
              <td className="r mono tabular dim">${t.prevClose.toFixed(2)}</td>
              <td className="r mono tabular">${t.last.toFixed(2)}</td>
              <td className={`r mono tabular ${t.gap>=0?"up":"dn"}`} data-field="schwab.quote.pre.gap_pct"><b>{t.gap>=0?"+":""}{t.gap.toFixed(1)}%</b></td>
              <td className="r mono tabular" data-field="schwab.quote.pre.volume">{t.pmVol.toFixed(1)}M</td>
              <td className={`r mono tabular ${t.pmVol/t.adv>=2?"up":"dim"}`}>{(t.pmVol/t.adv).toFixed(1)}×</td>
              <td><Pill tone={t.catTone} small>{t.cat}</Pill></td>
              <td><span className={`pm-taxon pm-tax--${t.taxon==="GAP & GO"?"gn":t.taxon==="BREAKDOWN"?"rd":t.taxon==="EXHAUSTION"?"amb":"ink"}`}>{t.taxon}</span></td>
              <td className={`r mono tabular ${t.fillProb>=60?"amb":"dim"}`}>{t.fillProb}%</td>
              <td className="r mono tabular dim">${t.pmLow.toFixed(0)}–${t.pmHigh.toFixed(0)}</td>
              <td className="r mono dim">›</td>
            </tr>
          ))}</tbody>
        </table>
      </div>

      {/* High-value cockpit panels */}
      <div className="pm-panels">
        <div className="lab-card">
          <div className="lab-card-h mono">⚠ MACRO CALENDAR · pre-open prints</div>
          <div className="pm-macro">
            {[
              ["08:30","CPI Core MoM","HIGH","+0.3%","+0.3%","amb"],
              ["08:30","Jobless Claims","MED","218k","221k","ink"],
              ["10:00","FOMC Speak · Powell","HIGH","—","—","amb"],
              ["—","NFP (Fri)","HIGH","185k","175k","rd"],
            ].map((m,i)=>(
              <div key={i} className={`pm-macro-row pm-macro--${m[5]}`}>
                <span className="mono pm-macro-t">{m[0]}</span>
                <span className="mono pm-macro-e">{m[1]}</span>
                <Pill tone={m[2]==="HIGH"?"rd":m[2]==="MED"?"amb":"ink"} small>{m[2]}</Pill>
                <span className="mono dim2 pm-macro-f">fcst {m[3]} · prior {m[4]}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="lab-card">
          <div className="lab-card-h mono">📊 EARNINGS REPORTERS · overnight + BMO</div>
          <table className="dtable wsx-tbl pm-mini-tbl">
            <thead><tr><th>Sym</th><th>When</th><th className="r">EPS</th><th className="r">Surprise</th><th className="r">React</th></tr></thead>
            <tbody>{[
              ["CRWV","AMC","$0.91","+8.3%","+9.2%","gn"],
              ["GENO","AMC","$0.62","−4.6%","−6.1%","rd"],
              ["TURM","BMO","$0.48","+2.1%","+1.4%","gn"],
              ["BORA","BMO","$1.04","+3.8%","+4.0%","gn"],
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

        <div className="lab-card">
          <div className="lab-card-h mono">💼 YOUR BOOK · pre-market exposure</div>
          <div className="pm-book">
            {[
              ["BORA","+1.8%","+$311","held · earnings BMO","gn"],
              ["FLNX","−0.4%","−$40","held","rd"],
              ["INPR","+0.2%","+$11","held","gn"],
            ].map((p,i)=>(
              <div key={i} className="pm-book-row" onClick={()=>onTicker(p[0])}>
                <span className="mono"><b>{p[0]}</b></span>
                <span className={`mono ${p[1].startsWith("+")?"up":"dn"}`}>{p[1]}</span>
                <span className={`mono ${p[2].startsWith("+")?"up":"dn"}`}>{p[2]}</span>
                <span className="mono dim2">{p[3]}</span>
              </div>
            ))}
            <div className="pm-book-net mono"><span className="dim2">Overnight P&L</span> <b className="up">+$282</b> <span className="dim2">· 1 reporter (BORA) · watch gap</span></div>
          </div>
        </div>

        <div className="lab-card">
          <div className="lab-card-h mono">🔥 SECTOR PRE-MARKET HEAT</div>
          <div className="pm-secheat">
            {[["Tech","+1.4%","gn",4],["Energy","+2.1%","gn",2],["Materials","+0.9%","gn",3],["Healthcare","−0.8%","rd",2],["Financials","−0.3%","rd",1],["Cons. Disc","+0.2%","ink",1]].map((s,i)=>(
              <div key={i} className={`pm-sec pm-sec--${s[2]}`}><span className="mono pm-sec-n">{s[0]}</span><span className={`mono kpi-tone--${s[2]}`}>{s[1]}</span><span className="mono dim2">{s[3]} gappers</span></div>
            ))}
          </div>
          <div className="lab-verdict mono dim2">Tech + Energy gapping together = risk-on rotation, not idiosyncratic. Trade the sector, not just the name.</div>
        </div>

        <div className="lab-card">
          <div className="lab-card-h mono">📈 GAP STATISTICS · backtested edge</div>
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
          <div className="lab-verdict mono dim2">Big up-gaps (&gt;5%) only fill 38% — they tend to run. Big down-gaps fill 44%. Source: 10y EODHD gap study.</div>
        </div>

        <div className="lab-card">
          <div className="lab-card-h mono">📰 NEWS WIRE · gapper headlines</div>
          <div className="pm-wire">
            {[
              ["06:42","CRWV","Beats Q1, raises FY guide on data-center demand","gn"],
              ["06:18","GENO","Phase-2 endpoint missed; shares slide pre-market","rd"],
              ["05:50","ARCM","Upgraded to Buy at Goldman, PT $78","gn"],
              ["05:12","XLE","Crude jumps 2% on supply headline — energy bid","gn"],
            ].map((n,i)=>(
              <div key={i} className={`pm-wire-row pm-wire--${n[3]}`} onClick={()=>onTicker(n[1])}>
                <span className="mono dim2 pm-wire-t">{n[0]}</span>
                <span className="mono pm-wire-s">{n[1]}</span>
                <span className="mono pm-wire-h">{n[2]}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="pm-gameplan mono">
        <span className="pm-gp-tag">OPEN GAMEPLAN</span>
        <span className="pm-gp-txt">Don't chase gaps &gt;3% in the first 5 min — wait for the 09:45 range to set. Earnings-gap names = no fresh swing entries (blackout). Size pre-market fills at half; spreads are wide before 09:30. Macro at 08:30 (CPI) can override every single-name thesis — flat risk into the print if unsure.</span>
      </div>

      <div className="pm-note mono dim2">
        Gap % &amp; PM volume from <b>Schwab /markets/quotes</b> (pre-session, 5s poll) · catalyst tags + news from <b>EODHD /news + /calendar</b> ·
        gap taxonomy from gap size × PM-RVOL × range · gap stats from 10y EODHD study · earnings-gap names blocked (blackout).
      </div>
    </div>
  );
}

window.SurfacePreMarket = SurfacePreMarket;

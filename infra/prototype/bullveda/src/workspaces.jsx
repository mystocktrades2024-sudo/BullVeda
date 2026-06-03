// workspaces.jsx — config-driven rich workspace engine for Part-2 sidebar tabs.
// One renderer; many configs. Each renders: header + KPI strip + sortable table + side rail.
// Data shaped as if from EODHD All-In-One + Schwab.

const { useState: useWS, useMemo: useWSm } = React;

// ── shared synthetic universe (EODHD-shaped) ──
const WS_UNIV = (() => {
  const base = HEATMAP.map(([sym, sector, mcap, chg]) => {
    const code = sym.charCodeAt(0) + sym.charCodeAt(1);
    const w = WATCHLIST.find(x => x.sym === sym);
    return {
      sym, sector, mcap, chg,
      name: w?.name || `${sector} Corp`,
      price: w?.price || (20 + code % 220),
      score: w?.score || Math.max(28, Math.min(94, 50 + Math.round(chg * 5))),
      verdict: w?.verdict || (chg > 1.5 ? "BUY" : chg < -1 ? "AVOID" : "WATCH"),
      setup: w?.setup || (chg > 1.5 ? "Continuation" : chg > 0 ? "Pullback" : "Distribution"),
      rvol: (0.6 + code % 14 / 10),
      rs: Math.max(15, Math.min(99, 45 + Math.round(chg * 6))),
      iv: 28 + code % 30,
      wlb: Math.max(30, Math.min(70, 45 + Math.round((w?.score || 60) - 55))),
      er: 2 + code % 70,
      insider: (code % 9) - 4,
      pe: 12 + code % 30,
      fwdPe: 10 + code % 24,
      div: ((code % 40) / 10).toFixed(1),
      pf: (1 + (code % 18) / 10).toFixed(2),
      mom: chg + (code % 8) - 3,
    };
  });
  return base;
})();

const tone = (v, hi, lo) => v >= hi ? "gn" : v <= lo ? "rd" : "amb";

// ── per-workspace configs ──
const WS_CFG = {
  "elite": {
    title: "Elite Picks", eyebrow: "5-PILLAR COMPOSITE · SCORE ≥ 75",
    sub: "all-pillar green · Wilson LB ≥ 50% · regime-fit", src: "scan · last_bundle.json + setup_stats",
    accent: "violet",
    filter: u => u.filter(r => r.score >= 72).sort((a,b)=>b.score-a.score),
    kpis: rows => [
      ["ELITE", rows.length, "violet", "score ≥ 72"],
      ["AVG SCORE", Math.round(rows.reduce((s,r)=>s+r.score,0)/(rows.length||1)), "gn", "composite"],
      ["AVG WILSON", Math.round(rows.reduce((s,r)=>s+r.wlb,0)/(rows.length||1))+"%", "gn", "LB · validated"],
      ["ALL-GREEN", rows.filter(r=>r.score>=80).length, "gn", "5 of 5 pillars"],
    ],
    cols: ["sym","name","sector","score","verdict","rr","wlb","rs","setup"],
  },
  "momentum": {
    title: "Momentum", eyebrow: "RELATIVE STRENGTH · 1M–3M",
    sub: "leaders by RS rank · RVOL surge · trend persistence", src: "EODHD /technical · RS computed",
    accent: "copper",
    filter: u => u.filter(r => r.mom > 0).sort((a,b)=>b.rs-a.rs),
    kpis: rows => [
      ["LEADERS", rows.length, "copper", "RS-positive"],
      ["AVG RS", Math.round(rows.reduce((s,r)=>s+r.rs,0)/(rows.length||1)), "gn", "vs SPX"],
      ["SURGING", rows.filter(r=>r.rvol>=1.5).length, "amb", "RVOL ≥ 1.5×"],
      ["NEW HIGHS", rows.filter(r=>r.rs>=90).length, "gn", "RS ≥ 90"],
    ],
    cols: ["sym","name","rs","rvol","chg","mom","score","setup"],
  },
  "buy": {
    title: "BUY Candidates", eyebrow: "PASSED ALL GATES",
    sub: "9–10 of 10 rule gates · ranked by R × Wilson LB", src: "rule engine · last_bundle",
    accent: "gn",
    filter: u => u.filter(r => r.verdict === "BUY").sort((a,b)=>b.score-a.score),
    kpis: rows => [
      ["BUY", rows.length, "gn", "gated"],
      ["AVG R:R", (rows.reduce((s,r)=>s+(1+(r.score-50)/30),0)/(rows.length||1)).toFixed(2), "gn", "to T1"],
      ["ER ≤ 10d", rows.filter(r=>r.er<=10).length, "amb", "cap size"],
      ["AVG WILSON", Math.round(rows.reduce((s,r)=>s+r.wlb,0)/(rows.length||1))+"%", "gn", "LB"],
    ],
    cols: ["sym","name","price","chg","rr","wlb","er","setup"],
  },
  "killed": {
    title: "Killed / AVOID", eyebrow: "FAILED GATES · DO NOT TRADE",
    sub: "setups that broke · distribution · failed breakouts", src: "rule engine · kill list",
    accent: "rd",
    filter: u => u.filter(r => r.verdict === "AVOID").sort((a,b)=>a.score-b.score),
    kpis: rows => [
      ["KILLED", rows.length, "rd", "this scan"],
      ["DISTRIB.", rows.filter(r=>r.chg<-1).length, "rd", "selling"],
      ["FAILED BO", rows.filter(r=>r.setup.includes("Distrib")).length, "amb", "breakdown"],
      ["AVG SCORE", Math.round(rows.reduce((s,r)=>s+r.score,0)/(rows.length||1)), "rd", "sub-gate"],
    ],
    cols: ["sym","name","sector","score","chg","verdict","why"],
  },
  "options-flow": {
    title: "Options Flow", eyebrow: "UNUSUAL ACTIVITY · DEALER POSITIONING",
    sub: "block prints · sweep detection · call/put premium imbalance", src: "Schwab /options/chains + UOA",
    accent: "amb",
    filter: u => [...u].sort((a,b)=>b.iv-a.iv),
    kpis: rows => [
      ["UOA PRINTS", 42, "amb", "today"],
      ["CALL FLOW", "$284M", "gn", "premium 5d"],
      ["PUT FLOW", "$161M", "rd", "premium 5d"],
      ["NET GEX", "+1.2B", "gn", "dealer gamma"],
    ],
    cols: ["sym","side","strike","exp","prem","iv","oi","note"],
    optionRows: true,
  },
  "earnings": {
    title: "Earnings", eyebrow: "CALENDAR · IMPLIED MOVE · ESP",
    sub: "next-14d reporters · beat-probability · pre-ER drift", src: "EODHD /earnings + Zacks ESP",
    accent: "amb",
    filter: u => u.filter(r => r.er <= 21).sort((a,b)=>a.er-b.er),
    kpis: rows => [
      ["NEXT 14D", rows.filter(r=>r.er<=14).length, "amb", "reporting"],
      ["TODAY", rows.filter(r=>r.er<=1).length, "rd", "BMO/AMC"],
      ["AVG IMPLIED", "±7.8%", "amb", "ATM straddle"],
      ["+ESP", rows.filter(r=>r.score>60).length, "gn", "beat-skew"],
    ],
    cols: ["sym","name","er","esp","implied","beat","verdict"],
  },
  "sector-etf": {
    title: "Sector ETFs · Industries", eyebrow: "ROTATION HEATMAP · RS RANK",
    sub: "11 GICS sectors · relative strength · breadth", src: "EODHD /eod sector ETFs",
    accent: "cy",
    sectorRows: true,
    kpis: () => [
      ["LEADER", "XLB +1.2%", "gn", "materials"],
      ["LAGGARD", "XLF −0.4%", "rd", "financials"],
      ["RISK-ON", "5 / 11", "gn", "above 50-DMA"],
      ["BREADTH", "1.84", "gn", "A/D"],
    ],
    cols: ["sector","etf","chg","rs","breadth","trend"],
  },
  "themes": {
    title: "Themes", eyebrow: "NARRATIVE BASKETS · MOMENTUM",
    sub: "AI · reshoring · GLP-1 · nuclear · quantum · defense", src: "curated baskets · RS-weighted",
    accent: "violet",
    themeRows: true,
    kpis: () => [
      ["THEMES", 6, "violet", "active"],
      ["HOT", "AI Infra +4.2%", "gn", "leader"],
      ["MEMBERS", 84, "ink", "tickers"],
      ["FLOWS", "+$2.1B", "gn", "5d net"],
    ],
    cols: ["theme","members","chg","leader","rs","flow"],
  },
  "strategies": {
    title: "Strategies", eyebrow: "SLEEVE LIBRARY · LIVE EDGE",
    sub: "11 strategy families · Wilson LB · profit factor · decay", src: "setup_stats.json · walk-forward",
    accent: "copper",
    stratRows: true,
    kpis: () => [
      ["SLEEVES", 11, "copper", "active"],
      ["BEST WR", "Cont. BO 62%", "gn", "Wilson 48%"],
      ["AVG PF", "1.64", "gn", "haircut"],
      ["DECAYING", 2, "amb", "watch"],
    ],
    cols: ["strat","n","wr","wilson","pf","medR","decay"],
  },
  "leveraged": {
    title: "Leveraged · ETFs", eyebrow: "3× / 2× · DECAY-AWARE",
    sub: "leveraged & inverse · path-dependency warnings", src: "EODHD /eod · leverage factor",
    accent: "rd",
    filter: u => [...u].sort((a,b)=>Math.abs(b.chg)-Math.abs(a.chg)).slice(0,14),
    kpis: () => [
      ["INSTRUMENTS", 24, "rd", "3×/2×"],
      ["DECAY ALERT", 6, "amb", "hold > 5d"],
      ["BEST 1D", "+9.4%", "gn", "TQQQ"],
      ["WORST 1D", "−8.1%", "rd", "SQQQ"],
    ],
    cols: ["sym","name","chg","rvol","note"],
  },
  "crypto": {
    title: "Crypto", eyebrow: "MAJORS + ALTS · 24/7",
    sub: "spot + perp funding · BTC dominance · regime", src: "EODHD crypto + Schwab",
    accent: "amb",
    cryptoRows: true,
    kpis: () => [
      ["BTC", "$71,240", "gn", "+2.1%"],
      ["ETH", "$3,840", "gn", "+1.6%"],
      ["DOMINANCE", "54.2%", "ink", "BTC.D"],
      ["FUNDING", "+0.012%", "amb", "perp 8h"],
    ],
    cols: ["sym","name","price","chg","vol","funding"],
  },
  "premarket": {
    title: "Pre-Market", eyebrow: "GAPPERS · NEWS-DRIVEN",
    sub: "pre 09:30 movers · gap % · catalyst · volume", src: "Schwab /quotes pre-session",
    accent: "violet",
    filter: u => [...u].sort((a,b)=>Math.abs(b.chg)-Math.abs(a.chg)).slice(0,16),
    kpis: rows => [
      ["GAPPERS", rows.length, "violet", "> 2% gap"],
      ["GAP UP", rows.filter(r=>r.chg>0).length, "gn", ""],
      ["GAP DOWN", rows.filter(r=>r.chg<0).length, "rd", ""],
      ["NEWS-DRIVEN", 7, "amb", "catalyst"],
    ],
    cols: ["sym","name","chg","rvol","catalyst"],
  },
  "macro": {
    title: "Macro · Events", eyebrow: "REGIME · CALENDAR · CROSS-ASSET",
    sub: "FOMC · CPI · PCE · NFP · yields · surprise reactions", src: "EODHD economic calendar",
    accent: "cy", macroRows: true,
    kpis: () => [
      ["REGIME", "RISK ON", "gn", "bull · low-vol"],
      ["NEXT", "FOMC 14:00", "amb", "today"],
      ["VIX", "16.3", "gn", "−1.8%"],
      ["10Y", "4.32%", "gn", "−14bp 5d"],
    ],
    cols: ["when","event","impact","forecast","prior","reaction"],
  },
  "events": {
    title: "Events · IPO / Splits", eyebrow: "CORP ACTIONS",
    sub: "IPOs · splits · spinoffs · index adds", src: "EODHD /calendar",
    accent: "info", eventRows: true,
    kpis: () => [
      ["IPOs 5D", 4, "info", "pricing"],
      ["SPLITS", 2, "ink", "ex-date"],
      ["INDEX ADD", 1, "gn", "S&P add"],
      ["SPINOFFS", 1, "amb", ""],
    ],
    cols: ["date","sym","type","detail","impact"],
  },
  "performance": {
    title: "Performance", eyebrow: "EQUITY CURVE · ATTRIBUTION",
    sub: "P&L by sleeve · Sharpe · drawdown · vs SPY", src: "portfolio_state · trade log",
    accent: "gn", perfRows: true,
    kpis: () => [
      ["YTD", "+12.27%", "gn", "vs SPY +9.4%"],
      ["SHARPE", "1.84", "gn", "annualized"],
      ["MAX DD", "−2.1%", "rd", "peak-trough"],
      ["WIN RATE", "61.7%", "gn", "n=47"],
    ],
    cols: ["sleeve","trades","wr","pf","pnl","contrib"],
  },
  "accuracy": {
    title: "Accuracy", eyebrow: "CALIBRATION · BRIER · RELIABILITY",
    sub: "predicted vs realized · per-bucket calibration", src: "ml_edge_predictions · holdout",
    accent: "violet", accuracyRows: true,
    kpis: () => [
      ["BRIER", "0.21", "gn", "lower better"],
      ["ECE", "0.04", "gn", "calibrated"],
      ["HOLDOUT WR", "61.7%", "gn", "OOS"],
      ["DRIFT KS", "0.08", "gn", "below alert"],
    ],
    cols: ["bucket","predicted","realized","n","gap"],
  },
  "factor-exposure": {
    title: "Factor Exposure", eyebrow: "BOOK BETAS · STYLE TILTS",
    sub: "momentum · value · quality · size · vol loadings", src: "factor decomposition",
    accent: "cy", factorRows: true,
    kpis: () => [
      ["MOMENTUM", "+0.80", "amb", "high tilt"],
      ["QUALITY", "+0.41", "gn", ""],
      ["VALUE", "−0.08", "rd", "growth-lean"],
      ["NET β", "0.93", "cy", "to SPX"],
    ],
    cols: ["factor","exposure","cap","pct","contrib"],
  },
  "leaders": {
    title: "Leaders Board", eyebrow: "RANKED OPERATORS · VERIFIED",
    sub: "public track records · Wilson-validated · tier-gated", src: "leaderboard · attested",
    accent: "copper", leaderRows: true,
    kpis: () => [
      ["RANKED", 248, "copper", "operators"],
      ["YOUR RANK", "#34", "gn", "top 14%"],
      ["TOP WR", "71.2%", "gn", "verified"],
      ["VERIFIED", 86, "info", "attested"],
    ],
    cols: ["rank","handle","ytd","wr","sharpe","verified"],
  },
  "pairs": {
    title: "Pairs Trading", eyebrow: "COINTEGRATION · Z-SCORE",
    sub: "mean-reverting pairs · spread z · half-life", src: "stat-arb engine",
    accent: "info", pairRows: true,
    kpis: () => [
      ["PAIRS", 12, "info", "cointegrated"],
      ["SIGNAL", 3, "gn", "z > 2"],
      ["AVG HALF-LIFE", "6.2d", "ink", "reversion"],
      ["BEST SHARPE", "2.1", "gn", "KO/PEP"],
    ],
    cols: ["pair","z","halflife","corr","signal"],
  },
};

const WS_LABELS = {
  "watchlist": "Watchlist", "portfolio-srf": "Portfolio", "screener": "Screener",
  "alerts": "Alerts", "news": "News · Sentiment", "insider": "Insider Trading",
  "journal": "Trade Journal", "social": "Social Sentiment", "settings": "Settings",
  "status": "System Status",
};

function WorkspaceSurface({ id, onTicker }) {
  const cfg = WS_CFG[id];
  const [sort, setSort] = useWS({ col: "score", dir: -1 });
  const rows = useWSm(() => (cfg && cfg.filter ? cfg.filter(WS_UNIV) : WS_UNIV).slice(0, 40), [id]);
  if (!cfg) return <WorkspaceStub id={id} />;
  const kpis = cfg.kpis ? cfg.kpis(rows) : [];

  return (
    <div className={`surface wsx wsx--${cfg.accent}`}>
      <div className="wsx-hdr">
        <div className="wsx-hdr-l">
          <div className="wsx-eyebrow mono">{cfg.eyebrow}</div>
          <h1 className="wsx-title mono">{cfg.title}</h1>
          <div className="wsx-sub mono dim2">{cfg.sub}</div>
        </div>
        <div className="wsx-hdr-r">
          <FreshnessPill state="live" age="18s" />
          <span className="mono dim2">src · {cfg.src}</span>
        </div>
      </div>

      <div className="wsx-kpis">
        {kpis.map((k, i) => (
          <div key={i} className={`wsx-kpi wsx-kpi--${k[2]}`}>
            <div className="wsx-kpi-l mono">{k[0]}</div>
            <div className={`wsx-kpi-v mono kpi-tone--${k[2]}`}>{k[1]}</div>
            <div className="wsx-kpi-s mono dim2">{k[3]}</div>
          </div>
        ))}
      </div>

      <div className="wsx-body">
        <WSTable cfg={cfg} rows={rows} sort={sort} setSort={setSort} onTicker={onTicker} />
      </div>
    </div>
  );
}

// ── specialized + generic table ──
function WSTable({ cfg, rows, sort, setSort, onTicker }) {
  // specialized row renderers
  if (cfg.optionRows) return <WSOptions onTicker={onTicker} />;
  if (cfg.sectorRows) return <WSSectors />;
  if (cfg.themeRows) return <WSThemes />;
  if (cfg.stratRows) return <WSStrats />;
  if (cfg.cryptoRows) return <WSCrypto />;
  if (cfg.macroRows) return <WSMacro />;
  if (cfg.eventRows) return <WSEvents onTicker={onTicker} />;
  if (cfg.perfRows) return <WSPerf />;
  if (cfg.accuracyRows) return <WSAccuracy />;
  if (cfg.factorRows) return <WSFactor />;
  if (cfg.leaderRows) return <WSLeaders />;
  if (cfg.pairRows) return <WSPairs />;

  // generic ticker table
  const HEAD = {
    sym:"Sym", name:"Name", sector:"Sector", price:"Price", chg:"1D %", score:"Score",
    verdict:"Verdict", rr:"R:R", wlb:"Wilson", rs:"RS", iv:"IV", er:"ER d", setup:"Setup",
    mom:"Mom", why:"Why killed",
  };
  const sorted = useWSm(() => {
    const c = sort.col;
    return [...rows].sort((a,b) => {
      const av=a[c], bv=b[c]; const an=parseFloat(av), bn=parseFloat(bv);
      if (!isNaN(an)&&!isNaN(bn)) return (an-bn)*sort.dir;
      return String(av).localeCompare(String(bv))*sort.dir;
    });
  }, [rows, sort]);
  const cell = (r, c) => {
    switch(c){
      case "sym": return <td className="mono"><b>{r.sym}</b></td>;
      case "name": return <td className="dim">{r.name}</td>;
      case "sector": return <td className="mono dim2">{r.sector}</td>;
      case "price": return <td className="r mono tabular">${r.price.toFixed(2)}</td>;
      case "chg": return <td className={`r mono tabular ${r.chg>=0?"up":"dn"}`}>{r.chg>=0?"+":""}{r.chg.toFixed(2)}%</td>;
      case "score": return <td className="r mono tabular"><b>{r.score}</b></td>;
      case "verdict": return <td><Pill tone={r.verdict==="BUY"?"gn":r.verdict==="AVOID"?"rd":"amb"} small>{r.verdict}</Pill></td>;
      case "rr": return <td className="r mono tabular">{(1+(r.score-50)/30).toFixed(2)}</td>;
      case "wlb": return <td className={`r mono tabular ${r.wlb>=50?"up":"warn"}`}>{r.wlb}%</td>;
      case "rs": return <td className="r mono tabular">{r.rs}</td>;
      case "iv": return <td className="r mono tabular dim">{r.iv}%</td>;
      case "er": return <td className={`r mono tabular ${r.er<=10?"warn":"dim"}`}>{r.er<=70?r.er:"—"}</td>;
      case "setup": return <td className="mono dim">{r.setup}</td>;
      case "mom": return <td className={`r mono tabular ${r.mom>=0?"up":"dn"}`}>{r.mom>=0?"+":""}{r.mom.toFixed(1)}</td>;
      case "why": return <td className="mono dim">{r.chg<-1?"distribution":"failed breakout"}</td>;
      default: return <td>—</td>;
    }
  };
  const numeric = ["price","chg","score","rr","wlb","rs","iv","er","mom"];
  return (
    <table className="dtable wsx-tbl">
      <thead><tr>
        {cfg.cols.map(c => (
          <th key={c} className={`${numeric.includes(c)?"r":""} wsx-th ${sort.col===c?"is-active":""}`}
              onClick={() => setSort(s => s.col===c?{col:c,dir:-s.dir}:{col:c,dir:-1})}>
            {HEAD[c]||c}{sort.col===c && <span className="wsx-arr mono">{sort.dir>0?"▲":"▼"}</span>}
          </th>
        ))}
      </tr></thead>
      <tbody>
        {sorted.map((r,i) => (
          <tr key={r.sym+i} onClick={() => onTicker(r.sym)}>{cfg.cols.map(c => <React.Fragment key={c}>{cell(r,c)}</React.Fragment>)}</tr>
        ))}
      </tbody>
    </table>
  );
}

// ── specialized renderers ──
function WSOptions({ onTicker }) {
  const rows = [
    ["ARGN","CALL","$220","Jul 18","$1.42","48%","1,120","BTO · 3.8× OI","gn"],
    ["ARCM","CALL","$70","Jul 18","$1.10","49%","940","sweep","gn"],
    ["DRSH","CALL","$60","Aug 15","$0.88","44%","620","pre-ER","gn"],
    ["MERC","PUT","$16","Jul 18","$0.74","58%","1,240","hedge","rd"],
    ["BIVO","PUT","$70","Jun 20","$2.10","62%","480","bearish","rd"],
    ["GENO","CALL","$32","Jun 20","$1.86","55%","760","gamma","gn"],
  ];
  return (
    <table className="dtable wsx-tbl">
      <thead><tr><th>Sym</th><th>Side</th><th>Strike</th><th>Exp</th><th className="r">Prem</th><th className="r">IV</th><th className="r">OI</th><th>Note</th></tr></thead>
      <tbody>{rows.map((r,i)=>(
        <tr key={i} onClick={()=>onTicker(r[0])}>
          <td className="mono"><b>{r[0]}</b></td>
          <td><Pill tone={r[1]==="CALL"?"gn":"rd"} small>{r[1]}</Pill></td>
          <td className="mono">{r[2]}</td><td className="mono dim">{r[3]}</td>
          <td className="r mono tabular">{r[4]}</td><td className="r mono tabular">{r[5]}</td>
          <td className="r mono tabular dim">{r[6]}</td>
          <td className={`mono ${r[8]==="gn"?"up":"dn"}`}>{r[7]}</td>
        </tr>))}</tbody>
    </table>
  );
}
function WSSectors() {
  const rows = [
    ["Materials","XLB",1.2,88,"strong","up"],["Energy","XLE",2.9,82,"strong","up"],
    ["Technology","XLK",0.8,76,"firm","up"],["Healthcare","XLV",0.4,61,"neutral","flat"],
    ["Industrials","XLI",0.6,58,"neutral","flat"],["Consumer Disc.","XLY",-0.3,49,"soft","flat"],
    ["Comm.","XLC",0.2,52,"neutral","flat"],["Staples","XLP",-0.1,44,"soft","flat"],
    ["Utilities","XLU",-0.5,38,"weak","down"],["Real Estate","XLRE",-0.7,32,"weak","down"],
    ["Financials","XLF",-0.4,41,"soft","down"],
  ];
  return (
    <table className="dtable wsx-tbl">
      <thead><tr><th>Sector</th><th>ETF</th><th className="r">1D %</th><th className="r">RS</th><th>Breadth</th><th>Trend</th></tr></thead>
      <tbody>{rows.map((r,i)=>(
        <tr key={i}>
          <td className="mono">{r[0]}</td><td className="mono dim2">{r[1]}</td>
          <td className={`r mono tabular ${r[2]>=0?"up":"dn"}`}>{r[2]>=0?"+":""}{r[2]}%</td>
          <td className="r mono tabular"><b>{r[3]}</b></td>
          <td className="mono dim">{r[4]}</td>
          <td><Pill tone={r[5]==="up"?"gn":r[5]==="down"?"rd":"amb"} small>{r[5]}</Pill></td>
        </tr>))}</tbody>
    </table>
  );
}
function WSThemes() {
  const rows = [["AI Infrastructure",18,4.2,"NVRH",92,"+$820M"],["Reshoring",14,2.1,"ARCM",78,"+$340M"],
    ["GLP-1 / Obesity",11,1.4,"GENO",71,"+$210M"],["Nuclear / SMR",9,3.1,"DRSH",84,"+$180M"],
    ["Quantum",8,-1.2,"KLYX",46,"−$60M"],["Defense",12,0.8,"ARGN",66,"+$120M"]];
  return (
    <table className="dtable wsx-tbl">
      <thead><tr><th>Theme</th><th className="r">Members</th><th className="r">1M %</th><th>Leader</th><th className="r">RS</th><th className="r">5d Flow</th></tr></thead>
      <tbody>{rows.map((r,i)=>(
        <tr key={i}><td className="mono"><b>{r[0]}</b></td><td className="r mono tabular dim">{r[1]}</td>
          <td className={`r mono tabular ${r[2]>=0?"up":"dn"}`}>{r[2]>=0?"+":""}{r[2]}%</td>
          <td className="mono">{r[3]}</td><td className="r mono tabular">{r[4]}</td>
          <td className={`r mono tabular ${r[5].startsWith("+")?"up":"dn"}`}>{r[5]}</td></tr>))}</tbody>
    </table>
  );
}
function WSStrats() {
  const rows = [["Continuation BO",47,"61.7%","47.7%","1.84","+0.72","stable"],
    ["VCP",38,"58.0%","45.0%","1.62","+0.61","stable"],["Pullback",52,"55.8%","44.0%","1.41","+0.48","stable"],
    ["Gap & Go",29,"51.7%","40.0%","1.28","+0.34","decaying"],["Mean Revert",41,"54.0%","43.0%","1.36","+0.41","stable"],
    ["Earnings Drift",22,"59.1%","44.0%","1.55","+0.58","decaying"]];
  return (
    <table className="dtable wsx-tbl">
      <thead><tr><th>Strategy</th><th className="r">n</th><th className="r">WR</th><th className="r">Wilson LB</th><th className="r">PF</th><th className="r">Med R</th><th>Edge</th></tr></thead>
      <tbody>{rows.map((r,i)=>(
        <tr key={i}><td className="mono"><b>{r[0]}</b></td><td className="r mono tabular dim">{r[1]}</td>
          <td className="r mono tabular up">{r[2]}</td><td className="r mono tabular">{r[3]}</td>
          <td className="r mono tabular">{r[4]}</td><td className="r mono tabular up">{r[5]}R</td>
          <td><Pill tone={r[6]==="stable"?"gn":"amb"} small>{r[6]}</Pill></td></tr>))}</tbody>
    </table>
  );
}
function WSCrypto() {
  const rows = [["BTC","Bitcoin","$71,240",2.1,"$42B","+0.012%"],["ETH","Ethereum","$3,840",1.6,"$18B","+0.008%"],
    ["SOL","Solana","$184",3.4,"$4.2B","+0.021%"],["AVAX","Avalanche","$38",-1.2,"$0.8B","−0.004%"],
    ["LINK","Chainlink","$18.4",0.9,"$0.6B","+0.006%"]];
  return (
    <table className="dtable wsx-tbl">
      <thead><tr><th>Sym</th><th>Name</th><th className="r">Price</th><th className="r">24h %</th><th className="r">Vol</th><th className="r">Funding</th></tr></thead>
      <tbody>{rows.map((r,i)=>(
        <tr key={i}><td className="mono"><b>{r[0]}</b></td><td className="dim">{r[1]}</td>
          <td className="r mono tabular">{r[2]}</td><td className={`r mono tabular ${r[3]>=0?"up":"dn"}`}>{r[3]>=0?"+":""}{r[3]}%</td>
          <td className="r mono tabular dim">{r[4]}</td><td className={`r mono tabular ${r[5].startsWith("+")?"up":"dn"}`}>{r[5]}</td></tr>))}</tbody>
    </table>
  );
}
function WSMacro() {
  const rows = [["TODAY 14:00","FOMC Minutes","HIGH","—","—","watch"],["May 30 08:30","PCE Core MoM","HIGH","+0.3%","+0.3%","±"],
    ["Jun 03","ISM Manufacturing","MED","49.5","49.2","±"],["Jun 05","ECB Rate Decision","HIGH","hold","hold","—"],
    ["Jun 07 08:30","NFP Payrolls","HIGH","185k","175k","±"]];
  return (
    <table className="dtable wsx-tbl">
      <thead><tr><th>When</th><th>Event</th><th>Impact</th><th className="r">Forecast</th><th className="r">Prior</th><th>Reaction</th></tr></thead>
      <tbody>{rows.map((r,i)=>(
        <tr key={i}><td className="mono dim2">{r[0]}</td><td className="mono">{r[1]}</td>
          <td><Pill tone={r[2]==="HIGH"?"amb":"ink"} small>{r[2]}</Pill></td>
          <td className="r mono tabular">{r[3]}</td><td className="r mono tabular dim">{r[4]}</td>
          <td className="mono dim">{r[5]}</td></tr>))}</tbody>
    </table>
  );
}
function WSEvents({ onTicker }) {
  const rows = [["May 30","CRWV","IPO","priced $40 · +18% open","high"],["Jun 02","ZOTR","Split","4:1 forward","med"],
    ["Jun 04","NEXO","Spinoff","spins NewCo","med"],["Jun 06","ARGN","Index Add","S&P 400 add","high"]];
  return (
    <table className="dtable wsx-tbl">
      <thead><tr><th>Date</th><th>Sym</th><th>Type</th><th>Detail</th><th>Impact</th></tr></thead>
      <tbody>{rows.map((r,i)=>(
        <tr key={i} onClick={()=>onTicker(r[1])}><td className="mono dim2">{r[0]}</td><td className="mono"><b>{r[1]}</b></td>
          <td><Pill tone="info" small>{r[2]}</Pill></td><td className="mono dim">{r[3]}</td>
          <td><Pill tone={r[4]==="high"?"amb":"ink"} small>{r[4]}</Pill></td></tr>))}</tbody>
    </table>
  );
}
function WSPerf() {
  const rows = [["Continuation BO",18,"66.7%","2.10","+$4,820","+38%"],["VCP",12,"58.3%","1.74","+$2,140","+17%"],
    ["Pullback",9,"55.6%","1.52","+$1,680","+13%"],["Earnings Drift",5,"60.0%","1.61","+$1,240","+10%"],
    ["Mean Revert",3,"33.3%","0.82","−$320","−3%"]];
  return (
    <table className="dtable wsx-tbl">
      <thead><tr><th>Sleeve</th><th className="r">Trades</th><th className="r">WR</th><th className="r">PF</th><th className="r">P&L</th><th className="r">Contrib</th></tr></thead>
      <tbody>{rows.map((r,i)=>(
        <tr key={i}><td className="mono"><b>{r[0]}</b></td><td className="r mono tabular dim">{r[1]}</td>
          <td className="r mono tabular">{r[2]}</td><td className={`r mono tabular ${parseFloat(r[3])>=1?"up":"dn"}`}>{r[3]}</td>
          <td className={`r mono tabular ${r[4].startsWith("+")?"up":"dn"}`}>{r[4]}</td>
          <td className={`r mono tabular ${r[5].startsWith("+")?"up":"dn"}`}>{r[5]}</td></tr>))}</tbody>
    </table>
  );
}
function WSAccuracy() {
  const rows = [["0–20%","12%","11%",84,"−1%"],["20–40%","31%","29%",142,"−2%"],["40–60%","52%","54%",210,"+2%"],
    ["60–80%","68%","66%",156,"−2%"],["80–100%","87%","85%",62,"−2%"]];
  return (
    <table className="dtable wsx-tbl">
      <thead><tr><th>Confidence bucket</th><th className="r">Predicted</th><th className="r">Realized</th><th className="r">n</th><th className="r">Gap</th></tr></thead>
      <tbody>{rows.map((r,i)=>(
        <tr key={i}><td className="mono">{r[0]}</td><td className="r mono tabular">{r[1]}</td>
          <td className="r mono tabular up">{r[2]}</td><td className="r mono tabular dim">{r[3]}</td>
          <td className="r mono tabular">{r[4]}</td></tr>))}</tbody>
    </table>
  );
}
function WSFactor() {
  const rows = [["Momentum","+0.80","1.00","80%","+0.34"],["Quality","+0.41","1.00","41%","+0.12"],
    ["Value","−0.08","0.50","−16%","−0.03"],["Size","−0.16","0.50","−32%","−0.05"],["Low-Vol","+0.22","0.40","55%","+0.08"]];
  return (
    <table className="dtable wsx-tbl">
      <thead><tr><th>Factor</th><th className="r">Exposure</th><th className="r">Cap</th><th className="r">% of cap</th><th className="r">Contrib</th></tr></thead>
      <tbody>{rows.map((r,i)=>(
        <tr key={i}><td className="mono">{r[0]}</td><td className={`r mono tabular ${parseFloat(r[1])>=0?"up":"dn"}`}>{r[1]}</td>
          <td className="r mono tabular dim">{r[2]}</td><td className="r mono tabular">{r[3]}</td>
          <td className={`r mono tabular ${parseFloat(r[4])>=0?"up":"dn"}`}>{r[4]}</td></tr>))}</tbody>
    </table>
  );
}
function WSLeaders() {
  const rows = [["1","@quantedge","+38.2%","71.2%","2.4","✓"],["2","@vol_harvest","+31.4%","66.8%","2.1","✓"],
    ["3","@basehunter","+28.1%","63.4%","1.9","✓"],["34","you · @jkairos","+12.3%","61.7%","1.84","✓"],
    ["35","@swingdesk","+11.9%","58.2%","1.6","—"]];
  return (
    <table className="dtable wsx-tbl">
      <thead><tr><th className="r">Rank</th><th>Handle</th><th className="r">YTD</th><th className="r">WR</th><th className="r">Sharpe</th><th>Verified</th></tr></thead>
      <tbody>{rows.map((r,i)=>(
        <tr key={i} className={r[1].includes("you")?"is-current":""}><td className="r mono"><b>#{r[0]}</b></td><td className="mono">{r[1]}</td>
          <td className="r mono tabular up">{r[2]}</td><td className="r mono tabular">{r[3]}</td>
          <td className="r mono tabular">{r[4]}</td><td className="mono">{r[5]==="✓"?<span className="up">✓ verified</span>:<span className="dim">—</span>}</td></tr>))}</tbody>
    </table>
  );
}
function WSPairs() {
  const rows = [["KO / PEP","+2.3","6.2d","0.91","SHORT spread"],["XLE / XLB","−2.1","8.4d","0.84","LONG spread"],
    ["NVRH / BIVO","+1.4","5.1d","0.78","watch"],["ARCM / TURM","−0.8","7.0d","0.88","neutral"]];
  return (
    <table className="dtable wsx-tbl">
      <thead><tr><th>Pair</th><th className="r">Z-score</th><th className="r">Half-life</th><th className="r">Corr</th><th>Signal</th></tr></thead>
      <tbody>{rows.map((r,i)=>(
        <tr key={i}><td className="mono"><b>{r[0]}</b></td><td className={`r mono tabular ${Math.abs(parseFloat(r[1]))>=2?"warn":"dim"}`}>{r[1]}</td>
          <td className="r mono tabular dim">{r[2]}</td><td className="r mono tabular">{r[3]}</td>
          <td><Pill tone={r[4].includes("SHORT")?"rd":r[4].includes("LONG")?"gn":"ink"} small>{r[4]}</Pill></td></tr>))}</tbody>
    </table>
  );
}

function WorkspaceStub({ id }) {
  const label = WS_LABELS[id] || id;
  return (
    <div className="surface wsx">
      <div className="wsx-hdr">
        <div className="wsx-hdr-l">
          <div className="wsx-eyebrow mono">WORKSPACE</div>
          <h1 className="wsx-title mono">{label}</h1>
          <div className="wsx-sub mono dim2">Surface registered in the IA · full module on the build roadmap.</div>
        </div>
        <FreshnessPill state="scaffold" />
      </div>
      <div className="wsx-stub-banner">
        <span>⚠</span>
        <span><b>Partial scaffolding</b> — this tab exists in the tier/IA map but its rich module isn't wired yet. Data wires from EODHD All-In-One + Schwab when built.</span>
      </div>
    </div>
  );
}

window.WorkspaceSurface = WorkspaceSurface;
window.WS_CFG_IDS = Object.keys(WS_CFG);

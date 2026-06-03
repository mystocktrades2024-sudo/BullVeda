// surface-etf-screener.jsx — full ETF universe screener.
// Searchable, filterable, sortable list across all categories with verdict + RS + trend.

const { useState: useEtf, useMemo: useEtfm } = React;

const ETF_UNIV = [
  // [sym, name, category, chg(1D), rs, aum$B, exp%, verdict, r1m, r6m, r1y, r5y, r10y] — returns = total %
  ["SPY","S&P 500","Broad Index",0.42,62,512,0.09,"WATCH", 2.1, 9.0, 16, 98, 245],
  ["QQQ","Nasdaq 100","Broad Index",0.84,74,268,0.20,"BUY", 3.2, 13, 24, 155, 430],
  ["IWM","Russell 2000","Broad Index",-0.21,44,62,0.19,"WATCH", -0.8, 4.0, 9, 52, 118],
  ["DIA","Dow 30","Broad Index",0.18,55,38,0.16,"WATCH", 1.4, 7.0, 13, 74, 185],
  ["VTI","Total Market","Broad Index",0.40,60,395,0.03,"WATCH", 2.0, 9.0, 16, 95, 235],
  ["RSP","S&P Equal-Wt","Broad Index",0.22,52,58,0.20,"WATCH", 1.1, 6.0, 11, 78, 175],
  ["XLK","Technology","Sector",1.8,88,72,0.09,"BUY", 4.2, 16, 32, 175, 520],
  ["XLB","Materials","Sector",1.2,84,9,0.09,"BUY", 2.6, 10, 14, 70, 135],
  ["XLE","Energy","Sector",2.9,82,40,0.09,"BUY", 3.8, 8.0, 6, 95, 70],
  ["XLI","Industrials","Sector",0.6,61,21,0.09,"WATCH", 1.2, 7.0, 13, 82, 165],
  ["XLV","Healthcare","Sector",0.4,58,40,0.09,"WATCH", 0.6, 3.0, 7, 48, 160],
  ["XLF","Financials","Sector",-0.4,41,45,0.09,"AVOID", -0.8, 5.0, 12, 72, 150],
  ["XLY","Consumer Disc","Sector",-0.3,49,22,0.09,"WATCH", -0.4, 6.0, 11, 58, 210],
  ["XLP","Staples","Sector",-0.1,44,16,0.09,"WATCH", 0.2, 2.0, 6, 32, 95],
  ["XLU","Utilities","Sector",-0.5,38,15,0.09,"AVOID", -1.1, 1.0, 9, 38, 110],
  ["XLRE","Real Estate","Sector",-0.7,32,7,0.09,"AVOID", -1.4, -2.0, 4, 18, 75],
  ["XLC","Communications","Sector",0.2,54,22,0.09,"WATCH", 1.8, 9.0, 19, 88, 130],
  ["MTUM","Momentum Factor","Factor",0.8,79,16,0.15,"BUY", 2.8, 12, 22, 96, 205],
  ["VLUE","Value Factor","Factor",-0.1,42,12,0.15,"WATCH", -0.2, 5.0, 10, 68, 120],
  ["QUAL","Quality Factor","Factor",0.5,64,42,0.15,"BUY", 2.1, 9.0, 17, 92, 220],
  ["USMV","Min Volatility","Factor",0.1,48,24,0.15,"WATCH", 0.8, 4.0, 9, 44, 135],
  ["SMH","Semiconductors","Thematic",1.9,90,24,0.35,"BUY", 5.1, 20, 42, 260, 780],
  ["ARKK","Innovation","Thematic",2.4,71,7,0.75,"WATCH", 4.8, 14, 28, -35, 95],
  ["XBI","Biotech","Thematic",-0.6,46,8,0.35,"AVOID", -1.2, 2.0, 5, -8, 85],
  ["TAN","Solar","Thematic",1.1,58,2,0.69,"WATCH", 2.4, -4.0, -12, -28, 60],
  ["IBB","Biotech (lg)","Thematic",-0.3,49,7,0.45,"WATCH", -0.6, 3.0, 6, 12, 95],
  ["HACK","Cybersecurity","Thematic",1.4,76,2,0.60,"BUY", 3.1, 13, 26, 88, 210],
  ["LIT","Lithium/Battery","Thematic",0.9,54,1.2,0.75,"WATCH", 1.8, -6.0, -18, 42, 120],
  ["TLT","20Y Treasury","Bonds",-0.5,34,48,0.15,"AVOID", -1.2, -3.0, -6, -38, -12],
  ["IEF","7-10Y Treasury","Bonds",-0.2,40,30,0.15,"WATCH", -0.6, -1.0, 1, -12, 6],
  ["HYG","High Yield","Bonds",0.1,52,17,0.49,"WATCH", 0.4, 3.0, 8, 14, 42],
  ["LQD","Inv-Grade Corp","Bonds",-0.2,44,32,0.14,"WATCH", -0.4, 1.0, 4, -6, 28],
  ["TIP","TIPS","Bonds",0.0,46,20,0.19,"WATCH", 0.2, 2.0, 5, 8, 22],
  ["GLD","Gold","Commodity",0.3,66,62,0.40,"BUY", 2.6, 14, 34, 78, 135],
  ["SLV","Silver","Commodity",0.5,61,12,0.50,"BUY", 3.2, 16, 38, 72, 95],
  ["USO","Crude Oil","Commodity",-0.9,38,1.5,0.60,"AVOID", -2.1, -6.0, -14, 48, -22],
  ["DBC","Commodities Basket","Commodity",-0.4,45,2,0.85,"WATCH", -0.8, 2.0, 4, 52, 18],
  ["EEM","Emerging Mkts","International",0.7,58,18,0.69,"WATCH", 1.4, 8.0, 14, 18, 52],
  ["EFA","Developed ex-US","International",0.3,54,52,0.32,"WATCH", 1.1, 7.0, 12, 42, 68],
  ["FXI","China Large-Cap","International",1.4,68,5,0.74,"BUY", 3.6, 18, 28, 8, 35],
  ["EWJ","Japan","International",-0.2,48,15,0.50,"WATCH", 0.4, 5.0, 10, 38, 95],
  ["INDA","India","International",1.1,72,9,0.64,"BUY", 2.2, 9.0, 16, 82, 145],
  ["TQQQ","3× Nasdaq","Leveraged",2.5,80,22,0.86,"WATCH", 8.4, 32, 58, 320, 2800],
  ["SOXL","3× Semis","Leveraged",5.7,84,11,0.94,"WATCH", 12.6, 44, 72, 180, 1900],
  ["SQQQ","-3× Nasdaq","Leveraged",-2.5,18,3,0.95,"AVOID", -9.1, -34, -52, -92, -99],
  ["UVXY","1.5× VIX","Leveraged",-4.1,12,0.6,0.95,"AVOID", -14.2, -48, -78, -98, -99.9],
];
const ETF_CATS = ["All","Broad Index","Sector","Factor","Thematic","Bonds","Commodity","International","Leveraged"];

function SurfaceEtfScreener({ onTicker }) {
  const [cat, setCat] = useEtf("All");
  const [q, setQ] = useEtf("");
  const [side, setSide] = useEtf("ALL");
  const [sort, setSort] = useEtf({ col: "rs", dir: -1 });

  const rows = useEtfm(() => {
    let r = ETF_UNIV.map(e => ({ sym:e[0], name:e[1], category:e[2], chg:e[3], rs:e[4], aum:e[5], exp:e[6], verdict:e[7], r1m:e[8], r6m:e[9], r1y:e[10], r5y:e[11], r10y:e[12] }));
    if (cat !== "All") r = r.filter(x => x.category === cat);
    if (side !== "ALL") r = r.filter(x => x.verdict === side);
    if (q) r = r.filter(x => (x.sym + x.name).toLowerCase().includes(q.toLowerCase()));
    return r.sort((a,b)=>{ const av=a[sort.col],bv=b[sort.col]; const an=+av,bn=+bv; if(!isNaN(an)&&!isNaN(bn))return (an-bn)*sort.dir; return String(av).localeCompare(String(bv))*sort.dir; });
  }, [cat, q, side, sort]);

  const TH = (col,l,r)=>(<th className={`${r?"r":""} wsx-th ${sort.col===col?"is-active":""}`} onClick={()=>setSort(s=>s.col===col?{col,dir:-s.dir}:{col,dir:-1})}>{l}{sort.col===col&&<span className="wsx-arr mono">{sort.dir>0?"▲":"▼"}</span>}</th>);
  const fmtRet = v => `${v >= 0 ? "+" : ""}${Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(1)}%`;
  const retCell = v => <td className={`r mono tabular ${v >= 0 ? "up" : "dn"}`}>{fmtRet(v)}</td>;

  return (
    <div className="surface wsx wsx--cy etf">
      <div className="wsx-hdr">
        <div className="wsx-hdr-l">
          <div className="wsx-eyebrow mono">FULL ETF UNIVERSE · {ETF_UNIV.length} INSTRUMENTS</div>
          <h1 className="wsx-title mono">ETF Screener</h1>
          <div className="wsx-sub mono dim2">all categories · RS-ranked · verdict-gated · AUM &amp; expense filtered · click to drill</div>
        </div>
        <div className="wsx-hdr-r"><FreshnessPill state="live" age="18s" /><span className="mono dim2">src · EODHD /eod + Schwab quotes</span></div>
      </div>

      <div className="wsx-kpis">
        <div className="wsx-kpi wsx-kpi--cy"><div className="wsx-kpi-l mono">UNIVERSE</div><div className="wsx-kpi-v mono kpi-tone--cy">{ETF_UNIV.length}</div><div className="wsx-kpi-s mono dim2">{ETF_CATS.length-1} categories</div></div>
        <div className="wsx-kpi wsx-kpi--gn"><div className="wsx-kpi-l mono">BULLISH</div><div className="wsx-kpi-v mono kpi-tone--gn">{ETF_UNIV.filter(e=>e[7]==="BUY").length}</div><div className="wsx-kpi-s mono dim2">RS-leaders</div></div>
        <div className="wsx-kpi wsx-kpi--amb"><div className="wsx-kpi-l mono">NEUTRAL</div><div className="wsx-kpi-v mono kpi-tone--amb">{ETF_UNIV.filter(e=>e[7]==="WATCH").length}</div><div className="wsx-kpi-s mono dim2">forming</div></div>
        <div className="wsx-kpi wsx-kpi--rd"><div className="wsx-kpi-l mono">BEARISH</div><div className="wsx-kpi-v mono kpi-tone--rd">{ETF_UNIV.filter(e=>e[7]==="AVOID").length}</div><div className="wsx-kpi-s mono dim2">laggards</div></div>
      </div>

      <div className="etf-filters">
        <div className="etf-cats">{ETF_CATS.map(c=><button key={c} className={`wl-chip ${cat===c?"is-on":""}`} onClick={()=>setCat(c)}>{c}</button>)}</div>
        <div className="ss2-side">{["BUY","WATCH","AVOID","ALL"].map(s=><button key={s} className={`ss2-side-btn ss2-side--${s.toLowerCase()} ${side===s?"is-on":""}`} onClick={()=>setSide(s)}>{s==="ALL"?"ALL":secBias(s)}</button>)}</div>
        <input className="wl-search mono" placeholder="⌕ ticker / name…" value={q} onChange={e=>setQ(e.target.value)} />
      </div>

      <div className="wsx-body etf-body">
        <table className="dtable wsx-tbl etf-tbl">
          <thead><tr>{TH("sym","Sym")}<th>Name</th>{TH("category","Category")}{TH("r1m","1M",true)}{TH("r6m","6M",true)}{TH("r1y","1Y",true)}{TH("r5y","5Y",true)}{TH("r10y","10Y",true)}{TH("rs","RS",true)}{TH("aum","AUM $B",true)}{TH("exp","Exp %",true)}<th>Bias</th><th></th></tr></thead>
          <tbody>{rows.map((t,i)=>(
            <tr key={t.sym+i} onClick={()=>onTicker(t.sym)}>
              <td className="mono"><b>{t.sym}</b></td>
              <td className="dim">{t.name}</td>
              <td className="mono dim2">{t.category}</td>
              {retCell(t.r1m)}{retCell(t.r6m)}{retCell(t.r1y)}{retCell(t.r5y)}{retCell(t.r10y)}
              <td className="r"><span className={`mo-rsbadge mo-rs--${t.rs>=70?"hot":t.rs>=50?"warm":"cool"}`}>{t.rs}</span></td>
              <td className="r mono tabular dim">{t.aum}</td>
              <td className="r mono tabular dim">{t.exp}</td>
              <td><Pill tone={secBiasTone(t.verdict)} small>{secBias(t.verdict)}</Pill></td>
              <td className="r mono dim">›</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <div className="pm-note mono dim2">
        Full ETF universe — broad index, sector, factor, thematic, bonds, commodity, international, leveraged. Bias = same 5-pillar engine applied to ETFs (RS + trend + flows).
        <b> Informational only · not investment advice</b> — it ranks relative strength so you choose where to research. Source: EODHD /eod + Schwab quotes.
      </div>
    </div>
  );
}

window.SurfaceEtfScreener = SurfaceEtfScreener;

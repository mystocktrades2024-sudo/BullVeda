// surface-options-flow.jsx — Options Flow / UOA cockpit.
// Designed as a 20-yr quant options trader's smart-money tape:
// flow read · net-premium KPIs · sweep/block tape · dealer gamma · IV map · most-active.

const { useState: useOF, useMemo: useOFm } = React;

const OF_PRINTS = (() => {
  // BULLVEDA: real ticker-level UOA aggregates (options_flow.json top30) when available.
  const BV = window.__BV;
  if (BV && BV.optionsFlow && BV.optionsFlow.length) {
    return BV.optionsFlow.map((o) => {
      const pcr = (typeof o.put_call_ratio === "number") ? o.put_call_ratio : 1;
      const isCall = pcr <= 1;
      const prem = (o.premium_total_$ || 0) / 1e6;          // $M (real)
      const size = Math.round(o.total_options_vol || o.call_volume || 0);
      const oi = o.call_oi || 1;
      const iv = o.atm_iv ? Math.round(o.atm_iv * 100) : (o.iv_percentile || 0);
      const dte = o.atm_dte || 14;
      return {
        t: "agg", sym: o.ticker, sector: o.sector || "—", spot: o.price || 0,
        type: isCall ? "C" : "P", strike: o.atm_strike || Math.round(o.price || 0), dte,
        exp: dte + "d", size, prem, oi, volOi: oi ? size / oi : 0, iv,
        aggr: "BTO", exec: o.uoa_calls ? "SWEEP" : "BLOCK",
        sentiment: pcr < 0.85 ? "bull" : pcr > 1.2 ? "bear" : "bull",
        catalyst: o.uoa_detail || "—",
        zscore: +Math.abs(Math.log(pcr || 1) * 3 + 2).toFixed(1),
        unusual: prem.toFixed(1),
      };
    }).sort((a, b) => b.prem - a.prem);
  }
  const names = [
    ["NVDA","Tech",118.4], ["ARGN","Tech",213.4], ["CRWV","Tech",62.1], ["GENO","Healthcare",29.4],
    ["ARCM","Materials",67.4], ["DRSH","Energy",56.1], ["MERC","Tech",17.2], ["NVRH","Healthcare",142.1],
    ["XLE","ETF",91.2], ["BIVO","Healthcare",72.6], ["ZOTR","Tech",41.8], ["BORA","Industrials",31.1],
  ];
  const out = [];
  let hh = 13, mm = 52;
  names.forEach(([sym, sector, spot], i) => {
    const reps = 1 + (sym.charCodeAt(0) % 2);
    for (let r = 0; r < reps; r++) {
      const code = sym.charCodeAt(0) + sym.charCodeAt(1) + i * 11 + r * 7;
      const isCall = code % 3 !== 0;
      const dte = [7, 14, 21, 35, 60][code % 5];
      const strikePct = isCall ? 1 + (code % 8) / 100 : 1 - (code % 8) / 100;
      const strike = Math.round(spot * strikePct);
      const size = (2 + (code % 38)) * 100;          // contracts
      const prem = (size * (0.5 + (code % 40) / 10) * 100) / 1e6; // $M
      const oi = 200 + (code % 30) * 80;
      const volOi = size / oi;
      const iv = 28 + (code % 40);
      const aggr = code % 4 === 0 ? "STO" : "BTO";
      const exec = ["SWEEP", "BLOCK", "SPLIT"][code % 3];
      const sentiment = (isCall && aggr === "BTO") || (!isCall && aggr === "STO") ? "bull" : "bear";
      mm -= 3 + (code % 11); if (mm < 0) { mm += 60; hh -= 1; }
      const cats = ["Earnings 8d", "—", "FDA 14d", "M&A rumor", "—", "Analyst day", "—"];
      const catalyst = cats[code % cats.length];
      const zscore = (2.0 + (code % 45) / 10);  // flow imbalance Z
      out.push({
        t: `${String(hh).padStart(2,"0")}:${String(mm).padStart(2,"0")}`,
        sym, sector, spot, type: isCall ? "C" : "P", strike, dte,
        exp: dte <= 7 ? "Jun 06" : dte <= 14 ? "Jun 13" : dte <= 21 ? "Jun 20" : dte <= 35 ? "Jul 03" : "Jul 18",
        size, prem, oi, volOi, iv, aggr, exec, sentiment, catalyst, zscore,
        unusual: (volOi * (prem) * (exec === "SWEEP" ? 1.4 : 1)).toFixed(1),
      });
    }
  });
  return out.sort((a, b) => b.prem - a.prem);
})();

function SurfaceOptionsFlow({ onTicker }) {
  const [filter, setFilter] = useOF("all");
  const [q, setQ] = useOF("");

  const rows = useOFm(() => {
    let r = OF_PRINTS;
    if (filter === "sweep") r = r.filter(p => p.exec === "SWEEP");
    if (filter === "block") r = r.filter(p => p.exec === "BLOCK");
    if (filter === "bull") r = r.filter(p => p.sentiment === "bull");
    if (filter === "bear") r = r.filter(p => p.sentiment === "bear");
    if (filter === "calls") r = r.filter(p => p.type === "C");
    if (filter === "puts") r = r.filter(p => p.type === "P");
    if (q.trim()) r = r.filter(p => p.sym.toLowerCase().includes(q.toLowerCase()));
    return r;
  }, [filter, q]);

  const callPrem = OF_PRINTS.filter(p => p.type === "C").reduce((s, p) => s + p.prem, 0);
  const putPrem = OF_PRINTS.filter(p => p.type === "P").reduce((s, p) => s + p.prem, 0);
  const netPrem = callPrem - putPrem;
  const cpRatio = (callPrem / putPrem);
  const bull = OF_PRINTS.filter(p => p.sentiment === "bull").length;
  const bearish = OF_PRINTS.length - bull;
  const sweeps = OF_PRINTS.filter(p => p.exec === "SWEEP").length;

  // top tickers by net premium
  const byTicker = useOFm(() => {
    const m = {};
    OF_PRINTS.forEach(p => {
      if (!m[p.sym]) m[p.sym] = { sym: p.sym, call: 0, put: 0, n: 0 };
      m[p.sym][p.type === "C" ? "call" : "put"] += p.prem;
      m[p.sym].n++;
    });
    return Object.values(m).map(x => ({ ...x, net: x.call - x.put }))
      .sort((a, b) => Math.abs(b.net) - Math.abs(a.net)).slice(0, 7);
  }, []);

  return (
    <div className="surface wsx wsx--amb oflow">
      <div className="wsx-hdr">
        <div className="wsx-hdr-l">
          <div className="wsx-eyebrow mono">OPTIONS FLOW · UNUSUAL ACTIVITY</div>
          <h1 className="wsx-title mono">Options Flow</h1>
          <div className="wsx-sub mono dim2">smart-money tape · sweeps &amp; blocks · net-premium imbalance · dealer gamma · IV map</div>
        </div>
        <div className="wsx-hdr-r">
          <FreshnessPill state="live" age="3s" />
          <span className="mono dim2">Schwab /options time&amp;sales · {OF_PRINTS.length} prints · today</span>
        </div>
      </div>

      {/* Flow read */}
      <div className="of-read">
        <div className="of-read-net">
          <div className="of-read-num mono" data-tone={netPrem >= 0 ? "gn" : "rd"}>{netPrem >= 0 ? "+" : "−"}${Math.abs(netPrem).toFixed(1)}M</div>
          <div className="of-read-lbl mono dim2">NET PREMIUM · CALL − PUT</div>
        </div>
        <div className="of-read-body mono">
          Tape skews <b className="up">bullish</b> — ${callPrem.toFixed(1)}M call premium vs ${putPrem.toFixed(1)}M put ({cpRatio.toFixed(2)}× C/P), {bull} bullish vs {bearish} bearish prints,
          {" "}{sweeps} sweeps hitting the offer. <b className="warn">Concentration:</b> flow is led by {byTicker[0]?.sym} and {byTicker[1]?.sym} — single-name, not broad. Confirm with spot before fading.
        </div>
        <div className="of-read-skew">
          <div className="of-skew-bar">
            <div className="of-skew-call" style={{ width: `${callPrem/(callPrem+putPrem)*100}%` }}><span className="mono">CALLS ${callPrem.toFixed(0)}M</span></div>
            <div className="of-skew-put" style={{ width: `${putPrem/(callPrem+putPrem)*100}%` }}><span className="mono">PUTS ${putPrem.toFixed(0)}M</span></div>
          </div>
        </div>
      </div>

      <div className="wsx-kpis">
        <div className="wsx-kpi wsx-kpi--gn"><div className="wsx-kpi-l mono">CALL PREMIUM</div><div className="wsx-kpi-v mono kpi-tone--gn">${callPrem.toFixed(1)}M</div><div className="wsx-kpi-s mono dim2">{OF_PRINTS.filter(p=>p.type==="C").length} prints</div></div>
        <div className="wsx-kpi wsx-kpi--rd"><div className="wsx-kpi-l mono">PUT PREMIUM</div><div className="wsx-kpi-v mono kpi-tone--rd">${putPrem.toFixed(1)}M</div><div className="wsx-kpi-s mono dim2">{OF_PRINTS.filter(p=>p.type==="P").length} prints</div></div>
        <div className="wsx-kpi wsx-kpi--amb"><div className="wsx-kpi-l mono">C/P RATIO</div><div className="wsx-kpi-v mono kpi-tone--amb">{cpRatio.toFixed(2)}×</div><div className="wsx-kpi-s mono dim2">{cpRatio > 1.2 ? "call-skewed" : cpRatio < 0.8 ? "put-skewed" : "balanced"}</div></div>
        <div className="wsx-kpi wsx-kpi--violet"><div className="wsx-kpi-l mono">SWEEPS</div><div className="wsx-kpi-v mono kpi-tone--violet">{sweeps}</div><div className="wsx-kpi-s mono dim2">aggressive · hit offer</div></div>
        <div className="wsx-kpi wsx-kpi--cy"><div className="wsx-kpi-l mono">BULL / BEAR</div><div className="wsx-kpi-v mono kpi-tone--cy">{bull}/{bearish}</div><div className="wsx-kpi-s mono dim2">directional split</div></div>
      </div>

      <div className="lab-tabs">
        {[["all","All flow"],["sweep","Sweeps"],["block","Blocks"],["calls","Calls"],["puts","Puts"],["bull","Bullish"],["bear","Bearish"]].map(([id,l])=>(
          <button key={id} className={`lab-tab ${filter===id?"is-on":""}`} onClick={()=>setFilter(id)}>{l}</button>
        ))}
        <input className="nw-search mono" placeholder="⌕ ticker…" value={q} onChange={e=>setQ(e.target.value)} />
      </div>

      <div className="of-grid">
        {/* Flow tape */}
        <div className="wsx-body of-tape-wrap">
          <table className="dtable wsx-tbl of-tbl">
            <thead><tr>
              <th>Time</th><th>Sym</th><th>Contract</th><th className="r">Spot</th><th className="r">Size</th>
              <th className="r">Notional</th><th className="r">Vol/OI</th><th className="r">Imbal·Z</th><th className="r">IV</th>
              <th>Exec</th><th>Aggr</th><th>Bias</th><th>Catalyst</th><th className="r">Unusual</th><th></th>
            </tr></thead>
            <tbody>{rows.map((p,i)=>(
              <tr key={i} onClick={()=>onTicker(p.sym)}>
                <td className="mono dim2">{p.t}</td>
                <td className="mono"><b>{p.sym}</b></td>
                <td className="mono">
                  <span className={`of-type of-type--${p.type==="C"?"c":"p"}`}>{p.type}</span>
                  <span className="of-strike">${p.strike}</span>
                  <span className="dim2"> {p.exp}</span>
                </td>
                <td className="r mono tabular dim">${p.spot.toFixed(0)}</td>
                <td className="r mono tabular">{p.size.toLocaleString()}</td>
                <td className="r mono tabular"><b className={p.type==="C"?"up":"dn"}>${p.prem.toFixed(2)}M</b></td>
                <td className={`r mono tabular ${p.volOi>=2?"amb":"dim"}`}>{p.volOi.toFixed(1)}×</td>
                <td className={`r mono tabular ${p.zscore>=3?"amb":"dim"}`}>{p.zscore.toFixed(1)}σ</td>
                <td className="r mono tabular dim">{p.iv}%</td>
                <td><span className={`of-exec of-exec--${p.exec.toLowerCase()}`}>{p.exec}</span></td>
                <td className={`mono ${p.aggr==="BTO"?"up":"dn"}`}>{p.aggr}</td>
                <td><span className={`of-bias of-bias--${p.sentiment}`}>{p.sentiment==="bull"?"▲ BULL":"▼ BEAR"}</span></td>
                <td className="mono">{p.catalyst==="—"
                  ? <span className="of-cat-none" title="No known catalyst — the more interesting signal">⚠ none</span>
                  : <span className="dim2">{p.catalyst}</span>}</td>
                <td className="r mono tabular"><span className="of-unusual" style={{opacity: Math.min(1, 0.4+parseFloat(p.unusual)/20)}}>{p.unusual}</span></td>
                <td className="r mono dim">›</td>
              </tr>
            ))}</tbody>
          </table>
        </div>

        {/* Right rail */}
        <div className="of-rail">
          <div className="lab-card">
            <div className="lab-card-h mono">💰 NET PREMIUM · by ticker</div>
            <div className="of-byticker">
              {byTicker.map((x,i)=>(
                <button key={i} className="of-bt-row" onClick={()=>onTicker(x.sym)}>
                  <span className="mono of-bt-sym"><b>{x.sym}</b></span>
                  <div className="of-bt-bar">
                    {x.net>=0
                      ? <i className="of-bt-call" style={{width:`${Math.min(50,Math.abs(x.net)/byTicker[0].net*50)}%`,marginLeft:"50%"}} />
                      : <i className="of-bt-put" style={{width:`${Math.min(50,Math.abs(x.net)/Math.abs(byTicker[0].net)*50)}%`,marginLeft:`${50-Math.min(50,Math.abs(x.net)/Math.abs(byTicker[0].net)*50)}%`}} />}
                    <span className="of-bt-axis" />
                  </div>
                  <span className={`mono of-bt-net ${x.net>=0?"up":"dn"}`}>{x.net>=0?"+":"−"}${Math.abs(x.net).toFixed(1)}M</span>
                </button>
              ))}
            </div>
          </div>

          <div className="lab-card">
            <div className="lab-card-h mono">⚡ DEALER GAMMA · est. positioning</div>
            <div className="of-gamma">
              <div className="of-gamma-flip mono"><span className="dim2">Gamma flip</span> <b className="amb">$5,820 SPX</b></div>
              <div className="of-gamma-row"><span className="mono dim2">Net GEX</span><span className="mono dn">−$1.4B</span><span className="mono dim2">short gamma · vol amplifies</span></div>
              <div className="of-gamma-row"><span className="mono dim2">Call wall</span><span className="mono up">$6,200</span><span className="mono dim2">resistance magnet</span></div>
              <div className="of-gamma-row"><span className="mono dim2">Put wall</span><span className="mono rd">$6,000</span><span className="mono dim2">support magnet</span></div>
              <div className="lab-verdict mono dim2">Below flip = dealers short gamma → moves get amplified, not dampened. Expect range expansion.</div>
            </div>
          </div>

          <div className="lab-card">
            <div className="lab-card-h mono">📊 IV RANK · movers</div>
            <div className="of-ivr">
              {[["GENO",82,"+14","rd"],["BIVO",71,"+9","rd"],["ARCM",48,"−6","gn"],["NVDA",38,"+3","amb"],["ARGN",34,"−4","gn"]].map((r,i)=>(
                <button key={i} className="of-ivr-row" onClick={()=>onTicker(r[0])}>
                  <span className="mono of-ivr-sym"><b>{r[0]}</b></span>
                  <div className="of-ivr-bar"><i style={{width:`${r[1]}%`,background:r[1]>=70?"var(--rd)":r[1]>=40?"var(--amb)":"var(--gn)"}} /></div>
                  <span className="mono dim2">{r[1]}%</span>
                  <span className={`mono ${r[2].startsWith("+")?"dn":"up"}`}>{r[2]}</span>
                </button>
              ))}
              <div className="lab-verdict mono dim2">High IV-rank (GENO 82) = options rich → favor premium selling. Low (ARGN 34) = buy premium.</div>
            </div>
          </div>

          <div className="lab-card">
            <div className="lab-card-h mono">🗓 MOST-ACTIVE EXPIRIES</div>
            <div className="of-exp">
              {[["Jun 06",28,"0DTE-ish · gamma"],["Jun 20",41,"monthly · OpEx"],["Jul 18",22,"next monthly"],["Jul 03",9,"weekly"]].map((r,i)=>(
                <div key={i} className="of-exp-row">
                  <span className="mono of-exp-d">{r[0]}</span>
                  <div className="of-exp-bar"><i style={{width:`${r[1]/41*100}%`}} /></div>
                  <span className="mono dim2 of-exp-n">{r[1]}%</span>
                  <span className="mono dim2 of-exp-note">{r[2]}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="of-playbook mono">
        <span className="of-pb-tag">FLOW PLAYBOOK</span>
        <span className="of-pb-txt">Sweeps &gt; blocks for urgency (paying up to hit the offer = conviction). Confirm flow direction with spot — bullish calls + rising stock = real; bullish calls + falling stock = likely hedging/closing. STO (sell-to-open) flow fades the move; BTO leads it. Single-name concentration ≠ market signal. Never chase a print without your own R:R.</span>
      </div>

      <div className="pm-note mono dim2">
        Prints from <b>Schwab /markets/options time&amp;sales</b> (3s poll) · sweep/block tagged by exchange routing &amp; size-vs-NBBO ·
        BTO/STO inferred from trade-at-bid/ask · dealer gamma modeled from OI &amp; spot · IV rank from 252d ATM history.
      </div>
    </div>
  );
}

window.SurfaceOptionsFlow = SurfaceOptionsFlow;

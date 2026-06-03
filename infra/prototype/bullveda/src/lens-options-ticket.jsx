// lens-options-ticket.jsx — per-ticker Options cockpit, 3-tier architecture.
// Decision strip (always visible) → 3 tabs (Pricing & Greeks · Context · Build).
// Overrides window.LensOptions (loaded last).

const { useState: useOT, useMemo: useOTm } = React;

const EXPIRIES = [
  { dte: 7,   tag: "Weekly",  iv: 96.2 },
  { dte: 21,  tag: "Weekly",  iv: 88.1 },
  { dte: 35,  tag: "Monthly", iv: 85.4, def: true },
  { dte: 63,  tag: "Monthly", iv: 79.0 },
  { dte: 120, tag: "LEAP-ish",iv: 75.6 },
  { dte: 245, tag: "LEAP",    iv: 73.2 },
];

function LensOptions({ ticker, mode }) {
  const [tab, setTab] = useOT("pricing");
  const [contracts, setContracts] = useOT(1);
  const modeDte = mode === "POSITION" ? 63 : mode === "INVESTMENT" ? 245 : 35;
  const [dte, setDte] = useOT(modeDte);
  const [dteTouched, setDteTouched] = useOT(false);
  React.useEffect(() => { if (!dteTouched) setDte(modeDte); }, [modeDte]);

  // derive an option ticket off the ticker
  const o = useOTm(() => {
    const spot = ticker.price;
    const exp = EXPIRIES.find(e => e.dte === dte) || EXPIRIES[2];
    const tFac = Math.sqrt(dte / 35);
    const prem = +(spot * 0.093 * tFac).toFixed(2);   // ATM call premium scales w/ √t
    const strike = Math.round(spot * 1.0);
    const be = +(strike + prem).toFixed(2);
    const target = +(spot * 1.07).toFixed(2);
    const stop = +(spot * 0.97).toFixed(2);
    const iv = exp.iv, hv20 = 107.9, ivrp = +(iv - hv20).toFixed(1);
    const rr = +(((target - be) / Math.max(0.01, be - stop)) * 1.8).toFixed(1);
    const impMove = +(iv / 100 * Math.sqrt(dte / 252) * 100).toFixed(1);
    // earnings inside this expiry window?
    const erDays = ticker.earnings?.days ?? 11;
    const erInWindow = erDays <= dte;
    return { spot, prem, strike, be, target, stop, iv, hv20, ivrp, rr, dte, expTag: exp.tag, sym: ticker.symbol,
      delta: 0.57, gamma: 0.084, theta: -0.04, vega: 0.02,
      pop: 46, impMove, skew: 18.7, term: 1.19, maxPain: Math.round(spot),
      ba: 7.2, beta: 1.58, premUSD: 10.06, edge: 86,
      erDays, erInWindow, ivCrush: erInWindow ? Math.round(iv * 0.34) : 0 };
  }, [ticker, dte]);

  const cost = (o.prem * 100 * contracts);
  const TABS = [["chain","Chain & Expiry"],["pricing","Pricing & Greeks"],["context","Context"],["build","Build & Journal"]];

  return (
    <div className="lens lens--otk">
      {/* ───── DECISION STRIP (always visible) ───── */}
      <div className="otk-strip">
        <div className="otk-ticket">
          <div className="otk-ticket-h mono">⊞ TRADE TICKET · <span className="cy">Long Call</span></div>
          <div className="otk-ticket-row">
            <span className="otk-buy mono">▶ BUY</span>
            <span className="otk-prem mono">${o.prem.toFixed(2)}</span>
            <span className="otk-contract mono dim2">{o.strike}C · {o.dte}DTE · spot ${o.spot.toFixed(2)}</span>
          </div>
          <div className="otk-exp-row">
            {EXPIRIES.map(e => (
              <button key={e.dte} className={`otk-exp ${o.dte===e.dte?"is-on":""}`} onClick={()=>{ setDteTouched(true); setDte(e.dte); }} title={`${e.tag} · IV ${e.iv}%`}>
                {e.dte}d
              </button>
            ))}
          </div>
          <div className="otk-tt-levels">
            <div className="otk-lvl"><span className="otk-lvl-l mono">🎯 TARGET</span><span className="otk-lvl-v mono up">${o.target.toFixed(2)}</span></div>
            <div className="otk-lvl"><span className="otk-lvl-l mono">🛑 STOP</span><span className="otk-lvl-v mono dn">${o.stop.toFixed(2)}</span></div>
            <div className="otk-lvl"><span className="otk-lvl-l mono">BE</span><span className="otk-lvl-v mono">${o.be.toFixed(2)}</span></div>
          </div>
          <div className="otk-size">
            <span className="mono dim2">Contracts</span>
            <div className="otk-size-ctl">
              <button onClick={()=>setContracts(c=>Math.max(1,c-1))}>−</button>
              <span className="mono">{contracts}</span>
              <button onClick={()=>setContracts(c=>c+1)}>+</button>
            </div>
            <div className="otk-quick">
              {["½R","1R","2R"].map(q=> <button key={q} className="otk-q mono">{q}</button>)}
            </div>
          </div>
          <div className="otk-cost">
            <div><span className="mono dim2">Total</span> <b className="mono cy">${cost.toFixed(0)}</b></div>
            <div><span className="mono dim2">Max risk</span> <b className="mono dn">${cost.toFixed(0)}</b></div>
            <div><span className="mono dim2">Max reward</span> <b className="mono up">uncapped</b></div>
          </div>
          <div className="otk-actions">
            <button className="btn btn--sm">★ Save to ideas</button>
            <button className="btn btn--sm">🔔 Alert</button>
          </div>
        </div>

        <div className="otk-verdict">
          <div className="otk-verdict-top">
            <span className="otk-verdict-tag">BULLISH BIAS</span>
            <span className="otk-edge mono">{o.edge}<span className="dim2">/100 edge</span></span>
          </div>
          <div className="otk-checks">
            <div className="otk-chk ok mono"><span>✓</span> STRONG composite — PCR + UOA + Δ aligned</div>
            <div className="otk-chk ok mono"><span>✓</span> STRONG UOA — extreme imbalance + size</div>
            <div className="otk-chk ok mono"><span>✓</span> IV CHEAP (IVRP {o.ivrp}%) — long-premium edge</div>
            {o.erInWindow
              ? <div className="otk-chk bad mono"><span>⚠</span> EARNINGS in {o.erDays}d — IV-crush ~{o.ivCrush}% post-print</div>
              : <div className="otk-chk ok mono"><span>✓</span> No earnings before expiry — clean theta</div>}
            <div className="otk-chk warn mono"><span>·</span> R:R {o.rr}× — acceptable, above 2.0 floor</div>
          </div>
          <div className="otk-heroes">
            <div className="otk-hero"><div className="mono dim2">R:R</div><div className="mono kpi-tone--gn otk-hero-v">{o.rr}×</div></div>
            <div className="otk-hero"><div className="mono dim2">POP</div><div className="mono otk-hero-v">{o.pop}%</div></div>
            <div className="otk-hero"><div className="mono dim2">IVRP</div><div className={`mono otk-hero-v ${o.ivrp<0?"up":"warn"}`}>{o.ivrp}%</div><div className="mono dim2" style={{fontSize:8}}>{o.ivrp<0?"cheap":"rich"}</div></div>
            <div className="otk-hero"><div className="mono dim2">IMP MOVE</div><div className="mono otk-hero-v warn">±{o.impMove}%</div></div>
          </div>
        </div>
      </div>

      {/* ───── TABS ───── */}
      <div className="otk-tabs">
        {TABS.map(([id,l])=> <button key={id} className={`otk-tab ${tab===id?"is-on":""}`} onClick={()=>setTab(id)}>{l}</button>)}
      </div>

      <div className="otk-body">
        {tab==="chain" && <OtkChain o={o} setDte={setDte} />}
        {tab==="pricing" && <OtkPricing o={o} />}
        {tab==="context" && <OtkContext o={o} ticker={ticker} />}
        {tab==="build" && <OtkBuild o={o} />}
      </div>
    </div>
  );
}

function OtkPayoffBig({ o }) {
  const W=380, H=210, padL=44, padR=20, padT=18, padB=30;
  const lo=o.spot*0.82, hi=o.spot*1.20, rng=hi-lo;
  const x=p=> padL + ((p-lo)/rng)*(W-padL-padR);
  const pnl=p=> Math.max(-o.prem, (p>o.strike? p-o.strike : 0) - o.prem);
  const maxG=hi-o.strike-o.prem, maxL=-o.prem;
  const y=v=> padT + (1-((v-maxL)/(maxG-maxL)))*(H-padT-padB);
  const y0=y(0), beX=x(o.be), spotX=x(o.spot);
  const pts=[]; for(let p=lo;p<=hi;p+=0.3)pts.push([x(p),y(pnl(p))]);
  const ticks=[lo, o.stop, o.spot, o.strike, o.be, o.target, hi];
  return (
    <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet" className="otk-payoff-svg">
      <defs><linearGradient id="otk-bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--gn)" stopOpacity="0.30"/><stop offset="100%" stopColor="var(--gn)" stopOpacity="0"/></linearGradient></defs>
      {/* grid */}
      {[maxG, maxG/2, 0, maxL].map((v,i)=>(
        <g key={i}><line x1={padL} y1={y(v)} x2={W-padR} y2={y(v)} stroke="var(--glass-line)" strokeDasharray={v===0?"none":"2 3"} opacity={v===0?0.8:0.4}/>
          <text x={padL-5} y={y(v)+3} fontSize="9" className="mono" textAnchor="end" fill={v>0?"var(--gn)":v<0?"var(--rd)":"var(--ink-3)"}>{v>=0?"+":"−"}${Math.abs(v*100).toFixed(0)}</text></g>
      ))}
      {/* profit fill */}
      <clipPath id="otk-cp"><rect x={beX} y="0" width={W-beX} height={y0}/></clipPath>
      <path d={`M ${padL} ${y0} L ${pts.map(p=>p.join(",")).join(" L ")} L ${W-padR} ${y0} Z`} fill="url(#otk-bg)" clipPath="url(#otk-cp)"/>
      {/* payoff line split at BE */}
      <polyline points={pts.filter(p=>p[0]<=beX).map(p=>p.join(",")).join(" ")} fill="none" stroke="var(--rd)" strokeWidth="2.4"/>
      <polyline points={pts.filter(p=>p[0]>=beX).map(p=>p.join(",")).join(" ")} fill="none" stroke="var(--gn)" strokeWidth="2.4" style={{filter:"drop-shadow(0 0 5px var(--gn))"}}/>
      {/* markers */}
      <line x1={x(o.stop)} y1={padT} x2={x(o.stop)} y2={H-padB} stroke="var(--rd)" strokeDasharray="3 3" opacity="0.55"/>
      <line x1={beX} y1={padT} x2={beX} y2={H-padB} stroke="var(--copper)" strokeDasharray="3 3" opacity="0.7"/>
      <line x1={x(o.target)} y1={padT} x2={x(o.target)} y2={H-padB} stroke="var(--gn)" strokeDasharray="3 3" opacity="0.55"/>
      <circle cx={spotX} cy={y(pnl(o.spot))} r="4" fill="var(--ink)" stroke="var(--bg)" strokeWidth="2"/>
      {/* x labels */}
      <text x={x(o.stop)} y={H-14} fontSize="8.5" className="mono" textAnchor="middle" fill="var(--rd)">stop ${o.stop.toFixed(0)}</text>
      <text x={spotX} y={H-14} fontSize="8.5" className="mono" textAnchor="middle" fill="var(--ink-2)">spot ${o.spot.toFixed(0)}</text>
      <text x={beX} y={H-2} fontSize="8.5" className="mono" textAnchor="middle" fill="var(--copper)">BE ${o.be.toFixed(0)}</text>
      <text x={x(o.target)} y={H-14} fontSize="8.5" className="mono" textAnchor="middle" fill="var(--gn)">tgt ${o.target.toFixed(0)}</text>
    </svg>
  );
}

// ───── TAB: CHAIN & EXPIRY ─────
function OtkChain({ o, setDte }) {
  const strikes = useOTm(() => {
    const base = o.strike;
    const step = Math.max(1, Math.round(o.spot * 0.025));
    const rows = [];
    for (let k = base - step*4; k <= base + step*4; k += step) {
      const itm = k < o.spot;
      const dist = (k - o.spot) / o.spot;
      const cPrem = Math.max(0.05, o.prem - dist * o.spot * 0.55);
      const cDelta = Math.max(0.03, Math.min(0.97, 0.5 - dist * 6));
      const ivK = +(o.iv + Math.abs(dist) * 42).toFixed(1); // smile
      const oi = Math.round(4200 * Math.exp(-Math.abs(dist)*8) + 120);
      const vol = Math.round(oi * (0.3 + Math.random()*0.6));
      rows.push({ k, itm, cPrem, cDelta, ivK, oi, vol, atm: k === base });
    }
    return rows;
  }, [o]);

  const maxOI = Math.max(...strikes.map(s => s.oi));

  // term structure: IV by DTE
  const term = EXPIRIES.map(e => ({ dte: e.dte, iv: e.iv, on: e.dte === o.dte }));
  const tW=300, tH=120, tPadL=34, tPadB=22, tPadT=12, tPadR=12;
  const tMaxIV = Math.max(...term.map(t=>t.iv)), tMinIV = Math.min(...term.map(t=>t.iv));
  const tx = i => tPadL + (i/(term.length-1))*(tW-tPadL-tPadR);
  const ty = v => tPadT + (1-((v-tMinIV+3)/(tMaxIV-tMinIV+6)))*(tH-tPadT-tPadB);

  // skew curve: IV by delta/strike
  const skew = strikes.map(s => ({ k: s.k, iv: s.ivK, atm: s.atm }));
  const sW=300, sH=120, sPadL=34, sPadB=22, sPadT=12, sPadR=12;
  const sMaxIV=Math.max(...skew.map(s=>s.iv)), sMinIV=Math.min(...skew.map(s=>s.iv));
  const sx = i => sPadL + (i/(skew.length-1))*(sW-sPadL-sPadR);
  const sy = v => sPadT + (1-((v-sMinIV+2)/(sMaxIV-sMinIV+4)))*(sH-sPadT-sPadB);

  const contango = term[term.length-1].iv > term[0].iv;

  return (
    <div className="otk-grid">
      <div className="otk-card otk-card--wide">
        <div className="otk-card-h mono">CALL CHAIN · {o.dte}DTE · ±4 strikes · <span className="dim2">tap a strike to inspect</span></div>
        <table className="dtable otk-tbl otk-chain">
          <thead><tr><th>Strike</th><th>Moneyness</th><th className="r">Δ</th><th className="r">IV</th><th className="r">Bid/Ask mid</th><th className="r">Volume</th><th className="r">Open Int</th><th>OI depth</th></tr></thead>
          <tbody>{strikes.map((s,i)=>(
            <tr key={i} className={s.atm?"is-current":""}>
              <td className="mono"><b>${s.k}</b>{s.atm && <span className="otk-atm mono">ATM</span>}</td>
              <td className={`mono ${s.itm?"up":"dim2"}`}>{s.itm?"ITM":(s.k===o.strike?"ATM":"OTM")} {((s.k-o.spot)/o.spot*100).toFixed(1)}%</td>
              <td className="r mono">{s.cDelta.toFixed(2)}</td>
              <td className="r mono">{s.ivK}%</td>
              <td className="r mono cy">${s.cPrem.toFixed(2)}</td>
              <td className="r mono dim2">{s.vol.toLocaleString()}</td>
              <td className="r mono">{s.oi.toLocaleString()}</td>
              <td><div className="otk-oibar"><i style={{width:`${s.oi/maxOI*100}%`}}/></div></td>
            </tr>
          ))}</tbody>
        </table>
      </div>

      <div className="otk-card">
        <div className="otk-card-h mono">VOL TERM STRUCTURE · IV by DTE</div>
        <svg width="100%" height={tH} viewBox={`0 0 ${tW} ${tH}`} className="otk-mini-svg">
          <polyline points={term.map((t,i)=>`${tx(i)},${ty(t.iv)}`).join(" ")} fill="none" stroke="var(--copper)" strokeWidth="2" style={{filter:"drop-shadow(0 0 4px var(--copper))"}}/>
          {term.map((t,i)=>(
            <g key={i}>
              <circle cx={tx(i)} cy={ty(t.iv)} r={t.on?5:3} fill={t.on?"var(--copper)":"var(--ink-2)"} stroke="var(--bg)" strokeWidth="1.5"/>
              <text x={tx(i)} y={tH-8} fontSize="8" className="mono" textAnchor="middle" fill={t.on?"var(--copper)":"var(--ink-3)"}>{t.dte}d</text>
              <text x={tx(i)} y={ty(t.iv)-9} fontSize="8" className="mono" textAnchor="middle" fill="var(--ink-2)">{t.iv}</text>
            </g>
          ))}
        </svg>
        <div className="otk-verdict-mini mono"><span className={contango?"warn":"up"}>{contango?"CONTANGO":"BACKWARDATION"}</span> · {contango?"front cheap vs back — calendars favor long-back":"front rich — event premium, sell-front edge"}</div>
      </div>

      <div className="otk-card">
        <div className="otk-card-h mono">SKEW CURVE · IV by strike · 25Δ {o.skew}%</div>
        <svg width="100%" height={sH} viewBox={`0 0 ${sW} ${sH}`} className="otk-mini-svg">
          <polyline points={skew.map((s,i)=>`${sx(i)},${sy(s.iv)}`).join(" ")} fill="none" stroke="var(--violet)" strokeWidth="2" style={{filter:"drop-shadow(0 0 4px var(--violet))"}}/>
          {skew.map((s,i)=> s.atm && <line key={i} x1={sx(i)} y1={sPadT} x2={sx(i)} y2={sH-sPadB} stroke="var(--copper)" strokeDasharray="3 3" opacity="0.6"/>)}
          {skew.map((s,i)=>(<circle key={i} cx={sx(i)} cy={sy(s.iv)} r={s.atm?4:2.5} fill={s.atm?"var(--copper)":"var(--violet)"}/>))}
          <text x={sPadL} y={sH-8} fontSize="8" className="mono" fill="var(--ink-3)">OTM put</text>
          <text x={sW-sPadR} y={sH-8} fontSize="8" className="mono" textAnchor="end" fill="var(--ink-3)">OTM call</text>
        </svg>
        <div className="otk-verdict-mini mono"><span className="warn">PUT SKEW +{o.skew}%</span> · downside fear bid — favors put-spread financing / call over put</div>
      </div>
    </div>
  );
}

// ───── TAB 1: PRICING & GREEKS ─────
function OtkThetaCurve({ o }) {
  const W = 360, H = 150, padL = 40, padR = 14, padT = 14, padB = 26;
  const dte = o.dte || 35;
  const valAt = d => +(o.prem * Math.sqrt(Math.max(0, (dte - d)) / dte)).toFixed(2);
  const days = [0, Math.round(dte * 0.25), Math.round(dte * 0.5), Math.round(dte * 0.75), dte];
  const pts = [];
  for (let d = 0; d <= dte; d++) pts.push({ d, v: valAt(d) });
  const maxV = o.prem || 1;
  const x = d => padL + (d / dte) * (W - padL - padR);
  const y = v => padT + (1 - v / maxV) * (H - padT - padB);
  const path = pts.map((p, i) => `${i ? "L" : "M"} ${x(p.d).toFixed(1)} ${y(p.v).toFixed(1)}`).join(" ");
  const area = `${path} L ${x(dte)} ${y(0)} L ${x(0)} ${y(0)} Z`;
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} className="otk-mini-svg">
        <defs><linearGradient id="otk-theta" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--rd)" stopOpacity="0.28" /><stop offset="100%" stopColor="var(--rd)" stopOpacity="0" /></linearGradient></defs>
        {[0, 0.5, 1].map((f, i) => <line key={i} x1={padL} y1={y(maxV * f)} x2={W - padR} y2={y(maxV * f)} stroke="var(--line)" strokeDasharray="2 3" />)}
        <path d={area} fill="url(#otk-theta)" />
        <path d={path} fill="none" stroke="var(--rd)" strokeWidth="1.8" />
        {days.map((d, i) => (
          <g key={i}>
            <circle cx={x(d)} cy={y(valAt(d))} r="3" fill="var(--rd)" />
            <text x={x(d)} y={H - 9} fontSize="8.5" className="mono" textAnchor="middle" fill="var(--ink-3)">{d === 0 ? "today" : "T+" + d}</text>
            <text x={x(d)} y={y(valAt(d)) - 7} fontSize="8" className="mono" textAnchor="middle" fill="var(--ink-2)">${valAt(d).toFixed(2)}</text>
          </g>
        ))}
        <text x={padL - 6} y={y(maxV) + 3} fontSize="8" className="mono" textAnchor="end" fill="var(--ink-3)">${maxV.toFixed(2)}</text>
        <text x={padL - 6} y={y(0) + 3} fontSize="8" className="mono" textAnchor="end" fill="var(--ink-3)">$0</text>
      </svg>
      <div className="mono dim2" style={{ fontSize: 10.5, marginTop: 4 }}>If spot doesn't move, the long premium bleeds <b className="dn">${(o.prem - valAt(Math.round(dte / 2))).toFixed(2)}</b> by the half-life (T+{Math.round(dte / 2)}) and accelerates into expiry. Theta <b className="dn">${o.theta}/day</b> now — you need the move <b>before</b> the curve rolls over.</div>
    </div>
  );
}

// Black-Scholes call value + normal CDF (for the profit grid)
function bsNormCdf(x) {
  const t = 1 / (1 + 0.2316419 * Math.abs(x));
  const d = 0.3989423 * Math.exp(-x * x / 2);
  let p = d * t * (0.3193815 + t * (-0.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274))));
  return x > 0 ? 1 - p : p;
}
function bsCall(S, K, T, sigma, r = 0.04) {
  if (T <= 0) return Math.max(S - K, 0);
  const v = sigma * Math.sqrt(T);
  const d1 = (Math.log(S / K) + (r + sigma * sigma / 2) * T) / v;
  const d2 = d1 - v;
  return S * bsNormCdf(d1) - K * Math.exp(-r * T) * bsNormCdf(d2);
}
function bsPut(S, K, T, sigma, r = 0.04) {
  if (T <= 0) return Math.max(K - S, 0);
  return bsCall(S, K, T, sigma, r) - S + K * Math.exp(-r * T);   // put-call parity
}

// Profit calculator — option P&L% across (price level) × (days held), IV held.
// Rich grid: BS-params header, +5d time buckets, spot line, target band, ±% col.
function OtkProfitGrid({ o }) {
  const [ivShift, setIvShift] = React.useState(0);          // vol-point shift (−10/0/+10) or "crush"
  const [dir, setDir] = React.useState("buy");              // buy | write
  const [otype, setOtype] = React.useState("call");          // call | put
  const [strike, setStrike] = React.useState(o.strike);
  const [prem, setPrem] = React.useState(o.prem);
  const [contracts, setContracts] = React.useState(1);
  // strategy presets — each pins direction + option type + a sensible strike
  const STRATS = {
    "Long Call": { dir: "buy", otype: "call", k: () => Math.round(o.spot), note: "bullish" },
    "Long Put": { dir: "buy", otype: "put", k: () => Math.round(o.spot), note: "bearish" },
    "Covered Call": { dir: "write", otype: "call", k: () => Math.round(o.spot * 1.05), note: "income · own shares" },
    "Cash Secured Put": { dir: "write", otype: "put", k: () => Math.round(o.spot * 0.95), note: "bullish · get paid to wait" },
    "Naked Call": { dir: "write", otype: "call", k: () => Math.round(o.spot * 1.07), note: "bearish · undefined risk" },
    "Naked Put": { dir: "write", otype: "put", k: () => Math.round(o.spot * 0.93), note: "bullish · undefined risk" },
  };
  const [strat, setStrat] = React.useState("Long Call");
  const applyStrat = (name) => {
    const s = STRATS[name]; if (!s) return;
    setStrat(name); setDir(s.dir); setOtype(s.otype); setStrike(s.k());
  };
  // reset manual inputs when the underlying ticket changes
  React.useEffect(() => { setStrike(o.strike); setPrem(o.prem); }, [o.strike, o.prem]);
  const crush = ivShift === "crush";
  const sigma = Math.max(0.05, (o.iv + (crush ? -(o.ivCrush || Math.round(o.iv * 0.34)) : ivShift)) / 100);
  const entry = prem;                                         // premium per share (manual)
  const r = 0.045;
  const totalCost = entry * 100 * contracts * (dir === "write" ? -1 : 1);
  const optVal = (S, T) => otype === "put" ? bsPut(S, strike, T, sigma, r) : bsCall(S, strike, T, sigma, r);
  // price rows: % steps around spot (more upside shown, like the reference)
  const pcts = [];
  for (let p = 6.6; p >= -7.2; p -= 0.62) pcts.push(+p.toFixed(1));
  // time buckets: 0, +step, … up to dte, then EXPIRY — aim for ~7 day columns
  const step = Math.max(5, Math.round(o.dte / 7 / 5) * 5);
  const days = [];
  for (let d = 0; d < o.dte; d += step) days.push(d);
  days.push(o.dte);                                            // expiry
  const colLbl = days.map((d, i) => i === 0 ? ["Today", "d0"] : d >= o.dte ? ["EXPIRY", "exp"] : [`+${d}d`, `+${d}`]);
  const cell = (pricePct, daysHeld) => {
    const S = o.spot * (1 + pricePct / 100);
    const Trem = Math.max(0, (o.dte - daysHeld)) / 365;
    const val = optVal(S, Trem);
    const pl = (val - entry) / entry * 100;                   // long P&L%
    return dir === "write" ? -pl : pl;                        // writer = inverse
  };
  const tone = pct => {
    if (pct >= 40) return "g3"; if (pct >= 12) return "g2"; if (pct >= 0) return "g1";
    if (pct > -25) return "r1"; if (pct > -55) return "r2"; return "r3";
  };
  // target row = the +% closest to the AI/T1 move (q75-ish); spot row = nearest 0
  const targetPct = +(((o.target || o.spot * 1.06) / o.spot - 1) * 100).toFixed(1);
  const nearest = (val) => pcts.reduce((a, b) => Math.abs(b - val) < Math.abs(a - val) ? b : a, pcts[0]);
  const spotRow = nearest(0), tgtRow = nearest(targetPct);
  return (
    <div className="otk-pg">
      <div className="otk-pg-hd">
        <span className="otk-pg-title mono">{dir === "write" ? "WRITE" : "LONG"} ${strike} {otype.toUpperCase()} · {o.dte} DTE · {contracts}×</span>
        <span className="otk-pg-params mono dim2">illustrative BS · σ {(sigma * 100).toFixed(0)}% · r {(r * 100).toFixed(1)}% · anchored on live spot ${o.spot.toFixed(2)}</span>
      </div>
      <div className="otk-pg-form">
        <label className="otk-pg-fld mono">Strategy
          <select className="otk-pg-select" value={strat} onChange={e => applyStrat(e.target.value)}>
            {Object.keys(STRATS).map(n => <option key={n} value={n}>{n} ({STRATS[n].note})</option>)}
          </select>
        </label>
        <div className="otk-pg-seg">
          {["buy", "write"].map(d => <button key={d} className={dir === d ? "is-on" : ""} onClick={() => setDir(d)}>{d === "buy" ? "Buy" : "Write"}</button>)}
        </div>
        <div className="otk-pg-seg">
          {["call", "put"].map(t => <button key={t} className={otype === t ? "is-on" : ""} onClick={() => setOtype(t)}>{t === "call" ? "Call" : "Put"}</button>)}
        </div>
        <label className="otk-pg-fld mono">Strike <span className="otk-pg-inwrap">$<input type="number" step="1" value={strike} onChange={e => setStrike(+e.target.value || 0)} /></span></label>
        <label className="otk-pg-fld mono">Premium <span className="otk-pg-inwrap">$<input type="number" step="0.01" value={prem} onChange={e => setPrem(+e.target.value || 0)} /></span></label>
        <label className="otk-pg-fld mono">Contracts <span className="otk-pg-inwrap"><input type="number" step="1" min="1" value={contracts} onChange={e => setContracts(Math.max(1, +e.target.value || 1))} /><span className="dim2">×100</span></span></label>
        <span className="otk-pg-total mono">{dir === "write" ? "Credit" : "Total cost"} <b className={dir === "write" ? "up" : ""}>${Math.abs(totalCost).toFixed(2)}</b></span>
        <button className="otk-pg-reset mono" onClick={() => { applyStrat("Long Call"); setPrem(o.prem); setContracts(1); }}>reset</button>
      </div>
      <div className="otk-pg-iv">
        <span className="mono dim2">IV scenario</span>
        {[["-10", -10], ["flat", 0], ["+10", 10]].map(([l, v]) => (
          <button key={l} className={`otk-pg-ivbtn ${ivShift === v ? "is-on" : ""}`} onClick={() => setIvShift(v)}>{typeof v === "number" && v > 0 ? "+" : ""}{l === "flat" ? "IV flat" : l + " vol"}</button>
        ))}
        <button className={`otk-pg-ivbtn otk-pg-ivbtn--crush ${crush ? "is-on" : ""}`} onClick={() => setIvShift("crush")} title={`earnings IV-crush −${o.ivCrush || Math.round(o.iv * 0.34)} vol pts`}>⚡ ER crush</button>
        <span className="mono dim2 otk-pg-ivnow">σ now <b>{(sigma * 100).toFixed(0)}%</b></span>
      </div>
      <div className="otk-pg-scroll">
      <table className="otk-pg-tbl otk-pg-tbl--rich">
        <thead>
          <tr>
            <th className="otk-pg-corner mono">Price ▾</th>
            {colLbl.map((l, i) => <th key={i} className="mono"><div>{l[0]}</div><div className="otk-pg-colsub dim2">{l[1]}</div></th>)}
            <th className="mono otk-pg-pctcol">±% spot</th>
          </tr>
        </thead>
        <tbody>
          {pcts.map((pp, ri) => {
            const price = o.spot * (1 + pp / 100);
            const isSpot = pp === spotRow, isTgt = pp === tgtRow && !isSpot;
            return (
              <tr key={ri} className={`${isSpot ? "otk-pg-spotrow" : ""} ${isTgt ? "otk-pg-tgtrow" : ""}`}>
                <th className="otk-pg-rowh mono">${price.toFixed(0)}</th>
                {days.map((d, ci) => {
                  const pct = cell(pp, d);
                  return <td key={ci} className={`otk-pg-cell otk-pg--${tone(pct)} mono`} title={`$${price.toFixed(2)} · ${colLbl[ci][0]} → ${pct >= 0 ? "+" : ""}${pct.toFixed(0)}%`}>{pct >= 0 ? "+" : ""}{Math.round(pct)}</td>;
                })}
                <td className="otk-pg-pct mono dim2">{isSpot ? "spot" : (pp >= 0 ? "+" : "") + pp + "%"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      </div>
      <div className="otk-pg-foot mono dim2">
        Each cell = % return on the <b>${entry.toFixed(2)}</b> premium ({o.strike}C · {o.dte}DTE) at that price &amp; date, IV {crush ? "crushed" : ivShift ? `shifted ${ivShift > 0 ? "+" : ""}${ivShift}pts` : "held"} at σ {(sigma * 100).toFixed(0)}%. The <span className="cy">cyan line</span> is live spot; the <span className="amb-c">amber band</span> is the AI/T1 target (${(o.target || o.spot * 1.06).toFixed(2)}). <b>EXPIRY</b> = intrinsic value; reading left→right along a row shows theta erosion. Breakeven at expiry ${o.be.toFixed(2)} (+{((o.be / o.spot - 1) * 100).toFixed(1)}%).
      </div>
    </div>
  );
}

function OtkPricing({ o }) {
  const stress=[["↓ -10%",o.spot*0.9,-1.27,-61],["↓ -5%",o.spot*0.95,-0.84,-40],["↓ -2%",o.spot*0.98,-0.53,-25],["· +0%",o.spot,-0.30,-14],["↑ +2%",o.spot*1.02,-0.05,-3],["↑ +5%",o.spot*1.05,0.35,17],["↑ +10%",o.spot*1.10,1.09,53]];
  const decay=[["1d",-0.05,-2],["3d",-0.15,-7],["5d",-0.26,-13],["7d",-0.38,-18],["14d",-0.88,-42]];
  const vrp=[["IV (ATM)","85.4%","—","baseline","ink"],["HV20","107.9%","-22.4%","IV cheap","gn"],["HV30","93.5%","-8.1%","IV cheap","gn"],["HV60","75.2%","+10.2%","IV rich","rd"],["HV90","76.1%","+9.3%","IV rich","rd"]];
  return (
    <div className="otk-grid">
      <div className="otk-card">
        <div className="otk-card-h mono">GREEKS · ATM ~21d</div>
        <div className="otk-greeks">
          {[["Δ","+"+o.delta],["Γ",o.gamma],["Θ/d","$"+o.theta],["ν","+$"+o.vega]].map(([k,v],i)=>(
            <div key={i} className="otk-greek"><span className="mono dim2">{k}</span><span className="mono otk-greek-v">{v}</span></div>
          ))}
        </div>
      </div>
      <div className="otk-card">
        <div className="otk-card-h mono">QUICK STATS</div>
        <div className="otk-stats">
          {[["IV",o.iv+"%"],["HV20",o.hv20+"%"],["IVRP",o.ivrp+"%"],["25Δ Skew","+"+o.skew+"%"],["Term",o.term],["Imp move","±"+o.impMove+"%"],["POP",o.pop+"%"],["Max Pain","$"+o.maxPain],["B/A",o.ba+"%"],["β-SPY",o.beta]].map(([k,v],i)=>(
            <div key={i} className="otk-stat"><span className="mono dim2">{k}</span><span className="mono">{v}</span></div>
          ))}
        </div>
      </div>
      <div className="otk-card">
        <div className="otk-card-h mono">GREEKS-STRESS · spot scenarios</div>
        <table className="dtable otk-tbl">
          <thead><tr><th>Spot Move</th><th className="r">Spot</th><th className="r">Δ Prem</th><th className="r">P&L %</th></tr></thead>
          <tbody>{stress.map((r,i)=>(
            <tr key={i}><td className="mono">{r[0]}</td><td className="r mono">${r[1].toFixed(2)}</td>
              <td className={`r mono ${r[2]>=0?"up":"dn"}`}>{r[2]>=0?"+":""}${Math.abs(r[2]).toFixed(2)}</td>
              <td className={`r mono ${r[3]>=0?"up":"dn"}`}>{r[3]>=0?"+":""}{r[3]}%</td></tr>
          ))}</tbody>
        </table>
      </div>
      <div className="otk-card">
        <div className="otk-card-h mono">VOL RISK PREMIUM LADDER · IV vs realized</div>
        <table className="dtable otk-tbl">
          <thead><tr><th>Horizon</th><th className="r">Realized</th><th className="r">IV − HV</th><th>Verdict</th></tr></thead>
          <tbody>{vrp.map((r,i)=>(
            <tr key={i}><td className="mono">{r[0]}</td><td className="r mono">{r[1]}</td><td className={`r mono kpi-tone--${r[4]}`}>{r[2]}</td><td><span className={`kpi-tone--${r[4]} mono`}>{r[3]}</span></td></tr>
          ))}</tbody>
        </table>
      </div>
      <div className="otk-card otk-card--wide">
        <div className="otk-card-h mono">PROFIT CALCULATOR · DAILY % RETURN GRID <span className="dim2" style={{textTransform:"none",letterSpacing:".04em"}}>· option P&amp;L across spot move × days held (Black-Scholes, IV held)</span></div>
        <OtkProfitGrid o={o} />
      </div>

      <div className="otk-card">
        <div className="otk-card-h mono">THETA DECAY · premium value by date <span className="dim2" style={{textTransform:"none",letterSpacing:".04em"}}>· spot unchanged</span></div>
        <OtkThetaCurve o={o} />
      </div>
      <div className="otk-card">
        <div className="otk-card-h mono">SMART FILL ESTIMATE</div>
        <div className="otk-stats">
          {[["Bid/Ask",o.ba+"%"],["Half-spread","$0.08"],["Mid (target)","$"+o.prem.toFixed(2)],["Realistic fill","$"+(o.prem+0.05).toFixed(2)],["Slip vs mid","2.2%"]].map(([k,v],i)=>(
            <div key={i} className="otk-stat"><span className="mono dim2">{k}</span><span className="mono">{v}</span></div>
          ))}
        </div>
        <div className="otk-verdict-mini mono"><span className="up">OK</span> · mid+30% target</div>
      </div>

      <div className="otk-card">
        <div className="otk-card-h mono">LIQUIDITY GRADE · can I get filled?</div>
        <div className="otk-liq">
          <div className="otk-liq-grade mono">B+</div>
          <div className="otk-liq-rows">
            {[["Spread %",o.ba+"%","amb"],["OI @ strike","4,200","gn"],["Vol today","2,310","gn"],["Slip est.","2.2%","gn"],["Fill speed","~3s mid","gn"]].map(([k,v,t],i)=>(
              <div key={i} className="otk-liq-row"><span className="mono dim2">{k}</span><span className={`mono kpi-tone--${t}`}>{v}</span></div>
            ))}
          </div>
        </div>
        <div className="otk-verdict-mini mono"><span className="up">FILLABLE</span> · use limit @ mid, work up to mid+½spread</div>
      </div>

      <div className="otk-card">
        <div className="otk-card-h mono">BOOK GREEKS IMPACT · marginal Δ to portfolio</div>
        <table className="dtable otk-tbl">
          <thead><tr><th>Greek</th><th className="r">Book now</th><th className="r">+ this trade</th><th className="r">After</th></tr></thead>
          <tbody>
            {[["Net Δ","+182","+57","+239","amb"],["Net Γ","+3.1","+8.4","+11.5","amb"],["Net Θ/d","−$112","−$4","−$116","dn"],["Net ν","+$340","+$2","+$342","gn"],["β-wtd Δ","+0.93","+0.09","+1.02","amb"]].map((r,i)=>(
              <tr key={i}><td className="mono">{r[0]}</td><td className="r mono dim2">{r[1]}</td><td className="r mono cy">{r[2]}</td><td className={`r mono kpi-tone--${r[4]}`}>{r[3]}</td></tr>
            ))}
          </tbody>
        </table>
        <div className="otk-verdict-mini mono"><span className="warn">Δ tilts net-long</span> · adds directional; vega still light</div>
      </div>

      <div className="otk-card">
        <div className="otk-card-h mono">ROLL / EXIT PLANNER · pre-decided</div>
        <div className="otk-roll">
          {[["Profit target","+100% prem","sell ½ · trail rest","gn"],["Time stop","21 DTE","roll out or close","amb"],["Loss stop","−50% prem","close full","rd"],["Roll trigger","Δ &gt; 0.80","roll up & out 1 strike","cy"],["Gamma risk","≤ 7 DTE","close — no expiry week","rd"]].map((r,i)=>(
            <div key={i} className={`otk-roll-row otk-roll--${r[3]}`}>
              <span className="mono otk-roll-when">{r[0]}</span>
              <span className="mono dim2">{r[1]}</span>
              <span className="mono otk-roll-act" dangerouslySetInnerHTML={{__html:r[2]}}/>
            </div>
          ))}
        </div>
      </div>

      <div className="otk-card">
        <div className="otk-card-h mono">ASSIGNMENT / PIN RISK</div>
        <div className="otk-stats">
          {[["Style","American"],["ITM now",o.spot>o.strike?"yes":"no"],["Ex-div ≤ exp","none"],["Pin risk @ exp",o.maxPain===o.strike?"HIGH":"low"],["Early-assign p","< 2%"],["Max-pain $","$"+o.maxPain]].map(([k,v],i)=>(
            <div key={i} className="otk-stat"><span className="mono dim2">{k}</span><span className="mono">{v}</span></div>
          ))}
        </div>
        <div className="otk-verdict-mini mono"><span className="up">LOW</span> · long call · assignment not applicable unless deep-ITM near ex-div</div>
      </div>
    </div>
  );
}

// ───── TAB 2: CONTEXT ─────
// Dealer gamma exposure (GEX) — computed from the option chain OI × gamma.
// Net positive GEX = dealers dampen moves (price pins toward walls); negative = moves amplified.
function OtkGEX({ o }) {
  const g = useOTm(() => {
    const spot = o.spot;
    const step = Math.max(1, Math.round(spot * 0.025));
    const atmK = Math.round(spot / step) * step;
    const rows = [];
    for (let i = -5; i <= 5; i++) {
      const k = atmK + i * step;
      const dist = (k - spot) / spot;
      const callOI = Math.round(4600 * Math.exp(-Math.pow((dist - 0.025) * 8, 2)) + 90);
      const putOI  = Math.round(6200 * Math.exp(-Math.pow((dist + 0.035) * 8, 2)) + 90);
      const gamma  = Math.exp(-Math.pow(dist * 7, 2)) * 0.09;             // per-contract γ peaks ATM
      // dealer convention: short calls (−), short puts (+) → net dealer gamma, $mm per 1% move
      const callGEX = -callOI * gamma * spot * spot * 4e-6;
      const putGEX  =  putOI  * gamma * spot * spot * 4e-6;
      rows.push({ k, callOI, putOI, net: +(callGEX + putGEX).toFixed(2) });
    }
    // max-pain = strike minimizing total option-holder payout
    let maxPain = rows[0].k, minPay = Infinity;
    rows.forEach(r => { let p = 0; rows.forEach(s => { p += Math.max(0, r.k - s.k) * s.callOI + Math.max(0, s.k - r.k) * s.putOI; }); if (p < minPay) { minPay = p; maxPain = r.k; } });
    const callWall = rows.reduce((a, b) => b.callOI > a.callOI ? b : a).k;
    const putWall  = rows.reduce((a, b) => b.putOI  > a.putOI  ? b : a).k;
    let flip = spot; for (let i = 1; i < rows.length; i++) { if ((rows[i - 1].net < 0) !== (rows[i].net < 0)) { flip = rows[i].k; break; } }
    const total = +rows.reduce((a, b) => a + b.net, 0).toFixed(2);
    return { rows, maxPain, callWall, putWall, flip, total };
  }, [o]);

  const W = 720, H = 220, padL = 16, padR = 16, padT = 16, padB = 30;
  const n = g.rows.length, bw = (W - padL - padR) / n;
  const maxAbs = Math.max(...g.rows.map(r => Math.abs(r.net)), 0.1);
  const y0 = padT + (H - padT - padB) / 2;
  const yh = (H - padT - padB) / 2;
  const cx = i => padL + bw * (i + 0.5);
  const spotI = (o.spot - g.rows[0].k) / (g.rows[n - 1].k - g.rows[0].k) * (n - 1);
  const spotX = padL + bw * (spotI + 0.5);
  const pos = g.total >= 0;
  const gexPrompt = () => `Explain options dealer-gamma (GEX) to a BEGINNER STOCK trader (they don't trade options) in plain, simple English. Use the live numbers for ${o.sym} below: 3-4 short sentences, use the actual prices, end with ONE practical takeaway for someone trading the shares.
Spot price: $${o.spot.toFixed(2)}
Net GEX: ${g.total >= 0 ? "+" : ""}${g.total} (${g.total >= 0 ? "positive — moves get dampened, range-bound day" : "negative — moves get amplified, trending day"})
Ceiling / call wall (resistance): $${g.callWall}
Floor / put wall (support): $${g.putWall}
Flip level (calm-vs-volatile switch): $${g.flip}
Magnet by Friday / max pain: $${g.maxPain}`;
  return (
    <div className="otk-card otk-card--wide">
      <div className="otk-card-h mono">DEALER GAMMA (GEX) · by strike · <span className="dim2">computed from chain OI × γ</span></div>
      <div className="otk-gex-kpis">
        <div className="otk-gex-kpi"><span className="mono dim2">NET GEX</span><span className={`mono otk-gex-kv ${pos ? "up" : "dn"}`}>{pos ? "+" : "−"}${Math.abs(g.total).toFixed(1)}mm</span><span className="mono dim2" style={{ fontSize: 8 }}>{pos ? "stabilizing" : "amplifying"}</span></div>
        <div className="otk-gex-kpi"><span className="mono dim2">γ-FLIP</span><span className="mono otk-gex-kv warn">${g.flip}</span></div>
        <div className="otk-gex-kpi"><span className="mono dim2">MAX PAIN</span><span className="mono otk-gex-kv copper">${g.maxPain}</span></div>
        <div className="otk-gex-kpi"><span className="mono dim2">CALL WALL</span><span className="mono otk-gex-kv up">${g.callWall}</span></div>
        <div className="otk-gex-kpi"><span className="mono dim2">PUT WALL</span><span className="mono otk-gex-kv dn">${g.putWall}</span></div>
      </div>
      <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet" className="otk-gex-svg">
        <line x1={padL} y1={y0} x2={W - padR} y2={y0} stroke="var(--glass-line)" />
        {g.rows.map((r, i) => {
          const h = (Math.abs(r.net) / maxAbs) * yh;
          const up = r.net >= 0;
          return (
            <g key={i}>
              <rect x={cx(i) - bw * 0.32} y={up ? y0 - h : y0} width={bw * 0.64} height={h}
                fill={up ? "var(--gn)" : "var(--rd)"} opacity="0.78" rx="1.5" />
              <text x={cx(i)} y={H - 9} fontSize="9" className="mono" textAnchor="middle" fill={r.k === g.maxPain ? "var(--copper)" : "var(--ink-3)"}>${r.k}</text>
            </g>
          );
        })}
        {/* wall + flip markers on the bars */}
        {(() => {
          const marks = [
            { k: g.callWall, lbl: "CALL WALL", c: "var(--gn)" },
            { k: g.putWall,  lbl: "PUT WALL",  c: "var(--rd)" },
            { k: g.flip,     lbl: "γ-FLIP",    c: "var(--amb)" },
          ];
          const used = {};
          return marks.map((m, mi) => {
            const i = g.rows.findIndex(rw => rw.k === m.k);
            if (i < 0) return null;
            const x = cx(i);
            const slot = (used[i] = (used[i] || 0) + 1);
            const ly = padT + 7 + (slot - 1) * 11;
            return (
              <g key={mi}>
                <line x1={x} y1={padT} x2={x} y2={H - padB} stroke={m.c} strokeWidth="1.2" opacity="0.4" />
                <rect x={x - 26} y={ly - 8} width="52" height="11" rx="2" fill="var(--bg-1)" opacity="0.85" />
                <text x={x} y={ly} fontSize="7.5" className="mono" textAnchor="middle" fill={m.c} fontWeight="700">{m.lbl}</text>
              </g>
            );
          });
        })()}
        {/* spot */}
        <line x1={spotX} y1={padT} x2={spotX} y2={H - padB} stroke="var(--ink)" strokeDasharray="3 3" opacity="0.7" />
        <text x={spotX} y={padT - 4} fontSize="8.5" className="mono" textAnchor="middle" fill="var(--ink-2)">spot ${o.spot.toFixed(0)}</text>
        <text x={padL + 2} y={padT + 8} fontSize="8" className="mono" fill="var(--gn)">+ dealers dampen</text>
        <text x={padL + 2} y={H - padB - 2} fontSize="8" className="mono" fill="var(--rd)">− dealers amplify</text>
      </svg>
      <div className="otk-verdict-mini mono">
        <span className={pos ? "up" : "dn"}>{pos ? "POSITIVE γ" : "NEGATIVE γ"}</span> ·{" "}
        {pos
          ? <>dealers buy dips / sell rips → moves get <b>dampened</b>; price tends to gravitate toward <b className="copper">max-pain ${g.maxPain}</b> and pin between the <b className="dn">put wall ${g.putWall}</b> and <b className="up">call wall ${g.callWall}</b> into expiry. A break <b>below the γ-flip ${g.flip}</b> turns this amplifying.</>
          : <>dealer hedging <b>amplifies</b> moves (air-pockets) — expect larger swings; reclaiming the <b className="warn">γ-flip ${g.flip}</b> would restore stability.</>}
        <span className="dim2"> · informational, not advice.</span>
      </div>
      <div className="otk-gex-stock">
        <div className="otk-gex-stock-top">
          <span className="otk-gex-stock-tag mono">FOR THE STOCK</span>
        </div>
        <div className="otk-gex-plain mono">
          {pos ? <>
            <div className="otk-gex-pl-hd"><b className="up">Likely a calm, range-bound day.</b> It should mostly trade between two prices:</div>
            <div className="otk-gex-pl-row"><span className="otk-gex-pl-k dn">FLOOR ${g.putWall}</span> — when it dips here, buyers tend to step in and it <b>bounces back up</b>.</div>
            <div className="otk-gex-pl-row"><span className="otk-gex-pl-k up">CEILING ${g.callWall}</span> — when it rallies here, sellers tend to step in and it <b>stalls / pulls back</b>.</div>
            <div className="otk-gex-pl-row"><span className="otk-gex-pl-k warn">IF IT BREAKS ${g.flip}+</span> the calm is over — it can <b>take off and run</b>, so don't expect a bounce.</div>
            <div className="otk-gex-pl-foot dim2">In plain words: expect chop between <b>${g.putWall}</b> and <b>${g.callWall}</b>, often drifting to about <b>${g.maxPain}</b> by Friday. Informational only — not advice.</div>
          </> : <>
            <div className="otk-gex-pl-hd"><b className="dn">Likely a fast, trending day.</b> Moves get bigger and harder to fade:</div>
            <div className="otk-gex-pl-row"><span className="otk-gex-pl-k dn">${g.putWall} may not hold</span> — a drop can keep falling instead of bouncing.</div>
            <div className="otk-gex-pl-row"><span className="otk-gex-pl-k up">${g.callWall} may not cap it</span> — a rally can keep running instead of stalling.</div>
            <div className="otk-gex-pl-row"><span className="otk-gex-pl-k warn">WATCH ${g.flip}</span> — getting back above it usually brings the calm, range-bound behavior back.</div>
            <div className="otk-gex-pl-foot dim2">In plain words: bigger swings, breakouts can run — don't bet on bounces today. Informational only — not advice.</div>
          </>}
        </div>
        <AiExplain build={gexPrompt} label="Explain with AI" />
      </div>
    </div>
  );
}

function OtkContext({ o, ticker }) {
  return (
    <div className="otk-grid">
      <OtkGEX o={o} />
      <div className="otk-card otk-card--wide">
        <div className="otk-card-h mono">NEWS · last headlines</div>
        <div className="otk-news">
          {[["08:42","Analyst reiterates Buy, raises PT","gn"],["07:15","Sector flows turn positive on macro","gn"],["Yesterday","Mixed guidance from peer name","amb"]].map((n,i)=>(
            <div key={i} className={`otk-news-row otk-news--${n[2]}`}><span className="mono dim2">{n[0]}</span><span className="mono">{n[1]}</span></div>
          ))}
        </div>
      </div>
      <div className="otk-card">
        <div className="otk-card-h mono">CATALYSTS</div>
        <div className="otk-cats">
          {[["🏦 FOMC","20d"],["📈 CPI","12d"],["💼 NFP","7d"],["🔱 TripleW","21d"]].map((c,i)=>(
            <div key={i} className="otk-cat"><span className="mono">{c[0]}</span><span className="mono amb">{c[1]}</span></div>
          ))}
        </div>
      </div>
      <div className="otk-card">
        <div className="otk-card-h mono">CORPORATE ACTIONS · ≤60d</div>
        <div className="otk-news"><div className="otk-news-row mono dim2">No ex-div / splits in window</div></div>
      </div>
      <div className="otk-card">
        <div className="otk-card-h mono">WHALE STRIKES · vol &gt; 2.5σ</div>
        <div className="otk-news"><div className="otk-news-row mono dim2">No outlier strikes detected</div></div>
      </div>
      <div className="otk-card otk-card--wide">
        <div className="otk-card-h mono">ALT-DATA · Senate · EDGAR · Wiki · Reddit</div>
        <div className="otk-alt">
          {[["Senate trades","0 filings 90d","ink"],["EDGAR 8-K","1 recent","amb"],["Wiki views","+12% wk","gn"],["Reddit mentions","+38% wk","gn"]].map((a,i)=>(
            <div key={i} className="otk-alt-cell"><div className="mono dim2">{a[0]}</div><div className={`mono kpi-tone--${a[2]}`}>{a[1]}</div></div>
          ))}
        </div>
      </div>
      <div className="otk-card otk-card--wide">
        <div className="otk-card-h mono">VOL SURFACE METRICS</div>
        <div className="otk-stats">
          {[["Butterfly","+7.86%"],["25Δ Risk Rev","+18.74%"],["Vega notional","+$2/ct/IVpp"],["Vol of vol","124.0%"],["Term ratio",o.term]].map(([k,v],i)=>(
            <div key={i} className="otk-stat"><span className="mono dim2">{k}</span><span className="mono">{v}</span></div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ───── TAB 3: BUILD ─────
const OTK_STRATS = {
  "Long Call":        { dir: "bull", legs: s => [`+1 C ${s.k0}`], calc: (S, P) => ({ debit: P, maxLoss: P * 100, maxGain: "open", be: S + P, pop: 46 }) },
  "Bull Call Spread": { dir: "bull", legs: s => [`+1 C ${s.k0}`, `−1 C ${s.k1}`], calc: (S, P) => { const d = +(P * 0.45).toFixed(2), w = +(S * 0.08).toFixed(2); return { debit: d, maxLoss: d * 100, maxGain: +((w - d) * 100).toFixed(0), be: +(S + d).toFixed(2), pop: 41 }; } },
  "Long Put":         { dir: "bear", legs: s => [`+1 P ${s.k0}`], calc: (S, P) => ({ debit: P, maxLoss: P * 100, maxGain: +((S - P) * 100).toFixed(0), be: S - P, pop: 44 }) },
  "Bear Put Spread":  { dir: "bear", legs: s => [`+1 P ${s.k0}`, `−1 P ${s.k1d}`], calc: (S, P) => { const d = +(P * 0.45).toFixed(2), w = +(S * 0.08).toFixed(2); return { debit: d, maxLoss: d * 100, maxGain: +((w - d) * 100).toFixed(0), be: +(S - d).toFixed(2), pop: 43 }; } },
  "Cash-Secured Put": { dir: "neutral-bull", legs: s => [`−1 P ${s.k1d}`], calc: (S, P) => { const c = +(P * 0.6).toFixed(2); return { debit: -c, maxLoss: +((S * 0.95 - c) * 100).toFixed(0), maxGain: +(c * 100).toFixed(0), be: +(S * 0.95 - c).toFixed(2), pop: 68 }; } },
  "Iron Condor":      { dir: "neutral", legs: s => [`−1 C ${s.k1}`, `+1 C ${s.k2}`, `−1 P ${s.k1d}`, `+1 P ${s.k2d}`], calc: (S, P) => { const c = +(P * 0.5).toFixed(2), w = +(S * 0.06).toFixed(2); return { debit: -c, maxLoss: +((w - c) * 100).toFixed(0), maxGain: +(c * 100).toFixed(0), be: `${(S*0.94).toFixed(0)}–${(S*1.06).toFixed(0)}`, pop: 64 }; } },
};
function OtkBuild({ o }) {
  const [strat, setStrat] = useOT("Long Call");
  const S = o.spot, P = o.prem;
  const strikes = { k0: `$${Math.round(S)}`, k1: `$${Math.round(S * 1.08)}`, k2: `$${Math.round(S * 1.16)}`, k1d: `$${Math.round(S * 0.95)}`, k2d: `$${Math.round(S * 0.87)}` };
  const def = OTK_STRATS[strat];
  const legs = def.legs(strikes);
  const r = def.calc(S, P);
  const credit = r.debit < 0;
  return (
    <div className="otk-grid">
      <div className="otk-card otk-card--wide">
        <div className="otk-card-h mono">SPREAD BUILDER · calls &amp; puts · defined-risk structures</div>
        <div className="otk-sb-strats">
          {Object.keys(OTK_STRATS).map(s => (
            <button key={s} className={`otk-sb-chip ${strat === s ? "is-on" : ""}`} onClick={() => setStrat(s)}>{s}</button>
          ))}
        </div>
        <div className="otk-sb-legs">
          {legs.map((l, i) => <span key={i} className={`otk-sb-leg ${l[0] === "+" ? "buy" : "sell"}`}>{l}</span>)}
          <span className="otk-sb-bias mono dim2">· {def.dir} bias</span>
        </div>
        <div className="otk-sb-stats">
          <div className="otk-sb-stat"><span className="mono dim2">{credit ? "Credit" : "Debit"}</span><span className={`mono ${credit ? "up" : ""}`}>${Math.abs(r.debit).toFixed(2)}</span></div>
          <div className="otk-sb-stat"><span className="mono dim2">Max loss</span><span className="mono dn">−${typeof r.maxLoss === "number" ? r.maxLoss.toLocaleString() : r.maxLoss}</span></div>
          <div className="otk-sb-stat"><span className="mono dim2">Max gain</span><span className="mono up">{r.maxGain === "open" ? "open ↑" : "+$" + (r.maxGain).toLocaleString()}</span></div>
          <div className="otk-sb-stat"><span className="mono dim2">Breakeven</span><span className="mono">{typeof r.be === "number" ? "$" + r.be.toFixed(2) : r.be}</span></div>
          <div className="otk-sb-stat"><span className="mono dim2">POP</span><span className={`mono ${r.pop >= 60 ? "up" : ""}`}>{r.pop}%</span></div>
          <div className="otk-sb-stat"><span className="mono dim2">R:R</span><span className="mono copper">{typeof r.maxGain === "number" && typeof r.maxLoss === "number" ? (r.maxGain / r.maxLoss).toFixed(2) : "—"}</span></div>
        </div>
        <div className="mono dim2" style={{ fontSize: 10.5, marginTop: 8 }}>{credit ? "Credit structure — you collect premium; max gain is the credit, risk is defined by the wings." : "Debit structure — you pay premium; max loss is the debit. "}{def.dir === "neutral" ? "Profits if price stays inside the wings through expiry." : def.dir.includes("bull") ? "Profits as price rises toward the short strike." : "Profits as price falls."} Demo pricing off ATM premium + IV.</div>
      </div>
      <div className="otk-card">
        <div className="otk-card-h mono">STREAMER · real-time NBBO</div>
        <div className="otk-stream"><span className="mono dim2">Status</span><span className="mono dn">disconnected</span><button className="btn btn--sm">▶ Start</button></div>
        <div className="mono dim2" style={{fontSize:9,marginTop:6}}>SSE bridge · free via Schwab brokerage auth</div>
      </div>
      <div className="otk-card otk-card--wide">
        <div className="otk-card-h mono">TRADE JOURNAL · per-ticker notes</div>
        <OtkJournal sym={o.strike ? null : null} symbol={o.sym || o.symbol} />
      </div>
    </div>
  );
}

// per-ticker journal — persists to localStorage
function OtkJournal({ symbol }) {
  const key = "otk-journal-" + (symbol || "x");
  const [val, setVal] = useOT(() => { try { return localStorage.getItem(key) || ""; } catch (e) { return ""; } });
  return (
    <>
      <textarea className="otk-journal mono" placeholder="Why this trade? · entry rationale · invalidation triggers · post-trade review"
        value={val} onChange={e => { setVal(e.target.value); try { localStorage.setItem(key, e.target.value); } catch (e2) {} }} />
      <div className="mono dim2" style={{ fontSize: 9 }}>auto-saves to localStorage per ticker{symbol ? ` · ${symbol}` : ""}</div>
    </>
  );
}

window.LensOptions = LensOptions;

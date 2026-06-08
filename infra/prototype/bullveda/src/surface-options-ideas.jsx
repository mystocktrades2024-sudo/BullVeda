// surface-options-ideas.jsx — "Top Options to Buy" — ranked actionable option trades.
// Schwab /options/chains + scan verdicts → concrete option tickets, ranked by edge.

const { useState: useOI, useMemo: useOIm } = React;

// ── served-aware real source ────────────────────────────────────────
// BULLVEDA: real options ideas are derived from the live UOA tape
// (window.__BV.optionsFlow ← critical.options_flow_top30 — real ticker-level
// unusual-options-activity aggregates). We surface a CONCRETE directional read
// per UOA name from fields that genuinely exist (bias from put/call ratio,
// spot, ATM strike/DTE/IV, total premium). We do NOT fabricate per-leg debits,
// POP, Greeks, BE, or Kelly — those require a priced chain we don't have here,
// so they render "—". Honest-empty when served and the UOA tape is empty.
// The OI_IDEAS_DEMO array below is the standalone-showcase fallback ONLY.
const OI_SERVED = (typeof window !== "undefined" && !!window.__BV);

function oiRealIdeas() {
  const BV = (typeof window !== "undefined") ? window.__BV : null;
  const flow = (BV && Array.isArray(BV.optionsFlow)) ? BV.optionsFlow : null;
  if (!flow || !flow.length) return null;
  return flow.map(o => {
    const pcr = (typeof o.put_call_ratio === "number") ? o.put_call_ratio : 1;
    const dir = pcr < 0.85 ? "bull" : pcr > 1.2 ? "bear" : "bull";
    const spot = +(o.price || o.spot || 0) || 0;
    const ivr = (typeof o.iv_percentile === "number") ? Math.round(o.iv_percentile)
              : (o.atm_iv ? Math.round(o.atm_iv * 100) : null);
    const dte = o.atm_dte || null;
    const strike = o.atm_strike || (spot ? Math.round(spot) : null);
    const premM = (o.premium_total_$ || 0) / 1e6;
    // IV-rank → suggested structure (honest guidance, not a priced ticket).
    const strat = ivr == null ? "Directional (UOA)"
                : ivr < 45 ? (dir === "bear" ? "Long Put" : "Long Call")
                : ivr < 70 ? (dir === "bear" ? "Put Debit Spread" : "Bull Call Spread")
                : "Calendar / sell premium";
    return {
      sym: String(o.ticker || "").toUpperCase(),
      spot, dir, strat,
      structure: (strike != null && dte != null) ? `~${strike}${dir === "bear" ? "P" : "C"} · ${dte}d` : "chain not priced",
      debit: null, maxLoss: null, maxGain: null, be: null, pop: null,
      rr: null, ivr, dte, delta: null, theta: null,
      catalyst: o.uoa_detail || "—",
      conv: null, kelly: null,
      why: `UOA tape: net ${dir === "bear" ? "put" : "call"} premium ${premM >= 0.01 ? "$" + premM.toFixed(1) + "M" : "flow"} (P/C ${pcr.toFixed(2)})${ivr != null ? " · IV-rank " + ivr : ""}. Structure is IV-rank guidance — price the leg on the Options lens before sizing.`,
      premM, pcr,
      risk: "size off the Options lens", riskTone: "amb",
    };
  }).filter(x => x.sym).sort((a, b) => (b.premM || 0) - (a.premM || 0));
}

const OI_IDEAS_DEMO = [
  { sym:"DMOA", spot:213.40, dir:"bull", strat:"Long Call", structure:"Jul18 220C", debit:8.40, maxLoss:840, maxGain:"open", be:228.40, pop:46, rr:"3.1", ivr:34, dte:35, delta:0.52, theta:-12, catalyst:"Order backlog · upgrade", conv:5, kelly:0.16, why:"Low IV-rank (34) + strong momentum → buy premium, not spread. Cheap optionality into automation cycle.", risk:"none material", riskTone:"gn" },
  { sym:"DMOB", spot:67.42, dir:"bull", strat:"Bull Call Spread", structure:"Jul18 68/78C", debit:3.10, maxLoss:310, maxGain:690, be:71.10, pop:41, rr:"2.2", ivr:48, dte:35, delta:0.34, theta:-6, catalyst:"Breakout base #2 · ER 11d", conv:4, kelly:0.11, why:"Mid IV-rank → defined-risk spread caps cost. Short leg above T1 funds the long.", risk:"earnings in 11d (pre-T1)", riskTone:"amb" },
  { sym:"DMOC", spot:29.40, dir:"bull", strat:"Call Debit (ER)", structure:"Jun13 30C", debit:1.85, maxLoss:185, maxGain:"open", be:31.85, pop:38, rr:"2.8", ivr:82, dte:14, delta:0.44, theta:-9, catalyst:"Phase-2 readout", conv:3, kelly:0.04, why:"Binary catalyst trade — only justified as a small lottery into the readout.", risk:"IV-crush 82 IVR · binary", riskTone:"rd" },
  { sym:"DMOE", spot:56.10, dir:"bull", strat:"Long Call", structure:"Jul03 57C", debit:2.40, maxLoss:240, maxGain:"open", be:59.40, pop:43, rr:"2.5", ivr:31, dte:21, delta:0.49, theta:-7, catalyst:"Energy bid · sector RS", conv:4, kelly:0.10, why:"Cheap IV + sector tailwind. Sympathy strength; ride the sector, defined risk.", risk:"sector-beta dependent", riskTone:"amb" },
  { sym:"DMOI", spot:17.20, dir:"bull", strat:"Call Calendar", structure:"Jun20/Jul18 18C", debit:0.95, maxLoss:95, maxGain:480, be:"~18", pop:52, rr:"5.1", ivr:64, dte:35, delta:0.18, theta:"+", catalyst:"M&A rumor", conv:3, kelly:0.06, why:"Elevated IV + uncertain timing → calendar sells near-dated rich vol, owns far-dated.", risk:"gap kills calendar", riskTone:"amb" },
  { sym:"DMOL", spot:72.55, dir:"bear", strat:"Put Debit", structure:"Jul18 70/60P", debit:3.20, maxLoss:320, maxGain:680, be:66.80, pop:44, rr:"2.1", ivr:71, dte:35, delta:-0.38, theta:-5, catalyst:"FDA CRL · downgrade", conv:4, kelly:0.09, why:"Post-CRL pipeline reset + distribution. Defined-risk put spread; IV rich so spread over naked put.", risk:"dead-cat bounce", riskTone:"amb" },
  { sym:"DMOD", spot:142.10, dir:"bull", strat:"Bull Call Spread", structure:"Jul18 145/160C", debit:5.20, maxLoss:520, maxGain:980, be:150.20, pop:39, rr:"1.9", ivr:38, dte:35, delta:0.36, theta:-8, catalyst:"Pullback hold · MA stack", conv:3, kelly:0.0, why:"Only if pullback holds 145 on volume. Otherwise wait.", risk:"below R:R floor (1.9)", riskTone:"rd" },
  { sym:"DMOF", spot:41.80, dir:"bull", strat:"Long Call", structure:"Jul03 42C", debit:1.95, maxLoss:195, maxGain:"open", be:43.95, pop:42, rr:"2.4", ivr:36, dte:21, delta:0.48, theta:-6, catalyst:"Flag · gap & go", conv:3, kelly:0.07, why:"Clean flag, cheap vol. Lower conviction — confirm breakout before entry.", risk:"unconfirmed breakout", riskTone:"amb" },
  { sym:"DMOG", spot:88.30, dir:"bull", strat:"Long Call", structure:"Aug15 90C", debit:5.10, maxLoss:510, maxGain:"open", be:95.10, pop:45, rr:"2.9", ivr:29, dte:63, delta:0.53, theta:-5, catalyst:"Stage-2 trend · RS new high", conv:5, kelly:0.14, why:"Cheapest IV on the board (29) + leadership RS. Longer-dated to ride the primary trend with low theta.", risk:"none material", riskTone:"gn" },
  { sym:"DMOH", spot:124.60, dir:"bull", strat:"Bull Call Spread", structure:"Jul18 125/140C", debit:5.60, maxLoss:560, maxGain:940, be:130.60, pop:43, rr:"1.7", ivr:55, dte:35, delta:0.41, theta:-9, catalyst:"Cup & handle · vol dry-up", conv:4, kelly:0.0, why:"Textbook setup but the spread prices poorly — R:R below floor at these strikes.", risk:"below R:R floor (1.7)", riskTone:"rd" },
  { sym:"DMON", spot:53.90, dir:"bull", strat:"Long Call", structure:"Jul18 55C", debit:2.85, maxLoss:285, maxGain:"open", be:57.85, pop:44, rr:"2.6", ivr:41, dte:35, delta:0.50, theta:-7, catalyst:"SMC bull BOS · OB retest", conv:4, kelly:0.10, why:"Smart-money structure flip + cheap-ish vol. ATM delta for clean directional exposure.", risk:"wide bid/ask (illiquid)", riskTone:"amb" },
  { sym:"DMOJ", spot:198.20, dir:"bear", strat:"Put Debit", structure:"Jul18 195/175P", debit:6.30, maxLoss:630, maxGain:1370, be:188.70, pop:47, rr:"2.2", ivr:52, dte:35, delta:-0.44, theta:-8, catalyst:"Distribution · CHoCH down", conv:4, kelly:0.09, why:"Wyckoff distribution + change-of-character. Spread caps cost on mid-IV.", risk:"counter-trend vs market", riskTone:"amb" },
  { sym:"DMOM", spot:34.10, dir:"bull", strat:"Long Call", structure:"Aug15 35C", debit:2.20, maxLoss:220, maxGain:"open", be:37.20, pop:43, rr:"2.7", ivr:33, dte:63, delta:0.49, theta:-4, catalyst:"Insider cluster buy", conv:4, kelly:0.11, why:"Form-4 cluster buying + cheap vol. Longer DTE lets the thesis play out with low decay.", risk:"slow-moving thesis", riskTone:"amb" },
  { sym:"HAVN", spot:61.75, dir:"bull", strat:"Bull Call Spread", structure:"Jul18 62/72C", debit:3.40, maxLoss:340, maxGain:660, be:65.40, pop:42, rr:"1.9", ivr:58, dte:35, delta:0.38, theta:-7, catalyst:"Flag breakout · ER 18d", conv:3, kelly:0.0, why:"Setup ok but earnings lands mid-trade and R:R sits under the floor.", risk:"earnings + below R:R", riskTone:"rd" },
  { sym:"DMOK", spot:45.30, dir:"bull", strat:"Long Call", structure:"Jul03 46C", debit:2.05, maxLoss:205, maxGain:"open", be:48.05, pop:44, rr:"2.5", ivr:37, dte:21, delta:0.50, theta:-6, catalyst:"Momentum accel · RS rising", conv:4, kelly:0.10, why:"Accelerating RS + cheap vol. ATM call for a clean momentum continuation play.", risk:"extended from MA", riskTone:"amb" },
  { sym:"DMOO", spot:112.40, dir:"bear", strat:"Long Put", structure:"Jul18 110P", debit:4.10, maxLoss:410, maxGain:"open", be:105.90, pop:42, rr:"3.0", ivr:36, dte:35, delta:-0.47, theta:-8, catalyst:"Failed breakout · RS rollover", conv:4, kelly:0.10, why:"Cheap IV on a short → buy the put outright. Failed breakout + relative-strength rollover.", risk:"none material", riskTone:"gn" },
];

function SurfaceOptionsIdeas({ onTicker }) {
  const [filter, setFilter] = useOI("all");
  const [sort, setSort] = useOI("conv");
  const [acct, setAcct] = useOI(() => { try { return +localStorage.getItem("oi-acct") || 50000; } catch (e) { return 50000; } });
  const [kFrac, setKFrac] = useOI(() => { try { return +localStorage.getItem("oi-kfrac") || 0.5; } catch (e) { return 0.5; } });
  const setAcctP = (v) => { setAcct(v); try { localStorage.setItem("oi-acct", v); } catch (e) {} };
  const setKFracP = (v) => { setKFrac(v); try { localStorage.setItem("oi-kfrac", v); } catch (e) {} };

  // Real UOA-derived ideas (served) or demo (standalone showcase).
  const realIdeas = oiRealIdeas();
  const REAL = !!realIdeas;
  const IDEAS = realIdeas || OI_IDEAS_DEMO;

  // Served + no live UOA tape → honest-empty. Never fabricate option ideas.
  if (OI_SERVED && !realIdeas) {
    return (
      <div className="surface wsx wsx--gn oidea">
        <div className="wsx-hdr">
          <div className="wsx-hdr-l">
            <div className="wsx-eyebrow mono">TOP OPTIONS TO BUY · RANKED IDEAS</div>
            <h1 className="wsx-title mono">No options ideas right now</h1>
            <div className="wsx-sub mono dim2">ideas are derived from the live unusual-options-activity tape</div>
          </div>
          <div className="wsx-hdr-r"><span className="mono dim2">src · options_flow_top30 (UOA)</span></div>
        </div>
        <div className="wsx-body"><div className="lab-verdict mono dim2" style={{ padding: 24, lineHeight: 1.7 }}>
          No unusual-options-activity names on the tape from the latest scan, so there
          are no option ideas to surface. This board is built only from real UOA
          aggregates (<b className="cop">critical.options_flow_top30</b>) — it stays
          empty rather than show fabricated tickets. Per-leg pricing (debit / POP /
          Greeks / Kelly) lives on each name's <b>Options lens</b> (Schwab chain).
        </div></div>
      </div>
    );
  }

  // position sizing: fractional-Kelly capital → contracts, capped at 5% risk/idea.
  // Only applies to demo ideas (real UOA carries no priced Kelly/max-loss).
  const sizeFor = (x) => {
    if (!x.kelly || x.kelly <= 0 || !x.maxLoss) return { contracts: 0, dollars: 0, pctRisk: 0, note: REAL ? "price on lens" : "skip" };
    const kCap = Math.min(x.kelly * kFrac, 0.05);           // half-Kelly, hard 5% cap
    const riskBudget = acct * kCap;
    const contracts = Math.max(0, Math.floor(riskBudget / x.maxLoss));
    const dollars = contracts * x.maxLoss;
    return { contracts, dollars, pctRisk: acct ? (dollars / acct) * 100 : 0, note: contracts === 0 ? "below 1 lot" : "" };
  };

  const rows = useOIm(() => {
    let r = IDEAS;
    if (filter === "bull") r = r.filter(x => x.dir === "bull");
    if (filter === "bear") r = r.filter(x => x.dir === "bear");
    if (filter === "cheap") r = r.filter(x => x.ivr != null && x.ivr < 45);
    if (filter === "spread") r = r.filter(x => x.strat.includes("Spread") || x.strat.includes("Calendar"));
    if (filter === "long") r = r.filter(x => x.strat.includes("Long") || x.strat.includes("Debit"));
    if (filter === "actionable") r = r.filter(x => (x.conv || 0) >= 4 && parseFloat(x.rr) >= 2.0);
    const sf = (x) => sort === "conv" ? (x.conv || 0) : sort === "rr" ? (parseFloat(x.rr) || 0) : sort === "size" ? sizeFor(x).contracts : (x.pop || x.premM || 0);
    r = [...r].sort((a, b) => sf(b) - sf(a));
    return r;
  }, [filter, sort, acct, kFrac, REAL]);

  const best = IDEAS.slice().sort((a, b) => REAL ? (b.premM || 0) - (a.premM || 0) : (b.conv || 0) - (a.conv || 0))[0];
  const nActionable = IDEAS.filter(x => (x.conv || 0) >= 4 && parseFloat(x.rr) >= 2.0).length;
  // live sizing summary across all ideas (updates with account / Kelly)
  const sized = IDEAS.map(sizeFor).filter(s => s.contracts > 0);
  const nSizeable = IDEAS.filter(x => x.kelly > 0).length;
  const deployed = sized.reduce((a, s) => a + s.dollars, 0);
  const totRiskPct = acct ? (deployed / acct) * 100 : 0;
  const nSized = sized.length;
  const num = (v, fn) => (v == null || (typeof v === "number" && !Number.isFinite(v))) ? "—" : (fn ? fn(v) : v);

  return (
    <div className="surface wsx wsx--gn oidea">
      <div className="wsx-hdr">
        <div className="wsx-hdr-l">
          <div className="wsx-eyebrow mono">TOP OPTIONS TO BUY · RANKED IDEAS</div>
          <h1 className="wsx-title mono">Options Ideas</h1>
          <div className="wsx-sub mono dim2">{REAL ? "live unusual-options-activity tape · bias from P/C · structure by IV-rank · price the leg on each Options lens" : "concrete option tickets · ranked by edge · IV-aware structure · Schwab chains"}</div>
        </div>
        <div className="wsx-hdr-r">
          {!REAL && <FreshnessPill state="live" age="6s" />}
          <span className="mono dim2">{IDEAS.length} {REAL ? "UOA names · price legs on Options lens" : `ideas · ${nActionable} actionable · Schwab chains`}</span>
        </div>
      </div>

      {!REAL && <div className="oi-sizebar">
        <span className="label-cap">Position sizing</span>
        <label className="oi-size-fld mono">Account
          <span className="oi-size-input">$<input type="number" min="0" step="1000" value={acct || ""} placeholder="50000" onChange={e => setAcctP(e.target.value === "" ? 0 : Math.max(0, +e.target.value))} /></span>
        </label>
        <label className="oi-size-fld mono">Kelly fraction
          <select value={kFrac} onChange={e => setKFracP(+e.target.value)}>
            <option value={0.25}>¼ Kelly (conservative)</option>
            <option value={0.5}>½ Kelly (recommended)</option>
            <option value={1}>Full Kelly (aggressive)</option>
          </select>
        </label>
        <span className="oi-size-live mono">
          <span className="oi-size-live-cell"><span className="dim2">Deployed</span> <b className="cop">${(deployed / 1000).toFixed(1)}k</b></span>
          <span className="oi-size-live-cell"><span className="dim2">Total risk</span> <b className={totRiskPct > 25 ? "dn" : "up"}>{totRiskPct.toFixed(1)}%</b></span>
          <span className="oi-size-live-cell"><span className="dim2">Sized</span> <b>{nSized}/{nSizeable}</b></span>
        </span>
        <span className="oi-size-note mono dim2">auto-sized from each idea's Kelly edge × your fraction, capped 5%/idea · updates live</span>
      </div>}

      {/* Best idea hero */}
      {best && <div className="oi-best">
        <div className="oi-best-l">
          <div className="oi-best-eyebrow mono">{REAL ? "🔊 LOUDEST UOA NAME" : "⭐ HIGHEST-CONVICTION IDEA"}</div>
          <div className="oi-best-row">
            <span className="oi-best-sym mono">{best.sym}</span>
            <span className={`oi-best-dir oi-best-dir--${best.dir}`}>{best.dir === "bull" ? "▲ BULLISH" : "▼ BEARISH"}</span>
            <span className="oi-best-strat mono">{best.strat}</span>
          </div>
          <div className="oi-best-struct mono">{best.structure} <span className="dim2">{REAL
            ? `· net premium ${best.premM >= 0.01 ? "$" + best.premM.toFixed(1) + "M" : "—"} · price the leg on the Options lens`
            : `· debit ${best.debit != null ? "$" + best.debit.toFixed(2) : "—"} ($${best.maxLoss} max loss) · BE $${best.be}`}</span></div>
          <div className="oi-best-why mono dim2">{best.why}</div>
        </div>
        <div className="oi-best-r">
          <div className="oi-best-kpi"><div className="mono dim2">R:R</div><div className="mono kpi-tone--gn oi-best-kpi-v">{num(best.rr)}</div></div>
          <div className="oi-best-kpi"><div className="mono dim2">POP</div><div className="mono oi-best-kpi-v">{num(best.pop, v => v + "%")}</div></div>
          <div className="oi-best-kpi"><div className="mono dim2">IV RANK</div><div className={`mono oi-best-kpi-v ${best.ivr != null && best.ivr < 45 ? "up" : "warn"}`}>{num(best.ivr, v => v + "%")}</div></div>
          <div className="oi-best-kpi"><div className="mono dim2">{REAL ? "PREM" : "CONV"}</div><div className="mono kpi-tone--gn oi-best-kpi-v">{REAL ? (best.premM >= 0.01 ? "$" + best.premM.toFixed(1) + "M" : "—") : num(best.conv, v => v + "/5")}</div></div>
        </div>
      </div>}

      <div className="lab-tabs">
        {[["all","All ideas"],["actionable","✓ Actionable"],["bull","Bullish"],["bear","Bearish"],["cheap","Cheap IV"],["long","Long premium"],["spread","Spreads"]].map(([id,l])=>(
          <button key={id} className={`lab-tab ${filter===id?"is-on":""}`} onClick={()=>setFilter(id)}>{l}</button>
        ))}
        <div className="seg" style={{marginLeft:"auto"}}>
          {(REAL ? [["pop","Premium"],["rr","Bias"]] : [["conv","Conviction"],["rr","R:R"],["pop","POP"],["size","Size"]]).map(([id,l])=>(
            <button key={id} className={`seg-btn ${sort===id?"is-on":""}`} onClick={()=>setSort(id)}>{l}</button>
          ))}
        </div>
      </div>

      <div className="wsx-body">
        <table className="dtable wsx-tbl oi-tbl">
          <thead><tr>
            <th>Sym</th><th>Bias</th><th>Strategy</th><th>Structure</th>
            <th className="r">{REAL ? "Net prem" : "Debit"}</th>
            <th className="r">{REAL ? "P/C" : "Max Loss"}</th><th className="r">R:R</th><th className="r">POP</th><th className="r">IV Rank</th>
            <th>{REAL ? "UOA detail" : "Catalyst"}</th><th>{REAL ? "Note" : "Why not"}</th>
            <th className="r">{REAL ? "Prem" : "Conv"}</th><th className="r">Size</th><th></th>
          </tr></thead>
          <tbody>{rows.map((x,i)=>{
            const sz = sizeFor(x);
            return (
            <tr key={i} onClick={()=>onTicker(x.sym)}>
              <td className="mono"><b>{x.sym}</b><span className="dim2"> {x.spot ? "$" + x.spot.toFixed(0) : ""}</span></td>
              <td><span className={`of-bias of-bias--${x.dir}`}>{x.dir==="bull"?"▲":"▼"}</span></td>
              <td className="mono">{x.strat}</td>
              <td className="mono oi-struct">{x.structure}</td>
              <td className="r mono tabular cop">{REAL ? (x.premM >= 0.01 ? "$" + x.premM.toFixed(1) + "M" : "—") : "$" + x.debit.toFixed(2)}</td>
              <td className="r mono tabular dn">{REAL ? num(x.pcr, v => v.toFixed(2)) : "$" + x.maxLoss}</td>
              <td className={`r mono tabular ${parseFloat(x.rr)>=2?"up":"warn"}`}><b>{num(x.rr)}</b></td>
              <td className="r mono tabular">{num(x.pop, v => v + "%")}</td>
              <td className={`r mono tabular ${x.ivr != null && x.ivr<45?"up":x.ivr != null && x.ivr<70?"warn":"dn"}`}>{num(x.ivr, v => v + "%")}</td>
              <td className="mono dim2">{x.catalyst}</td>
              <td><span className={`oi-risk oi-risk--${x.riskTone}`}>{x.risk}</span></td>
              <td className="r">{REAL
                ? <span className="mono dim2">{x.premM >= 0.01 ? "$" + x.premM.toFixed(1) + "M" : "—"}</span>
                : <span className="oi-conv mono" data-c={x.conv}>{"●".repeat(x.conv)}<span className="oi-conv-off">{"●".repeat(5-x.conv)}</span></span>}</td>
              <td className="r mono tabular">{sz.contracts>0 ? <span className="oi-size-cell"><b className="up">{sz.contracts}×</b><span className="dim2"> ${(sz.dollars/1000).toFixed(1)}k · {sz.pctRisk.toFixed(1)}%</span></span> : <span className="dim2">{sz.note}</span>}</td>
              <td className="r mono dim">›</td>
            </tr>
          );})}</tbody>
        </table>
      </div>

      <div className="of-playbook mono">
        <span className="of-pb-tag" style={{color:"var(--gn)"}}>STRUCTURE RULES</span>
        <span className="of-pb-txt">IV-rank picks the structure: <b>&lt;45</b> = buy premium (long call/put — cheap optionality); <b>45–70</b> = debit spread (cap the vol you overpay); <b>&gt;70</b> = sell premium or calendar (IV rich, time-decay works for you). R:R ≥ 2.0 floor. Earnings inside the hold window → size −25% or skip the binary. Every idea is a starting structure — set your own size off the Risk lens.</span>
      </div>

      <div className="pm-note mono dim2">
        {REAL
          ? <>Names are the live unusual-options-activity tape (<b className="cop">critical.options_flow_top30</b>): bias from put/call ratio, structure suggested by IV-rank, net premium from the aggregate. Per-leg pricing (debit / max-loss / BE / POP / Greeks / Kelly) is <b>not</b> fabricated here — open a name's <b>Options lens</b> for the real Schwab chain. Click any row → 14-lens detail.</>
          : <>Ideas ranked from scan verdicts × <b>Schwab /markets/options/chains</b> (real bid/ask/IV/Greeks, 6s poll) · structure auto-selected by IV-rank · debit/max-loss/BE/POP Black-Scholes priced · catalyst from EODHD /calendar + /news. Click any row → 14-lens detail + full Options lens.</>}
      </div>
    </div>
  );
}

window.SurfaceOptionsIdeas = SurfaceOptionsIdeas;

// Unified Options surface: Flow + Ideas sub-tabs (mirrors the ETFs pattern).
function SurfaceOptions({ onTicker }) {
  const [tab, setTab] = useOI("flow");
  return (
    <div className="etfs-wrap">
      <div className="etfs-tabbar">
        <div className="etfs-tabs">
          <button className={`etfs-tab ${tab === "flow" ? "is-on" : ""}`} onClick={() => setTab("flow")}>
            <span className="etfs-tab-l">Options Flow</span>
            <span className="etfs-tab-s mono dim2">smart-money tape · UOA</span>
          </button>
          <button className={`etfs-tab ${tab === "ideas" ? "is-on" : ""}`} onClick={() => setTab("ideas")}>
            <span className="etfs-tab-l">Options Ideas</span>
            <span className="etfs-tab-s mono dim2">ranked tickets · IV-aware</span>
          </button>
          <button className={`etfs-tab ${tab === "track" ? "is-on" : ""}`} onClick={() => setTab("track")}>
            <span className="etfs-tab-l">Track Record</span>
            <span className="etfs-tab-s mono dim2">1Y · hot / failed</span>
          </button>
        </div>
      </div>
      {tab === "flow"
        ? <SurfaceOptionsFlow onTicker={onTicker} />
        : tab === "ideas"
        ? <SurfaceOptionsIdeas onTicker={onTicker} />
        : (window.OptionsTrackRecord ? <window.OptionsTrackRecord onTicker={onTicker} /> : null)}
    </div>
  );
}

window.SurfaceOptions = SurfaceOptions;

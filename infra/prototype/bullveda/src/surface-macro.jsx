// surface-macro.jsx — Macro & Economic event calendar
// Sources: Trading Economics + FRED releases, rate-cut odds from CME FedWatch (fed funds futures),
// yields from US Treasury / FRED, DXY & VIX from CBOE/ICE.
const { useState: useMacS } = React;

const MAC_EVENTS = [
  { d:"TODAY", time:"08:30", region:"US", imp:3, ev:"Core CPI (MoM)", fc:"+0.3%", prior:"+0.4%", act:"+0.2%", surprise:"down" },
  { d:"TODAY", time:"10:00", region:"US", imp:2, ev:"NAHB Housing Index", fc:"42", prior:"41", act:"43", surprise:"up" },
  { d:"TODAY", time:"13:00", region:"US", imp:2, ev:"10Y Note Auction", fc:"—", prior:"4.31%", act:null, surprise:null },
  { d:"TUE 03", time:"08:30", region:"US", imp:3, ev:"PPI (MoM)", fc:"+0.2%", prior:"+0.5%", act:null, surprise:null },
  { d:"TUE 03", time:"All day", region:"EU", imp:2, ev:"ECB Lagarde Speech", fc:"—", prior:"—", act:null, surprise:null },
  { d:"WED 04", time:"14:00", region:"US", imp:3, ev:"FOMC Rate Decision", fc:"5.25%", prior:"5.50%", act:null, surprise:null, star:true },
  { d:"WED 04", time:"14:30", region:"US", imp:3, ev:"Powell Press Conf.", fc:"—", prior:"—", act:null, surprise:null },
  { d:"THU 05", time:"08:30", region:"US", imp:3, ev:"Initial Jobless Claims", fc:"232k", prior:"229k", act:null, surprise:null },
  { d:"THU 05", time:"08:30", region:"US", imp:2, ev:"Retail Sales (MoM)", fc:"+0.4%", prior:"+0.6%", act:null, surprise:null },
  { d:"FRI 06", time:"08:30", region:"US", imp:3, ev:"Non-Farm Payrolls", fc:"180k", prior:"206k", act:null, surprise:null, star:true },
  { d:"FRI 06", time:"08:30", region:"US", imp:3, ev:"Unemployment Rate", fc:"4.0%", prior:"4.1%", act:null, surprise:null },
  { d:"FRI 06", time:"10:00", region:"US", imp:2, ev:"U. Michigan Sentiment", fc:"69.5", prior:"69.1", act:null, surprise:null },
];
// CME FedWatch implied probabilities for next meeting
const MAC_FED = [
  { lbl:"Hold 5.50%", p:18 },
  { lbl:"−25bp → 5.25%", p:67 },
  { lbl:"−50bp → 5.00%", p:15 },
];
const MAC_REGIME = [
  { k:"10Y YIELD", v:"4.28%", d:"−6bp", tone:"gn" },
  { k:"2s10s", v:"−18bp", d:"steepening", tone:"amb" },
  { k:"DXY", v:"104.2", d:"−0.3%", tone:"gn" },
  { k:"HY CREDIT (OAS)", v:"312bp", d:"+4bp", tone:"amb" },
  { k:"WTI CRUDE", v:"$78.4", d:"+1.1%", tone:"dim" },
  { k:"GOLD", v:"$2,384", d:"+0.6%", tone:"dim" },
];
const impDot = n => "●".repeat(n) + "○".repeat(3 - n);

// earnings reporters this week (catalyst calendar — full detail)
const MAC_EARN = [
  { d:"TODAY", time:"AMC", sym:"DOCU", name:"DocuSign", days:0, tier:"STRONG", prob:71, est:"$0.82", whisper:"$0.87", impMove:8.4, hist:"7/8", sector:"Tech" },
  { d:"TODAY", time:"AMC", sym:"ARGN", name:"Argentum Robotics", days:0, tier:"SOLID", prob:64, est:"$1.57", whisper:"$1.61", impMove:9.1, hist:"8/8", sector:"Tech" },
  { d:"TUE 03", time:"BMO", sym:"NVRH", name:"Novara Health", days:1, tier:"STRONG", prob:69, est:"$2.14", whisper:"$2.22", impMove:6.8, hist:"6/8", sector:"Healthcare" },
  { d:"WED 04", time:"AMC", sym:"ARCM", name:"Arclight Materials", days:2, tier:"MODERATE", prob:55, est:"$0.91", whisper:"$0.92", impMove:7.2, hist:"5/8", sector:"Materials" },
  { d:"THU 05", time:"BMO", sym:"GENO", name:"Genoa Biosystems", days:3, tier:"SOLID", prob:63, est:"$0.44", whisper:"$0.48", impMove:11.5, hist:"6/8", sector:"Healthcare" },
  { d:"FRI 06", time:"AMC", sym:"FLNX", name:"Flux Nexus", days:4, tier:"STRONG", prob:73, est:"$1.18", whisper:"$1.25", impMove:8.9, hist:"7/8", sector:"Tech" },
  { d:"FRI 06", time:"BMO", sym:"BORA", name:"Borealis Aero", days:4, tier:"MODERATE", prob:52, est:"$0.67", whisper:"$0.67", impMove:6.1, hist:"4/8", sector:"Industrials" },
];
const earnTone = t => t === "STRONG" ? "gn" : t === "SOLID" ? "cy" : "amb";
// the 6 beat-model signals (per ruleset)
const MAC_EARN_SIGNALS = [
  ["Historical beat rate", 25], ["Price run-up vs sector", 20], ["Volume accumulation", 15],
  ["Analyst positioning", 15], ["Options flow / IV", 15], ["Sector co-movers", 10],
];

function MacKpi({ k, v, tone, s }) {
  return <div className={`wsx-kpi wsx-kpi--${tone}`}><div className="wsx-kpi-l mono">{k}</div><div className={`wsx-kpi-v mono kpi-tone--${tone}`}>{v}</div><div className="wsx-kpi-s mono dim2">{s}</div></div>;
}

function SurfaceMacro({ onTicker }) {
  const days = [...new Set(MAC_EVENTS.map(e => e.d))];
  const [tab, setTab] = useMacS("economic");
  const eDays = [...new Set(MAC_EARN.map(e => e.d))];
  return (
    <div className="surface wsx wsx--cy mcx">
      <div className="wsx-hdr">
        <div className="wsx-hdr-l">
          <div className="wsx-eyebrow mono">MACRO · EVENTS · EARNINGS CATALYSTS</div>
          <h1 className="wsx-title mono">Economic · Catalyst Calendar</h1>
          <div className="wsx-sub mono dim2">high-impact macro releases + earnings reporters · rate-decision odds · the events that gate swing entries</div>
        </div>
        <div className="wsx-hdr-r"><FreshnessPill state="live" age="31s" /><span className="mono dim2">src · Trading Economics · FRED · CME FedWatch · EODHD</span></div>
      </div>

      <div className="wsx-kpis mcx-kpis">
        <MacKpi k="NEXT HIGH-IMPACT" v="Core CPI" tone="rd" s="today 08:30 ET" />
        <MacKpi k="FOMC" v="2 days" tone="amb" s="Wed · −25bp priced" />
        <MacKpi k="CUT ODDS" v="67%" tone="gn" s="−25bp · CME FedWatch" />
        <MacKpi k="EARNINGS · WK" v={`${MAC_EARN.length}`} tone="violet" s={`${MAC_EARN.filter(e=>e.tier==="STRONG").length} STRONG tier`} />
        <MacKpi k="VIX" v="14.2" tone="gn" s="contango · calm" />
        <MacKpi k="DXY" v="104.2" tone="cy" s="−0.3% · USD soft" />
      </div>

      <div className="lab-tabs mcx-tabs">
        {[["economic", "Economic Releases"], ["earnings", `Earnings Catalysts · ${MAC_EARN.length}`]].map(([id, l]) => (
          <button key={id} className={`lab-tab ${tab === id ? "is-on" : ""}`} onClick={() => setTab(id)}>{l}</button>
        ))}
      </div>

      {tab === "economic" ? (
      <div className="mcx-grid">
        <div className="wsx-card mcx-cal">
          <div className="rkx-card-h mono">RELEASES · THIS WEEK <span className="dim2">· ● importance · actual vs forecast</span></div>
          {days.map(d => (
            <div key={d} className="mcx-day">
              <div className="mcx-day-h mono">{d}</div>
              {MAC_EVENTS.filter(e => e.d === d).map((e, i) => (
                <div key={i} className={`mcx-row ${e.star ? "is-star" : ""} imp-${e.imp}`}>
                  <span className="mono mcx-time">{e.time}</span>
                  <span className={`mcx-reg mcx-reg--${e.region.toLowerCase()}`}>{e.region}</span>
                  <span className={`mono mcx-imp imp--${e.imp}`}>{impDot(e.imp)}</span>
                  <span className="mcx-ev">{e.ev}{e.star && <span className="mcx-flag mono">KEY</span>}</span>
                  <span className="mono mcx-fc">{e.act ? <b className={`kpi-tone--${e.surprise === "up" ? "gn" : e.surprise === "down" ? "rd" : "dim"}`}>{e.act}</b> : <span className="dim2">{e.fc}</span>}</span>
                  <span className="mono dim2 mcx-prior">{e.act ? `fc ${e.fc}` : `prior ${e.prior}`}</span>
                </div>
              ))}
            </div>
          ))}
        </div>
        <div className="mcx-side">
          <div className="wsx-card mcx-fed">
            <div className="rkx-card-h mono">FOMC · IMPLIED ODDS</div>
            {MAC_FED.map((f, i) => (
              <div key={i} className="mcx-fed-row">
                <span className="mono mcx-fed-l">{f.lbl}</span>
                <span className="mcx-fed-bar"><i style={{ width:`${f.p}%` }} className={f.p >= 50 ? "kpi-tone-bg--gn" : ""} /></span>
                <span className={`mono mcx-fed-v ${f.p >= 50 ? "up" : "dim2"}`}>{f.p}%</span>
              </div>
            ))}
            <div className="rkx-note mono dim2">A −25bp cut is the base case. A hawkish hold (18%) is the tail risk for long-biased books — size into Wed accordingly.</div>
          </div>
          <div className="wsx-card mcx-regime">
            <div className="rkx-card-h mono">REGIME DASHBOARD</div>
            <div className="mcx-regime-grid">
              {MAC_REGIME.map((r, i) => (
                <div key={i} className="mcx-reg-tile">
                  <div className="mono dim2 mcx-reg-k">{r.k}</div>
                  <div className="mono mcx-reg-v">{r.v}</div>
                  <div className={`mono mcx-reg-d kpi-tone--${r.tone}`}>{r.d}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
      ) : (
      <div className="mcx-earntab">
        <div className="wsx-card">
          <div className="rkx-card-h mono">EARNINGS CATALYSTS · THIS WEEK <span className="dim2">· EODHD calendar → 6-signal beat model · click a row for the ticker</span></div>
          <table className="dtable wsx-tbl mcx-earntbl">
            <thead><tr><th>When</th><th>Sym</th><th>Company</th><th>Sector</th><th className="r">Est</th><th className="r">Whisper</th><th className="r">Impl. move</th><th className="r">Hist</th><th className="r">Beat prob</th><th>Tier</th></tr></thead>
            <tbody>{MAC_EARN.map((e, i) => (
              <tr key={i} onClick={() => onTicker && onTicker(e.sym)} style={{ cursor: "pointer" }}>
                <td className="mono dim2">{e.d} · <span className="mono">{e.time}</span></td>
                <td className="mono"><b>{e.sym}</b></td>
                <td>{e.name}</td>
                <td className="dim2">{e.sector}</td>
                <td className="r mono tabular dim2">{e.est}</td>
                <td className="r mono tabular cop">{e.whisper}</td>
                <td className="r mono tabular">±{e.impMove}%</td>
                <td className="r mono tabular dim2">{e.hist}</td>
                <td className="r"><span className="mcx-prob-bar"><i style={{ width:`${e.prob}%` }} className={`kpi-tone-bg--${earnTone(e.tier)}`} /></span><b className={`mono kpi-tone--${earnTone(e.tier)}`}>{e.prob}%</b></td>
                <td><span className={`mcx-earn-tier kpi-tone--${earnTone(e.tier)}`}>{e.tier}</span></td>
              </tr>
            ))}</tbody>
          </table>
          <div className="rkx-note mono dim2">Reporters are forced into scan coverage so they get full analysis. Beat-probability tiers come from the 6-signal composite below; open <b>Earnings AI</b> for per-ticker prediction logs &amp; calibration.</div>
        </div>
        <div className="mcx-earnside">
          <div className="wsx-card">
            <div className="rkx-card-h mono">6-SIGNAL BEAT MODEL <span className="dim2">· composite weights</span></div>
            <div className="mcx-sig">
              {MAC_EARN_SIGNALS.map(([k, w], i) => (
                <div key={i} className="mcx-sig-row">
                  <span className="mcx-sig-k">{k}</span>
                  <span className="mcx-sig-bar"><i style={{ width:`${w * 4}%` }} /></span>
                  <span className="mono dim2 mcx-sig-w">{w}</span>
                </div>
              ))}
            </div>
            <div className="rkx-note mono dim2">Scored 0–100 then bucketed STRONG / SOLID / MODERATE. Signal #1 (history) and #6 (cohort) feed back from the outcome log after each report.</div>
          </div>
          <div className="wsx-card">
            <div className="rkx-card-h mono">TIER CALIBRATION <span className="dim2">· last 90d</span></div>
            <div className="mcx-calib">
              {[["STRONG", 71, "gn"], ["SOLID", 63, "cy"], ["MODERATE", 54, "amb"]].map(([t, h, c], i) => (
                <div key={i} className="mcx-calib-row">
                  <span className={`mcx-earn-tier kpi-tone--${c}`}>{t}</span>
                  <span className="mcx-calib-bar"><i style={{ width:`${h}%` }} className={`kpi-tone-bg--${c}`} /></span>
                  <span className={`mono kpi-tone--${c}`}>{h}%</span>
                </div>
              ))}
            </div>
            <div className="rkx-note mono dim2">STRONG-tier predictions have beaten ~71% of the time historically — the honesty check on the model.</div>
          </div>
        </div>
      </div>
      )}
    </div>
  );
}
window.SurfaceMacro = SurfaceMacro;

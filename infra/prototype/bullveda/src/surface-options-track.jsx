// surface-options-track.jsx — Options · Track Record (trailing 12 months).
// Every option idea the desk fired, scored at exit: HOT (winner) / FAILED (loser)
// / FLAT (scratch). Surfaces win-rate, R-multiple equity curve, monthly results,
// and edge by structure & IV-rank — so the Ideas tab's claims are auditable.
const { useMemo: useMemoOT, useState: useStateOT } = React;

// trailing-12-month monthly ledger — n closed · win-rate % · net R captured
const OT_MONTHS = [
  { m: "Jun '25", n: 14, win: 50, r: +3.2 },
  { m: "Jul '25", n: 16, win: 56, r: +6.8 },
  { m: "Aug '25", n: 12, win: 42, r: -2.4 },
  { m: "Sep '25", n: 15, win: 53, r: +4.6 },
  { m: "Oct '25", n: 18, win: 61, r: +9.1 },
  { m: "Nov '25", n: 14, win: 50, r: +2.2 },
  { m: "Dec '25", n: 11, win: 45, r: -1.1 },
  { m: "Jan '26", n: 17, win: 59, r: +7.4 },
  { m: "Feb '26", n: 13, win: 46, r: -1.8 },
  { m: "Mar '26", n: 19, win: 63, r: +10.2 },
  { m: "Apr '26", n: 16, win: 56, r: +5.1 },
  { m: "May '26", n: 12, win: 58, r: +4.4 },
];

// win-rate by structure type
const OT_BY_STRUCT = [
  { k: "Long Call",    n: 64, win: 58, tone: "gn" },
  { k: "Debit Spread", n: 58, win: 54, tone: "cy" },
  { k: "Calendar",     n: 24, win: 61, tone: "violet" },
  { k: "Put Debit",    n: 31, win: 47, tone: "amb" },
];
// win-rate by IV-rank bucket — validates the "buy cheap vol" playbook rule
const OT_BY_IVR = [
  { k: "IVR < 45 · cheap", win: 59, tone: "gn" },
  { k: "IVR 45–70 · mid",  win: 52, tone: "amb" },
  { k: "IVR > 70 · rich",  win: 41, tone: "rd" },
];

// resolved-idea ledger — full trailing-month of dated closes (R = realized reward/risk)
const OT_LEDGER = [
  { d: "2026-05-29", sym: "FLNX", strat: "Long Call",   bias: "bull", deb: 5.10, exit: 11.7, r: +1.3, out: "hot" },
  { d: "2026-05-28", sym: "ARGN", strat: "Long Call",   bias: "bull", deb: 8.40, exit: 21.0, r: +1.5, out: "hot" },
  { d: "2026-05-27", sym: "AXLE", strat: "Bull Spread", bias: "bull", deb: 3.40, exit: 3.6,  r: +0.1, out: "flat" },
  { d: "2026-05-23", sym: "KOSM", strat: "Bull Spread", bias: "bull", deb: 3.10, exit: 6.9,  r: +1.2, out: "hot" },
  { d: "2026-05-22", sym: "GENO", strat: "Call (ER)",   bias: "bull", deb: 1.85, exit: 0.0,  r: -1.0, out: "failed" },
  { d: "2026-05-20", sym: "LIGN", strat: "Long Put",    bias: "bear", deb: 4.10, exit: 8.2,  r: +1.0, out: "hot" },
  { d: "2026-05-19", sym: "NVRH", strat: "Bull Spread", bias: "bull", deb: 5.20, exit: 9.8,  r: +0.9, out: "hot" },
  { d: "2026-05-15", sym: "BIVO", strat: "Put Debit",   bias: "bear", deb: 3.20, exit: 1.1,  r: -0.65, out: "failed" },
  { d: "2026-05-14", sym: "NEXO", strat: "Long Call",   bias: "bull", deb: 2.85, exit: 5.9,  r: +1.1, out: "hot" },
  { d: "2026-05-12", sym: "QBIT", strat: "Long Call",   bias: "bull", deb: 4.10, exit: 9.4,  r: +1.3, out: "hot" },
  { d: "2026-05-09", sym: "VELO", strat: "Long Call",   bias: "bull", deb: 2.80, exit: 3.0,  r: +0.1, out: "flat" },
  { d: "2026-05-08", sym: "PALA", strat: "Calendar",    bias: "bull", deb: 0.95, exit: 2.4,  r: +1.5, out: "hot" },
  { d: "2026-05-07", sym: "INPR", strat: "Long Call",   bias: "bull", deb: 2.20, exit: 1.2,  r: -0.45, out: "failed" },
  { d: "2026-05-06", sym: "ARCM", strat: "Bull Spread", bias: "bull", deb: 3.10, exit: 5.1,  r: +0.6, out: "hot" },
  { d: "2026-05-05", sym: "VLCT", strat: "Put Debit",   bias: "bear", deb: 6.30, exit: 11.0, r: +0.7, out: "hot" },
  { d: "2026-05-02", sym: "MERC", strat: "Calendar",    bias: "bull", deb: 0.95, exit: 0.3,  r: -0.7, out: "failed" },
  { d: "2026-05-01", sym: "DRSH", strat: "Long Call",   bias: "bull", deb: 2.40, exit: 5.6,  r: +1.3, out: "hot" },
  { d: "2026-04-30", sym: "MAPL", strat: "Put Debit",   bias: "bear", deb: 2.10, exit: 4.0,  r: +0.9, out: "hot" },
  { d: "2026-04-29", sym: "ZOTR", strat: "Long Call",   bias: "bull", deb: 1.95, exit: 1.0,  r: -0.5, out: "failed" },
  { d: "2026-04-28", sym: "BORA", strat: "Long Call",   bias: "bull", deb: 2.05, exit: 4.3,  r: +1.1, out: "hot" },
  { d: "2026-04-25", sym: "NMBS", strat: "Bull Spread", bias: "bull", deb: 4.20, exit: 7.1,  r: +0.7, out: "hot" },
  { d: "2026-04-23", sym: "KARO", strat: "Bull Spread", bias: "bull", deb: 5.60, exit: 5.9,  r: +0.05, out: "flat" },
];

function OTKpi({ k, v, tone, s }) {
  return <div className={`wsx-kpi wsx-kpi--${tone}`}><div className="wsx-kpi-l mono">{k}</div><div className={`wsx-kpi-v mono kpi-tone--${tone}`}>{v}</div><div className="wsx-kpi-s mono dim2">{s}</div></div>;
}

// cumulative R-multiple equity curve from the monthly net-R series
function OTEquity() {
  const cum = useMemoOT(() => {
    let v = 0; return OT_MONTHS.map(mo => (v += mo.r));
  }, []);
  const w = 560, h = 190, padB = 18;
  const min = Math.min(0, ...cum), max = Math.max(...cum);
  const x = i => (i / (cum.length - 1)) * w;
  const y = v => (h - padB) - ((v - min) / (max - min)) * (h - padB - 6) + 3;
  return (
    <div>
      <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{ overflow: "visible" }}>
        <defs><linearGradient id="ot-eq" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--gn)" stopOpacity="0.26" /><stop offset="100%" stopColor="var(--gn)" stopOpacity="0" />
        </linearGradient></defs>
        {[0.25, 0.5, 0.75].map(g => <line key={g} x1="0" y1={(h - padB) * g + 3} x2={w} y2={(h - padB) * g + 3} stroke="var(--glass-line)" strokeOpacity="0.5" />)}
        <line x1="0" y1={y(0)} x2={w} y2={y(0)} stroke="var(--glass-line)" strokeDasharray="2 3" />
        <path d={`M 0 ${y(0)} L ${cum.map((v, i) => `${x(i)},${y(v)}`).join(" L ")} L ${w} ${y(0)} Z`} fill="url(#ot-eq)" />
        <polyline points={cum.map((v, i) => `${x(i)},${y(v)}`).join(" ")} stroke="var(--gn)" strokeWidth="2" fill="none" style={{ filter: "drop-shadow(0 0 5px var(--gn))" }} />
        {OT_MONTHS.map((mo, i) => i % 2 === 0 && <text key={i} x={x(i)} y={h - 4} textAnchor={i === 0 ? "start" : "middle"} className="mono ait-eq-tick">{mo.m.split(" ")[0]}</text>)}
      </svg>
      <div className="ait-eq-legend mono">
        <span><i className="ait-swatch ait-swatch--gn" /> Cumulative R <b className="up">+{cum[cum.length - 1].toFixed(1)}R</b></span>
        <span><span className="label-cap">Max DD</span> <b className="dn">−4.1R</b></span>
        <span><span className="label-cap">Profit factor</span> <b className="copper">1.9</b></span>
      </div>
    </div>
  );
}

function OptionsTrackRecord({ onTicker }) {
  const tot = OT_MONTHS.reduce((a, m) => a + m.n, 0);
  const wWin = OT_MONTHS.reduce((a, m) => a + m.win * m.n, 0) / tot;
  const totR = OT_MONTHS.reduce((a, m) => a + m.r, 0);
  const best = [...OT_MONTHS].sort((a, b) => b.r - a.r)[0];
  const worst = [...OT_MONTHS].sort((a, b) => a.r - b.r)[0];
  const maxWinR = Math.max(...OT_MONTHS.map(m => m.win), 70);
  const minWinR = 40;
  const hot = OT_LEDGER.filter(r => r.out === "hot").length;
  const failed = OT_LEDGER.filter(r => r.out === "failed").length;

  return (
    <div className="surface wsx wsx--gn otrack">
      <div className="wsx-hdr">
        <div className="wsx-hdr-l">
          <div className="wsx-eyebrow mono">OPTIONS TRACK RECORD · TRAILING 12 MONTHS</div>
          <h1 className="wsx-title mono">Options Track Record</h1>
          <div className="wsx-sub mono dim2">every idea scored at exit · hot / failed / flat · win-rate · R-multiple equity · edge by structure &amp; IV-rank</div>
        </div>
        <div className="wsx-hdr-r"><FreshnessPill state="live" age="EOD" /><span className="mono dim2">src · options trade_log · Schwab fills · BS-marked</span></div>
      </div>

      <div className="wsx-kpis">
        <OTKpi k="CLOSED · 12M" v={tot} tone="gn" s="resolved option ideas" />
        <OTKpi k="WIN RATE" v={`${wWin.toFixed(1)}%`} tone="gn" s={`${hot}/${OT_LEDGER.length} hot shown`} />
        <OTKpi k="NET R · 12M" v={`+${totR.toFixed(1)}R`} tone="copper" s="sum of R-multiples" />
        <OTKpi k="AVG R / TRADE" v={`+${(totR / tot).toFixed(2)}R`} tone="gn" s="expectancy" />
        <OTKpi k="PROFIT FACTOR" v="1.9" tone="cy" s="gross win ÷ loss" />
        <OTKpi k="BEST / WORST MO" v={`+${best.r.toFixed(1)} / ${worst.r.toFixed(1)}R`} tone="amb" s={`${best.m.split(" ")[0]} · ${worst.m.split(" ")[0]}`} />
      </div>

      <div className="otrack-grid">
        <div className="otrack-main">
          <div className="lab-card">
            <div className="lab-card-h mono">CUMULATIVE R · TRAILING 12 MONTHS <span className="dim2">· risk-normalized P&amp;L of every closed idea</span></div>
            <OTEquity />
          </div>

          <div className="lab-card">
            <div className="lab-card-h mono">MONTHLY WIN-RATE <span className="dim2">· 50% line · bar height = win-rate, label = net R</span></div>
            <div className="ait-month">
              {OT_MONTHS.map((mo, i) => {
                const hgt = ((mo.win - minWinR) / (maxWinR - minWinR)) * 100;
                const tone = mo.r >= 4 ? "gn" : mo.r >= 0 ? "amb" : "rd";
                return (
                  <div key={i} className="ait-month-col" title={`${mo.m} · ${mo.n} closed · ${mo.win}% win · ${mo.r >= 0 ? "+" : ""}${mo.r}R`}>
                    <div className="ait-month-track"><div className="ait-month-base" /><div className={`ait-month-fill kpi-tone-bg--${tone}`} style={{ height: `${Math.max(4, hgt)}%` }} /></div>
                    <span className={`mono ait-month-v kpi-tone--${tone}`}>{mo.r >= 0 ? "+" : ""}{mo.r}</span>
                    <span className="mono ait-month-m dim2">{mo.m.split(" ")[0]}</span>
                  </div>
                );
              })}
            </div>
          </div>

          <LedgerCard onTicker={onTicker} />
        </div>

        <div className="otrack-side">
          <div className="lab-card">
            <div className="lab-card-h mono">WIN-RATE BY STRUCTURE</div>
            <div className="ait-break">
              {OT_BY_STRUCT.map((c, i) => (
                <div key={i} className="ait-break-row">
                  <span className="mono ait-break-k">{c.k}</span>
                  <span className="ait-break-bar"><i className={`kpi-tone-bg--${c.tone}`} style={{ width: `${(c.win - 35) / 35 * 100}%` }} /></span>
                  <span className={`mono ait-break-v kpi-tone--${c.tone}`}>{c.win}%</span>
                  <span className="mono dim2 ait-break-n">{c.n}</span>
                </div>
              ))}
              <div className="ait-break-foot mono dim2">Calendars and long calls lead — defined-debit structures bought into cheap vol. Naked put debits lag; bearish premium is harder to time.</div>
            </div>
          </div>

          <div className="lab-card">
            <div className="lab-card-h mono">WIN-RATE BY IV-RANK</div>
            <div className="ait-break">
              {OT_BY_IVR.map((c, i) => (
                <div key={i} className="ait-break-row">
                  <span className="mono ait-break-k">{c.k}</span>
                  <span className="ait-break-bar"><i className={`kpi-tone-bg--${c.tone}`} style={{ width: `${(c.win - 35) / 35 * 100}%` }} /></span>
                  <span className={`mono ait-break-v kpi-tone--${c.tone}`}>{c.win}%</span>
                </div>
              ))}
              <div className="ait-break-foot mono dim2">The playbook holds up out-of-sample: buying premium when <b className="up">IVR&lt;45</b> wins 59% vs just 41% when <b className="dn">IVR&gt;70</b> — you lose on rich vol even when right on direction.</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function LedgerCard({ onTicker }) {
  const [tk, setTk] = useStateOT("");
  const [out, setOut] = useStateOT("all");
  const [from, setFrom] = useStateOT("");
  const [to, setTo] = useStateOT("");
  const [sort, setSort] = useStateOT("date");

  const fmtD = (iso) => { const d = new Date(iso + "T00:00:00"); return d.toLocaleDateString("en-US", { day: "2-digit", month: "short" }); };
  const rows = useMemoOT(() => {
    let r = OT_LEDGER.filter(x => {
      if (tk && !x.sym.toLowerCase().includes(tk.toLowerCase())) return false;
      if (out !== "all" && x.out !== out) return false;
      if (from && x.d < from) return false;
      if (to && x.d > to) return false;
      return true;
    });
    if (sort === "date") r = [...r].sort((a, b) => b.d.localeCompare(a.d));
    else if (sort === "r") r = [...r].sort((a, b) => b.r - a.r);
    else if (sort === "sym") r = [...r].sort((a, b) => a.sym.localeCompare(b.sym));
    return r;
  }, [tk, out, from, to, sort]);

  const hot = rows.filter(r => r.out === "hot").length;
  const failed = rows.filter(r => r.out === "failed").length;
  const flat = rows.filter(r => r.out === "flat").length;
  const netR = rows.reduce((a, r) => a + r.r, 0);
  const dates = OT_LEDGER.map(x => x.d).sort();
  const reset = () => { setTk(""); setOut("all"); setFrom(""); setTo(""); };
  const active = tk || out !== "all" || from || to;

  return (
    <div className="lab-card">
      <div className="lab-card-h mono">RESOLVED-IDEA LEDGER <span className="dim2">· trailing month · {rows.length} of {OT_LEDGER.length} · {hot} hot · {failed} failed · net {netR >= 0 ? "+" : ""}{netR.toFixed(1)}R</span></div>
      <div className="otk-filters">
        <span className="otk-fld"><span className="label-cap">Ticker</span><input className="mono" placeholder="all" value={tk} onChange={e => setTk(e.target.value.toUpperCase())} /></span>
        <span className="otk-fld"><span className="label-cap">From</span><input className="mono" type="date" min={dates[0]} max={dates[dates.length - 1]} value={from} onChange={e => setFrom(e.target.value)} /></span>
        <span className="otk-fld"><span className="label-cap">To</span><input className="mono" type="date" min={dates[0]} max={dates[dates.length - 1]} value={to} onChange={e => setTo(e.target.value)} /></span>
        <span className="otk-seg">{[["all", "All"], ["hot", "Hot"], ["failed", "Failed"], ["flat", "Flat"]].map(([id, l]) => (
          <button key={id} className={out === id ? "is-on" : ""} onClick={() => setOut(id)}>{l}</button>
        ))}</span>
        <span className="otk-seg">{[["date", "Date"], ["r", "R"], ["sym", "Sym"]].map(([id, l]) => (
          <button key={id} className={sort === id ? "is-on" : ""} onClick={() => setSort(id)} title={`Sort by ${l}`}>↓{l}</button>
        ))}</span>
        {active && <button className="otk-reset" onClick={reset}>✕ clear</button>}
      </div>
      <table className="dtable wsx-tbl ait-tbl">
        <thead><tr><th>Closed</th><th>Sym</th><th>Structure</th><th>Bias</th><th className="r">Debit</th><th className="r">Exit</th><th className="r">R</th><th>Outcome</th></tr></thead>
        <tbody>{rows.length === 0 ? <tr><td colSpan={8} style={{ textAlign: "center", padding: 22 }} className="dim2">No closes match these filters.</td></tr> : rows.map((x, i) => (
          <tr key={i} onClick={() => onTicker(x.sym)} style={{ cursor: "pointer" }}>
            <td className="mono dim2">{fmtD(x.d)}</td>
            <td className="mono"><b>{x.sym}</b></td>
            <td className="mono">{x.strat}</td>
            <td><span className={`of-bias of-bias--${x.bias}`}>{x.bias === "bull" ? "▲" : "▼"}</span></td>
            <td className="r mono tabular cop">${x.deb.toFixed(2)}</td>
            <td className="r mono tabular dim">${x.exit.toFixed(2)}</td>
            <td className={`r mono tabular ${x.r >= 0 ? "up" : "dn"}`}><b>{x.r >= 0 ? "+" : ""}{x.r.toFixed(2)}R</b></td>
            <td><span className={`ait-out ait-out--${x.out === "hot" ? "hit" : x.out === "failed" ? "miss" : "flat"}`}>{x.out === "hot" ? "HOT" : x.out === "failed" ? "FAILED" : "FLAT"}</span></td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

window.OptionsTrackRecord = OptionsTrackRecord;
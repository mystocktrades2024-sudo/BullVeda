// surface-ipo.jsx — Upcoming IPOs calendar. Lists pending/priced offerings with
// expected date, price range, deal size, underwriters, and a status pill.
// Mock data (replace with a real IPO-calendar feed). Exposes window.SurfaceIPO.

const { useState: useIPO, useMemo: useIPOm } = React;

const IPO_ROWS = [
  { sym: "RBRK", name: "Riverbrook Robotics", sector: "Industrials", exch: "NASDAQ", date: "2026-06-04", lo: 27, hi: 30, shares: 18.5, lead: "Goldman Sachs · Morgan Stanley", status: "priced", priced: 29, note: "Warehouse automation; 41% rev growth" },
  { sym: "NMBL", name: "Nimbus Cloud", sector: "Technology", exch: "NYSE", date: "2026-06-05", lo: 18, hi: 21, shares: 32.0, lead: "J.P. Morgan · BofA", status: "upcoming", note: "Infra SaaS; net retention 128%" },
  { sym: "HELX", name: "Helix Therapeutics", sector: "Healthcare", exch: "NASDAQ", date: "2026-06-06", lo: 15, hi: 17, shares: 9.4, lead: "Jefferies · Cowen", status: "upcoming", note: "Phase-3 oncology readout Q3" },
  { sym: "VOLT", name: "Voltaic Energy", sector: "Energy", exch: "NYSE", date: "2026-06-09", lo: 22, hi: 26, shares: 24.0, lead: "Citigroup · Barclays", status: "upcoming", note: "Grid-scale storage; backlog $1.4B" },
  { sym: "FRSH", name: "Freshline Foods", sector: "Consumer", exch: "NASDAQ", date: "2026-06-11", lo: 16, hi: 18, shares: 12.2, lead: "Morgan Stanley", status: "filing", note: "DTC grocery; first profitable qtr" },
  { sym: "QNTA", name: "Quanta Compute", sector: "Technology", exch: "NASDAQ", date: "2026-06-12", lo: 33, hi: 38, shares: 27.5, lead: "Goldman Sachs · Evercore", status: "upcoming", note: "AI inference silicon" },
  { sym: "ATLS", name: "Atlas Logistics", sector: "Industrials", exch: "NYSE", date: "2026-06-16", lo: 19, hi: 22, shares: 15.8, lead: "Wells Fargo · RBC", status: "filing", note: "Last-mile freight network" },
  { sym: "MRNE", name: "Marine Biosciences", sector: "Healthcare", exch: "NASDAQ", date: "2026-06-18", lo: 12, hi: 14, shares: 7.0, lead: "Piper Sandler", status: "filing", note: "Marine-derived therapeutics" },
  { sym: "PYLN", name: "Paylon", sector: "Financials", exch: "NYSE", date: "2026-06-23", lo: 24, hi: 28, shares: 21.0, lead: "J.P. Morgan · Citigroup", status: "upcoming", note: "Embedded payments; take-rate 1.9%" },
  { sym: "SOLR", name: "Solaria Materials", sector: "Materials", exch: "NASDAQ", date: "2026-06-25", lo: 20, hi: 23, shares: 14.5, lead: "BofA · Mizuho", status: "filing", note: "Perovskite cell maker" },
  { sym: "VRDA", name: "Verda Bio", sector: "Healthcare", exch: "NASDAQ", date: "2026-07-01", lo: 17, hi: 19, shares: 10.1, lead: "Cowen · Leerink", status: "rumored", note: "Confidential S-1 reported" },
  { sym: "DGTL", name: "Digitalis Media", sector: "Communications", exch: "NYSE", date: "2026-07-08", lo: 21, hi: 24, shares: 19.3, lead: "Morgan Stanley · UBS", status: "rumored", note: "Streaming adtech; targeting Q3" },
];

const IPO_STATUS = { priced: { l: "Priced", tone: "gn" }, upcoming: { l: "Upcoming", tone: "cy" }, filing: { l: "Filed (S-1)", tone: "amb" }, rumored: { l: "Rumored", tone: "ink" } };

function ipoMid(r) { return (r.lo + r.hi) / 2; }
function ipoDeal(r) { return ipoMid(r) * r.shares; } // $M
function ipoDateStr(d) { return new Date(d + "T00:00:00").toLocaleDateString("en-US", { weekday: "short", day: "2-digit", month: "short" }); }
function ipoDaysOut(d) { return Math.round((new Date(d + "T00:00:00").getTime() - Date.now()) / 86400000); }

function SurfaceIPO({ onTicker }) {
  const [win, setWin] = useIPO("all");        // week | month | all
  const [sec, setSec] = useIPO("all");        // sector filter
  const [stat, setStat] = useIPO("all");      // status filter

  const sectors = useIPOm(() => ["all", ...Array.from(new Set(IPO_ROWS.map(r => r.sector)))], []);
  const rows = useIPOm(() => {
    return IPO_ROWS
      .filter(r => {
        const d = ipoDaysOut(r.date);
        if (win === "week" && (d < 0 || d > 7)) return false;
        if (win === "month" && (d < 0 || d > 31)) return false;
        if (sec !== "all" && r.sector !== sec) return false;
        if (stat !== "all" && r.status !== stat) return false;
        return true;
      })
      .sort((a, b) => a.date.localeCompare(b.date));
  }, [win, sec, stat]);

  const totalDeal = rows.reduce((s, r) => s + ipoDeal(r), 0);
  const thisWeek = IPO_ROWS.filter(r => { const d = ipoDaysOut(r.date); return d >= 0 && d <= 7; }).length;
  const priced = IPO_ROWS.filter(r => r.status === "priced").length;

  return (
    <div className="surface wsx wsx--copper ipo">
      <div className="wsx-hdr">
        <div className="wsx-hdr-l">
          <div className="wsx-eyebrow mono">PRIMARY MARKET · NEW LISTINGS</div>
          <div className="mpf-titlerow"><h2 className="ipo-title">Upcoming IPOs</h2></div>
          <div className="wsx-sub mono dim2">expected date · price range · deal size · underwriters · demo calendar, replace with a live IPO feed</div>
        </div>
        <div className="wsx-hdr-r">
          <FreshnessPill state="live" age="sim" />
        </div>
      </div>

      <div className="ipo-kpis">
        <PfTile l="On the calendar" v={IPO_ROWS.length} s="next ~5 weeks" tone="ink" />
        <PfTile l="Pricing this week" v={thisWeek} s="≤ 7 days out" tone="cy" />
        <PfTile l="Already priced" v={priced} s="live to trade" tone="gn" />
        <PfTile l="Filtered deal size" v={`$${totalDeal.toFixed(0)}M`} s={`${rows.length} offerings`} tone="copper" />
      </div>

      <div className="ipo-bar">
        <div className="trk-toggle trk-toggle--sm">
          {[["week", "This week"], ["month", "This month"], ["all", "All"]].map(([id, l]) => (
            <button key={id} className={win === id ? "is-on" : ""} onClick={() => setWin(id)}>{l}</button>
          ))}
        </div>
        <div className="ipo-chips">
          {sectors.map(sc => <button key={sc} className={`trk-chip ${sec === sc ? "is-on" : ""}`} onClick={() => setSec(sc)}>{sc === "all" ? "All sectors" : sc}</button>)}
        </div>
        <div className="trk-toggle trk-toggle--sm ipo-bar-r">
          {[["all", "Any"], ["priced", "Priced"], ["upcoming", "Upcoming"], ["filing", "Filed"], ["rumored", "Rumored"]].map(([id, l]) => (
            <button key={id} className={stat === id ? "is-on" : ""} onClick={() => setStat(id)}>{l}</button>
          ))}
        </div>
      </div>

      <div className="wsx-body">
        <table className="dtable wsx-tbl pf-tbl ipo-tbl">
          <thead><tr>
            <th>Expected</th><th className="r">Days</th><th>Symbol</th><th>Company</th><th>Sector</th><th>Exch</th>
            <th className="r">Price range</th><th className="r">Shares</th><th className="r">Deal size</th><th>Lead underwriters</th><th>Status</th>
          </tr></thead>
          <tbody>{rows.length === 0 ? (
            <tr><td colSpan={11} className="dim2" style={{ textAlign: "center", padding: 26 }}>No offerings match these filters.</td></tr>
          ) : rows.map(r => {
            const st = IPO_STATUS[r.status]; const d = ipoDaysOut(r.date);
            return (
              <tr key={r.sym} onClick={() => onTicker && onTicker(r.sym)} title={r.note}>
                <td className="mono dim2">{ipoDateStr(r.date)}</td>
                <td className={`r tabular mono ${d <= 7 ? "up" : "dim2"}`}>{d < 0 ? "—" : d + "d"}</td>
                <td><b className="ipo-sym">{r.sym}</b></td>
                <td>{r.name}<div className="ipo-note dim2">{r.note}</div></td>
                <td className="dim2">{r.sector}</td>
                <td className="dim2 mono">{r.exch}</td>
                <td className="r tabular">${r.lo}–{r.hi}{r.status === "priced" && <span className="ipo-priced mono"> @ ${r.priced}</span>}</td>
                <td className="r tabular dim2">{r.shares.toFixed(1)}M</td>
                <td className="r tabular"><b>${ipoDeal(r).toFixed(0)}M</b></td>
                <td className="dim2 ipo-lead">{r.lead}</td>
                <td><span className={`ipo-status ipo-status--${st.tone}`}>{st.l}</span></td>
              </tr>
            );
          })}</tbody>
        </table>
        <div className="lab-verdict mono dim2">Click a row to open the ticker's detail. Price range × shares = indicative deal size; "priced" rows show the final offer price. Replace <b>IPO_ROWS</b> with a live primary-market calendar feed.</div>
      </div>
    </div>
  );
}

window.SurfaceIPO = SurfaceIPO;

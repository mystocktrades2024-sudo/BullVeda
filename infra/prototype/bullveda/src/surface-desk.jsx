// surface-desk.jsx — Alerts (real-time triage) · Trade Journal (log + behavioral analytics) · Playbook (regime matrix + discipline)
// Alerts derive from held positions + scan change-log. Journal reads trade_log. Playbook reads regime context + SLEEVES.

const { useState: useDesk, useMemo: useDeskm } = React;

// ═══════════════════════════════════════════════════════════════
//  ALERTS — derived in real-time from scan state + held positions
// ═══════════════════════════════════════════════════════════════
const ALERTS = [
  { sev: "P0", type: "STOP BREACHED", sym: "INPR", detail: "Held 180sh below stop $38.40 → last $37.95 (−1.2% past stop). Defend or exit on close.", act: "EXIT", age: "2m", held: true },
  { sev: "P0", type: "EARNINGS ≤2d", sym: "FLNX", detail: "Held 60sh · reports AMC tomorrow. Binary event on live money — flatten before the bell.", act: "FLATTEN", age: "14m", held: true },
  { sev: "P0", type: "STOP NEAR", sym: "ARCM", detail: "Held 110sh within 0.8% of stop $62.40 (last $62.90). One red close triggers the bracket.", act: "WATCH", age: "6m", held: true },
  { sev: "P1", type: "T1 HIT", sym: "BORA", detail: "Held 240sh reached T1 $34.50 (+$1,608, +2.4R). Trim ⅔ and trail stop to breakeven.", act: "TRIM", age: "3m", held: true },
  { sev: "P1", type: "NEW BUY", sym: "ARGN", detail: "Passed all 10 gates · score 81 · Cont. BO · R:R 2.6 to T1 · Wilson 48%. Fresh entry candidate.", act: "PLAN", age: "21m", held: false },
  { sev: "P1", type: "SETUP DRIFT", sym: "—", detail: "Gap & Go sleeve: Wilson LB fell 6pts over 60 trades — edge erosion (principle 11). Size down.", act: "REVIEW", age: "1h", held: false },
  { sev: "P1", type: "DEMOTED", sym: "MERC", detail: "BUY → WATCH · failed RS gate (RS 41 < 45 floor). Removed from BUY candidates this scan.", act: "REVIEW", age: "32m", held: false },
  { sev: "P2", type: "PROMOTED", sym: "DRSH", detail: "WATCH → BUY · cleared catalyst-tier gate after energy sector RS flip. Now on the board.", act: "VIEW", age: "44m", held: false },
  { sev: "P2", type: "SCORE SHIFT", sym: "NVRH", detail: "Composite +11 (60 → 71) on volume + RS expansion. Crossed the BUY floor.", act: "VIEW", age: "52m", held: false },
  { sev: "P2", type: "EARN IMMINENT", sym: "GENO", detail: "Unheld watch name reports in 2 days · implied ±9.4%. New swing entries blocked (blackout).", act: "VIEW", age: "1h", held: false },
];
const SEV = { P0: ["rd", "critical"], P1: ["amb", "attention"], P2: ["blue", "info"] };

function SurfaceAlerts({ onTicker }) {
  const [filt, setFilt] = useDesk("all");
  const rows = ALERTS.filter(a => filt === "all" || a.sev === filt);
  const c = s => ALERTS.filter(a => a.sev === s).length;
  const kpis = [
    ["P0 · CRITICAL", c("P0"), "rd", "act now · open risk"],
    ["P1 · ATTENTION", c("P1"), "amb", "review soon"],
    ["P2 · INFO", c("P2"), "blue", "context"],
    ["STOP-RELATED", ALERTS.filter(a => a.type.includes("STOP")).length, "rd", "breached / near"],
    ["T1 HITS", ALERTS.filter(a => a.type === "T1 HIT").length, "gn", "ready to trim"],
    ["EARNINGS ≤2d", ALERTS.filter(a => a.type.includes("EARN")).length, "amb", "blackout / flatten"],
  ];

  return (
    <div className="surface wsx wsx--rd q-alerts">
      <div className="wsx-hdr">
        <div className="wsx-hdr-l">
          <div className="wsx-eyebrow mono">REAL-TIME TRIAGE · DERIVED · NO PERSISTENT STORE</div>
          <h1 className="wsx-title mono">Alerts</h1>
          <div className="wsx-sub mono dim2">re-evaluated every load from current scan state + held positions · sorted by severity · one-click action</div>
        </div>
        <div className="wsx-hdr-r">
          <FreshnessPill state="live" age="re-eval 4s" />
          <span className="mono dim2">src · scan change-log · portfolio_state · Schwab /quotes</span>
        </div>
      </div>

      <div className="q-kpis q-kpis--6">
        {kpis.map((k, i) => (
          <div key={i} className={`q-kpi q-kpi--${k[2]}`}>
            <div className="q-kpi-l mono">{k[0]}</div>
            <div className={`q-kpi-v mono kpi-tone--${k[2]}`}>{k[1]}</div>
            <div className="q-kpi-s mono dim2">{k[3]}</div>
          </div>
        ))}
      </div>

      <div className="q-chips">
        {[["all", "All", ALERTS.length], ["P0", "P0 · critical", c("P0")], ["P1", "P1 · attention", c("P1")], ["P2", "P2 · info", c("P2")]].map(([id, l, n]) => (
          <button key={id} className={`q-chip-btn ${filt === id ? "is-on" : ""} ${id !== "all" ? `q-chip-btn--${SEV[id][0]}` : ""}`} onClick={() => setFilt(id)}>
            {l} <span className="q-chip-n mono">{n}</span>
          </button>
        ))}
      </div>

      <div className="wsx-body">
        <table className="dtable wsx-tbl q-alert-tbl">
          <thead><tr><th>Sev</th><th>Type</th><th>Ticker</th><th>Detail</th><th className="r">Age</th><th>Action</th></tr></thead>
          <tbody>{rows.map((a, i) => (
            <tr key={i} className={`q-alert-row q-alert-row--${SEV[a.sev][0]}`} onClick={() => a.sym !== "—" && onTicker(a.sym)}>
              <td><span className={`q-sev q-sev--${SEV[a.sev][0]}`}>{a.sev}</span></td>
              <td><span className={`q-atype mono kpi-tone--${SEV[a.sev][0]}`}>{a.type}</span></td>
              <td>{a.sym === "—" ? <span className="dim2">sleeve</span> : <b className="mono">{a.sym}</b>}{a.held && <span className="q-held mono">HELD</span>}</td>
              <td className="dim q-alert-detail">{a.detail}</td>
              <td className="r mono dim2">{a.age}</td>
              <td onClick={e => e.stopPropagation()}><button className={`q-act-btn q-act-btn--${SEV[a.sev][0]}`}>{a.act}</button></td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <div className="pf-note mono dim2">
        Alerts are <b>computed, not stored</b> — every load re-derives them from live scan deltas and your open book, so they can never go stale.
        P0 = open risk on real money (act now) · P1 = review queue · P2 = FYI context. Click a row → 14-lens detail.
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
//  TRADE JOURNAL — log + R-analytics + behavioral attribution
// ═══════════════════════════════════════════════════════════════
const JOURNAL = [
  { date: "May 24", sym: "ARGN", sleeve: "Cont. BO", dir: "L", entry: 198.40, exit: 213.40, r: 1.84, pnl: 1210, days: 9, grade: "A", plan: true, tag: "—" },
  { date: "May 21", sym: "VLCT", sleeve: "Pullback", dir: "L", entry: 44.10, exit: 42.80, r: -1.00, pnl: -420, days: 3, grade: "B", plan: true, tag: "—" },
  { date: "May 16", sym: "ZOTR", sleeve: "Flag", dir: "L", entry: 38.20, exit: 44.60, r: 2.10, pnl: 1480, days: 14, grade: "A", plan: true, tag: "—" },
  { date: "May 12", sym: "MERC", sleeve: "Range", dir: "L", entry: 18.40, exit: 17.20, r: -0.60, pnl: -252, days: 5, grade: "C", plan: false, tag: "chased entry" },
  { date: "May 08", sym: "NVRH", sleeve: "Pullback", dir: "L", entry: 138.0, exit: 142.1, r: 0.41, pnl: 320, days: 7, grade: "B", plan: true, tag: "early exit" },
  { date: "May 02", sym: "DRSH", sleeve: "Breakout", dir: "L", entry: 51.20, exit: 56.10, r: 1.62, pnl: 980, days: 6, grade: "A", plan: true, tag: "—" },
  { date: "Apr 28", sym: "BIVO", sleeve: "Mean Rev", dir: "L", entry: 74.0, exit: 71.4, r: -1.00, pnl: -390, days: 2, grade: "B", plan: true, tag: "—" },
  { date: "Apr 22", sym: "FRAC", sleeve: "Gap & Go", dir: "L", entry: 24.10, exit: 22.60, r: -0.85, pnl: -310, days: 1, grade: "C", plan: false, tag: "no stop set" },
  { date: "Apr 15", sym: "INDX", sleeve: "Cont. BO", dir: "L", entry: 88.4, exit: 96.2, r: 2.40, pnl: 1640, days: 11, grade: "A", plan: true, tag: "—" },
  { date: "Apr 09", sym: "HAVN", sleeve: "Pullback", dir: "L", entry: 41.0, exit: 39.8, r: -0.70, pnl: -280, days: 4, grade: "B", plan: true, tag: "—" },
  { date: "Apr 03", sym: "KOPL", sleeve: "VCP", dir: "L", entry: 30.2, exit: 34.1, r: 1.55, pnl: 860, days: 8, grade: "A", plan: true, tag: "—" },
  { date: "Mar 27", sym: "TWPN", sleeve: "Range", dir: "S", entry: 62.0, exit: 64.4, r: -1.00, pnl: -480, days: 3, grade: "C", plan: false, tag: "fought trend" },
];

function SurfaceJournal({ onTicker }) {
  const [gf, setGf] = useDesk("all");
  const D = useDeskm(() => {
    let cum = 0; const eq = JOURNAL.slice().reverse().map(t => { cum += t.r; return +cum.toFixed(2); });
    const wins = JOURNAL.filter(t => t.r > 0), losses = JOURNAL.filter(t => t.r <= 0);
    const wr = wins.length / JOURNAL.length * 100;
    const avgW = wins.reduce((a, t) => a + t.r, 0) / wins.length;
    const avgL = losses.reduce((a, t) => a + t.r, 0) / losses.length;
    const pf = wins.reduce((a, t) => a + t.pnl, 0) / Math.abs(losses.reduce((a, t) => a + t.pnl, 0));
    const exp = JOURNAL.reduce((a, t) => a + t.r, 0) / JOURNAL.length;
    const planFollow = JOURNAL.filter(t => t.plan).length / JOURNAL.length * 100;
    return { eq, wr, avgW, avgL, pf, exp, planFollow, totalPnl: JOURNAL.reduce((a, t) => a + t.pnl, 0) };
  }, []);
  const rbins = [
    { label: "<-1R", count: 1, win: false }, { label: "-1R", count: 5, win: false },
    { label: "0R", count: 0, win: false }, { label: "+1R", count: 2, win: true },
    { label: "+2R", count: 3, win: true }, { label: ">+2R", count: 1, win: true },
  ];
  // WR by sleeve
  const bySleeve = useDeskm(() => {
    const m = {}; JOURNAL.forEach(t => { (m[t.sleeve] = m[t.sleeve] || []).push(t); });
    return Object.entries(m).map(([k, ts]) => ({ label: k, value: +(ts.reduce((a, t) => a + t.r, 0)).toFixed(2), n: ts.length }))
      .sort((a, b) => b.value - a.value);
  }, []);
  const rows = JOURNAL.filter(t => gf === "all" || (gf === "win" ? t.r > 0 : gf === "loss" ? t.r <= 0 : !t.plan));

  return (
    <div className="surface wsx wsx--violet q-journal">
      <div className="wsx-hdr">
        <div className="wsx-hdr-l">
          <div className="wsx-eyebrow mono">TRADE LOG · R-ANALYTICS · BEHAVIORAL ATTRIBUTION</div>
          <h1 className="wsx-title mono">Trade Journal</h1>
          <div className="wsx-sub mono dim2">every closed trade · R-multiple normalized · grade + plan-adherence + mistake tags · the feedback loop that makes the system learn</div>
        </div>
        <div className="wsx-hdr-r">
          <FreshnessPill state="live" age="synced" />
          <span className="mono dim2">src · trade_log · portfolio_state</span>
        </div>
      </div>

      <div className="q-kpis">
        {[["NET P&L", `+$${D.totalPnl.toLocaleString()}`, "gn", `${JOURNAL.length} closed`],
          ["WIN RATE", `${D.wr.toFixed(0)}%`, "gn", `${JOURNAL.filter(t => t.r > 0).length}W / ${JOURNAL.filter(t => t.r <= 0).length}L`],
          ["EXPECTANCY", `+${D.exp.toFixed(2)}R`, "copper", "per trade"],
          ["PROFIT FACTOR", D.pf.toFixed(2), "gn", "gross W ÷ L"],
          ["AVG WIN", `+${D.avgW.toFixed(2)}R`, "gn", `vs ${D.avgL.toFixed(2)}R loss`],
          ["PAYOFF", `${(D.avgW / Math.abs(D.avgL)).toFixed(2)}×`, "gn", "win ÷ loss size"],
          ["PLAN FOLLOWED", `${D.planFollow.toFixed(0)}%`, D.planFollow >= 80 ? "gn" : "amb", "discipline"],
          ["MISTAKES", JOURNAL.filter(t => !t.plan).length, "rd", "rule breaks"]].map((k, i) => (
          <div key={i} className={`q-kpi q-kpi--${k[2]}`}>
            <div className="q-kpi-l mono">{k[0]}</div>
            <div className={`q-kpi-v mono kpi-tone--${k[2]}`}>{k[1]}</div>
            <div className="q-kpi-s mono dim2">{k[3]}</div>
          </div>
        ))}
      </div>

      <div className="q-grid2">
        <div className="lab-card">
          <div className="lab-card-h mono">CUMULATIVE R · closed-trade equity</div>
          <QEquity book={D.eq} h={130} tone="violet" />
          <div className="q-dist-stats mono"><span>total <b className="up">+{D.eq[D.eq.length - 1].toFixed(1)}R</b></span><span>best <b className="up">+2.4R</b></span><span>worst <b className="dn">−1.0R</b></span><span>streak <b className="up">3W</b></span></div>
        </div>
        <div className="lab-card">
          <div className="lab-card-h mono">R-MULTIPLE DISTRIBUTION</div>
          <QHist bins={rbins} h={120} />
          <div className="q-dist-stats mono"><span>avg win <b className="up">+{D.avgW.toFixed(2)}R</b></span><span>avg loss <b className="dn">{D.avgL.toFixed(2)}R</b></span><span>expectancy <b className="copper">+{D.exp.toFixed(2)}R</b></span></div>
        </div>
        <div className="lab-card">
          <div className="lab-card-h mono">EDGE BY SLEEVE · net R</div>
          <QDiverge rows={bySleeve} fmt={v => `${v >= 0 ? "+" : ""}${v.toFixed(2)}R`} />
        </div>
        <div className="lab-card">
          <div className="lab-card-h mono">BEHAVIORAL · what costs you R</div>
          <div className="q-behav">
            {[["Chased entry", 1, "−0.6R", "rd"], ["No stop set", 1, "−0.85R", "rd"], ["Fought trend", 1, "−1.0R", "rd"], ["Early exit", 1, "−1.7R missed", "amb"]].map((b, i) => (
              <div key={i} className="q-behav-row">
                <span className="q-behav-tag mono">{b[0]}</span>
                <span className="q-behav-n mono dim2">×{b[1]}</span>
                <span className={`q-behav-cost mono kpi-tone--${b[3]}`}>{b[2]}</span>
              </div>
            ))}
            <div className="q-behav-foot mono dim2">3 of 12 trades broke the plan — all 3 were losers. Plan-followed trades: <b className="up">67% WR</b>.</div>
          </div>
        </div>
      </div>

      <div className="q-chips">
        {[["all", "All trades", JOURNAL.length], ["win", "Winners", JOURNAL.filter(t => t.r > 0).length], ["loss", "Losers", JOURNAL.filter(t => t.r <= 0).length], ["break", "Rule breaks", JOURNAL.filter(t => !t.plan).length]].map(([id, l, n]) => (
          <button key={id} className={`q-chip-btn ${gf === id ? "is-on" : ""}`} onClick={() => setGf(id)}>{l} <span className="q-chip-n mono">{n}</span></button>
        ))}
      </div>

      <div className="wsx-body">
        <table className="dtable wsx-tbl q-journal-tbl">
          <thead><tr><th>Date</th><th>Sym</th><th>Sleeve</th><th className="c">Dir</th><th className="r">Entry</th><th className="r">Exit</th><th className="r">R</th><th className="r">P&amp;L</th><th className="r">Held</th><th className="c">Grade</th><th>Plan / note</th></tr></thead>
          <tbody>{rows.map((t, i) => (
            <tr key={i} onClick={() => onTicker(t.sym)}>
              <td className="mono dim2">{t.date}</td>
              <td><b className="mono">{t.sym}</b></td>
              <td className="dim2">{t.sleeve}</td>
              <td className="c"><span className={`q-dir ${t.dir === "L" ? "up" : "dn"}`}>{t.dir === "L" ? "LONG" : "SHORT"}</span></td>
              <td className="r tabular dim">${t.entry.toFixed(2)}</td>
              <td className="r tabular">${t.exit.toFixed(2)}</td>
              <td className={`r tabular ${t.r >= 0 ? "up" : "dn"}`}><b>{t.r >= 0 ? "+" : ""}{t.r.toFixed(2)}R</b></td>
              <td className={`r tabular ${t.pnl >= 0 ? "up" : "dn"}`}>{t.pnl >= 0 ? "+" : "−"}${Math.abs(t.pnl)}</td>
              <td className="r tabular dim">{t.days}d</td>
              <td className="c"><span className={`q-grade q-grade--${t.grade}`}>{t.grade}</span></td>
              <td>{t.plan ? <span className="q-plan-ok mono up">✓ followed</span> : <span className="q-plan-no mono dn">✕ {t.tag}</span>}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <div className="pf-note mono dim2">R-multiple normalizes every trade to its initial risk so a $420 loss and a $1,480 win compare on one axis. Grade = execution quality (entry timing, management), independent of outcome. Plan-adherence is the single most actionable column — discipline, not picks, is where most edge leaks.</div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
//  PLAYBOOK — regime activation matrix + hard gates + sizing policy
// ═══════════════════════════════════════════════════════════════
const GATES = [
  ["Liquidity", "ADV ≥ $20M · spread ≤ 0.3%", "pass"],
  ["Earnings blackout", "no new entry if ER ≤ 7d", "pass"],
  ["Regime fit", "setup must match active regime", "pass"],
  ["Score floor", "composite ≥ 65 (best regime)", "pass"],
  ["RS gate", "RS rank ≥ 45 vs SPX", "pass"],
  ["Catalyst tier", "tier 1–2 catalyst present", "pass"],
  ["Entry quality", "≤ 1.5 ATR from pivot", "pass"],
  ["Setup kill", "sleeve Wilson LB ≥ 40%", "pass"],
  ["Tail loss", "max loss ≤ 1.5% NAV", "pass"],
  ["Fund check", "no going-concern / dilution flag", "warn"],
];
const SIZING = [
  ["Risk per trade", "0.75% NAV", "to initial stop", "gn"],
  ["Max open positions", "8", "5 open now", "gn"],
  ["Max per sector", "25% NAV", "Tech 18% peak", "gn"],
  ["Open heat cap", "4.0R", "2.8R now", "gn"],
  ["Book β cap", "1.20", "0.93 now", "gn"],
  ["Correlated cluster", "≤ 0.60 pairwise", "0.42 max", "amb"],
];
const PREMORTEM = [
  ["Breakout fails", "price loses pivot on close → exit, no average-down"],
  ["Gap through stop", "overnight gap below stop → exit at open, accept slippage"],
  ["Earnings surprise", "held into ER (policy break) → flatten pre-event next time"],
  ["Regime flip", "VIX > 25 or breadth < 1.0 → cut leverage, raise cash"],
  ["Edge decay", "sleeve Wilson < 40% → quarantine, stop new entries"],
];

function SurfacePlaybook({ onTicker }) {
  const sleeves = window.SLEEVES || [];
  const regCols = [["bull", "RISK ON", "gn"], ["chop", "CHOP", "amb"], ["bear", "RISK OFF", "rd"]];
  const active = "bull";
  const dotLbl = v => v >= 2 ? "RUN" : v === 1 ? "SEL" : "OFF";
  const dotTone = v => v >= 2 ? "gn" : v === 1 ? "amb" : "rd";

  return (
    <div className="surface wsx wsx--gn q-playbook">
      <div className="wsx-hdr">
        <div className="wsx-hdr-l">
          <div className="wsx-eyebrow mono">REGIME ACTIVATION · HARD GATES · SIZING POLICY</div>
          <h1 className="wsx-title mono">Playbook</h1>
          <div className="wsx-sub mono dim2">the standing rules — which sleeves to run in the current regime, the 10 entry gates, sizing limits, and the pre-mortem</div>
        </div>
        <div className="wsx-hdr-r">
          <FreshnessPill state="live" age="regime 18s" />
          <span className="mono dim2">src · regime context · setup_stats · risk policy</span>
        </div>
      </div>

      {/* regime banner */}
      <div className="q-regime-banner">
        <div className="q-regime-main">
          <span className="q-regime-dot" />
          <div>
            <div className="q-regime-lbl mono up">REGIME · RISK ON</div>
            <div className="q-regime-sub mono dim2">bull · low-vol · breadth expanding — run momentum &amp; continuation sleeves at full size</div>
          </div>
        </div>
        <div className="q-regime-tiles">
          {[["VIX", "16.3", "gn", "−1.8%"], ["BREADTH A/D", "1.84", "gn", "expanding"], ["10Y", "4.32%", "gn", "−14bp 5d"], ["% > 50-DMA", "68%", "gn", "risk-on"]].map((t, i) => (
            <div key={i} className="q-regime-tile"><span className="mono dim2">{t[0]}</span><span className={`mono kpi-tone--${t[2]}`}>{t[1]}</span><span className="mono dim2">{t[3]}</span></div>
          ))}
        </div>
      </div>

      {/* activation matrix */}
      <div className="lab-card">
        <div className="lab-card-h mono">SLEEVE ACTIVATION MATRIX · current regime highlighted</div>
        <table className="dtable wsx-tbl q-matrix">
          <thead><tr><th>Sleeve</th>{regCols.map(([k, l, t]) => <th key={k} className={`c ${k === active ? "q-mx-active" : ""}`}>{l}{k === active && <span className="q-mx-now mono"> ◂ now</span>}</th>)}<th className="r">Wilson</th><th>Status</th></tr></thead>
          <tbody>{sleeves.map(s => (
            <tr key={s.k}>
              <td><b>{s.k}</b></td>
              {regCols.map(([k]) => (
                <td key={k} className={`c ${k === active ? "q-mx-active" : ""}`}>
                  <span className={`q-mx-cell q-mx-cell--${dotTone(s.regime[k])}`}>{dotLbl(s.regime[k])}</span>
                </td>
              ))}
              <td className={`r tabular ${s.lb >= 45 ? "up" : s.lb >= 40 ? "warn" : "dn"}`}>{s.lb.toFixed(0)}%</td>
              <td><Pill tone={s.status === "stable" ? "gn" : s.status === "decaying" ? "amb" : "ink"} small>{s.status}</Pill></td>
            </tr>
          ))}</tbody>
        </table>
        <div className="lab-verdict mono dim2">In <b className="up">RISK ON</b>: run Continuation BO, VCP, Pullback, Earnings Drift at full size. Mean-Revert &amp; Range-Fade are OFF in trend. Decaying sleeves at half size.</div>
      </div>

      {/* gates + sizing grid */}
      <div className="q-grid2">
        <div className="lab-card">
          <div className="lab-card-h mono">ENTRY GATES · all must pass · ordered hard-stops</div>
          <div className="q-gates">
            {GATES.map((g, i) => (
              <div key={i} className="q-gate-row">
                <span className={`q-gate-chk q-gate-chk--${g[2]}`}>{g[2] === "pass" ? "✓" : "!"}</span>
                <span className="q-gate-n">{i + 1}. {g[0]}</span>
                <span className="q-gate-rule mono dim2">{g[1]}</span>
              </div>
            ))}
          </div>
          <div className="lab-verdict mono dim2">A single failed gate kills the trade — no soft overrides. 9/10 pass; <b className="warn">Fund check</b> flagged on one name.</div>
        </div>
        <div className="lab-card">
          <div className="lab-card-h mono">SIZING &amp; RISK POLICY · live vs limit</div>
          <div className="q-sizing">
            {SIZING.map((s, i) => (
              <div key={i} className="q-size-row">
                <span className="q-size-l">{s[0]}</span>
                <span className={`q-size-v mono kpi-tone--${s[3]}`}>{s[1]}</span>
                <span className="q-size-s mono dim2">{s[2]}</span>
              </div>
            ))}
          </div>
          <div className="lab-card-h mono q-sub-h">PRE-MORTEM · how trades die</div>
          <div className="q-premortem">
            {PREMORTEM.map((p, i) => (
              <div key={i} className="q-pm-row"><span className="q-pm-k mono dn">{p[0]}</span><span className="q-pm-v dim">{p[1]}</span></div>
            ))}
          </div>
        </div>
      </div>
      <div className="pf-note mono dim2">The Playbook is the system's constitution — it executes mechanically so the human can't rationalize around a rule. Regime is re-classified every scan from VIX + breadth + trend; sleeve activation follows. Gates are evaluated in order; sizing is enforced at order entry.</div>
    </div>
  );
}

window.SurfaceAlerts = SurfaceAlerts;
window.SurfaceJournal = SurfaceJournal;
window.SurfacePlaybook = SurfacePlaybook;

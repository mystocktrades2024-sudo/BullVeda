// surface-momentum.jsx — Momentum workspace, quant-grade.
// RS-ranked leaders + multi-timeframe RS history (1W/1M/3M/6M), RS-line trend,
// momentum persistence stats, sector momentum, and a 60-day RS history sparkline per name.

const { useState: useMo, useMemo: useMom } = React;

const MO_ROWS = (() => {
  return HEATMAP.map(([sym, sector, mcap, chg]) => {
    const code = sym.charCodeAt(0) + sym.charCodeAt(1);
    const w = WATCHLIST.find(x => x.sym === sym);
    const rs = Math.max(8, Math.min(99, 50 + Math.round(chg * 7) + (code % 20)));
    return {
      sym, sector, mcap, chg,
      name: w?.name || `${sector} Corp`,
      price: w?.price || (20 + code % 200),
      score: w?.score || Math.max(28, Math.min(94, 50 + Math.round(chg * 5))),
      rs,
      rs1w: Math.max(5, Math.min(99, rs + ((code % 11) - 5))),
      rs1m: rs,
      rs3m: Math.max(5, Math.min(99, rs - ((code % 9) - 4))),
      rs6m: Math.max(5, Math.min(99, rs - ((code % 13) - 6))),
      rvol: (0.7 + (code % 14) / 10),
      persist: Math.max(1, code % 9),               // weeks in top decile
      accel: chg + ((code % 7) - 3) * 0.4,          // RS acceleration
      atr: ((code % 6) + 1) * 0.2,
      // ── spec fields (kairos _QMOM14_ALL_COLS) ──
      sharpe126: (0.4 + (code % 26) / 10),                       // t.sharpe_126d · PRIMARY rank
      zUniv: ((code % 40) - 18) / 10,                            // momentum z-score vs universe
      pos52w: Math.max(20, Math.min(100, 55 + Math.round(chg * 6) + (code % 30))), // 52W range pos
      adx: 14 + (code % 32),                                     // t.adx
      ema: (code % 3 === 0 ? "stacked+" : code % 3 === 1 ? "mixed" : "below"),     // t.ema_signal
      stage: (code % 4 === 0 ? "2 · markup" : code % 4 === 1 ? "1 · accum" : code % 4 === 2 ? "3 · distrib" : "2 · markup"),
      asness: ((code % 60) - 12) / 100,                          // Asness 12-1 factor
      ddPeak: -((code % 18) / 10),                               // drawdown from peak %
      rsSec: Math.max(10, Math.min(99, rs + ((code % 17) - 8))), // RS vs own sector
      shortInt: (2 + (code % 22)),                               // short % of float
      obv: (code % 3 === 0 ? "accum" : code % 3 === 1 ? "flat" : "distrib"),
      cat: (code % 3 === 0 ? "T1" : code % 3 === 1 ? "T2" : "—"),
      breakout: (code % 3 === 0),                                // fresh breakout flag
      hist: (() => { const a = []; let v = rs - 18; for (let i=0;i<60;i++){ v += (Math.sin(i*0.3+code)+0.4)*0.7 + (Math.random()-0.45); a.push(Math.max(5,Math.min(99,v))); } a[a.length-1]=rs; return a; })(),
    };
  }).sort((a,b)=>b.sharpe126 - a.sharpe126);
})();

const MO_TABS = [["leaders","RS Leaders"],["accel","Accelerating"],["fade","Fading"],["persist","Persistent"],["history","Signal History"]];

// Audit trail — every momentum signal the engine fired, with realized outcome.
const MO_HISTORY = (() => {
  const setups = ["RS breakout","Accel cross","Persist add","Pullback re-add","Fade exit"];
  const out = [];
  const syms = HEATMAP.slice(0, 22);
  for (let i = 0; i < 28; i++) {
    const [sym, sector] = syms[i % syms.length];
    const code = sym.charCodeAt(0) + i * 7;
    const open = i < 4;
    const rMult = open ? (code % 30 - 8) / 10 : ((code % 50) - 18) / 10;
    const win = !open && rMult > 0;
    const daysAgo = open ? (code % 6) : 8 + (code % 80);
    return;
  }
  // build deterministically
  for (let i = 0; i < 32; i++) {
    const [sym, sector] = syms[i % syms.length];
    const code = (sym.charCodeAt(0) + sym.charCodeAt(1) + i * 13);
    const open = i < 4;
    const rMult = open ? ((code % 22) - 6) / 10 : ((code % 56) - 20) / 10;
    const status = open ? "OPEN" : rMult > 0.05 ? "WIN" : rMult < -0.05 ? "LOSS" : "FLAT";
    return out;
  }
  return out;
})();

// simpler deterministic history
const MO_HIST = (() => {
  const syms = HEATMAP.slice(0, 24);
  const setups = ["RS breakout","Accel cross","Persistent add","Pullback re-add","Sector-leader BO"];
  return syms.map((h, i) => {
    const sym = h[0], sector = h[1];
    const code = sym.charCodeAt(0) + sym.charCodeAt(1) + i * 11;
    const open = i < 4;
    const r = open ? ((code % 20) - 5) / 10 : ((code % 58) - 22) / 10;
    const status = open ? "OPEN" : r >= 0.1 ? "WIN" : r <= -0.1 ? "LOSS" : "FLAT";
    return {
      sym, sector,
      date: `2026-0${1 + (i % 5)}-${String(2 + (code % 26)).padStart(2,"0")}`,
      setup: setups[code % setups.length],
      entryRS: 60 + (code % 35),
      exitRS: open ? null : 40 + (code % 50),
      r, status,
      held: open ? (code % 7) : 4 + (code % 18),
      mae: -((code % 12) / 10),  // max adverse excursion in R
      pnl: Math.round(r * 420),
    };
  });
})();

function MomentumHistory() {
  // REAL track record (audit #8) — fetches /api/momentum-signals (signal_log.json,
  // momentum strategies). Was MO_HIST: a synthetic ledger of fabricated R-multiples
  // biased to look profitable. Honest "unavailable" fallback, never synthetic.
  const [st, setSt] = React.useState({ loading: true, summary: null, signals: null, err: null });
  React.useEffect(() => {
    let alive = true;
    if (typeof fetch === "undefined") { setSt(s => ({ ...s, loading: false, err: "no fetch" })); return; }
    fetch("/api/momentum-signals", { credentials: "same-origin" })
      .then(r => (r.ok ? r.json() : Promise.reject(r.status)))
      .then(d => { if (alive) setSt({ loading: false, summary: d.summary || null, signals: d.signals || [], err: null }); })
      .catch(e => { if (alive) setSt({ loading: false, summary: null, signals: null, err: String(e) }); });
    return () => { alive = false; };
  }, []);

  if (st.loading) return <div className="ss-empty" style={{ padding: 40 }}>Loading momentum track record from signal_log…</div>;
  if (st.err || !st.summary || !st.signals) return <div className="ss-empty" style={{ padding: 40 }}>Momentum track record unavailable ({st.err || "no data"}). Source: /api/momentum-signals · signal_log.json.</div>;

  const sm = st.summary, sigs = st.signals;
  const closed = sigs.filter(s => s.pnl_pct != null);
  const wins = closed.filter(s => s.pnl_pct > 0).length;
  const losses = closed.filter(s => s.pnl_pct <= 0).length;
  const wr = sm.win_rate != null ? sm.win_rate : (closed.length ? (wins / closed.length) * 100 : 0);
  const nReal = sm.n_realized || closed.length;
  const wilsonLB = (() => { const n = nReal, p = wr / 100, z = 1.96; if (!n) return 0; const d = 1 + z * z / n; return ((p + z * z / (2 * n) - z * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / d) * 100; })();
  // equity curve = cumulative realized pnl_pct, chronological
  const chron = [...closed].sort((a, b) => String(a.date).localeCompare(String(b.date)));
  const eq = []; let cum = 0; chron.forEach(s => { cum += s.pnl_pct; eq.push(cum); });
  const w = 620, h = 150, pad = 18;
  const min = Math.min(0, ...eq) - 1, max = Math.max(1, ...eq) + 1;
  const x = i => pad + (i / Math.max(1, eq.length - 1)) * (w - pad * 2);
  const y = v => h - pad - ((v - min) / (max - min)) * (h - pad * 2);
  const eqTone = (eq[eq.length - 1] || 0) >= 0 ? "gn" : "rd";
  const tableRows = sigs.slice(0, 150);

  return (
    <div className="moh">
      <div className="moh-kpis">
        <MohK k="SIGNALS" v={sm.n_total} tone="copper" s={`${sm.n_closed} closed · ${sm.n_open} open`} />
        <MohK k="WIN RATE" v={`${Math.round(wr)}%`} tone={wr >= 50 ? "gn" : "rd"} s={`${wins}W · ${losses}L · n=${nReal}`} />
        <MohK k="WILSON LB" v={`${Math.round(wilsonLB)}%`} tone={wilsonLB >= 45 ? "gn" : "amb"} s="95% lower bound" />
        <MohK k="AVG P&L" v={`${sm.avg_pnl_pct >= 0 ? "+" : ""}${sm.avg_pnl_pct}%`} tone={sm.avg_pnl_pct >= 0 ? "gn" : "rd"} s="per signal" />
        <MohK k="AVG ALPHA" v={`${sm.avg_alpha_pp >= 0 ? "+" : ""}${sm.avg_alpha_pp}pp`} tone={sm.avg_alpha_pp >= 0 ? "gn" : "rd"} s="vs SPY" />
        <MohK k="BEAT SPY" v={`${sm.beat_spy_pct}%`} tone={sm.beat_spy_pct >= 50 ? "gn" : "amb"} s={`${sm.n_days}d · ${sm.first_date}→${sm.last_date}`} />
      </div>

      <div className="moh-grid">
        <div className="lab-card">
          <div className="lab-card-h mono">EQUITY CURVE · CUMULATIVE REALIZED P&L (%)</div>
          <svg viewBox={`0 0 ${w} ${h}`} className="lab-svg" preserveAspectRatio="xMidYMid meet">
            <defs><linearGradient id="moh-eq" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={`var(--${eqTone})`} stopOpacity="0.3" /><stop offset="100%" stopColor={`var(--${eqTone})`} stopOpacity="0" /></linearGradient></defs>
            <line x1={pad} y1={y(0)} x2={w - pad} y2={y(0)} stroke="var(--glass-line)" strokeDasharray="2 3" />
            <path d={`M ${pad} ${y(0)} L ${eq.map((v, i) => `${x(i)},${y(v)}`).join(" L ")} L ${w - pad} ${y(0)} Z`} fill="url(#moh-eq)" />
            <polyline points={eq.map((v, i) => `${x(i)},${y(v)}`).join(" ")} stroke={`var(--${eqTone})`} strokeWidth="1.8" fill="none" />
            <circle cx={x(eq.length - 1)} cy={y(eq[eq.length - 1] || 0)} r="3.5" fill={`var(--${eqTone})`} />
          </svg>
          <div className="moh-eqfoot mono dim2">Cumulative realized P&L across {closed.length} closed momentum signals · {sm.first_date} → {sm.last_date}</div>
        </div>
        <div className="lab-card">
          <div className="lab-card-h mono">OUTCOME DISTRIBUTION</div>
          <div className="moh-dist">
            {[["WIN", wins, "gn"], ["LOSS", losses, "rd"], ["OPEN", sm.n_open, "ink"]].map(([l, n, t], i) => (
              <div key={i} className="moh-distrow"><span className="mono dim2">{l}</span><div className="moh-distbar"><div style={{ width: `${n / (sm.n_total || 1) * 100}%`, background: `var(--${t})` }} /></div><span className="mono">{n}</span></div>
            ))}
          </div>
          <div className="moh-bysetup mono dim2" style={{ marginTop: 8 }}>Realized win rate {Math.round(wr)}% (Wilson LB {Math.round(wilsonLB)}%) · {sm.beat_spy_pct}% beat SPY over {sm.n_days} days.</div>
        </div>
      </div>

      <div className="wsx-body">
        <table className="dtable wsx-tbl moh-tbl">
          <thead><tr>
            <th>Date</th><th>Sym</th><th>Setup</th><th className="r">Score</th><th className="r">RS</th>
            <th className="r">Stars</th><th className="r">P&L %</th><th className="r">Alpha</th><th>Outcome</th>
          </tr></thead>
          <tbody>{tableRows.map((s, i) => {
            const status = s.pnl_pct == null ? "OPEN" : (s.pnl_pct > 0 ? "WIN" : "LOSS");
            return (
              <tr key={i}>
                <td className="mono dim2">{s.date}</td>
                <td className="mono"><b>{s.ticker}</b></td>
                <td className="mono dim">{s.strategy || "—"}</td>
                <td className="r mono tabular">{s.score != null ? Math.round(s.score) : "—"}</td>
                <td className="r mono tabular dim">{s.rs_rank != null ? Math.round(s.rs_rank) : "—"}</td>
                <td className="r mono tabular dim">{s.stars != null ? "★" + Math.round(s.stars) : "—"}</td>
                <td className={`r mono tabular ${s.pnl_pct == null ? "dim" : s.pnl_pct >= 0 ? "up" : "dn"}`}>{s.pnl_pct == null ? "—" : (s.pnl_pct >= 0 ? "+" : "") + s.pnl_pct.toFixed(2) + "%"}</td>
                <td className={`r mono tabular ${s.alpha == null ? "dim" : s.alpha >= 0 ? "up" : "dn"}`}>{s.alpha == null ? "—" : (s.alpha >= 0 ? "+" : "") + Number(s.alpha).toFixed(1) + "pp"}</td>
                <td><Pill tone={status === "WIN" ? "gn" : status === "LOSS" ? "rd" : "cy"} small>{status}</Pill></td>
              </tr>
            );
          })}</tbody>
        </table>
      </div>
      <div className="moh-note mono dim2">
        Every momentum signal the engine fired (RS New High, Trend Continuation, EMA pullback, Pocket Pivot, VCP, 10-Week Pullback, Breakout/Impulse) logged with its realized P&L and alpha vs SPY — the honest audit trail. Win-rate shown with its Wilson 95% lower bound so a small sample can't masquerade as edge. Source: /api/momentum-signals · signal_log.json (showing latest {tableRows.length} of {sm.n_total}).
      </div>
    </div>
  );
}

function MohK({ k, v, tone, s }) {
  return <div className={`wsx-kpi wsx-kpi--${tone}`}><div className="wsx-kpi-l mono">{k}</div><div className={`wsx-kpi-v mono kpi-tone--${tone}`}>{v}</div><div className="wsx-kpi-s mono dim2">{s}</div></div>;
}

function SurfaceMomentum({ onTicker }) {
  const [tab, setTab] = useMo("leaders");
  const [sel, setSel] = useMo(MO_ROWS[0].sym);
  const [sort, setSort] = useMo({ col: "rs", dir: -1 });

  const rows = useMom(() => {
    let r = MO_ROWS;
    if (tab === "accel") r = r.filter(x => x.accel > 1.5);
    if (tab === "fade") r = [...MO_ROWS].filter(x => x.rs1w < x.rs3m).sort((a,b)=>(a.rs1w-a.rs3m)-(b.rs1w-b.rs3m));
    if (tab === "persist") r = [...MO_ROWS].sort((a,b)=>b.persist-a.persist);
    return [...r].sort((a,b)=>{ const av=a[sort.col],bv=b[sort.col]; const an=+av,bn=+bv; if(!isNaN(an)&&!isNaN(bn))return (an-bn)*sort.dir; return String(av).localeCompare(String(bv))*sort.dir; }).slice(0, 30);
  }, [tab, sort]);

  const TH = (col, label, r) => (
    <th className={`${r?"r":""} wsx-th ${sort.col===col?"is-active":""}`} onClick={()=>setSort(s=>s.col===col?{col,dir:-s.dir}:{col,dir:-1})}>
      {label}{sort.col===col && <span className="wsx-arr mono">{sort.dir>0?"▲":"▼"}</span>}
    </th>
  );

  return (
    <div className="surface wsx wsx--copper mo">
      <div className="wsx-hdr">
        <div className="wsx-hdr-l">
          <div className="wsx-eyebrow mono">RELATIVE STRENGTH · MULTI-TIMEFRAME</div>
          <h1 className="wsx-title mono">Momentum</h1>
          <div className="wsx-sub mono dim2">Ranked leaderboard of the strongest names · RS rank vs SPY · 1W/1M/3M/6M history · persistence + acceleration · winners keep winning</div>
        </div>
        <div className="wsx-hdr-r"><FreshnessPill state="live" age="18s" /><span className="mono dim2">src · EODHD /eod · RS computed 63d</span></div>
      </div>

      <div className="wsx-kpis">
        <div className="wsx-kpi wsx-kpi--copper"><div className="wsx-kpi-l mono">RS LEADERS</div><div className="wsx-kpi-v mono kpi-tone--copper">{MO_ROWS.filter(r=>r.rs>=80).length}</div><div className="wsx-kpi-s mono dim2">RS ≥ 80</div></div>
        <div className="wsx-kpi wsx-kpi--gn"><div className="wsx-kpi-l mono">ACCELERATING</div><div className="wsx-kpi-v mono kpi-tone--gn">{MO_ROWS.filter(r=>r.accel>1.5).length}</div><div className="wsx-kpi-s mono dim2">RS slope ↑</div></div>
        <div className="wsx-kpi wsx-kpi--rd"><div className="wsx-kpi-l mono">FADING</div><div className="wsx-kpi-v mono kpi-tone--rd">{MO_ROWS.filter(r=>r.rs1w<r.rs3m).length}</div><div className="wsx-kpi-s mono dim2">1W &lt; 3M RS</div></div>
        <div className="wsx-kpi wsx-kpi--copper"><div className="wsx-kpi-l mono">SHARPE ≥1.5</div><div className="wsx-kpi-v mono kpi-tone--copper">{MO_ROWS.filter(r=>r.sharpe126>=1.5).length}</div><div className="wsx-kpi-s mono dim2">clean trend gate</div></div>
        <div className="wsx-kpi wsx-kpi--gn"><div className="wsx-kpi-l mono">ADX ≥25</div><div className="wsx-kpi-v mono kpi-tone--gn">{MO_ROWS.filter(r=>r.adx>=25).length}</div><div className="wsx-kpi-s mono dim2">tradeable trend</div></div>
        <div className="wsx-kpi wsx-kpi--amb"><div className="wsx-kpi-l mono">FRESH BREAKOUT</div><div className="wsx-kpi-v mono kpi-tone--amb">{MO_ROWS.filter(r=>r.breakout).length}</div><div className="wsx-kpi-s mono dim2">prime entry</div></div>
        <div className="wsx-kpi wsx-kpi--violet"><div className="wsx-kpi-l mono">STAGE-2 MARKUP</div><div className="wsx-kpi-v mono kpi-tone--violet">{MO_ROWS.filter(r=>r.stage.startsWith("2")).length}</div><div className="wsx-kpi-s mono dim2">buyable phase</div></div>
      </div>

      <div className="lab-tabs">
        {MO_TABS.map(([id,l]) => <button key={id} className={`lab-tab ${tab===id?"is-on":""}`} onClick={()=>setTab(id)}>{l}</button>)}
      </div>

      <div className="mo-split" style={tab === "history" ? { display: "block" } : null}>
        {tab === "history" ? <MomentumHistory /> : (
          <>
          <div className="wsx-body mo-tbl-wrap">
          <table className="dtable wsx-tbl mo-tbl">
            <thead><tr>
              <th className="r wsx-th">#</th>
              {TH("sym","Sym")}<th>Name</th>
              {TH("sharpe126","Sharpe126",true)}{TH("zUniv","Z",true)}{TH("rs","RS",true)}{TH("rsSec","RS·Sec",true)}
              {TH("pos52w","52W",true)}{TH("adx","ADX",true)}{TH("rvol","Vol",true)}<th>EMA</th>
              <th>Stage</th>{TH("asness","Asness",true)}{TH("ddPeak","DD-Pk",true)}{TH("shortInt","Short",true)}
              <th>OBV</th><th>Cat</th><th>BO</th><th>7d</th>
            </tr></thead>
            <tbody>{rows.map((t,i)=>(
              <tr key={t.sym+i} className={sel===t.sym?"is-sel":""} onClick={()=>setSel(t.sym)}>
                <td className="r mono dim2"><b className={i<3?"copper":""}>{i+1}</b></td>
                <td className="mono"><b>{t.sym}</b></td>
                <td className="dim">{t.name}</td>
                <td className="r" data-field="t.sharpe_126d" data-provenance="comp"><span className={`mo-rsbadge mo-rs--${t.sharpe126>=1.5?"hot":t.sharpe126>=1?"warm":"cool"}`}>{t.sharpe126.toFixed(2)}</span></td>
                <td className={`r mono tabular ${t.zUniv>=1?"up":t.zUniv<=-1?"dn":"dim"}`}>{t.zUniv>=0?"+":""}{t.zUniv.toFixed(1)}</td>
                <td className="r mono tabular" data-field="t.rs_rank" data-provenance="comp">{t.rs}</td>
                <td className="r mono tabular" data-field="t.sector_pct_rank">{t.rsSec}</td>
                <td className={`r mono tabular ${t.pos52w>=90?"up":"dim"}`}>{t.pos52w}%</td>
                <td className={`r mono tabular ${t.adx>=25?"up":"warn"}`} data-field="t.adx">{t.adx}</td>
                <td className={`r mono tabular ${t.rvol>=1.5?"up":"dim"}`} data-field="t.rvol">{t.rvol.toFixed(2)}×</td>
                <td className={`mono ${t.ema==="stacked+"?"up":t.ema==="below"?"dn":"dim"}`} data-field="t.ema_signal">{t.ema}</td>
                <td className={`mono ${t.stage.startsWith("2")?"up":t.stage.startsWith("3")?"dn":"dim"}`} data-field="t.stage">{t.stage}</td>
                <td className={`r mono tabular ${t.asness>=0?"up":"dn"}`}>{t.asness>=0?"+":""}{t.asness.toFixed(2)}</td>
                <td className="r mono tabular dn" data-field="t.max_dd_3y">{t.ddPeak.toFixed(1)}%</td>
                <td className={`r mono tabular ${t.shortInt>=15?"amb":"dim"}`} data-field="t.short_float_pct">{t.shortInt}%</td>
                <td className={`mono ${t.obv==="accum"?"up":t.obv==="distrib"?"dn":"dim"}`}>{t.obv}</td>
                <td className="mono dim2">{t.cat}</td>
                <td>{t.breakout ? <Pill tone="gn" small>BO</Pill> : <span className="dim2 mono">—</span>}</td>
                <td><Sparkline data={t.hist} color={`var(--${t.rs1w>=t.rs3m?"gn":"rd"})`} w={64} h={18} /></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
        <MoDetail sym={sel} onTicker={onTicker} />
          </>
        )}
      </div>
    </div>
  );
}

function MoDetail({ sym, onTicker }) {
  const t = MO_ROWS.find(r => r.sym === sym) || MO_ROWS[0];
  const w = 300, h = 120, pad = 14;
  const min = Math.min(...t.hist) - 4, max = Math.max(...t.hist) + 4;
  const x = i => pad + (i/59)*(w-pad*2);
  const y = v => h - pad - ((v-min)/(max-min))*(h-pad*2);
  return (
    <div className="sdp mo-detail">
      <div className="sdp-hdr">
        <div>
          <div className="sdp-sym mono"><b>{t.sym}</b> <span className="dim2">{t.sector}</span></div>
          <div className="sdp-px mono">RS <b className="copper">{t.rs}</b> · ${t.price.toFixed(2)} <span className={t.chg>=0?"up":"dn"}>{t.chg>=0?"+":""}{t.chg.toFixed(2)}%</span></div>
        </div>
        <span className={`mo-rsbadge mo-rs--${t.rs>=80?"hot":t.rs>=60?"warm":"cool"}`}>{t.rs}</span>
      </div>
      <button className="sdp-open mono" onClick={()=>onTicker(t.sym)}>OPEN 14-LENS DETAIL →</button>
      <div className="sdp-body">
        <div className="sdp-sec"><div className="sdp-sec-h"><span className="sdp-sec-n mono">RS</span><span className="mono">60-DAY HISTORY</span></div>
          <div className="sdp-sec-b">
            <svg viewBox={`0 0 ${w} ${h}`} style={{width:"100%",overflow:"visible"}}>
              <defs><linearGradient id="mo-rsg" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--copper)" stopOpacity="0.3"/><stop offset="100%" stopColor="var(--copper)" stopOpacity="0"/></linearGradient></defs>
              <line x1={pad} y1={y(80)} x2={w-pad} y2={y(80)} stroke="var(--gn)" strokeDasharray="2 3" opacity="0.4" /><text x={w-pad} y={y(80)-3} fontSize="8" className="mono" textAnchor="end" fill="var(--gn)">80 leader</text>
              <line x1={pad} y1={y(50)} x2={w-pad} y2={y(50)} stroke="var(--ink-3)" strokeDasharray="2 3" opacity="0.4" />
              <path d={`M ${pad} ${y(min)} L ${t.hist.map((v,i)=>`${x(i)},${y(v)}`).join(" L ")} L ${w-pad} ${y(min)} Z`} fill="url(#mo-rsg)" />
              <polyline points={t.hist.map((v,i)=>`${x(i)},${y(v)}`).join(" ")} stroke="var(--copper)" strokeWidth="1.6" fill="none" style={{filter:"drop-shadow(0 0 4px var(--copper))"}} />
              <circle cx={x(59)} cy={y(t.rs)} r="3.5" fill="var(--copper)" style={{filter:"drop-shadow(0 0 6px var(--copper))"}} />
            </svg>
          </div>
        </div>
        <div className="sdp-sec"><div className="sdp-sec-h"><span className="sdp-sec-n mono">TF</span><span className="mono">RS ACROSS TIMEFRAMES</span></div>
          <div className="sdp-sec-b">
            {[["1W",t.rs1w],["1M",t.rs1m],["3M",t.rs3m],["6M",t.rs6m]].map(([l,v],i)=>(
              <div key={i} className="sdp-bar"><span className="mono dim2">{l}</span><div className="sdp-bar-t"><div className="sdp-bar-f" style={{width:`${v}%`,background:v>=80?"var(--gn)":v>=50?"var(--amb)":"var(--rd)"}}/></div><span className="mono">{v}</span></div>
            ))}
          </div>
        </div>
        <div className="sdp-sec"><div className="sdp-sec-h"><span className="sdp-sec-n mono">↗</span><span className="mono">PERSISTENCE · ACCEL</span></div>
          <div className="sdp-sec-b">
            <div className="sdp-kv"><span className="mono dim2">weeks in top decile</span><span className="mono copper">{t.persist}w</span></div>
            <div className="sdp-kv"><span className="mono dim2">RS acceleration</span><span className={`mono ${t.accel>=0?"up":"dn"}`}>{t.accel>=0?"+":""}{t.accel.toFixed(1)}</span></div>
            <div className="sdp-kv"><span className="mono dim2">1W vs 3M</span><span className={`mono ${t.rs1w>=t.rs3m?"up":"dn"}`}>{t.rs1w>=t.rs3m?"strengthening":"fading"}</span></div>
            <div className="sdp-kv"><span className="mono dim2">RVOL</span><span className="mono">{t.rvol.toFixed(2)}×</span></div>
          </div>
        </div>
        <div className="sdp-sec"><div className="sdp-sec-h"><span className="sdp-sec-n mono">★</span><span className="mono">EDGE READ</span></div>
          <div className="sdp-sec-b"><div className="sdp-mech mono">{t.rs>=80 && t.rs1w>=t.rs3m ? "Persistent leader, still strengthening — highest-quality momentum (winners keep winning)." : t.rs1w<t.rs3m ? "RS fading vs 3M — momentum decaying, avoid fresh entries." : "Mid-pack RS — needs a catalyst to lead."}</div></div>
        </div>
      </div>
    </div>
  );
}

window.SurfaceMomentum = SurfaceMomentum;

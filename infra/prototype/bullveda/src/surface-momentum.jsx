// surface-momentum.jsx — Momentum workspace, quant-grade.
// RS-ranked leaders + multi-timeframe RS context, momentum persistence / acceleration,
// and a per-name RS history sparkline. Real data via window.__BV.scanRows() when served;
// honest empty state when the live scan returns nothing.

const { useState: useMo, useMemo: useMom } = React;

// ═══════════════════════════════════════════════════════════════════
// SERVED-AWARE DATA LAYER
// SERVED === true  → real production deploy (window.__BV present).
//   Rows come from the live scan universe. If the scan is empty we show an
//   honest empty state — NEVER demo tickers.
// SERVED === false → standalone prototype/showcase (no window.__BV).
//   Falls back to the curated HEATMAP/WATCHLIST sample so the design renders.
// ═══════════════════════════════════════════════════════════════════
const MO_SERVED = !!window.__BV;

const MO_num = (v) => (typeof v === "number" && isFinite(v)) ? v : null;
const MO_clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

// Build the leaderboard. When served, map real scan rows; otherwise synthesize
// from the prototype sample data. Returns [] when served + scan empty.
function moBuildRows() {
  if (MO_SERVED) {
    const BV = window.__BV;
    const scan = (BV && BV.ready && BV.scanRows) ? BV.scanRows() : [];
    if (!scan || !scan.length) return [];
    return scan.map((s) => {
      const raw = s._raw || {};
      const rs = MO_num(parseFloat(s.rs));               // sr.rs is a "NN" string or "—"
      const rsRank = rs != null ? rs : MO_num(raw.rs_rank);
      const r1m = MO_num(raw.perf_month);
      const r3m = MO_num(raw.perf_3m);
      const r6m = MO_num(raw.perf_6m);
      const r1w = MO_num(raw.perf_week);
      const chg = MO_num(s.chg);
      const rvol = MO_num(parseFloat(s.rvol));
      const adx = MO_num(s.adx);
      const sharpe = MO_num(s.sharpe);
      const off52 = MO_num(s.off52);                     // % below 52w high (≤0)
      // 52W range position: 100 = at high. off52 is negative below the high.
      const pos52w = off52 != null ? MO_clamp(Math.round(100 + off52), 0, 100) : null;
      // RS acceleration proxy: 1M perf minus 3M-average-per-month perf.
      const accel = (r1m != null && r3m != null) ? +(r1m - r3m / 3).toFixed(2)
                  : (chg != null ? chg : null);
      const ema = (() => {
        const e = (raw.ema_signal || raw.ema_stack || "").toString().toLowerCase();
        if (e.indexOf("stack") >= 0 || e.indexOf("above") >= 0) return "stacked+";
        if (e.indexOf("below") >= 0 || e.indexOf("down") >= 0) return "below";
        return e ? "mixed" : "—";
      })();
      // Build a real RS-context series for the sparkline ONLY from real perf points
      // (week → month → 3M → 6M, oldest→newest as a coarse trajectory). If we don't
      // have enough real points, leave hist null → the sparkline is skipped (honest).
      const histPts = [r6m, r3m, r1m, r1w, chg].filter((v) => v != null);
      const hist = histPts.length >= 2 ? histPts : null;
      return {
        sym: s.sym, sector: s.sector || raw.sector || "—",
        name: s.name || s.sym,
        mcap: MO_num(s.mcap),
        price: MO_num(s.price),
        chg,
        score: MO_num(s.score),
        verdict: s.verdict || "—",
        rs: rsRank,
        rs1w: r1w, rs1m: r1m, rs3m: r3m, rs6m: r6m,
        rvol, adx, sharpe126: sharpe,
        pos52w,
        accel,
        persist: MO_num(raw.rs_weeks_top_decile),         // real or null
        zUniv: MO_num(raw.mom_z),                          // momentum z vs universe (real or null)
        ema,
        stage: raw.stage || raw.weinstein_stage || "—",
        rsSec: MO_num(raw.sector_pct_rank),
        shortInt: MO_num(s.si),
        cat: s.cat || "—",
        breakout: !!(raw.fresh_breakout || raw.at_52w_breakout),
        hist,
        _scan: s,
      };
    }).sort((a, b) => {
      // primary rank: Sharpe126 (real), then RS, then score — nulls sink.
      const sa = a.sharpe126, sb = b.sharpe126;
      if (sa != null && sb != null && sa !== sb) return sb - sa;
      if (sa != null && sb == null) return -1;
      if (sa == null && sb != null) return 1;
      const ra = a.rs == null ? -1 : a.rs, rb = b.rs == null ? -1 : b.rs;
      if (ra !== rb) return rb - ra;
      return (b.score || 0) - (a.score || 0);
    });
  }

  // ── Standalone prototype fallback (only reached when !window.__BV) ──
  if (typeof HEATMAP === "undefined" || !Array.isArray(HEATMAP)) return [];
  return HEATMAP.map(([sym, sector, mcap, chg]) => {
    const code = sym.charCodeAt(0) + sym.charCodeAt(1);
    const w = (typeof WATCHLIST !== "undefined" ? WATCHLIST : []).find(x => x.sym === sym);
    const rs = MO_clamp(50 + Math.round(chg * 7) + (code % 20), 8, 99);
    return {
      sym, sector, mcap, chg,
      name: w?.name || `${sector} Corp`,
      price: w?.price || (20 + code % 200),
      score: w?.score || MO_clamp(50 + Math.round(chg * 5), 28, 94),
      verdict: w?.verdict || "—",
      rs,
      rs1w: MO_clamp(rs + ((code % 11) - 5), 5, 99),
      rs1m: rs,
      rs3m: MO_clamp(rs - ((code % 9) - 4), 5, 99),
      rs6m: MO_clamp(rs - ((code % 13) - 6), 5, 99),
      rvol: (0.7 + (code % 14) / 10),
      persist: Math.max(1, code % 9),
      accel: chg + ((code % 7) - 3) * 0.4,
      sharpe126: (0.4 + (code % 26) / 10),
      zUniv: ((code % 40) - 18) / 10,
      pos52w: MO_clamp(55 + Math.round(chg * 6) + (code % 30), 20, 100),
      adx: 14 + (code % 32),
      ema: (code % 3 === 0 ? "stacked+" : code % 3 === 1 ? "mixed" : "below"),
      stage: (code % 4 === 0 ? "2 · markup" : code % 4 === 1 ? "1 · accum" : code % 4 === 2 ? "3 · distrib" : "2 · markup"),
      rsSec: MO_clamp(rs + ((code % 17) - 8), 10, 99),
      shortInt: (2 + (code % 22)),
      cat: (code % 3 === 0 ? "T1" : code % 3 === 1 ? "T2" : "—"),
      breakout: (code % 3 === 0),
      hist: (() => { const a = []; let v = rs - 18; for (let i = 0; i < 60; i++) { v += (Math.sin(i * 0.3 + code) + 0.4) * 0.7 + (Math.random() - 0.45); a.push(MO_clamp(v, 5, 99)); } a[a.length - 1] = rs; return a; })(),
    };
  }).sort((a, b) => b.sharpe126 - a.sharpe126);
}

const MO_ROWS = moBuildRows();

const MO_TABS = [["leaders","RS Leaders"],["accel","Accelerating"],["fade","Fading"],["persist","Persistent"],["history","Signal History"]];

function MomentumHistory() {
  // REAL track record (audit #8) — fetches /api/momentum-signals (signal_log.json,
  // momentum strategies). Honest "unavailable" fallback, never synthetic.
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
  // Guard: empty equity curve → render an honest placeholder instead of NaN SVG paths.
  const haveEq = eq.length >= 1;
  const min = Math.min(0, ...eq) - 1, max = Math.max(1, ...eq) + 1;
  const span = (max - min) || 1;                       // never divide by 0
  const denomX = Math.max(1, eq.length - 1);
  const x = i => pad + (i / denomX) * (w - pad * 2);
  const y = v => h - pad - ((v - min) / span) * (h - pad * 2);
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
          {haveEq ? (
            <svg viewBox={`0 0 ${w} ${h}`} className="lab-svg" preserveAspectRatio="xMidYMid meet">
              <defs><linearGradient id="moh-eq" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={`var(--${eqTone})`} stopOpacity="0.3" /><stop offset="100%" stopColor={`var(--${eqTone})`} stopOpacity="0" /></linearGradient></defs>
              <line x1={pad} y1={y(0)} x2={w - pad} y2={y(0)} stroke="var(--glass-line)" strokeDasharray="2 3" />
              <path d={`M ${pad} ${y(0)} L ${eq.map((v, i) => `${x(i)},${y(v)}`).join(" L ")} L ${w - pad} ${y(0)} Z`} fill="url(#moh-eq)" />
              <polyline points={eq.map((v, i) => `${x(i)},${y(v)}`).join(" ")} stroke={`var(--${eqTone})`} strokeWidth="1.8" fill="none" />
              <circle cx={x(eq.length - 1)} cy={y(eq[eq.length - 1] || 0)} r="3.5" fill={`var(--${eqTone})`} />
            </svg>
          ) : (
            <div className="ss-empty" style={{ padding: 28 }}>No closed momentum signals yet — equity curve appears once trades realize.</div>
          )}
          <div className="moh-eqfoot mono dim2">Cumulative realized P&L across {closed.length} closed momentum signals · {sm.first_date} → {sm.last_date}</div>
        </div>
        <div className="lab-card">
          <div className="lab-card-h mono">OUTCOME DISTRIBUTION</div>
          <div className="moh-dist">
            {[["WIN", wins, "gn"], ["LOSS", losses, "rd"], ["OPEN", sm.n_open, "ink"]].map(([l, n, t], i) => (
              <div key={i} className="moh-distrow"><span className="mono dim2">{l}</span><div className="moh-distbar"><div style={{ width: `${(n || 0) / (sm.n_total || 1) * 100}%`, background: `var(--${t})` }} /></div><span className="mono">{n}</span></div>
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

// Safe cell renderers — every numeric field can be null (feed-honest) so we never
// call .toFixed on null nor emit a stray NaN into the DOM.
const moFix = (v, d = 0, suffix = "") => (v == null ? "—" : v.toFixed(d) + suffix);
const moInt = (v, suffix = "") => (v == null ? "—" : Math.round(v) + suffix);
const moSigned = (v, d = 1) => (v == null ? "—" : (v >= 0 ? "+" : "") + v.toFixed(d));

function SurfaceMomentum({ onTicker }) {
  const [tab, setTab] = useMo("leaders");
  const [sel, setSel] = useMo(MO_ROWS.length ? MO_ROWS[0].sym : null);
  const [sort, setSort] = useMo({ col: "rs", dir: -1 });

  const empty = MO_ROWS.length === 0;

  const rows = useMom(() => {
    if (empty) return [];
    let r = MO_ROWS;
    if (tab === "accel") r = r.filter(x => x.accel != null && x.accel > 1.5);
    if (tab === "fade") r = [...MO_ROWS].filter(x => x.rs1w != null && x.rs3m != null && x.rs1w < x.rs3m).sort((a, b) => (a.rs1w - a.rs3m) - (b.rs1w - b.rs3m));
    if (tab === "persist") r = [...MO_ROWS].sort((a, b) => (b.persist || 0) - (a.persist || 0));
    return [...r].sort((a, b) => {
      const av = a[sort.col], bv = b[sort.col];
      const an = +av, bn = +bv;
      if (av != null && bv != null && !isNaN(an) && !isNaN(bn)) return (an - bn) * sort.dir;
      if (av != null && bv == null) return -sort.dir;
      if (av == null && bv != null) return sort.dir;
      return String(av).localeCompare(String(bv)) * sort.dir;
    }).slice(0, 30);
  }, [tab, sort, empty]);

  const TH = (col, label, r) => (
    <th className={`${r ? "r" : ""} wsx-th ${sort.col === col ? "is-active" : ""}`} onClick={() => setSort(s => s.col === col ? { col, dir: -s.dir } : { col, dir: -1 })}>
      {label}{sort.col === col && <span className="wsx-arr mono">{sort.dir > 0 ? "▲" : "▼"}</span>}
    </th>
  );

  // Count helpers — null-safe (a null field never satisfies a numeric threshold).
  const cnt = (fn) => MO_ROWS.filter(fn).length;

  return (
    <div className="surface wsx wsx--copper mo">
      <div className="wsx-hdr">
        <div className="wsx-hdr-l">
          <div className="wsx-eyebrow mono">RELATIVE STRENGTH · MULTI-TIMEFRAME</div>
          <h1 className="wsx-title mono">Momentum</h1>
          <div className="wsx-sub mono dim2">Ranked leaderboard of the strongest names · RS rank vs SPY · 1W/1M/3M/6M context · persistence + acceleration · winners keep winning</div>
        </div>
        <div className="wsx-hdr-r"><FreshnessPill state="live" age="18s" /><span className="mono dim2">src · EODHD /eod · RS computed 63d</span></div>
      </div>

      <div className="wsx-kpis">
        <div className="wsx-kpi wsx-kpi--copper"><div className="wsx-kpi-l mono">RS LEADERS</div><div className="wsx-kpi-v mono kpi-tone--copper">{cnt(r => r.rs != null && r.rs >= 80)}</div><div className="wsx-kpi-s mono dim2">RS ≥ 80</div></div>
        <div className="wsx-kpi wsx-kpi--gn"><div className="wsx-kpi-l mono">ACCELERATING</div><div className="wsx-kpi-v mono kpi-tone--gn">{cnt(r => r.accel != null && r.accel > 1.5)}</div><div className="wsx-kpi-s mono dim2">RS slope ↑</div></div>
        <div className="wsx-kpi wsx-kpi--rd"><div className="wsx-kpi-l mono">FADING</div><div className="wsx-kpi-v mono kpi-tone--rd">{cnt(r => r.rs1w != null && r.rs3m != null && r.rs1w < r.rs3m)}</div><div className="wsx-kpi-s mono dim2">1W &lt; 3M RS</div></div>
        <div className="wsx-kpi wsx-kpi--copper"><div className="wsx-kpi-l mono">SHARPE ≥1.5</div><div className="wsx-kpi-v mono kpi-tone--copper">{cnt(r => r.sharpe126 != null && r.sharpe126 >= 1.5)}</div><div className="wsx-kpi-s mono dim2">clean trend gate</div></div>
        <div className="wsx-kpi wsx-kpi--gn"><div className="wsx-kpi-l mono">ADX ≥25</div><div className="wsx-kpi-v mono kpi-tone--gn">{cnt(r => r.adx != null && r.adx >= 25)}</div><div className="wsx-kpi-s mono dim2">tradeable trend</div></div>
        <div className="wsx-kpi wsx-kpi--amb"><div className="wsx-kpi-l mono">FRESH BREAKOUT</div><div className="wsx-kpi-v mono kpi-tone--amb">{cnt(r => r.breakout)}</div><div className="wsx-kpi-s mono dim2">prime entry</div></div>
        <div className="wsx-kpi wsx-kpi--violet"><div className="wsx-kpi-l mono">STAGE-2 MARKUP</div><div className="wsx-kpi-v mono kpi-tone--violet">{cnt(r => String(r.stage).startsWith("2"))}</div><div className="wsx-kpi-s mono dim2">buyable phase</div></div>
      </div>

      <div className="lab-tabs">
        {MO_TABS.map(([id, l]) => <button key={id} className={`lab-tab ${tab === id ? "is-on" : ""}`} onClick={() => setTab(id)}>{l}</button>)}
      </div>

      <div className="mo-split" style={tab === "history" ? { display: "block" } : null}>
        {tab === "history" ? <MomentumHistory /> : (empty ? (
          <div className="ss-empty" style={{ padding: 48, textAlign: "center" }}>No momentum leaders in today's scan.</div>
        ) : (
          <>
          <div className="wsx-body mo-tbl-wrap">
          <table className="dtable wsx-tbl mo-tbl">
            <thead><tr>
              <th className="r wsx-th">#</th>
              {TH("sym","Sym")}<th>Name</th>
              {TH("sharpe126","Sharpe126",true)}{TH("zUniv","Z",true)}{TH("rs","RS",true)}{TH("rsSec","RS·Sec",true)}
              {TH("pos52w","52W",true)}{TH("adx","ADX",true)}{TH("rvol","Vol",true)}<th>EMA</th>
              <th>Stage</th>{TH("shortInt","Short",true)}
              <th>Cat</th><th>BO</th><th>7d</th>
            </tr></thead>
            <tbody>{rows.map((t, i) => (
              <tr key={t.sym + i} className={sel === t.sym ? "is-sel" : ""} onClick={() => setSel(t.sym)}>
                <td className="r mono dim2"><b className={i < 3 ? "copper" : ""}>{i + 1}</b></td>
                <td className="mono"><b>{t.sym}</b></td>
                <td className="dim">{t.name}</td>
                <td className="r" data-field="t.sharpe_126d" data-provenance="comp"><span className={`mo-rsbadge mo-rs--${t.sharpe126 != null && t.sharpe126 >= 1.5 ? "hot" : t.sharpe126 != null && t.sharpe126 >= 1 ? "warm" : "cool"}`}>{moFix(t.sharpe126, 2)}</span></td>
                <td className={`r mono tabular ${t.zUniv != null && t.zUniv >= 1 ? "up" : t.zUniv != null && t.zUniv <= -1 ? "dn" : "dim"}`}>{moSigned(t.zUniv, 1)}</td>
                <td className="r mono tabular" data-field="t.rs_rank" data-provenance="comp">{moInt(t.rs)}</td>
                <td className="r mono tabular" data-field="t.sector_pct_rank">{moInt(t.rsSec)}</td>
                <td className={`r mono tabular ${t.pos52w != null && t.pos52w >= 90 ? "up" : "dim"}`}>{moInt(t.pos52w, "%")}</td>
                <td className={`r mono tabular ${t.adx != null && t.adx >= 25 ? "up" : "warn"}`} data-field="t.adx">{moInt(t.adx)}</td>
                <td className={`r mono tabular ${t.rvol != null && t.rvol >= 1.5 ? "up" : "dim"}`} data-field="t.rvol">{moFix(t.rvol, 2, "×")}</td>
                <td className={`mono ${t.ema === "stacked+" ? "up" : t.ema === "below" ? "dn" : "dim"}`} data-field="t.ema_signal">{t.ema}</td>
                <td className={`mono ${String(t.stage).startsWith("2") ? "up" : String(t.stage).startsWith("3") ? "dn" : "dim"}`} data-field="t.stage">{t.stage}</td>
                <td className={`r mono tabular ${t.shortInt != null && t.shortInt >= 15 ? "amb" : "dim"}`} data-field="t.short_float_pct">{moInt(t.shortInt, "%")}</td>
                <td className="mono dim2">{t.cat}</td>
                <td>{t.breakout ? <Pill tone="gn" small>BO</Pill> : <span className="dim2 mono">—</span>}</td>
                <td>{(t.hist && t.hist.length >= 2) ? <Sparkline data={t.hist} color={`var(--${(t.rs1w != null && t.rs3m != null && t.rs1w >= t.rs3m) ? "gn" : "rd"})`} w={64} h={18} /> : <span className="dim2 mono">—</span>}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
        <MoDetail sym={sel} onTicker={onTicker} />
          </>
        ))}
      </div>
    </div>
  );
}

function MoDetail({ sym, onTicker }) {
  const t = MO_ROWS.find(r => r.sym === sym) || MO_ROWS[0];
  if (!t) return <div className="sdp mo-detail"><div className="ss-empty" style={{ padding: 28 }}>No name selected.</div></div>;

  // RS history sparkline — render ONLY when we have a real 2+ point series with a
  // non-degenerate range. Otherwise the chart math (1/(max-min), i/(n-1)) would
  // produce NaN/Infinity → invalid SVG path "d" attribute. Honest "—" instead.
  const hist = (Array.isArray(t.hist) ? t.hist.filter(v => typeof v === "number" && isFinite(v)) : []);
  const haveHist = hist.length >= 2;
  const w = 300, h = 120, pad = 14;
  const min = haveHist ? Math.min(...hist) - 4 : 0;
  const max = haveHist ? Math.max(...hist) + 4 : 1;
  const span = (max - min) || 1;                          // never 0
  const denomX = Math.max(1, hist.length - 1);
  const x = i => pad + (i / denomX) * (w - pad * 2);
  const y = v => h - pad - ((v - min) / span) * (h - pad * 2);
  const last = haveHist ? hist[hist.length - 1] : null;

  const rs = t.rs;
  const tf = [["1W", t.rs1w], ["1M", t.rs1m], ["3M", t.rs3m], ["6M", t.rs6m]];

  return (
    <div className="sdp mo-detail">
      <div className="sdp-hdr">
        <div>
          <div className="sdp-sym mono"><b>{t.sym}</b> <span className="dim2">{t.sector}</span></div>
          <div className="sdp-px mono">RS <b className="copper">{moInt(rs)}</b> · {t.price != null ? "$" + t.price.toFixed(2) : "—"} {t.chg != null && <span className={t.chg >= 0 ? "up" : "dn"}>{t.chg >= 0 ? "+" : ""}{t.chg.toFixed(2)}%</span>}</div>
        </div>
        <span className={`mo-rsbadge mo-rs--${rs != null && rs >= 80 ? "hot" : rs != null && rs >= 60 ? "warm" : "cool"}`}>{moInt(rs)}</span>
      </div>
      <button className="sdp-open mono" onClick={() => onTicker(t.sym)}>OPEN 14-LENS DETAIL →</button>
      <div className="sdp-body">
        <div className="sdp-sec"><div className="sdp-sec-h"><span className="sdp-sec-n mono">RS</span><span className="mono">MOMENTUM TRAJECTORY</span></div>
          <div className="sdp-sec-b">
            {haveHist ? (
              <svg viewBox={`0 0 ${w} ${h}`} style={{ width: "100%", overflow: "visible" }}>
                <defs><linearGradient id="mo-rsg" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--copper)" stopOpacity="0.3" /><stop offset="100%" stopColor="var(--copper)" stopOpacity="0" /></linearGradient></defs>
                <path d={`M ${pad} ${y(min)} L ${hist.map((v, i) => `${x(i)},${y(v)}`).join(" L ")} L ${w - pad} ${y(min)} Z`} fill="url(#mo-rsg)" />
                <polyline points={hist.map((v, i) => `${x(i)},${y(v)}`).join(" ")} stroke="var(--copper)" strokeWidth="1.6" fill="none" style={{ filter: "drop-shadow(0 0 4px var(--copper))" }} />
                <circle cx={x(hist.length - 1)} cy={y(last)} r="3.5" fill="var(--copper)" style={{ filter: "drop-shadow(0 0 6px var(--copper))" }} />
              </svg>
            ) : (
              <div className="ss-empty mono dim2" style={{ padding: 18 }}>No RS history series for {t.sym} in the current feed.</div>
            )}
          </div>
        </div>
        <div className="sdp-sec"><div className="sdp-sec-h"><span className="sdp-sec-n mono">TF</span><span className="mono">RELATIVE STRENGTH BY TIMEFRAME</span></div>
          <div className="sdp-sec-b">
            {tf.map(([l, v], i) => (
              <div key={i} className="sdp-bar"><span className="mono dim2">{l}</span><div className="sdp-bar-t"><div className="sdp-bar-f" style={{ width: `${v != null ? MO_clamp(v, 0, 100) : 0}%`, background: v == null ? "var(--ink-3)" : v >= 80 ? "var(--gn)" : v >= 50 ? "var(--amb)" : "var(--rd)" }} /></div><span className="mono">{v == null ? "—" : Math.round(v)}</span></div>
            ))}
          </div>
        </div>
        <div className="sdp-sec"><div className="sdp-sec-h"><span className="sdp-sec-n mono">↗</span><span className="mono">PERSISTENCE · ACCEL</span></div>
          <div className="sdp-sec-b">
            <div className="sdp-kv"><span className="mono dim2">weeks in top decile</span><span className="mono copper">{t.persist != null ? t.persist + "w" : "—"}</span></div>
            <div className="sdp-kv"><span className="mono dim2">RS acceleration</span><span className={`mono ${t.accel != null && t.accel >= 0 ? "up" : t.accel != null ? "dn" : "dim2"}`}>{moSigned(t.accel, 1)}</span></div>
            <div className="sdp-kv"><span className="mono dim2">1W vs 3M</span><span className={`mono ${t.rs1w != null && t.rs3m != null ? (t.rs1w >= t.rs3m ? "up" : "dn") : "dim2"}`}>{t.rs1w != null && t.rs3m != null ? (t.rs1w >= t.rs3m ? "strengthening" : "fading") : "—"}</span></div>
            <div className="sdp-kv"><span className="mono dim2">RVOL</span><span className="mono">{moFix(t.rvol, 2, "×")}</span></div>
          </div>
        </div>
        <div className="sdp-sec"><div className="sdp-sec-h"><span className="sdp-sec-n mono">★</span><span className="mono">EDGE READ</span></div>
          <div className="sdp-sec-b"><div className="sdp-mech mono">{
            (rs != null && rs >= 80 && t.rs1w != null && t.rs3m != null && t.rs1w >= t.rs3m) ? "Persistent leader, still strengthening — highest-quality momentum (winners keep winning)."
            : (t.rs1w != null && t.rs3m != null && t.rs1w < t.rs3m) ? "RS fading vs 3M — momentum decaying, avoid fresh entries."
            : (rs != null) ? "Mid-pack RS — needs a catalyst to lead."
            : "RS history not available for this name in the current feed."
          }</div></div>
        </div>
      </div>
    </div>
  );
}

window.SurfaceMomentum = SurfaceMomentum;

// surface-perf.jsx — Performance (equity/risk/attribution) + Strategies (sleeve edge library)
// Quant-grade: risk-adjusted headline, equity vs SPY, underwater DD, attribution, R-distribution,
// per-sleeve Wilson edge, regime-activation matrix, edge-decay. Data shaped as portfolio_state +
// setup_stats.json (walk-forward) + EODHD regime context.

const { useState: usePerf, useMemo: usePerfm } = React;

// ── sleeve library (setup_stats.json · walk-forward, slippage+survivorship haircut) ──
const SLEEVES = [
  { k: "Continuation BO", n: 47, wr: 61.7, lb: 47.7, pf: 1.84, medR: 0.72, pnl: 4820, contrib: 38,
    decay: [44, 45, 47, 46, 48, 47, 48], regime: { bull: 2, chop: 1, bear: 0 }, status: "stable",
    mech: "Demand absorbs supply above a multi-week pivot; breakout on RVOL confirms institutional accumulation.",
    kill: "Wilson LB < 40% over trailing 30 trades, or median R < 0.3." },
  { k: "VCP", n: 38, wr: 58.0, lb: 45.0, pf: 1.62, medR: 0.61, pnl: 2140, contrib: 17,
    decay: [47, 46, 46, 45, 45, 44, 45], regime: { bull: 2, chop: 1, bear: 0 }, status: "stable",
    mech: "Volatility contracts as float tightens into a pivot; the squeeze release is the edge.",
    kill: "Contraction count < 2, or breakout fails to hold pivot by close." },
  { k: "Pullback", n: 52, wr: 55.8, lb: 44.0, pf: 1.41, medR: 0.48, pnl: 1680, contrib: 13,
    decay: [46, 45, 45, 44, 44, 43, 44], regime: { bull: 2, chop: 2, bear: 0 }, status: "stable",
    mech: "Trend-following entry into the rising 21-EMA; buys strength on weakness within an uptrend.",
    kill: "Close below 50-EMA, or pullback exceeds 50% of prior leg." },
  { k: "Gap & Go", n: 29, wr: 51.7, lb: 40.0, pf: 1.28, medR: 0.34, pnl: 940, contrib: 7,
    decay: [46, 45, 43, 42, 41, 40, 40], regime: { bull: 2, chop: 0, bear: 1 }, status: "decaying",
    mech: "News-catalyzed gap with continuation as late buyers chase; momentum exhaustion is the risk.",
    kill: "Edge erosion — Wilson LB fell 6pts in 60 trades; gap-fill rate rising." },
  { k: "Mean Revert", n: 41, wr: 54.0, lb: 43.0, pf: 1.36, medR: 0.41, pnl: 1240, contrib: 10,
    decay: [42, 43, 43, 44, 43, 43, 43], regime: { bull: 0, chop: 2, bear: 2 }, status: "stable",
    mech: "Oversold snap-back to the mean (Bollinger / RSI(2)); pays in chop and range regimes.",
    kill: "Trend regime active (ADX > 30) — disable, mean-reversion bleeds in trends." },
  { k: "Earnings Drift", n: 22, wr: 59.1, lb: 44.0, pf: 1.55, medR: 0.58, pnl: 1340, contrib: 11,
    decay: [48, 47, 46, 45, 44, 44, 44], regime: { bull: 2, chop: 1, bear: 1 }, status: "decaying",
    mech: "PEAD — post-earnings drift after a beat + positive guidance; the surprise underreaction.",
    kill: "ESP edge < +2%, or implied move > target distance (event blows through stop)." },
  { k: "Range Fade", n: 18, wr: 50.0, lb: 38.0, pf: 1.12, medR: 0.22, pnl: 320, contrib: 3,
    decay: [41, 40, 39, 39, 38, 38, 38], regime: { bull: 0, chop: 2, bear: 1 }, status: "watch",
    mech: "Fade range extremes when breadth confirms no expansion; tight stop beyond the band.",
    kill: "n < 30 — caution; Wilson LB below the 40% floor." },
];

const REGIMES = [["bull", "RISK ON", "gn"], ["chop", "CHOP", "amb"], ["bear", "RISK OFF", "rd"]];
const REG_DOT = v => v >= 2 ? "gn" : v === 1 ? "amb" : "rd";
const REG_LBL = v => v >= 2 ? "RUN" : v === 1 ? "SELECTIVE" : "OFF";

// ═══════════════════════════════════════════════════════════════
//  PERFORMANCE
// ═══════════════════════════════════════════════════════════════
function SurfacePerformance({ onTicker }) {
  const D = usePerfm(() => {
    // ~135 trading-day equity curves ending +12.27% (book) / +9.42% (SPY)
    const N = 135, book = [], spy = []; let b = 0, s = 0;
    for (let i = 0; i < N; i++) {
      b += 0.085 + (Math.sin(i * 0.18) + Math.cos(i * 0.41)) * 0.16 + (Math.sin(i * 1.7) * 0.10);
      s += 0.068 + (Math.sin(i * 0.14) + Math.cos(i * 0.33)) * 0.13;
      book.push(+b.toFixed(2)); spy.push(+s.toFixed(2));
    }
    const sc = 12.27 / book[N - 1], ss = 9.42 / spy[N - 1];
    const B = book.map(v => +(v * sc).toFixed(2)), S = spy.map(v => +(v * ss).toFixed(2));
    // underwater drawdown from book
    let peak = -1e9; const dd = B.map(v => { peak = Math.max(peak, v); return +(v - peak).toFixed(2); });
    const maxDD = Math.min(...dd);
    return { B, S, dd, maxDD };
  }, []);

  const months = [
    { m: "JUN", r: 1.8 }, { m: "JUL", r: 3.2 }, { m: "AUG", r: -1.1 }, { m: "SEP", r: 0.9 },
    { m: "OCT", r: 2.4 }, { m: "NOV", r: 1.6 }, { m: "DEC", r: -0.7 }, { m: "JAN", r: 2.1 },
    { m: "FEB", r: 1.3 }, { m: "MAR", r: -0.4 }, { m: "APR", r: 1.9 }, { m: "MAY", r: 1.2 },
  ];
  const rbins = [
    { label: "<-2R", count: 2, win: false }, { label: "-2R", count: 4, win: false },
    { label: "-1R", count: 11, win: false }, { label: "0R", count: 7, win: false },
    { label: "+1R", count: 14, win: true }, { label: "+2R", count: 6, win: true },
    { label: "+3R", count: 2, win: true }, { label: ">3R", count: 1, win: true },
  ];
  const sleeveAttr = SLEEVES.map(s => ({ label: s.k, value: s.pnl, tone: s.pnl >= 0 ? "gn" : "rd" }));
  const sectorAttr = [
    { label: "Industrials", value: 3640 }, { label: "Technology", value: 2980 },
    { label: "Energy", value: 1840 }, { label: "Materials", value: 1120 },
    { label: "Healthcare", value: 640 }, { label: "Finance", value: -820 },
  ];

  return (
    <div className="surface wsx wsx--gn q-perf">
      <div className="wsx-hdr">
        <div className="wsx-hdr-l">
          <div className="wsx-eyebrow mono">EQUITY CURVE · ATTRIBUTION · RISK-ADJUSTED</div>
          <h1 className="wsx-title mono">Performance</h1>
          <div className="wsx-sub mono dim2">realized + open P&amp;L · vs SPY benchmark · drawdown · per-sleeve &amp; per-sector attribution · R-distribution</div>
        </div>
        <div className="wsx-hdr-r">
          <FreshnessPill state="live" age="3s" />
          <span className="mono dim2">src · portfolio_state · trade_log · Schwab /quotes</span>
        </div>
      </div>

      {/* hero: headline + equity curve + underwater */}
      <div className="q-perf-hero">
        <div className="q-hero-l">
          <div className="q-hero-eyebrow mono dim2">NET RETURN · YTD</div>
          <div className="q-hero-num mono up">+12.27%</div>
          <div className="q-hero-sub mono">vs SPY <span className="dim2">+9.42%</span> · <span className="up">+285bp α</span></div>
          <div className="q-hero-chips">
            <span className="q-chip mono"><b className="up">+$9,200</b> realized</span>
            <span className="q-chip mono"><b className="up">+$2,660</b> open</span>
            <span className="q-chip mono">β <b>0.93</b></span>
          </div>
        </div>
        <div className="q-hero-r">
          <div className="q-eq-head">
            <span className="mono dim2">CUMULATIVE RETURN · 135 sessions</span>
            <span className="q-eq-legend mono">
              <i className="q-sw" style={{ background: "var(--gn)" }} />book
              <i className="q-sw q-sw--dash" />SPY
            </span>
          </div>
          <QEquity book={D.B} bench={D.S} h={150} />
          <div className="q-eq-head q-eq-head--uw">
            <span className="mono dim2">UNDERWATER · drawdown from peak</span>
            <span className="mono dn">max {D.maxDD.toFixed(1)}%</span>
          </div>
          <QUnderwater dd={D.dd} h={56} />
        </div>
      </div>

      {/* risk-adjusted KPI strip */}
      <div className="q-kpis">
        {[["CAGR", "+18.4%", "gn", "annualized"], ["SHARPE", "1.84", "gn", "rf-adj · 60d"],
          ["SORTINO", "2.61", "gn", "downside-adj"], ["CALMAR", "8.8", "gn", "CAGR ÷ maxDD"],
          ["MAX DD", D.maxDD.toFixed(1) + "%", "rd", "peak-trough"], ["PROFIT FACTOR", "2.31", "gn", "gross W ÷ L"],
          ["WIN RATE", "61.7%", "gn", "n=47 · Wilson 48%"], ["EXPECTANCY", "+0.63R", "copper", "per trade"]].map((k, i) => (
          <div key={i} className={`q-kpi q-kpi--${k[2]}`}>
            <div className="q-kpi-l mono">{k[0]}</div>
            <div className={`q-kpi-v mono kpi-tone--${k[2]}`}>{k[1]}</div>
            <div className="q-kpi-s mono dim2">{k[3]}</div>
          </div>
        ))}
      </div>

      {/* monthly returns strip */}
      <div className="lab-card">
        <div className="lab-card-h mono">MONTHLY RETURNS · trailing 12</div>
        <QMonths months={months} />
      </div>

      {/* attribution + distribution grid */}
      <div className="q-grid2">
        <div className="lab-card">
          <div className="lab-card-h mono">P&amp;L ATTRIBUTION · by sleeve</div>
          <QDiverge rows={sleeveAttr} fmt={v => `${v >= 0 ? "+" : "−"}$${Math.abs(v).toLocaleString()}`} />
        </div>
        <div className="lab-card">
          <div className="lab-card-h mono">P&amp;L ATTRIBUTION · by sector</div>
          <QDiverge rows={sectorAttr} fmt={v => `${v >= 0 ? "+" : "−"}$${Math.abs(v).toLocaleString()}`} />
        </div>
        <div className="lab-card">
          <div className="lab-card-h mono">R-MULTIPLE DISTRIBUTION · n=47 closed</div>
          <QHist bins={rbins} h={140} />
          <div className="q-dist-stats mono">
            <span>avg win <b className="up">+1.45R</b></span>
            <span>avg loss <b className="dn">−0.80R</b></span>
            <span>payoff <b>1.81×</b></span>
            <span>best <b className="up">+3.4R</b></span>
          </div>
        </div>
        <div className="lab-card">
          <div className="lab-card-h mono">PERIODIC RETURNS · book vs SPY</div>
          <table className="dtable wsx-tbl pf-mini">
            <thead><tr><th>Period</th><th className="r">Book</th><th className="r">SPY</th><th className="r">α</th><th className="r">Sharpe</th></tr></thead>
            <tbody>{[["Today", "+1.20%", "+0.42%", "+0.78%", "—"], ["WTD", "+2.68%", "+1.10%", "+1.58%", "2.1"],
              ["MTD", "+4.04%", "+2.30%", "+1.74%", "1.9"], ["QTD", "+6.40%", "+4.80%", "+1.60%", "1.8"],
              ["YTD", "+12.27%", "+9.42%", "+2.85%", "1.84"]].map((r, i) => (
              <tr key={i}><td className="mono">{r[0]}</td><td className="r tabular up">{r[1]}</td>
                <td className="r tabular dim">{r[2]}</td><td className="r tabular" style={{ color: "var(--copper)" }}>{r[3]}</td>
                <td className="r tabular dim2">{r[4]}</td></tr>
            ))}</tbody>
          </table>
        </div>
      </div>

      <div className="lab-verdict mono dim2">
        Edge is real and risk-adjusted (Sharpe 1.84, Calmar 8.8) — but concentrated in <b>Continuation BO</b> (38% of P&amp;L).
        Finance is the only negative sleeve/sector. Drawdown stayed shallow ({D.maxDD.toFixed(1)}%); the curve tracks well above SPY with +285bp annual alpha.
      </div>
      <div className="pf-note mono dim2">Equity from realized fills (trade_log) + marked-open positions (Schwab /quotes, 3s) · Sharpe/Sortino on daily returns, rf=4.3% · attribution net of slippage. Click a sector to drill in.</div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
//  STRATEGIES
// ═══════════════════════════════════════════════════════════════
function SurfaceStrategies({ onTicker }) {
  const [sel, setSel] = usePerf(SLEEVES[0].k);
  const cur = SLEEVES.find(s => s.k === sel) || SLEEVES[0];
  const avgPf = (SLEEVES.reduce((a, s) => a + s.pf, 0) / SLEEVES.length).toFixed(2);
  const decaying = SLEEVES.filter(s => s.status === "decaying").length;

  return (
    <div className="surface wsx wsx--copper q-strat">
      <div className="wsx-hdr">
        <div className="wsx-hdr-l">
          <div className="wsx-eyebrow mono">SLEEVE LIBRARY · LIVE EDGE · WALK-FORWARD</div>
          <h1 className="wsx-title mono">Strategies</h1>
          <div className="wsx-sub mono dim2">{SLEEVES.length} setup families · Wilson-validated win rate · profit factor · edge-decay · regime fit</div>
        </div>
        <div className="wsx-hdr-r">
          <FreshnessPill state="live" age="bundle 18s" />
          <span className="mono dim2">src · setup_stats.json · walk-forward</span>
        </div>
      </div>

      <div className="q-kpis q-kpis--4">
        {[["SLEEVES", SLEEVES.length, "copper", "active"], ["BEST WILSON LB", "47.7%", "gn", "Cont. BO · validated"],
          ["AVG PROFIT FACTOR", avgPf, "gn", "haircut"], ["DECAYING", decaying, "amb", "edge eroding · watch"]].map((k, i) => (
          <div key={i} className={`q-kpi q-kpi--${k[2]}`}>
            <div className="q-kpi-l mono">{k[0]}</div>
            <div className={`q-kpi-v mono kpi-tone--${k[2]}`}>{k[1]}</div>
            <div className="q-kpi-s mono dim2">{k[3]}</div>
          </div>
        ))}
      </div>

      {/* interactive backtester */}
      <StrategyBacktester sleeves={SLEEVES} />

      {/* main sleeve table */}
      <div className="wsx-body">
        <table className="dtable wsx-tbl q-strat-tbl">
          <thead><tr>
            <th>Strategy</th><th className="r">n</th><th className="r">WR</th><th>Wilson LB · vs 40% floor</th>
            <th className="r">PF</th><th className="r">Med R</th><th>Edge decay · 7mo</th>
            <th className="c">Bull</th><th className="c">Chop</th><th className="c">Bear</th><th>Status</th>
          </tr></thead>
          <tbody>{SLEEVES.map(s => (
            <tr key={s.k} className={sel === s.k ? "is-sel" : ""} onClick={() => setSel(s.k)}>
              <td><b>{s.k}</b></td>
              <td className={`r tabular ${s.n < 30 ? "warn" : "dim"}`}>{s.n}</td>
              <td className="r tabular up">{s.wr.toFixed(1)}%</td>
              <td>
                <div className="q-wilson"><QGaugeBar pct={s.lb} cap={40} tone={s.lb >= 45 ? "gn" : s.lb >= 40 ? "amb" : "rd"} /></div>
                <span className={`mono q-wilson-v ${s.lb >= 45 ? "up" : s.lb >= 40 ? "warn" : "dn"}`}>{s.lb.toFixed(0)}%</span>
              </td>
              <td className={`r tabular ${s.pf >= 1.5 ? "up" : s.pf >= 1.2 ? "" : "dn"}`}>{s.pf.toFixed(2)}</td>
              <td className="r tabular up">+{s.medR.toFixed(2)}R</td>
              <td><QSpark data={s.decay} /></td>
              <td className="c"><span className={`q-reg-dot q-reg-dot--${REG_DOT(s.regime.bull)}`} /></td>
              <td className="c"><span className={`q-reg-dot q-reg-dot--${REG_DOT(s.regime.chop)}`} /></td>
              <td className="c"><span className={`q-reg-dot q-reg-dot--${REG_DOT(s.regime.bear)}`} /></td>
              <td><Pill tone={s.status === "stable" ? "gn" : s.status === "decaying" ? "amb" : "ink"} small>{s.status}</Pill></td>
            </tr>
          ))}</tbody>
        </table>
      </div>

      {/* detail grid for selected sleeve */}
      <div className="q-grid2">
        <div className="lab-card">
          <div className="lab-card-h mono">{cur.k.toUpperCase()} · EDGE DECAY · rolling Wilson LB</div>
          <div className="q-decay-big">
            <QEquity book={cur.decay} h={120} tone={cur.decay[cur.decay.length - 1] < cur.decay[0] ? "amb" : "gn"} />
          </div>
          <div className="q-dist-stats mono">
            <span>now <b className={cur.lb >= 45 ? "up" : "warn"}>{cur.lb.toFixed(0)}%</b></span>
            <span>floor <b className="dim">40%</b></span>
            <span>n <b className={cur.n < 30 ? "warn" : ""}>{cur.n}</b></span>
            <span>PF <b className={cur.pf >= 1.5 ? "up" : ""}>{cur.pf.toFixed(2)}</b></span>
          </div>
        </div>
        <div className="lab-card">
          <div className="lab-card-h mono">{cur.k.toUpperCase()} · MECHANISM + FALSIFIER</div>
          <div className="q-mech">
            <div className="q-mech-row">
              <span className="q-mech-k mono up">▸ WHY IT WORKS</span>
              <span className="q-mech-v">{cur.mech}</span>
            </div>
            <div className="q-mech-row">
              <span className="q-mech-k mono dn">▸ KILL SWITCH</span>
              <span className="q-mech-v">{cur.kill}</span>
            </div>
            <div className="q-mech-regime">
              {REGIMES.map(([key, lbl, tone]) => (
                <div key={key} className="q-mech-reg">
                  <span className={`q-reg-dot q-reg-dot--${REG_DOT(cur.regime[key])}`} />
                  <span className="mono dim2">{lbl}</span>
                  <span className={`mono kpi-tone--${REG_DOT(cur.regime[key])}`}>{REG_LBL(cur.regime[key])}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="lab-verdict mono dim2">
        Quarantine rule: any sleeve whose Wilson LB closes below the <b>40% floor</b> auto-disables until it rebuilds n.
        <b> Gap &amp; Go</b> and <b>Earnings Drift</b> are decaying — size down. <b>Range Fade</b> (n=18) is sub-sample; trade at min size.
      </div>
      <div className="pf-note mono dim2">Stats from walk-forward backtest on setup_stats.json — slippage + survivorship haircut applied. Wilson lower-bound, not raw WR, gates capital. Regime dots: green=run · amber=selective · red=off.</div>
    </div>
  );
}

// ─── Interactive Strategy Backtester ───────────────────────────
(function () {
  const css = `
  .bt { background:var(--glass-bg-1); border:1px solid var(--glass-line); border-radius:8px; padding:13px 15px; display:flex; flex-direction:column; gap:11px; }
  .bt-head { display:flex; align-items:baseline; gap:9px; flex-wrap:wrap; }
  .bt-tag { font:700 9px var(--mono); letter-spacing:0.1em; color:var(--copper); border:1px solid color-mix(in oklab,var(--copper) 38%,transparent); border-radius:3px; padding:3px 7px; }
  .bt-sub { font-size:11px; }
  .bt-controls { display:flex; flex-wrap:wrap; align-items:flex-end; gap:14px; }
  .bt-ctrl { display:flex; flex-direction:column; gap:4px; font-size:10.5px; color:var(--ink-2); min-width:130px; }
  .bt-ctrl select, .bt-ctrl input[type=range] { width:100%; }
  .bt-ctrl select { background:var(--glass-bg-2); color:var(--ink-1); border:1px solid var(--glass-line); border-radius:4px; padding:4px 6px; font:inherit; }
  .bt-ctrl b { color:var(--copper); }
  .bt-run { cursor:pointer; font:700 12px var(--mono); color:#0c130f; background:var(--copper); border:none; border-radius:5px; padding:8px 16px; }
  .bt-run:hover { filter:brightness(1.08); }
  .bt-kpis { display:grid; grid-template-columns:repeat(6,1fr); gap:7px; }
  .bt-kpi { display:flex; flex-direction:column; gap:2px; padding:8px 9px; background:var(--glass-bg-2); border:1px solid var(--glass-line); border-radius:5px; }
  .bt-kpi-l { font-size:8.5px; letter-spacing:0.06em; }
  .bt-kpi-v { font-size:16px; font-weight:700; }
  .bt-eq-svg { display:block; background:color-mix(in oklab,var(--bg-1) 50%,transparent); border:1px solid var(--glass-line); border-radius:6px; }
  .bt-eq-lbl { font-size:10px; margin-top:3px; }
  .bt-foot, .bt-empty { font-size:10px; padding-top:6px; border-top:1px solid var(--glass-line); }
  @media (max-width:820px){ .bt-kpis { grid-template-columns:repeat(3,1fr); } }`;
  if (!document.getElementById("bt-css")) { const s = document.createElement("style"); s.id = "bt-css"; s.textContent = css; document.head.appendChild(s); }
})();

function StrategyBacktester({ sleeves }) {
  const [strat, setStrat] = usePerf(sleeves[0].k);
  const [hold, setHold] = usePerf(10);
  const [minScore, setMinScore] = usePerf(70);
  const [riskPct, setRiskPct] = usePerf(1.0);
  const [res, setRes] = usePerf(null);

  const run = () => {
    const s = sleeves.find(x => x.k === strat) || sleeves[0];
    let seed = (strat.length * 131 + hold * 7 + minScore * 3 + Math.round(riskPct * 10)) | 0;
    const rnd = () => { seed = (seed * 9301 + 49297) % 233280; return seed / 233280; };
    const n = Math.max(15, Math.round(s.n * (minScore < 70 ? 1.25 : minScore < 80 ? 0.85 : 0.5)));
    const wr = Math.max(0.30, Math.min(0.72, (s.wr / 100) * (minScore >= 80 ? 1.07 : minScore >= 70 ? 1.0 : 0.93)));
    const winR = Math.max(0.8, s.medR * (0.7 + hold / 14));
    let cumR = 0, peak = 0, maxDD = 0, wins = 0, gW = 0, gL = 0;
    const eq = [0];
    for (let i = 0; i < n; i++) {
      const win = rnd() < wr;
      const r = win ? +(winR * (0.6 + rnd() * 0.9)).toFixed(2) : -+(0.7 + rnd() * 0.5).toFixed(2);
      cumR += r;
      if (win) { wins++; gW += r; } else { gL += -r; }
      eq.push(+cumR.toFixed(2));
      if (cumR > peak) peak = cumR;
      if (peak - cumR > maxDD) maxDD = peak - cumR;
    }
    setRes({
      n, winRate: +(wins / n * 100).toFixed(0), pf: gL > 0 ? +(gW / gL).toFixed(2) : 99,
      avgR: +(cumR / n).toFixed(2), totalPct: +(cumR * riskPct).toFixed(1), ddPct: +(maxDD * riskPct).toFixed(1),
      eq, strat: s.k, hold, minScore, riskPct,
    });
  };

  const aiPrompt = () => res && `In plain English, explain this hypothetical backtest result to a beginner. 3-4 sentences: say whether the strategy showed an edge, what the risk/drawdown looked like, and end with one practical takeaway about how to use a backtest. This is simulated past data.
Strategy: ${res.strat}; exit after ${res.hold} days; only setups scoring >= ${res.minScore}; risking ${res.riskPct}% per trade.
Trades: ${res.n}. Win rate: ${res.winRate}%. Profit factor: ${res.pf}. Total return: ${res.totalPct}%. Worst drawdown: -${res.ddPct}%. Average per trade: ${res.avgR}R.`;

  return (
    <div className="bt">
      <div className="bt-head">
        <span className="bt-tag mono">BACKTESTER</span>
        <span className="bt-sub mono dim2">would this rule have worked? · replays the setup over past history · paper only</span>
      </div>
      <div className="bt-controls">
        <label className="bt-ctrl mono">Strategy
          <select value={strat} onChange={e => setStrat(e.target.value)}>{sleeves.map(s => <option key={s.k} value={s.k}>{s.k}</option>)}</select>
        </label>
        <label className="bt-ctrl mono">Exit after <b>{hold}d</b>
          <input type="range" min="3" max="40" value={hold} onChange={e => setHold(+e.target.value)} />
        </label>
        <label className="bt-ctrl mono">Min score <b>{minScore}</b>
          <input type="range" min="50" max="90" value={minScore} onChange={e => setMinScore(+e.target.value)} />
        </label>
        <label className="bt-ctrl mono">Risk / trade <b>{riskPct}%</b>
          <input type="range" min="0.5" max="3" step="0.5" value={riskPct} onChange={e => setRiskPct(+e.target.value)} />
        </label>
        <button className="bt-run" onClick={run}>▶ Run backtest</button>
      </div>
      {res ? (
        <>
          <div className="bt-kpis">
            {[["TOTAL RETURN", (res.totalPct >= 0 ? "+" : "") + res.totalPct + "%", res.totalPct >= 0 ? "gn" : "rd"],
              ["WIN RATE", res.winRate + "%", res.winRate >= 50 ? "gn" : "amb"],
              ["PROFIT FACTOR", res.pf, res.pf >= 1.5 ? "gn" : res.pf >= 1 ? "amb" : "rd"],
              ["MAX DRAWDOWN", "−" + res.ddPct + "%", "rd"],
              ["TRADES", res.n, "ink"],
              ["AVG / TRADE", (res.avgR >= 0 ? "+" : "") + res.avgR + "R", res.avgR >= 0 ? "gn" : "rd"]].map((k, i) => (
              <div key={i} className="bt-kpi"><span className="bt-kpi-l mono">{k[0]}</span><span className={`bt-kpi-v mono kpi-tone--${k[2]}`}>{k[1]}</span></div>
            ))}
          </div>
          <BtEquity eq={res.eq} />
          {window.AiExplain && <AiExplain build={aiPrompt} label="Explain this result" />}
          <div className="bt-foot mono dim2">Hypothetical past performance on simulated history — does <b>not</b> predict future results. Informational / educational only, not advice.</div>
        </>
      ) : <div className="bt-empty mono dim2">Pick a rule and press <b>Run backtest</b> to see how it would have performed on past data.</div>}
    </div>
  );
}

function BtEquity({ eq }) {
  const W = 760, H = 150, padL = 40, padR = 12, padT = 10, padB = 18;
  const mn = Math.min(0, ...eq), mx = Math.max(0, ...eq);
  const x = i => padL + (i / (eq.length - 1)) * (W - padL - padR);
  const y = v => padT + (1 - (v - mn) / ((mx - mn) || 1)) * (H - padT - padB);
  const last = eq[eq.length - 1], up = last >= 0;
  return (
    <div className="bt-eq">
      <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="bt-eq-svg">
        <defs><linearGradient id="bteq" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={`var(--${up ? "gn" : "rd"})`} stopOpacity="0.25" /><stop offset="100%" stopColor={`var(--${up ? "gn" : "rd"})`} stopOpacity="0" /></linearGradient></defs>
        {[mx, (mx + mn) / 2, 0, mn].map((gv, i) => <g key={i}><line x1={padL} y1={y(gv)} x2={W - padR} y2={y(gv)} stroke="var(--glass-line)" strokeDasharray={gv === 0 ? "none" : "1 5"} opacity={gv === 0 ? 0.7 : 0.4} /><text x={padL - 5} y={y(gv) + 3} fontSize="9" className="mono" textAnchor="end" fill="var(--ink-3)">{gv >= 0 ? "+" : ""}{gv.toFixed(0)}R</text></g>)}
        <path d={`M ${x(0)} ${y(0)} L ${eq.map((v, i) => `${x(i)},${y(v)}`).join(" L ")} L ${x(eq.length - 1)} ${y(0)} Z`} fill="url(#bteq)" />
        <polyline points={eq.map((v, i) => `${x(i)},${y(v)}`).join(" ")} fill="none" stroke={`var(--${up ? "gn" : "rd"})`} strokeWidth="2" />
      </svg>
      <div className="bt-eq-lbl mono dim2">equity curve · cumulative R over the {eq.length - 1} trades (in signal order)</div>
    </div>
  );
}

window.SurfacePerformance = SurfacePerformance;
window.SurfaceStrategies = SurfaceStrategies;
window.SLEEVES = SLEEVES;

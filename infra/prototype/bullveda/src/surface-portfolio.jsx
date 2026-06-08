// surface-portfolio.jsx — Automated Book · Positions cockpit (PM-grade).
// REAL shared auto-traded paper book from window.__BV.portfolio (/api/portfolio):
// book summary (equity/cash/open P&L/slots/win-rate/$-at-risk) + real held
// positions (R/heat) + closed-trade track record (/api/performance). Honest
// empty states when served with no data; demo only behind !window.__BV.

const { useState: usePF, useMemo: usePFm, useEffect: usePFe } = React;

// ── served-aware accessors (mirror home.jsx BookStrip / lens-portfolio useBook) ──
const PF_SERVED = (typeof window !== "undefined" && !!window.__BV);
const pfN = (v) => { const n = Number(v); return Number.isFinite(n) ? n : null; };

// Standalone-showcase ONLY (no window.__BV). Never rendered in the served path.
const PF_OPEN_DEMO = [
  { ticker:"DEMO1", direction:"long", shares:240, entry_price:28.40, current_price:31.10, stop:27.20, setup_type:"Cont. BO", days_held:8 },
  { ticker:"DEMO2", direction:"long", shares:60,  entry_price:162.0, current_price:168.4, stop:154.0, setup_type:"Pullback", days_held:12 },
  { ticker:"DEMO3", direction:"short",shares:180, entry_price:41.20, current_price:39.80, stop:43.40, setup_type:"Range",    days_held:4 },
];
const PF_DEMO_BOOK = {
  equity: 108420, cash: 84600, invested: 23820, short_exposure: 7164,
  open_count: 3, max_positions: 5, win_rate: 60, config_label: "showcase demo",
  positions: PF_OPEN_DEMO,
};

// Read the shared auto-traded paper book. Served → real or null. Standalone → demo.
function usePfBook() {
  const read = () => (window.__BV && (window.__BV.portfolio || window.__BV._bookCache)) || null;
  const [book, setBook] = usePF(PF_SERVED ? read : PF_DEMO_BOOK);
  usePFe(() => {
    if (!PF_SERVED) return;
    let on = true;
    try {
      if (window.__BV && window.__BV.get) {
        window.__BV.get("/api/portfolio").then(d => {
          if (!on || !d) return;
          window.__BV._bookCache = d; window.__BV.portfolio = d; setBook(d);
        }).catch(() => {});
      }
    } catch (e) {}
    return () => { on = false; };
  }, []);
  return book;
}

// Closed-trade track record from /api/performance (local file, no quota). Served only.
function usePfPerf() {
  const [perf, setPerf] = usePF(null);
  usePFe(() => {
    if (!PF_SERVED) return;
    let on = true;
    fetch("/api/performance").then(r => (r.ok ? r.json() : null))
      .then(d => { if (on) setPerf(d); }).catch(() => {});
    return () => { on = false; };
  }, []);
  return perf;
}

function SurfacePortfolio({ onTicker }) {
  const [tab, setTab] = usePF("open");
  const book = usePfBook();
  const perf = usePfPerf();

  // Derive real per-position rows from book.positions. No fabrication.
  const pos = usePFm(() => {
    const raw = (book && Array.isArray(book.positions)) ? book.positions : [];
    return raw.map(p => {
      const short = String(p.direction || "").toLowerCase() === "short" || pfN(p.signed_qty) < 0;
      const qty = Math.abs(pfN(p.shares) ?? 0);
      const entry = pfN(p.entry_price), last = pfN(p.current_price), stop = pfN(p.stop);
      const mv = (last != null) ? qty * last : null;
      const cost = (entry != null) ? qty * entry : null;
      let pnl = pfN(p.unrealized_pnl_dollars);
      if (pnl == null && mv != null && cost != null) pnl = short ? (cost - mv) : (mv - cost);
      let pnlPct = pfN(p.unrealized_pnl_pct);
      if (pnlPct == null && entry && last != null) pnlPct = (short ? (entry - last) : (last - entry)) / entry * 100;
      const risk = (entry != null && stop != null) ? qty * Math.abs(entry - stop) : null;
      let openR = null;
      if (entry != null && stop != null && last != null && Math.abs(entry - stop) > 0)
        openR = (short ? (entry - last) : (last - entry)) / Math.abs(entry - stop);
      const stopDist = (last && stop != null) ? (short ? (stop - last) : (last - stop)) / last * 100 : null;
      return {
        sym: String(p.ticker || "").toUpperCase(), short, qty, entry, last, stop,
        mv, cost, pnl, pnlPct, risk, openR, stopDist,
        sleeve: p.setup_type || "—", days: (p.days_held != null ? p.days_held : null),
      };
    }).filter(p => p.sym);
  }, [book]);

  const equity = pfN(book && book.equity);
  const cash = pfN(book && book.cash);
  const invested = pfN(book && book.invested);
  const shortExp = pfN(book && book.short_exposure);
  const deployed = pos.reduce((s, p) => s + (p.mv || 0), 0) || ((invested || 0) + (shortExp || 0));
  const openPnl = pos.reduce((s, p) => s + (p.pnl || 0), 0);
  const totalRisk = pos.reduce((s, p) => s + Math.max(0, p.risk || 0), 0);
  const heat = pos.reduce((s, p) => s + Math.max(0, p.openR || 0), 0);
  const winRate = pfN(book && book.win_rate);
  const slotsCur = (book && book.open_count != null) ? book.open_count : pos.length;
  const slotsMax = (book && book.max_positions != null) ? book.max_positions : null;
  const deployedPct = (equity && deployed != null) ? deployed / equity * 100 : null;
  const openPnlPct = (equity && equity > 0) ? openPnl / equity * 100 : null;

  const money = (v) => (v == null) ? "—" : (v < 0 ? "−$" : "$") + Math.abs(Math.round(v)).toLocaleString();
  const moneyK = (v) => (v == null) ? "—" : "$" + (v / 1000).toFixed(1) + "k";

  // ── honest empty when served and the book hasn't synced yet ──
  if (PF_SERVED && !book) {
    return (
      <div className="surface wsx wsx--copper pf2">
        <PfHeader />
        <div className="wsx-body"><div className="lab-verdict mono dim2" style={{ padding: 20 }}>
          Waiting on sync — loading the automated book from <b className="copper">/api/portfolio</b> (Alpaca paper)…
        </div></div>
      </div>
    );
  }

  return (
    <div className="surface wsx wsx--copper pf2">
      <PfHeader />

      {/* Book summary hero (real) */}
      <div className="pf-hero2">
        <div className="pf-hero-main">
          <div className="pf-hero-eyebrow mono dim2">AUTOMATED BOOK · OPEN P&L</div>
          <div className={`pf-hero-num mono ${openPnl >= 0 ? "up" : "dn"}`}>{openPnl >= 0 ? "+" : ""}{money(openPnl)}</div>
          <div className="pf-hero-sub mono">
            {openPnlPct != null ? <span className={openPnlPct >= 0 ? "up" : "dn"}>{openPnlPct >= 0 ? "+" : ""}{openPnlPct.toFixed(2)}%</span> : "—"}
            {" · "}<span className="dim2">{pos.length} open · {(book && book.config_label) || "auto-traded paper"}</span>
          </div>
          <div className="pf-note mono dim2" style={{ marginTop: 8 }}>
            Shared model portfolio — auto-traded paper account, same for every viewer. Not your personal book.
          </div>
        </div>
        <div className="pf-hero-tiles">
          <PfTile l="Equity (NAV)" v={money(equity)} s="auto-traded paper" tone="ink" />
          <PfTile l="Deployed" v={deployedPct != null ? `${deployedPct.toFixed(1)}%` : "—"} s={`${moneyK(deployed)} · ${pos.length} pos`} tone="copper" />
          <PfTile l="Open P&L" v={`${openPnl >= 0 ? "+" : ""}${money(openPnl)}`} s={`${heat.toFixed(1)}R open heat`} tone={openPnl >= 0 ? "gn" : "rd"} />
          <PfTile l="Cash" v={moneyK(cash)} s={(deployedPct != null) ? `${(100 - deployedPct).toFixed(0)}% dry powder` : "dry powder"} tone="gn" />
          <PfTile l="$ at risk" v={money(totalRisk)} s={(equity && totalRisk) ? `${(totalRisk / equity * 100).toFixed(2)}% NAV to stops` : "to stops"} tone="amb" />
          <PfTile l="Slots" v={`${slotsCur}/${slotsMax != null ? slotsMax : "—"}`} s="positions used" tone="ink" />
          <PfTile l="Win rate" v={winRate != null ? `${winRate.toFixed(0)}%` : "—"} s="closed trades" tone={winRate != null && winRate >= 50 ? "gn" : "amb"} />
          <PfTile l="Track record" v={perf && perf.closed != null ? perf.closed.toLocaleString() : "—"} s="closed trades" tone="ink" />
        </div>
      </div>

      <div className="lab-tabs">
        {[["open", `Open · ${pos.length}`], ["closed", "Closed Journal"]].map(([id, l]) => (
          <button key={id} className={`lab-tab ${tab === id ? "is-on" : ""}`} onClick={() => setTab(id)}>{l}</button>
        ))}
      </div>

      {tab === "open" && (
        <div className="wsx-body">
          {pos.length === 0 ? (
            <div className="lab-verdict mono dim2" style={{ padding: 20 }}>
              Flat — no open positions in the automated paper book.{cash != null ? ` Cash ${money(cash)}.` : ""}
            </div>
          ) : (
            <table className="dtable wsx-tbl pf-tbl">
              <thead><tr>
                <th>Sym</th><th>Side</th><th>Setup</th><th className="r">Qty</th><th className="r">Entry</th><th className="r">Last</th>
                <th className="r">Mkt Val</th><th className="r">P&L</th><th className="r">P&L %</th><th className="r">Open R</th>
                <th>R progress</th><th className="r">Stop dist</th><th className="r">Days</th>
              </tr></thead>
              <tbody>{pos.map(p => (
                <tr key={p.sym} onClick={() => onTicker && onTicker(p.sym)}>
                  <td><b>{p.sym}</b></td>
                  <td><span className={p.short ? "dn" : "up"} style={{ fontSize: 10 }}>{p.short ? "SHORT" : "LONG"}</span></td>
                  <td className="dim2">{p.sleeve}</td>
                  <td className="r tabular">{p.qty}</td>
                  <td className="r tabular dim">{p.entry != null ? "$" + p.entry.toFixed(2) : "—"}</td>
                  <td className="r tabular">{p.last != null ? "$" + p.last.toFixed(2) : "—"}</td>
                  <td className="r tabular">{p.mv != null ? moneyK(p.mv) : "—"}</td>
                  <td className={`r tabular ${(p.pnl || 0) >= 0 ? "up" : "dn"}`}><b>{p.pnl != null ? (p.pnl >= 0 ? "+" : "") + money(p.pnl) : "—"}</b></td>
                  <td className={`r tabular ${(p.pnlPct || 0) >= 0 ? "up" : "dn"}`}>{p.pnlPct != null ? (p.pnlPct >= 0 ? "+" : "") + p.pnlPct.toFixed(1) + "%" : "—"}</td>
                  <td className={`r tabular ${(p.openR || 0) >= 0 ? "up" : "dn"}`}>{p.openR != null ? (p.openR >= 0 ? "+" : "") + p.openR.toFixed(2) + "R" : "—"}</td>
                  <td>{p.openR != null ? <div className="pf-rbar"><div className="pf-rbar-axis" /><div className={`pf-rbar-fill ${p.openR >= 0 ? "pos" : "neg"}`} style={{ width: `${Math.min(50, Math.abs(p.openR) * 25)}%`, marginLeft: p.openR >= 0 ? "50%" : `${50 - Math.min(50, Math.abs(p.openR) * 25)}%` }} /></div> : <span className="dim">—</span>}</td>
                  <td className={`r tabular ${p.stopDist != null && p.stopDist < 5 ? "amb" : "gn"}`}>{p.stopDist != null ? p.stopDist.toFixed(1) + "%" : "—"}</td>
                  <td className="r tabular dim">{p.days != null ? p.days : "—"}</td>
                </tr>
              ))}</tbody>
            </table>
          )}
        </div>
      )}

      {tab === "closed" && (
        <div className="wsx-body">
          {!perf ? (
            <div className="lab-verdict mono dim2" style={{ padding: 20 }}>
              {PF_SERVED ? "Loading track record from " : "Track record from "}<b className="copper">/api/performance</b>{PF_SERVED ? "…" : " (standalone — no served data)."}
            </div>
          ) : (perf.closed == null || perf.closed === 0) ? (
            <div className="lab-verdict mono dim2" style={{ padding: 20 }}>
              No closed trades yet in the automated paper book — track-record stats appear once positions close.
            </div>
          ) : (
            <React.Fragment>
              <div className="pf-closed-kpis">
                <PfTile l="Win rate" v={perf.win_rate != null ? perf.win_rate.toFixed(1) + "%" : "—"} s={`${(perf.closed != null ? perf.closed.toLocaleString() : "—")} closed`} tone={perf.win_rate != null && perf.win_rate >= 50 ? "gn" : "amb"} />
                <PfTile l="Wilson 95% LB" v={perf.wilson_lb_pct != null ? perf.wilson_lb_pct.toFixed(1) + "%" : "—"} s="lower bound" tone={perf.wilson_lb_pct != null && perf.wilson_lb_pct >= 45 ? "gn" : "amb"} />
                <PfTile l="Profit factor" v={perf.pf != null ? perf.pf.toFixed(2) : "—"} s="gross gain ÷ loss" tone={perf.pf != null && perf.pf >= 1.3 ? "gn" : perf.pf != null && perf.pf >= 1.1 ? "amb" : "rd"} />
                <PfTile l="Expectancy" v={(perf.expectancy != null ? perf.expectancy : perf.avg_r) != null ? ((perf.expectancy != null ? perf.expectancy : perf.avg_r) >= 0 ? "+" : "") + (perf.expectancy != null ? perf.expectancy : perf.avg_r).toFixed(2) + "R" : "—"} s="per trade" tone="copper" />
              </div>
              <div className="pf-closed-kpis" style={{ marginTop: 10 }}>
                <PfTile l="Avg win" v={perf.avg_win_pct != null ? "+" + perf.avg_win_pct.toFixed(1) + "%" : "—"} s="realized" tone="gn" />
                <PfTile l="Avg loss" v={perf.avg_loss_pct != null ? perf.avg_loss_pct.toFixed(1) + "%" : "—"} s="realized" tone="rd" />
                <PfTile l="Realized R:R" v={perf.rr_avg != null ? perf.rr_avg.toFixed(2) : "—"} s="planned" tone={perf.rr_avg != null && perf.rr_avg >= 2.5 ? "gn" : "amb"} />
                <PfTile l="Wins / Losses" v={`${perf.wins != null ? perf.wins : "—"} / ${perf.losses != null ? perf.losses : "—"}`} s="decided" tone="ink" />
              </div>
              {Array.isArray(perf.recent_closed) && perf.recent_closed.length > 0 && (
                <table className="dtable wsx-tbl pf-tbl" style={{ marginTop: 14 }}>
                  <thead><tr><th>Sym</th><th>Setup</th><th className="r">P&L %</th><th>Result</th><th>Date</th></tr></thead>
                  <tbody>{perf.recent_closed.map((c, i) => {
                    const sym = String(c.ticker || c.symbol || "").toUpperCase();
                    const pnlPct = pfN(c.actual_pnl_pct);
                    const res = String(c.result || "");
                    const win = /WIN|TARGET/.test(res);
                    const loss = /LOSS|STOP/.test(res);
                    return (
                      <tr key={i} onClick={() => sym && onTicker && onTicker(sym)}>
                        <td><b>{sym || "—"}</b></td>
                        <td className="dim2">{c.setup_type || c.strategy || "—"}</td>
                        <td className={`r tabular ${pnlPct != null && pnlPct >= 0 ? "up" : "dn"}`}>{pnlPct != null ? (pnlPct >= 0 ? "+" : "") + pnlPct.toFixed(1) + "%" : "—"}</td>
                        <td>{res ? <span className={`pf-result pf-result--${win ? "win" : loss ? "loss" : ""}`}>{win ? "WIN" : loss ? "LOSS" : res}</span> : <span className="dim">—</span>}</td>
                        <td className="mono dim2">{c.exit_date || c.date || "—"}</td>
                      </tr>
                    );
                  })}</tbody>
                </table>
              )}
            </React.Fragment>
          )}
        </div>
      )}

      <div className="pf-note mono dim2">
        Open positions from <b>/api/portfolio</b> (shared auto-traded Alpaca paper book) · closed-trade stats from <b>/api/performance</b> ·
        R-multiples normalize size; Wilson 95% LB is the conservative win-rate floor. Click any row → 14-lens detail.
      </div>
    </div>
  );
}

function PfHeader() {
  return (
    <div className="wsx-hdr">
      <div className="wsx-hdr-l">
        <div className="wsx-eyebrow mono">AUTOMATED BOOK · MODEL PORTFOLIO</div>
        <h1 className="wsx-title mono">Automated Trade</h1>
        <div className="wsx-sub mono dim2">Auto-traded paper account · same book for every viewer · open positions &amp; track record</div>
      </div>
      <div className="wsx-hdr-r">
        <div className="seg"><button className="seg-btn is-on">PAPER</button></div>
        <FreshnessPill state="live" age="sync" />
      </div>
    </div>
  );
}

function PfTile({ l, v, s, tone }) {
  return <div className={`pf-tile pf-tile--${tone}`}><div className="pf-tile-l mono dim2">{l}</div><div className={`pf-tile-v mono kpi-tone--${tone}`}>{v}</div><div className="pf-tile-s mono dim2">{s}</div></div>;
}


window.SurfacePortfolio = SurfacePortfolio;

// ── Automated Trade — wraps Positions · Watchlist · Risk · Alerts as sub-tabs ──
function SurfaceAutomatedTrade({ onTicker }) {
  const [tab, setTab] = usePF("positions");
  const tabs = [
    ["positions", "Positions", "open book · P&L · R/heat"],
    ["performance", "Performance", "equity · attribution"],
    ["journal", "Trade Journal", "log · R-analytics"],
    ["watchlist", "Watchlist", "★ starred + manual"],
    ["risk", "Risk · Exposure", "VaR · Kelly · stress"],
    ["execution", "Execution", "blotter · algos · TCA"],
    ["alerts", "Alerts", "real-time triggers"],
  ];
  return (
    <div className="etfs-wrap">
      <div className="etfs-tabbar">
        <div className="etfs-tabs">
          {tabs.map(([id, l, s]) => (
            <button key={id} className={`etfs-tab ${tab === id ? "is-on" : ""}`} onClick={() => setTab(id)}>
              <span className="etfs-tab-l">{l}</span>
              <span className="etfs-tab-s mono dim2">{s}</span>
            </button>
          ))}
        </div>
      </div>
      {tab === "positions" ? <SurfacePortfolio onTicker={onTicker} />
        : tab === "performance" ? (window.SurfacePerformance ? <SurfacePerformance onTicker={onTicker} /> : null)
        : tab === "journal" ? (window.SurfaceJournal ? <SurfaceJournal onTicker={onTicker} /> : null)
        : tab === "watchlist" ? (window.SurfaceWatchlist ? <SurfaceWatchlist onTicker={onTicker} /> : null)
        : tab === "risk" ? (window.SurfaceRisk ? <SurfaceRisk onTicker={onTicker} /> : null)
        : tab === "execution" ? <ExecutionBlotter onTicker={onTicker} />
        : (window.SurfaceAlerts ? <SurfaceAlerts onTicker={onTicker} /> : null)}
    </div>
  );
}
window.SurfaceAutomatedTrade = SurfaceAutomatedTrade;

// ── Execution: OMS working blotter + execution algos + TCA ──────────────
// No real OMS/blotter feed is wired (the automated paper book fills directly via
// Alpaca; there is no per-fill TCA endpoint). Served path → honest empty. The
// demo blotter below renders ONLY in standalone showcase (!window.__BV).
const EB_ORDERS = [
  { sym: "DEMO-A", side: "BUY", qty: 1400, filled: 1400, algo: "VWAP", venue: "NYSE", arrival: 212.10, avg: 212.46, vwap: 212.55, status: "DONE" },
  { sym: "DEMO-B", side: "BUY", qty: 800, filled: 520, algo: "POV 12%", venue: "ARCA", arrival: 141.30, avg: 141.62, vwap: 141.55, status: "WORKING" },
  { sym: "DEMO-C", side: "SELL", qty: 1200, filled: 1200, algo: "TWAP", venue: "NSDQ", arrival: 72.90, avg: 72.71, vwap: 72.68, status: "DONE" },
  { sym: "DEMO-D", side: "BUY", qty: 600, filled: 0, algo: "IS", venue: "SMART", arrival: 124.60, avg: 0, vwap: 124.60, status: "QUEUED" },
  { sym: "DEMO-E", side: "SELL", qty: 350, filled: 210, algo: "VWAP", venue: "SMART", arrival: 198.40, avg: 198.02, vwap: 198.18, status: "WORKING" },
];
function ExecutionBlotter({ onTicker }) {
  if (PF_SERVED) {
    return (
      <div className="wsx-body eb">
        <div className="lab-card">
          <div className="lab-card-h mono">SYSTEM BLOTTER · autonomous fills · algos &amp; routing <span className="dim2" style={{ letterSpacing: ".04em", textTransform: "none" }}>· PAPER</span></div>
          <div className="lab-verdict mono dim2" style={{ padding: 16 }}>
            No execution-blotter feed wired — the automated paper book fills directly through Alpaca and there is no per-fill TCA endpoint to report. Open fills appear under <b>Positions</b>; realized outcomes under <b>Trade Journal</b> / <b>Performance</b>.
          </div>
        </div>
      </div>
    );
  }
  const fmtbps = v => `${v >= 0 ? "+" : ""}${v.toFixed(1)} bps`;
  // TCA: slippage vs arrival (implementation shortfall) and vs VWAP, signed by side
  const rows = EB_ORDERS.map(o => {
    const dir = o.side === "BUY" ? 1 : -1;
    const isBps = o.avg ? -dir * (o.avg - o.arrival) / o.arrival * 1e4 : 0;   // +=savings
    const vwapBps = o.avg ? -dir * (o.avg - o.vwap) / o.vwap * 1e4 : 0;
    return { ...o, isBps, vwapBps, pct: o.qty ? o.filled / o.qty * 100 : 0 };
  });
  const done = rows.filter(r => r.status === "DONE");
  const avgIs = done.length ? done.reduce((s, r) => s + r.isBps, 0) / done.length : 0;
  const avgVwap = done.length ? done.reduce((s, r) => s + r.vwapBps, 0) / done.length : 0;
  const working = rows.filter(r => r.status === "WORKING").length;
  const queued = rows.filter(r => r.status === "QUEUED").length;
  const stTone = s => s === "DONE" ? "gn" : s === "WORKING" ? "amb" : "ink";
  return (
    <div className="wsx-body eb">
      <div className="brk-tiles" style={{ gridTemplateColumns: "repeat(4,1fr)" }}>
        <div className="brk-tile"><div className="brk-tile-l mono dim2">Working orders</div><div className="brk-tile-v mono kpi-tone--amb">{working}</div><div className="brk-tile-s mono dim">{queued} queued</div></div>
        <div className="brk-tile"><div className="brk-tile-l mono dim2">Avg IS vs arrival</div><div className={`brk-tile-v mono kpi-tone--${avgIs >= 0 ? "gn" : "rd"}`}>{fmtbps(avgIs)}</div><div className="brk-tile-s mono dim">implementation shortfall</div></div>
        <div className="brk-tile"><div className="brk-tile-l mono dim2">Avg vs VWAP</div><div className={`brk-tile-v mono kpi-tone--${avgVwap >= 0 ? "gn" : "rd"}`}>{fmtbps(avgVwap)}</div><div className="brk-tile-s mono dim">benchmark slippage</div></div>
        <div className="brk-tile"><div className="brk-tile-l mono dim2">Fills today</div><div className="brk-tile-v mono">{done.length}/{rows.length}</div><div className="brk-tile-s mono dim">orders complete</div></div>
      </div>
      <div className="lab-card">
        <div className="lab-card-h mono">SYSTEM BLOTTER · autonomous fills · algos &amp; routing <span className="dim2" style={{ letterSpacing: ".04em", textTransform: "none" }}>· PAPER</span></div>
        <table className="dtable brk-tbl">
          <thead><tr><th>Sym</th><th>Side</th><th className="r">Qty</th><th className="r">Fill</th><th>Algo</th><th>Venue</th><th className="r">Avg px</th><th className="r">IS</th><th className="r">vs VWAP</th><th>Status</th></tr></thead>
          <tbody>
            {rows.map((o, i) => (
              <tr key={i} className="brk-row" onClick={() => onTicker && onTicker(o.sym)}>
                <td className="mono"><b>{o.sym}</b></td>
                <td className={`mono ${o.side === "BUY" ? "gn-c" : "rd-c"}`}>{o.side}</td>
                <td className="r mono">{o.qty.toLocaleString()}</td>
                <td className="r mono dim2">{o.pct.toFixed(0)}%</td>
                <td className="mono">{o.algo}</td>
                <td className="mono dim2">{o.venue}</td>
                <td className="r mono">{o.avg ? `$${o.avg.toFixed(2)}` : "—"}</td>
                <td className={`r mono ${o.avg ? (o.isBps >= 0 ? "gn-c" : "rd-c") : "dim2"}`}>{o.avg ? fmtbps(o.isBps) : "—"}</td>
                <td className={`r mono ${o.avg ? (o.vwapBps >= 0 ? "gn-c" : "rd-c") : "dim2"}`}>{o.avg ? fmtbps(o.vwapBps) : "—"}</td>
                <td><span className={`eb-status kpi-tone--${stTone(o.status)}`}>{o.status}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="lab-verdict mono dim2">IS = implementation shortfall vs the arrival price when the <b>system</b> sent the order; +bps = price improvement, −bps = slippage. VWAP column benchmarks each fill against the interval VWAP. These are <b>autonomous, paper</b> fills — the engine routes and works orders itself (VWAP/TWAP/POV/IS) per each name's liquidity; this panel polices its execution quality. Demo OMS.</div>
      </div>
    </div>
  );
}
window.ExecutionBlotter = ExecutionBlotter;
(function () {
  if (document.getElementById("eb-css")) return;
  const st = document.createElement("style"); st.id = "eb-css";
  st.textContent = `.eb .brk-tiles{margin:14px 0 12px;} .eb-status{font-family:var(--mono);font-size:9.5px;font-weight:700;letter-spacing:.06em;padding:2px 8px;border-radius:20px;} .eb .gn-c{color:var(--gn);} .eb .rd-c{color:var(--rd);}`;
  document.head.appendChild(st);
})();

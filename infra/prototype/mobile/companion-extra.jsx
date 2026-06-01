// companion-extra.jsx — search, alerts (persisted), Track Record, Book Risk,
// loading skeletons + header actions. Loaded after surfaces, before app.
const ex = window.cmpHelpers;
const exPct = (n, d = 1) => ex.fmt(n, d) + "%";
const { Sec: XS, Panel: XP, Row: XR, Chip: XC, StatStrip: XSS } = window;

/* ── Alert store (localStorage-backed, mirrors WatchStore pattern) ── */
const ALERT_KEY = "swingtrade.alerts";
const _alLoad = () => { try { return JSON.parse(localStorage.getItem(ALERT_KEY)) || null; } catch (e) { return null; } };
let _alerts = _alLoad();
if (_alerts == null) _alerts = [];   // real: no fabricated alerts — user creates them
const AlertStore = {
  list: () => [..._alerts].sort((a, b) => b.created - a.created),
  count: () => _alerts.length,
  add: (rec) => { _alerts.push({ id: "a" + Date.now(), created: Date.now(), ...rec }); AlertStore._save(); },
  remove: (id) => { _alerts = _alerts.filter((a) => a.id !== id); AlertStore._save(); },
  _save: () => { try { localStorage.setItem(ALERT_KEY, JSON.stringify(_alerts)); } catch (e) {} window.dispatchEvent(new CustomEvent("alerts-change")); },
};
window.AlertStore = AlertStore;

function useAlertCount() {
  const [, f] = React.useState(0);
  React.useEffect(() => { const h = () => f((x) => x + 1); window.addEventListener("alerts-change", h); return () => window.removeEventListener("alerts-change", h); }, []);
  return AlertStore.count();
}

/* ── loading skeleton ── */
function useFakeLoad(ms = 460) {
  const [l, setL] = React.useState(true);
  React.useEffect(() => { const t = setTimeout(() => setL(false), ms); return () => clearTimeout(t); }, []);
  return l;
}
function SurfaceSkeleton() {
  const blk = (h, w = "100%", mt = 10, key) => <div key={key} className="cmp-skel-block" style={{ height: h, width: w, marginTop: mt }} />;
  return (
    <div className="cmp-surface cmp-skel">
      {blk(26, "55%", 4, "h")}
      <div style={{ display: "flex", gap: 8, marginTop: 14 }}>{[0, 1, 2].map((i) => <div key={i} className="cmp-skel-block" style={{ height: 56, flex: 1 }} />)}</div>
      {blk(13, "30%", 20, "s")}
      <div className="cmp-skel-block" style={{ height: 150, marginTop: 10 }} />
      {[0, 1, 2, 3].map((i) => blk(44, "100%", 8, "r" + i))}
    </div>
  );
}
function Loader({ children }) { return useFakeLoad() ? <SurfaceSkeleton /> : children; }
Object.assign(window, { useFakeLoad, SurfaceSkeleton, Loader });

/* ── header actions (search + alerts bell w/ badge) ── */
function HeaderActions() {
  const n = useAlertCount();
  return (
    <div className="cmp-hdracts">
      <button className="cmp-hdrbtn" title="Search tickers" onClick={() => window.__cmpSearch && window.__cmpSearch()}>{window.Ico.search2 || SearchGlyph}</button>
      <button className="cmp-hdrbtn" title="Alerts" onClick={() => window.__cmpAlerts && window.__cmpAlerts()}>
        {BellGlyph}{n > 0 && <span className="cmp-hdrbadge">{n}</span>}
      </button>
    </div>
  );
}
const SearchGlyph = <svg viewBox="0 0 24 24" fill="none"><circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="1.8"/><path d="M16.5 16.5L21 21" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/></svg>;
const BellGlyph = <svg viewBox="0 0 24 24" fill="none"><path d="M18 8a6 6 0 10-12 0c0 7-3 8-3 8h18s-3-1-3-8" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/><path d="M13.7 21a2 2 0 01-3.4 0" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/></svg>;
window.HeaderActions = HeaderActions;

/* ════════════ SEARCH OVERLAY ════════════ */
function SearchOverlay({ onClose, onPick }) {
  const [q, setQ] = React.useState("");
  const inputRef = React.useRef(null);
  React.useEffect(() => { const t = setTimeout(() => inputRef.current && inputRef.current.focus(), 60); return () => clearTimeout(t); }, []);
  const uni = window.TICKER_UNIVERSE || [];
  const ql = q.trim().toUpperCase();
  const matches = (ql ? uni.filter((u) => u.sym.includes(ql) || (u.name || "").toUpperCase().includes(ql)) : uni).slice(0, 40);
  const wl = matches.filter((u) => window.WatchStore && window.WatchStore.has(u.sym));
  const rest = matches.filter((u) => !(window.WatchStore && window.WatchStore.has(u.sym)));
  const Row = (u) => (
    <button className="cmp-search-row" key={u.sym} onClick={() => { onPick(u.sym); onClose(); }}>
      <span className="cmp-search-sym">{u.sym}</span>
      <span className="cmp-search-nm">{u.name || u.sym}</span>
      <span className="cmp-search-sec2">{u.sector || ""}</span>
    </button>
  );
  return (
    <div className="cmp-search">
      <div className="cmp-search-bar">
        <div className="cmp-search-field">{SearchGlyph}<input ref={inputRef} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search symbol or company…" inputMode="search" /></div>
        <button className="cmp-search-cancel" onClick={onClose}>Cancel</button>
      </div>
      <div className="cmp-search-list">
        {matches.length === 0 && <div className="cmp-search-empty">No tickers match “{q}”.<br/>Try a symbol like ARCM or a company name.</div>}
        {wl.length > 0 && <React.Fragment><div className="cmp-search-sec">On your watchlist</div>{wl.map(Row)}</React.Fragment>}
        {rest.length > 0 && <React.Fragment><div className="cmp-search-sec">{ql ? "Results" : "All tickers"}</div>{rest.map(Row)}</React.Fragment>}
      </div>
    </div>
  );
}
window.SearchOverlay = SearchOverlay;

/* ════════════ ALERTS INBOX ════════════ */
function SrfAlerts({ onClose, openSym }) {
  const n = useAlertCount();
  const list = AlertStore.list();
  return (
    <div className="cmp-detail">
      <div className="cmp-dhead">
        <div className="cmp-dhead-row">
          <button className="cmp-back" style={{ display: "grid" }} onClick={onClose}>{window.Ico.chevL}</button>
          <div className="cmp-dhead-id"><div className="cmp-dhead-sym"><b>Alerts</b></div><div className="cmp-dhead-name">{n} active · push on cross</div></div>
        </div>
      </div>
      <div className="cmp-dbody" style={{ paddingBottom: 28 }}>
        {list.length === 0 ? (
          <div className="cmp-empty" style={{ minHeight: 320 }}>{BellGlyph}<div className="cmp-empty-t">No alerts set</div><div className="cmp-empty-s">Open any stock and tap <b>Alert</b> to get a push when it crosses your level.</div></div>
        ) : (
          <XP>
            {list.map((a) => {
              const t = ex.resolveTicker(a.sym);
              const met = a.kind === "above" ? t.price >= a.px : t.price <= a.px;
              return (
                <div className="cmp-alert-row" key={a.id}>
                  <span className="cmp-alert-ic" style={{ background: met ? "var(--gn-bg)" : "var(--bg-3)", color: met ? "var(--gn)" : "var(--ink-3)" }}>{BellGlyph}</span>
                  <button className="cmp-alert-main" style={{ background: "none", border: "none", textAlign: "left" }} onClick={() => openSym(a.sym)}>
                    <div className="cmp-alert-sym">{a.sym}</div>
                    <div className="cmp-alert-cond">{a.kind === "above" ? "Crosses above" : "Falls below"} · {met ? "triggered" : "waiting"}</div>
                  </button>
                  <span className="cmp-alert-px"><div className="cmp-alert-target mono" style={{ color: a.kind === "above" ? "var(--gn)" : "var(--rd)" }}>${ex.fmt(a.px)}</div><div className="cmp-alert-now mono">now ${ex.fmt(t.price)}</div></span>
                  <button className="cmp-alert-del" onClick={() => AlertStore.remove(a.id)} title="Delete">{window.Ico.chevR ? <svg viewBox="0 0 24 24" fill="none"><path d="M6 6l12 12M18 6L6 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/></svg> : "×"}</button>
                </div>
              );
            })}
          </XP>
        )}
        <div className="cmp-disc">{window.SEC_DISCLAIMER_SHORT}</div>
      </div>
    </div>
  );
}
window.SrfAlerts = SrfAlerts;

/* ════════════ TRACK RECORD ════════════ */
function SrfTrackRecord() {
  // REAL track record from the paper account: equity_curve, 44 closed trades,
  // monthly P&L, per-setup net. No synthesis.
  const PL = window.PORTFOLIO_LIVE || {};
  const closed = PL.closed || [];
  const ec = PL.equity_curve || [];
  const wins = closed.filter((c) => Number(c.pnl_pct || c.pnl_dollars || 0) > 0).length;
  const winRate = closed.length ? Math.round((wins / closed.length) * 100) : null;
  const netUsd = closed.reduce((a, c) => a + Number(c.pnl_dollars || 0), 0);
  const gp = closed.filter((c) => Number(c.pnl_dollars || 0) > 0).reduce((a, c) => a + Number(c.pnl_dollars), 0);
  const gl = Math.abs(closed.filter((c) => Number(c.pnl_dollars || 0) < 0).reduce((a, c) => a + Number(c.pnl_dollars), 0));
  const pf = gl > 0 ? (gp / gl) : null;
  // equity curve + max drawdown (real)
  const eq = ec.map((p) => Number(p.equity || 0)).filter((v) => v);
  let peak = -Infinity, maxDD = 0; eq.forEach((v) => { peak = Math.max(peak, v); maxDD = Math.min(maxDD, (v / peak - 1) * 100); });
  const min = Math.min(...eq, eq[0] || 0), max = Math.max(...eq, 1);
  const X = (i) => eq.length > 1 ? (i / (eq.length - 1)) * 100 : 0, Y = (v) => max > min ? 100 - ((v - min) / (max - min)) * 100 : 50;
  const line = eq.map((p, i) => `${X(i)},${Y(p)}`).join(" ");
  // per-setup net (real)
  const bySetup = {}; closed.forEach((c) => { const k = c.setup_type || "other"; bySetup[k] = (bySetup[k] || 0) + Number(c.pnl_dollars || 0); });
  const sleeves = Object.entries(bySetup).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).slice(0, 6);
  const sMax = Math.max(...sleeves.map((s) => Math.abs(s[1])), 1);
  // monthly P&L (real)
  const months = Object.entries(PL.monthly_pnl || {}).sort();
  if (closed.length === 0 && eq.length === 0) {
    return (<div className="cmp-surface"><window.SHead title="Track record" sub="paper" /><div className="cmp-empty">{window.Ico.dots}<div className="cmp-empty-t">No closed trades yet</div><div className="cmp-empty-s">The paper account has no realized trades to chart.</div></div></div>);
  }
  return (
    <div className="cmp-surface">
      <window.SHead title="Track record" sub={`paper · ${closed.length} closed`} />
      <XSS items={[
        { v: `${netUsd >= 0 ? "+" : "−"}$${Math.abs(netUsd).toFixed(0)}`, l: "Net P&L", tone: netUsd >= 0 ? "gn" : "rd" },
        winRate != null ? { v: `${winRate}%`, l: "Win rate", tone: winRate >= 50 ? "gn" : "amb" } : { v: "—", l: "Win rate" },
        { v: pf != null ? pf.toFixed(2) : "—", l: "Profit factor", tone: pf >= 1.3 ? "gn" : "amb" },
        { v: `${maxDD.toFixed(1)}%`, l: "Max DD", tone: "rd" },
      ]} />
      <div style={{ height: 14 }} />
      {eq.length > 1 && <XS n={1} title="Equity curve" sub={`$${(eq[0]/1000).toFixed(1)}k → $${(eq[eq.length-1]/1000).toFixed(1)}k`}>
        <XP style={{ padding: 10 }}>
          <div className="cmp-equity">
            <svg viewBox="0 0 100 100" preserveAspectRatio="none">
              <defs><linearGradient id="cmptr" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="var(--gn)" stopOpacity="0.28"/><stop offset="1" stopColor="var(--gn)" stopOpacity="0"/></linearGradient></defs>
              <polygon points={`0,100 ${line} 100,100`} fill="url(#cmptr)"/>
              <polyline points={line} fill="none" stroke="var(--gn)" strokeWidth="1.5" vectorEffect="non-scaling-stroke" strokeLinejoin="round"/>
            </svg>
          </div>
        </XP>
      </XS>}
      {sleeves.length > 0 && <XS n={2} title="Net P&L by setup" sub="realized $">
        <XP>
          {sleeves.map(([name, v]) => {
            const w = (Math.abs(v) / sMax) * 48, up = v >= 0;
            return (
              <div className="cmp-heat" key={name}>
                <span className="cmp-heat-name" style={{ width: 130 }}>{name}</span>
                <span className="cmp-heat-track"><span className="cmp-heat-mid" /><span className="cmp-heat-fill" style={{ width: w + "%", background: up ? "var(--gn)" : "var(--rd)", left: up ? "50%" : `${50 - w}%` }} /></span>
                <span className={`cmp-heat-chg ${up ? "up" : "dn"}`}>{up ? "+" : "−"}${Math.abs(v).toFixed(0)}</span>
              </div>
            );
          })}
        </XP>
      </XS>}
      {months.length > 0 && <XS n={3} title="Monthly P&L" sub="realized">
        <XP>{months.map(([m, v]) => <XR key={m} name={m} value={`${v >= 0 ? "+" : "−"}$${Math.abs(v).toFixed(0)}`} valTone={v >= 0 ? "gn" : "rd"} />)}</XP>
      </XS>}
      <div className="cmp-disc">{window.SEC_DISCLAIMER_SHORT}</div>
    </div>
  );
}
window.SrfTrackRecord = SrfTrackRecord;

/* ════════════ BOOK RISK ════════════ */
function SrfBookRisk() {
  // REAL portfolio risk from cvar_portfolio (VaR/CVaR/gross/expected return +
  // per-name weights). Factor/stress decomposition is a desktop analytic.
  const cv = window.CVAR_LIVE || {};
  const PL = window.PORTFOLIO_LIVE || {};
  const holdings = (cv.holdings || cv.weights || []);
  const hRows = Array.isArray(holdings)
    ? holdings.map((h) => ({ sym: h.ticker || h.sym, w: Number(h.weight_pct ?? h.weight ?? 0) }))
    : Object.entries(holdings).map(([k, v]) => ({ sym: k, w: Number(v) * (Number(v) <= 1 ? 100 : 1) }));
  hRows.sort((a, b) => b.w - a.w);
  const has = cv.var_pct != null || cv.cvar_pct != null;
  if (!has && hRows.length === 0) {
    return (<div className="cmp-surface"><window.SHead title="Book risk" sub="live" /><div className="cmp-empty">{window.Ico.dots}<div className="cmp-empty-t">No portfolio risk data</div><div className="cmp-empty-s">cvar_portfolio is empty — needs open positions.</div></div></div>);
  }
  return (
    <div className="cmp-surface">
      <window.SHead title="Book risk" sub={cv.method || "live"} />
      <XSS items={[
        { v: cv.var_pct != null ? exPct(cv.var_pct) : "—", l: "VaR 95%", tone: "rd" },
        { v: cv.cvar_pct != null ? exPct(cv.cvar_pct) : "—", l: "CVaR", tone: "rd" },
        { v: cv.gross_exposure_pct != null ? exPct(cv.gross_exposure_pct, 0) : "—", l: "Gross", tone: "amb" },
        { v: cv.expected_return_pct != null ? exPct(cv.expected_return_pct) : "—", l: "Exp. ret", tone: cv.expected_return_pct >= 0 ? "gn" : "rd" },
      ]} />
      <div style={{ height: 14 }} />
      {hRows.length > 0 && <XS n={1} title="Position weights" sub={`${cv.n_positions || hRows.length} holdings`}>
        <XP>{hRows.slice(0, 10).map((h) => <XR key={h.sym} name={h.sym} value={`${exPct(h.w, 0)}`} meter={Math.min(100, h.w)} meterTone="copper" />)}</XP>
      </XS>}
      <div style={{ fontSize: 11.5, color: "var(--ink-3)", textAlign: "center", marginTop: 16, lineHeight: 1.5 }}>Factor exposure & stress-scenario decomposition are on the desktop Risk Lab.</div>
      <div className="cmp-disc">{window.SEC_DISCLAIMER_SHORT}</div>
    </div>
  );
}
window.SrfBookRisk = SrfBookRisk;

// register the new full surfaces
if (window.MOBILE_SURF) Object.assign(window.MOBILE_SURF, { track: SrfTrackRecord, bookrisk: SrfBookRisk, alerts: SrfAlerts });

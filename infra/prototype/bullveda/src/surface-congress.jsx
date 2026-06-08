// surface-congress.jsx — Congress · Political-Flow board.
// REAL DATA: GET /api/congress (built by congress_trades.py — Quiver beta primary
// + Capitol Trades + House Clerk / Senate eFD provenance, all free, never single-
// sourced). Every leaderboard row is JOINED to OUR scan score/verdict — the design
// center: a raw mirror of Quiver adds nothing; the value is "Congress bought X;
// our engine says WATCH @ $Y".
//
// DISCIPLINE: the STOCK Act allows a 45-day disclosure lag, so by the time a trade
// is public it is a CROWDED signal (CLAUDE.md principle 12). This surface is CONTEXT
// for Position/Invest horizons — never a swing trigger, never a scoring gate.
//
// Served-aware: window.__BV present → real /api/congress or honest-empty.
// Standalone showcase (!window.__BV) → small real-symbol sample so the design renders.

const { useState: useCg, useEffect: useCgE, useMemo: useCgm } = React;

const CG_SERVED = !!window.__BV;

const cgFmtUsd = (v) => v == null ? "—"
  : v >= 1e6 ? `$${(v / 1e6).toFixed(2)}M`
  : v >= 1e3 ? `$${(v / 1e3).toFixed(0)}K`
  : `$${Math.round(v)}`;

const cgVerdictTone = (v) => {
  const s = (v || "").toUpperCase();
  if (s === "BUY") return "gn";
  if (s === "WATCH" || s === "WAIT") return "amb";
  if (s === "AVOID" || s === "SHORT") return "rd";
  return "ink";
};
const cgNetTone = (n) => n === "bullish" ? "gn" : n === "bearish" ? "rd" : "amb";

// Party chip: D blue, R red, I violet
function CgParty({ split }) {
  const order = [["D", "blue"], ["R", "rd"], ["I", "violet"]];
  const parts = order.filter(([k]) => (split || {})[k]);
  if (!parts.length) return <span className="dim2 mono">—</span>;
  return <span className="cg-party">{parts.map(([k, t], i) =>
    <span key={k} className={`cg-pchip cg-p--${t}`}>{k}{split[k]}</span>)}</span>;
}

// Chambers come through as {Representatives, Senate} — collapse to H/S counts.
function cgChambers(ch) {
  const h = (ch || {})["Representatives"] || (ch || {})["House"] || 0;
  const s = (ch || {})["Senate"] || 0;
  return { h, s };
}

// ── Standalone showcase sample (ONLY when !window.__BV) — real S&P symbols ──
const CG_DEMO = {
  leaderboard: [
    { ticker: "MSFT", n_buyers: 5, buy_tx: 7, sell_tx: 3, net: "bullish", total_amount_min: 569007, party_split: { D: 4, R: 3 }, chambers: { Representatives: 5, Senate: 2 }, latest_trade_date: "2026-05-19", our_score: null, our_verdict: "WATCH", our_price: 512.4, buyers: [{ politician: "Josh Gottheimer", party: "D", chamber: "Representatives", size_range: "$500,001 - $1,000,000", trade_date: "2026-05-19" }] },
    { ticker: "PANW", n_buyers: 3, buy_tx: 4, sell_tx: 0, net: "bullish", total_amount_min: 4004, party_split: { D: 4 }, chambers: { Representatives: 4 }, latest_trade_date: "2026-05-14", our_score: 62, our_verdict: "WAIT", our_price: 191.2, buyers: [] },
    { ticker: "MU", n_buyers: 3, buy_tx: 3, sell_tx: 1, net: "bullish", total_amount_min: 3003, party_split: { D: 3 }, chambers: { Representatives: 2, Senate: 1 }, latest_trade_date: "2026-05-21", our_score: 80, our_verdict: "WATCH", our_price: 98.7, buyers: [] },
  ],
  feed: [
    { politician: "Tim Moore", party: "R", chamber: "Representatives", ticker: "T", type: "buy", size_range: "$50,001 - $100,000", trade_date: "2026-06-04", our_verdict: "WAIT" },
    { politician: "April Mcclain Delaney", party: "D", chamber: "Representatives", ticker: "HUBB", type: "buy", size_range: "$1,001 - $15,000", trade_date: "2026-05-29", our_verdict: "—" },
  ],
  meta: { lookback_days: 90, n_transactions_recent: 908, n_tickers: 267,
    provenance: { house_clerk: { reachable: true, latest_filing: "2026-06-06" }, senate_efd: { reachable: false } },
    sources: [{ name: "quiver", ok: true, n: 989 }, { name: "house_clerk", ok: true, n: 241 }] },
};

const CG_TABS = [["board", "Most Bought"], ["agree", "Where We Agree"], ["feed", "Live Feed"]];

function SurfaceCongress({ onTicker }) {
  const [st, setSt] = useCg({ loading: CG_SERVED, data: CG_SERVED ? null : CG_DEMO, err: null });
  const [tab, setTab] = useCg("board");
  const [sel, setSel] = useCg(null);

  useCgE(() => {
    if (!CG_SERVED) return;
    let alive = true;
    fetch("/api/congress?limit=40&side=buy", { credentials: "same-origin" })
      .then(r => (r.ok ? r.json() : Promise.reject(r.status)))
      .then(d => { if (alive) setSt({ loading: false, data: d && d.available ? d : null, err: d && d.reason ? d.reason : (d && d.available ? null : "unavailable") }); })
      .catch(e => { if (alive) setSt({ loading: false, data: null, err: String(e) }); });
    return () => { alive = false; };
  }, []);

  const board = (st.data && st.data.leaderboard) || [];
  const feed = (st.data && st.data.feed) || [];
  const meta = (st.data && st.data.meta) || {};
  const prov = meta.provenance || {};

  // default selection = top name
  useCgE(() => { if (!sel && board.length) setSel(board[0].ticker); }, [board.length]);

  const agree = useCgm(() =>
    board.filter(e => e.our_score != null && e.our_score >= 65 &&
                      (e.our_verdict || "").toUpperCase() !== "AVOID"), [board]);

  if (st.loading) return <div className="surface wsx wsx--violet"><div className="ss-empty" style={{ padding: 48 }}>Loading congressional flow from /api/congress…</div></div>;

  if (!st.data) return (
    <div className="surface wsx wsx--violet">
      <div className="wsx-hdr"><div className="wsx-hdr-l">
        <div className="wsx-eyebrow mono">POLITICAL FLOW · STOCK ACT DISCLOSURES</div>
        <h1 className="wsx-title mono">Congress</h1></div></div>
      <div className="ss-empty" style={{ padding: 48, textAlign: "center" }}>
        Congressional flow unavailable ({st.err || "no data"}).<br />
        Run <code className="mono">python3 scripts/refresh_congress.py</code> to build the feed.
      </div>
    </div>
  );

  const totalUsd = board.reduce((a, e) => a + (e.total_amount_min || 0), 0);
  const bullishN = board.filter(e => e.net === "bullish").length;
  const senateN = board.filter(e => cgChambers(e.chambers).s > 0).length;
  const houseN = board.filter(e => cgChambers(e.chambers).h > 0).length;
  const rows = tab === "agree" ? agree : board;

  return (
    <div className="surface wsx wsx--violet cg">
      <div className="wsx-hdr">
        <div className="wsx-hdr-l">
          <div className="wsx-eyebrow mono">POLITICAL FLOW · STOCK ACT DISCLOSURES</div>
          <h1 className="wsx-title mono">Congress</h1>
          <div className="wsx-sub mono dim2">What House + Senate members are buying — last {meta.lookback_days || 90}d · joined to our verdict. <b className="amb">Slow signal:</b> up to 45-day disclosure lag → Position/Invest context, never a swing trigger.</div>
        </div>
        <div className="wsx-hdr-r">
          <FreshnessPill state={meta.stale ? "stale" : (prov.house_clerk && prov.house_clerk.reachable ? "live" : "stale")} age={meta.stale ? "stale" : (prov.house_clerk ? (prov.house_clerk.latest_filing || "—") : "—")} />
          <span className="mono dim2">src · {(meta.sources || []).filter(s => s.ok).map(s => s.name).join(" + ") || "multi"}</span>
        </div>
      </div>

      {meta.stale ? <div className="cg-note" style={{ borderColor: "var(--amb)", color: "var(--amb)" }}>⚠ Ticker-level sources were unreachable on the last refresh — showing the last good cache (prior fetch). Official House Clerk freshness: {(prov.house_clerk && prov.house_clerk.latest_filing) || "—"}.</div> : null}

      <div className="wsx-kpis">
        <div className="wsx-kpi wsx-kpi--violet"><div className="wsx-kpi-l mono">NAMES BOUGHT</div><div className="wsx-kpi-v mono kpi-tone--violet">{board.length}</div><div className="wsx-kpi-s mono dim2">{meta.n_tickers || board.length} total · {meta.n_transactions_recent || 0} txns</div></div>
        <div className="wsx-kpi wsx-kpi--copper"><div className="wsx-kpi-l mono">$ COMMITTED</div><div className="wsx-kpi-v mono kpi-tone--copper">{cgFmtUsd(totalUsd)}</div><div className="wsx-kpi-s mono dim2">lower-bound of disclosed bands</div></div>
        <div className="wsx-kpi wsx-kpi--gn"><div className="wsx-kpi-l mono">NET BULLISH</div><div className="wsx-kpi-v mono kpi-tone--gn">{bullishN}</div><div className="wsx-kpi-s mono dim2">≥2 buyers, buys &gt; sells</div></div>
        <div className="wsx-kpi wsx-kpi--blue"><div className="wsx-kpi-l mono">WE AGREE</div><div className="wsx-kpi-v mono kpi-tone--blue">{agree.length}</div><div className="wsx-kpi-s mono dim2">our score ≥65 &amp; not AVOID</div></div>
        <div className="wsx-kpi wsx-kpi--cy"><div className="wsx-kpi-l mono">HOUSE · SENATE</div><div className="wsx-kpi-v mono kpi-tone--cy">{houseN}·{senateN}</div><div className="wsx-kpi-s mono dim2">names by chamber</div></div>
        <div className="wsx-kpi wsx-kpi--amb"><div className="wsx-kpi-l mono">OFFICIAL CHECK</div><div className="wsx-kpi-v mono kpi-tone--amb">{prov.house_clerk && prov.house_clerk.reachable ? "✓" : "—"}</div><div className="wsx-kpi-s mono dim2">House Clerk {prov.house_clerk ? (prov.house_clerk.latest_filing || "") : ""}</div></div>
      </div>

      <div className="lab-tabs">
        {CG_TABS.map(([id, l]) => <button key={id} className={`lab-tab ${tab === id ? "is-on" : ""}`} onClick={() => setTab(id)}>{l}{id === "agree" ? ` · ${agree.length}` : ""}{id === "feed" ? ` · ${feed.length}` : ""}</button>)}
      </div>

      <div className="cg-split">
        {tab === "feed" ? (
          <div className="wsx-body" style={{ width: "100%" }}>
            <table className="dtable wsx-tbl cg-feed-tbl">
              <thead><tr><th>Filed/Trade</th><th>Sym</th><th>Member</th><th>Party</th><th>Chamber</th><th>Side</th><th>Size</th><th className="r">Our read</th></tr></thead>
              <tbody>{feed.map((f, i) => (
                <tr key={i} onClick={() => f.ticker && onTicker(f.ticker)} className="dtable-row">
                  <td className="mono dim2">{f.trade_date || f.publish_date || "—"}</td>
                  <td className="mono"><b>{f.ticker}</b></td>
                  <td className="dim">{f.politician}</td>
                  <td><CgParty split={{ [f.party]: 1 }} /></td>
                  <td className="mono dim2">{f.chamber === "Representatives" ? "House" : f.chamber}</td>
                  <td><Pill tone={f.type === "buy" ? "gn" : "rd"} small>{f.type === "buy" ? "BUY" : "SELL"}</Pill></td>
                  <td className="mono dim2">{f.size_range || "—"}</td>
                  <td className="r">{f.our_verdict ? <Pill tone={cgVerdictTone(f.our_verdict)} small>{f.our_verdict}</Pill> : <span className="dim2 mono">—</span>}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        ) : (
          <>
          <div className="wsx-body cg-tbl-wrap">
            {rows.length === 0 ? (
              <div className="ss-empty" style={{ padding: 40 }}>{tab === "agree" ? "No congressional buys currently clear our score ≥65 / not-AVOID filter." : "No congressional buys in the lookback window."}</div>
            ) : (
            <table className="dtable wsx-tbl cg-tbl">
              <thead><tr>
                <th className="r">#</th><th>Sym</th><th className="r">Buyers</th><th>Party</th><th>Chamber</th>
                <th className="r">$ Committed</th><th>Net</th><th>Latest</th><th className="r">Our score</th><th className="r">Our read</th>
              </tr></thead>
              <tbody>{rows.map((e, i) => {
                const ch = cgChambers(e.chambers);
                return (
                  <tr key={e.ticker} className={sel === e.ticker ? "is-sel" : ""} onClick={() => setSel(e.ticker)}>
                    <td className="r mono dim2"><b className={i < 3 ? "violet" : ""}>{i + 1}</b></td>
                    <td className="mono"><b>{e.ticker}</b></td>
                    <td className="r mono tabular"><b>{e.n_buyers}</b>{e.sell_tx ? <span className="dim2"> /{e.sell_tx}s</span> : null}</td>
                    <td><CgParty split={e.party_split} /></td>
                    <td className="mono dim2">{ch.h ? `H${ch.h}` : ""}{ch.h && ch.s ? "·" : ""}{ch.s ? `S${ch.s}` : ""}</td>
                    <td className="r mono tabular">{cgFmtUsd(e.total_amount_min)}</td>
                    <td><Pill tone={cgNetTone(e.net)} small>{e.net}</Pill></td>
                    <td className="mono dim2">{e.latest_trade_date || "—"}</td>
                    <td className={`r mono tabular ${e.our_score != null && e.our_score >= 65 ? "up" : "dim"}`}>{e.our_score != null ? Math.round(e.our_score) : "—"}</td>
                    <td className="r">{e.our_verdict ? <Pill tone={cgVerdictTone(e.our_verdict)} small>{e.our_verdict}</Pill> : <span className="dim2 mono">—</span>}</td>
                  </tr>
                );
              })}</tbody>
            </table>
            )}
          </div>
          <CgDetail entry={board.find(e => e.ticker === sel)} onTicker={onTicker} />
          </>
        )}
      </div>

      <div className="cg-note mono dim2">
        Sources (free, never single-sourced): <b>Quiver beta</b> (ticker-level, both chambers) + <b>Capitol Trades</b> + official <b>House Clerk</b> bulk FD ZIP{prov.senate_efd && prov.senate_efd.reachable ? " + Senate eFD" : ""} for provenance. Disclosed amounts are bands — we sum lower bounds. STOCK Act permits up to a 45-day filing lag, so this is a lagging, crowded signal (principle 12): <b>context, never a scoring gate</b>. Our verdict column is the live engine read for the same name.
      </div>
    </div>
  );
}

function CgDetail({ entry, onTicker }) {
  if (!entry) return <div className="sdp cg-detail"><div className="ss-empty" style={{ padding: 28 }}>Select a name to see who bought it.</div></div>;
  const ch = cgChambers(entry.chambers);
  const buyers = entry.buyers || [];
  return (
    <div className="sdp cg-detail">
      <div className="sdp-hdr">
        <div>
          <div className="sdp-sym mono"><b>{entry.ticker}</b> {entry.our_sector ? <span className="dim2">{entry.our_sector}</span> : null}</div>
          <div className="sdp-px mono">{entry.our_price != null ? "$" + Number(entry.our_price).toFixed(2) : ""} {entry.our_verdict ? <Pill tone={cgVerdictTone(entry.our_verdict)} small>{entry.our_verdict}</Pill> : null} {entry.our_score != null ? <span className="dim2">· score {Math.round(entry.our_score)}</span> : null}</div>
        </div>
        <span className={`cg-netbadge cg-net--${cgNetTone(entry.net)}`}>{entry.net}</span>
      </div>
      <button className="sdp-open mono" onClick={() => onTicker(entry.ticker)}>OPEN 14-LENS DETAIL →</button>
      <div className="sdp-body">
        <div className="sdp-sec"><div className="sdp-sec-h"><span className="sdp-sec-n mono">$</span><span className="mono">ACCUMULATION</span></div>
          <div className="sdp-sec-b">
            <div className="sdp-kv"><span className="mono dim2">unique buyers</span><span className="mono violet">{entry.n_buyers}</span></div>
            <div className="sdp-kv"><span className="mono dim2">buy / sell txns</span><span className="mono">{entry.buy_tx} / {entry.sell_tx}</span></div>
            <div className="sdp-kv"><span className="mono dim2">$ committed (band floor)</span><span className="mono copper">{cgFmtUsd(entry.total_amount_min)}</span></div>
            <div className="sdp-kv"><span className="mono dim2">chambers</span><span className="mono">{ch.h ? `${ch.h} House` : ""}{ch.h && ch.s ? " · " : ""}{ch.s ? `${ch.s} Senate` : ""}</span></div>
            <div className="sdp-kv"><span className="mono dim2">party split</span><CgParty split={entry.party_split} /></div>
          </div>
        </div>
        <div className="sdp-sec"><div className="sdp-sec-h"><span className="sdp-sec-n mono">★</span><span className="mono">WHO BOUGHT IT</span></div>
          <div className="sdp-sec-b">
            {buyers.length ? buyers.map((b, i) => (
              <div key={i} className="cg-buyer">
                <span className="cg-buyer-name mono"><CgParty split={{ [b.party]: 1 }} /> {b.politician}</span>
                <span className="cg-buyer-meta mono dim2">{b.size_range} · {b.trade_date} · {b.chamber === "Representatives" ? "House" : b.chamber}</span>
              </div>
            )) : <div className="ss-empty mono dim2" style={{ padding: 14 }}>Buyer detail not in feed for this name.</div>}
          </div>
        </div>
        <div className="sdp-sec"><div className="sdp-sec-h"><span className="sdp-sec-n mono">⚑</span><span className="mono">EDGE READ</span></div>
          <div className="sdp-sec-b"><div className="sdp-mech mono">{
            (entry.our_verdict || "").toUpperCase() === "BUY" && entry.net === "bullish"
              ? "Congress accumulation AND our engine agrees — rare confluence. Still a slow signal; size on OUR plan, not the disclosure."
            : entry.net === "bullish" && entry.our_score != null && entry.our_score >= 65
              ? "Congress buying a name our engine also rates well — corroborating context, not a standalone entry."
            : entry.net === "bullish"
              ? "Congress buying, but our engine isn't constructive — likely a slow/positional thesis or a crowded follow. Don't chase on the disclosure alone."
            : "Mixed/selling — no net congressional conviction here."
          }</div></div>
        </div>
      </div>
    </div>
  );
}

window.SurfaceCongress = SurfaceCongress;

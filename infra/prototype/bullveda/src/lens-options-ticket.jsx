// lens-options-ticket.jsx — per-ticker Options cockpit (REAL DATA · Schwab chain).
// Every contract, greek, IV, OI, the chain, dealer-gamma (GEX), term & skew are
// computed from the live Schwab marketdata chain (/api/options). No seeded strikes,
// no hardcoded IV/HV, no fabricated news/whale/alt-data.
// LIMITATION (honest): Schwab returns near-term only (≈0–5 DTE, ~8 strikes) and the
// IV-history series is still building, so there's no IV-rank/percentile yet — those
// are shown as "building", not invented.
// Overrides window.LensOptions (loaded last).

const { useState: useOT, useMemo: useOTm } = React;

const _on = (v, d) => (typeof v === "number" && isFinite(v)) ? v : (d === undefined ? null : d);
const _of = (v, dp = 2) => v == null ? "—" : v.toFixed(dp);

// fetch the real options chain
function useOptions(sym) {
  const [d, setD] = React.useState(null);
  React.useEffect(() => {
    const BV = window.__BV;
    if (!BV || !BV.get || !sym) { setD(false); return; }
    let on = true; setD(null);
    BV.get("/api/options/" + encodeURIComponent(sym)).then(j => { if (on) setD(j && j.expirations ? j : false); }).catch(() => { if (on) setD(false); });
    return () => { on = false; };
  }, [sym]);
  return d;   // null = loading, false = none, object = data
}

function LensOptions({ ticker, mode }) {
  const [tab, setTab] = useOT("chain");
  const [contracts, setContracts] = useOT(1);
  const chain = useOptions(ticker.symbol);
  const loading = chain === null, none = chain === false;
  const exps = (chain && chain.expirations) || [];
  // mode prefers longer-dated; real feed is near-term only → pick the longest available
  const wantDte = mode === "POSITION" ? 9999 : mode === "INVESTMENT" ? 99999 : 4;
  const [dte, setDte] = useOT(null);
  React.useEffect(() => {
    if (!exps.length) return;
    const pick = exps.reduce((a, e) => Math.abs(e.dte - wantDte) < Math.abs(a.dte - wantDte) ? e : a, exps[0]);
    setDte(d => d == null || !exps.some(e => e.dte === d) ? pick.dte : d);
  }, [chain, mode]);

  // build the REAL ATM ticket from the selected expiration
  const o = useOTm(() => {
    if (!chain || !exps.length) return null;
    const spot = _on(chain.spot, _on(ticker.price));
    const exp = exps.find(e => e.dte === dte) || exps[exps.length - 1];
    const strikes = (exp.strikes || []).filter(s => s && s.call);
    if (!spot || !strikes.length) return null;
    const atm = strikes.reduce((a, s) => Math.abs(s.strike - spot) < Math.abs(a.strike - spot) ? s : a, strikes[0]);
    const c = atm.call || {}, pu = atm.put || {};
    const mid = (_on(c.bid) != null && _on(c.ask) != null && c.ask > 0) ? +(((c.bid + c.ask) / 2)).toFixed(2) : _on(c.mark);
    const prem = mid != null ? mid : _on(c.mark, 0);
    const iv = _on(c.iv, _on(chain.atm && chain.atm.iv));
    const be = +(atm.strike + prem).toFixed(2);
    const spread = (_on(c.bid) != null && _on(c.ask) != null && c.ask > 0) ? c.ask - c.bid : null;
    const spreadPct = (spread != null && prem > 0) ? +(spread / prem * 100).toFixed(1) : null;
    const impMove = iv != null ? +(iv / 100 * Math.sqrt(Math.max(dte, 1) / 252) * 100).toFixed(1) : null;
    // POP for a long call = risk-neutral P(S_T > breakeven) = N(d2) — real, not a delta proxy.
    const pop = (iv != null && prem > 0 && spot > 0) ? bsPOP(spot, be, Math.max(dte, 1) / 252, iv / 100) : null;
    const erDays = ticker.earnings && ticker.earnings.days != null ? ticker.earnings.days : null;
    const erInWindow = erDays != null && erDays <= dte;
    return {
      spot, strikes, exp, prem, strike: atm.strike, be, iv, dte, sym: ticker.symbol,
      delta: _on(c.delta), gamma: _on(c.gamma), theta: _on(c.theta), vega: _on(c.vega),
      oi: _on(c.oi), vol: _on(c.vol), bid: _on(c.bid), ask: _on(c.ask), mark: _on(c.mark),
      putMark: _on(pu.mark), spread, spreadPct, impMove, pop, erDays, erInWindow,
      hv20: _on(chain.hv20), hv30: _on(chain.hv30),
      ivVsHv: (iv != null && _on(chain.hv20) != null) ? +(iv - chain.hv20).toFixed(1) : null,
      source: chain.source, ts: chain.ts,
    };
  }, [chain, dte, ticker]);

  if (loading) return <div className="lens lens--otk"><div className="mono dim2" style={{ padding: "48px 18px", textAlign: "center" }}>Loading the live options chain for <b className="copper">{ticker.symbol}</b>…</div></div>;
  if (none || !o) return <div className="lens lens--otk"><div className="mono dim2" style={{ padding: "48px 18px", textAlign: "center" }}>No live options chain for <b className="copper">{ticker.symbol}</b> — it may not be optionable, or the Schwab feed returned nothing.</div></div>;

  const cost = (o.prem * 100 * contracts);
  const TABS = [["chain", "Contract & Pricing"], ["gex", "Where It Pins · GEX"], ["build", "Strategies & Journal"]];
  const maxDte = exps.length ? Math.max(...exps.map(e => e.dte)) : 0;
  const horizonMismatch = (mode === "INVESTMENT" && maxDte < 120) || (mode === "POSITION" && maxDte < 45);

  return (
    <div className="lens lens--otk">
      {/* ───── DECISION STRIP ───── */}
      <div className="otk-strip">
        <div className="otk-ticket">
          <div className="otk-ticket-h mono">⊞ TRADE TICKET · <span className="cy">Long Call (ATM)</span></div>
          <div className="otk-ticket-row">
            <span className="otk-buy mono">▶ BUY</span>
            <span className="otk-prem mono">${o.prem.toFixed(2)}</span>
            <span className="otk-contract mono dim2">{o.strike}C · {o.dte}DTE · spot ${o.spot.toFixed(2)}</span>
          </div>
          <div className="otk-exp-row">
            {exps.map(e => (
              <button key={e.dte} className={`otk-exp ${o.dte === e.dte ? "is-on" : ""}`} onClick={() => setDte(e.dte)} title={`${e.expiration} · ${e.dte} DTE`}>
                {e.dte}d
              </button>
            ))}
          </div>
          <div className="otk-tt-levels">
            <div className="otk-lvl"><span className="otk-lvl-l mono">BE</span><span className="otk-lvl-v mono">${o.be.toFixed(2)}</span></div>
            <div className="otk-lvl"><span className="otk-lvl-l mono">BID/ASK</span><span className="otk-lvl-v mono dim2">{o.bid != null ? `$${o.bid.toFixed(2)} / $${o.ask.toFixed(2)}` : "—"}</span></div>
            <div className="otk-lvl"><span className="otk-lvl-l mono">IMP MOVE</span><span className="otk-lvl-v mono warn">{o.impMove != null ? `±${o.impMove}%` : "—"}</span></div>
          </div>
          <div className="otk-size">
            <span className="mono dim2">Contracts</span>
            <div className="otk-size-ctl">
              <button onClick={() => setContracts(c => Math.max(1, c - 1))}>−</button>
              <span className="mono">{contracts}</span>
              <button onClick={() => setContracts(c => c + 1)}>+</button>
            </div>
          </div>
          <div className="otk-cost">
            <div><span className="mono dim2">Total</span> <b className="mono cy">${cost.toFixed(0)}</b></div>
            <div><span className="mono dim2">Max risk</span> <b className="mono dn">${cost.toFixed(0)}</b></div>
            <div><span className="mono dim2">Max reward</span> <b className="mono up">uncapped</b></div>
          </div>
          <div className="mono dim2" style={{ fontSize: 9, marginTop: 4 }}>{o.source || "schwab"} · spot ${o.spot.toFixed(2)}{o.ts ? ` · ${String(o.ts).slice(11, 16)}` : ""}</div>
        </div>

        <div className="otk-verdict">
          <div className="otk-verdict-top">
            <span className="otk-verdict-tag">LIVE CHAIN</span>
            <span className="otk-edge mono">{o.dte}<span className="dim2"> DTE</span></span>
          </div>
          <div className="otk-checks">
            <OtkCheck ok={o.spreadPct != null && o.spreadPct < 15} warn={o.spreadPct != null && o.spreadPct >= 15}
              text={o.spreadPct != null ? `Spread ${o.spreadPct}% of premium — ${o.spreadPct < 8 ? "tight, easy fill" : o.spreadPct < 15 ? "workable" : "wide, mind slippage"}` : "Spread n/a"} />
            <OtkCheck ok={o.oi != null && o.oi >= 500} warn={o.oi != null && o.oi < 500}
              text={o.oi != null ? `ATM open interest ${o.oi.toLocaleString()} · vol ${(o.vol || 0).toLocaleString()} — ${o.oi >= 500 ? "liquid" : "thin"}` : "OI n/a"} />
            {o.ivVsHv != null
              ? <OtkCheck ok={o.ivVsHv <= -5} warn={o.ivVsHv > -5 && o.ivVsHv < 8} bad={o.ivVsHv >= 8}
                  text={`IV ${o.iv.toFixed(0)}% vs realized HV20 ${o.hv20.toFixed(0)}% → vol is ${o.ivVsHv <= -5 ? "CHEAP — buying premium favorable" : o.ivVsHv >= 8 ? "RICH — you're overpaying for vol" : "fair vs realized"}`} />
              : <OtkCheck neutral text={`ATM IV ${o.iv != null ? o.iv.toFixed(1) + "%" : "—"} — realized-vol comparison unavailable`} />}
            {o.erInWindow
              ? <OtkCheck bad text={`EARNINGS in ${o.erDays}d (inside this expiry) — expect IV crush post-print`} />
              : o.erDays != null ? <OtkCheck ok text={`No earnings before expiry (next in ${o.erDays}d) — clean theta`} />
                : <OtkCheck neutral text="Earnings date unknown" />}
          </div>
          <div className="otk-heroes">
            <div className="otk-hero"><div className="mono dim2">PREMIUM</div><div className="mono otk-hero-v cy">${o.prem.toFixed(2)}</div></div>
            <div className="otk-hero"><div className="mono dim2">Δ DELTA</div><div className="mono otk-hero-v">{o.delta != null ? o.delta.toFixed(2) : "—"}</div></div>
            <div className="otk-hero"><div className="mono dim2">POP*</div><div className="mono otk-hero-v">{o.pop != null ? o.pop + "%" : "—"}</div><div className="mono dim2" style={{ fontSize: 8 }}>≈ from Δ</div></div>
            <div className="otk-hero"><div className="mono dim2">θ/DAY</div><div className="mono otk-hero-v dn">{o.theta != null ? "$" + o.theta.toFixed(2) : "—"}</div></div>
          </div>
        </div>
      </div>

      {horizonMismatch && (
        <div className="otk-horizon mono">⚑ {mode === "INVESTMENT" ? "Invest" : "Position"} horizon: the live feed only has near-term contracts (≤{maxDte} DTE). Options aren't suited to a multi-month thesis here — this shows the nearest weekly for context, not a {mode === "INVESTMENT" ? "long-term" : "multi-month"} holding.</div>
      )}
      <OptQuickTake ticker={ticker} mode={mode} o={o} />

      <div className="otk-tabs">
        {TABS.map(([id, l]) => <button key={id} className={`otk-tab ${tab === id ? "is-on" : ""}`} onClick={() => setTab(id)}>{l}</button>)}
      </div>

      <div className="otk-body">
        {tab === "chain" && <OtkChainGreeks o={o} exps={exps} />}
        {tab === "gex" && <OtkGEX o={o} />}
        {tab === "build" && <OtkBuild o={o} />}
      </div>
    </div>
  );
}

// ───── Options Quick Take — "should I do this trade?" decision layer ─────
function OptQuickTake({ ticker, mode, o }) {
  const cv = window.compositeVerdict ? window.compositeVerdict(ticker, mode) : null;
  const net = cv ? cv.net : null;
  const biasBull = net != null ? net >= 55 : null, biasBear = net != null ? net < 45 : null;
  const beMove = (o.be / o.spot - 1) * 100;            // % move to breakeven
  const imp = o.impMove;                                // implied move over the DTE
  const achievable = imp != null ? beMove <= imp : null;
  const gex = useOTm(() => { try { return computeGEX(o); } catch (e) { return null; } }, [o]);
  const F = [];
  if (net != null) F.push({ k: "Direction", v: biasBull ? 1 : biasBear ? -1 : 0, text: biasBull ? `stock reads bullish (${Math.round(net)}/100) — a call aligns with the trend` : biasBear ? `stock reads bearish (${Math.round(net)}/100) — a long call fights the trend` : `stock is mixed (${Math.round(net)}/100) — no directional tailwind` });
  if (achievable != null) F.push({ k: "Cost vs move", v: achievable ? 1 : -1, text: `needs ${beMove >= 0 ? "+" : ""}${beMove.toFixed(1)}% by expiry; the market prices ±${imp}% → breakeven is ${achievable ? "achievable" : "a stretch"}` });
  if (o.ivVsHv != null) F.push({ k: "Volatility", v: o.ivVsHv <= -5 ? 1 : o.ivVsHv >= 8 ? -1 : 0, text: `IV ${o.iv.toFixed(0)}% vs realized ${o.hv20.toFixed(0)}% — ${o.ivVsHv <= -5 ? "cheap, good for buying premium" : o.ivVsHv >= 8 ? "rich, you overpay for vol" : "fair"}` });
  F.push({ k: "Time", v: o.dte >= 3 ? 0 : -1, text: o.dte <= 1 ? `${o.dte}-DTE — expiry-day gamma/theta, all-or-nothing` : o.dte < 3 ? `${o.dte}-DTE — theta bleeds fast, needs an immediate move` : `${o.dte}-DTE — short-dated; the move must come within days` });
  if (o.spreadPct != null) F.push({ k: "Liquidity", v: (o.spreadPct < 15 && (o.oi || 0) >= 500) ? 1 : (o.spreadPct < 25) ? 0 : -1, text: `spread ${o.spreadPct}% of premium · ATM OI ${(o.oi || 0).toLocaleString()}` });
  if (o.erInWindow) F.push({ k: "Earnings", v: -1, text: `earnings in ${o.erDays}d, inside this expiry — expect IV crush after the print` });
  const fails = F.filter(f => f.v < 0).length, passes = F.filter(f => f.v > 0).length;
  const verdict = fails === 0 && passes >= 2 ? "REASONABLE SETUP" : fails <= 1 ? "TRADEABLE · WITH CARE" : "POOR SETUP";
  const tone = fails === 0 ? "gn" : fails <= 1 ? "amb" : "rd";
  const expShort = (o.exp.expiration || "").slice(5);
  const plain = `A ${o.dte}-DTE ATM call costs $${(o.prem * 100).toFixed(0)} and needs ${ticker.symbol} to move ${beMove >= 0 ? "+" : ""}${beMove.toFixed(1)}% by ${expShort} just to break even` +
    (imp != null ? ` — options are pricing a ±${imp}% move over that window, so breakeven is ${achievable ? "within reach" : "a stretch"}.` : ".") +
    (biasBear ? ` The stock itself reads bearish, so a long call is fighting the trend.` : biasBull ? ` The stock's trend is supportive.` : "");
  return (
    <div className={`qt qt--${tone}`} style={{ margin: "0 0 12px" }}>
      <div className="qt-grid" style={{ gridTemplateColumns: "150px 1fr 170px" }}>
        <div className="qt-verdict">
          <div className="label-cap">Trade read</div>
          <div className={`qt-v mono kpi-tone--${tone}`} style={{ fontSize: 20 }}>{verdict}</div>
          <div className="qt-conf mono dim2">{passes} green · {fails} red · long ATM call</div>
        </div>
        <div className="qt-tally">
          {F.map((f, i) => (
            <div key={i} className="otk-qt-factor mono">
              <span className={`otk-qt-dot kpi-tone--${f.v > 0 ? "gn" : f.v < 0 ? "rd" : "amb"}`}>{f.v > 0 ? "✓" : f.v < 0 ? "✕" : "·"}</span>
              <span className="otk-qt-k">{f.k}</span><span className="dim2"> — {f.text}</span>
            </div>
          ))}
        </div>
        <div className="qt-plan">
          <div className="label-cap">Break-even vs move</div>
          <div className="qt-plan-row"><span className="mono dim2">Breakeven</span><span className="mono copper">${o.be.toFixed(2)}</span></div>
          <div className="qt-plan-row"><span className="mono dim2">Move needed</span><span className={`mono ${beMove <= (imp || 999) ? "up" : "dn"}`}>{beMove >= 0 ? "+" : ""}{beMove.toFixed(1)}%</span></div>
          <div className="qt-plan-row"><span className="mono dim2">Implied move</span><span className="mono">±{imp != null ? imp : "—"}%</span></div>
          <div className="qt-plan-row"><span className="mono dim2">POP (N·d₂)</span><span className="mono">{o.pop != null ? o.pop + "%" : "—"}</span></div>
        </div>
      </div>
      <div className="qt-plain mono">{plain}{gex ? ` Dealer gamma is ${gex.total >= 0 ? (gex.putWall === gex.callWall ? `positive — price tends to pin near $${gex.maxPain}` : `positive — price tends to pin between $${Math.min(gex.putWall, gex.callWall)} and $${Math.max(gex.putWall, gex.callWall)}`) : `negative — expect amplified, trending moves`}.` : ""}</div>
    </div>
  );
}

function OtkCheck({ ok, bad, warn, neutral, text }) {
  const cls = ok ? "ok" : bad ? "bad" : warn ? "warn" : "warn";
  const icon = ok ? "✓" : bad ? "⚠" : "·";
  return <div className={`otk-chk ${cls} mono`}><span>{icon}</span> {text}</div>;
}

// ───── TAB 1: CHAIN & GREEKS (real) ─────
function OtkChainGreeks({ o, exps }) {
  const mid = (b, a, m) => (_on(b) != null && _on(a) != null) ? (b + a) / 2 : _on(m);
  const rows = o.strikes.map(s => {
    const c = s.call || {}, p = s.put || {};
    const dist = (s.strike - o.spot) / o.spot;
    return { k: s.strike, atm: s.strike === o.strike, itm: s.strike < o.spot, dist,
      cMid: mid(c.bid, c.ask, c.mark), cDelta: _on(c.delta), cIv: _on(c.iv), cOi: _on(c.oi, 0), cVol: _on(c.vol, 0),
      pMid: mid(p.bid, p.ask, p.mark), pDelta: _on(p.delta), pIv: _on(p.iv), pOi: _on(p.oi, 0), pVol: _on(p.vol, 0) };
  });
  const maxOI = Math.max(...rows.map(r => Math.max(r.cOi, r.pOi)), 1);
  // put/call ratios (sentiment) + real unusual activity (today's vol > resting OI)
  const totCOi = rows.reduce((a, r) => a + r.cOi, 0), totPOi = rows.reduce((a, r) => a + r.pOi, 0);
  const totCVol = rows.reduce((a, r) => a + r.cVol, 0), totPVol = rows.reduce((a, r) => a + r.pVol, 0);
  const pcrOi = totCOi > 0 ? +(totPOi / totCOi).toFixed(2) : null;
  const pcrVol = totCVol > 0 ? +(totPVol / totCVol).toFixed(2) : null;
  const uoa = rows.flatMap(r => {
    const out = [];
    if (r.cVol > r.cOi && r.cVol > 200) out.push({ k: r.k, side: "C", vol: r.cVol });
    if (r.pVol > r.pOi && r.pVol > 200) out.push({ k: r.k, side: "P", vol: r.pVol });
    return out;
  }).sort((a, b) => b.vol - a.vol);
  // term structure: real ATM IV by expiry
  const term = exps.map(e => {
    const ss = (e.strikes || []).filter(s => s.call);
    const atm = ss.length ? ss.reduce((a, s) => Math.abs(s.strike - o.spot) < Math.abs(a.strike - o.spot) ? s : a, ss[0]) : null;
    return { dte: e.dte, iv: atm ? _on(atm.call.iv) : null, on: e.dte === o.dte };
  }).filter(t => t.iv != null);
  // skew: real IV by strike (call side; put IV where call missing)
  const skew = rows.map(r => ({ k: r.k, iv: r.cIv != null ? r.cIv : r.pIv, atm: r.atm })).filter(s => s.iv != null);
  const tW = 300, tH = 120, tPad = 30;
  const tMax = term.length ? Math.max(...term.map(t => t.iv)) : 1, tMin = term.length ? Math.min(...term.map(t => t.iv)) : 0;
  const tx = i => tPad + (i / Math.max(1, term.length - 1)) * (tW - tPad - 12);
  const ty = v => 12 + (1 - ((v - tMin + 1) / (tMax - tMin + 2))) * (tH - 12 - 22);
  const sMax = skew.length ? Math.max(...skew.map(s => s.iv)) : 1, sMin = skew.length ? Math.min(...skew.map(s => s.iv)) : 0;
  const sx = i => tPad + (i / Math.max(1, skew.length - 1)) * (tW - tPad - 12);
  const sy = v => 12 + (1 - ((v - sMin + 1) / (sMax - sMin + 2))) * (tH - 12 - 22);
  const contango = term.length >= 2 ? term[term.length - 1].iv > term[0].iv : null;
  const atmRow = rows.find(r => r.atm);
  const otmCall = rows.filter(r => r.k > o.spot).slice(0, 1)[0];
  const otmPut = rows.filter(r => r.k < o.spot).slice(-1)[0];
  const putSkew = (otmPut && otmCall && otmPut.pIv != null && otmCall.cIv != null) ? +(otmPut.pIv - otmCall.cIv).toFixed(1) : null;
  return (
    <div className="otk-grid">
      <div className="otk-card otk-card--wide">
        <div className="otk-card-h mono">CHAIN · {o.exp.expiration} · {o.dte}DTE · <span className="cy">calls</span> ◂ strike ▸ <span className="violet">puts</span> · <span className="dim2">live Schwab greeks</span></div>
        <table className="dtable otk-tbl otk-chain">
          <thead><tr>
            <th className="r">OI</th><th className="r">Vol</th><th className="r">IV</th><th className="r">Δ</th><th className="r">Mid</th>
            <th style={{ textAlign: "center" }}>STRIKE</th>
            <th className="r">Mid</th><th className="r">Δ</th><th className="r">IV</th><th className="r">Vol</th><th className="r">OI</th>
          </tr></thead>
          <tbody>{rows.map((s, i) => (
            <tr key={i} className={s.atm ? "is-current" : ""}>
              <td className="r mono dim2">{(s.cOi || 0).toLocaleString()}</td>
              <td className={`r mono ${s.cVol > s.cOi && s.cVol > 200 ? "up" : "dim2"}`}>{(s.cVol || 0).toLocaleString()}</td>
              <td className="r mono">{s.cIv != null ? s.cIv.toFixed(0) + "%" : "—"}</td>
              <td className="r mono dim2">{_of(s.cDelta)}</td>
              <td className="r mono cy">{s.cMid != null ? "$" + s.cMid.toFixed(2) : "—"}</td>
              <td className="mono" style={{ textAlign: "center" }}><b>${s.k}</b>{s.atm && <span className="otk-atm mono">ATM</span>}</td>
              <td className="r mono" style={{ color: "var(--violet)" }}>{s.pMid != null ? "$" + s.pMid.toFixed(2) : "—"}</td>
              <td className="r mono dim2">{_of(s.pDelta)}</td>
              <td className="r mono">{s.pIv != null ? s.pIv.toFixed(0) + "%" : "—"}</td>
              <td className={`r mono ${s.pVol > s.pOi && s.pVol > 200 ? "dn" : "dim2"}`}>{(s.pVol || 0).toLocaleString()}</td>
              <td className="r mono dim2">{(s.pOi || 0).toLocaleString()}</td>
            </tr>
          ))}</tbody>
        </table>
        <div className="mono" style={{ fontSize: 10.5, marginTop: 6, display: "flex", gap: 16, flexWrap: "wrap", color: "var(--ink-2)" }}>
          {pcrOi != null && <span>Put/Call OI <b className={pcrOi >= 1 ? "dn" : "up"}>{pcrOi}</b> — {pcrOi >= 1.2 ? "put-heavy (hedging / bearish lean)" : pcrOi <= 0.7 ? "call-heavy (bullish lean)" : "balanced"}</span>}
          {pcrVol != null && <span className="dim2">· P/C vol {pcrVol}</span>}
          {uoa.length > 0
            ? <span>· <b className="copper">Unusual:</b> {uoa.slice(0, 3).map(u => `${u.k}${u.side} ${u.vol.toLocaleString()}v`).join(", ")} <span className="dim2">(today's vol &gt; resting OI)</span></span>
            : <span className="dim2">· no unusual vol vs OI</span>}
        </div>
      </div>

      <div className="otk-card">
        <div className="otk-card-h mono">GREEKS · ATM {o.strike}C · {o.dte}DTE</div>
        <div className="otk-greeks">
          {[
            ["Δ", o.delta != null ? (o.delta >= 0 ? "+" : "") + o.delta.toFixed(3) : "—", o.delta != null ? `moves ≈$${(o.delta).toFixed(2)} per $1 the stock moves` : "directional sensitivity"],
            ["Γ", o.gamma != null ? o.gamma.toFixed(4) : "—", "how fast delta changes — higher = more responsive near the strike"],
            ["Θ/d", o.theta != null ? "$" + o.theta.toFixed(3) : "—", o.theta != null ? `loses ≈$${Math.abs(o.theta * 100).toFixed(0)}/day to time if the stock sits still` : "time decay per day"],
            ["ν", o.vega != null ? "$" + o.vega.toFixed(3) : "—", "gains/loses this per 1 IV point — volatility sensitivity"],
          ].map(([k, v, help], i) => (
            <div key={i} className="otk-greek" title={help}><span className="mono dim2">{k} <span style={{ fontSize: 8, color: "var(--ink-3)" }}>ⓘ</span></span><span className="mono otk-greek-v">{v}</span></div>
          ))}
        </div>
        <div className="mono dim2" style={{ fontSize: 10, marginTop: 6, lineHeight: 1.5 }}>
          {o.delta != null && <>Δ <b>{o.delta.toFixed(2)}</b>: gains ≈<b className="up">${(o.delta).toFixed(2)}</b> per +$1 {o.sym}. </>}
          {o.theta != null && <>Θ: bleeds ≈<b className="dn">${Math.abs(o.theta * 100).toFixed(0)}/day</b> to time.</>}
        </div>
        <div className="otk-stats" style={{ marginTop: 8 }}>
          {[["ATM IV", o.iv != null ? o.iv.toFixed(1) + "%" : "—"], ["Realized HV20", o.hv20 != null ? o.hv20.toFixed(1) + "%" : "—"], ["IV − HV", o.ivVsHv != null ? (o.ivVsHv >= 0 ? "+" : "") + o.ivVsHv : "—"], ["Imp move", o.impMove != null ? "±" + o.impMove + "%" : "—"], ["Put skew", putSkew != null ? (putSkew >= 0 ? "+" : "") + putSkew + "%" : "—"], ["Spread", o.spreadPct != null ? o.spreadPct + "%" : "—"]].map(([k, v], i) => (
            <div key={i} className="otk-stat"><span className="mono dim2">{k}</span><span className="mono">{v}</span></div>
          ))}
        </div>
      </div>

      <div className="otk-card">
        <div className="otk-card-h mono">VOL TERM STRUCTURE · ATM IV by DTE</div>
        {term.length >= 2 ? <>
          <svg width="100%" height={tH} viewBox={`0 0 ${tW} ${tH}`} className="otk-mini-svg">
            <polyline points={term.map((t, i) => `${tx(i)},${ty(t.iv)}`).join(" ")} fill="none" stroke="var(--copper)" strokeWidth="2" />
            {term.map((t, i) => (<g key={i}>
              <circle cx={tx(i)} cy={ty(t.iv)} r={t.on ? 5 : 3} fill={t.on ? "var(--copper)" : "var(--ink-2)"} stroke="var(--bg)" strokeWidth="1.5" />
              <text x={tx(i)} y={tH - 8} fontSize="8" className="mono" textAnchor="middle" fill={t.on ? "var(--copper)" : "var(--ink-3)"}>{t.dte}d</text>
              <text x={tx(i)} y={ty(t.iv) - 9} fontSize="8" className="mono" textAnchor="middle" fill="var(--ink-2)">{t.iv.toFixed(0)}</text>
            </g>))}
          </svg>
          <div className="otk-verdict-mini mono"><span className={contango ? "warn" : "up"}>{contango ? "CONTANGO" : "BACKWARDATION"}</span> · {contango ? "front cheaper than back" : "front richer — near-term event/fear premium"}</div>
        </> : <div className="mono dim2" style={{ padding: 14, fontSize: 11 }}>Only one expiry returned by the live feed — term structure needs ≥2.</div>}
      </div>

      <div className="otk-card">
        <div className="otk-card-h mono">SKEW · IV by strike{putSkew != null ? ` · put-call ${putSkew >= 0 ? "+" : ""}${putSkew}%` : ""}</div>
        {skew.length >= 3 ? <>
          <svg width="100%" height={tH} viewBox={`0 0 ${tW} ${tH}`} className="otk-mini-svg">
            <polyline points={skew.map((s, i) => `${sx(i)},${sy(s.iv)}`).join(" ")} fill="none" stroke="var(--violet)" strokeWidth="2" />
            {skew.map((s, i) => s.atm && <line key={i} x1={sx(i)} y1={12} x2={sx(i)} y2={tH - 22} stroke="var(--copper)" strokeDasharray="3 3" opacity="0.6" />)}
            {skew.map((s, i) => <circle key={i} cx={sx(i)} cy={sy(s.iv)} r={s.atm ? 4 : 2.5} fill={s.atm ? "var(--copper)" : "var(--violet)"} />)}
            <text x={tPad} y={tH - 8} fontSize="8" className="mono" fill="var(--ink-3)">↓ lower strike</text>
            <text x={tW - 12} y={tH - 8} fontSize="8" className="mono" textAnchor="end" fill="var(--ink-3)">higher ↑</text>
          </svg>
          <div className="otk-verdict-mini mono">{putSkew != null && putSkew > 1 ? <><span className="warn">PUT SKEW +{putSkew}%</span> · downside protection bid richer</> : putSkew != null && putSkew < -1 ? <><span className="up">CALL SKEW {putSkew}%</span> · upside bid richer</> : <span className="dim2">Roughly symmetric skew</span>}</div>
        </> : <div className="mono dim2" style={{ padding: 14, fontSize: 11 }}>Too few strikes with IV for a skew curve.</div>}
      </div>

      <div className="otk-card">
        <div className="otk-card-h mono">THETA DECAY · premium value by date <span className="dim2" style={{ textTransform: "none", letterSpacing: ".04em" }}>· spot unchanged</span></div>
        <OtkThetaCurve o={o} />
      </div>

      <div className="otk-card otk-card--wide">
        <div className="otk-card-h mono">PROFIT CALCULATOR · option P&amp;L across spot move × days held <span className="dim2" style={{ textTransform: "none", letterSpacing: ".04em" }}>· Black-Scholes off the live IV</span></div>
        <OtkProfitGrid o={o} />
      </div>
    </div>
  );
}

// theta decay viz off the REAL premium / theta / dte
function OtkThetaCurve({ o }) {
  const W = 360, H = 150, padL = 40, padR = 14, padT = 14, padB = 26;
  const dte = Math.max(1, o.dte || 5);
  const valAt = d => +(o.prem * Math.sqrt(Math.max(0, (dte - d)) / dte)).toFixed(2);
  const days = Array.from(new Set([0, Math.round(dte * 0.25), Math.round(dte * 0.5), Math.round(dte * 0.75), dte]));
  const pts = []; for (let d = 0; d <= dte; d++) pts.push({ d, v: valAt(d) });
  const maxV = o.prem || 1;
  const x = d => padL + (d / dte) * (W - padL - padR);
  const y = v => padT + (1 - v / maxV) * (H - padT - padB);
  const path = pts.map((p, i) => `${i ? "L" : "M"} ${x(p.d).toFixed(1)} ${y(p.v).toFixed(1)}`).join(" ");
  const area = `${path} L ${x(dte)} ${y(0)} L ${x(0)} ${y(0)} Z`;
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} className="otk-mini-svg">
        <defs><linearGradient id="otk-theta" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--rd)" stopOpacity="0.28" /><stop offset="100%" stopColor="var(--rd)" stopOpacity="0" /></linearGradient></defs>
        {[0, 0.5, 1].map((f, i) => <line key={i} x1={padL} y1={y(maxV * f)} x2={W - padR} y2={y(maxV * f)} stroke="var(--line)" strokeDasharray="2 3" />)}
        <path d={area} fill="url(#otk-theta)" /><path d={path} fill="none" stroke="var(--rd)" strokeWidth="1.8" />
        {days.map((d, i) => (<g key={i}>
          <circle cx={x(d)} cy={y(valAt(d))} r="3" fill="var(--rd)" />
          <text x={x(d)} y={H - 9} fontSize="8.5" className="mono" textAnchor="middle" fill="var(--ink-3)">{d === 0 ? "today" : "T+" + d}</text>
        </g>))}
      </svg>
      <div className="mono dim2" style={{ fontSize: 10.5, marginTop: 4 }}>If spot doesn't move, the premium bleeds toward zero by expiry — theta <b className="dn">${o.theta != null ? o.theta.toFixed(2) : "—"}/day</b> now. You need the move <b>before</b> the curve rolls over (this is a {o.dte}-DTE contract).</div>
    </div>
  );
}

// Black-Scholes (for the what-if profit grid)
function bsNormCdf(x) { const t = 1 / (1 + 0.2316419 * Math.abs(x)); const d = 0.3989423 * Math.exp(-x * x / 2); let p = d * t * (0.3193815 + t * (-0.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274)))); return x > 0 ? 1 - p : p; }
function bsCall(S, K, T, sigma, r = 0.04) { if (T <= 0) return Math.max(S - K, 0); const v = sigma * Math.sqrt(T); const d1 = (Math.log(S / K) + (r + sigma * sigma / 2) * T) / v; const d2 = d1 - v; return S * bsNormCdf(d1) - K * Math.exp(-r * T) * bsNormCdf(d2); }
// risk-neutral probability the call finishes above breakeven by expiry = N(d2|K=BE)
function bsPOP(S, BE, T, sigma, r = 0.04) { if (T <= 0 || sigma <= 0 || S <= 0 || BE <= 0) return S > BE ? 100 : 0; const d2 = (Math.log(S / BE) + (r - sigma * sigma / 2) * T) / (sigma * Math.sqrt(T)); return Math.round(Math.max(1, Math.min(99, bsNormCdf(d2) * 100))); }

function OtkProfitGrid({ o }) {
  const sigma = (o.iv != null ? o.iv : 40) / 100;
  const K = o.strike, prem = o.prem, dteY = (o.dte || 5) / 252;
  const moves = [-0.10, -0.05, -0.02, 0, 0.02, 0.05, 0.10];
  const dayBuckets = Array.from(new Set([0, Math.round(o.dte * 0.5), o.dte])).filter(d => d <= o.dte);
  const cell = (mv, dHeld) => {
    const S = o.spot * (1 + mv);
    const Trem = Math.max(0, ((o.dte || 5) - dHeld)) / 252;
    const val = bsCall(S, K, Trem, sigma);
    const pl = (val - prem) / prem * 100;
    return pl;
  };
  const tone = pl => pl >= 25 ? "gn" : pl >= 0 ? "amb" : pl <= -50 ? "rd" : "rd";
  return (
    <table className="dtable otk-tbl">
      <thead><tr><th>Spot move</th>{dayBuckets.map(d => <th key={d} className="r">{d === 0 ? "now" : `T+${d}`}</th>)}</tr></thead>
      <tbody>{moves.map((mv, i) => (
        <tr key={i}>
          <td className="mono">{mv >= 0 ? "+" : ""}{(mv * 100).toFixed(0)}% → ${(o.spot * (1 + mv)).toFixed(0)}</td>
          {dayBuckets.map(d => { const pl = cell(mv, d); return <td key={d} className={`r mono kpi-tone--${tone(pl)}`}>{pl >= 0 ? "+" : ""}{pl.toFixed(0)}%</td>; })}
        </tr>
      ))}</tbody>
    </table>
  );
}

// ───── TAB 2: DEALER GAMMA (real, from the live chain) ─────
function computeGEX(o) {
  const spot = o.spot;
  const rows = o.strikes.map(s => {
    const cOi = _on((s.call || {}).oi, 0), pOi = _on((s.put || {}).oi, 0);
    const cG = _on((s.call || {}).gamma, 0), pG = _on((s.put || {}).gamma, 0);
    const callGEX = -cOi * cG * spot * spot * 1e-4;   // dealer short calls (−), short puts (+)
    const putGEX = pOi * pG * spot * spot * 1e-4;
    return { k: s.strike, callOI: cOi, putOI: pOi, net: +(callGEX + putGEX).toFixed(2) };
  });
  if (!rows.length) return null;
  let maxPain = rows[0].k, minPay = Infinity;
  rows.forEach(r => { let p = 0; rows.forEach(s => { p += Math.max(0, r.k - s.k) * s.callOI + Math.max(0, s.k - r.k) * s.putOI; }); if (p < minPay) { minPay = p; maxPain = r.k; } });
  const callWall = rows.reduce((a, b) => b.callOI > a.callOI ? b : a).k;
  const putWall = rows.reduce((a, b) => b.putOI > a.putOI ? b : a).k;
  let flip = spot; for (let i = 1; i < rows.length; i++) { if ((rows[i - 1].net < 0) !== (rows[i].net < 0)) { flip = rows[i].k; break; } }
  const total = +rows.reduce((a, b) => a + b.net, 0).toFixed(2);
  return { rows, maxPain, callWall, putWall, flip, total };
}
function OtkGEX({ o }) {
  const g = useOTm(() => computeGEX(o), [o]);
  if (!g) return <div className="otk-card otk-card--wide"><div className="mono dim2" style={{ padding: 16 }}>Not enough open-interest in the live chain to compute dealer gamma.</div></div>;
  const W = 720, H = 220, padL = 16, padR = 16, padT = 16, padB = 30;
  const n = g.rows.length, bw = (W - padL - padR) / n;
  const maxAbs = Math.max(...g.rows.map(r => Math.abs(r.net)), 0.01);
  const y0 = padT + (H - padT - padB) / 2, yh = (H - padT - padB) / 2;
  const cx = i => padL + bw * (i + 0.5);
  const spotI = (o.spot - g.rows[0].k) / Math.max(1e-6, (g.rows[n - 1].k - g.rows[0].k)) * (n - 1);
  const spotX = padL + bw * (spotI + 0.5);
  const pos = g.total >= 0;
  const gexPrompt = () => `Explain options dealer-gamma (GEX) to a BEGINNER STOCK trader (they don't trade options) in plain, simple English. Use the live numbers for ${o.sym} below: 3-4 short sentences, use the actual prices, end with ONE practical takeaway for someone trading the shares.
Spot: $${o.spot.toFixed(2)} · Net GEX: ${g.total >= 0 ? "+" : ""}${g.total} (${g.total >= 0 ? "positive — moves dampened" : "negative — moves amplified"}) · Call wall: $${g.callWall} · Put wall: $${g.putWall} · Flip: $${g.flip} · Max pain: $${g.maxPain}`;
  return (
    <div className="otk-card otk-card--wide">
      <div className="otk-card-h mono">DEALER GAMMA (GEX) · {o.dte}DTE · <span className="dim2">computed from live chain OI × γ</span></div>
      <div className="otk-gex-kpis">
        <div className="otk-gex-kpi"><span className="mono dim2">NET GEX</span><span className={`mono otk-gex-kv ${pos ? "up" : "dn"}`}>{pos ? "+" : "−"}${Math.abs(g.total).toFixed(2)}</span><span className="mono dim2" style={{ fontSize: 8 }}>{pos ? "stabilizing" : "amplifying"}</span></div>
        <div className="otk-gex-kpi"><span className="mono dim2">γ-FLIP</span><span className="mono otk-gex-kv warn">${g.flip}</span></div>
        <div className="otk-gex-kpi"><span className="mono dim2">MAX PAIN</span><span className="mono otk-gex-kv copper">${g.maxPain}</span></div>
        <div className="otk-gex-kpi"><span className="mono dim2">CALL WALL</span><span className="mono otk-gex-kv up">${g.callWall}</span></div>
        <div className="otk-gex-kpi"><span className="mono dim2">PUT WALL</span><span className="mono otk-gex-kv dn">${g.putWall}</span></div>
      </div>
      <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet" className="otk-gex-svg">
        <line x1={padL} y1={y0} x2={W - padR} y2={y0} stroke="var(--glass-line)" />
        {g.rows.map((r, i) => { const h = (Math.abs(r.net) / maxAbs) * yh; const up = r.net >= 0;
          return (<g key={i}><rect x={cx(i) - bw * 0.32} y={up ? y0 - h : y0} width={bw * 0.64} height={h} fill={up ? "var(--gn)" : "var(--rd)"} opacity="0.78" rx="1.5" />
            <text x={cx(i)} y={H - 9} fontSize="9" className="mono" textAnchor="middle" fill={r.k === g.maxPain ? "var(--copper)" : "var(--ink-3)"}>${r.k}</text></g>); })}
        <line x1={spotX} y1={padT} x2={spotX} y2={H - padB} stroke="var(--ink)" strokeDasharray="3 3" opacity="0.7" />
        <text x={spotX} y={padT - 4} fontSize="8.5" className="mono" textAnchor="middle" fill="var(--ink-2)">spot ${o.spot.toFixed(0)}</text>
        <text x={padL + 2} y={padT + 8} fontSize="8" className="mono" fill="var(--gn)">+ dealers dampen</text>
        <text x={padL + 2} y={H - padB - 2} fontSize="8" className="mono" fill="var(--rd)">− dealers amplify</text>
      </svg>
      <div className="otk-verdict-mini mono">
        <span className={pos ? "up" : "dn"}>{pos ? "POSITIVE γ" : "NEGATIVE γ"}</span> ·{" "}
        {pos ? <>dealers buy dips / sell rips → moves <b>dampened</b>; price gravitates toward <b className="copper">max-pain ${g.maxPain}</b>, pinning between <b className="dn">put wall ${g.putWall}</b> and <b className="up">call wall ${g.callWall}</b>. Below <b>γ-flip ${g.flip}</b> turns amplifying.</>
          : <>dealer hedging <b>amplifies</b> moves — expect bigger swings; reclaiming <b className="warn">γ-flip ${g.flip}</b> restores stability.</>}
        <span className="dim2"> · {o.dte}-DTE chain · informational, not advice.</span>
      </div>
      <div className="otk-gex-stock">
        <div className="otk-gex-stock-top"><span className="otk-gex-stock-tag mono">FOR THE STOCK</span></div>
        <div className="otk-gex-plain mono">
          {pos ? <>
            <div className="otk-gex-pl-hd"><b className="up">Likely calmer / range-bound near-term.</b> It tends to trade between two prices:</div>
            <div className="otk-gex-pl-row"><span className="otk-gex-pl-k dn">FLOOR ${g.putWall}</span> — dips here often get bought.</div>
            <div className="otk-gex-pl-row"><span className="otk-gex-pl-k up">CEILING ${g.callWall}</span> — rallies here often stall.</div>
            <div className="otk-gex-pl-row"><span className="otk-gex-pl-k warn">IF IT BREAKS ${g.flip}+</span> the calm is over — it can run.</div>
          </> : <>
            <div className="otk-gex-pl-hd"><b className="dn">Likely faster / trending near-term.</b> Moves get bigger:</div>
            <div className="otk-gex-pl-row"><span className="otk-gex-pl-k dn">${g.putWall} may not hold</span> — drops can keep falling.</div>
            <div className="otk-gex-pl-row"><span className="otk-gex-pl-k up">${g.callWall} may not cap it</span> — rallies can keep running.</div>
            <div className="otk-gex-pl-row"><span className="otk-gex-pl-k warn">WATCH ${g.flip}</span> — back above usually restores calm.</div>
          </>}
          <div className="otk-gex-pl-foot dim2">Near-term ({o.dte}-DTE) dealer positioning only. Informational — not advice.</div>
        </div>
        {window.AiExplain && <AiExplain build={gexPrompt} label="Explain with AI" tag="KAIROS · GEX" />}
      </div>
    </div>
  );
}

// ───── TAB 3: STRATEGIES & JOURNAL (real legs from the chain) ─────
function legInfo(o, strike, type) {
  const s = o.strikes.find(x => x.strike === strike) || o.strikes.reduce((a, x) => Math.abs(x.strike - strike) < Math.abs(a.strike - strike) ? x : a, o.strikes[0]);
  const leg = type === "call" ? (s.call || {}) : (s.put || {});
  const prem = (_on(leg.bid) != null && _on(leg.ask) != null) ? (leg.bid + leg.ask) / 2 : _on(leg.mark, 0);
  return { strike: s.strike, prem: prem || 0, delta: _on(leg.delta, 0), gamma: _on(leg.gamma, 0), theta: _on(leg.theta, 0), vega: _on(leg.vega, 0) };
}
function OtkBuild({ o }) {
  const [strat, setStrat] = useOT("Long Call");
  const ks = o.strikes.map(s => s.strike).sort((a, b) => a - b);
  const atmK = o.strike, above = ks.filter(k => k > atmK), below = ks.filter(k => k < atmK);
  const kUp1 = above[0] || atmK, kDn1 = below[below.length - 1] || atmK;
  const DEFS = {
    "Long Call": { bias: "bullish", legs: [{ type: "call", dir: 1, strike: atmK }] },
    "Long Put": { bias: "bearish", legs: [{ type: "put", dir: 1, strike: atmK }] },
    "Bull Call Spread": { bias: "bullish", legs: [{ type: "call", dir: 1, strike: atmK }, { type: "call", dir: -1, strike: kUp1 }] },
    "Bear Put Spread": { bias: "bearish", legs: [{ type: "put", dir: 1, strike: atmK }, { type: "put", dir: -1, strike: kDn1 }] },
    "Cash-Secured Put": { bias: "neutral-bull", legs: [{ type: "put", dir: -1, strike: kDn1 }] },
  };
  const def = DEFS[strat];
  const legs = def.legs.map(l => ({ ...l, ...legInfo(o, l.strike, l.type) }));
  const netDebit = legs.reduce((a, l) => a + l.dir * l.prem, 0);    // + = debit, − = credit (per share)
  const credit = netDebit < 0;
  const net = ["delta", "gamma", "theta", "vega"].reduce((acc, g) => { acc[g] = legs.reduce((a, l) => a + l.dir * l[g], 0); return acc; }, {});
  const payoff = S => legs.reduce((a, l) => { const intr = l.type === "call" ? Math.max(S - l.strike, 0) : Math.max(l.strike - S, 0); return a + l.dir * (intr - l.prem); }, 0) * 100;
  // sample payoff to get max/min/breakeven across a wide spot range
  const lo = o.spot * 0.80, hi = o.spot * 1.20, N = 120;
  const samp = []; for (let i = 0; i <= N; i++) { const S = lo + (hi - lo) * i / N; samp.push({ S, pl: payoff(S) }); }
  const maxGain = Math.max(...samp.map(p => p.pl)), maxLoss = Math.min(...samp.map(p => p.pl));
  const uncapped = strat === "Long Call" || strat === "Bull Call Spread" ? (payoff(hi) >= maxGain - 1 && strat === "Long Call") : false;
  const bes = []; for (let i = 1; i < samp.length; i++) { if ((samp[i - 1].pl < 0) !== (samp[i].pl < 0)) bes.push(+( (samp[i - 1].S + samp[i].S) / 2).toFixed(2)); }
  return (
    <div className="otk-grid">
      <div className="otk-card otk-card--wide">
        <div className="otk-card-h mono">STRATEGY BUILDER · legs priced off the live chain · real strikes &amp; marks</div>
        <div className="otk-sb-strats">{Object.keys(DEFS).map(s => <button key={s} className={`otk-sb-chip ${strat === s ? "is-on" : ""}`} onClick={() => setStrat(s)}>{s}</button>)}</div>
        <div className="otk-sb-legs">{legs.map((l, i) => <span key={i} className={`otk-sb-leg ${l.dir > 0 ? "buy" : "sell"}`}>{l.dir > 0 ? "+1" : "−1"} {l.type === "call" ? "C" : "P"} {l.strike}</span>)}<span className="otk-sb-bias mono dim2">· {def.bias} bias</span></div>
        <OtkPayoff samp={samp} spot={o.spot} bes={bes} />
        <div className="otk-sb-stats" style={{ marginTop: 8 }}>
          <div className="otk-sb-stat"><span className="mono dim2">{credit ? "Net credit" : "Net debit"}</span><span className={`mono ${credit ? "up" : ""}`}>${Math.abs(netDebit * 100).toFixed(0)}</span></div>
          <div className="otk-sb-stat"><span className="mono dim2">Max loss</span><span className="mono dn">−${Math.abs(maxLoss).toFixed(0)}</span></div>
          <div className="otk-sb-stat"><span className="mono dim2">Max gain</span><span className="mono up">{uncapped ? "uncapped ↑" : "+$" + maxGain.toFixed(0)}</span></div>
          <div className="otk-sb-stat"><span className="mono dim2">Breakeven</span><span className="mono">{bes.length ? bes.map(b => "$" + b.toFixed(2)).join(" / ") : "—"}</span></div>
        </div>
        <div className="otk-greeks" style={{ marginTop: 8 }}>
          {[["net Δ", net.delta], ["net Γ", net.gamma], ["net Θ/d", net.theta], ["net ν", net.vega]].map(([k, v], i) => (
            <div key={i} className="otk-greek"><span className="mono dim2">{k}</span><span className={`mono otk-greek-v ${v >= 0 ? "" : "dn"}`}>{v >= 0 ? "+" : ""}{(k.includes("Θ") || k.includes("ν") ? "$" : "")}{v.toFixed(k.includes("Γ") ? 4 : 3)}</span></div>
          ))}
        </div>
        <div className="mono dim2" style={{ fontSize: 10.5, marginTop: 8 }}>Every leg is the live mid from the real chain; payoff is at expiry. Net greeks sum the legs. Verify exact fills in your broker.</div>
      </div>
      <div className="otk-card">
        <div className="otk-card-h mono">CONTRACT · live quote + smart fill</div>
        <div className="otk-stats">
          {[["Strike", "$" + o.strike], ["Expiry", o.exp.expiration], ["Bid", o.bid != null ? "$" + o.bid.toFixed(2) : "—"], ["Ask", o.ask != null ? "$" + o.ask.toFixed(2) : "—"],
            ["Mid (target)", (o.bid != null && o.ask != null) ? "$" + ((o.bid + o.ask) / 2).toFixed(2) : "—"],
            ["Spread", (o.bid != null && o.ask != null) ? "$" + (o.ask - o.bid).toFixed(2) + ` (${o.spreadPct}%)` : "—"],
            ["Open int", o.oi != null ? o.oi.toLocaleString() : "—"]].map(([k, v], i) => (
            <div key={i} className="otk-stat"><span className="mono dim2">{k}</span><span className="mono">{v}</span></div>
          ))}
        </div>
        <div className="otk-verdict-mini mono">{(o.bid != null && o.ask != null)
          ? <><span className={o.spreadPct < 10 ? "up" : "warn"}>{o.spreadPct < 10 ? "TIGHT" : "WIDE"}</span> · work a limit at the mid <b className="cy">${((o.bid + o.ask) / 2).toFixed(2)}</b>{o.spreadPct >= 10 ? <>, then up to <b>${((o.bid + o.ask) / 2 + (o.ask - o.bid) * 0.25).toFixed(2)}</b> (mid + ¼ spread)</> : ""}</>
          : "no live bid/ask"}</div>
      </div>
      <div className="otk-card otk-card--wide">
        <div className="otk-card-h mono">TRADE JOURNAL · per-ticker notes</div>
        <OtkJournal symbol={o.sym} />
      </div>
    </div>
  );
}

// payoff-at-expiry curve for the selected structure
function OtkPayoff({ samp, spot, bes }) {
  const W = 600, H = 150, padL = 44, padR = 12, padT = 12, padB = 22;
  const xs = samp.map(p => p.S), pls = samp.map(p => p.pl);
  const xmin = Math.min(...xs), xmax = Math.max(...xs);
  const ymin = Math.min(...pls, 0), ymax = Math.max(...pls, 0);
  const x = S => padL + (S - xmin) / (xmax - xmin) * (W - padL - padR);
  const y = v => padT + (1 - (v - ymin) / (ymax - ymin || 1)) * (H - padT - padB);
  const path = samp.map((p, i) => `${i ? "L" : "M"} ${x(p.S).toFixed(1)} ${y(p.pl).toFixed(1)}`).join(" ");
  return (
    <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} className="otk-mini-svg" preserveAspectRatio="none" style={{ marginTop: 6 }}>
      <line x1={padL} y1={y(0)} x2={W - padR} y2={y(0)} stroke="var(--ink-3)" opacity="0.5" />
      <text x={padL - 4} y={y(0) + 3} fontSize="8" className="mono" textAnchor="end" fill="var(--ink-3)">$0</text>
      <path d={path} fill="none" stroke="var(--copper)" strokeWidth="2" />
      <line x1={x(spot)} y1={padT} x2={x(spot)} y2={H - padB} stroke="var(--ink)" strokeDasharray="3 3" opacity="0.6" />
      <text x={x(spot)} y={H - 7} fontSize="8" className="mono" textAnchor="middle" fill="var(--ink-2)">spot ${spot.toFixed(0)}</text>
      {bes.map((b, i) => <g key={i}><line x1={x(b)} y1={padT} x2={x(b)} y2={H - padB} stroke="var(--amber, #d9a441)" strokeDasharray="2 2" opacity="0.7" /><text x={x(b)} y={padT + 8} fontSize="8" className="mono" textAnchor="middle" fill="var(--amber, #d9a441)">BE ${b.toFixed(0)}</text></g>)}
    </svg>
  );
}

function OtkJournal({ symbol }) {
  const key = "otk-journal-" + (symbol || "x");
  const [val, setVal] = useOT(() => { try { return localStorage.getItem(key) || ""; } catch (e) { return ""; } });
  return (
    <>
      <textarea className="otk-journal mono" placeholder="Why this trade? · entry rationale · invalidation triggers · post-trade review"
        value={val} onChange={e => { setVal(e.target.value); try { localStorage.setItem(key, e.target.value); } catch (e2) {} }} />
      <div className="mono dim2" style={{ fontSize: 9 }}>auto-saves to localStorage per ticker{symbol ? ` · ${symbol}` : ""}</div>
    </>
  );
}

window.LensOptions = LensOptions;

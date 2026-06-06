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
  // mode → target DTE: swing = weekly, position = ~2-3mo, invest = LEAP (~9mo+)
  const wantDte = mode === "POSITION" ? 75 : mode === "INVESTMENT" ? 270 : 5;
  const [dte, setDte] = useOT(null);
  // mode is the driver: re-target the DTE whenever the horizon changes or the chain
  // loads. Manual chip clicks set dte directly and persist until the next mode change.
  React.useEffect(() => {
    if (!exps.length) return;
    const pick = exps.reduce((a, e) => Math.abs(e.dte - wantDte) < Math.abs(a.dte - wantDte) ? e : a, exps[0]);
    setDte(pick.dte);
  }, [mode, exps.length]);

  // recommend the DIRECTION from the stock's own bias — a call shouldn't fight a
  // bearish trend. User can override with the call/put toggle (side != null).
  const cv = window.compositeVerdict ? window.compositeVerdict(ticker, mode) : null;
  const bias = cv ? (cv.net >= 55 ? "bull" : cv.net < 45 ? "bear" : "neutral") : "neutral";
  const recSide = bias === "bear" ? "put" : "call";
  const [side, setSide] = useOT(null);            // null = follow recommendation
  const effSide = side || recSide;
  React.useEffect(() => { setSide(null); }, [ticker.symbol, mode]);   // reset override on ticker/mode change

  // build the REAL ATM ticket (call OR put) from the selected expiration
  const o = useOTm(() => {
    if (!chain || !exps.length) return null;
    const spot = _on(chain.spot, _on(ticker.price));
    const exp = exps.find(e => e.dte === dte) || exps[exps.length - 1];
    const isPut = effSide === "put";
    const strikes = (exp.strikes || []).filter(s => s && (isPut ? s.put : s.call));
    if (!spot || !strikes.length) return null;
    const atm = strikes.reduce((a, s) => Math.abs(s.strike - spot) < Math.abs(a.strike - spot) ? s : a, strikes[0]);
    const leg = (isPut ? atm.put : atm.call) || {}, other = (isPut ? atm.call : atm.put) || {};
    const mid = (_on(leg.bid) != null && _on(leg.ask) != null && leg.ask > 0) ? +(((leg.bid + leg.ask) / 2)).toFixed(2) : _on(leg.mark);
    const prem = mid != null ? mid : _on(leg.mark, 0);
    const iv = _on(leg.iv, _on(chain.atm && chain.atm.iv));
    const be = isPut ? +(atm.strike - prem).toFixed(2) : +(atm.strike + prem).toFixed(2);
    const spread = (_on(leg.bid) != null && _on(leg.ask) != null && leg.ask > 0) ? leg.ask - leg.bid : null;
    const spreadPct = (spread != null && prem > 0) ? +(spread / prem * 100).toFixed(1) : null;
    const impMove = iv != null ? +(iv / 100 * Math.sqrt(Math.max(dte, 1) / 252) * 100).toFixed(1) : null;
    // POP = P(profitable at expiry): call → P(S>BE) = N(d2); put → P(S<BE) = 1−N(d2).
    const popRaw = (iv != null && prem > 0 && spot > 0) ? bsPOP(spot, be, Math.max(dte, 1) / 252, iv / 100) : null;
    const pop = popRaw == null ? null : (isPut ? 100 - popRaw : popRaw);
    const erDays = ticker.earnings && ticker.earnings.days != null ? ticker.earnings.days : null;
    const erInWindow = erDays != null && erDays <= dte;
    return {
      spot, strikes, exp, prem, strike: atm.strike, be, iv, dte, sym: ticker.symbol, side: effSide, isPut,
      delta: _on(leg.delta), gamma: _on(leg.gamma), theta: _on(leg.theta), vega: _on(leg.vega),
      oi: _on(leg.oi), vol: _on(leg.vol), bid: _on(leg.bid), ask: _on(leg.ask), mark: _on(leg.mark),
      putMark: _on(other.mark), spread, spreadPct, impMove, pop, erDays, erInWindow,
      hv20: _on(chain.hv20), hv30: _on(chain.hv30),
      ivVsHv: (iv != null && _on(chain.hv20) != null) ? +(iv - chain.hv20).toFixed(1) : null,
      source: chain.source, ts: chain.ts,
    };
  }, [chain, dte, ticker, effSide]);

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
          <div className="otk-ticket-h mono">⊞ TRADE TICKET · <span className="cy">Long {o.isPut ? "Put" : "Call"} (ATM)</span>
            <span className="otk-side-toggle mono">
              <button className={!o.isPut ? "is-on" : ""} onClick={() => setSide("call")}>Call</button>
              <button className={o.isPut ? "is-on" : ""} onClick={() => setSide("put")}>Put</button>
            </span>
          </div>
          {side == null && <div className="mono dim2" style={{ fontSize: 9, marginTop: 1 }}>auto-picked {recSide} to match the stock's {bias} read · tap to override</div>}
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
            <div className="otk-hero"><div className="mono dim2">P(PROFIT)</div><div className="mono otk-hero-v">{o.pop != null ? o.pop + "%" : "—"}</div><div className="mono dim2" style={{ fontSize: 8 }}>at expiry</div></div>
            <div className="otk-hero"><div className="mono dim2">θ/DAY</div><div className="mono otk-hero-v dn">{o.theta != null ? "$" + o.theta.toFixed(2) : "—"}</div></div>
          </div>
        </div>
      </div>

      {horizonMismatch && (
        <div className="otk-horizon mono">⚑ {mode === "INVESTMENT" ? "Invest" : "Position"} horizon: the live feed only has near-term contracts (≤{maxDte} DTE). Options aren't suited to a multi-month thesis here — this shows the nearest weekly for context, not a {mode === "INVESTMENT" ? "long-term" : "multi-month"} holding.</div>
      )}
      <OptQuickTake ticker={ticker} mode={mode} o={o} exps={exps} />
      <RetailPlan o={o} contracts={contracts} />

      <div className="otk-tabs">
        {TABS.map(([id, l]) => <button key={id} className={`otk-tab ${tab === id ? "is-on" : ""}`} onClick={() => setTab(id)}>{l}</button>)}
      </div>

      <div className="otk-body">
        {tab === "chain" && <OtkChainGreeks o={o} exps={exps} />}
        {tab === "gex" && <OtkGEX o={o} exps={exps} />}
        {tab === "build" && <OtkBuild o={o} />}
      </div>
    </div>
  );
}

// ───── Options Quick Take — "should I do this trade?" decision layer ─────
function OptQuickTake({ ticker, mode, o, exps }) {
  const cv = window.compositeVerdict ? window.compositeVerdict(ticker, mode) : null;
  const net = cv ? cv.net : null;
  const biasBull = net != null ? net >= 55 : null, biasBear = net != null ? net < 45 : null;
  const opt = o.isPut ? "put" : "call";
  const beMove = (o.be / o.spot - 1) * 100;            // % to breakeven (neg for puts)
  const beAbs = Math.abs(beMove);
  const imp = o.impMove;                                // implied move over the DTE
  const achievable = imp != null ? beAbs <= imp : null;
  const aligned = (o.isPut && biasBear) || (!o.isPut && biasBull);
  const fights = (o.isPut && biasBull) || (!o.isPut && biasBear);
  const gex = useOTm(() => { try { return computeGEX(o.spot, exps); } catch (e) { return null; } }, [o.spot, exps]);
  const F = [];
  if (net != null) F.push({ k: "Direction", v: aligned ? 1 : fights ? -1 : 0, text: aligned ? `${opt} aligns with the stock's ${biasBull ? "bullish" : "bearish"} read (${Math.round(net)}/100)` : fights ? `${opt} fights the stock's ${biasBull ? "bullish" : "bearish"} read (${Math.round(net)}/100) — wrong direction` : `stock is mixed (${Math.round(net)}/100) — no directional tailwind` });
  if (achievable != null) F.push({ k: "Cost vs move", v: achievable ? 1 : -1, text: `needs ${beMove >= 0 ? "+" : ""}${beMove.toFixed(1)}% (${o.isPut ? "a drop" : "a rise"}) by expiry; market prices ±${imp}% → ${achievable ? "achievable" : "a stretch"}` });
  if (o.ivVsHv != null) F.push({ k: "Volatility", v: o.ivVsHv <= -5 ? 1 : o.ivVsHv >= 8 ? -1 : 0, text: `IV ${o.iv.toFixed(0)}% vs realized ${o.hv20.toFixed(0)}% — ${o.ivVsHv <= -5 ? "cheap, good for buying premium" : o.ivVsHv >= 8 ? "rich, you overpay for vol" : "fair"}` });
  F.push({ k: "Time", v: o.dte >= 5 ? 0 : -1, text: o.dte <= 1 ? `${o.dte}-DTE — expiry-day gamma/theta, all-or-nothing` : o.dte < 5 ? `${o.dte}-DTE — theta bleeds fast, needs an immediate move` : `${o.dte}-DTE — time to be right` });
  if (o.spreadPct != null) F.push({ k: "Liquidity", v: (o.spreadPct < 15 && (o.oi || 0) >= 500) ? 1 : (o.spreadPct < 25) ? 0 : -1, text: `spread ${o.spreadPct}% of premium · ATM OI ${(o.oi || 0).toLocaleString()}` });
  if (o.erInWindow) F.push({ k: "Earnings", v: -1, text: `earnings in ${o.erDays}d, inside this expiry — expect IV crush after the print` });
  const fails = F.filter(f => f.v < 0).length, passes = F.filter(f => f.v > 0).length;
  // a directional bet can't be "reasonable" without a directional edge
  const dirOk = aligned, dirBad = fights;
  const verdict = (fails === 0 && passes >= 2 && dirOk) ? "REASONABLE SETUP" : (fails <= 1 && !dirBad) ? "TRADEABLE · WITH CARE" : "POOR SETUP";
  const tone = (fails === 0 && dirOk) ? "gn" : (fails <= 1 && !dirBad) ? "amb" : "rd";
  const expShort = (o.exp.expiration || "").slice(5);
  // structure recommendation from bias × IV
  const ivRich = o.ivVsHv != null && o.ivVsHv >= 8, ivCheap = o.ivVsHv != null && o.ivVsHv <= -5;
  const rec = (net == null || (!biasBull && !biasBear))
    ? `No clear directional edge — options aren't the obvious play here; consider a defined-risk spread or skip.`
    : ivRich
      ? `Vol is rich — instead of paying up for a single long ${opt}, a ${o.isPut ? "bear put" : "bull call"} debit spread cuts the vol cost.`
      : ivCheap
        ? `Bias is ${biasBull ? "bullish" : "bearish"} and vol is cheap — a long ${opt} is a clean way to express it.`
        : `Bias is ${biasBull ? "bullish" : "bearish"}; a long ${opt} works, or a debit spread to lower cost.`;
  const plain = `A ${o.dte}-DTE ATM ${opt} costs $${(o.prem * 100).toFixed(0)} and needs ${ticker.symbol} to ${o.isPut ? "fall" : "rise"} ${beAbs.toFixed(1)}% by ${expShort} just to break even` +
    (imp != null ? ` — the market is pricing a ±${imp}% move, so breakeven is ${achievable ? "within reach" : "a stretch"}.` : ".") +
    ` Buying options is a low-probability bet: P(profit) ≈ ${o.pop != null ? o.pop + "%" : "—"} — you're paying for a big, fast move.`;
  return (
    <div className={`qt qt--${tone}`} style={{ margin: "0 0 12px" }}>
      <div className="qt-grid" style={{ gridTemplateColumns: "150px 1fr 170px" }}>
        <div className="qt-verdict">
          <div className="label-cap">Trade read</div>
          <div className={`qt-v mono kpi-tone--${tone}`} style={{ fontSize: 20 }}>{verdict}</div>
          <div className="qt-conf mono dim2">{passes} green · {fails} red · long ATM {opt}</div>
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
          <div className="qt-plan-row"><span className="mono dim2">Move needed</span><span className={`mono ${achievable ? "up" : "dn"}`}>{beMove >= 0 ? "+" : ""}{beMove.toFixed(1)}%</span></div>
          <div className="qt-plan-row"><span className="mono dim2">Implied move</span><span className="mono">±{imp != null ? imp : "—"}%</span></div>
          <div className="qt-plan-row"><span className="mono dim2">P(profit)</span><span className="mono">{o.pop != null ? o.pop + "%" : "—"}</span></div>
        </div>
      </div>
      <div className={`otk-rec mono kpi-tone--${tone}`}>▸ {rec}</div>
      <div className="qt-plain mono">{plain}{gex ? ` Dealer gamma is ${gex.total >= 0 ? (gex.putWall === gex.callWall ? `positive — price tends to pin near $${gex.maxPain}` : `positive — price tends to pin between $${Math.min(gex.putWall, gex.callWall)} and $${Math.max(gex.putWall, gex.callWall)}`) : `negative — expect amplified, trending moves`}.` : ""}</div>
    </div>
  );
}

function OtkCheck({ ok, bad, warn, neutral, text }) {
  const cls = ok ? "ok" : bad ? "bad" : warn ? "warn" : "warn";
  const icon = ok ? "✓" : bad ? "⚠" : "·";
  return <div className={`otk-chk ${cls} mono`}><span>{icon}</span> {text}</div>;
}

// ───── Retail plan — 3 plain outcomes · sizing guardrail · vs-shares · exits ─────
function RetailPlan({ o, contracts }) {
  const sigma = (o.iv != null ? o.iv : 40) / 100, T = Math.max(o.dte, 1) / 252;
  const cost = o.prem * 100 * contracts;
  // if right: stock makes ~1 implied move in the trade's direction, value at expiry
  const targetS = o.isPut ? o.spot * (1 - (o.impMove || 5) / 100) : o.spot * (1 + (o.impMove || 5) / 100);
  const intrTgt = o.isPut ? Math.max(o.strike - targetS, 0) : Math.max(targetS - o.strike, 0);
  const winPL = (intrTgt - o.prem) * 100 * contracts;
  // if flat: BS value with half the time left, spot unchanged → theta cost
  const flatVal = (o.isPut ? bsPut : bsCall)(o.spot, o.strike, T / 2, sigma);
  const flatPL = (flatVal - o.prem) * 100 * contracts;
  const shares100 = o.spot * 100 * contracts;
  const lev = shares100 / cost;
  const NAV = (window.__BV && typeof window.__BV.nav === "number") ? window.__BV.nav : null;
  const riskBudget = NAV ? NAV * 0.02 : null;          // 2%-of-book per options trade
  const maxCt = riskBudget ? Math.max(0, Math.floor(riskBudget / (o.prem * 100))) : null;
  const bookPct = NAV ? (cost / NAV * 100) : null;
  const oversized = maxCt != null && contracts > maxCt;
  const M = v => (v >= 0 ? "+$" : "−$") + Math.abs(Math.round(v)).toLocaleString();
  return (
    <div className="otk-retail">
      <div className="otk-rp-outcomes">
        <div className="otk-rp-o otk-rp-o--gn">
          <div className="label-cap">If you're right</div>
          <div className="otk-rp-v mono up">{M(winPL)}</div>
          <div className="mono dim2">{o.sym} {o.isPut ? "falls" : "rises"} to ~${targetS.toFixed(0)} (its implied move) by expiry</div>
        </div>
        <div className="otk-rp-o otk-rp-o--amb">
          <div className="label-cap">If it sits still</div>
          <div className="otk-rp-v mono dn">{M(flatPL)}</div>
          <div className="mono dim2">theta bleed by the half-way point — time is working against you</div>
        </div>
        <div className="otk-rp-o otk-rp-o--rd">
          <div className="label-cap">Worst case (max loss)</div>
          <div className="otk-rp-v mono dn">−${Math.round(cost).toLocaleString()}</div>
          <div className="mono dim2">the whole premium — a long {o.isPut ? "put" : "call"} can go to zero</div>
        </div>
      </div>
      <div className="otk-rp-rows">
        <div className={`otk-rp-row ${oversized ? "otk-rp-warn" : ""} mono`}>
          <span className="otk-rp-k">Size</span>
          {riskBudget != null
            ? <span>Risking 2% of your ${Math.round(NAV).toLocaleString()} book is <b>${Math.round(riskBudget).toLocaleString()}</b> → up to <b className={oversized ? "dn" : "up"}>{maxCt}</b> contract{maxCt === 1 ? "" : "s"}. You have <b>{contracts}</b> = ${Math.round(cost).toLocaleString()}{bookPct != null ? ` (${bookPct.toFixed(1)}% of book)` : ""}.{oversized ? " ⚠ over the 2% guardrail." : ""}</span>
            : <span>Max risk is the full <b>${Math.round(cost).toLocaleString()}</b> premium. Rule of thumb: risk ≤ 1–2% of your account per options trade.</span>}
        </div>
        <div className="otk-rp-row mono">
          <span className="otk-rp-k">vs shares</span>
          <span>${Math.round(cost).toLocaleString()} controls {100 * contracts} shares (worth ${Math.round(shares100).toLocaleString()}) — <b>{lev.toFixed(0)}×</b> leverage, but it expires {o.exp.expiration} and decays daily. Buying the shares can't go to zero on time.</span>
        </div>
        <div className="otk-rp-row mono">
          <span className="otk-rp-k">Exit plan</span>
          <span>Take profit at <b className="up">+50–100%</b> of premium · cut at <b className="dn">−50%</b> · close before expiry week ({Math.max(1, o.dte - 5)}+ days held = gamma/theta danger zone){o.erInWindow ? " · close before the earnings print (IV crush)" : ""}.</span>
        </div>
      </div>
    </div>
  );
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
function bsPut(S, K, T, sigma, r = 0.04) { if (T <= 0) return Math.max(K - S, 0); return bsCall(S, K, T, sigma, r) - S + K * Math.exp(-r * T); }
// risk-neutral probability the call finishes above breakeven by expiry = N(d2|K=BE)
function bsPOP(S, BE, T, sigma, r = 0.04) { if (T <= 0 || sigma <= 0 || S <= 0 || BE <= 0) return S > BE ? 100 : 0; const d2 = (Math.log(S / BE) + (r - sigma * sigma / 2) * T) / (sigma * Math.sqrt(T)); return Math.round(Math.max(1, Math.min(99, bsNormCdf(d2) * 100))); }

// helper: ATM call/put mid from the live chain (for strategy switches)
function _atmMid(o, type) {
  const s = o.strikes.find(x => x.strike === o.strike) || o.strikes[0];
  const leg = (type === "put" ? s.put : s.call) || {};
  return (_on(leg.bid) != null && _on(leg.ask) != null) ? +(((leg.bid + leg.ask) / 2)).toFixed(2) : _on(leg.mark, 0);
}
const OTK_STRATS = {
  "Long Call (bullish)": { dir: "buy", otype: "call" },
  "Long Put (bearish)": { dir: "buy", otype: "put" },
  "Covered Call (income)": { dir: "write", otype: "call" },
  "Cash-Secured Put": { dir: "write", otype: "put" },
};
function OtkProfitGrid({ o }) {
  const [strat, setStrat] = useOT(o.isPut ? "Long Put (bearish)" : "Long Call (bullish)");
  const def = OTK_STRATS[strat] || OTK_STRATS["Long Call (bullish)"];
  const [strike, setStrike] = useOT(o.strike);
  const [prem, setPrem] = useOT(o.prem);
  const [contracts, setContracts] = useOT(1);
  const [ivScen, setIvScen] = useOT("flat");          // -10 | flat | +10 | crush
  // re-sync to the live ticket when the underlying contract changes
  React.useEffect(() => { setStrike(o.strike); setPrem(_atmMid(o, def.otype)); }, [o.strike, o.dte, o.sym, strat]);
  const baseSigma = (o.iv != null ? o.iv : 40) / 100;
  const sigma = Math.max(0.03, ivScen === "crush" ? baseSigma * 0.6 : ivScen === "-10" ? baseSigma - 0.10 : ivScen === "+10" ? baseSigma + 0.10 : baseSigma);
  const dteN = Math.max(1, o.dte || 5);
  const isPut = def.otype === "put", isWrite = def.dir === "write";
  const fn = isPut ? bsPut : bsCall;
  const beAtExp = isPut ? +(strike - prem).toFixed(2) : +(strike + prem).toFixed(2);
  // day columns: Today → ~6 steps → EXPIRY
  const maxCol = Math.min(30, dteN), step = Math.max(1, Math.round(maxCol / 6));
  const cols = []; for (let d = 0; d <= maxCol && d < dteN; d += step) cols.push(d); cols.push(dteN);
  const colLbl = d => d === 0 ? "Today" : d >= dteN ? "EXPIRY" : "+" + d + "d";
  // price rows: spot ±7.5%, high → low
  const hiP = o.spot * 1.075, loP = o.spot * 0.925, NR = 21;
  const prices = []; for (let i = 0; i < NR; i++) prices.push(+(hiP - (hiP - loP) * i / (NR - 1)).toFixed(prices.length && hiP < 50 ? 2 : 0));
  const tgt = isPut ? o.spot * (1 - (o.impMove || 5) / 100) : o.spot * (1 + (o.impMove || 5) / 100);
  const spotRow = prices.reduce((bi, p, i) => Math.abs(p - o.spot) < Math.abs(prices[bi] - o.spot) ? i : bi, 0);
  const tgtRow = prices.reduce((bi, p, i) => Math.abs(p - tgt) < Math.abs(prices[bi] - tgt) ? i : bi, 0);
  const cellPL = (S, dHeld) => {
    const Trem = Math.max(0, (dteN - dHeld)) / 252;
    const val = fn(S, strike, Trem, sigma);
    let pl = (val - prem) / Math.max(0.01, prem) * 100;
    if (isWrite) pl = Math.max(-400, -pl);   // short: invert, floor the visual
    return pl;
  };
  const cellStyle = pl => { const c = pl >= 0 ? "var(--gn)" : "var(--rd)"; const op = Math.min(0.4, Math.abs(pl) / 130 * 0.4 + 0.04); return { background: `color-mix(in oklab, ${c} ${Math.round(op * 100)}%, transparent)`, color: pl >= 0 ? "var(--gn)" : "var(--rd)" }; };
  const totalCost = prem * 100 * contracts;
  return (
    <div className="otk-pcalc">
      <div className="otk-pc-ctrl mono">
        <select value={strat} onChange={e => setStrat(e.target.value)}>{Object.keys(OTK_STRATS).map(s => <option key={s}>{s}</option>)}</select>
        <span className="otk-pc-seg"><button className={!isWrite ? "is-on" : ""} onClick={() => setStrat(isPut ? "Long Put (bearish)" : "Long Call (bullish)")}>Buy</button><button className={isWrite ? "is-on" : ""} onClick={() => setStrat(isPut ? "Cash-Secured Put" : "Covered Call (income)")}>Write</button></span>
        <span className="otk-pc-seg"><button className={!isPut ? "is-on" : ""} onClick={() => setStrat(isWrite ? "Covered Call (income)" : "Long Call (bullish)")}>Call</button><button className={isPut ? "is-on" : ""} onClick={() => setStrat(isWrite ? "Cash-Secured Put" : "Long Put (bearish)")}>Put</button></span>
        <label>Strike <input type="number" value={strike} onChange={e => setStrike(+e.target.value)} /></label>
        <label>Premium <input type="number" step="0.05" value={prem} onChange={e => setPrem(+e.target.value)} /></label>
        <label>Contracts <input type="number" min="1" value={contracts} onChange={e => setContracts(Math.max(1, +e.target.value))} /></label>
        <span className="otk-pc-cost">Cost <b className="cy">${totalCost.toLocaleString()}</b></span>
      </div>
      <div className="otk-pc-iv mono">
        <span className="dim2">IV scenario</span>
        {[["-10", "−10 vol"], ["flat", "IV flat"], ["+10", "+10 vol"], ["crush", "⚡ ER crush"]].map(([k, l]) => <button key={k} className={ivScen === k ? "is-on" : ""} onClick={() => setIvScen(k)}>{l}</button>)}
        <span className="dim2" style={{ marginLeft: "auto" }}>σ now <b>{(baseSigma * 100).toFixed(0)}%</b>{ivScen !== "flat" ? ` → ${(sigma * 100).toFixed(0)}%` : ""}</span>
      </div>
      <div className="otk-pc-scroll">
        <table className="otk-pc-tbl mono">
          <thead><tr><th>Price</th>{cols.map((d, i) => <th key={i} className="r">{colLbl(d)}</th>)}<th className="r">±% spot</th></tr></thead>
          <tbody>{prices.map((p, ri) => (
            <tr key={ri} className={ri === spotRow ? "is-spot" : ri === tgtRow ? "is-tgt" : ""}>
              <td className="otk-pc-px">${p.toLocaleString()}{ri === spotRow ? <span className="otk-pc-tag cy">spot</span> : ri === tgtRow ? <span className="otk-pc-tag warn">target</span> : ""}</td>
              {cols.map((d, ci) => { const pl = cellPL(p, d); return <td key={ci} className="r" style={cellStyle(pl)}>{pl >= 0 ? "+" : ""}{pl.toFixed(0)}</td>; })}
              <td className="r dim2">{p >= o.spot ? "+" : ""}{((p / o.spot - 1) * 100).toFixed(1)}%</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <div className="mono dim2" style={{ fontSize: 10.5, marginTop: 6 }}>Each cell = % return on the ${prem.toFixed(2)} premium ({strike}{isPut ? "P" : "C"} · {dteN}DTE) at that price &amp; date, IV held at σ {(sigma * 100).toFixed(0)}%. <b className="cy">Cyan</b> = live spot; <b className="warn">amber</b> = implied-move target (${tgt.toFixed(0)}). EXPIRY = intrinsic. Breakeven at expiry <b>${beAtExp.toFixed(2)}</b> ({isPut ? "" : "+"}{((beAtExp / o.spot - 1) * 100).toFixed(1)}%).</div>
    </div>
  );
}

// ───── TAB 2: DEALER GAMMA (real, from the live chain) ─────
function computeGEX(spot, exps) {
  if (!spot || !exps || !exps.length) return null;
  const dol = 100 * spot * (spot * 0.01);   // $ per 1% move per (γ × OI) contract
  const agg = {};
  exps.forEach(e => (e.strikes || []).forEach(s => {
    const k = s.strike; if (k == null) return;
    const c = s.call || {}, p = s.put || {};
    const cOi = _on(c.oi, 0), pOi = _on(p.oi, 0), cG = _on(c.gamma, 0), pG = _on(p.gamma, 0);
    const a = agg[k] || (agg[k] = { net: 0, callOI: 0, putOI: 0 });
    a.net += (-cOi * cG + pOi * pG) * dol;   // dealers short calls (−), short puts (+)
    a.callOI += cOi; a.putOI += pOi;
  }));
  let rows = Object.keys(agg).map(k => ({ k: +k, ...agg[k] })).sort((a, b) => a.k - b.k);
  const win = rows.filter(r => r.k >= spot * 0.88 && r.k <= spot * 1.14);
  rows = win.length >= 4 ? win : rows;
  if (rows.length > 13) {
    const ci = rows.reduce((bi, r, i) => Math.abs(r.k - spot) < Math.abs(rows[bi].k - spot) ? i : bi, 0);
    rows = rows.slice(Math.max(0, ci - 6), ci + 7);
  }
  if (!rows.length) return null;
  const callWall = rows.reduce((a, b) => b.callOI > a.callOI ? b : a).k;
  const putWall = rows.reduce((a, b) => b.putOI > a.putOI ? b : a).k;
  let flip = spot; for (let i = 1; i < rows.length; i++) { if ((rows[i - 1].net < 0) !== (rows[i].net < 0)) { flip = rows[i].k; break; } }
  let maxPain = rows[0].k, minPay = Infinity;
  rows.forEach(r => { let pay = 0; rows.forEach(s => { pay += Math.max(0, r.k - s.k) * s.callOI + Math.max(0, s.k - r.k) * s.putOI; }); if (pay < minPay) { minPay = pay; maxPain = r.k; } });
  const total = rows.reduce((a, b) => a + b.net, 0);
  return { rows, callWall, putWall, flip, maxPain, total };
}
function OtkGEX({ o, exps }) {
  const g = useOTm(() => computeGEX(o.spot, exps), [o.spot, exps]);
  if (!g) return <div className="otk-card otk-card--wide"><div className="mono dim2" style={{ padding: 16 }}>Not enough open-interest in the live chain to compute dealer gamma.</div></div>;
  const W = 720, H = 234, padL = 16, padR = 16, padT = 30, padB = 30;
  const n = g.rows.length, bw = (W - padL - padR) / n;
  const maxAbs = Math.max(...g.rows.map(r => Math.abs(r.net)), 1);
  const y0 = padT + (H - padT - padB) / 2, yh = (H - padT - padB) / 2;
  const cx = i => padL + bw * (i + 0.5);
  const spotI = (o.spot - g.rows[0].k) / Math.max(1e-6, (g.rows[n - 1].k - g.rows[0].k)) * (n - 1);
  const spotX = padL + bw * (spotI + 0.5);
  const pos = g.total >= 0;
  const fmtMM = v => (v >= 0 ? "+" : "−") + "$" + Math.abs(v / 1e6).toFixed(1) + "mm";
  const idxOf = k => g.rows.findIndex(r => r.k === k);
  const marks = [{ k: g.putWall, lbl: "PUT WALL", c: "var(--rd)" }, { k: g.callWall, lbl: "CALL WALL", c: "var(--gn)" }, { k: g.flip, lbl: "γ-FLIP", c: "var(--amber, #d9a441)" }].filter(m => idxOf(m.k) >= 0);
  const slots = {};
  const gexPrompt = () => `Explain options dealer-gamma (GEX) to a BEGINNER STOCK trader (they don't trade options) in plain, simple English. Use the live numbers for ${o.sym} below: 3-4 short sentences, use the actual prices, end with ONE practical takeaway for someone trading the shares.
Spot: $${o.spot.toFixed(2)} · Net GEX: ${fmtMM(g.total)} (${pos ? "positive — moves dampened" : "negative — moves amplified"}) · Call wall: $${g.callWall} · Put wall: $${g.putWall} · Flip: $${g.flip} · Max pain: $${g.maxPain}`;
  return (
    <div className="otk-card otk-card--wide">
      <div className="otk-card-h mono">DEALER GAMMA (GEX) · by strike · <span className="dim2">computed from chain OI × γ (all expirations)</span></div>
      <div className="otk-gex-kpis">
        <div className="otk-gex-kpi"><span className="mono dim2">NET GEX</span><span className={`mono otk-gex-kv ${pos ? "up" : "dn"}`}>{fmtMM(g.total)}</span><span className="mono dim2" style={{ fontSize: 8 }}>{pos ? "stabilizing" : "amplifying"}</span></div>
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
        {marks.map((m, mi) => { const i = idxOf(m.k); const x = cx(i); const slot = (slots[i] = (slots[i] || 0) + 1); const ly = padT - 18 + (slot - 1) * 9;
          return (<g key={mi}><line x1={x} y1={padT} x2={x} y2={H - padB} stroke={m.c} strokeWidth="1.2" opacity="0.45" /><text x={x} y={ly} fontSize="7.5" className="mono" textAnchor="middle" fill={m.c} fontWeight="700">{m.lbl}</text></g>); })}
        <line x1={spotX} y1={padT} x2={spotX} y2={H - padB} stroke="var(--ink)" strokeDasharray="3 3" opacity="0.75" />
        <text x={spotX} y={padT - 4} fontSize="8.5" className="mono" textAnchor="middle" fill="var(--ink-2)">spot ${o.spot.toFixed(0)}</text>
        <text x={padL + 2} y={y0 - yh + 8} fontSize="8" className="mono" fill="var(--gn)">+ dealers dampen</text>
        <text x={padL + 2} y={y0 + yh - 2} fontSize="8" className="mono" fill="var(--rd)">− dealers amplify</text>
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

// lens-investment.jsx — Investment · Value  (REAL DATA)
// Fair value from a multiples anchor (peer P/E ×2 + Graham) + a reverse-DCF check,
// quality scorecard, real same-industry peer cohort, real 5-yr statements + capital
// allocation, data-driven bull/bear, real earnings calendar. Nothing seeded.
//
// Sources: ticker._fund (EODHD highlights/valuation/shares/income_5y/cashflow_5y),
// /api/peers (data/fundamentals.db cohort), compositeVerdict (engine INVESTMENT read).

// ── parse + format helpers ──
function _P(v) { const n = typeof v === "string" ? parseFloat(v) : v; return (typeof n === "number" && isFinite(n)) ? n : null; }
function _money(v) {
  if (v == null) return "—";
  const a = Math.abs(v);
  if (a >= 1e9) return (v / 1e9).toFixed(2) + "B";
  if (a >= 1e6) return (v / 1e6).toFixed(0) + "M";
  if (a >= 1e3) return (v / 1e3).toFixed(0) + "K";
  return v.toFixed(0);
}
function _pct(v, d = 1) { return v == null ? "—" : (v >= 0 ? "+" : "") + v.toFixed(d) + "%"; }

// ── peer cohort fetch (real /api/peers) ──
function usePeers(sym) {
  const [d, setD] = React.useState(null);
  React.useEffect(() => {
    const BV = window.__BV;
    if (!BV || !BV.get || !sym) { setD(null); return; }
    let on = true;
    BV.get("/api/peers/" + encodeURIComponent(sym)).then(j => { if (on) setD(j); }).catch(() => { if (on) setD(null); });
    return () => { on = false; };
  }, [sym]);
  return d;
}

// ── derive the real fundamentals bundle the whole lens runs on ──
function useInvData(ticker) {
  return React.useMemo(() => {
    const fund = ticker._fund || {};
    const inc = (fund.income_5y || ticker._income5y || []);   // [0] = latest
    const cf = (fund.cashflow_5y || ticker._cashflow5y || []);
    const bs = (fund.balance_5y || ticker._balance5y || []);
    const H = fund.highlights || {}, V = fund.valuation || {}, S = fund.shares || {};
    const price = _P(ticker.price);
    const sharesOut = _P(S.SharesOutstanding) || ((_P(ticker.mcap) && price) ? _P(ticker.mcap) / price : null);
    const pe = _P(ticker.pe), fwdPe = _P(ticker.fwdPe), pb = _P(ticker.pb);
    const eps = (pe && pe > 0 && price) ? price / pe : null;
    const fwdEps = (fwdPe && fwdPe > 0 && price) ? price / fwdPe : null;
    const bvps = (pb && pb > 0 && price) ? price / pb : null;
    const fcf0 = cf.length ? _P(cf[0].freeCashFlow) : null;
    const fcfPS = (fcf0 != null && sharesOut) ? fcf0 / sharesOut : null;
    const cagr = (arr, key) => {
      const vals = arr.map(r => _P(r[key])).filter(v => v != null);
      if (vals.length < 2) return null;
      const latest = vals[0], oldest = vals[vals.length - 1], yrs = vals.length - 1;
      if (oldest <= 0 || latest <= 0) return null;
      return Math.pow(latest / oldest, 1 / yrs) - 1;
    };
    // ── balance sheet (real, from EODHD Balance_Sheet) ──
    const bs0 = bs[0] || {};
    const equity = _P(bs0.totalStockholderEquity);
    const totalDebt = _P(bs0.shortLongTermDebtTotal) != null ? _P(bs0.shortLongTermDebtTotal)
      : ((_P(bs0.longTermDebt) || 0) + (_P(bs0.shortTermDebt) || 0)) || null;
    const netDebt = _P(bs0.netDebt) != null ? _P(bs0.netDebt) : ((totalDebt != null && _P(bs0.cash) != null) ? totalDebt - _P(bs0.cash) : null);
    const curAssets = _P(bs0.totalCurrentAssets), curLiab = _P(bs0.totalCurrentLiabilities);
    const currentRatio = (curAssets != null && curLiab && curLiab > 0) ? curAssets / curLiab : null;
    const debtEquity = (totalDebt != null && equity && equity > 0) ? totalDebt / equity : null;
    const ebitda0 = _P((inc[0] || {}).ebitda) != null ? _P((inc[0] || {}).ebitda) : _P(H.EBITDA);
    const netDebtEbitda = (netDebt != null && ebitda0 && ebitda0 > 0) ? netDebt / ebitda0 : null;
    const shareSeries = bs.map(r => _P(r.commonStockSharesOutstanding)).filter(v => v != null);
    const shareCagr = (shareSeries.length >= 2 && shareSeries[0] > 0 && shareSeries[shareSeries.length - 1] > 0)
      ? Math.pow(shareSeries[0] / shareSeries[shareSeries.length - 1], 1 / (shareSeries.length - 1)) - 1 : null;
    const rev0 = _P((inc[0] || {}).totalRevenue);
    const salesPS = (rev0 && sharesOut) ? rev0 / sharesOut : null;
    return {
      price, sharesOut, pe, fwdPe, pb, eps, fwdEps, bvps, fcf0, fcfPS,
      fcfCagr: cagr(cf, "freeCashFlow"), revCagr: cagr(inc, "totalRevenue"),
      ebitdaCagr: cagr(inc, "ebitda"), niCagr: cagr(inc, "netIncome"),
      inc, cf, bs, H, V, S, targetPrice: _P(ticker.targetPrice), beta: _P(ticker.beta),
      roe: _P(H.ReturnOnEquityTTM), roa: _P(H.ReturnOnAssetsTTM),
      opMargin: _P(H.OperatingMarginTTM), profitMargin: _P(H.ProfitMargin),
      revGrowthQ: _P(H.QuarterlyRevenueGrowthYOY), divYield: _P(H.DividendYield),
      equity, totalDebt, netDebt, currentRatio, debtEquity, ebitda0, netDebtEbitda, shareCagr, salesPS,
      sector: ticker.sector || fund.sector || "",
      hasFund: !!(inc.length || cf.length || H.MarketCapitalization),
    };
  }, [ticker.symbol, ticker.price, ticker._fund]);
}

// ── CAPM WACC: risk-free + beta × equity-risk-premium, clamped to a sane band ──
function _capmWacc(beta) {
  const rf = 0.043, erp = 0.052;   // ~10y UST + long-run US equity risk premium
  const b = (beta != null && isFinite(beta)) ? beta : 1.0;
  return Math.max(0.07, Math.min(0.13, rf + b * erp));
}

// ── DCF / reverse-DCF (10y explicit FCF/sh, linear fade g→tg, + terminal) ──
function _dcfValue(fcfPS, g, w, tg) {
  if (fcfPS == null || fcfPS <= 0 || w <= tg) return null;
  let pv = 0, f = fcfPS;
  for (let t = 1; t <= 10; t++) { const gt = g + (tg - g) * ((t - 1) / 9); f = f * (1 + gt); pv += f / Math.pow(1 + w, t); }
  const terminal = (f * (1 + tg)) / (w - tg) / Math.pow(1 + w, 10);
  return pv + terminal;
}
function _impliedGrowth(fcfPS, price, w, tg) {
  if (fcfPS == null || fcfPS <= 0 || !price) return null;
  let lo = -0.5, hi = 1.0;
  for (let i = 0; i < 64; i++) { const mid = (lo + hi) / 2; const v = _dcfValue(fcfPS, mid, w, tg); if (v == null) return null; if (v < price) lo = mid; else hi = mid; }
  return (lo + hi) / 2;
}

// ── the real fair-value method stack (multiples anchor + reverse-DCF) ──
function fairValueMethods(d, peers) {
  const out = [];
  const med = (peers && peers.medians) || {};
  const peerPE = _P(med.pe_ttm), peerFwdPE = _P(med.forward_pe), peerEvEbitda = _P(med.ev_ebitda), peerPS = _P(med.price_sales);
  const peerGrow = _P(med.revenue_growth);
  const ownGrow = d.revCagr != null ? d.revCagr : d.revGrowthQ;
  // growth-adjust peer multiple reversion (relative-PEG): a fast grower shouldn't revert to a
  // mature cohort's multiple. clamp 0.6–1.8× so it tempers, never fabricates, the anchor.
  const growthAdj = (ownGrow != null && peerGrow != null && peerGrow > 0 && ownGrow > 0)
    ? Math.max(0.6, Math.min(1.8, (1 + ownGrow) / (1 + peerGrow))) : 1;
  const adjLbl = growthAdj !== 1 ? ` · growth-adj ${growthAdj.toFixed(2)}×` : "";
  const isGrowth = ownGrow != null && ownGrow >= 0.15;   // Graham's mechanism fails for growth names
  const isFinancial = /financ|bank|insur|capital market/i.test(d.sector || "");   // enterprise multiples invalid for lenders
  const wacc = _capmWacc(d.beta);

  if (d.targetPrice) out.push({ key: "pt", m: "Analyst price target", sub: "consensus mean · EODHD", fair: d.targetPrice, w: 0.20, band: 0.08 });
  if (peerPE && d.eps && d.eps > 0) out.push({ key: "peTrail", m: "Peer P/E · trailing EPS", sub: `cohort ${peerPE.toFixed(1)}× · EPS $${d.eps.toFixed(2)}${adjLbl}`, fair: peerPE * d.eps * growthAdj, w: 0.16, band: 0.12 });
  if (peerFwdPE && d.fwdEps && d.fwdEps > 0) out.push({ key: "peFwd", m: "Peer fwd P/E · forward EPS", sub: `cohort fwd ${peerFwdPE.toFixed(1)}× · fwd EPS $${d.fwdEps.toFixed(2)}${adjLbl}`, fair: peerFwdPE * d.fwdEps * growthAdj, w: 0.16, band: 0.12 });
  // EV/EBITDA peer reversion → enterprise value, then back out equity per share
  // (skip for financials — their "net debt" is operating funding, not leverage)
  if (!isFinancial && peerEvEbitda && d.ebitda0 && d.ebitda0 > 0 && d.sharesOut) {
    const eqPS = (peerEvEbitda * d.ebitda0 - (d.netDebt || 0)) / d.sharesOut;
    if (eqPS > 0) out.push({ key: "evEbitda", m: "Peer EV/EBITDA", sub: `cohort ${peerEvEbitda.toFixed(1)}× · EBITDA $${_money(d.ebitda0)} − net debt`, fair: eqPS, w: 0.16, band: 0.13 });
  }
  // P/S peer reversion (growth-adjusted) — the workhorse for not-yet-profitable names
  if (peerPS && d.salesPS && d.salesPS > 0) out.push({ key: "ps", m: "Peer P/S", sub: `cohort ${peerPS.toFixed(1)}× · sales/sh $${d.salesPS.toFixed(2)}${adjLbl}`, fair: peerPS * d.salesPS * growthAdj, w: 0.12, band: 0.15 });
  // Graham number: deep-value floor — only meaningful for sub-15%-growth, asset-relevant names
  if (!isGrowth && d.eps && d.eps > 0 && d.bvps && d.bvps > 0) out.push({ key: "graham", m: "Graham number", sub: `√(22.5·EPS·BVPS) · BVPS $${d.bvps.toFixed(2)}`, fair: Math.sqrt(22.5 * d.eps * d.bvps), w: 0.10, band: 0.05 });
  // FINANCIALS: justified P/B from return-on-equity vs cost of equity (Gordon for banks/
  // lenders — the correct model where FCF/EV are distorted). fair = (ROE÷COE) × book/sh.
  if (isFinancial && d.roe && d.roe > 0 && d.bvps && d.bvps > 0) {
    const coe = wacc, justPB = Math.max(0.3, Math.min(5, d.roe / coe));
    out.push({ key: "pbRoe", m: "Justified P/B · ROE÷COE", sub: `ROE ${(d.roe * 100).toFixed(0)}% ÷ COE ${(coe * 100).toFixed(1)}% → ${justPB.toFixed(2)}× · BVPS $${d.bvps.toFixed(2)}`, fair: justPB * d.bvps, w: 0.24, band: 0.13 });
  }
  // Reverse-DCF — skip for financials (FCF distorted by loan-book / funding flows)
  if (!isFinancial && d.fcfPS && d.fcfPS > 0) {
    const g = Math.max(0.02, Math.min(0.18, d.fcfCagr != null ? d.fcfCagr : (d.revCagr != null ? d.revCagr * 0.8 : 0.08)));
    const fv = _dcfValue(d.fcfPS, g, wacc, 0.03);
    if (fv) out.push({ key: "dcf", m: "Reverse-DCF · base case", sub: `FCF/sh $${d.fcfPS.toFixed(2)} · g ${(g * 100).toFixed(0)}%→3% · WACC ${(wacc * 100).toFixed(1)}%`, fair: fv, w: 0.26, band: 0.18, g });
  }
  const tw = out.reduce((s, x) => s + x.w, 0) || 1;
  out.forEach(x => { x.wn = x.w / tw; x.mos = (x.fair / d.price - 1) * 100; });
  const blended = out.length ? out.reduce((s, x) => s + x.fair * x.wn, 0) : null;
  return { methods: out, blended, blendedMos: blended != null ? (blended / d.price - 1) * 100 : null, growthAdj, isGrowth, isFinancial, wacc };
}

function _tone(mos) { return mos == null ? "ink" : mos >= 8 ? "gn" : mos >= -8 ? "amb" : "rd"; }

// ════════════════════════════════════════════════════════════════════
function LensInvestment({ ticker, mode, sizeCat, headerStyle, kpiStyle, heroStyle }) {
  const s1 = useStateToggle("iv-1"); const s2 = useStateToggle("iv-2");
  const s3 = useStateToggle("iv-3"); const s4 = useStateToggle("iv-4");
  const s5 = useStateToggle("iv-5"); const s6 = useStateToggle("iv-6");
  const s7 = useStateToggle("iv-7");
  const d = useInvData(ticker);
  const peers = usePeers(ticker.symbol);
  const fv = React.useMemo(() => fairValueMethods(d, peers), [d, peers]);

  if (!d.hasFund && !ticker._loading) {
    return (
      <div className="lens lens--inv">
        <div className="lens-pad" style={{ padding: "40px 18px", textAlign: "center" }}>
          <div className="label-cap" style={{ marginBottom: 8 }}>Investment · Value</div>
          <div className="mono dim2" style={{ fontSize: 13 }}>No fundamentals returned for <b className="copper">{ticker.symbol}</b> — value lens needs EODHD financials (income / cash-flow / balance). It may be an ETF, ADR, or a name outside the fundamentals universe.</div>
        </div>
      </div>
    );
  }

  return (
    <div className="lens lens--inv">
      <ValueHero ticker={ticker} mode={mode} d={d} fv={fv} />

      <div className="lens-section">
        <SectionHeader n={1} title="Fair Value · What It's Worth"
          sub="multiple-reversion anchor (peer P/E, Graham) + a reverse-DCF check · the spread is your bull/bear band"
          style={headerStyle} right={<StateToggle name="iv-1" />} />
        <StateWrap state={s1.value} source="EODHD financials + /api/peers cohort">
          <div className="lens-pad">
            <PriceFairChannel ticker={ticker} d={d} peers={peers} />
            <FootballField d={d} fv={fv} />
            <div className="iv-split" style={{ marginTop: 14 }}>
              <div className="iv-split-main"><MarginOfSafety d={d} fv={fv} /></div>
              <div className="iv-split-side"><ValueScale d={d} fv={fv} /><ReverseDcf d={d} fv={fv} /></div>
            </div>
          </div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={2} title="Quality Scorecard"
          sub="returns on capital · balance-sheet · operator alignment · 5y trend — all from filings"
          style={headerStyle} right={<StateToggle name="iv-2" />} />
        <StateWrap state={s2.value} source="EODHD Highlights + Income/Cash-Flow 5y">
          <div className="lens-pad"><QualityCard d={d} peers={peers} ticker={ticker} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={3} title="Peer Cohort"
          sub={peers && peers.basis ? `${(peers.medians && peers.medians.n) || 0} closest names by market cap · same ${peers.basis}` : "same-industry cohort · normalized"}
          style={headerStyle} right={<StateToggle name="iv-3" />} />
        <StateWrap state={s3.value} source="data/fundamentals.db · same-GICS cohort">
          <div className="lens-pad"><PeerCohort ticker={ticker} peers={peers} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={4} title="5-Year Statements"
          sub="revenue · gross profit · EBITDA · net income · FCF · buybacks · with real CAGR"
          style={headerStyle} right={<StateToggle name="iv-4" />} />
        <StateWrap state={s4.value} source="EODHD · Income_Statement + Cash_Flow yearly">
          <div className="lens-pad"><Statements d={d} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={5} title="Capital Allocation"
          sub="where 5 years of cash went · capex · buybacks · dividends · debt · investing"
          style={headerStyle} right={<StateToggle name="iv-5" />} />
        <StateWrap state={s5.value} source="EODHD · Cash_Flow 5y">
          <div className="lens-pad"><CapAlloc d={d} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={6} title="Bull · Bear"
          sub="strongest case both ways · derived from the real numbers · pre-mortem before entry"
          style={headerStyle} right={<StateToggle name="iv-6" />} />
        <StateWrap state={s6.value} source="computed from filings + valuation">
          <div className="lens-pad"><BullBear ticker={ticker} d={d} fv={fv} peers={peers} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={7} title="Earnings Calendar · Forward"
          sub="next report · estimate · last-4-quarter surprise trend"
          style={headerStyle} right={<StateToggle name="iv-7" />} />
        <StateWrap state={s7.value} source="EODHD · earnings history + estimates">
          <div className="lens-pad"><CatCal ticker={ticker} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={8} title="Cross-Lens Confluence"
          sub="this lens's value read alongside the live reads from the other engine lenses" style={headerStyle} />
        <div className="lens-pad"><CrossLens lead="violet" cells={crossLensCells(ticker, mode, d, fv)} /></div>
      </div>

      <TheRead d={d} fv={fv} />
    </div>
  );
}

// ─── Hero ──────────────────────────────────────────────────────────
function ValueHero({ ticker, mode, d, fv }) {
  const cv = window.compositeVerdict ? window.compositeVerdict(ticker, mode) : null;
  const verdict = cv ? cv.verdict : (ticker.verdict || "WATCH");
  const vtone = cv ? cv.vtone : "amb";
  const net = cv ? cv.net : ticker.score;
  const mos = fv.blendedMos;
  const tone = _tone(mos);
  const lo = fv.methods.length ? Math.min(...fv.methods.map(m => m.fair)) : null;
  const hi = fv.methods.length ? Math.max(...fv.methods.map(m => m.fair)) : null;
  return (
    <div className="hero value-hero">
      <div className="vh-top">
        <div>
          <div className="label-cap">Master verdict · {(mode || "INVEST").toUpperCase()} mode</div>
          <div className="vh-verdict">
            <span className={`vh-tag kpi-tone--${vtone}`}>{window.secBias ? window.secBias(verdict) : verdict}</span>
            {net != null && <span className="vh-score mono">{Math.round(net)}<span className="th-score-unit">/100</span></span>}
            {mos != null && <Pill tone={tone} small>{mos >= 0 ? "premium" : "margin"} {Math.abs(mos).toFixed(0)}%</Pill>}
          </div>
          <div className="vh-line mono dim2">
            {fv.blended != null ? <>
              Blended fair <b>${fv.blended.toFixed(2)}</b> · range ${lo.toFixed(0)}–${hi.toFixed(0)} across {fv.methods.length} methods.
              Current <b>${d.price.toFixed(2)}</b> sits {mos >= 0 ? <b className="dn">{mos.toFixed(0)}% above</b> : <b className="up">{Math.abs(mos).toFixed(0)}% below</b>} blended fair value.
            </> : <>Not enough earnings / cash-flow to triangulate fair value — analyst target only.</>}
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── §1 · Price vs fair-value channel (real history × earnings multiple) ──
// FAST-Graphs style: price overlaid on an EPS × [low/normal/high P/E] band built from
// the real annual EPS series. Gated to names with a positive-earnings history; the
// football field below covers everyone else. Never seeded — renders null if ineligible.
function PriceFairChannel({ ticker, d, peers }) {
  const [hist, setHist] = React.useState(null);
  React.useEffect(() => {
    const BV = window.__BV;
    if (!BV || !BV.get || !ticker.symbol) { setHist(null); return; }
    let on = true;
    BV.get("/api/ohlcv/" + encodeURIComponent(ticker.symbol) + "?days=1460").then(r => {
      if (!on) return; const c = (r && r.candles) || [];
      setHist(c.length >= 60 ? c : null);
    }).catch(() => { if (on) setHist(null); });
    return () => { on = false; };
  }, [ticker.symbol]);
  const [ref, w] = useWidth(900);
  const uid = React.useId();

  // real annual EPS series (netIncome / share-count, matched by year)
  const epsSeries = React.useMemo(() => {
    const out = [];
    (d.inc || []).forEach(r => {
      const ni = _P(r.netIncome), yr = (r.date || "").slice(0, 4);
      const bsRow = (d.bs || []).find(b => (b.date || "").slice(0, 4) === yr);
      const shr = _P((bsRow || {}).commonStockSharesOutstanding) || d.sharesOut;
      const t = Date.parse(r.date) / 1000;
      if (ni != null && shr && isFinite(t)) out.push({ t, eps: ni / shr });
    });
    return out.sort((a, b) => a.t - b.t);
  }, [d.inc, d.bs, d.sharesOut]);

  const med = (peers && peers.medians) || {};
  const normPE = _P(med.pe_ttm) || d.pe;
  const eligible = hist && epsSeries.length >= 3 && epsSeries.every(e => e.eps > 0) && normPE && normPE > 0;
  if (!eligible) return null;

  const cand = hist.filter((_, i) => i % Math.max(1, Math.floor(hist.length / 160)) === 0);
  const epsAt = t => { let e = epsSeries[0].eps; for (const p of epsSeries) { if (p.t <= t) e = p.eps; else break; } return e; };
  const pts = cand.map(c => { const t = c.time || c.t; const eps = epsAt(t); return { t, px: c.close, mid: eps * normPE, lo: eps * normPE * 0.75, hi: eps * normPE * 1.25 }; });
  const padL = 4, padR = 46, padT = 10, padB = 18, H = 200;
  const plotW = Math.max(120, w - padL - padR), plotH = H - padT - padB;
  const allV = pts.flatMap(p => [p.px, p.lo, p.hi]);
  const min = Math.min(...allV) * 0.95, max = Math.max(...allV) * 1.05;
  const t0 = pts[0].t, t1 = pts[pts.length - 1].t;
  const xOf = t => padL + ((t - t0) / (t1 - t0 || 1)) * plotW;
  const yOf = v => padT + plotH - ((v - min) / (max - min)) * plotH;
  const line = key => pts.map((p, i) => `${i ? "L" : "M"} ${xOf(p.t).toFixed(1)},${yOf(p[key]).toFixed(1)}`).join(" ");
  const band = `M ${pts.map(p => `${xOf(p.t).toFixed(1)},${yOf(p.hi).toFixed(1)}`).join(" L ")} L ${pts.slice().reverse().map(p => `${xOf(p.t).toFixed(1)},${yOf(p.lo).toFixed(1)}`).join(" L ")} Z`;
  const now = pts[pts.length - 1];
  const richPct = (now.px / now.mid - 1) * 100;
  const yrTicks = []; const yrsSpan = (t1 - t0) / (365.25 * 86400);
  for (let i = 0; i <= Math.min(6, Math.ceil(yrsSpan)); i++) { const t = t1 - i * 365.25 * 86400; if (t >= t0) yrTicks.push(t); }
  return (
    <div className="iv-bands" ref={ref} style={{ marginBottom: 12 }}>
      <svg width={w} height={H}>
        <defs><linearGradient id={`pfc-${uid}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--gn)" stopOpacity="0.13" /><stop offset="100%" stopColor="var(--rd)" stopOpacity="0.13" /></linearGradient></defs>
        <path d={band} fill={`url(#pfc-${uid})`} />
        <path d={line("hi")} fill="none" stroke="var(--gn)" strokeWidth="1" strokeDasharray="4 4" opacity="0.6" />
        <path d={line("mid")} fill="none" stroke="var(--ink-2)" strokeWidth="1.2" strokeDasharray="2 3" opacity="0.75" />
        <path d={line("lo")} fill="none" stroke="var(--rd)" strokeWidth="1" strokeDasharray="4 4" opacity="0.6" />
        <path d={line("px")} fill="none" stroke="var(--copper)" strokeWidth="2" style={{ filter: "drop-shadow(0 0 4px color-mix(in oklab, var(--copper) 50%, transparent))" }} />
        {[["hi", "gn"], ["mid", "ink-2"], ["lo", "rd"]].map(([k, t], i) => <text key={i} x={xOf(now.t) + 5} y={yOf(now[k]) + 3} fontSize="9" className="mono" fill={`var(--${t})`}>${now[k].toFixed(0)}</text>)}
        <circle cx={xOf(now.t)} cy={yOf(now.px)} r="3.5" fill="var(--copper)" stroke="var(--bg-1)" strokeWidth="1.3" />
        {yrTicks.map((t, i) => <text key={i} x={xOf(t)} y={H - 5} fontSize="8.5" className="mono" fill="var(--ink-3)" textAnchor="middle">{new Date(t * 1000).getFullYear()}</text>)}
      </svg>
      <div className="iv-bands-leg mono dim2">
        <span><span className="iv-dot" style={{ background: "var(--copper)" }} /> price</span>
        <span><span className="iv-dot" style={{ background: "var(--ink-2)" }} /> EPS × {normPE.toFixed(0)}× (normal)</span>
        <span><span className="iv-dot" style={{ background: "var(--gn)" }} /> ×{(normPE * 1.25).toFixed(0)} hi · <span className="iv-dot" style={{ background: "var(--rd)" }} /> ×{(normPE * 0.75).toFixed(0)} lo</span>
        <span className="iv-bands-read">Price vs its earnings-multiple channel over {yrsSpan.toFixed(1)}y. Now <b className={richPct >= 0 ? "dn" : "up"}>{richPct >= 0 ? "+" : ""}{richPct.toFixed(0)}%</b> vs the normal-multiple line.</span>
      </div>
    </div>
  );
}

// ─── §1 · Valuation football field ──────────────────────────────────
function FootballField({ d, fv }) {
  const [ref, w] = useWidth(900);
  if (!fv.methods.length) return <div className="mono dim2" style={{ padding: 12 }}>No fundamental valuation methods available for this name.</div>;
  const labelW = 188, padR = 50, padT = 8, rowH = 30, padB = 26;
  const rows = fv.methods.length;
  const h = padT + rows * rowH + padB;
  const plotL = labelW, plotW = Math.max(120, w - labelW - padR);
  const allV = fv.methods.flatMap(m => [m.fair * (1 - m.band), m.fair * (1 + m.band)]).concat([d.price]);
  const lo = Math.min(...allV) * 0.96, hi = Math.max(...allV) * 1.04;
  const xOf = v => plotL + ((v - lo) / (hi - lo)) * plotW;
  const ticks = 5;
  return (
    <div className="iv-ff" ref={ref}>
      <svg width={w} height={h}>
        {/* x grid + axis */}
        {Array.from({ length: ticks + 1 }, (_, i) => {
          const v = lo + (hi - lo) * (i / ticks);
          return <g key={i}><line x1={xOf(v)} y1={padT} x2={xOf(v)} y2={padT + rows * rowH} stroke="var(--line)" strokeDasharray="1 5" opacity="0.4" /><text x={xOf(v)} y={h - 9} fontSize="9" className="mono" fill="var(--ink-3)" textAnchor="middle">${v.toFixed(0)}</text></g>;
        })}
        {/* method range bars */}
        {fv.methods.map((m, i) => {
          const y = padT + i * rowH + rowH / 2;
          const x0 = xOf(m.fair * (1 - m.band)), x1 = xOf(m.fair * (1 + m.band)), xf = xOf(m.fair);
          const t = _tone(m.mos);
          return (
            <g key={m.key}>
              <text x={labelW - 10} y={y - 3} fontSize="10.5" className="mono" fill="var(--ink-1)" textAnchor="end" style={{ fontWeight: 600 }}>{m.m}</text>
              <text x={labelW - 10} y={y + 8.5} fontSize="8.5" className="mono" fill="var(--ink-3)" textAnchor="end">{m.sub}</text>
              <line x1={x0} y1={y} x2={x1} y2={y} stroke={`var(--${t})`} strokeWidth="7" strokeLinecap="round" opacity="0.32" />
              <circle cx={xf} cy={y} r="4.5" fill={`var(--${t})`} stroke="var(--bg-1)" strokeWidth="1.4" />
              <text x={x1 + 7} y={y + 3.5} fontSize="9.5" className="mono" fill={`var(--${t})`} style={{ fontWeight: 700 }}>${m.fair.toFixed(0)}</text>
            </g>
          );
        })}
        {/* blended fair value marker */}
        {fv.blended != null && <line x1={xOf(fv.blended)} y1={padT - 2} x2={xOf(fv.blended)} y2={padT + rows * rowH + 2} stroke="var(--ink-2)" strokeWidth="1.3" strokeDasharray="3 3" opacity="0.7" />}
        {/* current price line */}
        <line x1={xOf(d.price)} y1={padT - 2} x2={xOf(d.price)} y2={padT + rows * rowH + 2} stroke="var(--copper)" strokeWidth="2" style={{ filter: "drop-shadow(0 0 4px color-mix(in oklab, var(--copper) 55%, transparent))" }} />
        <g transform={`translate(${xOf(d.price) - 20}, ${padT - 2})`}><rect width="40" height="14" rx="2.5" fill="var(--copper)" /><text x="20" y="10.5" fontSize="9" textAnchor="middle" className="mono" fill="var(--bg-0)" style={{ fontWeight: 700 }}>${d.price.toFixed(0)}</text></g>
      </svg>
      <div className="iv-bands-leg mono dim2">
        <span><span className="iv-dot" style={{ background: "var(--copper)" }} /> spot</span>
        <span><span className="iv-dot" style={{ background: "var(--ink-2)" }} /> blended fair</span>
        <span><span className="iv-dot" style={{ background: "var(--gn)" }} /> margin</span>
        <span><span className="iv-dot" style={{ background: "var(--rd)" }} /> premium</span>
        <span className="iv-bands-read">Each bar is one independent valuation method ± its uncertainty. Where the copper spot line sits in the cluster is your margin of safety.</span>
      </div>
    </div>
  );
}

// ─── §1 · Margin of safety table (real methods) ─────────────────────
function MarginOfSafety({ d, fv }) {
  if (!fv.methods.length) return null;
  const blended = fv.blendedMos;
  const tone = _tone(blended);
  const Bar = ({ v }) => {
    const cap = Math.max(-40, Math.min(40, v == null ? 0 : v));
    const half = Math.abs(cap) / 40 * 50;
    return (
      <div className="iv-mos-bar-cell">
        <span className="mono dim2">−40%</span>
        <div className="iv-mos-track"><span className="zero" />
          <div className={`iv-mos-fill ${_tone(v)}`} style={v >= 0 ? { left: "50%", width: `${half}%` } : { left: `${50 - half}%`, width: `${half}%` }} /></div>
        <span className="mono dim2">+40%</span>
      </div>
    );
  };
  return (
    <div className="iv-mos">
      <div className="iv-mos-hd">
        <div className="iv-mos-blend">
          <div className="label-cap">Margin of Safety · vs blended fair</div>
          <div className={`iv-mos-blend-v mono kpi-tone--${tone}`}>{blended >= 0 ? "+" : ""}{blended.toFixed(1)}%</div>
          <div className="mono dim2">weighted across {fv.methods.length} independent methods</div>
        </div>
        <Pill tone={tone} small>{blended >= 8 ? "MARGIN" : blended <= -8 ? "PREMIUM" : "FAIR"} {Math.abs(blended).toFixed(0)}%</Pill>
      </div>
      <table className="pv-table iv-mos-tbl">
        <thead><tr>
          <th className="label-cap">Methodology</th>
          <th className="label-cap" style={{ textAlign: "right" }}>Fair</th>
          <th className="label-cap" style={{ textAlign: "right" }}>MoS</th>
          <th className="label-cap">−40% · spot · +40%</th>
        </tr></thead>
        <tbody>
          {fv.methods.map(m => (
            <tr key={m.key}>
              <td><b>{m.m}</b><br /><span className="dim2" style={{ fontSize: 10 }}>{m.sub}</span></td>
              <td className="mono" style={{ textAlign: "right" }}>${m.fair.toFixed(0)}</td>
              <td className="mono" style={{ textAlign: "right", color: `var(--${_tone(m.mos)})`, fontWeight: 700 }}>{m.mos >= 0 ? "+" : ""}{m.mos.toFixed(0)}%</td>
              <td><Bar v={m.mos} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── §1 · Reverse-DCF — what growth is priced in vs delivered ───────
function ReverseDcf({ d, fv }) {
  if (fv.isFinancial) return (
    <div className="dcf-sens"><div className="label-cap" style={{ marginBottom: 6 }}>Reverse-DCF</div>
      <div className="mono dim2" style={{ fontSize: 11 }}>This is a financial — its free cash flow is distorted by loan-book and funding flows, so a cash-flow DCF doesn't apply. Value rests on the <b>Justified P/B (ROE÷COE)</b> method above instead.</div></div>
  );
  if (!d.fcfPS || d.fcfPS <= 0) return (
    <div className="dcf-sens"><div className="label-cap" style={{ marginBottom: 6 }}>Reverse-DCF</div>
      <div className="mono dim2" style={{ fontSize: 11 }}>FCF is not positive on a trailing basis — a cash-flow DCF doesn't apply. Lean on the multiple-reversion methods above.</div></div>
  );
  const wacc = fv.wacc || 0.09;
  const implied = _impliedGrowth(d.fcfPS, d.price, wacc, 0.03);
  const hist = d.fcfCagr;
  const w0 = Math.round(wacc * 100);
  const waccs = [w0 - 1, w0, w0 + 1, w0 + 2].map(x => x / 100), grows = [0.02, 0.05, 0.08, 0.12];
  const tone = mos => mos >= 8 ? "gn" : mos >= -8 ? "amb" : "rd";
  return (
    <div className="dcf-sens">
      <div className="label-cap" style={{ marginBottom: 6 }}>Reverse-DCF · what's priced in</div>
      <div className="rdcf-head mono">
        <div><span className="dim2">market is pricing FCF growth of</span> <b className={implied != null && hist != null ? (implied > hist ? "dn" : "up") : ""}>{implied != null ? (implied * 100).toFixed(1) + "%/yr" : "—"}</b></div>
        <div><span className="dim2">you've delivered (5y FCF CAGR)</span> <b>{hist != null ? (hist * 100).toFixed(1) + "%/yr" : "—"}</b></div>
        <div className="dim2" style={{ fontSize: 10.5, marginTop: 2 }}>{implied != null && hist != null ? (implied > hist ? "Priced-in growth exceeds your track record — the market is optimistic; the thesis needs acceleration." : "Priced-in growth is below your track record — the bar is beatable if history repeats.") : `10y fade to 3% terminal · ${(wacc * 100).toFixed(1)}% WACC (CAPM, β ${(d.beta != null ? d.beta : 1).toFixed(2)}).`}</div>
      </div>
      <table className="dtable dcf-grid" style={{ marginTop: 8 }}>
        <thead><tr><th className="dim2">WACC ↓ · g →</th>{grows.map(g => <th key={g} className="r">{(g * 100).toFixed(0)}%</th>)}</tr></thead>
        <tbody>
          {waccs.map(wv => (
            <tr key={wv}><td className="mono dim2">{(wv * 100).toFixed(0)}%</td>
              {grows.map(g => { const val = _dcfValue(d.fcfPS, g, wv, 0.03); const mos = val ? (val / d.price - 1) * 100 : null;
                return <td key={g} className={`r mono dcf-cell kpi-tone--${mos == null ? "ink" : tone(mos)}`} title={mos != null ? `MoS ${mos >= 0 ? "+" : ""}${mos.toFixed(0)}%` : "n/a"} style={mos != null ? { background: `color-mix(in oklab, var(--${tone(mos)}) ${Math.min(22, Math.abs(mos))}%, transparent)` } : {}}>{val ? "$" + val.toFixed(0) : "—"}</td>; })}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mono dim2" style={{ fontSize: 10.5, marginTop: 6 }}>Intrinsic value/share at each discount rate × first-stage growth. Green = trades below fair.</div>
    </div>
  );
}

// ─── §1 · Value scale (real anchors: bear=min, bull=max, fair=blended) ─
function ValueScale({ d, fv }) {
  if (!fv.methods.length) return null;
  const fairs = fv.methods.map(m => m.fair);
  const bear = Math.min(...fairs), bull = Math.max(...fairs), fair = fv.blended;
  const tgt = d.targetPrice || fair;
  const span = (bull - bear) || (bull * 0.1) || 1;
  const pos = v => Math.max(0, Math.min(100, ((v - bear) / span) * 100));
  const fmt = v => `$${v.toFixed(0)}`;
  return (
    <div className="vh-scale" style={{ marginBottom: 10 }}>
      <div className="vh-scale-cap"><span className="label-cap">Value scale</span><span className="mono dim2">bear · fair · target · bull</span></div>
      <div className="vh-scale-track">
        <div className="vh-scale-fill" />
        <div className="vh-scale-marker vh-bear" style={{ left: "0%" }}><div className="vh-scale-px mono">{fmt(bear)}</div><div className="label-cap">bear</div></div>
        <div className="vh-scale-marker vh-fair" style={{ left: `${pos(fair)}%` }}><div className="vh-scale-px mono">{fmt(fair)}</div><div className="label-cap">fair</div></div>
        {d.targetPrice && <div className="vh-scale-marker vh-target" style={{ left: `${pos(tgt)}%` }}><div className="vh-scale-px mono">{fmt(tgt)}</div><div className="label-cap">PT</div></div>}
        <div className="vh-scale-marker vh-bull" style={{ left: "100%" }}><div className="vh-scale-px mono">{fmt(bull)}</div><div className="label-cap">bull</div></div>
        <div className="vh-scale-current" style={{ left: `${pos(d.price)}%` }}><div className="vh-cur-px mono">${d.price.toFixed(2)}</div></div>
      </div>
    </div>
  );
}

// ─── §2 Quality scorecard (real) ────────────────────────────────────
function _grade(score) { return score >= 85 ? "A" : score >= 72 ? "A−" : score >= 60 ? "B+" : score >= 48 ? "B" : score >= 35 ? "C" : "D"; }
function QualityCard({ d, peers, ticker }) {
  const inc0 = d.inc[0] || {};
  const grossMargin = (_P(inc0.grossProfit) != null && _P(inc0.totalRevenue)) ? _P(inc0.grossProfit) / _P(inc0.totalRevenue) * 100 : null;
  const ebit = _P(inc0.ebit), intExp = _P(inc0.interestExpense);
  const intCover = (ebit != null && intExp && intExp > 0) ? ebit / intExp : null;
  const de = d.debtEquity != null ? d.debtEquity : (peers && peers.self ? _P(peers.self.debt_equity) : null);
  const netMarginNow = d.profitMargin != null ? d.profitMargin * 100 : null;
  const incOld = d.inc[d.inc.length - 1] || {};
  const netMarginOld = (_P(incOld.netIncome) != null && _P(incOld.totalRevenue)) ? _P(incOld.netIncome) / _P(incOld.totalRevenue) * 100 : null;
  const marginTrend = (netMarginNow != null && netMarginOld != null) ? netMarginNow - netMarginOld : null;
  const insider = _P(ticker.insiderOwn);
  const v = (x, suf = "", dec = 1) => x == null ? "—" : x.toFixed(dec) + suf;
  const tn = (x, hi, lo) => x == null ? "ink" : x >= hi ? "gn" : x <= lo ? "rd" : "amb";

  // grades from real numbers
  const bizScore = [d.roe != null ? Math.min(100, Math.max(0, d.roe * 100 * 4)) : null, grossMargin != null ? Math.min(100, grossMargin * 1.5) : null, d.opMargin != null ? Math.min(100, Math.max(0, d.opMargin * 100 * 4)) : null].filter(x => x != null);
  const balScore = [intCover != null ? Math.min(100, intCover * 8) : null, de != null ? Math.max(0, 100 - de * 40) : null, d.currentRatio != null ? Math.min(100, d.currentRatio * 40) : null, d.netDebtEbitda != null ? Math.max(0, 100 - Math.max(0, d.netDebtEbitda) * 22) : null].filter(x => x != null);
  const trendScore = [d.revCagr != null ? Math.min(100, Math.max(0, 50 + d.revCagr * 200)) : null, d.fcfCagr != null ? Math.min(100, Math.max(0, 50 + d.fcfCagr * 150)) : null, marginTrend != null ? Math.min(100, Math.max(0, 50 + marginTrend * 5)) : null].filter(x => x != null);
  const avg = a => a.length ? a.reduce((s, x) => s + x, 0) / a.length : null;

  const cats = [
    { cat: "Business", grade: avg(bizScore), metrics: [
      { k: "ROE (TTM)", v: v(d.roe != null ? d.roe * 100 : null, "%"), tone: tn(d.roe != null ? d.roe * 100 : null, 15, 5) },
      { k: "Gross margin", v: v(grossMargin, "%"), tone: tn(grossMargin, 40, 20) },
      { k: "Op margin (TTM)", v: v(d.opMargin != null ? d.opMargin * 100 : null, "%"), tone: tn(d.opMargin != null ? d.opMargin * 100 : null, 15, 0) },
    ] },
    { cat: "Balance", grade: avg(balScore), metrics: [
      { k: "Debt / equity", v: de == null ? "—" : de.toFixed(2), tone: de == null ? "ink" : tn(2 - de, 1.2, 0.5) },
      { k: "Net debt / EBITDA", v: d.netDebtEbitda == null ? "—" : d.netDebtEbitda.toFixed(2) + "×", tone: d.netDebtEbitda == null ? "ink" : tn(4 - d.netDebtEbitda, 2.5, 0.5) },
      { k: "Current ratio", v: d.currentRatio == null ? "—" : d.currentRatio.toFixed(2), tone: tn(d.currentRatio, 1.5, 1) },
      { k: "Interest cover", v: v(intCover, "×"), tone: tn(intCover, 6, 2) },
    ] },
    { cat: "Operator", grade: avg([insider != null ? Math.min(100, 40 + insider * 6) : null, d.shareCagr != null ? Math.max(0, Math.min(100, 60 - d.shareCagr * 600)) : null].filter(x => x != null)), metrics: [
      { k: "Insider own", v: v(insider, "%"), tone: tn(insider, 5, 1) },
      { k: "Share count 5y", v: d.shareCagr == null ? "—" : (d.shareCagr >= 0 ? "+" : "") + (d.shareCagr * 100).toFixed(1) + "%/yr", tone: d.shareCagr == null ? "ink" : tn(-d.shareCagr * 100, 0, -3) },
      { k: "Div yield", v: d.divYield != null ? (d.divYield * 100).toFixed(2) + "%" : "0.00%", tone: "ink" },
    ] },
    { cat: "Trend", grade: avg(trendScore), metrics: [
      { k: "Rev CAGR 5y", v: v(d.revCagr != null ? d.revCagr * 100 : null, "%"), tone: tn(d.revCagr != null ? d.revCagr * 100 : null, 10, 0) },
      { k: "FCF CAGR 5y", v: v(d.fcfCagr != null ? d.fcfCagr * 100 : null, "%"), tone: tn(d.fcfCagr != null ? d.fcfCagr * 100 : null, 8, 0) },
      { k: "Net-margin trend", v: marginTrend == null ? "—" : (marginTrend >= 0 ? "+" : "") + marginTrend.toFixed(1) + "pp", tone: tn(marginTrend, 1, -1) },
    ] },
  ];
  return (
    <div className="quality">
      {cats.map((c, i) => {
        const g = c.grade != null ? _grade(c.grade) : "—";
        return (
          <div key={i} className="qual-cat">
            <div className="qual-hdr"><span className="label-cap">{c.cat}</span>
              <span className={`qual-grade mono ${g.startsWith("A") ? "up" : g.startsWith("B") ? "warn" : g === "—" ? "dim2" : "dn"}`}>{g}</span></div>
            {c.metrics.map((m, j) => (
              <div key={j} className="qual-metric"><span className="mono dim2">{m.k}</span><span className={`mono kpi-tone--${m.tone}`}>{m.v}</span></div>
            ))}
          </div>
        );
      })}
    </div>
  );
}

// ─── §3 Peer cohort (real /api/peers) ───────────────────────────────
function PeerCohort({ ticker, peers }) {
  if (!peers) return <div className="mono dim2" style={{ padding: 12 }}>Loading cohort…</div>;
  if (!peers.peers || !peers.peers.length) return <div className="mono dim2" style={{ padding: 12 }}>{peers.note || "No peer cohort available for this name in the local fundamentals universe."}</div>;
  const cohort = [{ ...peers.self, current: true }, ...peers.peers];
  // quality composite → percentile within cohort (ROE-ish via margins + growth − valuation)
  const q = p => (_P(p.profit_margin) || 0) * 60 + (_P(p.revenue_growth) || 0) * 40 - (_P(p.pe_ttm) || 30) * 0.15;
  const scored = cohort.map(p => ({ ...p, q: q(p) }));
  const qs = scored.map(p => p.q).sort((a, b) => a - b);
  scored.forEach(p => { p.pct = qs.length > 1 ? Math.round((qs.filter(x => x <= p.q).length - 1) / (qs.length - 1) * 100) : 50; });
  const cur = scored.find(p => p.current);
  const fmtPe = v => { const n = _P(v); return n == null || n <= 0 ? "—" : n.toFixed(1); };
  const fmtPct = v => { const n = _P(v); return n == null ? "—" : (n * 100).toFixed(1) + "%"; };
  return (
    <>
      <table className="dtable peers">
        <thead><tr><th>Peer</th><th className="r">P/E</th><th className="r">Rev growth</th><th className="r">Op margin</th><th className="r">Net margin</th><th className="r">Mkt cap</th><th className="r">Cohort %ile</th></tr></thead>
        <tbody>
          {scored.map(p => (
            <tr key={p.ticker} className={p.current ? "is-current" : ""}>
              <td className="mono"><b>{p.ticker}</b></td>
              <td className="r mono tabular">{fmtPe(p.pe_ttm)}</td>
              <td className={`r mono tabular ${_P(p.revenue_growth) > 0.1 ? "up" : "dim2"}`}>{fmtPct(p.revenue_growth)}</td>
              <td className="r mono tabular">{fmtPct(p.operating_margin)}</td>
              <td className={`r mono tabular ${_P(p.profit_margin) > 0.1 ? "up" : "dim2"}`}>{fmtPct(p.profit_margin)}</td>
              <td className="r mono tabular">{_money(_P(p.market_cap))}</td>
              <td className="r mono tabular"><span className={`peer-pct kpi-tone--${p.pct >= 66 ? "gn" : p.pct >= 40 ? "amb" : "rd"}`}>{p.pct}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="lab-verdict mono dim2" style={{ marginTop: 8 }}><b className="copper">{cur.ticker}</b> ranks in the <b className={cur.pct >= 66 ? "up" : ""}>{cur.pct}th percentile</b> of its {scored.length}-name {peers.basis} cohort on a quality composite (margins + growth − valuation) — {cur.pct >= 66 ? "best-in-cohort fundamentals" : cur.pct >= 40 ? "middle of the pack" : "lagging peers on quality"}. Cohort median P/E <b>{fmtPe(peers.medians && peers.medians.pe_ttm)}×</b>.</div>
    </>
  );
}

// ─── §4 5-yr statements (real, chronological) ───────────────────────
function Statements({ d }) {
  const inc = d.inc.slice().reverse();   // chronological
  const cf = d.cf.slice().reverse();
  const bs = d.bs.slice().reverse();
  if (!inc.length) return <div className="mono dim2" style={{ padding: 12 }}>No income-statement history.</div>;
  const yrs = inc.map(r => (r.date || "").slice(0, 4));
  const series = (arr, key) => arr.map(r => _P(r[key]));
  const buyback = cf.map(r => { const v = _P(r.salePurchaseOfStock); return v != null ? Math.max(0, -v) : null; });   // negative = repurchase
  const rows = [
    { line: "Revenue", vals: series(inc, "totalRevenue"), kind: "money" },
    { line: "Gross Pft", vals: series(inc, "grossProfit"), kind: "money" },
    { line: "EBITDA", vals: series(inc, "ebitda"), kind: "money" },
    { line: "Net Inc", vals: series(inc, "netIncome"), kind: "money" },
    { line: "FCF", vals: series(cf, "freeCashFlow"), kind: "money" },
    { line: "CapEx", vals: series(cf, "capitalExpenditures").map(v => v == null ? null : Math.abs(v)), kind: "money" },
    { line: "Buyback", vals: buyback, kind: "money" },
    { line: "Sh out", vals: series(bs, "commonStockSharesOutstanding"), kind: "shares", inv: true },   // fewer shares = good
  ];
  const cagr = vals => {
    const v = vals.filter(x => x != null);
    if (v.length < 2 || v[0] <= 0 || v[v.length - 1] <= 0) return null;
    return (Math.pow(v[v.length - 1] / v[0], 1 / (v.length - 1)) - 1) * 100;
  };
  return (
    <table className="dtable statements">
      <thead><tr><th>Line</th>{yrs.map((y, i) => <th key={i} className="r">{y}</th>)}<th>Trend</th><th className="r">CAGR</th></tr></thead>
      <tbody>
        {rows.map((r, i) => {
          const cg = cagr(r.vals);
          const good = cg == null ? null : (r.inv ? cg < 0 : cg > 0);
          const clean = r.vals.filter(x => x != null);
          if (!clean.length) return null;
          return (
            <tr key={i}>
              <td className="mono">{r.line}</td>
              {r.vals.map((v, j) => <td key={j} className="r mono tabular">{v == null ? "—" : r.kind === "shares" ? (v / 1e6).toFixed(0) + "M" : _money(v)}</td>)}
              <td>{clean.length >= 2 ? <Sparkline data={clean} color={`var(--${good ? "gn" : "rd"})`} w={60} h={18} /> : <span className="dim2">—</span>}</td>
              <td className={`r mono tabular ${good == null ? "dim2" : good ? "up" : "dn"}`}>{cg == null ? "—" : (cg >= 0 ? "+" : "") + cg.toFixed(1) + "%"}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

// ─── §5 Capital allocation (real 5y cash-flow sums) ─────────────────
function CapAlloc({ d }) {
  const cf = d.cf;
  if (!cf.length) return <div className="mono dim2" style={{ padding: 12 }}>No cash-flow history.</div>;
  const sumPos = key => cf.reduce((s, r) => { const v = _P(r[key]); return v != null ? s + v : s; }, 0);
  const capex = Math.abs(sumPos("capitalExpenditures"));
  const buyback = cf.reduce((s, r) => { const v = _P(r.salePurchaseOfStock); return v != null ? s + Math.max(0, -v) : s; }, 0);
  const dividends = Math.abs(cf.reduce((s, r) => { const v = _P(r.dividendsPaid); return v != null ? s + v : s; }, 0));
  const debtPaid = cf.reduce((s, r) => { const v = _P(r.netBorrowings); return v != null && v < 0 ? s + Math.abs(v) : s; }, 0);
  const invest = cf.reduce((s, r) => { const v = _P(r.investments); return v != null && v < 0 ? s + Math.abs(v) : s; }, 0);
  const raw = [
    { use: "Reinvestment (capex)", amt: capex, tone: "gn" },
    { use: "Buybacks", amt: buyback, tone: "copper" },
    { use: "Dividends", amt: dividends, tone: "ink" },
    { use: "Debt paydown", amt: debtPaid, tone: "ink" },
    { use: "Investing (net)", amt: invest, tone: "amb" },
  ].filter(x => x.amt > 0);
  const total = raw.reduce((s, x) => s + x.amt, 0) || 1;
  raw.forEach(x => x.pct = x.amt / total);
  raw.sort((a, b) => b.amt - a.amt);
  if (!raw.length) return <div className="mono dim2" style={{ padding: 12 }}>No material capital-allocation flows in the 5y window.</div>;
  const yrs = d.cf.length;
  const topUse = raw[0];
  return (
    <div className="cap-alloc">
      <div className="cap-bar">{raw.map((it, i) => <div key={i} className={`cap-seg cap-${it.tone}`} style={{ width: `${it.pct * 100}%` }} title={`${it.use}: $${_money(it.amt)}`} />)}</div>
      <div className="cap-legend">
        {raw.map((it, i) => (
          <div key={i} className="cap-row"><span className={`cap-sw cap-${it.tone}`} /><span className="cap-use mono">{it.use}</span><span className="cap-amt mono dim2">${_money(it.amt)}</span><span className="cap-pct mono">{(it.pct * 100).toFixed(0)}%</span></div>
        ))}
      </div>
      <div className="cap-note mono dim">Last {yrs} years of cash deployment · ${_money(total)} total. Largest use: <b>{topUse.use}</b> at {(topUse.pct * 100).toFixed(0)}%.</div>
    </div>
  );
}

// ─── §6 Bull · Bear (derived from the real numbers) + AI ────────────
function BullBear({ ticker, d, fv, peers }) {
  const bull = [], bear = [];
  const mos = fv.blendedMos;
  if (mos != null && mos <= -10) bull.push(`Trades ${Math.abs(mos).toFixed(0)}% below blended fair value — a real margin of safety across methods.`);
  if (d.roe != null && d.roe >= 0.15) bull.push(`ROE ${(d.roe * 100).toFixed(0)}% — high return on equity signals a quality compounder.`);
  if (d.revCagr != null && d.revCagr >= 0.10) bull.push(`Revenue compounding ${(d.revCagr * 100).toFixed(0)}%/yr over 5 years — durable top-line.`);
  if (d.fcfCagr != null && d.fcfCagr >= 0.08) bull.push(`Free cash flow growing ${(d.fcfCagr * 100).toFixed(0)}%/yr — self-funding, owner-friendly.`);
  if (_P(ticker.insiderOwn) != null && _P(ticker.insiderOwn) >= 5) bull.push(`Insiders own ${_P(ticker.insiderOwn).toFixed(1)}% — management's capital is aligned with yours.`);
  if (d.targetPrice && d.price && d.targetPrice / d.price - 1 >= 0.12) bull.push(`Street target $${d.targetPrice.toFixed(0)} implies ${((d.targetPrice / d.price - 1) * 100).toFixed(0)}% upside to consensus.`);

  if (mos != null && mos >= 10) bear.push(`Trades ${mos.toFixed(0)}% above blended fair value — paying a premium; little room for error.`);
  if (d.opMargin != null && d.opMargin <= 0) bear.push(`Operating margin is negative (${(d.opMargin * 100).toFixed(1)}%) — not yet profitable at the operating line.`);
  if (d.profitMargin != null && d.profitMargin <= 0.03 && d.profitMargin > -1) bear.push(`Thin net margin (${(d.profitMargin * 100).toFixed(1)}%) — limited cushion if costs rise.`);
  if (_P(ticker.shortFloat) != null && _P(ticker.shortFloat) >= 8) bear.push(`Short interest ${_P(ticker.shortFloat).toFixed(0)}% of float — the crowd is positioned against it.`);
  if (d.revCagr != null && d.revGrowthQ != null && d.revGrowthQ < d.revCagr - 0.05) bear.push(`Latest quarterly revenue growth (${(d.revGrowthQ * 100).toFixed(0)}%) is decelerating vs the 5y CAGR (${(d.revCagr * 100).toFixed(0)}%).`);
  if (peers && peers.medians && _P(peers.medians.pe_ttm) && d.pe && d.pe > _P(peers.medians.pe_ttm) * 1.3) bear.push(`P/E ${d.pe.toFixed(0)}× sits well above the cohort median ${_P(peers.medians.pe_ttm).toFixed(0)}× — richly valued vs peers.`);
  if (d.fcfPS != null && d.fcfPS <= 0) bear.push(`Trailing free cash flow is negative — valuation rests on future profitability, not today's cash.`);

  if (!bull.length) bull.push("No standout bullish signals in the current fundamentals — this is a show-me name.");
  if (!bear.length) bear.push("No major red flags in the fundamentals — risk is mostly valuation and execution.");

  const aiPrompt = () => `Give a balanced 3-sentence investor read on ${ticker.symbol} (${ticker.name}). Price $${d.price.toFixed(2)}, blended fair value $${fv.blended ? fv.blended.toFixed(2) : "n/a"} (margin of safety ${mos != null ? mos.toFixed(0) + "%" : "n/a"}), ROE ${d.roe != null ? (d.roe * 100).toFixed(0) + "%" : "n/a"}, 5y revenue CAGR ${d.revCagr != null ? (d.revCagr * 100).toFixed(0) + "%" : "n/a"}, operating margin ${d.opMargin != null ? (d.opMargin * 100).toFixed(0) + "%" : "n/a"}. Bull points: ${bull.slice(0, 3).join("; ")}. Bear points: ${bear.slice(0, 3).join("; ")}.`;

  return (
    <>
      <div className="bullbear">
        <div className="bb-col bb-col--bull">
          <div className="bb-hdr"><Pill tone="gn" dot>BULL CASE</Pill><span className="mono dim2">why this works</span></div>
          {bull.map((p, i) => <div key={i} className="bb-row"><span className="bb-num mono">{String(i + 1).padStart(2, "0")}</span><span className="bb-pt">{p}</span></div>)}
        </div>
        <div className="bb-col bb-col--bear">
          <div className="bb-hdr"><Pill tone="rd" dot>BEAR CASE</Pill><span className="mono dim2">what kills the thesis</span></div>
          {bear.map((p, i) => <div key={i} className="bb-row"><span className="bb-num mono">{String(i + 1).padStart(2, "0")}</span><span className="bb-pt">{p}</span></div>)}
        </div>
      </div>
      {window.AiExplain && <div style={{ marginTop: 10 }}><AiExplain build={aiPrompt} label="Synthesize bull vs bear" tag="KAIROS · VALUE" /></div>}
    </>
  );
}

// ─── §7 Earnings calendar (real earnings_history) ───────────────────
function CatCal({ ticker }) {
  const hist = (ticker._fund && ticker._fund.earnings_history) || ticker.earningsHistory || [];
  if (!hist.length) return <div className="mono dim2" style={{ padding: 12 }}>No earnings calendar available for {ticker.symbol}.</div>;
  // upcoming = epsActual null; past = has actual. EODHD history is reverse-chron.
  const upcoming = hist.filter(e => e.epsActual == null && e.reportDate).slice(-2).reverse();
  const past = hist.filter(e => e.epsActual != null).slice(0, 4);
  const surprise = e => (e.epsEstimate && e.epsActual != null) ? ((e.epsActual - e.epsEstimate) / Math.abs(e.epsEstimate) * 100) : (e.surprisePercent != null ? _P(e.surprisePercent) : null);
  // real beat-rate + average surprise across the reported quarters
  const surps = past.map(surprise).filter(s => s != null);
  const beats = surps.filter(s => s >= 0).length;
  const avgSurp = surps.length ? surps.reduce((a, b) => a + b, 0) / surps.length : null;
  const nextEst = upcoming.length ? _P(upcoming[0].epsEstimate) : null;
  return (
    <div className="catcal">
      {surps.length >= 2 && (
        <div className="cat-summary mono dim2" style={{ display: "flex", gap: 14, flexWrap: "wrap", padding: "2px 2px 8px", fontSize: 11.5 }}>
          <span>Track record · <b className={beats >= surps.length * 0.6 ? "up" : "dn"}>beat {beats} of {surps.length}</b></span>
          {avgSurp != null && <span>· avg surprise <b className={avgSurp >= 0 ? "up" : "dn"}>{avgSurp >= 0 ? "+" : ""}{avgSurp.toFixed(1)}%</b></span>}
          {nextEst != null && <span>· next est EPS <b>${nextEst.toFixed(2)}</b></span>}
        </div>
      )}
      {upcoming.map((e, i) => (
        <div key={"u" + i} className="cat-row cat-amb">
          <span className="cat-when mono">{(e.reportDate || "").slice(0, 10)}</span>
          <span className="cat-label">Earnings report{e.epsEstimate != null ? ` · est EPS $${_P(e.epsEstimate).toFixed(2)}` : ""}{e.beforeAfterMarket ? ` · ${e.beforeAfterMarket}` : ""}</span>
          <Pill tone="amb" small>upcoming</Pill>
        </div>
      ))}
      {past.map((e, i) => {
        const s = surprise(e);
        return (
          <div key={"p" + i} className={`cat-row cat-ink`}>
            <span className="cat-when mono">{(e.reportDate || "").slice(0, 10)}</span>
            <span className="cat-label">Reported EPS ${_P(e.epsActual) != null ? _P(e.epsActual).toFixed(2) : "—"}{e.epsEstimate != null ? ` vs est $${_P(e.epsEstimate).toFixed(2)}` : ""}</span>
            {s != null ? <Pill tone={s >= 0 ? "gn" : "rd"} small>{s >= 0 ? "beat +" : "miss "}{s.toFixed(0)}%</Pill> : <Pill tone="ink" small>—</Pill>}
          </div>
        );
      })}
    </div>
  );
}

// ─── §8 Cross-lens — this lens's value read + the REAL engine reads from the
//     other lenses (compositeVerdict reconciliation, not recomputed locally) ──
function crossLensCells(ticker, mode, d, fv) {
  const cells = [];
  const mos = fv.blendedMos;
  // (1) value-specific read — the one cell this lens owns, with fundamental detail
  cells.push({ lens: "Value", verdict: mos == null ? "—" : mos <= -8 ? "CHEAP" : mos >= 8 ? "RICH" : "FAIR", tone: mos == null ? "ink" : _tone(mos), note: mos != null ? `MoS ${mos >= 0 ? "+" : ""}${mos.toFixed(0)}%` : "no fair value" });
  // (2) live reads pulled from the engine's other lenses (real scores + reasons)
  const cv = window.compositeVerdict ? window.compositeVerdict(ticker, mode) : null;
  if (cv && cv.lenses) {
    const want = ["AI Edge", "Earnings", "Insider", "Risk", "Track Rec."];
    want.forEach(k => {
      const l = cv.lenses.find(x => x.k === k);
      if (l) cells.push({ lens: l.k, verdict: l.v >= 60 ? "BULL" : l.v >= 45 ? "MIXED" : "BEAR", tone: l.tone, note: l.why });
    });
  } else {
    // engine unavailable (off-universe) — fall back to fundamental-derived reads
    if (d.roe != null) cells.push({ lens: "Quality", verdict: d.roe >= 0.15 ? "HIGH" : d.roe >= 0.05 ? "OK" : "LOW", tone: d.roe >= 0.15 ? "gn" : d.roe >= 0.05 ? "amb" : "rd", note: `ROE ${(d.roe * 100).toFixed(0)}%` });
    if (d.revCagr != null) cells.push({ lens: "Growth", verdict: d.revCagr >= 0.15 ? "FAST" : d.revCagr >= 0.05 ? "STEADY" : "SLOW", tone: d.revCagr >= 0.15 ? "gn" : d.revCagr >= 0.05 ? "amb" : "rd", note: `rev ${(d.revCagr * 100).toFixed(0)}%/yr` });
  }
  return cells;
}

// ─── The Read (computed) ────────────────────────────────────────────
function TheRead({ d, fv }) {
  const mos = fv.blendedMos;
  if (mos == null) return null;
  const cheap = mos <= -8, rich = mos >= 8;
  const entry = fv.blended ? fv.blended * 0.92 : d.price * 0.92;
  return (
    <div className="lens-call">
      <span className="label-cap">The Read · Investment</span>
      <span className="mono">
        <b className={cheap ? "up" : rich ? "dn" : "copper"}>{cheap ? `Margin of safety ${Math.abs(mos).toFixed(0)}%` : rich ? `Premium ${mos.toFixed(0)}%` : "Roughly fair"}</b>
        {" "}· blended fair <b>${fv.blended ? fv.blended.toFixed(2) : "—"}</b>.{" "}
        {rich ? <>More attractive on a pullback toward <b>${entry.toFixed(2)}</b>.</> : cheap ? <>Valuation supports accumulation; size to conviction and let the thesis play out.</> : <>Wait for a better entry or a fundamental catalyst to tip the risk/reward.</>}
      </span>
    </div>
  );
}

window.LensInvestment = LensInvestment;

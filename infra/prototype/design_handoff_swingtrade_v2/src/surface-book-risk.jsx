// surface-book-risk.jsx — book-level risk the per-ticker lenses can't show:
// Barra-style factor tilts, gross/net/leverage exposure, concentration, and
// per-name risk contribution (component VaR). Reads MyPF holdings live.
const { useState: useBR, useMemo: useBRm, useEffect: useBRe } = React;

const BR_FACTORS = [
  ["Value", "val"], ["Momentum", "mom"], ["Size", "sz"], ["Quality", "q"], ["Low-Vol", "lv"],
];
function brHash(s) { let h = 0; for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0; return h; }
function brLoad(sym, salt) { const h = brHash(sym.toUpperCase() + salt); return ((h % 2000) / 1000) - 1; } // -1..1
function brFmt$(v) { const a = Math.abs(v); const s = v < 0 ? "-" : ""; if (a >= 1e6) return `${s}$${(a/1e6).toFixed(2)}M`; if (a >= 1e3) return `${s}$${(a/1e3).toFixed(1)}k`; return `${s}$${a.toFixed(0)}`; }

function SurfaceBookRisk({ onTicker }) {
  if (typeof useMyPF === "function") useMyPF();
  const MyPF = window.MyPF;
  const [scope, setScope] = useBR("all");          // "all" | active id
  const [sortRisk, setSortRisk] = useBR(true);
  const [objective, setObjective] = useBR("maxSharpe");
  const [targetVol, setTargetVol] = useBR(15);

  const model = useBRm(() => {
    if (!MyPF) return null;
    const pf = scope === "all" ? MyPF.combined() : MyPF.active();
    const sum = MyPF.summarize(pf);
    const rk = MyPF.risk(pf);
    const eq = sum.rows.filter(r => r.type !== "cash");
    if (!eq.length) return { empty: true };
    const longMv = eq.filter(r => r.mv > 0).reduce((s, r) => s + r.mv, 0);
    const shortMv = eq.filter(r => r.mv < 0).reduce((s, r) => s + Math.abs(r.mv), 0);
    const gross = longMv + shortMv, net = longMv - shortMv;
    const cash = pf.cash || 0;
    const equity = sum.invested + cash;
    const leverage = equity ? gross / equity : 0;
    const invested = sum.invested || 1;
    // factor tilts: weighted average loading across the book
    const factors = BR_FACTORS.map(([label, salt]) => {
      let tilt = 0;
      eq.forEach(r => {
        const wt = r.mv / invested;
        let l = brLoad(r.sym, salt);
        if (salt === "mom") l = Math.max(-1, Math.min(1, l * 0.5 + (r.pnlPct || 0) / 25));   // realized momentum nudge
        if (salt === "lv") l = -Math.max(-1, Math.min(1, (r.beta - 1) * 1.1));                // low-vol = inverse beta
        tilt += wt * l;
      });
      return { label, tilt: +tilt.toFixed(2) };
    });
    // per-name risk contribution (component): wt * standalone vol, normalized
    const withVol = eq.map(r => {
      const wt = r.mv / invested;
      const vol = r.beta * 16 + (brHash(r.sym) % 12);   // standalone annual vol proxy
      return { ...r, wt, vol, risk: wt * vol };
    });
    const totalRisk = withVol.reduce((s, r) => s + r.risk, 0) || 1;
    withVol.forEach(r => { r.riskPct = (r.risk / totalRisk) * 100; r.wtPct = r.wt * 100; });
    const names = withVol.slice().sort((a, b) => b.mv - a.mv);
    const top5 = names.slice(0, 5);
    const top5Wt = top5.reduce((s, r) => s + r.wtPct, 0);
    // portfolio Greeks — net option-overlay exposure aggregated across the book
    const greeks = (() => {
      let d = 0, g = 0, v = 0, th = 0;
      withVol.forEach(r => {
        const dir = r.mv >= 0 ? 1 : -1; const wt = Math.abs(r.wt);
        d += dir * wt * (0.45 + (brHash(r.sym + "d") % 40) / 100);     // net delta (0-1 per $)
        g += wt * (brHash(r.sym + "g") % 12) / 1000;
        v += wt * (brHash(r.sym + "v") % 30) / 100;
        th += -wt * (brHash(r.sym + "t") % 18) / 100;
      });
      const netDeltaUsd = (longMv - shortMv) * d;
      return { delta: +d.toFixed(2), netDeltaUsd, gamma: +g.toFixed(3), vega: +(v * invested / 100).toFixed(0), theta: +(th * invested / 100).toFixed(0) };
    })();
    // ── optimizer: target weights under 3 objectives, vs current ──
    const opt = (() => {
      const items = withVol.map(r => {
        const ret = (r.beta * 6 + (brHash(r.sym + "ret") % 80) / 10);   // expected ann return proxy %
        const vol = r.vol;
        return { sym: r.sym, cur: r.wt, ret, vol, sharpe: ret / vol };
      });
      const norm = arr => { const s = arr.reduce((a, b) => a + b.raw, 0) || 1; arr.forEach(x => x.tgt = x.raw / s); return arr; };
      const maxSharpe = norm(items.map(x => ({ ...x, raw: Math.max(0.0001, x.sharpe) ** 2 })));
      const riskParity = norm(items.map(x => ({ ...x, raw: 1 / Math.max(1, x.vol) })));
      const minVar = norm(items.map(x => ({ ...x, raw: 1 / Math.max(1, x.vol * x.vol) })));
      return { maxSharpe, riskParity, minVar };
    })();
    return { empty: false, pf, sum, rk, eq, longMv, shortMv, gross, net, cash, equity, leverage, factors, names: withVol, top5, top5Wt, invested, opt, greeks };
  }, [MyPF, scope, MyPF && MyPF.active && MyPF.active().holdings.length]);

  // re-render on portfolio changes
  const [, bump] = useBR(0);
  useBRe(() => { const h = () => bump(x => x + 1); window.addEventListener("mypf-change", h); return () => window.removeEventListener("mypf-change", h); }, []);

  if (!model) return <div className="wsx-body"><div className="mpf-empty"><div className="mpf-empty-t">Loading…</div></div></div>;
  if (model.empty) return (
    <div className="brk">
      <BrHeader scope={scope} setScope={setScope} MyPF={MyPF} />
      <div className="mpf-empty"><div className="mpf-empty-ico">▦</div><div className="mpf-empty-t">No positions in this book</div><div className="mpf-empty-s mono dim2">Add holdings in <b>My Portfolios</b> — book risk aggregates them here.</div></div>
    </div>
  );

  const m = model;
  const namesSorted = sortRisk ? m.names.slice().sort((a, b) => b.riskPct - a.riskPct) : m.names.slice().sort((a, b) => b.wtPct - a.wtPct);
  const betaTone = m.rk.beta > 1.2 ? "rd" : m.rk.beta > 0.95 ? "amb" : "gn";
  const levTone = m.leverage > 1.5 ? "rd" : m.leverage > 1.05 ? "amb" : "gn";
  const concTone = m.top5Wt > 60 ? "rd" : m.top5Wt > 45 ? "amb" : "gn";

  return (
    <div className="brk">
      <BrHeader scope={scope} setScope={setScope} MyPF={MyPF} />

      <div className="brk-tiles">
        <BrTile l="Gross exposure" v={brFmt$(m.gross)} s={`${(m.gross / m.equity * 100).toFixed(0)}% of equity`} tone="ink" />
        <BrTile l="Net exposure" v={brFmt$(m.net)} s={`${(m.net / m.equity * 100).toFixed(0)}% of equity`} tone={m.net >= 0 ? "gn" : "rd"} />
        <BrTile l="Long" v={brFmt$(m.longMv)} s={`${m.eq.filter(r=>r.mv>0).length} names`} tone="gn" />
        <BrTile l="Short" v={brFmt$(m.shortMv)} s={`${m.eq.filter(r=>r.mv<0).length} names`} tone={m.shortMv ? "rd" : "ink"} />
        <BrTile l="Leverage" v={`${m.leverage.toFixed(2)}×`} s="gross / equity" tone={levTone} />
        <BrTile l="Book β" v={m.rk.beta.toFixed(2)} s="vs SPY" tone={betaTone} />
        <BrTile l="β-adj net" v={brFmt$(m.net * m.rk.beta)} s="market-equiv $" tone="ink" />
        <BrTile l="Cash" v={brFmt$(m.cash)} s={`${(m.cash / m.equity * 100).toFixed(0)}% of equity`} tone="cy" />
      </div>

      <div className="brk-2col">
        <div className="lab-card">
          <div className="lab-card-h mono">FACTOR TILTS · book-weighted exposure</div>
          <div className="brk-facs">
            {m.factors.map(f => {
              const pos = f.tilt >= 0; const w = Math.min(50, Math.abs(f.tilt) * 50);
              return (
                <div key={f.label} className="brk-fac">
                  <span className="brk-fac-k mono">{f.label}</span>
                  <div className="brk-fac-track">
                    <span className="brk-fac-mid" />
                    <span className={`brk-fac-fill ${pos ? "pos" : "neg"}`} style={{ left: pos ? "50%" : `${50 - w}%`, width: `${w}%` }} />
                  </div>
                  <span className={`brk-fac-v mono ${pos ? "gn-c" : "rd-c"}`}>{pos ? "+" : ""}{f.tilt.toFixed(2)}</span>
                </div>
              );
            })}
          </div>
          <div className="lab-verdict mono dim2">+ = book is tilted toward the factor, − = away. Tilts are book-weighted standardized loadings (demo factor model). A desk reads this to see hidden bets: a high <b>+Momentum / −Value</b> book is a growth/trend bet regardless of the individual theses.</div>
        </div>

        <div className="lab-card">
          <div className="lab-card-h mono">CONCENTRATION</div>
          <div className="brk-conc-tiles">
            <BrTile l="HHI" v={m.rk.hhi.toFixed(3)} s={m.rk.hhi > 0.25 ? "concentrated" : "diversified"} tone={m.rk.hhi > 0.25 ? "amb" : "gn"} small />
            <BrTile l="Top-5 weight" v={`${m.top5Wt.toFixed(0)}%`} s={`of ${m.eq.length} names`} tone={concTone} small />
            <BrTile l="Largest" v={m.rk.topSym} s={`${m.rk.topWt.toFixed(0)}%`} tone={m.rk.topWt > 25 ? "amb" : "ink"} small />
          </div>
          <div className="brk-top5">
            {m.top5.map(r => (
              <button key={r.id} className="brk-top5-row" onClick={() => onTicker && onTicker(r.sym)}>
                <span className="mono brk-t5-sym">{r.sym}</span>
                <div className="brk-t5-track"><span className="brk-t5-fill" style={{ width: `${Math.min(100, r.wtPct / m.top5[0].wtPct * 100)}%` }} /></div>
                <span className="mono dim2 brk-t5-w">{r.wtPct.toFixed(1)}%</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="lab-card">
        <div className="lab-card-h mono">PORTFOLIO GREEKS · net option-overlay exposure</div>
        <div className="brk-tiles" style={{ gridTemplateColumns: "repeat(4,1fr)", margin: 0 }}>
          <div className="brk-tile"><div className="brk-tile-l mono dim2">Net Δ (delta)</div><div className={`brk-tile-v mono kpi-tone--${m.greeks.delta >= 0 ? "gn" : "rd"}`}>{m.greeks.delta >= 0 ? "+" : ""}{m.greeks.delta}</div><div className="brk-tile-s mono dim">{brFmt$(m.greeks.netDeltaUsd)} market-equiv</div></div>
          <div className="brk-tile"><div className="brk-tile-l mono dim2">Net Γ (gamma)</div><div className="brk-tile-v mono">{m.greeks.gamma}</div><div className="brk-tile-s mono dim">per 1% move</div></div>
          <div className="brk-tile"><div className="brk-tile-l mono dim2">Net ν (vega)</div><div className={`brk-tile-v mono kpi-tone--${m.greeks.vega >= 0 ? "gn" : "rd"}`}>{m.greeks.vega >= 0 ? "+" : ""}{brFmt$(m.greeks.vega)}</div><div className="brk-tile-s mono dim">per IV-pt</div></div>
          <div className="brk-tile"><div className="brk-tile-l mono dim2">Net Θ (theta)</div><div className={`brk-tile-v mono kpi-tone--${m.greeks.theta >= 0 ? "gn" : "rd"}`}>{brFmt$(m.greeks.theta)}</div><div className="brk-tile-s mono dim">per day</div></div>
        </div>
        <div className="lab-verdict mono dim2">Book-level Greeks aggregate every name's option overlay. Net <b>Δ {m.greeks.delta}</b> is your directional bet ({brFmt$(m.greeks.netDeltaUsd)} market-equivalent); net <b className={m.greeks.vega >= 0 ? "gn-c" : "rd-c"}>ν {m.greeks.vega >= 0 ? "long" : "short"} vol</b> and <b className="rd-c">Θ {brFmt$(m.greeks.theta)}/day</b> bleed tell you the carry. Watch Θ vs ν when the book is net-long premium.</div>
      </div>

      <div className="lab-card">
        <div className="lab-card-h mono">SECTOR EXPOSURE</div>
        <div className="pf-secbar">{m.rk.sectors.map((s, i) => <div key={i} className="pf-secseg" style={{ width: `${s.pct}%`, background: BR_SEC[s.k] || "var(--ink-3)" }} title={`${s.k} ${s.pct.toFixed(0)}%`} />)}</div>
        <div className="pf-seclegend">{m.rk.sectors.map((s, i) => <div key={i} className="pf-secrow"><span className="pf-secdot" style={{ background: BR_SEC[s.k] || "var(--ink-3)" }} /><span className="pf-seck mono">{s.k}</span><span className="pf-secv mono dim2">{s.pct.toFixed(0)}%</span></div>)}</div>
      </div>

      <div className="lab-card">
        <div className="lab-card-h mono">PORTFOLIO OPTIMIZER · target weights vs current
          <span className="brk-sort">
            {[["maxSharpe", "max-Sharpe"], ["riskParity", "risk-parity"], ["minVar", "min-var"]].map(([k, l]) => (
              <button key={k} className={objective === k ? "is-on" : ""} onClick={() => setObjective(k)}>{l}</button>
            ))}
          </span>
        </div>
        {(() => {
          const tgt = m.opt[objective];
          const byCur = tgt.slice().sort((a, b) => b.cur - a.cur);
          const turnover = byCur.reduce((s, r) => s + Math.abs(r.tgt - r.cur), 0) / 2 * 100;
          return (
            <>
              <table className="dtable brk-tbl">
                <thead><tr><th>Name</th><th className="r">Exp. return</th><th className="r">Vol</th><th className="r">Current</th><th className="r">Target</th><th>Δ trade</th></tr></thead>
                <tbody>
                  {byCur.map(r => {
                    const d = (r.tgt - r.cur) * 100;
                    return (
                      <tr key={r.sym} className="brk-row" onClick={() => onTicker && onTicker(r.sym)}>
                        <td className="mono"><b>{r.sym}</b></td>
                        <td className="r mono gn-c">+{r.ret.toFixed(1)}%</td>
                        <td className="r mono dim2">{r.vol.toFixed(0)}%</td>
                        <td className="r mono">{(r.cur * 100).toFixed(1)}%</td>
                        <td className="r mono"><b>{(r.tgt * 100).toFixed(1)}%</b></td>
                        <td><div className="brk-punch"><span className="brk-punch-mid" /><span className={`brk-punch-fill ${d >= 0 ? "pos" : "neg"}`} style={{ left: d >= 0 ? "50%" : `${50 - Math.min(48, Math.abs(d) * 2.2)}%`, width: `${Math.min(48, Math.abs(d) * 2.2)}%` }} /></div></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <div className="lab-verdict mono dim2">Target weights for the <b>{objective === "maxSharpe" ? "max-Sharpe" : objective === "riskParity" ? "risk-parity" : "min-variance"}</b> objective. Green Δ = <b className="gn-c">add</b>, red = <b className="rd-c">trim</b> to reach target. One-way <b>turnover ≈ {turnover.toFixed(0)}%</b> of book — at ~10bps each way that's ≈ {brFmt$(turnover / 100 * m.invested * 0.001 * 2)} in cost. Demo optimizer (expected-return proxy); not investment advice.</div>
              <div className="brk-voltgt">
                <span className="mono dim2">VOL TARGET</span>
                {[10, 15, 20].map(tv => <button key={tv} className={`brk-vt-btn ${targetVol === tv ? "is-on" : ""}`} onClick={() => setTargetVol(tv)}>{tv}%</button>)}
                {(() => {
                  const bookVol = m.rk.annVol || 18;
                  const lev = targetVol / bookVol;
                  return <span className="mono brk-vt-read">book vol <b>{bookVol.toFixed(0)}%</b> → to target <b className="copper">{targetVol}%</b> run gross <b className={lev > 1.05 ? "amb-c" : "gn-c"}>{lev.toFixed(2)}×</b> {lev < 1 ? `(de-lever ${((1-lev)*100).toFixed(0)}% to cash)` : lev > 1 ? `(add ${((lev-1)*100).toFixed(0)}% leverage)` : "(at target)"}</span>;
                })()}
              </div>
            </>
          );
        })()}
      </div>

      <div className="lab-card">
        <div className="lab-card-h mono">HEDGE OVERLAY · neutralize net exposure</div>
        {(() => {
          const spy = 542;
          const betaDollars = m.net * m.rk.beta;             // market-equiv $ to hedge
          const spyShares = Math.round(betaDollars / spy);
          const topSec = m.rk.sectors[0];
          const tailCost = +(m.gross * 0.012).toFixed(0);    // ~1.2% for 3-mo 5% OTM put spread
          const names = m.names.slice().sort((a, b) => b.wt - a.wt);
          const longLeg = names[0], shortLeg = names[names.length - 1];
          return (
            <>
              <div className="brk-hedges">
                <div className="brk-hedge">
                  <div className="brk-hedge-h mono">β-HEDGE (to market-neutral)</div>
                  <div className="brk-hedge-v mono">Short <b className="rd-c">{spyShares.toLocaleString()}</b> SPY <span className="dim2">(≈{brFmt$(betaDollars)})</span></div>
                  <div className="mono dim2" style={{ fontSize: 10.5 }}>neutralizes book β {m.rk.beta.toFixed(2)} → ~0; keeps stock-specific α</div>
                </div>
                <div className="brk-hedge">
                  <div className="brk-hedge-h mono">SECTOR HEDGE</div>
                  <div className="brk-hedge-v mono">Short <b className="rd-c">{topSec ? topSec.k : "—"}</b> ETF <span className="dim2">{topSec ? topSec.pct.toFixed(0) : 0}% tilt</span></div>
                  <div className="mono dim2" style={{ fontSize: 10.5 }}>trims your largest sector concentration</div>
                </div>
                <div className="brk-hedge">
                  <div className="brk-hedge-h mono">TAIL HEDGE</div>
                  <div className="brk-hedge-v mono">3-mo 5% OTM put spread <span className="dim2">≈{brFmt$(tailCost)}</span></div>
                  <div className="mono dim2" style={{ fontSize: 10.5 }}>{(tailCost / m.gross * 100).toFixed(1)}% of gross · caps a left-tail gap</div>
                </div>
                <div className="brk-hedge">
                  <div className="brk-hedge-h mono">PAIRS IDEA (factor-neutral)</div>
                  <div className="brk-hedge-v mono"><b className="gn-c">+{longLeg.sym}</b> / <b className="rd-c">−{shortLeg.sym}</b></div>
                  <div className="mono dim2" style={{ fontSize: 10.5 }}>long strongest, short weakest — isolates relative alpha, dollar-neutral</div>
                </div>
              </div>
              <div className="lab-verdict mono dim2">Your book is net <b className={m.net >= 0 ? "gn-c" : "rd-c"}>{m.net >= 0 ? "long" : "short"}</b> with β {m.rk.beta.toFixed(2)} — these overlays let you keep the stock-specific bets while dialing out the market/sector beta you're not being paid for. Paper book: hedges are illustrative sizing, not orders.</div>
            </>
          );
        })()}
      </div>

      <div className="lab-card">
        <div className="lab-card-h mono">RETURN ATTRIBUTION · by factor &amp; specific</div>
        {(() => {
          // attribute book return = Σ (factor tilt × factor period return) + stock-specific
          const facRet = { "Value": -1.2, "Momentum": 3.4, "Size": 0.8, "Quality": 1.1, "Low-Vol": -0.6 }; // demo period factor returns %
          const contribs = m.factors.map(f => ({ k: f.label, v: +(f.tilt * (facRet[f.label] || 0)).toFixed(2) }));
          const factorTotal = contribs.reduce((s, c) => s + c.v, 0);
          const bookRet = +(m.sum.unrealizedPct || 4.2).toFixed(2);
          const specific = +(bookRet - factorTotal).toFixed(2);
          const all = [...contribs, { k: "Stock-specific (α)", v: specific, alpha: true }];
          const mx = Math.max(...all.map(c => Math.abs(c.v)), 0.5);
          return (
            <>
              <div className="brk-attrib">
                {all.map((c, i) => (
                  <div key={i} className="brk-attrib-row">
                    <span className={`brk-attrib-k mono ${c.alpha ? "copper" : "dim2"}`}>{c.k}</span>
                    <div className="brk-attrib-track"><span className="brk-attrib-mid" /><span className={`brk-attrib-fill ${c.v >= 0 ? "pos" : "neg"}`} style={{ left: c.v >= 0 ? "50%" : `${50 - Math.abs(c.v) / mx * 48}%`, width: `${Math.abs(c.v) / mx * 48}%` }} /></div>
                    <span className={`brk-attrib-v mono ${c.v >= 0 ? "gn-c" : "rd-c"}`}>{c.v >= 0 ? "+" : ""}{c.v}%</span>
                  </div>
                ))}
              </div>
              <div className="lab-verdict mono dim2">Book return <b>{bookRet >= 0 ? "+" : ""}{bookRet}%</b> decomposed: <b className={factorTotal >= 0 ? "gn-c" : "rd-c"}>{factorTotal >= 0 ? "+" : ""}{factorTotal.toFixed(1)}%</b> from factor tilts (mostly <b>Momentum</b>), <b className={specific >= 0 ? "gn-c" : "rd-c"}>{specific >= 0 ? "+" : ""}{specific}%</b> stock-specific α. If most of your return is <i>factor</i>, you're being paid for beta you could get cheaper — the α row is the part that's actually your edge. Demo attribution model.</div>
            </>
          );
        })()}
      </div>

      <div className="lab-card">
        <div className="lab-card-h mono">CROWDING &amp; POSITIONING · per name</div>
        <table className="dtable brk-tbl">
          <thead><tr><th>Name</th><th className="r">Short int.</th><th className="r">Days-to-cover</th><th className="r">13F Δ qtr</th><th className="r">Crowding</th><th className="r">Capacity</th><th>Read</th></tr></thead>
          <tbody>
            {m.names.slice().sort((a, b) => b.mv - a.mv).map(r => {
              const si = (brHash(r.sym + "si") % 22) + 1;                 // short interest %
              const dtc = +(((brHash(r.sym + "dtc") % 60) / 10) + 0.5).toFixed(1);  // days to cover
              const f13 = ((brHash(r.sym + "13f") % 40) - 18);            // 13F net qtr change %
              const crowd = Math.round(Math.min(99, si * 1.8 + dtc * 5 + Math.max(0, -f13) * 1.2)); // 0-100
              const ct = crowd >= 66 ? "rd" : crowd >= 45 ? "amb" : "gn";
              const decay = (brHash(r.sym + "dec") % 35) + 5;             // alpha half-life decay %/mo
              const cap = decay > 28 ? "thin" : decay > 16 ? "moderate" : "deep";
              const capT = decay > 28 ? "rd" : decay > 16 ? "amb" : "gn";
              const read = crowd >= 66 ? "crowded — squeeze/unwind risk" : crowd >= 45 ? "moderate positioning" : "uncrowded — clean tape";
              return (
                <tr key={r.id} className="brk-row" onClick={() => onTicker && onTicker(r.sym)}>
                  <td className="mono"><b>{r.sym}</b></td>
                  <td className="r mono">{si}%</td>
                  <td className="r mono">{dtc}</td>
                  <td className={`r mono ${f13 >= 0 ? "gn-c" : "rd-c"}`}>{f13 >= 0 ? "+" : ""}{f13}%</td>
                  <td className="r mono"><span className={`brk-crowd kpi-tone--${ct}`}>{crowd}</span></td>
                  <td className={`r mono kpi-tone--${capT}`} title={`alpha decay ~${decay}%/mo`}>{cap}</td>
                  <td className="mono dim2" style={{ fontSize: 11 }}>{read}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <div className="lab-verdict mono dim2">Crowding blends short interest, days-to-cover and 13F flow into a 0–100 score. <b className="rd-c">High</b> = many funds already in the trade (squeeze fuel on the way up, stampede risk on the way out); <b className="gn-c">low</b> = you're early / contrarian. A desk checks this before sizing up a "consensus" name. Demo positioning model.</div>
      </div>

      <div className="lab-card">
        <div className="lab-card-h mono">RISK CONTRIBUTION · component vs weight
          <span className="brk-sort">
            <button className={sortRisk ? "is-on" : ""} onClick={() => setSortRisk(true)}>by risk</button>
            <button className={!sortRisk ? "is-on" : ""} onClick={() => setSortRisk(false)}>by weight</button>
          </span>
        </div>
        <table className="dtable brk-tbl">
          <thead><tr><th>Name</th><th>Sector</th><th className="r">β</th><th className="r">Weight</th><th className="r">Risk share</th><th>Risk vs weight</th></tr></thead>
          <tbody>
            {namesSorted.map(r => {
              const punch = r.riskPct - r.wtPct;  // +ve = contributes more risk than its weight
              return (
                <tr key={r.id} className="brk-row" onClick={() => onTicker && onTicker(r.sym)}>
                  <td className="mono"><b>{r.sym}</b></td>
                  <td className="dim2 mono" style={{ fontSize: 11 }}>{r.sector}</td>
                  <td className="r mono">{r.beta.toFixed(2)}</td>
                  <td className="r mono">{r.wtPct.toFixed(1)}%</td>
                  <td className="r mono"><b>{r.riskPct.toFixed(1)}%</b></td>
                  <td>
                    <div className="brk-punch"><span className="brk-punch-mid" /><span className={`brk-punch-fill ${punch >= 0 ? "neg" : "pos"}`} style={{ left: punch >= 0 ? "50%" : `${50 - Math.min(48, Math.abs(punch) * 3)}%`, width: `${Math.min(48, Math.abs(punch) * 3)}%` }} /></div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <div className="lab-verdict mono dim2">Risk share = each name's contribution to book volatility (weight × standalone vol), normalized. Bars to the <b className="rd-c">right</b> = the name carries <b>more risk than its weight</b> (a high-β position punching above its size); <b className="gn-c">left</b> = ballast. The book β is <b className={`${betaTone}-c`}>{m.rk.beta.toFixed(2)}</b>; 1-day 95% VaR ≈ <b>{brFmt$(m.rk.var95)}</b> ({(m.rk.var95 / m.invested * 100).toFixed(1)}% of invested). Demo factor + risk model.</div>
      </div>
    </div>
  );
}
const BR_SEC = { Tech: "var(--cy)", Finance: "var(--blue)", Healthcare: "var(--violet)", Energy: "var(--amb)", Materials: "var(--copper)", Industrials: "var(--ink-2)", Consumer: "var(--gn)", Utilities: "var(--blue)", Crypto: "var(--amb)", Cash: "var(--ink-3)" };

function BrHeader({ scope, setScope, MyPF }) {
  const list = MyPF ? MyPF.list() : [];
  return (
    <div className="wsx-hdr">
      <div className="wsx-hdr-l">
        <div className="wsx-eyebrow mono">PORTFOLIO · FACTOR &amp; EXPOSURE</div>
        <h1 className="wsx-title mono">Book Risk</h1>
        <div className="wsx-sub mono dim2">aggregate factor tilts · gross / net / leverage · concentration · per-name risk contribution — across your whole book</div>
      </div>
      <div className="wsx-hdr-r">
        <div className="brk-scope seg">
          <button className={`seg-btn ${scope === "all" ? "is-on" : ""}`} onClick={() => setScope("all")}>All books</button>
          <button className={`seg-btn ${scope !== "all" ? "is-on" : ""}`} onClick={() => setScope("active")}>Active</button>
        </div>
      </div>
    </div>
  );
}

function BrTile({ l, v, s, tone = "ink", small }) {
  return (
    <div className={`brk-tile ${small ? "brk-tile--sm" : ""}`}>
      <div className="brk-tile-l mono dim2">{l}</div>
      <div className={`brk-tile-v mono kpi-tone--${tone}`}>{v}</div>
      <div className="brk-tile-s mono dim">{s}</div>
    </div>
  );
}
window.SurfaceBookRisk = SurfaceBookRisk;

(function () {
  if (document.getElementById("brk-css")) return;
  const s = document.createElement("style"); s.id = "brk-css";
  s.textContent = `
  .brk{padding:0 0 40px;}
  .brk-tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:14px 0 16px;}
  @media(max-width:1100px){.brk-tiles{grid-template-columns:repeat(2,1fr);}}
  .brk-tile{background:var(--bg-1);border:1px solid var(--line);border-radius:7px;padding:12px 14px;}
  .brk-tile--sm{padding:9px 11px;}
  .brk-tile-l{font-size:9.5px;letter-spacing:.1em;text-transform:uppercase;}
  .brk-tile-v{font-size:21px;font-weight:600;margin-top:3px;}
  .brk-tile--sm .brk-tile-v{font-size:16px;}
  .brk-tile-s{font-size:10px;margin-top:2px;}
  .brk-2col{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px;}
  @media(max-width:900px){.brk-2col{grid-template-columns:1fr;}}
  .lab-card{background:var(--bg-1);border:1px solid var(--line);border-radius:7px;padding:14px 16px;margin-bottom:12px;}
  .lab-card-h{font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--ink-3);margin-bottom:12px;display:flex;justify-content:space-between;align-items:center;}
  .brk-facs{display:flex;flex-direction:column;gap:9px;}
  .brk-fac{display:grid;grid-template-columns:74px 1fr 46px;align-items:center;gap:10px;}
  .brk-fac-k{font-size:11.5px;}
  .brk-fac-track{position:relative;height:14px;background:var(--bg-3);border-radius:3px;}
  .brk-fac-mid{position:absolute;left:50%;top:-2px;bottom:-2px;width:1px;background:var(--line-2);}
  .brk-fac-fill{position:absolute;top:0;bottom:0;border-radius:3px;}
  .brk-fac-fill.pos{background:var(--gn);} .brk-fac-fill.neg{background:var(--rd);}
  .brk-fac-v{font-size:12px;text-align:right;}
  .gn-c{color:var(--gn);} .rd-c{color:var(--rd);} .amb-c{color:var(--amb);}
  .brk-conc-tiles{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:12px;}
  .brk-top5{display:flex;flex-direction:column;gap:6px;}
  .brk-top5-row{display:grid;grid-template-columns:52px 1fr 44px;align-items:center;gap:8px;background:none;border:none;padding:2px 0;cursor:pointer;}
  .brk-t5-sym{font-size:12px;color:var(--ink-1);text-align:left;}
  .brk-t5-track{height:9px;background:var(--bg-3);border-radius:3px;overflow:hidden;}
  .brk-t5-fill{display:block;height:100%;background:var(--copper);border-radius:3px;}
  .brk-t5-w{font-size:11px;text-align:right;}
  .brk-top5-row:hover .brk-t5-sym{color:var(--copper);}
  .brk-sort{display:inline-flex;gap:4px;}
  .brk-sort button{font-family:var(--mono);font-size:9.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-3);background:var(--bg-3);border:1px solid var(--line);border-radius:4px;padding:2px 8px;cursor:pointer;}
  .brk-sort button.is-on{color:var(--copper);border-color:var(--copper);}
  .brk-tbl{width:100%;}
  .brk-row{cursor:pointer;} .brk-row:hover{background:var(--bg-2);}
  .brk-punch{position:relative;height:12px;background:var(--bg-3);border-radius:3px;min-width:120px;}
  .brk-punch-mid{position:absolute;left:50%;top:-2px;bottom:-2px;width:1px;background:var(--line-2);}
  .brk-punch-fill{position:absolute;top:0;bottom:0;border-radius:3px;}
  .brk-punch-fill.pos{background:var(--gn);} .brk-punch-fill.neg{background:var(--rd);}
  .brk-crowd{font-family:var(--mono);font-weight:700;font-size:12px;padding:1px 8px;border-radius:20px;}
  .brk-voltgt{display:flex;align-items:center;gap:8px;margin-top:10px;padding-top:10px;border-top:1px solid var(--line);flex-wrap:wrap;}
  .brk-voltgt > span:first-child{font-size:9.5px;letter-spacing:.1em;}
  .brk-vt-btn{font-family:var(--mono);font-size:11px;color:var(--ink-2);background:var(--bg-3);border:1px solid var(--line);border-radius:4px;padding:3px 10px;cursor:pointer;}
  .brk-vt-btn.is-on{color:var(--copper);border-color:var(--copper);}
  .brk-vt-read{font-size:11px;color:var(--ink-2);margin-left:6px;}
  .brk-attrib{display:flex;flex-direction:column;gap:7px;}
  .brk-attrib-row{display:grid;grid-template-columns:120px 1fr 56px;align-items:center;gap:10px;}
  .brk-attrib-k{font-size:11px;}
  .brk-attrib-track{position:relative;height:12px;background:var(--bg-3);border-radius:3px;}
  .brk-attrib-mid{position:absolute;left:50%;top:-2px;bottom:-2px;width:1px;background:var(--line-2);}
  .brk-attrib-fill{position:absolute;top:0;bottom:0;border-radius:3px;}
  .brk-attrib-fill.pos{background:var(--gn);} .brk-attrib-fill.neg{background:var(--rd);}
  .brk-attrib-v{font-size:11.5px;text-align:right;}
  .brk-hedges{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;}
  .brk-hedge{background:var(--bg-2);border:1px solid var(--line);border-radius:6px;padding:10px 12px;}
  .brk-hedge-h{font-size:9px;letter-spacing:.1em;color:var(--ink-3);margin-bottom:4px;}
  .brk-hedge-v{font-size:13px;color:var(--ink-1);margin-bottom:2px;}
  @media(max-width:760px){.brk-hedges{grid-template-columns:1fr;}}
  .pf-secbar{display:flex;height:14px;border-radius:3px;overflow:hidden;gap:1px;margin-bottom:10px;}
  .pf-secseg{height:100%;}
  .pf-seclegend{display:flex;flex-wrap:wrap;gap:12px;}
  .pf-secrow{display:flex;align-items:center;gap:5px;}
  .pf-secdot{width:8px;height:8px;border-radius:2px;}
  .pf-seck{font-size:11px;} .pf-secv{font-size:11px;}
  `;
  document.head.appendChild(s);
})();

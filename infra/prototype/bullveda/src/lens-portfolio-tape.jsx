// lens-portfolio.jsx + lens-tape.jsx

// ════════════════════════════════════════════════════════════════════
// PORTFOLIO — REAL book state from /api/portfolio (Alpaca paper sync).
// Held positions, candidate sizing, correlation-to-book (real OHLCV),
// sector exposure, sleep-test from realized book vol. No fabricated
// positions — honest empty states when the book is flat or a feed is
// absent. Seeded synchronously from window.__BV.portfolio (boot cache),
// refreshed async from /api/portfolio.
// ════════════════════════════════════════════════════════════════════

function pfNum(v) { const n = Number(v); return Number.isFinite(n) ? n : null; }

function useBook() {
  const read = () => (window.__BV && window.__BV.portfolio) || (window.__BV && window.__BV._bookCache) || null;
  const [book, setBook] = React.useState(read);
  React.useEffect(() => {
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

// sign-aware open-R multiple for a held position
function pfOpenR(p) {
  const entry = pfNum(p.entry_price), stop = pfNum(p.stop), cur = pfNum(p.current_price);
  if (entry == null || stop == null || cur == null) return null;
  const risk = Math.abs(entry - stop); if (!(risk > 0)) return null;
  const short = (p.direction || "").toLowerCase() === "short";
  return short ? (entry - cur) / risk : (cur - entry) / risk;
}

function pfDaysHeld(p) {
  const s = p.entry_date || (p.entry_datetime || "").slice(0, 10); if (!s) return null;
  const t = Date.parse(s); if (!Number.isFinite(t)) return null;
  return Math.max(0, Math.round((Date.now() - t) / 86400000));
}

// max drawdown % from an equity curve [{equity}]
function pfMaxDD(curve) {
  let peak = -Infinity, mdd = 0;
  for (const pt of curve) {
    const e = pfNum(pt.equity); if (e == null) continue;
    if (e > peak) peak = e;
    if (peak > 0) mdd = Math.min(mdd, (e - peak) / peak);
  }
  return mdd * 100; // ≤ 0
}

function pfSectorOf(sym) {
  try {
    const r = window.__BV && window.__BV.findRow ? window.__BV.findRow(sym) : null;
    if (r && r.sector) return r.sector;
  } catch (e) {}
  return null;
}

function pfPearson(a, b) {
  const n = Math.min(a.length, b.length); if (n < 10) return null;
  const A = a.slice(a.length - n), B = b.slice(b.length - n);
  const ma = A.reduce((x, y) => x + y, 0) / n, mb = B.reduce((x, y) => x + y, 0) / n;
  let num = 0, da = 0, db = 0;
  for (let i = 0; i < n; i++) { const x = A[i] - ma, y = B[i] - mb; num += x * y; da += x * x; db += y * y; }
  if (da <= 0 || db <= 0) return null;
  return num / Math.sqrt(da * db);
}

// fetch 60-day daily returns for a set of symbols (real OHLCV)
function usePfReturns(symbols) {
  const key = symbols.slice().sort().join(",");
  const [data, setData] = React.useState(null);
  React.useEffect(() => {
    let on = true;
    if (!symbols.length || !(window.__BV && window.__BV.get)) { setData({}); return; }
    Promise.all(symbols.map(s =>
      window.__BV.get("/api/ohlcv/" + encodeURIComponent(s) + "?days=75")
        .then(d => [s, (d && Array.isArray(d.candles)) ? d.candles : []])
        .catch(() => [s, []])
    )).then(pairs => {
      if (!on) return;
      const out = {};
      for (const [s, candles] of pairs) {
        const closes = candles.map(c => pfNum(c.close)).filter(v => v != null);
        const rets = [];
        for (let i = 1; i < closes.length; i++) rets.push(closes[i] / closes[i - 1] - 1);
        out[s] = rets;
      }
      setData(out);
    }).catch(() => { if (on) setData({}); });
    return () => { on = false; };
  }, [key]);
  return data;
}

function LensPortfolio({ ticker, mode, sizeCat, headerStyle, kpiStyle, heroStyle }) {
  const s1 = useStateToggle("pf-1"); const s2 = useStateToggle("pf-2");
  const s3 = useStateToggle("pf-3"); const s4 = useStateToggle("pf-4");
  const s5 = useStateToggle("pf-5");
  const book = useBook();
  const sz = (window.positionSizing && ticker) ? window.positionSizing(ticker, mode) : null;

  if (!book) {
    return (
      <div className="lens lens--pf">
        <div className="lens-section"><div className="lens-pad">
          <div className="smc-empty mono dim2" style={{ padding: 16 }}>
            Loading book from <b className="copper">/api/portfolio</b> (Alpaca paper sync)…
          </div>
        </div></div>
      </div>
    );
  }

  const equity = pfNum(book.equity);
  const longExp = pfNum(book.invested), shortExp = pfNum(book.short_exposure);
  const gross = (longExp != null && shortExp != null) ? longExp + shortExp : null;
  const grossPct = (gross != null && equity) ? gross / equity * 100 : null;
  const openCt = book.open_count, maxPos = book.max_positions;
  const candPct = (sz && sz.ok) ? sz.navPct : null;
  const wr = pfNum(book.win_rate);

  return (
    <div className="lens lens--pf">
      <div className="hero pf-hero">
        <div className="th-left">
          <div className="label-cap">Book fit · {(ticker && ticker.symbol) || ""}</div>
          <div className="th-score">
            <div className="th-score-num mono">{candPct != null ? "+" + candPct.toFixed(1) + "%" : "—"}</div>
            <Pill tone={candPct == null ? "ink" : candPct > 10 ? "rd" : candPct > 7 ? "amb" : "gn"} dot>
              {candPct == null ? "candidate not sizable" : "NAV this name would add"}
            </Pill>
          </div>
          <div className="th-pill-row">
            <Pill tone="ink" small>NAV ${equity != null ? Math.round(equity).toLocaleString() : "—"}{sz && sz.demo ? " · demo" : ""}</Pill>
            <Pill tone={grossPct != null && grossPct > 100 ? "amb" : "gn"} small>gross {grossPct != null ? grossPct.toFixed(0) + "%" : "—"}</Pill>
            <Pill tone="gn" small>{openCt != null ? openCt : "—"}/{maxPos != null ? maxPos : "—"} slots</Pill>
            {wr != null && <Pill tone={wr >= 50 ? "gn" : "amb"} small>win rate {wr.toFixed(0)}%</Pill>}
          </div>
        </div>
        <div className="th-right">
          <BookSparkline book={book} />
        </div>
      </div>

      <div className="lens-section">
        <SectionHeader n={1} title="Held-Position State"
          sub="cash · positions · open R · live Alpaca paper sync"
          style={headerStyle} right={<StateToggle name="pf-1" />} />
        <StateWrap state={s1.value} source="portfolio_state · Alpaca paper">
          <div className="lens-pad"><HeldState book={book} candidate={ticker} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={2} title="Position Simulator"
          sub="this name · 0.5× / 1× / 1.5× / 2× the engine-sized risk"
          style={headerStyle} right={<StateToggle name="pf-2" />} />
        <StateWrap state={s2.value} source="positionSizing · live NAV">
          <div className="lens-pad"><PositionSim sz={sz} ticker={ticker} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={3} title="Correlation to Book"
          sub="60-day daily-return correlation · candidate vs each held"
          style={headerStyle} right={<StateToggle name="pf-3" />} />
        <StateWrap state={s3.value} source="EODHD OHLCV · 60d returns">
          <div className="lens-pad"><CorrTable book={book} candidate={ticker} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={4} title="Sector Exposure"
          sub="held notional by sector · pre vs post adding this name"
          style={headerStyle} right={<StateToggle name="pf-4" />} />
        <StateWrap state={s4.value} source="positions × sector map">
          <div className="lens-pad"><SectorExposure book={book} candidate={ticker} sz={sz} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={5} title="Sleep-Test · Overnight Risk"
          sub="modeled from realized book volatility (equity curve) + candidate ER"
          style={headerStyle} right={<StateToggle name="pf-5" />} />
        <StateWrap state={s5.value} source="realized book vol · scenario">
          <div className="lens-pad"><SleepTest book={book} candidate={ticker} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={6} title="Cross-Lens Confluence" style={headerStyle} />
        <div className="lens-pad">
          <CrossLens lead="copper" cells={[
            { lens: "Book", verdict: openCt != null ? `${openCt}/${maxPos}` : "—", tone: "gn", note: "slots used" },
            { lens: "Gross", verdict: grossPct != null ? `${grossPct.toFixed(0)}%` : "—", tone: grossPct != null && grossPct > 100 ? "amb" : "gn", note: "exposure / NAV" },
            { lens: "Add", verdict: candPct != null ? `+${candPct.toFixed(1)}%` : "—", tone: candPct == null ? "ink" : candPct > 10 ? "rd" : candPct > 7 ? "amb" : "gn", note: "this name" },
            { lens: "Win rate", verdict: wr != null ? `${wr.toFixed(0)}%` : "—", tone: wr != null && wr >= 50 ? "gn" : "amb", note: `${book.wins || 0}W / ${book.losses || 0}L` },
            { lens: "Plan", verdict: sz && sz.ok ? "READY" : "—", tone: sz && sz.ok ? "gn" : "ink", note: sz && sz.ok ? "pre-sized ticket" : "no levels" },
          ]} />
        </div>
      </div>

      <div className="lens-call">
        <span className="label-cap">The Read · Portfolio</span>
        <span className="mono">
          Book at <b>${equity != null ? Math.round(equity).toLocaleString() : "—"}</b> · {openCt != null ? openCt : "—"}/{maxPos != null ? maxPos : "—"} slots used · gross {grossPct != null ? grossPct.toFixed(0) + "%" : "—"} of NAV.
          {candPct != null
            ? <> This name sizes to <b className={candPct > 10 ? "dn" : "copper"}>+{candPct.toFixed(1)}% NAV</b> at the engine risk budget{sz && sz.maxLoss ? <> (max loss ${Math.round(sz.maxLoss).toLocaleString()})</> : null}.</>
            : <> No engine levels for this name — size it manually in <b className="copper">Plan</b>.</>}
        </span>
      </div>
    </div>
  );
}

function BookSparkline({ book }) {
  const curve = (book && Array.isArray(book.equity_curve)) ? book.equity_curve : [];
  if (curve.length < 2) {
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 8 }}>
        <div className="label-cap">Book equity</div>
        <div className="mono" style={{ fontSize: 14 }}>{book && pfNum(book.equity) != null ? "$" + Math.round(book.equity).toLocaleString() : "—"}</div>
        <div className="mono dim2" style={{ fontSize: 10 }}>equity curve &lt; 2 points</div>
      </div>
    );
  }
  const data = curve.map(p => pfNum(p.equity)).filter(v => v != null);
  const last = data[data.length - 1], prev = data[data.length - 2];
  const dayChg = prev ? (last - prev) / prev * 100 : 0;
  const mdd = pfMaxDD(curve);
  const up = last >= data[0];
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 8 }}>
      <div className="label-cap">Book equity · {data.length}d</div>
      <Sparkline data={data} color={up ? "var(--gn)" : "var(--rd)"} w={220} h={56} />
      <div className="mono dim2" style={{ fontSize: 11 }}>
        ${Math.round(last).toLocaleString()} · <span className={dayChg >= 0 ? "up" : "dn"}>{dayChg >= 0 ? "+" : ""}{dayChg.toFixed(2)}% today</span> · max DD {mdd.toFixed(1)}%
      </div>
    </div>
  );
}

function HeldState({ book, candidate }) {
  const rows = (book && Array.isArray(book.positions)) ? book.positions : [];
  if (!rows.length) {
    return <div className="smc-empty mono dim2">Flat — no open positions in the paper book. Cash ${book && pfNum(book.cash) != null ? Math.round(book.cash).toLocaleString() : "—"}.</div>;
  }
  const candSym = (candidate && candidate.symbol || "").toUpperCase();
  const totalPL = rows.reduce((a, p) => a + (pfNum(p.unrealized_pnl_dollars) || 0), 0);
  const gross = (pfNum(book.invested) || 0) + (pfNum(book.short_exposure) || 0);
  return (
    <table className="dtable">
      <thead><tr>
        <th>Sym</th><th>Dir</th><th className="r">Qty</th><th className="r">Entry</th>
        <th className="r">Last</th><th className="r">Open R</th><th className="r">P/L</th><th className="r">Held d</th>
      </tr></thead>
      <tbody>
        {rows.map((p, i) => {
          const oR = pfOpenR(p), pl = pfNum(p.unrealized_pnl_dollars), dh = pfDaysHeld(p);
          const short = (p.direction || "").toLowerCase() === "short";
          const isCand = (p.ticker || "").toUpperCase() === candSym;
          return (
            <tr key={i} className={isCand ? "is-current" : ""}>
              <td className="mono"><b>{p.ticker}</b>{isCand ? <span className="dim2"> ◀ this name</span> : null}</td>
              <td><Pill tone={short ? "rd" : "gn"} small>{short ? "SHORT" : "LONG"}</Pill></td>
              <td className="r mono tabular">{Math.abs(pfNum(p.shares) || 0).toLocaleString()}</td>
              <td className="r mono tabular">{pfNum(p.entry_price) != null ? p.entry_price.toFixed(2) : "—"}</td>
              <td className="r mono tabular">{pfNum(p.current_price) != null ? p.current_price.toFixed(2) : "—"}</td>
              <td className={`r mono tabular ${oR == null ? "dim" : oR >= 0 ? "up" : "dn"}`}>{oR == null ? "—" : (oR >= 0 ? "+" : "") + oR.toFixed(2) + "R"}</td>
              <td className={`r mono tabular ${pl == null ? "dim" : pl >= 0 ? "up" : "dn"}`}>{pl == null ? "—" : (pl >= 0 ? "+" : "−") + "$" + Math.abs(Math.round(pl)).toLocaleString()}</td>
              <td className="r mono tabular dim">{dh == null ? "—" : dh}</td>
            </tr>
          );
        })}
        <tr style={{ borderTop: "1px solid var(--line)" }}>
          <td colSpan={6} className="mono dim2"><b>{rows.length} position{rows.length > 1 ? "s" : ""} · cash ${pfNum(book.cash) != null ? Math.round(book.cash).toLocaleString() : "—"} · gross ${Math.round(gross).toLocaleString()}</b></td>
          <td className={`r mono tabular ${totalPL >= 0 ? "up" : "dn"}`}>{totalPL >= 0 ? "+" : "−"}${Math.abs(Math.round(totalPL)).toLocaleString()}</td>
          <td></td>
        </tr>
      </tbody>
    </table>
  );
}

function PositionSim({ sz, ticker }) {
  if (!sz || !sz.ok) {
    return <div className="smc-empty mono dim2">— no engine levels for {(ticker && ticker.symbol) || "this name"} (need a valid entry / stop / target to size). Set them in Plan.</div>;
  }
  const base = sz.shares, entry = sz.entry, risk = sz.risk, nav = sz.nav;
  const rows = [0.5, 1, 1.5, 2].map(m => {
    const sh = Math.max(1, Math.round(base * m));
    const notional = sh * entry, maxL = sh * risk;
    const navPct = notional / nav * 100;
    return { m, sh, notional, navPct, maxL, lossPct: maxL / nav * 100,
      tone: navPct > 13 ? "rd" : navPct > 10 ? "amb" : m === 1 ? "copper" : "gn", on: m === 1 };
  });
  return (
    <div>
      <table className="dtable">
        <thead><tr><th>Size</th><th className="r">Shares</th><th className="r">Notional</th><th className="r">% NAV</th><th className="r">Max loss</th><th className="r">% NAV risk</th></tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className={r.on ? "is-current" : ""}>
              <td className="mono"><b>{r.m.toFixed(1)}×</b>{r.on ? <span className="dim2"> engine</span> : null}</td>
              <td className="r mono tabular">{r.sh.toLocaleString()}</td>
              <td className="r mono tabular">${Math.round(r.notional).toLocaleString()}</td>
              <td className={`r mono tabular kpi-tone--${r.tone}`}>{r.navPct.toFixed(1)}%</td>
              <td className={`r mono tabular kpi-tone--${r.tone}`}>−${Math.round(r.maxL).toLocaleString()}</td>
              <td className="mono dim r">{r.lossPct.toFixed(2)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="corr-note mono dim2" style={{ marginTop: 6 }}>
        Engine 1× risk budget = ${Math.round(sz.riskBudget || 0).toLocaleString()} ({(sz.lossNavPct || 0).toFixed(2)}% NAV) · entry ${entry.toFixed(2)} · stop ${sz.stop.toFixed(2)} ({(sz.pctToStop || 0).toFixed(1)}% away) · R:R {sz.rr != null ? sz.rr.toFixed(1) : "—"}{sz.wr != null ? ` · setup WR ${(sz.wr * 100).toFixed(0)}% (n=${sz.n || 0})` : ""}.
      </div>
    </div>
  );
}

function CorrTable({ book, candidate }) {
  const candSym = (candidate && candidate.symbol || "").toUpperCase();
  const held = (book && Array.isArray(book.positions)) ? book.positions.map(p => (p.ticker || "").toUpperCase()).filter(Boolean) : [];
  const heldUnique = held.filter((s, i) => s && held.indexOf(s) === i && s !== candSym);
  const syms = candSym ? [candSym, ...heldUnique] : heldUnique;
  const rets = usePfReturns(syms);
  if (!candSym) return <div className="smc-empty mono dim2">— open a candidate from the scan to correlate it against the book.</div>;
  if (!heldUnique.length) return <div className="smc-empty mono dim2">— book has no other open names to correlate against (flat or single-name).</div>;
  if (rets == null) return <div className="smc-empty mono dim2">Fetching 60-day returns for {syms.join(", ")}…</div>;
  const candR = rets[candSym] || [];
  if (candR.length < 10) return <div className="smc-empty mono dim2">— not enough price history for {candSym} to correlate.</div>;
  const posBySym = {};
  (book.positions || []).forEach(p => { posBySym[(p.ticker || "").toUpperCase()] = Math.abs(pfNum(p.position_size) || 0); });
  let wsum = 0, cwsum = 0;
  const rows = heldUnique.map(s => {
    const c = pfPearson(candR, rets[s] || []);
    const w = posBySym[s] || 0;
    if (c != null) { wsum += w; cwsum += c * w; }
    return { sym: s, c, tone: c == null ? "ink" : c > 0.5 ? "rd" : c > 0.2 ? "amb" : "gn" };
  });
  const comp = wsum > 0 ? cwsum / wsum : null;
  rows.push({ sym: "Book composite", c: comp, tone: comp == null ? "ink" : comp > 0.5 ? "rd" : comp > 0.2 ? "amb" : "gn", bold: true });
  return (
    <div className="corr-tbl">
      {rows.map((r, i) => (
        <div key={i} className={`corr-row ${r.bold ? "is-bold" : ""}`}>
          <span className="mono">{r.sym}</span>
          <div className="corr-bar">
            <div className={`corr-bar-fill kpi-tone--${r.tone}`} style={{
              width: r.c == null ? "0%" : `${Math.abs(r.c) * 50}%`,
              marginLeft: r.c == null ? "50%" : r.c < 0 ? `${50 - Math.abs(r.c) * 50}%` : "50%",
              background: r.tone === "gn" ? "var(--gn)" : r.tone === "amb" ? "var(--amb)" : "var(--rd)",
            }} />
            <div className="corr-bar-axis" />
          </div>
          <span className={`mono kpi-tone--${r.tone}`}>{r.c == null ? "—" : (r.c >= 0 ? "+" : "") + r.c.toFixed(2)}</span>
        </div>
      ))}
      <div className="corr-note mono dim2">Pearson on 60-day daily returns (EODHD), notional-weighted for the composite. High positive correlation to existing longs concentrates directional risk; a short leg flips the sign of the hedge.</div>
    </div>
  );
}

function SectorExposure({ book, candidate, sz }) {
  const positions = (book && Array.isArray(book.positions)) ? book.positions : [];
  const equity = pfNum(book.equity) || 1;
  if (!positions.length && !(sz && sz.ok)) return <div className="smc-empty mono dim2">— flat book and no candidate sizing; nothing to allocate.</div>;
  const pre = {}; let unknown = 0;
  positions.forEach(p => {
    const sec = pfSectorOf((p.ticker || "").toUpperCase()) || "Unknown";
    const not = Math.abs(pfNum(p.position_size) || 0);
    pre[sec] = (pre[sec] || 0) + not;
    if (sec === "Unknown") unknown += not;
  });
  const post = Object.assign({}, pre);
  const candSym = (candidate && candidate.symbol || "").toUpperCase();
  const candSec = pfSectorOf(candSym) || (candidate && candidate.sector) || "Unknown";
  const candNot = (sz && sz.ok) ? sz.notional : 0;
  if (candNot) post[candSec] = (post[candSec] || 0) + candNot;
  const secs = Object.keys(post).sort((a, b) => post[b] - post[a]);
  if (!secs.length) return <div className="smc-empty mono dim2">— no sizable exposure.</div>;
  return (
    <div>
      <table className="dtable">
        <thead><tr><th>Sector</th><th className="r">Pre %NAV</th><th className="r">Post %NAV</th><th>Δ</th></tr></thead>
        <tbody>
          {secs.map((s, i) => {
            const a = (pre[s] || 0) / equity * 100, b = (post[s] || 0) / equity * 100, d = b - a;
            const tone = b > 40 ? "rd" : b > 25 ? "amb" : "gn";
            return (
              <tr key={i}>
                <td className="mono">{s}{s === candSec && candNot ? <span className="dim2"> ◀ adds here</span> : null}</td>
                <td className="r mono tabular dim">{a.toFixed(1)}%</td>
                <td className={`r mono tabular kpi-tone--${tone}`}>{b.toFixed(1)}%</td>
                <td className={`mono ${d > 0.05 ? "up" : d < -0.05 ? "dn" : "dim"}`}>{d >= 0 ? "+" : ""}{d.toFixed(1)}%</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="corr-note mono dim2" style={{ marginTop: 6 }}>
        Gross notional ÷ NAV per sector (shorts counted gross). {unknown > 0 ? "“Unknown” = held name not in the current scan universe (no sector tag). " : ""}Sectors above ~25% NAV concentrate single-factor risk.
      </div>
    </div>
  );
}

function SleepTest({ book, candidate }) {
  const curve = (book && Array.isArray(book.equity_curve)) ? book.equity_curve.map(p => pfNum(p.equity)).filter(v => v != null) : [];
  const equity = pfNum(book.equity) || 0;
  let sigmaPct = null;
  if (curve.length >= 8) {
    const rets = [];
    for (let i = 1; i < curve.length; i++) if (curve[i - 1] > 0) rets.push(curve[i] / curve[i - 1] - 1);
    if (rets.length >= 5) {
      const m = rets.reduce((a, b) => a + b, 0) / rets.length;
      const v = rets.reduce((a, b) => a + (b - m) * (b - m), 0) / rets.length;
      sigmaPct = Math.sqrt(v);
    }
  }
  const sig$ = sigmaPct != null ? sigmaPct * equity : null;
  const er = (candidate && candidate.earnings && candidate.earnings.days != null) ? candidate.earnings : null;
  const tiles = [
    { label: "Overnight 1σ", value: sig$ != null ? `−$${Math.round(sig$).toLocaleString()}` : "—", tone: "gn", sub: sigmaPct != null ? `${(sigmaPct * 100).toFixed(2)}% book σ/day` : "need ≥8d curve" },
    { label: "Stress 3σ", value: sig$ != null ? `−$${Math.round(sig$ * 3).toLocaleString()}` : "—", tone: "amb", sub: "realized book vol ×3" },
    { label: "ER-week", value: er ? `T−${er.days}d` : "none", tone: er && er.days <= 7 ? "rd" : er ? "amb" : "gn", sub: er ? (er.days <= 7 ? "candidate reports in window" : "candidate ER scheduled") : "no candidate ER" },
    { label: "Sleep score", value: sigmaPct == null ? "—" : sigmaPct * 100 < 0.5 ? "A" : sigmaPct * 100 < 1.0 ? "B" : "C", tone: sigmaPct == null ? "ink" : sigmaPct * 100 < 0.5 ? "gn" : sigmaPct * 100 < 1.0 ? "amb" : "rd", sub: "from realized vol" },
  ];
  return (
    <div>
      <div className="kpi-row" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
        {tiles.map((t, i) => <KpiTile key={i} label={t.label} value={t.value} tone={t.tone} sub={t.sub} />)}
      </div>
      <div className="corr-note mono dim2" style={{ marginTop: 6 }}>
        Overnight loss bands are the book's realized daily volatility (from the {curve.length}-point equity curve) scaled to NAV — a portfolio-level estimate, not a per-position Greek. ER-week flags the candidate's next report inside the swing window.
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────
// TAPE · FLOW — news, insider, sentiment, 13F, catalysts
// ────────────────────────────────────────────────────────────
// Real tape data off the ticker's fundamentals (13F holders + insider) + sentiment
// pillar + earnings catalyst. Per-ticker news isn't on the ticker object (only
// market-level), so the news timeline shows an honest "not in feed" state.
function tapeData(ticker) {
  const holders = Array.isArray(ticker.holders) ? ticker.holders : (ticker.holders ? Object.values(ticker.holders) : []);
  const insider = Array.isArray(ticker.insiderTx) ? ticker.insiderTx : (ticker.insiderTx ? Object.values(ticker.insiderTx) : []);
  const sp = (ticker.pillars && typeof ticker.pillars.sentiment === "number") ? ticker.pillars.sentiment
    : (ticker.pillarPct && typeof ticker.pillarPct.sentiment === "number") ? ticker.pillarPct.sentiment : null;
  const sentNorm = (typeof sp === "number") ? +(sp / 50 - 1).toFixed(2) : null;   // 0-100 → −1..+1
  const er = (ticker.earnings && ticker.earnings.days != null) ? ticker.earnings : null;
  return { holders, insider, sentNorm, er, any: !!(holders.length || insider.length || sentNorm != null) };
}

function LensTape({ ticker, mode, sizeCat, headerStyle, kpiStyle, heroStyle }) {
  const s1 = useStateToggle("tp-1"); const s2 = useStateToggle("tp-2");
  const s3 = useStateToggle("tp-3"); const s4 = useStateToggle("tp-4");
  const s5 = useStateToggle("tp-5");
  const td = tapeData(ticker);
  const insBuys = td.insider.filter(x => /^(P|BUY)/i.test(x.transactionCode || x.action || "")).length;
  const insSells = td.insider.filter(x => /^(S|SELL)/i.test(x.transactionCode || x.action || "")).length;
  const netIns = insBuys - insSells;
  const sentTone = td.sentNorm == null ? "ink" : td.sentNorm > 0.15 ? "gn" : td.sentNorm < -0.15 ? "rd" : "amb";

  if (!td.any) {
    return (
      <div className="lens lens--tape">
        <div className="lens-section"><div className="lens-pad">
          <div className="smc-empty mono dim2" style={{ padding: "16px" }}>
            No tape data loaded for <b className="warn">{(ticker && ticker.symbol) || "this name"}</b> yet —
            13F holders, insider transactions and the sentiment pillar come from the per-ticker fundamentals
            fetch. {ticker && ticker._loading ? "Loading…" : "Open from the scan (or wait for enrichment) to populate."}
          </div>
        </div></div>
      </div>
    );
  }

  return (
    <div className="lens lens--tape">
      <div className="hero tape-hero">
        <div className="th-left">
          <div className="label-cap">Tape read · {(ticker && ticker.symbol) || ""}</div>
          <div className="th-score">
            <div className="th-score-num mono">{netIns >= 0 ? "+" : ""}{netIns}</div>
            <Pill tone={netIns > 0 ? "gn" : netIns < 0 ? "rd" : "ink"} dot>net insider {netIns >= 0 ? "buys" : "sells"}</Pill>
            {td.sentNorm != null && <Pill tone={sentTone} small>sentiment {td.sentNorm >= 0 ? "+" : ""}{td.sentNorm}</Pill>}
          </div>
          <div className="th-pill-row">
            <Pill tone={td.insider.length ? "gn" : "ink"} small>{td.insider.length} insider tx</Pill>
            <Pill tone={td.holders.length ? "gn" : "ink"} small>{td.holders.length} 13F holders</Pill>
            {td.er && <Pill tone="copper" small>ER in {td.er.days}d</Pill>}
          </div>
        </div>
        <div className="th-right">
          <SentimentDial sentNorm={td.sentNorm} />
        </div>
      </div>

      <div className="lens-section">
        <SectionHeader n={1} title="News Timeline"
          sub="per-ticker dated · scored"
          style={headerStyle} right={<StateToggle name="tp-1" />} />
        <StateWrap state={s1.value} source="EODHD · per-ticker news">
          <div className="lens-pad"><NewsTimeline ticker={ticker} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={2} title="Insider Transactions"
          sub="Form 4 · net direction"
          style={headerStyle} right={<StateToggle name="tp-2" />} />
        <StateWrap state={s2.value} source="EODHD · InsiderTransactions">
          <div className="lens-pad"><InsiderTable rows={td.insider} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={3} title="13F Holders"
          sub="institutional ownership · qty-on-qty change"
          style={headerStyle} right={<StateToggle name="tp-4" />} />
        <StateWrap state={s4.value} source="EODHD · Holders">
          <div className="lens-pad"><HoldersTable rows={td.holders} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={4} title="Earnings Catalyst"
          sub="next scheduled report in the hold window"
          style={headerStyle} right={<StateToggle name="tp-5" />} />
        <StateWrap state={s5.value} source="earnings calendar">
          <div className="lens-pad">
            {td.er ? <div className="catcal">
              <div className="cat-countdown">
                <span className="cat-cd-n mono">{td.er.days}<span className="cat-cd-u">d</span></span>
                <div className="cat-cd-body">
                  <span className="cat-cd-lbl mono dim2">NEXT EARNINGS{td.er.date ? " · " + td.er.date : ""}</span>
                  <span className="cat-cd-evt mono">scheduled report <span className="cat-cd-imp">high impact</span></span>
                </div>
                {td.er.days <= 7 && <span className="cat-cd-warn mono">⚠ inside swing window — size −25% / flatten T−2</span>}
              </div>
            </div> : <div className="smc-empty mono dim2">— no scheduled earnings in the window</div>}
          </div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={5} title="Cross-Lens Confluence" style={headerStyle} />
        <div className="lens-pad">
          <CrossLens lead="violet" cells={[
            { lens: "Insider", verdict: `${netIns >= 0 ? "+" : ""}${netIns}`, tone: netIns > 0 ? "gn" : netIns < 0 ? "rd" : "ink", note: `${insBuys} buys / ${insSells} sells` },
            { lens: "Sentiment", verdict: td.sentNorm != null ? `${td.sentNorm >= 0 ? "+" : ""}${td.sentNorm}` : "—", tone: sentTone, note: "pillar score" },
            { lens: "Holders", verdict: `${td.holders.length}`, tone: td.holders.length ? "gn" : "ink", note: "13F institutions" },
            { lens: "Earnings", verdict: td.er ? `${td.er.days}d` : "—", tone: "amb", note: td.er ? "in window" : "none scheduled" },
            { lens: "Risk", verdict: "OK", tone: "gn", note: "tape doesn't override risk" },
          ]} />
        </div>
      </div>

      <div className="lens-call">
        <span className="label-cap">The Read · Tape</span>
        <span className="mono">
          Insider net <b className={netIns > 0 ? "up" : netIns < 0 ? "dn" : ""}>{netIns >= 0 ? "+" : ""}{netIns}</b> ({insBuys} buys / {insSells} sells) ·
          {td.sentNorm != null ? <> sentiment <b className={sentTone === "gn" ? "up" : sentTone === "rd" ? "dn" : "warn"}>{td.sentNorm >= 0 ? "+" : ""}{td.sentNorm}</b> ·</> : null}
          {" "}{td.holders.length} institutional holders{td.er ? <> · earnings in <b className="copper">{td.er.days}d</b></> : ""}.
        </span>
      </div>
    </div>
  );
}

function SentimentDial({ sentNorm }) {
  const have = typeof sentNorm === "number";
  const v = have ? Math.max(-1, Math.min(1, sentNorm)) : 0;
  const tone = !have ? "ink-3" : v > 0.15 ? "gn" : v < -0.15 ? "rd" : "amb";
  const lbl = !have ? "NO DATA" : v > 0.15 ? "BULLISH" : v < -0.15 ? "BEARISH" : "NEUTRAL";
  const txt = have ? (v >= 0 ? "+" : "") + v.toFixed(2) : "—";
  const angle = -90 + v * 90;
  const tipX = 100 + 64 * Math.cos((angle * Math.PI) / 180);
  const tipY = 110 + 64 * Math.sin((angle * Math.PI) / 180);
  return (
    <svg viewBox="0 0 200 130" width="240" height="156" style={{ overflow: "visible" }}>
      <defs>
        <linearGradient id="sd-arc" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="var(--rd)" stopOpacity="1" />
          <stop offset="50%" stopColor="var(--amb)" stopOpacity="1" />
          <stop offset="100%" stopColor="var(--gn)" stopOpacity="1" />
        </linearGradient>
      </defs>
      <path d="M 30 110 A 70 70 0 0 1 170 110" stroke="var(--line)" strokeWidth="12" fill="none" strokeLinecap="round" />
      <path d="M 30 110 A 70 70 0 0 1 170 110" stroke="url(#sd-arc)" strokeWidth="12" fill="none" strokeLinecap="round"
            style={{ filter: "drop-shadow(0 0 8px color-mix(in oklab, var(--gn) 40%, transparent))" }} />
      {/* Tick marks */}
      {[0, 0.25, 0.5, 0.75, 1].map((t, i) => {
        const a = -180 + t * 180;
        const x1 = 100 + 56 * Math.cos((a * Math.PI) / 180);
        const y1 = 110 + 56 * Math.sin((a * Math.PI) / 180);
        const x2 = 100 + 66 * Math.cos((a * Math.PI) / 180);
        const y2 = 110 + 66 * Math.sin((a * Math.PI) / 180);
        return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke="var(--bg-1)" strokeWidth="2" />;
      })}
      {/* Needle */}
      <line x1="100" y1="110" x2={tipX} y2={tipY} stroke="var(--copper)" strokeWidth="3" strokeLinecap="round"
            style={{ filter: "drop-shadow(0 0 8px var(--copper))" }} />
      <circle cx="100" cy="110" r="7" fill="var(--bg-1)" stroke="var(--copper)" strokeWidth="2.5"
              style={{ filter: "drop-shadow(0 0 8px var(--copper))" }} />
      <circle cx="100" cy="110" r="3" fill="var(--copper)" />
      <text x="100" y="128" textAnchor="middle" className="mono" fontSize="16" fill={`var(--${tone})`} fontWeight="500"
            style={{ filter: `drop-shadow(0 0 8px color-mix(in oklab, var(--${tone}) 40%, transparent))` }}>{txt}</text>
      <text x="100" y="142" textAnchor="middle" className="mono" fontSize="9" fill="var(--ink-3)" letterSpacing="0.18em">{lbl}</text>
    </svg>
  );
}

function NewsTimeline({ ticker }) {
  const raw = (ticker && Array.isArray(ticker.news_articles)) ? ticker.news_articles : [];
  if (!raw.length) {
    return <div className="smc-empty mono dim2">— per-ticker news not in this feed (market-level news lives on the Markets tab)</div>;
  }
  const items = raw.slice(0, 8).map(a => {
    const sc = typeof a.sentiment === "number" ? a.sentiment : (a.sentiment && a.sentiment.polarity) || 0;
    return {
      d: (a.date || a.published || "").slice(5, 10).replace("-", "/"),
      t: a.title || a.headline || "—",
      s: (sc >= 0 ? "+" : "") + sc.toFixed(1),
      tone: sc > 0.15 ? "gn" : sc < -0.15 ? "rd" : "ink",
    };
  });
  return (
    <div className="news-tl">
      {items.map((it, i) => (
        <div key={i} className={`news-row news-${it.tone}`}>
          <span className="mono dim2 news-when">{it.d}</span>
          <span className="mono news-title">{it.t}</span>
          <span className={`mono news-score kpi-tone--${it.tone}`}>{it.s}</span>
        </div>
      ))}
    </div>
  );
}

function InsiderTable({ rows }) {
  const src = Array.isArray(rows) ? rows : [];
  if (!src.length) return <div className="smc-empty mono dim2">— no insider transactions on file</div>;
  const mapped = src.slice(0, 8).map(r => {
    const code = (r.transactionCode || r.action || "").toUpperCase();
    const isBuy = /^(P|BUY|A)/.test(code);
    const isSell = /^(S|SELL|D)/.test(code);
    const sh = Number(r.transactionAmount ?? r.sh ?? r.shares ?? 0) || 0;
    const px = Number(r.transactionPrice ?? r.px ?? r.price ?? 0) || 0;
    return {
      date: (r.transactionDate || r.date || "").slice(5, 10).replace("-", "/"),
      who: r.ownerName || r.who || r.name || "—",
      action: isBuy ? "BUY" : isSell ? "SELL" : (code || "—"),
      sh, px, val: sh * px,
      tone: isBuy ? "gn" : isSell ? "rd" : "ink",
    };
  });
  return (
    <table className="dtable">
      <thead>
        <tr>
          <th>Date</th><th>Who</th><th>Action</th>
          <th className="r">Shares</th><th className="r">Price</th><th className="r">Value</th>
        </tr>
      </thead>
      <tbody>
        {mapped.map((r, i) => (
          <tr key={i}>
            <td className="mono dim">{r.date}</td>
            <td className="mono">{r.who}</td>
            <td><Pill tone={r.tone} small>{r.action}</Pill></td>
            <td className="r mono tabular">{r.sh.toLocaleString()}</td>
            <td className="r mono tabular">{r.px ? "$" + r.px.toFixed(2) : "—"}</td>
            <td className={`r mono tabular kpi-tone--${r.tone}`}>{r.val ? "$" + Math.round(r.val).toLocaleString() : "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function HoldersTable({ rows }) {
  const src = Array.isArray(rows) ? rows : [];
  if (!src.length) return <div className="smc-empty mono dim2">— no 13F holder data on file</div>;
  const mapped = src.map(r => {
    const ownPct = Number(r.totalShares ?? r.ownPct ?? r.pct ?? 0) || 0;
    const ch = Number(r.change_p ?? r.delta ?? 0);
    return {
      name: r.name || r.holder || "—",
      ownPct,
      ch: Number.isFinite(ch) ? ch : 0,
      tone: ch > 0.05 ? "gn" : ch < -0.05 ? "rd" : "ink",
    };
  }).sort((a, b) => b.ownPct - a.ownPct).slice(0, 8);
  return (
    <table className="dtable">
      <thead><tr><th>Holder</th><th className="r">Own %</th><th className="r">QoQ Δ</th></tr></thead>
      <tbody>
        {mapped.map((r, i) => (
          <tr key={i}>
            <td className="mono">{r.name}</td>
            <td className="r mono tabular">{r.ownPct.toFixed(1)}%</td>
            <td className={`r mono tabular kpi-tone--${r.tone}`}>{r.ch >= 0 ? "+" : ""}{r.ch.toFixed(1)}%</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

window.LensPortfolio = LensPortfolio;
window.LensTape = LensTape;

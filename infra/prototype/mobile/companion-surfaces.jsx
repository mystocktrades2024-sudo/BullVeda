// companion-surfaces.jsx — app surfaces + navigation chrome.
const { Sec: S, Panel: P, KpiGrid: KG, Chip: C, Row: R, StatStrip: SS, Sparkbars: SB, GaugeRing: GR, Cone: CO } = window;
const sfx = window.cmpHelpers;
const SIco = window.Ico;
const pctS = (n, d = 1) => sfx.fmt(n, d) + "%";

/* ── shared ── */
function SHead({ title, sub }) {
  return (
    <div className="cmp-shead">
      <span className="cmp-shead-t">{title}</span>
      <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 10 }}>
        {sub && <span className="cmp-shead-s" style={{ marginLeft: 0 }}>{sub}</span>}
        {window.HeaderActions && <window.HeaderActions />}
      </div>
    </div>
  );
}
function MiniSpark({ seed, up }) {
  const h = sfx.hash(seed);
  const pts = Array.from({ length: 9 }, (_, i) => 10 - Math.sin(i * 0.8 + h) * 4 - (up ? i * 0.5 : -i * 0.5));
  const max = Math.max(...pts), min = Math.min(...pts);
  const d = pts.map((p, i) => `${(i / 8) * 54},${20 - ((p - min) / (max - min || 1)) * 18 - 1}`).join(" ");
  return <svg className="cmp-mover-spark" viewBox="0 0 54 20" preserveAspectRatio="none"><polyline points={d} fill="none" stroke={up ? "var(--gn)" : "var(--rd)"} strokeWidth="1.5" vectorEffect="non-scaling-stroke" /></svg>;
}
const heat = () => (window.HEATMAP || []).map(([sym, sector, mcap, chg]) => ({ sym, sector, mcap, chg }));

/* ════════════ HOME ════════════ */
function SrfHome({ openSym }) {
  const hm = heat();
  const gainers = [...hm].sort((a, b) => b.chg - a.chg).slice(0, 4);
  const setups = (window.WATCHLIST || []).filter((r) => r.verdict === "BUY").slice(0, 3);
  // REAL indices: SPY + Nasdaq/Russell from sector_etf._indices, VIX from regime.
  const se = (window.MARKET_LIVE || {}).sector_etf || {};
  const ind = se._indices || {};
  const rg = window.REGIME_LIVE || {};
  const meta = window.SCAN_META || {};
  const vix = sfx.fmt((rg.vix && rg.vix.vix_current) || rg.vix_current || meta.vix || 0, 1);
  const idx = [
    ["S&P 500", se.SPY ? "$" + sfx.fmt(se.SPY.price, 0) : "—", (se.SPY && se.SPY.perf_pct) || 0],
    ["Nasdaq", ind.QQQ ? "$" + sfx.fmt(ind.QQQ.price, 0) : "—", (ind.QQQ && ind.QQQ.perf_pct) || 0],
    ["Russell", ind.IWM ? "$" + sfx.fmt(ind.IWM.price, 0) : "—", (ind.IWM && ind.IWM.perf_pct) || 0],
    ["VIX", vix, -(rg.vix && rg.vix.slope_5d || 0)],
  ];
  const regimeLabel = (meta.regime || rg.regime4 || rg.regime || "—").toString().replace(/_/g, " ");
  const breadth = sfx.fmt(meta.breadth || rg.breadth_pct_50d || 0, 0);
  const cycle = (rg.market_cycle || "").toString().replace(/_/g, " ");
  // REAL scan funnel: universe → passed (buy+watch) → bullish (buy) → elite (buy)
  const fUniv = meta.universe || 0, fPass = (meta.buy || 0) + (meta.watch || 0), fBuy = meta.buy || 0;
  const funnel = [[fUniv ? String(fUniv) : "—", "Universe"], [String(fPass), "Passed"], [String(fBuy), "Bullish"], [String(fBuy), "Elite"]];
  const tsLabel = meta.ts ? new Date(meta.ts).toLocaleString("en-US", { timeZone: "America/Los_Angeles", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) + " PT" : "—";
  return (
    <div className="cmp-surface">
      <SHead title="Market pulse" sub={tsLabel} />
      {meta.error && <div className="cmp-regime" style={{ borderColor: "var(--rd)" }}><div className="cmp-regime-dot" style={{ color: "var(--rd)" }}>!</div><div><div className="cmp-regime-t">Live data unavailable</div><div className="cmp-regime-s">Server unreachable ({meta.error}).</div></div></div>}
      <div className="cmp-idx">
        {idx.map(([n, v, c]) => (
          <div className="cmp-idx-c" key={n}><div className="cmp-idx-n">{n}</div><div className="cmp-idx-v mono">{v}</div><div className={`cmp-idx-c2 mono ${c >= 0 ? "up" : "dn"}`}>{sfx.sign(c)}{pctS(c)}</div></div>
        ))}
      </div>
      <div className="cmp-regime">
        <div className="cmp-regime-dot">{SIco.bolt}</div>
        <div><div className="cmp-regime-t" style={{ textTransform: "capitalize" }}>{regimeLabel}{cycle ? " · " + cycle : ""}</div><div className="cmp-regime-s">{breadth}% of S&P above 50-DMA · VIX {vix} · credit {rg.credit_state || "—"}</div></div>
      </div>
      <S n={1} title="Today's scan funnel" sub="universe → elite">
        <P>
          <div className="cmp-funnel">
            {funnel.map(([v, l], i) => (
              <React.Fragment key={l}>
                {i > 0 && <span className="cmp-funnel-arr">{SIco.chevR}</span>}
                <div className="cmp-funnel-step"><div className="cmp-funnel-v mono" style={{ color: i === 3 ? "var(--copper)" : i >= 2 ? "var(--gn)" : "var(--ink-1)" }}>{v}</div><div className="cmp-funnel-l">{l}</div></div>
              </React.Fragment>
            ))}
          </div>
        </P>
      </S>
      <S n={2} title="Top movers" sub="by % change">
        <P>
          {gainers.map((m) => (
            <button className="cmp-mover" key={m.sym} onClick={() => openSym(m.sym)}>
              <span className="cmp-mover-sym">{m.sym}</span><span className="cmp-mover-name">{m.sector}</span>
              <MiniSpark seed={m.sym} up={m.chg >= 0} />
              <span className={`cmp-mover-chg ${m.chg >= 0 ? "up" : "dn"}`}>{sfx.sign(m.chg)}{pctS(m.chg)}</span>
            </button>
          ))}
        </P>
      </S>
      <S n={3} title="Today's setups" sub="from the scan">
        <P style={{ padding: "4px 12px" }}>
          {setups.map((r) => <window.StockCard key={r.sym} row={r} onOpen={openSym} />)}
        </P>
      </S>
      <div className="cmp-disc">{window.SEC_DISCLAIMER_SHORT}</div>
    </div>
  );
}

/* ════════════ WATCHLIST (list surface) ════════════ */
function SrfWatchlist({ openSym, selectedSym }) {
  const [, f] = React.useState(0);
  React.useEffect(() => { const h = () => f((x) => x + 1); window.addEventListener("watchlist-change", h); return () => window.removeEventListener("watchlist-change", h); }, []);
  const base = window.WATCHLIST || [];
  const added = window.WatchStore ? window.WatchStore.added() : [];
  const removed = window.WatchStore ? window.WatchStore.removed() : new Set();
  const rows = [...base.filter((r) => !removed.has(r.sym)), ...added.map((a) => ({ sym: a.sym, name: a.name, price: a.price || 0, chg: a.chg || 0, score: a.score || 50, verdict: a.verdict || "WATCH", setup: a.setup || "—" }))];
  const bull = rows.filter((r) => r.verdict === "BUY").length;
  const avg = rows.length ? Math.round(rows.reduce((a, r) => a + r.score, 0) / rows.length) : 0;
  return (
    <div className="cmp-rail">
      <div className="cmp-listhead">
        <div className="cmp-brandrow">
          <div><div className="cmp-brand-name">Watchlist</div><div className="cmp-brand-sub">{rows.length} names · synced from starred</div></div>
          <div className="cmp-listhead-spacer" />
          {window.HeaderActions && <window.HeaderActions />}
        </div>
        <div className="cmp-scantabs">
          <div className="cmp-scantab is-on" style={{ cursor: "default" }}><b>{rows.length}</b><span className="cmp-scantab-n">NAMES</span></div>
          <div className="cmp-scantab" style={{ cursor: "default" }}><b>{bull}</b><span className="cmp-scantab-n">BULLISH</span></div>
          <div className="cmp-scantab" style={{ cursor: "default" }}><b>{avg}</b><span className="cmp-scantab-n">AVG SCORE</span></div>
        </div>
      </div>
      <div className="cmp-listscroll">
        {rows.length === 0 ? (
          <div className="cmp-empty">{SIco.star}<div className="cmp-empty-t">No names yet</div><div className="cmp-empty-s">Star a stock from any detail view to track it here.</div></div>
        ) : rows.map((r) => <window.StockCard key={r.sym} row={r} selected={selectedSym === r.sym} onOpen={openSym} />)}
        <div className="cmp-disc">{window.SEC_DISCLAIMER_SHORT}</div>
      </div>
    </div>
  );
}

/* ════════════ PORTFOLIO ════════════ */
function SrfPortfolio({ openSym }) {
  // REAL portfolio from cache (paper account, Alpaca-synced). Live positions,
  // market value, unrealized P&L, sector allocation — no synthesis.
  const PL = window.PORTFOLIO_LIVE || { positions: [], closed: [], equity: 0 };
  const pos = (PL.positions || []).map((p) => ({
    sym: p.ticker, shares: p.shares, mv: (p.shares || 0) * (p.current_price || p.entry_price || 0),
    pl: Number(p.unrealized_pnl_pct || 0), plUsd: Number(p.unrealized_pnl_dollars || 0),
    sector: p.sector || "—", dir: p.direction || "long",
  }));
  const equity = Number(PL.equity || pos.reduce((a, p) => a + p.mv, 0));
  const dayPL = pos.reduce((a, p) => a + (p.plUsd || 0), 0);
  const closed = PL.closed || [];
  const wins = closed.filter((c) => Number(c.pnl_pct || c.realized_pnl_pct || c.pnl || 0) > 0).length;
  const winRate = closed.length ? Math.round((wins / closed.length) * 100) : null;
  const secs = {};
  pos.forEach((p) => { secs[p.sector] = (secs[p.sector] || 0) + p.mv; });
  const alloc = Object.entries(secs).sort((a, b) => b[1] - a[1]);
  if (pos.length === 0) {
    return (
      <div className="cmp-surface">
        <SHead title="My portfolio" sub="paper account" />
        <div className="cmp-empty">{SIco.star}<div className="cmp-empty-t">No open positions</div><div className="cmp-empty-s">{PL.equity ? `Equity $${(equity/1000).toFixed(1)}k · all flat` : "Portfolio is flat or the paper account is not synced yet."}</div></div>
        <div className="cmp-disc">{window.SEC_DISCLAIMER_SHORT}</div>
      </div>
    );
  }
  return (
    <div className="cmp-surface">
      <SHead title="My portfolio" sub="paper · live P&L" />
      <SS items={[
        { v: `$${(equity / 1000).toFixed(1)}k`, l: "Equity", tone: "copper" },
        { v: `${dayPL >= 0 ? "+" : ""}$${Math.abs(dayPL).toFixed(0)}`, l: "Unreal. P&L", tone: dayPL >= 0 ? "gn" : "rd" },
        { v: pos.length, l: "Positions" },
        winRate != null ? { v: `${winRate}%`, l: "Win rate", tone: winRate >= 50 ? "gn" : "amb" } : { v: closed.length, l: "Closed" },
      ]} />
      <div style={{ height: 14 }} />
      <S n={1} title="Holdings" sub={`${pos.length} open`}>
        <P>
          {pos.map((p) => (
            <button className="cmp-mover" key={p.sym} onClick={() => openSym(p.sym)}>
              <span className="cmp-mover-sym">{p.sym}{p.dir === "short" ? " ↓" : ""}</span>
              <span className="cmp-mover-name">{p.shares} sh · ${(p.mv / 1000).toFixed(1)}k</span>
              <span className={`cmp-mover-chg ${p.pl >= 0 ? "up" : "dn"}`}>{sfx.sign(p.pl)}{pctS(p.pl)}</span>
            </button>
          ))}
        </P>
      </S>
      {alloc.length > 0 && <S n={2} title="Allocation" sub="by sector">
        <P>
          {alloc.map(([name, mv]) => {
            const w = Math.round((mv / (equity || 1)) * 100);
            return <R key={name} name={name} value={`${w}%`} meter={w} meterTone="copper" />;
          })}
        </P>
      </S>}
      <div className="cmp-disc">{window.SEC_DISCLAIMER_SHORT}</div>
    </div>
  );
}

/* ════════════ NEWS ════════════ */
function SrfNews({ openSym }) {
  // REAL news from market_news (EODHD feed): title, source, symbols, sentiment.
  const raw = window.NEWS_LIVE || [];
  const toneOf = (s) => s === "positive" ? "gn" : s === "negative" ? "rd" : "amb";
  const ago = (iso) => { try { const ms = Date.now() - new Date(iso).getTime(); const h = Math.floor(ms / 3.6e6); return h < 1 ? Math.max(1, Math.floor(ms / 6e4)) + "m" : h < 24 ? h + "h" : Math.floor(h / 24) + "d"; } catch (e) { return ""; } };
  const usSym = (arr) => (arr || []).map((s) => String(s).replace(/\.US$/, "")).filter((s) => /^[A-Z]{1,5}$/.test(s));
  const news = raw.slice(0, 16).map((n) => ({ title: n.title || "", src: n.source || n._provider || "wire", time: ago(n.date), tone: toneOf(n.sentiment), syms: usSym(n.symbols) }));
  const pos = raw.filter((n) => n.sentiment === "positive").length, neg = raw.filter((n) => n.sentiment === "negative").length, neu = raw.length - pos - neg;
  const pc = (n) => raw.length ? Math.round((n / raw.length) * 100) : 0;
  const counts = {}; raw.forEach((n) => usSym(n.symbols).forEach((s) => counts[s] = (counts[s] || 0) + 1));
  const trend = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 8).map(([s]) => s);
  if (raw.length === 0) {
    return (<div className="cmp-surface"><SHead title="News · sentiment" sub="last 24h" /><div className="cmp-empty">{SIco.dots}<div className="cmp-empty-t">No headlines</div><div className="cmp-empty-s">News feed is empty in the latest scan.</div></div></div>);
  }
  const tappable = (s) => (window.TICKER_BY_SYM || {})[s] || (window.WATCHLIST || []).some((r) => r.sym === s);
  return (
    <div className="cmp-surface">
      <SHead title="News · sentiment" sub={`${raw.length} stories · 24h`} />
      <div className="cmp-sent">
        <div className="cmp-sent-c"><div className="cmp-sent-v t-gn">{pc(pos)}%</div><div className="cmp-sent-l">Bullish</div></div>
        <div className="cmp-sent-c"><div className="cmp-sent-v t-amb">{pc(neu)}%</div><div className="cmp-sent-l">Neutral</div></div>
        <div className="cmp-sent-c"><div className="cmp-sent-v t-rd">{pc(neg)}%</div><div className="cmp-sent-l">Bearish</div></div>
      </div>
      {trend.length > 0 && <S n={1} title="Trending tickers">
        <div className="cmp-chiprow">
          {trend.map((s) => <button className="cmp-tickchip" key={s} onClick={() => tappable(s) && openSym(s)}>{s}<b className="up">{counts[s]}×</b></button>)}
        </div>
      </S>}
      <S n={2} title="Headline feed">
        <P><div className="cmp-news">
          {news.map((n, i) => {
            const lead = n.syms.find((s) => tappable(s));
            return (
              <div className="cmp-news-row" key={i} onClick={() => lead && openSym(lead)} style={{ cursor: lead ? "pointer" : "default" }}>
                <span className="cmp-news-tick" style={{ background: sfx.toneVar(n.tone) }} />
                <div className="cmp-news-body"><div className="cmp-news-hd">{lead && <b className="t-copper">{lead} </b>}{n.title}</div><div className="cmp-news-meta">{n.src || "wire"}{n.time ? " · " + n.time + " ago" : ""}</div></div>
              </div>
            );
          })}
        </div></P>
      </S>
      <div className="cmp-disc">{window.SEC_DISCLAIMER_SHORT}</div>
    </div>
  );
}

/* ════════════ SECTORS ════════════ */
function SrfSectors({ openSym }) {
  // REAL sector rotation from sector_etf — 11 SPDR sectors, perf vs SPY, ranks.
  const se = (window.MARKET_LIVE || {}).sector_etf || {};
  const agg = Object.entries(se)
    .filter(([k, v]) => !k.startsWith("_") && k !== "SPY" && v && typeof v === "object" && "perf_pct" in v)
    .map(([etf, v]) => ({ etf, sec: v.sector || etf, perf: Number(v.perf_pct || 0), vs: Number(v.vs_spy_pct || 0), rank: v.rank, out: !!v.outperforming }))
    .sort((a, b) => (a.rank || 99) - (b.rank || 99));
  if (agg.length === 0) {
    return (<div className="cmp-surface"><SHead title="Sectors · ETFs" sub="rotation" /><div className="cmp-empty">{SIco.dots}<div className="cmp-empty-t">No sector data</div><div className="cmp-empty-s">Sector ETF feed is empty in the latest scan.</div></div></div>);
  }
  const max = Math.max(...agg.map((a) => Math.abs(a.vs)), 1);
  return (
    <div className="cmp-surface">
      <SHead title="Sectors · ETFs" sub={`${agg.length} groups · vs SPY`} />
      <SS items={[
        { v: agg[0].sec, l: "Leading", tone: "gn" },
        { v: agg[agg.length - 1].sec, l: "Lagging", tone: "rd" },
        { v: `${agg.filter((a) => a.out).length}/${agg.length}`, l: "Outperforming" },
      ]} />
      <div style={{ height: 14 }} />
      <S n={1} title="Rotation heat" sub="% vs SPY (YTD)">
        <P>
          {agg.map((a) => {
            const w = (Math.abs(a.vs) / max) * 48;
            const up = a.vs >= 0;
            return (
              <div className="cmp-heat" key={a.etf}>
                <span className="cmp-heat-name">{a.sec}</span>
                <span className="cmp-heat-track">
                  <span className="cmp-heat-mid" />
                  <span className="cmp-heat-fill" style={{ width: w + "%", background: up ? "var(--gn)" : "var(--rd)", left: up ? "50%" : `${50 - w}%` }} />
                </span>
                <span className={`cmp-heat-chg ${up ? "up" : "dn"}`}>{sfx.sign(a.vs)}{pctS(a.vs)}</span>
                <span className="cmp-heat-n mono">#{a.rank || "—"}</span>
              </div>
            );
          })}
        </P>
      </S>
      <div className="cmp-disc">{window.SEC_DISCLAIMER_SHORT}</div>
    </div>
  );
}

/* ════════════ MOMENTUM ════════════ */
function SrfMomentum({ openSym }) {
  // REAL momentum: rank scan names by composite score; show real RS-rank + setup
  // from the elite snapshot (TICKER_BY_SYM carries rsRank). No fabricated RS.
  const byId = window.TICKER_BY_SYM || {};
  const leaders = (window.WATCHLIST || [])
    .map((r) => ({ ...r, rsRank: (byId[r.sym] && byId[r.sym].rsRank) || ((r._snap || {}).rs_rank) || null }))
    .sort((a, b) => b.score - a.score).slice(0, 12);
  if (leaders.length === 0) {
    return (<div className="cmp-surface"><SHead title="Momentum" sub="RS leaders" /><div className="cmp-empty">{SIco.dots}<div className="cmp-empty-t">No leaders</div><div className="cmp-empty-s">No qualifying names in the latest scan.</div></div></div>);
  }
  const topRS = leaders.filter((l) => (l.rsRank || 0) >= 80).length;
  const avgScore = Math.round(leaders.reduce((a, l) => a + l.score, 0) / leaders.length);
  return (
    <div className="cmp-surface">
      <SHead title="Momentum" sub="ranked by score" />
      <SS items={[
        { v: leaders.length, l: "Names", tone: "gn" },
        { v: topRS, l: "RS ≥ 80", tone: "copper" }, { v: avgScore, l: "Avg score" },
      ]} />
      <div style={{ height: 14 }} />
      <S n={1} title="Top setups" sub="composite score · RS rank">
        <P>
          {leaders.map((m) => (
            <button className="cmp-mover" key={m.sym} onClick={() => openSym(m.sym)}>
              <span className="cmp-mover-sym">{m.sym}</span>
              <span className="cmp-mover-name">{m.setup || "—"}{m.rsRank != null ? " · RS " + Math.round(m.rsRank) : ""}</span>
              <span className="cmp-mover-chg mono" style={{ color: sfx.toneVar(sfx.scoreTone(m.score)) }}>{m.score}</span>
            </button>
          ))}
        </P>
      </S>
      <div className="cmp-disc">{window.SEC_DISCLAIMER_SHORT}</div>
    </div>
  );
}

/* ════════════ EARNINGS ════════════ */
function SrfEarnings({ openSym }) {
  // REAL: ESP picks (Zacks ESP scanner) when present, else scan names with a
  // real days-to-earnings from their snapshot. No fabricated implied/beat.
  const esp = window.ESP_LIVE || [];
  const byId = window.TICKER_BY_SYM || {};
  let rep;
  if (esp.length) {
    rep = esp.map((e) => ({ sym: e.ticker || e.symbol, day: e.days_to_earnings ?? e.earn_days, date: e.earnings_date || "—",
      esp: e.esp, rank: e.zacks_rank })).filter((r) => r.sym);
  } else {
    rep = (window.WATCHLIST || [])
      .map((r) => { const snap = r._snap || (byId[r.sym] || {}); const day = snap.earn_days != null ? snap.earn_days : (byId[r.sym] && byId[r.sym].earnings && byId[r.sym].earnings.days); return { sym: r.sym, day, date: (byId[r.sym] && byId[r.sym].earnings && byId[r.sym].earnings.date) || "—", setup: r.setup }; })
      .filter((r) => r.day != null).sort((a, b) => a.day - b.day).slice(0, 12);
  }
  if (rep.length === 0) {
    return (<div className="cmp-surface"><SHead title="Earnings" sub="ESP + countdown" /><div className="cmp-empty">{SIco.dots}<div className="cmp-empty-t">No earnings data</div><div className="cmp-empty-s">No ESP picks and no dated reporters among scan names in the latest run.</div></div></div>);
  }
  const soon = rep.filter((r) => (r.day || 99) <= 7).length;
  return (
    <div className="cmp-surface">
      <SHead title="Earnings" sub={esp.length ? "Zacks ESP picks" : "scan-name countdown"} />
      <SS items={[
        { v: soon, l: "Within 7d", tone: "amb" },
        { v: rep.length, l: esp.length ? "ESP picks" : "Reporters" },
        esp.length ? { v: "ESP", l: "source", tone: "copper" } : { v: "scan", l: "source" },
      ]} />
      <div style={{ height: 14 }} />
      <S n={1} title={esp.length ? "ESP picks" : "Upcoming reporters"}>
        <P>
          {rep.map((r) => (
            <button className="cmp-mover" key={r.sym} onClick={() => openSym(r.sym)} style={{ alignItems: "center" }}>
              <span className="cmp-mover-sym">{r.sym}</span>
              <span className="cmp-mover-name">{r.date}{r.day != null ? " · in " + r.day + "d" : ""}{r.setup ? " · " + r.setup : ""}</span>
              {r.esp != null ? <C tone={r.esp > 0 ? "gn" : "rd"}>ESP {sfx.sign(r.esp)}{sfx.fmt(r.esp, 1)}%</C> : (r.day != null && <C tone={r.day <= 7 ? "amb" : "gn"}>{r.day}d</C>)}
            </button>
          ))}
        </P>
      </S>
      <div className="cmp-disc">{window.SEC_DISCLAIMER_SHORT}</div>
    </div>
  );
}

/* ════════════ OPTIONS FLOW ════════════ */
function SrfOptions({ openSym }) {
  // REAL unusual-options-activity from options_flow_top30 (UOA scanner output).
  const raw = window.OPTIONS_LIVE || [];
  const prints = raw.slice(0, 14).map((o) => {
    const call = Number(o.call_volume || 0) >= Number(o.put_volume || 0);
    return { sym: o.ticker, call, price: Number(o.price || 0), status: o.status || "", pcr: Number(o.put_call_ratio || 0),
      vol: Number(o.total_options_vol || o.call_volume || 0), maxPain: o.max_pain, rr: o.rr, sector: o.sector };
  });
  const strong = prints.filter((p) => /STRONG/i.test(p.status)).length;
  const callLed = prints.filter((p) => p.call).length;
  if (raw.length === 0) {
    return (<div className="cmp-surface"><SHead title="Options flow" sub="UOA tape" /><div className="cmp-empty">{SIco.dots}<div className="cmp-empty-t">No unusual flow</div><div className="cmp-empty-s">Options-flow scanner returned no names in the latest run.</div></div></div>);
  }
  const tappable = (s) => (window.TICKER_BY_SYM || {})[s] || (window.WATCHLIST || []).some((r) => r.sym === s);
  return (
    <div className="cmp-surface">
      <SHead title="Options flow" sub={`${raw.length} UOA names`} />
      <SS items={[
        { v: `${callLed}/${prints.length}`, l: "Call-led", tone: "gn" },
        { v: strong, l: "STRONG", tone: "copper" },
        { v: prints.length, l: "Active" },
      ]} />
      <div style={{ height: 14 }} />
      <S n={1} title="Unusual activity" sub="abnormal call/put volume">
        <P>
          {prints.map((p, i) => (
            <button className="cmp-print" key={i} onClick={() => tappable(p.sym) && openSym(p.sym)}>
              <span className="cmp-print-cp" style={{ background: p.call ? "var(--gn-bg)" : "var(--rd-bg)", color: p.call ? "var(--gn)" : "var(--rd)" }}>{p.call ? "C" : "P"}</span>
              <span className="cmp-print-main"><span className="cmp-print-sym">{p.sym} <span className="mono" style={{ fontWeight: 600 }}>${sfx.fmt(p.price, 2)}</span></span><span className="cmp-print-det">{p.sector || "—"}{p.maxPain ? " · max pain $" + sfx.fmt(p.maxPain, 0) : ""}</span></span>
              <span className="cmp-print-prem" style={{ color: /STRONG/i.test(p.status) ? "var(--copper)" : p.call ? "var(--gn)" : "var(--rd)" }}>{p.status || (p.rr ? p.rr + "R" : "")}</span>
            </button>
          ))}
        </P>
      </S>
      <div className="cmp-disc">{window.SEC_DISCLAIMER_SHORT}</div>
    </div>
  );
}

window.MOBILE_SURF = {
  home: SrfHome, watchlist: SrfWatchlist, portfolio: SrfPortfolio,
  news: SrfNews, sectors: SrfSectors, momentum: SrfMomentum, earnings: SrfEarnings, options: SrfOptions,
};

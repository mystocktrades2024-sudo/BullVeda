// companion-surfaces2.jsx — the remaining Markets + Discover surfaces.
// Registers into window.MOBILE_SURF. Loaded after extra, before app.
const z = window.cmpHelpers;
const { Sec: S2, Panel: P2, Row: R2, Chip: C2, StatStrip: SS2 } = window;
const zp = (n, d = 1) => z.fmt(n, d) + "%";
const heat2 = () => (window.HEATMAP || []).map(([sym, sector, mcap, chg]) => ({ sym, sector, mcap, chg }));
const SH = (props) => (window.SHead ? window.SHead(props) : null);

/* ════════════ MARKET INTERNALS ════════════ */
function SrfInternals() {
  // REAL breadth from market_breadth (universe-wide % above MAs + new H/L).
  const b = window.BREADTH_LIVE || {};
  const tone = (p) => p >= 60 ? "gn" : p >= 40 ? "amb" : "rd";
  const p50 = Number(b.pct_above_50d || 0), p20 = Number(b.pct_above_20d || 0), p100 = Number(b.pct_above_100d || 0), p200 = Number(b.pct_above_200d || 0);
  const nh = Number(b.new_highs || 0), nl = Number(b.new_lows || 0), netHL = nh - nl;
  const part = [["% above 50-DMA", p50, tone(p50)], ["% above 100-DMA", p100, tone(p100)], ["% above 200-DMA", p200, tone(p200)]].filter((r) => r[1]);
  if (!b.total) {
    return (<div className="cmp-surface"><SH title="Market internals" sub="breadth" /><div className="cmp-empty">{window.Ico.dots}<div className="cmp-empty-t">No breadth data</div><div className="cmp-empty-s">market_breadth is empty in the latest scan.</div></div></div>);
  }
  return (
    <div className="cmp-surface">
      <SH title="Market internals" sub={`${b.total} names`} />
      <SS2 items={[{ v: `${z.fmt(p50, 0)}%`, l: "> 50DMA", tone: tone(p50) }, { v: `${netHL >= 0 ? "+" : ""}${netHL}`, l: "Net H–L", tone: netHL >= 0 ? "gn" : "rd" }, { v: `${z.fmt(p200, 0)}%`, l: "> 200DMA", tone: tone(p200) }]} />
      <div style={{ height: 14 }} />
      <S2 n={1} title="New highs vs lows" sub="52-week">
        <P2>
          <div style={{ display: "flex", height: 26, borderRadius: 8, overflow: "hidden", border: "1px solid var(--line)" }}>
            <div style={{ width: (nh / Math.max(1, nh + nl) * 100) + "%", background: "var(--gn-bg)", color: "var(--gn)", display: "grid", placeItems: "center", fontSize: 11, fontWeight: 700, minWidth: 36 }}>{nh} ▲</div>
            <div style={{ width: (nl / Math.max(1, nh + nl) * 100) + "%", background: "var(--rd-bg)", color: "var(--rd)", display: "grid", placeItems: "center", fontSize: 11, fontWeight: 700, minWidth: 36 }}>▼ {nl}</div>
          </div>
        </P2>
      </S2>
      <S2 n={2} title="Participation" sub="% above MA">
        <P2>{part.map(([n, v, t]) => <R2 key={n} name={n} value={`${z.fmt(v, 0)}%`} meter={v} meterTone={t} />)}</P2>
      </S2>
      <div className="cmp-disc">{window.SEC_DISCLAIMER_SHORT}</div>
    </div>
  );
}

/* ════════════ PRE-MARKET ════════════ */
function SrfPremarket({ openSym }) {
  // REAL pre-market gappers from the premarket feed (gappers_up / gappers_dn).
  const pm = window.PREMARKET_LIVE || {};
  const norm = (g) => ({ sym: g.ticker || g.sym || g.symbol, gap: Number(g.gap_pct ?? g.premarket_change_pct ?? g.chg ?? 0), reason: g.catalyst || g.reason || g.setup || "gap", price: Number(g.price || g.premarket_price || 0) });
  const up = (pm.gappers_up || []).map(norm), dn = (pm.gappers_dn || []).map(norm);
  const gappers = [...up, ...dn].filter((g) => g.sym).sort((a, b) => Math.abs(b.gap) - Math.abs(a.gap)).slice(0, 12);
  const cats = (pm.catalysts || []).length;
  if (gappers.length === 0) {
    return (<div className="cmp-surface"><SH title="Pre-market" sub="gap board" /><div className="cmp-empty">{window.Ico.dots}<div className="cmp-empty-t">No pre-market gappers</div><div className="cmp-empty-s">Pre-market feed is empty — likely outside the pre-market window.</div></div></div>);
  }
  return (
    <div className="cmp-surface">
      <SH title="Pre-market" sub={(pm._meta && pm._meta.asof) || "gap board"} />
      <SS2 items={[{ v: up.length, l: "Gap up", tone: "gn" }, { v: dn.length, l: "Gap dn", tone: "rd" }, { v: cats, l: "Catalysts", tone: "amb" }]} />
      <div style={{ height: 14 }} />
      <S2 n={1} title="Gap board" sub="pre-market movers">
        <P2>
          {gappers.map((g) => (
            <button className="cmp-mover" key={g.sym} onClick={() => openSym(g.sym)}>
              <span className="cmp-mover-sym">{g.sym}</span>
              <span className="cmp-mover-name">{g.reason}{g.price ? " · $" + z.fmt(g.price, 2) : ""}</span>
              <span className={`cmp-mover-chg ${g.gap >= 0 ? "up" : "dn"}`}>{z.sign(g.gap)}{zp(g.gap)}</span>
            </button>
          ))}
        </P2>
      </S2>
      <div className="cmp-disc">{window.SEC_DISCLAIMER_SHORT}</div>
    </div>
  );
}

/* ════════════ MACRO CALENDAR ════════════ */
function SrfCalendar() {
  // REAL macro calendar from economic_events (EODHD): type, date, impact, est/prev.
  const ev = (window.CALENDAR_LIVE || []).filter((e) => e && e.date);
  const toneOf = (imp) => /high/i.test(imp) ? "rd" : /med/i.test(imp) ? "amb" : "gn";
  const fmtD = (s) => { try { const d = new Date(s.replace(" ", "T") + "Z"); return d.toLocaleString("en-US", { timeZone: "America/Los_Angeles", weekday: "short", hour: "numeric", minute: "2-digit" }); } catch (e) { return s; } };
  const rows = ev.map((e) => ({ name: e.type || "event", imp: e._impact || "LOW", tone: toneOf(e._impact || ""), when: fmtD(e.date),
    val: [e.estimate != null ? "est " + e.estimate : null, e.previous != null ? "prev " + e.previous : null].filter(Boolean).join(" · ") || "—",
    ts: Date.parse((e.date || "").replace(" ", "T") + "Z") || 0 })).sort((a, b) => a.ts - b.ts);
  const high = rows.filter((r) => /high/i.test(r.imp)).length;
  if (rows.length === 0) {
    return (<div className="cmp-surface"><SH title="Macro calendar" sub="events" /><div className="cmp-empty">{window.Ico.dots}<div className="cmp-empty-t">No scheduled events</div><div className="cmp-empty-s">Economic calendar is empty in the latest scan.</div></div></div>);
  }
  return (
    <div className="cmp-surface">
      <SH title="Macro calendar" sub="upcoming · US" />
      <SS2 items={[{ v: rows.length, l: "Events", tone: "amb" }, { v: high, l: "High-impact", tone: "rd" }, { v: "US", l: "Region" }]} />
      <div style={{ height: 14 }} />
      <S2 n={1} title="Upcoming" sub="PT">
        <P2>
          {rows.slice(0, 16).map((r, i) => (
            <div className="cmp-row" key={i}>
              <span className="mono" style={{ width: 84, flex: "none", fontSize: 11, color: "var(--ink-2)", fontWeight: 600 }}>{r.when}</span>
              <div className="cmp-row-l"><div className="cmp-row-name">{r.name}</div><div className="cmp-row-sub">{r.val}</div></div>
              <C2 tone={r.tone}>{r.imp}</C2>
            </div>
          ))}
        </P2>
      </S2>
      <div className="cmp-disc">{window.SEC_DISCLAIMER_SHORT}</div>
    </div>
  );
}

/* ════════════ THEMES ════════════ */
function SrfThemes({ openSym }) {
  // REAL themed baskets from the themes feed (Zacks/curated lists of constituents).
  const T = window.THEMES_LIVE || {};
  const label = (k) => k.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  const baskets = Object.entries(T).map(([k, v]) => ({ key: k, name: label(k), names: Array.isArray(v) ? v : (v && v.tickers) || [] }))
    .filter((b) => b.names.length > 0).sort((a, b) => b.names.length - a.names.length);
  const symOf = (x) => typeof x === "string" ? x : (x && (x.ticker || x.sym)) || "";
  if (baskets.length === 0) {
    return (<div className="cmp-surface"><SH title="Themes" sub="baskets" /><div className="cmp-empty">{window.Ico.dots}<div className="cmp-empty-t">No populated baskets</div><div className="cmp-empty-s">Theme baskets are empty in the latest scan.</div></div></div>);
  }
  return (
    <div className="cmp-surface">
      <SH title="Themes" sub={`${baskets.length} baskets`} />
      <SS2 items={[{ v: baskets.length, l: "Baskets", tone: "violet" }, { v: baskets[0].name.split(" ")[0], l: "Largest", tone: "copper" }, { v: baskets.reduce((a, b) => a + b.names.length, 0), l: "Names" }]} />
      <div style={{ height: 14 }} />
      <S2 n={1} title="Theme board" sub="constituents">
        <P2>
          {baskets.map((b) => { const lead = symOf(b.names[0]); return (
            <div className="cmp-row" key={b.key}>
              <div className="cmp-row-l"><div className="cmp-row-name">{b.name}</div><div className="cmp-row-sub">{b.names.length} names{lead ? <span> · lead <button onClick={() => openSym(lead)} style={{ background: "none", border: "none", color: "var(--copper)", fontWeight: 700, padding: 0, fontSize: 11 }}>{lead}</button></span> : null}</div></div>
            </div>
          ); })}
        </P2>
      </S2>
      <div className="cmp-disc">{window.SEC_DISCLAIMER_SHORT}</div>
    </div>
  );
}

/* ════════════ ML PREDICTIONS ════════════ */
function SrfML({ openSym }) {
  // REAL: each name's MC P(profit) + T1-vs-stop edge from the elite snapshot.
  const picks = (window.WATCHLIST || []).map((r) => {
    const t = z.resolveTicker(r.sym);
    const pup = t.ml && t.ml.direction != null ? Math.round(t.ml.direction * 100) : null;
    return { sym: r.sym, name: r.name, pup, edge: t.ml ? Math.round((t.ml.hitNet || 0) * 100) : 0, conf: t.score };
  }).filter((p) => p.pup != null).sort((a, b) => b.pup - a.pup).slice(0, 10);
  if (picks.length === 0) {
    return (<div className="cmp-surface"><SH title="ML predictions" sub="ensemble" /><div className="cmp-empty">{window.Ico.dots}<div className="cmp-empty-t">No model output</div><div className="cmp-empty-s">No scan name carries a Monte-Carlo P(profit) this run.</div></div></div>);
  }
  const avg = Math.round(picks.reduce((a, p) => a + p.pup, 0) / picks.length);
  const bull = picks.filter((p) => p.edge > 0).length;
  return (
    <div className="cmp-surface">
      <SH title="ML predictions" sub="MC P(profit)" />
      <SS2 items={[{ v: picks.length, l: "Picks", tone: "violet" }, { v: `${avg}%`, l: "Avg P(up)", tone: z.scoreTone(avg) }, { v: `${bull}/${picks.length}`, l: "+edge" }]} />
      <div style={{ height: 14 }} />
      <S2 n={1} title="Ranked picks" sub="P(up) · edge">
        <P2>
          {picks.map((p) => (
            <button className="cmp-mover" key={p.sym} onClick={() => openSym(p.sym)} style={{ alignItems: "center" }}>
              <span className="cmp-mover-sym">{p.sym}</span>
              <span className="cmp-mover-name">edge {p.edge >= 0 ? "+" : ""}{p.edge}% · conf {p.conf}</span>
              <span style={{ width: 70, flex: "none", display: "flex", flexDirection: "column", gap: 4 }}>
                <span className="mono" style={{ fontSize: 12.5, fontWeight: 700, textAlign: "right", color: z.toneVar(z.scoreTone(p.pup)) }}>{p.pup}%</span>
                <span className="cmp-meter"><i style={{ width: p.pup + "%", background: z.toneVar(z.scoreTone(p.pup)) }} /></span>
              </span>
            </button>
          ))}
        </P2>
      </S2>
      <div className="cmp-disc">{window.SEC_DISCLAIMER_SHORT}</div>
    </div>
  );
}

/* ════════════ INSIDER TRADING ════════════ */
function SrfInsider({ openSym }) {
  // REAL insider — surfaced per-name in each ticker's Tape · Flow lens. The
  // universe-wide Form-4 cluster scan is a desktop surface; here we list scan
  // names whose snapshot flags insider activity (no fabricated filings).
  const byId = window.TICKER_BY_SYM || {};
  const rows = (window.WATCHLIST || []).map((r) => {
    const row = (byId[r.sym] || {})._row || {};
    const ins = row.insider_data || row.insider_cluster_audit || null;
    const own = row.fundamentals && row.fundamentals.details && row.fundamentals.details.institutional_ownership;
    return { sym: r.sym, name: r.name, hasIns: !!(ins && (ins.cluster || ins.net_buys || ins.recent_buys)), own };
  }).filter((r) => r.hasIns);
  return (
    <div className="cmp-surface">
      <SH title="Insider trading" sub="Form 4" />
      {rows.length === 0 ? (
        <div className="cmp-empty">{window.Ico.dots}<div className="cmp-empty-t">No insider clusters flagged</div><div className="cmp-empty-s">No scan name has an insider cluster in the latest run. Per-name Form-4 detail is in each ticker's <b>Tape · Flow</b> lens.</div></div>
      ) : (
        <S2 n={1} title="Names with insider activity">
          <P2>{rows.map((r) => (
            <button className="cmp-mover" key={r.sym} onClick={() => openSym(r.sym)}>
              <span className="cmp-mover-sym">{r.sym}</span><span className="cmp-mover-name">{r.name}</span>
              <C2 tone="gn">insider</C2>
            </button>
          ))}</P2>
        </S2>
      )}
      <div className="cmp-disc">{window.SEC_DISCLAIMER_SHORT}</div>
    </div>
  );
}

/* ════════════ SMC / PATTERNS ════════════ */
function SrfSMC({ openSym }) {
  // REAL SMC structure is computed per-name (each ticker's SMC lens). Here we
  // list scan names that carry a real SMC payload, with their structure label.
  const byId = window.TICKER_BY_SYM || {};
  const rows = (window.WATCHLIST || []).map((r) => {
    const row = (byId[r.sym] || {})._row || {};
    const smc = row.smc || row.smc_data || null;
    const label = smc && (smc.structure || smc.bias || smc.label || (smc.bos ? "BOS" : null));
    return { sym: r.sym, name: r.name, label };
  }).filter((r) => r.label);
  return (
    <div className="cmp-surface">
      <SH title="SMC / patterns" sub="structure" />
      {rows.length === 0 ? (
        <div className="cmp-empty">{window.Ico.dots}<div className="cmp-empty-t">Open a ticker for SMC</div><div className="cmp-empty-s">Per-name market structure (BOS/CHoCH, order blocks, FVGs) is in each ticker's <b>SMC</b> lens. No scan name carries a top-level structure label this run.</div></div>
      ) : (
        <S2 n={1} title="Names with structure">
          <P2>{rows.map((r) => (
            <button className="cmp-mover" key={r.sym} onClick={() => openSym(r.sym)} style={{ alignItems: "center" }}>
              <span className="cmp-mover-sym">{r.sym}</span><span className="cmp-mover-name">{r.name}</span>
              <C2 tone="violet">{String(r.label).slice(0, 14)}</C2>
            </button>
          ))}</P2>
        </S2>
      )}
      <div className="cmp-disc">{window.SEC_DISCLAIMER_SHORT}</div>
    </div>
  );
}

if (window.MOBILE_SURF) Object.assign(window.MOBILE_SURF, {
  internals: SrfInternals, premarket: SrfPremarket, calendar: SrfCalendar, themes: SrfThemes,
  ai: SrfML, insider: SrfInsider, smc: SrfSMC,
});

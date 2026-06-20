// scan-column.jsx — middle column: switchable scan surface
// Tabs: Map · Watchlist · BUY · Elite. List view with active ticker highlight.
// Width preset S/M/L/XL changes density/columns.

const { useState: useStateSC, useMemo: useMemoSC } = React;

const SCAN_WIDTHS = { S: 192, M: 248, L: 320, XL: 400 };

function ScanColumn({
  activeSurface, onSurface,
  activeTicker, onTicker,
  widthCat, onWidthCat,
  collapsed, // Focus mode
}) {
  const width = collapsed ? 64 : SCAN_WIDTHS[widthCat];

  return (
    <aside
      className={`sc ${collapsed ? "sc--collapsed" : ""}`}
      style={{ width }}
    >
      {!collapsed && (
        <div className="sc-hdr">
          <div className="sc-surf-tabs">
            {[
              { id: "market-map", label: "MAP",   tone: "copper" },
              { id: "buy",        label: "BULLISH", tone: "gn" },
              { id: "watchlist",  label: "WATCH", tone: "ink" },
              { id: "elite",      label: "ELITE", tone: "violet" },
            ].map(t => (
              <button
                key={t.id}
                className={`sc-surf ${activeSurface === t.id ? "is-on" : ""} sc-surf--${t.tone}`}
                onClick={() => onSurface(t.id)}
              >{t.label}</button>
            ))}
          </div>
          <div className="sc-presets">
            {["S","M","L","XL"].map(s => (
              <button
                key={s}
                className={`sc-preset ${widthCat === s ? "is-on" : ""}`}
                onClick={() => onWidthCat(s)}
                title={`Scan column width ${s}`}
              >{s}</button>
            ))}
          </div>
        </div>
      )}

      <ScanList
        activeSurface={activeSurface}
        activeTicker={activeTicker}
        onTicker={onTicker}
        widthCat={collapsed ? "C" : widthCat}
        collapsed={collapsed}
      />

      {!collapsed && (
        <div className="sc-foot">
          <FreshnessPill state="live" age="18s" />
          <span className="mono dim2">612 ranked · 2026-05-27</span>
        </div>
      )}
    </aside>
  );
}

// ─── List body ─────────────────────────────────────────────────────
function ScanList({ activeSurface, activeTicker, onTicker, widthCat, collapsed }) {
  // Use same WATCHLIST as data — filter / re-rank by surface.
  // Every surface ranks by score DESCENDING (aligned with the signal scanner).
  // Null / non-finite scores sink to the bottom so they never out-rank real ones.
  const _sc = x => (x.score == null || !isFinite(x.score)) ? -1 : x.score;
  // KILL->LABEL (2026-06-11): WEAK-edge names (realized track-record PF<1.0 in this
  // regime) sink BELOW all non-weak names, then rank by score within each group.
  // The signal is NEVER hidden — it just ranks last, carrying its ⚠ WEAK badge.
  // Tier comes from the live scan row (_raw.edge_tier) via findRow.
  const _isWeak = x => {
    const lr = (window.__BV && window.__BV.findRow) ? window.__BV.findRow(x.sym) : null;
    const et = (lr && lr._raw && lr._raw.edge_tier) || x.edge_tier || null;
    return !!(et && et.tier === "WEAK");
  };
  const _byScoreDesc = (a, b) => {
    const wa = _isWeak(a), wb = _isWeak(b);
    if (wa !== wb) return wa ? 1 : -1;   // weak sinks to the bottom
    return _sc(b) - _sc(a);              // score-descending within each group
  };
  const items = useMemoSC(() => {
    if (activeSurface === "buy")     return WATCHLIST.filter(w => w.verdict === "BUY").sort(_byScoreDesc);
    if (activeSurface === "elite")   return WATCHLIST.filter(w => w.score >= 70).sort(_byScoreDesc);
    if (activeSurface === "watchlist")return [...WATCHLIST].sort(_byScoreDesc);
    // map mode pulls the top-mover universe from heatmap, but ranks by score
    // (descending) like every other surface. HEATMAP tuples carry no price, so
    // pull the real price from the live scan row when the name isn't in WATCHLIST
    // (otherwise it would render $0.00). price stays null when genuinely absent.
    return HEATMAP
      .map(([sym, sector, mcap, chg]) => {
        const w = WATCHLIST.find(x => x.sym === sym);
        const live = (window.__BV && window.__BV.findRow) ? window.__BV.findRow(sym) : null;
        // score: prefer the real scan-row score; never synthesize an impossible
        // (>100) value. INTC showed "114" from the old `50 + chg*5` fallback.
        const _liveScore = (live && isFinite(live.score)) ? live.score : null;
        const base = w || { sym, name: (live && live.name) || sector, price: null,
          chg, score: _liveScore,
          verdict: (live ? live.verdict : chg > 1.5 ? "BUY" : "WATCH"),
          setup: (live ? live.setup : sector) };
        const price = (base.price != null && base.price > 0) ? base.price
                    : (live && typeof live.price === "number" && live.price > 0 ? live.price : null);
        return { ...base, price, chg, sector };
      })
      .sort(_byScoreDesc)
      .slice(0, 28);
  }, [activeSurface]);

  return (
    <div className="sc-list">
      {items.map((it, i) => (
        <ScanRow
          key={it.sym + i}
          item={it}
          active={it.sym === activeTicker}
          onClick={() => onTicker(it.sym)}
          widthCat={widthCat}
          collapsed={collapsed}
          rank={i + 1}
        />
      ))}
      {items.length === 0 && (
        <div className="sc-empty">
          <div className="state-msg-em">No candidates in this scan.</div>
          <div className="state-msg mono dim">Check filters · or wait for next bundle.</div>
        </div>
      )}
    </div>
  );
}

// BUY-QUALITY TRAFFIC LIGHT (2026-06-20). Grades how "ideal to buy" a BUY row is,
// from the EMPIRICAL edge of the true canonical BUYs (ticker_snapshots, May18→now):
//   score 70–89 = sweet spot (PF 2.5+) · 60–69 = decent (PF 1.86) ·
//   90+ = exhaustion (PF 0.74) · Impulse Catalyst setup = weak in chop (PF 0.33).
// Raw composite score is NOT monotonic (90+ reverts), so the light keys on the
// empirical band + setup, not the score number alone. Only grades verdict==BUY.
function buyLight(it) {
  const v = String((it && it.verdict) || "").toUpperCase();
  if (v !== "BUY") return null;
  const s = (it.score == null || !isFinite(it.score)) ? null : it.score;
  const setup = String(it.setup || "");
  if (s != null && s >= 90)        return { c: "rd",  t: "Caution — 90+ score tends to exhaust (hist. PF 0.74). Wait for a pullback." };
  if (/impulse/i.test(setup))      return { c: "rd",  t: "Caution — Impulse Catalyst is weak in choppy tape (hist. PF 0.33)." };
  if (s != null && s >= 70)        return { c: "gn",  t: "Ideal buy — 70–89 sweet spot (hist. PF 2.5+)." };
  if (s != null && s >= 60)        return { c: "amb", t: "OK buy — 60–69 band (hist. PF 1.86)." };
  return { c: "amb", t: "Buy" };
}
function BuyDot({ item, mini }) {
  const bl = buyLight(item);
  if (!bl) return null;
  const d = mini ? 6 : 7;
  return (
    <span className="sc-buylight" title={bl.t}
      style={{ display: "inline-block", width: d + "px", height: d + "px", borderRadius: "50%",
               marginRight: "5px", verticalAlign: "middle", flex: "0 0 auto",
               background: `var(--${bl.c})`, boxShadow: `0 0 4px var(--${bl.c})` }} />
  );
}

function ScanRow({ item, active, onClick, widthCat, collapsed, rank }) {
  const verdictTone = item.verdict === "BUY" ? "gn" : item.verdict === "AVOID" ? "rd" : "amb";
  // KILL->LABEL / honest edge tier (2026-06-11 audit). Read from the live scan
  // row (_raw carries the /api/universe fields). edge_tier = honest PROVEN/
  // DEVELOPING/WEAK/UNPROVEN badge from the realized track record; edge_warning =
  // weak-setup chip for a signal that WOULD have been score-killed but is kept
  // visible. Informational only — the BUY stays clickable regardless.
  const _liveRow = (window.__BV && window.__BV.findRow) ? window.__BV.findRow(item.sym) : null;
  const _edge = (_liveRow && _liveRow._raw && _liveRow._raw.edge_tier) || item.edge_tier || null;
  const _warn = (_liveRow && _liveRow._raw && _liveRow._raw.edge_warning) || item.edge_warning || null;
  const _edgeVar = { good: "gn", neutral: "info", muted: "dim2", warn: "rd" };
  if (collapsed) {
    // thin rail mode — just symbol + chg
    return (
      <button
        className={`sc-row sc-row--mini ${active ? "is-active" : ""}`}
        onClick={onClick}
        title={`${item.name} · ${window.biasRead ? window.biasRead(item).label : (window.secBias ? window.secBias(item.verdict) : item.verdict)} · score ${item.score}`}
      >
        <BuyDot item={item} mini />
        <span className={`sc-row-sym mono ${active ? "copper" : ""}`}>{item.sym}</span>
        <span className={`sc-row-chg mono ${item.chg >= 0 ? "up" : "dn"}`}>
          {item.chg == null || !isFinite(item.chg) ? "—" : (item.chg >= 0 ? "+" : "") + item.chg.toFixed(1)}
        </span>
      </button>
    );
  }
  return (
    <button
      className={`sc-row ${active ? "is-active" : ""}`}
      onClick={onClick}
    >
      <div className="sc-row-head">
        <span className="sc-row-rank mono dim">{String(rank).padStart(2, "0")}</span>
        <BuyDot item={item} />
        <span className={`sc-row-sym mono ${active ? "copper" : ""}`}><b>{item.sym}</b></span>
        <span className={`sc-row-chg mono ${item.chg >= 0 ? "up" : "dn"}`}>
          {item.chg == null || !isFinite(item.chg) ? "—" : (item.chg >= 0 ? "+" : "") + item.chg.toFixed(2) + "%"}
        </span>
        <span className="sc-row-score mono"><b>{item.score == null || !isFinite(item.score) ? "—" : item.score}</b></span>
      </div>
      {(widthCat === "L" || widthCat === "XL" || widthCat === "M") && (
        <div className="sc-row-meta">
          <span className="sc-row-name dim">{item.name}</span>
          {(widthCat === "L" || widthCat === "XL") && (
            <span className="sc-row-px mono dim2">{item.price != null && isFinite(item.price) && item.price > 0 ? "$" + item.price.toFixed(2) : "—"}</span>
          )}
        </div>
      )}
      {(widthCat === "M" || widthCat === "L" || widthCat === "XL") && (
        <div className="sc-conv" title={`conviction ${item.score == null ? "—" : item.score}/100`}>
          <span className="sc-conv-fill" style={{ width: `${item.score == null || !isFinite(item.score) ? 0 : Math.max(0, Math.min(100, item.score))}%`, background: `var(--${(item.score || 0) >= 66 ? "gn" : (item.score || 0) >= 50 ? "amb" : "rd"})` }} />
        </div>
      )}
      {(widthCat === "L" || widthCat === "XL") && (
        <div className="sc-row-foot">
          <Pill tone={verdictTone} small>{window.biasRead ? window.biasRead(item).label : (window.secBias ? window.secBias(item.verdict) : item.verdict)}</Pill>
          <span className="sc-row-setup mono dim">{item.setup}</span>
          {_edge && (
            <span className="mono" title={_edge.label}
              style={{ fontSize: "9.5px", fontWeight: 700, letterSpacing: ".04em",
                       color: `var(--${_edgeVar[_edge.tone] || "dim2"})` }}>
              {_edge.icon} {_edge.tier}
            </span>
          )}
        </div>
      )}
      {(widthCat === "M" || widthCat === "L" || widthCat === "XL") && (() => {
        const s = scanSignals(item);
        return (
          <div className="sc-row-chips">
            <span className="sc-chip" title="relative volume vs 20-day avg"><span className="sc-chip-k">RVOL</span><b className={isFinite(s.rvol) && s.rvol >= 1.5 ? "up" : "dim2"}>{isFinite(s.rvol) ? s.rvol.toFixed(1) + "×" : "—"}</b></span>
            <span className="sc-chip" title="ML model P(up) over swing horizon"><span className="sc-chip-k">P↑</span><b className={s.pUp == null ? "dim2" : `kpi-tone--${s.pUp >= 60 ? "gn" : s.pUp >= 45 ? "amb" : "rd"}`}>{s.pUp == null ? "—" : s.pUp + "%"}</b></span>
            <span className="sc-chip" title="reward:risk to T1"><span className="sc-chip-k">R:R</span><b className={isFinite(s.rr) && s.rr >= 2 ? "up" : "dim2"}>{isFinite(s.rr) ? s.rr.toFixed(1) : "—"}</b></span>
            <span className="sc-chip" title="distance to breakout pivot"><span className="sc-chip-k">PIV</span><b className={isFinite(s.toPivot) && Math.abs(s.toPivot) <= 1 ? "up" : "dim2"}>{isFinite(s.toPivot) ? (s.toPivot >= 0 ? "+" : "") + s.toPivot + "%" : "—"}</b></span>
            {s.insider !== 0 && <span className={`sc-flowdot sc-flowdot--${s.insider > 0 ? "buy" : "sell"}`} title={`insider net ${s.insider > 0 ? "buying" : "selling"} (90d)`}>{s.insider > 0 ? "▲" : "▼"}</span>}
            {s.erDays <= 7 && <span className="sc-chip sc-chip--er" title={`earnings in ${s.erDays} sessions`}>⚡ ER {s.erDays}d</span>}
            {_warn && _warn.label && (
              <span className="sc-chip" title={_warn.note || _warn.source || _warn.label}
                style={{ color: "var(--rd)" }}>
                <b>{_warn.label}</b>
              </span>
            )}
          </div>
        );
      })()}
      {widthCat === "XL" && (
        <div className="sc-row-spark">
          <Sparkline data={fakeSpark(item.sym)} color={`var(--${item.chg >= 0 ? "gn" : "rd"})`} w={180} h={20} />
        </div>
      )}
    </button>
  );
}

// Per-symbol derived scan signals (RVOL, ML P(up), R:R, earnings days)
const scanSigCache = {};
function scanSignals(item) {
  const sym = item.sym;
  if (scanSigCache[sym]) return scanSigCache[sym];
  let h = 0; for (let i = 0; i < sym.length; i++) h = (h * 31 + sym.charCodeAt(i)) >>> 0;
  // real row (live /api/universe) when available — drives price + RVOL + R:R fallbacks
  const row = (window.__BV && window.__BV.findRow) ? window.__BV.findRow(sym) : null;
  let rvol = row && row.rvol != null && row.rvol !== "—" ? parseFloat(row.rvol) : NaN;
  if (!isFinite(rvol)) rvol = +(0.7 + (h % 240) / 100).toFixed(2);
  let pUp = null;
  try {
    const pr = window.AIPredict ? window.AIPredict.predict(sym) : null;
    // predict() returns {error,...} (no pUp) for symbols outside the ML set →
    // pUp is undefined; Math.round(undefined*100) === NaN, so guard for finite.
    if (pr && typeof pr.pUp === "number" && isFinite(pr.pUp)) pUp = Math.round(pr.pUp * 100);
  } catch (e) { pUp = null; }
  // last real fallback: live p_up on the scan row (0..1) → percent
  if (pUp == null && row && row._raw && typeof row._raw.p_up === "number" && isFinite(row._raw.p_up)) {
    pUp = Math.round(row._raw.p_up * 100);
  }
  // pUp stays null when no ML forecast exists → render honest "—" (never NaN%)
  let rr = row && row.rr != null && row.rr !== "—" ? parseFloat(row.rr) : NaN;
  if (!isFinite(rr)) rr = +(1.1 + ((h >> 3) % 220) / 100).toFixed(2);
  const erDays = (row && row.er != null) ? row.er : (h >> 5) % 45;
  // distance-to-pivot: real (price→pivot, or price→entry/T1 when pivot absent),
  // else deterministic synthetic. Guard against null/0-denominator → NaN.
  let toPivot = NaN;
  if (row) {
    const px = row.price;
    const pivRaw = row._raw && row._raw.pivot;
    const entRaw = row.entry != null && row.entry !== "—" ? parseFloat(row.entry) : NaN;
    const ref = (typeof pivRaw === "number" && isFinite(pivRaw) && pivRaw > 0) ? pivRaw
              : (isFinite(entRaw) && entRaw > 0) ? entRaw : NaN;
    if (typeof px === "number" && isFinite(px) && px > 0 && isFinite(ref)) {
      toPivot = +(((px - ref) / ref) * 100).toFixed(1);
    }
  }
  if (!isFinite(toPivot)) toPivot = +(((h >> 7) % 90) / 10 - 4.5).toFixed(1);
  const insider = (row && typeof row.insNet === "number") ? Math.sign(row.insNet) : ((h >> 9) % 3) - 1; // -1/0/+1
  const s = { rvol, pUp, rr, erDays, toPivot, insider };
  scanSigCache[sym] = s;
  return s;
}

// Stable per-symbol sparkline data
const sparkCache = {};
function fakeSpark(sym) {
  if (sparkCache[sym]) return sparkCache[sym];
  let p = 50 + (sym.charCodeAt(0) % 20);
  const arr = [];
  const trend = ((sym.charCodeAt(1) || 0) % 5 - 2) * 0.2;
  for (let i = 0; i < 22; i++) {
    p += trend + (Math.sin(i * 0.6 + sym.charCodeAt(0)) * 0.7);
    arr.push(p);
  }
  sparkCache[sym] = arr;
  return arr;
}

window.ScanColumn = ScanColumn;
window.SCAN_WIDTHS = SCAN_WIDTHS;

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
              { id: "buy",        label: "BUY",   tone: "gn" },
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
  // Use same WATCHLIST as data — filter / re-rank by surface
  const items = useMemoSC(() => {
    if (activeSurface === "buy")     return WATCHLIST.filter(w => w.verdict === "BUY");
    if (activeSurface === "elite")   return WATCHLIST.filter(w => w.score >= 70);
    if (activeSurface === "watchlist")return [...WATCHLIST].sort((a,b) => b.score - a.score);
    // map mode shows top movers from heatmap
    return HEATMAP
      .map(([sym, sector, mcap, chg]) => {
        const w = WATCHLIST.find(x => x.sym === sym) || { sym, name: sector, price: 0, chg, score: 50 + Math.round(chg*5), verdict: chg > 1.5 ? "BUY" : chg > 0 ? "WATCH" : "WATCH", setup: sector };
        return { ...w, chg, sector };
      })
      .sort((a, b) => Math.abs(b.chg) - Math.abs(a.chg))
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

function ScanRow({ item, active, onClick, widthCat, collapsed, rank }) {
  const verdictTone = item.verdict === "BUY" ? "gn" : item.verdict === "AVOID" ? "rd" : "amb";
  if (collapsed) {
    // thin rail mode — just symbol + chg
    return (
      <button
        className={`sc-row sc-row--mini ${active ? "is-active" : ""}`}
        onClick={onClick}
        title={`${item.name} · ${item.verdict} · score ${item.score}`}
      >
        <span className={`sc-row-sym mono ${active ? "copper" : ""}`}>{item.sym}</span>
        <span className={`sc-row-chg mono ${item.chg >= 0 ? "up" : "dn"}`}>
          {item.chg >= 0 ? "+" : ""}{item.chg.toFixed(1)}
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
        <span className={`sc-row-sym mono ${active ? "copper" : ""}`}><b>{item.sym}</b></span>
        <span className={`sc-row-chg mono ${item.chg >= 0 ? "up" : "dn"}`}>
          {item.chg >= 0 ? "+" : ""}{item.chg.toFixed(2)}%
        </span>
        <span className="sc-row-score mono"><b>{item.score}</b></span>
      </div>
      {(widthCat === "L" || widthCat === "XL" || widthCat === "M") && (
        <div className="sc-row-meta">
          <span className="sc-row-name dim">{item.name}</span>
          {(widthCat === "L" || widthCat === "XL") && (
            <span className="sc-row-px mono dim2">${item.price.toFixed(2)}</span>
          )}
        </div>
      )}
      {(widthCat === "L" || widthCat === "XL") && (
        <div className="sc-row-foot">
          <Pill tone={verdictTone} small>{item.verdict}</Pill>
          <span className="sc-row-setup mono dim">{item.setup}</span>
        </div>
      )}
      {widthCat === "XL" && (
        <div className="sc-row-spark">
          <Sparkline data={fakeSpark(item.sym)} color={`var(--${item.chg >= 0 ? "gn" : "rd"})`} w={180} h={20} />
        </div>
      )}
    </button>
  );
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

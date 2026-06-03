// market-map.jsx — treemap heatmap sized by mcap, colored by daily %
// Plus secondary surfaces: Watchlist, Elite Picks, BUY candidates.

const { useMemo: useMemoMM } = React;

// Simple squarified-ish treemap using rows of slices.
function layoutTreemap(items, w, h) {
  // items: [{ key, value, ...payload }]
  const total = items.reduce((s, i) => s + i.value, 0);
  // Greedy row layout: pack into rows of decreasing width.
  const rects = [];
  let remaining = [...items].sort((a, b) => b.value - a.value);
  let y = 0;
  let remH = h;
  let remW = w;
  while (remaining.length) {
    // pick how many items go in the next row, minimizing worst aspect.
    const rowH = Math.max(40, Math.min(remH, remH * 0.42)); // banded rows
    const rowItems = [];
    let rowVal = 0;
    const remTotal = remaining.reduce((s, i) => s + i.value, 0);
    const rowTargetArea = (rowH / remH) * remTotal;
    while (remaining.length && rowVal < rowTargetArea) {
      const next = remaining.shift();
      rowItems.push(next);
      rowVal += next.value;
    }
    // place items in row
    let x = 0;
    for (const it of rowItems) {
      const wPx = (it.value / rowVal) * remW;
      rects.push({ ...it, x, y, w: wPx, h: rowH });
      x += wPx;
    }
    y += rowH;
    remH -= rowH;
    if (remH < 24) break;
  }
  return rects;
}

function pctColor(p) {
  // Returns high-contrast cell color that works on both dark + light themes.
  // p in % (e.g. +2.4 / -1.2)
  const abs = Math.min(Math.abs(p), 5);
  const intensity = 0.30 + (abs / 5) * 0.55;
  if (p >= 0.2) return { bg: `rgba(34, 175, 92, ${intensity})`, fg: "#e8fcef" };
  if (p >= -0.2) return { bg: `rgba(120, 120, 120, 0.22)`, fg: "#d8d8d8" };
  return { bg: `rgba(220, 60, 60, ${intensity})`, fg: "#fde6e6" };
}

function MarketMap({ onTicker, dims }) {
  // group by sector, allocate per-sector area proportional to summed mcap
  const w = dims?.w || 1100;
  const h = dims?.h || 680;
  const bySector = useMemoMM(() => {
    const g = {};
    for (const [sym, sector, mcap, chg] of HEATMAP) {
      if (!g[sector]) g[sector] = { sector, items: [], total: 0 };
      g[sector].items.push({ key: sym, value: mcap, sym, sector, mcap, chg });
      g[sector].total += mcap;
    }
    return SECTORS_ORDER.map(s => g[s]).filter(Boolean);
  }, []);
  const grandTotal = bySector.reduce((s, g) => s + g.total, 0);

  // Lay sectors out as banded rows (treemap of treemaps).
  const sectorRects = useMemoMM(() => {
    return layoutTreemap(
      bySector.map(g => ({ key: g.sector, value: g.total, ...g })),
      w, h
    );
  }, [bySector, w, h]);

  // Indices strip
  const indices = [
    { sym: "S&P 500", val: "6,148.2", chg: 0.42, tone: "gn" },
    { sym: "NASDAQ",  val: "20,310",  chg: 0.84, tone: "gn" },
    { sym: "DOW",     val: "42,684",  chg: 0.18, tone: "gn" },
    { sym: "RUSSELL", val: "2,182",   chg: -0.21, tone: "rd" },
    { sym: "VIX",     val: "17.4",    chg: -1.81, tone: "gn" },
    { sym: "US10Y",   val: "4.32%",   chg: -0.46, tone: "gn" },
  ];

  return (
    <div className="mm-wrap">
      <div className="mm-indices">
        {indices.map((i, k) => (
          <div key={k} className={`mm-idx mm-idx--${i.chg >= 0 ? "gn" : "rd"}`}>
            <span className="mm-idx-sym mono">{i.sym}</span>
            <span className="mm-idx-val mono">{i.val}</span>
            <span className={`mm-idx-chg mono ${i.chg >= 0 ? "up" : "dn"}`}>
              {i.chg >= 0 ? "+" : ""}{i.chg.toFixed(2)}%
            </span>
          </div>
        ))}
      </div>

      <div className="mm-toolbar">
        <div className="mm-title">
          <span className="mono label-cap">Market Map</span>
          <span className="mono dim2">· sized by market cap · colored by 1D %</span>
        </div>
        <div className="mm-toolbar-right">
          <div className="seg" role="tablist">
            <button className="seg-btn is-on">1D</button>
            <button className="seg-btn">5D</button>
            <button className="seg-btn">1M</button>
            <button className="seg-btn">YTD</button>
          </div>
          <div className="seg" role="tablist">
            <button className="seg-btn is-on">Sector</button>
            <button className="seg-btn">Industry</button>
            <button className="seg-btn">Theme</button>
          </div>
          <FreshnessPill state="live" age="18s" />
        </div>
      </div>

      <div className="mm-body" style={{ width: "100%", height: h }}>
        <svg
          width="100%"
          height={h}
          viewBox={`0 0 ${w} ${h}`}
          preserveAspectRatio="none"
          style={{ display: "block" }}
        >
          {sectorRects.map(sec => {
            const inner = layoutTreemap(sec.items, sec.w - 2, sec.h - 22);
            return (
              <g key={sec.sector} transform={`translate(${sec.x},${sec.y})`}>
                {/* sector label band */}
                <rect x="0" y="0" width={sec.w} height="22" fill="rgba(20,26,35,0.85)" />
                <line x1="0" y1="22" x2={sec.w} y2="22" stroke="rgba(255,255,255,0.12)" />
                <text x="8" y="15" className="mono"
                      fontSize="11" letterSpacing="0.18em" fontWeight="500" fill="rgba(255,255,255,0.85)">
                  {sec.sector.toUpperCase()}
                </text>
                <text x={sec.w - 8} y="15" textAnchor="end" className="mono"
                      fontSize="10.5" fill="rgba(255,255,255,0.55)">
                  ${(sec.total).toLocaleString()}B
                </text>
                <g transform="translate(1,22)">
                  {inner.map(it => {
                    const c = pctColor(it.chg);
                    const showLabel = it.w > 36 && it.h > 30;
                    const showPct = it.w > 28 && it.h > 22;
                    const isUs = it.sym === "ARCM";
                    return (
                      <g
                        key={it.sym}
                        transform={`translate(${it.x},${it.y})`}
                        className="mm-cell"
                        onClick={() => onTicker(it.sym)}
                      >
                        <rect
                          x="0.5" y="0.5"
                          width={Math.max(1, it.w - 1)}
                          height={Math.max(1, it.h - 1)}
                          fill={c.bg}
                          stroke={isUs ? "var(--copper)" : "rgba(255,255,255,0.08)"}
                          strokeWidth={isUs ? "1.5" : "0.5"}
                        />
                        {showLabel && (
                          <text x={it.w / 2} y={it.h / 2 - 2} textAnchor="middle"
                                className="mono" fontSize={Math.min(15, Math.max(11, it.w / 7))}
                                fontWeight="600" fill={c.fg}>
                            {it.sym}
                          </text>
                        )}
                        {showPct && (
                          <text x={it.w / 2} y={it.h / 2 + 13} textAnchor="middle"
                                className="mono" fontSize={Math.min(11, Math.max(9, it.w / 10))}
                                fill={c.fg} opacity="0.9">
                            {it.chg >= 0 ? "+" : ""}{it.chg.toFixed(1)}%
                          </text>
                        )}
                      </g>
                    );
                  })}
                </g>
              </g>
            );
          })}
        </svg>
      </div>

      <div className="mm-legend">
        <div className="mm-leg-grp">
          <span className="label-cap">1D %</span>
          <div className="mm-leg-bar">
            {[-4, -2, 0, 1, 2, 4].map((p, i) => {
              const c = pctColor(p === 0 ? 0.5 : p);
              return <div key={i} style={{ background: c.bg }} />;
            })}
          </div>
          <span className="mono dim2">−5% · +5%</span>
        </div>
        <div className="mm-leg-grp">
          <span className="label-cap">Tickers</span>
          <span className="mono">{HEATMAP.length}</span>
        </div>
        <div className="mm-leg-grp">
          <span className="label-cap">Universe</span>
          <span className="mono">US equity · ≥$100M mcap</span>
        </div>
        <div className="mm-leg-grp">
          <span className="label-cap">Tip</span>
          <span className="mono dim2">Click any tile for the 14-lens detail</span>
        </div>
      </div>
    </div>
  );
}

window.MarketMap = MarketMap;

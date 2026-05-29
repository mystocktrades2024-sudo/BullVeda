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
  // p in % (e.g. +2.4 / -1.2)
  if (p >= 3)  return { bg: "rgba(74,222,128,0.42)", fg: "#dffce6" };
  if (p >= 1)  return { bg: "rgba(74,222,128,0.26)", fg: "#cfeed8" };
  if (p >= 0)  return { bg: "rgba(74,222,128,0.12)", fg: "#b8d8c1" };
  if (p >= -1) return { bg: "rgba(248,113,113,0.14)", fg: "#e8c4c4" };
  if (p >= -3) return { bg: "rgba(248,113,113,0.28)", fg: "#f1c8c8" };
  return { bg: "rgba(248,113,113,0.46)", fg: "#fde4e4" };
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

  return (
    <div className="mm-wrap">
      <div className="mm-toolbar">
        <div className="mm-title">
          <span className="mono label-cap">Market Map</span>
          <span className="mono dim2">· Sized by market cap · Colored by 1D %</span>
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
          preserveAspectRatio="xMidYMid meet"
          style={{ display: "block" }}
        >
          {sectorRects.map(sec => {
            const inner = layoutTreemap(sec.items, sec.w - 2, sec.h - 18);
            return (
              <g key={sec.sector} transform={`translate(${sec.x},${sec.y})`}>
                {/* sector label band */}
                <rect x="0" y="0" width={sec.w} height="18" fill="var(--bg-2)" />
                <line x1="0" y1="18" x2={sec.w} y2="18" stroke="var(--line)" />
                <text x="6" y="13" className="mono"
                      fontSize="10" letterSpacing="0.16em" fill="var(--ink-2)">
                  {sec.sector.toUpperCase()}
                </text>
                <text x={sec.w - 6} y="13" textAnchor="end" className="mono"
                      fontSize="10" fill="var(--ink-3)">
                  {(sec.total).toLocaleString()}B
                </text>
                <g transform="translate(1,18)">
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
                          stroke={isUs ? "var(--copper)" : "var(--line)"}
                          strokeWidth={isUs ? "1.5" : "0.5"}
                        />
                        {showLabel && (
                          <text x={it.w / 2} y={it.h / 2 - 2} textAnchor="middle"
                                className="mono" fontSize={Math.min(13, Math.max(10, it.w / 8))}
                                fontWeight="500" fill={c.fg}>
                            {it.sym}
                          </text>
                        )}
                        {showPct && (
                          <text x={it.w / 2} y={it.h / 2 + 11} textAnchor="middle"
                                className="mono" fontSize={Math.min(10, Math.max(8, it.w / 11))}
                                fill={c.fg} opacity="0.85">
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

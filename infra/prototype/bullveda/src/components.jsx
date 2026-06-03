// components.jsx — the recurring grammar of the terminal
// Section header, KPI tile, Pill, DataTable, CrossLensStrip, FreshnessPill,
// WilsonPill, StateWrap (handles loading/empty/scaffolding/live), Sparkline,
// Gauge, Radar, Cone.
//
// All read CSS vars at runtime so the dark/light theme + Tweaks just work.

const { useState, useEffect, useRef, useMemo } = React;

// ────────────────────────────────────────────────────────────
// Section header
// ────────────────────────────────────────────────────────────

function SectionHeader({ n, title, sub, freshness = "live", freshnessAge, right, style = "copper" }) {
  // style: 'copper' (§N copper number), 'minimal' (no number, thin rule), 'sticky-rail' (left rail)
  if (style === "minimal") {
    return (
      <div className="sec-hdr sec-hdr--min">
        <div className="sec-hdr-text">
          <div className="sec-hdr-title">{title}</div>
          {sub && <div className="sec-hdr-sub">{sub}</div>}
        </div>
        <div className="sec-hdr-right">
          <FreshnessPill state={freshness} age={freshnessAge} />
          {right}
        </div>
      </div>
    );
  }
  if (style === "sticky-rail") {
    return (
      <div className="sec-hdr sec-hdr--rail">
        <div className="sec-hdr-rail-num">§{String(n).padStart(2, "0")}</div>
        <div className="sec-hdr-text">
          <div className="sec-hdr-title">{title}</div>
          {sub && <div className="sec-hdr-sub">{sub}</div>}
        </div>
        <div className="sec-hdr-right">
          <FreshnessPill state={freshness} age={freshnessAge} />
          {right}
        </div>
      </div>
    );
  }
  // copper default
  return (
    <div className="sec-hdr sec-hdr--copper">
      <div className="sec-hdr-num">§{n}</div>
      <div className="sec-hdr-text">
        <div className="sec-hdr-title">{title}</div>
        {sub && <div className="sec-hdr-sub">{sub}</div>}
      </div>
      <div className="sec-hdr-right">
        <FreshnessPill state={freshness} age={freshnessAge} />
        {right}
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────
// Freshness pill
// ────────────────────────────────────────────────────────────

function FreshnessPill({ state = "live", age }) {
  if (state === "stale")   return <Pill tone="rd" small>STALE {age || ""}</Pill>;
  if (state === "loading") return <Pill tone="ink" small>· · ·</Pill>;
  if (state === "scaffold")return <Pill tone="amb" small>SCAFFOLD</Pill>;
  if (state === "empty")   return <Pill tone="ink" small>NO DATA</Pill>;
  return <Pill tone="gn" small dot>LIVE {age ? `· ${age}` : ""}</Pill>;
}

// ────────────────────────────────────────────────────────────
// Pill / Tag
// ────────────────────────────────────────────────────────────

function Pill({ tone = "ink", children, small, dot, outline }) {
  const cls = [
    "pill",
    `pill--${tone}`,
    small && "pill--sm",
    outline && "pill--outline",
  ].filter(Boolean).join(" ");
  return (
    <span className={cls}>
      {dot && <span className="pill-dot" />}
      {children}
    </span>
  );
}

// ────────────────────────────────────────────────────────────
// Wilson-LB / n<30 pill — the "honesty surface"
// ────────────────────────────────────────────────────────────

function WilsonPill({ n, winRate, lb }) {
  const noData = n == null || winRate == null;
  const low = !noData && n < 30;
  return (
    <span className={`wilson ${low ? "wilson--low" : ""}`}>
      <span className="wilson-block">
        <span className="wilson-k">n</span>
        <span className="wilson-v mono">{n == null ? "—" : n}</span>
      </span>
      <span className="wilson-block">
        <span className="wilson-k">wr</span>
        <span className="wilson-v mono">{winRate == null ? "—" : (winRate * 100).toFixed(0) + "%"}</span>
      </span>
      <span className="wilson-block">
        <span className="wilson-k">wilson lb</span>
        <span className="wilson-v mono">{lb == null ? "—" : (lb * 100).toFixed(0) + "%"}</span>
      </span>
      {noData && <span className="wilson-warn">no ledger history yet</span>}
      {low && <span className="wilson-warn">n&lt;30 · ACT WITH CAUTION</span>}
    </span>
  );
}

// ────────────────────────────────────────────────────────────
// KPI tile
// ────────────────────────────────────────────────────────────

function KpiTile({ label, value, unit, sub, tone = "ink", delta, spark, style = "bare" }) {
  // style: 'bare' | 'sparkline' | 'delta'
  return (
    <div className={`kpi kpi--${style}`}>
      <div className="kpi-label label-cap">{label}</div>
      <div className={`kpi-value mono tabular kpi-tone--${tone}`}>
        {value}
        {unit && <span className="kpi-unit">{unit}</span>}
      </div>
      {style === "sparkline" && spark && (
        <div className="kpi-spark">
          <Sparkline data={spark} color={`var(--${tone === "ink" ? "ink-3" : tone})`} />
        </div>
      )}
      {style === "delta" && delta != null && (
        <div className={`kpi-delta mono ${delta >= 0 ? "up" : "dn"}`}>
          {delta >= 0 ? "▲" : "▼"} {Math.abs(delta).toFixed(2)}%
        </div>
      )}
      {sub && <div className="kpi-sub label-cap dim">{sub}</div>}
    </div>
  );
}

// ────────────────────────────────────────────────────────────
// Cross-Lens strip (5 cells, lead cell color-topped)
// ────────────────────────────────────────────────────────────

function CrossLens({ lead, cells }) {
  // cells: [{ lens, verdict, note, tone }]  — first cell is the lead
  return (
    <div className="xlens">
      {cells.map((c, i) => (
        <div
          key={i}
          className={`xlens-cell ${i === 0 ? "xlens-lead" : ""}`}
          style={i === 0 ? { borderTopColor: `var(--${lead || "copper"})` } : null}
        >
          <div className="label-cap">{c.lens}</div>
          <div className={`xlens-verdict mono kpi-tone--${c.tone || "ink"}`}>{c.verdict}</div>
          <div className="xlens-note dim">{c.note}</div>
        </div>
      ))}
    </div>
  );
}

// ────────────────────────────────────────────────────────────
// State wrapper — handles loading / empty / scaffold / live
// ────────────────────────────────────────────────────────────

function StateWrap({ state, source, scaffoldOf, children, minH = 80 }) {
  if (state === "live") return children;
  if (state === "loading") {
    return (
      <div className="state state--loading" style={{ minHeight: minH }}>
        <div className="state-spinner" />
        <div className="state-msg mono">Fetching from {source || "feed"}…</div>
      </div>
    );
  }
  if (state === "empty") {
    return (
      <div className="state state--empty" style={{ minHeight: minH }}>
        <div className="state-msg-em">No data for this ticker.</div>
        <div className="state-msg dim">Source: {source || "—"}</div>
      </div>
    );
  }
  if (state === "scaffold") {
    return (
      <div className="state state--scaffold">
        <div className="state-banner">
          <span className="state-banner-icon">⚠</span>
          <span>
            <b>Partial scaffolding</b> — layout built, but {scaffoldOf || "this feed"} isn't wired yet.
            Numbers below are illustrative.
          </span>
        </div>
        <div className="state-scaffold-body">{children}</div>
      </div>
    );
  }
  return children;
}

// ────────────────────────────────────────────────────────────
// Sparkline / Gauge / Radar / Cone
// ────────────────────────────────────────────────────────────

function Sparkline({ data, color = "currentColor", h = 22, w = 84, fill = true }) {
  if (!data || data.length === 0) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const step = w / (data.length - 1);
  const pts = data.map((v, i) => [i * step, h - ((v - min) / range) * h]);
  const d = "M " + pts.map(p => p.join(" ")).join(" L ");
  const area = d + ` L ${w} ${h} L 0 ${h} Z`;
  const gid = `sp-${Math.random().toString(36).slice(2, 8)}`;
  const last = pts[pts.length - 1];
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ display: "block", overflow: "visible" }}>
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.30" />
          <stop offset="100%" stopColor={color} stopOpacity="0.02" />
        </linearGradient>
      </defs>
      {fill && <path d={area} fill={`url(#${gid})`} />}
      <path d={d} stroke={color} fill="none" strokeWidth="1.4" strokeLinecap="round"
            style={{ filter: `drop-shadow(0 0 4px ${color})` }} />
      <circle cx={last[0]} cy={last[1]} r="2.4" fill={color}
              style={{ filter: `drop-shadow(0 0 5px ${color})` }} />
    </svg>
  );
}

function Gauge({ value, max = 100, label, size = 132 }) {
  // semi-circular score gauge
  const cx = size / 2, cy = size * 0.72, r = size * 0.42;
  const startAngle = Math.PI; // 180°
  const endAngle = 2 * Math.PI; // 360°
  const pct = Math.max(0, Math.min(1, value / max));
  const angle = startAngle + (endAngle - startAngle) * pct;
  const x1 = cx + r * Math.cos(startAngle), y1 = cy + r * Math.sin(startAngle);
  const x2 = cx + r * Math.cos(angle),       y2 = cy + r * Math.sin(angle);
  const xE = cx + r * Math.cos(endAngle),    yE = cy + r * Math.sin(endAngle);
  const large = pct > 0.5 ? 1 : 0;
  const tone = value >= 70 ? "var(--gn)" : value >= 50 ? "var(--amb)" : "var(--rd)";
  const gid = `g-${Math.random().toString(36).slice(2, 8)}`;
  return (
    <svg width={size} height={size * 0.86} viewBox={`0 0 ${size} ${size * 0.86}`} style={{ overflow: "visible" }}>
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor={tone} stopOpacity="0.5" />
          <stop offset="100%" stopColor={tone} stopOpacity="1" />
        </linearGradient>
      </defs>
      <path
        d={`M ${x1} ${y1} A ${r} ${r} 0 1 1 ${xE} ${yE}`}
        stroke="var(--line)" strokeWidth="10" fill="none" strokeLinecap="round"
      />
      <path
        d={`M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`}
        stroke={`url(#${gid})`} strokeWidth="10" fill="none" strokeLinecap="round"
        style={{ filter: `drop-shadow(0 0 10px ${tone})` }}
      />
      <circle cx={x2} cy={y2} r="6" fill={tone}
              style={{ filter: `drop-shadow(0 0 8px ${tone})` }} />
      <text x={cx} y={cy - 6} textAnchor="middle" className="mono" fontSize={size * 0.28} fontWeight="500" fill="var(--ink)">{value}</text>
      <text x={cx} y={cy + 14} textAnchor="middle" className="mono label-cap" fontSize="9" letterSpacing="0.14em" fill="var(--ink-3)">{label}</text>
    </svg>
  );
}

function Radar({ pillars, size = 200 }) {
  const keys = ["technical", "fundamental", "catalyst", "risk", "edge"];
  const labels = ["TECH", "FUND", "CAT", "RISK", "EDGE"];
  const cx = size / 2, cy = size / 2, r = size * 0.36;
  const pts = keys.map((k, i) => {
    const a = -Math.PI / 2 + (i * 2 * Math.PI) / keys.length;
    const v = (pillars[k] || 0) / 100;
    return [cx + r * v * Math.cos(a), cy + r * v * Math.sin(a)];
  });
  const axisPts = keys.map((_, i) => {
    const a = -Math.PI / 2 + (i * 2 * Math.PI) / keys.length;
    return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
  });
  const labelPts = keys.map((_, i) => {
    const a = -Math.PI / 2 + (i * 2 * Math.PI) / keys.length;
    return [cx + (r + 14) * Math.cos(a), cy + (r + 14) * Math.sin(a)];
  });
  const polyPts = pts.map(p => p.join(",")).join(" ");
  const gid = `r-${Math.random().toString(36).slice(2, 8)}`;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ overflow: "visible" }}>
      <defs>
        <radialGradient id={gid} cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="var(--copper)" stopOpacity="0.45" />
          <stop offset="100%" stopColor="var(--copper)" stopOpacity="0.05" />
        </radialGradient>
      </defs>
      {[0.25, 0.5, 0.75, 1].map(f => (
        <polygon
          key={f}
          points={keys.map((_, i) => {
            const a = -Math.PI / 2 + (i * 2 * Math.PI) / keys.length;
            return [cx + r * f * Math.cos(a), cy + r * f * Math.sin(a)].join(",");
          }).join(" ")}
          fill="none" stroke="var(--line)" strokeWidth={f === 1 ? "1" : "0.5"}
        />
      ))}
      {axisPts.map((p, i) => (
        <line key={i} x1={cx} y1={cy} x2={p[0]} y2={p[1]} stroke="var(--line)" strokeWidth="0.5" />
      ))}
      <polygon points={polyPts} fill={`url(#${gid})`} stroke="var(--copper)" strokeWidth="1.6"
               style={{ filter: "drop-shadow(0 0 8px var(--copper))" }} />
      {pts.map((p, i) => (
        <circle key={i} cx={p[0]} cy={p[1]} r="3" fill="var(--copper)"
                style={{ filter: "drop-shadow(0 0 6px var(--copper))" }} />
      ))}
      {labelPts.map((p, i) => (
        <text key={i} x={p[0]} y={p[1] + 3} textAnchor="middle"
              className="mono label-cap" fontSize="9" letterSpacing="0.14em" fill="var(--ink-3)">
          {labels[i]}
        </text>
      ))}
    </svg>
  );
}

function Cone({ lo, mid, hi, current = 0, w = 280, h = 110 }) {
  const pad = 14;
  const innerW = w - pad * 2;
  const innerH = h - pad * 2;
  const yMid = pad + innerH / 2;
  const span = Math.max(Math.abs(lo), Math.abs(hi)) * 1.25 || 1;
  const yFor = (v) => yMid - (v / span) * (innerH / 2);
  const path = (v) => `M ${pad} ${yMid} Q ${pad + innerW * 0.4} ${yFor(v)}, ${w - pad} ${yFor(v)}`;
  const gid = `c-${Math.random().toString(36).slice(2, 8)}`;
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ display: "block", overflow: "visible" }}>
      <defs>
        <linearGradient id={`${gid}-gn`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--gn)" stopOpacity="0.40" />
          <stop offset="100%" stopColor="var(--gn)" stopOpacity="0" />
        </linearGradient>
        <linearGradient id={`${gid}-rd`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--rd)" stopOpacity="0" />
          <stop offset="100%" stopColor="var(--rd)" stopOpacity="0.35" />
        </linearGradient>
      </defs>
      {/* Filled cone bands */}
      <path d={`${path(hi)} L ${w - pad} ${yMid} L ${pad} ${yMid} Z`} fill={`url(#${gid}-gn)`} />
      <path d={`${path(lo)} L ${w - pad} ${yMid} L ${pad} ${yMid} Z`} fill={`url(#${gid}-rd)`} />
      {/* Center line */}
      <line x1={pad} y1={yMid} x2={w - pad} y2={yMid} stroke="var(--line)" strokeDasharray="3 3" />
      <path d={path(hi)}  stroke="var(--gn)" strokeOpacity="0.6" strokeWidth="1.25" fill="none" />
      <path d={path(mid)} stroke="var(--gn)" strokeWidth="1.6" fill="none"
            style={{ filter: "drop-shadow(0 0 6px var(--gn))" }} />
      <path d={path(lo)}  stroke="var(--rd)" strokeOpacity="0.7" strokeWidth="1.25" fill="none" />
      <circle cx={pad} cy={yMid} r="3.5" fill="var(--copper)"
              style={{ filter: "drop-shadow(0 0 6px var(--copper))" }} />
      <text x={w - pad} y={yFor(hi) - 4} textAnchor="end" className="mono" fontSize="10" fill="var(--gn)">+{hi.toFixed(1)}%</text>
      <text x={w - pad} y={yFor(mid) - 4} textAnchor="end" className="mono" fontSize="10" fill="var(--ink-2)">+{mid.toFixed(1)}%</text>
      <text x={w - pad} y={yFor(lo) + 12} textAnchor="end" className="mono" fontSize="10" fill="var(--rd)">{lo.toFixed(1)}%</text>
    </svg>
  );
}

Object.assign(window, {
  SectionHeader, FreshnessPill, Pill, WilsonPill, KpiTile, CrossLens, StateWrap,
  Sparkline, Gauge, Radar, Cone,
});

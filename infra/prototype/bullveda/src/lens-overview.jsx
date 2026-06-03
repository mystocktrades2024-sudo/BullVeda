// lens-overview.jsx — quant overview (overrides the in-file LensOverview)
// Loaded AFTER detail-panel.jsx so window.LensOverview = this one.

// ──── Rich VerdictHero — overrides the in-file one ──────────────
function VerdictHero({ ticker, mode, heroStyle, sizeCat }) {
  const pillars = ticker.pillars;
  const entry = ticker.pivot * 1.002;
  const risk = entry - ticker.stop;
  const reward1 = ticker.t1 - entry;
  return (
    <div className="hero vh-rich vh-rich--compact">
      <div className="vhr-cockpit">
        <div className="vhr-vis">
          {heroStyle === "gauge" && <Gauge value={ticker.score} label="OVERALL" size={sizeCat === "S" ? 120 : 140} />}
          {heroStyle === "radar" && <Radar pillars={pillars} size={sizeCat === "S" ? 130 : 156} />}
          {heroStyle === "cone"  && (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
              <div className="label-cap">10d cone · ±{ticker.ml.magnitude.hi.toFixed(0)}%</div>
              <Cone lo={ticker.ml.magnitude.lo} mid={ticker.ml.magnitude.mid} hi={ticker.ml.magnitude.hi} w={220} h={108} />
            </div>
          )}
          <div className="vhr-pillchips">
            {Object.entries(pillars).map(([k, v]) => {
              const tone = v >= 70 ? "gn" : v >= 50 ? "amb" : "rd";
              return <span key={k} className={`vhr-pchip kpi-tone--${tone}`} title={k} data-field={`t.scoring_breakdown.${k}_score`}>{k.slice(0, 4)} {v}</span>;
            })}
          </div>
        </div>

        <div className="vhr-body">
          <div className="vhr-eyebrow">
            <span className="mono label-cap">Setup · Execution · <b className="copper">{mode}</b></span>
            <Pill tone="gn" dot small>LIVE 14:23 ET</Pill>
          </div>
          <div className="vhr-setup mono">
            <b className="copper">{ticker.setupFamily}</b>
            <span className="dim2"> · hold ~{ticker.holdDays}d · </span><b>{ticker.rMultiple.toFixed(2)}R</b>
            <span className="dim2"> · {ticker.setupStats.winRate != null ? (ticker.setupStats.winRate*100).toFixed(0)+"% hist" : "no ledger hist"}{ticker.setupStats.wilsonLB != null ? " · Wilson LB "+(ticker.setupStats.wilsonLB*100).toFixed(0)+"%" : ""}</span>
          </div>

          <div className="vhr-ticket">
            <div className="vhr-tk">
              <div className="vhr-tk-l label-cap">ENTRY</div>
              <div className="vhr-tk-v mono copper" data-field="canonical_trade_plan.entry.low" data-fallback="entry_low ▸ entry_lo" data-provenance="comp">${entry.toFixed(2)}</div>
            </div>
            <div className="vhr-tk">
              <div className="vhr-tk-l label-cap">STOP · MAX LOSS</div>
              <div className="vhr-tk-v mono dn" data-field="canonical_trade_plan.stop" data-fallback="trade_plan.stop ▸ stop" data-provenance="comp">${ticker.stop.toFixed(2)}</div>
              <div className="vhr-tk-sub mono dim2">−${risk.toFixed(2)} · −{(risk/entry*100).toFixed(1)}%</div>
            </div>
            <div className="vhr-tk">
              <div className="vhr-tk-l label-cap">T1 · T2</div>
              <div className="vhr-tk-v mono up" data-field="canonical_trade_plan.target1" data-fallback="t1 ▸ trade_levels.t1" data-provenance="comp">${ticker.t1.toFixed(2)} <span className="dim2">·</span> ${ticker.t2.toFixed(2)}</div>
              <div className="vhr-tk-sub mono dim2">+${reward1.toFixed(2)} · {(reward1/risk).toFixed(2)}R</div>
            </div>
            <div className="vhr-tk">
              <div className="vhr-tk-l label-cap">SIZE · NAV</div>
              <div className="vhr-tk-v mono" data-field="position_size.shares" data-provenance="comp">110 sh</div>
              <div className="vhr-tk-sub mono dim2">$7,416 · 6.8% NAV</div>
            </div>
            <div className="vhr-tk">
              <div className="vhr-tk-l label-cap">R · WILSON</div>
              <div className="vhr-tk-v mono copper" data-field="canonical_trade_plan.rr_ratio" data-fallback="rr_ratio ▸ rr" data-provenance="comp">{ticker.rMultiple.toFixed(2)}R</div>
              <div className="vhr-tk-sub mono dim2">LB 47.7% · PF 1.41</div>
            </div>
          </div>

          <div className="vhr-actions">
            <button className="vhr-act vhr-act--gn">▲ Place bracket</button>
            <button className="vhr-act vhr-act--rd">▼ Place short</button>
            <button className="vhr-act">＋ Watchlist</button>
            <button className="vhr-act vhr-act--ghost">⚙ Adjust size</button>
          </div>
        </div>
      </div>
    </div>
  );
}
window.VerdictHero = VerdictHero;

// ════════════════════════════════════════════════════════════════════
// DecisionHero — THE one canonical answer. Merges the composite verdict,
// the trade ticket, and the desk-read edge metrics into a single block so
// trade levels / score / expectancy each live in exactly ONE place.
// Consumer reads top-to-bottom: verdict → edge → the trade → act.
// ════════════════════════════════════════════════════════════════════
(function () {
  const css = `
  .dh{ background:var(--glass-bg-1); border:1px solid var(--glass-line); border-radius:10px; padding:0; margin-bottom:14px; overflow:hidden; }
  .dh--gn{ border-left:3px solid var(--gn); } .dh--amb{ border-left:3px solid var(--amb); } .dh--rd{ border-left:3px solid var(--rd); }
  .dh-top{ display:grid; grid-template-columns:auto 1fr; gap:20px; padding:16px 18px 14px; align-items:center; }
  .dh-vis{ flex:none; display:flex; flex-direction:column; align-items:center; gap:6px; }
  .dh-main{ display:flex; flex-direction:column; gap:9px; min-width:0; }
  .dh-eyebrow{ display:flex; align-items:center; justify-content:space-between; gap:10px; }
  .dh-eyebrow-l{ font-size:10px; letter-spacing:.16em; color:var(--ink-3); }
  .dh-verdict{ display:flex; align-items:baseline; gap:13px; flex-wrap:wrap; }
  .dh-bias{ font-size:25px; font-weight:700; letter-spacing:.01em; line-height:1; }
  .dh-bias--gn{ color:var(--gn); } .dh-bias--amb{ color:var(--amb); } .dh-bias--rd{ color:var(--rd); }
  .dh-net{ font-family:var(--mono); font-size:27px; font-weight:600; line-height:1; color:var(--ink-1); }
  .dh-net-of{ font-size:13px; color:var(--ink-3); }
  .dh-conf{ font-family:var(--mono); font-size:10.5px; color:var(--ink-2); }
  .dh-counts{ display:flex; gap:6px; }
  .dh-cnt{ font-family:var(--mono); font-size:9.5px; font-weight:700; letter-spacing:.05em; padding:2px 8px; border-radius:20px; }
  .dh-cnt--gn{ color:var(--gn); background:color-mix(in oklab,var(--gn) 14%,transparent); }
  .dh-cnt--amb{ color:var(--amb); background:color-mix(in oklab,var(--amb) 14%,transparent); }
  .dh-cnt--rd{ color:var(--rd); background:color-mix(in oklab,var(--rd) 14%,transparent); }
  .dh-setup{ font-family:var(--mono); font-size:12px; color:var(--ink-2); }
  .dh-setup b{ color:var(--ink-1); }
  .dh-read{ font-size:13px; line-height:1.5; color:var(--ink-1); text-wrap:pretty; }
  .dh-dissent{ display:flex; align-items:center; gap:6px; flex-wrap:wrap; font-family:var(--mono); font-size:10.5px; }
  .dh-diss-pill{ font-family:var(--mono); font-size:10.5px; color:var(--ink-1); background:var(--glass-bg-2); border:1px solid var(--glass-line); border-radius:5px; padding:2px 8px; cursor:pointer; }
  .dh-diss-pill:hover{ border-color:var(--copper); color:var(--copper); }
  /* canonical trade ticket strip */
  .dh-ticket{ display:grid; grid-template-columns:repeat(6,1fr); border-top:1px solid var(--glass-line); background:var(--glass-bg-2); }
  .dh-tk{ padding:10px 13px; border-right:1px solid var(--glass-line); display:flex; flex-direction:column; gap:3px; min-width:0; }
  .dh-tk:last-child{ border-right:none; }
  .dh-tk-l{ font-size:8.5px; letter-spacing:.1em; color:var(--ink-3); text-transform:uppercase; }
  .dh-tk-v{ font-family:var(--mono); font-size:16px; font-weight:600; color:var(--ink-1); white-space:nowrap; }
  .dh-tk-v.copper{ color:var(--copper); } .dh-tk-v.up{ color:var(--gn); } .dh-tk-v.dn{ color:var(--rd); }
  .dh-tk-sub{ font-family:var(--mono); font-size:9.5px; color:var(--ink-2); white-space:nowrap; }
  /* hero grid · verdict + ladder (left) · chart (right) */
  .dh-grid{ display:grid; grid-template-columns:minmax(330px,0.9fr) minmax(0,1.1fr); align-items:stretch; }
  .dh-left{ display:flex; flex-direction:column; min-width:0; border-right:1px solid var(--glass-line); }
  .dh-chart{ padding:11px 14px 11px; min-width:0; display:flex; flex-direction:column; }
  .dh-chart-h{ display:flex; align-items:center; justify-content:space-between; gap:8px; margin-bottom:5px; }
  .dh-chart-h .label-cap{ font-size:8.5px; }
  .dh-chart-hr{ display:flex; align-items:center; gap:10px; flex:none; }
  .dh-ema-leg{ font-size:9px; }
  .dh-chart-toggle{ display:inline-flex; border:1px solid var(--glass-line); border-radius:6px; overflow:hidden; }
  .dh-chart-toggle button{ font-family:var(--mono); font-size:9px; letter-spacing:.04em; padding:3px 9px; background:transparent; color:var(--ink-3); border:none; cursor:pointer; }
  .dh-chart-toggle button:first-child{ border-right:1px solid var(--glass-line); }
  .dh-chart-toggle button.is-on{ background:color-mix(in oklab,var(--copper) 18%,transparent); color:var(--copper); }
  .dh-chart-toggle button:hover:not(.is-on){ color:var(--ink-1); }
  .dh-chart-svg{ display:block; width:100%; height:auto; max-height:128px; }
  .dh-lw{ width:100%; height:auto; flex:1 1 auto; min-height:300px; }
  .dh-rail-stats{ display:flex; border-top:1px solid var(--glass-line); border-bottom:1px solid var(--glass-line); margin-top:3px; }
  .dh-rs{ flex:1; padding:6px 9px; border-right:1px solid var(--glass-line); display:flex; flex-direction:column; gap:1px; min-width:0; }
  .dh-rs:last-child{ border-right:none; }
  .dh-rs-l{ font-size:8px; letter-spacing:.09em; color:var(--ink-3); }
  .dh-rs-v{ font-size:14px; font-weight:600; color:var(--ink-1); }
  .dh-rs-sub{ font-size:8.5px; color:var(--ink-2); white-space:nowrap; }
  .dh-ladder{ padding:11px 14px 11px; display:flex; flex-direction:column; gap:7px; min-width:0; border-top:1px solid var(--glass-line); }
  .dh-state{ display:flex; align-items:center; gap:9px; }
  .dh-state-badge{ font-family:var(--mono); font-size:11px; font-weight:700; letter-spacing:.06em; padding:3px 10px; border-radius:6px; border:1px solid currentColor; }
  .dh-state--gn{ color:var(--gn); background:color-mix(in oklab,var(--gn) 12%,transparent); }
  .dh-state--amb{ color:var(--amb); background:color-mix(in oklab,var(--amb) 12%,transparent); }
  .dh-state--rd{ color:var(--rd); background:color-mix(in oklab,var(--rd) 12%,transparent); }
  .dh-state-note{ font-family:var(--mono); font-size:10.5px; color:var(--ink-2); }
  .dh-rungs{ display:flex; flex-direction:column; gap:2px; }
  .dh-rung{ display:grid; grid-template-columns:54px 1fr auto; align-items:center; gap:9px; padding:3px 8px; border-radius:5px; font-family:var(--mono); font-size:11px; }
  .dh-rung-k{ font-size:8.5px; letter-spacing:.08em; color:var(--ink-3); }
  .dh-rung-v{ font-weight:600; color:var(--ink-1); }
  .dh-rung-d{ font-size:10px; color:var(--ink-2); text-align:right; }
  .dh-rung--now{ background:var(--glass-bg-2); border:1px solid color-mix(in oklab,var(--copper) 40%,var(--glass-line)); }
  .dh-rung--now .dh-rung-k{ color:var(--copper); } .dh-rung--now .dh-rung-v{ color:var(--copper); }
  .dh-rung--t .dh-rung-v{ color:var(--gn); } .dh-rung--stop .dh-rung-v{ color:var(--rd); } .dh-rung--trig .dh-rung-v{ color:var(--copper); }
  .dh-fit{ display:flex; align-items:center; gap:7px; flex-wrap:wrap; padding-top:6px; margin-top:1px; border-top:1px solid var(--glass-line); font-family:var(--mono); font-size:10px; color:var(--ink-2); }
  .dh-fit-chip{ padding:2px 7px; border-radius:5px; background:var(--glass-bg-2); border:1px solid var(--glass-line); color:var(--ink-1); }
  .dh-actions{ display:flex; gap:8px; flex-wrap:wrap; padding:12px 14px; border-top:1px solid var(--glass-line); }
  .dh-act{ font-family:var(--mono); font-size:11.5px; font-weight:600; padding:8px 15px; border-radius:7px; border:1px solid var(--glass-line); background:var(--glass-bg-2); color:var(--ink-1); cursor:pointer; transition:all .15s; }
  .dh-act:hover{ border-color:var(--copper); }
  .dh-act--primary{ background:color-mix(in oklab,var(--gn) 18%,transparent); border-color:color-mix(in oklab,var(--gn) 45%,transparent); color:var(--gn); }
  .dh-act--primary:hover{ background:color-mix(in oklab,var(--gn) 26%,transparent); border-color:var(--gn); }
  .dh-act--rd{ color:var(--rd); border-color:color-mix(in oklab,var(--rd) 35%,transparent); }
  .dh-act--rd:hover{ border-color:var(--rd); }
  .dh-act--spacer{ margin-left:auto; }
  @media (max-width:980px){ .dh-top{ grid-template-columns:1fr; } .dh-vis{ flex-direction:row; align-self:flex-start; } .dh-grid{ grid-template-columns:1fr; } .dh-left{ border-right:none; } .dh-chart{ border-top:1px solid var(--glass-line); } .dh-lw{ min-height:280px; } .dh-ticket{ grid-template-columns:repeat(3,1fr); } .dh-tk:nth-child(3n){ border-right:none; } .dh-tk:nth-child(-n+3){ border-bottom:1px solid var(--glass-line); } }
  @media (max-width:520px){ .dh-ticket{ grid-template-columns:repeat(2,1fr); } .dh-tk:nth-child(2n){ border-right:none; } }`;
  if (!document.getElementById("dh-css")) { const s = document.createElement("style"); s.id = "dh-css"; s.textContent = css; document.head.appendChild(s); }
})();

// Resolve a coherent {price,pivot,stop,t1,t2} set. The canonical ticker is
// already consistent; off-universe stubs reuse one ticker's levels with their
// own price, so we rescale geometry around price when it's clearly inconsistent.
window.coherentLevels = function (t) {
  const price = t.price || t.pivot || 0;
  let pivot = t.pivot, stop = t.stop, t1 = t.t1, t2 = t.t2;
  const ordered = stop < pivot && pivot < t1 && t1 < t2;
  const near = price > 0 && Math.abs(price / pivot - 1) < 0.25 && price > stop * 0.9 && price < t2 * 1.08;
  if (!(ordered && near) && price > 0) {
    pivot = +(price * 0.982).toFixed(2);
    stop  = +(price * 0.926).toFixed(2);
    t1    = +(price * 1.080).toFixed(2);
    t2    = +(price * 1.160).toFixed(2);
  }
  return { price, pivot, stop, t1, t2 };
};

// ─── discoveryFootprint — which screen engines surfaced this name ───
// Deterministic per-symbol. In production, read each engine's ranked
// output (momentum/ML/earnings/options/insider/SMC) and report hits.
function discoveryFootprint(ticker) {
  const sym = (ticker.symbol || "ARGN").toUpperCase();
  let h = 0; for (let i = 0; i < sym.length; i++) h = (h * 31 + sym.charCodeAt(i)) >>> 0;
  const rnd = (n) => { h = (h * 1103515245 + 12345) >>> 0; return h % n; };
  const defs = [
    { id: "momentum",     label: "Momentum",       surf: "momentum",     sub: "rel-strength rank",   metric: () => `RS ${80 + rnd(20)}` },
    { id: "ai-predict",   label: "ML Predictions", surf: "ai-predict",   sub: "model edge",          metric: () => `P(up) 0.${62 + rnd(33)}` },
    { id: "earnings",     label: "Earnings AI",    surf: "earnings-cal", sub: "surprise prediction", metric: () => `ESP +${(1 + rnd(50) / 10).toFixed(1)}%` },
    { id: "options-flow", label: "Options Flow",   surf: "options-flow", sub: "unusual activity",    metric: () => ["call sweep", "UOA", "put-sale"][rnd(3)] },
    { id: "insider",      label: "Insider",        surf: "insider",      sub: "Form-4 cluster",      metric: () => ["CFO+COO buy", "CEO buy", "3-insider cluster"][rnd(3)] },
    { id: "smc",          label: "SMC · Patterns", lens: "patterns",     sub: "structure",           metric: () => ["VCP base", "OB + BoS", "flag · B2"][rnd(3)] },
  ];
  const out = defs.map(e => {
    const hit = rnd(100) > 32;            // ~68% each → ~4 of 6
    const rank = hit ? 1 + rnd(38) : null;
    const m = e.metric();
    const tone = !hit ? "off" : rank <= 10 ? "gn" : rank <= 25 ? "cy" : "amb";
    return { ...e, hit, rank, tone, m };
  });
  if (out.filter(e => e.hit).length < 2) { out[0].hit = true; out[0].rank = out[0].rank || (3 + rnd(8)); out[0].tone = "gn"; }
  return out;
}

// horizon strip — same ticker scored across all 3 modes, side by side
function HorizonStrip({ ticker, mode, onMode }) {
  const cv = window.compositeVerdict;
  if (!cv) return null;
  const modes = [["SWING", "Swing", "2–15d"], ["POSITION", "Position", "1–6mo"], ["INVESTMENT", "Invest", "1–5yr"]];
  return (
    <div className="hz">
      <span className="hz-tag mono">HORIZONS</span>
      {modes.map(([m, label, hold]) => {
        const v = cv(ticker, m);
        const bias = window.secBias ? window.secBias(v.verdict) : v.verdict;
        return (
          <button key={m} className={`hz-cell hz-${v.vtone} ${m === mode ? "is-active" : ""}`} onClick={() => onMode && onMode(m)} title={`Score ${v.net}/100 · ${v.conf} confidence`}>
            <span className="hz-mode mono">{label}<span className="hz-hold dim2"> · {hold}</span></span>
            <span className={`hz-bias mono kpi-tone--${v.vtone}`}>{bias}</span>
            <span className="hz-net mono">{v.net}<span className="dim2">/100</span></span>
          </button>
        );
      })}
      <span className="hz-note mono dim2">one name, three time horizons — weighting reflows per mode</span>
    </div>
  );
}

function SurfacedBy({ ticker }) {
  const engines = React.useMemo(() => discoveryFootprint(ticker), [ticker.symbol]);
  const hits = engines.filter(e => e.hit);
  const miss = engines.filter(e => !e.hit);
  const go = (e) => { if (e.lens) { window.__setLens && window.__setLens(e.lens); } else { window.__setSurface && window.__setSurface(e.surf); } };
  return (
    <div className="sfb">
      <div className="sfb-hd">
        <span className="sfb-tag mono">SURFACED BY</span>
        <span className="sfb-count mono"><b className={hits.length >= 4 ? "up" : hits.length >= 3 ? "copper" : "warn"}>{hits.length}</b> of {engines.length} engines</span>
        <span className="sfb-sub mono dim2">independent screens that flagged {ticker.symbol} — more hits = stronger confluence · click to open the engine</span>
      </div>
      <div className="sfb-chips">
        {hits.sort((a, b) => (a.rank || 99) - (b.rank || 99)).map(e => (
          <button key={e.id} className={`sfb-chip sfb-${e.tone}`} onClick={() => go(e)} title={`${e.label} · ${e.sub}`}>
            <span className="sfb-chip-l mono">{e.label}</span>
            {e.rank != null && <span className="sfb-rank mono">#{e.rank}</span>}
            <span className="sfb-m mono">{e.m}</span>
          </button>
        ))}
        {miss.length > 0 && <span className="sfb-miss mono dim2">not in · {miss.map(e => e.label).join(" · ")}</span>}
      </div>
    </div>
  );
}

// ─── SetupChart — compact TradingView candles w/ plan price-lines on the axis ───
function SetupChart({ L, sym, view = "full" }) {
  const wrap = React.useRef(null);
  const refs = React.useRef({});

  // deterministic seeded series — base → VCP contraction → breakout to live price
  const d = React.useMemo(() => {
    const str = sym || "ARCM"; let s = 0;
    for (let i = 0; i < str.length; i++) s += str.charCodeAt(i) * (i + 7);
    const rng = () => { s = (s * 9301 + 49297) % 233280; return s / 233280; };
    const n = 46, step = 86400, now = Math.floor(Date.now() / 1000), start = now - n * step;
    const baseMid = (L.stop + L.pivot) / 2, range = (L.pivot - L.stop) || (L.pivot * 0.05);
    const bars = []; let p = L.pivot * 0.985;
    for (let i = 0; i < n; i++) {
      const t = i / (n - 1);
      // volatility contracts through the base (VCP), expands on the breakout leg
      const contract = t < 0.4 ? 1 - t * 0.6 : t < 0.78 ? 0.78 - (t - 0.4) * 1.05 : 0.36 + (t - 0.78) * 2.1;
      const vol = range * 0.18 * Math.max(0.12, contract);
      let target;
      if (t < 0.4) target = baseMid + (L.pivot - baseMid) * (0.4 - t);
      else if (t < 0.78) target = baseMid + Math.sin(i * 0.7) * vol * 0.55;
      else target = L.pivot + (L.price - L.pivot) * Math.pow((t - 0.78) / 0.22, 0.9);
      p = p + (target - p) * 0.32 + (rng() - 0.5) * vol * 1.15;
      // occasional small gap for realism
      let o = i === 0 ? p : bars[i - 1].close;
      if (i > 0 && rng() > 0.9) o = bars[i - 1].close * (1 + (rng() - 0.5) * 0.012);
      const c = +p.toFixed(2);
      const dayRange = vol * (0.55 + rng() * 1.25);              // varied true range
      const upWick = dayRange * (0.15 + rng() * 0.6);
      const dnWick = dayRange * (0.15 + rng() * 0.6);
      const hi = +(Math.max(o, c) + upWick).toFixed(2);
      const lo = +(Math.min(o, c) - dnWick).toFixed(2);
      const breakout = t > 0.78;
      const spike = rng() > 0.86 ? 0.7 : 0;
      const v = Math.round((0.35 + rng() * 0.4 + (breakout ? 0.7 : 0) + spike) * 1e6);
      bars.push({ time: start + i * step, open: +(+o).toFixed(2), high: hi, low: lo, close: c, value: v });
    }
    bars[n - 1].close = +L.price.toFixed(2);
    bars[n - 1].high = Math.max(bars[n - 1].high, bars[n - 1].close + range * 0.05);
    bars[n - 1].low = Math.min(bars[n - 1].low, bars[n - 1].close);
    const ema = per => { const k = 2 / (per + 1); let pr = bars[0].close; return bars.map((b, i) => { pr = i === 0 ? b.close : b.close * k + pr * (1 - k); return { time: b.time, value: +pr.toFixed(2) }; }); };
    return { bars, e9: ema(9), e21: ema(21) };
  }, [sym, L.pivot, L.stop, L.price, L.t1, L.t2]);

  // create chart once
  React.useEffect(() => {
    if (!wrap.current || !window.LightweightCharts) return;
    const LWC = window.LightweightCharts;
    const cssv = (n, f) => (getComputedStyle(document.documentElement).getPropertyValue(n).trim() || f);
    const chart = LWC.createChart(wrap.current, {
      autoSize: false,
      width: Math.max(10, wrap.current.clientWidth), height: Math.max(10, wrap.current.clientHeight),
      layout: { background: { color: "transparent" }, textColor: cssv("--ink-3", "#7c807c"), fontFamily: "inherit", fontSize: 9 },
      grid: { vertLines: { visible: false }, horzLines: { color: "rgba(255,255,255,0.04)" } },
      crosshair: { mode: 1, vertLine: { visible: false, labelVisible: false }, horzLine: { labelVisible: false, color: "rgba(255,255,255,0.12)" } },
      rightPriceScale: { borderColor: "rgba(255,255,255,0.10)", scaleMargins: { top: 0.08, bottom: 0.22 }, entireTextOnly: true },
      timeScale: { visible: false, rightOffset: 2 },
      handleScroll: false, handleScale: false,
    });
    const candle = chart.addCandlestickSeries({
      upColor: "#34d399", downColor: "#f87171", borderUpColor: "#34d399", borderDownColor: "#f87171",
      wickUpColor: "rgba(52,211,153,0.7)", wickDownColor: "rgba(248,113,113,0.7)",
      priceLineVisible: true, priceLineColor: "rgba(217,119,87,0.85)", priceLineStyle: 0, priceLineWidth: 1, lastValueVisible: true,
      autoscaleInfoProvider: () => { const rg = refs.current.range; return rg ? { priceRange: { minValue: rg.min, maxValue: rg.max } } : null; },
    });
    const vol = chart.addHistogramSeries({ priceFormat: { type: "volume" }, priceScaleId: "vol" });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.86, bottom: 0 } });
    // SVG overlay for shaded risk / reward zones (chart is static — redraw on resize)
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "dh-lw-zones");
    svg.style.cssText = "position:absolute;left:0;top:0;width:100%;height:100%;pointer-events:none;z-index:1;";
    wrap.current.style.position = "relative";
    wrap.current.appendChild(svg);
    refs.current = { chart, candle, vol, svg, lines: [], ov: [] };
    const draw = () => {
      const r = refs.current; if (!r.chart || !r.zones) return;
      const host = wrap.current; if (!host) return;
      const psW = (() => { try { return r.chart.priceScale("right").width(); } catch (e) { return 52; } })();
      const W = host.clientWidth - psW, H = host.clientHeight;
      while (r.svg.firstChild) r.svg.removeChild(r.svg.firstChild);
      r.zones.forEach(z => {
        const y1 = r.candle.priceToCoordinate(z.top), y2 = r.candle.priceToCoordinate(z.bot);
        if (y1 == null || y2 == null) return;
        const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        rect.setAttribute("x", 0); rect.setAttribute("y", Math.min(y1, y2));
        rect.setAttribute("width", Math.max(0, W)); rect.setAttribute("height", Math.abs(y2 - y1));
        rect.setAttribute("fill", z.fill); rect.setAttribute("opacity", z.op);
        r.svg.appendChild(rect);
      });
    };
    refs.current.draw = draw;
    const fit = () => {
      const host = wrap.current; if (!host) return false;
      const r = host.getBoundingClientRect();
      const w = Math.round(r.width), h = Math.round(r.height) || 288;
      if (w < 20) { return false; }                   // still hidden / unlaid-out
      try {
        // jiggle the size so LWC reallocates the bitmap and repaints, even if it
        // was first sized while hidden (otherwise the canvas backing stays 300×150).
        chart.resize(w - 1, h, true);
        chart.resize(w, h, true);
        chart.timeScale().fitContent();
        if (refs.current.replay) refs.current.replay();
      } catch (e) {}
      draw();
      return true;
    };
    refs.current.fit = fit;
    const ro = new ResizeObserver(() => requestAnimationFrame(fit));
    ro.observe(wrap.current);
    refs.current.ro = ro;
    fit();
    // persistent self-heal: if the canvas backing ever drifts from the container width
    // (e.g. the chart mounted while the lens was hidden), re-fit. Cheap; runs for the lifetime.
    const heal = setInterval(() => {
      const host = wrap.current; if (!host) return;
      const w = Math.round(host.getBoundingClientRect().width); if (w < 20) return;
      const cv = host.querySelector("canvas");
      if (!cv || Math.abs(cv.width - w) > 6) fit();
    }, 350);
    refs.current.heal = heal;
    return () => { try { clearInterval(heal); ro.disconnect(); chart.remove(); } catch (e) {} refs.current = {}; };
  }, []);

  // feed data + zones + bold level lines + EMAs
  React.useEffect(() => {
    const r = refs.current; if (!r.chart) return;
    const lows = d.bars.map(b => b.low), highs = d.bars.map(b => b.high);
    const mk = (price, color, title, w = 2, style = 0) => r.candle.createPriceLine({ price, color, lineWidth: w, lineStyle: style, axisLabelVisible: true, title });
    r.lines.forEach(l => r.candle.removePriceLine(l));
    if (view === "action") {
      // tight frame — candles read big; targets live in the ladder beside the chart
      r.range = { min: Math.min(L.stop, ...lows) * 0.994, max: Math.max(L.price, ...highs) * 1.02 };
      r.zones = [
        { top: r.range.max, bot: L.pivot, fill: "#34d399", op: 0.06 },
        { top: L.pivot, bot: Math.max(L.stop, r.range.min), fill: "#f87171", op: 0.09 },
      ];
      r.lines = [
        mk(L.pivot, "#d97757", `TRIGGER ${L.pivot.toFixed(2)}`),
        mk(L.stop, "#f87171", `STOP ${L.stop.toFixed(2)}`),
      ];
    } else {
      // full trade — frame stop → T1 so the targets sit on the chart
      r.range = { min: Math.min(L.stop, ...lows) * 0.994, max: L.t1 * 1.012 };
      r.zones = [
        { top: L.t1, bot: L.pivot, fill: "#34d399", op: 0.06 },                          // reward runway → T1
        { top: L.pivot, bot: Math.max(L.stop, r.range.min), fill: "#f87171", op: 0.09 },  // risk band → stop
      ];
      r.lines = [
        mk(L.t2, "#34d399", `T2 ${L.t2.toFixed(2)}`, 1, 2),
        mk(L.t1, "#34d399", `T1 ${L.t1.toFixed(2)}`),
        mk(L.pivot, "#d97757", `TRIGGER ${L.pivot.toFixed(2)}`),
        mk(L.stop, "#f87171", `STOP ${L.stop.toFixed(2)}`),
      ];
    }
    r.candle.setData(d.bars);
    r.vol.setData(d.bars.map(b => ({ time: b.time, value: b.value, color: b.close >= b.open ? "rgba(52,211,153,0.30)" : "rgba(248,113,113,0.30)" })));
    r.replay = () => { try { r.candle.setData(d.bars); } catch (e) {} };
    r.ov.forEach(o => r.chart.removeSeries(o)); r.ov = [];
    const addLine = (data, color) => { const ls = r.chart.addLineSeries({ color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false }); ls.setData(data); r.ov.push(ls); };
    addLine(d.e9, "rgba(93,214,214,0.55)");
    addLine(d.e21, "rgba(167,139,250,0.5)");
    r.chart.timeScale().fitContent();
    requestAnimationFrame(() => { (r.fit || r.draw) && (r.fit || r.draw)(); });
    setTimeout(() => { (r.fit || r.draw) && (r.fit || r.draw)(); }, 60);
  }, [d, L.pivot, L.stop, L.t1, L.t2, view]);

  return <div ref={wrap} className="dh-lw" />;
}
window.SetupChart = SetupChart;

function DecisionHero({ ticker, mode, heroStyle, sizeCat, onLens }) {
  const cv = window.compositeVerdict ? window.compositeVerdict(ticker, mode) : null;
  const net = cv ? cv.net : (ticker.score || 60);
  const vtone = cv ? cv.vtone : (net >= 66 ? "gn" : net >= 50 ? "amb" : "rd");
  const bias = window.secBias ? window.secBias(cv ? cv.verdict : ticker.verdict) : (cv ? cv.verdict : ticker.verdict);
  const pillars = ticker.pillars;
  const L = window.coherentLevels(ticker);
  const [chartView, setChartView] = React.useState(() => { try { return localStorage.getItem("dh-chart-view") || "full"; } catch (e) { return "full"; } });
  const pickChartView = v => { setChartView(v); try { localStorage.setItem("dh-chart-view", v); } catch (e) {} };
  const entry = L.pivot;                       // the trigger / entry
  const risk = entry - L.stop;
  const reward1 = L.t1 - entry;
  const rrToT1 = risk > 0 ? reward1 / risk : 0;
  const ss = ticker.setupStats || {};
  const wr = ss.winRate || 0.617, lb = ss.wilsonLB || 0.477;
  const evR = (wr * rrToT1 - (1 - wr) * 1);
  const erTxt = ticker.earnings ? `earnings in ${ticker.earnings.days}d` : "a clean catalyst window";
  const dissenters = cv ? cv.dissenters.slice(0, 4) : [];

  // ── live STATE relative to the trigger — the "what do I do now" crown ──
  const buyTop = entry * 1.03;
  let st, stTone, stNote;
  if (L.price < entry) { st = "WATCH"; stTone = "amb"; stNote = `${((entry - L.price) / L.price * 100).toFixed(1)}% below trigger · arm alert at $${entry.toFixed(2)}`; }
  else if (L.price <= buyTop) { st = "ACTIONABLE"; stTone = "gn"; stNote = "in the buy zone · trigger cleared"; }
  else { st = "EXTENDED"; stTone = "amb"; stNote = `${((L.price - entry) / entry * 100).toFixed(1)}% above trigger · wait for a pullback`; }

  // sizing math (risk-based): risk budget ÷ per-share stop distance
  const navRisk = 420, shares = risk > 0 ? Math.round(navRisk / risk) : 0;
  const dollars = Math.round(shares * L.price);

  // price ladder rungs, high → low, distance measured from live price
  const dist = v => `${v >= L.price ? "+" : ""}${((v - L.price) / L.price * 100).toFixed(1)}%`;
  const rungs = [
    { k: "T2", v: L.t2, cls: "dh-rung--t", d: dist(L.t2), field: "canonical_trade_plan.target2" },
    { k: "T1", v: L.t1, cls: "dh-rung--t", d: dist(L.t1), field: "canonical_trade_plan.target1" },
    { k: "NOW", v: L.price, cls: "dh-rung--now", d: "live", field: "price" },
    { k: "TRIGGER", v: entry, cls: "dh-rung--trig", d: dist(entry), field: "canonical_trade_plan.entry.low" },
    { k: "STOP", v: L.stop, cls: "dh-rung--stop", d: dist(L.stop), field: "canonical_trade_plan.stop" },
  ].sort((a, b) => b.v - a.v);

  return (
    <div className={`dh dh--${vtone}`}>
      <div className="dh-grid">
       <div className="dh-left">
        <div className="dh-top">
        <div className="dh-vis">
          {heroStyle === "gauge" && <Gauge value={net} label="COMPOSITE" size={sizeCat === "S" ? 108 : 124} />}
          {heroStyle === "cone" && (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
              <div className="label-cap">10d cone · ±{ticker.ml.magnitude.hi.toFixed(0)}%</div>
              <Cone lo={ticker.ml.magnitude.lo} mid={ticker.ml.magnitude.mid} hi={ticker.ml.magnitude.hi} w={200} h={100} />
            </div>
          )}
          {(heroStyle === "radar" || !heroStyle) && <Radar pillars={pillars} size={sizeCat === "S" ? 124 : 144} />}
        </div>

        <div className="dh-main">
          <div className="dh-eyebrow">
            <span className="dh-eyebrow-l mono">COMPOSITE BIAS · {cv ? cv.lenses.length : 12} LENSES · <b className="copper">{mode}</b></span>
            <Pill tone="gn" dot small>LIVE 14:23 ET</Pill>
          </div>

          <div className="dh-verdict">
            <span className={`dh-bias dh-bias--${vtone}`}>{bias}</span>
            <span className="dh-net mono">{net}<span className="dh-net-of">/100</span></span>
            <span className="dh-conf mono">conf {cv ? cv.conf : "—"}</span>
            {cv && (
              <span className="dh-counts">
                <span className="dh-cnt dh-cnt--gn">{cv.agree} agree</span>
                <span className="dh-cnt dh-cnt--amb">{cv.caution} caution</span>
                <span className="dh-cnt dh-cnt--rd">{cv.fail} against</span>
              </span>
            )}
          </div>

          <div className="dh-setup mono">
            <b className="copper">{ticker.setupFamily || "Continuation breakout"}</b>
            <span> · hold ~{ticker.holdDays || 9}d · </span>
            <b className={evR >= 0 ? "up" : "dn"}>{evR >= 0 ? "+" : ""}{evR.toFixed(2)}R expectancy</b>
            <span> · edge LB <b className="up">{(lb * 100).toFixed(0)}%</b> · {erTxt}</span>
          </div>

          <div className="dh-read">
            <b className={vtone === "gn" ? "up" : vtone === "rd" ? "dn" : "warn"}>{ticker.symbol} reads {bias.toLowerCase()}</b> for a {mode.toLowerCase()} hold — a sample-validated {(ticker.setupFamily || "continuation").toLowerCase()} with a real edge (Wilson LB {(lb * 100).toFixed(0)}%, +{evR.toFixed(2)}R). Downside is bounded at one stop; {erTxt} is the live caveat to size around.
          </div>

          {dissenters.length > 0 && (
            <div className="dh-dissent mono">
              <span className="dim2">Watch the dissent:</span>
              {dissenters.map(d => (
                <button key={d.k} className="dh-diss-pill" onClick={() => onLens && onLens(d.k)} title={d.why}>{d.k} <span className="dim2">{d.v}</span></button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── the setup, drawn · + price-to-levels ladder + live state ── */}
        <div className="dh-ladder">
          <div className="dh-state">
            <span className={`dh-state-badge dh-state--${stTone} mono`}>▶ {st}</span>
            <span className="dh-state-note mono">{stNote}</span>
          </div>
          <div className="dh-rungs">
            {rungs.map((r, i) => (
              <div key={i} className={`dh-rung ${r.cls} mono`}>
                <span className="dh-rung-k">{r.k}</span>
                <span className="dh-rung-v" data-field={r.field} data-provenance="comp">${r.v.toFixed(2)}</span>
                <span className="dh-rung-d">{r.d}</span>
              </div>
            ))}
          </div>
          <div className="dh-rail-stats">
            <div className="dh-rs">
              <span className="dh-rs-l mono">R : R</span>
              <span className="dh-rs-v mono copper" data-field="canonical_trade_plan.rr_ratio" data-fallback="rr_ratio ▸ rr" data-provenance="comp">{(ticker.rMultiple || rrToT1).toFixed(2)}R</span>
              <span className="dh-rs-sub mono">reward ÷ risk</span>
            </div>
            <div className="dh-rs">
              <span className="dh-rs-l mono">SIZE</span>
              <span className="dh-rs-v mono" data-field="position_size.shares" data-provenance="comp">{shares} sh</span>
              <span className="dh-rs-sub mono">${dollars.toLocaleString()} · {(dollars / 108420 * 100).toFixed(1)}% NAV</span>
            </div>
            <div className="dh-rs">
              <span className="dh-rs-l mono">EDGE</span>
              <span className="dh-rs-v mono up">{(lb * 100).toFixed(0)}%</span>
              <span className="dh-rs-sub mono">Wilson LB · PF 1.84</span>
            </div>
          </div>
          <div className="dh-fit mono">
            <span className="dh-fit-chip">size = ${navRisk} risk ÷ ${risk.toFixed(2)} stop</span>
            <span className="dh-fit-chip">not held</span>
            <span className="dh-fit-chip">correl 0.34 → book</span>
            <span>adds cleanly · ½-Kelly</span>
          </div>
        </div>
       </div>

       <div className="dh-chart">
          <div className="dh-chart-h">
            <span className="label-cap mono">{chartView === "action" ? "THE SETUP · stop · trigger · EMA 9/21" : "THE SETUP · stop · trigger · T1 / T2 · EMA 9/21"}</span>
            <div className="dh-chart-hr">
              <span className="mono dim2 dh-ema-leg"><b style={{ color: "var(--cy)" }}>━</b> EMA9 <b style={{ color: "var(--violet)" }}>━</b> EMA21</span>
              <div className="dh-chart-toggle mono">
                <button className={chartView === "action" ? "is-on" : ""} onClick={() => pickChartView("action")} title="Tight frame — bigger candles">Action</button>
                <button className={chartView === "full" ? "is-on" : ""} onClick={() => pickChartView("full")} title="Show the full trade — targets on chart">Full trade</button>
              </div>
            </div>
          </div>
          <SetupChart L={L} sym={ticker.symbol} view={chartView} />
        </div>
      </div>

      <div className="dh-actions">
        <button className="dh-act dh-act--primary">▲ Place bracket</button>
        <button className="dh-act">＋ Watchlist</button>
        <button className="dh-act">⚙ Adjust size</button>
        <button className="dh-act">🔔 Alert at ${entry.toFixed(2)}</button>
        <button className="dh-act dh-act--rd dh-act--spacer">▼ Place short</button>
      </div>
    </div>
  );
}
window.DecisionHero = DecisionHero;

// ─── Thesis card — crisp bull/bear case synthesized across all lenses ───
(function () {
  const css = `
  .thx { background:var(--glass-bg-1); border:1px solid color-mix(in oklab,var(--copper) 22%,var(--glass-line)); border-radius:8px; padding:13px 15px; display:flex; flex-direction:column; gap:11px; margin-bottom:4px; }
  .thx-head { display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap; }
  .thx-head-l { display:flex; align-items:center; gap:9px; flex-wrap:wrap; }
  .thx-bias { font:700 11px var(--mono); padding:3px 10px; border-radius:999px; border:1px solid color-mix(in oklab,currentColor 42%,transparent); background:color-mix(in oklab,currentColor 12%,transparent); }
  .thx-head-sub { font-size:10px; }
  .thx-ai-btn { flex:none; }
  .thx-tag { flex:none; font:700 9px var(--mono); letter-spacing:0.12em; color:var(--copper); border:1px solid color-mix(in oklab,var(--copper) 40%,transparent); border-radius:3px; padding:3px 8px; }
  .thx-line { font-size:13.5px; line-height:1.55; color:var(--ink-1); }
  .thx-col { padding-left:9px; border-left:2px solid var(--glass-line); }
  .thx-col--bull { border-left-color:color-mix(in oklab,var(--gn) 45%,transparent); }
  .thx-col--bear { border-left-color:color-mix(in oklab,var(--rd) 45%,transparent); }
  .thx-cols { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
  .thx-col-h { font-size:9.5px; letter-spacing:0.08em; margin-bottom:5px; }
  .thx-pt { display:flex; gap:8px; align-items:baseline; padding:3px 0; font-size:12px; line-height:1.45; }
  .thx-pt-k { flex:none; min-width:58px; font-weight:700; color:var(--ink-1); font-size:10.5px; }
  .thx-score { flex:none; display:inline-flex; align-items:center; justify-content:center; min-width:24px; height:15px; border-radius:3px; font-size:9.5px; font-weight:700; }
  .thx-score--gn { background:color-mix(in oklab,var(--gn) 20%,transparent); color:var(--gn); }
  .thx-score--amb { background:color-mix(in oklab,var(--amb) 18%,transparent); color:var(--amb); }
  .thx-score--rd { background:color-mix(in oklab,var(--rd) 18%,transparent); color:var(--rd); }
  .thx-pt-d { color:var(--ink-2); }
  .thx-ref { background:var(--glass-bg-2); border:1px solid var(--glass-line); border-radius:6px; padding:9px 11px; }
  .thx-ref-h { font-size:8.5px; letter-spacing:0.1em; display:block; margin-bottom:7px; }
  .thx-ref-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:8px 14px; }
  .thx-ref-cell { display:flex; flex-direction:column; gap:1px; }
  .thx-ref-cell .dim2 { font-size:9px; letter-spacing:0.04em; text-transform:uppercase; }
  .thx-ref-cell .mono:last-child { font-size:12.5px; font-weight:600; color:var(--ink-1); }
  .thx-foot { font-size:9.5px; padding-top:6px; border-top:1px solid var(--glass-line); }
  @media (max-width:760px){ .thx-cols{ grid-template-columns:1fr; } .thx-ref-grid{ grid-template-columns:repeat(2,1fr); } }`;
  if (!document.getElementById("thx-css")) { const s = document.createElement("style"); s.id = "thx-css"; s.textContent = css; document.head.appendChild(s); }
})();

function ThesisCard({ ticker, mode }) {
  const [tAi, setTAi] = React.useState(null);   // null | "loading" | text
  const cv = window.compositeVerdict ? window.compositeVerdict(ticker, mode) : null;
  const net = cv ? cv.net : (ticker.score || 60);
  const bias = window.secBias ? window.secBias(cv ? cv.verdict : ticker.verdict) : (cv ? cv.verdict : ticker.verdict);
  const tone = net >= 66 ? "up" : net >= 50 ? "warn" : "dn";
  const sTone = v => v >= 62 ? "gn" : v >= 46 ? "amb" : "rd";
  const entry = (ticker.pivot || ticker.price || 0) * 1.002;
  const ss = ticker.setupStats || {};
  const erTxt = ticker.earnings ? `earnings in ${ticker.earnings.days}d` : "a clean catalyst window";
  const bulls = cv ? cv.lenses.filter(l => l.v >= 60).sort((a, b) => b.v - a.v).slice(0, 4) : [];
  const bears = cv ? cv.lenses.filter(l => l.v < 48).sort((a, b) => a.v - b.v).slice(0, 3) : [];
  const ref = [
    ["Entry", `$${entry.toFixed(2)}`],
    ["Stop", `$${(ticker.stop || 0).toFixed(2)}`],
    ["T1 · T2", `$${(ticker.t1 || 0).toFixed(2)} · $${(ticker.t2 || 0).toFixed(2)}`],
    ["R:R", `${(ticker.rMultiple || 0).toFixed(2)}R`],
    ["Setup", ticker.setupFamily || "—"],
    ["Win · Wilson", ss.winRate ? `${(ss.winRate * 100).toFixed(0)}% · ${(ss.wilsonLB * 100).toFixed(0)}% LB` : "—"],
    ["Sample", ss.n ? `n=${ss.n}` : "—"],
    ["Earnings", ticker.earnings ? `${ticker.earnings.days}d${ticker.earnings.date ? ` · ${ticker.earnings.date}` : ""}` : "—"],
  ];
  const aiThesis = () => `Write a crisp swing-trade thesis for ${ticker.symbol}${ticker.name ? " (" + ticker.name + ")" : ""}, ${mode} timeframe, overall read ${bias} ${net}/100. 4-5 sentences in plain English: the core idea, the 2-3 strongest supporting points, the single biggest risk, and the key levels to watch.
Supporting: ${bulls.length ? bulls.map(b => `${b.k} ${b.v}/100 (${b.why})`).join("; ") : "composite score " + net}.
Risks / weakest: ${bears.length ? bears.map(b => `${b.k} ${b.v}/100 (${b.why})`).join("; ") : erTxt}.
Levels: entry $${entry.toFixed(2)}, stop $${(ticker.stop || 0).toFixed(2)}, targets $${(ticker.t1 || 0).toFixed(2)} / $${(ticker.t2 || 0).toFixed(2)}, R:R ${(ticker.rMultiple || 0).toFixed(2)}, setup ${ticker.setupFamily || "continuation"}.`;
  const writeThesis = async () => { setTAi("loading"); const r = await window.aiComplete(aiThesis()); setTAi(r.text); };
  const Pt = ({ b }) => (
    <div className="thx-pt"><span className="thx-pt-k mono">{b.k}</span><span className={`thx-score thx-score--${sTone(b.v)} mono`}>{b.v}</span><span className="thx-pt-d">{b.why}</span></div>
  );
  return (
    <div className="thx">
      <div className="thx-head">
        <div className="thx-head-l">
          <span className="thx-tag mono">THESIS</span>
          <span className={`thx-bias mono kpi-tone--${sTone(net)}`}>{bias} · {net}/100</span>
          <span className="thx-head-sub mono dim2">{mode.toLowerCase()} · synthesized across 14 lenses</span>
        </div>
        <button className="thx-ai-btn aix-btn mono" onClick={writeThesis} disabled={tAi === "loading"}>
          {tAi === "loading" ? "✦ thinking…" : "✦ Write the full thesis"}
        </button>
      </div>

      <div className="thx-line">{ticker.symbol} reads <b className={tone}>{bias}</b> for a {mode.toLowerCase()} hold — a <b>{ticker.setupFamily || "continuation"}</b> setup on a <b className={tone}>{net}/100</b> cross-lens score, into {erTxt}.</div>

      <div className="thx-cols">
        <div className="thx-col thx-col--bull">
          <div className="thx-col-h mono up">▲ WHY · THE CASE</div>
          {bulls.length ? bulls.map((b, i) => <Pt key={i} b={b} />)
            : <div className="thx-pt"><span className="thx-pt-d dim2">Composite {net}/100 with broad lens agreement.</span></div>}
        </div>
        <div className="thx-col thx-col--bear">
          <div className="thx-col-h mono dn">▼ WHY NOT · THE RISK</div>
          {bears.length ? bears.map((b, i) => <Pt key={i} b={b} />)
            : <div className="thx-pt"><span className="thx-pt-d dim2">No lens materially dissents — main risk is {erTxt} and the broad tape.</span></div>}
        </div>
      </div>

      <div className="thx-ref" style={{display:"none"}}>
        <span className="thx-ref-h mono dim2">FOR REFERENCE</span>
        <div className="thx-ref-grid">
          {ref.map((r, i) => <div key={i} className="thx-ref-cell"><span className="mono dim2">{r[0]}</span><span className="mono">{r[1]}</span></div>)}
        </div>
      </div>

      {tAi && tAi !== "loading" && (
        <div className="aix-out mono thx-aiout">
          <span className="aix-tag">✦ KAIROS THESIS</span>
          <span className="aix-txt">{tAi}</span>
        </div>
      )}

      <div className="thx-foot mono dim2">Click any lens above to verify a point. Informational / educational only — not advice.</div>
    </div>
  );
}
window.ThesisCard = ThesisCard;

// ─── News Catalyst classifier — LLM-structured headline reads ───
(function () {
  const css = `
  .nc { background:var(--glass-bg-1); border:1px solid var(--glass-line); border-radius:8px; padding:13px 15px; display:flex; flex-direction:column; gap:9px; margin-bottom:4px; }
  .nc-head { display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap; }
  .nc-head-l { display:flex; align-items:center; gap:9px; flex-wrap:wrap; }
  .nc-tag { font:700 9px var(--mono); letter-spacing:0.12em; color:var(--copper); border:1px solid color-mix(in oklab,var(--copper) 40%,transparent); border-radius:3px; padding:3px 8px; }
  .nc-sub { font-size:10.5px; }
  .nc-row { display:flex; align-items:center; gap:9px; padding:6px 8px; background:var(--glass-bg-2); border-radius:5px; border-left:2px solid var(--glass-line); }
  .nc-row--high { border-left-color:var(--gn); } .nc-row--med { border-left-color:var(--amb); } .nc-row--low { border-left-color:var(--ink-4); }
  .nc-time { flex:none; font:600 9.5px var(--mono); color:var(--ink-3); min-width:34px; }
  .nc-type { flex:none; font:700 8.5px var(--mono); letter-spacing:0.05em; padding:2px 6px; border-radius:3px; background:color-mix(in oklab,var(--cy) 14%,transparent); color:var(--cy); }
  .nc-mat { flex:none; font:700 8px var(--mono); letter-spacing:0.06em; }
  .nc-mat--high { color:var(--gn); } .nc-mat--med { color:var(--amb); } .nc-mat--low { color:var(--ink-3); }
  .nc-h { font-size:11.5px; color:var(--ink-2); line-height:1.4; }
  .nc-foot { font-size:9.5px; padding-top:5px; border-top:1px solid var(--glass-line); }`;
  if (!document.getElementById("nc-css")) { const s = document.createElement("style"); s.id = "nc-css"; s.textContent = css; document.head.appendChild(s); }
})();

function NewsCatalysts({ ticker }) {
  const [ai, setAi] = React.useState(null);
  const sec = ticker.sector || "sector";
  const heads = [
    { t: "08:42", h: `Analyst reiterates Buy on ${ticker.symbol}, raises price target`, type: "RATING", mat: "med", fresh: "first report" },
    { t: "06:15", h: `${sec} flows turn positive on macro print`, type: "MACRO", mat: "low", fresh: "follow-on" },
    { t: "Yest", h: `${sec} peer guides above consensus — read-through`, type: "GUIDANCE", mat: "high", fresh: "first report" },
    { t: "2d", h: `Insider cluster buy disclosed (Form 4)`, type: "INSIDER", mat: "high", fresh: "first report" },
  ];
  const classify = async () => {
    setAi("loading");
    const prompt = `You are a news catalyst classifier for a stock trader following ${ticker.symbol}. For EACH headline below, give one short line: catalyst type, how material it is (high/med/low), and whether it's tradeable now or already priced in. Be concise.\n` + heads.map(h => `- ${h.h}`).join("\n");
    const r = await window.aiComplete(prompt);
    setAi(r.text);
  };
  return (
    <div className="nc">
      <div className="nc-head">
        <div className="nc-head-l">
          <span className="nc-tag mono">NEWS CATALYSTS</span>
          <span className="nc-sub mono dim2">classified by type · materiality · freshness</span>
        </div>
        <button className="aix-btn mono" onClick={classify} disabled={ai === "loading"}>{ai === "loading" ? "✦ thinking…" : "✦ Classify catalysts"}</button>
      </div>
      {heads.map((n, i) => (
        <div key={i} className={`nc-row nc-row--${n.mat}`}>
          <span className="nc-time">{n.t}</span>
          <span className="nc-type">{n.type}</span>
          <span className={`nc-mat nc-mat--${n.mat}`}>{n.mat === "high" ? "MATERIAL" : n.mat === "med" ? "MODERATE" : "LOW"}</span>
          <span className="nc-h">{n.h} <span className="dim2">· {n.fresh}</span></span>
        </div>
      ))}
      {ai && ai !== "loading" && (
        <div className="aix-out mono" style={{ width: "100%" }}>
          <span className="aix-tag">✦ KAIROS · CATALYST READ</span>
          <span className="aix-txt">{ai}</span>
        </div>
      )}
      <div className="nc-foot mono dim2">Headlines from the news feed (EODHD in production) · type/materiality classified by the LLM. Informational only — not advice.</div>
    </div>
  );
}
window.NewsCatalysts = NewsCatalysts;

// ─── Entry Checklist — runs the buy funnel live as ✓/✗ rows ───
(function () {
  const css = `
  .bk { background:var(--glass-bg-1); border:1px solid var(--glass-line); border-radius:8px; padding:13px 15px; display:flex; flex-direction:column; gap:10px; margin-bottom:4px; }
  .bk-head { display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap; }
  .bk-head-l { display:flex; align-items:center; gap:9px; flex-wrap:wrap; }
  .bk-tag { font:700 9px var(--mono); letter-spacing:0.12em; color:var(--copper); border:1px solid color-mix(in oklab,var(--copper) 40%,transparent); border-radius:3px; padding:3px 8px; }
  .bk-score { font:700 13px var(--mono); }
  .bk-verdict { font:700 9px var(--mono); letter-spacing:0.08em; padding:3px 9px; border-radius:999px; border:1px solid currentColor; }
  .bk-bar { height:6px; border-radius:999px; background:var(--glass-bg-2); overflow:hidden; }
  .bk-bar i { display:block; height:100%; border-radius:999px; }
  .bk-rows { display:grid; grid-template-columns:1fr 1fr; gap:6px 14px; }
  .bk-row { display:flex; align-items:center; gap:8px; padding:5px 0; border-bottom:1px solid var(--glass-line); }
  .bk-ic { flex:none; width:17px; height:17px; border-radius:50%; display:inline-flex; align-items:center; justify-content:center; font:700 10px var(--mono); }
  .bk-ic--pass { background:color-mix(in oklab,var(--gn) 22%,transparent); color:var(--gn); }
  .bk-ic--fail { background:color-mix(in oklab,var(--rd) 18%,transparent); color:var(--rd); }
  .bk-k { flex:1; font-size:11.5px; color:var(--ink-1); }
  .bk-v { flex:none; font:600 11px var(--mono); }
  .bk-need { flex:none; font:500 9px var(--mono); color:var(--ink-3); min-width:54px; text-align:right; }
  .bk-foot { font-size:10px; padding-top:5px; border-top:1px solid var(--glass-line); }
  @media (max-width:680px){ .bk-rows{ grid-template-columns:1fr; } }`;
  if (!document.getElementById("bk-css")) { const s = document.createElement("style"); s.id = "bk-css"; s.textContent = css; document.head.appendChild(s); }
})();

function BuyChecklist({ ticker, mode }) {
  const cv = window.compositeVerdict ? window.compositeVerdict(ticker, mode) : null;
  const net = cv ? cv.net : (ticker.score || 60);
  const bias = window.secBias ? window.secBias(cv ? cv.verdict : ticker.verdict) : "—";
  const moKey = mode === "POSITION" ? "position" : mode === "INVESTMENT" ? "invest" : "swing";
  const proj = (window.AIPredict && ticker.symbol) ? window.AIPredict.projection(ticker.symbol, moKey) : null;
  const lensV = n => cv ? (cv.lenses.find(l => l.k === n || l.k.startsWith(n)) || {}).v : null;
  const ss = ticker.setupStats || {};
  const rr = ticker.rMultiple || 0;
  const erDays = ticker.earnings ? ticker.earnings.days : null;
  const hold = ticker.holdDays || 9;
  const checks = [
    { k: "Bias is Bullish", v: `${bias} ${net}`, need: "≥66", pass: net >= 66 },
    { k: "Lens confluence", v: cv ? `${cv.agree}/${cv.lenses.length}` : "—", need: "majority", pass: cv ? cv.agree >= Math.ceil(cv.lenses.length * 0.5) : false },
    { k: "Technicals aligned", v: lensV("Technicals") != null ? `${lensV("Technicals")}` : "—", need: "≥60", pass: (lensV("Technicals") || 0) >= 60 },
    { k: "Pattern / SMC", v: lensV("Patterns") != null ? `${lensV("Patterns")}` : "—", need: "≥60", pass: (lensV("Patterns") || 0) >= 60 },
    { k: "AI P(up)", v: proj ? `${Math.round(proj.pUp * 100)}%` : "—", need: "≥55%", pass: proj ? proj.pUp >= 0.55 : false },
    { k: "Setup edge", v: ss.wilsonLB ? `${(ss.wilsonLB * 100).toFixed(0)}% n${ss.n}` : "—", need: "LB≥45·n≥30", pass: (ss.wilsonLB || 0) >= 0.45 && (ss.n || 0) >= 30 },
    { k: "Reward : Risk", v: `${rr.toFixed(2)}R`, need: "≥2.0", pass: rr >= 2 },
    (mode === "INVESTMENT"
      ? { k: "Earnings (core event)", v: erDays != null ? `${erDays}d` : "none", need: "review", pass: true }
      : mode === "POSITION"
      ? { k: "Earnings (catalyst)", v: erDays != null ? `${erDays}d` : "none", need: "≤30d ok", pass: true }
      : { k: "Earnings clear", v: erDays != null ? `${erDays}d` : "none", need: ">7d", pass: erDays != null ? erDays > 7 : true }),
  ];
  const passed = checks.filter(c => c.pass).length, total = checks.length;
  const vtone = passed === total ? "gn" : passed >= total - 2 ? "amb" : "rd";
  const vlabel = passed === total ? "COMPLETE" : passed >= total - 2 ? "FORMING" : "INCOMPLETE";
  return (
    <div className="bk">
      <div className="bk-head">
        <div className="bk-head-l">
          <span className="bk-tag mono">ENTRY CHECKLIST</span>
          <span className={`bk-score kpi-tone--${vtone}`}>{passed}<span className="dim2">/{total}</span></span>
          <span className="mono dim2" style={{ fontSize: 10.5 }}>criteria met · the buy funnel, live</span>
        </div>
        <span className={`bk-verdict kpi-tone--${vtone}`}>{vlabel}</span>
      </div>
      <div className="bk-bar"><i style={{ width: `${passed / total * 100}%`, background: `var(--${vtone})` }} /></div>
      <div className="bk-rows">
        {checks.map((c, i) => (
          <div key={i} className="bk-row">
            <span className={`bk-ic bk-ic--${c.pass ? "pass" : "fail"}`}>{c.pass ? "✓" : "✕"}</span>
            <span className="bk-k">{c.k}</span>
            <span className={`bk-v kpi-tone--${c.pass ? "gn" : "rd"}`}>{c.v}</span>
            <span className="bk-need">{c.need}</span>
          </div>
        ))}
      </div>
      <div className="bk-foot mono dim2">{passed === total ? "All entry criteria met — the setup is complete." : `${total - passed} criterion${total - passed === 1 ? "" : "a"} not met — treat as a watch until they clear.`} Informational / educational only — not advice.</div>
    </div>
  );
}
window.BuyChecklist = BuyChecklist;

// per-ticker pre-mortem note — persisted to localStorage
function PreMortemNote({ symbol }) {
  const key = "premortem-" + (symbol || "x");
  const [val, setVal] = React.useState(() => { try { return localStorage.getItem(key) || ""; } catch (e) { return ""; } });
  return (
    <div className="pm-note-wrap">
      <div className="label-cap" style={{ marginBottom: 6 }}>Your pre-mortem · written before entry</div>
      <textarea className="pm-note mono" placeholder="If this trade fails, the most likely reason will be… (your own words — saved per ticker)"
        value={val} onChange={e => { setVal(e.target.value); try { localStorage.setItem(key, e.target.value); } catch (e2) {} }} />
    </div>
  );
}

// ─── OvSection — collapsible Overview section (persists open/closed) ───
function OvSection({ n, title, sub, headerStyle, defaultOpen = true, teaser, children }) {
  const key = "ovsecv5-" + n;
  const [open, setOpen] = React.useState(() => { try { const v = localStorage.getItem(key); return v == null ? defaultOpen : v === "1"; } catch (e) { return defaultOpen; } });
  React.useEffect(() => {
    const h = (e) => { if (e.detail === n - 1) setOpen(true); };
    window.addEventListener("ov-jump-open", h);
    return () => window.removeEventListener("ov-jump-open", h);
  }, [n]);
  const toggle = () => setOpen(o => { const nx = !o; try { localStorage.setItem(key, nx ? "1" : "0"); } catch (e) {} return nx; });
  return (
    <div className={`lens-section ov-sec ${open ? "is-open" : "is-closed"}`}>
      <div className="ov-sec-head" onClick={toggle} role="button" tabIndex={0}
        onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } }}>
        <SectionHeader n={n} title={title} sub={sub} style={headerStyle}
          right={<span className={`ov-sec-chev mono ${open ? "is-open" : ""}`}>▸</span>} />
      </div>
      {open
        ? <div className="lens-pad">{children}</div>
        : <button className="ov-sec-teaser mono" onClick={toggle}>{teaser || `Show ${(title || "").split(" · ")[0]}`} <span className="copper">· expand</span></button>}
    </div>
  );
}
window.OvSection = OvSection;

function LensOverview({ ticker: t0, mode, sizeCat, headerStyle, kpiStyle, heroStyle }) {
  const ticker = (window.modeAdjust ? window.modeAdjust(t0, mode) : t0);

  // route a lens name → lens id, used by the hero dissent pills + confluence grid
  const routeLens = (name) => {
    const map = { "Overview": "overview", "AI Edge": "mledge", "Technicals": "technicals", "Patterns": "patterns", "SMC": "smc", "Value": "investment", "Risk": "risk", "Track Rec.": "mledge", "Plan": "plan", "Earnings": "earnings", "Options": "options", "Insider": "tape", "Tape": "tape", "Chart": "chart", "Portfolio": "tape" };
    if (window.__setLens && map[name]) window.__setLens(map[name]);
  };

  return (
    <div className="lens lens--ov">

      {/* ── THE ANSWER · verdict + edge + the trade, one canonical block ── */}
      {window.DecisionHero && <DecisionHero ticker={ticker} mode={mode} heroStyle={heroStyle} sizeCat={sizeCat} onLens={routeLens} />}

      {/* ── SURFACED BY · which discovery engines flagged this name ── */}
      <SurfacedBy ticker={ticker} />

      {/* ── HORIZON STRIP · swing / position / investment verdicts side-by-side ── */}
      <HorizonStrip ticker={ticker} mode={mode} onMode={(m) => window.__setMode && window.__setMode(m)} />

      {/* ── 1 · COMPANY & CATALYSTS · context first (full width, above the analysis) ── */}
      <OvSection n={1} title="Company & Catalysts · Context"
        sub="who they are · valuation · earnings · what's hitting the tape"
        headerStyle={headerStyle} defaultOpen={true}
        teaser="Profile · valuation vs peers · earnings in 11d · 4 classified catalysts">
        <div className="ov-co2x2">
          <CompanySnapshot ticker={ticker} />
          <CompanyValuation ticker={ticker} />
          <NewsCatalysts ticker={ticker} />
        </div>
      </OvSection>

      {/* ── 2 · ENTRY READINESS · the buy funnel, live ── */}
      <OvSection n={2} title="Entry Readiness · Are We Cleared?"
        sub="the buy funnel as ✓/✗ · plus the full rule-engine audit" headerStyle={headerStyle}>
        <BuyChecklist ticker={ticker} mode={mode} />
        {(window.__tier ?? 4) >= 3 && (
          <details className="ov-more">
            <summary className="ov-more-sum mono">Show the full 10-gate rule-engine audit · how 612 ranked → {window.secBias ? window.secBias((window.compositeVerdict ? window.compositeVerdict(ticker, mode).verdict : "BUY")) : "Bullish"} · PRO+</summary>
            <div className="ov-more-body"><GateCascade /></div>
          </details>
        )}
      </OvSection>

      {/* ── 3 · LENS CONFLUENCE · the ONE evidence grid + launchpad ── */}
      <OvSection n={3} title="Lens Confluence · The Evidence"
        sub="every discipline's read · click any tile to open that lens" headerStyle={headerStyle}>
        <ConfluenceHeatmap />
      </OvSection>

      {/* ── 4 · THE CASE · bull vs bear, synthesized once ── */}
      <OvSection n={4} title="The Case · Bull vs Bear"
        sub="why it's a buy — and what would make it wrong" headerStyle={headerStyle}>
        <ThesisCard ticker={ticker} mode={mode} />
      </OvSection>

      {/* ── 5 · KEEP ME HONEST · pre-mortem | what-changed | why-edge ── */}
      <OvSection n={5} title="Keep Me Honest"
        sub="what would break the thesis · what moved in 24h · why the edge exists"
        headerStyle={headerStyle} defaultOpen={true}
        teaser="4 pre-mortem triggers · your note · 6 24h deltas · sleeve mechanism">
        <div className="ov-honest-3col">
        <div className="ov-honest-block">
        <div className="ov-honest-sub label-cap">▼ What would make this wrong · pre-mortem</div>
        <div className="premortem">
          <div className="premortem-row"><span className="pm-num mono">1</span><span className="pm-text">Loses VWAP intraday AND closes below ${(window.coherentLevels ? window.coherentLevels(ticker).pivot * 0.9837 : ticker.pivot * 0.9837).toFixed(2)} — invalidation cascade.</span><Pill tone="rd" small>HARD</Pill></div>
          {(mode === "INVESTMENT"
            ? [["2", "ROIC falls below WACC — capital destruction.", "FUNDAMENTAL", "rd"], ["3", "Operating cash flow diverges below reported EPS — accrual risk.", "QUALITY", "amb"], ["4", "Price exceeds 90% of DCF fair value — margin of safety gone.", "VALUATION", "amb"]]
            : mode === "POSITION"
            ? [["2", "Sector RS rank drops below 50th pct for 2 weeks — leadership lost.", "MACRO", "rd"], ["3", "Regime flips to Risk-Off Trending — thesis backdrop gone.", "MACRO", "amb"], ["4", "13F shows institutions distributing — smart money exits.", "FUNDAMENTAL", "rd"]]
            : [["2", "Sector ETF (XLB) breaks 50-DMA on +1.5σ volume — regime flip.", "MEDIUM", "amb"], ["3", "CPI prints >0.4% MoM next Wed — risk-off reset.", "MACRO", "amb"], ["4", "Top-2 customer (31% of revenue) cuts guidance on Q1 call.", "FUNDAMENTAL", "rd"]]
          ).map(([n, t, tag, tone]) => (
            <div key={n} className="premortem-row"><span className="pm-num mono">{n}</span><span className="pm-text">{t}</span><Pill tone={tone} small>{tag}</Pill></div>
          ))}
        </div>
        <PreMortemNote symbol={ticker.symbol} />
        </div>

          <div className="ov-honest-block">
            <div className="ov-honest-sub label-cap">↗ What changed · last 24h</div>
            <WhatChanged />
          </div>
          <div className="ov-honest-block">
            <div className="ov-honest-sub label-cap">⚙ Why the edge exists · mechanism</div>
            <SleeveAttribution ticker={ticker} />
          </div>
        </div>
      </OvSection>

      <div className="lens-call">
        <span className="label-cap">The Read · {mode}</span>
        <span className="mono">
          A breakout above <b className="copper">${(window.coherentLevels ? window.coherentLevels(ticker).pivot : ticker.pivot).toFixed(2)}</b> confirms the setup ·
          half-Kelly sizing reference · 9 of 10 gates pass · Wilson LB <b className="up">47.7%</b> · expectancy <b className="up">+0.51R</b> ·
          <b className="warn"> size −25% into ER.</b>
        </span>
      </div>
    </div>
  );
}

function ConfluenceHeatmap() {
  const cells = [
    { lens: "Overview", v: "Bullish", tone: "gn",  note: "score 78" },
    { lens: "Plan",     v: "READY",   tone: "gn",  note: "R 1.74" },
    { lens: "Chart",    v: "TREND+",  tone: "gn",  note: "stacked-bull" },
    { lens: "Technicals",v:"PASS",    tone: "gn",  note: "RSI 64" },
    { lens: "Patterns", v: "VCP·B2",  tone: "gn",  note: "conf 74%" },
    { lens: "SMC",      v: "OB+BoS",  tone: "gn",  note: "spring held" },
    { lens: "Value",    v: "MARG.",   tone: "amb", note: "MoS 6%" },
    { lens: "Risk",     v: "OK",      tone: "gn",  note: "VaR −2.1%" },
    { lens: "Earnings", v: "11d",     tone: "amb", note: "event risk pre-ER" },
    { lens: "Options",  v: "RICH",    tone: "amb", note: "IV/HV 1.42" },
    { lens: "Portfolio",v: "FIT",     tone: "gn",  note: "correl 0.34" },
    { lens: "Tape",     v: "+12 INS", tone: "gn",  note: "rising sent." },
    { lens: "Track Rec.",v:"EDGE",    tone: "gn",  note: "Wilson 47.7" },
    { lens: "AI Edge",  v: "+0.18",   tone: "gn",  note: "hit-net pos." },
  ];
  return (
    <div className="conf-grid">
      {cells.map((c, i) => {
        const map = { "Overview": "overview", "Plan": "plan", "Chart": "chart", "Technicals": "technicals", "Patterns": "patterns", "SMC": "smc", "Value": "investment", "Risk": "risk", "Earnings": "earnings", "Options": "options", "Portfolio": "tape", "Tape": "tape", "Track Rec.": "mledge", "AI Edge": "mledge" };
        const go = () => { if (window.__setLens && map[c.lens]) window.__setLens(map[c.lens]); };
        return (
          <button key={i} className={`conf-cell conf-${c.tone}`} onClick={go} title={`open ${c.lens}`}>
            <div className="conf-lens mono">{c.lens}</div>
            <div className={`conf-v mono kpi-tone--${c.tone}`}>{c.v}</div>
            <div className="conf-note mono dim2">{c.note}</div>
          </button>
        );
      })}
      <div className="conf-summary">
        <Pill tone="gn" dot>10 PASS</Pill>
        <Pill tone="amb" small>3 CAUTION</Pill>
        <Pill tone="rd" small>0 FAIL</Pill>
        <span className="mono dim2" style={{ marginLeft: 12 }}>
          Disagreement score: <b className="warn">low</b> — clean confluence; act on the bracket.
        </span>
      </div>
    </div>
  );
}

function SleeveAttribution({ ticker }) {
  return (
    <div className="sleeve">
      <div className="sleeve-row">
        <span className="sleeve-lbl mono">SLEEVE</span>
        <div><Pill tone="copper">CONTINUATION BREAKOUT · base #2</Pill> <span className="mono dim2">· 2 of 11 active sleeves · 12% of current book</span></div>
      </div>
      <div className="sleeve-row">
        <span className="sleeve-lbl mono">MECHANISM</span>
        <span className="mono">
          Post-base breakout on dry-volume pullback. <b className="copper">Alpha source:</b> liquidity withdrawal then demand absorption at pivot.
          <b className="copper"> Why it works:</b> regime where institutional accumulation is observable but not yet priced.
        </span>
      </div>
      <div className="sleeve-row">
        <span className="sleeve-lbl mono">WILSON</span>
        <WilsonPill n={47} winRate={0.617} lb={0.477} />
      </div>
      <div className="sleeve-row">
        <span className="sleeve-lbl mono">LAST 5</span>
        <div className="sleeve-recent">
          {[
            { sym: "ARGN", date: "Apr 22", out: "+1.84R", tone: "gn" },
            { sym: "BORA", date: "Apr 04", out: "+0.72R", tone: "gn" },
            { sym: "VLCT", date: "Mar 18", out: "−1.0R",  tone: "rd" },
            { sym: "ZOTR", date: "Feb 27", out: "+2.10R", tone: "gn" },
            { sym: "NVRH", date: "Feb 06", out: "+0.41R", tone: "amb" },
          ].map((s, i) => (
            <div key={i} className="sleeve-rec">
              <span className="mono"><b>{s.sym}</b></span>
              <span className="mono dim2">{s.date}</span>
              <span className={`mono kpi-tone--${s.tone}`}>{s.out}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function GateCascade() {
  const gates = [
    { n: 1, label: "Universe · mcap ≥ $100M · ADV ≥ 500k",       v: "612 / 1402", tone: "gn" },
    { n: 2, label: "Liquidity · spread ≤ 10bp · L1 ≥ 1000",      v: "PASS",       tone: "gn" },
    { n: 3, label: "Trend · close > 50-DMA · 200-DMA rising",    v: "PASS",       tone: "gn" },
    { n: 4, label: "Setup detected · pattern conf ≥ 0.60",       v: "VCP 0.74",   tone: "gn" },
    { n: 5, label: "Wilson LB ≥ 45% · per setup family",         v: "47.7%",      tone: "gn" },
    { n: 6, label: "R-multiple ≥ 1.5 · entry/stop/T1 valid",     v: "1.74R",      tone: "gn" },
    { n: 7, label: "Risk · max loss ≤ 0.75% NAV",                v: "0.39%",      tone: "gn" },
    { n: 8, label: "Correl-to-book ≤ 0.55",                      v: "0.34",       tone: "gn" },
    { n: 9, label: "ER not in T1 window (T+14d > ER date)",      v: "ER in 11d",  tone: "amb", warn: true },
    { n: 10,label: "ML hit-net ≥ +0.05",                         v: "+0.18",      tone: "gn" },
  ];
  return (
    <div className="gates">
      {gates.map(g => (
        <div key={g.n} className={`gate-row gate-${g.tone}`}>
          <span className="gate-n mono">{String(g.n).padStart(2,"0")}</span>
          <span className="gate-mark mono">{g.warn ? "!" : "✓"}</span>
          <span className="gate-lbl">{g.label}</span>
          <span className={`gate-result mono kpi-tone--${g.tone}`}>{g.v}</span>
        </div>
      ))}
      <div className="gates-summary mono">
        <b className="up">9 of 10 gates pass · 1 caution (ER in window).</b> Recommendation: take bracket with <b>25% size cut</b> + full exit T−2 sessions pre-ER unless thesis confirms.
      </div>
    </div>
  );
}

function MacroDrill() {
  return (
    <div className="kpi-row" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
      <KpiTile label="Regime · MULTI-FACTOR" value="BULL · LOW-VIX" tone="gn" sub="highest WR regime · 71% historical" />
      <KpiTile label="XLB · 50-DMA"          value="+3.4%"          tone="gn" sub="rising · sector tailwind" />
      <KpiTile label="VIX percentile 1y"     value="32%"            tone="gn" sub="below median · risk-on" />
      <KpiTile label="US10Y · 5d delta"      value="−14bp"          tone="gn" sub="rates easing · duration friendly" />
      <KpiTile label="Breadth · A/D NYSE"    value="1.84"           tone="gn" sub="participation broad" />
      <KpiTile label="HY spread · 5d"        value="−6bp"           tone="gn" sub="risk appetite holding" />
    </div>
  );
}

function WhatChanged() {
  const items = [
    { label: "Composite score",           old: "74",   now: "78",   tone: "gn",  note: "+4 · drove Bullish shift" },
    { label: "Technical pillar",          old: "78",   now: "82",   tone: "gn",  note: "MACD+ · VWAP reclaim" },
    { label: "Catalyst pillar",           old: "62",   now: "58",   tone: "amb", note: "−4 · ER proximity weight" },
    { label: "ML hit-net",                old: "0.14", now: "0.18", tone: "gn",  note: "+4pt edge improvement" },
    { label: "Insider activity (90d net)",old: "+8",   now: "+12",  tone: "gn",  note: "CFO + COO buys May 18-22" },
    { label: "Sector ETF (XLB)",          old: "+0.6%",now: "+1.2%",tone: "gn",  note: "sector confirming" },
  ];
  return (
    <div className="wc">
      {items.map((it, i) => (
        <div key={i} className="wc-row">
          <span className="mono wc-lbl">{it.label}</span>
          <span className="mono dim2 wc-old">{it.old}</span>
          <span className="mono dim">→</span>
          <span className={`mono wc-new kpi-tone--${it.tone}`}><b>{it.now}</b></span>
          <span className="mono dim wc-note">{it.note}</span>
        </div>
      ))}
    </div>
  );
}

function StressSnapshot() {
  const scenarios = [
    { name: "VIX spike +8",       pnl: "−$680",   pct: "−0.63% NAV", action: "Cut 50%",    tone: "amb" },
    { name: "Sector rotation −5%",pnl: "−$520",   pct: "−0.48% NAV", action: "Trim 25%",   tone: "amb" },
    { name: "Earnings gap −15%",  pnl: "−$420",   pct: "−0.39% NAV", action: "OCO exit",   tone: "rd"  },
    { name: "Macro shock (CPI)",  pnl: "−$610",   pct: "−0.56% NAV", action: "Reduce 50%", tone: "amb" },
    { name: "Sector kill",        pnl: "−$890",   pct: "−0.82% NAV", action: "Flatten",    tone: "rd"  },
    { name: "Liquidity dry-up",   pnl: "−$340",   pct: "−0.31% NAV", action: "Hold · wide",tone: "ink" },
  ];
  return (
    <div className="kpi-row" style={{ gridTemplateColumns: "repeat(6, 1fr)" }}>
      {scenarios.map((s, i) => (
        <KpiTile key={i} label={s.name} value={s.pnl} tone={s.tone} sub={`${s.pct} · ${s.action}`} />
      ))}
    </div>
  );
}

// Override the in-file LensOverview from detail-panel.jsx
window.LensOverview = LensOverview;

// ─── Desk Read — how a 20-yr quant scans it in 2 seconds ────────
function DeskRead({ ticker, mode }) {
  const entry = ticker.pivot * 1.002;
  const risk = entry - ticker.stop;
  const reward = ticker.t1 - entry;
  const wr = 0.617, lb = 0.477;
  // expectancy in R: p*win − q*loss (loss capped at 1R)
  const evR = (wr * (reward / risk) - (1 - wr) * 1).toFixed(2);
  return (
    <div className="dr">
      <div className="dr-metrics">
        <DrCell label="EXPECTANCY" value={`+${evR}R`} tone="gn" tip="p·b − q · per unit risk" />
        <DrCell label="EDGE · WILSON LB" value={`${(lb*100).toFixed(0)}%`} tone="gn" tip="95% lower bound · n=47" />
        <DrCell label="DOWNSIDE" value="−$420" tone="rd" tip="0.39% NAV · hard stop" />
        <DrCell label="R:R" value={`${(reward/risk).toFixed(2)}`} tone="copper" tip="reward ÷ risk to T1" />
        <DrCell label="CORREL → BOOK" value="0.34" tone="gn" tip="cap 0.55 · adds cleanly" />
        <DrCell label="LIQUIDITY" value="A" tone="gn" tip="2 bp spread · 1.12M ADV" />
        <DrCell label="REGIME FIT" value="71%" tone="gn" tip="setup WR in current regime" />
        <DrCell label="TIME RISK" value="ER 11d" tone="amb" tip="event risk into the print" />
      </div>

      <div className="dr-call mono">
        <span className="dr-call-tag">DESK READ</span>
        <span className="dr-call-txt">
          Clean continuation BO with a real, sample-validated edge (LB 48%, +{evR}R expectancy).
          Downside bounded at 0.39% NAV, adds at 0.34 correl, fits the bull/low-VIX regime where this
          setup wins 71%. <b className="warn">One caveat:</b> ER in 11d — historically this setup is sized −25% and flattened T−2 when unconfirmed.
          <b className="copper"> Ticket is pre-filled for your review.</b>
        </span>
      </div>
    </div>
  );
}

function DrCell({ label, value, tone, tip }) {
  return (
    <div className={`dr-cell dr-cell--${tone}`} title={tip}>
      <div className="dr-cell-l mono">{label}</div>
      <div className={`dr-cell-v mono kpi-tone--${tone}`}>{value}</div>
    </div>
  );
}

// ─── Company Snapshot · Quant Read ──────────────────────────
function CompanySnapshot({ ticker }) {
  return (
    <React.Fragment>
      <div className="cs-card cs-card--who">
        <div className="cs-card-hdr">
          <div className="label-cap">WHO · {ticker.symbol}</div>
          <span className="mono dim2">{ticker.exchange} · {ticker.sector} · {ticker.industry}</span>
        </div>
        <div className="cs-name mono">{ticker.name}</div>
        <div className="cs-blurb mono dim">
          Mid-cap specialty-materials operator · 70% specialty coatings / 30% adjacent chemicals ·
          top-2 customers = 31% of revenue · Akron capacity expansion ships H2 (+18% volume).
        </div>
        <div className="cs-meta">
          <span className="cs-chip mono"><span className="dim2">mcap</span> <b>${(ticker.mcap/1e9).toFixed(2)}B</b></span>
          <span className="cs-chip mono"><span className="dim2">β</span> <b>{ticker.beta.toFixed(2)}</b></span>
          <span className="cs-chip mono"><span className="dim2">float</span> <b>76.4M</b></span>
          <span className="cs-chip mono"><span className="dim2">short</span> <b>{ticker.shortFloat.toFixed(1)}%</b></span>
          <span className="cs-chip mono"><span className="dim2">insider own</span> <b>{ticker.insiderOwn.toFixed(1)}%</b></span>
          <span className="cs-chip mono"><span className="dim2">ADV 20d</span> <b>{(ticker.avgVol/1e6).toFixed(2)}M sh</b></span>
          <span className="cs-chip mono"><span className="dim2">spread</span> <b className="up">2 bp</b></span>
          <span className="cs-chip mono"><span className="dim2">opt OI</span> <b>48k</b></span>
        </div>
      </div>

      <div className="cs-card cs-card--er">
        <div className="cs-card-hdr">
          <div className="label-cap">EARNINGS · NEXT CATALYST</div>
          <Pill tone="amb" small>T−{ticker.earnings.days}d</Pill>
        </div>
        <div className="cs-er-big">
          <div className="cs-er-num mono">{ticker.earnings.days}</div>
          <div className="cs-er-meta">
            <div className="mono dim2">days to print</div>
            <div className="mono"><b>{ticker.earnings.date}</b> · BMO · Wed</div>
          </div>
        </div>
        <div className="cs-er-tiles">
          <div className="cs-er-tile">
            <span className="label-cap">ESP</span>
            <span className="mono up"><b>+4.1%</b></span>
          </div>
          <div className="cs-er-tile">
            <span className="label-cap">EPS est.</span>
            <span className="mono"><b>$0.97</b></span>
          </div>
          <div className="cs-er-tile">
            <span className="label-cap">Beat rate</span>
            <span className="mono up"><b>6 / 8 Q</b></span>
          </div>
          <div className="cs-er-tile">
            <span className="label-cap">Implied move</span>
            <span className="mono warn"><b>±6.4%</b></span>
          </div>
        </div>
        <div className="cs-er-history mono">
          <span className="dim2">last 8Q:</span>
          {[+5.2,+3.1,-6.2,+2.4,+0.6,+2.8,-1.4,+3.9].map((r, i) => (
            <span key={i} className={r >= 0 ? "up" : "dn"}>{r >= 0 ? "▲" : "▼"}{Math.abs(r).toFixed(1)}</span>
          ))}
        </div>
      </div>
    </React.Fragment>
  );
}

// Valuation card pulled out so §4 can show it beside News in a 2-col row.
function CompanyValuation({ ticker }) {
  return (
      <div className="cs-card cs-card--val">
        <div className="cs-card-hdr">
          <div className="label-cap">VALUATION · QUALITY</div>
          <Pill tone="amb" small>MoS 6%</Pill>
        </div>
        <div className="cs-val-row">
          <div className="cs-val-tile">
            <span className="label-cap">P/E TTM</span>
            <span className="mono"><b>{ticker.pe.toFixed(1)}</b></span>
            <span className="mono dim2">peers 24.1</span>
          </div>
          <div className="cs-val-tile">
            <span className="label-cap">Fwd P/E</span>
            <span className="mono up"><b>{ticker.fwdPe.toFixed(1)}</b></span>
            <span className="mono dim2">peers 21.0</span>
          </div>
          <div className="cs-val-tile">
            <span className="label-cap">P/S TTM</span>
            <span className="mono"><b>4.6</b></span>
            <span className="mono dim2">peers 5.2</span>
          </div>
          <div className="cs-val-tile">
            <span className="label-cap">EV/EBITDA</span>
            <span className="mono up"><b>14.8</b></span>
            <span className="mono dim2">peers 17.4</span>
          </div>
        </div>
        <div className="cs-val-row">
          <div className="cs-val-tile">
            <span className="label-cap">ROIC 5y</span>
            <span className="mono up"><b>18.2%</b></span>
            <span className="mono dim2">A · top quartile</span>
          </div>
          <div className="cs-val-tile">
            <span className="label-cap">Op margin</span>
            <span className="mono up"><b>16.4%</b></span>
            <span className="mono dim2">stable 3Q</span>
          </div>
          <div className="cs-val-tile">
            <span className="label-cap">Net debt/EBITDA</span>
            <span className="mono up"><b>0.81×</b></span>
            <span className="mono dim2">low leverage</span>
          </div>
          <div className="cs-val-tile">
            <span className="label-cap">FCF yield</span>
            <span className="mono up"><b>4.8%</b></span>
            <span className="mono dim2">vs UST 4.32%</span>
          </div>
        </div>
      </div>
  );
}
window.CompanyValuation = CompanyValuation;

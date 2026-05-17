// subtabs/technicals/chart.js — 10-section Technicals lens (risk-redesign aesthetic).
// Redesigned 2026-05-17 to match cache/technicals_redesign_prototype.html.
//
// Sections:
//   HERO   — banner + chart preview + 3 indicator gauges + structural levels matrix
//   §1     — Indicator Dashboard (RSI / MACD / Stoch / ADX / MFI / CMF)
//   §2     — EMA / SMA stack
//   §3     — Pattern + Signal detection (bullish vs bearish)
//   §4     — S/R confluence ladder
//   §5     — Volume analytics (regime + institutional fingerprint)
//   §6     — Statistical Backbone — Wilson LB on this setup
//   §7     — Cross-Source Confluence — 6 lenses
//   §8     — Regime-Conditional Edge — same setup, 4 regimes
//   §9     — Pre-Mortem · falsification criteria
//   §10    — Sizing + Mechanical Exit Discipline
//
// Data sources (no stale data — every section shows freshness pill):
//   T (ticker bundle)               — current scan (≤4h fresh, run_daily_scan every 4 scans/day)
//   /v2/setup_stats.json            — Wilson CI per-setup, refreshed on morning scan
//   /v2/ml_edge_predictions.json    — ML lens for §7, refreshed every scan
//   T.live_quote_* (kairos poll)    — intraday price (≤30s stale during market hours)

const _T = () => (window.__getDetailTicker ? window.__getDetailTicker() : window.T);

let _setupStatsCache = null;
let _mlEdgeCache = null;

async function _fetchSetupStats() {
  if (_setupStatsCache && !(_setupStatsCache._meta || {}).error) return _setupStatsCache;
  try {
    const r = await fetch('/v2/setup_stats.json', { cache: 'no-store' });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    _setupStatsCache = await r.json();
  } catch (e) {
    _setupStatsCache = { _meta: { error: String(e) }, setups: {} };
  }
  return _setupStatsCache;
}

async function _fetchMlEdge() {
  if (window.__mlEdgeCache && !(window.__mlEdgeCache._meta || {}).error) return window.__mlEdgeCache;
  if (_mlEdgeCache && !(_mlEdgeCache._meta || {}).error) return _mlEdgeCache;
  try {
    const r = await fetch('/v2/ml_edge_predictions.json', { cache: 'no-store' });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    _mlEdgeCache = await r.json();
    window.__mlEdgeCache = _mlEdgeCache;
  } catch (e) {
    _mlEdgeCache = { _meta: { error: String(e) }, predictions: {} };
  }
  return _mlEdgeCache;
}

// ── Style injection (rk-* aesthetic, scoped under .rk-tech-scope) ──────────
function _ensureStyles() {
  if (document.getElementById('tech-rk-styles')) return;
  const s = document.createElement('style');
  s.id = 'tech-rk-styles';
  s.textContent = _RK_STYLES;
  document.head.appendChild(s);
}

const _RK_STYLES = `
.rk-tech-scope {
  /* DARK defaults */
  --bg:#0a0d0c; --bg-1:#11151a; --bg-2:#161a1e; --bg-3:#1c2125;
  --line:#262b2d; --line-2:#353a3c;
  --ink:#ecefe9; --ink-1:#d4d8d1; --ink-2:#9a9e98; --ink-3:#686c68; --ink-4:#444947;
  --gn:#4ade80; --gn-dim:#166534; --gn-bg:rgba(74,222,128,0.10);
  --rd:#f87171; --rd-dim:#991b1b; --rd-bg:rgba(248,113,113,0.10);
  --amb:#fbbf24; --amb-dim:#92400e; --amb-bg:rgba(251,191,36,0.10);
  --info:#60a5fa; --info-dim:#1e40af; --info-bg:rgba(96,165,250,0.10);
  --violet:#a78bfa; --violet-dim:#5b21b6; --violet-bg:rgba(167,139,250,0.10);
  --copper:#d97757; --copper-bg:rgba(217,119,87,0.10);
  --cyan:#5ec8d8; --cyan-dim:#155e75; --cyan-bg:rgba(94,200,216,0.10);
  --mono:'JetBrains Mono',ui-monospace,monospace;
  background: var(--bg); color: var(--ink); padding: 18px 4px; font-variant-numeric: tabular-nums;
}
/* LIGHT-mode overrides — inherits from body.light (the page-level theme toggle) */
body.light .rk-tech-scope {
  --bg:#f8f9f8; --bg-1:#f2f3f1; --bg-2:#e9ece8; --bg-3:#e0e3de;
  --line:#d0d4cd; --line-2:#c4c8c1;
  --ink:#181c17; --ink-1:#363a34; --ink-2:#565b53; --ink-3:#787d74; --ink-4:#a0a59c;
  --gn:#1a7a38; --gn-dim:#aedcbc; --gn-bg:rgba(26,122,56,0.09);
  --rd:#c0321e; --rd-dim:#f5b5ae; --rd-bg:rgba(192,50,30,0.07);
  --amb:#9b5c00; --amb-dim:#f5d9a8; --amb-bg:rgba(155,92,0,0.08);
  --info:#1d4ed8; --info-dim:#bfdbfe; --info-bg:rgba(29,78,216,0.08);
  --violet:#6d28d9; --violet-dim:#ddd6fe; --violet-bg:rgba(109,40,217,0.08);
  --copper:#b05a3a; --copper-bg:rgba(176,90,58,0.10);
  --cyan:#0e7490; --cyan-dim:#a5f3fc; --cyan-bg:rgba(14,116,144,0.09);
}
.rk-tech-scope .bc { font: 700 11px var(--mono); color: var(--ink-3); letter-spacing: 0.18em; text-transform: uppercase; margin: 0 4px 14px; }
.rk-tech-scope .bc b { color: var(--ink-1); }
.rk-tech-scope .bc .copper { color: var(--copper); }
.rk-tech-scope .bc .gn { color: var(--gn); }
.rk-tech-scope .bc .am { color: var(--amb); }
.rk-tech-scope .bc .rd { color: var(--rd); }

.rk-tech-scope .rk-hero { background: var(--bg-1); border: 1px solid var(--gn-dim); border-left: 4px solid var(--gn); border-radius: 2px; margin-bottom: 14px; overflow: hidden; font-family: var(--mono); }
.rk-tech-scope .rk-hero.bear { border-color: var(--rd-dim); border-left-color: var(--rd); }
.rk-tech-scope .rk-hero.neu  { border-color: var(--amb-dim); border-left-color: var(--amb); }
.rk-tech-scope .rk-hero-banner { display: flex; align-items: center; gap: 14px; padding: 10px 18px; background: var(--gn-bg); border-bottom: 1px solid var(--gn-dim); flex-wrap: wrap; }
.rk-tech-scope .rk-hero.bear .rk-hero-banner { background: var(--rd-bg); border-bottom-color: var(--rd-dim); }
.rk-tech-scope .rk-hero.neu  .rk-hero-banner { background: var(--amb-bg); border-bottom-color: var(--amb-dim); }
.rk-tech-scope .rk-hero-badge { font: 800 14px var(--mono); letter-spacing: 0.14em; padding: 4px 12px; border-radius: 2px; color: var(--gn); border: 1px solid var(--gn-dim); background: rgba(74,222,128,0.06); }
.rk-tech-scope .rk-hero.bear .rk-hero-badge { color: var(--rd); border-color: var(--rd-dim); background: rgba(248,113,113,0.06); }
.rk-tech-scope .rk-hero.neu  .rk-hero-badge { color: var(--amb); border-color: var(--amb-dim); background: rgba(251,191,36,0.06); }
.rk-tech-scope .rk-hero-q { font: 600 12px var(--mono); color: var(--ink-1); letter-spacing: 0.04em; flex: 1; min-width: 240px; }
.rk-tech-scope .rk-hero-q b { color: var(--ink); }
.rk-tech-scope .rk-hero-q .copper { color: var(--copper); }
.rk-tech-scope .rk-hero-tk { margin-left: auto; font: 800 16px var(--mono); color: var(--ink); letter-spacing: 0.06em; }
.rk-tech-scope .rk-hero-tk small { font-size: 10px; color: var(--ink-3); margin-left: 6px; letter-spacing: 0.10em; }
.rk-tech-scope .rk-hero-body { display: grid; grid-template-columns: 1.6fr 1.2fr 1fr; gap: 0; }
@media (max-width:980px) { .rk-tech-scope .rk-hero-body { grid-template-columns: 1fr; } }
.rk-tech-scope .rk-hero-chart { padding: 14px 18px; border-right: 1px solid var(--line); }
.rk-tech-scope .rk-hero-chart-h { font: 700 10px var(--mono); color: var(--ink-3); letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 6px; display: flex; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.rk-tech-scope .rk-hero-chart-h .legend { color: var(--ink-2); font-weight: 500; }
.rk-tech-scope .rk-hero-chart-h .legend i { display: inline-block; width: 8px; height: 8px; margin-right: 4px; vertical-align: middle; border-radius: 1px; }
.rk-tech-scope .rk-hero-chart svg { width: 100%; height: 220px; display: block; }
.rk-tech-scope .rk-hero-gauges { padding: 14px 14px; border-right: 1px solid var(--line); display: grid; grid-template-rows: auto 1fr; }
.rk-tech-scope .rk-hero-gauges-h { font: 700 10px var(--mono); color: var(--ink-3); letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 10px; }
.rk-tech-scope .rk-hero-gauges-grid { display: grid; grid-template-columns: 1fr; gap: 8px; }
.rk-tech-scope .rk-gauge { border: 1px solid var(--line); border-radius: 2px; padding: 9px 12px; background: var(--bg-2); }
.rk-tech-scope .rk-gauge.mom { border-color: var(--info-dim); background: rgba(96,165,250,0.04); }
.rk-tech-scope .rk-gauge.trd { border-color: var(--gn-dim); background: rgba(74,222,128,0.04); }
.rk-tech-scope .rk-gauge.vol { border-color: var(--violet-dim); background: rgba(167,139,250,0.04); }
.rk-tech-scope .rk-gauge-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 4px; }
.rk-tech-scope .rk-gauge-k { font: 700 9px var(--mono); color: var(--ink-3); letter-spacing: 0.12em; text-transform: uppercase; }
.rk-tech-scope .rk-gauge.mom .rk-gauge-k { color: var(--info); }
.rk-tech-scope .rk-gauge.trd .rk-gauge-k { color: var(--gn); }
.rk-tech-scope .rk-gauge.vol .rk-gauge-k { color: var(--violet); }
.rk-tech-scope .rk-gauge-status { font: 700 8.5px var(--mono); letter-spacing: 0.10em; padding: 1px 6px; border-radius: 2px; }
.rk-tech-scope .rk-gauge-status.gn { color: var(--gn); background: var(--gn-bg); border: 1px solid var(--gn-dim); }
.rk-tech-scope .rk-gauge-status.am { color: var(--amb); background: var(--amb-bg); border: 1px solid var(--amb-dim); }
.rk-tech-scope .rk-gauge-status.rd { color: var(--rd); background: var(--rd-bg); border: 1px solid var(--rd-dim); }
.rk-tech-scope .rk-gauge-row { display: flex; align-items: baseline; gap: 8px; }
.rk-tech-scope .rk-gauge-v { font: 800 22px var(--mono); line-height: 1.05; }
.rk-tech-scope .rk-gauge.mom .rk-gauge-v { color: var(--info); }
.rk-tech-scope .rk-gauge.trd .rk-gauge-v { color: var(--gn); }
.rk-tech-scope .rk-gauge.vol .rk-gauge-v { color: var(--violet); }
.rk-tech-scope .rk-gauge-sub { font: 600 10px var(--mono); color: var(--ink-2); letter-spacing: 0.06em; }
.rk-tech-scope .rk-gauge-bar { height: 4px; background: var(--bg-3); border-radius: 1px; margin-top: 5px; overflow: hidden; }
.rk-tech-scope .rk-gauge-bar > div { height: 100%; }
.rk-tech-scope .rk-gauge.mom .rk-gauge-bar > div { background: var(--info); }
.rk-tech-scope .rk-gauge.trd .rk-gauge-bar > div { background: var(--gn); }
.rk-tech-scope .rk-gauge.vol .rk-gauge-bar > div { background: var(--violet); }
.rk-tech-scope .rk-gauge-foot { font: 500 9.5px var(--mono); color: var(--ink-3); margin-top: 5px; letter-spacing: 0.02em; line-height: 1.4; }
.rk-tech-scope .rk-cap-matrix { padding: 14px 16px; }
.rk-tech-scope .rk-cap-h { font: 700 10px var(--mono); color: var(--ink-3); letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 8px; }
.rk-tech-scope .rk-cap-row { display: grid; grid-template-columns: 1fr 64px; gap: 8px; align-items: center; padding: 5px 0; border-bottom: 1px dashed var(--line); font-size: 11px; font-family: var(--mono); }
.rk-tech-scope .rk-cap-row:last-child { border-bottom: none; }
.rk-tech-scope .rk-cap-lbl { font: 600 10px var(--mono); color: var(--ink-2); letter-spacing: 0.06em; text-transform: uppercase; }
.rk-tech-scope .rk-cap-val { text-align: right; font: 700 12px var(--mono); color: var(--ink); }
.rk-tech-scope .rk-cap-val.am { color: var(--amb); } .rk-tech-scope .rk-cap-val.rd { color: var(--rd); } .rk-tech-scope .rk-cap-val.gn { color: var(--gn); }
.rk-tech-scope .rk-cap-val.info { color: var(--info); }
.rk-tech-scope .rk-cap-bar { grid-column: 1 / -1; height: 5px; background: var(--bg-3); border-radius: 1px; overflow: hidden; margin-top: 2px; }
.rk-tech-scope .rk-cap-bar > div { height: 100%; }
.rk-tech-scope .rk-cap-bar > div.gn { background: var(--gn); }
.rk-tech-scope .rk-cap-bar > div.am { background: var(--amb); }
.rk-tech-scope .rk-cap-bar > div.rd { background: var(--rd); }
.rk-tech-scope .rk-cap-bar > div.info { background: var(--info); }
.rk-tech-scope .rk-hero-foot { padding: 9px 18px; background: var(--bg-2); border-top: 1px solid var(--line); display: flex; gap: 18px; flex-wrap: wrap; font: 600 11px var(--mono); color: var(--ink-2); letter-spacing: 0.04em; }
.rk-tech-scope .rk-hero-foot b { color: var(--ink); font-weight: 700; }
.rk-tech-scope .rk-hero-foot .gn { color: var(--gn); } .rk-tech-scope .rk-hero-foot .rd { color: var(--rd); } .rk-tech-scope .rk-hero-foot .am { color: var(--amb); } .rk-tech-scope .rk-hero-foot .info { color: var(--info); }
.rk-tech-scope .rk-divider { font: 700 10px var(--mono); color: var(--ink-3); letter-spacing: 0.20em; text-transform: uppercase; margin: 20px 4px 12px; display: flex; align-items: center; gap: 10px; }
.rk-tech-scope .rk-divider::before, .rk-tech-scope .rk-divider::after { content: ''; flex: 1; height: 1px; background: var(--line); }
.rk-tech-scope .rk-divider .copper { color: var(--copper); }
.rk-tech-scope .rk-section { background: var(--bg-1); border: 1px solid var(--line); border-radius: 2px; margin-bottom: 12px; overflow: hidden; }
.rk-tech-scope .rk-section-head { padding: 10px 18px 8px; border-bottom: 1px solid var(--line); display: flex; justify-content: space-between; align-items: baseline; gap: 12px; flex-wrap: wrap; }
.rk-tech-scope .rk-section-title { font: 700 11.5px var(--mono); color: var(--ink-1); letter-spacing: 0.14em; text-transform: uppercase; }
.rk-tech-scope .rk-section-title .num { color: var(--copper); margin-right: 6px; }
.rk-tech-scope .rk-section-sub { font: 500 11px var(--mono); color: var(--ink-3); letter-spacing: 0.06em; }
.rk-tech-scope .rk-section-body { padding: 14px 18px 16px; }
.rk-tech-scope .ind-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px; }
@media (max-width:1100px) { .rk-tech-scope .ind-grid { grid-template-columns: repeat(3, 1fr); } }
@media (max-width:720px) { .rk-tech-scope .ind-grid { grid-template-columns: repeat(2, 1fr); } }
.rk-tech-scope .ind-card { background: var(--bg-2); border: 1px solid var(--line); border-top: 2px solid var(--ink-4); border-radius: 2px; padding: 10px 12px; font-family: var(--mono); }
.rk-tech-scope .ind-card.gn { border-top-color: var(--gn); }
.rk-tech-scope .ind-card.am { border-top-color: var(--amb); }
.rk-tech-scope .ind-card.rd { border-top-color: var(--rd); }
.rk-tech-scope .ind-card.info { border-top-color: var(--info); }
.rk-tech-scope .ind-card.violet { border-top-color: var(--violet); }
.rk-tech-scope .ind-card-h { font: 700 9px var(--mono); color: var(--ink-3); letter-spacing: 0.12em; text-transform: uppercase; margin-bottom: 4px; }
.rk-tech-scope .ind-card-v { font: 800 22px var(--mono); line-height: 1.05; color: var(--ink); }
.rk-tech-scope .ind-card-v.gn { color: var(--gn); } .rk-tech-scope .ind-card-v.am { color: var(--amb); } .rk-tech-scope .ind-card-v.rd { color: var(--rd); } .rk-tech-scope .ind-card-v.info { color: var(--info); } .rk-tech-scope .ind-card-v.violet { color: var(--violet); }
.rk-tech-scope .ind-card-sub { font: 600 10px var(--mono); color: var(--ink-2); margin-top: 3px; letter-spacing: 0.04em; }
.rk-tech-scope .ind-card-bar { height: 4px; background: var(--bg-3); border-radius: 1px; margin-top: 6px; overflow: hidden; position: relative; }
.rk-tech-scope .ind-card-bar > div { height: 100%; }
.rk-tech-scope .ind-card-bar > div.gn { background: var(--gn); }
.rk-tech-scope .ind-card-bar > div.am { background: var(--amb); }
.rk-tech-scope .ind-card-bar > div.rd { background: var(--rd); }
.rk-tech-scope .ind-card-bar > div.info { background: var(--info); }
.rk-tech-scope .ind-card-bar > div.violet { background: var(--violet); }
.rk-tech-scope .ind-card-zones { position: absolute; top: 0; bottom: 0; pointer-events: none; }
.rk-tech-scope .ind-card-zone { position: absolute; top: -4px; bottom: -4px; width: 1px; background: var(--ink-4); }
.rk-tech-scope .ind-card-foot { font: 500 9.5px var(--mono); color: var(--ink-3); margin-top: 5px; letter-spacing: 0.02em; line-height: 1.4; }
.rk-tech-scope .ema-stack { display: grid; grid-template-columns: 1fr; gap: 4px; font-family: var(--mono); font-size: 12px; }
.rk-tech-scope .ema-row { display: grid; grid-template-columns: 80px 1fr 80px 80px; gap: 12px; align-items: center; padding: 8px 12px; background: var(--bg-2); border: 1px solid var(--line); border-radius: 2px; }
.rk-tech-scope .ema-row.cur { border-color: var(--copper); background: var(--copper-bg); }
.rk-tech-scope .ema-row .lbl { font: 700 11px var(--mono); color: var(--ink-1); letter-spacing: 0.06em; }
.rk-tech-scope .ema-row .lbl.cur { color: var(--copper); }
.rk-tech-scope .ema-row .px { font: 700 12px var(--mono); color: var(--ink); text-align: right; }
.rk-tech-scope .ema-row .dist { display: flex; align-items: center; gap: 6px; }
.rk-tech-scope .ema-row .dist-track { flex: 1; height: 5px; background: var(--bg-3); border-radius: 1px; position: relative; overflow: hidden; }
.rk-tech-scope .ema-row .dist-fill { height: 100%; position: absolute; top: 0; }
.rk-tech-scope .ema-row .dist-fill.up { background: var(--gn); left: 50%; }
.rk-tech-scope .ema-row .dist-fill.dn { background: var(--rd); right: 50%; }
.rk-tech-scope .ema-row .dist-mid { position: absolute; left: 50%; top: -2px; bottom: -2px; width: 1px; background: var(--line-2); }
.rk-tech-scope .ema-row .dist-pct { font: 700 11px var(--mono); min-width: 56px; text-align: right; }
.rk-tech-scope .ema-row .dist-pct.up { color: var(--gn); } .rk-tech-scope .ema-row .dist-pct.dn { color: var(--rd); }
.rk-tech-scope .ema-row .status { display: flex; justify-content: flex-end; }
.rk-tech-scope .pat-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
@media (max-width:720px) { .rk-tech-scope .pat-grid { grid-template-columns: 1fr; } }
.rk-tech-scope .pat-block { background: var(--bg-2); border: 1px solid var(--line); border-radius: 2px; padding: 12px 14px; }
.rk-tech-scope .pat-block-h { font: 700 10px var(--mono); color: var(--ink-3); letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 10px; }
.rk-tech-scope .pat-row { display: grid; grid-template-columns: 16px 1fr auto; gap: 10px; align-items: center; padding: 6px 0; border-bottom: 1px dashed var(--line); font-size: 12px; font-family: var(--mono); }
.rk-tech-scope .pat-row:last-child { border-bottom: none; }
.rk-tech-scope .pat-row .ico { font-size: 13px; text-align: center; }
.rk-tech-scope .pat-row .ico.gn { color: var(--gn); } .rk-tech-scope .pat-row .ico.am { color: var(--amb); } .rk-tech-scope .pat-row .ico.rd { color: var(--rd); } .rk-tech-scope .pat-row .ico.dim { color: var(--ink-4); }
.rk-tech-scope .pat-row .name { color: var(--ink-1); font-weight: 600; }
.rk-tech-scope .pat-row .name small { display: block; color: var(--ink-3); font-weight: 500; font-size: 10px; margin-top: 1px; }
.rk-tech-scope table.rk-tbl { width: 100%; border-collapse: collapse; font-family: var(--mono); font-size: 12px; }
.rk-tech-scope table.rk-tbl th { text-align: left; padding: 7px 8px; font-size: 9.5px; color: var(--ink-3); letter-spacing: 0.12em; text-transform: uppercase; border-bottom: 1px solid var(--line); font-weight: 700; }
.rk-tech-scope table.rk-tbl th.r { text-align: right; }
.rk-tech-scope table.rk-tbl td { padding: 8px 8px; border-bottom: 1px solid var(--line); color: var(--ink-1); font-size: 12px; }
.rk-tech-scope table.rk-tbl td.r { text-align: right; }
.rk-tech-scope table.rk-tbl tr:last-child td { border-bottom: none; }
.rk-tech-scope table.rk-tbl tr.spot td { background: var(--copper-bg); }
.rk-tech-scope table.rk-tbl tr.sel td { background: var(--gn-bg); box-shadow: inset 2px 0 0 var(--gn); }
.rk-tech-scope table.rk-tbl b.gn { color: var(--gn); } .rk-tech-scope table.rk-tbl b.rd { color: var(--rd); } .rk-tech-scope table.rk-tbl b.am { color: var(--amb); } .rk-tech-scope table.rk-tbl b.copper { color: var(--copper); }
.rk-tech-scope .rk-pill { display: inline-block; padding: 2px 7px; font: 700 9px var(--mono); letter-spacing: 0.08em; text-transform: uppercase; border-radius: 2px; background: var(--bg-2); border: 1px solid var(--line-2); color: var(--ink-2); }
.rk-tech-scope .rk-pill.gn { color: var(--gn); border-color: var(--gn-dim); background: var(--gn-bg); }
.rk-tech-scope .rk-pill.rd { color: var(--rd); border-color: var(--rd-dim); background: var(--rd-bg); }
.rk-tech-scope .rk-pill.am { color: var(--amb); border-color: var(--amb-dim); background: var(--amb-bg); }
.rk-tech-scope .rk-pill.info { color: var(--info); border-color: var(--info-dim); background: var(--info-bg); }
.rk-tech-scope .rk-pill.violet { color: var(--violet); border-color: var(--violet-dim); background: var(--violet-bg); }
.rk-tech-scope .rk-pill.cyan { color: var(--cyan); border-color: var(--cyan-dim); background: var(--cyan-bg); }
.rk-tech-scope .rk-pill.copper { color: var(--copper); border-color: rgba(217,119,87,0.5); background: var(--copper-bg); }
.rk-tech-scope .rk-note { margin-top: 10px; padding: 8px 12px; border-left: 2px solid var(--ink-4); background: var(--bg-2); border-radius: 0 2px 2px 0; font-size: 12px; color: var(--ink-2); line-height: 1.55; }
.rk-tech-scope .rk-note.gn { border-left-color: var(--gn); } .rk-tech-scope .rk-note.am { border-left-color: var(--amb); } .rk-tech-scope .rk-note.rd { border-left-color: var(--rd); }
.rk-tech-scope .rk-note.info { border-left-color: var(--info); } .rk-tech-scope .rk-note.violet { border-left-color: var(--violet); }
.rk-tech-scope .rk-note b { color: var(--ink); }
.rk-tech-scope .axis { stroke: var(--line-2); stroke-width: 1; }
.rk-tech-scope .grid { stroke: var(--line); stroke-dasharray: 2,3; stroke-width: 0.5; }
.rk-tech-scope .lbl  { fill: var(--ink-3); font: 600 9px var(--mono); }
.rk-tech-scope .vlbl { fill: var(--ink-2); font: 700 10px var(--mono); }
.rk-tech-scope .rk-split-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
@media (max-width:980px) { .rk-tech-scope .rk-split-2 { grid-template-columns: 1fr; } }
.rk-tech-scope .freshness-pill { display: inline-flex; align-items: center; gap: 6px; padding: 2px 8px; border-radius: 2px; font: 700 9px var(--mono); letter-spacing: 0.08em; }
.rk-tech-scope .freshness-pill.gn { background: var(--gn-bg); color: var(--gn); border: 1px solid var(--gn-dim); }
.rk-tech-scope .freshness-pill.am { background: var(--amb-bg); color: var(--amb); border: 1px solid var(--amb-dim); }
.rk-tech-scope .freshness-pill.rd { background: var(--rd-bg); color: var(--rd); border: 1px solid var(--rd-dim); }
.rk-tech-scope .freshness-pill .dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.rk-tech-scope .rk-footer { margin-top: 22px; padding: 12px; border-top: 1px solid var(--line); font: 600 10.5px var(--mono); color: var(--ink-3); letter-spacing: 0.08em; text-align: center; }
.rk-tech-scope .rk-footer .copper { color: var(--copper); }
`;

// ── Helpers ────────────────────────────────────────────────────────────────
function _fmt$(v, d = 2) { return v == null ? '—' : '$' + Number(v).toFixed(d); }
function _fmtSgn(v, d = 2) { return v == null ? '—' : (v >= 0 ? '+' : '') + Number(v).toFixed(d) + '%'; }
function _fmtPct(v, d = 0) { return v == null ? '—' : Number(v).toFixed(d) + '%'; }
function _fmtAge(iso) {
  if (!iso) return { rel: '—', stale: true, cls: 'rd' };
  const t = new Date(iso).getTime();
  const ageH = (Date.now() - t) / 3600000;
  let rel, cls, stale = false;
  if (ageH < 1) rel = Math.max(1, Math.round(ageH * 60)) + 'm ago';
  else if (ageH < 24) rel = Math.round(ageH) + 'h ago';
  else rel = Math.round(ageH / 24) + 'd ago';
  if (ageH < 4) cls = 'gn';
  else if (ageH < 12) cls = 'am';
  else { cls = 'rd'; stale = true; }
  return { rel, stale, cls };
}
function _freshnessPill(label, iso, threshOk = 4) {
  const a = _fmtAge(iso);
  return `<span class="freshness-pill ${a.cls}"><span class="dot"></span>${label} ${a.rel}</span>`;
}

// ── HERO ────────────────────────────────────────────────────────────────────
function _buildHero(T, bundleFreshIso) {
  const ind = (T.technicals || {}).indicators || {};
  const cp = T.canonical_trade_plan || T.trade_plan || {};
  const planEntry = cp.entry;
  const entry = (typeof planEntry === 'object' && planEntry) ? (planEntry.mid ?? planEntry.low ?? planEntry.high ?? T.price) : (planEntry ?? T.price);
  const spot = +(T.price ?? entry) || 100;
  const stop = +cp.stop || spot * 0.96;
  const t1 = +cp.target1 || spot * 1.04;
  const t2 = +cp.target2 || spot * 1.08;
  const atr = ind.atr || ind.atr14 || T.atr;
  const ivRank = (T.options_kpis || {}).iv_percentile;
  const erDays = (T.earnings || {}).days_to_earnings;
  const setupFam = T.setup_family || T.setup_type || '—';
  const entryQ = T.entry_quality || '—';
  const score = T.score;
  const rr = T.rr_ratio ?? cp.rr_ratio;
  const verdict = T.verdict || (T.decision || {}).verdict;
  const flavor = /BUY|BULL/.test(verdict) ? '' : /SHORT|BEAR|AVOID|KILL/.test(verdict) ? 'bear' : 'neu';

  // Indicator gauges (composite 0-10 scores per axis)
  const momRSI = ind.rsi || 50;
  const momMACDok = ind.macd_bullish ? 1 : 0;
  const momStochOk = ind.stoch_k_above_d ? 1 : 0;
  const momScore = Math.round(((momRSI - 50) / 25 + 5 + momMACDok + momStochOk) * 0.8);  // 0-10ish
  const trdEMAstack = (ind.above_20ema && ind.above_50ema && ind.above_200sma) ? 1 : 0;
  const trdADX = ind.adx || 0;
  const trdScore = Math.round((trdADX / 5) + trdEMAstack * 3);
  const volRVOL = ind.rvol || T.rvol || 1;
  const volOBV = ind.obv_rising ? 1 : 0;
  const volCMF = ind.cmf || 0;
  const volScore = Math.round(volRVOL * 3 + volOBV * 2 + (volCMF > 0 ? 2 : 0) + 3);

  const gauge = (cls, kIcon, kLabel, statusLabel, statusCls, value, valSuffix, sub, barPct, foot) => `
    <div class="rk-gauge ${cls}">
      <div class="rk-gauge-head">
        <div class="rk-gauge-k">${kIcon} ${kLabel}</div>
        <span class="rk-gauge-status ${statusCls}">${statusLabel}</span>
      </div>
      <div class="rk-gauge-row">
        <div class="rk-gauge-v">${value}${valSuffix || ''}</div>
        <div class="rk-gauge-sub">${sub}</div>
      </div>
      <div class="rk-gauge-bar"><div style="width:${Math.min(100, Math.max(0, barPct))}%"></div></div>
      <div class="rk-gauge-foot">${foot}</div>
    </div>`;

  // Structural levels matrix
  const distPct = (lvl) => spot > 0 ? ((lvl - spot) / spot * 100) : 0;
  const capRow = (lbl, val, valCls, barPct, barCls) => `
    <div class="rk-cap-row">
      <span class="rk-cap-lbl">${lbl}</span>
      <span class="rk-cap-val ${valCls}">${val}</span>
      <div class="rk-cap-bar"><div class="${barCls}" style="width:${Math.min(100, Math.max(0, barPct))}%"></div></div>
    </div>`;

  return `
    <div class="bc">Kairos · Quant Detail · <b>${T.ticker || '?'}</b> · <span class="copper">Technicals · Chart Lens</span>
      &nbsp;&nbsp;${_freshnessPill('bundle', bundleFreshIso)}</div>
    <section class="rk-hero ${flavor}">
      <div class="rk-hero-banner">
        <div class="rk-hero-badge">TECHNICALS</div>
        <div class="rk-hero-q">Is <b>${T.ticker}</b>'s setup <b>actionable</b>, by <span class="copper">what evidence</span>, against what structural levels?</div>
        <div class="rk-hero-tk">${T.ticker} <small>${_fmt$(spot)}${T.beta ? ' · β ' + T.beta.toFixed(2) : ''}${T.sector ? ' · ' + T.sector : ''}</small></div>
      </div>
      <div class="rk-hero-body">
        <div class="rk-hero-chart">
          <div class="rk-hero-chart-h">
            <span>60-day price · EMA21 / EMA50 / EMA200 stack · T1/T2/Stop overlay</span>
            <span class="legend">
              <i style="background:#fbbf24"></i>EMA21 ·
              <i style="background:#60a5fa"></i>EMA50 ·
              <i style="background:#a78bfa"></i>EMA200
            </span>
          </div>
          ${_buildPriceChart(T, spot, stop, t1, t2, ind)}
        </div>
        <div class="rk-hero-gauges">
          <div class="rk-hero-gauges-h">Indicator Roll-up · 3-axis read</div>
          <div class="rk-hero-gauges-grid">
            ${gauge('mom', '⚡', 'Momentum (RSI / MACD / Stoch)',
                     momScore >= 7 ? 'STRONG' : momScore >= 4 ? 'MIXED' : 'WEAK',
                     momScore >= 7 ? 'gn' : momScore >= 4 ? 'am' : 'rd',
                     momScore, '/10',
                     `RSI ${(ind.rsi ?? '—')} · MACD ${ind.macd_signal || '—'} · Stoch ${ind.stoch_k_above_d ? 'K>D' : 'K<D'}`,
                     momScore * 10,
                     ind.rsi > 70 ? 'overbought zone · watch divergence' : ind.rsi < 30 ? 'oversold zone' : 'neutral momentum range')}
            ${gauge('trd', '📈', 'Trend (EMA stack / ADX)',
                     trdEMAstack && trdADX > 25 ? 'ALIGNED' : trdEMAstack ? 'WEAK TREND' : 'NO TREND',
                     trdEMAstack && trdADX > 25 ? 'gn' : trdEMAstack ? 'am' : 'rd',
                     trdScore, '/10',
                     `Stack ${trdEMAstack ? '✓' : '✗'} · ADX ${trdADX.toFixed(0)}`,
                     trdScore * 10,
                     trdADX > 50 ? 'strong trend · maximum sizing band' : trdADX > 25 ? 'trend onset · normal sizing' : 'range-bound · cut size')}
            ${gauge('vol', '📊', 'Volume (RVOL / OBV / CMF)',
                     volScore >= 7 ? 'ACCUM' : volScore >= 4 ? 'MIXED' : 'DRY',
                     volScore >= 7 ? 'gn' : volScore >= 4 ? 'am' : 'rd',
                     volScore, '/10',
                     `RVOL ${volRVOL.toFixed(2)} · OBV ${ind.obv_rising ? '↑' : '↓'} · CMF ${volCMF.toFixed(2)}`,
                     volScore * 10,
                     volCMF > 0.1 ? 'accumulation · institutional flow positive' : volCMF < -0.1 ? 'distribution · flow negative' : 'neutral volume flow')}
          </div>
        </div>
        <div class="rk-cap-matrix">
          <div class="rk-cap-h">Structural Levels · ATR-normalized</div>
          ${capRow('T2 (BSL)', _fmtSgn(distPct(t2)), 'gn', Math.abs(distPct(t2)) * 10, 'gn')}
          ${capRow('T1 (HVN)', _fmtSgn(distPct(t1)), 'gn', Math.abs(distPct(t1)) * 10, 'gn')}
          ${capRow('52w High', _fmtSgn(distPct(ind.high_52w || t2)), 'info', Math.abs(distPct(ind.high_52w || t2)) * 5, 'info')}
          ${capRow('VWAP', _fmtSgn(distPct(ind.vwap || spot)), distPct(ind.vwap || spot) > 0 ? 'gn' : 'am', Math.abs(distPct(ind.vwap || spot)) * 20, 'am')}
          ${capRow('EMA21', _fmtSgn(distPct(ind.ema21 || spot * 0.98)), distPct(ind.ema21 || spot * 0.98) > 0 ? 'gn' : 'am', Math.abs(distPct(ind.ema21 || spot * 0.98)) * 10, 'am')}
          ${capRow('Stop (−1.25 ATR)', _fmtSgn(distPct(stop)), 'rd', Math.abs(distPct(stop)) * 10, 'rd')}
        </div>
      </div>
      <div class="rk-hero-foot">
        <span>Setup: <b class="gn">${setupFam} × ${entryQ}</b></span>
        <span>R:R: <b class="${rr >= 3 ? 'gn' : 'am'}">${rr != null ? rr.toFixed(1) + ' : 1' : '—'}</b></span>
        ${score != null ? `<span>Composite: <b class="info">${score}</b></span>` : ''}
        ${atr ? `<span>ATR: <b>$${atr.toFixed(2)}</b></span>` : ''}
        ${ivRank != null ? `<span>IV-rank: <b class="${ivRank > 75 ? 'rd' : ivRank > 50 ? 'am' : 'gn'}">${ivRank}</b></span>` : ''}
        ${erDays != null && erDays >= 0 && erDays <= 14 ? `<span class="am">⚠ Earnings T-${erDays} — sizing cap 50%</span>` : ''}
      </div>
    </section>`;
}

// Build a simple 60-day candlestick chart from T.ohlcv
function _buildPriceChart(T, spot, stop, t1, t2, ind) {
  const W = 600, H = 220, pL = 50, pR = 16, pT = 20, pB = 25;
  const ohlcv = (T.ohlcv || []).slice(-60);
  if (ohlcv.length < 5) {
    return `<svg viewBox="0 0 ${W} ${H}"><text x="${W/2}" y="${H/2}" text-anchor="middle" class="lbl">no OHLCV data</text></svg>`;
  }
  const highs = ohlcv.map(b => b.h);
  const lows = ohlcv.map(b => b.l);
  const allY = [...highs, ...lows, stop, t1, t2, spot].filter(Number.isFinite);
  const maxP = Math.max(...allY) * 1.01;
  const minP = Math.min(...allY) * 0.99;
  const cW = W - pL - pR, cH = H - pT - pB;
  const yFor = (p) => pT + (maxP - p) / (maxP - minP) * cH;
  const xFor = (i) => pL + (i / (ohlcv.length - 1)) * cW;
  const bw = (cW / ohlcv.length) * 0.55;

  let candles = '';
  ohlcv.forEach((b, i) => {
    const up = b.c >= b.o;
    const col = up ? '#4ade80' : '#f87171';
    const x = xFor(i);
    candles += `<line x1="${x.toFixed(1)}" y1="${yFor(b.h).toFixed(1)}" x2="${x.toFixed(1)}" y2="${yFor(b.l).toFixed(1)}" stroke="${col}" stroke-width="1"/>`;
    candles += `<rect x="${(x - bw / 2).toFixed(1)}" y="${yFor(Math.max(b.o, b.c)).toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(1, Math.abs(yFor(b.o) - yFor(b.c))).toFixed(1)}" fill="${col}"/>`;
  });
  // EMA overlay
  const ema21 = ind.ema21, ema50 = ind.ema50, ema200 = ind.ema200;
  let levels = '';
  const lvLine = (price, color, label, dash) => {
    if (price == null || !isFinite(price) || price < minP || price > maxP) return '';
    const y = yFor(price);
    return `<line x1="${pL}" y1="${y}" x2="${W - pR}" y2="${y}" stroke="${color}" stroke-width="1" stroke-dasharray="${dash}" opacity="0.7"/>
            <text class="vlbl" x="${W - pR - 2}" y="${y - 3}" text-anchor="end" fill="${color}">${label}</text>`;
  };
  levels += lvLine(t2, '#4ade80', `T2 ${_fmt$(t2, 0)}`, '4,3');
  levels += lvLine(t1, '#4ade80', `T1 ${_fmt$(t1, 0)}`, '4,3');
  levels += lvLine(spot, '#d97757', `spot ${_fmt$(spot, 2)}`, '2,2');
  levels += lvLine(ema21, '#fbbf24', 'EMA21', '1,2');
  levels += lvLine(ema50, '#60a5fa', 'EMA50', '1,2');
  levels += lvLine(ema200, '#a78bfa', 'EMA200', '1,2');
  levels += lvLine(stop, '#f87171', `Stop ${_fmt$(stop, 0)}`, '4,3');

  // y-axis labels
  let yLabels = '';
  for (let i = 0; i <= 4; i++) {
    const y = pT + (i / 4) * cH;
    const price = maxP - (i / 4) * (maxP - minP);
    yLabels += `<line class="grid" x1="${pL}" y1="${y}" x2="${W - pR}" y2="${y}"/>`;
    yLabels += `<text class="lbl" x="${pL - 6}" y="${y + 3}" text-anchor="end">${price.toFixed(0)}</text>`;
  }

  return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
    ${yLabels}
    ${candles}
    ${levels}
  </svg>`;
}

// ── §1 INDICATOR DASHBOARD ─────────────────────────────────────────────────
function _renderIndicators(T) {
  const ind = (T.technicals || {}).indicators || {};
  const indCard = (label, val, valCls, sub, barPct, barCls, zones, foot) => `
    <div class="ind-card ${valCls}">
      <div class="ind-card-h">${label}</div>
      <div class="ind-card-v ${valCls}">${val}</div>
      <div class="ind-card-sub">${sub}</div>
      <div class="ind-card-bar">
        <div class="ind-card-zones">${(zones || []).map(z => `<div class="ind-card-zone" style="left:${z}%"></div>`).join('')}</div>
        <div class="${barCls}" style="width:${Math.min(100, Math.max(0, barPct))}%"></div>
      </div>
      <div class="ind-card-foot">${foot}</div>
    </div>`;
  const rsi = ind.rsi || null;
  const rsiState = rsi == null ? 'info' : rsi > 70 ? 'rd' : rsi < 30 ? 'rd' : rsi > 60 ? 'am' : 'gn';
  return `
    <div class="rk-divider"><span class="copper">§ 1</span> Indicator Dashboard · 6 oscillators / volume readings</div>
    <section class="rk-section">
      <div class="rk-section-head">
        <div>
          <div class="rk-section-title"><span class="num">§1</span>Momentum + Volume Battery</div>
          <div class="rk-section-sub">Each card shows level, regime, zone-position bar with overbought/oversold markers</div>
        </div>
        <span class="rk-pill info">daily bars · most recent close</span>
      </div>
      <div class="rk-section-body">
        <div class="ind-grid">
          ${indCard('RSI 14', rsi == null ? '—' : rsi.toFixed(0), rsiState,
                    rsi == null ? '—' : rsi > 70 ? 'overbought' : rsi < 30 ? 'oversold' : 'neutral range',
                    rsi || 0, rsiState, [30, 70],
                    '30 / 70 thresholds')}
          ${indCard('MACD', ind.macd_signal || '—', ind.macd_bullish ? 'gn' : 'rd',
                    ind.macd_bullish ? 'expansion · bullish cross' : 'compression · bearish',
                    ind.macd_bullish ? 70 : 30, ind.macd_bullish ? 'gn' : 'rd', [50],
                    '12 / 26 / 9 standard')}
          ${indCard('StochRSI', ind.stoch_k_above_d == null ? '—' : (ind.stoch_k_above_d ? 'K > D' : 'K < D'),
                    ind.stoch_k_above_d ? 'gn' : 'am',
                    ind.stoch_k_above_d ? 'bull cross' : 'bear cross',
                    ind.stoch_k_above_d ? 75 : 25, ind.stoch_k_above_d ? 'gn' : 'am', [20, 80],
                    'fast RSI · noisier · 20 / 80 zones')}
          ${indCard('ADX 14', ind.adx == null ? '—' : ind.adx.toFixed(0),
                    ind.adx == null ? 'info' : ind.adx > 25 ? 'gn' : ind.adx > 15 ? 'am' : 'rd',
                    ind.adx_trending ? `trending · DI+ ${(ind.adx_plus_di || 0).toFixed(0)} > DI− ${(ind.adx_minus_di || 0).toFixed(0)}` : 'range-bound',
                    Math.min(100, (ind.adx || 0) * 2), ind.adx > 25 ? 'gn' : 'am', [25, 50],
                    '25 = trend onset · 50 = strong trend')}
          ${indCard('MFI 14', ind.mfi == null ? '—' : ind.mfi.toFixed(0),
                    ind.mfi == null ? 'info' : ind.mfi > 80 ? 'rd' : ind.mfi < 20 ? 'rd' : 'violet',
                    ind.mfi_bullish ? 'volume-weighted bullish' : 'volume-weighted neutral',
                    ind.mfi || 0, 'violet', [20, 80],
                    'real money flow · volume-weighted RSI')}
          ${indCard('CMF 20', ind.cmf == null ? '—' : (ind.cmf >= 0 ? '+' : '') + ind.cmf.toFixed(3),
                    ind.cmf == null ? 'info' : ind.cmf > 0.1 ? 'gn' : ind.cmf < -0.1 ? 'rd' : 'am',
                    ind.cmf_accumulating ? 'accumulation · positive flow' : 'distribution / neutral',
                    50 + (ind.cmf || 0) * 200, ind.cmf > 0 ? 'gn' : 'rd', [50],
                    'Chaikin · volume-weighted MFI variant')}
        </div>
      </div>
    </section>`;
}

// ── §2 EMA STACK ───────────────────────────────────────────────────────────
function _renderEmaStack(T) {
  const ind = (T.technicals || {}).indicators || {};
  const spot = +T.price || 100;
  const rows = [
    { lbl: 'EMA 5',   price: ind.ema5 },
    { lbl: 'EMA 13',  price: ind.ema13 },
    { lbl: 'EMA 20',  price: ind.ema20 },
    { lbl: 'EMA 21',  price: ind.ema21 },
    { lbl: 'EMA 34',  price: ind.ema34 },
    { lbl: 'EMA 50',  price: ind.ema50 },
    { lbl: 'EMA 100', price: ind.ema100 },
    { lbl: 'EMA 200', price: ind.ema200 },
  ].filter(r => r.price != null);

  // Insert SPOT row in correct order
  const items = [...rows, { lbl: 'SPOT', price: spot, cur: true }].sort((a, b) => b.price - a.price);
  const stackAligned = ind.above_20ema && ind.above_50ema && ind.above_200sma;

  const rowHtml = items.map(r => {
    const dist = ((r.price - spot) / spot) * 100;  // for ema rows, this is negative when ema is below spot
    const dPct = ((spot - r.price) / spot) * 100;  // spot vs this ema; +ve = ema below spot
    if (r.cur) {
      return `
        <div class="ema-row cur">
          <div class="lbl cur">▶ SPOT</div>
          <div class="dist"><span style="font:600 10px var(--mono);color:var(--ink-3);letter-spacing:0.10em">CURRENT PRICE</span></div>
          <div class="px">${_fmt$(r.price)}</div>
          <div class="status"><span class="rk-pill copper">NOW</span></div>
        </div>`;
    }
    const dirCls = dPct >= 0 ? 'up' : 'dn';
    const dirSign = dPct >= 0 ? 'up' : 'dn';
    const w = Math.min(50, Math.abs(dPct) * 4);
    const dPctText = (dPct >= 0 ? '+' : '') + dPct.toFixed(2) + '%';
    const status = Math.abs(dPct) < 1 ? '<span class="rk-pill am">NEAR</span>'
                  : dPct > 0 ? '<span class="rk-pill gn">BELOW</span>'
                  : '<span class="rk-pill rd">ABOVE</span>';
    return `
      <div class="ema-row">
        <div class="lbl">${r.lbl}</div>
        <div class="dist">
          <div class="dist-track">
            <div class="dist-mid"></div>
            <div class="dist-fill ${dirCls}" style="width:${w}%"></div>
          </div>
          <div class="dist-pct ${dirCls}">${dPctText}</div>
        </div>
        <div class="px">${_fmt$(r.price)}</div>
        <div class="status">${status}</div>
      </div>`;
  }).join('');

  return `
    <div class="rk-divider"><span class="copper">§ 2</span> EMA / SMA Stack · trend hierarchy</div>
    <section class="rk-section">
      <div class="rk-section-head">
        <div>
          <div class="rk-section-title"><span class="num">§2</span>Moving-average alignment</div>
          <div class="rk-section-sub">Stack ascending = bullish · price's distance from each anchor</div>
        </div>
        <span class="rk-pill ${stackAligned ? 'gn' : 'am'}">${stackAligned ? 'BULLISH STACK ✓' : 'STACK MISALIGNED'}</span>
      </div>
      <div class="rk-section-body">
        <div class="ema-stack">${rowHtml}</div>
        ${stackAligned ? `<div class="rk-note gn">EMAs aligned bullish. First defended support is EMA21 (${_fmt$(ind.ema21)}) — close below invalidates the FRESH-entry premise.</div>` : `<div class="rk-note am">EMA stack not fully aligned — some moving averages out of order. Validate other lenses before sizing.</div>`}
      </div>
    </section>`;
}

// ── §3 PATTERN + SIGNAL DETECTION ──────────────────────────────────────────
function _renderPatterns(T) {
  const ind = (T.technicals || {}).indicators || {};
  const sf = T.setup_family || '';
  const isVCP = /VCP/i.test(sf);
  const isBreak = /Breakout|52|Range/i.test(sf);
  const isTrendCon = /Trend Continuation|Pullback/i.test(sf);
  const isMomImp = /Impulse|Catalyst|Earnings/i.test(sf);
  const insiderFired = (T.insider_cluster_audit || {}).fired;
  const momFired = (T.momentum_audit || {}).fired;
  const peadFired = (T.pead_audit || {}).fired;
  const espFired = (T.esp_play_audit || {}).fired;
  const sqz = T.squeeze_flag || {};
  const dDayCount = ind.distribution_days || 0;

  const patRow = (icoCls, name, sub, pillTxt, pillCls) => `
    <div class="pat-row">
      <div class="ico ${icoCls}">${icoCls === 'gn' ? '●' : icoCls === 'am' ? '◐' : icoCls === 'rd' ? '●' : '○'}</div>
      <div class="name">${name}<small>${sub}</small></div>
      <span class="rk-pill ${pillCls}">${pillTxt}</span>
    </div>`;

  return `
    <div class="rk-divider"><span class="copper">§ 3</span> Pattern + Signal Detection · setup library</div>
    <section class="rk-section">
      <div class="rk-section-head">
        <div>
          <div class="rk-section-title"><span class="num">§3</span>Active patterns &amp; special signals</div>
          <div class="rk-section-sub">Setup-family · catalyst tier · special signals (squeeze / divergence / Wyckoff)</div>
        </div>
        <span class="rk-pill ${sf ? 'gn' : 'am'}">Primary: ${sf || 'none'}</span>
      </div>
      <div class="rk-section-body">
        <div class="pat-grid">
          <div class="pat-block">
            <div class="pat-block-h">▲ Bullish patterns</div>
            ${patRow(isVCP ? 'gn' : 'dim', 'VCP · Volatility Contraction',
                     isVCP ? 'detected · setup_family match' : 'not detected',
                     isVCP ? 'ACTIVE' : 'N/A', isVCP ? 'gn' : '')}
            ${patRow(isBreak ? 'gn' : 'dim', '52w / Range Breakout',
                     isBreak ? `setup_family = ${sf}` : 'not breaking out',
                     isBreak ? 'ACTIVE' : 'N/A', isBreak ? 'gn' : '')}
            ${patRow(sqz.level ? 'am' : 'dim', 'Squeeze · Bollinger inside Keltner',
                     sqz.level ? `${sqz.level} · ${(ind.bars_in_squeeze || 0)} bars` : 'no compression',
                     sqz.level ? 'ARMED' : 'N/A', sqz.level ? 'am' : '')}
            ${patRow(isTrendCon ? 'am' : 'dim', 'EMA21 Pullback / Trend Continuation',
                     isTrendCon ? `setup_family = ${sf}` : 'not in pullback',
                     isTrendCon ? 'VALID' : 'N/A', isTrendCon ? 'am' : '')}
            ${patRow(insiderFired ? 'gn' : 'dim', 'Insider Cluster · ≥3 buys $200K+',
                     insiderFired ? `${(T.insider_data || {}).buys || '?'} buys in 30d` : 'no insider cluster',
                     insiderFired ? 'CONFIRMED' : 'N/A', insiderFired ? 'gn' : '')}
            ${patRow(peadFired ? 'gn' : 'dim', 'PEAD · Post-Earnings Drift',
                     peadFired ? 'EPS beat + gap window active' : 'no PEAD setup',
                     peadFired ? 'ACTIVE' : 'N/A', peadFired ? 'gn' : '')}
            ${patRow(espFired ? 'gn' : 'dim', 'ESP Play · pre-earnings drift',
                     espFired ? 'Zacks ESP > 0 + Rank ≤3 + earn 4-14d' : 'no ESP setup',
                     espFired ? 'ACTIVE' : 'N/A', espFired ? 'gn' : '')}
          </div>
          <div class="pat-block">
            <div class="pat-block-h">▼ Bearish / risk patterns</div>
            ${patRow(ind.rsi > 70 ? 'am' : 'dim', 'RSI Overbought · &gt;70',
                     ind.rsi > 70 ? `RSI ${ind.rsi.toFixed(0)}` : `RSI ${(ind.rsi || 0).toFixed(0)} · within range`,
                     ind.rsi > 70 ? 'MONITOR' : 'N/A', ind.rsi > 70 ? 'am' : '')}
            ${patRow(dDayCount >= 3 ? 'rd' : dDayCount >= 1 ? 'am' : 'dim', 'Distribution-day count',
                     `${dDayCount} of 5 thresh`,
                     dDayCount >= 3 ? 'EXIT' : dDayCount >= 1 ? 'MONITOR' : 'N/A',
                     dDayCount >= 3 ? 'rd' : dDayCount >= 1 ? 'am' : '')}
            ${patRow((T.earnings || {}).earnings_risk ? 'rd' : ((T.earnings || {}).days_to_earnings <= 14 ? 'am' : 'dim'),
                     'Earnings overhang',
                     (T.earnings || {}).days_to_earnings != null ? `T-${(T.earnings || {}).days_to_earnings} days` : 'no upcoming earnings',
                     (T.earnings || {}).earnings_risk ? 'BLOCKED' : ((T.earnings || {}).days_to_earnings <= 14 ? 'CAP-SIZE' : 'N/A'),
                     (T.earnings || {}).earnings_risk ? 'rd' : ((T.earnings || {}).days_to_earnings <= 14 ? 'am' : ''))}
            ${patRow(ind.below_200sma ? 'rd' : 'dim', 'Bear regime · price &lt; SMA200',
                     ind.above_200sma ? 'in bull cycle' : 'in bear cycle',
                     ind.above_200sma ? 'N/A' : 'BEAR REGIME', ind.above_200sma ? '' : 'rd')}
            ${patRow(ind.obv_rising === false ? 'am' : 'dim', 'OBV divergence',
                     ind.obv_rising === false ? 'OBV not confirming price' : 'OBV confirms price',
                     ind.obv_rising === false ? 'MONITOR' : 'N/A', ind.obv_rising === false ? 'am' : '')}
          </div>
        </div>
      </div>
    </section>`;
}

// ── §4 SUPPORT / RESISTANCE CONFLUENCE ─────────────────────────────────────
function _renderSupportResistance(T) {
  const ind = (T.technicals || {}).indicators || {};
  const cp = T.canonical_trade_plan || T.trade_plan || {};
  const planEntry = cp.entry;
  const entry = (typeof planEntry === 'object' && planEntry) ? (planEntry.mid ?? planEntry.low ?? T.price) : (planEntry ?? T.price);
  const spot = +(T.price ?? entry) || 100;
  const stop = +cp.stop || spot * 0.96;
  const t1 = +cp.target1 || spot * 1.04;
  const t2 = +cp.target2 || spot * 1.08;
  const vp = T.volume_profile || {};
  const fH = ind.fractal_highs || [];
  const fL = ind.fractal_lows || [];

  const levels = [
    { name: 'T2 · BSL', price: t2, conf: ['BSL', 'Fib 1.618'], strength: 'HIGH', sourceCls: 'gn' },
    { name: 'T1 · HVN', price: t1, conf: ['HVN', 'prior R'], strength: 'HIGH', sourceCls: 'gn' },
    { name: '52w High', price: ind.high_52w, conf: ['Yearly hi'], strength: 'MED', sourceCls: 'info' },
    { name: 'VAH (Vol)', price: vp.vah, conf: ['Vol profile'], strength: 'MED', sourceCls: 'info' },
    { name: 'POC', price: vp.poc, conf: ['Vol POC'], strength: 'HIGH', sourceCls: 'info' },
    { name: '▶ SPOT', price: spot, conf: ['CURRENT'], strength: '—', sourceCls: 'copper', spot: true },
    { name: 'VWAP', price: ind.vwap || vp.price, conf: ['VWAP 20d'], strength: 'MED', sourceCls: 'am' },
    { name: 'EMA21', price: ind.ema21, conf: ['EMA', 'trendline'], strength: 'HIGH', sourceCls: 'am' },
    { name: 'EMA50', price: ind.ema50, conf: ['EMA'], strength: 'MED', sourceCls: 'am' },
    { name: 'VAL (Vol)', price: vp.val, conf: ['Vol profile'], strength: 'MED', sourceCls: 'am' },
    { name: 'AVWAP-lo', price: ind.avwap_swing_low, conf: ['Anchored VWAP'], strength: 'HIGH', sourceCls: 'rd' },
    { name: 'Stop', price: stop, conf: ['ATR', 'AVWAP-lo'], strength: 'HIGH', sourceCls: 'rd' },
  ].filter(l => l.price != null && isFinite(l.price));
  // sort descending by price
  levels.sort((a, b) => b.price - a.price);

  const rowHtml = levels.map(l => {
    const delta = ((l.price - spot) / spot) * 100;
    const cls = l.spot ? 'spot' : '';
    return `
      <tr class="${cls}">
        <td><b class="${l.sourceCls}">${l.name}</b></td>
        <td class="r"><b class="${l.sourceCls}">${_fmt$(l.price)}</b></td>
        <td class="r ${l.sourceCls}">${l.spot ? '0.0%' : _fmtSgn(delta)}</td>
        <td>${l.conf.map(c => `<span class="rk-pill ${l.sourceCls === 'copper' ? 'copper' : l.sourceCls}">${c}</span>`).join(' ')}</td>
        <td><span class="rk-pill ${l.strength === 'HIGH' ? l.sourceCls : 'am'}">${l.strength}</span></td>
      </tr>`;
  }).join('');

  return `
    <div class="rk-divider"><span class="copper">§ 4</span> Support / Resistance · structural confluence</div>
    <section class="rk-section">
      <div class="rk-section-head">
        <div>
          <div class="rk-section-title"><span class="num">§4</span>S/R Map · confluence-weighted</div>
          <div class="rk-section-sub">Spot row in copper · ranked by price · confluence shows which signals agree</div>
        </div>
        <span class="rk-pill info">${levels.length} levels</span>
      </div>
      <div class="rk-section-body">
        <table class="rk-tbl">
          <thead><tr><th>Level</th><th class="r">Price</th><th class="r">Δ from spot</th><th>Confluence</th><th>Strength</th></tr></thead>
          <tbody>${rowHtml}</tbody>
        </table>
      </div>
    </section>`;
}

// ── §5 VOLUME ANALYTICS ───────────────────────────────────────────────────
function _renderVolume(T) {
  const ind = (T.technicals || {}).indicators || {};
  const insT = T.inst_trend || {};
  const opts = T.options_kpis || {};
  const ins = T.insider_data || {};
  const rvol = ind.rvol || T.rvol || 0;
  const obvRising = ind.obv_rising;
  const cmf = ind.cmf;
  const rvolPill = rvol > 1.5 ? 'gn' : rvol > 1.0 ? 'am' : 'rd';

  return `
    <div class="rk-divider"><span class="copper">§ 5</span> Volume Analytics · accumulation profile</div>
    <section class="rk-section">
      <div class="rk-section-head">
        <div>
          <div class="rk-section-title"><span class="num">§5</span>Volume regime + flow</div>
          <div class="rk-section-sub">Relative volume · OBV trend · institutional fingerprint</div>
        </div>
        <span class="rk-pill ${cmf > 0.1 ? 'violet' : 'am'}">${cmf > 0.1 ? 'ACCUMULATION' : cmf < -0.1 ? 'DISTRIBUTION' : 'NEUTRAL FLOW'}</span>
      </div>
      <div class="rk-section-body">
        <div class="rk-split-2">
          <div class="pat-block">
            <div class="pat-block-h">▲ Volume regime</div>
            <table class="rk-tbl">
              <tbody>
                <tr><td>RVOL · current</td><td class="r"><b class="${rvolPill}">${rvol.toFixed(2)}×</b></td><td><span class="rk-pill ${rvolPill}">${rvol > 1.5 ? 'ABOVE-AVG' : rvol > 1 ? 'NORMAL+' : 'BELOW-AVG'}</span></td></tr>
                <tr><td>OBV · rising?</td><td class="r"><b class="${obvRising ? 'gn' : 'am'}">${obvRising ? 'YES' : 'NO'}</b></td><td><span class="rk-pill ${obvRising ? 'gn' : 'am'}">${obvRising ? 'CONFIRMS' : 'DIVERGES'}</span></td></tr>
                <tr><td>CMF 20</td><td class="r"><b class="${cmf > 0 ? 'gn' : 'rd'}">${cmf == null ? '—' : (cmf >= 0 ? '+' : '') + cmf.toFixed(3)}</b></td><td><span class="rk-pill ${cmf > 0.1 ? 'gn' : cmf < -0.1 ? 'rd' : 'am'}">${cmf > 0.1 ? 'ACCUM' : cmf < -0.1 ? 'DISTRIB' : 'NEUTRAL'}</span></td></tr>
                <tr><td>MFI 14</td><td class="r"><b class="violet">${ind.mfi == null ? '—' : ind.mfi.toFixed(0)}</b></td><td><span class="rk-pill ${ind.mfi_bullish ? 'gn' : 'am'}">${ind.mfi_bullish ? 'BULLISH' : 'NEUTRAL'}</span></td></tr>
                <tr><td>Avg volume</td><td class="r"><b>${T.avg_volume ? (T.avg_volume / 1e6).toFixed(1) + 'M' : '—'}</b></td><td><span class="rk-pill">${T.avg_volume > 10e6 ? 'LIQUID' : T.avg_volume > 1e6 ? 'NORMAL' : 'THIN'}</span></td></tr>
              </tbody>
            </table>
          </div>
          <div class="pat-block">
            <div class="pat-block-h">▶ Institutional fingerprint</div>
            <table class="rk-tbl">
              <tbody>
                <tr><td>Inst. ownership %</td><td class="r"><b>${insT.inst_pct != null ? insT.inst_pct.toFixed(1) + '%' : '—'}</b></td><td><span class="rk-pill ${insT.inst_trend === 'increasing' ? 'gn' : insT.inst_trend === 'decreasing' ? 'rd' : 'am'}">${(insT.inst_trend || '—').toUpperCase()}</span></td></tr>
                <tr><td>Inst. net change · qtr</td><td class="r"><b class="${insT.net_change_pct > 0 ? 'gn' : 'rd'}">${insT.net_change_pct != null ? (insT.net_change_pct >= 0 ? '+' : '') + insT.net_change_pct.toFixed(2) + '%' : '—'}</b></td><td><span class="rk-pill ${insT.net_change_pct > 0 ? 'gn' : 'rd'}">${insT.net_change_pct > 0 ? '13F BUYS' : '13F SELLS'}</span></td></tr>
                <tr><td>Insider buys · 90d</td><td class="r"><b class="${(ins.buys || 0) > 0 ? 'gn' : ''}">${ins.buys || 0}</b></td><td><span class="rk-pill ${ins.sentiment === 'bullish' ? 'gn' : 'am'}">${(ins.sentiment || '—').toUpperCase()}</span></td></tr>
                <tr><td>P/C ratio</td><td class="r"><b>${opts.put_call_ratio != null ? opts.put_call_ratio.toFixed(2) : '—'}</b></td><td><span class="rk-pill ${opts.put_call_ratio < 0.7 ? 'gn' : opts.put_call_ratio > 1.3 ? 'rd' : 'am'}">${opts.put_call_ratio < 0.7 ? 'CALL-HEAVY' : opts.put_call_ratio > 1.3 ? 'PUT-HEAVY' : 'BALANCED'}</span></td></tr>
                <tr><td>IV rank</td><td class="r"><b class="${opts.iv_percentile > 75 ? 'rd' : opts.iv_percentile > 50 ? 'am' : 'gn'}">${opts.iv_percentile != null ? opts.iv_percentile : '—'}</b></td><td><span class="rk-pill ${opts.iv_percentile > 75 ? 'rd' : 'info'}">${opts.iv_percentile > 75 ? 'RICH VOL' : opts.iv_percentile > 50 ? 'MODERATE' : 'CHEAP'}</span></td></tr>
                <tr><td>UOA</td><td class="r"><b class="${opts.uoa_calls ? 'gn' : opts.uoa_puts ? 'rd' : ''}">${opts.uoa_calls ? 'CALL' : opts.uoa_puts ? 'PUT' : '—'}</b></td><td><span class="rk-pill ${opts.uoa_calls ? 'gn' : opts.uoa_puts ? 'rd' : ''}">${opts.uoa_calls ? 'BULL FLOW' : opts.uoa_puts ? 'BEAR FLOW' : 'QUIET'}</span></td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </section>`;
}

// ── §6 STATISTICAL BACKBONE (Wilson CI from /v2/setup_stats.json) ─────────
function _renderStatBackbone(T, stats) {
  const sf = T.setup_family || '';
  const sFresh = (stats || {})._meta || {};
  const setupRow = (stats && stats.setups) ? stats.setups[sf] : null;
  if (!setupRow) {
    return `
      <div class="rk-divider"><span class="copper">§ 6</span> Statistical Backbone · setup edge with confidence</div>
      <section class="rk-section">
        <div class="rk-section-head">
          <div>
            <div class="rk-section-title"><span class="num">§6</span>No stats available</div>
            <div class="rk-section-sub">${sf ? `Setup family "${sf}" has no closed trades in picks_history yet.` : 'No setup_family detected on this ticker.'}</div>
          </div>
          ${sFresh.generated_at ? _freshnessPill('setup-stats', sFresh.generated_at, 24) : '<span class="rk-pill rd">no data</span>'}
        </div>
        <div class="rk-section-body">
          <div class="rk-note am">Refusing to act on n &lt; 30 per CLAUDE.md principle 1. Build setup_stats.json on the next morning scan, or wait until ≥30 trades close for this family.</div>
        </div>
      </section>`;
  }
  const decay = setupRow.decay || {};
  const wlb = setupRow.wilson_lb;
  const breakeven = setupRow.median_r != null && setupRow.median_r > 0 ? 1 / (1 + setupRow.median_r) : 0.4;
  return `
    <div class="rk-divider"><span class="copper">§ 6</span> Statistical Backbone · setup edge with confidence interval</div>
    <section class="rk-section">
      <div class="rk-section-head">
        <div>
          <div class="rk-section-title"><span class="num">§6</span>${sf} · historical edge</div>
          <div class="rk-section-sub">Point estimates lie · Wilson LB is what we act on · n ≥ 30 required (principle 1)</div>
        </div>
        ${_freshnessPill('setup-stats', sFresh.generated_at, 24)}
      </div>
      <div class="rk-section-body">
        <div class="rk-split-2">
          <div class="pat-block">
            <div class="pat-block-h">${sf} · base rates (full sample)</div>
            <table class="rk-tbl">
              <tbody>
                <tr><td>Sample size</td><td class="r"><b>${setupRow.n} trades</b></td><td><span class="rk-pill ${setupRow.n >= 30 ? 'gn' : 'rd'}">n ${setupRow.n >= 30 ? '≥ 30 floor' : '< 30 ACT WITH CAUTION'}</span></td></tr>
                <tr><td>Raw win-rate</td><td class="r"><b class="gn">${(setupRow.wr * 100).toFixed(0)}%</b></td><td><span style="font-family:var(--mono);font-size:10px;color:var(--ink-3)">point estimate</span></td></tr>
                <tr><td>Wilson 95% lower bound</td><td class="r"><b class="${wlb > breakeven ? 'gn' : 'am'}">${(wlb * 100).toFixed(1)}%</b></td><td><span class="rk-pill ${wlb > breakeven ? 'gn' : 'am'}">${wlb > breakeven ? 'CLEARS BREAKEVEN' : 'AT RISK'}</span></td></tr>
                <tr><td>Wilson 95% upper bound</td><td class="r"><b>${(setupRow.wilson_ub * 100).toFixed(1)}%</b></td><td><span style="font-family:var(--mono);font-size:10px;color:var(--ink-3)">CI width ${((setupRow.wilson_ub - wlb) * 100).toFixed(1)}pp</span></td></tr>
                <tr><td>Profit factor · raw</td><td class="r"><b class="${setupRow.pf > 1.5 ? 'gn' : setupRow.pf > 1 ? 'am' : 'rd'}">${setupRow.pf.toFixed(2)}</b></td><td><span class="rk-pill ${setupRow.pf > 1.5 ? 'gn' : 'am'}">${setupRow.pf > 1.5 ? 'STRONG' : 'MARGINAL'}</span></td></tr>
                <tr><td>Profit factor · haircut −0.20</td><td class="r"><b class="${setupRow.pf_haircut > 1.3 ? 'gn' : 'am'}">${setupRow.pf_haircut.toFixed(2)}</b></td><td><span class="rk-pill ${setupRow.pf_haircut > 1.3 ? 'gn' : 'am'}">${setupRow.pf_haircut > 1.3 ? 'POST-SLIP OK' : 'TIGHT'}</span></td></tr>
                <tr><td>Median R-multiple</td><td class="r"><b class="${setupRow.median_r > 0 ? 'gn' : 'rd'}">${(setupRow.median_r >= 0 ? '+' : '') + (setupRow.median_r || 0).toFixed(2)}R</b></td><td><span style="font-family:var(--mono);font-size:10px;color:var(--ink-3)">vs theoretical R</span></td></tr>
              </tbody>
            </table>
          </div>
          <div class="pat-block">
            <div class="pat-block-h">⏱ Edge decay · is it still working?</div>
            <table class="rk-tbl">
              <tbody>
                ${['trailing_90d', 'trailing_6mo', 'trailing_12mo'].map(slice => {
                  const s = decay[slice] || {};
                  const label = { trailing_90d: 'Last 90 days', trailing_6mo: 'Trailing 6 months', trailing_12mo: 'Trailing 12 months' }[slice];
                  if (!s.n) return `<tr><td>${label}</td><td class="r"><b class="am">no data</b></td><td><span class="rk-pill am">—</span></td></tr>`;
                  return `<tr><td>${label} · WR</td><td class="r"><b class="${s.wr > 0.5 ? 'gn' : 'am'}">${(s.wr * 100).toFixed(0)}% (n=${s.n})</b></td><td><span class="rk-pill ${s.n < 30 ? 'am' : 'gn'}">${s.n < 30 ? 'small sample' : 'stable'}</span></td></tr>`;
                }).join('')}
                <tr><td>KS drift · last 30d vs full</td><td class="r"><b class="${setupRow.ks_drift_30d < 0.10 ? 'gn' : 'am'}">${setupRow.ks_drift_30d.toFixed(2)}</b></td><td><span class="rk-pill ${setupRow.ks_drift_30d < 0.10 ? 'gn' : 'am'}">${setupRow.ks_drift_30d < 0.10 ? 'BELOW THRESHOLD' : 'POSSIBLE DRIFT'}</span></td></tr>
              </tbody>
            </table>
          </div>
        </div>
        <div class="rk-note ${wlb > breakeven ? 'gn' : 'am'}">
          <b>Wilson LB ${(wlb * 100).toFixed(0)}% is what we act on.</b> With n=${setupRow.n}, the true win rate sits between ${(wlb * 100).toFixed(0)}–${(setupRow.wilson_ub * 100).toFixed(0)}% with 95% confidence. ${wlb > breakeven ? `Clears the breakeven threshold (~${(breakeven * 100).toFixed(0)}% at this R-multiple) by ~${((wlb - breakeven) * 100).toFixed(0)}pp — genuine edge after frictions.` : `Below breakeven threshold — edge is statistically marginal.`}
        </div>
      </div>
    </section>`;
}

// ── §7 CROSS-SOURCE CONFLUENCE (6 lenses) ──────────────────────────────────
function _renderCrossSource(T, mlAll) {
  const sb = T.scoring_breakdown || {};
  const opts = T.options_kpis || {};
  const ins = T.insider_data || {};
  const earn = T.earnings || {};
  const sym = (T.ticker || '').toUpperCase();
  const mlPayload = mlAll && mlAll.predictions && mlAll.predictions.swing ? (mlAll.predictions.swing || {})[sym] : null;
  const mlMeta = (mlAll || {})._meta || {};
  const mlPred = mlPayload && mlPayload.direction ? mlPayload : null;

  const lenses = [
    {
      lens: '1. Technicals',
      verdictCls: sb.tech_score >= 25 ? 'gn' : sb.tech_score >= 15 ? 'am' : 'rd',
      verdict: sb.tech_score >= 25 ? 'BULLISH' : sb.tech_score >= 15 ? 'NEUTRAL' : 'BEARISH',
      strength: sb.tech_score != null ? `${sb.tech_score.toFixed(0)}/35` : '—',
      source: T.setup_family || '—',
      mechanism: 'Chart structure + indicator alignment',
      horizon: '5–14 days',
    },
    {
      lens: '2. Fundamentals',
      verdictCls: sb.qg_score >= 7 ? 'gn' : sb.qg_score >= 4 ? 'am' : 'rd',
      verdict: sb.qg_score >= 7 ? 'BULLISH' : sb.qg_score >= 4 ? 'NEUTRAL' : 'BEARISH',
      strength: sb.qg_score != null ? `${sb.qg_score.toFixed(0)}/10` : '—',
      source: `${T.grade_growth || '—'}/${T.grade_value || '—'}/${T.grade_momentum || '—'}`,
      mechanism: 'Growth · value · momentum grades',
      horizon: '2–4 quarters',
    },
    {
      lens: '3. Catalyst / Earnings',
      verdictCls: T.catalyst_tier === 1 ? 'gn' : T.catalyst_tier === 2 ? 'am' : earn.earnings_risk ? 'rd' : 'am',
      verdict: T.catalyst_tier === 1 ? 'STRONG' : T.catalyst_tier === 2 ? 'MODERATE' : earn.earnings_risk ? 'BLOCKED' : 'NEUTRAL',
      strength: sb.cat_score != null ? `${sb.cat_score.toFixed(0)}/20` : '—',
      source: earn.days_to_earnings != null ? `ER T-${earn.days_to_earnings}` : (T.catalyst_tags || []).join(', ') || '—',
      mechanism: 'Tier 1=PEAD/UOA/VCP · Tier 2=Squeeze/Pullback',
      horizon: '1–2 weeks',
    },
    {
      lens: '4. Options Flow',
      verdictCls: opts.uoa_calls ? 'gn' : opts.uoa_puts ? 'rd' : 'am',
      verdict: opts.uoa_calls ? 'BULLISH' : opts.uoa_puts ? 'BEARISH' : 'NEUTRAL',
      strength: opts.put_call_ratio != null ? `P/C ${opts.put_call_ratio.toFixed(2)}` : '—',
      source: `IV-rank ${opts.iv_percentile != null ? opts.iv_percentile : '—'} · UOA ${opts.uoa_calls ? 'CALL' : opts.uoa_puts ? 'PUT' : 'none'}`,
      mechanism: 'Smart money flow + vol regime',
      horizon: '1–4 weeks',
    },
    {
      lens: '5. Smart Money / Insider',
      verdictCls: ((T.inst_trend || {}).inst_trend === 'increasing' || ins.sentiment === 'bullish') ? 'gn' : ((T.inst_trend || {}).inst_trend === 'decreasing' || ins.sentiment === 'bearish') ? 'rd' : 'am',
      verdict: ((T.inst_trend || {}).inst_trend === 'increasing' || ins.sentiment === 'bullish') ? 'BULLISH' : ((T.inst_trend || {}).inst_trend === 'decreasing' || ins.sentiment === 'bearish') ? 'BEARISH' : 'NEUTRAL',
      strength: sb.sm_score != null ? `${sb.sm_score.toFixed(0)}/15` : '—',
      source: `13F: ${(T.inst_trend || {}).inst_trend || '—'} · Insider: ${ins.sentiment || '—'} (${ins.buys || 0}B/${ins.sells || 0}S)`,
      mechanism: 'Institutional + insider info edge',
      horizon: '1–6 months',
    },
  ];
  if (mlPred) {
    lenses.push({
      lens: '6. ML Edge (swing)',
      verdictCls: mlPred.verdict.color === 'pass' ? 'gn' : mlPred.verdict.color === 'fail' ? 'rd' : 'am',
      verdict: mlPred.verdict.text || 'NEUTRAL',
      strength: mlPred.direction.p_up != null ? `P(up) ${(mlPred.direction.p_up * 100).toFixed(0)}%` : '—',
      source: `q50 ${(mlPred.magnitude.q50 >= 0 ? '+' : '') + (mlPred.magnitude.q50 || 0).toFixed(1)}% · P(T1) ${((mlPred.hit_net || {}).p_t1_first != null ? ((mlPred.hit_net.p_t1_first) * 100).toFixed(0) + '%' : '—')}`,
      mechanism: 'GBM + isotonic + quantile + Hit-Net',
      horizon: '5d native',
    });
  }
  const bullCount = lenses.filter(l => l.verdictCls === 'gn').length;
  const bearCount = lenses.filter(l => l.verdictCls === 'rd').length;
  const overallPill = bullCount >= lenses.length - 1 ? 'gn' : bearCount >= lenses.length - 1 ? 'rd' : 'am';
  const overallTxt = `${bullCount} BULL · ${lenses.length - bullCount - bearCount} NEUTRAL · ${bearCount} BEAR of ${lenses.length}`;
  return `
    <div class="rk-divider"><span class="copper">§ 7</span> Cross-Source Confluence · 6 lenses agree or disagree?</div>
    <section class="rk-section">
      <div class="rk-section-head">
        <div>
          <div class="rk-section-title"><span class="num">§7</span>5-lens + ML agreement matrix</div>
          <div class="rk-section-sub">Orthogonal signals · alignment = high conviction · divergence = horizon-dependent edge</div>
        </div>
        <span class="rk-pill ${overallPill}">${overallTxt}</span>
      </div>
      <div class="rk-section-body">
        <table class="rk-tbl">
          <thead><tr><th>Lens</th><th>Verdict</th><th>Strength</th><th>Source / metric</th><th>Mechanism</th><th>Horizon</th></tr></thead>
          <tbody>
            ${lenses.map(l => `
              <tr>
                <td><b>${l.lens}</b></td>
                <td><span class="rk-pill ${l.verdictCls}">${l.verdict}</span></td>
                <td><b class="${l.verdictCls}">${l.strength}</b></td>
                <td>${l.source}</td>
                <td><span style="color:var(--ink-2);font-size:11px">${l.mechanism}</span></td>
                <td><span style="color:var(--ink-3);font-size:11px">${l.horizon}</span></td>
              </tr>`).join('')}
          </tbody>
        </table>
        ${mlMeta.generated_at ? `<div style="margin-top:6px;text-align:right">${_freshnessPill('ML Edge', mlMeta.generated_at, 6)}</div>` : ''}
      </div>
    </section>`;
}

// ── §8 REGIME-CONDITIONAL EDGE ────────────────────────────────────────────
function _renderRegimeConditional(T, stats) {
  const sf = T.setup_family || '';
  const setupRow = (stats && stats.setups) ? stats.setups[sf] : null;
  if (!setupRow || !setupRow.per_regime) return '';
  const currentRegime = (T.regime4 || T.regime || '').replace(/_/g, ' ');
  const order = ['risk_on_trending', 'risk_on_choppy', 'risk_off_trending', 'panic'];
  const labels = {
    'risk_on_trending': 'Risk-on trending',
    'risk_on_choppy': 'Risk-on choppy',
    'risk_off_trending': 'Risk-off trending',
    'panic': 'Panic',
  };
  const rows = order.map(r => {
    const s = setupRow.per_regime[r] || { n: 0 };
    const isCurrent = r === (T.regime4 || T.regime);
    if (s.n === 0) {
      return `<tr><td><b class="${isCurrent ? 'copper' : ''}">${isCurrent ? '▶ ' : ''}${labels[r]}</b></td><td class="r"><b>0</b></td><td colspan="6" style="color:var(--ink-3)"><i>no trades · n=0</i></td></tr>`;
    }
    const sizeMult = s.wilson_lb > 0.5 ? '1.0×' : s.wilson_lb > 0.4 ? '0.6×' : s.wilson_lb > 0.3 ? '0.3×' : '0×';
    const sizeCls = s.wilson_lb > 0.5 ? 'gn' : s.wilson_lb > 0.4 ? 'am' : 'rd';
    const cls = isCurrent ? 'spot' : '';
    return `<tr class="${cls}">
      <td><b class="${isCurrent ? 'copper' : ''}">${isCurrent ? '▶ ' : ''}${labels[r]}${isCurrent ? ' (CURRENT)' : ''}</b></td>
      <td class="r">${s.n}</td>
      <td class="r"><b class="${s.wr > 0.5 ? 'gn' : s.wr > 0.4 ? 'am' : 'rd'}">${(s.wr * 100).toFixed(0)}%</b></td>
      <td class="r"><b class="${s.wilson_lb > 0.5 ? 'gn' : s.wilson_lb > 0.4 ? 'am' : 'rd'}">${(s.wilson_lb * 100).toFixed(0)}%</b></td>
      <td class="r"><b class="${s.pf > 1.5 ? 'gn' : s.pf > 1 ? 'am' : 'rd'}">${s.pf.toFixed(2)}</b></td>
      <td class="r"><b>${s.median_r != null ? (s.median_r >= 0 ? '+' : '') + s.median_r.toFixed(2) + 'R' : '—'}</b></td>
      <td><span class="rk-pill ${sizeCls}">${sizeMult}</span></td>
    </tr>`;
  }).join('');

  return `
    <div class="rk-divider"><span class="copper">§ 8</span> Regime-Conditional Performance · same setup, different worlds</div>
    <section class="rk-section">
      <div class="rk-section-head">
        <div>
          <div class="rk-section-title"><span class="num">§8</span>${sf} · per-regime breakdown</div>
          <div class="rk-section-sub">Generic averages lie · current regime: <b class="copper">${currentRegime || '—'}</b></div>
        </div>
        <span class="rk-pill copper">CURRENT REGIME ROW HIGHLIGHTED</span>
      </div>
      <div class="rk-section-body">
        <table class="rk-tbl">
          <thead><tr><th>Regime</th><th class="r">n</th><th class="r">WR</th><th class="r">Wilson LB</th><th class="r">PF</th><th class="r">Median R</th><th>Size mult</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
        <div class="rk-note info">Refuse the same setup at smaller size when Wilson LB &lt; 50%. Skip entirely if Wilson LB &lt; 40% in a regime with n ≥ 30. Current regime determines sizing multiplier (right column).</div>
      </div>
    </section>`;
}

// ── §9 PRE-MORTEM · FALSIFICATION CRITERIA ────────────────────────────────
function _renderPreMortem(T) {
  const ind = (T.technicals || {}).indicators || {};
  const cp = T.canonical_trade_plan || T.trade_plan || {};
  const ema21 = ind.ema21;
  const erDays = (T.earnings || {}).days_to_earnings;
  const dDayCount = ind.distribution_days || 0;
  const vix = T.market_vix;

  const rules = [
    { name: '1. Close below EMA21', thresh: ema21 ? `$${ema21.toFixed(2)} close-based` : '—', action: 'EXIT IMMEDIATELY', actionCls: 'rd', mechanism: 'FRESH-entry premise broken · trend support violated' },
    { name: '2. Distribution-day count', thresh: '≥ 3 in last 5 days', action: dDayCount >= 3 ? 'EXIT NOW' : 'MONITOR', actionCls: dDayCount >= 3 ? 'rd' : 'am', mechanism: 'Institutional selling overwhelms accumulation' },
    { name: '3. RSI bearish divergence', thresh: 'New price hi + lower RSI hi', action: 'TRIM 50%', actionCls: 'am', mechanism: 'Momentum exhaustion · partial protection' },
    { name: '4. VIX spike', thresh: `VIX > 22 (currently ${vix != null ? vix.toFixed(1) : '—'})`, action: 'CUT SIZE 0.5×', actionCls: 'am', mechanism: 'Regime transition · choppy → risk-off' },
    { name: '5. Earnings disappoint', thresh: erDays != null ? `T+0 reaction (ER in ${erDays}d)` : 'no upcoming earnings', action: erDays != null && erDays <= 14 ? 'EXIT REMAINING POST-ER' : 'N/A', actionCls: erDays != null && erDays <= 14 ? 'rd' : '', mechanism: 'Binary catalyst against · thesis broken' },
    { name: '6. ML divergence', thresh: 'ML flips BEARISH (P(up) < 0.35)', action: 'TRIM 50%', actionCls: 'am', mechanism: 'Statistical disagreement · partial' },
  ];

  return `
    <div class="rk-divider"><span class="copper">§ 9</span> Pre-Mortem · What kills this thesis BEFORE you size in</div>
    <section class="rk-section">
      <div class="rk-section-head">
        <div>
          <div class="rk-section-title"><span class="num">§9</span>Adversarial check · explicit invalidation criteria</div>
          <div class="rk-section-sub">Principle 4 · every BUY needs falsification criteria written BEFORE entry</div>
        </div>
        <span class="rk-pill rd">${rules.length} INVALIDATION RULES</span>
      </div>
      <div class="rk-section-body">
        <table class="rk-tbl">
          <thead><tr><th>Invalidation rule</th><th>Threshold</th><th>Action</th><th>Mechanism · why</th></tr></thead>
          <tbody>
            ${rules.map(r => `<tr>
              <td><b class="${r.actionCls === 'rd' ? 'rd' : r.actionCls === 'am' ? 'am' : ''}">${r.name}</b></td>
              <td>${r.thresh}</td>
              <td><span class="rk-pill ${r.actionCls}">${r.action}</span></td>
              <td><span style="color:var(--ink-2);font-size:11px">${r.mechanism}</span></td>
            </tr>`).join('')}
          </tbody>
        </table>
        <div class="rk-note ${dDayCount >= 3 ? 'rd' : erDays != null && erDays <= 14 ? 'am' : 'info'}">
          <b>What "I'm wrong" looks like:</b> ${ema21 ? `close below $${ema21.toFixed(2)} in next 5 sessions, or ` : ''}post-ER reaction &lt; −3% if ER ≤ 14d. Mechanical exit — do not anchor, do not average down.
        </div>
      </div>
    </section>`;
}

// ── §10 SIZING + EXIT DISCIPLINE ──────────────────────────────────────────
function _renderSizingExits(T) {
  const ks = T.kelly_size || {};
  const cp = T.canonical_trade_plan || T.trade_plan || {};
  const stop = +cp.stop;
  const t1 = +cp.target1;
  const t2 = +cp.target2;
  const erDays = (T.earnings || {}).days_to_earnings;
  const planEntry = cp.entry;
  const entry = (typeof planEntry === 'object' && planEntry) ? (planEntry.mid ?? planEntry.low ?? T.price) : (planEntry ?? T.price);

  return `
    <div class="rk-divider"><span class="copper">§ 10</span> Position Sizing &amp; Exit Discipline · risk-first, mechanical</div>
    <section class="rk-section">
      <div class="rk-section-head">
        <div>
          <div class="rk-section-title"><span class="num">§10</span>Kelly cascade · multipliers · mechanical exits</div>
          <div class="rk-section-sub">Principle 3: risk surfaces BEFORE targets · Principle 17: mechanical &gt; emotional</div>
        </div>
        <span class="rk-pill ${ks.final_alloc_pct > 5 ? 'gn' : ks.final_alloc_pct > 1 ? 'am' : 'rd'}">FINAL ALLOC: ${ks.final_alloc_pct != null ? ks.final_alloc_pct.toFixed(1) + '%' : '—'}</span>
      </div>
      <div class="rk-section-body">
        <div class="rk-split-2">
          <div class="pat-block">
            <div class="pat-block-h">⚖ Size derivation · Kelly cascade</div>
            <table class="rk-tbl">
              <tbody>
                <tr><td>Full Kelly</td><td class="r"><b class="info">${ks.kelly_pct != null ? ks.kelly_pct.toFixed(1) + '%' : '—'}</b></td><td><span style="font-family:var(--mono);font-size:10px;color:var(--ink-3)">f = p − (1−p)/b</span></td></tr>
                <tr><td>Half Kelly (cap)</td><td class="r"><b class="info">${ks.half_kelly_pct != null ? ks.half_kelly_pct.toFixed(1) + '%' : '—'}</b></td><td><span class="rk-pill info">conservative floor</span></td></tr>
                <tr><td>× Regime multiplier</td><td class="r"><b class="${ks.regime_mult >= 1 ? 'gn' : 'am'}">${ks.regime_mult != null ? ks.regime_mult.toFixed(2) + '×' : '—'}</b></td><td><span class="rk-pill ${ks.regime_mult >= 1 ? 'gn' : 'am'}">${T.regime4 || '—'}</span></td></tr>
                ${ks.vix_mult != null ? `<tr><td>× VIX multiplier</td><td class="r"><b>${ks.vix_mult.toFixed(2)}×</b></td><td><span class="rk-pill info">VIX ${T.market_vix ? T.market_vix.toFixed(0) : '—'}</span></td></tr>` : ''}
                ${ks.drawdown_mult != null ? `<tr><td>× Drawdown multiplier</td><td class="r"><b>${ks.drawdown_mult.toFixed(2)}×</b></td><td><span class="rk-pill info">DD-based</span></td></tr>` : ''}
                ${ks.earnings_mult != null ? `<tr><td>× Earnings multiplier</td><td class="r"><b class="${ks.earnings_mult < 1 ? 'am' : 'gn'}">${ks.earnings_mult.toFixed(2)}×</b></td><td><span class="rk-pill ${ks.earnings_mult < 1 ? 'am' : 'gn'}">${erDays != null ? `ER T-${erDays}` : 'no ER'}</span></td></tr>` : ''}
                ${ks.sharpe_mult != null ? `<tr><td>× Sharpe tilt</td><td class="r"><b>${ks.sharpe_mult.toFixed(2)}×</b></td><td><span class="rk-pill info">126d Sharpe</span></td></tr>` : ''}
                <tr class="spot"><td><b class="copper">Final allocation</b></td><td class="r"><b class="copper">${ks.final_alloc_pct != null ? ks.final_alloc_pct.toFixed(1) + '%' : '—'}</b></td><td><b class="copper">${ks.dollar_risk != null ? '$' + Math.round(ks.dollar_risk).toLocaleString() + ' risk' : '—'} · ${ks.suggested_shares || '—'} shares</b></td></tr>
              </tbody>
            </table>
          </div>
          <div class="pat-block">
            <div class="pat-block-h">⛔ Mechanical exit rules</div>
            <table class="rk-tbl">
              <tbody>
                <tr><td><b class="rd">Stop · close-based</b></td><td class="r"><b>${_fmt$(stop)}</b></td><td><span class="rk-pill rd">−1.25 ATR · daily close only</span></td></tr>
                <tr><td><b class="gn">T1 partial · 50%</b></td><td class="r"><b>${_fmt$(t1)}</b></td><td><span class="rk-pill gn">trim half · stop to BE</span></td></tr>
                <tr><td><b class="gn">T2 close · remainder</b></td><td class="r"><b>${_fmt$(t2)}</b></td><td><span class="rk-pill gn">all out</span></td></tr>
                <tr><td>Trailing stop · activation</td><td class="r"><b>+2% from entry</b></td><td><span style="font-family:var(--mono);font-size:10px;color:var(--ink-3)">close-based · 1.5 ATR trail</span></td></tr>
                ${erDays != null && erDays <= 14 ? `<tr><td><b class="am">ER cutoff · T-1 EOD</b></td><td class="r"><b>Forced exit</b></td><td><span class="rk-pill am">no overnight binary risk</span></td></tr>` : ''}
                <tr><td>Time stop · no T1 in 10d</td><td class="r"><b>D+10</b></td><td><span class="rk-pill">close stale</span></td></tr>
                <tr><td>Wick-based exit</td><td class="r"><b>NEVER</b></td><td><span class="rk-pill gn">close only · no intraday stops</span></td></tr>
              </tbody>
            </table>
          </div>
        </div>
        <div class="rk-note info">
          <b>Process discipline:</b> pre-place limit orders for entry zone, stop-loss on close-based trigger only, scale-out orders at T1/T2. <b>No emotional override</b> — if rules say exit, exit. Judge process, not outcome (principle 20).
        </div>
      </div>
    </section>`;
}

// ── ENTRY POINT ────────────────────────────────────────────────────────────
// Two call patterns:
//   render()                       — elite-detail.html via CapStudio shell
//                                     (target = #chartBody via window.__getDetailTicker)
//   renderInto(targetEl, ticker)   — kairos.html QuantDetail (target + T passed in)
export async function render() {
  const T = _T();
  if (!T) return;
  const target = document.getElementById('chartBody') || document.getElementById('technicalsBody') || document.querySelector('.sec#chart');
  if (!target) return;
  return renderInto(target, T);
}

export async function renderInto(target, T) {
  if (!target || !T) return;
  _ensureStyles();

  // Loading state with hero (which is fully sync)
  target.innerHTML = `<div class="rk-tech-scope">${_buildHero(T, (window.DATA || {}).generated_at)}<div style="padding:30px;text-align:center;color:var(--ink-3);font-family:'JetBrains Mono';font-size:11px;letter-spacing:0.14em">Loading setup stats + ML edge…</div></div>`;

  // Async-fetch setup stats + ml edge predictions in parallel
  const [stats, mlAll] = await Promise.all([_fetchSetupStats(), _fetchMlEdge()]);

  // Full render
  target.innerHTML = `
    <div class="rk-tech-scope">
      ${_buildHero(T, (window.DATA || {}).generated_at)}
      ${_renderIndicators(T)}
      ${_renderEmaStack(T)}
      ${_renderPatterns(T)}
      ${_renderSupportResistance(T)}
      ${_renderVolume(T)}
      ${_renderStatBackbone(T, stats)}
      ${_renderCrossSource(T, mlAll)}
      ${_renderRegimeConditional(T, stats)}
      ${_renderPreMortem(T)}
      ${_renderSizingExits(T)}
      <div class="rk-footer">
        Technicals lens · <span class="copper">10 sections · live bundle + ML Edge + setup_stats</span><br>
        <span style="font-size: 9.5px; color: var(--ink-4); margin-top: 6px; display: inline-block;">
          Hedge-fund quant mindset · Wilson LB acts · mechanism &gt; correlation · risk before return · regime over averages · pre-mortem before BUY
        </span>
      </div>
    </div>`;
}

export function dispose() { /* no-op */ }

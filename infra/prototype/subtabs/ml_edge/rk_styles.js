// subtabs/ml_edge/rk_styles.js — Bloomberg-terminal aesthetic CSS, scoped under .rk-scope.
//
// Single source of truth for the risk-redesign primitives used across the ml_edge
// sub-modules. Injected once by ml_edge.js into <head> via <style id="ml-edge-rk-styles">.
//
// Scoping: every selector lives under .rk-scope so this won't leak into other
// sub-tabs until we promote these tokens into a global kairos.css.

export const RK_STYLES = `
.rk-scope {
  --bg: #0a0d0c; --bg-1: #11151a; --bg-2: #161a1e; --bg-3: #1c2125;
  --line: #262b2d; --line-2: #353a3c;
  --ink: #ecefe9; --ink-1: #d4d8d1; --ink-2: #9a9e98; --ink-3: #686c68; --ink-4: #444947;
  --gn: #4ade80; --gn-dim: #166534; --gn-bg: rgba(74,222,128,0.10);
  --rd: #f87171; --rd-dim: #991b1b; --rd-bg: rgba(248,113,113,0.10);
  --amb: #fbbf24; --amb-dim: #92400e; --amb-bg: rgba(251,191,36,0.10);
  --info: #60a5fa; --info-dim: #1e40af; --info-bg: rgba(96,165,250,0.10);
  --violet: #a78bfa; --violet-dim: #5b21b6; --violet-bg: rgba(167,139,250,0.10);
  --copper: #d97757; --copper-bg: rgba(217,119,87,0.10);
  --mono: 'JetBrains Mono', ui-monospace, monospace;
  font: 14px/1.5 -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  color: var(--ink); font-variant-numeric: tabular-nums;
}
.rk-scope * { box-sizing: border-box; }

/* HERO ------------------------------------------------------------- */
.rk-scope .rk-hero { background: var(--bg-1); border: 1px solid var(--gn-dim); border-left: 4px solid var(--gn); border-radius: 2px; margin-bottom: 14px; overflow: hidden; font-family: var(--mono); }
.rk-scope .rk-hero.rd { border-color: var(--rd-dim); border-left-color: var(--rd); }
.rk-scope .rk-hero.am { border-color: var(--amb-dim); border-left-color: var(--amb); }
.rk-scope .rk-hero.info { border-color: var(--info-dim); border-left-color: var(--info); }
.rk-scope .rk-hero-banner { display: flex; align-items: center; gap: 14px; padding: 10px 18px; background: var(--gn-bg); border-bottom: 1px solid var(--gn-dim); flex-wrap: wrap; }
.rk-scope .rk-hero.rd .rk-hero-banner { background: var(--rd-bg); border-bottom-color: var(--rd-dim); }
.rk-scope .rk-hero.am .rk-hero-banner { background: var(--amb-bg); border-bottom-color: var(--amb-dim); }
.rk-scope .rk-hero.info .rk-hero-banner { background: var(--info-bg); border-bottom-color: var(--info-dim); }
.rk-scope .rk-hero-badge { font-size: 14px; font-weight: 800; letter-spacing: 0.14em; padding: 4px 12px; border-radius: 2px; color: var(--gn); border: 1px solid var(--gn-dim); background: rgba(74,222,128,0.06); }
.rk-scope .rk-hero.rd .rk-hero-badge { color: var(--rd); border-color: var(--rd-dim); background: rgba(248,113,113,0.06); }
.rk-scope .rk-hero.am .rk-hero-badge { color: var(--amb); border-color: var(--amb-dim); background: rgba(251,191,36,0.06); }
.rk-scope .rk-hero.info .rk-hero-badge { color: var(--info); border-color: var(--info-dim); background: rgba(96,165,250,0.06); }
.rk-scope .rk-hero-q { font: 600 12px var(--mono); color: var(--ink-1); letter-spacing: 0.04em; }
.rk-scope .rk-hero-q b { color: var(--ink); }
.rk-scope .rk-hero-q .copper { color: var(--copper); }
.rk-scope .rk-hero-tk { margin-left: auto; font: 800 18px var(--mono); color: var(--ink); letter-spacing: 0.06em; }
.rk-scope .rk-hero-tk small { font-size: 10px; color: var(--ink-3); margin-left: 6px; letter-spacing: 0.10em; }

.rk-scope .rk-hero-body { display: grid; grid-template-columns: 1.6fr 1.4fr 1fr; gap: 0; }
.rk-scope .rk-hero-cone { padding: 14px 18px; border-right: 1px solid var(--line); }
.rk-scope .rk-hero-cone-h { font: 700 10px var(--mono); color: var(--ink-3); letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 6px; display: flex; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.rk-scope .rk-hero-cone-h .legend { color: var(--ink-2); font-weight: 500; }
.rk-scope .rk-hero-cone-h .legend i { display: inline-block; width: 8px; height: 8px; margin-right: 4px; vertical-align: middle; border-radius: 1px; }
.rk-scope .rk-hero-cone svg { width: 100%; height: 220px; display: block; }

.rk-scope .rk-hero-gauges { padding: 14px 14px; border-right: 1px solid var(--line); display: grid; grid-template-rows: auto 1fr; }
.rk-scope .rk-hero-gauges-h { font: 700 10px var(--mono); color: var(--ink-3); letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 10px; }
.rk-scope .rk-hero-gauges-grid { display: grid; grid-template-columns: 1fr; gap: 8px; }
.rk-scope .rk-gauge { border: 1px solid var(--line); border-radius: 2px; padding: 10px 12px; background: var(--bg-2); }
.rk-scope .rk-gauge.dir { border-color: var(--info-dim); background: rgba(96,165,250,0.04); }
.rk-scope .rk-gauge.mag { border-color: var(--violet-dim); background: rgba(167,139,250,0.04); }
.rk-scope .rk-gauge.hit { border-color: var(--gn-dim); background: rgba(74,222,128,0.04); }
.rk-scope .rk-gauge-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 6px; gap: 6px; }
.rk-scope .rk-gauge-k { font: 700 9px var(--mono); color: var(--ink-3); letter-spacing: 0.12em; text-transform: uppercase; }
.rk-scope .rk-gauge.dir .rk-gauge-k { color: var(--info); }
.rk-scope .rk-gauge.mag .rk-gauge-k { color: var(--violet); }
.rk-scope .rk-gauge.hit .rk-gauge-k { color: var(--gn); }
.rk-scope .rk-gauge-status { font: 700 9px var(--mono); letter-spacing: 0.10em; padding: 1px 6px; border-radius: 2px; white-space: nowrap; }
.rk-scope .rk-gauge-status.pass { color: var(--gn); background: var(--gn-bg); border: 1px solid var(--gn-dim); }
.rk-scope .rk-gauge-status.warn { color: var(--amb); background: var(--amb-bg); border: 1px solid var(--amb-dim); }
.rk-scope .rk-gauge-status.fail { color: var(--rd); background: var(--rd-bg); border: 1px solid var(--rd-dim); }
.rk-scope .rk-gauge-status.info { color: var(--info); background: var(--info-bg); border: 1px solid var(--info-dim); }
.rk-scope .rk-gauge-row { display: flex; align-items: baseline; gap: 8px; }
.rk-scope .rk-gauge-v { font: 800 22px var(--mono); line-height: 1.05; }
.rk-scope .rk-gauge.dir .rk-gauge-v { color: var(--info); }
.rk-scope .rk-gauge.mag .rk-gauge-v { color: var(--violet); }
.rk-scope .rk-gauge.hit .rk-gauge-v { color: var(--gn); }
.rk-scope .rk-gauge-sub { font: 600 10px var(--mono); color: var(--ink-2); letter-spacing: 0.06em; }
.rk-scope .rk-gauge-bar { height: 4px; background: var(--bg-3); border-radius: 1px; margin-top: 6px; overflow: hidden; }
.rk-scope .rk-gauge-bar > div { height: 100%; }
.rk-scope .rk-gauge.dir .rk-gauge-bar > div { background: var(--info); }
.rk-scope .rk-gauge.mag .rk-gauge-bar > div { background: var(--violet); }
.rk-scope .rk-gauge.hit .rk-gauge-bar > div { background: var(--gn); }
.rk-scope .rk-gauge-foot { font: 500 10px var(--mono); color: var(--ink-3); margin-top: 5px; letter-spacing: 0.02em; line-height: 1.4; }

.rk-scope .rk-cap-matrix { padding: 14px 16px; }
.rk-scope .rk-cap-h { font: 700 10px var(--mono); color: var(--ink-3); letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 8px; }
.rk-scope .rk-cap-row { display: grid; grid-template-columns: 1fr 64px; gap: 8px; align-items: center; padding: 5px 0; border-bottom: 1px dashed var(--line); font-size: 11px; font-family: var(--mono); }
.rk-scope .rk-cap-row:last-child { border-bottom: none; }
.rk-scope .rk-cap-lbl { font: 600 10px var(--mono); color: var(--ink-2); letter-spacing: 0.06em; text-transform: uppercase; }
.rk-scope .rk-cap-val { text-align: right; font: 700 12px var(--mono); color: var(--ink); }
.rk-scope .rk-cap-val.am { color: var(--amb); }
.rk-scope .rk-cap-val.rd { color: var(--rd); }
.rk-scope .rk-cap-val.gn { color: var(--gn); }
.rk-scope .rk-cap-val.info { color: var(--info); }
.rk-scope .rk-cap-val.violet { color: var(--violet); }
.rk-scope .rk-cap-bar { grid-column: 1 / -1; height: 5px; background: var(--bg-3); border-radius: 1px; overflow: hidden; margin-top: 2px; }
.rk-scope .rk-cap-bar > div { height: 100%; }
.rk-scope .rk-cap-bar > div.gn { background: var(--gn); }
.rk-scope .rk-cap-bar > div.am { background: var(--amb); }
.rk-scope .rk-cap-bar > div.rd { background: var(--rd); }
.rk-scope .rk-cap-bar > div.info { background: var(--info); }
.rk-scope .rk-cap-bar > div.violet { background: var(--violet); }

.rk-scope .rk-hero-foot { padding: 9px 18px; background: var(--bg-2); border-top: 1px solid var(--line); display: flex; gap: 18px; flex-wrap: wrap; font: 600 11px var(--mono); color: var(--ink-2); letter-spacing: 0.04em; }
.rk-scope .rk-hero-foot b { color: var(--ink); font-weight: 700; }
.rk-scope .rk-hero-foot .rd { color: var(--rd); }
.rk-scope .rk-hero-foot .am { color: var(--amb); }
.rk-scope .rk-hero-foot .gn { color: var(--gn); }
.rk-scope .rk-hero-foot .info { color: var(--info); }

/* SECTIONS --------------------------------------------------------- */
.rk-scope .rk-section { background: var(--bg-1); border: 1px solid var(--line); border-radius: 2px; margin-bottom: 12px; overflow: hidden; }
.rk-scope .rk-section-head { padding: 10px 18px 8px; border-bottom: 1px solid var(--line); display: flex; justify-content: space-between; align-items: baseline; gap: 12px; flex-wrap: wrap; }
.rk-scope .rk-section-title { font: 700 12px var(--mono); color: var(--ink-2); letter-spacing: 0.14em; text-transform: uppercase; }
.rk-scope .rk-section-title .num { color: var(--copper); margin-right: 6px; }
.rk-scope .rk-section-sub { font: 500 11px var(--mono); color: var(--ink-3); margin-top: 2px; letter-spacing: 0.06em; }
.rk-scope .rk-section-body { padding: 14px 18px 16px; }

.rk-scope .rk-chart-card { background: var(--bg-2); border: 1px solid var(--line); border-radius: 2px; padding: 10px 12px; }
.rk-scope .rk-chart-card.dir { border-top: 2px solid var(--info); }
.rk-scope .rk-chart-card.mag { border-top: 2px solid var(--violet); }
.rk-scope .rk-chart-card.hit { border-top: 2px solid var(--gn); }
.rk-scope .rk-chart-title { font: 700 10px var(--mono); color: var(--ink-3); letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 8px; display: flex; justify-content: space-between; flex-wrap: wrap; gap: 6px; }
.rk-scope .rk-chart-title .legend { color: var(--ink-2); font-weight: 500; }
.rk-scope .rk-chart-title .legend i { display: inline-block; width: 8px; height: 8px; margin-right: 4px; vertical-align: middle; border-radius: 1px; }

/* Splits */
.rk-scope .rk-split-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.rk-scope .rk-split-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.rk-scope .rk-split-32 { display: grid; grid-template-columns: 3fr 2fr; gap: 12px; }
.rk-scope .rk-split-1-2-1 { display: grid; grid-template-columns: 1.05fr 1.5fr 1.05fr; gap: 12px; }
@media (max-width: 980px) {
  .rk-scope .rk-split-3,
  .rk-scope .rk-split-2,
  .rk-scope .rk-split-32,
  .rk-scope .rk-split-1-2-1 { grid-template-columns: 1fr; }
  .rk-scope .rk-hero-body { grid-template-columns: 1fr; }
}

/* Tables */
.rk-scope table.rk-tbl { width: 100%; border-collapse: collapse; font-family: var(--mono); font-size: 12px; }
.rk-scope table.rk-tbl th { text-align: left; padding: 6px 8px; font-size: 10px; color: var(--ink-3); letter-spacing: 0.12em; text-transform: uppercase; border-bottom: 1px solid var(--line); font-weight: 700; }
.rk-scope table.rk-tbl th.r { text-align: right; }
.rk-scope table.rk-tbl td { padding: 8px 8px; border-bottom: 1px solid var(--line); color: var(--ink-1); font-size: 12px; }
.rk-scope table.rk-tbl td.r { text-align: right; }
.rk-scope table.rk-tbl tr:last-child td { border-bottom: none; }
.rk-scope table.rk-tbl tr.sel td { background: rgba(74,222,128,0.06); box-shadow: inset 2px 0 0 var(--gn); }
.rk-scope table.rk-tbl tr.bear td { background: rgba(248,113,113,0.04); }
.rk-scope table.rk-tbl b.gn { color: var(--gn); }
.rk-scope table.rk-tbl b.rd { color: var(--rd); }
.rk-scope table.rk-tbl b.am { color: var(--amb); }
.rk-scope table.rk-tbl b.ink { color: var(--ink); }

/* Pills */
.rk-scope .rk-pill { display: inline-block; padding: 2px 7px; font: 700 9px var(--mono); letter-spacing: 0.08em; text-transform: uppercase; border-radius: 2px; background: var(--bg-2); border: 1px solid var(--line-2); color: var(--ink-2); }
.rk-scope .rk-pill.gn { color: var(--gn); border-color: var(--gn-dim); background: var(--gn-bg); }
.rk-scope .rk-pill.rd { color: var(--rd); border-color: var(--rd-dim); background: var(--rd-bg); }
.rk-scope .rk-pill.am { color: var(--amb); border-color: var(--amb-dim); background: var(--amb-bg); }
.rk-scope .rk-pill.info { color: var(--info); border-color: var(--info-dim); background: var(--info-bg); }
.rk-scope .rk-pill.violet { color: var(--violet); border-color: var(--violet-dim); background: var(--violet-bg); }

/* Notes */
.rk-scope .rk-note { margin-top: 10px; padding: 8px 12px; border-left: 2px solid var(--ink-4); background: var(--bg-2); border-radius: 0 2px 2px 0; font-size: 12px; color: var(--ink-2); line-height: 1.55; }
.rk-scope .rk-note.rd { border-left-color: var(--rd); }
.rk-scope .rk-note.am { border-left-color: var(--amb); }
.rk-scope .rk-note.gn { border-left-color: var(--gn); }
.rk-scope .rk-note.info { border-left-color: var(--info); }
.rk-scope .rk-note b { color: var(--ink); }

/* Direction tiles */
.rk-scope .rk-dir-tiles { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 12px; }
.rk-scope .rk-dir-tile { padding: 10px 12px; border: 1px solid; border-radius: 2px; font-family: var(--mono); }
.rk-scope .rk-dir-tile.up { background: rgba(74,222,128,0.05); border-color: var(--gn-dim); }
.rk-scope .rk-dir-tile.dn { background: rgba(248,113,113,0.05); border-color: var(--rd-dim); }
.rk-scope .rk-dir-tile-k { font: 700 9px var(--mono); letter-spacing: 0.12em; text-transform: uppercase; margin-bottom: 4px; }
.rk-scope .rk-dir-tile.up .rk-dir-tile-k { color: var(--gn); }
.rk-scope .rk-dir-tile.dn .rk-dir-tile-k { color: var(--rd); }
.rk-scope .rk-dir-tile-v { font: 800 22px var(--mono); line-height: 1; }
.rk-scope .rk-dir-tile.up .rk-dir-tile-v { color: var(--gn); }
.rk-scope .rk-dir-tile.dn .rk-dir-tile-v { color: var(--rd); }
.rk-scope .rk-dir-tile-sub { font: 600 10px var(--mono); color: var(--ink-3); margin-top: 4px; letter-spacing: 0.04em; }

/* Skew bar */
.rk-scope .rk-skew { padding: 10px 12px; background: var(--bg-2); border-radius: 2px; border: 1px solid var(--line); margin-bottom: 12px; font-family: var(--mono); }
.rk-scope .rk-skew-row { display: flex; align-items: center; justify-content: space-between; font: 600 10px var(--mono); margin-bottom: 6px; }
.rk-scope .rk-skew-row .lbl-inline { color: var(--ink-3); letter-spacing: 0.10em; text-transform: uppercase; }
.rk-scope .rk-skew-track { height: 7px; background: var(--bg-3); border-radius: 1px; overflow: hidden; display: flex; position: relative; }
.rk-scope .rk-skew-up { background: var(--gn); height: 100%; }
.rk-scope .rk-skew-dn { background: var(--rd); height: 100%; }
.rk-scope .rk-skew-mid { position: absolute; left: 50%; top: -2px; bottom: -2px; width: 1px; background: var(--line-2); }
.rk-scope .rk-skew-note { font: 500 10px var(--mono); color: var(--ink-3); margin-top: 5px; line-height: 1.4; }

/* Level-hit rows */
.rk-scope .rk-lvl-row { display: grid; grid-template-columns: 90px 64px 1fr 44px; gap: 10px; align-items: center; padding: 7px 0; border-bottom: 1px dashed var(--line); font-size: 12px; font-family: var(--mono); }
.rk-scope .rk-lvl-row:last-child { border-bottom: none; }
.rk-scope .rk-lvl-label { color: var(--ink-1); font-weight: 600; }
.rk-scope .rk-lvl-label.gn { color: var(--gn); }
.rk-scope .rk-lvl-label.rd { color: var(--rd); }
.rk-scope .rk-lvl-label.dim { color: var(--ink-3); }
.rk-scope .rk-lvl-px { color: var(--ink-3); font-size: 11px; text-align: right; }
.rk-scope .rk-lvl-track { height: 5px; background: var(--bg-3); border-radius: 1px; overflow: hidden; }
.rk-scope .rk-lvl-fill { height: 100%; }
.rk-scope .rk-lvl-fill.gn { background: var(--gn); }
.rk-scope .rk-lvl-fill.rd { background: var(--rd); }
.rk-scope .rk-lvl-fill.dim { background: var(--ink-3); }
.rk-scope .rk-lvl-val { font-size: 11px; text-align: right; font-weight: 700; }
.rk-scope .rk-lvl-val.gn { color: var(--gn); }
.rk-scope .rk-lvl-val.rd { color: var(--rd); }
.rk-scope .rk-lvl-val.dim { color: var(--ink-3); }

/* Column titles */
.rk-scope .rk-coltitle { font: 700 10px var(--mono); color: var(--ink-3); letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 8px; }
.rk-scope .rk-coltitle.gn { color: var(--gn); }
.rk-scope .rk-coltitle.rd { color: var(--rd); }

/* SHAP feature rows */
.rk-scope .rk-feat-row { display: grid; grid-template-columns: 130px 1fr 56px; gap: 10px; align-items: center; padding: 5px 0; font-family: var(--mono); font-size: 11px; }
.rk-scope .rk-feat-name { color: var(--ink-1); }
.rk-scope .rk-feat-bar { height: 5px; background: var(--bg-3); border-radius: 1px; position: relative; overflow: hidden; }
.rk-scope .rk-feat-fill { position: absolute; top: 0; height: 100%; }
.rk-scope .rk-feat-fill.pos { background: var(--gn); left: 50%; }
.rk-scope .rk-feat-fill.neg { background: var(--rd); right: 50%; }
.rk-scope .rk-feat-mid { position: absolute; left: 50%; top: -2px; bottom: -2px; width: 1px; background: var(--line-2); }
.rk-scope .rk-feat-val { text-align: right; font-weight: 700; font-size: 11px; }
.rk-scope .rk-feat-val.pos { color: var(--gn); }
.rk-scope .rk-feat-val.neg { color: var(--rd); }

/* Footer */
.rk-scope .rk-footer { margin-top: 20px; padding: 10px 14px; border-top: 1px solid var(--line); font: 600 11px var(--mono); color: var(--ink-3); letter-spacing: 0.08em; text-align: center; }
.rk-scope .rk-footer .copper { color: var(--copper); }

/* SVG helpers (need to override SVG inheritance) */
.rk-scope .axis { stroke: var(--line-2); stroke-width: 1; }
.rk-scope .grid { stroke: var(--line); stroke-dasharray: 2,3; stroke-width: 0.5; }
.rk-scope .lbl { fill: var(--ink-3); font: 600 9px var(--mono); }
.rk-scope .vlbl { fill: var(--ink-2); font: 700 10px var(--mono); }

/* ── Cross-horizon comparison strip (added 2026-05-16) ───────────────────── */
.rk-scope .rk-cross-section { margin: 14px 0 16px; }
.rk-scope .rk-cross-banner {
  padding: 8px 14px; border-radius: 2px; font: 700 11px var(--mono);
  letter-spacing: 0.08em; margin-bottom: 8px; border: 1px solid var(--line);
  background: var(--bg-2); color: var(--ink-2);
}
.rk-scope .rk-cross-banner.gn { background: var(--gn-bg); border-color: var(--gn-dim); color: var(--gn); }
.rk-scope .rk-cross-banner.rd { background: var(--rd-bg); border-color: var(--rd-dim); color: var(--rd); }
.rk-scope .rk-cross-banner.am { background: var(--amb-bg); border-color: var(--amb-dim); color: var(--amb); }
.rk-scope .rk-cross-banner.info { background: var(--info-bg); border-color: var(--info-dim); color: var(--info); }
.rk-scope .rk-cross-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.rk-scope .rk-cross-card {
  background: var(--bg-1); border: 1px solid var(--line); border-top: 3px solid var(--ink-4);
  border-radius: 2px; padding: 10px 14px; font-family: var(--mono);
}
.rk-scope .rk-cross-card.gn { border-top-color: var(--gn); }
.rk-scope .rk-cross-card.rd { border-top-color: var(--rd); }
.rk-scope .rk-cross-card.am { border-top-color: var(--amb); }
.rk-scope .rk-cross-card.info { border-top-color: var(--info); }
.rk-scope .rk-cross-card.empty { opacity: 0.4; }
.rk-scope .rk-cross-h {
  font: 700 10px var(--mono); color: var(--ink-3); letter-spacing: 0.12em;
  text-transform: uppercase; margin-bottom: 4px;
}
.rk-scope .rk-cross-verdict {
  font: 800 18px var(--mono); letter-spacing: -0.01em; margin-bottom: 8px;
  padding-bottom: 6px; border-bottom: 1px dashed var(--line);
}
.rk-scope .rk-cross-verdict.gn { color: var(--gn); }
.rk-scope .rk-cross-verdict.rd { color: var(--rd); }
.rk-scope .rk-cross-verdict.am { color: var(--amb); }
.rk-scope .rk-cross-verdict.info { color: var(--info); }
.rk-scope .rk-cross-row {
  display: grid; grid-template-columns: 1fr auto; gap: 6px; padding: 3px 0;
  font: 600 11px var(--mono); color: var(--ink-2);
}
.rk-scope .rk-cross-row b { color: var(--ink); }
.rk-scope .rk-cross-row b.gn { color: var(--gn); }
.rk-scope .rk-cross-row b.rd { color: var(--rd); }
.rk-scope .rk-cross-row b.am { color: var(--amb); }
.rk-scope .rk-cross-empty {
  font: 500 11px var(--mono); color: var(--ink-3); padding: 12px 0;
  text-align: center; letter-spacing: 0.06em;
}
`;

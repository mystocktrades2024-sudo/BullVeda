// subtabs/research/research.js — extracted from elite-detail.html (renderResearchDetail 2026-05-09)
// CapStudio modular loader for the per-ticker detail page.
// T (current ticker) accessed via window.__getDetailTicker() — NOT yet wired
// in elite-detail.html. This module is created as a candidate for future
// activation; calling render() before wiring requires window.T to be set.

const _T = () => (window.__getDetailTicker ? window.__getDetailTicker() : window.T);

export function render() {
  const T = _T();
  const body = document.getElementById('researchSecBody');
  if (!body || !T) return;
  const tabs = RD_TABS.map(([k, lbl, st]) => {
    const dot = st === 'live' ? '✓' : st === 'partial' ? '⚠' : st === 'mock' ? '🚧' : '🛠';
    const dc  = st === 'live' ? 'var(--pass)' : st === 'partial' ? 'var(--warn)' : st === 'mock' ? 'var(--purple,#a78bfa)' : 'var(--ink-3)';
    return `<button class="rd-tab" data-rd="${k}" onclick="rdSwitch('${k}')">${lbl} <span style="color:${dc};">${dot}</span></button>`;
  }).join('');
  body.innerHTML = `
    <div id="rdTabs" style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:14px;padding:10px 12px;background:var(--bg-1);border:1px solid var(--rule);border-radius:8px;">${tabs}</div>
    <div id="rdContent" style="background:var(--bg-1);border:1px solid var(--rule);border-radius:8px;min-height:380px;padding:18px 22px;"></div>
    <style>
      .rd-tab { background: var(--bg-2); border: 1px solid var(--rule-2); color: var(--ink-1);
                padding: 6px 11px; font-size: 11px; font-weight: 600; letter-spacing: 0.04em;
                border-radius: 5px; cursor: pointer; font-family: var(--mono); transition: all 0.15s; }
      .rd-tab:hover { border-color: var(--accent); color: var(--ink-0); }
      .rd-tab.on    { background: var(--accent); border-color: var(--accent); color: var(--bg-0); }
      .rd-card { background: var(--bg-2); border-radius: 8px; padding: 16px 20px; margin-bottom: 14px; }
      .rd-card h4 { margin: 0 0 10px; font-size: 13px; color: var(--ink-2); letter-spacing: 0.05em; text-transform: uppercase; font-weight: 700;
                     display: flex; align-items: center; gap: 8px; }
      .rd-card h4::before { content: ''; width: 5px; height: 5px; background: var(--accent); border-radius: 50%; }
      .rd-narr { background: color-mix(in oklch, var(--accent) 10%, var(--bg-2)); border-left: 3px solid var(--accent);
                  padding: 11px 14px; margin: 8px 0 14px; border-radius: 0 5px 5px 0;
                  font-size: 12.5px; line-height: 1.6; color: var(--ink-1); }
      .rd-narr b { color: var(--accent); }
      .rd-warn { background: color-mix(in oklch, var(--warn) 10%, var(--bg-2)); border-left: 3px solid var(--warn);
                  padding: 11px 14px; margin: 8px 0 14px; border-radius: 0 5px 5px 0;
                  font-size: 12.5px; line-height: 1.6; color: var(--ink-1); }
      .rd-good { background: color-mix(in oklch, var(--pass) 10%, var(--bg-2)); border-left: 3px solid var(--pass);
                  padding: 11px 14px; margin: 8px 0 14px; border-radius: 0 5px 5px 0;
                  font-size: 12.5px; line-height: 1.6; color: var(--ink-1); }
      .rd-kpi { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; }
      .rd-kpi-cell { background: var(--bg-1); border-top: 2.5px solid var(--accent); padding: 11px 14px;
                      border-radius: 6px; transition: transform 0.15s; }
      .rd-kpi-cell:hover { transform: translateY(-1px); }
      .rd-kpi-cell.pos { border-top-color: var(--pass); }
      .rd-kpi-cell.neg { border-top-color: var(--fail); }
      .rd-kpi-cell.warn { border-top-color: var(--warn); }
      .rd-kpi-cell.purple { border-top-color: var(--purple, #a78bfa); }
      .rd-kpi-cell .l { font-size: 9.5px; color: var(--ink-3); letter-spacing: 0.06em; text-transform: uppercase; font-weight: 600; }
      .rd-kpi-cell .v { font-family: var(--mono); font-size: 18px; font-weight: 800; margin-top: 4px; color: var(--ink-0);
                         font-variant-numeric: tabular-nums; }
      .rd-kpi-cell .s { font-size: 10px; color: var(--ink-2); margin-top: 3px; line-height: 1.4; }

      /* Forest-plot rows (rigor, signal-decay) */
      .rd-fp { display: grid; grid-template-columns: 180px 1fr 100px; gap: 12px; align-items: center;
                padding: 9px 0; border-bottom: 1px solid color-mix(in oklch, var(--rule-2) 30%, transparent); }
      .rd-fp:last-child { border-bottom: none; }
      .rd-fp .nm { font-family: var(--mono); font-size: 12px; color: var(--ink-0); }
      .rd-fp .nm small { color: var(--ink-3); font-weight: 400; }
      .rd-fp .ci { position: relative; height: 22px; background: var(--bg-3); border-radius: 4px; }
      .rd-fp .ci::before { content: ''; position: absolute; left: 50%; top: 0; bottom: 0; width: 1px;
                            background: var(--ink-3); opacity: 0.4; }
      .rd-fp .band { position: absolute; height: 14px; top: 4px; border-radius: 3px; opacity: 0.5; }
      .rd-fp .point { position: absolute; width: 10px; height: 10px; top: 6px; border-radius: 50%;
                       border: 2px solid var(--bg-1); }
      .rd-fp .band.pass { background: var(--pass); }
      .rd-fp .band.warn { background: var(--warn); }
      .rd-fp .band.fail { background: var(--fail); }
      .rd-fp .band.info { background: var(--accent); }
      .rd-fp .point.pass { background: var(--pass); }
      .rd-fp .point.warn { background: var(--warn); }
      .rd-fp .point.fail { background: var(--fail); }
      .rd-fp .point.info { background: var(--accent); }
      .rd-fp .v { font-family: var(--mono); font-size: 11px; color: var(--ink-1); text-align: right; }
      .rd-fp-axis { display: grid; grid-template-columns: 180px 1fr 100px; gap: 12px;
                     padding: 4px 0; margin-bottom: 8px; font-family: var(--mono); font-size: 10px; color: var(--ink-3); }
      .rd-fp-axis .ticks { display: flex; justify-content: space-between; }

      /* SHAP-style waterfall rows */
      .rd-wf { display: grid; grid-template-columns: 200px 1fr 80px; gap: 12px; align-items: center;
                padding: 7px 0; font-size: 12px; border-bottom: 1px solid color-mix(in oklch, var(--rule-2) 30%, transparent); }
      .rd-wf:last-child { border-bottom: none; }
      .rd-wf .lbl { font-family: var(--mono); color: var(--ink-1); }
      .rd-wf .barc { position: relative; height: 16px; background: var(--bg-3); border-radius: 3px; overflow: hidden; }
      .rd-wf .barc::after { content: ''; position: absolute; left: 50%; top: 0; bottom: 0; width: 1px; background: var(--ink-3); opacity: 0.3; }
      .rd-wf .b { position: absolute; height: 100%; }
      .rd-wf .b.pos { background: var(--pass); left: 50%; }
      .rd-wf .b.neg { background: var(--fail); right: 50%; }
      .rd-wf .v { font-family: var(--mono); font-weight: 800; text-align: right; font-size: 12px; }
      .rd-wf .v.pos { color: var(--pass); }
      .rd-wf .v.neg { color: var(--fail); }
      .rd-wf .v.dim { color: var(--ink-3); }

      /* Threshold counterfactual (counter sub-tab) */
      .rd-thr { display: grid; grid-template-columns: 1fr 60px 60px; gap: 12px; align-items: center;
                 padding: 8px 12px; margin: 4px 0; border-radius: 5px; font-family: var(--mono); font-size: 12px; }
      .rd-thr.taken { background: color-mix(in oklch, var(--pass) 10%, var(--bg-2)); }
      .rd-thr.skipped { background: color-mix(in oklch, var(--ink-3) 8%, var(--bg-2)); color: var(--ink-3); }
      .rd-thr .label { color: var(--ink-1); }
      .rd-thr.taken .label { color: var(--ink-0); }
      .rd-thr .v { color: var(--ink-2); }
      .rd-thr .icon { text-align: right; font-weight: 800; }
      .rd-thr.taken .icon { color: var(--pass); }
      .rd-thr.skipped .icon { color: var(--ink-3); }

      /* Catalyst tag pill */
      .rd-tag { display: inline-block; background: var(--accent); color: var(--bg-0); padding: 3px 9px;
                 border-radius: 3px; font-size: 10px; font-weight: 800; letter-spacing: 0.05em;
                 margin-right: 5px; margin-bottom: 4px; }
      .rd-tag.warn { background: var(--warn); }
      .rd-tag.purple { background: var(--purple, #a78bfa); }

      /* Status header strip */
      .rd-hdr { display: flex; align-items: baseline; gap: 14px; margin-bottom: 14px; padding: 10px 14px;
                 background: var(--bg-2); border-radius: 6px; font-size: 12px; }
      .rd-hdr .ticker { font-family: var(--mono); font-size: 16px; font-weight: 800; color: var(--accent); }
      .rd-hdr .meta { color: var(--ink-2); }

      .rd-soon { padding: 40px 30px; text-align: center; color: var(--ink-3); font-size: 12.5px; line-height: 1.7;
                  background: var(--bg-2); border-radius: 6px; border: 1px dashed var(--rule-2); }
      .rd-soon .icon { font-size: 36px; margin-bottom: 12px; }
      .rd-soon .title { color: var(--ink-1); font-size: 14px; font-weight: 700; margin-bottom: 8px; }
    </style>`;
  rdSwitch('rigor');
}

export function dispose() { /* no-op */ }

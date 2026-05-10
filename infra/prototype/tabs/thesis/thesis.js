// tabs/thesis/thesis.js — extracted from dashboard.html (renderThesisLibrary 2026-05-09)
// CapStudio modular loader. DATA accessed via getData() from core/shared.js.
// Window-bound helpers (function declarations) referenced as window.X where needed.
import { getData, $ } from '../../core/shared.js';

export async function render() {
  const DATA = getData();
  const body = document.getElementById('thesisBody');
  const meta = document.getElementById('thesisMeta');
  const sbCt = document.getElementById('sbThesisCt');
  const fsCt = document.getElementById('fsThesisCt');
  if (!body) return;
  body.innerHTML = `<div style="padding:24px;color:var(--ink-3);font-size:13px;">Loading theses…</div>`;

  let tickersData = {};
  try { tickersData = await _getTickers(); } catch (_e) {}
  // Use thesis_card (structured) — legacy "thesis" was a string for Overview strip
  const rows = Object.values(tickersData || {}).filter(r => {
    const tc = r && (r.thesis_card || (typeof r.thesis === 'object' ? r.thesis : null));
    return tc && !tc.error;
  });
  if (sbCt) sbCt.textContent = rows.length;
  if (fsCt) fsCt.textContent = rows.length;
  if (!rows.length) {
    body.innerHTML = `<div style="padding:24px;color:var(--ink-3);font-size:13px;">No theses available — re-run scan + build_data.py.</div>`;
    return;
  }
  if (meta) meta.textContent = `${rows.length} ticker${rows.length === 1 ? '' : 's'} · click any card to expand full thesis`;

  // Group by mode preference: prefer position_verdict if BUY, else invest_verdict, else swing
  // We'll show three columns: Swing / Position / Invest. Each gets all tickers
  // routed by which mode flagged them BUY (or WATCH if no BUYs).
  const modes = { Swing: [], Position: [], Invest: [] };
  for (const r of rows) {
    // route to ALL modes where it's surfaced as BUY/WATCH
    const swingV    = (r.swing_verdict || r.verdict || '').toUpperCase();
    const positionV = (r.position_verdict || '').toUpperCase();
    const investV   = (r.invest_verdict || '').toUpperCase();
    if (swingV === 'BUY' || swingV === 'WATCH') modes.Swing.push(r);
    if (positionV === 'BUY' || positionV === 'WATCH') modes.Position.push(r);
    if (investV === 'BUY' || investV === 'WATCH') modes.Invest.push(r);
  }
  const _tcScore = (r) => {
    const tc = r.thesis_card || (typeof r.thesis === 'object' ? r.thesis : null) || {};
    return tc.score || 0;
  };
  for (const k of Object.keys(modes)) modes[k].sort((a,b) => _tcScore(b) - _tcScore(a));

  let html = '';
  // Toolbar
  html += `<div style="display:flex;gap:10px;align-items:center;margin-bottom:14px;flex-wrap:wrap;font-family:var(--mono);font-size:11px;">
    <input id="_thFilter" type="text" placeholder="Filter ticker / sector…" style="flex:1;min-width:220px;padding:7px 10px;background:var(--bg-2);border:1px solid var(--rule-2);border-radius:5px;color:var(--ink-0);font-family:inherit;">
    <select id="_thVerdict" style="padding:7px 10px;background:var(--bg-2);border:1px solid var(--rule-2);border-radius:5px;color:var(--ink-1);font-family:inherit;">
      <option value="">All verdicts</option><option value="BUY">BUY only</option><option value="WATCH">WATCH only</option>
    </select>
    <select id="_thMin" style="padding:7px 10px;background:var(--bg-2);border:1px solid var(--rule-2);border-radius:5px;color:var(--ink-1);font-family:inherit;">
      <option value="0">Score ≥ 0</option><option value="60">Score ≥ 60</option><option value="70">Score ≥ 70</option><option value="80">Score ≥ 80</option>
    </select>
  </div>`;

  html += `<div id="_thGrid" style="display:grid;grid-template-columns:repeat(3, 1fr);gap:14px;">`;
  for (const mode of ['Swing','Position','Invest']) {
    const list = modes[mode];
    html += `<div data-th-mode="${mode}" style="background:var(--bg-1);border:1px solid var(--rule-2);border-radius:8px;padding:12px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid var(--rule-2);">
        <h3 style="margin:0;font-size:13px;letter-spacing:0.06em;text-transform:uppercase;color:var(--accent);">${mode}</h3>
        <span style="font-family:var(--mono);font-size:11px;color:var(--ink-3);">${list.length} picks</span>
      </div>
      <div data-th-list="${mode}" style="display:flex;flex-direction:column;gap:8px;max-height:72vh;overflow-y:auto;">`;
    for (const r of list) {
      html += _renderThesisRow(r);
    }
    html += `</div></div>`;
  }
  html += `</div>`;
  body.innerHTML = html;

  // wire filter
  const apply = () => {
    const q = (document.getElementById('_thFilter')?.value || '').toUpperCase().trim();
    const vf = document.getElementById('_thVerdict')?.value || '';
    const mn = +(document.getElementById('_thMin')?.value || 0);
    document.querySelectorAll('#_thGrid [data-th-row]').forEach(el => {
      const t = el.getAttribute('data-th-ticker') || '';
      const s = (el.getAttribute('data-th-sector') || '').toUpperCase();
      const v = el.getAttribute('data-th-verdict') || '';
      const sc = +(el.getAttribute('data-th-score') || 0);
      const matchQ = !q || t.includes(q) || s.includes(q);
      const matchV = !vf || v === vf;
      const matchM = sc >= mn;
      el.style.display = (matchQ && matchV && matchM) ? '' : 'none';
    });
  };
  ['_thFilter','_thVerdict','_thMin'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('input', apply);
  });
}

export function dispose() { /* no-op */ }

// tabs/earnings/rows.js — Row + table-shell HTML renderer for the earnings grid.
// Returns the full table block as an HTML string consumed by entry orchestrator.

const fmtPx = v => v == null || isNaN(v) ? '—' : Number(v).toFixed(2);

function _row(e, tickerData, beatByT, beatStats, myPositions) {
  const t        = e.ticker;
  const td       = tickerData[t] || {};
  const ownsTag  = myPositions.has(t)
    ? `<span style="background:var(--fail);color:#fff;padding:1px 6px;border-radius:3px;font-size:9px;font-weight:700;">⚠ OWNED</span>` : '';
  const when = e.before_after_market === 'BeforeMarket' ? 'BMO'
             : e.before_after_market === 'AfterMarket'  ? 'AMC' : '—';
  const days = e.days_to_earnings;
  const daysStyle = days <= 1 ? 'color:var(--fail);font-weight:700'
                  : days <= 3 ? 'color:var(--warn);font-weight:700'
                  : days <= 5 ? 'color:var(--accent)' : 'color:var(--ink-2)';
  const setup        = td.setup_family || td.setup || '';
  const score        = td.score != null ? td.score.toFixed(0) : '—';
  const verdict      = td.verdict || td.stage || '';
  const verdictColor = verdict === 'BUY' ? 'var(--green)' : verdict === 'WATCH' ? 'var(--accent)' : 'var(--ink-3)';
  const sector       = td.sector || '—';
  const stats        = beatStats[t];
  const beatTag      = stats && stats.total > 0
    ? `<span style="color:var(--ink-3);font-size:10px;" title="${stats.total} prior reports">${stats.beats}B/${stats.misses}M/${stats.inline}I</span>`
    : '<span style="color:var(--ink-3);font-size:10px;">—</span>';

  const bp   = beatByT[t] || {};
  const bs   = bp.beat_score;
  const tier = bp.tier;
  let beatScoreCell;
  if (bs == null) {
    beatScoreCell = '<span style="color:var(--ink-3);font-size:10px">—</span>';
  } else {
    const tColor = tier === 'STRONG'   ? 'var(--green)'
                 : tier === 'SOLID'    ? 'var(--accent)'
                 : tier === 'MODERATE' ? 'var(--ink-1)' : 'var(--ink-3)';
    const tooltip = bp.breakdown
      ? `H${bp.breakdown.historical?.pts || 0}/Run${bp.breakdown.runup_10d?.pts || 0}/Vol${bp.breakdown.vol_accum?.pts || 0}/An${bp.breakdown.analyst_upside?.pts || 0}/Op${bp.breakdown.options?.pts || 0}/Sec${bp.breakdown.sector_beats?.pts || 0}` : '';
    const tierIcon = tier === 'STRONG' ? '🎯 ' : '';
    beatScoreCell = `<span style="color:${tColor};font-weight:700;font-size:11.5px;" title="${tooltip}">${tierIcon}${bs.toFixed(0)}</span>`;
  }

  return `
    <tr style="border-bottom:1px solid var(--rule);">
      <td style="padding:8px 12px;font-family:var(--mono);font-weight:700;">
        <a href="elite-detail.html?t=${encodeURIComponent(t)}" style="color:var(--ink-0);text-decoration:none;">${t}</a> ${ownsTag}
      </td>
      <td style="padding:8px 12px;${daysStyle};font-family:var(--mono);">${days}d</td>
      <td style="padding:8px 12px;color:var(--ink-2);">${e.report_date}</td>
      <td style="padding:8px 12px;color:var(--ink-2);font-size:11px;">${when}</td>
      <td style="padding:8px 12px;text-align:center;">${score !== '—' ? `<b>${score}</b>` : '<span style="color:var(--ink-3)">—</span>'}</td>
      <td style="padding:8px 12px;text-align:center;">
        ${verdict ? `<span style="color:${verdictColor};font-weight:700;font-size:10px;">${verdict}</span>` : '<span style="color:var(--ink-3)">—</span>'}
      </td>
      <td style="padding:8px 12px;color:var(--ink-2);font-size:11px;">${setup}</td>
      <td style="padding:8px 12px;text-align:right;font-family:var(--mono);">${e.estimate != null ? fmtPx(e.estimate) : '—'}</td>
      <td style="padding:8px 12px;text-align:center;">${beatTag}</td>
      <td style="padding:8px 12px;text-align:center;">${beatScoreCell}</td>
      <td style="padding:8px 12px;color:var(--ink-2);font-size:11px;">${sector.slice(0, 24)}</td>
    </tr>`;
}

export function buildTable(filtered, ctx) {
  const rows = filtered.map(e => _row(e, ctx.tickerData, ctx.beatByT, ctx.beatStats, ctx.myPositions)).join('');
  return `
    <div style="padding:0 0 14px;color:var(--ink-2);font-size:11.5px;line-height:1.55;">
      <b style="color:var(--fail)">Red days = ≤1d</b> (highest risk) · <b style="color:var(--warn)">Yellow = ≤3d</b> · <b style="color:var(--accent)">Amber = ≤5d</b>.
      <b>BEAT/MISS/INLINE</b> column = last 30 days of prior reports for that ticker (pattern hint, not promise).
      <b>OWNED</b> tag = currently in your portfolio.
    </div>
    <div style="overflow-x:auto;max-height:70vh;overflow-y:auto;">
      <table style="width:100%;border-collapse:collapse;font-size:12px;">
        <thead style="position:sticky;top:0;z-index:5;">
          <tr style="background:var(--bg-2);color:var(--ink-3);text-align:left;border-bottom:1px solid var(--rule-2);">
            <th style="padding:9px 12px;font-weight:600;letter-spacing:0.04em;font-size:10px;">TICKER</th>
            <th style="padding:9px 12px;font-weight:600;letter-spacing:0.04em;font-size:10px;">DAYS</th>
            <th style="padding:9px 12px;font-weight:600;letter-spacing:0.04em;font-size:10px;">REPORT</th>
            <th style="padding:9px 12px;font-weight:600;letter-spacing:0.04em;font-size:10px;">WHEN</th>
            <th style="padding:9px 12px;text-align:center;font-weight:600;letter-spacing:0.04em;font-size:10px;">SCORE</th>
            <th style="padding:9px 12px;text-align:center;font-weight:600;letter-spacing:0.04em;font-size:10px;">VERDICT</th>
            <th style="padding:9px 12px;font-weight:600;letter-spacing:0.04em;font-size:10px;">SETUP</th>
            <th style="padding:9px 12px;text-align:right;font-weight:600;letter-spacing:0.04em;font-size:10px;">EPS EST</th>
            <th style="padding:9px 12px;text-align:center;font-weight:600;letter-spacing:0.04em;font-size:10px;" title="BEAT / MISS / INLINE — last 30d of prior reports">PRIOR</th>
            <th style="padding:9px 12px;text-align:center;font-weight:600;letter-spacing:0.04em;font-size:10px;" title="Composite beat-probability score 0-100 — historical beat rate + price runup + volume accumulation + analyst sentiment + options flow + sector co-movers">BEAT %</th>
            <th style="padding:9px 12px;font-weight:600;letter-spacing:0.04em;font-size:10px;">SECTOR</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

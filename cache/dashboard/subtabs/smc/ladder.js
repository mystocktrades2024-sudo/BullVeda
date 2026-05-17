// subtabs/smc/ladder.js — Price-ladder SVG renderer.
// Renders ±15% viewport around current price with OB rectangles (left half),
// FVG bands (right half), fractal levels, VWAP/AVWAP lines, NOW marker.
// Pure function — returns SVG markup as a string.

export function buildLadderSVG(ctx) {
  const { px, obs, fvgs, fracHi, fracLo, vwap } = ctx;

  const levels = [];
  obs.slice(0, 12).forEach(o => levels.push({ price: o.price_level }));
  fvgs.slice(0, 8).forEach(f => levels.push({ price: (f.top + f.bottom) / 2 }));
  if (fracHi > 0) levels.push({ price: fracHi });
  if (fracLo > 0) levels.push({ price: fracLo });
  if (vwap.vwap_20d)        levels.push({ price: +vwap.vwap_20d });
  if (vwap.avwap_swing_low) levels.push({ price: +vwap.avwap_swing_low });

  const allP    = [px, ...levels.map(l => l.price).filter(p => p != null)].filter(p => p > 0);
  const padding = px * 0.18;
  const minP    = Math.max(Math.min(...allP) - padding * 0.15, px - padding);
  const maxP    = Math.min(Math.max(...allP) + padding * 0.15, px + padding);
  const range   = Math.max(maxP - minP, px * 0.05);
  const W = 360, H = 360, padT = 14, padB = 14, padL = 14, padR = 130;
  const yScale  = p => padT + ((maxP - p) / range) * (H - padT - padB);
  const cWidth  = W - padL - padR;
  const yPx     = yScale(px);

  let svg = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" class="smc-ladder-svg" xmlns="http://www.w3.org/2000/svg">`;

  // Background grid
  for (let i = 0; i <= 8; i++) {
    const y = padT + (i / 8) * (H - padT - padB);
    const p = maxP - (i / 8) * range;
    svg += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="#222" stroke-dasharray="2 3" stroke-width="0.5"/>`;
    svg += `<text x="${W - padR + 8}" y="${y + 3}" font-size="9" fill="#7a818c" font-family="var(--mono)">$${p.toFixed(2)}</text>`;
  }

  // OB rectangles (left half)
  obs.slice(0, 12).forEach(o => {
    const yT      = yScale(o.high), yB = yScale(o.low);
    const isBull  = o.type === 'bullish';
    const opacity = o.status === 'mitigated' ? 0.18 : o.status === 'tested' ? 0.5 : 0.85;
    const fill    = isBull ? `rgba(74, 222, 128, ${opacity * 0.5})` : `rgba(248, 113, 113, ${opacity * 0.5})`;
    const stroke  = isBull ? `rgba(74, 222, 128, ${opacity})`       : `rgba(248, 113, 113, ${opacity})`;
    svg += `<rect x="${padL + 4}" y="${Math.min(yT, yB)}" width="${cWidth * 0.5}" height="${Math.max(2, Math.abs(yB - yT))}" fill="${fill}" stroke="${stroke}" stroke-width="1" rx="2"/>`;
  });

  // FVG bands (right half)
  fvgs.slice(0, 8).forEach(f => {
    const yT      = yScale(f.top), yB = yScale(f.bottom);
    const isBull  = f.type === 'bullish';
    const opacity = f.status === 'closed' ? 0.18 : 0.6;
    const fill    = isBull ? `rgba(74, 222, 128, ${opacity * 0.4})` : `rgba(248, 113, 113, ${opacity * 0.4})`;
    const stroke  = isBull ? `rgba(74, 222, 128, ${opacity})`       : `rgba(248, 113, 113, ${opacity})`;
    svg += `<rect x="${padL + cWidth * 0.55}" y="${Math.min(yT, yB)}" width="${cWidth * 0.45}" height="${Math.max(2, Math.abs(yB - yT))}" fill="${fill}" stroke="${stroke}" stroke-width="1" stroke-dasharray="3 2" rx="2"/>`;
  });

  // Fractal levels
  if (fracHi > 0) {
    const y = yScale(fracHi);
    svg += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="#94a3b8" stroke-width="1" stroke-dasharray="6 3"/>`;
    svg += `<text x="${padL + 4}" y="${y - 3}" font-size="9" fill="#94a3b8" font-weight="700">FH $${fracHi.toFixed(2)}</text>`;
  }
  if (fracLo > 0) {
    const y = yScale(fracLo);
    svg += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="#94a3b8" stroke-width="1" stroke-dasharray="6 3"/>`;
    svg += `<text x="${padL + 4}" y="${y - 3}" font-size="9" fill="#94a3b8" font-weight="700">FL $${fracLo.toFixed(2)}</text>`;
  }

  // VWAP / AVWAP
  if (vwap.vwap_20d) {
    const y = yScale(+vwap.vwap_20d);
    svg += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="#a78bfa" stroke-width="1.2"/>`;
    svg += `<text x="${padL + 4}" y="${y - 3}" font-size="9" fill="#a78bfa" font-weight="700">VWAP $${(+vwap.vwap_20d).toFixed(2)}</text>`;
  }
  if (vwap.avwap_swing_low) {
    const y = yScale(+vwap.avwap_swing_low);
    svg += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="#a78bfa" stroke-width="1" stroke-dasharray="3 2"/>`;
    svg += `<text x="${padL + 4}" y="${y + 10}" font-size="9" fill="#a78bfa" font-weight="700">AVWAP $${(+vwap.avwap_swing_low).toFixed(2)}</text>`;
  }

  // Current price marker (highlighted)
  svg += `<line x1="${padL}" y1="${yPx}" x2="${W - padR}" y2="${yPx}" stroke="#fbbf24" stroke-width="2"/>`;
  svg += `<rect x="${W - padR - 70}" y="${yPx - 8}" width="60" height="16" fill="#fbbf24" rx="2"/>`;
  svg += `<text x="${W - padR - 40}" y="${yPx + 4}" font-size="10" fill="#0a0e14" text-anchor="middle" font-weight="800" font-family="var(--mono)">NOW $${px.toFixed(2)}</text>`;
  svg += `</svg>`;

  return svg;
}

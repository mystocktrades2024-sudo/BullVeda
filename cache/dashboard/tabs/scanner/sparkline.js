// tabs/scanner/sparkline.js — deterministic mini sparkline for each ticker row.
// Pure function: given (ticker, score, dir), returns SVG points + areaPath +
// up/down direction + last-point coords. Uses LCG seeded from the ticker hash
// so the same ticker always renders the same shape (no DOM, no DATA).

export function buildSparkPath(ticker, score, dir) {
  const seed = (ticker || '').split('').reduce((s, c) => s + c.charCodeAt(0), 0) * 31 + (score || 0);
  let s = seed;
  const rand = () => { s = (s * 9301 + 49297) % 233280; return s / 233280; };
  const w = 60, h = 22, n = 30;
  let v = 50;
  const pts = [];
  const trend = dir > 0 ? 0.4 : dir < 0 ? -0.4 : 0;
  for (let i = 0; i < n; i++) {
    v += (rand() - 0.5) * 6 + trend;
    v = Math.max(15, Math.min(85, v));
    pts.push(v);
  }
  const min = Math.min(...pts), max = Math.max(...pts), range = max - min || 1;
  const xy = pts.map((p, i) => [(i / (n - 1) * w), (h - ((p - min) / range) * (h - 4) - 2)]);
  const points = xy.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const areaPath = `M ${xy[0][0]},${h} L ` + xy.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' L ') + ` L ${xy[xy.length - 1][0]},${h} Z`;
  const upDown = pts[n - 1] >= pts[0] ? 'up' : 'dn';
  const lastPt = xy[xy.length - 1];
  return { points, areaPath, dir: upDown, lastX: lastPt[0], lastY: lastPt[1] };
}

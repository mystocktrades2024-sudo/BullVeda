/**
 * PROTOTYPE — push SwingTrade structural levels onto a TradingView chart.
 *
 * Reads cache/target_engine/{TICKER}_{MODE}.json (the Project-2 structural
 * target engine output) and draws entry / stop / T1 / T2 as labelled
 * horizontal lines on a DISPOSABLE TradingView chart tab.
 *
 * Safety: opens its OWN ephemeral chart via CDP Target.createTarget (no saved
 * layout id) so it can never modify a chart you already have open. The tab is
 * left open at the end so you can look at it; close it like any tab.
 *
 * Requires: TradingView Desktop running with --remote-debugging-port=9222
 *   ~/tradingview-mcp/scripts/launch_tv_debug_mac.sh
 *
 * Usage (chrome-remote-interface lives in the bridge repo):
 *   NODE_PATH=~/tradingview-mcp/node_modules \
 *     node infra/prototype/tv_bridge/push_levels.mjs NEM swing
 *
 * Not affiliated with TradingView. Drives YOUR logged-in desktop app; no new
 * data license. Visual/authoring layer only — never the scoring data path.
 */
import CDP from 'chrome-remote-interface';
import fs from 'node:fs';
import path from 'node:path';

const HOST = 'localhost', PORT = 9222;
const TICKER = (process.argv[2] || 'NEM').toUpperCase();
const MODE   = (process.argv[3] || 'swing').toLowerCase();
const REPO   = '/Volumes/MyMacDisk/Claude Skills/SwingTrade';
const RES_BY_MODE = { swing: '1D', position: '1W', invest: '1M' };

const COLORS = {
  stop:  '#ef4444',
  entry: '#f59e0b',
  t1:    '#22c55e',
  t2:    '#22c55e',
};

function loadPlan() {
  const f = path.join(REPO, 'cache', 'target_engine', `${TICKER}_${MODE}.json`);
  if (!fs.existsSync(f)) throw new Error(`No target_engine cache: ${f}`);
  return JSON.parse(fs.readFileSync(f, 'utf8'));
}

const sleep = (ms) => new Promise(r => setTimeout(r, ms));

async function main() {
  const plan = loadPlan();
  const res = RES_BY_MODE[MODE] || '1D';
  console.log(`[plan] ${TICKER} ${MODE}  entry=${plan.entry?.price} stop=${plan.stop?.price} `
            + `T1=${plan.t1?.price} (conf ${plan.t1?.confluence}) T2=${plan.t2?.price} (conf ${plan.t2?.confluence})`);

  // 1) open our OWN scratch tab via Cmd+T (a fresh Untitled chart, NOT a saved
  //    layout) so we never write to a chart you already have open.
  const listCharts = async () => {
    const r = await (await fetch(`http://${HOST}:${PORT}/json/list`)).json();
    return r.filter(t => t.type === 'page' && /tradingview\.com\/chart/i.test(t.url)).map(t => t.id);
  };
  const before = await listCharts();
  const opener = await CDP({ host: HOST, port: PORT, target: before[0] });
  const isMac = process.platform === 'darwin';
  await opener.Input.dispatchKeyEvent({ type: 'keyDown', modifiers: isMac ? 4 : 2, key: 't', code: 'KeyT', windowsVirtualKeyCode: 84 });
  await opener.Input.dispatchKeyEvent({ type: 'keyUp', key: 't', code: 'KeyT' });
  await opener.close();
  await sleep(2500);
  const after = await listCharts();
  const targetId = after.find(id => !before.includes(id));
  if (!targetId) throw new Error('new tab did not appear (Cmd+T may have been swallowed)');
  console.log(`[tab ] opened scratch chart targetId=${targetId.slice(0, 8)}`);

  // 2) connect to that exact target — stable, isolated
  const c = await CDP({ host: HOST, port: PORT, target: targetId });
  await c.Runtime.enable();
  await c.Page.enable();
  const ev = async (expr) =>
    (await c.Runtime.evaluate({ expression: expr, returnByValue: true, awaitPromise: true })).result.value;
  const api = `window.TradingViewApi._activeChartWidgetWV.value()`;

  // 3) wait for the chart API + symbol to be ready
  let ready = false;
  for (let i = 0; i < 30; i++) {
    const sym = await ev(`(function(){try{return ${api}.symbol();}catch(e){return null}})()`);
    if (sym) { ready = true; break; }
    await sleep(1000);
  }
  if (!ready) throw new Error('chart API never became ready');
  await ev(`(function(){try{${api}.setSymbol(${JSON.stringify(TICKER)},{});return 'ok'}catch(e){return e.message}})()`);
  await sleep(2500);
  await ev(`(function(){try{${api}.setResolution(${JSON.stringify(res)},{});return 'ok'}catch(e){return e.message}})()`);
  await sleep(2500);
  console.log(`[sym ] ${await ev(`(function(){try{return ${api}.symbol()+' @ '+${api}.resolution();}catch(e){return 'err'}})()`)}`);

  // 4) draw the four structural levels
  const t = Math.floor(Date.now() / 1000);
  const draw = async (price, color, label, dashed) => {
    if (price == null) return null;
    const ov = JSON.stringify({ linecolor: color, linewidth: 2, linestyle: dashed ? 2 : 0, showLabel: true, text: label });
    const before = await ev(`${api}.getAllShapes().map(function(s){return s.id;})`);
    await ev(`${api}.createShape({time:${t},price:${price}},{shape:'horizontal_line',overrides:${ov},text:${JSON.stringify(label)}})`);
    await sleep(250);
    const after = await ev(`${api}.getAllShapes().map(function(s){return s.id;})`);
    const id = (after || []).find(x => !(before || []).includes(x)) || null;
    console.log(`[draw] ${label.padEnd(34)} -> ${id}`);
    return id;
  };

  await draw(plan.stop?.price,  COLORS.stop,  `STOP ${plan.stop?.price}  (${plan.stop?.distance_atr ?? '?'}xATR)`, true);
  await draw(plan.entry?.price, COLORS.entry, `ENTRY ${plan.entry?.price}`, false);
  await draw(plan.t1?.price,    COLORS.t1,    `T1 ${plan.t1?.price}  conf ${plan.t1?.confluence}  R ${plan.t1?.r_multiple}`, false);
  await draw(plan.t2?.price,    COLORS.t2,    `T2 ${plan.t2?.price}  conf ${plan.t2?.confluence}`, true);

  // 5) screenshot
  await sleep(1500);
  const shot = await c.Page.captureScreenshot({ format: 'png' });
  const outDir = path.join(REPO, 'infra', 'prototype', 'tv_bridge', 'shots');
  fs.mkdirSync(outDir, { recursive: true });
  const outFile = path.join(outDir, `${TICKER}_${MODE}_levels.png`);
  fs.writeFileSync(outFile, Buffer.from(shot.data, 'base64'));
  console.log(`[shot] ${outFile}`);

  await c.close();
  console.log('[done] levels pushed to ephemeral chart (left open).');
}

main().catch(e => { console.error('ERROR:', e.message); process.exit(1); });

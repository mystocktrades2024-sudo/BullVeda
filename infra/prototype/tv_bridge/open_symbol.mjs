// open_symbol.mjs — switch the SYMBOL on the user's logged-in TradingView
// Desktop chart via the CDP bridge (port 9222). Unlike find_and_push.mjs (which
// only DRAWS on a chart already showing the symbol), this SETS the symbol on the
// active chart of the first live chart tab — preserving the saved layout and all
// loaded studies (PHSwing, LuxAlgo, …). Backs the "📈 TV" button on Screener Desk
// cards (/api/tv/open). Visual layer only — never feeds scoring.
//
// Usage: node open_symbol.mjs <TICKER> [swing|position|invest]
// Exit codes: 0 ok · 2 no bridge / no chart tab (→ web fallback) · 3 bad ticker
import CDP from 'chrome-remote-interface';
const HOST = 'localhost', PORT = 9222;
const TICKER = (process.argv[2] || '').toUpperCase().trim();
const MODE = (process.argv[3] || 'swing').toLowerCase();
const RES = { swing: '1D', position: '1W', invest: '1M' }[MODE] || null;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const api = `window.TradingViewApi._activeChartWidgetWV.value()`;

if (!/^[A-Z0-9.\-:]{1,16}$/.test(TICKER)) { console.error('bad ticker'); process.exit(3); }

async function chartTargets() {
  const list = (await (await fetch(`http://${HOST}:${PORT}/json/list`)).json())
    .filter(t => t.type === 'page' && /tradingview\.com\/chart/i.test(t.url));
  return list;
}

let list;
try { list = await chartTargets(); }
catch (e) { console.error('no bridge (is TV Desktop running with --remote-debugging-port=9222?): ' + e.message); process.exit(2); }
if (!list.length) { console.error('No TradingView Desktop chart tab open.'); process.exit(2); }

let done = false, lastErr = '';
for (const t of list) {
  try {
    const c = await CDP({ host: HOST, port: PORT, target: t.id });
    await c.Runtime.enable();
    const ev = async e => (await c.Runtime.evaluate({ expression: e, returnByValue: true, awaitPromise: true })).result.value;
    const has = await ev(`(function(){try{return !!(${api});}catch(e){return false}})()`);
    if (!has) { await c.close(); continue; }
    const before = await ev(`(function(){try{return ${api}.symbol();}catch(e){return ''}})()`);
    const r = await ev(`(function(){try{${api}.setSymbol(${JSON.stringify(TICKER)},{});return 'ok'}catch(e){return 'ERR:'+e.message}})()`);
    if (RES) await ev(`(function(){try{${api}.setResolution(${JSON.stringify(RES)},{});}catch(e){}})()`);
    await sleep(800);
    const after = await ev(`(function(){try{return ${api}.symbol();}catch(e){return ''}})()`);
    await c.close();
    if (String(r).startsWith('ERR')) { lastErr = r; continue; }
    console.log('[open]', before, '->', after);
    done = true; break;
  } catch (e) { lastErr = e.message; }
}
if (!done) { console.error('setSymbol failed: ' + lastErr); process.exit(2); }
console.log('[done]');

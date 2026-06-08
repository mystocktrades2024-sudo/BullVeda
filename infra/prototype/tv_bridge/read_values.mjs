/**
 * PROTOTYPE — read the live Pine-indicator values (LuxAlgo / AlgoAlpha / any
 * loaded study) off YOUR TradingView Desktop chart for a given symbol.
 *
 * Finds the tab whose chart symbol matches the ticker, reads each study's
 * data-window values (the same numbers TradingView shows in its Data Window),
 * and prints them as JSON. License-clean: you hold the seat, it reads your own
 * screen. Informational only — never feeds the SwingTrade scoring path.
 *
 * Usage:  node infra/prototype/tv_bridge/read_values.mjs MU
 * Exit 2 = no chart currently showing that symbol.
 */
import CDP from 'chrome-remote-interface';
const HOST = 'localhost', PORT = 9222;
const TICKER = (process.argv[2] || '').toUpperCase();
const api = `window.TradingViewApi._activeChartWidgetWV.value()`;
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

const EXTRACT = `
  (function() {
    try {
      var chart = window.TradingViewApi._activeChartWidgetWV.value()._chartWidget;
      var sources = chart.model().model().dataSources();
      var results = [];
      for (var si = 0; si < sources.length; si++) {
        var s = sources[si];
        if (!s.metaInfo) continue;
        try {
          var meta = s.metaInfo();
          var name = meta.description || meta.shortDescription || '';
          if (!name) continue;
          var values = {};
          try {
            var dwv = s.dataWindowView();
            if (dwv) {
              var items = dwv.items();
              if (items) for (var i = 0; i < items.length; i++) {
                var it = items[i];
                if (it._value && it._value !== '∅' && it._title) values[it._title] = it._value;
              }
            }
          } catch(e) {}
          if (Object.keys(values).length > 0) results.push({ name: name, values: values });
        } catch(e) {}
      }
      return JSON.stringify(results);
    } catch(e) { return JSON.stringify({ __err: e.message }); }
  })()
`;

async function findBySymbol() {
  const list = (await (await fetch(`http://${HOST}:${PORT}/json/list`)).json())
    .filter(t => t.type === 'page' && /tradingview\.com\/chart/i.test(t.url));
  for (const t of list) {
    try {
      const c = await CDP({ host: HOST, port: PORT, target: t.id });
      await c.Runtime.enable();
      const sym = (await c.Runtime.evaluate({ expression: `(function(){try{return ${api}.symbol();}catch(e){return''}})()`, returnByValue: true })).result.value || '';
      if (sym.toUpperCase().includes(TICKER)) {
        try { await c.Page.enable(); await c.Page.bringToFront(); } catch (e) {}
        return { c, sym };
      }
      await c.close();
    } catch (e) {}
  }
  return null;
}

async function main() {
  if (!TICKER) { console.error('usage: read_values.mjs SYM'); process.exit(1); }
  const hit = await findBySymbol();
  if (!hit) { console.log(JSON.stringify({ ok: false, needs_tab: true, symbol: TICKER })); process.exit(2); }
  const { c, sym } = hit;
  await sleep(1200);  // let the data-window recompute after bringToFront
  const raw = (await c.Runtime.evaluate({ expression: EXTRACT, returnByValue: true })).result.value;
  await c.close();
  let studies = [];
  try { studies = JSON.parse(raw); } catch (e) {}
  if (studies && studies.__err) { console.log(JSON.stringify({ ok: false, error: studies.__err, symbol: sym })); return; }
  console.log(JSON.stringify({ ok: true, symbol: sym, study_count: studies.length, studies }));
}
main().catch(e => { console.log(JSON.stringify({ ok: false, error: e.message })); process.exit(1); });

// subtabs/insider/aggregate.js — pure data transforms for the Insider sub-tab.
// Walks Form 4 transactions, classifies title levels, computes totals, builds
// the verdict + narrative + horizon-impact strings. No DOM, no fetch.

export const isBuyTx = t => (t.type || '').toUpperCase().startsWith('P') || (t.type || '').toUpperCase() === 'BUY';

export function titleLevel(title) {
  const t = (title || '').toUpperCase();
  if (/\b(CEO|CFO|COO|CTO|CHIEF|PRESIDENT|CHAIRMAN)\b/.test(t)) return 'csuite';
  if (/\b(EVP|EXECUTIVE VP|EXEC.*VP)\b/.test(t))                 return 'evp';
  if (/\b(DIRECTOR|BOARD)\b/.test(t))                            return 'dir';
  if (/\b(VP|VICE PRES)\b/.test(t))                              return 'vp';
  return 'other';
}

export function titlePillCls(lvl) {
  return lvl === 'csuite' ? 'csuite' : lvl === 'evp' ? 'evp' : lvl === 'dir' ? 'dir' : '';
}

export function titleShort(title) {
  const t = (title || '').toUpperCase();
  if (/\bCEO\b/.test(t))       return 'CEO';
  if (/\bCFO\b/.test(t))       return 'CFO';
  if (/\bCOO\b/.test(t))       return 'COO';
  if (/\bCTO\b/.test(t))       return 'CTO';
  if (/\bPRESIDENT\b/.test(t)) return 'PRES';
  if (/\bCHAIRMAN\b/.test(t))  return 'CHAIR';
  if (/\bEVP\b/.test(t))       return 'EVP';
  if (/\bDIRECTOR\b/.test(t))  return 'DIR';
  if (/\bVP\b/.test(t))        return 'VP';
  return (title || '').slice(0, 12).toUpperCase();
}

export function aggregate(txs, T) {
  let totalBuys = 0, totalSells = 0, buyValue = 0, sellValue = 0;
  let buyShares = 0, sellShares = 0;
  let csuiteSells = 0, csuiteBuys = 0;
  let oldestDate = null, newestDate = null;

  txs.forEach(t => {
    const isBuy = isBuyTx(t);
    if (isBuy) { totalBuys++;  buyValue  += t.value || 0; buyShares  += t.shares || 0; }
    else       { totalSells++; sellValue += t.value || 0; sellShares += t.shares || 0; }
    const lvl = titleLevel(t.title);
    if (lvl === 'csuite') { isBuy ? csuiteBuys++ : csuiteSells++; }
    const dt = t.date ? new Date(t.date) : null;
    if (dt && !isNaN(dt)) {
      if (!oldestDate || dt < oldestDate) oldestDate = dt;
      if (!newestDate || dt > newestDate) newestDate = dt;
    }
  });

  const netValue   = buyValue - sellValue;
  const totalTx    = totalBuys + totalSells;
  const dayRange   = oldestDate && newestDate ? Math.max(1, Math.round((newestDate - oldestDate) / 86400000)) : 90;
  const avgSellPx  = sellShares > 0 ? sellValue / sellShares : 0;
  const avgBuyPx   = buyShares  > 0 ? buyValue  / buyShares  : 0;
  const px         = +(T.price || 0);
  const mcap       = +(T.market_cap || 0);
  const netPctMcap = mcap > 0 ? Math.abs(netValue) / mcap * 100 : 0;
  const sellVsNow  = px && avgSellPx ? (px - avgSellPx) / avgSellPx * 100 : 0;
  const maxValue   = Math.max(...txs.map(t => Math.abs(t.value || 0)), 1);

  // Verdict
  let verdict, severity, tone;
  if (netValue < -1e6 && totalSells >= totalBuys * 2) {
    tone     = 'dist';
    severity = csuiteSells >= 2 || Math.abs(netValue) > 20e6 ? 'HEAVY'
             : Math.abs(netValue) > 5e6                       ? 'MODERATE'
             :                                                  'LIGHT';
    verdict = `${severity} DISTRIBUTION`;
  } else if (netValue > 1e6 && totalBuys >= totalSells * 2) {
    tone     = 'accum';
    severity = csuiteBuys >= 1 || netValue > 5e6 ? 'STRONG' : 'MODEST';
    verdict  = `${severity} ACCUMULATION`;
  } else {
    tone     = 'balanced';
    severity = 'NEUTRAL';
    verdict  = 'BALANCED FLOW';
  }

  // Narrative
  let narrative;
  if (tone === 'dist') {
    narrative = `${totalSells} sells in ${dayRange} days totaling $${(sellValue/1e6).toFixed(2)}M (${netPctMcap.toFixed(3)}% of market cap)` +
      (csuiteSells > 0 ? ` — ${csuiteSells} from C-suite` : '') +
      (avgSellPx ? `. Avg sell $${avgSellPx.toFixed(2)} vs current $${px.toFixed(2)} (${sellVsNow >= 0 ? 'sold cheaper than now — less alarming' : 'sold above current — bearish read'})` : '') + '.';
  } else if (tone === 'accum') {
    narrative = `${totalBuys} buys in ${dayRange} days totaling $${(buyValue/1e6).toFixed(2)}M` +
      (csuiteBuys > 0 ? ` — ${csuiteBuys} from C-suite (high-confidence signal)` : '') +
      (avgBuyPx ? `. Avg buy $${avgBuyPx.toFixed(2)} vs current $${px.toFixed(2)}` : '') + '.';
  } else {
    narrative = `${totalBuys} buys + ${totalSells} sells over ${dayRange} days. Insider activity is mixed — neutral signal.`;
  }

  return {
    totalBuys, totalSells, buyValue, sellValue, buyShares, sellShares,
    csuiteSells, csuiteBuys, netValue, totalTx, dayRange,
    avgSellPx, avgBuyPx, px, netPctMcap, sellVsNow, maxValue,
    tone, severity, verdict, narrative,
    horizon: buildHorizonImpact(tone, severity),
  };
}

function buildHorizonImpact(tone, severity) {
  if (tone === 'dist') {
    const heavy = severity === 'HEAVY';
    return {
      swing:    { lvl: 'minor',                      txt: heavy ? 'Selling near recent highs may pressure short-term momentum, but most insider sells are not market-timed. Don\'t overweight.' : 'Minor signal at swing horizon — insider sales rarely time daily moves.' },
      position: { lvl: heavy ? 'medium' : 'minor',    txt: heavy ? 'Several weeks of distribution worth noting. Consider tighter stops or smaller size on Position trades.'             : 'Light bearish bias for 3–8w hold; not enough to reject otherwise-strong setups.' },
      invest:   { lvl: heavy ? 'major' : 'medium',    txt: heavy ? 'C-suite distribution is a real long-term signal. Re-examine fundamental thesis — is the trade about to compress?' : 'Some bearish weight on 12–24m horizon. Worth pairing with margin/growth check.' },
    };
  }
  if (tone === 'accum') {
    return {
      swing:    { lvl: 'minor',  txt: 'Insider buying provides backstop support but rarely triggers immediate moves.' },
      position: { lvl: 'medium', txt: 'C-suite buying within last 90d is a quality 3–8 week tailwind. Add weight to bull case.' },
      invest:   { lvl: 'major',  txt: 'Insider conviction at the 12–24m horizon is a high-quality signal. Pair with strong fundamentals.' },
    };
  }
  return {
    swing:    { lvl: 'minor', txt: 'No directional signal from insider flow.' },
    position: { lvl: 'minor', txt: 'No directional signal from insider flow.' },
    invest:   { lvl: 'minor', txt: 'No directional signal from insider flow.' },
  };
}

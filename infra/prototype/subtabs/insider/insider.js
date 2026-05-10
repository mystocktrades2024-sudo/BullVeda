// subtabs/insider/insider.js — extracted from elite-detail.html (renderInsider 2026-05-09)
// CapStudio modular loader for the per-ticker detail page.
// T (current ticker) accessed via window.__getDetailTicker() — NOT yet wired
// in elite-detail.html. This module is created as a candidate for future
// activation; calling render() before wiring requires window.T to be set.

const _T = () => (window.__getDetailTicker ? window.__getDetailTicker() : window.T);

export async function render() {
  const T = _T();
  if (!T) return;
  const body = document.getElementById('insiderBody');
  if (!body) return;
  body.innerHTML = '<div style="padding:30px;color:var(--ink-1);text-align:center">Loading insider transactions…</div>';
  try {
    const r = await fetch(`/api/insider/${T.ticker}?days=90`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const d = await r.json();
    const txs = d.transactions || [];
    if (txs.length === 0) {
      body.innerHTML = `
        <div class="ins-empty">
          <div class="ico">○</div>
          <div class="h">No Form 4 filings for ${T.ticker}</div>
          <div class="sub">No insider transactions reported in the last 90 days. Could mean: insiders in lockup, low public-float company, or simply quiet quarter.</div>
        </div>`;
      return;
    }

    // ── Aggregate ──
    const isBuyTx = t => (t.type || '').toUpperCase().startsWith('P') || (t.type || '').toUpperCase() === 'BUY';
    let totalBuys = 0, totalSells = 0, buyValue = 0, sellValue = 0;
    let buyShares = 0, sellShares = 0;
    let csuiteSells = 0, csuiteBuys = 0;
    let oldestDate = null, newestDate = null;
    const titleLevel = title => {
      const t = (title || '').toUpperCase();
      if (/\b(CEO|CFO|COO|CTO|CHIEF|PRESIDENT|CHAIRMAN)\b/.test(t)) return 'csuite';
      if (/\b(EVP|EXECUTIVE VP|EXEC.*VP)\b/.test(t)) return 'evp';
      if (/\b(DIRECTOR|BOARD)\b/.test(t)) return 'dir';
      if (/\b(VP|VICE PRES)\b/.test(t)) return 'vp';
      return 'other';
    };
    txs.forEach(t => {
      const isBuy = isBuyTx(t);
      if (isBuy) { totalBuys++; buyValue += t.value || 0; buyShares += t.shares || 0; }
      else       { totalSells++; sellValue += t.value || 0; sellShares += t.shares || 0; }
      const lvl = titleLevel(t.title);
      if (lvl === 'csuite') { isBuy ? csuiteBuys++ : csuiteSells++; }
      const dt = t.date ? new Date(t.date) : null;
      if (dt && !isNaN(dt)) {
        if (!oldestDate || dt < oldestDate) oldestDate = dt;
        if (!newestDate || dt > newestDate) newestDate = dt;
      }
    });
    const netValue = buyValue - sellValue;
    const totalTx = totalBuys + totalSells;
    const dayRange = oldestDate && newestDate ? Math.max(1, Math.round((newestDate - oldestDate) / 86400000)) : 90;

    // ── Verdict logic ──
    const px = +(T.price || 0);
    const mcap = +(T.market_cap || 0);
    const netPctMcap = mcap > 0 ? Math.abs(netValue) / mcap * 100 : 0;
    let verdict, severity, tone, narrative;
    if (netValue < -1e6 && totalSells >= totalBuys * 2) {
      tone = 'dist';
      severity = csuiteSells >= 2 || Math.abs(netValue) > 20e6 ? 'HEAVY' : Math.abs(netValue) > 5e6 ? 'MODERATE' : 'LIGHT';
      verdict = `${severity} DISTRIBUTION`;
    } else if (netValue > 1e6 && totalBuys >= totalSells * 2) {
      tone = 'accum';
      severity = csuiteBuys >= 1 || netValue > 5e6 ? 'STRONG' : 'MODEST';
      verdict = `${severity} ACCUMULATION`;
    } else {
      tone = 'balanced';
      severity = 'NEUTRAL';
      verdict = 'BALANCED FLOW';
    }
    const avgSellPx = sellShares > 0 ? sellValue / sellShares : 0;
    const avgBuyPx = buyShares > 0 ? buyValue / buyShares : 0;
    const sellVsNow = px && avgSellPx ? (px - avgSellPx) / avgSellPx * 100 : 0;
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

    // ── Horizon impact ──
    const horizonImpact = (() => {
      if (tone === 'dist') {
        const heavy = severity === 'HEAVY';
        return {
          swing: { lvl: 'minor', txt: heavy ? 'Selling near recent highs may pressure short-term momentum, but most insider sells are not market-timed. Don\'t overweight.' : 'Minor signal at swing horizon — insider sales rarely time daily moves.' },
          position: { lvl: heavy ? 'medium' : 'minor', txt: heavy ? 'Several weeks of distribution worth noting. Consider tighter stops or smaller size on Position trades.' : 'Light bearish bias for 3–8w hold; not enough to reject otherwise-strong setups.' },
          invest: { lvl: heavy ? 'major' : 'medium', txt: heavy ? 'C-suite distribution is a real long-term signal. Re-examine fundamental thesis — is the trade about to compress?' : 'Some bearish weight on 12–24m horizon. Worth pairing with margin/growth check.' },
        };
      }
      if (tone === 'accum') {
        return {
          swing: { lvl: 'minor', txt: 'Insider buying provides backstop support but rarely triggers immediate moves.' },
          position: { lvl: 'medium', txt: 'C-suite buying within last 90d is a quality 3–8 week tailwind. Add weight to bull case.' },
          invest: { lvl: 'major', txt: 'Insider conviction at the 12–24m horizon is a high-quality signal. Pair with strong fundamentals.' },
        };
      }
      return {
        swing: { lvl: 'minor', txt: 'No directional signal from insider flow.' },
        position: { lvl: 'minor', txt: 'No directional signal from insider flow.' },
        invest: { lvl: 'minor', txt: 'No directional signal from insider flow.' },
      };
    })();

    // ── Title pill class ──
    const titlePillCls = lvl => lvl === 'csuite' ? 'csuite' : lvl === 'evp' ? 'evp' : lvl === 'dir' ? 'dir' : '';
    const titleShort = title => {
      const t = (title || '').toUpperCase();
      if (/\bCEO\b/.test(t)) return 'CEO';
      if (/\bCFO\b/.test(t)) return 'CFO';
      if (/\bCOO\b/.test(t)) return 'COO';
      if (/\bCTO\b/.test(t)) return 'CTO';
      if (/\bPRESIDENT\b/.test(t)) return 'PRES';
      if (/\bCHAIRMAN\b/.test(t)) return 'CHAIR';
      if (/\bEVP\b/.test(t)) return 'EVP';
      if (/\bDIRECTOR\b/.test(t)) return 'DIR';
      if (/\bVP\b/.test(t)) return 'VP';
      return (title || '').slice(0, 12).toUpperCase();
    };

    // ── Bar widths (relative scaling) ──
    const maxValue = Math.max(...txs.map(t => Math.abs(t.value || 0)), 1);
    const buyBarWidth = (totalBuys + totalSells) > 0 ? (totalBuys / (totalBuys + totalSells)) * 100 : 0;
    const sellBarWidth = (totalBuys + totalSells) > 0 ? (totalSells / (totalBuys + totalSells)) * 100 : 0;
    const netSign = netValue >= 0 ? '+' : '';

    body.innerHTML = `
      <!-- VERDICT BANNER -->
      <div class="ins-verdict ${tone}">
        <div class="ins-v-l">
          <div class="ins-v-tag"><span class="dot"></span>SMART MONEY · ${verdict}</div>
          <div class="ins-v-headline">${totalSells > totalBuys ? 'Insiders are net <span class="severity">selling</span>' : totalBuys > totalSells ? 'Insiders are net <span class="severity">buying</span>' : 'Insider activity is balanced'} over the last ${dayRange} days</div>
          <div class="ins-v-narr">${narrative}</div>
        </div>
        <div class="ins-v-r">
          <div class="ins-v-net">${netSign}$${(netValue/1e6).toFixed(2)}M</div>
          <div class="ins-v-net-lbl">Net 90d flow</div>
        </div>
      </div>

      <!-- 3 STAT TILES -->
      <div class="ins-tiles">
        <div class="ins-tile buys">
          <div class="lbl">Buys (90d) <span class="meta">${totalBuys} of ${totalTx}</span></div>
          <div class="v">${totalBuys}</div>
          <div class="sub">$${(buyValue/1e6).toFixed(2)}M${buyShares > 0 ? ` · ${buyShares.toLocaleString()} sh` : ''}${avgBuyPx ? ` · avg $${avgBuyPx.toFixed(2)}` : ''}</div>
          <div class="bar-track"><div class="bar-fill" style="width:${buyBarWidth.toFixed(0)}%"></div></div>
        </div>
        <div class="ins-tile sells">
          <div class="lbl">Sells (90d) <span class="meta">${totalSells} of ${totalTx}</span></div>
          <div class="v">${totalSells}</div>
          <div class="sub">$${(sellValue/1e6).toFixed(2)}M${sellShares > 0 ? ` · ${sellShares.toLocaleString()} sh` : ''}${avgSellPx ? ` · avg $${avgSellPx.toFixed(2)}` : ''}</div>
          <div class="bar-track"><div class="bar-fill" style="width:${sellBarWidth.toFixed(0)}%"></div></div>
        </div>
        <div class="ins-tile net ${netValue >= 0 ? 'pos' : 'neg'}">
          <div class="lbl">Net Flow <span class="meta">${netPctMcap.toFixed(3)}% of mcap</span></div>
          <div class="v">${netSign}$${(netValue/1e6).toFixed(2)}M</div>
          <div class="sub">${csuiteSells > 0 ? `${csuiteSells} C-suite sell${csuiteSells>1?'s':''}` : ''}${csuiteSells > 0 && csuiteBuys > 0 ? ' · ' : ''}${csuiteBuys > 0 ? `${csuiteBuys} C-suite buy${csuiteBuys>1?'s':''}` : ''}${csuiteSells === 0 && csuiteBuys === 0 ? 'No C-suite participation' : ''}</div>
        </div>
      </div>

      <!-- PATTERN INTELLIGENCE + HORIZON IMPACT -->
      <div class="ins-pattern-grid">
        <div class="ins-pat">
          <div class="ins-pat-h"><span class="ico">🔍</span>CLUSTER PATTERN</div>
          <div class="ins-pat-row"><span class="l">Window</span><span class="r">${dayRange} days</span></div>
          <div class="ins-pat-row"><span class="l">Total transactions</span><span class="r">${totalTx}</span></div>
          <div class="ins-pat-row"><span class="l">C-suite involvement</span><span class="r ${csuiteSells>=2?'fail':csuiteBuys>=1?'pass':''}">${csuiteSells + csuiteBuys} (${csuiteSells} sells / ${csuiteBuys} buys)</span></div>
          <div class="ins-pat-row"><span class="l">Avg sell price</span><span class="r">${avgSellPx ? '$'+avgSellPx.toFixed(2) : '—'}</span></div>
          <div class="ins-pat-row"><span class="l">Sell vs current price</span><span class="r ${sellVsNow >= 5 ? 'pass' : sellVsNow <= -5 ? 'fail' : ''}">${avgSellPx && px ? (sellVsNow >= 0 ? '+' : '') + sellVsNow.toFixed(1) + '%' : '—'}</span></div>
          <div class="ins-pat-row"><span class="l">Net % of market cap</span><span class="r ${netPctMcap > 0.1 ? 'warn' : ''}">${netPctMcap.toFixed(4)}%</span></div>
        </div>
        <div class="ins-pat">
          <div class="ins-pat-h"><span class="ico">🎯</span>HORIZON IMPACT</div>
          <div class="ins-hz-grid">
            <div class="ins-hz ${horizonImpact.swing.lvl}">
              <div class="ins-hz-h">⚡ SWING<span class="impact">${horizonImpact.swing.lvl.toUpperCase()}</span></div>
              <div class="ins-hz-t">${horizonImpact.swing.txt}</div>
            </div>
            <div class="ins-hz ${horizonImpact.position.lvl}">
              <div class="ins-hz-h">📈 POSITION<span class="impact">${horizonImpact.position.lvl.toUpperCase()}</span></div>
              <div class="ins-hz-t">${horizonImpact.position.txt}</div>
            </div>
            <div class="ins-hz ${horizonImpact.invest.lvl}">
              <div class="ins-hz-h">🚀 INVEST<span class="impact">${horizonImpact.invest.lvl.toUpperCase()}</span></div>
              <div class="ins-hz-t">${horizonImpact.invest.txt}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- TRANSACTION TABLE -->
      <div class="ins-tx-wrap">
        <div class="ins-tx-h">
          <h4>Form 4 Transactions · ${T.ticker} · last 90 days</h4>
          <div class="legend">
            <span class="ck"><span class="dot" style="background:var(--accent)"></span>C-suite</span>
            <span class="ck"><span class="dot" style="background:var(--info)"></span>EVP</span>
            <span class="ck"><span class="dot" style="background:var(--warn)"></span>Director</span>
          </div>
        </div>
        <table class="ins-tx-table">
          <thead><tr>
            <th>Date</th>
            <th>Insider</th>
            <th>Title</th>
            <th>Type</th>
            <th class="r">Shares</th>
            <th class="r">Price</th>
            <th class="r">Value</th>
          </tr></thead>
          <tbody>
            ${txs.slice(0, 50).map(t => {
              const isBuy = isBuyTx(t);
              const lvl = titleLevel(t.title);
              const cls = isBuy ? 'buy' : 'sell';
              const tPx = +(t.price || 0);
              const delta = px && tPx ? (tPx - px) / px * 100 : 0;
              const valPct = (Math.abs(t.value || 0) / maxValue) * 100;
              return `<tr>
                <td><span class="date">${t.date || '—'}</span></td>
                <td><span class="name">${t.name || '—'}</span></td>
                <td><span class="title-pill ${titlePillCls(lvl)}">${titleShort(t.title)}</span></td>
                <td><span class="type-pill ${cls}">${isBuy ? '+ BUY' : '− SELL'}</span></td>
                <td class="num">${(t.shares || 0).toLocaleString()}</td>
                <td class="price-cell">
                  <div class="px">$${tPx.toFixed(2)}</div>
                  ${px && tPx ? `<div class="delta ${delta > 0 ? 'pos' : delta < 0 ? 'neg' : ''}">${delta >= 0 ? '+' : ''}${delta.toFixed(1)}% vs now</div>` : ''}
                </td>
                <td class="value-cell">
                  <div class="v-amt">$${(t.value || 0).toLocaleString()}</div>
                  <div class="v-bar"><div class="v-bar-f ${cls}" style="width:${valPct.toFixed(0)}%"></div></div>
                </td>
              </tr>`;
            }).join('')}
          </tbody>
        </table>
      </div>`;
  } catch (e) {
    body.innerHTML = `<div class="ins-empty"><div class="ico">⚠</div><div class="h">Could not load insider data</div><div class="sub">${e.message}</div></div>`;
  }
}

export function dispose() { /* no-op */ }

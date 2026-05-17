// subtabs/insider/view.js — HTML builders for the Insider sub-tab.
// Verdict banner + 3 stat tiles + Pattern Intelligence + Horizon Impact card
// + Form-4 transactions table. Returns one big HTML string.

import { isBuyTx, titleLevel, titlePillCls, titleShort } from './aggregate.js';

export function buildBody(T, txs, agg) {
  const { totalBuys, totalSells, buyValue, sellValue, buyShares, sellShares,
          csuiteSells, csuiteBuys, netValue, totalTx, dayRange,
          avgSellPx, avgBuyPx, px, netPctMcap, sellVsNow, maxValue,
          tone, verdict, narrative, horizon } = agg;

  const buyBarWidth  = totalTx > 0 ? (totalBuys  / totalTx) * 100 : 0;
  const sellBarWidth = totalTx > 0 ? (totalSells / totalTx) * 100 : 0;
  const netSign      = netValue >= 0 ? '+' : '';

  return `
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
          <div class="ins-hz ${horizon.swing.lvl}">
            <div class="ins-hz-h">⚡ SWING<span class="impact">${horizon.swing.lvl.toUpperCase()}</span></div>
            <div class="ins-hz-t">${horizon.swing.txt}</div>
          </div>
          <div class="ins-hz ${horizon.position.lvl}">
            <div class="ins-hz-h">📈 POSITION<span class="impact">${horizon.position.lvl.toUpperCase()}</span></div>
            <div class="ins-hz-t">${horizon.position.txt}</div>
          </div>
          <div class="ins-hz ${horizon.invest.lvl}">
            <div class="ins-hz-h">🚀 INVEST<span class="impact">${horizon.invest.lvl.toUpperCase()}</span></div>
            <div class="ins-hz-t">${horizon.invest.txt}</div>
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
            const lvl   = titleLevel(t.title);
            const cls   = isBuy ? 'buy' : 'sell';
            const tPx   = +(t.price || 0);
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
}

// subtabs/ruleengine/tab_consensus.js — Per-Tab Consensus Matrix.
// For each of 12 FD tabs, returns a {tab, icon, kind, conf, ev} verdict
// based on that tab's underlying signals. kind ∈ {bull, bear, wait, na}.
// Pure function over T — no DOM.

const _v = (kind, conf, ev) => ({ kind, conf, ev });

export function buildTabVerdicts(T) {
  const out = [];

  const verdict   = (T.verdict || T.decision?.verdict || '—').toString().toUpperCase();
  const score     = +(T.score || 0);
  const rrRatio   = +(T.rr_ratio || T.rr || 0);
  const setupFamily = T.setup_family || T.setup || '—';
  const tc        = T.theory_confluence || {};
  const tcStates  = tc.states || {};
  const tcDir     = tc.direction;

  // 1. Overview — uses canonical verdict
  out.push({ tab: 'Overview', icon: '📋', ...(() => {
    if (verdict === 'BUY' || verdict === 'STRONG BUY')        return _v('bull', 'high', `Score ${score} · R:R ${rrRatio.toFixed(1)}× · ${setupFamily}`);
    if (verdict === 'WATCH' || verdict === 'HOLD')             return _v('wait', 'med',  `Score ${score} · awaiting trigger`);
    if (['SHORT','SELL','AVOID'].includes(verdict))            return _v('bear', 'high', `Score ${score} · ${T.bear_type || 'bearish'}`);
    return _v('na', 'low', '—');
  })() });

  // 2. Plan — same verdict + entry quality
  out.push({ tab: 'Plan', icon: '🎯', ...(() => {
    const eq = (T.entry_quality || '').toUpperCase();
    if (verdict === 'BUY' && (eq === 'FRESH' || eq === 'PULLBACK' || eq === 'VALID')) return _v('bull', 'high', `${eq} entry · stop $${(T.stop||0).toFixed(2)}`);
    if (verdict === 'BUY' && eq === 'EXTENDED')                                        return _v('wait', 'med',  `EXTENDED — wait for pullback`);
    if (verdict === 'BUY' && eq === 'MISSED')                                          return _v('wait', 'low',  `MISSED — re-entry blocked`);
    if (['SHORT','SELL'].includes(verdict))                                            return _v('bear', 'high', `Short plan · stop ${(T.stop||0).toFixed(2)}`);
    return _v('wait', 'low', `${eq || 'no plan'} `);
  })() });

  // 3. Technicals — pillar score + EMA stack + RSI/MACD
  out.push({ tab: 'Technicals', icon: '📈', ...(() => {
    const tcr = T.tech_score || 0, tcrm = T.tech_max || 35;
    const stackBull = !!T.above_50ema && !!T.above_200sma;
    const macdBull  = !!T.macd_bullish;
    const rsi       = T.rsi;
    const tcRatio   = tcr / tcrm;
    if (tcRatio >= 0.7 && stackBull && macdBull) return _v('bull', 'high', `${tcr.toFixed(0)}/${tcrm} · stack bull · MACD↑ · RSI ${rsi?.toFixed(0)}`);
    if (tcRatio >= 0.5 && stackBull)             return _v('bull', 'med',  `${tcr.toFixed(0)}/${tcrm} · stack bull`);
    if (!stackBull && tcRatio < 0.4)             return _v('bear', 'high', `${tcr.toFixed(0)}/${tcrm} · below 50EMA · weak`);
    if (rsi >= 70)                                return _v('wait', 'med',  `RSI ${rsi.toFixed(0)} overbought`);
    if (rsi <= 30)                                return _v('wait', 'med',  `RSI ${rsi.toFixed(0)} oversold`);
    return _v('wait', 'med', `${tcr.toFixed(0)}/${tcrm} · mixed signals`);
  })() });

  // 4. Models — theory_confluence direction
  out.push({ tab: 'Models', icon: '🧠', ...(() => {
    const dir   = (tcDir || '').toUpperCase();
    const bull  = tc.bull_count || 0;
    const ct    = (tc.eligible_theories || []).length || 3;
    if (dir === 'BULLISH') return _v('bull', bull >= 3 ? 'high' : 'med', `Confluence ${bull}/${ct} bullish · ${tcStates.wyckoff || 'NA'}`);
    if (dir === 'BEARISH') return _v('bear', 'high', `Confluence bearish · ${tcStates.wyckoff || 'NA'}`);
    return _v('wait', 'low', `${bull}/${ct} aligned · no confluence`);
  })() });

  // 5. TradingView — uses tv_rec_str
  out.push({ tab: 'TradingView', icon: '📊', ...(() => {
    const tv = (T.tv_rec_str || '').toUpperCase();
    if (tv === 'STRONG_BUY')                  return _v('bull', 'high', `TV consensus STRONG BUY`);
    if (tv === 'BUY')                          return _v('bull', 'med',  `TV consensus BUY`);
    if (tv === 'HOLD' || tv === 'NEUTRAL')    return _v('wait', 'med',  `TV consensus HOLD`);
    if (tv === 'SELL')                         return _v('bear', 'med',  `TV consensus SELL`);
    if (tv === 'STRONG_SELL')                 return _v('bear', 'high', `TV consensus STRONG SELL`);
    return _v('na', 'low', 'no TV rating');
  })() });

  // 6. SMC — smc_direction + bos_choch
  out.push({ tab: 'SMC', icon: '🏦', ...(() => {
    const smc = T.smc || {};
    const dir = (smc.smc_direction || '').toLowerCase();
    const bc  = smc.bos_choch || {};
    if (dir === 'bullish' || bc.bos_bullish) return _v('bull', 'high', `${bc.last_structure || 'HH/HL'} · ${bc.bos_bullish ? 'BOS bull' : 'markup'}`);
    if (dir === 'bearish' || bc.bos_bearish) return _v('bear', 'high', `${bc.last_structure || 'LH/LL'} · BOS bear ${bc.bos_bars_ago != null ? bc.bos_bars_ago + 'b ago' : ''}`);
    return _v('wait', 'low', 'no clear structure');
  })() });

  // 7. Fundamentals — long_term_score + Zacks VGM
  out.push({ tab: 'Fundamentals', icon: '💰', ...(() => {
    const lt    = T.long_term_score;
    const vgm   = (T.zacks_grades || {}).vgm;
    const upPct = (T.analyst_full || T.analyst || {}).upside_pct;
    if (lt >= 80 || vgm === 'A')              return _v('bull', 'high', `Score ${lt?.toFixed(0)} · VGM ${vgm || 'B+'} · ${upPct ? `+${upPct.toFixed(1)}%` : 'strong'}`);
    if (lt >= 60 || vgm === 'B')              return _v('wait', 'med',  `Score ${lt?.toFixed(0)} · VGM ${vgm}`);
    if (lt < 50 || vgm === 'F')               return _v('bear', 'med',  `Score ${lt?.toFixed(0)} · VGM ${vgm} · weak quality`);
    return _v('wait', 'low', `Score ${lt?.toFixed(0)}`);
  })() });

  // 8. Sentiment — composite + insider net
  out.push({ tab: 'Sentiment', icon: '💬', ...(() => {
    const sentScore = (T.sentiment || {}).score;
    const sentMax   = (T.sentiment || {}).max || 10;
    const ins       = T.insider_full || T.insider || {};
    const netIns    = ins.net_signal != null ? ins.net_signal : ((ins.buys || 0) - (ins.sells || 0));
    const newsMom   = (T.news_sentiment_score || {}).momentum;
    if (sentScore >= 7 && (newsMom === 'bullish' || netIns > 2))                  return _v('bull', 'high', `Sent ${sentScore}/10 · news ${newsMom || 'bull'} · ins +${netIns}`);
    if (sentScore <= 3 || newsMom === 'bearish' || netIns < -3)                    return _v('bear', 'med',  `Sent ${sentScore}/10 · news ${newsMom || 'weak'} · ins ${netIns}`);
    return _v('wait', 'low', `Sent ${sentScore}/${sentMax}`);
  })() });

  // 9. Options — options_kpis.verdict
  out.push({ tab: 'Options', icon: '📞', ...(() => {
    const k       = T.options_kpis || {};
    const v       = (k.verdict || {}).verdict || k.verdict;
    const conf    = ((k.verdict || {}).confidence || '').toUpperCase();
    const vs      = (typeof v === 'string' ? v : '').toUpperCase();
    const confKey = conf === 'HIGH' ? 'high' : conf === 'MED' ? 'med' : 'low';
    if (vs === 'BULLISH') return _v('bull', confKey, `IV ${k.iv_rank?.toFixed(0) || '?'} · UOA ${k.uoa_calls || 0}c/${k.uoa_puts || 0}p`);
    if (vs === 'BEARISH') return _v('bear', confKey, `Skew bear · UOA ${k.uoa_calls || 0}c/${k.uoa_puts || 0}p`);
    if (vs === 'MIXED')   return _v('wait', confKey, `Mixed flow`);
    return _v('na', 'low', 'no options data');
  })() });

  // 10. News — news momentum + article count
  out.push({ tab: 'News', icon: '📰', ...(() => {
    const polynews  = T.news_articles || T.polygon_news || [];
    const polyscore = T.news_sentiment_score || T.polygon_news_score || {};
    const ct        = polynews.length;
    if (ct === 0) return _v('na', 'low', 'no recent news');
    const articleSent = polynews.map(n => {
      const i = (n.insights || []).find(x => (x.ticker || '').toUpperCase() === T.ticker);
      return i?.sentiment || n.sentiment || 'neutral';
    });
    const bull = articleSent.filter(s => s === 'positive').length;
    const bear = articleSent.filter(s => s === 'negative').length;
    const mom  = (typeof polyscore === 'object' ? polyscore.momentum : null) || 'neutral';
    if (mom === 'bullish' || bull > bear * 1.5) return _v('bull', bull >= 5 ? 'high' : 'med', `${bull}↑ ${bear}↓ · ${mom}`);
    if (mom === 'bearish' || bear > bull * 1.5) return _v('bear', 'med',                       `${bull}↑ ${bear}↓ · ${mom}`);
    return _v('wait', 'low', `${bull}↑ ${bear}↓ neutral · ${ct} articles`);
  })() });

  // 11. Insider — net flow + C-suite
  out.push({ tab: 'Insider', icon: '🥷', ...(() => {
    const ins    = T.insider_full || T.insider || {};
    const netIns = ins.net_signal != null ? ins.net_signal : ((ins.buys || 0) - (ins.sells || 0));
    const ceoBuy = !!ins.ceo_buy;
    const cfoBuy = !!ins.cfo_buy;
    if ((netIns >= 3 && ceoBuy) || (netIns >= 5 && cfoBuy)) return _v('bull', 'high', `Net +${netIns} · CEO ${ceoBuy ? '✓' : '·'} · CFO ${cfoBuy ? '✓' : '·'}`);
    if (netIns >= 2)                                          return _v('bull', 'med',  `Net +${netIns} (${ins.buys || 0}↑/${ins.sells || 0}↓)`);
    if (netIns <= -3)                                         return _v('bear', 'med',  `Net ${netIns} (${ins.buys || 0}↑/${ins.sells || 0}↓)`);
    return _v('wait', 'low', `Net ${netIns >= 0 ? '+' : ''}${netIns}`);
  })() });

  // 12. Institution — composite of Zacks + inst_trend + smart-money signals
  out.push({ tab: 'Institution', icon: '🏛', ...(() => {
    const inst    = T.inst_trend || {};
    const trend   = (inst.inst_trend || '').toLowerCase();
    const instPct = inst.inst_pct;
    const zr      = T.zacks_rank1;
    const zsell   = T.zacks_sell;
    if (zr && (trend === 'increasing' || instPct >= 70)) return _v('bull', 'high', `Zacks #1 · inst ${trend} · ${instPct?.toFixed(0)}% own`);
    if (zr)                                                return _v('bull', 'med',  `Zacks Rank #1 · inst ${trend || 'stable'}`);
    if (zsell || trend === 'decreasing')                   return _v('bear', 'med',  `${zsell ? 'Zacks #5' : 'inst outflow'} · ${instPct?.toFixed(0)}% own`);
    if (instPct >= 50)                                     return _v('wait', 'med',  `Inst ${instPct?.toFixed(0)}% · ${trend || 'stable'}`);
    return _v('wait', 'low', `${trend || 'stable'} · ${instPct ? instPct.toFixed(0) + '%' : 'limited data'}`);
  })() });

  return out;
}

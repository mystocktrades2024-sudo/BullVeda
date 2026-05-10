// tabs/strategies/strategies.js — Strategy Engine tab thin orchestrator.
//
// Sub-modules:
//   constants.js — REGIME_META + STRATEGY_ALIASES + REGIME_KEY_MAP
//   banner.js    — hero banner + leaderboard + filter chip bar (#strategiesBanner)
//   cards.js     — per-strategy card renderer (#strategiesList)
//   counts.js    — setup_counts + verdict_counts panels (#setupCountsBody + #verdictCountsBody)

import { getData, $ }                        from '../../core/shared.js';
import { REGIME_KEY_MAP }                    from './constants.js';
import { buildBanner, filterStrategies }     from './banner.js';
import { buildCards }                        from './cards.js';
import { renderCountsPanels }                from './counts.js';

export function render() {
  const DATA       = getData();
  const STRATEGIES = window.STRATEGIES;
  const tbs        = (DATA.performance && DATA.performance.tickers_by_strategy) || {};

  const currentRegime = (DATA.regime?.regime4 || '').toLowerCase();
  const regKey        = REGIME_KEY_MAP[currentRegime];
  const isStrategyActive = s => s.status === 'ACTIVE' && (!regKey || s.regimes.includes(regKey));

  const active             = STRATEGIES.filter(s => s.status === 'ACTIVE');
  const planned            = STRATEGIES.filter(s => s.status === 'PLANNED');
  const totalActiveInRegime = active.filter(isStrategyActive).length;

  $('strategiesBanner').innerHTML = buildBanner(STRATEGIES, active, planned, totalActiveInRegime, regKey);
  $('strategiesList').innerHTML   = buildCards(STRATEGIES, tbs, isStrategyActive, regKey);
  renderCountsPanels(DATA.setup_counts, DATA.verdict_counts);
}

export function dispose() { /* no-op */ }

// Auto-bind helpers to window for inline-HTML onclick callers
if (typeof window !== 'undefined') {
  window.seFilterStrategies = filterStrategies;
}

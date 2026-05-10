// subtabs/sentiment/sentiment.js — Sentiment sub-tab thin orchestrator.
//
// Sub-modules:
//   aggregate.js — pure data transform: news/insider/EODHD/composite tone
//                  + sparkline SVG. Plus fmt2/dollarsM helpers.
//   cards.js     — verdict banner + 3 primary source cards + catalyst/social
//                  row + composite breakdown + horizon impact + (optional)
//                  short-pressure card via window._renderShortPressureCard.
//
// Entry replaces a bare `$('sentimentBody')` reference (ReferenceError in
// the original) with document.getElementById, and guards the
// _renderShortPressureCard window helper rather than failing if it's absent.

import { aggregate } from './aggregate.js';
import { buildBody } from './cards.js';

const _T = () => (window.__getDetailTicker ? window.__getDetailTicker() : window.T);

export function render() {
  const T = _T();
  if (!T) return;
  const target = document.getElementById('sentimentBody');
  if (!target) return;

  const agg = aggregate(T);
  target.innerHTML = buildBody(T, agg);
}

export function dispose() { /* no-op */ }

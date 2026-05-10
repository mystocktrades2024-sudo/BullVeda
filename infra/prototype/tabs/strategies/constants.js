// tabs/strategies/constants.js — module-private constants for the Strategy Engine.
// REGIME_META = pretty labels + status-pill class per regime.
// STRATEGY_ALIASES = mapping of display name → aliases used in
//   DATA.performance.tickers_by_strategy lookup keys.
// REGIME_KEY_MAP = current regime4 → short key used inside STRATEGIES[].regimes[].

export const REGIME_META = {
  RoT:   { label: 'Risk-On Trending', cls: 'pass' },
  RoC:   { label: 'Risk-On Choppy',   cls: 'info' },
  Off:   { label: 'Risk-Off',         cls: 'warn' },
  Panic: { label: 'Panic',            cls: 'fail' },
};

export const STRATEGY_ALIASES = {
  'Core Swing Engine':  [],
  '10-Week Pullback':   ['10-Week Pullback'],
  'Mean Reversion':     ['Mean Reversion'],
  'Sector Rotation':    ['Sector Rotation'],
  'VCP Breakout':       ['VCP Breakout'],
  'Pocket Pivot':       ['Pocket Pivot'],
  'RS New High':        ['52wk Breakout', 'RS New High'],
  'Insider Buying':     ['Insider Buying'],
  'Insider Cluster':    ['Insider Cluster'],
  'Gap Holds':          ['Gap Holds', 'Gap Hold'],
  'Short Squeeze':      ['Short Squeeze', 'Breakdown'],
  'Earnings Run-Up':    ['Earnings Run-Up'],
  'Golden Cross':       ['Golden Cross', 'Trend Continuation'],
  'Bull Flag':          ['Bull Flag', 'Squeeze Expansion'],
  'Volume Breakout':    ['Volume Breakout', 'EMA21 Pullback'],
  'NR7 / Inside Day':   ['NR7', 'Inside Day'],
  'Volume Dry-Up':      ['Volume Dry-Up'],
  'OBV Divergence':     ['OBV Divergence', 'OBV Bull Div'],
  'Beat & Raise PEAD':  ['PEAD', 'Beat and Raise'],
};

export const REGIME_KEY_MAP = {
  'risk_on_trending':  'RoT',
  'risk_on_choppy':    'RoC',
  'risk_off_trending': 'Off',
  'panic':             'Panic',
};

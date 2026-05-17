// =============================================================================
// SHARED TOOLTIP DICTIONARY — plain-English explanations for trading terms
// Loaded by dashboard.html and elite-detail.html. Each definition is 2-3 lines
// written for someone who has never traded before.
// =============================================================================

const TIPS = {
  // -- Verdict / Stage --
  'verdict':   'The system\'s recommendation: BUY (good setup, take a position), WATCH (almost ready, wait for confirmation), SHORT (bet on price falling), or AVOID (skip this one).\nIt combines technicals, fundamentals, and market context into one call.',
  'stg':       'Stage: same as Verdict. BUY / WATCH / SHORT / AVOID — what the system thinks you should do today.',
  'stage':     'The system\'s recommendation: BUY (good setup, take a position), WATCH (almost ready, wait for confirmation), SHORT (bet on price falling), or AVOID (skip this one).',
  'buy':       'BUY signal — the setup looks ready right now. Entry zone is live and the gates are clear.',
  'watch':     'WATCH signal — close to ready but missing one or two confirmations. Set an alert and check back.',
  'short':     'SHORT signal — bearish setup. You\'d profit if the price falls. Riskier and only allowed in specific market regimes.',
  'avoid':     'AVOID — too many things are wrong. Skip this ticker today.',

  // -- Score / Pillars --
  'score':     'Conviction score from 0–100. The sum of 5 independent pillars (technicals, fundamentals, smart money, news, quality).\n70+ = strong setup. 60–70 = decent. <60 = weak — better opportunities exist.',
  'bap':       'Best-and-Powerful score — the same 0–100 conviction number used to rank picks. Higher is better.',
  'tech':      'Technical pillar score (out of 38). Measures price action quality: trend strength, volume, momentum, support/resistance, RS, weekly alignment.',
  'fund':      'Fundamentals pillar score (out of 30). Revenue growth, profit margin, balance sheet health, valuation, analyst revisions.',
  'smc':       'Smart Money Concepts pillar (out of 10). Whether the chart shows institutional order blocks, liquidity sweeps, and structural breaks.',
  'news':      'News sentiment pillar. +1 to +3 if recent headlines are bullish, −1 to −3 if bearish, 0 if neutral or no news.',
  'sentiment': 'How positive or negative recent news is for this stock — bullish, neutral, or bearish.',

  // -- Price / change --
  'px':        'Price — the latest close (or last live tick during market hours).',
  'price':     'Price — the latest close (or last live tick during market hours).',
  'now':       'NOW — the current price right now. Updates live during market hours.',
  '%d':        'Percent change today — how much the stock has moved since yesterday\'s close.',
  '5d':        'Percent change over the last 5 trading days (one week).',
  '20d':       'Percent change over the last 20 trading days (about one month).',
  'pct_chg':   'Percent change today — how much the stock has moved since yesterday\'s close.',

  // -- Volume / volatility --
  'rvol':      'Relative Volume — today\'s volume vs the 20-day average. 1.5× means trading 50% more than usual.\nHigh RVOL signals real interest from buyers or sellers, not just background noise.',
  'volume':    'Number of shares traded. High volume on a price move = strong conviction. Low volume = weak signal.',
  'atr':       'Average True Range — the typical daily price swing in dollars. ATR% expresses it as a percentage.\nIt tells you how volatile the stock is and is used to size stops.',
  'atr%':      'ATR as a percentage of price. 2% = the stock typically moves $2 per $100 in a day. Bigger = more volatile.',
  'iv':        'Implied Volatility — what the options market expects future moves to be. High IV = market expects big swings.',
  'vix':       'VIX — the "fear index" of the S&P 500. Below 16 = calm market. Above 22 = elevated. Above 35 = panic.',
  'beta':      'How much the stock moves vs the S&P 500. Beta 1.0 = moves with the market. 1.5 = 50% more volatile. <1 = less volatile.',
  'sigma':     'σ (sigma) — annualized volatility (yearly standard deviation of returns). 30% means a typical year sees ±30% swings.',
  'σ':         'σ (sigma) — annualized volatility (yearly standard deviation of returns). 30% means a typical year sees ±30% swings.',

  // -- Momentum indicators --
  'rsi':       'Relative Strength Index — momentum on a 0–100 scale.\nAbove 70 = overbought (might pull back). Below 30 = oversold (might bounce). 50 is neutral.',
  'macd':      'MACD — measures whether short-term momentum is accelerating or fading vs long-term momentum. Bullish = trend turning up.',
  'stochrsi':  'Stochastic RSI — a faster, more reactive version of RSI. Hits 80+ on rallies, 20- on selloffs.',
  'mfi':       'Money Flow Index — RSI weighted by volume. Above 80 = overbought with high volume. Below 20 = oversold.',
  'obv':       'On-Balance Volume — adds volume on up-days and subtracts it on down-days. Rising OBV = accumulation.',
  'cmf':       'Chaikin Money Flow — measures buying vs selling pressure over 20 days. Positive = buying, negative = selling.',
  'adx':       'Average Directional Index — trend strength (0–100). Above 25 = real trend. Below 20 = sideways/choppy.',

  // -- Trend / structure --
  'ema':       'Exponential Moving Average — average price over N days, weighted toward recent days. EMA21 = last 21 days, EMA50 = last 50.',
  'sma':       'Simple Moving Average — average closing price over N days, equal weight. SMA200 = "are we in a long-term uptrend?"',
  'vwap':      'Volume-Weighted Average Price — the average price weighted by volume.\nAbove VWAP = buyers in control today. Below = sellers in control.',
  'rs':        'Relative Strength rank vs the S&P 500 (1–99). RS 80 means this stock outperformed 80% of others.\nLeaders tend to keep leading.',
  'rs rank':   'Relative Strength rank vs the S&P 500 (1–99). RS 80 means this stock outperformed 80% of others.',

  // -- Trade plan --
  'entry':     'Entry zone — the price range where buying makes sense. Inside this range you have a tight stop and good R:R.\nOutside it, the trade is either extended or invalidated.',
  'ent':       'Entry zone low — the lower end of the buy range.',
  'entry zone':'The price range where buying makes sense — tight stop, good risk/reward. Outside this range, the trade is either extended or no longer valid.',
  'stop':      'Stop loss — the price where you exit if the trade goes wrong.\nAlways set this BEFORE entering. It defines exactly how much you can lose on this trade.',
  't1':        'First target — where you take partial profits (typically half) and move your stop to break-even.\nTrim here means the trade can\'t become a loser anymore.',
  't2':        'Second target — where you exit the rest of the position. Usually 1.6–2.0× the move from entry to T1.',
  'r:r':       'Risk-to-Reward ratio. 1:3 means you risk $1 to make $3.\n3:1 or better is the minimum to make money long-term, even with a 50% win rate.',
  'rr':        'Risk-to-Reward ratio. 1:3 means you risk $1 to make $3. 3:1+ is the minimum for long-term profitability.',
  'r:r t1':    'Risk-to-Reward calculated against the first target. (T1 − Entry) / (Entry − Stop).',
  'spark':     'Mini-chart of recent price action — shows the trend at a glance.',
  'ruler':     'Visual map: Stop → Entry → Now → T1 → T2 across the price range. Your current position on this ruler.',
  'earn':      'Earnings — days until the next earnings report. Within 7 days = high gap risk. Within 14 = trim before report.',
  'earnings':  'Days until the next earnings report. Earnings are binary events that can gap a stock 10–20% overnight in either direction.',
  'n':         'News — was there any meaningful news in the last few days? +/− indicates positive or negative sentiment.',
  'n news':    'News indicator. + = bullish news, − = bearish, · = no news.',
  'sect':      'Sector — the broad industry the stock belongs to (Technology, Energy, Healthcare, etc.).',
  'sector':    'Sector — the broad industry the stock belongs to (Technology, Energy, Healthcare, etc.).',
  'industry':  'Industry — a more specific grouping within a sector (e.g. "Semiconductors" within Technology).',
  'setup':     'Setup family — the kind of trade pattern this is (Trend Continuation, Breakout, Pullback, Reversal). Each has its own playbook.',
  'setup family': 'Setup family — the kind of trade pattern this is (Trend Continuation, Breakout, Pullback, Reversal). Each has its own playbook.',

  // -- Sizing --
  'size':      'Position size — number of shares (or % of portfolio) to put into this trade. Calculated from your risk tolerance and the distance to your stop.',
  'shares':    'Shares — how many units of the stock to buy. (Position size $) / (Entry price).',
  'alloc':     'Allocation — what % of your total portfolio is in this trade. Higher score / better R:R = bigger allocation.',
  'allocation':'Allocation — what % of your total portfolio is in this trade. Higher score / better R:R = bigger allocation.',
  'kelly':     'Kelly Fraction — mathematically optimal position size given win rate and R:R. Capped at 25% to prevent ruin in real-world conditions.',

  // -- Fundamentals --
  'rev':       'Revenue growth — sales growth year-over-year. Above 8% is healthy. 15%+ is strong.',
  'rev growth':'Revenue growth — sales growth year-over-year. Above 8% is healthy, 15%+ is strong.',
  'margin':    'Net profit margin — what % of revenue ends up as profit after all expenses. Above 10% is healthy.',
  'net margin':'Net profit margin — what % of revenue ends up as profit after all expenses.',
  'gross margin':'Gross margin — revenue minus cost of goods sold, as % of revenue. Software ~70%+, retail ~30%.',
  'op margin': 'Operating margin — profit before interest and taxes, as % of revenue. Excludes one-time items.',
  'roe':       'Return on Equity — profit divided by shareholder equity. Higher = better use of investor capital. >15% is excellent.',
  'roa':       'Return on Assets — profit divided by total assets. Measures how efficiently the company uses everything it owns.',
  'pe':        'Price-to-Earnings ratio — price divided by annual earnings per share. Lower = cheaper, higher = more expensive (or higher growth expected).',
  'p/e':       'Price-to-Earnings — price divided by annual earnings per share. The S&P 500 averages around 20.',
  'fwd pe':    'Forward Price-to-Earnings — P/E based on next year\'s expected earnings. Better forward-looking than trailing P/E.',
  'peg':       'PEG ratio — P/E divided by growth rate. PEG of 1.0 is "fair price for the growth". Below 1 = potentially undervalued.',
  'pt':        'Price Target — the average analyst price target. Comparing it to current price gives you analyst upside.',
  'analyst':   'Analyst consensus — the buy/hold/sell view averaged across all Wall Street analysts who cover the stock.',
  'consensus': 'Analyst consensus — the buy/hold/sell view averaged across all Wall Street analysts who cover the stock.',
  'upside':    'Upside — how much the stock would need to rise to hit the analyst price target, as a percentage.',
  'beat':      'Earnings beats — how often the company beats analyst expectations. Consistent beats build trust.',

  // -- Smart money / insiders / options --
  'insider':   'Insider activity — buys and sells by company officers and directors. Insiders buying = strong signal (they have an edge).',
  'insider buys':'Insider buys — open-market purchases by company officers/directors in the last 30 days. 2+ buys is a strong signal.',
  'insider sells':'Insider sells — open-market sales by insiders. Some selling is normal (compensation), heavy selling is a warning.',
  'short interest':'Short interest — % of float being bet against the stock. Above 10% = potential squeeze if price rises.',
  'iv rank':   'Implied Volatility Rank (0–100) — where current options IV sits vs the last 12 months. High IV rank = expensive options.',
  'p/c ratio': 'Put-to-Call Ratio — bearish vs bullish options activity. Above 1.0 = more bearish bets.',

  // -- Market regime --
  'regime':    'Market regime — the overall environment. Risk-On Trending = chase strength. Choppy = be selective. Risk-Off = small sizes.\nPanic = stay flat. The system gates trades by regime.',
  'breadth':   'Market breadth — what % of stocks are above their 50-day moving average. Above 60% = healthy bull. Below 40% = correction.',
  'distribution':'Distribution day — a 0.2%+ down day on heavier volume than the prior day. 4–5 in 25 days = institutions selling.',

  // -- Elliott Wave --
  'wave':      'Elliott Wave — the theory that markets move in 5-wave bullish impulses and 3-wave (A-B-C) corrections at every timeframe.',
  'w0':        'W0 — the starting low of the current Elliott Wave count. The trade idea is invalid if price breaks below this.',
  'w1':        'W1 — Wave 1, the first impulse up after a low. Often muted and mistaken for a counter-trend bounce.',
  'w2':        'W2 — Wave 2, the pullback after Wave 1. Must not breach W0. Typically retraces 50–62% of W1.',
  'w3':        'W3 — Wave 3, the strongest, longest leg. Cannot be the shortest of waves 1, 3, 5. Volume expands.',
  'w4':        'W4 — Wave 4, a sideways/complex correction after W3. Cannot overlap into W1\'s price territory.',
  'w5':        'W5 — Wave 5, the final leg. Often shows momentum divergence vs W3.',
  'fibonacci': 'Fibonacci levels — ratios (38.2%, 61.8%, etc.) that markets respect for retracements and extensions. Used to project targets.',
  'fib':       'Fibonacci levels — ratios (38.2%, 61.8%, etc.) that markets respect for retracements and extensions.',

  // -- Wyckoff --
  'wyckoff':   'Wyckoff Method — the framework that markets cycle through Accumulation (smart money buying) and Distribution (smart money selling) phases.',
  'accumulation':'Accumulation — smart money quietly buying. Range-bound, lower volatility, eventual breakout up.',
  'distribution':'Distribution — smart money quietly selling. Range-bound near highs, eventual breakdown.',
  'sc':        'Selling Climax — the panic low with maximum volume and fear. Often marks the bottom of the accumulation range.',
  'ar':        'Automatic Rally — the bounce after the SC, establishing the top of the trading range.',
  'creek':     'Creek — the key resistance line in the trading range. Breaking above = "Sign of Strength" (SOS) confirms accumulation.',
  'spring':    'Spring — a brief shakeout below support that traps weak hands, then snaps back. Often the BEST entry in accumulation.',
  'utad':      'Upthrust After Distribution — a fake breakout above resistance that traps bulls. Often the BEST short entry.',
  'phase a':   'Phase A — Stopping the prior trend. SC, AR, ST establish the new range.',
  'phase b':   'Phase B — Building the cause. Range trades sideways while operators absorb supply.',
  'phase c':   'Phase C — Testing (Spring or UTAD). The shakeout that traps the wrong-way crowd. Best entry zone.',
  'phase d':   'Phase D — Sign of Strength/Weakness. Range breaks decisively. Pullback (LPS) offers a second entry.',
  'phase e':   'Phase E — Markup or Markdown. Trend leaves the range. The "cause" produces the "effect".',

  // -- Monte Carlo / quant --
  'mu':        'μ (mu) — annualized expected return (drift). Built from fundamentals, momentum, and macro. Positive μ = stock should grow over time.',
  'μ':         'μ (mu) — annualized expected return (drift). Positive μ = stock should grow over time.',
  'sharpe':    'Sharpe ratio — return per unit of risk. Above 1.0 is good, above 2.0 is excellent. Negative = losing money over time.',
  'sharpe ratio':'Sharpe ratio — return per unit of risk. Above 1.0 is good, above 2.0 is excellent.',
  'p(profit)': 'Probability of profit — % of Monte Carlo simulations that ended above the entry price. >55% = setup leans bullish.',
  'prob. of profit':'Probability of profit — % of Monte Carlo simulations that ended above the entry price.',
  'var':       'Value at Risk — the worst-case 5% outcome. "5% VaR = $X" means there\'s a 5% chance you end below $X.',
  '5% var':    'Value at Risk — the worst-case 5% outcome. There\'s only a 5% chance the price ends below this level.',
  'ev':        'Expected Value — the average final price across all simulated paths. Higher than entry = positive expectancy.',
  'expected value':'Expected Value — the average final price across all Monte Carlo paths.',
  'p10':       'P10 — the 10th percentile. 90% of simulations ended above this price (only 10% ended worse).',
  'p25':       'P25 — the 25th percentile. 75% of simulations ended above this price.',
  'p50':       'P50 — the median. Half of simulations ended above, half below. The "typical" outcome.',
  'p75':       'P75 — the 75th percentile. Only 25% of simulations did better than this.',
  'p90':       'P90 — the 90th percentile. Only 10% of simulations did better than this — an optimistic outcome.',
  'gbm':       'Geometric Brownian Motion — the standard math model for simulating future price paths assuming constant drift and volatility.',
  'monte carlo':'Monte Carlo — running thousands of random simulated price paths to estimate the probability distribution of outcomes.',

  // -- Patterns --
  'vcp':       'Volatility Contraction Pattern — a series of progressively tighter pullbacks before a breakout. Classic Minervini setup.',
  'pullback':  'Pullback — a temporary dip in an uptrend. Buying pullbacks to support is a high-probability entry.',
  'breakout':  'Breakout — price clears a key resistance level, ideally on volume. Triggers continuation moves.',
  'squeeze':   'Squeeze — Bollinger Bands inside Keltner Channels. Compressed volatility about to expand — often violently.',
  '52wk':      '52-week breakout — price breaks above its highest level in the last year. Strong continuation signal.',
  'fresh':     'Fresh entry — price is right at the trigger level. Tight stop, clean R:R.',
  'extended':  'Extended — price has run too far past entry. R:R is bad. Wait for a pullback.',
  'shallow pb':'Shallow Pullback — price barely dipped before resuming up. Strong stocks have shallow pullbacks.',

  // -- Portfolio --
  'equity':    'Equity — total value of your account (cash + open positions at current prices).',
  'cash':      'Cash — available money not in any positions, ready to deploy.',
  'unrealized':'Unrealized P&L — paper gains/losses on open positions. Becomes "realized" when you close.',
  'realized':  'Realized P&L — actual gains/losses from closed trades. This is the money you\'ve made or lost for real.',
  'position':  'Position — an active trade (open shares of a ticker).',
  'long':      'Long — you own the stock. You profit when price rises.',
  'mfe':       'Maximum Favorable Excursion — the biggest unrealized GAIN the trade reached at any point.',
  'mae':       'Maximum Adverse Excursion — the biggest unrealized LOSS the trade reached at any point. Helps tune stops.',

  // -- Misc --
  'live':      'Live — data feed is active and updating from the market.',
  'star':      'Star rating — quick visual conviction signal. 5★ = top setup, 1★ = weak.',
  'cat tier':  'Catalyst tier — T1 (best, highest-conviction setups), T2 (good), T3 (acceptable). Drives position sizing.',
  'conviction':'Conviction tier — T1/T2/T3/WATCH. Combines score, R:R, RS, and regime. Determines size.',
  'zone':      'Zone — the price range where the setup is valid. Inside the zone = good R:R. Outside = trade has changed.',
  'win rate':  'Win rate — % of closed trades that ended profitable. Combined with R:R, this determines profit factor.',
  'profit factor':'Profit Factor — total winnings divided by total losses. Above 1.5 = consistently profitable. Above 2.0 = excellent.',
  'expectancy':'Expectancy — average $ won per $1 risked. Positive = strategy works long-term. (WinRate × AvgWin) − (LossRate × AvgLoss).',

  // -- Multi-Method sub-tabs --
  '📈 monte carlo': 'Monte Carlo — runs thousands of random simulated price paths to estimate probabilities. Independent of trend reading.',
  '🌊 elliott wave': 'Elliott Wave — identifies the current wave and projects the next move using Fibonacci ratios.',
  '⛏ wyckoff':      'Wyckoff — classifies whether smart money is accumulating (bullish) or distributing (bearish) and where in the cycle we are.',
  '🧠 expert view': 'Expert View — combines all three methods into actionable trade plans for swing, 1-3 month, and long-term horizons.',
  'paths':          'Paths — all simulated price trajectories from now to the horizon. Shows the cone of possible outcomes.',
  'distribution':   'Distribution — histogram of where the simulated paths ended. Green = profit, red = loss. Tells you the shape of the outcome.',
  'levels':         'Levels — the precise percentile prices (P5, P10, P50, P90, P95) and model parameters (μ, σ, Sharpe).',

  // -- Elliott Wave degree/mode toggles --
  'major iv':       'Major degree — multi-month to multi-year swings. Use for long-term strategic positioning.',
  'major i-v':      'Major degree — multi-month to multi-year swings. Use for long-term strategic positioning.',
  'major':          'Major degree — multi-month to multi-year swings. Use for long-term strategic positioning.',
  'intermediate':   'Intermediate degree — multi-week to multi-month swings. Use for 1-3 month trades.',
  'intermediate ①-⑤':'Intermediate degree — multi-week to multi-month swings. Use for 1-3 month trades.',
  'minor':          'Minor degree — multi-day to multi-week swings. Use for swing trading entries and exits.',
  'minor 1-5':      'Minor degree — multi-day to multi-week swings. Use for swing trading entries and exits.',
  'impulse':        'Impulse mode — 5-wave move WITH the trend. Bullish if trend is up.',
  'corrective':     'Corrective mode — 3-wave (A-B-C) move AGAINST the trend. Counter-trend pullback or bounce.',

  // -- Wyckoff phase letters (single-char A-E) --
  'a':              'Phase A — Stopping the prior trend. SC (or BC), AR, ST mark the new range boundaries.',
  'b':              'Phase B — Building the cause. Range trades sideways while smart money accumulates or distributes.',
  'c':              'Phase C — The Spring (or UTAD). Final shakeout that traps the wrong-way crowd. Often the BEST entry.',
  'd':              'Phase D — Sign of Strength (or Weakness). Range breaks on volume. LPS pullback offers second entry.',
  'e':              'Phase E — Markup or Markdown. Trend leaves the range. The "cause" produces the "effect".',

  // -- Header tags / regime labels seen on elite-detail --
  'risk on choppy': 'Risk-On Choppy — bullish regime but with whipsaws. SPY above 50EMA but breadth is mixed. Position sizes 60-70%.',
  'risk on trending':'Risk-On Trending — best regime. SPY+QQQ above 50/200 EMAs, VIX low, breadth strong. Full size on T1 setups.',
  'risk off trending':'Risk-Off Trending — bearish regime. SPY below 50EMA. Reduced size, higher score thresholds, R:R minimum 4:1.',
  'panic':          'Panic regime — VIX > 35 or breadth < 20%. Stay flat. No long entries permitted.',
  'neutral':        'Neutral regime — system can\'t classify cleanly. Be cautious and selective.',

  // -- Misc UI elements --
  'in zone':        'IN ZONE — current price is inside the entry range. You can buy now with a tight stop.',
  'in entry zone':  'IN ENTRY ZONE — current price is inside the entry range. Buy with a tight stop.',
  'approaching':    'Approaching — price is close to but not yet inside the entry zone. Set an alert.',
  'pullback':       'Pullback — temporary dip in an uptrend. Buying pullbacks to support is a high-probability entry.',
  'first pullback': 'First Pullback — the FIRST pullback after a strong move up. Statistically the highest-probability buy.',
  'shallow pb':     'Shallow Pullback — price barely dipped before resuming up. Strong stocks have shallow pullbacks.',
  'deep pb':        'Deep Pullback — price retraced 50%+ of the prior up-move. Higher risk entry.',
  'mid pb':         'Mid Pullback — price retraced 30-50% of the prior up-move. Moderate setup.',
  'continuation':   'Continuation — the trade thesis is the trend keeps going. Bull trend continues up, bear continues down.',
  'trend':          'Trend — the direction of the prevailing price movement (up, down, or sideways).',
  'below trend':    'Below Trend — price is under its key moving averages. Caution: trend support has broken.',
  'zone: strong':   'Zone: Strong — entry zone has high R:R (3:1+) and confluence with multiple support levels.',
  'zone: ok':       'Zone: OK — decent R:R (2-3:1) but missing some confluence.',
  'zone: weak':     'Zone: Weak — R:R below 2:1. Skip unless other factors are exceptional.',
  'timing: value':  'Timing: Value — you\'d be entering at a good price within the zone. Tight stop, full upside.',
  'timing: premium':'Timing: Premium — entering at the high end of the zone. Reduced upside, wider stop needed.',
  'cat t1':         'Catalyst Tier 1 — highest-conviction setup. Score 80+, regime risk-on, multiple confirmations.',
  'cat t2':         'Catalyst Tier 2 — solid setup. Score 70-79. Smaller size than T1.',
  'cat t3':         'Catalyst Tier 3 — acceptable setup. Score < 70. Smallest size.',

  // -- Scanner column shortcuts --
  '#':              'Rank within the section (1 = highest score).',
  'sym':            'Stock ticker symbol.',
  'spark':          'Sparkline — mini chart of recent price action. Quick visual of the trend.',
  'ruler (stop·ent·now·t1·t2)': 'Visual map of where current price sits between Stop, Entry, T1, and T2 levels.',

  // ─────────────────────────────────────────────────────────────────────────
  // 2026-05-04 — V-series + Kelly stack + UI surfaces shipped this sprint
  // ─────────────────────────────────────────────────────────────────────────

  // -- T1/T2/T3 disambiguation --
  // (These are the *price target* meaning. The conviction-tier T1/T2/T3 lives
  // under "conviction" / "cat t1" — context-resolved by surrounding labels.)
  't1':             'T1 — first profit target. Default plan: trim 50% here, move stop to break-even, trail the rest.\n(In a Conviction badge it means Tier-1 = full-size best-quality setup. Look at surrounding context.)',
  't2':             'T2 — second profit target. Where the remaining position closes if the trend keeps running.',
  't3':             'T3 — long-horizon target (only on Position/Invest mode plans).',
  'tier':           'Conviction tier (T1/T2/T3/WATCH). T1 = full size, T2 = half size, T3 = quarter, WATCH = no capital.',
  'conviction tier':'Conviction tier (T1/T2/T3/WATCH). Drives position size. T1 needs all 5 gates: score 88+, R:R 3.5+, RS 85+, Risk-On Trending regime, fresh entry.',

  // -- V-1 Monte Carlo (per-ticker) --
  'p(target)':      'Probability the simulated price hits T1 BEFORE the stop, over 63 trading days. Higher = better risk-adjusted setup.',
  'p(t1 1st)':      'Probability the simulated price hits T1 BEFORE the stop, over 63 trading days.',
  'p(target first)':'Probability the simulated price hits T1 BEFORE the stop. From V-1 Monte Carlo (3,000 paths × 63d).',
  'p(stop 1st)':    'Probability the simulated price hits the stop BEFORE T1. Pair with P(target) to see edge.',
  'p(stop first)':  'Probability the simulated price hits the stop BEFORE T1. Should be lower than P(target).',
  'p(neither hit)': 'Probability that neither T1 nor stop is hit within the 63-day horizon (timeout).',
  'fwd sharpe':     'Forward Sharpe — Monte-Carlo expected return divided by simulated volatility, annualized. >1.0 good, >2.0 excellent.',
  'forward sharpe': 'Forward Sharpe — Monte-Carlo expected return divided by simulated volatility, annualized.',
  'sharpe':         'Sharpe ratio — return per unit of risk. Above 1.0 good, above 2.0 excellent. Negative = losing money over time.',
  'λ jumps':        'Jump intensity — annual rate of large outlier moves (>3σ). Calibrated from history per ticker.',
  'jumps':          'Jump intensity — annual rate of large outlier moves. Captures earnings gaps and news-driven spikes.',
  'σ jump':         'Jump volatility — typical size of a single jump event in log-return terms.',
  'monte carlo':    'Monte Carlo (V-1) — runs 3,000 simulated price paths over 63 trading days using Merton jump-diffusion. Accounts for volatility AND earnings-style jumps.',

  // -- V-3 Forward Distribution --
  'forward dist':   'Forward Distribution (V-3) — empirical bootstrap from history. VaR/CVaR/P(profit) computed on rolling 10-day windows from price history.',
  'forward distribution':'Forward Distribution — empirical resampling of historical 10-day returns to estimate worst-case loss and edge.',
  'var-95':         'Value at Risk (95%) — the 5th percentile loss. There\'s a 5% chance the trade loses worse than this over the horizon.',
  'var 95':         'Value at Risk (95%) — the 5th percentile loss. 5% probability of loss worse than this.',
  'cvar-97':        'Conditional Value at Risk (97.5%) — average loss in the worst 2.5% of outcomes. The "tail expected loss".',
  'cvar 97':        'Conditional Value at Risk — average loss in the worst 2.5% of outcomes. Worse than VaR — captures how bad the tail is.',
  'cvar':           'Conditional Value at Risk — average loss in the worst-case tail. CVaR-97.5 = average of worst 2.5% outcomes.',
  'cvar-97.5':      'Conditional VaR (97.5%) — average loss in worst 2.5% of outcomes. Captures tail severity beyond VaR.',
  'n samples':      'Number of historical 10-day windows used to compute the empirical forward distribution.',

  // -- V-2 HMM Regime --
  'hmm':            'Hidden Markov Model regime detector — outputs probability the market is currently Bull, Neutral, or Bear. Uses 21d of SPY returns.',
  'hmm regime':     'HMM Regime — soft probability of Bull/Neutral/Bear market state. Pairs with the 4-regime hard classifier.',
  'p(bull)':        'Probability the HMM thinks we\'re in a Bull regime, based on SPY returns last 21 days.',
  'p(neutral)':     'Probability the HMM thinks we\'re in a Neutral regime — neither strong bull nor bear.',
  'p(bear)':        'Probability the HMM thinks we\'re in a Bear regime. High = reduce size or sit out.',
  'confidence':     'How concentrated the HMM\'s probability distribution is. 100% = strongly one regime, 0% = uniform/uncertain.',

  // -- V-4 Kelly stack --
  'drawdown mult':  'Drawdown multiplier — automatically shrinks position size when account is in drawdown. 5%+ DD → 0.85×, 10%+ → 0.65×.',
  'earnings mult':  'Earnings multiplier — shrinks size when earnings are imminent. 0-3d → 0.4×, 4-7d → 0.6×, 8-14d → 0.8×.',
  'var floor':      'VaR-floor multiplier — caps size if forward CVaR exceeds 2× per-trade risk budget. Protects from tail-risk underestimation.',
  'var floor mult': 'VaR-floor multiplier — shrinks size when CVaR-implied risk exceeds budget.',
  'final alloc':    'Final allocation % — kelly_signal × regime × VIX × drawdown × earnings × VaR-floor → final position size as % of equity.',
  'kelly':          'Kelly Criterion — optimal bet size given win rate and reward/risk. We use HALF-Kelly to reduce variance. Live stats override defaults.',

  // -- V-7 Accuracy framework --
  'accuracy':       'Accuracy framework — validates the scoring engine against realized outcomes via Kupiec POF, Christoffersen, and Basel III tests.',
  'basel':          'Basel III traffic-light — model calibration zone. Green = working, Yellow = monitor, Red = recalibrate.',
  'kupiec':         'Kupiec POF test — checks if the actual exception rate matches expected. p-value < 0.05 = reject the model.',
  'christoffersen': 'Christoffersen test — checks if exceptions cluster (bad) or are independent (acceptable).',
  'score band':     'Score band the ticker falls into (90-100, 80-89, 70-79, 60-69, <60). Used to look up historical win rate at this conviction level.',
  'tail filter':    'Tail-loss filter — demotes BUY → WATCH if score < 60 OR stars < 4. Backtest projects move from RED to GREEN Basel zone.',
  'tail-loss filter':'Tail-loss filter — demotes BUY → WATCH if score < 60 OR stars < 4.',
  'cleared':        'Tail-loss filter CLEARED — this ticker passes both score ≥ 60 AND stars ≥ 4 thresholds.',
  'demoted':        'Tail-loss filter DEMOTED — failed score ≥ 60 OR stars ≥ 4. Shown for transparency; system will not allocate capital.',

  // -- V-8 DCC-GARCH --
  'dcc':            'Dynamic Conditional Correlation — measures how correlations between assets change over time. Updates daily.',
  'dcc-garch':      'DCC-GARCH — Engle (2002) dynamic correlation model. Captures "correlations spike during crashes" without static assumptions.',
  'alpha':          'DCC α — how strongly recent shocks update the correlation estimate. Higher = more reactive.',
  'beta':           'DCC β — correlation persistence. Higher = correlations decay slowly. (Sticky — what happened yesterday matters today.)',
  'persistence':    'α + β. Close to 1 = correlations are persistent (yesterday\'s state matters). Close to 0 = noise-driven.',
  'avg corr':       'Average correlation across all open BUY pairs right now. Lower = better diversification. Spikes in crashes.',
  'avg corr now':   'Today\'s dynamic correlation. Compare to static — if higher, correlations are spiking (regime shift).',
  'avg corr static':'Static (unconditional) correlation across the full window. Reference for comparing dynamic correlation.',
  'corr spike':     'Difference: dynamic - static correlation. Positive spike = correlations rising (crash regime). Negative = diversification working.',

  // -- V-10 Student-t copula --
  'copula':         'Copula — models JOINT dependence between assets independent of marginals. Tells you if two stocks crash together.',
  'student-t':      'Student-t copula — captures TAIL dependence. Low ν = strong joint-crash risk. High ν ≈ Gaussian (no tail dep).',
  'ν':              'Degrees of freedom. Low ν (≤8) = strong joint-tail dependence (assets crash together). High ν (≥20) = near-Gaussian.',
  'nu':             'Degrees of freedom. Low ν = strong joint-tail dependence. High ν ≈ Gaussian.',
  'tail dep':       'Tail dependence (λ_L) — probability two assets crash together. 0 = independent in tails, 1 = always together.',
  'tail dependence':'Tail dependence — probability two assets crash together. 0 = independent in tails, 1 = always together.',
  'avg tail dep':   'Average tail dependence across all asset pairs. Rises during regime shifts and crashes.',
  'λ_l':            'Lower-tail dependence — probability of joint crash. Computed from copula parameters.',

  // -- V-11 CVaR optimizer --
  'cvar portfolio': 'CVaR-Optimal Portfolio — solves a Rockafellar-Uryasev LP that maximizes expected return subject to CVaR ≤ budget.',
  'optimal weight': 'Recommended portfolio weight from the CVaR optimizer. Pick weights are informational; not auto-traded.',
  'port e[r]':      'Portfolio expected return at the optimal weights.',
  'port cvar':      'Portfolio Conditional VaR — average loss in the worst 5% of joint-portfolio scenarios.',
  'port positions': 'Number of positions in the optimal portfolio after the LP solver picks weights.',
  'gross exposure': 'Total deployed capital (sum of all weights). Constraint: ≤ 80% of equity.',

  // -- S-3 / S-5 / S-6 / S-7 Strategy items --
  'cup with handle':'Cup-with-Handle — O\'Neil\'s flagship continuation pattern. U-shape consolidation + small handle pullback before breakout.',
  'wyckoff spring': 'Wyckoff Spring — price breaks below support then quickly reclaims. Bullish reversal — best Wyckoff entry.',
  'failed breakdown':'Failed Breakdown — price breaks support then snaps back. Same as Spring. Trapped shorts → squeeze up.',
  'sector pair':    'Sector RS Pair — long the strongest sector ETF + short the weakest. Market-neutral, profits from divergence regardless of S&P direction.',
  'spread 21d':     'RS spread (21d) — relative outperformance of long sector vs short sector over last 21 trading days.',
  'spread 63d':     'RS spread (63d) — relative outperformance over last quarter. Confirms longer-term divergence.',
  'cross-asset':    'Cross-asset signal — risk-on/off read from DXY (dollar) + HYG (credit) + GLD (gold). Confirms equity regime call.',

  // -- D-series UI features --
  'concordance':    'Tab agreement % — how many analysis tabs (Tech/Fund/SMC/Sentiment/Options) reach the same direction.',
  'tab agreement':  'Tab agreement — single number summarizing whether all analysis lenses agree. >65% = strong consensus.',
  'cross-mode':     'Cross-Mode Exposure — sums BUY signals across Swing + Position + Invest by sector. Surfaces concentration risk.',
  'cross-mode exposure':'Cross-Mode Exposure — sector concentration across all 3 horizons (Swing/Position/Invest).',
  'factor':         'Factor exposure — Momentum (RS rank) / Quality (fundamentals) / Value (inverse PE). Shows portfolio tilt.',
  'momentum':       'Momentum factor — average RS rank vs SPY. >70 = strong momentum tilt.',
  'quality':        'Quality factor — average quality-gate pillar score (margins, balance sheet, growth).',
  'value':          'Value factor — inverse forward P/E. Higher score = cheaper portfolio.',
  'wash sale':      'Wash sale rule — buying within 30 days of a loss-sale disallows the IRS loss deduction. The loss is added to new cost basis.',
  'wash-sale':      'Wash sale rule — buying within 30 days of a loss-sale disallows the IRS loss deduction.',

  // -- Status/Tier markers --
  '✓ cleared':      'Tail-loss filter CLEARED — this ticker passes both score ≥ 60 AND stars ≥ 4 thresholds.',
  '✗ demoted':      'Tail-loss filter DEMOTED — score < 60 OR stars < 4. System will not allocate capital.',
  'was tier':       'Original conviction tier before any filter demotion (T1/T2/T3 before tail-loss filter applied).',

  // -- Misc additions --
  'p25':            'P25 — 25th percentile forward return. 75% of paths ended above this. Pessimistic case.',
  'p50':            'P50 — median forward return. Half of Monte Carlo paths ended above, half below. Typical outcome.',
  'p75':            'P75 — 75th percentile forward return. Only 25% of paths did better. Optimistic case.',
  'p(profit)':      'Probability of profit — % of Monte Carlo or historical paths that ended above entry. >55% = bullish edge.',
  'p profit':       'Probability of profit — % of paths that ended above entry.',
  'mean':           'Mean — average return across all simulated paths. Should align with μ but skewed by jumps.',
  'std':            'Standard deviation — typical spread around mean. Bigger = wider distribution = more uncertainty.',
  'mcap':           'Market Cap — total value of all shares (price × float). Large-cap >$10B, mid $2-10B, small <$2B.',
  'rev gr':         'Revenue Growth — year-over-year revenue change. Positive = company growing top-line.',
  'net mgn':        'Net Margin — net income as % of revenue. Higher = more profitable per dollar of sales.',
  'roe':            'Return on Equity — net income / shareholder equity. >15% = strong, >25% = exceptional.',
  'debt/e':         'Debt-to-Equity — leverage measure. <0.5 = conservative, >2.0 = leveraged (financial risk).',
  'pt mean':        'Mean analyst price target. Compare to current to see analyst-implied upside.',
  'inst own':       'Institutional ownership % — what fraction of float is held by funds/institutions.',
  'short %':        'Short interest as % of float. >20% = high squeeze potential. <5% = no short pressure.',
  'float':          'Float — shares available for public trading (excludes insider/restricted holdings). Smaller float = more volatile.',
  'days':           'Days until next earnings report. <7d = blackout window, system blocks new entries.',
};


// =============================================================================
// TOOLTIP RENDERER — auto-applies tips by matching label text
// =============================================================================
function _normalize(s) { return (s || '').trim().toLowerCase().replace(/\s+/g, ' ').replace(/[:·]/g, '').trim(); }

function _lookupTip(text) {
  const key = _normalize(text);
  if (TIPS[key]) return TIPS[key];
  // Fallback: try first word
  const first = key.split(' ')[0];
  return TIPS[first] || null;
}

function applyTooltips(root = document) {
  // Selectors that hold field labels in either page
  const selectors = [
    'th',                          // table headers
    '.lbl',                        // generic labels (.strip-item .lbl, .stat-tile .lbl, etc.)
    '.l',                          // 2026-05-04: ov-mini4 / ov-stat-grid mini-labels
    '.card-h',                     // card headers
    '.tb-label',                   // toolbar labels
    '.mc-l',                       // macro strip labels
    '.sb-group-h',                 // sidebar group headers
    '.ex-pillar-name',             // pillar names in expand panel
    '.pillar-name',                // scorecard pillars
    '.h-tags .pill',               // header tag pills (in elite-detail)
    '.extag',                      // expand panel tags
    '.pf-pill',                    // portfolio direction pills
    '.stg-cell',                   // stage pills in row
    '.verdict-tile .lbl',          // verdict tile label
    '.score-tile .lbl',            // score tile label
    '.ew-charac-head .h',          // elliott wave characteristic header
    '.mm-fib-tile .lbl',           // multi-method fib tile labels
    '.strip-item .lbl',            // top strip item labels (elite-detail)
    '.mm-bar .lbl',                // multi-method bar labels
    '.ex-fund-card .lbl',          // expand-panel fund card labels
    '.ex-zone-line .lbl',          // expand-panel zone labels
    '.plan-stat .lbl',             // plan stats strip labels
    '.ps-name',                    // monte carlo scenario names
    '.pp-row .lbl',                // pre-flight checklist labels
    '.tl-lbl-name',                // timeline label names
    '.lane-head .h',               // entry/exit/risk lane headers
    '.bt-card .lbl',               // backtest card labels
    '.kpi-lbl',                    // KPI labels
    '.mm-tab',                     // multi-method tabs (MC / EW / WY / Expert)
    '.mm-mctab .opt',              // monte carlo sub-tabs (Paths / Dist / Levels)
    '.mm-controls .opt',           // EW degree, mode, Wyckoff phase toggles
    // 2026-05-04: NEW UI surfaces shipped this sprint
    '.elite-ov-h',                 // overview row tile headers (Row 4: Monte Carlo, Forward Dist, Regime, CVaR)
    '.pas-card-h .lbl',            // per-ticker accuracy + forward risk strip labels
    '.cme-sec',                    // cross-mode exposure sector names
    '.fac-name',                   // factor heatmap labels (Momentum/Quality/Value)
    '.dtree-name',                 // decision tree step names
    '.lux-tf',                     // LuxAlgo MTF screener TF pills
    '.re-tag',                     // Rule Engine concordance tags (BULL/BEAR/WAIT/N/A)
    '.re-tab-row .name',           // Rule Engine per-tab names
    '.re-concord-l .lbl',          // Concordance banner label
    '.cvar-card .lbl',             // CVaR portfolio tile labels
    '.fac-row',                    // factor heatmap rows
    // Chips in scanner / advanced filter rail
    '.chip',                       // scanner verdict / setup family / sector / price chips
    '.sc2-toggle span',            // watchlist / earnings toggles
  ];
  // Chip-context lookup map: data-attr value → TIPS key
  // (Lets icon chips like ⚡▲→★ get rich tips even though text is meaningless.)
  const _chipMap = {
    // verdict chips (data-fsv)
    'fsv': { 'ALL': 'All — show every ticker regardless of verdict.',
             'BUY': TIPS['buy'],
             'WATCH': TIPS['watch'],
             'SELL': TIPS['short'] },
    // setup-family chips (data-fsf)
    'fsf': { 'ALL': 'All setups.',
             'impulse':  'Impulse Catalyst — PEAD (post-earnings drift), UOA (unusual options), gap-and-go. Hold 5-8 days.',
             'breakout': 'Breakout Expansion — VCP (volatility contraction pattern), 52-week breakouts, squeeze expansion. Hold 7-21 days.',
             'trend':    'Trend Continuation — pullback to EMA21/50 in established uptrend, bounce, re-break. Hold 7-21 days.',
             'special':  'Special Situation — insider cluster buys, float rotation, short squeezes. Hold 5-15 days.' },
    // tier chips (data-fst)
    'fst': { 'ALL': 'All conviction tiers.',
             'T1': 'Tier 1 conviction — full size. Score ≥ 88, R:R ≥ 3.5, RS ≥ 85, Risk-On Trending regime, FRESH/PULLBACK entry.',
             'T2': 'Tier 2 conviction — half size. Score ≥ 78, R:R ≥ 3.0, not Panic regime.',
             'T3': 'Tier 3 conviction — quarter size. Score ≥ 70, R:R ≥ 3.0.' },
    // entry-quality chips (data-fseq)
    'fseq': { 'ALL': 'All entry qualities.',
              'FRESH':    'FRESH entry — price right at the trigger level. Tight stop, optimal R:R.',
              'PULLBACK': 'PULLBACK entry — price has retraced to a key MA / S-R level after running. Lower-risk entry.',
              'EXTENDED': 'EXTENDED entry — price has run too far past trigger. Wide stop, poor R:R. Wait for pullback.' },
    // price tier chips (data-fsp)
    'fsp': { 'ALL':   'All price tiers.',
             'lt100': 'Under $100 — typical retail/swing range. Most setups in S&P 500 fit here.',
             'lt250': '$100-$250 — mid-range stocks. Common range for tech mega-caps.',
             'gt250': 'Over $250 — high-priced stocks. NVDA, GOOGL post-split, etc. Each share is more capital.' },
  };

  // Helper: find a chip-context tip by walking data-* attributes
  const _chipTip = (el) => {
    for (const attr of ['fsv', 'fsf', 'fst', 'fseq', 'fsp']) {
      const v = el.dataset[attr];
      if (v != null && _chipMap[attr] && _chipMap[attr][v]) return _chipMap[attr][v];
    }
    // Fallback: existing title= attribute (chips already have these on icon variants)
    if (el.title && el.title.length > 5) return el.title;
    return null;
  };

  selectors.forEach(sel => {
    root.querySelectorAll(sel).forEach(el => {
      if (el.classList.contains('tip')) return; // already applied
      // Chip context first (more specific)
      let tip = null;
      if (el.classList.contains('chip')) tip = _chipTip(el);
      if (!tip) tip = _lookupTip(el.textContent);
      if (!tip && el.getAttribute('aria-label')) tip = _lookupTip(el.getAttribute('aria-label'));
      if (tip) {
        el.classList.add('tip');
        el.setAttribute('data-tip', tip);
      }
    });
  });
  // Manual data-tip-key="..." overrides for specific elements
  root.querySelectorAll('[data-tip-key]').forEach(el => {
    const t = TIPS[el.dataset.tipKey];
    if (t) { el.classList.add('tip'); el.setAttribute('data-tip', t); }
  });
  // Special cases: verdict-tile .v (the BUY/WATCH text) should show verdict tooltip
  root.querySelectorAll('.verdict-tile').forEach(tile => {
    if (tile.classList.contains('tip')) return;
    tile.classList.add('tip');
    tile.setAttribute('data-tip', TIPS['verdict']);
  });
  // Score tile (.score-tile) → score tooltip
  root.querySelectorAll('.score-tile').forEach(tile => {
    if (tile.classList.contains('tip')) return;
    tile.classList.add('tip');
    tile.setAttribute('data-tip', TIPS['score']);
  });
  // Live indicator
  root.querySelectorAll('.live-indicator').forEach(el => {
    if (el.classList.contains('tip')) return;
    el.classList.add('tip');
    el.setAttribute('data-tip', TIPS['live']);
  });
  // Stars rating
  root.querySelectorAll('.stars, .ex-stars').forEach(el => {
    if (el.classList.contains('tip')) return;
    el.classList.add('tip');
    el.setAttribute('data-tip', TIPS['star']);
  });
  // Price block in header → Price tooltip
  root.querySelectorAll('.price-block').forEach(el => {
    if (el.classList.contains('tip')) return;
    el.classList.add('tip');
    el.setAttribute('data-tip', TIPS['price']);
  });
}

// Auto-run on DOM mutations so dynamically-rendered content gets tips too
function startTooltipObserver() {
  applyTooltips();
  const obs = new MutationObserver(muts => {
    let needs = false;
    for (const m of muts) {
      if (m.addedNodes && m.addedNodes.length) { needs = true; break; }
    }
    if (needs) applyTooltips();
  });
  obs.observe(document.body, { childList: true, subtree: true });
}

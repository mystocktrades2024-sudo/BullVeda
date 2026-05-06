# SwingTrade Config Change History

Append-only log of profile switches.

## 2026-04-15 08:21:26 PDT — switched to `industry_standard`

**Note:** dropped 85% WR lock 2026-04-15, moving to industry-standard swing targets

**Backup:** `config/history/config_backup_20260415_082126.json`

| Key | Before | After |
|---|---|---|
| `decisions.buy_min_score` | `65` | `58` |
| `decisions.buy_min_rr` | `3.0` | `2.0` |
| `decisions.watch_min_score` | `50` | `45` |
| `decisions.avoid_below` | `50` | `40` |
| `regime_thresholds.bull.buy_min_score` | `60` | `58` |
| `regime_thresholds.bull.watch_min_score` | `48` | `45` |
| `regime_thresholds.bull.rs_min` | `75` | `60` |
| `regime_thresholds.bull.rr_min` | `2.5` | `2.0` |
| `regime_thresholds.neutral.buy_min_score` | `62` | `58` |
| `regime_thresholds.neutral.watch_min_score` | `50` | `45` |
| `regime_thresholds.neutral.rs_min` | `75` | `60` |
| `regime_thresholds.neutral.rr_min` | `2.5` | `2.0` |
| `regime_thresholds.neutral.high_vix_extra_score` | `8` | `6` |
| `regime_thresholds.bear.buy_min_score` | `68` | `65` |
| `regime_thresholds.bear.watch_min_score` | `60` | `55` |
| `regime_thresholds.bear.rs_min` | `75` | `70` |
| `regime_thresholds.bear.rr_min` | `4.0` | `3.0` |
| `regime_thresholds.bear.high_vix_extra_score` | `10` | `8` |
| `regime4_thresholds.risk_on_trending.buy_min_score` | `65` | `58` |
| `regime4_thresholds.risk_on_trending.rs_min` | `80` | `65` |
| `regime4_thresholds.risk_on_trending.rr_min` | `3.0` | `2.0` |
| `regime4_thresholds.risk_on_choppy.buy_min_score` | `72` | `60` |
| `regime4_thresholds.risk_on_choppy.rs_min` | `75` | `60` |
| `regime4_thresholds.risk_on_choppy.rr_min` | `3.0` | `2.0` |
| `regime4_thresholds.risk_off_trending.buy_min_score` | `78` | `70` |
| `regime4_thresholds.risk_off_trending.rs_min` | `80` | `70` |
| `regime4_thresholds.risk_off_trending.rr_min` | `4.0` | `3.0` |

## 2026-04-02 18:19 — commit `d849f1a` — feat: add SwingTrade skill — rules-based swing trading agent

- Backup: `config/history/config_backup_20260402_181933_d849f1a.json`
- Top-level keys changed: 10 — decisions, filters, gates, hold_period_days, output, portfolio, scoring, technicals, universe, zacks_credentials

## 2026-04-02 19:37 — commit `ce36b83` — feat(SwingTrade): add ADX, StochRSI, MFI, CMF, SAR, 52w, VIX, sector rotation, options IV

- Backup: `config/history/config_backup_20260402_193725_ce36b83.json`
- Top-level keys changed: 5 — adx, options, sector_rotation, vix, weekly

## 2026-04-02 21:35 — commit `da46160` — feat: price tiers top-5, beta-adjusted sizing, sector concentration gate

- Backup: `config/history/config_backup_20260402_213533_da46160.json`
- Top-level keys changed: 3 — filters, output, portfolio

## 2026-04-10 11:28 — commit `d553ba9` — feat(SwingTrade): signal improvements #14-30 + Slack/Mac alerts

- Backup: `config/history/config_backup_20260410_112820_d553ba9.json`
- Top-level keys changed: 12 — alerts, congressional, decisions, filters, gates, options, performance, portfolio, reddit_wsb, regime_thresholds, scoring, universe

## 2026-04-11 01:48 — commit `b8d4b72` — feat(SwingTrade): signal audit — new signals, IBD removed, VWAP fix, squeeze scoring

- Backup: `config/history/config_backup_20260411_014856_b8d4b72.json`
- Top-level keys changed: 5 — alpaca, data_sources, email, scoring, technicals

## 2026-04-11 01:56 — commit `90960d7` — feat(SwingTrade): email dashboard HTML after each scan

- Backup: `config/history/config_backup_20260411_015617_90960d7.json`
- Top-level keys changed: 1 — email

## 2026-04-11 03:02 — commit `a87b719` — perf(SwingTrade): fast OHLCV pre-screen + 2× enrichment workers

- Backup: `config/history/config_backup_20260411_030249_a87b719.json`
- Top-level keys changed: 1 — performance

## 2026-04-11 03:37 — commit `c3cf42c` — fix(dashboard): Zacks inner divs inline + DOMContentLoaded init; add email

- Backup: `config/history/config_backup_20260411_033733_c3cf42c.json`
- Top-level keys changed: 1 — email

## 2026-04-11 11:20 — commit `7a26693` — feat(watchlist): add 34 leveraged ETFs and fix fractals variable ordering

- Backup: `config/history/config_backup_20260411_112040_7a26693.json`
- Top-level keys changed: 1 — universe

## 2026-04-11 11:38 — commit `484d621` — refactor(scoring): 29 systemic fixes to improve signal quality and reduce false positives

- Backup: `config/history/config_backup_20260411_113836_484d621.json`
- Top-level keys changed: 2 — regime_thresholds, scoring

## 2026-04-11 12:28 — commit `d4c7671` — feat(swing-trade): Phase 1-3 signal quality, validation, and stress testing (25 changes)

- Backup: `config/history/config_backup_20260411_122840_d4c7671.json`
- Top-level keys changed: 3 — gates, scoring, universe

## 2026-04-11 13:39 — commit `7acfdd3` — feat(swing-trade): Improve win rate from 47.9% to 50%+ through backtest-driven optimization

- Backup: `config/history/config_backup_20260411_133922_7acfdd3.json`
- Top-level keys changed: 1 — regime_thresholds

## 2026-04-11 14:11 — commit `0092af1` — feat(swing-trade): Eliminate low-WR Continuation setup, add RS >= 75 global gate, tighten stops

- Backup: `config/history/config_backup_20260411_141136_0092af1.json`
- Top-level keys changed: 1 — scoring

## 2026-04-11 14:16 — commit `50e4957` — feat(swing-trade): Implement strict threshold strategy to eliminate low-WR trades

- Backup: `config/history/config_backup_20260411_141629_50e4957.json`
- Top-level keys changed: 1 — regime_thresholds

## 2026-04-12 00:43 — commit `dd58eae` — feat(finviz): integrate FINVIZ Elite bulk data as primary enrichment source

- Backup: `config/history/config_backup_20260412_004327_dd58eae.json`
- Top-level keys changed: 9 — data_sources, email, gates, hold_period_by_family, hold_period_days, regime4_thresholds, regime_multipliers, scoring, vix_multipliers

## 2026-04-13 10:43 — commit `8b1d916` — Phase 4: 23 logic fixes, portfolio engine, 3 new strategies, SMC MTF matrix

- Backup: `config/history/config_backup_20260413_104335_8b1d916.json`
- Top-level keys changed: 15 — breadth_bands, data_sources, drawdown_controls, email, exit_rules, gates, portfolio, regime4_thresholds, regime_hysteresis, regime_thresholds, risk_budget, scoring, technicals, time_stops, universe

## 2026-04-13 13:20 — commit `41a0d21` — Add all 10 strategy scanners + update to 5 positions

- Backup: `config/history/config_backup_20260413_132038_41a0d21.json`
- Top-level keys changed: 1 — portfolio

## 2026-04-13 13:55 — commit `31ccb81` — Account selector, star ratings, 14 strategies, Vinod's items, multi-threaded server

- Backup: `config/history/config_backup_20260413_135509_31ccb81.json`
- Top-level keys changed: 2 — account_profiles, portfolio

## 2026-04-13 15:42 — commit `dfd883b` — Fix thresholds for new scoring engine + 5 tiles per row

- Backup: `config/history/config_backup_20260413_154218_dfd883b.json`
- Top-level keys changed: 1 — regime_thresholds

## 2026-04-13 21:36 — commit `3bf0fbe` — Raise max_enrichment to 500 + fix config override

- Backup: `config/history/config_backup_20260413_213631_3bf0fbe.json`
- Top-level keys changed: 1 — performance

## 2026-04-13 21:46 — commit `c9a99f3` — Set max_enrichment to 1200 — score ALL tickers, no pre-screen cuts

- Backup: `config/history/config_backup_20260413_214611_c9a99f3.json`
- Top-level keys changed: 1 — performance

## 2026-04-13 22:12 — commit `69fd16c` — Fix input text color + add leveraged ETFs to custom watchlist for tracking

- Backup: `config/history/config_backup_20260413_221207_69fd16c.json`
- Top-level keys changed: 1 — universe

## 2026-04-13 22:15 — commit `c11b032` — Add 23 leveraged ETFs to archive + watchlist (TQQQ, SOXL, UPRO, SQQQ, etc)

- Backup: `config/history/config_backup_20260413_221557_c11b032.json`
- Top-level keys changed: 1 — universe

## 2026-04-14 09:14 — commit `039fd25` — Vinod review batch 2: fix #3, #9, #13, #23, #25, #27, #29, #30

- Backup: `config/history/config_backup_20260414_091421_039fd25.json`
- Top-level keys changed: 4 — _meta, account_profiles, performance, portfolio

## 2026-04-14 11:13 — commit `b347fc0` — AI-2c: scrub plaintext API keys from config.json

- Backup: `config/history/config_backup_20260414_111329_b347fc0.json`
- Top-level keys changed: 2 — alpaca, data_sources

## 2026-04-14 12:06 — commit `ca409d3` — AI-2c finish: scrub last 2 secrets (slack_webhook + gmail app_password)

- Backup: `config/history/config_backup_20260414_120619_ca409d3.json`
- Top-level keys changed: 2 — alerts, email

## 2026-04-14 21:54 — commit `20fe3bf` — Settings tab + swing defaults applied

- Backup: `config/history/config_backup_20260414_215450_20fe3bf.json`
- Top-level keys changed: 4 — _meta, gates, regime_thresholds, scoring

## 2026-04-14 22:01 — commit `4433d08` — Loosen 12 harsh gates for swing trading

- Backup: `config/history/config_backup_20260414_220102_4433d08.json`
- Top-level keys changed: 7 — _meta, adx, filters, gates, portfolio, regime_thresholds, technicals

## 2026-04-15 08:38 — commit `e67527c` — Config profiles + industry-standard switch + Polygon data-path fixes

- Backup: `config/history/config_backup_20260415_083835_e67527c.json`
- Top-level keys changed: 5 — decisions, performance, regime4_thresholds, regime_thresholds, walk_forward

## 2026-04-15 11:07 — commit `e608af1` — Settings tab: Run Scan button, Trading Profiles, Attribution, Audit table

- Backup: `config/history/config_backup_20260415_110741_e608af1.json`
- Top-level keys changed: 3 — decisions, regime4_thresholds, setup_gates

## 2026-04-15 19:14:03 PDT — switched to `adaptive`

**Note:** First adaptive scan — testing p90-dynamic + setup bonuses + top-N in choppy market

**Backup:** `config/history/config_backup_20260415_191403.json`

| Key | Before | After |
|---|---|---|
| `decisions.buy_min_score` | `58` | `50` |
| `decisions.watch_min_score` | `45` | `40` |
| `decisions.avoid_below` | `40` | `35` |
| `decisions.adaptive_mode` | `None` | `True` |
| `decisions.adaptive_p90_offset` | `None` | `-8` |
| `decisions.adaptive_floor` | `None` | `40` |
| `decisions.adaptive_top_n` | `None` | `5` |
| `regime_thresholds.bull.buy_min_score` | `58` | `55` |
| `regime_thresholds.bull.watch_min_score` | `45` | `42` |
| `regime_thresholds.bull.rs_min` | `60` | `55` |
| `regime_thresholds.neutral.buy_min_score` | `58` | `52` |
| `regime_thresholds.neutral.watch_min_score` | `45` | `40` |
| `regime_thresholds.neutral.rs_min` | `60` | `50` |
| `regime_thresholds.neutral.high_vix_extra_score` | `6` | `5` |
| `regime_thresholds.bear.buy_min_score` | `65` | `60` |
| `regime_thresholds.bear.watch_min_score` | `55` | `50` |
| `regime_thresholds.bear.rs_min` | `70` | `65` |
| `regime4_thresholds.risk_on_trending.buy_min_score` | `58` | `55` |
| `regime4_thresholds.risk_on_trending.rs_min` | `65` | `60` |
| `regime4_thresholds.risk_on_choppy.buy_min_score` | `60` | `48` |
| `regime4_thresholds.risk_on_choppy.rs_min` | `60` | `50` |
| `regime4_thresholds.risk_on_choppy.max_size_pct` | `70` | `50` |
| `regime4_thresholds.risk_on_choppy.breadth_min` | `40` | `35` |
| `regime4_thresholds.risk_on_choppy.vix_max` | `25` | `28` |
| `regime4_thresholds.risk_off_trending.buy_min_score` | `70` | `65` |
| `regime4_thresholds.risk_off_trending.rs_min` | `70` | `65` |
| `regime4_thresholds.risk_off_trending.max_size_pct` | `35` | `30` |

## 2026-04-16 11:42:10 PDT — switched to `focused`

**Note:** Backtest validation run

**Backup:** `config/history/config_backup_20260416_114210.json`

| Key | Before | After |
|---|---|---|
| `decisions.buy_min_score` | `72` | `40` |
| `decisions.watch_min_score` | `40` | `35` |
| `decisions.avoid_below` | `35` | `30` |
| `decisions.adaptive_floor` | `40` | `35` |
| `decisions.adaptive_top_n` | `5` | `3` |
| `regime_thresholds.bull.buy_min_score` | `65` | `45` |
| `regime_thresholds.bull.watch_min_score` | `55` | `35` |
| `regime_thresholds.bull.rs_min` | `55` | `50` |
| `regime_thresholds.neutral.buy_min_score` | `72` | `45` |
| `regime_thresholds.neutral.watch_min_score` | `60` | `35` |
| `regime_thresholds.bear.buy_min_score` | `78` | `55` |
| `regime_thresholds.bear.watch_min_score` | `65` | `45` |
| `regime_thresholds.bear.rs_min` | `65` | `60` |
| `regime4_thresholds.risk_on_trending.buy_min_score` | `65` | `45` |
| `regime4_thresholds.risk_on_trending.rs_min` | `60` | `50` |
| `regime4_thresholds.risk_on_trending.breadth_min` | `65` | `55` |
| `regime4_thresholds.risk_on_trending.vix_max` | `18` | `20` |
| `regime4_thresholds.risk_on_choppy.buy_min_score` | `72` | `45` |
| `regime4_thresholds.risk_on_choppy.max_size_pct` | `50` | `70` |
| `regime4_thresholds.risk_on_choppy.breadth_min` | `35` | `30` |
| `regime4_thresholds.risk_off_trending.buy_min_score` | `78` | `60` |
| `regime4_thresholds.risk_off_trending.rs_min` | `65` | `60` |
| `regime4_thresholds.risk_off_trending.max_size_pct` | `30` | `35` |

## 2026-04-17 08:23:49 PDT — switched to `trending_leaders`

**Backup:** `config/history/config_backup_20260417_082349.json`

| Key | Before | After |
|---|---|---|
| `decisions.buy_min_score` | `40` | `78` |
| `decisions.buy_min_rr` | `2.0` | `3.0` |
| `decisions.watch_min_score` | `35` | `60` |
| `decisions.avoid_below` | `30` | `60` |
| `decisions.adaptive_mode` | `True` | `False` |
| `regime_thresholds.bull.buy_min_score` | `45` | `78` |
| `regime_thresholds.bull.watch_min_score` | `35` | `60` |
| `regime_thresholds.bull.rs_min` | `50` | `75` |
| `regime_thresholds.bull.rr_min` | `2.0` | `3.0` |
| `regime_thresholds.bull.weekly_bull_required` | `False` | `True` |
| `regime_thresholds.bull.high_vix_threshold` | `30` | `18` |
| `regime_thresholds.neutral.buy_min_score` | `45` | `82` |
| `regime_thresholds.neutral.watch_min_score` | `35` | `60` |
| `regime_thresholds.neutral.rs_min` | `50` | `80` |
| `regime_thresholds.neutral.rr_min` | `2.0` | `3.0` |
| `regime_thresholds.neutral.weekly_bull_required` | `False` | `True` |
| `regime_thresholds.neutral.high_vix_threshold` | `25` | `18` |
| `regime_thresholds.neutral.high_vix_extra_score` | `5` | `8` |
| `regime_thresholds.bear.buy_min_score` | `55` | `88` |
| `regime_thresholds.bear.watch_min_score` | `45` | `65` |
| `regime_thresholds.bear.rs_min` | `60` | `85` |
| `regime_thresholds.bear.rr_min` | `3.0` | `4.0` |
| `regime_thresholds.bear.high_vix_extra_score` | `8` | `10` |
| `regime4_thresholds.risk_on_trending.buy_min_score` | `45` | `78` |
| `regime4_thresholds.risk_on_trending.watch_min_score` | `40` | `60` |
| `regime4_thresholds.risk_on_trending.rs_min` | `50` | `75` |
| `regime4_thresholds.risk_on_trending.rr_min` | `2.0` | `3.0` |
| `regime4_thresholds.risk_on_trending.breadth_min` | `55` | `65` |
| `regime4_thresholds.risk_on_trending.vix_max` | `20` | `18` |
| `regime4_thresholds.risk_on_choppy.buy_min_score` | `45` | `82` |
| `regime4_thresholds.risk_on_choppy.watch_min_score` | `40` | `60` |
| `regime4_thresholds.risk_on_choppy.rs_min` | `50` | `80` |
| `regime4_thresholds.risk_on_choppy.rr_min` | `2.0` | `3.0` |
| `regime4_thresholds.risk_on_choppy.max_size_pct` | `70` | `50` |
| `regime4_thresholds.risk_on_choppy.breadth_min` | `30` | `40` |
| `regime4_thresholds.risk_on_choppy.vix_max` | `28` | `25` |
| `regime4_thresholds.risk_off_trending.buy_min_score` | `60` | `88` |
| `regime4_thresholds.risk_off_trending.watch_min_score` | `55` | `65` |
| `regime4_thresholds.risk_off_trending.rs_min` | `60` | `85` |
| `regime4_thresholds.risk_off_trending.rr_min` | `3.0` | `4.0` |
| `regime4_thresholds.risk_off_trending.max_size_pct` | `35` | `25` |

## 2026-04-17 08:40:44 PDT — switched to `trending_leaders`

**Note:** Apply full trending leaders config: scoring weights, entry quality, catalyst tiers

**Backup:** `config/history/config_backup_20260417_084044.json`

| Key | Before | After |
|---|---|---|
| `filters.min_price` | `2` | `5` |
| `filters.min_daily_dollar_volume` | `5000000` | `10000000` |
| `filters.earnings_blackout_days` | `None` | `7` |
| `setup_gates.pocket_pivot.rs_min` | `75` | `85` |
| `setup_gates.vcp_breakout.rs_min` | `70` | `80` |
| `setup_gates.vcp_breakout.rvol_min` | `1.0` | `1.2` |
| `setup_gates.52wk_breakout.rs_min` | `75` | `85` |
| `setup_gates.52wk_breakout.rvol_min` | `1.0` | `1.2` |
| `setup_gates.52wk_breakout.weekly_bull_required` | `False` | `True` |
| `setup_gates.52wk_breakout.elite_rs_min` | `85` | `90` |
| `setup_gates.ema21_pullback.rs_min` | `70` | `80` |
| `setup_gates.ema21_pullback.weekly_bull_required` | `False` | `True` |
| `setup_gates.ema50_pullback.rs_min` | `65` | `75` |
| `setup_gates.ema50_pullback.weekly_bull_required` | `False` | `True` |
| `setup_gates.trend_continuation.rs_min` | `65` | `75` |
| `setup_gates.trend_continuation.weekly_bull_required` | `False` | `True` |
| `setup_gates.bounce.rs_min` | `75` | `85` |
| `setup_gates.bounce.weekly_bull_required` | `False` | `True` |
| `setup_gates.near_vcp.rs_min` | `80` | `85` |
| `setup_gates.breakdown.rvol_min` | `1.0` | `1.2` |
| `setup_gates.breakdown.min_score` | `72` | `82` |
| `setup_gates.default.rs_min` | `60` | `80` |
| `setup_gates.default.rvol_min` | `0.8` | `1.0` |
| `setup_gates.default.weekly_bull_required` | `False` | `True` |
| `entry_quality_rules.FRESH` | `None` | `BUY` |
| `entry_quality_rules.PULLBACK` | `None` | `BUY` |
| `entry_quality_rules.VALID` | `None` | `WATCH` |
| `entry_quality_rules.EXTENDED` | `None` | `WATCH` |
| `entry_quality_rules.MISSED` | `None` | `AVOID` |
| `scoring_weights.trend_structure` | `None` | `30` |
| `scoring_weights.rs_sector` | `None` | `25` |
| `scoring_weights.catalyst_expansion` | `None` | `20` |
| `scoring_weights.smart_money` | `None` | `10` |
| `scoring_weights.quality_fundamentals` | `None` | `5` |
| `scoring_weights.entry_rr` | `None` | `10` |
| `score_bands.avoid.max` | `None` | `59` |
| `score_bands.avoid.verdict` | `None` | `AVOID` |
| `score_bands.watch_low.min` | `None` | `60` |
| `score_bands.watch_low.max` | `None` | `69` |
| `score_bands.watch_low.verdict` | `None` | `WATCH` |
| `score_bands.watch_high.min` | `None` | `70` |
| `score_bands.watch_high.max` | `None` | `77` |
| `score_bands.watch_high.verdict` | `None` | `WATCH` |
| `score_bands.buy.min` | `None` | `78` |
| `score_bands.buy.max` | `None` | `87` |
| `score_bands.buy.verdict` | `None` | `BUY` |
| `score_bands.priority_buy.min` | `None` | `88` |
| `score_bands.priority_buy.verdict` | `None` | `PRIORITY BUY` |
| `catalyst_tiers.T1.eligible` | `None` | `True` |
| `catalyst_tiers.T1.examples` | `None` | `['PEAD', 'UOA confirmed', 'VCP breakout', '52wk breakout', 'pocket pivot']` |
| `catalyst_tiers.T2.eligible` | `None` | `with_trend_and_volume` |
| `catalyst_tiers.T2.examples` | `None` | `['squeeze expansion', 'EMA pullback', 'insider cluster', 'bullish IV skew']` |
| `catalyst_tiers.T3.eligible` | `None` | `watch_only` |
| `catalyst_tiers.T3.examples` | `None` | `['analyst headlines', 'social sentiment', 'weak continuation']` |
| `short_rules.min_vix` | `None` | `25` |
| `short_rules.min_rsi` | `None` | `75` |
| `short_rules.min_rr` | `None` | `4.0` |
| `short_rules.require_bear_regime` | `None` | `True` |
| `short_rules.require_bearish_structure` | `None` | `True` |
| `price_buckets` | `{}` | `[{'label': 'Under $100', 'min': 5, 'max': 100}, {'label': '$100 – $250', 'min': 100, 'max': 250}, {'label': 'Above $250', 'min': 250, 'max': 500}]` |

## 2026-04-17 11:29:53 PDT — switched to `trending_leaders`

**Note:** Re-apply: ensure scoring_weights merged correctly

**Backup:** `config/history/config_backup_20260417_112953.json`

| Key | Before | After |
|---|---|---|
| `scoring_weights.trend_structure` | `35` | `30` |
| `scoring_weights.rs_sector` | `20` | `25` |
| `scoring_weights.smart_money` | `15` | `10` |
| `scoring_weights.quality_fundamentals` | `10` | `5` |
| `scoring_weights.entry_rr` | `None` | `10` |

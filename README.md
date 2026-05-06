# SwingTrade

A disciplined, rule-based swing trading system for US equities. Scans ~1,000 S&P 500 / Russell 1000 / Zacks premium tickers hourly, scores them across 5 pillars (Tech · Catalyst · RS · Smart Money · Quality Gate), and produces ranked BUY / WATCH / SHORT / AVOID verdicts with explicit entry zones, stops, and targets.

Paper-trade execution via Alpaca runs mechanically — no manual intervention required. A dashboard at `http://localhost:7432/dashboard` surfaces signals, portfolio P&L, drift monitoring, and per-setup attribution.

**Target outcome:** +40–90%/yr on $5K (vs SPY +12%), validated against 252-day backtests. Expect live WR 55–70% (backtests report 85%+ due to survivorship).

---

## What it does

| Layer | Function |
|---|---|
| **Scan** | Hourly (Mon-Fri, 1am-5pm PT): pull OHLCV (Polygon → archive → yfinance failover), score universe, write `cache/last_bundle.json` |
| **Decide** | 5-pillar score → regime-aware thresholds → Vinod decision states (AT_ZONE / EXTENDED / MISSED / POST_BREAKOUT_DRIFT) → 4 short-side filters + squeeze/earnings/DTC gates |
| **Execute** | 6:35am PT weekdays: `executor.py` submits Alpaca paper bracket orders (entry limit + OCO stop + target) for BUY signals |
| **Manage** | 12:55pm PT weekdays: `eod_manager.py` applies exits, runner-trims, stop-tightens, gap-down closes |
| **Validate** | Weekly (Sat 2am): walk-forward backtest refreshes `config._meta.last_backtest_wr`. Daily: drift checker compares live vs backtest WR per setup |

Dashboard tabs: Trades · Strategies · Portfolio · Performance · Screener · Themes · Research · Leveraged · Industries · Market · Crypto · Playbook · Guide · Reference · System Status.

---

## Quick start

### 1. Install
```bash
git clone <repo-url> SwingTrade && cd SwingTrade
python3 -m pip install -r requirements.txt
```

### 2. Set up secrets
```bash
cp .env.example .env
# Edit .env — fill in Polygon, Finnhub, FMP, Finviz, Alpaca (paper),
# optional Slack webhook + Gmail app password.
chmod 600 .env
```

### 3. First scan
```bash
python3 swing_trade.py
# ~8 minutes. Produces cache/dashboard.html.
```

### 4. Start the server + view the dashboard
```bash
python3 server.py &
open http://localhost:7432/dashboard
```

### 5. Run the integration tests
```bash
python3 tests/test_make_decision.py
# Expected: 23/23 pass
```

### 6. (Optional) Enable automated trading
```bash
# Install launchd plists (macOS):
cp launchd_plists/* ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.swingtrade.daily.plist
launchctl load ~/Library/LaunchAgents/com.swingtrade.executor.plist
launchctl load ~/Library/LaunchAgents/com.swingtrade.fill.plist
launchctl load ~/Library/LaunchAgents/com.swingtrade.eod.plist
launchctl load ~/Library/LaunchAgents/com.swingtrade.weekly-backtest.plist
# Verify:
launchctl list | grep swingtrade
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  scheduled hourly scan (launchd)                            │
│  swing_trade.py → cache/last_bundle.json + dashboard.html   │
└────────┬────────────────────────────────────────────────────┘
         │
         ├── analysis.py        (5-pillar scoring + make_decision)
         ├── data_fetcher.py    (Polygon / Finnhub / FMP / Finviz)
         ├── tracker.py         (live trade history, per-direction stats)
         ├── signal_tracker.py  (per-signal outcome log)
         └── html_generator.py  (dashboard render — 20K+ lines)

┌─────────────────────────────────────────────────────────────┐
│  6:35am PT execution (launchd)                              │
│  executor.py → Alpaca paper bracket orders                  │
└────────┬────────────────────────────────────────────────────┘
         │
         ├── secrets_loader.py  (.env → env → fallback)
         ├── alpaca-py SDK      (TradingClient, paper=True)
         └── cache/orders.jsonl (per-order audit trail)

┌─────────────────────────────────────────────────────────────┐
│  12:55pm PT end-of-day (launchd)                            │
│  eod_manager.py → exits, trims, tightens, gap-downs         │
└─────────────────────────────────────────────────────────────┘

Support tools:
  drift_check.py          # weekly live-vs-backtest drift
  leaderboard.py          # per-setup expectancy ranking
  weekly_review.py        # Friday performance report
  walk_forward_parallel.py # N-fold concurrent backtest
  config_schema.py         # pydantic v2 config validation
  emergency_close_all.sh   # cancel all + market-sell all positions
```

---

## Dashboard (http://localhost:7432/dashboard)

Key tabs to know:

- **📘 Playbook** — what fires when, where to look, kill switches, day-in-the-life timeline. Open this first.
- **🛠 System Status** — build info, config integrity, drift monitor, validation (P7) progress, data health (P6), roadmap (renders `OPEN_ITEMS.md` live).
- **🎯 Trades** — today's BUY / WATCH / SHORT signals as tiles with entry/stop/target.
- **💼 Portfolio** — equity, cash, today's P&L, gross exposure, risk consumption, open positions, closed trades.
- **📈 Performance** — backtest vs live, per-setup / regime attribution.

---

## Safety layers (active)

Every BUY candidate passes through **10+ hard gates** before it can become a live order:

1. Min liquidity ($10M+ daily $-volume)
2. Min history (30+ bars)
3. Earnings blackout (within 7 days → block)
4. VIX spike kill (+30% vs 5d → all new longs blocked)
5. Extended-ATR gate (>1.5 ATR above EMA21 → block)
6. Distribution-days gate (7+ dist days → block)
7. 3-consecutive-loss circuit breaker
8. -8% drawdown kill switch
9. -4% daily-loss halt (AI-45)
10. Weekend risk cap (Fridays, 50% gross max)
11. PDT hard-block (sub-$25K accounts, 3/5d day-trades)
12. Industry concentration cap (2 per industry max)
13. Pre-market gap filter (gap >3% → demote to WATCH)
14. Regime transition auto-trim (risk-off flip → force exit)

Plus the short side: bear regime required, VIX ≥ 25, RS ≤ 30, no earnings window, sector underperforming, short float ≤ 15%, DTC ≤ 5, no TTM squeeze.

---

## Kill switches

### Stop new trades, keep positions
```bash
launchctl unload ~/Library/LaunchAgents/com.swingtrade.executor.plist
launchctl unload ~/Library/LaunchAgents/com.swingtrade.eod.plist
```

### Close everything now
```bash
./emergency_close_all.sh
# 5-sec Ctrl-C window, then cancel all open orders + market-sell all positions
```

---

## Configuration

All secrets are in `.env` (never committed). Non-secret config is in `config/config.json`:

```jsonc
{
  "_meta": { "schema_version": "2.0", "last_backtested": "2026-04-14", ... },
  "regime4_thresholds": {
    "risk_on_trending":  { "buy_min_score": 65, "rs_min": 80, "rr_min": 3.0, "max_size_pct": 100 },
    "risk_on_choppy":    { "buy_min_score": 72, "rs_min": 75, "rr_min": 3.0, "max_size_pct": 70 },
    "risk_off_trending": { "buy_min_score": 78, "rs_min": 80, "rr_min": 4.0, "max_size_pct": 35 },
    "panic":             { "buy_min_score": 999, "max_size_pct": 0 }
  },
  "portfolio": {
    "account_equity": 5000,
    "config_e": { "max_positions": 4, "pct_per_trade": 0.2 }  // 80% gross, 20% cash buffer
  }
  // ... gates, regime, universe, etc.
}
```

Run `python3 config_schema.py` to validate your config against the pydantic schema.
Run `python3 config_validator.py` for lighter runtime checks.

---

## Development

### Integration tests
```bash
python3 tests/test_make_decision.py
# 23 scenarios covering BUY / WATCH / SHORT / AVOID paths + all gates
```

### Regenerate dashboard without re-scanning
```bash
python3 swing_trade.py regen
# Reads cache/last_bundle.json, re-renders HTML in ~15 sec
```

### Parallel walk-forward backtest
```bash
python3 walk_forward_parallel.py
# 3 folds (1yr / 2yr / 3yr trailing) concurrent
python3 walk_forward_parallel.py --sensitivity score --values 60,65,70,75
# Parameter sweep
```

### Drift monitoring
```bash
python3 drift_check.py --slack
# Live vs backtest WR + per-setup breakdown; Slack post on WARN
```

---

## Go-live gate (before real money)

Don't even think about live trading until **all 6 gates pass** (visible in System Status → Validation):

- ✅ Live WR ≥ 65% over 60+ paper trades
- ✅ Max drawdown ≤ 12%
- ✅ `executor.py` ran cleanly for 5+ consecutive days
- ✅ `eod_manager.py` firing daily without errors
- ✅ Alpaca keys valid in `.env`
- ✅ Setup distribution matches backtest (per `leaderboard.py`)

If you pass: start at **half size** ($5K × 10% per position, not 20%) for 3 months before scaling up.

---

## Repository conventions

- `cache/` — regenerable runtime state (ignored)
- `data/` — persistent state (signals, portfolio, OHLCV archive)
- `tests/` — `test_make_decision.py` (23 integration scenarios)
- `config/` — config.json + gmail_token.json (token ignored)
- `docs/` — auxiliary HTML/markdown reference
- `launchd_plists/` — macOS scheduling (if shipped separately)

---

## License & support

Personal use. Bring your own API keys. Author makes no warranties about profitability — this is a research system, not financial advice. Read `/Playbook` tab on the dashboard before running with real money.

For issues: read the in-dashboard **Playbook** tab first — it covers every common scenario.

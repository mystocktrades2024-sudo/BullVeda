#!/usr/bin/env python3
"""Trace why historical-date backtest produces 0 BUYs.

For a fixed date + ticker, prints the make_decision reason + score breakdown.
Usage: python3 scripts/debug_historical_buy_block.py [DATE] [TICKER1,TICKER2,...]
"""
from __future__ import annotations
import sys
from pathlib import Path
import json
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import importlib.util
_bt_spec = importlib.util.spec_from_file_location("backtest_mod", ROOT / "backtest.py")
_bt = importlib.util.module_from_spec(_bt_spec)
_bt_spec.loader.exec_module(_bt)
_score_as_of = _bt._score_as_of
_regime_as_of = _bt._regime_as_of
from data_fetcher import fetch_ohlcv_with_failover  # noqa


def main():
    date_str = sys.argv[1] if len(sys.argv) > 1 else "2025-09-04"
    tickers = (sys.argv[2] if len(sys.argv) > 2 else "AAPL,MSFT,NVDA,DELL,WMB").split(",")

    cfg_path = ROOT / "config" / "config.json"
    cfg = json.loads(cfg_path.read_text())
    # Disable rolling-Sharpe kill for this diagnostic
    cfg.setdefault("rolling_sharpe_kill", {})["_enabled"] = False

    as_of = pd.Timestamp(date_str)

    # SPY for regime
    print(f"Fetching SPY...")
    spy, _ = fetch_ohlcv_with_failover("SPY", days=1000)
    if spy is None or len(spy) < 200:
        print("SPY data missing — abort")
        return 1
    regime = _regime_as_of(spy, as_of)
    print(f"Regime as of {date_str}: {regime['regime']}  SPY=${regime['spy_price']}  daily%={regime['spy_daily_chg']}")
    print(f"  above_50ema={regime.get('above_50ema')} above_200sma={regime.get('above_200sma')} dist_days={regime['distribution_days']}")
    print()

    for t in tickers:
        print(f"════════ {t} ════════")
        df, _ = fetch_ohlcv_with_failover(t, days=400)
        if df is None or len(df) < 60:
            print(f"  No OHLCV data — skip")
            continue
        info = {"sector": "Tech"}  # placeholder
        result = _score_as_of(t, df, as_of, spy, cfg, info, finviz_data=None)
        if result is None:
            print(f"  _score_as_of returned None")
            continue
        print(f"  verdict:   {result.get('verdict')}")
        print(f"  reason:    {result.get('reason')}")
        print(f"  score:     {result.get('score')}")
        print(f"  setup:     {result.get('setup_type')}")
        print(f"  rs_rank:   {result.get('rs_rank')}")
        print(f"  rr_ratio:  {result.get('rr_ratio')}")
        print(f"  entry_q:   {result.get('entry_quality')}")
        print(f"  gate_pass: {result.get('gate_passed')}")
        print(f"  weekly_b:  {result.get('weekly_bull')}")
        print()


if __name__ == "__main__":
    main()

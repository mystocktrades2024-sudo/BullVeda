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

    # Import scorers directly so we can see per-pillar breakdown
    from analysis import (
        score_technicals, score_fundamentals, score_optionality,
        score_sentiment, score_bear_setup, compute_trade_plan, pre_trade_gate,
    )
    from data_fetcher import get_finviz_bulk
    import pandas as _pd

    print("Loading FINVIZ bulk (35-field fundamentals)...")
    fvz_all = get_finviz_bulk()
    print(f"  loaded {len(fvz_all)} tickers")
    print()

    for t in tickers:
        print(f"════════ {t} ════════")
        df, _ = fetch_ohlcv_with_failover(t, days=400)
        if df is None or len(df) < 60:
            print(f"  No OHLCV data — skip")
            continue
        info = {"sector": "Tech"}
        fvz = fvz_all.get(t, {})
        # Build _ef from FINVIZ (matches backtest _score_as_of logic)
        _ef = {}
        for fvz_k, ef_k, pct in [
            ("roe_pct","roe",True), ("roa_pct","roa",True),
            ("gross_margin_pct","gross_margin",True),
            ("oper_margin_pct","operating_margin",True),
            ("profit_margin_pct","profit_margin",True),
            ("current_ratio","current_ratio",False),
            ("inst_own_pct","institutional_pct",False),
        ]:
            v = fvz.get(fvz_k)
            if v is not None and v == v:  # NaN check
                _ef[ef_k] = v / 100.0 if pct else v
        for fvz_k, ef_k in [("eps_growth_this_yr","eps_growth_this_yr"), ("eps_growth_next_yr","eps_growth_next_yr")]:
            v = fvz.get(fvz_k)
            if v is not None and v == v:
                _ef[ef_k] = v / 100.0
        for fvz_k, ef_k in [("peg","peg"),("fwd_pe","fwd_pe"),("ps","ps")]:
            v = fvz.get(fvz_k)
            if v is not None and v == v:
                _ef[ef_k] = v
        # Slice to as_of
        df_slc = df[df.index <= as_of].copy()
        if isinstance(df_slc.columns, _pd.MultiIndex):
            df_slc.columns = df_slc.columns.get_level_values(0)
        if len(df_slc) < 60:
            print(f"  not enough history at {date_str}: only {len(df_slc)} bars")
            continue
        spy_close = spy[spy.index <= as_of]["Close"].squeeze().dropna()

        # Derive weekly
        try:
            wdf = df_slc[["Open","High","Low","Close","Volume"]].resample("W-FRI").agg(
                {"Open":"first","High":"max","Low":"min","Close":"last","Volume":"sum"}).dropna(how="all")
            if len(wdf) < 10: wdf = None
        except Exception:
            wdf = None

        # Per-pillar
        try:
            tech = score_technicals(df_slc, regime, spy_close, weekly_df=wdf)
        except Exception as e:
            print(f"  tech FAIL: {type(e).__name__}: {e}"); continue
        try:
            fund = score_fundamentals(info, zacks=None, beat_rate=None,
                                       extra_fund=_ef if _ef else None)
        except Exception as e:
            print(f"  fund FAIL: {type(e).__name__}: {e}"); continue
        try:
            opt  = score_optionality(df_slc, info, tech["sr"], {"earnings_risk": False, "days_to_earnings": None}, {"score": 0}, options_data=None)
        except Exception as e:
            opt = {"score": 0, "max": 20, "reasons": [f"FAIL: {e}"]}
        try:
            sent = score_sentiment({"score": 0, "bias": "neutral"}, {"buys": 0, "sells": 0, "sentiment": "neutral"}, info)
        except Exception as e:
            sent = {"score": 0, "max": 15, "reasons": [f"FAIL: {e}"]}

        ind = tech["indicators"]
        norm = round((tech["score"] + fund["score"]) / max(1, tech.get("max", 38) + fund.get("max", 30)) * 100, 1)

        print(f"  📊 PILLAR SCORES:")
        print(f"     tech: {tech['score']:6.1f}/{tech.get('max',38)} ({tech['score']/max(1,tech.get('max',38))*100:.0f}%)")
        print(f"     fund: {fund['score']:6.1f}/{fund.get('max',30)} ({fund['score']/max(1,fund.get('max',30))*100:.0f}%)")
        print(f"     opt:  {opt.get('score',0):6.1f}/{opt.get('max',20)}")
        print(f"     sent: {sent.get('score',0):6.1f}/{sent.get('max',15)}")
        print(f"     normalized (tech+fund): {norm}")
        print()
        print(f"  📐 KEY INDICATORS:")
        for k in ["price","rsi","rvol","atr","ema8","ema21","ema50","ema200","adx","weekly_ema_bullish","trend_direction","rs_rank","vcp","pocket_pivot","squeeze"]:
            v = ind.get(k)
            if v is not None:
                if isinstance(v, float): v = round(v, 2)
                print(f"     {k:<22} = {v}")
        print()
        if tech.get("reasons"):
            print(f"  📝 TECH REASONS (top 8):")
            for r in (tech.get("reasons") or [])[:8]:
                print(f"     - {r}")
        if fund.get("reasons"):
            print(f"  📝 FUND REASONS (top 5):")
            for r in (fund.get("reasons") or [])[:5]:
                print(f"     - {r}")
        print()
        # Now run full scorer for verdict
        result = _score_as_of(t, df, as_of, spy, cfg, info, finviz_data=None)
        if result is not None:
            print(f"  ⚖️  VERDICT: {result.get('verdict')}  reason: {result.get('reason')}")
        print()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""scripts/export_ticker_fields.py — emit ticker-field inventory as Excel.

Reads cache/last_bundle.json, picks the highest-scored ticker, walks every
field (top-level + nested), categorizes it, attaches sample value + source,
and writes a multi-sheet workbook to cache/ticker_field_inventory_<DATE>.xlsx.

Use:
    python3 scripts/export_ticker_fields.py
"""
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "cache" / "last_bundle.json"
OUT = ROOT / "cache" / f"ticker_field_inventory_{date.today().isoformat()}.xlsx"


# ── Categorization rules ────────────────────────────────────────────────────
# Each rule = (category_label, source, brief_description) keyed by path or prefix.
# Falls through to "Other" if no match.
CATEGORY_RULES = {
    # Identity
    "ticker": ("Identity", "scan", "Stock symbol"),
    "name": ("Identity", "yfinance/EODHD", "Company name"),
    "sector": ("Identity", "yfinance/Schwab", "GICS sector"),
    "industry": ("Identity", "yfinance/Schwab", "GICS industry"),
    "sector_etf": ("Identity", "computed", "Mapped sector ETF (XLK, XLF, etc.)"),
    "sector_n": ("Identity", "computed", "Number of tickers in this sector this scan"),
    "sector_rank": ("Identity", "computed", "Sector rank by avg score"),
    "sector_outperforming": ("Identity", "computed", "Sector ETF beating SPY"),

    # Pricing / volume / volatility
    "price": ("Pricing", "EODHD/Schwab", "Latest close or quote"),
    "volume": ("Pricing", "EODHD", "Latest session volume"),
    "avg_volume": ("Pricing", "computed", "20-day average volume"),
    "rvol": ("Pricing", "computed", "Relative volume vs 20d avg"),
    "atr_pct": ("Pricing", "computed", "ATR as % of price"),
    "beta": ("Pricing", "yfinance", "Beta vs SPY"),

    # Scoring
    "score": ("Scoring", "computed", "Normalized 0-100 score (post-multiplier)"),
    "score_raw": ("Scoring", "computed", "Pre-rounded normalized score"),
    "raw_score": ("Scoring", "computed", "Raw additive score"),
    "raw_momentum_score": ("Scoring", "computed", "Pillar: momentum sub-score"),
    "raw_growth_score": ("Scoring", "computed", "Pillar: growth sub-score"),
    "raw_value_score": ("Scoring", "computed", "Pillar: value sub-score"),
    "scoring_breakdown": ("Scoring", "computed", "5-pillar breakdown (tech/cat/rs/sm/qg) + multiplier + bonuses"),
    "star_rating": ("Scoring", "computed", "1-5 star pre-decision rating"),
    "raw_total": ("Scoring", "computed", "Sum of all pillars before normalize"),

    # Verdict / decision
    "verdict": ("Verdict", "decision_engine", "BUY / WATCH / SHORT / AVOID"),
    "decision": ("Verdict", "decision_engine", "Full decision dict (verdict, emoji, color, reason)"),
    "decision_state": ("Verdict", "decision_engine", "Entry-zone state (FRESH/PULLBACK/VALID/EXTENDED/MISSED)"),
    "conviction": ("Verdict", "decision_engine", "Conviction tier T1/T2/T3 + size multiplier"),
    "audit_trail": ("Verdict", "decision_engine", "Why-this-is-X: gate failures, caveats, decided_by"),
    "bear_type": ("Verdict", "computed", "If SHORT: which bear setup"),
    "bear_setup": ("Verdict", "computed", "Bear-side scoring result"),
    "reject_reason": ("Verdict", "decision_engine", "Top-level reason for WATCH/AVOID"),
    "gates_evaluated": ("Verdict", "decision_engine", "List of 8-gate cascade results"),
    "gate": ("Verdict", "pre_trade_gate", "Pre-trade gate (liquidity, earnings, regime, gap)"),
    "caveats": ("Verdict", "decision_engine", "Soft warnings (not gate failures)"),

    # Setup attribution
    "setup_family": ("Setup", "classify_setup_family", "Breakout/Trend Continuation/Impulse/Special"),
    "entry_quality": ("Setup", "classify_entry_quality", "FRESH/PULLBACK/VALID/EXTENDED/MISSED"),
    "entry_subtype": ("Setup", "computed", "Sub-classifier (e.g., 'Breakout Add')"),
    "entry_timing": ("Setup", "computed", "FRESH/LATE/MISSED timing label"),
    "hold_period_guide": ("Setup", "classify_setup_family", "Recommended hold (e.g., '7-21d')"),
    "factor_tags": ("Setup", "computed", "Factor tags (PEAD/UOA/etc.)"),
    "catalyst_tags": ("Setup", "computed", "Active catalyst names"),
    "catalyst_tier": ("Setup", "tag_catalysts", "T1 (PEAD/UOA/VCP) / T2 / T3"),
    "catalyst_meta": ("Setup", "computed", "Catalyst meta info (T1 count etc.)"),

    # Trade plan
    "trade_plan": ("Trade Plan", "compute_trade_plan", "Full trade plan (37 fields): entry/stop/targets/zones/exit_rules"),
    "canonical_trade_plan": ("Trade Plan", "K6 canonical_trade_plan", "Single-source-of-truth dataclass (21 fields)"),
    "setup_quality": ("Trade Plan", "compute_trade_plan", "Quality label + momentum/strength/trend sub-scores"),

    # Technicals
    "technicals": ("Technicals", "score_technicals", "Container: indicators + smc_result + sr + details + score"),
    "ema_signal": ("Technicals", "computed", "EMA stack status (BULLISH STACK / etc.)"),
    "macd_signal": ("Technicals", "computed", "MACD trend (GOLDEN CROSS / etc.)"),
    "rsi": ("Technicals", "computed", "14-period RSI"),
    "fractal_high": ("Technicals", "computed", "Most recent fractal high (resistance)"),
    "fractal_low": ("Technicals", "computed", "Most recent fractal low (stop reference)"),
    "fractal_signal": ("Technicals", "computed", "Bullish/Bearish fractal pattern label"),
    "squeeze": ("Technicals", "computed", "TTM-style squeeze active flag"),
    "squeeze_flag": ("Technicals", "computed", "Squeeze detail (on/fired/direction)"),
    "patterns": ("Technicals", "computed", "Chart pattern detection (triangle, flag, etc.)"),
    "volume_profile": ("Technicals", "_volume_profile_full", "POC/VAH/VAL/HVN/LVN volume nodes"),
    "vwap": ("Technicals", "computed", "VWAP + anchored VWAP"),
    "premarket": ("Technicals", "premarket scan", "Premarket move + volume"),
    "patterns_short": ("Technicals", "computed", "Short-side patterns"),

    # SMC
    "smc": ("SMC", "smc_module", "Smart Money Concepts: BoS/CHoCH, FVG, OB, liquidity"),

    # Elliott Wave
    "elliott_wave": ("Elliott Wave", "classify_elliott_wave", "Legacy EW classifier (wave#, swing, fib levels)"),

    # Fundamentals
    "fundamentals": ("Fundamentals", "score_fundamentals", "Composite (bull_drivers, bear_risks, score)"),
    "extra_fund": ("Fundamentals", "get_extra_fundamentals", "EV/EBITDA, P/FCF, ROA, ROE, margins, buyback"),
    "fmp": ("Fundamentals", "schwab-fund-shim", "FMP-shape fundamentals (consensus, current_ratio, etc.)"),
    "finnhub": ("Fundamentals", "schwab-fund-shim", "Finnhub-shape fundamentals (52w, analysts, pe, eps)"),
    "analyst": ("Fundamentals", "computed", "Analyst targets/upgrades/eps_trend/revisions"),
    "eps_trend": ("Fundamentals", "computed", "EPS estimate trend (current/next Q + Y)"),

    # Options
    "options_data": ("Options", "Schwab Trader API", "current_iv, P/C ratio, OI, max_pain"),
    "options_intelligence": ("Options", "computed", "Gamma walls, IV skew, dominant flow, UOA detection"),
    "options_kpis": ("Options", "computed", "IV %ile, gamma_net, skew_25d, term_structure, verdict"),
    "options_chain": ("Options", "Schwab Trader API", "Raw option chain"),
    "options_intel": ("Options", "computed", "Aggregated intel summary"),
    "uoa": ("Options", "computed", "UOA flag/details"),
    "gamma": ("Options", "computed", "Gamma exposure data"),
    "optionality": ("Options", "score_optionality", "Pillar score for options/UOA"),

    # Smart-money / insider / institutional
    "insider_data": ("Smart Money", "EODHD/SEC EDGAR", "Insider buys/sells, CEO/CFO flag, sentiment"),
    "inst_trend": ("Smart Money", "computed", "Institutional ownership trend"),
    "congressional": ("Smart Money", "Senate Stock Watcher", "Congressional trades (free dataset)"),
    "sec_filings": ("Smart Money", "SEC EDGAR", "Recent 8K/10Q/Form 4 filings"),

    # Sentiment
    "stocktwits": ("Sentiment", "StockTwits scrape", "Bull%, message_volume, watchlist_count"),
    "reddit_wsb": ("Sentiment", "Reddit/WSB scrape", "Mentions + sentiment"),
    "news_articles": ("Sentiment", "EODHD+yfinance", "Raw news article list"),
    "news_data": ("Sentiment", "computed", "Aggregated news metadata"),
    "news_sentiment_score": ("Sentiment", "compute_news_sentiment_score", "Score/momentum/article_count/breaking"),
    "sentiment": ("Sentiment", "score_sentiment", "Pillar score for sentiment"),

    # Zacks
    "zacks_rank1": ("Zacks", "Zacks Premium scrape", "Is in Zacks Rank #1 universe"),
    "zacks_sell": ("Zacks", "Zacks Premium scrape", "Is in Zacks Sell list"),
    "zacks_vgm": ("Zacks", "Zacks Premium scrape", "VGM grade details"),
    "grade_growth": ("Zacks", "Zacks Premium scrape", "Zacks Growth grade (A-F)"),
    "grade_momentum": ("Zacks", "Zacks Premium scrape", "Zacks Momentum grade (A-F)"),
    "grade_value": ("Zacks", "Zacks Premium scrape", "Zacks Value grade (A-F)"),
    "grade_vgm": ("Zacks", "Zacks Premium scrape", "Combined VGM grade (A-F)"),
    "vgm_verdict": ("Zacks", "computed", "Bullish/Bearish/Neutral VGM verdict"),
    "gmail_bonus": ("Zacks", "gmail Zacks scraper", "Premium service email mentions"),

    # Regime
    "regime4": ("Regime", "get_market_regime", "risk_on_trending / risk_on_choppy / risk_off_trending / panic"),
    "market_phase": ("Regime", "computed", "Bull/early bull/late bull/correction/bear"),

    # Risk / sizing
    "kelly_size": ("Risk", "kelly_position_size", "Full Kelly stack (21 fields: kelly%, half-Kelly, regime/VIX/drawdown mults, suggested shares, CVaR)"),
    "sizing_multiplier": ("Risk", "computed", "Composite sizing multiplier"),
    "mc_p_profit": ("Risk", "compute_mc_p_profit", "Monte Carlo probability of profit"),

    # Theory confluence
    "theory_confluence": ("Theory", "compute_theory_confluence", "Bull/bear alignment across N theories (P11)"),

    # Tier-1 signals
    "tier1_signals": ("Tier1 Signals", "tier1_signals.py", "6 additive detectors (insider cluster, NR7, vol dry-up, OBV div, mean rev, beat-and-raise)"),

    # Multi-timeframe
    "mtf_label": ("Multi-Timeframe", "computed", "MTF agreement label"),
    "mtf_conflict": ("Multi-Timeframe", "computed", "MTF conflict flag"),
    "tf_4h": ("Multi-Timeframe", "computed", "4-hour timeframe data"),
    "long_term": ("Multi-Timeframe", "computed", "Long-term timeframe stats (6 fields)"),
    "medium_term": ("Multi-Timeframe", "computed", "Medium-term timeframe stats (5 fields)"),

    # Earnings
    "earnings": ("Earnings", "computed", "earnings_risk + days_to_earnings + last_earnings_date"),
    "earnings_warning": ("Earnings", "computed", "Warning string if upcoming earnings"),

    # Misc / meta
    "ohlcv": ("Bookkeeping", "data_fetcher", "90-day OHLCV bars (latest)"),
    "price_tier": ("Bookkeeping", "computed", "Price tier label ($1-25 / $25-100 / etc.)"),
    "ticker_source": ("Bookkeeping", "swing_trade", "Which universe added this ticker"),
    "_sector_rotation_bonus": ("Bookkeeping", "computed", "Bonus from sector rotation context"),
    "sector_pct_rank": ("Bookkeeping", "computed", "Percentile rank within sector"),
    "reaction_checklist": ("Bookkeeping", "computed", "Post-pick check items"),
    "methodology_checklist": ("Bookkeeping", "computed", "Pre-pick check items"),
    "trade_thesis": ("Bookkeeping", "compose_thesis", "Narrative thesis string"),
    "zone_quality": ("Bookkeeping", "computed", "Entry zone quality scoring"),
    "kpi": ("Bookkeeping", "computed", "Key performance indicators (live quote)"),
    "state": ("Bookkeeping", "computed", "Internal state placeholder"),
    "quote_snapshot": ("Bookkeeping", "real_time", "Live quote snapshot (delayed)"),
    "tv_rating": ("Bookkeeping", "TradingView scrape", "TradingView aggregate rating"),
    "direction": ("Bookkeeping", "computed", "long / short / neutral"),

    # Squeeze / patterns special
    "fractal_lows": ("Technicals", "computed", "Recent fractal low pivots"),
    "fractal_highs": ("Technicals", "computed", "Recent fractal high pivots"),
}


def _type_str(v) -> str:
    if isinstance(v, dict):
        return f"dict[{len(v)}]"
    if isinstance(v, list):
        return f"list[{len(v)}]"
    if v is None:
        return "None"
    return type(v).__name__


def _short_value(v) -> str:
    if isinstance(v, dict):
        return f"{{ {', '.join(list(v.keys())[:4])}{'...' if len(v) > 4 else ''} }}"
    if isinstance(v, list):
        if not v:
            return "[]"
        return f"[ {type(v[0]).__name__} × {len(v)} ]"
    s = repr(v)
    return s[:75] + "…" if len(s) > 75 else s


def categorize(field: str) -> tuple[str, str, str]:
    """Return (category, source, description) for a top-level field."""
    if field in CATEGORY_RULES:
        return CATEGORY_RULES[field]
    return ("Other", "—", "Uncategorized — review manually")


def walk_indicators(indicators: dict) -> list[tuple]:
    """Build rows for technicals.indicators (123 fields). Each row inherits 'Indicator' as cat."""
    rows = []
    for k in sorted(indicators.keys()):
        v = indicators[k]
        # Sub-categorize indicators
        if k.startswith("ema") or k.startswith("weekly_ema"):
            sub = "EMA Ladder"
        elif any(m in k for m in ("rsi", "stoch", "macd", "mfi", "cmf", "adx")):
            sub = "Momentum"
        elif any(t in k for t in ("supertrend", "sar", "golden_cross", "death_cross", "trend_direction", "trend_age", "bullish_stack", "ema_signal", "fib_ribbon")):
            sub = "Trend Signal"
        elif "52w" in k or k in ("near_52w_high", "near_52w_low", "pct_from_52w_high"):
            sub = "Range / 52w"
        elif any(v_ in k for v_ in ("atr", "bb_", "squeeze")):
            sub = "Volatility / Squeeze"
        elif any(p in k for p in ("vcp", "stage2", "near_vcp", "pocket_pivot", "candle_pattern", "fractal", "holy_grail")):
            sub = "Pattern"
        elif k in ("rvol", "pp_vol_ratio", "breakout_vol_ratio", "power_days", "power_trend", "obv_rising"):
            sub = "Volume / Flow"
        elif k in ("rs_rank", "rs_63d_pct", "outperforming_sector", "outperforming_spy", "sector_rotation_score", "sector_rotation_trend", "sector_rotation_label", "sector_vs_spy_pct", "sector_underperform", "sector_rank"):
            sub = "Relative Strength / Sector"
        elif k in ("support", "resistance", "vwap", "avwap_swing_low", "above_vwap", "above_avwap"):
            sub = "S/R / VWAP"
        elif k in ("lav_score", "lav_label", "at_resistance", "at_support", "loc_vol_at_resistance", "loc_vol_at_support", "loc_vol_score", "loc_vol_label"):
            sub = "Location-Adjusted Volume"
        elif k in ("day_change_pct", "prev_close", "above_20ema", "above_50ema", "above_200sma", "price_above_ema5"):
            sub = "Position vs Reference"
        else:
            sub = "Other indicator"
        rows.append(("Technicals", sub, f"technicals.indicators.{k}", _type_str(v), _short_value(v), "computed", ""))
    return rows


def walk_nested(parent_path: str, d: dict, category: str, source: str) -> list[tuple]:
    """Walk a nested dict one level deep — return rows."""
    rows = []
    if not isinstance(d, dict):
        return rows
    for k in sorted(d.keys()):
        v = d[k]
        rows.append((category, parent_path, f"{parent_path}.{k}", _type_str(v), _short_value(v), source, ""))
    return rows


def build_rows(sample: dict) -> list[tuple]:
    """Build all rows. Each tuple: (Category, SubGroup, Path, Type, Sample, Source, Notes)."""
    rows = []
    # Top-level fields
    for k in sorted(sample.keys()):
        v = sample[k]
        cat, src, desc = categorize(k)
        rows.append((cat, "Top-level", k, _type_str(v), _short_value(v), src, desc))

    # Drill into key rich nested fields
    NESTED = [
        ("trade_plan", "Trade Plan", "compute_trade_plan"),
        ("canonical_trade_plan", "Trade Plan", "K6 canonical_trade_plan"),
        ("scoring_breakdown", "Scoring", "computed"),
        ("conviction", "Verdict", "decision_engine"),
        ("decision_state", "Verdict", "decision_engine"),
        ("audit_trail", "Verdict", "decision_engine"),
        ("gate", "Verdict", "pre_trade_gate"),
        ("kelly_size", "Risk", "kelly_position_size"),
        ("setup_quality", "Trade Plan", "computed"),
        ("smc", "SMC", "smc_module"),
        ("elliott_wave", "Elliott Wave", "classify_elliott_wave"),
        ("options_data", "Options", "Schwab Trader API"),
        ("options_intelligence", "Options", "computed"),
        ("options_kpis", "Options", "computed"),
        ("fundamentals", "Fundamentals", "score_fundamentals"),
        ("extra_fund", "Fundamentals", "get_extra_fundamentals"),
        ("fmp", "Fundamentals", "schwab-fund-shim"),
        ("finnhub", "Fundamentals", "schwab-fund-shim"),
        ("analyst", "Fundamentals", "computed"),
        ("insider_data", "Smart Money", "EODHD/SEC EDGAR"),
        ("inst_trend", "Smart Money", "computed"),
        ("congressional", "Smart Money", "Senate Stock Watcher"),
        ("stocktwits", "Sentiment", "StockTwits scrape"),
        ("reddit_wsb", "Sentiment", "Reddit/WSB scrape"),
        ("news_sentiment_score", "Sentiment", "compute_news_sentiment_score"),
        ("theory_confluence", "Theory", "compute_theory_confluence"),
        ("tier1_signals", "Tier1 Signals", "tier1_signals.py"),
        ("gmail_bonus", "Zacks", "gmail Zacks scraper"),
    ]
    for top_key, cat, src in NESTED:
        sub = sample.get(top_key)
        if isinstance(sub, dict):
            rows.extend(walk_nested(top_key, sub, cat, src))

    # Special: technicals.indicators (123 fields, deserves its own sheet)
    indicators = (sample.get("technicals") or {}).get("indicators") or {}
    rows.extend(walk_indicators(indicators))
    return rows


def build_workbook(rows: list[tuple], sample_ticker: str) -> Workbook:
    wb = Workbook()

    # ── Sheet 1: Summary ────────────────────────────────────────────────
    ws = wb.active
    ws.title = "Summary"
    ws["A1"] = f"SwingTrade — Per-Ticker Field Inventory ({date.today().isoformat()})"
    ws["A1"].font = Font(size=14, bold=True)
    ws["A2"] = f"Sample ticker: {sample_ticker}"
    ws["A3"] = f"Total fields: {len(rows)}"
    ws["A4"] = "Source: cache/last_bundle.json (latest live scan)"

    # Category counts
    from collections import Counter
    cat_counts = Counter(r[0] for r in rows)
    ws["A6"] = "Category"
    ws["B6"] = "Field Count"
    ws["A6"].font = Font(bold=True); ws["B6"].font = Font(bold=True)
    row = 7
    for cat, n in sorted(cat_counts.items(), key=lambda x: -x[1]):
        ws.cell(row=row, column=1, value=cat)
        ws.cell(row=row, column=2, value=n)
        row += 1

    for col, width in enumerate([28, 14], 1):
        ws.column_dimensions[get_column_letter(col)].width = width

    # ── Sheet 2: All fields (flat) ─────────────────────────────────────
    ws = wb.create_sheet("All Fields")
    headers = ["Category", "SubGroup", "Field Path", "Type", "Sample Value", "Source", "Description"]
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="305496")
        cell.alignment = Alignment(horizontal="left", vertical="center")

    # Sort rows by category then sub-group
    cat_order = {
        "Identity": 1, "Pricing": 2, "Scoring": 3, "Verdict": 4,
        "Setup": 5, "Trade Plan": 6, "Technicals": 7, "SMC": 8,
        "Elliott Wave": 9, "Fundamentals": 10, "Options": 11,
        "Smart Money": 12, "Sentiment": 13, "Zacks": 14, "Regime": 15,
        "Risk": 16, "Theory": 17, "Tier1 Signals": 18,
        "Multi-Timeframe": 19, "Earnings": 20, "Bookkeeping": 21, "Other": 22,
    }
    rows_sorted = sorted(rows, key=lambda r: (cat_order.get(r[0], 99), r[1], r[2]))

    for ri, r in enumerate(rows_sorted, 2):
        for ci, v in enumerate(r, 1):
            ws.cell(row=ri, column=ci, value=v)
        # Alternate row shading per category
        cat = r[0]
        fill_color = {
            "Identity": "F0F8FF", "Pricing": "F0FFFF", "Scoring": "FFFAF0",
            "Verdict": "FFF5EE", "Setup": "FFEFD5", "Trade Plan": "F5FFFA",
            "Technicals": "F0FFF0", "SMC": "E6E6FA", "Elliott Wave": "FFF0F5",
            "Fundamentals": "FFFACD", "Options": "F5F5DC", "Smart Money": "FFE4E1",
            "Sentiment": "E0FFFF", "Zacks": "FFFFE0", "Regime": "F8F8FF",
            "Risk": "FFF0F5", "Theory": "FAFAD2", "Tier1 Signals": "FFE4B5",
            "Multi-Timeframe": "F0F8FF", "Earnings": "FFEFD5", "Bookkeeping": "F5F5F5",
            "Other": "FFFFFF",
        }.get(cat, "FFFFFF")
        for ci in range(1, len(headers) + 1):
            ws.cell(row=ri, column=ci).fill = PatternFill("solid", fgColor=fill_color)

    # Auto column widths
    for col, width in enumerate([18, 26, 50, 14, 50, 28, 60], 1):
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    # ── Sheet 3: Indicator deep-dive (123 fields organized) ────────────
    indicator_rows = [r for r in rows if r[0] == "Technicals" and r[1] != "Top-level"]
    ws = wb.create_sheet("Indicators (123)")
    for col, h in enumerate(["SubGroup", "Field Path", "Type", "Sample", "Source"], 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="305496")
    for ri, r in enumerate(sorted(indicator_rows, key=lambda x: (x[1], x[2])), 2):
        ws.cell(row=ri, column=1, value=r[1])  # SubGroup
        ws.cell(row=ri, column=2, value=r[2])  # Path
        ws.cell(row=ri, column=3, value=r[3])  # Type
        ws.cell(row=ri, column=4, value=r[4])  # Sample
        ws.cell(row=ri, column=5, value=r[5])  # Source
    for col, width in enumerate([28, 50, 14, 50, 16], 1):
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    return wb


def main():
    bundle = json.loads(BUNDLE.read_text())
    all_s = bundle.get("all_scored") or []
    if not all_s:
        print("No tickers in cache/last_bundle.json. Run a scan first.")
        return 1
    sample = max(all_s, key=lambda x: x.get("score", 0) or 0)
    rows = build_rows(sample)
    wb = build_workbook(rows, sample["ticker"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)
    print(f"Wrote {OUT}  ({OUT.stat().st_size:,} bytes, {len(rows)} fields)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

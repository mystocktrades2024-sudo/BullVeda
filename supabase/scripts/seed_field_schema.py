"""Seed public.field_schema from the field-inventory TSV.

The inventory TSV (supabase/seed_data/field_inventory.tsv) is the result of
the export_ticker_fields.py audit. Each row describes one field captured by
the scan pipeline.

Idempotent — ON CONFLICT (field_path) updates.

Columns expected in the TSV (tab-separated, header row):
    Category, SubGroup, Field Path, Type, Sample Value, Source, Description
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _client import pg_conn, repo_root  # noqa: E402


SEED_FILE = repo_root() / "supabase" / "seed_data" / "field_inventory.tsv"


# Heuristic mapping: field_path → (table_name, column_name)
# Reads my ER design and infers the table where each field lives.
PATH_TO_TABLE = {
    # technicals.indicators.* → technicals_ema / momentum / volatility / etc.
    r"^technicals\.indicators\.ema":             "technicals_ema",
    r"^technicals\.indicators\.weekly_ema":      "technicals_ema",
    r"^technicals\.indicators\.(?:rsi|macd|stoch|mfi|cmf|adx)":  "technicals_momentum",
    r"^technicals\.indicators\.(?:atr|bb_pct|squeeze|enhanced_squeeze|bars_in_squeeze)": "technicals_volatility",
    r"^technicals\.indicators\.(?:vcp|pocket_pivot|holy_grail|stage2|fractal|candle_patterns|near_vcp)": "technicals_pattern",
    r"^technicals\.indicators\.(?:golden_cross|death_cross|supertrend|sar|fib_ribbon|bullish_stack|trend_)": "technicals_trend",
    r"^technicals\.indicators\.(?:obv|power|rvol|breakout_vol|pp_vol)": "technicals_volume_flow",
    r"^technicals\.indicators\.(?:above_|day_change|prev_close|price_above_ema5)": "technicals_position",
    r"^technicals\.indicators\.(?:high_52w|low_52w|near_52w|at_52w|pct_from_52w)": "technicals_52w",
    r"^technicals\.indicators\.(?:rs_rank|rs_63d|sector_rank|sector_etf|sector_vs_spy|outperforming|sector_rotation|sector_outperforming|sector_underperform)": "technicals_relative_strength",
    r"^technicals\.indicators\.(?:vwap|avwap|above_vwap|above_avwap|support|resistance)": "technicals_sr_vwap",
    r"^technicals\.indicators\.(?:at_resistance|at_support|loc_vol|lav_)": "technicals_loc_volume",
    r"^technicals\.indicators\.weekly_aligned":  "technicals_relative_strength",
    r"^technicals\.indicators\.rr_ratio":        "trade_plan_risk",
    r"^technicals\.indicators\.":                "technicals_ema",   # fallback for stragglers
    r"^smc\.bos_choch":         "smc_bos_choch",
    r"^smc\.order_blocks":      "smc_order_blocks",
    r"^smc\.fvg_zones":         "smc_fvg_zones",
    r"^smc\.liquidity_sweeps":  "smc_liquidity_sweeps",
    r"^smc\.":                  "smc_summary",
    r"^elliott_wave":           "elliott_wave",
    r"^theory_confluence":      "theory_confluence",
    r"^canonical_trade_plan\.regime":  "trade_plans",
    r"^canonical_trade_plan\.risk":    "trade_plan_risk",
    r"^canonical_trade_plan\.entry":   "trade_plan_entries",
    r"^canonical_trade_plan\.":        "trade_plans",
    r"^trade_plan\.exit_":             "trade_plan_exit_rules",
    r"^trade_plan\.risk_flags":        "trade_plan_risk_flags",
    r"^trade_plan\.zone_confluence":   "trade_plan_zone_confluence",
    r"^trade_plan\.deep_zone":         "trade_plan_entries",
    r"^trade_plan\.shallow_zone":      "trade_plan_entries",
    r"^trade_plan\.primary_zone":      "trade_plan_entries",
    r"^trade_plan\.entry_":            "trade_plan_entries",
    r"^trade_plan\.fib_":              "trade_plan_entries",
    r"^trade_plan\.ichimoku":          "trade_plan_entries",
    r"^trade_plan\.elliott_wave":      "elliott_wave",
    r"^trade_plan\.":                  "trade_plans",
    r"^setup_quality":          "analysis_thesis",
    r"^scoring_breakdown":      "analysis_scoring",
    r"^audit_trail":            "analysis_verdict",
    r"^conviction":             "analysis_conviction",
    r"^decision_state":         "analysis_verdict",
    r"^gate\.":                 "analysis_gates",
    r"^gates_evaluated":        "analysis_gates",
    r"^kelly_size":             "risk_sizing",
    r"^mc_p_profit":            "risk_sizing",
    r"^sizing_multiplier":      "risk_sizing",
    r"^tier1_signals":          "tier1_signals",
    r"^analyst":                "analyst_summary",
    r"^extra_fund":             "fundamentals_extra",
    r"^fundamentals":           "fundamentals_pillar",
    r"^finnhub":                "ticker_fundamentals",
    r"^fmp":                    "ticker_fundamentals",
    r"^options_data":           "options_snapshot",
    r"^options_intelligence":   "options_intelligence",
    r"^options_kpis":           "options_kpis",
    r"^options_chain":          "option_chain",
    r"^options_intel":          "options_intelligence",
    r"^options_per_mode":       "options_per_mode",
    r"^uoa":                    "option_uoa_alerts",
    r"^gamma":                  "gamma_exposure",
    r"^optionality":            "options_kpis",
    r"^insider_data":           "insider_summary",
    r"^congressional":          "congressional_summary",
    r"^inst_trend":             "institutional_trend",
    r"^sec_filings":             "sec_filings",
    r"^news_articles":          "news_articles",
    r"^news_data":              "news_sentiment_snapshot",
    r"^news_sentiment_score":   "news_sentiment_snapshot",
    r"^reddit_wsb":             "reddit_wsb_snapshot",
    r"^stocktwits":             "stocktwits_snapshot",
    r"^sentiment":              "sentiment_pillar",
    r"^tv_rating":              "tv_rating",
    r"^grade_|^vgm_|^zacks_|^gmail_bonus": "zacks_data",
    r"^earnings":               "analysis_earnings",
    r"^mtf_|^long_term|^medium_term|^tf_4h": "mtf_summary",
    r"^volume_profile":         "volume_profile",
    r"^premarket":              "technicals_premarket",
    r"^patterns":               "chart_patterns",
    r"^kpi\.":                  "analysis_pricing",
    r"^quote_snapshot":         "analysis_pricing",
    r"^methodology_checklist":  "analysis_methodology",
    r"^reaction_checklist":     "analysis_methodology",
    r"^trade_thesis":           "analysis_thesis",
    r"^zone_quality":           "analysis_thesis",
    r"^catalyst_meta":          "analysis_catalysts",
    r"^catalyst_tags":          "analysis_catalysts",
    r"^catalyst_tier":          "ticker_analyses",
    r"^factor_tags":            "analysis_catalysts",
    r"^ohlcv":                  "analysis_ohlcv_window",
    r"^direction|^ticker$|^name$|^sector|^industry$|^beta$|^market_cap":  "tickers",
    r"^price$|^volume$|^avg_volume$|^rvol$|^atr_pct$|^price_tier$":  "analysis_pricing",
    r"^raw_score|^raw_growth|^raw_momentum|^raw_value|^score|^score_raw|^star_rating": "analysis_scoring",
    r"^verdict|^decision|^reject_reason|^caveats|^bear_setup|^bear_type": "analysis_verdict",
    r"^entry_quality|^entry_subtype|^entry_timing|^hold_period_guide|^setup_family|^setup_type": "ticker_analyses",
    r"^_sector_rotation_bonus|^state$|^ticker_source|^sector_pct_rank": "ticker_analyses",
    r"^market_phase|^regime4": "runs",
}


def map_field_to_table(field_path: str) -> tuple[str | None, str | None]:
    """Return (table_name, column_name) — best guess from the field_path."""
    for pattern, tbl in PATH_TO_TABLE.items():
        if re.match(pattern, field_path):
            # column = last segment of the path, with dots → _
            col = field_path.split(".")[-1]
            return tbl, col
    return None, field_path.split(".")[-1]


def load_seed():
    if not SEED_FILE.exists():
        print(f"  · seed file not found: {SEED_FILE}")
        print(f"  · expecting a TSV with columns: Category, SubGroup, Field Path, Type, Sample Value, Source, Description")
        return 0

    rows = []
    with SEED_FILE.open() as f:
        reader = csv.DictReader(f, delimiter="\t")
        for r in reader:
            fp = (r.get("Field Path") or r.get("field_path") or "").strip()
            if not fp:
                continue
            tbl, col = map_field_to_table(fp)
            rows.append((
                r.get("Category") or None,
                r.get("SubGroup") or r.get("Sub Group") or None,
                fp,
                tbl,
                col,
                r.get("Type") or None,
                (r.get("Sample Value") or "")[:512],
                r.get("Source") or None,
                r.get("Description") or None,
            ))

    if not rows:
        print("  · seed file has no rows")
        return 0

    with pg_conn() as conn, conn.cursor() as cur:
        cur.executemany(
            """
            insert into public.field_schema
                (category, sub_group, field_path, table_name, column_name,
                 data_type, sample_value, source, description)
            values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            on conflict (field_path) do update set
                category    = excluded.category,
                sub_group   = excluded.sub_group,
                table_name  = excluded.table_name,
                column_name = excluded.column_name,
                data_type   = excluded.data_type,
                sample_value= excluded.sample_value,
                source      = excluded.source,
                description = excluded.description,
                updated_at  = now()
            """,
            rows,
        )

    print(f"  ✓ field_schema seeded: {len(rows)} rows")
    return len(rows)


if __name__ == "__main__":
    load_seed()

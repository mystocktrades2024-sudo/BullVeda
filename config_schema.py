#!/usr/bin/env python3
"""AI-37: Pydantic-typed config schema.

Additive safety layer — the runtime still uses json.load(), this schema is
available for CI / development. Catches typos at load time and cross-field
rules (e.g. buy_min > watch_min).

Usage:
  python3 config_schema.py              # validate current config
  from config_schema import load_and_validate
  cfg = load_and_validate("config/config.json")
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Optional, Union

_ROOT = Path(__file__).parent

try:
    from pydantic import BaseModel, Field, field_validator, model_validator, ValidationError
    PYDANTIC_V2 = True
except ImportError:
    print("pydantic v2 required. Install: pip install 'pydantic>=2'", file=sys.stderr)
    sys.exit(2)


# ── Sub-models ──────────────────────────────────────────────────────────────

class MetaBlock(BaseModel):
    schema_version: str = "1.0"
    last_backtested: Optional[str] = None
    last_backtest_wr: Optional[float] = Field(default=None, ge=0, le=1)
    last_backtest_config: Optional[str] = None
    last_modified: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("last_backtested", "last_modified")
    @classmethod
    def _date_str(cls, v):
        if v is None:
            return v
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except Exception:
            raise ValueError(f"expected YYYY-MM-DD, got: {v}")
        return v


class RegimeThresholds(BaseModel):
    buy_min_score: int = Field(ge=0, le=100)
    watch_min_score: int = Field(default=55, ge=0, le=100)
    rs_min: int = Field(default=65, ge=0, le=100)
    rr_min: float = Field(default=3.0, gt=0)
    weekly_bull_required: bool = True

    @model_validator(mode="after")
    def _order(self):
        if self.buy_min_score <= self.watch_min_score:
            raise ValueError(f"buy_min_score ({self.buy_min_score}) must be > watch_min_score ({self.watch_min_score})")
        return self


class Regime4Thresholds(BaseModel):
    model_config = {"extra": "allow"}
    buy_min_score: int = Field(ge=0, le=9999)
    watch_min_score: Optional[int] = Field(default=None, ge=0, le=9999)
    rs_min: int = Field(default=65, ge=0, le=9999)
    rr_min: float = Field(default=3.0, gt=0)
    max_size_pct: int = Field(default=100, ge=0, le=100)
    vix_max: float = Field(default=25.0, gt=0)
    breadth_min: int = Field(default=30, ge=0, le=100)


class SetupGate(BaseModel):
    """Per-setup gate overrides. Read by analysis.py to replace hardcoded per-setup floors."""
    model_config = {"extra": "allow"}
    rs_min: int = Field(default=0, ge=0, le=100)
    rvol_min: float = Field(default=0.0, ge=0)
    weekly_bull_required: bool = Field(default=False)
    score_bonus_required: int = Field(default=0, ge=0)
    elite_rs_min: Optional[int] = Field(default=None, ge=0, le=100)
    min_score: Optional[int] = Field(default=None, ge=0, le=100)


class GatesConfig(BaseModel):
    min_liquidity_daily: float = Field(default=10_000_000, ge=0)
    earnings_blackout_days: int = Field(default=7, ge=0, le=30)
    extended_atr_gate: float = Field(default=1.5, gt=0)
    short_min_bear_score: int = Field(default=12, ge=0, lt=16,
                                       description="Must be < 16 (max bear_score)")
    short_min_vix: float = Field(default=25.0, gt=0)
    short_max_short_float_pct: float = Field(default=15.0, ge=0, le=100)
    short_max_dtc: float = Field(default=5.0, ge=0)
    short_max_rs_rank: int = Field(default=30, ge=0, le=100)
    short_earnings_block_days: int = Field(default=7, ge=0)
    distribution_days_no_new: int = Field(default=7, ge=0)
    vix_spike_kill_pct: float = Field(default=30.0, gt=0)


class ConfigE(BaseModel):
    max_positions: int = Field(ge=1, le=20)
    pct_per_trade: float = Field(gt=0, le=1)
    hold_days: int = Field(default=5, ge=1)
    max_hold_days: int = Field(default=10, ge=1)

    @model_validator(mode="after")
    def _gross(self):
        gross = self.max_positions * self.pct_per_trade
        if gross > 1.0:
            raise ValueError(f"max_positions × pct_per_trade = {gross:.2f} > 1.0 (>100% gross)")
        return self


class PortfolioConfig(BaseModel):
    account_equity: float = Field(gt=0)
    active_config: str = "config_e"
    config_e: ConfigE


class SwingTradeConfig(BaseModel):
    """Top-level typed view of config.json — additive validation only."""
    model_config = {"extra": "allow"}  # unknown keys pass through; we only validate what we type

    meta: Optional[MetaBlock] = Field(default=None, alias="_meta")
    gates: GatesConfig = Field(default_factory=GatesConfig)
    portfolio: PortfolioConfig
    regime_thresholds: Dict[str, RegimeThresholds] = Field(default_factory=dict)
    regime4_thresholds: Dict[str, Union[Regime4Thresholds, dict]] = Field(default_factory=dict)
    setup_gates: Dict[str, SetupGate] = Field(default_factory=dict)

    @field_validator("regime4_thresholds", mode="before")
    @classmethod
    def _drop_meta_keys(cls, v):
        """Config has '_max_size_pct_note' keys mixed in with regime dicts — drop those."""
        if isinstance(v, dict):
            return {k: val for k, val in v.items()
                    if not k.startswith("_") and isinstance(val, dict)}
        return v


# ── Loader ──────────────────────────────────────────────────────────────────

def load_and_validate(path: Optional[Union[str, Path]] = None) -> SwingTradeConfig:
    """Parse config.json → typed model. Raises with clear field-level errors."""
    path = path or (_ROOT / "config" / "config.json")
    try:
        raw = json.loads(Path(path).read_text())
    except Exception as e:
        raise RuntimeError(f"Cannot parse {path}: {e}")
    try:
        return SwingTradeConfig.model_validate(raw)
    except ValidationError as e:
        # Pretty-print errors
        lines = [f"❌ Config validation failed ({e.error_count()} error(s)):"]
        for err in e.errors():
            loc = ".".join(str(x) for x in err["loc"])
            lines.append(f"  · {loc}: {err['msg']}")
        raise RuntimeError("\n".join(lines)) from None


def describe_schema() -> Dict[str, Any]:
    """Return field counts + a summary for CLI reporting."""
    def _count(model) -> int:
        return len(model.model_fields) if hasattr(model, "model_fields") else 0
    return {
        "pydantic_version": __import__("pydantic").VERSION,
        "models": {
            "MetaBlock":         _count(MetaBlock),
            "RegimeThresholds":  _count(RegimeThresholds),
            "Regime4Thresholds": _count(Regime4Thresholds),
            "GatesConfig":       _count(GatesConfig),
            "ConfigE":           _count(ConfigE),
            "PortfolioConfig":   _count(PortfolioConfig),
            "SetupGate":         _count(SetupGate),
            "SwingTradeConfig":  _count(SwingTradeConfig),
        },
    }


def main():
    meta = describe_schema()
    print(f"Schema uses pydantic {meta['pydantic_version']}; {len(meta['models'])} models defined")
    total_fields = sum(meta["models"].values())
    for m, n in meta["models"].items():
        print(f"  {m:20s} {n} fields")
    print(f"Total typed fields: {total_fields}")
    print()
    try:
        cfg = load_and_validate()
        schema_ver = cfg.meta.schema_version if cfg.meta else "?"
        print(f"✓ Current config validates (schema v{schema_ver})")
        print(f"  portfolio.account_equity: ${cfg.portfolio.account_equity:,.0f}")
        print(f"  portfolio.config_e.max_positions × pct_per_trade: "
              f"{cfg.portfolio.config_e.max_positions} × {cfg.portfolio.config_e.pct_per_trade*100:.0f}% "
              f"= {cfg.portfolio.config_e.max_positions * cfg.portfolio.config_e.pct_per_trade*100:.0f}% gross")
        print(f"  regime4_thresholds: {list(cfg.regime4_thresholds.keys())}")
    except Exception as e:
        print(str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()

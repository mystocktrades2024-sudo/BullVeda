"""Startup config validator — fail fast if config.json is internally inconsistent.

Called by swing_trade.py at startup. Raises ConfigError with a clear message
listing every problem found (not just the first). Helps catch:
  - buy_min < watch_min (impossible ordering)
  - unreachable thresholds (e.g. short_min_bear_score > max possible score)
  - missing universe lists
  - missing required env vars
  - stale backtest (>90 days)
  - conflicting duplicate threshold sources

Usage:
    from config_validator import validate_config
    issues = validate_config(config_path="config/config.json")
    if issues:
        for i in issues: log.warning(i)
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path


class ConfigError(RuntimeError):
    pass


def validate_config(config_path: str | None = None, strict: bool = False) -> list[str]:
    """Return list of issues. If strict=True, raise ConfigError on any issue."""
    root = Path(__file__).parent
    config_path = config_path or str(root / "config" / "config.json")
    issues: list[str] = []

    try:
        cfg = json.loads(Path(config_path).read_text())
    except Exception as e:
        raise ConfigError(f"Cannot parse {config_path}: {e}")

    # ── Schema meta ──────────────────────────────────────────────
    _meta = cfg.get("_meta", {})
    if not _meta:
        issues.append("⚠️  _meta block missing — add schema_version + last_backtested")
    else:
        last_bt = _meta.get("last_backtested")
        if last_bt:
            try:
                bt_date = datetime.strptime(str(last_bt), "%Y-%m-%d").date()
                days_stale = (date.today() - bt_date).days
                if days_stale > 90:
                    issues.append(f"⚠️  Last backtest is {days_stale} days old ({last_bt}) — rerun to validate thresholds")
            except Exception:
                issues.append(f"⚠️  _meta.last_backtested not YYYY-MM-DD: {last_bt}")

    # ── Threshold ordering (buy_min > watch_min) ─────────────────
    for regime_key in ("regime_thresholds", "regime4_thresholds"):
        for name, rt in (cfg.get(regime_key) or {}).items():
            if not isinstance(rt, dict):
                continue
            buy = rt.get("buy_min_score")
            watch = rt.get("watch_min_score")
            # Skip sentinel "blocked" buckets (e.g. panic uses 999 for all).
            if buy is not None and watch is not None and buy < 999 and buy <= watch:
                issues.append(f"🔴 {regime_key}.{name}: buy_min_score ({buy}) <= watch_min_score ({watch}) — impossible")
            rr = rt.get("rr_min") or rt.get("buy_min_rr")
            if rr is not None and rr <= 0:
                issues.append(f"🔴 {regime_key}.{name}: rr_min ({rr}) must be > 0")

    # ── Short threshold reachability ─────────────────────────────
    short_min_bs = (
        cfg.get("regime_thresholds", {}).get("bear", {}).get("short_min_bear_score")
        or cfg.get("gates", {}).get("short_min_bear_score")
    )
    if short_min_bs is not None and short_min_bs > 15:
        issues.append(f"🔴 short_min_bear_score={short_min_bs} > max bear_score (15) — unreachable")

    # ── Conflicting threshold sources (informational) ────────────
    _buy_mins = []
    _dec_bm = cfg.get("decisions", {}).get("buy_min_score")
    if _dec_bm is not None:
        _buy_mins.append(("decisions.buy_min_score", _dec_bm))
    _bull_bm = cfg.get("regime_thresholds", {}).get("bull", {}).get("buy_min_score")
    if _bull_bm is not None:
        _buy_mins.append(("regime_thresholds.bull.buy_min_score", _bull_bm))
    _r4_bm = cfg.get("regime4_thresholds", {}).get("risk_on_trending", {}).get("buy_min_score")
    if _r4_bm is not None:
        _buy_mins.append(("regime4_thresholds.risk_on_trending.buy_min_score", _r4_bm))
    _unique_vals = {v for _, v in _buy_mins}
    if len(_unique_vals) > 1:
        pairs = ", ".join(f"{k}={v}" for k, v in _buy_mins)
        issues.append(f"⚠️  Conflicting bull BUY thresholds: {pairs} — pick one via resolver")

    # ── Universe ────────────────────────────────────────────────
    uni = cfg.get("universe", {})
    if not (uni.get("include_sp500") or uni.get("include_russell1000") or uni.get("custom_watchlist")):
        issues.append("🔴 universe: no SP500/Russell1000/custom_watchlist enabled — scan will be empty")

    # ── Sizing sanity ────────────────────────────────────────────
    pf = cfg.get("portfolio", {})
    cfg_e = pf.get("config_e", {})
    gross = float(cfg_e.get("max_positions", 0)) * float(cfg_e.get("pct_per_trade", 0))
    if gross > 1.0:
        issues.append(f"🔴 config_e gross allocation {gross*100:.0f}% > 100%")
    elif gross > 0.95:
        issues.append(f"⚠️  config_e gross allocation {gross*100:.0f}% — no cash buffer for trail stops")

    # ── Required keys present ───────────────
    # EODHD is the sole market-data provider as of 2026-04-25 migration.
    # Polygon / Finnhub / FMP keys are no longer required — checks removed 2026-05-02.
    try:
        import os
        if not os.environ.get("EODHD_API_KEY"):
            # Fallback: check .env file
            from pathlib import Path
            env_path = Path(__file__).parent / ".env"
            if env_path.exists():
                env_text = env_path.read_text()
                has_key = any(line.startswith("EODHD_API_KEY=") and len(line.split("=", 1)[1].strip()) > 5
                              for line in env_text.splitlines())
                if not has_key:
                    issues.append("⚠️  EODHD_API_KEY missing — sole market-data provider disabled")
            else:
                issues.append("⚠️  EODHD_API_KEY missing — sole market-data provider disabled")
    except Exception:
        pass

    # ── Regime4 buckets must carry watch_min_score ───────────────
    r4 = cfg.get("regime4_thresholds") or {}
    for name, rt in r4.items():
        if name.startswith("_") or not isinstance(rt, dict):
            continue
        if "watch_min_score" not in rt:
            issues.append(f"🔴 regime4_thresholds.{name}: missing watch_min_score (newly-required)")

    # ── setup_gates block required, must have 'default' ──────────
    sg = cfg.get("setup_gates")
    if not isinstance(sg, dict) or not sg:
        issues.append("🔴 setup_gates: block missing — analysis.py falls back to hardcoded per-setup floors")
    elif "default" not in sg:
        issues.append("🔴 setup_gates: missing required 'default' key")

    # ── regime_thresholds required fields ────────────────────────
    _required_reg = {"buy_min_score", "watch_min_score", "rs_min", "rr_min", "weekly_bull_required"}
    for name, rt in (cfg.get("regime_thresholds") or {}).items():
        if name.startswith("_") or not isinstance(rt, dict):
            continue
        missing = _required_reg - set(rt.keys())
        if missing:
            issues.append(f"🔴 regime_thresholds.{name}: missing required key(s): {sorted(missing)}")

    if strict and issues:
        raise ConfigError("Config validation failed:\n" + "\n".join(f"  {i}" for i in issues))

    return issues


if __name__ == "__main__":
    issues = validate_config()
    if not issues:
        print("✓ Config validation passed — no issues")
    else:
        print(f"Config validation found {len(issues)} issue(s):")
        for i in issues:
            print(f"  {i}")

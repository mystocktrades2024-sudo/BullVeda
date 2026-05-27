#!/usr/bin/env python3
"""
refresh_options_flow.py — intraday Live Options Flow refresh.

Runs every 5 min during extended market hours (Mon-Fri 5:30am-1:30pm PT). Reads the
universe from cache/last_bundle.json (top liquid tickers), fetches fresh
Schwab options chains, runs options_flow_scanner.scan(), and atomic-writes
infra/prototype/options_flow.json. The V2 dashboard reads this file and
overlays it onto the in-data.json options_flow_top30 if newer.

Cost: ~150 Schwab API calls per refresh, ~2-3 min runtime.
"""
from __future__ import annotations
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
LOG_DIR = BASE / "cache" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "options_flow_refresh.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [options_flow] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


def _is_market_hours() -> bool:
    """Schwab-authoritative market-hours check with safe hardcoded fallback.

    PRIMARY: Schwab /markets API via schwab_client.is_market_open_now(extended=True).
    This handles half-days (post-Thanksgiving, MLK day, early closes) correctly
    and uses the actual exchange calendar instead of a static window.

    FALLBACK (Schwab API unreachable): Mon-Fri 5:30am-1:30pm PT — 8h window
    covering pre-market UOA prints + 30min of post-close settlement data.

    Window rationale (fallback only):
      - 5:30am PT (= 8:30am ET) — covers pre-market UOA flow
      - 1:30pm PT (= 4:30pm ET) — catches post-close settled-print tick
    """
    # Primary path: Schwab market-calendar
    try:
        import schwab_client
        # include_extended=True covers pre+post (matches our 5:30-13:30 PT window)
        return schwab_client.is_market_open_now(include_extended=True)
    except Exception:
        pass

    # Fallback: hardcoded window
    import zoneinfo
    now = datetime.now(zoneinfo.ZoneInfo("America/Los_Angeles"))
    if now.weekday() >= 5:  # Sat=5, Sun=6
        return False
    minutes = now.hour * 60 + now.minute
    return (5 * 60 + 30) <= minutes <= (13 * 60 + 30)


# 2026-05-15 · High-options-volume seed list. These tickers carry the deepest
# options markets in US equities — UOA detection lives here regardless of
# whether the swing-screener flags them as setups. Mega-caps + sector ETFs +
# high-retail-vol single names. Refreshed manually when liquidity rankings
# shift (typically once a quarter).
OPTIONS_LIQUID_SEED = [
    # Mag-7 + adjacents
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "GOOG", "TSLA",
    # High-options-vol single names
    "AMD", "NFLX", "BABA", "PLTR", "SOFI", "RIVN", "COIN", "MSTR",
    "HOOD", "GME", "AMC", "NIO", "BA", "DIS", "AVGO", "CRM", "ORCL",
    "INTC", "MU", "MARA", "RIOT", "F", "GM", "X", "CCL", "DAL", "UAL",
    # Financials with deep options
    "JPM", "BAC", "GS", "MS", "C", "WFC", "BLK",
    # Sector ETFs
    "SPY", "QQQ", "IWM", "DIA",
    "XLK", "XLF", "XLE", "XLV", "XLY", "XLI", "XLP", "XLU", "XLB", "XLRE", "XLC",
    # Volatility products
    "VIX", "UVXY", "VXX", "SVXY",
    # Megacap-adjacent
    "ADBE", "PEP", "KO", "WMT", "HD", "COST", "JNJ", "PFE", "UNH",
]


def _load_universe(top_n: int = 200) -> list[str]:
    """Pull universe for UOA scan = top-N by screener score UNION high-options-volume seed.

    The screener's score-ranked top-N curates for SETUP QUALITY (swing-trade signals).
    UOA detection is a DIFFERENT lens — smart-money positioning lives in high-liquidity
    names regardless of setup quality. Without the seed union, mega-caps like AAPL/NVDA
    with clear PCR < 0.5 imbalances never reach the scanner because they don't surface
    in the swing screen. Union ensures both universes get checked.
    """
    bundle_path = BASE / "cache" / "last_bundle.json"
    if not bundle_path.exists():
        log.warning("No bundle found — falling back to OPTIONS_LIQUID_SEED only")
        return list(dict.fromkeys(OPTIONS_LIQUID_SEED))

    bundle = json.loads(bundle_path.read_text())
    candidates: dict[str, float] = {}

    for sec in ("buy_candidates", "watch_list", "near_short_blocked",
                "all_scored", "medium_term_picks", "long_term_picks"):
        items = bundle.get(sec) or []
        if not isinstance(items, list):
            continue
        for r in items:
            if not isinstance(r, dict):
                continue
            t = r.get("ticker")
            if not t:
                continue
            score = float(r.get("score") or r.get("composite_score") or 0)
            candidates[t] = max(candidates.get(t, 0), score)

    ranked = sorted(candidates.items(), key=lambda kv: -kv[1])
    screener_top = [t for t, _ in ranked[:top_n]]
    # Union: preserve screener order first, then append seeds not already covered
    seen = set(screener_top)
    out = list(screener_top)
    for t in OPTIONS_LIQUID_SEED:
        if t not in seen:
            out.append(t)
            seen.add(t)
    return out


def _fetch_options(tickers: list[str]) -> tuple[dict, dict]:
    """Fetch Schwab options chains; return (options_iv_data, prices)."""
    from data_fetcher import get_options_iv_data
    from concurrent.futures import ThreadPoolExecutor, as_completed

    options: dict[str, dict] = {}
    prices: dict[str, float] = {}

    def _fetch_one(t: str):
        try:
            return t, get_options_iv_data(t)
        except Exception as e:
            log.debug(f"options fetch failed for {t}: {e}")
            return t, None

    log.info(f"Fetching Schwab chains for {len(tickers)} tickers...")
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(_fetch_one, t): t for t in tickers}
        n = 0
        for fut in as_completed(futures):
            t, data = fut.result()
            n += 1
            if data:
                options[t] = data
                # Schwab response includes spot via the chain — but get_options_iv_data
                # doesn't extract it, so estimate from the bundle if needed.
            if n % 50 == 0:
                log.info(f"  {n}/{len(tickers)} fetched ({(time.time()-t0):.1f}s elapsed)")
    log.info(f"Got options data for {len(options)}/{len(tickers)} tickers ({(time.time()-t0):.1f}s)")
    return options, prices


def _enrich_prices_from_bundle(tickers: list[str]) -> dict[str, float]:
    """Pull prices from the bundle for scan() rather than re-fetching."""
    bundle_path = BASE / "cache" / "last_bundle.json"
    bundle = json.loads(bundle_path.read_text()) if bundle_path.exists() else {}
    prices: dict[str, float] = {}
    for sec_val in bundle.values():
        if not isinstance(sec_val, list):
            continue
        for r in sec_val:
            if not isinstance(r, dict):
                continue
            t = r.get("ticker")
            p = r.get("price")
            if t and p and t in tickers and t not in prices:
                prices[t] = float(p)
    return prices


def _enrich_funds_from_bundle(tickers: list[str]) -> dict[str, dict]:
    """Pull sector + days_to_earnings sidecar for scan()."""
    bundle_path = BASE / "cache" / "last_bundle.json"
    bundle = json.loads(bundle_path.read_text()) if bundle_path.exists() else {}
    funds: dict[str, dict] = {}
    for sec_val in bundle.values():
        if not isinstance(sec_val, list):
            continue
        for r in sec_val:
            if not isinstance(r, dict):
                continue
            t = r.get("ticker")
            if t and t in tickers and t not in funds:
                funds[t] = {
                    "sector": r.get("sector") or "Unknown",
                    "days_to_earnings": ((r.get("earnings") or {}).get("days_to_earnings")
                                         if isinstance(r.get("earnings"), dict) else None),
                }
    return funds


def _read_previous_strong() -> set[str]:
    """Strong tickers from the previous refresh — for delta-based alerting."""
    out_path = BASE / "infra" / "prototype" / "options_flow.json"
    if not out_path.exists():
        return set()
    try:
        prev = json.loads(out_path.read_text())
        return {x["ticker"] for x in (prev.get("top30") or []) if x.get("status") == "STRONG"}
    except Exception:
        return set()


def _send_slack_delta(top30: list[dict], prev_strong: set[str]) -> None:
    """Slack-alert NEW STRONG signals (delta from prior refresh).

    No spam: silent if no new STRONG. Includes price, P/C, max-pain, sector
    so the alert is actionable on its own without opening the dashboard.
    """
    cur_strong = [x for x in top30 if x.get("status") == "STRONG"]
    new_strong = [x for x in cur_strong if x["ticker"] not in prev_strong]
    if not new_strong:
        return
    try:
        from alerts import send_alert
        lines = []
        for x in new_strong:
            tk = x.get("ticker")
            px = x.get("price")
            pc = x.get("put_call_ratio")
            mp = x.get("max_pain")
            sec = (x.get("sector") or "").split(" - ")[0]
            uoa = "✓ UOA" if x.get("uoa_calls") else ""
            lines.append(
                f"*{tk}* @ ${px:.2f}  ·  P/C {pc:.2f}  ·  max-pain ${mp:.0f}  ·  {sec}  {uoa}"
            )
        body = "\n".join(lines)
        title = f"📈 New STRONG options flow: {', '.join(x['ticker'] for x in new_strong)}"
        send_alert("WARN", title, body)
        log.info(f"Slack alert sent for {len(new_strong)} new STRONG signal(s)")
    except Exception as e:
        log.warning(f"Slack alert failed (non-fatal): {e}")


def main(force: bool = False) -> int:
    if not force and not _is_market_hours():
        log.info("Skipping — outside market hours (Mon-Fri 5:30am-1:30pm PT). Use --force to override.")
        return 0

    tickers = _load_universe(top_n=200)
    if not tickers:
        log.error("No universe — bundle missing or empty. Run a full scan first.")
        return 1

    options, _ = _fetch_options(tickers)
    if not options:
        log.error("No options data fetched. Schwab token may be expired — run python3 schwab_auth.py oauth")
        return 2

    prices = _enrich_prices_from_bundle(list(options.keys()))
    funds = _enrich_funds_from_bundle(list(options.keys()))

    from options_flow_scanner import scan as _scan
    flow = _scan(options, prices, funds)
    top30 = flow[:30]

    if not top30:
        log.warning("Scanner returned 0 candidates — universe may not have UOA imbalance right now")

    # 2026-05-26 · OPTIONS-QUANT-DATA — enrich top30 with HV20 from EODHD daily
    # bars, then compute IVRP (variance risk premium) = atm_iv − HV20.
    # Vectorized: one EODHD call per ticker. Failures degrade gracefully to null.
    try:
        from data_fetcher import fetch_market_data
        import numpy as np
        tickers_for_hv = [p["ticker"] for p in top30 if p.get("atm_iv") is not None]
        if tickers_for_hv:
            md = fetch_market_data(tickers_for_hv, period="2mo")
            for pick in top30:
                tk = pick.get("ticker")
                df = md.get(tk) if isinstance(md, dict) else None
                if df is None or len(df) < 21:
                    pick["hv20"] = None
                    pick["ivrp"] = None
                    continue
                try:
                    close = df["Close"].astype(float)
                    logret = np.log(close / close.shift(1)).dropna()
                    if len(logret) < 20:
                        pick["hv20"] = None; pick["ivrp"] = None; continue
                    # Annualized 20-day realized vol (252 trading days)
                    hv20 = float(logret.iloc[-20:].std() * (252 ** 0.5))
                    pick["hv20"] = round(hv20, 4)
                    # HV30 / HV60 — broader-horizon realized vol for multi-tier IV-RV
                    if len(logret) >= 30:
                        pick["hv30"] = round(float(logret.iloc[-30:].std() * (252 ** 0.5)), 4)
                    else:
                        pick["hv30"] = None
                    if len(logret) >= 60:
                        pick["hv60"] = round(float(logret.iloc[-60:].std() * (252 ** 0.5)), 4)
                    else:
                        pick["hv60"] = None
                    atm_iv = pick.get("atm_iv")
                    if atm_iv is not None:
                        # IVRP > 0 = IV richer than realized (sell premium edge)
                        # IVRP < 0 = IV cheaper than realized (buy premium edge)
                        pick["ivrp"] = round(float(atm_iv) - hv20, 4)
                    else:
                        pick["ivrp"] = None
                except Exception:
                    pick["hv20"] = None; pick["hv30"] = None; pick["hv60"] = None; pick["ivrp"] = None
            log.info(f"HV20+IVRP computed for {sum(1 for p in top30 if p.get('hv20') is not None)}/{len(top30)} picks")
    except Exception as e:
        log.warning(f"HV20/IVRP enrichment failed (non-fatal): {e}")

    # Snapshot prior STRONG before overwriting, for delta-based Slack alert
    prev_strong = _read_previous_strong()

    payload = {
        "refreshed_at":  datetime.now(timezone.utc).isoformat(),
        "universe_size": len(options),
        "top30":          top30,
    }

    out_path = BASE / "infra" / "prototype" / "options_flow.json"
    tmp = out_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, default=str))
    tmp.replace(out_path)  # atomic on POSIX

    # 2026-05-25 · history snapshot logger — append one line per pick to
    # cache/options_flow_history.jsonl for later outcome tracking + accuracy
    # measurement. Compact schema; the outcome tracker fills in realized
    # results 7+ days later.
    try:
        hist_path = BASE / "cache" / "options_flow_history.jsonl"
        hist_path.parent.mkdir(parents=True, exist_ok=True)
        snap_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with open(hist_path, "a") as hf:
            for pick in top30:
                # 2026-05-26 · OPTIONS-HISTORY-OPTION-R · log strategy + chain fields
                # so future outcome trackers can compute true option-trade R-multiples
                pcr = pick.get("put_call_ratio") or 1.0
                iv_pct = pick.get("iv_percentile")
                is_bull = pcr < 1.0
                iv_rich = iv_pct is not None and iv_pct > 70
                strategy = (
                    ("Bull Call Spread" if iv_rich else "Long Call")
                    if is_bull else
                    ("Bear Put Spread" if iv_rich else "Long Put")
                )
                row = {
                    "snap_date":   snap_date,
                    "snap_ts":     payload["refreshed_at"],
                    "ticker":      pick.get("ticker"),
                    "price":       pick.get("price"),
                    "status":      pick.get("status"),
                    "put_call_ratio": pick.get("put_call_ratio"),
                    "uoa_calls":   pick.get("uoa_calls"),
                    "iv_percentile": pick.get("iv_percentile"),
                    "max_pain":    pick.get("max_pain"),
                    "stop":        pick.get("stop"),
                    "target":      pick.get("target"),
                    "rr":          pick.get("rr"),
                    "sector":      pick.get("sector"),
                    # New fields (commit 8 OPTIONS-HISTORY-OPTION-R)
                    "strategy":     strategy,
                    "atm_strike":   pick.get("atm_strike"),
                    "atm_dte":      pick.get("atm_dte"),
                    "atm_iv":       pick.get("atm_iv"),
                    "atm_delta":    pick.get("atm_delta"),
                    "hv20":         pick.get("hv20"),
                    "ivrp":         pick.get("ivrp"),
                    "direction":    "long" if is_bull else "short",
                    "iv_regime":    ("rich" if iv_rich else
                                     "cheap" if (iv_pct is not None and iv_pct < 30) else
                                     "normal" if iv_pct is not None else "unknown"),
                    "cohort_top":   max(
                        [("0DTE",    pick.get("cohort_0dte_pct") or 0),
                         ("weekly",  pick.get("cohort_weekly_pct") or 0),
                         ("monthly", pick.get("cohort_monthly_pct") or 0),
                         ("LEAP",    pick.get("cohort_leap_pct") or 0)],
                        key=lambda kv: kv[1]
                    )[0] if any(pick.get(k) for k in ("cohort_0dte_pct","cohort_weekly_pct","cohort_monthly_pct","cohort_leap_pct")) else None,
                }
                hf.write(json.dumps(row, default=str) + "\n")
        log.info(f"Logged {len(top30)} snapshots to options_flow_history.jsonl")
    except Exception as e:
        log.warning(f"options_flow history-log failed (non-fatal): {e}")

    strong = sum(1 for x in top30 if x.get("status") == "STRONG")
    mod    = sum(1 for x in top30 if x.get("status") == "MODERATE")
    log.info(f"Wrote {out_path.name}: {len(top30)} candidates "
             f"(STRONG={strong}, MODERATE={mod}); top STRONG: "
             f"{[x['ticker'] for x in top30 if x.get('status')=='STRONG'][:5]}")

    # Slack: only fires when we see NEW STRONG signals (no spam on repeats)
    if not force:  # don't alert on test/manual runs
        _send_slack_delta(top30, prev_strong)
    return 0


if __name__ == "__main__":
    force = "--force" in sys.argv
    sys.exit(main(force=force))

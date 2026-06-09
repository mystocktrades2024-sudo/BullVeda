#!/usr/bin/env python3
"""
health_check_sources.py — data-supplier liveness probe (Open Risk #5).
=====================================================================
Checks each upstream data supplier with ONE cheap call apiece and posts a
single Slack CRITICAL alert when any is DOWN. Built for the #1 silent-failure
mode: a dead Finviz Elite token silently falls back to per-ticker EODHD
fundamentals, costing ~10x the EODHD quota with NO warning.

Suppliers probed (in priority order):
  1. FINVIZ ELITE  — tiny 1-view export (cost risk; highest priority).
                     DOWN => 401 / empty / exception.
                     Consequence: scan falls back to 10x EODHD fundamentals cost.
  2. SCHWAB OAUTH  — refresh-token grant probe (same as check_schwab_token.py).
                     DOWN => auth fails / token expired => options + IV data dark.
  3. EODHD         — sync_quota_from_server() (1 billed unit). Also reports quota %.
                     DOWN => primary OHLCV/fundamentals provider unreachable.
  4. REDDIT/STKTWTS (free scrape, best-effort) — cache staleness only, no scrape.
  5. CONGRESS      (free scrape, best-effort) — cache staleness only, no scrape.

Reuses alerts.send_alert("CRITICAL", ...) — the project's canonical Slack helper
(auto-loads SLACK_WEBHOOK_URL via secrets_loader; posts Slack for WARN/CRITICAL).

ALWAYS exits 0 — a health check must not fail its own launchd job.

Args:
  --dry-run   probe + print, never post to Slack
  --verbose   per-check detail lines
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Free-scrape staleness threshold (hours). Reddit/StockTwits + Congress are
# refreshed by their own launchd jobs; we only flag if the cache went cold.
SCRAPE_STALE_HOURS = 48.0

# Best-effort env hydration so alerts.send_alert + clients see secrets even
# when launchd starts us with a bare environment.
def _hydrate_env() -> None:
    import os
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    try:
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            os.environ.setdefault(k, v)
    except Exception:
        pass


class CheckResult:
    def __init__(self, name: str, ok: bool, detail: str, consequence: str = "",
                 priority: int = 99):
        self.name = name
        self.ok = ok
        self.detail = detail
        self.consequence = consequence
        self.priority = priority  # lower = more important

    @property
    def status(self) -> str:
        return "UP" if self.ok else "DOWN"


# ── 1. FINVIZ ELITE — highest priority (cost risk) ───────────────────────────
def check_finviz() -> CheckResult:
    name = "Finviz Elite"
    consequence = ("Finviz down -> scan falls back to per-ticker EODHD "
                   "fundamentals (~10x EODHD quota cost) with no other warning")
    try:
        from secrets_loader import finviz_token as _ft
        token = _ft()
    except Exception:
        token = ""
    if not token:
        try:
            import data_fetcher
            token = data_fetcher._finviz_token()
        except Exception:
            token = ""
    if not token:
        return CheckResult(name, False, "no FINVIZ_TOKEN configured",
                           consequence, priority=1)

    # ONE tiny export call — view 111 (overview), capped tickers, ~1 cheap GET.
    try:
        import requests
        url = "https://elite.finviz.com/export.ashx"
        params = {"v": 111, "auth": token, "f": "idx_sp500"}
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36",
            "Accept": "text/csv,*/*",
            "Referer": "https://elite.finviz.com/screener.ashx",
        }
        r = requests.get(url, params=params, headers=headers, timeout=20)
        if r.status_code == 401 or r.status_code == 403:
            return CheckResult(name, False, f"HTTP {r.status_code} (token rejected)",
                               consequence, priority=1)
        if r.status_code != 200:
            return CheckResult(name, False, f"HTTP {r.status_code}",
                               consequence, priority=1)
        body = (r.text or "").strip()
        # A valid Elite export returns CSV with a "Ticker" header. A dead token
        # often returns 200 + an HTML login page or an empty body.
        if not body or "Ticker" not in body.splitlines()[0]:
            head = body[:60].replace("\n", " ")
            return CheckResult(name, False, f"empty / non-CSV body ('{head}')",
                               consequence, priority=1)
        rows = max(0, len(body.splitlines()) - 1)
        return CheckResult(name, True, f"export OK ({rows} rows)", priority=1)
    except Exception as e:
        return CheckResult(name, False, f"exception: {e}", consequence, priority=1)


# ── 2. SCHWAB OAUTH ──────────────────────────────────────────────────────────
def check_schwab() -> CheckResult:
    name = "Schwab OAuth"
    consequence = "Schwab auth down -> options chain + IV + intraday NBBO go dark"
    import os
    key = os.environ.get("SCHWAB_APP_KEY")
    secret = os.environ.get("SCHWAB_APP_SECRET")
    refresh = os.environ.get("SCHWAB_REFRESH_TOKEN")
    if not (key and secret and refresh):
        return CheckResult(name, False, "missing Schwab credentials in env",
                           consequence, priority=2)
    # Probe the refresh-token grant WITHOUT rotating/writing (read-only health
    # check; check_schwab_token.py owns the daily rotation). A successful grant
    # proves the refresh token is still valid.
    try:
        import base64
        import json as _json
        import urllib.request
        import urllib.error
        auth = base64.b64encode(f"{key}:{secret}".encode()).decode()
        body = f"grant_type=refresh_token&refresh_token={refresh}".encode()
        req = urllib.request.Request(
            "https://api.schwabapi.com/v1/oauth/token",
            data=body,
            headers={
                "Authorization": f"Basic {auth}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            tok = _json.loads(resp.read().decode())
        if tok.get("access_token"):
            return CheckResult(name, True, "refresh grant OK", priority=2)
        return CheckResult(name, False, "grant returned no access_token",
                           consequence, priority=2)
    except urllib.error.HTTPError as e:
        code = e.code
        try:
            err = e.read().decode()[:120]
        except Exception:
            err = ""
        return CheckResult(name, False, f"HTTP {code} ({err})", consequence,
                           priority=2)
    except Exception as e:
        return CheckResult(name, False, f"exception: {e}", consequence, priority=2)


# ── 3. EODHD ─────────────────────────────────────────────────────────────────
def check_eodhd() -> CheckResult:
    name = "EODHD"
    consequence = "EODHD down -> primary OHLCV + fundamentals + sentiment provider lost"
    try:
        import eodhd_client
        res = eodhd_client.sync_quota_from_server()  # 1 billed unit, crash-safe
        if not res:
            # sync returns {} on any failure (incl. transient); fall back to the
            # local no-network status so we still surface quota %.
            try:
                st = eodhd_client.eodhd_quota_status()
                used = st.get("count")
                limit = st.get("daily_limit")
                pct = (100.0 * used / limit) if (used and limit) else None
                pct_s = f", quota ~{pct:.0f}% (local)" if pct is not None else ""
                return CheckResult(name, False,
                                   f"quota sync returned empty{pct_s}",
                                   consequence, priority=3)
            except Exception:
                return CheckResult(name, False, "quota sync returned empty",
                                   consequence, priority=3)
        used = res.get("used")
        limit = res.get("limit")
        pct = (100.0 * used / limit) if (used and limit) else None
        pct_s = f", quota {pct:.0f}% used" if pct is not None else ""
        return CheckResult(name, True, f"user endpoint OK ({used:,} units{pct_s})",
                           priority=3)
    except Exception as e:
        return CheckResult(name, False, f"exception: {e}", consequence, priority=3)


# ── 4 & 5. Free scrapes — cache staleness only (no scrape, best-effort) ──────
def _cache_age_hours(p: Path) -> float | None:
    try:
        if not p.exists():
            return None
        return (time.time() - p.stat().st_mtime) / 3600.0
    except Exception:
        return None


def check_retail_scrapes() -> CheckResult:
    name = "Reddit/StockTwits"
    consequence = "social sentiment stale -> retail-sentiment signal degrades (informational)"
    age = _cache_age_hours(ROOT / "cache" / "retail_sentiment.json")
    if age is None:
        return CheckResult(name, False, "cache file missing", consequence, priority=4)
    if age > SCRAPE_STALE_HOURS:
        return CheckResult(name, False, f"cache stale {age:.0f}h (>{SCRAPE_STALE_HOURS:.0f}h)",
                           consequence, priority=4)
    return CheckResult(name, True, f"cache {age:.0f}h old", priority=4)


def check_congress() -> CheckResult:
    name = "Congress"
    consequence = "congressional-trades feed stale -> insider/political signal degrades (informational)"
    age = _cache_age_hours(ROOT / "cache" / "congressional_trades.json")
    if age is None:
        return CheckResult(name, False, "cache file missing", consequence, priority=5)
    if age > SCRAPE_STALE_HOURS:
        return CheckResult(name, False, f"cache stale {age:.0f}h (>{SCRAPE_STALE_HOURS:.0f}h)",
                           consequence, priority=5)
    return CheckResult(name, True, f"cache {age:.0f}h old", priority=5)


def run_checks() -> list[CheckResult]:
    checks = [
        check_finviz,
        check_schwab,
        check_eodhd,
        check_retail_scrapes,
        check_congress,
    ]
    results: list[CheckResult] = []
    for fn in checks:
        try:
            results.append(fn())
        except Exception as e:
            results.append(CheckResult(fn.__name__, False, f"check crashed: {e}",
                                       "", priority=50))
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description="Data-supplier liveness probe (Open Risk #5)")
    ap.add_argument("--dry-run", action="store_true",
                    help="probe + print, never post to Slack")
    ap.add_argument("--verbose", action="store_true", help="per-check detail")
    args = ap.parse_args()

    _hydrate_env()
    when = datetime.now().strftime("%a %b %-d %-I:%M %p PT")
    results = run_checks()
    down = [r for r in results if not r.ok]

    if args.verbose or args.dry_run:
        for r in sorted(results, key=lambda x: x.priority):
            mark = "OK  " if r.ok else "DOWN"
            print(f"  [{mark}] {r.name}: {r.detail}")

    # The cost-risk DOWN (Finviz) is the headline; otherwise list every DOWN.
    down_sorted = sorted(down, key=lambda x: x.priority)
    summary = (f"source-health {when} · {len(results)-len(down)}/{len(results)} UP"
               + (f" · DOWN: {', '.join(r.name for r in down_sorted)}" if down else ""))
    print(summary)

    if down:
        title = f"Data source DOWN: {', '.join(r.name for r in down_sorted)}"
        lines = []
        for r in down_sorted:
            line = f"• *{r.name}* DOWN — {r.detail}"
            if r.consequence:
                line += f"\n   ⮑ {r.consequence}"
            lines.append(line)
        ups = [r.name for r in results if r.ok]
        if ups:
            lines.append(f"_UP: {', '.join(ups)}_")
        body = "\n".join(lines)

        if args.dry_run:
            print("\n[DRY-RUN] Would post Slack CRITICAL:")
            print(f"  title: {title}")
            for ln in body.split("\n"):
                print(f"  {ln}")
        else:
            try:
                from alerts import send_alert
                send_alert("CRITICAL", title, body)
                print(f"Posted Slack CRITICAL ({len(down)} source(s) down)")
            except Exception as e:
                print(f"Slack post failed (continuing): {e}", file=sys.stderr)

    # ALWAYS exit 0 — health check must never fail its launchd job.
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"health_check_sources crashed: {e}", file=sys.stderr)
        sys.exit(0)

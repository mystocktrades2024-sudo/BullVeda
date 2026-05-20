#!/usr/bin/env python3
"""Pre-market session-aware gapper scanner.

Detects pre-market session (Mon-Fri 4:00-9:30am ET = 1:00-6:30am PT) and, when
in-session, fetches EODHD real_time quotes for the liquid universe + filters
gappers (|change_p| >= 3% AND meaningful volume). Cross-references with
overnight news for catalyst attribution. Writes cache/premarket.json.

When OUT of session, writes a "session_inactive" payload with the timestamp of
the last completed session's data — frontend tab falls back to data.market_movers
+ data.earnings_outcomes for context.

Designed to run every 30 minutes between 4am-9:30am ET on weekdays via launchd.
Cheap on EODHD quota: 1 batch real_time call per run (up to 500 tickers/batch).
"""
from __future__ import annotations
import datetime
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path(__file__).parent.parent
OUT = BASE / "cache" / "premarket.json"
sys.path.insert(0, str(BASE))


def _is_premarket_session_now() -> tuple[bool, datetime.datetime, str]:
    """Returns (in_session, now_et, reason)."""
    now_et = datetime.datetime.now(ZoneInfo("America/New_York"))
    wd = now_et.weekday()  # 0=Mon, 6=Sun
    if wd >= 5:
        return False, now_et, f"weekend (weekday={wd})"
    open_t  = now_et.replace(hour=4,  minute=0,  second=0, microsecond=0)
    close_t = now_et.replace(hour=9,  minute=30, second=0, microsecond=0)
    if open_t <= now_et < close_t:
        return True, now_et, "in pre-market session"
    if now_et < open_t:
        return False, now_et, f"before session ({now_et.strftime('%H:%M')} ET; opens 04:00)"
    return False, now_et, f"after session ({now_et.strftime('%H:%M')} ET; closed 09:30)"


def _load_universe() -> list[str]:
    """Load a liquid US-equity universe for the pre-market scan.

    Sources, in priority:
      1. cache/last_bundle.json all_scored (whatever was scored today)
      2. infra/prototype/tickers.json (v2 dashboard universe)
      3. SP500 from EODHD index_components fallback
    Caps at 500 tickers to stay within one batch real_time call.
    """
    # Bundle first — what we actually trade
    last = BASE / "cache" / "last_bundle.json"
    if last.exists():
        try:
            b = json.loads(last.read_text())
            tks = sorted({r.get("ticker") for r in (b.get("all_scored") or []) if r.get("ticker")})
            if tks:
                return tks[:500]
        except Exception:
            pass
    # Dashboard tickers
    tj = BASE / "infra" / "prototype" / "tickers.json"
    if tj.exists():
        try:
            d = json.loads(tj.read_text())
            tks = sorted(d.keys()) if isinstance(d, dict) else []
            if tks:
                return tks[:500]
        except Exception:
            pass
    # Last resort: SP500
    try:
        import eodhd_client as ec
        return (ec.index_components("SP500") or [])[:500]
    except Exception:
        return []


def _fetch_gappers(tickers: list[str]) -> list[dict]:
    """Fetch real_time quotes for tickers and filter to gappers (|chg|>=3%)."""
    if not tickers:
        return []
    try:
        import eodhd_client as ec
        quotes = ec.real_time(tickers, cache_ttl=120)  # 2-min cache during pre-market
    except Exception as e:
        print(f"[premarket] real_time fetch failed: {e}", file=sys.stderr)
        return []
    if not isinstance(quotes, list):
        quotes = [quotes] if isinstance(quotes, dict) else []
    out = []
    for q in quotes:
        if not isinstance(q, dict):
            continue
        chg = q.get("change_p")
        prev = q.get("previousClose") or q.get("previous_close")
        cur = q.get("close")
        vol = q.get("volume") or 0
        if chg is None or abs(float(chg)) < 3.0:
            continue
        if vol < 1000:    # filter ultra-illiquid pre-market noise
            continue
        code = (q.get("code") or "").replace(".US", "")
        out.append({
            "ticker": code,
            "price": cur,
            "previous_close": prev,
            "change_p": float(chg),
            "volume": int(vol),
            "timestamp": q.get("timestamp"),
        })
    # Sort by absolute change descending
    out.sort(key=lambda r: -abs(r["change_p"]))
    return out


def _attribute_catalysts(gappers: list[dict]) -> dict:
    """Cross-reference gappers with recent news from cache/news.json (if available)
    and earnings_outcomes_30d for post-ER context. Returns {ticker: [catalysts]}.
    """
    catalysts: dict = {tk: [] for tk in [g["ticker"] for g in gappers]}
    # News mentions (last 24h)
    try:
        nj = BASE / "infra" / "prototype" / "data.json"
        if nj.exists():
            d = json.loads(nj.read_text())
            news = d.get("market_news") or []
            news_by_tk = {}
            cutoff_iso = (datetime.datetime.utcnow() - datetime.timedelta(hours=24)).isoformat()
            for n in news:
                dt = n.get("date") or ""
                if dt < cutoff_iso:
                    continue
                # Very simple mention detection: ticker in title
                title = (n.get("title") or "").upper()
                for tk in catalysts:
                    if tk in title.split() or ' ' + tk + ' ' in ' ' + title + ' ':
                        catalysts[tk].append({"type": "NEWS", "title": n.get("title", "")[:80]})
            # Earnings outcomes today
            outcomes = d.get("earnings_outcomes_30d") or []
            today = datetime.date.today().isoformat()
            yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
            for o in outcomes if isinstance(outcomes, list) else []:
                if not isinstance(o, dict):
                    continue
                rd = (o.get("report_date") or "")[:10]
                if rd not in (today, yesterday):
                    continue
                tk = o.get("ticker")
                if tk in catalysts:
                    surp = o.get("eps_surprise_pct")
                    catalysts[tk].append({
                        "type": "EARNINGS",
                        "title": f"EPS surprise {surp:+.1f}%" if surp is not None else "Earnings reported",
                    })
    except Exception:
        pass
    return catalysts


def main(argv: list[str]) -> int:
    in_session, now_et, reason = _is_premarket_session_now()
    payload = {
        "_meta": {
            "generated_at": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "now_et": now_et.isoformat(),
            "session_active": in_session,
            "session_status": reason,
            "source": "eodhd.real_time" if in_session else "session inactive",
        },
        "gappers_up": [],
        "gappers_dn": [],
        "catalysts": {},
    }
    if in_session:
        universe = _load_universe()
        print(f"[premarket] in session — universe size {len(universe)}", file=sys.stderr)
        gappers = _fetch_gappers(universe)
        payload["catalysts"] = _attribute_catalysts(gappers)
        payload["gappers_up"] = [g for g in gappers if g["change_p"] > 0][:30]
        payload["gappers_dn"] = [g for g in gappers if g["change_p"] < 0][:30]
        payload["_meta"]["n_gappers_up"] = len(payload["gappers_up"])
        payload["_meta"]["n_gappers_dn"] = len(payload["gappers_dn"])
    else:
        # Preserve last session's data if present
        if OUT.exists():
            try:
                prev = json.loads(OUT.read_text())
                payload["gappers_up"] = prev.get("gappers_up") or []
                payload["gappers_dn"] = prev.get("gappers_dn") or []
                payload["catalysts"] = prev.get("catalysts") or {}
                payload["_meta"]["last_session_at"] = (prev.get("_meta") or {}).get("generated_at")
                payload["_meta"]["last_session_status"] = (prev.get("_meta") or {}).get("session_status")
            except Exception:
                pass
        print(f"[premarket] out of session: {reason} — wrote stale-flag payload", file=sys.stderr)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2))
    print(f"[premarket] wrote {OUT} · session_active={in_session} · up={len(payload['gappers_up'])} dn={len(payload['gappers_dn'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

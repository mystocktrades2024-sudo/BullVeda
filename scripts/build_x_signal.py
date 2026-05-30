#!/usr/bin/env python3
"""
build_x_signal.py — free X (Twitter) signal aggregator via Nitter RSS.

No paid API. Polls each tracked handle's public timeline through a free
Nitter mirror, extracts $TICKER cashtags, classifies posts (original / reply
/ retweet), and aggregates into a per-ticker + per-handle structure.

Output: cache/x_signal.json + append to cache/x_signal_history.jsonl
Config: config/x_handles.json
"""
from __future__ import annotations
import argparse, html, json, re, sys, urllib.request, urllib.error
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from email.utils import parsedate_to_datetime

REPO = Path(__file__).resolve().parents[1]
CFG_PATH    = REPO / "config" / "x_handles.json"
BUNDLE_PATH = REPO / "cache" / "last_bundle.json"
OUT_PATH    = REPO / "cache" / "x_signal.json"
HIST_PATH   = REPO / "cache" / "x_signal_history.jsonl"

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"

_AMBIG = {"A","I","AI","BE","DD","GO","IT","NO","ON","OR","PE","SO","TO","UP","US","WE","BY"}
_STOP = {
    "ALL","AND","ARE","ATH","BUY","CEO","CFO","DAY","DJI","EOD","EPS","FOR","FROM","GDP","IMO",
    "INC","IPO","IRA","ITM","JOB","LOL","NEW","NOW","OTM","OUT","PCE","PUT","SEC","SELL","SP",
    "THE","TLDR","TOP","TWO","USA","WIN","WSB","YOLO","YOY","ETF","FOMO","FOMC","FED","CPI",
    "PPI","NFP","ATM","CALL","HOLD","MOON","BAN","ONE","RIP","JPM","HALT","GAIN","LOSS","BULL",
    "BEAR","LONG","RICH","BANK","DEAL","BIG","HOT","KEY","MAX","MIN","HAS","BEEN","WILL","INTO",
    "JUST","NEXT","OVER","FROM","SAID","SAYS","SOME","SUCH","THAN","THAT","THEM","THIS","WITH",
    "REAL","VERY","WHAT","WHEN","WHERE","WHO","WHY","HOW","WHICH","SAYS","SAID","SOON","STILL",
    "EVERY","AFTER","AGAIN","STOCK","STOCKS","TODAY","REPORT","REPORTS","LATEST","BREAKING",
    "MARKET","MARKETS","TRADE","TRADES","TRADING","DEAL","DEALS","PRICE","PRICES","CHIEF",
    "OFFICER","EXEC","BANK","BANKS","HOUSE","STATE","STATES","GROUP","ABOUT","BILL","BANNED"
}


def _http_get(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return 0, ""


def _fetch_handle(handle, mirrors, timeout):
    last_status = 0
    for m in mirrors:
        status, body = _http_get(f"https://{m}/{handle}/rss", timeout=timeout)
        last_status = status
        if status == 200 and "<item>" in body:
            return m, body, ""
    return "", "", f"all mirrors failed (last status {last_status})"


def _parse_rss(handle, body, universe):
    posts = []
    for raw in re.findall(r"<item>(.*?)</item>", body, re.S):
        t_match = re.search(r"<title>(.*?)</title>", raw, re.S)
        d_match = re.search(r"<pubDate>(.*?)</pubDate>", raw, re.S)
        l_match = re.search(r"<link>(.*?)</link>", raw, re.S)
        desc_match = re.search(r"<description>(.*?)</description>", raw, re.S)
        if not t_match: continue
        title = html.unescape(t_match.group(1) or "").strip()
        desc  = html.unescape(desc_match.group(1) or "").strip() if desc_match else ""
        desc  = re.sub(r"<[^>]+>", " ", desc)
        full  = (title + " " + desc).strip()
        link  = (l_match.group(1) if l_match else "").strip()
        pub   = (d_match.group(1) if d_match else "").strip()
        try:
            ts = parsedate_to_datetime(pub) if pub else None
            if ts and ts.tzinfo is None: ts = ts.replace(tzinfo=timezone.utc)
        except Exception:
            ts = None
        if title.startswith("RT by @"): kind = "retweet"
        elif title.startswith("R to @"): kind = "reply"
        else: kind = "original"
        # Ticker extraction — strict to avoid English-word false positives:
        #   1) Explicit $cashtag (1-5 chars): always accepted (intentional signal).
        #   2) Bare ALLCAPS fallback: length>=4 only — kills HAS/BE/ON/BY/AIR/IT
        #      news-headline words that happen to also be real tickers.
        cashtags = set(m.upper() for m in re.findall(r"\$([A-Za-z]{1,5})\b", full))
        allcaps  = set(re.findall(r"\b([A-Z]{4,5})\b", full)) - _STOP
        tickers  = set()
        for t in cashtags:
            if t in _AMBIG and t not in universe: continue
            if not universe or t in universe: tickers.add(t)
        for t in allcaps:
            if t in universe: tickers.add(t)
        if not tickers: continue
        posts.append({
            "handle": handle, "kind": kind,
            "ts": ts.isoformat() if ts else None,
            "title": title[:280], "link": link,
            "tickers": sorted(tickers),
        })
    return posts


def _load_universe():
    try:
        b = json.loads(BUNDLE_PATH.read_text())
    except Exception:
        return set()
    uni = set()
    for k in ("sp500_list", "russell1000_list", "russell2000_list"):
        for t in (b.get(k) or []):
            if isinstance(t, str): uni.add(t.upper())
    for x in (b.get("all_scored") or []):
        t = x.get("ticker") if isinstance(x, dict) else None
        if t: uni.add(t.upper())
    return uni


def aggregate(all_posts, now):
    by_ticker = defaultdict(lambda: {
        "mentions_24h": 0, "mentions_7d": 0, "mentions_30d": 0,
        "accounts": {}, "latest_ts": None, "latest_excerpt": "", "latest_handle": "",
    })
    by_handle = defaultdict(lambda: {
        "n_items": 0, "n_originals": 0, "n_replys": 0, "n_retweets": 0,
        "tickers": Counter(), "latest_ts": None,
    })
    recent = []
    cutoff_24h = now - timedelta(hours=24)
    cutoff_7d  = now - timedelta(days=7)
    cutoff_30d = now - timedelta(days=30)

    for p in all_posts:
        h = p["handle"]
        by_handle[h]["n_items"] += 1
        key = f'n_{p["kind"]}s' if p["kind"] != "original" else "n_originals"
        by_handle[h][key] = by_handle[h].get(key, 0) + 1
        ts = None
        try: ts = datetime.fromisoformat(p["ts"]) if p["ts"] else None
        except Exception: ts = None
        if ts and (by_handle[h]["latest_ts"] is None or ts.isoformat() > by_handle[h]["latest_ts"]):
            by_handle[h]["latest_ts"] = ts.isoformat()
        for t in p["tickers"]:
            by_handle[h]["tickers"][t] += 1
            bt = by_ticker[t]
            if ts:
                if ts > cutoff_30d: bt["mentions_30d"] += 1
                if ts > cutoff_7d:  bt["mentions_7d"]  += 1
                if ts > cutoff_24h: bt["mentions_24h"] += 1
                if not bt["latest_ts"] or ts.isoformat() > bt["latest_ts"]:
                    bt["latest_ts"] = ts.isoformat()
                    bt["latest_excerpt"] = p["title"][:200]
                    bt["latest_handle"]  = h
            acct = bt["accounts"].setdefault(h, {"n_posts": 0, "latest_ts": None, "latest_excerpt": ""})
            acct["n_posts"] += 1
            if ts and (acct["latest_ts"] is None or ts.isoformat() > acct["latest_ts"]):
                acct["latest_ts"] = ts.isoformat()
                acct["latest_excerpt"] = p["title"][:200]
            if ts and ts > cutoff_7d:
                recent.append({
                    "ts": ts.isoformat(), "handle": h, "ticker": t,
                    "tickers": p["tickers"], "kind": p["kind"],
                    "title": p["title"][:200], "link": p["link"],
                })

    for h in by_handle:
        by_handle[h]["tickers"] = dict(by_handle[h]["tickers"].most_common(20))
    for t, bt in by_ticker.items():
        bt["accounts"] = dict(sorted(bt["accounts"].items(), key=lambda kv: -kv[1]["n_posts"]))
        bt["n_unique_handles"] = len(bt["accounts"])
    recent.sort(key=lambda r: r["ts"], reverse=True)
    return {"by_ticker": dict(by_ticker), "by_handle": dict(by_handle), "recent_posts": recent[:200]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--handles", help="comma-list to override config")
    args = ap.parse_args()

    if not CFG_PATH.exists():
        print(f"ERROR: config not found at {CFG_PATH}", file=sys.stderr); sys.exit(1)
    cfg = json.loads(CFG_PATH.read_text())
    if not cfg.get("enabled", True):
        print("disabled in config (enabled=false); exiting"); sys.exit(0)

    mirrors = cfg.get("nitter_mirrors") or ["nitter.net"]
    timeout = int(cfg.get("request_timeout_sec", 12))
    handles_cfg = cfg.get("handles") or []
    if args.handles:
        keep = set(h.strip() for h in args.handles.split(","))
        handles_cfg = [h for h in handles_cfg if h["handle"] in keep]

    universe = _load_universe()
    now = datetime.now(timezone.utc)
    print(f"polling {len(handles_cfg)} handles · universe={len(universe)} tickers · mirrors={mirrors}")

    all_posts = []
    handles_failed = []
    handles_polled = 0
    for h in handles_cfg:
        handle = h["handle"]
        mirror, body, err = _fetch_handle(handle, mirrors, timeout)
        if err:
            handles_failed.append({"handle": handle, "error": err})
            print(f"  X {handle}: {err}")
            continue
        posts = _parse_rss(handle, body, universe)
        all_posts.extend(posts)
        handles_polled += 1
        print(f"  ok {handle:<20} via {mirror:<14} {len(posts)} ticker-tagged posts")

    agg = aggregate(all_posts, now)
    top = sorted(agg["by_ticker"].items(), key=lambda kv: -kv[1]["mentions_7d"])[:30]
    top_24h = sorted(agg["by_ticker"].items(), key=lambda kv: -kv[1]["mentions_24h"])[:15]

    out = {
        "_meta": {
            "generated_at": now.isoformat(),
            "handles_total": len(cfg.get("handles", [])),
            "handles_polled": handles_polled,
            "handles_failed": handles_failed,
            "mirror_primary": mirrors[0],
            "universe_size": len(universe),
            "total_ticker_tagged_posts": len(all_posts),
            "unique_tickers": len(agg["by_ticker"]),
        },
        "config": {
            "handles": [{"handle": h["handle"], "category": h.get("category"),
                         "weight": h.get("weight", 1.0), "label": h.get("label", h["handle"])}
                        for h in cfg.get("handles", [])],
            "categories": cfg.get("categories", {}),
        },
        "top_tickers_7d":  [{"ticker": t, **v} for t, v in top],
        "top_tickers_24h": [{"ticker": t, **v} for t, v in top_24h],
        "by_ticker":   agg["by_ticker"],
        "by_handle":   agg["by_handle"],
        "recent_posts": agg["recent_posts"],
    }

    if args.dry_run:
        print(f"\n=== DRY RUN — {len(agg['by_ticker'])} tickers, top 10 by 7d mentions ===")
        for t, v in top[:10]:
            print(f"  {t:<6} 24h={v['mentions_24h']:>2} 7d={v['mentions_7d']:>2} "
                  f"hndl={v['n_unique_handles']:>2}  latest @{v['latest_handle']}: {v['latest_excerpt'][:80]}")
        return

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2))
    print(f"\nok wrote {OUT_PATH} ({OUT_PATH.stat().st_size//1024} KB)")

    HIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(HIST_PATH, "a") as f:
        snap = now.isoformat()
        for t, v in agg["by_ticker"].items():
            f.write(json.dumps({"snap_ts": snap, "ticker": t,
                                "mentions_24h": v["mentions_24h"],
                                "mentions_7d":  v["mentions_7d"],
                                "n_handles":    v["n_unique_handles"],
                                "latest_handle": v["latest_handle"]}) + "\n")
    print(f"ok appended {len(agg['by_ticker'])} history rows -> {HIST_PATH.name}")


if __name__ == "__main__":
    main()

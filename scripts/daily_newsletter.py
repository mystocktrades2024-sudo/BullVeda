#!/usr/bin/env python3
"""
daily_newsletter.py — daily Kairos newsletter.

5 sections (top 5 each):
  · 🎯 High Conviction   (T1/T2 conviction picks from latest scan)
  · 🚀 Momentum          (momentum_snapshots top-rank)
  · 🤖 ML Edge           (predictions.swing by edge magnitude)
  · 📊 Screener          (BUY candidates by score)
  · 📈 Options Flow      (STRONG status by total premium)

For every unique ticker: 1 recent EODHD news headline (≤ 24h).
Tickers appearing in 2+ sections get a 🌟 cross-tag.

Delivery:
  · Saved as HTML snapshot kind='daily-newsletter'
    → served at /reports/latest/daily-newsletter
  · Slack summary post (condensed)
  · (email TBD — wire when SMTP creds set in .env)

Usage:
  python3 scripts/daily_newsletter.py              # write + Slack
  python3 scripts/daily_newsletter.py --no-slack   # write only
  python3 scripts/daily_newsletter.py --dry-run    # render to stdout
"""
from __future__ import annotations
import argparse, hashlib, html, json, os, sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

BUNDLE_PATH   = REPO / "cache" / "last_bundle.json"
ML_PATH       = REPO / "cache" / "ml_edge_predictions.json"
OPTIONS_PATH  = REPO / "infra" / "prototype" / "options_flow.json"
MOMENTUM_PATH = REPO / "data" / "momentum_snapshots.jsonl"
STATE_PATH    = REPO / "data" / "daily_newsletter_state.json"
DASHBOARD     = "https://trade.mystockholding.com"


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────
def _webhook() -> str | None:
    env = REPO / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("SLACK_WEBHOOK_URL="):
                return line.split("=", 1)[1].strip()
    return os.environ.get("SLACK_WEBHOOK_URL")


def _slack(webhook: str, payload: dict) -> bool:
    try:
        import requests
        return requests.post(webhook, json=payload, timeout=8).status_code == 200
    except Exception as e:
        print(f"slack post failed: {e}", file=sys.stderr); return False


def _safe_load(p: Path):
    try: return json.loads(p.read_text()) if p.exists() else None
    except Exception: return None


def _today() -> str: return datetime.now().strftime("%Y-%m-%d")


# ────────────────────────────────────────────────────────────────────────────
# 5 data sources → top 5 each
# ────────────────────────────────────────────────────────────────────────────
def _bundle() -> dict:
    return _safe_load(BUNDLE_PATH) or {}


def _high_conviction(b: dict, n=5) -> list:
    """T1/T2 conviction picks. Fallback to top BUYs by score."""
    buys = b.get("buy_candidates") or []
    t12 = [p for p in buys if p.get("conviction_tier") in ("T1", "T2")]
    if not t12:
        t12 = buys[:]
    t12.sort(key=lambda r: (
        0 if r.get("conviction_tier") == "T1" else 1 if r.get("conviction_tier") == "T2" else 2,
        -(r.get("score") or 0)
    ))
    return t12[:n]


def _screener_top(b: dict, n=5) -> list:
    buys = b.get("buy_candidates") or []
    return sorted(buys, key=lambda r: -(r.get("score") or 0))[:n]


def _momentum_top(n=5) -> list:
    if not MOMENTUM_PATH.exists(): return []
    today = _today()
    rows = []
    for line in MOMENTUM_PATH.read_text().splitlines():
        if not line.strip(): continue
        try: r = json.loads(line)
        except Exception: continue
        if r.get("date") == today and r.get("rank") and r.get("rank") <= n:
            rows.append(r)
    rows.sort(key=lambda r: r.get("rank") or 99)
    return rows[:n]


def _ml_edge_top(n=5) -> list:
    d = _safe_load(ML_PATH) or {}
    swing = (d.get("predictions") or {}).get("swing") or {}
    rows = []
    for tk, v in swing.items():
        if not isinstance(v, dict): continue
        verdict = v.get("verdict") if "verdict" in v else (v.get("A") or {}).get("verdict")
        if not isinstance(verdict, dict): continue
        edge = verdict.get("edge")
        if edge is None: continue
        rows.append({
            "ticker": tk,
            "edge":   edge,
            "verdict": verdict.get("text", "—"),
            "level":  verdict.get("level", "—"),
            "conf":   verdict.get("confidence", "—"),
        })
    rows.sort(key=lambda r: -(r["edge"] or 0))
    return rows[:n]


def _options_top(n=5) -> list:
    d = _safe_load(OPTIONS_PATH) or {}
    top = d.get("top30") or []
    rank = {"STRONG": 3, "SOLID": 2, "BUILDING": 1}
    top = sorted(top, key=lambda r: (-rank.get(r.get("status",""), 0),
                                      -(r.get("premium_total_$") or 0)))
    return top[:n]


# ────────────────────────────────────────────────────────────────────────────
# News fetch via EODHD
# ────────────────────────────────────────────────────────────────────────────
def _fetch_news(tickers: list, max_age_hours: int = 30) -> dict:
    """Returns {ticker: [{title, link, published}, ...]} (top 1-2 per ticker)."""
    if not tickers: return {}
    try:
        import data_fetcher as df
    except Exception as e:
        print(f"news fetch unavailable: {e}", file=sys.stderr)
        return {}
    cutoff = datetime.now() - timedelta(hours=max_age_hours)
    out = {}
    for tk in tickers:
        try:
            articles = df.get_news_articles(tk, limit=3) or []
        except Exception:
            articles = []
        keep = []
        for a in articles:
            if not isinstance(a, dict): continue
            t = a.get("title") or a.get("headline")
            if not t: continue
            pub = a.get("date") or a.get("published") or a.get("published_at") or ""
            # Best-effort recency filter — drop if obvious old
            keep.append({
                "title": t,
                "link":  a.get("url") or a.get("link") or "",
                "published": pub,
                "sentiment": a.get("sentiment") or a.get("polarity"),
            })
            if len(keep) >= 2: break
        if keep:
            out[tk] = keep
    return out


# ────────────────────────────────────────────────────────────────────────────
# HTML render
# ────────────────────────────────────────────────────────────────────────────
def _data_json() -> dict:
    """Read the dashboard's data.json which has richer sector/macro shapes."""
    p = REPO / "infra" / "prototype" / "data.json"
    try: return json.loads(p.read_text())
    except Exception: return {}


def _esc(s) -> str:
    return html.escape(str(s)) if s is not None else "—"


def _pct_color(v):
    try: v = float(v)
    except Exception: return "#9ba7c2"
    if v >= 2:    return "#5be57c"
    if v >= 0.5:  return "#9be78e"
    if v >= -0.5: return "#9ba7c2"
    if v >= -2:   return "#ff9c7a"
    return "#ff6b6b"


def _market_snapshot_html(b: dict, dj: dict) -> str:
    r  = b.get("regime") or {}
    ms = b.get("macro_signals") or {}
    mb = dj.get("market_breadth") or {}
    vix = r.get("vix") or {}
    spy = r.get("spy_price")
    qqq = r.get("qqq_price")
    spy_chg = r.get("spy_daily_chg")
    vix_now = vix.get("vix_current")
    ts_ratio = vix.get("term_structure_ratio")
    vix_label = vix.get("vol_state","—")
    breadth = mb.get("pct_above_50d")
    breadth_lbl = mb.get("label_50","—")
    risk_signal = ms.get("risk_signal","—")

    def big(value, label, color="#fff", small=None):
        return (
            f'<div class="hero-cell">'
            f'  <div class="hc-v" style="color:{color}">{value}</div>'
            f'  <div class="hc-l">{label}</div>'
            + (f'  <div class="hc-s">{small}</div>' if small else "") +
            f'</div>'
        )

    def chg(v):
        if v is None: return "—"
        try: v = float(v)
        except Exception: return str(v)
        return f"{v:+.2f}%"

    macro_cells = []
    macro_cells.append(big(f"${spy:.2f}" if spy else "—", "SPY",
                           color=_pct_color(spy_chg), small=chg(spy_chg)))
    macro_cells.append(big(f"${qqq:.2f}" if qqq else "—", "QQQ", color="#fff"))
    vix_color = "#5be57c" if (vix_now or 0) < 16 else "#ffb95c" if (vix_now or 0) < 25 else "#ff6b6b"
    macro_cells.append(big(f"{vix_now:.1f}" if vix_now else "—", "VIX",
                           color=vix_color, small=vix_label))
    macro_cells.append(big(f"{ts_ratio:.2f}" if ts_ratio else "—", "VIX TERM",
                           small="contango" if (ts_ratio or 1) < 1 else "backwardation"))
    macro_cells.append(big(f"{breadth:.0f}%" if breadth else "—", "BREADTH 50D",
                           color=_pct_color((breadth or 0) - 50), small=breadth_lbl))
    dxy = (ms.get("dxy") or {}).get("price")
    macro_cells.append(big(f"{dxy:.2f}" if dxy else "—", "DXY",
                           small=(ms.get("dxy") or {}).get("trend","—")))
    gld = (ms.get("gld") or {}).get("price")
    macro_cells.append(big(f"${gld:.0f}" if gld else "—", "GOLD",
                           small=(ms.get("gld") or {}).get("trend","—")))
    pc = (ms.get("put_call") or {}).get("equity_pc")
    pc_sig = (ms.get("put_call") or {}).get("signal","—")
    pc_color = "#ff6b6b" if pc_sig == "fear" else "#5be57c" if pc_sig == "greed" else "#9ba7c2"
    macro_cells.append(big(f"{pc:.2f}" if pc else "—", "PUT/CALL",
                           color=pc_color, small=pc_sig))

    rs_color = ("#5be57c" if risk_signal == "risk-on"
                else "#ff6b6b" if risk_signal == "risk-off" else "#ffb95c")
    risk_banner = (
        f'<div class="risk-banner" style="background:{rs_color}14;border-left:3px solid {rs_color}">'
        f'  <span class="rb-l">REGIME</span> <b>{_esc(r.get("regime4","—"))}</b>'
        f'  <span class="rb-l">RISK</span> <b style="color:{rs_color};text-transform:uppercase">{_esc(risk_signal)}</b>'
        f'  <span class="rb-l">CYCLE</span> <b>{_esc(r.get("market_cycle","—"))}</b>'
        f'  <span class="rb-l">CREDIT</span> <b>{_esc(r.get("credit_state","—"))}</b>'
        f'  <span class="rb-l">DIST DAYS</span> <b>{_esc(r.get("distribution_days","—"))}</b>'
        f'</div>'
    )

    return f"""
    <section class="card snapshot">
      <div class="card-h"><span class="ic">📊</span><span class="ttl">Market Snapshot</span>
        <span class="card-meta">{_esc(datetime.now().strftime("%a %b %-d · %-I:%M %p PT"))}</span></div>
      <div class="hero-grid">{"".join(macro_cells)}</div>
      {risk_banner}
    </section>"""


def _sector_heatmap_html(dj: dict) -> str:
    sectors = dj.get("sector_etf") or {}
    if not sectors: return ""
    # Build rows with 1d (use vs_spy_pct as proxy if no 1d), perf_pct (often YTD), outperformer flag
    rows = []
    for tk, s in sectors.items():
        perf = s.get("perf_pct")
        vs_spy = s.get("vs_spy_pct")
        out = s.get("outperforming")
        rank = s.get("rank")
        sector = s.get("sector", tk)
        rows.append((rank or 99, tk, sector, perf, vs_spy, out))
    rows.sort()
    cells = []
    for rank, tk, sector, perf, vs_spy, out in rows[:11]:
        color = _pct_color(perf)
        cells.append(
            f'<div class="sh-cell">'
            f'  <div class="sh-tk">{_esc(tk)}</div>'
            f'  <div class="sh-sec">{_esc(sector)}</div>'
            f'  <div class="sh-perf" style="color:{color}">{("+" if (perf or 0) >= 0 else "")}{(perf or 0):.1f}%</div>'
            f'  <div class="sh-vs">vs SPY {("+" if (vs_spy or 0) >= 0 else "")}{(vs_spy or 0):.1f}%</div>'
            f'  <div class="sh-bar"><span class="sh-fill" style="background:{color};width:{min(100, abs((perf or 0))*3):.0f}%"></span></div>'
            f'</div>'
        )
    return f"""
    <section class="card">
      <div class="card-h"><span class="ic">🗺</span><span class="ttl">Sector Heatmap</span>
        <span class="card-meta">11 sectors · % return (lookback)</span></div>
      <div class="sh-grid">{"".join(cells)}</div>
    </section>"""


def _system_status_html(b: dict) -> str:
    r = b.get("regime") or {}
    sharpe = _safe_load(REPO / "cache" / "sharpe_kill_state.json") or {}
    drift  = _safe_load(REPO / "cache" / "drift_report.json") or {}
    wf     = _safe_load(REPO / "cache" / "walk_forward_v2_results.json") or {}

    sharpe_active = bool(sharpe.get("active"))
    sharpe_label = "🛑 KILL ACTIVE" if sharpe_active else "✅ Healthy"
    sharpe_color = "#ff6b6b" if sharpe_active else "#5be57c"
    sharpe_detail = (f'Sharpe {sharpe.get("sharpe"):.2f}'
                     if sharpe.get("sharpe") is not None else
                     f'n={sharpe.get("n","—")}')

    drift_comp = drift.get("compliance") or {}
    def chk(p): return "✅" if p else "⚠️"
    drift_lines = []
    for k in ("wr","rr","volume"):
        c = drift_comp.get(k) or {}
        actual = c.get("actual")
        if actual is not None:
            drift_lines.append(f'{chk(c.get("pass"))} {k.upper()} {actual:.2f}')

    wf_label = (f"{wf.get('total_trades',0)} trades · WR {(wf.get('aggregate_wr',0)*100):.0f}% · "
                f"Sharpe {wf.get('mean_sharpe',0):.2f}") if wf else "no run yet"

    sleeves = [
        ("Pullback (core)", "ON"),
        ("Momentum",        "ON"),
        ("Defensive Rot.",  "ON"),
        ("Mean Reversion",  "ON"),
        ("PEAD",            "ON"),
        ("Insider Cluster", "ON"),
        ("ESP Play",        "ON"),
    ]
    sleeve_chips = "".join(
        f'<span class="sleeve-chip">{_esc(name)} <span style="color:#5be57c">●</span></span>'
        for name, _st in sleeves
    )

    return f"""
    <section class="card">
      <div class="card-h"><span class="ic">🚦</span><span class="ttl">System Status</span></div>
      <div class="ss-grid">
        <div class="ss-cell"><div class="ss-lbl">REGIME</div><div class="ss-val">{_esc(r.get("regime4","—"))}</div></div>
        <div class="ss-cell"><div class="ss-lbl">VIX</div><div class="ss-val">{(r.get("vix") or {}).get("vix_current","—")}</div></div>
        <div class="ss-cell"><div class="ss-lbl">SHARPE GATE</div>
          <div class="ss-val" style="color:{sharpe_color}">{sharpe_label}</div>
          <div class="ss-sub">{_esc(sharpe_detail)}</div></div>
        <div class="ss-cell"><div class="ss-lbl">DRIFT</div>
          <div class="ss-val" style="font:600 11px var(--mono)">{" · ".join(drift_lines) or "—"}</div></div>
        <div class="ss-cell"><div class="ss-lbl">WALK-FWD</div>
          <div class="ss-val" style="font:600 11px var(--mono)">{_esc(wf_label)}</div></div>
        <div class="ss-cell"><div class="ss-lbl">SLEEVES</div>
          <div class="ss-val">{sleeve_chips}</div></div>
      </div>
    </section>"""


def _market_temperature(b: dict, dj: dict) -> tuple[float, str, str, dict]:
    """Compute 0-100 market temperature from VIX/breadth/regime/put-call/term/credit.
    Higher = hotter (risk-on). Returns (score, label, color, components)."""
    r  = b.get("regime") or {}
    ms = b.get("macro_signals") or {}
    mb = dj.get("market_breadth") or {}
    vix_now = (r.get("vix") or {}).get("vix_current") or 18
    ts_ratio = (r.get("vix") or {}).get("term_structure_ratio") or 1.0
    breadth = mb.get("pct_above_50d") or 50
    pc      = (ms.get("put_call") or {}).get("equity_pc") or 0.7
    credit  = (r.get("credit_state") or "—").lower()
    regime  = (r.get("regime4") or "").lower()

    # Component scores 0-100 (higher = warmer / risk-on)
    # VIX: <14 = 100, 14-18 = 80, 18-22 = 50, 22-28 = 20, >28 = 0
    if   vix_now < 14: vix_s = 100
    elif vix_now < 18: vix_s = 80
    elif vix_now < 22: vix_s = 50
    elif vix_now < 28: vix_s = 20
    else:              vix_s = 0
    # Breadth: linear 0-100% mapped to 0-100
    breadth_s = max(0, min(100, breadth))
    # Put/call: <0.6 = greedy/hot (100), 0.6-0.8 = 60, 0.8-1.0 = 30, >1.0 = fearful/cold (0)
    if   pc < 0.6:  pc_s = 90
    elif pc < 0.8:  pc_s = 60
    elif pc < 1.0:  pc_s = 30
    else:           pc_s = 5
    # Term structure: contango (<1) = healthy = 80; backwardation (>1) = stress = 20
    term_s = 80 if ts_ratio < 0.95 else 50 if ts_ratio < 1.0 else 20
    # Credit: healthy=80, stretched=50, distressed=10
    cred_s = 80 if "healthy" in credit else 50 if "stretched" in credit else 10
    # Regime: trending=85, choppy=55, risk_off=20, panic=0
    if   "risk_on_trending" in regime: reg_s = 85
    elif "risk_on_choppy"   in regime: reg_s = 55
    elif "risk_off"         in regime: reg_s = 20
    elif "panic"            in regime: reg_s = 0
    else:                              reg_s = 50

    components = {
        "VIX": (vix_s, f"{vix_now:.1f}"),
        "Breadth %>50d": (breadth_s, f"{breadth:.0f}%"),
        "Put/Call": (pc_s, f"{pc:.2f}"),
        "VIX Term": (term_s, f"{ts_ratio:.2f}"),
        "Credit": (cred_s, credit),
        "Regime": (reg_s, regime),
    }
    # Weighted average — VIX + Breadth + Regime get more weight
    weights = {"VIX": 2.5, "Breadth %>50d": 2.0, "Regime": 2.0,
               "Put/Call": 1.0, "VIX Term": 1.0, "Credit": 1.5}
    num = sum(components[k][0] * weights[k] for k in components)
    den = sum(weights.values())
    score = num / den

    # Label + color
    if   score >= 80: label, color, icon = "EUPHORIC",  "#ff6b6b", "🔥"
    elif score >= 65: label, color, icon = "HOT",       "#ffb95c", "☀️"
    elif score >= 50: label, color, icon = "WARM",      "#5be57c", "🌤"
    elif score >= 35: label, color, icon = "COOL",      "#62b3ff", "❄️"
    elif score >= 20: label, color, icon = "COLD",      "#b48cff", "🧊"
    else:             label, color, icon = "FROZEN",    "#ff6b6b", "🧨"
    return score, f"{icon} {label}", color, components


def _market_temperature_html(b: dict, dj: dict) -> str:
    score, label, color, components = _market_temperature(b, dj)
    # Build SVG arc gauge — semicircle from -90° to 90°
    # Score 0-100 → angle -90° to 90°
    import math
    angle_deg = -90 + (score / 100) * 180
    angle_rad = math.radians(angle_deg - 90)  # offset because 0° is right
    cx, cy, r = 110, 110, 90
    needle_x = cx + r * math.cos(angle_rad)
    needle_y = cy + r * math.sin(angle_rad)
    # Arc paths for color segments
    def arc(start_pct, end_pct, color_):
        a1 = math.radians(-180 + (start_pct/100)*180)
        a2 = math.radians(-180 + (end_pct/100)*180)
        x1 = cx + r * math.cos(a1); y1 = cy + r * math.sin(a1)
        x2 = cx + r * math.cos(a2); y2 = cy + r * math.sin(a2)
        large = 1 if (end_pct - start_pct) > 50 else 0
        return f'<path d="M {x1:.1f} {y1:.1f} A {r} {r} 0 {large} 1 {x2:.1f} {y2:.1f}" fill="none" stroke="{color_}" stroke-width="22" />'

    gauge_svg = f"""
    <svg width="220" height="140" viewBox="0 0 220 140" style="display:block">
      <!-- Background track -->
      {arc(0, 20, '#ff6b6b')}
      {arc(20, 35, '#b48cff')}
      {arc(35, 50, '#62b3ff')}
      {arc(50, 65, '#5be57c')}
      {arc(65, 80, '#ffb95c')}
      {arc(80, 100, '#ff6b6b')}
      <!-- Needle -->
      <line x1="{cx}" y1="{cy}" x2="{needle_x:.1f}" y2="{needle_y:.1f}" stroke="#fff" stroke-width="3" stroke-linecap="round"/>
      <circle cx="{cx}" cy="{cy}" r="6" fill="#fff"/>
      <!-- Number -->
      <text x="{cx}" y="{cy+30}" text-anchor="middle" fill="{color}" font-family="JetBrains Mono, monospace" font-weight="800" font-size="28">{score:.0f}</text>
      <text x="{cx}" y="{cy+48}" text-anchor="middle" fill="#8b9bbf" font-family="JetBrains Mono, monospace" font-weight="700" font-size="10" letter-spacing="2">/ 100</text>
    </svg>
    """

    # Components breakdown
    comp_rows = "\n".join(
        f'<div class="comp-row">'
        f'  <div class="comp-name">{_esc(k)}</div>'
        f'  <div class="comp-bar"><div class="comp-fill" style="width:{v[0]:.0f}%;background:{_pct_color(v[0]-50)}"></div></div>'
        f'  <div class="comp-val">{v[0]:.0f}</div>'
        f'  <div class="comp-raw">{_esc(v[1])}</div>'
        f'</div>'
        for k, v in components.items()
    )

    return f"""
    <section class="card">
      <div class="card-h"><span class="ic">🌡</span><span class="ttl">Market Temperature</span>
        <span class="card-meta">Composite risk-on/off score · 6 components</span></div>
      <div class="temp-wrap">
        <div class="temp-gauge">{gauge_svg}
          <div class="temp-label" style="color:{color}">{_esc(label)}</div>
        </div>
        <div class="temp-comps">{comp_rows}</div>
      </div>
    </section>"""


def _market_moving_news_html() -> str:
    """Filter universe news to high-impact / market-moving stories only."""
    try:
        import data_fetcher as df
        all_news = df.get_finviz_news() or []
    except Exception:
        return ""
    # High-impact keywords + reputable sources
    KEYWORDS = [
        "fed", "fomc", "powell", "rate", "rates", "inflation", "cpi", "ppi",
        "gdp", "jobs", "unemployment", "payroll", "earnings beat", "earnings miss",
        "guidance", "raises guidance", "cuts guidance", "downgrade", "upgrade",
        "tariff", "china", "war", "sanction", "iran", "russia",
        "oil", "crude", "opec", "supply", "shutdown", "default",
        "merger", "acquisition", "buyout", "ipo", "bankruptcy", "delisting",
        "fda", "approval", "rejection", "recall",
        "sec", "doj", "lawsuit", "settlement", "investigation",
        "ai", "chip", "nvidia", "apple", "tesla", "microsoft", "amazon", "google", "meta",
        "treasury", "yield", "bond", "credit",
        "vix", "sell-off", "selloff", "rally", "crash", "correction",
    ]
    REPUTABLE = {"reuters","bloomberg","wsj","cnbc","financial times","ft","ap","barron","seeking alpha","yahoo finance","marketwatch","bbc"}

    scored = []
    for n in all_news:
        title = (n.get("title") or "").lower()
        src   = (n.get("source") or "").lower()
        kw_hits = sum(1 for kw in KEYWORDS if kw in title)
        rep_hit = 1 if any(r in src for r in REPUTABLE) else 0
        if kw_hits == 0: continue
        # Score: keyword matches × reputability bonus
        impact_score = kw_hits * 2 + rep_hit
        scored.append((impact_score, n))
    scored.sort(key=lambda x: -x[0])
    top = [n for _, n in scored[:10]]

    if not top: return ""

    rows = []
    for n in top:
        title = _esc(n.get("title",""))[:200]
        url   = _esc(n.get("url",""))
        source = _esc(n.get("source",""))
        date_  = _esc(n.get("date",""))[:16]
        # Detect tone
        t_lower = (n.get("title") or "").lower()
        tone_color = "#ffb95c"
        tone_icon = "📣"
        if any(w in t_lower for w in ["rally","beat","raises","upgrade","gains","surges","approves"]):
            tone_color = "#5be57c"; tone_icon = "🟢"
        elif any(w in t_lower for w in ["sell-off","selloff","crash","miss","cuts","downgrade","plunges","tumbles","sinks","fall"]):
            tone_color = "#ff6b6b"; tone_icon = "🔴"
        elif any(w in t_lower for w in ["fed","fomc","inflation","tariff","war","iran"]):
            tone_color = "#b48cff"; tone_icon = "🌀"
        rows.append(
            f'<div class="mmn-row" style="border-left:3px solid {tone_color}">'
            f'  <span class="mmn-icon">{tone_icon}</span>'
            f'  <a href="{url}" target="_blank" class="mmn-title">{title}</a>'
            f'  <div class="mmn-meta">{source} · {date_}</div>'
            f'</div>'
        )
    return f"""
    <section class="card">
      <div class="card-h"><span class="ic">🚨</span><span class="ttl">Top News Shaking the Market</span>
        <span class="card-meta">High-impact + reputable-source filter · {len(top)} stories</span></div>
      <div class="mmn-wrap">{"".join(rows)}</div>
    </section>"""


def _multi_signal_spotlight(sections: dict, news: dict) -> str:
    """Tickers appearing in 2+ sections — the strongest cross-signal names."""
    cross_tags_map = _cross_tags(sections)
    if not cross_tags_map: return ""

    # Aggregate all info per multi-signal ticker
    cards = []
    for tk, signals in sorted(cross_tags_map.items(),
                              key=lambda kv: -len(kv[1])):
        # Find the most detailed record for this ticker
        rec = None
        rec_section = None
        for s in ("High Conviction", "Screener", "Momentum", "ML Edge", "Options Flow"):
            for p in sections.get(s, []):
                if p.get("ticker") == tk:
                    if rec is None:
                        rec, rec_section = p, s
                    # Prefer richer records (HC > Screener > others)
                    elif s in ("High Conviction","Screener"):
                        rec, rec_section = p, s
                    break
        if rec is None: continue

        # Collect signal data from each section the ticker appears in
        signal_lines = []
        for s in signals:
            for p in sections.get(s, []):
                if p.get("ticker") != tk: continue
                if s == "High Conviction":
                    signal_lines.append(f'🎯 *HC* score *{p.get("score",0):.0f}* · tier {p.get("conviction_tier","—")}')
                elif s == "Screener":
                    signal_lines.append(f'📊 *Screener* score *{p.get("score",0):.0f}* · RS {p.get("rs_rank_63d", p.get("rs_rank","—"))}')
                elif s == "Momentum":
                    signal_lines.append(f'🚀 *Momentum* comp *{p.get("composite",0):.0f}* · Sharpe {p.get("sharpe_126d",0):.2f}')
                elif s == "ML Edge":
                    signal_lines.append(f'🤖 *ML Edge* {p.get("edge",0):+.1f} · {p.get("verdict","—")}/{p.get("level","—")}')
                elif s == "Options Flow":
                    signal_lines.append(f'📈 *Options* {p.get("status","—")} · PCR {(p.get("put_call_ratio") or 0):.2f} · {_fmt_money(p.get("premium_total_$"))}')
                break

        # Pull news (top 2)
        news_items = news.get(tk, [])[:2]
        news_html = ""
        if news_items:
            news_html = "\n".join(
                f'<div class="news-row">📰 <a href="{_esc(n.get("link",""))}" target="_blank">{_esc(n.get("title",""))[:140]}</a></div>'
                for n in news_items
            )

        spark = _sparkline_svg(_ohlcv_closes(rec.get("ohlcv")), width=140, height=36)
        tp = rec.get("trade_plan") or {}
        sector = _sector_chip(rec.get("sector"))
        signal_count = len(signals)

        cards.append(f"""
        <div class="mss-card">
          <div class="mss-h">
            <div class="mss-l">
              <span class="mss-tk">{_esc(tk)}</span>
              <span class="mss-px">{_fmt_px(rec.get('price'))}</span>
              {spark}
            </div>
            <div class="mss-r">
              <span class="mss-count" title="appears in {signal_count} categories">🌟 {signal_count} signals</span>
              {sector}
            </div>
          </div>
          <div class="mss-signals">{"<br>".join(signal_lines)}</div>
          {f'<div class="mss-plan"><span class="lbl">Setup:</span> <b>{_esc(rec.get("setup_family",""))}</b>  ·  <span class="lbl">Entry:</span> <b>{_esc(tp.get("entry_zone","—"))}</b>  ·  <span class="lbl">Stop:</span> <b style="color:#ff6b6b">{_fmt_px(tp.get("stop"))}</b>  ·  <span class="lbl">T1:</span> <b style="color:#5be57c">{_fmt_px(tp.get("target1"))}</b></div>' if tp else ''}
          {news_html}
        </div>
        """)

    if not cards: return ""
    return f"""
    <section class="card">
      <div class="card-h"><span class="ic">🌟</span><span class="ttl">Multi-Signal Spotlight</span>
        <span class="card-meta">Tickers in 2+ categories · highest-confidence names</span></div>
      <div class="mss-grid">{"".join(cards)}</div>
    </section>"""


def _yesterdays_audit_html() -> str:
    """D1 outcomes of picks from 1-2 trading days ago."""
    led = _safe_load(REPO / "cache" / "audit_ledger.json") or {}
    recs = led.get("records") or []
    from datetime import timedelta
    yest = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    yest2 = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
    rows = [r for r in recs if r.get("pick_date") in (yest, yest2)
            and r.get("verdict") in ("BUY","WATCH")]
    rows.sort(key=lambda r: -(r.get("score") or 0))
    rows = rows[:12]
    if not rows:
        return ""
    cells = []
    for r in rows:
        tk = r.get("ticker","—")
        d0 = r.get("d0")
        d1 = r.get("d1")
        d1_color = _pct_color(d1)
        status = r.get("signal_status","—")
        pnl = r.get("signal_pnl_pct")
        pnl_color = _pct_color(pnl)
        outcome = r.get("outcome") or "—"
        outcome_color = "#5be57c" if outcome == "WIN" else "#ff6b6b" if outcome == "LOSS" else "#9ba7c2"
        mae = r.get("mae_pct")
        mfe = r.get("mfe_pct")
        cells.append(f"""
          <tr>
            <td><b>{_esc(tk)}</b></td>
            <td>{_esc(r.get("verdict","—"))}</td>
            <td class="r">{r.get("score","—")}</td>
            <td class="r" style="color:{_pct_color(d0)}">{(d0 or 0):+.2f}%</td>
            <td class="r" style="color:{d1_color}">{(d1 or 0):+.2f}%</td>
            <td class="r" style="color:#ff6b6b">{(mae or 0):.2f}%</td>
            <td class="r" style="color:#5be57c">{(mfe or 0):.2f}%</td>
            <td style="color:{pnl_color}">{(pnl or 0):+.2f}%</td>
            <td><span class="status-pill" style="background:{outcome_color}22;color:{outcome_color};border:1px solid {outcome_color}55">{_esc(outcome)}</span></td>
            <td class="r">{_esc(status)}</td>
          </tr>
        """)
    return f"""
    <section class="card">
      <div class="card-h"><span class="ic">📋</span><span class="ttl">Yesterday's Audit · D1 outcomes</span>
        <span class="card-meta">{len(rows)} picks · pick date {_esc(yest)}/{_esc(yest2)}</span></div>
      <table class="pos-tbl">
        <thead><tr>
          <th>Ticker</th><th>Verdict</th><th class="r">Score</th>
          <th class="r">D0</th><th class="r">D1</th>
          <th class="r">MAE</th><th class="r">MFE</th>
          <th>PnL</th><th>Outcome</th><th class="r">Status</th>
        </tr></thead>
        <tbody>{"".join(cells)}</tbody>
      </table>
    </section>"""


def _market_context_html(b: dict) -> str:
    """Index futures + yield curve + crypto + commodities + credit detail."""
    # Best-effort fetch via Schwab multi-quote endpoint (works without entitlement-issues)
    syms = ["SPY","QQQ","IWM","DIA","VIX","TLT","IEF","SHY","BTC-USD","ETH-USD",
            "USO","UNG","CPER","SLV","GLD","HYG","LQD","UUP"]
    quotes = {}
    try:
        import urllib.request
        import schwab_auth
        access = schwab_auth.get_access_token()
        if access:
            url = f"https://api.schwabapi.com/marketdata/v1/quotes?symbols={','.join(syms)}"
            req = urllib.request.Request(url, headers={
                "Authorization": f"Bearer {access}", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=6) as r:
                data = json.loads(r.read())
            for sym, payload in (data or {}).items():
                q = (payload or {}).get("quote") or {}
                quotes[sym] = {
                    "last": q.get("lastPrice") or q.get("mark"),
                    "chg":  q.get("netPercentChangeInDouble") or q.get("netPercentChange"),
                    "bid":  q.get("bidPrice"),
                    "ask":  q.get("askPrice"),
                }
    except Exception as e:
        print(f"market context fetch fail: {e}", file=sys.stderr)

    def cell(sym, label, color_pos=True):
        q = quotes.get(sym) or {}
        last = q.get("last")
        chg = q.get("chg")
        color = _pct_color(chg) if color_pos else "#9ba7c2"
        last_str = f"${last:,.2f}" if isinstance(last,(int,float)) else "—"
        chg_str  = f"{chg:+.2f}%" if isinstance(chg,(int,float)) else "—"
        return (f'<div class="mc-cell"><div class="mc-lbl">{label}</div>'
                f'<div class="mc-v">{last_str}</div>'
                f'<div class="mc-c" style="color:{color}">{chg_str}</div></div>')

    # Yield curve calc (2s10s proxy via TLT/IEF/SHY)
    yc_note = "—"
    try:
        sh = (quotes.get("SHY") or {}).get("last")  # 1-3y
        ie = (quotes.get("IEF") or {}).get("last")  # 7-10y
        tl = (quotes.get("TLT") or {}).get("last")  # 20+y
        if sh and ie:
            yc_note = "inverted" if sh > ie else "normal"
    except Exception: pass

    return f"""
    <section class="card">
      <div class="card-h"><span class="ic">🌐</span><span class="ttl">Market Context</span>
        <span class="card-meta">Index futures · yields · crypto · commodities · credit</span></div>
      <div class="mc-row-label">📈 INDICES</div>
      <div class="mc-grid">
        {cell("SPY","S&P 500")}{cell("QQQ","NASDAQ")}{cell("IWM","RUSSELL 2K")}{cell("DIA","DOW")}
      </div>
      <div class="mc-row-label">🏦 TREASURIES ({yc_note} curve)</div>
      <div class="mc-grid">
        {cell("SHY","SHY · 1-3y")}{cell("IEF","IEF · 7-10y")}{cell("TLT","TLT · 20+y")}{cell("UUP","UUP · USD")}
      </div>
      <div class="mc-row-label">₿ CRYPTO + COMMODITIES</div>
      <div class="mc-grid">
        {cell("BTC-USD","BITCOIN")}{cell("ETH-USD","ETHEREUM")}{cell("GLD","GOLD")}{cell("SLV","SILVER")}
      </div>
      <div class="mc-grid">
        {cell("USO","OIL · WTI")}{cell("UNG","NAT GAS")}{cell("CPER","COPPER")}{cell("VIX","VIX")}
      </div>
      <div class="mc-row-label">💵 CREDIT</div>
      <div class="mc-grid">
        {cell("HYG","HY · risky")}{cell("LQD","IG · safer")}
      </div>
    </section>"""


def _leadership_signals_html(b: dict, dj: dict) -> str:
    """Top industries + 52w highs/lows (from screener tickers)."""
    industries = dj.get("industries") or []
    top_inds = sorted(industries, key=lambda i: -(i.get("avg_score") or 0))[:6]
    bot_inds = sorted(industries, key=lambda i: (i.get("avg_score") or 0))[:3]

    # 52w hi/lo proxy: tickers within top 5% of 52w high vs bottom 5%
    all_scored = b.get("all_scored") or []
    near_hi = []
    near_lo = []
    for t in all_scored:
        pct = t.get("pct_off_52w_high")
        if pct is None: continue
        try: pct = float(pct)
        except Exception: continue
        if pct >= -5: near_hi.append(t)
        elif pct <= -40: near_lo.append(t)
    near_hi.sort(key=lambda t: -(t.get("score") or 0))
    near_lo.sort(key=lambda t: -(t.get("score") or 0))

    def ind_chip(i):
        score = i.get("avg_score") or 0
        color = _pct_color(score - 50)
        return (f'<div class="ld-chip" style="border-left:3px solid {color}">'
                f'<div class="ld-name">{_esc(i.get("industry",""))[:24]}</div>'
                f'<div class="ld-meta">avg <b style="color:{color}">{score:.0f}</b> · '
                f'{i.get("count")} names</div></div>')

    hi_chips = ", ".join(f'<code>{_esc(t.get("ticker"))}</code>' for t in near_hi[:8])
    lo_chips = ", ".join(f'<code>{_esc(t.get("ticker"))}</code>' for t in near_lo[:6])

    return f"""
    <section class="card">
      <div class="card-h"><span class="ic">👑</span><span class="ttl">Leadership Signals</span></div>
      <div style="padding:14px 18px">
        <div style="font:700 10px var(--mono);color:var(--gn);letter-spacing:.12em;margin-bottom:8px">TOP INDUSTRIES</div>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px">
          {"".join(ind_chip(i) for i in top_inds)}
        </div>
        <div style="font:700 10px var(--mono);color:var(--rd);letter-spacing:.12em;margin-top:14px;margin-bottom:8px">WEAKEST INDUSTRIES</div>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px">
          {"".join(ind_chip(i) for i in bot_inds)}
        </div>
        <div style="font:700 10px var(--mono);color:var(--gn);letter-spacing:.12em;margin-top:14px;margin-bottom:6px">📈 NEAR 52W HIGH ({len(near_hi)})</div>
        <div style="font:500 11.5px var(--mono);color:var(--ink-1);line-height:1.7">{hi_chips or "—"}</div>
        <div style="font:700 10px var(--mono);color:var(--rd);letter-spacing:.12em;margin-top:10px;margin-bottom:6px">📉 NEAR 52W LOW ({len(near_lo)})</div>
        <div style="font:500 11.5px var(--mono);color:var(--ink-1);line-height:1.7">{lo_chips or "—"}</div>
      </div>
    </section>"""


def _risk_dashboard_html() -> str:
    """Net portfolio beta, sector concentration, drawdown, Kelly per setup."""
    port = _safe_load(REPO / "data" / "portfolio_state.json") or {}
    positions = port.get("positions") or []
    equity = port.get("equity") or 1
    starting = port.get("starting_equity") or 1
    eq_curve = port.get("equity_curve") or []

    # Drawdown
    if eq_curve:
        eqs = [e.get("equity") for e in eq_curve if e.get("equity")]
        if eqs:
            peak = max(eqs)
            dd = ((equity - peak) / peak) * 100 if peak else 0
            max_dd_pct = min(((e - max(eqs[:i+1])) / max(eqs[:i+1])) * 100
                             for i, e in enumerate(eqs))
        else:
            dd = max_dd_pct = 0
    else:
        dd = max_dd_pct = 0

    # Sector concentration
    sectors = {}
    net_beta = 0
    total_exposure = 0
    for p in positions:
        sec = p.get("sector", "—")
        qty = p.get("shares") or p.get("quantity") or 0
        price = p.get("last") or p.get("entry") or 0
        beta  = p.get("beta") or 1.0
        exposure = qty * price
        total_exposure += exposure
        sectors[sec] = sectors.get(sec, 0) + exposure
        net_beta += exposure * beta
    net_beta = (net_beta / total_exposure) if total_exposure else 0
    sect_pcts = sorted(
        [(s, v / total_exposure * 100) for s, v in sectors.items()],
        key=lambda x: -x[1]
    ) if total_exposure else []

    # Kelly per setup (use setup_stats)
    ss = _safe_load(REPO / "cache" / "setup_stats.json") or {}
    setups = ss.get("setups") or {}
    kelly_rows = []
    for setup_key, sd in (setups.items() if isinstance(setups, dict) else []):
        wr = (sd.get("win_rate") or 0) / 100
        rr = sd.get("avg_r") or 1
        n = sd.get("n") or 0
        if n < 10: continue
        # Kelly = (p*b - q)/b where p=wr, q=1-wr, b=rr
        if rr <= 0: continue
        k = (wr * rr - (1 - wr)) / rr
        k_pct = max(0, min(100, k * 100))
        kelly_rows.append((setup_key, wr*100, rr, n, k_pct))
    kelly_rows.sort(key=lambda x: -x[4])
    kelly_rows = kelly_rows[:6]

    metric_cells = "".join([
        f'<div class="ss-cell"><div class="ss-lbl">EQUITY</div><div class="ss-val">${equity:,.0f}</div><div class="ss-sub">start ${starting:,.0f}</div></div>',
        f'<div class="ss-cell"><div class="ss-lbl">CURRENT DD</div><div class="ss-val" style="color:{_pct_color(dd)}">{dd:+.2f}%</div></div>',
        f'<div class="ss-cell"><div class="ss-lbl">MAX DD</div><div class="ss-val" style="color:#ff6b6b">{max_dd_pct:.2f}%</div></div>',
        f'<div class="ss-cell"><div class="ss-lbl">POSITIONS</div><div class="ss-val">{len(positions)}</div></div>',
        f'<div class="ss-cell"><div class="ss-lbl">NET BETA</div><div class="ss-val">{net_beta:.2f}</div></div>',
        f'<div class="ss-cell"><div class="ss-lbl">EXPOSURE</div><div class="ss-val">${total_exposure:,.0f}</div><div class="ss-sub">{(total_exposure/equity*100 if equity else 0):.1f}% of equity</div></div>',
    ])

    sect_html = ""
    if sect_pcts:
        sect_html = '<div style="padding:12px 18px"><div class="ss-lbl">SECTOR CONCENTRATION</div>'
        for s, pct in sect_pcts[:6]:
            sect_html += (f'<div style="display:flex;justify-content:space-between;align-items:center;margin-top:6px">'
                          f'<span style="font:500 11.5px var(--mono);color:var(--ink-1)">{_esc(s)}</span>'
                          f'<span style="font:700 11px var(--mono);color:var(--gn)">{pct:.1f}%</span>'
                          f'</div>'
                          f'<div style="height:4px;background:var(--bg-2);border-radius:99px;overflow:hidden">'
                          f'<div style="height:100%;width:{pct:.0f}%;background:var(--cu)"></div></div>')
        sect_html += '</div>'

    kelly_html = ""
    if kelly_rows:
        kelly_html = (
            '<div style="padding:12px 18px;border-top:1px solid var(--line)"><div class="ss-lbl">KELLY FRACTION BY SETUP (n≥10)</div>'
            '<table class="pos-tbl" style="margin-top:6px"><thead><tr>'
            '<th>Setup</th><th class="r">WR</th><th class="r">Avg R</th><th class="r">n</th><th class="r">Kelly %</th>'
            '</tr></thead><tbody>'
        )
        for setup, wr, rr, n, k in kelly_rows:
            color = _pct_color(k - 10)
            kelly_html += (f'<tr><td>{_esc(setup)}</td>'
                           f'<td class="r">{wr:.1f}%</td>'
                           f'<td class="r">{rr:.2f}</td>'
                           f'<td class="r">{n}</td>'
                           f'<td class="r" style="color:{color}"><b>{k:.1f}%</b></td></tr>')
        kelly_html += '</tbody></table></div>'

    return f"""
    <section class="card">
      <div class="card-h"><span class="ic">🛡</span><span class="ttl">Risk Dashboard</span></div>
      <div class="ss-grid">{metric_cells}</div>
      {sect_html}
      {kelly_html}
    </section>"""


def _tactical_opportunities_html(b: dict) -> str:
    """Implied move plays (earnings ≤7d w/ options), short squeeze candidates, pair watch."""
    # Implied move from earnings_watchlist cross-ref with options_flow
    wl = _safe_load(REPO / "data" / "earnings_watchlist.json") or {}
    options_d = _safe_load(REPO / "infra" / "prototype" / "options_flow.json") or {}
    options_top = options_d.get("top30") or []
    options_by_ticker = {o.get("ticker"): o for o in options_top}

    soon_earn = [w for w in (wl.get("watchlist") or [])
                 if w.get("days_to_earnings") is not None
                 and 0 <= w["days_to_earnings"] <= 7]
    soon_earn.sort(key=lambda w: w.get("days_to_earnings") or 99)

    im_rows = []
    for w in soon_earn[:8]:
        tk = w.get("ticker")
        opt = options_by_ticker.get(tk)
        if not opt: continue
        atm_iv = opt.get("atm_iv")
        days = w.get("days_to_earnings")
        if atm_iv is None: continue
        # Implied move = ATM IV * sqrt(days/365)
        try:
            import math
            im_pct = atm_iv * math.sqrt(max(days, 0.5) / 365) * 100
        except Exception:
            continue
        im_rows.append({
            "ticker": tk, "days": days, "iv": atm_iv,
            "im_pct": im_pct,
            "atm_strike": opt.get("atm_strike"),
            "price": opt.get("price"),
        })

    if not im_rows:
        return ""

    rows_html = "\n".join(
        f"""<tr>
            <td><b>{_esc(r['ticker'])}</b></td>
            <td class="r">+{r['days']}d</td>
            <td class="r">${(r.get('price') or 0):.2f}</td>
            <td class="r">${(r.get('atm_strike') or 0):.2f}</td>
            <td class="r">{(r['iv']*100):.1f}%</td>
            <td class="r" style="color:#5be57c"><b>±{r['im_pct']:.1f}%</b></td>
        </tr>"""
        for r in im_rows
    )
    return f"""
    <section class="card">
      <div class="card-h"><span class="ic">💡</span><span class="ttl">Tactical · Implied-Move Plays</span>
        <span class="card-meta">Earnings ≤7d · ATM IV → straddle move</span></div>
      <table class="pos-tbl">
        <thead><tr>
          <th>Ticker</th><th class="r">Earn</th><th class="r">Spot</th>
          <th class="r">ATM K</th><th class="r">ATM IV</th><th class="r">Implied Move</th>
        </tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
    </section>"""


def _earnings_density_html() -> str:
    """How crowded is earnings season this week?"""
    wl = _safe_load(REPO / "data" / "earnings_watchlist.json") or {}
    items = wl.get("watchlist") or []
    buckets = {}
    for e in items:
        d = e.get("days_to_earnings")
        if d is None: continue
        if 0 <= d <= 5:
            buckets[d] = buckets.get(d, [])
            buckets[d].append(e.get("ticker"))
    if not buckets: return ""
    from datetime import timedelta
    today = datetime.now()
    labels = ["Today (T+0)", "Tomorrow (T+1)", "T+2", "T+3", "T+4", "T+5"]
    bars = []
    max_n = max(len(v) for v in buckets.values()) if buckets else 1
    for i in range(6):
        tickers = buckets.get(i, [])
        n = len(tickers)
        d_str = (today + timedelta(days=i)).strftime("%a %b %-d")
        bar_w = (n / max_n) * 100 if max_n else 0
        sample = ", ".join(tickers[:8]) + ("…" if len(tickers) > 8 else "")
        bars.append(
            f'<div style="display:grid;grid-template-columns:120px 80px 1fr;align-items:center;gap:10px;margin-bottom:6px">'
            f'  <div style="font:600 11px var(--mono);color:var(--ink-2)">{labels[i]}</div>'
            f'  <div style="font:700 14px var(--mono);color:var(--cu);text-align:right">{n}</div>'
            f'  <div><div style="height:14px;background:var(--bg-2);border-radius:2px;overflow:hidden">'
            f'    <div style="height:100%;width:{bar_w:.0f}%;background:linear-gradient(90deg, var(--cu), var(--gn))"></div></div>'
            f'  <div style="font:500 10px var(--mono);color:var(--ink-3);margin-top:3px">{_esc(sample) or "—"} <span style="color:var(--ink-3)">{d_str}</span></div></div>'
            f'</div>'
        )
    return f"""
    <section class="card">
      <div class="card-h"><span class="ic">📅</span><span class="ttl">Earnings Density · Next 5d</span></div>
      <div style="padding:14px 18px">{"".join(bars)}</div>
    </section>"""


def _pnl_attribution_html() -> str:
    """Today's P&L by sleeve / setup."""
    port = _safe_load(REPO / "data" / "portfolio_state.json") or {}
    closed = port.get("closed_trades") or []
    today = _today()
    today_closes = [t for t in closed
                    if str(t.get("close_date") or t.get("exit_date") or "").startswith(today)]
    if not today_closes:
        return ""
    by_setup = {}
    for t in today_closes:
        setup = t.get("setup_family") or t.get("setup") or "—"
        pnl = t.get("realized_pnl") or t.get("pnl") or 0
        by_setup.setdefault(setup, {"n": 0, "pnl": 0, "wins": 0})
        by_setup[setup]["n"] += 1
        by_setup[setup]["pnl"] += pnl
        if pnl > 0: by_setup[setup]["wins"] += 1
    rows = sorted(
        [(s, v["n"], v["wins"], v["pnl"], (v["wins"]/v["n"]*100 if v["n"] else 0))
         for s, v in by_setup.items()],
        key=lambda x: -x[3]
    )
    rows_html = "\n".join(
        f'<tr><td>{_esc(s)}</td><td class="r">{n}</td><td class="r">{w}</td>'
        f'<td class="r" style="color:{_pct_color(pnl/1000)}"><b>{"+" if pnl>=0 else ""}${pnl:.2f}</b></td>'
        f'<td class="r">{wr:.0f}%</td></tr>'
        for s, n, w, pnl, wr in rows
    )
    return f"""
    <section class="card">
      <div class="card-h"><span class="ic">💰</span><span class="ttl">Today's P&L Attribution</span></div>
      <table class="pos-tbl">
        <thead><tr><th>Setup Family</th><th class="r">Trades</th><th class="r">Wins</th><th class="r">P&L</th><th class="r">WR</th></tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
    </section>"""


def _tomorrow_prep_html() -> str:
    """BMO earnings tomorrow + macro events tomorrow."""
    wl = _safe_load(REPO / "data" / "earnings_watchlist.json") or {}
    bmo_t1 = [e for e in (wl.get("watchlist") or [])
              if e.get("days_to_earnings") == 1
              and e.get("before_after_market") == "BeforeMarket"]
    amc_t1 = [e for e in (wl.get("watchlist") or [])
              if e.get("days_to_earnings") == 1
              and e.get("before_after_market") == "AfterMarket"]
    def _fmt_earn(e):
        tk = _esc(e.get("ticker"))
        est = e.get("estimate")
        return (f'<code>{tk}</code> est ${est:.2f}' if est is not None else f'<code>{tk}</code>')

    body_lines = []
    if bmo_t1:
        bmo_str = ", ".join(_fmt_earn(e) for e in bmo_t1[:14])
        body_lines.append(
            '<div style="margin-top:6px"><span class="ss-lbl">BMO (before open):</span><br>'
            '<div style="font:500 12px var(--mono);color:var(--ink-1);margin-top:4px;line-height:1.8">'
            f'{bmo_str}'
            '</div></div>')
    if amc_t1:
        amc_str = ", ".join(_fmt_earn(e) for e in amc_t1[:14])
        body_lines.append(
            '<div style="margin-top:10px"><span class="ss-lbl">AMC (after close):</span><br>'
            '<div style="font:500 12px var(--mono);color:var(--ink-1);margin-top:4px;line-height:1.8">'
            f'{amc_str}'
            '</div></div>')
    if not body_lines:
        body_lines.append('<div style="color:var(--ink-3);font:500 12px var(--mono)">Quiet day tomorrow — no significant earnings on watchlist.</div>')
    return f"""
    <section class="card">
      <div class="card-h"><span class="ic">🌅</span><span class="ttl">Tomorrow's Prep</span></div>
      <div style="padding:14px 18px">
        {"".join(body_lines)}
      </div>
    </section>"""


def _amc_results_html() -> str:
    """AMC earnings results that came out today."""
    outcomes_path = REPO / "data" / "earnings_outcomes.jsonl"
    if not outcomes_path.exists(): return ""
    today = _today()
    rows = []
    for line in outcomes_path.read_text().splitlines():
        if not line.strip(): continue
        try: r = json.loads(line)
        except Exception: continue
        if str(r.get("captured_at","")).startswith(today):
            rows.append(r)
    if not rows: return ""
    beats = [r for r in rows if r.get("beat") is True]
    misses = [r for r in rows if r.get("beat") is False]
    body = "\n".join(
        f'<tr><td><b>{_esc(r.get("ticker"))}</b></td>'
        f'<td class="r">${(r.get("estimate") or 0):.2f}</td>'
        f'<td class="r">${(r.get("actual") or 0):.2f}</td>'
        f'<td class="r" style="color:{_pct_color(r.get("surprise_pct"))}">{(r.get("surprise_pct") or 0):+.1f}%</td>'
        f'<td>{"✅ BEAT" if r.get("beat") else "❌ MISS" if r.get("beat") is False else "—"}</td></tr>'
        for r in rows[:15]
    )
    return f"""
    <section class="card">
      <div class="card-h"><span class="ic">🎯</span><span class="ttl">Earnings Results Today</span>
        <span class="card-meta">{len(beats)} beats · {len(misses)} misses</span></div>
      <table class="pos-tbl">
        <thead><tr><th>Ticker</th><th class="r">Est</th><th class="r">Actual</th><th class="r">Surprise</th><th>Result</th></tr></thead>
        <tbody>{body}</tbody>
      </table>
    </section>"""


def _market_top_movers_html(b: dict) -> str:
    """Today's biggest gainers/losers from all_scored."""
    all_scored = b.get("all_scored") or []
    movers = [t for t in all_scored if t.get("pct_chg") is not None]
    movers.sort(key=lambda t: -t.get("pct_chg", 0))
    gainers = movers[:8]
    movers.sort(key=lambda t: t.get("pct_chg", 0))
    losers = movers[:8]
    def row(t):
        chg = t.get("pct_chg")
        return (f'<tr><td><b>{_esc(t.get("ticker"))}</b></td>'
                f'<td class="r">${(t.get("price") or 0):.2f}</td>'
                f'<td class="r" style="color:{_pct_color(chg)}"><b>{chg:+.2f}%</b></td>'
                f'<td class="r">{t.get("score","—")}</td>'
                f'<td>{_esc((t.get("sector") or "—")[:14])}</td></tr>')
    g_html = "\n".join(row(t) for t in gainers)
    l_html = "\n".join(row(t) for t in losers)
    return f"""
    <section class="card">
      <div class="card-h"><span class="ic">🚀</span><span class="ttl">Today's Market Top Movers</span></div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:0px;border-top:1px solid var(--line)">
        <div style="border-right:1px solid var(--line)">
          <div style="padding:10px 14px;background:rgba(91,229,124,.06);font:700 10px var(--mono);color:var(--gn);letter-spacing:.12em">📈 GAINERS</div>
          <table class="pos-tbl">
            <thead><tr><th>Ticker</th><th class="r">Price</th><th class="r">%</th><th class="r">Score</th><th>Sector</th></tr></thead>
            <tbody>{g_html}</tbody>
          </table>
        </div>
        <div>
          <div style="padding:10px 14px;background:rgba(255,107,107,.06);font:700 10px var(--mono);color:var(--rd);letter-spacing:.12em">📉 LOSERS</div>
          <table class="pos-tbl">
            <thead><tr><th>Ticker</th><th class="r">Price</th><th class="r">%</th><th class="r">Score</th><th>Sector</th></tr></thead>
            <tbody>{l_html}</tbody>
          </table>
        </div>
      </div>
    </section>"""


def _open_positions_watch_html() -> str:
    port = _safe_load(REPO / "data" / "portfolio_state.json") or {}
    positions = port.get("positions") or []
    if not positions:
        return f"""
        <section class="card">
          <div class="card-h"><span class="ic">💼</span><span class="ttl">Open Positions</span></div>
          <div style="padding:14px 18px;color:#8b9bbf;font:500 12px var(--mono)">No open positions.</div>
        </section>"""
    cells = []
    for p in positions[:10]:
        tk = p.get("ticker","—")
        entry = p.get("entry") or p.get("price")
        last  = p.get("last") or p.get("current_price")
        stop  = p.get("stop")
        t1    = p.get("t1") or p.get("target1")
        if entry and last:
            pct_chg = ((last - entry) / entry) * 100
        else:
            pct_chg = None
        days = p.get("days_held") or 0
        pct_to_t1  = (((t1 - last) / last) * 100) if (t1 and last) else None
        pct_to_stop = (((last - stop) / last) * 100) if (stop and last) else None
        chg_color = _pct_color(pct_chg)
        stop_warn = "⚠️ near stop" if (pct_to_stop is not None and pct_to_stop < 2) else ""
        cells.append(f"""
          <tr>
            <td><b>{_esc(tk)}</b></td>
            <td class="r">{_fmt_px(entry)}</td>
            <td class="r">{_fmt_px(last)}</td>
            <td class="r" style="color:{chg_color}">{(pct_chg or 0):+.2f}%</td>
            <td class="r" style="color:#ff6b6b">{_fmt_px(stop)}</td>
            <td class="r" style="color:#5be57c">{_fmt_px(t1)}</td>
            <td class="r">{(pct_to_t1 or 0):.1f}%</td>
            <td class="r">{(pct_to_stop or 0):.1f}%</td>
            <td>{days}d</td>
            <td style="color:#ff6b6b;font:700 10px var(--mono)">{stop_warn}</td>
          </tr>
        """)
    return f"""
    <section class="card">
      <div class="card-h"><span class="ic">💼</span><span class="ttl">Open Positions Watch</span>
        <span class="card-meta">{len(positions)} open</span></div>
      <table class="pos-tbl">
        <thead><tr>
          <th>Ticker</th><th class="r">Entry</th><th class="r">Last</th><th class="r">% Chg</th>
          <th class="r">Stop</th><th class="r">T1</th><th class="r">→T1</th><th class="r">→Stop</th>
          <th>Held</th><th></th>
        </tr></thead>
        <tbody>{"".join(cells)}</tbody>
      </table>
    </section>"""


# ── Visual helpers: SVG sparklines · score bars · sector colors · stars ──
SECTOR_PALETTE = {
    "Technology":            {"bg": "rgba(98,179,255,.14)", "ink": "#62b3ff", "bd": "#62b3ff44"},
    "Financial Services":    {"bg": "rgba(91,229,124,.12)", "ink": "#5be57c", "bd": "#5be57c44"},
    "Healthcare":            {"bg": "rgba(255,107,107,.12)", "ink": "#ff6b6b", "bd": "#ff6b6b44"},
    "Energy":                {"bg": "rgba(255,185,92,.12)", "ink": "#ffb95c", "bd": "#ffb95c44"},
    "Consumer Cyclical":     {"bg": "rgba(217,119,87,.12)", "ink": "#d97757", "bd": "#d9775744"},
    "Consumer Defensive":    {"bg": "rgba(200,200,255,.10)", "ink": "#c8c8ff", "bd": "#c8c8ff44"},
    "Industrials":           {"bg": "rgba(180,210,140,.12)", "ink": "#b4d28c", "bd": "#b4d28c44"},
    "Communication Services":{"bg": "rgba(180,140,255,.12)", "ink": "#b48cff", "bd": "#b48cff44"},
    "Utilities":             {"bg": "rgba(140,200,200,.12)", "ink": "#8cc8c8", "bd": "#8cc8c844"},
    "Real Estate":           {"bg": "rgba(220,180,140,.12)", "ink": "#dcb48c", "bd": "#dcb48c44"},
    "Basic Materials":       {"bg": "rgba(170,160,140,.12)", "ink": "#aaa08c", "bd": "#aaa08c44"},
}


def _sector_chip(sector: str) -> str:
    s = (sector or "—").strip()
    pal = SECTOR_PALETTE.get(s, {"bg": "rgba(155,167,194,.10)", "ink": "#9ba7c2", "bd": "#9ba7c244"})
    short = s if len(s) <= 20 else s[:18] + "…"
    return (f'<span style="background:{pal["bg"]};color:{pal["ink"]};'
            f'border:1px solid {pal["bd"]};padding:2px 8px;border-radius:99px;'
            f'font:600 10px var(--mono);letter-spacing:.04em">{_esc(short)}</span>')


def _stars(rating) -> str:
    try:
        r = int(rating or 0)
    except Exception:
        r = 0
    r = max(0, min(5, r))
    filled = "★" * r
    empty  = "☆" * (5 - r)
    return f'<span class="stars" title="{r}/5 conviction stars">{filled}<span style="color:#3a4258">{empty}</span></span>'


def _score_bar(score, max_val: int = 100) -> str:
    try: s = float(score or 0)
    except Exception: s = 0
    s = max(0, min(max_val, s))
    pct = (s / max_val) * 100
    color = "#5be57c" if s >= 80 else "#ffb95c" if s >= 60 else "#ff6b6b" if s >= 40 else "#d97757"
    return (f'<span class="sb-wrap" title="Score {s:.0f}/100">'
            f'<span class="sb-num" style="color:{color}">{s:.0f}</span>'
            f'<span class="sb-bar"><span class="sb-fill" style="width:{pct:.0f}%;background:{color}"></span></span>'
            f'</span>')


def _sparkline_svg(closes: list, width: int = 100, height: int = 28,
                   trend_color: bool = True) -> str:
    """SVG sparkline from a price series. Auto-scales. Color by direction."""
    if not closes or len(closes) < 2:
        return ""
    lo = min(closes); hi = max(closes); rng = (hi - lo) or 1
    n = len(closes)
    pts = []
    for i, v in enumerate(closes):
        x = (i / (n - 1)) * (width - 2) + 1
        y = height - 2 - ((v - lo) / rng) * (height - 4)
        pts.append(f"{x:.1f},{y:.1f}")
    path = " ".join(pts)
    direction = closes[-1] - closes[0]
    color = "#5be57c" if (trend_color and direction >= 0) else "#ff6b6b" if trend_color else "#9ba7c2"
    last_x, last_y = pts[-1].split(",")
    return (f'<svg class="spark" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
            f'<polyline fill="none" stroke="{color}" stroke-width="1.6" '
            f'stroke-linejoin="round" stroke-linecap="round" points="{path}"/>'
            f'<circle cx="{last_x}" cy="{last_y}" r="2.2" fill="{color}"/>'
            f'</svg>')


def _ohlcv_closes(ohlcv: list, lookback: int = 60) -> list:
    if not isinstance(ohlcv, list): return []
    rows = ohlcv[-lookback:] if len(ohlcv) > lookback else ohlcv
    return [r.get("close") for r in rows if isinstance(r, dict) and r.get("close") is not None]


def _r_multiples_bar(entry, stop, t1, t2) -> str:
    """Visualize entry / stop / T1 / T2 as colored ratio bar."""
    try:
        entry, stop, t1 = float(entry), float(stop), float(t1)
    except Exception:
        return ""
    risk = entry - stop
    if risk <= 0: return ""
    r_to_t1 = (t1 - entry) / risk
    color = "#5be57c" if r_to_t1 >= 3 else "#ffb95c" if r_to_t1 >= 2 else "#ff6b6b"
    return (f'<span style="background:rgba(91,229,124,.10);color:{color};'
            f'border:1px solid {color}44;padding:2px 8px;border-radius:3px;'
            f'font:700 10px var(--mono);letter-spacing:.04em">'
            f'{r_to_t1:.1f}R</span>')


def _fmt_money(v):
    if v is None: return "—"
    try: v = float(v)
    except Exception: return "—"
    if v >= 1e9: return f"${v/1e9:.1f}B"
    if v >= 1e6: return f"${v/1e6:.1f}M"
    if v >= 1e3: return f"${v/1e3:.0f}k"
    return f"${v:.0f}"


def _fmt_px(v):
    if v is None: return "—"
    try: return f"${float(v):.2f}"
    except Exception: return str(v)


def _cross_tags(all_picks_by_section: dict) -> dict:
    """Build {ticker: set(section_names)} for cross-tagging."""
    tags = defaultdict(set)
    for sect, rows in all_picks_by_section.items():
        for r in rows:
            tk = r.get("ticker")
            if tk: tags[tk].add(sect)
    return {tk: s for tk, s in tags.items() if len(s) >= 2}


def _ticker_news_block(tk: str, news: dict) -> str:
    items = news.get(tk) or []
    if not items: return ""
    pieces = []
    for n in items[:2]:  # 2 headlines per ticker
        link = n.get("link") or "#"
        title = _esc(n.get("title", ""))[:140]
        pieces.append(
            f'<div class="news-row">📰 <a href="{_esc(link)}" target="_blank">{title}</a></div>'
        )
    return "\n".join(pieces)


def _universe_news(limit: int = 8) -> list:
    """Top market headlines from finviz news feed — macro / not ticker-specific."""
    try:
        import data_fetcher as df
        all_news = df.get_finviz_news() or []
    except Exception as e:
        print(f"universe news unavailable: {e}", file=sys.stderr)
        return []
    # Finviz uses 'Market' for news headlines + 'Blog' for opinion. Prefer Market.
    news_first = [n for n in all_news if (n.get("category") or "").lower() == "market"]
    blogs      = [n for n in all_news if (n.get("category") or "").lower() == "blog"]
    combined = news_first + blogs
    seen = set()
    out = []
    for n in combined:
        t = (n.get("title") or "").strip()
        if not t or t in seen: continue
        seen.add(t)
        out.append({
            "title": t[:200],
            "link":  n.get("url", ""),
            "source": n.get("source", ""),
            "date":  n.get("date", ""),
        })
        if len(out) >= limit: break
    return out


def _universe_news_html(items: list) -> str:
    if not items: return ""
    rows = "\n".join(
        f'<div class="news-row">📰 <a href="{_esc(n["link"])}" target="_blank">{_esc(n["title"])}</a> '
        f'<span style="color:#5e6e90">— {_esc(n.get("source",""))}</span></div>'
        for n in items
    )
    return f"""
    <section class="card">
      <div class="card-h"><span class="ic">🌍</span><span class="ttl">Universe News</span></div>
      <div class="card-body" style="padding:14px 18px">{rows}</div>
    </section>"""


def _section_html(title: str, icon: str, rows: list, cross_tags: dict,
                  formatter, news: dict) -> str:
    if not rows: return ""
    body = []
    for p in rows:
        tk = p.get("ticker", "—")
        extra_tags = sorted(cross_tags.get(tk, set()) - {title})
        cross = ""
        if extra_tags:
            cross = " " + " ".join(f'<span class="x-tag">🌟 also in {_esc(t)}</span>' for t in extra_tags)
        body.append(formatter(p, cross) + "\n" + _ticker_news_block(tk, news))
    return f"""
    <section class="card">
      <div class="card-h"><span class="ic">{icon}</span><span class="ttl">{_esc(title)}</span></div>
      <div class="card-body">{"<hr/>".join(body)}</div>
    </section>"""


def _hc_row(p, cross):
    tp = p.get("trade_plan") or {}
    spark = _sparkline_svg(_ohlcv_closes(p.get("ohlcv")))
    r_chip = _r_multiples_bar(p.get("price"), tp.get("stop"), tp.get("target1"), tp.get("target2"))
    return f"""
    <div class="row">
      <div class="row-top">
        <div class="row-l">
          <span class="tk">{_esc(p.get('ticker'))}</span>
          <span class="px">{_esc(_fmt_px(p.get('price')))}</span>
          {spark}
          <span class="stars-wrap">{_stars(p.get('star_rating'))}</span>
        </div>
        <div class="row-r">
          {_score_bar(p.get('score'))}
          {r_chip}
          <span class="t-chip">T{_esc(p.get('catalyst_tier','—'))}</span>
          {_sector_chip(p.get('sector'))}{cross}
        </div>
      </div>
      <div class="row-trade">
        <span class="lbl">Setup:</span> <b>{_esc(p.get('setup_family',''))}</b>
        <span class="sep">·</span>
        <span class="lbl">Entry:</span> <b>{_esc(tp.get('entry_zone','—'))}</b>
        <span class="sep">·</span>
        <span class="lbl">Stop:</span> <b style="color:#ff6b6b">{_esc(_fmt_px(tp.get('stop')))}</b>
        <span class="sep">·</span>
        <span class="lbl">T1:</span> <b style="color:#5be57c">{_esc(_fmt_px(tp.get('target1')))}</b>
        <span class="sep">·</span>
        <span class="lbl">T2:</span> <b style="color:#5be57c">{_esc(_fmt_px(tp.get('target2')))}</b>
      </div>
    </div>"""


def _mom_row(p, cross):
    return f"""
    <div class="row">
      <div class="row-top">
        <div class="row-l">
          <span class="tk">{_esc(p.get('ticker'))}</span>
          <span class="px">{_esc(_fmt_px(p.get('price')))}</span>
          <span class="stars-wrap" title="EMA stack: {_esc(p.get('ema_signal',''))}">📈</span>
        </div>
        <div class="row-r">
          {_score_bar(p.get('composite'))}
          <span class="metric-chip" title="126d annualized Sharpe">Sh {p.get('sharpe_126d',0):.2f}</span>
          <span class="metric-chip">RS {p.get('rs_rank',0):.0f}</span>
          {_sector_chip(p.get('sector'))}{cross}
        </div>
      </div>
      <div class="row-trade">
        <span class="lbl">Setup:</span> <b>{_esc(p.get('setup',''))}</b>
        <span class="sep">·</span>
        <span class="lbl">EMA:</span> <b>{_esc(p.get('ema_signal',''))}</b>
        <span class="sep">·</span>
        <span class="lbl">ADX:</span> <b>{p.get('adx',0):.0f}</b>
        <span class="sep">·</span>
        <span class="lbl">Trend:</span> <b style="color:{'#5be57c' if p.get('trend')=='accel' else '#ffb95c' if p.get('trend')=='flat' else '#ff6b6b'}">{_esc(p.get('trend','—'))}</b>
      </div>
    </div>"""


def _ml_row(p, cross):
    edge = p.get("edge", 0)
    edge_color = "#5be57c" if edge > 2 else "#ffb95c" if edge > 0 else "#ff6b6b"
    verdict = p.get("verdict", "")
    v_color = "#5be57c" if "BULL" in verdict.upper() else "#ff6b6b" if "BEAR" in verdict.upper() else "#9ba7c2"
    return f"""
    <div class="row">
      <div class="row-top">
        <div class="row-l">
          <span class="tk">{_esc(p.get('ticker'))}</span>
          <span class="ml-edge" style="color:{edge_color}">{edge:+.1f}</span>
          <span class="ml-edge-label">edge</span>
        </div>
        <div class="row-r">
          <span class="v-chip" style="background:{v_color}22;color:{v_color};border:1px solid {v_color}55">{_esc(verdict)}</span>
          <span class="metric-chip">{_esc(p.get('level',''))}</span>
          <span class="metric-chip">conf {_esc(p.get('conf',''))}</span>{cross}
        </div>
      </div>
      <div class="row-trade">
        <span class="lbl">5-day horizon ML forecast</span>
        <span class="sep">·</span>
        <span class="lbl">trained on cache/historical_backfill.json</span>
      </div>
    </div>"""


def _scr_row(p, cross):
    tp = p.get("trade_plan") or {}
    spark = _sparkline_svg(_ohlcv_closes(p.get("ohlcv")))
    r_chip = _r_multiples_bar(p.get("price"), tp.get("stop"), tp.get("target1"), tp.get("target2"))
    return f"""
    <div class="row">
      <div class="row-top">
        <div class="row-l">
          <span class="tk">{_esc(p.get('ticker'))}</span>
          <span class="px">{_esc(_fmt_px(p.get('price')))}</span>
          {spark}
        </div>
        <div class="row-r">
          {_score_bar(p.get('score'))}
          {r_chip}
          <span class="metric-chip">RS {_esc(p.get('rs_rank_63d', p.get('rs_rank','—')))}</span>
          {_sector_chip(p.get('sector'))}{cross}
        </div>
      </div>
      <div class="row-trade">
        <span class="lbl">Setup:</span> <b>{_esc(p.get('setup_family',''))}</b>
        <span class="sep">·</span>
        <span class="lbl">Entry:</span> <b>{_esc(tp.get('entry_zone','—'))}</b>
        <span class="sep">·</span>
        <span class="lbl">Stop:</span> <b style="color:#ff6b6b">{_esc(_fmt_px(tp.get('stop')))}</b>
        <span class="sep">·</span>
        <span class="lbl">T1:</span> <b style="color:#5be57c">{_esc(_fmt_px(tp.get('target1')))}</b>
      </div>
    </div>"""


def _opt_row(p, cross):
    status = p.get("status", "")
    s_color = "#5be57c" if status == "STRONG" else "#ffb95c" if status == "SOLID" else "#9ba7c2"
    pcr = p.get("put_call_ratio") or 0
    pcr_color = "#5be57c" if pcr < 0.3 else "#ffb95c" if pcr < 0.7 else "#ff6b6b"
    return f"""
    <div class="row">
      <div class="row-top">
        <div class="row-l">
          <span class="tk">{_esc(p.get('ticker'))}</span>
          <span class="px">{_esc(_fmt_px(p.get('price')))}</span>
          <span class="status-pill" style="background:{s_color}22;color:{s_color};border:1px solid {s_color}55">{_esc(status)}</span>
        </div>
        <div class="row-r">
          <span class="metric-chip" style="color:{pcr_color}">PCR {pcr:.2f}</span>
          <span class="metric-chip">ATM ${(p.get('atm_strike') or 0):.0f} · {(p.get('atm_dte') or 0):.0f}d</span>
          <span class="metric-chip" style="color:#5be57c">{_esc(_fmt_money(p.get('premium_total_$')))}</span>
          {_sector_chip(p.get('sector'))}{cross}
        </div>
      </div>
      <div class="row-trade">
        <span class="lbl">RR:</span> <b style="color:#5be57c">{(p.get('rr') or 0):.1f}x</b>
        <span class="sep">·</span>
        <span class="lbl">Target:</span> <b style="color:#5be57c">${(p.get('target') or 0):.2f}</b>
        <span class="sep">·</span>
        <span class="lbl">Stop:</span> <b style="color:#ff6b6b">${(p.get('stop') or 0):.2f}</b>
        <span class="sep">·</span>
        <span class="lbl">IV%ile:</span> <b>{p.get('iv_percentile') if p.get('iv_percentile') is not None else '—'}</b>
      </div>
    </div>"""


def _evening_recap_card(extras: dict) -> str:
    """Recap of today's morning picks: hit T1 / stopped / unchanged + closed trades."""
    closes  = extras.get("closes_today") or []
    morn    = extras.get("morning_results") or []
    earn    = extras.get("earnings_results") or []
    pieces = []
    if morn:
        rows = "\n".join(
            f'<div class="row-h"><b class="tk">{_esc(p["ticker"])}</b> '
            f'<span class="metric">entry {_fmt_px(p.get("entry"))}</span> '
            f'<span class="metric">close {_fmt_px(p.get("close"))}</span> '
            f'<span class="sc">{p.get("pct_move","—")}</span> '
            f'<span class="metric">{_esc(p.get("status","—"))}</span></div>'
            for p in morn[:15]
        )
        pieces.append(f'<div style="padding:12px 18px"><b style="color:#d97757">Morning picks · realized:</b><br>{rows}</div>')
    if closes:
        rows = "\n".join(
            f'<div class="row-h"><b class="tk">{_esc(t.get("ticker","—"))}</b> '
            f'<span class="sc">{"+" if (t.get("realized_pnl") or t.get("pnl") or 0) >= 0 else ""}${(t.get("realized_pnl") or t.get("pnl") or 0):.2f}</span></div>'
            for t in closes[:10]
        )
        pieces.append(f'<div style="padding:12px 18px"><b style="color:#5be57c">Closed today:</b><br>{rows}</div>')
    if earn:
        rows = ", ".join(
            f"<code>{_esc(o.get('ticker','—'))}</code> "
            + ("✅" if o.get("beat") else "❌")
            + (f"+{o.get('surprise_pct'):.1f}%" if o.get('surprise_pct') is not None else "")
            for o in earn[:15]
        )
        pieces.append(f'<div style="padding:12px 18px"><b style="color:#5be57c">Earnings outcomes today:</b><br>{rows}</div>')
    if not pieces:
        pieces.append('<div style="padding:14px 18px;color:#8b9bbf">Quiet day — no closed trades or earnings outcomes yet.</div>')
    return f"""
    <section class="card">
      <div class="card-h"><span class="ic">🌆</span><span class="ttl">Today's Recap</span></div>
      <div class="card-body">{"<hr/>".join(pieces)}</div>
    </section>"""


def _render_html(sections: dict, news: dict, regime: dict, when: str,
                 universe_news: list, mode: str = "morning",
                 evening_extras: dict | None = None) -> str:
    """Render full HTML newsletter — Bloomberg-grade quant terminal aesthetic."""
    b  = _bundle()
    dj = _data_json()
    cross_tags_map = _cross_tags(sections)
    formatters = {
        "High Conviction": ("🎯", _hc_row),
        "Momentum":        ("🚀", _mom_row),
        "ML Edge":         ("🤖", _ml_row),
        "Screener":        ("📊", _scr_row),
        "Options Flow":    ("📈", _opt_row),
    }
    cards = []
    # 1. Market Temperature gauge — leads with one big visual
    cards.append(_market_temperature_html(b, dj))
    # 2. Top news SHAKING the market (high-impact filter)
    cards.append(_market_moving_news_html())
    # 3. Market snapshot — 8-cell hero stats grid
    cards.append(_market_snapshot_html(b, dj))
    # 4. Market context (futures, treasuries, crypto, commodities, credit)
    cards.append(_market_context_html(b))
    # 5. Sector heatmap
    cards.append(_sector_heatmap_html(dj))
    # 6. Multi-Signal Spotlight — cross-section tickers with full detail
    cards.append(_multi_signal_spotlight(sections, news))
    # 4. Leadership signals (top industries, 52w hi/lo)
    cards.append(_leadership_signals_html(b, dj))
    # 5. System status
    cards.append(_system_status_html(b))
    # 6. Risk Dashboard (portfolio-level metrics)
    cards.append(_risk_dashboard_html())
    # 7. Open positions watch
    cards.append(_open_positions_watch_html())
    # 8. Yesterday's Audit (D1 outcomes)
    cards.append(_yesterdays_audit_html())
    # 9. Earnings density next 5d
    cards.append(_earnings_density_html())
    # 10. Evening: recap + extras
    if mode == "evening" and evening_extras:
        cards.append(_evening_recap_card(evening_extras))
        cards.append(_pnl_attribution_html())
        cards.append(_amc_results_html())
        cards.append(_market_top_movers_html(b))
        cards.append(_tomorrow_prep_html())
    # 11. The 5 strategy sections
    for sect, (icon, fmt) in formatters.items():
        cards.append(_section_html(sect, icon, sections.get(sect) or [], cross_tags_map, fmt, news))
    # 12. Tactical · Implied-move plays (only if there are earnings ≤7d)
    cards.append(_tactical_opportunities_html(b))
    # 13. Universe news at the bottom
    cards.append(_universe_news_html(universe_news))
    cards_html = "\n".join(c for c in cards if c)
    mode_label = "Daily Newsletter" if mode == "morning" else "Evening Recap"
    head_sub = (
        f"Regime: <b>{_esc(regime.get('regime4','—'))}</b>  ·  "
        f"VIX <b>{_esc(regime.get('vix','—'))}</b>  ·  "
        f"SPY 1m <b>{_esc(regime.get('spy_1m_ret','—'))}%</b>  ·  "
        f"<b>{sum(len(v) for v in sections.values())}</b> picks across 5 categories  ·  "
        f"<b>{sum(len(v) for v in news.values())}</b> headlines"
    )
    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<title>Kairos {_esc(mode_label)} — {_esc(when)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700;800&family=DM+Serif+Display:ital@1&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg-0:    #0a0d12;
    --bg-1:    #11151d;
    --bg-2:    #161b25;
    --line:    #1d2535;
    --line-2:  #2a3346;
    --ink:     #e7edf6;
    --ink-1:   #c2cbe0;
    --ink-2:   #8b9bbf;
    --ink-3:   #5e6e90;
    --gn:      #5be57c;
    --rd:      #ff6b6b;
    --am:      #ffb95c;
    --cu:      #d97757;
    --bl:      #62b3ff;
    --vi:      #b48cff;
    --mono:    'JetBrains Mono', 'SF Mono', Menlo, monospace;
    --sans:    'Inter', -apple-system, system-ui, sans-serif;
    --serif:   'DM Serif Display', 'GT Sectra', Georgia, serif;
  }}
  * {{ box-sizing: border-box; }}
  body {{ font: 14px/1.5 var(--sans); background:var(--bg-0); color:var(--ink); margin:0; padding:20px 12px; }}
  .wrap {{ max-width: 1100px; margin: 0 auto; }}

  /* HERO */
  .hero {{
    padding: 22px 26px; border:1px solid var(--line); border-radius:8px;
    background: linear-gradient(135deg, rgba(217,119,87,.06), rgba(91,229,124,.04) 40%, transparent 80%);
    margin-bottom: 14px; position:relative; overflow:hidden;
  }}
  .hero::before {{
    content:''; position:absolute; top:0; left:0; right:0; height:2px;
    background: linear-gradient(90deg, var(--cu), var(--gn), var(--bl), var(--vi));
  }}
  .hero .eyebrow {{ font:700 11px var(--mono); letter-spacing:.18em; color:var(--cu);
    text-transform:uppercase; margin-bottom: 6px; }}
  .hero h1 {{ margin:0 0 6px; font:400 36px var(--serif); font-style:italic; color:#fff; line-height:1.1; }}
  .hero h1::first-letter {{ color: var(--cu); }}
  .hero .sub {{ font:500 12.5px var(--mono); color:var(--ink-2); letter-spacing:.04em; }}
  .hero .sub b {{ color:#fff; font-weight:700; }}

  /* CARD */
  .card {{ background:var(--bg-1); border:1px solid var(--line); border-radius:6px;
           margin-bottom:14px; overflow:hidden; }}
  .card-h {{ display:flex; align-items:center; gap:10px; padding:11px 18px;
            border-bottom:1px solid var(--line); background:var(--bg-2);
            font:700 11px var(--mono); letter-spacing:.14em; text-transform:uppercase; color:var(--ink-2); }}
  .card-h .ic {{ font-size:16px; }}
  .card-h .ttl {{ color:var(--ink); }}
  .card-h .card-meta {{ margin-left:auto; color:var(--ink-3); font-size:10px; letter-spacing:.10em; }}

  /* HERO STATS GRID (market snapshot) */
  .hero-grid {{ display:grid; grid-template-columns:repeat(8, 1fr); gap:1px;
                background:var(--line); }}
  @media (max-width: 900px) {{ .hero-grid {{ grid-template-columns: repeat(4, 1fr); }} }}
  .hero-cell {{ background:var(--bg-1); padding:14px 12px; text-align:center; }}
  .hc-v {{ font:700 22px var(--mono); color:#fff; font-variant-numeric:tabular-nums; }}
  .hc-l {{ font:700 9.5px var(--mono); color:var(--ink-3); letter-spacing:.14em; text-transform:uppercase; margin-top:2px; }}
  .hc-s {{ font:500 10px var(--mono); color:var(--ink-2); margin-top:1px; text-transform:uppercase; }}

  /* RISK BANNER */
  .risk-banner {{ padding:11px 18px; font:600 11px var(--mono); color:var(--ink-1); display:flex; gap:18px; flex-wrap:wrap; align-items:baseline; }}
  .risk-banner .rb-l {{ color:var(--ink-3); margin-right:4px; letter-spacing:.12em; }}
  .risk-banner b {{ color:#fff; }}

  /* SECTOR HEATMAP */
  .sh-grid {{ display:grid; grid-template-columns: repeat(4, 1fr); gap:8px; padding:14px 16px; }}
  @media (max-width: 900px) {{ .sh-grid {{ grid-template-columns: repeat(2, 1fr); }} }}
  .sh-cell {{ background:var(--bg-2); border:1px solid var(--line); border-radius:4px;
               padding:10px 12px; min-height:80px; }}
  .sh-tk {{ font:700 11px var(--mono); color:var(--cu); letter-spacing:.10em; }}
  .sh-sec {{ font:500 11px var(--sans); color:var(--ink-1); margin-top:2px; }}
  .sh-perf {{ font:700 17px var(--mono); margin-top:6px; font-variant-numeric:tabular-nums; }}
  .sh-vs {{ font:500 10px var(--mono); color:var(--ink-3); margin-top:0; }}
  .sh-bar {{ height:3px; background:var(--bg-0); border-radius:99px; margin-top:6px; overflow:hidden; }}
  .sh-bar .sh-fill {{ display:block; height:100%; }}

  /* MARKET TEMPERATURE */
  .temp-wrap {{ display:grid; grid-template-columns: 240px 1fr; gap:24px; padding:18px 22px; align-items:center; }}
  @media (max-width: 900px) {{ .temp-wrap {{ grid-template-columns: 1fr; }} }}
  .temp-gauge {{ text-align:center; }}
  .temp-label {{ font:800 16px var(--mono); letter-spacing:.10em; margin-top:-2px; }}
  .temp-comps {{ display:flex; flex-direction:column; gap:8px; }}
  .comp-row {{ display:grid; grid-template-columns: 110px 1fr 30px 70px; align-items:center; gap:10px; font:600 11px var(--mono); }}
  .comp-name {{ color:var(--ink-2); letter-spacing:.06em; }}
  .comp-bar {{ height:8px; background:var(--bg-2); border-radius:99px; overflow:hidden; }}
  .comp-fill {{ display:block; height:100%; border-radius:99px; transition: width 200ms; }}
  .comp-val {{ color:var(--ink); text-align:right; font-weight:800; }}
  .comp-raw {{ color:var(--ink-3); font-size:10px; }}

  /* MARKET MOVING NEWS */
  .mmn-wrap {{ padding:6px 6px 12px; }}
  .mmn-row {{ background:var(--bg-2); margin:8px 12px; padding:10px 14px; border-radius:3px;
              display:grid; grid-template-columns: 24px 1fr; align-items:start; gap:10px; }}
  .mmn-icon {{ font-size:14px; }}
  .mmn-title {{ font:600 13px var(--sans); color:var(--ink-1); text-decoration:none; line-height:1.4; }}
  .mmn-title:hover {{ color:var(--gn); text-decoration:underline; }}
  .mmn-meta {{ grid-column: 2; font:500 10px var(--mono); color:var(--ink-3); margin-top:3px; letter-spacing:.04em; }}

  /* MULTI-SIGNAL SPOTLIGHT */
  .mss-grid {{ display:grid; grid-template-columns: repeat(2, 1fr); gap:12px; padding:14px 18px; }}
  @media (max-width: 900px) {{ .mss-grid {{ grid-template-columns: 1fr; }} }}
  .mss-card {{ background:var(--bg-2); border:1px solid var(--line); border-left:3px solid var(--gn);
                border-radius:4px; padding:12px 14px; }}
  .mss-h {{ display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap; margin-bottom:8px; }}
  .mss-l {{ display:flex; align-items:center; gap:10px; }}
  .mss-r {{ display:flex; align-items:center; gap:6px; }}
  .mss-tk {{ font:800 16px var(--mono); color:#fff; }}
  .mss-px {{ font:600 13px var(--mono); color:var(--ink-1); font-variant-numeric:tabular-nums; }}
  .mss-count {{ background:rgba(91,229,124,.14); color:var(--gn); padding:3px 9px; border-radius:99px;
                font:700 10px var(--mono); letter-spacing:.05em; border:1px solid rgba(91,229,124,.30); }}
  .mss-signals {{ font:500 11.5px var(--sans); color:var(--ink-2); line-height:1.6; margin-bottom:8px;
                   padding-bottom:8px; border-bottom:1px dashed var(--line); }}
  .mss-signals b {{ color:var(--ink); }}
  .mss-plan {{ font:500 11.5px var(--mono); color:var(--ink-2); margin-bottom:6px; }}
  .mss-plan .lbl {{ color:var(--ink-3); }}
  .mss-plan b {{ color:var(--ink); }}

  /* MARKET CONTEXT (futures/treasuries/crypto/commodities) */
  .mc-row-label {{ font:700 9px var(--mono); letter-spacing:.16em; text-transform:uppercase;
                    color:var(--cu); padding:8px 18px 4px; background:var(--bg-2); }}
  .mc-grid {{ display:grid; grid-template-columns:repeat(4, 1fr); gap:1px; background:var(--line); }}
  @media (max-width: 900px) {{ .mc-grid {{ grid-template-columns:repeat(2, 1fr); }} }}
  .mc-cell {{ background:var(--bg-1); padding:10px 14px; }}
  .mc-lbl {{ font:700 9px var(--mono); letter-spacing:.12em; color:var(--ink-3); text-transform:uppercase; }}
  .mc-v   {{ font:700 16px var(--mono); color:var(--ink); margin-top:3px; font-variant-numeric:tabular-nums; }}
  .mc-c   {{ font:600 11px var(--mono); margin-top:1px; font-variant-numeric:tabular-nums; }}

  /* LEADERSHIP CHIPS */
  .ld-chip {{ background:var(--bg-2); padding:8px 12px; border-radius:3px;
              border-left:3px solid var(--cu); }}
  .ld-name {{ font:600 12px var(--sans); color:var(--ink); }}
  .ld-meta {{ font:500 11px var(--mono); color:var(--ink-3); margin-top:2px; }}
  .ld-meta b {{ color:var(--ink); font-weight:700; }}

  /* SYSTEM STATUS */
  .ss-grid {{ display:grid; grid-template-columns:repeat(3, 1fr); gap:1px; background:var(--line); }}
  @media (max-width: 900px) {{ .ss-grid {{ grid-template-columns: repeat(2, 1fr); }} }}
  .ss-cell {{ background:var(--bg-1); padding:12px 16px; }}
  .ss-lbl {{ font:700 9px var(--mono); letter-spacing:.14em; text-transform:uppercase; color:var(--ink-3); }}
  .ss-val {{ font:700 14px var(--mono); color:var(--ink); margin-top:4px; }}
  .ss-sub {{ font:500 10px var(--mono); color:var(--ink-2); margin-top:2px; }}
  .sleeve-chip {{ display:inline-block; background:var(--bg-2); border:1px solid var(--line);
                   padding:2px 8px; margin:2px 4px 2px 0; border-radius:99px;
                   font:600 9.5px var(--mono); color:var(--ink-1); }}

  /* OPEN POSITIONS TABLE */
  .pos-tbl {{ width:100%; border-collapse:collapse; font:500 12px var(--mono); font-variant-numeric:tabular-nums; }}
  .pos-tbl thead th {{ background:var(--bg-2); color:var(--ink-3);
                         font:700 9.5px var(--mono); letter-spacing:.12em; text-transform:uppercase;
                         padding:10px 12px; text-align:left; border-bottom:1px solid var(--line); }}
  .pos-tbl thead th.r {{ text-align:right; }}
  .pos-tbl td {{ padding:8px 12px; border-bottom:1px solid var(--line); color:var(--ink-1); }}
  .pos-tbl td.r {{ text-align:right; }}
  .pos-tbl tbody tr:hover {{ background:var(--bg-2); }}

  /* PICK ROWS (5 sections) */
  .row {{ padding:14px 18px; border-bottom:1px solid var(--line); }}
  .row:last-child {{ border-bottom:none; }}
  .row-top {{ display:flex; justify-content:space-between; align-items:center; gap:14px; flex-wrap:wrap; }}
  .row-l {{ display:flex; gap:10px; align-items:center; font:600 14px var(--mono); }}
  .row-r {{ display:flex; gap:6px; align-items:center; flex-wrap:wrap; }}
  .tk {{ color:#fff; font:700 15px var(--mono); letter-spacing:.02em; min-width:55px; }}
  .px {{ color:var(--ink-1); font-variant-numeric:tabular-nums; }}
  .spark {{ display:inline-block; vertical-align:middle; }}
  .stars-wrap {{ font-size:13px; }}
  .stars {{ color:#ffd866; letter-spacing:.5px; }}

  /* Score bar */
  .sb-wrap {{ display:inline-flex; align-items:center; gap:6px; }}
  .sb-num {{ font:800 14px var(--mono); min-width:24px; text-align:right; }}
  .sb-bar {{ width:60px; height:5px; background:var(--bg-2); border-radius:99px; overflow:hidden; }}
  .sb-fill {{ display:block; height:100%; border-radius:99px; }}

  /* Chips */
  .t-chip {{ background:rgba(217,119,87,.16); color:var(--cu); padding:2px 7px;
              border-radius:2px; font:700 9.5px var(--mono); letter-spacing:.10em; border:1px solid rgba(217,119,87,.30); }}
  .metric-chip {{ background:var(--bg-2); color:var(--ink-1); padding:2px 8px;
                   border-radius:2px; font:600 10px var(--mono); border:1px solid var(--line); }}
  .v-chip {{ padding:2px 8px; border-radius:2px; font:700 10px var(--mono); letter-spacing:.06em; }}
  .status-pill {{ padding:2px 8px; border-radius:2px; font:700 10px var(--mono); letter-spacing:.06em; }}
  .ml-edge {{ font:800 18px var(--mono); font-variant-numeric:tabular-nums; }}
  .ml-edge-label {{ font:600 10px var(--mono); color:var(--ink-3); text-transform:uppercase; letter-spacing:.10em; }}

  /* Trade plan strip */
  .row-trade {{ font:500 11.5px var(--mono); color:var(--ink-2); margin-top:8px; padding-top:8px;
                 border-top:1px dashed var(--line); }}
  .row-trade .lbl {{ color:var(--ink-3); }}
  .row-trade b {{ color:var(--ink); font-weight:600; }}
  .row-trade .sep {{ color:var(--ink-3); margin:0 6px; }}

  /* Cross-tag (multi-signal) */
  .x-tag {{ background:rgba(91,229,124,.12); color:var(--gn); padding:2px 7px;
            border-radius:99px; font:700 9px var(--mono); letter-spacing:.05em;
            border:1px solid rgba(91,229,124,.30); }}

  /* News */
  .news-row {{ font:500 12px var(--sans); color:var(--ink-2); margin-top:5px;
               padding:4px 12px; background:var(--bg-2); border-left:2px solid var(--cu); }}
  .news-row a {{ color:var(--ink-1); text-decoration: none; }}
  .news-row a:hover {{ color:var(--gn); text-decoration: underline; }}

  hr {{ border:0; border-top:1px solid var(--line); margin:0; }}

  /* Footer */
  .ft {{ margin-top: 22px; padding: 14px; color:var(--ink-3);
         font:500 10.5px var(--mono); letter-spacing:.04em; text-align:center; }}
  .ft a {{ color:var(--cu); text-decoration:none; }}
  .ft a:hover {{ text-decoration:underline; }}
</style></head>
<body><div class="wrap">
  <div class="hero">
    <div class="eyebrow">{_esc(mode_label)}</div>
    <h1>Kairos — {_esc(when)}</h1>
    <div class="sub">{head_sub}</div>
  </div>
  {cards_html}
  <div class="ft">
    Generated by <code>scripts/daily_newsletter.py</code> · Mon-Fri 06:30 PT (morning) · 17:00 PT (evening)<br>
    <a href="{DASHBOARD}">{DASHBOARD}</a>
  </div>
</div></body></html>"""


# ────────────────────────────────────────────────────────────────────────────
# Slack render
# ────────────────────────────────────────────────────────────────────────────
def _slack_payload(sections: dict, news: dict, regime: dict, when: str,
                   snapshot_url: str | None, universe_news: list,
                   mode: str = "morning", evening_extras: dict | None = None) -> dict:
    cross_tags_map = _cross_tags(sections)
    title = "Kairos Daily" if mode == "morning" else "Kairos Evening Recap"
    icon  = "📨" if mode == "morning" else "🌆"
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn",
            "text": f"{icon} *{title} — {when}*"}},
        {"type": "context", "elements": [{"type": "mrkdwn",
            "text": f"Regime *{regime.get('regime4','—')}* · VIX *{regime.get('vix','—')}* "
                   f"· SPY 1m *{regime.get('spy_1m_ret','—')}%*"}]},
        {"type": "divider"},
    ]

    # Evening: prepend recap summary
    if mode == "evening" and evening_extras:
        morn = evening_extras.get("morning_results") or []
        closes = evening_extras.get("closes_today") or []
        earn = evening_extras.get("earnings_results") or []
        body_lines = []
        if morn:
            body_lines.append("*Morning picks realized:*\n" + "\n".join(
                f"`{p['ticker']:<5}` entry {_fmt_px(p.get('entry'))} → close {_fmt_px(p.get('close'))} *{p.get('pct_move','—')}* {p.get('status','—')}"
                for p in morn[:10]
            ))
        if closes:
            body_lines.append(f"*Closed today ({len(closes)}):* "
                + ", ".join(f"`{t.get('ticker','—')}` {'+'  if (t.get('realized_pnl') or t.get('pnl') or 0)>=0 else ''}${(t.get('realized_pnl') or t.get('pnl') or 0):.2f}"
                            for t in closes[:8]))
        if earn:
            body_lines.append(f"*Earnings today ({len(earn)}):* "
                + ", ".join(f"`{o.get('ticker')}` " + ("✅" if o.get("beat") else "❌")
                          + (f"+{o.get('surprise_pct'):.1f}%" if o.get('surprise_pct') is not None else "")
                          for o in earn[:12]))
        if body_lines:
            blocks.append({"type": "section", "text": {"type": "mrkdwn",
                "text": "*🌆 TODAY'S RECAP*\n" + "\n\n".join(body_lines)}})

    def cross_str(tk, this):
        extras = cross_tags_map.get(tk, set()) - {this}
        return (" 🌟 " + ",".join(sorted(extras))) if extras else ""

    def news_str(tk):
        items = news.get(tk) or []
        if not items: return ""
        # 2 headlines per ticker
        lines = []
        for n in items[:2]:
            t = (n.get("title") or "")[:110]
            lines.append(f"        📰 {t}")
        return "\n" + "\n".join(lines)

    # High Conviction
    hc = sections.get("High Conviction") or []
    if hc:
        body = "\n".join(
            f"`{p['ticker']:<5}` {_fmt_px(p.get('price')):>8} sc *{p.get('score',0):.0f}* {p.get('conviction_tier','')} "
            f"· {(p.get('setup_family') or '')[:18]}{cross_str(p['ticker'], 'High Conviction')}"
            f"{news_str(p['ticker'])}"
            for p in hc
        )
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
            "text": f"*🎯 HIGH CONVICTION*\n{body}"}})

    # Screener
    sc = sections.get("Screener") or []
    if sc:
        body = "\n".join(
            f"`{p['ticker']:<5}` {_fmt_px(p.get('price')):>8} sc *{p.get('score',0):.0f}* "
            f"· {(p.get('setup_family') or '')[:18]}{cross_str(p['ticker'], 'Screener')}"
            f"{news_str(p['ticker'])}"
            for p in sc
        )
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
            "text": f"*📊 SCREENER*\n{body}"}})

    # Momentum
    mm = sections.get("Momentum") or []
    if mm:
        body = "\n".join(
            f"`{p['ticker']:<5}` {_fmt_px(p.get('price')):>8} comp *{p.get('composite',0):.0f}* "
            f"Sh{p.get('sharpe_126d',0):.1f}{cross_str(p['ticker'], 'Momentum')}"
            f"{news_str(p['ticker'])}"
            for p in mm
        )
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
            "text": f"*🚀 MOMENTUM*\n{body}"}})

    # ML Edge
    ml = sections.get("ML Edge") or []
    if ml:
        body = "\n".join(
            f"`{p['ticker']:<5}` edge *{p['edge']:+.1f}* {p.get('verdict','')}/{p.get('level','')} "
            f"conf {p.get('conf','')}{cross_str(p['ticker'], 'ML Edge')}"
            f"{news_str(p['ticker'])}"
            for p in ml
        )
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
            "text": f"*🤖 ML EDGE (5d)*\n{body}"}})

    # Options Flow
    op = sections.get("Options Flow") or []
    if op:
        body = "\n".join(
            f"`{p['ticker']:<5}` {_fmt_px(p.get('price')):>8} *{p.get('status','')}* PCR {(p.get('put_call_ratio') or 0):.2f} "
            f"ATM ${(p.get('atm_strike') or 0):.0f}({(p.get('atm_dte') or 0):.0f}d) {_fmt_money(p.get('premium_total_$'))}"
            f"{cross_str(p['ticker'], 'Options Flow')}"
            f"{news_str(p['ticker'])}"
            for p in op
        )
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
            "text": f"*📈 OPTIONS FLOW*\n{body}"}})

    # Universe news (macro / market-wide)
    if universe_news:
        body = "\n".join(
            f"• <{n.get('link','')}|{(n.get('title') or '')[:120]}> — _{n.get('source','')}_"
            for n in universe_news[:8]
        )
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
            "text": f"*🌍 UNIVERSE NEWS*\n{body}"}})

    full_link = snapshot_url or f"{DASHBOARD}/reports/latest/daily-newsletter"
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn",
        "text": f"<{full_link}|📖 Open full newsletter ↗> · <{DASHBOARD}|Dashboard ↗>"}]})

    return {"text": f"{title} — {when}", "blocks": blocks}


# ────────────────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────────────────
def _evening_extras() -> dict:
    """Build evening-mode extras: realized morning picks + closed trades + earnings outcomes."""
    out = {"morning_results": [], "closes_today": [], "earnings_results": []}
    today = _today()

    # Closed trades today
    try:
        port = _safe_load(REPO / "data" / "portfolio_state.json") or {}
        out["closes_today"] = [
            t for t in (port.get("closed_trades") or [])
            if str(t.get("close_date") or t.get("exit_date") or "").startswith(today)
        ]
    except Exception: pass

    # Earnings outcomes today
    try:
        outcomes_path = REPO / "data" / "earnings_outcomes.jsonl"
        if outcomes_path.exists():
            for line in outcomes_path.read_text().splitlines():
                if not line.strip(): continue
                try: r = json.loads(line)
                except Exception: continue
                if str(r.get("captured_at","")).startswith(today):
                    out["earnings_results"].append(r)
    except Exception: pass

    # Morning picks realized — read this morning's state file + live quotes
    try:
        morn_state = _safe_load(REPO / "data" / "daily_newsletter_state.json") or {}
        morn_tickers = morn_state.get("morning_tickers") or []
        if not morn_tickers:
            # Fall back to today's BUY candidates from bundle
            morn_tickers = [p.get("ticker") for p in _high_conviction(_bundle()) if p.get("ticker")]
        if morn_tickers:
            import data_fetcher as df
            for tk in morn_tickers[:12]:
                try:
                    q = df.get_polygon_snapshot(tk) if hasattr(df, "get_polygon_snapshot") else None
                except Exception:
                    q = None
                close = (q or {}).get("last") or (q or {}).get("close") if q else None
                # Best-effort entry from bundle
                bundle_pick = next((p for p in (_bundle().get("buy_candidates") or [])
                                    if p.get("ticker") == tk), None)
                entry = (bundle_pick or {}).get("price") if bundle_pick else None
                pct = None
                status = "—"
                if close and entry:
                    pct = ((close - entry) / entry) * 100
                    status = "✅ winner" if pct > 0.5 else "❌ loser" if pct < -0.5 else "→ flat"
                out["morning_results"].append({
                    "ticker": tk, "entry": entry, "close": close,
                    "pct_move": f"{pct:+.2f}%" if pct is not None else "—",
                    "status": status,
                })
    except Exception as e:
        print(f"evening morning-recap failed: {e}", file=sys.stderr)

    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode",       choices=["morning","evening"], default="morning")
    ap.add_argument("--no-slack",   action="store_true")
    ap.add_argument("--no-snapshot", action="store_true")
    ap.add_argument("--dry-run",    action="store_true")
    ap.add_argument("--force",      action="store_true")
    args = ap.parse_args()

    b = _bundle()
    regime = b.get("regime") or {}
    regime_info = {
        "regime4": regime.get("regime4") or regime.get("regime", "—"),
        "vix": (regime.get("vix") or {}).get("vix_current"),
        "spy_1m_ret": regime.get("spy_1m_ret"),
    }

    sections = {
        "High Conviction": _high_conviction(b),
        "Screener":        _screener_top(b),
        "Momentum":        _momentum_top(),
        "ML Edge":         _ml_edge_top(),
        "Options Flow":    _options_top(),
    }
    # Tickers needing news lookup
    unique_tickers = sorted({
        p.get("ticker") for rows in sections.values() for p in rows if p.get("ticker")
    })
    print(f"mode={args.mode} · sections: {[(k, len(v)) for k,v in sections.items()]}")
    print(f"fetching news for {len(unique_tickers)} unique tickers...")
    news = _fetch_news(unique_tickers, max_age_hours=30)
    print(f"news headlines: {sum(len(v) for v in news.values())} across {len(news)} tickers")

    print("fetching universe news...")
    universe_news = _universe_news(limit=8)
    print(f"universe news: {len(universe_news)} headlines")

    evening_extras = _evening_extras() if args.mode == "evening" else None

    when = datetime.now().strftime("%a %b %-d · %-I:%M %p PT")
    html_doc = _render_html(sections, news, regime_info, when, universe_news,
                            mode=args.mode, evening_extras=evening_extras)

    # Persist snapshot (so /reports/latest/daily-newsletter works)
    snapshot_url = None
    if not args.no_snapshot and not args.dry_run:
        try:
            import db
            snap_kind = "daily-newsletter" if args.mode == "morning" else "evening-recap"
            snap_label = ("Daily Newsletter " if args.mode == "morning" else "Evening Recap ") + when
            snap_id = db.save_html_snapshot(
                kind=snap_kind,
                html_content=html_doc,
                label=snap_label,
                meta={"sections": {k: len(v) for k, v in sections.items()},
                      "n_unique_tickers": len(unique_tickers),
                      "n_with_news":     len(news)},
            )
            snapshot_url = f"{DASHBOARD}/reports/{snap_id}"
            print(f"snapshot saved id={snap_id} → {snapshot_url}")
        except Exception as e:
            print(f"snapshot save failed: {e}", file=sys.stderr)

    if args.dry_run:
        print("\n--- HTML PREVIEW (first 2000 chars) ---")
        print(html_doc[:2000])
        print("\n--- SLACK PAYLOAD (truncated) ---")
        payload = _slack_payload(sections, news, regime_info, when, snapshot_url,
                                 universe_news, mode=args.mode,
                                 evening_extras=evening_extras)
        print(json.dumps(payload, indent=2, default=str)[:3000])
        return 0

    if not args.no_slack:
        webhook = _webhook()
        if not webhook:
            print("SLACK_WEBHOOK_URL not set — skipping Slack post", file=sys.stderr)
        else:
            payload = _slack_payload(sections, news, regime_info, when, snapshot_url,
                                     universe_news, mode=args.mode,
                                     evening_extras=evening_extras)
            ok = _slack(webhook, payload)
            print(f"slack post: {'ok' if ok else 'FAILED'}")

    # State for dedupe + evening recap reference
    h = hashlib.md5("|".join([
        _today(), args.mode,
        *(p.get("ticker","") for v in sections.values() for p in v),
    ]).encode()).hexdigest()[:16]
    state = _safe_load(STATE_PATH) or {}
    state["last_hash"] = h
    state["last_posted_at"] = datetime.now().isoformat()
    state["last_mode"] = args.mode
    if args.mode == "morning":
        # Snapshot of morning picks so evening recap can compute "realized"
        state["morning_tickers"] = [p.get("ticker") for v in sections.values()
                                    for p in v if p.get("ticker")][:25]
        state["morning_at"] = datetime.now().isoformat()
    STATE_PATH.write_text(json.dumps(state, indent=2))
    print(f"newsletter delivered · mode={args.mode} hash={h}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

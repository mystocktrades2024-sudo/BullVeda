#!/usr/bin/env python3
"""morning_newsletter.py — Bloomberg/TradingView-style daily morning brief.

Renders a professional financial-grade HTML newsletter with:
  - Market snapshot hero (SPY/QQQ/IWM/VIX as big numbers with sparklines)
  - Top conviction picks with 20-day sparklines + key levels
  - Sector heatmap (color-coded grid)
  - Strategy sleeve activity panel
  - This-week macro calendar
  - Risk dashboard
  - Today's actionable insight
  - Earnings on deck

Output:
  cache/morning_newsletter_<DATE>.html
  DB html_snapshots kind='morning-newsletter'
  https://trade.mystockholding.com/reports/latest/morning-newsletter
  Slack summary post with deep-link

Schedule: Mon-Fri 7:45am PT via launchd
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


# ─── data gathering ──────────────────────────────────────────────────────────

def _load_bundle() -> dict:
    p = REPO / "cache" / "last_bundle.json"
    return json.loads(p.read_text()) if p.exists() else {}


def _load_portfolio() -> dict:
    p = REPO / "data" / "portfolio_state.json"
    return json.loads(p.read_text()) if p.exists() else {}


def _rolling_sharpe() -> dict:
    try:
        from decision_engine import compute_rolling_sharpe_kill_state
        cfg = json.loads((REPO / "config" / "config.json").read_text())
        return compute_rolling_sharpe_kill_state(cfg)
    except Exception:
        return {}


def _upcoming_macro(days: int = 14) -> list[dict]:
    try:
        import macro_calendar as mc
        today = date.today()
        out = []
        for ev in mc._MACRO_EVENTS_2026:
            ed = datetime.fromisoformat(ev["date"]).date()
            delta = (ed - today).days
            if 0 <= delta <= days:
                out.append({**ev, "days_until": delta})
        return out[:5]
    except Exception:
        return []


def _sparkline_data(ticker: str, n_bars: int = 20) -> tuple[list[float], float]:
    """Return (closes, pct_change_period) for a ticker."""
    try:
        from data_archive import load_ticker
        df = load_ticker(ticker)
        if df is None or len(df) < n_bars:
            return [], 0
        closes = df["Close"].tail(n_bars).tolist() if "Close" in df.columns else df["close"].tail(n_bars).tolist()
        closes = [float(c) for c in closes]
        if len(closes) < 2 or closes[0] == 0:
            return closes, 0
        pct = (closes[-1] - closes[0]) / closes[0] * 100
        return closes, round(pct, 2)
    except Exception:
        return [], 0


def _make_sparkline_svg(closes: list[float], width: int = 80, height: int = 24,
                         color: str = None) -> str:
    """Render a minimal SVG sparkline."""
    if len(closes) < 2:
        return ""
    lo, hi = min(closes), max(closes)
    rng = hi - lo if hi > lo else 1
    pts = []
    for i, c in enumerate(closes):
        x = (i / (len(closes) - 1)) * width
        y = height - ((c - lo) / rng) * height
        pts.append(f"{x:.1f},{y:.1f}")
    if color is None:
        color = "#00d68f" if closes[-1] >= closes[0] else "#ff4d4f"
    return (f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
            f'style="vertical-align:middle">'
            f'<polyline fill="none" stroke="{color}" stroke-width="1.5" points="{" ".join(pts)}"/>'
            f'<circle cx="{pts[-1].split(",")[0]}" cy="{pts[-1].split(",")[1]}" '
            f'r="1.8" fill="{color}"/></svg>')


def _sleeve_fires(bundle: dict) -> dict[str, list[dict]]:
    all_rows = (bundle.get("all_scored") or []) + \
               (bundle.get("buy_candidates") or []) + \
               (bundle.get("watch_list") or [])
    seen, fires = set(), {}
    for r in all_rows:
        if not isinstance(r, dict):
            continue
        t = r.get("ticker")
        if t in seen:
            continue
        seen.add(t)
        sf = r.get("setup_family") or ""
        if sf in ("Momentum Continuation", "Defensive Rotation", "Mean Reversion",
                   "PEAD", "Insider Cluster", "ESP Play"):
            fires.setdefault(sf, []).append(r)
    return fires


def _sector_heatmap(bundle: dict) -> list[dict]:
    """Build sector heatmap data from bundle.sector_etf or all_scored grouped."""
    se = bundle.get("sector_etf") or bundle.get("sector_etf_data") or {}
    out = []
    sectors = [
        ("XLK", "Technology"), ("XLF", "Financials"), ("XLV", "Healthcare"),
        ("XLY", "Consumer Disc"), ("XLP", "Cons Staples"), ("XLI", "Industrials"),
        ("XLE", "Energy"), ("XLU", "Utilities"), ("XLB", "Materials"),
        ("XLRE", "Real Estate"), ("XLC", "Comm Svcs"),
    ]
    for etf, name in sectors:
        d = se.get(etf) if isinstance(se, dict) else {}
        if isinstance(d, dict):
            chg = d.get("pct_change_1d") or d.get("daily_change_pct") or d.get("perf_1d") or 0
            try:
                chg = float(chg)
            except (TypeError, ValueError):
                chg = 0
        else:
            chg = 0
        # If bundle doesn't have it, try from data_archive
        if chg == 0:
            closes, pct = _sparkline_data(etf, n_bars=2)
            chg = pct
        out.append({"etf": etf, "name": name, "pct_1d": chg})
    return out


def _yesterday_recap() -> dict:
    try:
        import db
        conn = db.get_conn()
        today = date.today().isoformat()
        rows = conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(pnl_pct), 0) AS total_pnl FROM closed_trades WHERE substr(exit_date,1,10) = ?",
            (today,)
        ).fetchone()
        return {"closed_today": rows["n"] if rows else 0,
                "total_pnl_pct": rows["total_pnl"] if rows else 0}
    except Exception:
        return {"closed_today": 0, "total_pnl_pct": 0}


def _upcoming_earnings(bundle: dict, days: int = 7) -> list[dict]:
    """Tickers reporting earnings in next N days, sourced from earnings_watchlist."""
    try:
        ew = json.loads((REPO / "data" / "earnings_watchlist.json").read_text())
        watchlist = ew.get("watchlist") or []
        today = date.today()
        out = []
        for w in watchlist:
            ed_str = w.get("earnings_date")
            if not ed_str:
                continue
            try:
                ed = datetime.fromisoformat(ed_str).date()
                delta = (ed - today).days
                if 0 <= delta <= days:
                    out.append({**w, "days_until": delta})
            except Exception:
                continue
        out.sort(key=lambda x: x["days_until"])
        return out[:8]
    except Exception:
        return []


# ─── HTML rendering ─────────────────────────────────────────────────────────

def _pct_color(p: float) -> str:
    if p > 0.5: return "#00d68f"
    if p < -0.5: return "#ff4d4f"
    if p > 0: return "#7cd3a8"
    if p < 0: return "#e89195"
    return "#888"


def _pct_bg_color(p: float) -> str:
    """Background tint for heatmap cells based on % change."""
    if p > 2: return "rgba(0, 214, 143, 0.35)"
    if p > 1: return "rgba(0, 214, 143, 0.20)"
    if p > 0.3: return "rgba(0, 214, 143, 0.10)"
    if p < -2: return "rgba(255, 77, 79, 0.35)"
    if p < -1: return "rgba(255, 77, 79, 0.20)"
    if p < -0.3: return "rgba(255, 77, 79, 0.10)"
    return "rgba(255, 255, 255, 0.04)"


def _render_html(report: dict) -> str:
    bundle = report["bundle"]
    regime = bundle.get("regime", {})
    buys = bundle.get("buy_candidates") or []
    watch = bundle.get("watch_list") or []
    sleeves = report["sleeves"]
    rs = report["rolling_sharpe"]
    pf = report["portfolio"]
    macro = report["macro"]
    recap = report["recap"]
    earnings = report["earnings"]
    sector_map = report["sector_heatmap"]

    today_str = date.today().strftime("%A · %B %-d, %Y").upper()
    time_str = datetime.now().strftime("%-I:%M %p PT")
    regime4 = regime.get("regime4", "unknown")
    spy_price = regime.get("spy_price") or 0
    vix = regime.get("vix_current") or 0
    breadth = regime.get("breadth_pct_50d") or 50

    # Hero indices (SPY, QQQ, IWM, VIX) with sparklines
    indices = []
    for etf, label in [("SPY", "S&P 500"), ("QQQ", "NASDAQ"), ("IWM", "Russell 2K"), ("VIX", "VIX")]:
        closes, pct = _sparkline_data(etf, n_bars=20)
        if closes:
            spark = _make_sparkline_svg(closes, width=100, height=28)
            last = closes[-1]
            color = _pct_color(pct)
            indices.append(f"""
            <div class="hero-cell">
              <div class="hero-label">{label}</div>
              <div class="hero-num">{last:,.2f}</div>
              <div class="hero-spark">{spark}</div>
              <div class="hero-pct" style="color:{color}">{'▲' if pct >= 0 else '▼'} {abs(pct):.2f}%</div>
            </div>""")

    # Top picks with 20-day sparklines
    pick_cards = []
    for r in buys[:6]:
        ticker = r.get("ticker", "?")
        score = r.get("score", 0)
        sector_name = (r.get("sector") or "—")[:14]
        setup = (r.get("setup_family") or "—")
        tp = r.get("trade_plan") or {}
        price = r.get("price", 0)
        entry_lo = tp.get("entry_low") or tp.get("primary_zone_low") or price
        entry_hi = tp.get("entry_high") or tp.get("primary_zone_high") or price
        stop = tp.get("stop", 0)
        t1 = tp.get("target1", 0)
        t2 = tp.get("target2", 0)
        rr = tp.get("rr_ratio") or 0
        sharpe = r.get("sharpe_126d") or 0
        pct_1d = r.get("pct_chg") or 0
        sparkline_closes, sparkline_pct = _sparkline_data(ticker, n_bars=20)
        spark = _make_sparkline_svg(sparkline_closes, width=90, height=22) if sparkline_closes else ""
        in_zone = (entry_lo <= price <= entry_hi) if (price and entry_lo and entry_hi) else False
        zone_dot = '<span class="zone-on">●</span>' if in_zone else '<span class="zone-off">○</span>'
        pct_color = _pct_color(pct_1d)
        pct_arrow = '▲' if pct_1d >= 0 else '▼'

        pick_cards.append(f"""
        <tr class="pick-row">
          <td class="cell-ticker">
            <div class="ticker-big">{ticker}</div>
            <div class="ticker-sub">{sector_name}</div>
          </td>
          <td class="cell-spark">{spark}<div class="spark-pct" style="color:{pct_color}">{pct_arrow} {abs(pct_1d):.2f}%</div></td>
          <td class="cell-price"><div class="price-big">${price:.2f}</div><div class="price-sub">126d Sharpe {sharpe:.2f}</div></td>
          <td class="cell-score"><div class="score-big">{score}</div><div class="score-sub">R:R {rr:.1f}</div></td>
          <td class="cell-setup"><div class="setup-tag">{setup}</div></td>
          <td class="cell-plan">
            <div>Entry <b>${entry_lo:.0f}–${entry_hi:.0f}</b> {zone_dot}</div>
            <div class="stop-target">Stop <b style="color:#ff8896">${stop:.0f}</b> · T1 <b style="color:#7cd3a8">${t1:.0f}</b> · T2 <b style="color:#00d68f">${t2:.0f}</b></div>
          </td>
        </tr>""")

    pick_table = "".join(pick_cards) if pick_cards else \
        f'<tr><td colspan="6" style="padding:24px;text-align:center;color:#888">No BUY-tier picks today · {len(watch)} on WATCH list</td></tr>'

    # Sector heatmap
    heatmap_cells = []
    for sec in sector_map:
        pct = sec["pct_1d"]
        bg = _pct_bg_color(pct)
        color = _pct_color(pct)
        sign = '▲' if pct >= 0 else '▼'
        heatmap_cells.append(f"""
        <div class="heat-cell" style="background:{bg}">
          <div class="heat-etf">{sec['etf']}</div>
          <div class="heat-name">{sec['name']}</div>
          <div class="heat-pct" style="color:{color}">{sign} {abs(pct):.2f}%</div>
        </div>""")

    # Strategy sleeve panel
    sleeve_blocks = []
    sleeve_icons = {
        "Momentum Continuation": "🚀", "Defensive Rotation": "🛡️",
        "Mean Reversion": "🔄", "PEAD": "🎯",
        "Insider Cluster": "👥", "ESP Play": "📊",
    }
    for name in ["Momentum Continuation", "Mean Reversion", "PEAD",
                  "Defensive Rotation", "Insider Cluster", "ESP Play"]:
        hits = sleeves.get(name) or []
        icon = sleeve_icons.get(name, "•")
        if hits:
            tickers = " ".join(f'<code class="ticker-chip">{h.get("ticker", "?")}</code>' for h in hits[:5])
            more = f' <span class="more">+{len(hits)-5}</span>' if len(hits) > 5 else ''
            sleeve_blocks.append(f"""
            <div class="sleeve-block sleeve-active">
              <div class="sleeve-head"><span class="sleeve-icon">{icon}</span><b>{name}</b> <span class="fire-count">{len(hits)} fires</span></div>
              <div class="sleeve-body">{tickers}{more}</div>
            </div>""")
        else:
            sleeve_blocks.append(f"""
            <div class="sleeve-block sleeve-dormant">
              <div class="sleeve-head"><span class="sleeve-icon">{icon}</span><b>{name}</b> <span class="fire-count" style="color:#555">dormant</span></div>
            </div>""")

    # Macro events
    macro_rows = []
    for ev in macro:
        when = "TODAY" if ev["days_until"] == 0 else (f"+{ev['days_until']}d" if ev["days_until"] > 0 else f"{ev['days_until']}d")
        urgency = "high" if ev["days_until"] <= 1 else "med" if ev["days_until"] <= 5 else "low"
        macro_rows.append(f"""
        <div class="macro-row macro-{urgency}">
          <span class="macro-when">{when}</span>
          <span class="macro-type">{ev['type']}</span>
          <span class="macro-label">{ev['label']}</span>
        </div>""")
    if not macro_rows:
        macro_rows.append('<div class="macro-row" style="color:#888">No major macro events in next 14 days.</div>')

    # Earnings on deck
    earn_rows = []
    for e in earnings:
        when = "TODAY" if e["days_until"] == 0 else f"+{e['days_until']}d"
        earn_rows.append(f'<div class="earn-row"><b>{e.get("ticker","?")}</b><span class="earn-when">{when}</span></div>')
    if not earn_rows:
        earn_rows.append('<div class="earn-row" style="color:#888">No earnings tracked next 7 days.</div>')

    # Risk dashboard
    rs_active = rs.get("active", False)
    rs_sharpe = rs.get("sharpe", 0)
    rs_thresh = rs.get("threshold", -0.5)
    rs_n = rs.get("n", 0)
    rs_color = "#ff4d4f" if rs_active else ("#ffb800" if isinstance(rs_sharpe, (int, float)) and rs_sharpe < rs_thresh + 0.10 else "#00d68f")
    rs_label = "KILL ACTIVE" if rs_active else ("AT EDGE" if isinstance(rs_sharpe, (int, float)) and rs_sharpe < rs_thresh + 0.10 else "HEALTHY")
    open_n = len(pf.get("positions") or [])
    equity = pf.get("equity") or pf.get("cash") or 0

    # Today's insight
    insight_parts = []
    if rs_active:
        insight_parts.append('<span class="urgent">⚠️ Rolling Sharpe kill ACTIVE — all new BUYs HALTED.</span>')
    elif isinstance(rs_sharpe, (int, float)) and rs_sharpe < rs_thresh + 0.05:
        insight_parts.append(f'<span class="warn">⚠️ Rolling Sharpe at edge ({rs_sharpe:+.3f} vs {rs_thresh:+.2f}) — one losing trade triggers kill.</span>')
    pead_fires = sleeves.get("PEAD") or []
    mr_fires = sleeves.get("Mean Reversion") or []
    if pead_fires:
        names = ", ".join(h.get("ticker", "?") for h in pead_fires[:3])
        insight_parts.append(f'🎯 <b>PEAD active</b>: {names} — post-earnings drift candidates.')
    if mr_fires:
        names = ", ".join(h.get("ticker", "?") for h in mr_fires[:3])
        insight_parts.append(f'🔄 <b>Mean Reversion firing</b>: {names} — oversold-with-EMA200-floor bounces.')
    if regime4 == "risk_on_choppy":
        insight_parts.append('Regime is choppy — Pullback + Mean Reversion are the alpha sleeves. Momentum + Defensive correctly dormant.')
    if not insight_parts:
        insight_parts.append('Quiet morning. Watch entry triggers on the WATCH list.')
    insight_text = "<br><br>".join(insight_parts)

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>SwingTrade · Morning Brief · {date.today().isoformat()}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  * {{ box-sizing:border-box; }}
  body {{ background:#000; color:#e8e8e8; margin:0;
         font-family:'Inter',-apple-system,BlinkMacSystemFont,Helvetica,Arial,sans-serif;
         font-feature-settings:'tnum' 1, 'ss01' 1; }}
  .frame {{ max-width:880px; margin:0 auto; padding:0 16px 40px; }}

  /* Masthead */
  .masthead {{ padding:24px 0 16px; border-bottom:2px solid #ff7a00; margin-bottom:0; }}
  .masthead-row {{ display:flex; align-items:baseline; gap:16px; }}
  .brand {{ font-size:28px; font-weight:800; letter-spacing:-0.5px;
           color:#fff; line-height:1; }}
  .brand-bar {{ display:inline-block; width:4px; height:24px;
               background:#ff7a00; margin-right:10px; vertical-align:middle; }}
  .edition {{ font-size:11px; color:#888; letter-spacing:2px; text-transform:uppercase;
             font-weight:600; margin-top:6px; }}
  .date-bar {{ font-size:11px; color:#888; font-weight:500; letter-spacing:1px;
              margin-left:auto; text-align:right; }}
  .date-day {{ color:#ff7a00; font-weight:700; }}

  /* Hero strip */
  .hero {{ display:grid; grid-template-columns:repeat(4, 1fr); gap:1px;
          background:#222; padding:1px; margin:0 0 24px;
          border:1px solid #222; }}
  .hero-cell {{ background:#0a0a0a; padding:14px 16px; }}
  .hero-label {{ font-size:10px; color:#888; letter-spacing:1.5px;
                text-transform:uppercase; font-weight:600; }}
  .hero-num {{ font-family:'JetBrains Mono','SF Mono',monospace;
              font-size:22px; font-weight:600; color:#fff; margin-top:4px;
              letter-spacing:-0.5px; }}
  .hero-spark {{ margin-top:4px; }}
  .hero-pct {{ font-size:13px; font-weight:600; margin-top:2px;
              font-family:'JetBrains Mono','SF Mono',monospace; }}

  /* Sections */
  section {{ margin-bottom:28px; }}
  h2 {{ font-size:12px; color:#ff7a00; letter-spacing:2px; text-transform:uppercase;
       font-weight:700; margin:0 0 12px; padding-bottom:6px;
       border-bottom:1px solid #222; }}

  /* Top picks table */
  .picks-table {{ width:100%; border-collapse:collapse;
                 font-family:'Inter',sans-serif; }}
  .picks-table td {{ padding:14px 8px; border-bottom:1px solid #1a1a1a;
                    vertical-align:middle; font-size:13px; }}
  .pick-row:hover {{ background:#0a0a0a; }}
  .cell-ticker {{ width:90px; }}
  .ticker-big {{ font-size:18px; font-weight:700; color:#fff;
                font-family:'JetBrains Mono',monospace; }}
  .ticker-sub {{ font-size:10px; color:#888; margin-top:2px;
                text-transform:uppercase; letter-spacing:0.5px; }}
  .cell-spark {{ width:100px; }}
  .spark-pct {{ font-size:11px; margin-top:2px;
               font-family:'JetBrains Mono',monospace; font-weight:600; }}
  .cell-price {{ width:90px; }}
  .price-big {{ font-size:15px; font-weight:600; color:#fff;
               font-family:'JetBrains Mono',monospace; }}
  .price-sub {{ font-size:10px; color:#888; margin-top:2px; }}
  .cell-score {{ width:70px; }}
  .score-big {{ font-size:20px; font-weight:700; color:#00d4ff;
               font-family:'JetBrains Mono',monospace; }}
  .score-sub {{ font-size:10px; color:#888; margin-top:2px; }}
  .cell-setup {{ width:140px; }}
  .setup-tag {{ display:inline-block; padding:3px 8px; background:#1a1a1a;
               border:1px solid #2a2a2a; border-radius:3px;
               font-size:11px; color:#ddd; }}
  .cell-plan {{ font-size:12px; color:#ccc; font-family:'JetBrains Mono',monospace; }}
  .cell-plan b {{ color:#fff; }}
  .stop-target {{ margin-top:3px; font-size:11px; }}
  .zone-on {{ color:#00d68f; font-size:14px; }}
  .zone-off {{ color:#555; font-size:14px; }}

  /* Sector heatmap */
  .heatmap {{ display:grid; grid-template-columns:repeat(6, 1fr);
             gap:2px; background:#222; padding:1px; border:1px solid #222; }}
  .heat-cell {{ background:#0a0a0a; padding:10px;
               border:1px solid transparent; min-height:62px; }}
  .heat-etf {{ font-size:10px; color:#888; font-weight:600;
              font-family:'JetBrains Mono',monospace; }}
  .heat-name {{ font-size:9px; color:#999; margin-top:1px;
               text-transform:uppercase; letter-spacing:0.3px; }}
  .heat-pct {{ font-size:14px; font-weight:700; margin-top:4px;
              font-family:'JetBrains Mono',monospace; }}

  /* Sleeve panel */
  .sleeves-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:10px; }}
  .sleeve-block {{ background:#0a0a0a; border:1px solid #222;
                  border-radius:4px; padding:12px 14px; }}
  .sleeve-active {{ border-left:3px solid #ff7a00; }}
  .sleeve-dormant {{ opacity:0.6; }}
  .sleeve-head {{ font-size:13px; color:#fff; margin-bottom:6px;
                 display:flex; align-items:center; gap:6px; }}
  .sleeve-head b {{ font-weight:600; flex:1; }}
  .sleeve-icon {{ font-size:14px; }}
  .fire-count {{ font-size:11px; color:#ff7a00; font-weight:600;
                font-family:'JetBrains Mono',monospace; }}
  .sleeve-body {{ font-size:12px; color:#aaa; }}
  .ticker-chip {{ display:inline-block; padding:1px 6px;
                 background:#1a1a1a; border-radius:2px; color:#00d4ff;
                 font-family:'JetBrains Mono',monospace; font-size:11px;
                 margin:1px 2px; }}
  .more {{ color:#666; font-size:11px; }}

  /* Macro + Earnings panels (side by side) */
  .two-col {{ display:grid; grid-template-columns:1.4fr 1fr; gap:18px; }}
  .macro-row {{ display:flex; gap:10px; padding:6px 0;
               border-bottom:1px solid #1a1a1a; font-size:12px; align-items:center; }}
  .macro-row:last-child {{ border-bottom:none; }}
  .macro-when {{ font-family:'JetBrains Mono',monospace; font-weight:700;
                color:#888; width:48px; font-size:11px; }}
  .macro-type {{ background:#1a1a1a; padding:1px 6px; border-radius:2px;
                font-size:10px; font-weight:600; color:#ff7a00; }}
  .macro-label {{ color:#ccc; flex:1; }}
  .macro-high .macro-when {{ color:#ff4d4f; }}
  .macro-med .macro-when {{ color:#ffb800; }}

  .earn-row {{ display:flex; align-items:center; gap:10px;
              padding:5px 0; border-bottom:1px solid #1a1a1a; font-size:12px; }}
  .earn-row:last-child {{ border-bottom:none; }}
  .earn-row b {{ color:#fff; font-family:'JetBrains Mono',monospace; flex:1; }}
  .earn-when {{ color:#888; font-size:11px; font-family:'JetBrains Mono',monospace; }}

  /* Risk dashboard */
  .risk-grid {{ display:grid; grid-template-columns:repeat(4, 1fr);
               gap:1px; background:#222; padding:1px; border:1px solid #222; }}
  .risk-cell {{ background:#0a0a0a; padding:12px 14px; }}
  .risk-label {{ font-size:10px; color:#888; letter-spacing:1px;
                text-transform:uppercase; font-weight:600; }}
  .risk-val {{ font-size:20px; font-weight:700; margin-top:6px;
              font-family:'JetBrains Mono',monospace; color:#fff; }}
  .risk-sub {{ font-size:10px; color:#888; margin-top:3px; }}

  /* Insight */
  .insight-box {{ background:linear-gradient(135deg, #1a1410, #0a0a0a);
                 border-left:3px solid #ff7a00; border-radius:4px;
                 padding:18px 22px; }}
  .insight-text {{ font-size:14px; line-height:1.6; color:#ddd; }}
  .insight-text b {{ color:#fff; font-weight:600; }}
  .urgent {{ color:#ff4d4f; font-weight:600; }}
  .warn {{ color:#ffb800; font-weight:500; }}

  /* Footer */
  footer {{ margin-top:32px; padding-top:18px; border-top:1px solid #222;
           text-align:center; font-size:11px; color:#666; }}
  footer a {{ color:#ff7a00; text-decoration:none; margin:0 14px;
             font-weight:500; letter-spacing:0.5px; }}
  footer a:hover {{ color:#fff; }}
  .disclaimer {{ margin-top:14px; color:#444; font-size:10px;
                line-height:1.5; }}
</style></head>
<body>
<div class="frame">

<div class="masthead">
  <div class="masthead-row">
    <div>
      <div class="brand"><span class="brand-bar"></span>SwingTrade</div>
      <div class="edition">Morning Brief · Pre-Market Edition</div>
    </div>
    <div class="date-bar">
      <div class="date-day">{today_str}</div>
      <div style="margin-top:4px">{time_str}</div>
    </div>
  </div>
</div>

<div class="hero">
  {"".join(indices)}
</div>

<section>
  <h2>Top Conviction · {len(buys)} BUY · {len(watch)} WATCH</h2>
  <table class="picks-table">
    <tbody>{pick_table}</tbody>
  </table>
</section>

<section>
  <h2>Sector Heatmap · 1-Day % Change</h2>
  <div class="heatmap">{"".join(heatmap_cells)}</div>
</section>

<section>
  <h2>Strategy Sleeve Activity · Regime: {regime4}</h2>
  <div class="sleeves-grid">{"".join(sleeve_blocks)}</div>
</section>

<div class="two-col">
  <section>
    <h2>Macro Calendar · Next 14 Days</h2>
    {"".join(macro_rows)}
  </section>
  <section>
    <h2>Earnings on Deck · 7d</h2>
    {"".join(earn_rows)}
  </section>
</div>

<section>
  <h2>Risk Dashboard</h2>
  <div class="risk-grid">
    <div class="risk-cell">
      <div class="risk-label">Rolling Sharpe</div>
      <div class="risk-val" style="color:{rs_color}">{rs_sharpe if isinstance(rs_sharpe, str) else f'{rs_sharpe:+.3f}'}</div>
      <div class="risk-sub" style="color:{rs_color}">{rs_label} · n={rs_n} · thresh {rs_thresh}</div>
    </div>
    <div class="risk-cell">
      <div class="risk-label">Open Positions</div>
      <div class="risk-val">{open_n}</div>
      <div class="risk-sub">Equity ${equity:,.0f}</div>
    </div>
    <div class="risk-cell">
      <div class="risk-label">VIX</div>
      <div class="risk-val">{vix:.1f}</div>
      <div class="risk-sub">{'panic >35' if vix > 35 else 'elevated' if vix > 22 else 'normal'}</div>
    </div>
    <div class="risk-cell">
      <div class="risk-label">Breadth ›50dma</div>
      <div class="risk-val">{breadth:.0f}%</div>
      <div class="risk-sub">{'risk-on' if breadth > 60 else 'mixed' if breadth > 40 else 'risk-off'}</div>
    </div>
  </div>
</section>

<section>
  <h2>Today's Insight</h2>
  <div class="insight-box"><div class="insight-text">{insight_text}</div></div>
</section>

<footer>
  <a href="https://trade.mystockholding.com/kairos.html">Live Dashboard</a>
  <a href="https://trade.mystockholding.com/reports">Report Archive</a>
  <a href="https://trade.mystockholding.com/reports/latest/dashboard">Latest Snapshot</a>
  <div class="disclaimer">
    SwingTrade · Quant-disciplined systematic trading · Paper observation phase ·
    Calibration overlay (docs/claude_md_calibration.md) ·
    Educational use only — not investment advice
  </div>
</footer>

</div></body></html>"""
    return html


def _build_report() -> dict:
    bundle = _load_bundle()
    return {
        "bundle": bundle,
        "sleeves": _sleeve_fires(bundle),
        "rolling_sharpe": _rolling_sharpe(),
        "portfolio": _load_portfolio(),
        "macro": _upcoming_macro(),
        "recap": _yesterday_recap(),
        "earnings": _upcoming_earnings(bundle),
        "sector_heatmap": _sector_heatmap(bundle),
    }


def _slack_summary(report: dict) -> tuple[str, list]:
    bundle = report["bundle"]
    regime = bundle.get("regime", {})
    buys = bundle.get("buy_candidates") or []
    watch = bundle.get("watch_list") or []
    sleeves = report["sleeves"]
    rs = report["rolling_sharpe"]

    today = date.today().strftime("%A, %b %-d")
    regime4 = regime.get("regime4", "unknown")

    text = f"🌅 *Morning Brief — {today}* · regime `{regime4}` · {len(buys)} BUY · {len(watch)} WATCH"
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": "🌅 SwingTrade Morning Brief"}},
        {"type": "section", "text": {"type": "mrkdwn",
         "text": f"*{today}* · Regime: `{regime4}` · SPY `${regime.get('spy_price','?')}` · VIX `{regime.get('vix_current','?')}` · Breadth `{regime.get('breadth_pct_50d','?')}%`"}},
    ]
    if buys:
        top_lines = []
        for r in buys[:3]:
            t = r.get("ticker", "?")
            s = r.get("score", 0)
            rr = (r.get("trade_plan") or {}).get("rr_ratio") or 0
            sf = r.get("setup_family", "?")[:24]
            top_lines.append(f"• `{t}` score *{s}* · R:R *{rr:.1f}* · _{sf}_")
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
            "text": "*Top picks:*\n" + "\n".join(top_lines)}})
    sleeve_summary = []
    for name, hits in sleeves.items():
        if hits:
            sleeve_summary.append(f"`{name}` *{len(hits)}*")
    if sleeve_summary:
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
            "text": "*Sleeves firing:* " + " · ".join(sleeve_summary)}})
    rs_status = "🔴 KILL ACTIVE" if rs.get("active") else "🟢 healthy"
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn",
        "text": f"Rolling Sharpe: {rs_status} · sharpe `{rs.get('sharpe','n/a')}` vs `{rs.get('threshold','n/a')}`"}]})
    blocks.append({"type": "section", "text": {"type": "mrkdwn",
        "text": "<https://trade.mystockholding.com/reports/latest/morning-newsletter|🌅 Open Full Morning Brief →>"}})
    return text, blocks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-slack", action="store_true")
    ap.add_argument("--preview", action="store_true")
    args = ap.parse_args()

    report = _build_report()
    html = _render_html(report)

    out_p = REPO / "cache" / f"morning_newsletter_{date.today().isoformat()}.html"
    out_p.write_text(html)
    print(f"Wrote {out_p}")

    try:
        import db
        snap_id = db.save_html_snapshot(
            kind="morning-newsletter", html_content=html,
            label=f"Morning Brief {date.today().isoformat()}",
            meta={
                "regime": (report["bundle"].get("regime") or {}).get("regime4"),
                "buy_count": len(report["bundle"].get("buy_candidates") or []),
                "watch_count": len(report["bundle"].get("watch_list") or []),
                "sleeve_fires": sum(len(v) for v in report["sleeves"].values()),
            }
        )
        print(f"Saved to DB: snapshot id={snap_id}")
    except Exception as e:
        print(f"DB save failed: {e}")

    if args.preview:
        print(html[:2000])

    if not args.no_slack:
        text, blocks = _slack_summary(report)
        try:
            from secrets_loader import get_secret as _gs
            webhook = _gs("SLACK_WEBHOOK_URL", default="")
        except Exception:
            webhook = ""
        if webhook:
            from alerts import _slack_post
            ok = _slack_post(webhook, text, blocks)
            print(f"Slack: {'✓ sent' if ok else '✗ failed'}")


if __name__ == "__main__":
    main()

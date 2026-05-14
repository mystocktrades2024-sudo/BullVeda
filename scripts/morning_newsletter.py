#!/usr/bin/env python3
"""morning_newsletter.py — daily SwingTrade morning brief.

Reads last_bundle.json + signal_log + portfolio_state + macro calendar,
renders a scan-friendly HTML newsletter, saves to DB as 'morning-newsletter'
snapshot, posts summary + link to Slack.

Run schedule:
  Mon-Fri 7:30am PT (after morning-briefing at 6:30am, after pre-market scan)
  Via infra/launchd/com.swingtrade.morning-newsletter.plist

Usage:
  python3 scripts/morning_newsletter.py              # Generate + save + Slack
  python3 scripts/morning_newsletter.py --no-slack   # HTML only
  python3 scripts/morning_newsletter.py --preview    # Print HTML to stdout
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


def _yesterday_recap() -> dict:
    """Stub for now — would read closed_trades from DB."""
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


# ─── rendering ──────────────────────────────────────────────────────────────

def _emoji_regime(regime4: str) -> str:
    return {"risk_on_trending": "🟢", "risk_on_choppy": "🟡",
            "risk_off_trending": "🟠", "panic": "🔴",
            "bull": "🟢", "bear": "🔴", "neutral": "🟡"}.get(regime4, "⚪")


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

    today_str = date.today().strftime("%A, %B %d, %Y")
    time_str = datetime.now().strftime("%-I:%M %p PT")
    regime4 = regime.get("regime4", "unknown")
    regime_emoji = _emoji_regime(regime4)
    spy = regime.get("spy_price", "?")
    vix = regime.get("vix_current", "?")
    breadth = regime.get("breadth_pct_50d", "?")

    # Top picks (up to 5)
    pick_cards = []
    for r in buys[:5]:
        ticker = r.get("ticker", "?")
        score = r.get("score", 0)
        sector = (r.get("sector") or "—")[:18]
        setup = (r.get("setup_family") or "—")[:25]
        sf_emo = "🚀" if setup == "Momentum Continuation" else \
                 "🎯" if setup == "PEAD" else \
                 "🔄" if setup == "Mean Reversion" else \
                 "🛡️" if setup == "Defensive Rotation" else \
                 "👥" if setup == "Insider Cluster" else \
                 "📊" if setup == "ESP Play" else \
                 "📈"
        tp = r.get("trade_plan") or {}
        price = r.get("price", 0)
        entry_lo = tp.get("entry_low") or tp.get("primary_zone_low") or price
        entry_hi = tp.get("entry_high") or tp.get("primary_zone_high") or price
        stop = tp.get("stop", 0)
        t1 = tp.get("target1", 0)
        t2 = tp.get("target2", 0)
        rr = tp.get("rr_ratio") or 0
        sharpe = r.get("sharpe_126d") or 0
        in_zone = (entry_lo <= price <= entry_hi) if price and entry_lo and entry_hi else False
        zone_status = '<span style="color:#3fb950">● in zone</span>' if in_zone \
                      else '<span style="color:#7d8590">● near zone</span>'
        # Quick mechanism hint
        why = {
            "Trend Continuation": "EMA pullback / continuation",
            "Momentum Continuation": "Strength + ADX",
            "Breakout Expansion": "Range breakout",
            "Impulse Catalyst": "PEAD / catalyst",
            "Defensive Rotation": "Flight-to-safety",
            "Mean Reversion": "RSI<30 bounce",
            "PEAD": "Post-earnings drift",
            "Insider Cluster": "Insider asymmetry",
            "ESP Play": "Pre-earnings drift",
            "Special Situation": "Idiosyncratic edge",
        }.get(setup, "Score-driven")

        pick_cards.append(f"""
        <div class="pick-card">
          <div class="pick-head">
            <span class="ticker">{ticker}</span>
            <span class="score">Score <b>{score}</b></span>
            <span class="rr">R:R <b>{rr:.1f}</b></span>
            <span class="setup">{sf_emo} {setup}</span>
          </div>
          <div class="pick-row">
            <span class="sector">{sector}</span>
            <span class="sharpe">Sharpe 126d <b>{sharpe:.2f}</b></span>
            {zone_status}
          </div>
          <div class="pick-plan">
            Price <b>${price:.2f}</b> &nbsp;·&nbsp;
            Entry <b>${entry_lo:.2f}–${entry_hi:.2f}</b> &nbsp;·&nbsp;
            Stop <b>${stop:.2f}</b> &nbsp;·&nbsp;
            T1 <b>${t1:.2f}</b> &nbsp;·&nbsp;
            T2 <b>${t2:.2f}</b>
          </div>
          <div class="pick-why">→ {why}</div>
        </div>""")

    if not pick_cards:
        pick_cards.append('<div class="pick-card" style="color:#7d8590">No BUY-tier picks today. WATCH list has {} candidates.</div>'.format(len(watch)))

    # Sleeve fires summary
    sleeve_rows = []
    for sleeve_name in ["Momentum Continuation", "Defensive Rotation", "Mean Reversion",
                         "PEAD", "Insider Cluster", "ESP Play"]:
        hits = sleeves.get(sleeve_name) or []
        sample = ", ".join((h.get("ticker") or "?") for h in hits[:3])
        more = f" (+{len(hits)-3} more)" if len(hits) > 3 else ""
        if hits:
            sleeve_rows.append(f'<div class="sleeve-row sleeve-on">🔥 <b>{sleeve_name}</b>: {len(hits)} fires — <code>{sample}{more}</code></div>')
        else:
            sleeve_rows.append(f'<div class="sleeve-row sleeve-off">— {sleeve_name}: <span style="color:#7d8590">no fires</span></div>')

    # Macro events
    macro_rows = []
    for ev in macro:
        when = "Today" if ev["days_until"] == 0 else f"in {ev['days_until']}d" if ev["days_until"] > 0 else f"{abs(ev['days_until'])}d ago"
        emo = "🔴" if ev["days_until"] <= 1 else "🟡" if ev["days_until"] <= 5 else "⚪"
        macro_rows.append(f'<div class="macro-row">{emo} <b>{ev["date"]}</b> · {ev["type"]} · {ev["label"]} <span style="color:#7d8590">({when})</span></div>')
    if not macro_rows:
        macro_rows.append('<div class="macro-row" style="color:#7d8590">No major macro events in next 14 days.</div>')

    # Risk watch
    rs_active = rs.get("active", False)
    rs_sharpe = rs.get("sharpe", "n/a")
    rs_threshold = rs.get("threshold", "n/a")
    rs_n = rs.get("n", 0)
    rs_color = "#f85149" if rs_active else "#3fb950" if (isinstance(rs_sharpe, (int, float)) and rs_sharpe > rs_threshold + 0.10) else "#d29922"
    rs_status = "🔴 ACTIVE — BUYs HALTED" if rs_active else \
                "🟡 At edge" if isinstance(rs_sharpe, (int, float)) and rs_sharpe < rs_threshold + 0.10 else \
                "🟢 Healthy"
    open_n = len(pf.get("positions") or [])
    equity = pf.get("equity") or pf.get("cash") or 0

    # Today's insight (synthesize from data)
    insight_parts = []
    if sleeves.get("PEAD"):
        ticker_list = ", ".join((h.get("ticker") or "?") for h in sleeves["PEAD"][:3])
        insight_parts.append(f"🎯 PEAD sleeve fires on <b>{ticker_list}</b> — post-earnings drift candidates")
    if sleeves.get("Mean Reversion"):
        ticker_list = ", ".join((h.get("ticker") or "?") for h in sleeves["Mean Reversion"][:3])
        insight_parts.append(f"🔄 Mean Reversion active on <b>{ticker_list}</b> — oversold bounce setups")
    if regime4 == "risk_on_choppy":
        insight_parts.append("Regime is choppy — Pullback + Mean Reversion are the alpha sleeves today. Momentum + Defensive are correctly dormant.")
    if rs_active:
        insight_parts.insert(0, "⚠️ <b>Rolling Sharpe kill ACTIVE</b> — all new BUYs halted by capital preservation gate. Wait for recovery.")
    elif isinstance(rs_sharpe, (int, float)) and rs_sharpe < rs_threshold + 0.05:
        insight_parts.insert(0, f"⚠️ Rolling Sharpe at edge ({rs_sharpe:+.3f} vs {rs_threshold:+.2f}) — one more losing trade triggers kill switch.")
    if not insight_parts:
        insight_parts.append("Quiet day. Watch the WATCH list for entry triggers.")
    insight_text = "<br><br>".join(insight_parts)

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>SwingTrade Morning Brief — {date.today().isoformat()}</title>
<style>
  body {{ background:#0d1117; color:#c9d1d9;
         font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display','SF Pro',Helvetica,sans-serif;
         margin:0; padding:32px 16px; line-height:1.45; }}
  .container {{ max-width:680px; margin:0 auto; background:#0d1117; }}
  header {{ text-align:left; padding-bottom:24px; border-bottom:2px solid #30363d; margin-bottom:24px; }}
  h1 {{ margin:0 0 4px 0; font-size:26px; font-weight:700; color:#f0f6fc; letter-spacing:-0.5px; }}
  .date {{ color:#7d8590; font-size:14px; }}
  section {{ background:#161b22; border:1px solid #30363d; border-radius:10px; padding:20px;
            margin-bottom:18px; }}
  h2 {{ margin:0 0 12px 0; font-size:14px; font-weight:600; color:#7d8590; letter-spacing:0.7px;
       text-transform:uppercase; }}
  .market-row {{ display:flex; flex-wrap:wrap; gap:18px; font-size:14px; color:#c9d1d9; }}
  .market-row b {{ color:#f0f6fc; font-weight:600; }}
  .pick-card {{ background:#0d1117; border:1px solid #30363d; border-radius:8px;
               padding:14px; margin-bottom:10px; }}
  .pick-head {{ display:flex; flex-wrap:wrap; gap:14px; align-items:baseline;
               margin-bottom:6px; }}
  .ticker {{ font-size:18px; font-weight:700; color:#f0f6fc; letter-spacing:-0.3px; }}
  .score, .rr {{ font-size:12px; color:#7d8590; }}
  .score b, .rr b {{ color:#79c0ff; font-weight:600; }}
  .setup {{ font-size:12px; color:#c9d1d9; margin-left:auto; }}
  .pick-row {{ display:flex; gap:14px; font-size:12px; color:#7d8590; margin-bottom:8px; }}
  .pick-row b {{ color:#c9d1d9; font-weight:600; }}
  .pick-plan {{ font-size:13px; color:#c9d1d9; padding:8px 10px; background:#161b22;
               border-radius:6px; }}
  .pick-plan b {{ color:#f0f6fc; font-weight:600; }}
  .pick-why {{ font-size:12px; color:#7d8590; font-style:italic; margin-top:6px; }}
  .sleeve-row {{ font-size:13px; padding:6px 0; }}
  .sleeve-on b {{ color:#f0f6fc; }}
  .sleeve-on code {{ background:#161b22; padding:2px 6px; border-radius:4px;
                    color:#79c0ff; font-size:12px; }}
  .sleeve-off {{ color:#7d8590; }}
  .macro-row {{ font-size:13px; padding:4px 0; color:#c9d1d9; }}
  .macro-row b {{ font-family:'SF Mono',Menlo,monospace; color:#f0f6fc; }}
  .risk-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; }}
  .risk-cell {{ background:#0d1117; border:1px solid #30363d; border-radius:6px;
               padding:10px; font-size:12px; color:#7d8590; }}
  .risk-cell .v {{ font-size:18px; color:#f0f6fc; font-weight:600; }}
  .insight {{ font-size:14px; color:#c9d1d9; line-height:1.6; }}
  .insight b {{ color:#f0f6fc; }}
  footer {{ margin-top:24px; padding-top:16px; border-top:1px solid #30363d;
           text-align:center; font-size:13px; }}
  footer a {{ color:#3fb950; text-decoration:none; margin:0 12px; }}
  footer a:hover {{ text-decoration:underline; }}
</style></head>
<body>
<div class="container">

<header>
  <h1>🌅 SwingTrade Morning Brief</h1>
  <div class="date">{today_str} · {time_str}</div>
</header>

<section>
  <h2>📊 Market Context</h2>
  <div class="market-row">
    <div>Regime: {regime_emoji} <b>{regime4}</b></div>
    <div>SPY: <b>${spy}</b></div>
    <div>VIX: <b>{vix}</b></div>
    <div>Breadth: <b>{breadth}%</b> &gt;50dma</div>
  </div>
</section>

<section>
  <h2>⭐ Top Conviction · {len(buys)} BUY · {len(watch)} WATCH</h2>
  {"".join(pick_cards)}
</section>

<section>
  <h2>🔥 Strategy Sleeve Activity</h2>
  {"".join(sleeve_rows)}
</section>

<section>
  <h2>📅 Macro Calendar · Next 14 Days</h2>
  {"".join(macro_rows)}
</section>

<section>
  <h2>⚠️ Risk Watch</h2>
  <div class="risk-grid">
    <div class="risk-cell">Rolling Sharpe<br><span class="v" style="color:{rs_color}">{rs_sharpe if isinstance(rs_sharpe, str) else f'{rs_sharpe:+.3f}'}</span><br>{rs_status}<br><span style="color:#7d8590">vs threshold {rs_threshold} on n={rs_n}</span></div>
    <div class="risk-cell">Open Positions<br><span class="v">{open_n}</span><br>Equity: <b>${equity:,.0f}</b></div>
    <div class="risk-cell">Closed Today<br><span class="v">{recap['closed_today']}</span><br>P&amp;L: <b>{recap['total_pnl_pct']:+.2f}%</b></div>
    <div class="risk-cell">Sleeves Enabled<br><span class="v">{report.get('sleeves_enabled_count', 7)}/7</span><br>+ Pre-FOMC overlay</div>
  </div>
</section>

<section>
  <h2>💡 Today's Insight</h2>
  <div class="insight">{insight_text}</div>
</section>

<footer>
  <a href="https://trade.mystockholding.com/v2/dashboard.html">🔗 Live Dashboard</a>
  <a href="https://trade.mystockholding.com/reports">📚 Report Archive</a>
  <a href="https://trade.mystockholding.com/reports/latest/dashboard">🗂️ Latest Snapshot</a>
  <br><br>
  <span style="color:#7d8590; font-size:11px">
    SwingTrade · Built with quant-discipline · Paper observation phase ·
    Calibration overlay applies (docs/claude_md_calibration.md)
  </span>
</footer>

</div></body></html>"""
    return html


def _build_report() -> dict:
    bundle = _load_bundle()
    sleeves = _sleeve_fires(bundle)
    rs = _rolling_sharpe()
    pf = _load_portfolio()
    macro = _upcoming_macro()
    recap = _yesterday_recap()
    # Count sleeves enabled
    try:
        cfg = json.loads((REPO / "config" / "config.json").read_text())
        sleeves_enabled = sum(1 for k in [
            "momentum_sleeve", "defensive_rotation_sleeve", "mean_reversion_sleeve",
            "pead_sleeve", "insider_cluster_sleeve", "esp_play_sleeve"
        ] if cfg.get(k, {}).get("_enabled"))
    except Exception:
        sleeves_enabled = 0

    return {
        "bundle": bundle,
        "sleeves": sleeves,
        "rolling_sharpe": rs,
        "portfolio": pf,
        "macro": macro,
        "recap": recap,
        "sleeves_enabled_count": sleeves_enabled,
    }


def _slack_summary(report: dict) -> tuple[str, list]:
    """Build Slack summary that links to the full newsletter."""
    bundle = report["bundle"]
    regime = bundle.get("regime", {})
    buys = bundle.get("buy_candidates") or []
    watch = bundle.get("watch_list") or []
    sleeves = report["sleeves"]
    rs = report["rolling_sharpe"]

    today = date.today().strftime("%A, %b %d")
    regime4 = regime.get("regime4", "unknown")
    sleeve_count = sum(len(v) for v in sleeves.values())

    text = f"🌅 *Morning Brief — {today}* · regime `{regime4}` · {len(buys)} BUY · {len(watch)} WATCH"
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": "🌅 SwingTrade Morning Brief"}},
        {"type": "section", "text": {"type": "mrkdwn",
         "text": f"*{today}* · Regime: `{regime4}` · SPY `${regime.get('spy_price','?')}` · VIX `{regime.get('vix_current','?')}`"}},
    ]
    # Top 3 picks
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
    else:
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
            "text": f"_No BUY picks today. {len(watch)} on WATCH._"}})
    # Sleeve summary
    sleeve_summary = []
    for name, hits in sleeves.items():
        if hits:
            sleeve_summary.append(f"`{name}` *{len(hits)}*")
    if sleeve_summary:
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
            "text": "*Sleeves firing:* " + " · ".join(sleeve_summary)}})
    # Risk
    rs_status = "🔴 KILL ACTIVE" if rs.get("active") else "🟢 healthy"
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn",
        "text": f"Rolling Sharpe: {rs_status} · Sharpe `{rs.get('sharpe','n/a')}` vs threshold `{rs.get('threshold','n/a')}`"}]})
    # Link
    blocks.append({"type": "section", "text": {"type": "mrkdwn",
        "text": "<https://trade.mystockholding.com/reports/latest/morning-newsletter|🌅 Read the full Morning Brief →>"}})
    return text, blocks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-slack", action="store_true")
    ap.add_argument("--preview", action="store_true", help="Print HTML to stdout")
    args = ap.parse_args()

    report = _build_report()
    html = _render_html(report)

    # Save to disk + DB
    out_p = REPO / "cache" / f"morning_newsletter_{date.today().isoformat()}.html"
    out_p.write_text(html)
    print(f"Wrote {out_p}")

    try:
        import db
        snap_id = db.save_html_snapshot(
            kind="morning-newsletter",
            html_content=html,
            label=f"Morning Brief {date.today().isoformat()}",
            meta={
                "regime": (report["bundle"].get("regime") or {}).get("regime4"),
                "buy_count": len(report["bundle"].get("buy_candidates") or []),
                "watch_count": len(report["bundle"].get("watch_list") or []),
                "sleeve_fires": sum(len(v) for v in report["sleeves"].values()),
            }
        )
        print(f"Saved to DB: snapshot id={snap_id}")
        print(f"Access at: https://trade.mystockholding.com/reports/latest/morning-newsletter")
    except Exception as e:
        print(f"DB save failed: {e}")

    if args.preview:
        print("\n" + "=" * 60)
        print("HTML PREVIEW")
        print("=" * 60)
        print(html[:2000])
        print("...")

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
            print(f"\nSlack: {'✓ sent' if ok else '✗ failed'}")
        else:
            print("\nNo SLACK_WEBHOOK_URL — skipped Slack post")


if __name__ == "__main__":
    main()

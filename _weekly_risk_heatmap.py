"""
Tasks 21-23: Weekly Review, Risk Dashboard, Sector Heat Map
These functions should be imported into html_generator.py or merged directly.

Usage in html_generator.py:
    from _weekly_risk_heatmap import _build_weekly_review, _build_risk_dashboard, _build_sector_heatmap

Then in _tab_portfolio(), after the track record section (after content_banner = content_banner + _track_record_html):
    content_banner += _build_weekly_review()
    content_banner += _build_risk_dashboard(all_scored=None)

In _tab_market_intel(), after the header section:
    h += _build_sector_heatmap(sector_etf_data)
"""

from __future__ import annotations
import json
from datetime import datetime, timedelta
from pathlib import Path


def _build_weekly_review() -> str:
    """Generate a weekly performance review card from signal_log.json (Task 21)."""
    try:
        log_path = Path(__file__).parent / "data" / "signal_log.json"
        if not log_path.exists():
            return ('<div style="background:var(--surface);border:1px solid var(--border);border-radius:14px;'
                    'padding:28px 24px;margin-bottom:20px;box-shadow:0 2px 12px rgba(0,0,0,0.1);text-align:center">'
                    '<div style="font-size:16px;font-weight:800;color:var(--text);display:flex;align-items:center;'
                    'justify-content:center;gap:8px;margin-bottom:12px">'
                    '<span style="font-size:20px">&#128202;</span> Weekly Review</div>'
                    '<div style="color:var(--text-muted);font-size:13px;padding:12px 0">'
                    'No signal history yet. Run daily scans to build your track record.</div></div>')

        signals = json.loads(log_path.read_text())
        if not signals:
            return ('<div style="background:var(--surface);border:1px solid var(--border);border-radius:14px;'
                    'padding:28px 24px;margin-bottom:20px;text-align:center">'
                    '<div style="font-size:16px;font-weight:800;color:var(--text);display:flex;align-items:center;'
                    'justify-content:center;gap:8px;margin-bottom:12px">'
                    '<span style="font-size:20px">&#128202;</span> Weekly Review</div>'
                    '<div style="color:var(--text-muted);font-size:13px">'
                    'Signal log is empty. Signals will appear after your first scan.</div></div>')

        now = datetime.now()
        week_ago = now - timedelta(days=7)
        week_signals = []
        for s in signals:
            try:
                sig_date = datetime.strptime(s.get("date", ""), "%Y-%m-%d")
            except (ValueError, TypeError):
                sig_date = None
            if sig_date and sig_date >= week_ago:
                week_signals.append(s)

        total_this_week = len(week_signals)
        week_winners = [s for s in week_signals if s.get("result") == "WIN"]
        week_losers = [s for s in week_signals if s.get("result") == "LOSS"]
        week_open = [s for s in week_signals if s.get("status") == "OPEN" or s.get("result") is None]
        resolved_week = [s for s in week_signals if s.get("actual_pnl_pct") is not None]
        best_trade = max(resolved_week, key=lambda x: x.get("actual_pnl_pct", 0)) if resolved_week else None
        worst_trade = min(resolved_week, key=lambda x: x.get("actual_pnl_pct", 0)) if resolved_week else None
        decided = len(week_winners) + len(week_losers)
        wr = round(len(week_winners) / decided * 100, 0) if decided > 0 else 0
        week_pnl = sum(s.get("actual_pnl_pct", 0) for s in resolved_week)

        # Strategy breakdown across all signals
        strat_stats = {}
        for s in signals:
            strat = s.get("strategy", "Unknown")
            if strat not in strat_stats:
                strat_stats[strat] = {"total": 0, "wins": 0, "losses": 0, "pnl": 0.0}
            strat_stats[strat]["total"] += 1
            if s.get("result") == "WIN":
                strat_stats[strat]["wins"] += 1
            elif s.get("result") == "LOSS":
                strat_stats[strat]["losses"] += 1
            if s.get("actual_pnl_pct") is not None:
                strat_stats[strat]["pnl"] += s["actual_pnl_pct"]

        wr_color = "#22c55e" if wr >= 55 else "#ef4444" if wr < 45 else "#eab308"
        pnl_color = "#22c55e" if week_pnl >= 0 else "#ef4444"

        html = ('<div style="background:var(--surface);border:1px solid var(--border);border-radius:14px;'
                'padding:20px 24px;margin-bottom:20px;box-shadow:0 2px 12px rgba(0,0,0,0.1)">'
                '<div style="font-size:16px;font-weight:800;color:var(--text);display:flex;align-items:center;'
                'gap:8px;margin-bottom:16px"><span style="font-size:20px">&#128202;</span> Weekly Review'
                '<span style="font-size:11px;color:var(--text-muted);font-weight:500;margin-left:auto">'
                f'{week_ago.strftime("%b %d")} &ndash; {now.strftime("%b %d, %Y")}</span></div>')

        # Stats grid
        html += '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(100px,1fr));gap:10px;margin-bottom:16px">'
        for label, val, color in [
            ("Signals", str(total_this_week), "var(--primary)"),
            ("Winners", str(len(week_winners)), "#22c55e"),
            ("Losers", str(len(week_losers)), "#ef4444"),
            ("Still Open", str(len(week_open)), "#94a3b8"),
            ("Win Rate", f"{wr:.0f}%" if decided > 0 else "N/A", wr_color if decided > 0 else "#94a3b8"),
            ("Week P&amp;L", f"{week_pnl:+.1f}%" if resolved_week else "N/A", pnl_color if resolved_week else "#94a3b8"),
        ]:
            html += (f'<div style="background:var(--surface-alt);border-radius:8px;padding:10px 12px;text-align:center">'
                     f'<div style="font-size:10px;font-weight:700;color:var(--text-muted);text-transform:uppercase;'
                     f'letter-spacing:.4px">{label}</div>'
                     f'<div style="font-size:20px;font-weight:800;color:{color};margin-top:4px">{val}</div></div>')
        html += '</div>'

        # Best / worst trade
        if best_trade or worst_trade:
            html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:16px">'
            if best_trade:
                bp = best_trade.get("actual_pnl_pct", 0)
                html += (f'<div style="background:rgba(34,197,94,0.08);border:1px solid rgba(34,197,94,0.2);'
                         f'border-radius:10px;padding:12px 14px">'
                         f'<div style="font-size:10px;font-weight:700;color:#22c55e;text-transform:uppercase">Best Trade</div>'
                         f'<div style="font-size:18px;font-weight:800;color:#22c55e;margin-top:4px">'
                         f'{best_trade["ticker"]} {bp:+.1f}%</div>'
                         f'<div style="font-size:11px;color:var(--text-muted);margin-top:2px">'
                         f'{best_trade.get("strategy","")}</div></div>')
            if worst_trade:
                wp = worst_trade.get("actual_pnl_pct", 0)
                html += (f'<div style="background:rgba(239,68,68,0.08);border:1px solid rgba(239,68,68,0.2);'
                         f'border-radius:10px;padding:12px 14px">'
                         f'<div style="font-size:10px;font-weight:700;color:#ef4444;text-transform:uppercase">Worst Trade</div>'
                         f'<div style="font-size:18px;font-weight:800;color:#ef4444;margin-top:4px">'
                         f'{worst_trade["ticker"]} {wp:+.1f}%</div>'
                         f'<div style="font-size:11px;color:var(--text-muted);margin-top:2px">'
                         f'{worst_trade.get("strategy","")}</div></div>')
            html += '</div>'

        # Strategy performance bars
        if strat_stats:
            html += ('<div style="border-top:1px solid rgba(99,102,241,0.15);padding-top:14px;margin-top:4px">'
                     '<div style="font-size:11px;font-weight:700;color:var(--text-muted);letter-spacing:.5px;'
                     'text-transform:uppercase;margin-bottom:10px">Strategy Breakdown</div>')
            sorted_strats = sorted(strat_stats.items(), key=lambda x: x[1]["wins"], reverse=True)
            max_total = max((v["total"] for _, v in sorted_strats), default=1)
            for strat_name, st in sorted_strats:
                st_wr = round(st["wins"] / (st["wins"] + st["losses"]) * 100, 0) if (st["wins"] + st["losses"]) > 0 else 0
                st_wr_c = "#22c55e" if st_wr >= 55 else "#ef4444" if st_wr < 45 else "#eab308"
                bar_w = max(8, int(st["total"] / max_total * 100))
                pnl_c = "#22c55e" if st["pnl"] >= 0 else "#ef4444"
                html += (f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">'
                         f'<div style="min-width:140px;font-size:12px;font-weight:600;color:var(--text);'
                         f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{strat_name}</div>'
                         f'<div style="flex:1;background:var(--surface-alt);border-radius:6px;height:8px;overflow:hidden">'
                         f'<div style="height:100%;width:{bar_w}%;background:linear-gradient(90deg,{st_wr_c},{st_wr_c}88);'
                         f'border-radius:6px"></div></div>'
                         f'<div style="min-width:35px;font-size:11px;font-weight:700;color:{st_wr_c};text-align:right">'
                         f'{st_wr:.0f}%</div>'
                         f'<div style="min-width:55px;font-size:11px;color:var(--text-muted);text-align:right">'
                         f'{st["wins"]}W/{st["losses"]}L</div>'
                         f'<div style="min-width:55px;font-size:11px;font-weight:600;color:{pnl_c};text-align:right">'
                         f'{st["pnl"]:+.1f}%</div></div>')
            html += '</div>'

        # Improvement suggestions
        suggestions = []
        if decided > 0 and wr < 50:
            suggestions.append("Win rate below 50% &mdash; consider tightening entry criteria or waiting for better setups.")
        if decided > 0 and wr >= 65:
            suggestions.append("Excellent win rate! Consider increasing position sizes slightly.")
        if total_this_week == 0:
            suggestions.append("No signals this week. Ensure daily scans are running, or market conditions may be unfavorable.")
        if total_this_week > 10:
            suggestions.append("High signal volume &mdash; focus on the top 3-5 highest conviction setups only.")
        if strat_stats:
            top_strat = max(strat_stats.items(), key=lambda x: x[1]["total"])
            if top_strat[1]["total"] > total_this_week * 0.7 and total_this_week > 3:
                suggestions.append(f"Over-reliance on {top_strat[0]} &mdash; diversify across strategies for better risk distribution.")
        if not suggestions:
            suggestions.append("Keep running daily scans to build a reliable track record over time.")

        html += ('<div style="border-top:1px solid rgba(99,102,241,0.15);padding-top:14px;margin-top:14px">'
                 '<div style="font-size:11px;font-weight:700;color:var(--text-muted);letter-spacing:.5px;'
                 'text-transform:uppercase;margin-bottom:8px">&#128161; Suggestions</div>')
        for sug in suggestions:
            html += (f'<div style="display:flex;align-items:flex-start;gap:8px;margin-bottom:6px;font-size:12px;'
                     f'color:var(--text-muted)"><span style="color:var(--primary);font-size:10px;margin-top:2px">'
                     f'&#9679;</span><span>{sug}</span></div>')
        html += '</div></div>'
        return html
    except Exception:
        return ''


def _build_risk_dashboard(all_scored: list = None, portfolio_summary: dict = None) -> str:
    """Build a risk exposure dashboard card from portfolio positions (Task 22)."""
    try:
        if portfolio_summary is None:
            try:
                from portfolio_tracker import get_portfolio_summary
                portfolio_summary = get_portfolio_summary()
            except Exception:
                portfolio_summary = None

        _no_risk = ('<div style="background:var(--surface);border:1px solid var(--border);border-radius:14px;'
                    'padding:20px 24px;margin-bottom:20px;box-shadow:0 2px 12px rgba(0,0,0,0.1)">'
                    '<div style="font-size:16px;font-weight:800;color:var(--text);display:flex;align-items:center;'
                    'gap:8px;margin-bottom:12px"><span style="font-size:18px">&#128737;</span> Risk Dashboard</div>'
                    '<div style="color:var(--text-muted);font-size:13px;padding:16px 0;text-align:center;font-style:italic">'
                    'No risk exposure &mdash; portfolio is 100% cash</div></div>')

        if not portfolio_summary:
            return _no_risk

        positions = portfolio_summary.get("positions", [])
        equity = portfolio_summary.get("equity", 5000)
        cash = portfolio_summary.get("cash", equity)
        invested = portfolio_summary.get("invested", 0)

        if not positions:
            return _no_risk

        # 1. Total Exposure
        total_exposure_pct = round(invested / equity * 100, 1) if equity > 0 else 0
        exp_color = "#ef4444" if total_exposure_pct > 80 else "#eab308" if total_exposure_pct > 50 else "#22c55e"

        # 2. Sector Concentration
        sector_map, scored_lookup = {}, {}
        if all_scored:
            for r in all_scored:
                scored_lookup[r.get("ticker", "")] = r
        for p in positions:
            ticker = p.get("ticker", "?")
            sector = scored_lookup.get(ticker, {}).get("sector", "Unknown") or "Unknown"
            pos_size = p.get("position_size", p.get("entry_price", 0) * p.get("shares", 0))
            sector_map[sector] = sector_map.get(sector, 0) + pos_size
        total_pos_size = sum(sector_map.values()) or 1
        sector_pcts = sorted(
            [(s, round(v / total_pos_size * 100, 1)) for s, v in sector_map.items()],
            key=lambda x: x[1], reverse=True
        )

        # 3. Max Loss Scenario (3% market drop)
        max_loss_3pct = round(invested * 0.03, 2)

        # 4. Open Risk: sum of (stop_distance * shares)
        open_risk_dollars = 0.0
        for p in positions:
            entry = p.get("entry_price", 0)
            stop = p.get("stop", p.get("trail_stop", 0))
            shares = p.get("shares", 0)
            if entry > 0 and stop > 0:
                open_risk_dollars += abs(entry - stop) * shares
            else:
                open_risk_dollars += entry * shares * 0.03

        # 5. Correlation Warning (same sector = correlated)
        corr_warnings, sector_tickers = [], {}
        for p in positions:
            ticker = p.get("ticker", "?")
            sector = scored_lookup.get(ticker, {}).get("sector", "Unknown") or "Unknown"
            sector_tickers.setdefault(sector, []).append(ticker)
        for sector, tickers in sector_tickers.items():
            if len(tickers) >= 2 and sector != "Unknown":
                corr_warnings.append(
                    f"{', '.join(tickers)} are in <strong>{sector}</strong> &mdash; high correlation risk"
                )

        # Build HTML
        html = ('<div style="background:var(--surface);border:1px solid var(--border);border-radius:14px;'
                'padding:20px 24px;margin-bottom:20px;box-shadow:0 2px 12px rgba(0,0,0,0.1)">'
                '<div style="font-size:16px;font-weight:800;color:var(--text);display:flex;align-items:center;'
                'gap:8px;margin-bottom:16px"><span style="font-size:18px">&#128737;</span> Risk Dashboard</div>')

        risk_pct = round(open_risk_dollars / equity * 100, 1) if equity > 0 else 0
        risk_color = "#ef4444" if risk_pct > 5 else "#eab308" if risk_pct > 3 else "#22c55e"
        cash_color = "#22c55e" if cash > equity * 0.3 else "#eab308"
        cash_sub = f"{round(cash/equity*100,0):.0f}% of equity" if equity > 0 else ""

        html += '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin-bottom:16px">'
        for label, val, color, sub in [
            ("Total Exposure", f"{total_exposure_pct:.0f}%", exp_color, f"${invested:,.0f} of ${equity:,.0f}"),
            ("Open Risk", f"${open_risk_dollars:,.0f}", risk_color, f"{risk_pct:.1f}% of equity"),
            ("Max Loss (3%&darr;)", f"${max_loss_3pct:,.0f}", "#ef4444", "If market drops 3%"),
            ("Cash Reserve", f"${cash:,.0f}", cash_color, cash_sub),
        ]:
            html += (f'<div style="background:var(--surface-alt);border-radius:10px;padding:12px 14px;'
                     f'text-align:center;border-top:3px solid {color}">'
                     f'<div style="font-size:10px;font-weight:700;color:var(--text-muted);text-transform:uppercase;'
                     f'letter-spacing:.4px">{label}</div>'
                     f'<div style="font-size:20px;font-weight:800;color:{color};margin-top:4px">{val}</div>'
                     f'<div style="font-size:10px;color:var(--text-muted);margin-top:2px">{sub}</div></div>')
        html += '</div>'

        # Sector concentration bars
        if sector_pcts:
            html += ('<div style="border-top:1px solid rgba(99,102,241,0.15);padding-top:14px">'
                     '<div style="font-size:11px;font-weight:700;color:var(--text-muted);letter-spacing:.5px;'
                     'text-transform:uppercase;margin-bottom:10px">Sector Concentration</div>')
            _SC = ["#6366f1", "#8b5cf6", "#ec4899", "#f97316", "#14b8a6", "#3b82f6", "#84cc16", "#f43f5e"]
            for i, (sector, pct) in enumerate(sector_pcts[:6]):
                bar_color = _SC[i % len(_SC)]
                conc_warn = " &#9888;" if pct > 40 else ""
                html += (f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">'
                         f'<div style="min-width:120px;font-size:12px;font-weight:600;color:var(--text);'
                         f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{sector}</div>'
                         f'<div style="flex:1;background:var(--surface-alt);border-radius:6px;height:8px;overflow:hidden">'
                         f'<div style="height:100%;width:{min(pct, 100):.0f}%;background:{bar_color};'
                         f'border-radius:6px"></div></div>'
                         f'<div style="min-width:45px;font-size:11px;font-weight:700;color:var(--text);'
                         f'text-align:right">{pct:.0f}%{conc_warn}</div></div>')
            html += '</div>'

        # Correlation warnings
        if corr_warnings:
            html += ('<div style="border-top:1px solid rgba(99,102,241,0.15);padding-top:14px;margin-top:14px">'
                     '<div style="font-size:11px;font-weight:700;color:var(--text-muted);letter-spacing:.5px;'
                     'text-transform:uppercase;margin-bottom:8px">&#9888; Correlation Warnings</div>')
            for warn in corr_warnings:
                html += (f'<div style="background:rgba(245,158,11,0.08);border:1px solid rgba(245,158,11,0.2);'
                         f'border-radius:8px;padding:8px 12px;margin-bottom:6px;font-size:12px;color:#f59e0b">'
                         f'{warn}</div>')
            html += '</div>'

        html += '</div>'
        return html
    except Exception:
        return ''


def _build_sector_heatmap(sector_etf_data: dict = None) -> str:
    """Build a visual sector heat map from ETF performance data (Task 23)."""
    try:
        if not sector_etf_data:
            return ''

        etfs = []
        for k, v in sector_etf_data.items():
            if k.startswith("_") or k == "SPY" or not isinstance(v, dict):
                continue
            etfs.append({"etf": k, "sector": v.get("sector", k), "perf": v.get("perf_pct", 0) or 0})

        if not etfs:
            return ''

        etfs.sort(key=lambda x: x["perf"], reverse=True)
        max_abs = max(abs(e["perf"]) for e in etfs) or 1

        html = ('<div style="background:var(--surface);border:1px solid var(--border);border-radius:14px;'
                'padding:20px 24px;margin-bottom:20px;box-shadow:0 2px 12px rgba(0,0,0,0.1)">'
                '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">'
                '<div style="font-size:16px;font-weight:800;color:var(--text);display:flex;align-items:center;gap:8px">'
                '<span style="font-size:18px">&#127777;</span> Sector Heat Map</div>'
                '<div style="font-size:11px;color:var(--text-muted)">63-day performance</div></div>')

        for e in etfs:
            perf = e["perf"]
            is_pos = perf >= 0
            color = "#22c55e" if is_pos else "#ef4444"
            bg = "rgba(34,197,94,0.08)" if is_pos else "rgba(239,68,68,0.08)"
            border = "rgba(34,197,94,0.2)" if is_pos else "rgba(239,68,68,0.2)"
            arrow = "&#9650;" if is_pos else "&#9660;"
            bar_w = max(4, int(abs(perf) / max_abs * 100))
            bar_bg = ("linear-gradient(90deg, #22c55e, #4ade80)" if is_pos
                      else "linear-gradient(90deg, #ef4444, #f87171)")

            html += (f'<div style="display:flex;align-items:center;gap:10px;padding:8px 12px;margin-bottom:4px;'
                     f'background:{bg};border:1px solid {border};border-radius:8px">'
                     f'<div style="min-width:38px;font-size:12px;font-weight:800;color:var(--text)">{e["etf"]}</div>'
                     f'<div style="min-width:110px;font-size:12px;color:var(--text-muted);overflow:hidden;'
                     f'text-overflow:ellipsis;white-space:nowrap">{e["sector"]}</div>'
                     f'<div style="min-width:22px;font-size:10px;color:{color}">{arrow}</div>'
                     f'<div style="min-width:55px;font-size:13px;font-weight:800;color:{color};text-align:right">'
                     f'{perf:+.1f}%</div>'
                     f'<div style="flex:1;background:var(--surface-alt);border-radius:6px;height:10px;overflow:hidden">'
                     f'<div style="height:100%;width:{bar_w}%;background:{bar_bg};border-radius:6px;'
                     f'transition:width 0.4s ease"></div></div></div>')

        html += '</div>'
        return html
    except Exception:
        return ''

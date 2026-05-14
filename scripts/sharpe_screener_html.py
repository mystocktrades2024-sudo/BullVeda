#!/usr/bin/env python3
"""
sharpe_screener_html.py — render scripts/sharpe_screener.py JSON output as HTML.

Reads cache/sharpe_screen_<DATE>.json, generates a sortable table with tier
classification (A/B/C), 5-lens annotations, and conviction badges.

Output: cache/sharpe_screen.html (overwrites). Open in browser or serve via
the FastAPI server at /sharpe_screen.html (after wiring).

Usage:
  python3 scripts/sharpe_screener_html.py            # use today's JSON
  python3 scripts/sharpe_screener_html.py 2026-05-13 # specific date
"""
from __future__ import annotations
import json
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _tier(r: dict) -> tuple[str, str]:
    """Tier A: score≥70 + sharpe≥2.0. Tier B: score 50-69 + sharpe≥2.0.
    Tier C: high sharpe, score=0/3 (broken classification candidate)."""
    sc = r.get("score") or 0
    sh = r.get("sharpe") or 0
    if sc >= 70 and sh >= 2.0:
        return "A", "var(--gn)"
    if sc >= 50 and sh >= 2.0:
        return "B", "var(--amb)"
    if sc <= 5 and sh >= 1.5:
        return "C", "var(--rd)"
    return "—", "var(--ink-2)"


def _eq_color(eq: str) -> str:
    eq = (eq or "").upper()
    if eq in ("FRESH", "PULLBACK"):
        return "var(--gn)"
    if eq == "VALID":
        return "var(--amb)"
    if eq in ("EXTENDED", "MISSED"):
        return "var(--rd)"
    return "var(--ink-3)"


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()
    src = REPO / "cache" / f"sharpe_screen_{arg}.json"
    if not src.exists():
        print(f"ERROR: {src} not found. Run sharpe_screener.py first.", file=sys.stderr)
        sys.exit(1)

    data = json.loads(src.read_text())
    rows = data.get("tickers_above") or []
    threshold = data.get("threshold")
    lookback = data.get("lookback_days")
    n_above = data.get("n_above_threshold")
    n_computed = data.get("n_computed")
    n_scan = data.get("n_tickers_scan")

    # Tier counts
    tiered = []
    tier_counts = {"A": 0, "B": 0, "C": 0, "—": 0}
    for r in rows:
        t, c = _tier(r)
        r["_tier"] = t
        r["_tier_color"] = c
        tier_counts[t] += 1
        tiered.append(r)

    rows_html = []
    for i, r in enumerate(tiered, 1):
        sym = r["ticker"]
        sh = r.get("sharpe") or 0
        ret_a = r.get("return_ann_pct") or 0
        vol_a = r.get("vol_ann_pct") or 0
        sc = r.get("score")
        sc_str = str(sc) if sc is not None else "—"
        sc_color = "var(--gn)" if (sc and sc >= 70) else "var(--amb)" if (sc and sc >= 60) else "var(--rd)" if sc == 0 else "var(--ink-2)"
        verd = r.get("verdict") or "—"
        eq = r.get("entry_quality") or "—"
        st = (r.get("setup_family") or "—")[:24]
        sec = (r.get("sector") or "—")[:24]
        ed = r.get("earn_days")
        ed_str = f"{ed}d" if ed is not None else "—"
        ed_color = "var(--rd)" if (ed is not None and ed <= 7) else "var(--amb)" if (ed is not None and ed <= 14) else "var(--ink-2)"
        tier = r.get("_tier", "—")
        tier_color = r.get("_tier_color")

        rows_html.append(f"""<tr data-tier="{tier}" data-sharpe="{sh:.3f}" data-score="{sc or 0}">
  <td class="num dim">{i}</td>
  <td class="tier" style="color:{tier_color};font-weight:800">{tier}</td>
  <td class="sym">{sym}</td>
  <td class="num" style="color:var(--gn);font-weight:700">{sh:.2f}</td>
  <td class="num">{ret_a:+.1f}%</td>
  <td class="num dim">{vol_a:.1f}%</td>
  <td class="num" style="color:{sc_color};font-weight:700">{sc_str}</td>
  <td><span class="badge verdict-{verd.lower()}">{verd}</span></td>
  <td style="color:{_eq_color(eq)};font-family:var(--mono);font-size:11px">{eq}</td>
  <td class="dim">{st}</td>
  <td class="dim">{sec}</td>
  <td class="num" style="color:{ed_color}">{ed_str}</td>
</tr>""")

    today = date.today().isoformat()
    title = f"Sharpe Screen — {today}"
    body_table = "\n".join(rows_html)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
  :root {{
    --bg-0: #0a0e14; --bg-1: #0f141c; --bg-2: #181f2b; --bg-3: #232c3d;
    --ink-0: #e8eef7; --ink-1: #b9c5d6; --ink-2: #7d8a9f; --ink-3: #4a5468;
    --rule: #2a3447; --line: #1e2632;
    --gn: #22c55e; --amb: #f59e0b; --rd: #ef4444; --info: #3b82f6;
    --mono: 'JetBrains Mono', 'SF Mono', Menlo, monospace;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 24px;
    background: var(--bg-0);
    color: var(--ink-0);
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Inter, sans-serif;
    font-size: 14px; line-height: 1.5;
  }}
  .header {{
    display: flex; align-items: baseline; gap: 24px;
    border-bottom: 1px solid var(--rule); padding-bottom: 14px; margin-bottom: 18px;
  }}
  .header h1 {{ margin: 0; font-size: 22px; font-weight: 700; letter-spacing: -0.01em; color: var(--ink-0); }}
  .header .meta {{ color: var(--ink-2); font-family: var(--mono); font-size: 11px; }}
  .summary {{
    display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; margin-bottom: 18px;
  }}
  .stat {{
    background: var(--bg-1); border: 1px solid var(--rule); border-radius: 6px;
    padding: 12px 14px;
  }}
  .stat .lbl {{ font-family: var(--mono); font-size: 9.5px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--ink-3); font-weight: 700; margin-bottom: 4px; }}
  .stat .val {{ font-size: 22px; font-weight: 800; font-family: var(--mono); color: var(--ink-0); }}
  .stat .sub {{ font-size: 11px; color: var(--ink-2); margin-top: 2px; }}
  .filters {{
    display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 12px;
  }}
  .chip {{
    padding: 6px 12px; border-radius: 4px; font-family: var(--mono); font-size: 10.5px;
    background: var(--bg-1); border: 1px solid var(--rule); color: var(--ink-1);
    cursor: pointer; user-select: none; letter-spacing: 0.06em; text-transform: uppercase; font-weight: 600;
  }}
  .chip.on {{ background: var(--bg-3); color: var(--ink-0); border-color: var(--info); }}
  .chip:hover {{ border-color: var(--ink-2); }}
  table {{
    width: 100%; border-collapse: collapse;
    background: var(--bg-1); border: 1px solid var(--rule); border-radius: 6px; overflow: hidden;
  }}
  th, td {{
    padding: 8px 12px; text-align: left; border-bottom: 1px solid var(--line);
    font-size: 12.5px;
  }}
  th {{
    background: var(--bg-2); font-family: var(--mono); font-size: 10px;
    letter-spacing: 0.08em; text-transform: uppercase; color: var(--ink-2); font-weight: 700;
    cursor: pointer; user-select: none;
    border-bottom: 1px solid var(--rule);
  }}
  th:hover {{ color: var(--ink-0); }}
  th.sort-desc::after {{ content: " ↓"; color: var(--info); }}
  th.sort-asc::after {{ content: " ↑"; color: var(--info); }}
  tbody tr:hover {{ background: var(--bg-2); }}
  td.num {{ text-align: right; font-family: var(--mono); font-variant-numeric: tabular-nums; }}
  td.dim {{ color: var(--ink-2); }}
  td.sym {{ font-family: var(--mono); font-weight: 700; color: var(--ink-0); }}
  td.tier {{ text-align: center; font-family: var(--mono); }}
  .badge {{
    display: inline-block; padding: 2px 8px; border-radius: 3px;
    font-family: var(--mono); font-size: 9.5px; letter-spacing: 0.08em;
    text-transform: uppercase; font-weight: 700;
  }}
  .verdict-buy {{ background: color-mix(in oklch, var(--gn) 18%, transparent); color: var(--gn); border: 1px solid color-mix(in oklch, var(--gn) 40%, transparent); }}
  .verdict-watch {{ background: color-mix(in oklch, var(--amb) 18%, transparent); color: var(--amb); border: 1px solid color-mix(in oklch, var(--amb) 40%, transparent); }}
  .verdict-wait {{ background: color-mix(in oklch, var(--ink-3) 18%, transparent); color: var(--ink-2); border: 1px solid var(--rule); }}
  .verdict-avoid {{ background: color-mix(in oklch, var(--rd) 18%, transparent); color: var(--rd); border: 1px solid color-mix(in oklch, var(--rd) 40%, transparent); }}
  .lens-key {{
    margin-top: 18px; padding: 14px 18px;
    background: var(--bg-1); border: 1px solid var(--rule); border-radius: 6px;
  }}
  .lens-key h3 {{ margin: 0 0 8px; font-size: 13px; color: var(--ink-1); font-weight: 700; letter-spacing: 0.04em; }}
  .lens-key div {{ font-size: 12px; color: var(--ink-2); line-height: 1.7; }}
  .lens-key b {{ color: var(--ink-1); }}
</style>
</head>
<body>
  <div class="header">
    <h1>Sharpe Screen</h1>
    <div class="meta">
      generated {today} ·
      threshold ≥ <b style="color:var(--ink-0)">{threshold}</b> ·
      lookback <b style="color:var(--ink-0)">{lookback}d</b> ·
      <b style="color:var(--gn)">{n_above}</b> above / {n_computed} computed / {n_scan} scan
    </div>
  </div>

  <div class="summary">
    <div class="stat"><div class="lbl">Total ≥ {threshold}</div><div class="val">{n_above}</div><div class="sub">of {n_scan} scan tickers</div></div>
    <div class="stat"><div class="lbl">Tier A</div><div class="val" style="color:var(--gn)">{tier_counts['A']}</div><div class="sub">score ≥ 70 · Sharpe ≥ 2.0</div></div>
    <div class="stat"><div class="lbl">Tier B</div><div class="val" style="color:var(--amb)">{tier_counts['B']}</div><div class="sub">score 50–69 · Sharpe ≥ 2.0</div></div>
    <div class="stat"><div class="lbl">Tier C</div><div class="val" style="color:var(--rd)">{tier_counts['C']}</div><div class="sub">score ≤ 5 · Sharpe ≥ 1.5 (labeling bug?)</div></div>
    <div class="stat"><div class="lbl">Other</div><div class="val" style="color:var(--ink-2)">{tier_counts['—']}</div><div class="sub">below tier thresholds</div></div>
  </div>

  <div class="filters">
    <span class="chip on" data-filter="all">All ({n_above})</span>
    <span class="chip" data-filter="A">Tier A ({tier_counts['A']})</span>
    <span class="chip" data-filter="B">Tier B ({tier_counts['B']})</span>
    <span class="chip" data-filter="C">Tier C — labeling bug ({tier_counts['C']})</span>
    <span class="chip" data-filter="entry">Good entry (FRESH/PULLBACK/VALID)</span>
    <span class="chip" data-filter="earn-safe">Earnings ≥ 14d</span>
  </div>

  <table id="t">
    <thead>
      <tr>
        <th data-sort="num">#</th>
        <th data-sort="tier">Tier</th>
        <th data-sort="sym">Sym</th>
        <th data-sort="num" class="sort-desc">Sharpe</th>
        <th data-sort="num">Ret/yr</th>
        <th data-sort="num">Vol/yr</th>
        <th data-sort="num">Score</th>
        <th data-sort="sym">Verdict</th>
        <th data-sort="sym">Entry</th>
        <th data-sort="sym">Setup</th>
        <th data-sort="sym">Sector</th>
        <th data-sort="num">Earn</th>
      </tr>
    </thead>
    <tbody>
{body_table}
    </tbody>
  </table>

  <div class="lens-key">
    <h3>5-Lens Tier Logic</h3>
    <div>
      <b style="color:var(--gn)">Tier A</b> — Hedge fund + composite-score + price-action all agree (score ≥ 70 + Sharpe ≥ 2.0). Highest conviction. Tech-heavy means CFP-lens flags concentration risk.<br>
      <b style="color:var(--amb)">Tier B</b> — Score 50–69 + Sharpe ≥ 2.0. Mid-conviction; sector diversification candidates often live here.<br>
      <b style="color:var(--rd)">Tier C</b> — Sharpe ≥ 1.5 but composite score ≤ 5. Likely the EMA21-Pullback labeling bug: trade plan classified them as a killed setup. <b>Investigate</b>.<br>
      <b>Buffett lens</b>: at +60% to +200% annualized, NONE of these have margin of safety. Strategy is pure momentum/swing — accept that mandate or skip.
    </div>
  </div>

<script>
  // Filter chips
  document.querySelectorAll('.chip').forEach(c => {{
    c.addEventListener('click', () => {{
      document.querySelectorAll('.chip').forEach(x => x.classList.remove('on'));
      c.classList.add('on');
      const f = c.dataset.filter;
      document.querySelectorAll('#t tbody tr').forEach(tr => {{
        let show = true;
        if (f === 'A' || f === 'B' || f === 'C') show = (tr.dataset.tier === f);
        if (f === 'entry') show = ['FRESH','PULLBACK','VALID'].includes((tr.cells[8].textContent || '').trim().toUpperCase());
        if (f === 'earn-safe') {{
          const ed = (tr.cells[11].textContent || '').trim();
          if (ed === '—') show = true;
          else show = parseInt(ed) >= 14;
        }}
        tr.style.display = show ? '' : 'none';
      }});
    }});
  }});

  // Click-to-sort headers
  let _sortDir = {{}};
  document.querySelectorAll('#t thead th').forEach((th, ix) => {{
    th.addEventListener('click', () => {{
      const dir = _sortDir[ix] === 'desc' ? 'asc' : 'desc';
      _sortDir = {{[ix]: dir}};
      const isNum = th.dataset.sort === 'num';
      document.querySelectorAll('#t thead th').forEach(x => x.classList.remove('sort-desc','sort-asc'));
      th.classList.add('sort-' + dir);
      const tbody = document.querySelector('#t tbody');
      const rows = Array.from(tbody.querySelectorAll('tr'));
      rows.sort((a, b) => {{
        const av = a.cells[ix].textContent.trim().replace('%','').replace('+','').replace('—','-9999');
        const bv = b.cells[ix].textContent.trim().replace('%','').replace('+','').replace('—','-9999');
        if (isNum) {{
          const an = parseFloat(av) || -9999;
          const bn = parseFloat(bv) || -9999;
          return dir === 'desc' ? (bn - an) : (an - bn);
        }}
        return dir === 'desc' ? bv.localeCompare(av) : av.localeCompare(bv);
      }});
      rows.forEach(r => tbody.appendChild(r));
    }});
  }});
</script>
</body>
</html>"""

    out_p = REPO / "cache" / "sharpe_screen.html"
    out_p.write_text(html)
    print(f"Wrote: {out_p}  ({len(html):,} bytes · {len(rows)} tickers · A:{tier_counts['A']} B:{tier_counts['B']} C:{tier_counts['C']})")
    print()
    print(f"Open: file://{out_p}")
    print(f"Or serve: http://localhost:7432/sharpe_screen.html  (needs route — see server.py)")


if __name__ == "__main__":
    main()

"""Build scanner_v2_d.html — Option C + sidebar + table + filters with REAL data.

Reads cache/last_bundle.json + cache/ml_edge_predictions.json and emits a self-
contained HTML mockup at infra/prototype/mockups/scanner_v2_d.html.
"""
from __future__ import annotations
import json
import os
from pathlib import Path

BASE = Path(__file__).resolve().parents[3]   # SwingTrade root
BUNDLE = BASE / 'cache' / 'last_bundle.json'
ML     = BASE / 'cache' / 'ml_edge_predictions.json'
OUT    = Path(__file__).resolve().parent / 'scanner_v2_d.html'

print(f'reading {BUNDLE.relative_to(BASE)} ...')
b = json.loads(BUNDLE.read_text())
ml = {}
if ML.exists():
    ml = json.loads(ML.read_text())
print(f'  loaded · all_scored {len(b.get("all_scored", []))} · ml swing {len(ml.get("predictions", {}).get("swing", {}))}')

ascored = b.get('all_scored') or []
regime = b.get('regime') or {}

# ─── Verdict counts for the donut + chip bar ──────────────────────────
# Real verdict mapping from live data:
#   BUY → strong long signal
#   WATCH → on the radar, no capital
#   WAIT → conditions not met yet, neutral
#   AVOID → killed / rejected (conviction demoted, sector cap, etc.)
counts = {'BUY':0, 'WATCH':0, 'WAIT':0, 'AVOID':0, 'SHORT':0}
for t in ascored:
    v = (t.get('verdict') or '').upper()
    if v in counts: counts[v] += 1
TOTAL = len(ascored)
BUY_N = counts['BUY']
WATCH_N = counts['WATCH']
NEUT_N = counts['WAIT']
KILL_N = counts['AVOID'] + counts['SHORT']

# ─── Helper to build a compact row payload ────────────────────────────
def compact_row(t):
    tp = t.get('trade_plan') or {}
    ctp = t.get('canonical_trade_plan') or {}
    sb = t.get('score_breakdown') or {}
    e  = t.get('earnings') or {}
    pillars = [
        round(sb.get('tech', 0) or 0, 1),
        round(sb.get('catalyst', 0) or 0, 1),
        round(sb.get('rs', 0) or 0, 1),
        round(sb.get('smart_money', 0) or 0, 1),
        round(sb.get('quality_gate', 0) or 0, 1),
    ]
    # entry zone — mid of entry_low/high if present
    e_low = tp.get('entry_low'); e_high = tp.get('entry_high')
    e_mid = (e_low + e_high)/2 if e_low and e_high else (t.get('price') or 0)
    # ohlcv → last 28 closes for sparkline
    oh = t.get('ohlcv') or []
    if isinstance(oh, list):
        closes = [r.get('close') for r in oh[-28:] if isinstance(r, dict) and r.get('close') is not None]
    else:
        closes = []
    return {
        'sym':  t.get('ticker'),
        'score': int(round(t.get('score') or 0)),
        'verdict': t.get('verdict'),
        'killed':  bool(t.get('reject_reason')),
        'reject_reason': t.get('reject_reason'),
        'tier': ctp.get('conviction_tier') or '—',
        'setup': tp.get('setup_type') or t.get('setup_family') or '—',
        'family': t.get('setup_family') or '—',
        'sector': t.get('sector') or '—',
        'industry': t.get('industry') or '—',
        'rs': t.get('rs_rank'),
        'rsi': t.get('rsi'),
        'rvol': t.get('rvol'),
        'price': t.get('price'),
        'entry_low':  e_low,
        'entry_high': e_high,
        'entry_mid':  round(e_mid, 2) if e_mid else None,
        'stop':       tp.get('stop')   or ctp.get('stop'),
        't1':         tp.get('target1') or ctp.get('target1'),
        't2':         tp.get('target2') or ctp.get('target2'),
        'rr':         tp.get('rr_ratio'),
        'hold':       tp.get('max_hold_days'),
        'entry_quality': t.get('entry_quality') or '—',
        'cat_tier': t.get('catalyst_tier'),
        'earn_days': e.get('days_to_earnings'),
        'pillars': pillars,
        'closes': closes,
        'star_rating': t.get('star_rating'),
        'momentum': t.get('raw_momentum_score'),
        'mode_swing':  (t.get('decisions_by_mode') or {}).get('swing'),
        'allocation_pct': tp.get('allocation_pct'),
    }

# ─── Extract BUYs (verdict='BUY' and not killed) ────────────────────────
buys = sorted(
    [compact_row(t) for t in ascored if (t.get('verdict') == 'BUY' and not t.get('reject_reason'))],
    key=lambda r: -(r['score'] or 0),
)
print(f'  BUYs extracted: {len(buys)} → {[b["sym"] for b in buys]}')

# ─── Sidebar panels ───────────────────────────────────────────────────
def fresh_panel():
    rows = [compact_row(t) for t in ascored if t.get('entry_quality') == 'FRESH' and not t.get('reject_reason')]
    rows.sort(key=lambda r: -(r['score'] or 0))
    return rows[:5]

def earnings_panel():
    out = []
    for t in ascored:
        e = t.get('earnings') or {}
        d = e.get('days_to_earnings')
        if d is None: continue
        if 0 <= d <= 7:
            r = compact_row(t)
            r['earn_label'] = f'+{d}d' if d > 0 else 'TODAY'
            out.append(r)
    out.sort(key=lambda r: r['earn_days'] or 99)
    return out[:5]

def surges_panel():
    rows = [compact_row(t) for t in ascored if (t.get('rvol') or 0) >= 1.5]
    rows.sort(key=lambda r: -(r['rvol'] or 0))
    return rows[:5]

def momentum_panel():
    rows = [compact_row(t) for t in ascored if (t.get('raw_momentum_score') or 0) > 0]
    rows.sort(key=lambda r: -(r['momentum'] or 0))
    return rows[:5]

def ai_panel():
    pool = (ml.get('predictions') or {}).get('swing') or {}
    items = []
    for sym, p in pool.items():
        d = p.get('direction') or {}
        p_up = d.get('p_up') or 0
        edge = (p.get('verdict') or {}).get('edge') or d.get('edge') or 0
        items.append({'sym': sym, 'p_up': p_up, 'edge': edge, 'verdict': (p.get('verdict') or {}).get('text', '—')})
    items.sort(key=lambda x: -x['p_up'])
    return items[:5]

panels = {
    'fresh':    fresh_panel(),
    'earnings': earnings_panel(),
    'surges':   surges_panel(),
    'momentum': momentum_panel(),
    'ai':       ai_panel(),
}
for k, v in panels.items():
    print(f'  panel[{k}]: {len(v)}')

# ─── Table data — top 60 rows by score (full universe) ────────────────
table_rows = sorted(
    [compact_row(t) for t in ascored],
    key=lambda r: -(r['score'] or 0),
)[:60]
print(f'  table rows: {len(table_rows)}')

# ─── Build pulse strip data ───────────────────────────────────────────
vix = (regime.get('vix') or {})
pulse = {
    'regime4': regime.get('regime4') or 'neutral',
    'regime_label': (regime.get('regime4') or 'neutral').replace('_', ' ').upper(),
    'vix': vix.get('vix_current') or regime.get('vix_current') or 0,
    'vix_state': vix.get('vol_state', '—'),
    'vix_trend': vix.get('trend', '—'),
    'breadth': regime.get('breadth_pct_50d') or 0,
    'spy_price': regime.get('spy_price'),
    'spy_chg': regime.get('spy_daily_chg'),
    'sectors_outperforming': ((regime.get('sector_dispersion') or {}).get('sectors_outperforming_spy') or 0),
}

LAST_SCAN = b.get('run_timestamp') or b.get('run_date') or '—'

payload = {
    'last_scan': LAST_SCAN,
    'pulse': pulse,
    'counts': {'total': TOTAL, 'buy': BUY_N, 'watch': WATCH_N, 'neut': NEUT_N, 'kill': KILL_N},
    'buys': buys,
    'panels': panels,
    'table': table_rows,
}

print('writing HTML ...')

HTML = r'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Signal Scanner · Option D · Full Workspace</title>
  <style>
    :root {
      --bg:#08090c; --bg-1:#0d1014; --bg-2:#11151b; --card:#12161d; --card-hi:#171c25;
      --border:#1f2937; --border-hi:#334155; --border-soft:rgba(255,255,255,0.06);
      --ink:#f3f4f6; --ink-2:#d1d5db; --mute:#9ca3af; --mute-2:#6b7280; --mute-3:#4b5563;
      --copper:#c97b3a; --copper-hi:#e09850;
      --gn:#10b981; --gn-hi:#34d399; --gn-bg:rgba(16,185,129,0.10); --gn-glow:rgba(16,185,129,0.30);
      --rd:#f87171; --rd-bg:rgba(248,113,113,0.10);
      --am:#f59e0b; --am-hi:#fbbf24; --am-bg:rgba(245,158,11,0.10);
      --bl:#3b82f6; --bl-bg:rgba(59,130,246,0.10);
      --pl:#a78bfa; --pl-bg:rgba(167,139,250,0.10);
      --ti:#22d3ee;
    }
    *{box-sizing:border-box}
    body{margin:0;background:radial-gradient(ellipse at top, #0c1115 0%, var(--bg) 60%);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Inter,sans-serif;padding:14px 22px 64px;min-height:100vh;line-height:1.45}
    .back{color:var(--mute);font-size:0.78rem;text-decoration:none;margin-bottom:12px;display:inline-block}
    .back:hover{color:var(--copper-hi)}
    .wrap{max-width:1840px;margin:0 auto}

    /* ════════ HEADER ════════ */
    .hd{display:flex;align-items:center;justify-content:space-between;margin:4px 0 14px;padding:13px 18px;background:linear-gradient(180deg,var(--card) 0%,var(--bg-1) 100%);border:1px solid var(--border);border-radius:14px;position:relative;overflow:hidden}
    .hd::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,var(--gn),var(--copper),var(--am))}
    .hd-l{display:flex;align-items:center;gap:14px}
    .hd-l .dot{width:9px;height:9px;border-radius:50%;background:var(--gn);animation:pulse 2.4s infinite}
    @keyframes pulse{0%{box-shadow:0 0 0 0 var(--gn-glow)}70%{box-shadow:0 0 0 8px transparent}100%{box-shadow:0 0 0 0 transparent}}
    .hd-l .brand{color:var(--copper);font-weight:700;font-size:0.72rem;letter-spacing:0.14em;text-transform:uppercase}
    .hd-l h1{font-family:'Playfair Display',Georgia,serif;font-style:italic;font-weight:400;margin:0;font-size:1.65rem;background:linear-gradient(180deg,#fff 0%,#cbd5e1 100%);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}

    .hd-stats{display:flex;align-items:center;gap:14px;flex-wrap:wrap}
    .hs-cell{display:flex;align-items:center;gap:8px;padding:0 12px;border-right:1px solid var(--border-soft);height:38px}
    .hs-cell:last-child{border-right:none}
    .hs-lbl{font-size:0.58rem;color:var(--mute-2);text-transform:uppercase;letter-spacing:0.08em;font-weight:700;line-height:1.1}
    .hs-val{font-size:1.1rem;font-weight:700;font-family:ui-monospace,monospace;color:var(--ink);line-height:1.1}
    .hs-val.gn{color:var(--gn)} .hs-val.am{color:var(--am)} .hs-val.rd{color:var(--rd)} .hs-val.bl{color:var(--bl)}
    .hs-pill{display:inline-flex;align-items:center;gap:5px;padding:4px 9px;border-radius:999px;font-size:0.66rem;font-weight:700;background:var(--am-bg);color:var(--am);border:1px solid var(--am);text-transform:uppercase}
    .hs-pill.gn{background:var(--gn-bg);color:var(--gn);border-color:var(--gn)}
    .hs-pill.rd{background:var(--rd-bg);color:var(--rd);border-color:var(--rd)}
    .hs-pill .pd{width:5px;height:5px;border-radius:50%;background:currentColor;animation:pulse 2s infinite}
    .hs-bar{width:64px;height:6px;background:var(--bg-2);border-radius:3px;overflow:hidden;position:relative}
    .hs-fill{height:100%;background:linear-gradient(90deg,var(--rd),var(--am),var(--gn));opacity:0.5}
    .hs-marker{position:absolute;top:-2px;width:2px;height:10px;background:var(--ink)}
    .hs-gauge{width:52px;height:28px}

    /* ════════ LAYOUT — main + sidebar ════════ */
    .layout{display:grid;grid-template-columns:1fr 340px;gap:14px;margin-bottom:18px}
    @media (max-width:1200px){.layout{grid-template-columns:1fr}}

    /* ════════ MEGA CARDS ════════ */
    .sec-hd{display:flex;align-items:flex-end;justify-content:space-between;margin:4px 0 14px}
    .sec-hd .ttl{font-family:'Playfair Display',Georgia,serif;font-style:italic;font-size:1.4rem;color:var(--ink);font-weight:400;display:flex;align-items:baseline;gap:12px}
    .sec-hd .ttl .cnt{background:var(--gn-bg);color:var(--gn);border:1px solid var(--gn);padding:3px 10px;border-radius:999px;font-size:0.72rem;font-weight:700;font-style:normal;font-family:ui-monospace,monospace;letter-spacing:0.05em}
    .sec-hd .meta{color:var(--mute);font-size:0.72rem}

    .megacards{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:14px;margin-bottom:20px}
    .mc{background:linear-gradient(160deg,var(--card) 0%,var(--bg-1) 100%);border:1px solid var(--border);border-radius:14px;padding:16px 16px 14px;position:relative;overflow:hidden;cursor:pointer;transition:all .2s cubic-bezier(0.4,0,0.2,1);display:flex;flex-direction:column;gap:12px}
    .mc::before{content:'';position:absolute;top:0;left:0;right:0;height:4px;background:linear-gradient(90deg,var(--gn) 0%,var(--copper) 60%,var(--am) 100%)}
    .mc::after{content:'';position:absolute;top:-30px;right:-30px;width:120px;height:120px;background:radial-gradient(circle,var(--gn-glow) 0%,transparent 70%);opacity:0;transition:opacity .25s}
    .mc:hover{transform:translateY(-2px);border-color:var(--gn);box-shadow:0 12px 32px rgba(16,185,129,0.12),0 4px 12px rgba(0,0,0,0.5)}
    .mc:hover::after{opacity:1}

    .mc-row1{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;position:relative;z-index:2}
    .mc-left{display:flex;flex-direction:column;gap:5px}
    .mc-sym{font-size:1.75rem;font-weight:800;font-family:ui-monospace,monospace;color:var(--ink);line-height:1;letter-spacing:0.01em}
    .mc-livepx{display:flex;align-items:baseline;gap:8px;font-family:ui-monospace,monospace;font-size:0.78rem;color:var(--mute)}
    .mc-livepx b{color:var(--ink-2);font-weight:700;font-size:0.95rem}
    .mc-right{text-align:right;display:flex;flex-direction:column;align-items:flex-end;gap:3px}
    .mc-score{font-size:2.3rem;font-weight:800;font-family:ui-monospace,monospace;color:var(--gn);line-height:1;text-shadow:0 0 24px var(--gn-glow)}
    .mc-score-lbl{font-size:0.6rem;color:var(--mute-2);text-transform:uppercase;letter-spacing:0.1em;font-weight:700}
    .mc-tier-row{display:flex;gap:5px;margin-top:4px;flex-wrap:wrap;justify-content:flex-end}

    .chip{display:inline-block;padding:3px 8px;border-radius:6px;font-size:0.65rem;font-weight:700;letter-spacing:0.04em;background:var(--bg-2);color:var(--mute);border:1px solid var(--border);font-family:ui-monospace,monospace;text-transform:uppercase}
    .chip.tier1{background:var(--gn-bg);color:var(--gn);border-color:var(--gn)}
    .chip.tier2{background:var(--bl-bg);color:var(--bl);border-color:var(--bl)}
    .chip.tier3{background:var(--am-bg);color:var(--am);border-color:var(--am)}
    .chip.setup{background:var(--copper);color:#fff;border-color:var(--copper)}
    .chip.sector{background:var(--bg-2);color:var(--ink-2);border-color:var(--border-hi)}
    .chip.eq{background:var(--pl-bg);color:var(--pl);border-color:var(--pl)}

    .mc-mid{display:grid;grid-template-columns:1.5fr 1fr;gap:12px;align-items:stretch}
    .mc-spark-wrap{position:relative;background:var(--bg-1);border:1px solid var(--border-soft);border-radius:9px;padding:7px 9px;display:flex;flex-direction:column;gap:3px}
    .mc-spark-hdr{display:flex;justify-content:space-between;font-family:ui-monospace,monospace;font-size:0.6rem;color:var(--mute-2)}
    .mc-spark-hdr b{color:var(--ink-2);font-weight:700}
    .mc-spark{height:58px;width:100%;display:block}
    .mc-radar-wrap{background:var(--bg-1);border:1px solid var(--border-soft);border-radius:9px;padding:7px;display:flex;align-items:center;justify-content:center;position:relative}
    .mc-radar{width:100%;height:80px}
    .mc-radar-lbl{position:absolute;top:5px;left:8px;font-size:0.58rem;color:var(--mute-2);text-transform:uppercase;letter-spacing:0.08em;font-weight:700;font-family:ui-monospace,monospace}

    .mc-ladder{background:var(--bg-1);border:1px solid var(--border-soft);border-radius:9px;padding:12px 10px 6px;font-family:ui-monospace,monospace}
    .mc-ladder-hdr{display:flex;justify-content:space-between;font-size:0.6rem;color:var(--mute-2);text-transform:uppercase;letter-spacing:0.08em;font-weight:700;margin-bottom:7px}
    .mc-ladder-track{position:relative;height:26px;margin:0 6px}
    .mc-ladder-line{position:absolute;top:12px;left:0;right:0;height:3px;background:linear-gradient(90deg,var(--rd) 0%,#dc2626 8%,var(--am) 35%,#34d399 60%,var(--gn) 100%);border-radius:2px}
    .mc-ladder-tick{position:absolute;top:8px;width:2px;height:11px;background:rgba(255,255,255,0.55);border-radius:1px}
    .mc-ladder-dot{position:absolute;top:4px;width:16px;height:16px;border-radius:50%;background:var(--ink);border:3px solid var(--bg-1);box-shadow:0 0 0 1.5px var(--ink);transform:translateX(-8px)}
    .mc-ladder-lbl{position:absolute;font-size:0.58rem;font-weight:700;letter-spacing:0.04em;transform:translateX(-50%);white-space:nowrap}
    .mc-ladder-lbl.top{top:-12px}
    .mc-ladder-lbl.bot{top:24px}

    .rrbar{display:flex;align-items:center;gap:9px;font-size:0.72rem;color:var(--mute);font-family:ui-monospace,monospace;padding:0 2px}
    .rrlbl{color:var(--mute-2);font-weight:700;font-size:0.6rem;letter-spacing:0.1em;text-transform:uppercase;flex-shrink:0}
    .rrtrack{flex-grow:1;height:8px;background:var(--bg-2);border-radius:5px;position:relative;overflow:hidden;display:flex;border:1px solid var(--border-soft)}
    .rrtrack .risk{background:linear-gradient(90deg,#dc2626,var(--rd));height:100%}
    .rrtrack .reward{background:linear-gradient(90deg,var(--gn),var(--gn-hi));height:100%}
    .rrbar b{color:var(--gn);font-weight:800;flex-shrink:0;font-size:0.85rem}

    .mc-narr{font-size:0.74rem;color:var(--mute);line-height:1.5;font-style:italic;padding:9px 11px;background:var(--bg-1);border-radius:8px;border-left:3px solid var(--copper)}
    .mc-actions{display:flex;gap:6px}
    .mc-action{flex:1;background:var(--bg-2);border:1px solid var(--border);color:var(--ink-2);font-size:0.72rem;padding:8px;border-radius:8px;font-weight:700;letter-spacing:0.04em;cursor:pointer;font-family:inherit;transition:all .15s;text-transform:uppercase}
    .mc-action:hover{background:var(--copper);border-color:var(--copper);color:#fff;transform:translateY(-1px)}
    .mc-action.primary{background:var(--gn);color:#000;border-color:var(--gn)}
    .mc-action.primary:hover{background:var(--gn-hi);border-color:var(--gn-hi)}

    /* ════════ SIDEBAR ACCORDION ════════ */
    .sidebar{display:flex;flex-direction:column;gap:10px}
    .sb-card{background:var(--card);border:1px solid var(--border);border-radius:12px;overflow:hidden}
    .sb-hd{padding:11px 14px;display:flex;align-items:center;justify-content:space-between;cursor:pointer;transition:background .15s}
    .sb-hd:hover{background:var(--bg-2)}
    .sb-hd-l{display:flex;align-items:center;gap:8px;font-size:0.85rem;font-weight:700;letter-spacing:0.01em}
    .sb-hd .ico{font-size:1.05rem}
    .sb-hd-r{display:flex;align-items:center;gap:9px;font-size:0.72rem;color:var(--mute);font-family:ui-monospace,monospace}
    .sb-hd-r .cnt{background:var(--bg-2);color:var(--ink-2);padding:2px 8px;border-radius:5px;font-weight:700}
    .sb-hd .caret{color:var(--mute-2);transition:transform .15s;font-size:0.7rem}
    .sb-hd.open .caret{transform:rotate(180deg)}
    .sb-body{padding:8px 12px 12px;display:none;border-top:1px solid var(--border-soft)}
    .sb-body.show{display:block}
    .sb-row{display:flex;align-items:center;gap:9px;padding:8px 4px;border-bottom:1px dashed var(--border-soft);cursor:pointer;border-radius:5px}
    .sb-row:last-child{border-bottom:none}
    .sb-row:hover{background:var(--bg-2)}
    .sb-row .rk{font-family:ui-monospace,monospace;font-size:0.62rem;color:var(--mute-2);font-weight:700;flex-shrink:0;width:18px}
    .sb-row .sym{font-family:ui-monospace,monospace;font-weight:700;font-size:0.86rem;flex-shrink:0;width:62px}
    .sb-row .meta{font-size:0.66rem;color:var(--mute);flex-grow:1;line-height:1.35}
    .sb-row .meta b{color:var(--ink-2)}
    .sb-row .val{font-family:ui-monospace,monospace;font-weight:700;font-size:0.8rem;flex-shrink:0;text-align:right}
    .sb-row .val.gn{color:var(--gn)} .sb-row .val.am{color:var(--am)} .sb-row .val.rd{color:var(--rd)}
    .sb-row .mini-spark{width:36px;height:14px;flex-shrink:0}
    .sb-empty{padding:18px 6px;color:var(--mute-2);font-style:italic;font-size:0.74rem;text-align:center}

    /* ════════ FILTER BAR ════════ */
    .filterbar-wrap{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:12px 14px;margin-bottom:14px}
    .fb-row{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px;align-items:center}
    .fb-row:last-child{margin-bottom:0}
    .fb-lbl{font-size:0.62rem;color:var(--mute-2);text-transform:uppercase;letter-spacing:0.1em;font-weight:700;margin-right:8px;flex-shrink:0}
    .fchip{background:var(--bg-1);border:1px solid var(--border);color:var(--mute);font-size:0.72rem;padding:5px 10px;border-radius:7px;font-weight:600;cursor:pointer;font-family:inherit;display:flex;align-items:center;gap:5px;transition:all .15s}
    .fchip:hover{color:var(--ink);border-color:var(--border-hi)}
    .fchip.on{background:var(--copper);color:#fff;border-color:var(--copper)}
    .fchip .cnt{background:rgba(0,0,0,0.25);padding:0 5px;border-radius:3px;font-size:0.62rem;font-family:ui-monospace,monospace}
    .fchip:not(.on) .cnt{background:var(--bg-2);color:var(--mute-2)}
    .fb-search{margin-left:auto;display:flex;align-items:center;gap:6px}
    .fb-search input{background:var(--bg-1);border:1px solid var(--border);color:var(--ink);font-size:0.74rem;padding:6px 10px;border-radius:7px;width:220px;font-family:inherit;outline:none;transition:border-color .15s}
    .fb-search input:focus{border-color:var(--copper)}
    .fb-search input::placeholder{color:var(--mute-2)}

    /* ════════ TABLE ════════ */
    .table-wrap{background:var(--card);border:1px solid var(--border);border-radius:12px;overflow:hidden}
    .tb-hd{padding:12px 16px;border-bottom:1px solid var(--border-soft);display:flex;align-items:center;justify-content:space-between}
    .tb-title{font-family:'Playfair Display',Georgia,serif;font-style:italic;font-size:1.05rem;font-weight:400}
    .tb-meta{font-size:0.72rem;color:var(--mute);font-family:ui-monospace,monospace}
    .tb-scroll{max-height:520px;overflow-y:auto;overflow-x:auto}
    table{width:100%;border-collapse:collapse;font-size:0.74rem;font-family:ui-monospace,monospace;min-width:1300px}
    thead{position:sticky;top:0;background:var(--bg-2);z-index:2}
    th{padding:9px 10px;text-align:left;font-weight:700;color:var(--mute-2);text-transform:uppercase;letter-spacing:0.06em;font-size:0.62rem;border-bottom:1px solid var(--border);white-space:nowrap;cursor:pointer;user-select:none}
    th:hover{color:var(--copper-hi)}
    th.num{text-align:right}
    td{padding:8px 10px;border-bottom:1px solid var(--border-soft);color:var(--ink-2);white-space:nowrap}
    td.num{text-align:right}
    tr:hover td{background:var(--bg-2)}
    .vchip{display:inline-block;padding:1px 7px;border-radius:5px;font-size:0.62rem;font-weight:700;letter-spacing:0.04em}
    .vchip.BUY{background:var(--gn-bg);color:var(--gn);border:1px solid var(--gn)}
    .vchip.WATCH{background:var(--am-bg);color:var(--am);border:1px solid var(--am)}
    .vchip.NEUTRAL,.vchip.WAIT{background:var(--bg-2);color:var(--mute);border:1px solid var(--border)}
    .vchip.SHORT{background:var(--rd-bg);color:var(--rd);border:1px solid var(--rd)}
    .vchip.AVOID{background:var(--rd-bg);color:var(--rd);border:1px solid var(--rd)}
    .score-cell{font-weight:700}
    .score-cell.hi{color:var(--gn)}
    .score-cell.mid{color:var(--am)}
    .score-cell.lo{color:var(--mute)}
    .tbl-spark{width:62px;height:18px}

    .legend{margin-top:18px;text-align:center;color:var(--mute-2);font-size:0.72rem;padding-top:14px;border-top:1px dashed var(--border-soft)}
  </style>
</head>
<body>
  <div class="wrap">
    <a class="back" href="scanner_v2_index.html">← back to options</a>

    <!-- HEADER + PULSE -->
    <div class="hd">
      <div class="hd-l">
        <span class="dot"></span>
        <span class="brand">KAIROS · LIVE</span>
        <h1>Signal Scanner</h1>
      </div>
      <div class="hd-stats" id="hd-stats"></div>
    </div>

    <!-- LAYOUT: MAIN + SIDEBAR -->
    <div class="layout">
      <div>
        <!-- MEGA CARDS -->
        <div class="sec-hd">
          <div class="ttl">Today's BUYs <span class="cnt" id="buy-cnt"></span></div>
          <div class="meta">click → trade plan · all panels in sidebar →</div>
        </div>
        <div class="megacards" id="megacards"></div>
      </div>

      <!-- SIDEBAR -->
      <div class="sidebar" id="sidebar"></div>
    </div>

    <!-- FILTER BAR -->
    <div class="filterbar-wrap">
      <div class="fb-row">
        <span class="fb-lbl">Mode</span>
        <div class="fchip on">All <span class="cnt" id="cnt-all"></span></div>
        <div class="fchip">Swing</div>
        <div class="fchip">Position</div>
        <div class="fchip">Investment</div>
        <div class="fb-search"><span style="color:var(--mute-2);font-size:0.78rem">🔍</span><input type="text" id="search" placeholder="search ticker or name (/)"></div>
      </div>
      <div class="fb-row">
        <span class="fb-lbl">Verdict</span>
        <div class="fchip on">All</div>
        <div class="fchip">BUY <span class="cnt" id="cnt-buy"></span></div>
        <div class="fchip">WATCH <span class="cnt" id="cnt-watch"></span></div>
        <div class="fchip">NEUT <span class="cnt" id="cnt-neut"></span></div>
        <div class="fchip">KILLED <span class="cnt" id="cnt-kill"></span></div>
      </div>
      <div class="fb-row">
        <span class="fb-lbl">Entry</span>
        <div class="fchip">FRESH</div>
        <div class="fchip">PULLBACK</div>
        <div class="fchip">VALID</div>
        <div class="fchip">EXTENDED</div>
        <div class="fchip">MISSED</div>
        <div class="fchip">In Zone Now</div>
        <div class="fchip">Near Zone</div>
        <div class="fchip">≥14d</div>
      </div>
    </div>

    <!-- TABLE -->
    <div class="table-wrap">
      <div class="tb-hd">
        <div class="tb-title">Full Universe <span style="font-family:ui-monospace,monospace;color:var(--mute);font-size:0.72rem;font-style:normal">· top 60 by score · 228 total</span></div>
        <div class="tb-meta">click header to sort · click ticker for detail · CSV export</div>
      </div>
      <div class="tb-scroll">
        <table id="universe-table">
          <thead><tr>
            <th>Ticker</th>
            <th class="num">Score</th>
            <th>Verdict</th>
            <th>Tier</th>
            <th>Setup</th>
            <th>Sector</th>
            <th class="num">RS</th>
            <th class="num">RVOL</th>
            <th class="num">RSI</th>
            <th class="num">R:R</th>
            <th class="num">Entry</th>
            <th class="num">Stop</th>
            <th class="num">T1</th>
            <th>Entry Quality</th>
            <th class="num">Cat T</th>
            <th>5d Spark</th>
            <th class="num">Hold</th>
          </tr></thead>
          <tbody id="tb-body"></tbody>
        </table>
      </div>
    </div>

    <div class="legend">All data extracted live from <b style="color:var(--copper)">cache/last_bundle.json</b> · build by <b>build_scanner_v2_d.py</b></div>
  </div>

  <!-- ═════ DATA PAYLOAD ═════ -->
  <script id="data-payload" type="application/json">__PAYLOAD__</script>
  <script>
    const DATA = JSON.parse(document.getElementById('data-payload').textContent);

    // ─── HEADER PULSE STATS ──────────────────────────────────────────
    function renderPulse() {
      const p = DATA.pulse, c = DATA.counts;
      const regimeColor = p.regime4.includes('panic') ? 'rd' : p.regime4.includes('risk_off') ? 'rd' : p.regime4.includes('choppy') ? 'am' : 'gn';
      // VIX gauge needle position (10-50 range, ~26% for 16.9)
      const vixPct = Math.min(Math.max((p.vix - 10) / 40, 0), 1);
      const vixAngle = 180 + vixPct * 180; // 180 to 360 degrees
      const needleX = 50 + 25 * Math.cos(vixAngle * Math.PI / 180);
      const needleY = 45 + 25 * Math.sin(vixAngle * Math.PI / 180);
      const breadthPct = p.breadth || 0;
      const html = `
        <div class="hs-cell">
          <div>
            <div class="hs-lbl">Regime</div>
          </div>
          <div class="hs-pill ${regimeColor}"><span class="pd"></span>${p.regime_label}</div>
        </div>
        <div class="hs-cell">
          <svg class="hs-gauge" viewBox="0 0 100 50">
            <path d="M 10 45 A 40 40 0 0 1 90 45" fill="none" stroke="#1f2937" stroke-width="6" stroke-linecap="round"/>
            <path d="M 10 45 A 40 40 0 0 1 42 8" fill="none" stroke="#10b981" stroke-width="6" stroke-linecap="round"/>
            <path d="M 42 8 A 40 40 0 0 1 58 8" fill="none" stroke="#f59e0b" stroke-width="6"/>
            <path d="M 58 8 A 40 40 0 0 1 90 45" fill="none" stroke="#f87171" stroke-width="6" stroke-linecap="round"/>
            <line x1="50" y1="45" x2="${needleX.toFixed(1)}" y2="${needleY.toFixed(1)}" stroke="#fff" stroke-width="2" stroke-linecap="round"/>
            <circle cx="50" cy="45" r="3" fill="#c97b3a"/>
          </svg>
          <div>
            <div class="hs-lbl">VIX</div>
            <div class="hs-val">${p.vix.toFixed(1)} <span style="font-size:0.6rem;color:var(--gn)">${(p.vix_state||'').toUpperCase()}</span></div>
          </div>
        </div>
        <div class="hs-cell">
          <div>
            <div class="hs-lbl">Breadth</div>
            <div class="hs-val">${breadthPct.toFixed(0)}%</div>
          </div>
          <div class="hs-bar"><div class="hs-fill" style="width:100%"></div><div class="hs-marker" style="left:${breadthPct}%"></div></div>
        </div>
        <div class="hs-cell">
          <div><div class="hs-lbl">SPY</div><div class="hs-val">${(p.spy_price||0).toFixed(0)} <span style="font-size:0.6rem;color:${(p.spy_chg||0)>=0?'var(--gn)':'var(--rd)'}">${(p.spy_chg||0)>=0?'+':''}${(p.spy_chg||0).toFixed(1)}%</span></div></div>
        </div>
        <div class="hs-cell">
          <div><div class="hs-lbl">Scored</div><div class="hs-val">${c.total}</div></div>
        </div>
        <div class="hs-cell">
          <div><div class="hs-lbl">BUY</div><div class="hs-val gn">${c.buy}</div></div>
        </div>
        <div class="hs-cell">
          <div><div class="hs-lbl">WATCH</div><div class="hs-val am">${c.watch}</div></div>
        </div>
        <div class="hs-cell">
          <div><div class="hs-lbl">KILL</div><div class="hs-val rd">${c.kill}</div></div>
        </div>
        <div class="hs-cell">
          <div><div class="hs-lbl">Scan</div><div class="hs-val" style="font-size:0.74rem;color:var(--mute);font-weight:600">${(DATA.last_scan||'').slice(0,16).replace('T',' ')}</div></div>
        </div>
      `;
      document.getElementById('hd-stats').innerHTML = html;

      // Set filter counts
      document.getElementById('cnt-all').textContent = c.total;
      document.getElementById('cnt-buy').textContent = c.buy;
      document.getElementById('cnt-watch').textContent = c.watch;
      document.getElementById('cnt-neut').textContent = c.neut;
      document.getElementById('cnt-kill').textContent = c.kill;
      document.getElementById('buy-cnt').textContent = `${c.buy} ACTIVE`;
    }

    // ─── SPARKLINE FROM REAL OHLCV CLOSES ─────────────────────────────
    function sparkSvgFromCloses(closes, w, h, withMarker, withEnd) {
      if (!closes || closes.length < 2) return `<svg viewBox="0 0 ${w} ${h}"><line x1="0" y1="${h/2}" x2="${w}" y2="${h/2}" stroke="#374151" stroke-dasharray="2 2"/></svg>`;
      const min = Math.min(...closes), max = Math.max(...closes), range = max - min || 1;
      const pad = 3;
      const pts = closes.map((v, i) => {
        const x = pad + (i / (closes.length - 1)) * (w - 2 * pad);
        const y = h - pad - ((v - min) / range) * (h - 2 * pad);
        return [x, y];
      });
      const polyStr = pts.map(p => p.map(n => n.toFixed(1)).join(',')).join(' ');
      const trend = closes[closes.length-1] > closes[0] ? 'up' : closes[closes.length-1] < closes[0] ? 'down' : 'flat';
      const stroke = trend === 'up' ? '#10b981' : trend === 'down' ? '#f87171' : '#f59e0b';
      const fill = trend === 'up' ? 'rgba(16,185,129,0.15)' : trend === 'down' ? 'rgba(248,113,113,0.15)' : 'rgba(245,158,11,0.13)';
      const area = `${pad},${h-pad} ${polyStr} ${w-pad},${h-pad}`;
      const endDot = withEnd ? `<circle cx="${pts[pts.length-1][0].toFixed(1)}" cy="${pts[pts.length-1][1].toFixed(1)}" r="2.8" fill="#fff" stroke="${stroke}" stroke-width="1.5"/>` : '';
      return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
        <polyline points="${area}" fill="${fill}" stroke="none"/>
        <polyline points="${polyStr}" fill="none" stroke="${stroke}" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/>
        ${endDot}
      </svg>`;
    }

    // ─── RADAR / SPIDER for 5 pillars ─────────────────────────────────
    function radarSvg(pillars) {
      const max = [35, 20, 20, 15, 10];
      const labels = ['TEC','CAT','RS','SM','QG'];
      const cx = 60, cy = 45, r = 32, n = 5;
      const angle = i => -Math.PI/2 + (i * 2 * Math.PI / n);
      const polyAt = vals => vals.map((v, i) => {
        const norm = Math.min(v / max[i], 1);
        return `${(cx + r * norm * Math.cos(angle(i))).toFixed(1)},${(cy + r * norm * Math.sin(angle(i))).toFixed(1)}`;
      }).join(' ');
      let grid = '';
      [0.33, 0.66, 1.0].forEach(level => {
        const pts = [];
        for (let i = 0; i < n; i++) {
          pts.push(`${(cx + r * level * Math.cos(angle(i))).toFixed(1)},${(cy + r * level * Math.sin(angle(i))).toFixed(1)}`);
        }
        grid += `<polygon points="${pts.join(' ')}" fill="none" stroke="#1f2937" stroke-width="0.7"/>`;
      });
      let axes = '', labelTxt = '';
      for (let i = 0; i < n; i++) {
        const x = cx + r * Math.cos(angle(i)), y = cy + r * Math.sin(angle(i));
        axes += `<line x1="${cx}" y1="${cy}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}" stroke="#1f2937" stroke-width="0.7"/>`;
        const lx = cx + (r + 7) * Math.cos(angle(i)), ly = cy + (r + 7) * Math.sin(angle(i)) + 2;
        labelTxt += `<text x="${lx.toFixed(1)}" y="${ly.toFixed(1)}" font-size="6.5" fill="#6b7280" font-family="ui-monospace,monospace" text-anchor="middle" font-weight="700">${labels[i]}</text>`;
      }
      return `<svg class="mc-radar" viewBox="0 0 120 90">
        ${grid}${axes}
        <polygon points="${polyAt(pillars)}" fill="rgba(201,123,58,0.25)" stroke="#c97b3a" stroke-width="1.4"/>
        ${labelTxt}
      </svg>`;
    }

    function tierClass(t) { return t === 'T1' ? 'tier1' : t === 'T2' ? 'tier2' : 'tier3'; }

    function priceLadder(b) {
      if (!b.stop || !b.t1) return '<div class="mc-ladder" style="color:var(--mute-2);font-size:0.7rem">trade plan missing — see canonical_trade_plan</div>';
      const range = b.t1 - b.stop;
      const now = b.price || b.entry_mid || b.stop;
      const entry = b.entry_mid || b.entry_low || now;
      const nowPct = Math.max(0, Math.min(100, ((now - b.stop) / range) * 100));
      const entryPct = Math.max(0, Math.min(100, ((entry - b.stop) / range) * 100));
      return `
        <div class="mc-ladder">
          <div class="mc-ladder-hdr">
            <span style="color:var(--rd)">STOP ${b.stop.toFixed(2)}</span>
            <span style="color:var(--copper-hi)">ENTRY ${entry.toFixed(2)}</span>
            <span style="color:var(--gn)">T1 ${b.t1.toFixed(2)}</span>
          </div>
          <div class="mc-ladder-track">
            <div class="mc-ladder-line"></div>
            <div class="mc-ladder-tick" style="left:${entryPct}%"></div>
            <div class="mc-ladder-dot" style="left:${nowPct}%"></div>
            <div class="mc-ladder-lbl bot" style="left:${nowPct}%;color:var(--ink)">NOW ${now.toFixed(2)}</div>
          </div>
        </div>`;
    }

    function renderMegaCards() {
      if (!DATA.buys.length) {
        document.getElementById('megacards').innerHTML = '<div style="grid-column:1/-1;padding:48px;text-align:center;color:var(--mute-2);background:var(--card);border:1px dashed var(--border);border-radius:12px;font-style:italic">No BUY signals in this scan · check WATCH list →</div>';
        return;
      }
      const html = DATA.buys.map(b => {
        const rr = b.rr || 0;
        const riskPct = (1 / (1 + rr)) * 100;
        const rewardPct = (rr / (1 + rr)) * 100;
        const chgFromOpen = b.closes && b.closes.length >= 2 ? ((b.closes[b.closes.length-1] - b.closes[b.closes.length-2]) / b.closes[b.closes.length-2] * 100) : 0;
        const pctClass = chgFromOpen >= 0 ? 'up' : 'dn';
        const pctSign = chgFromOpen >= 0 ? '+' : '';
        const sparkHi = b.closes && b.closes.length ? Math.max(...b.closes).toFixed(2) : '—';
        const sparkLo = b.closes && b.closes.length ? Math.min(...b.closes).toFixed(2) : '—';
        const narr = `${b.setup || b.family} · ${b.sector} · RS ${b.rs ?? '—'} · RVOL ${(b.rvol||0).toFixed(2)} · catalyst T${b.cat_tier ?? '—'} · entry ${b.entry_quality}${b.earn_days != null ? ` · earnings ${b.earn_days}d` : ''}`;
        return `
          <div class="mc">
            <div class="mc-row1">
              <div class="mc-left">
                <div class="mc-sym">${b.sym}</div>
                <div class="mc-livepx"><b>$${(b.price||0).toFixed(2)}</b><span class="pct ${pctClass}" style="color:var(--${pctClass==='up'?'gn':'rd'});padding:1px 6px;background:rgba(${pctClass==='up'?'16,185,129':'248,113,113'},0.12);border-radius:5px;font-weight:700">${pctSign}${chgFromOpen.toFixed(2)}%</span></div>
              </div>
              <div class="mc-right">
                <div class="mc-score">${b.score}</div>
                <div class="mc-score-lbl">composite</div>
                <div class="mc-tier-row">
                  <span class="chip ${tierClass(b.tier)}">${b.tier}</span>
                  <span class="chip setup">${(b.setup || b.family).slice(0,12)}</span>
                </div>
              </div>
            </div>
            <div class="mc-mid">
              <div class="mc-spark-wrap">
                <div class="mc-spark-hdr">
                  <span>28-day · <b>${sparkLo}</b>→<b>${sparkHi}</b></span>
                  <span style="color:var(--mute-2)">${b.industry.slice(0,18)}</span>
                </div>
                <div class="mc-spark">${sparkSvgFromCloses(b.closes, 240, 58, false, true)}</div>
              </div>
              <div class="mc-radar-wrap">
                <div class="mc-radar-lbl">5-Pillar</div>
                ${radarSvg(b.pillars)}
              </div>
            </div>
            ${priceLadder(b)}
            <div class="rrbar">
              <span class="rrlbl">Risk : Reward</span>
              <span class="rrtrack">
                <span class="risk" style="width:${riskPct}%"></span>
                <span class="reward" style="width:${rewardPct}%"></span>
              </span>
              <b>${rr ? rr.toFixed(1) : '—'}:1</b>
            </div>
            <div class="mc-narr">${narr}</div>
            <div class="mc-actions">
              <button class="mc-action primary">▶ BUY</button>
              <button class="mc-action">⭐ Watch</button>
              <button class="mc-action">📋 Plan</button>
            </div>
          </div>`;
      }).join('');
      document.getElementById('megacards').innerHTML = html;
    }

    // ─── SIDEBAR ACCORDION ────────────────────────────────────────────
    function sidebarRow(rk, sym, val, valCls, m, closes) {
      const sparkHtml = closes && closes.length ? `<div class="mini-spark">${sparkSvgFromCloses(closes.slice(-12), 36, 14, false, false)}</div>` : '<div class="mini-spark"></div>';
      return `<div class="sb-row">
        <span class="rk">${rk}</span>
        <span class="sym">${sym}</span>
        <span class="meta">${m}</span>
        ${sparkHtml}
        <span class="val ${valCls||''}">${val}</span>
      </div>`;
    }

    function renderSidebar() {
      const fresh = DATA.panels.fresh.map((r,i) => sidebarRow(`#${i+1}`, r.sym, r.score, r.score>=75?'gn':r.score>=60?'am':'',
        `${r.setup||r.family} · ${r.sector}<br/>RVOL <b>${(r.rvol||0).toFixed(2)}</b> · RS <b>${r.rs ?? '—'}</b>`, r.closes)).join('') || '<div class="sb-empty">no FRESH entries</div>';
      const earn = DATA.panels.earnings.map((r,i) => sidebarRow(`#${i+1}`, r.sym, r.earn_label || `+${r.earn_days}d`, r.earn_days<=1?'rd':r.earn_days<=3?'am':'',
        `${r.sector} · ${r.setup||r.family}<br/>${r.industry.slice(0,28)}`, r.closes)).join('') || '<div class="sb-empty">no earnings inside 7d</div>';
      const surges = DATA.panels.surges.map((r,i) => sidebarRow(`#${i+1}`, r.sym, `${(r.rvol||0).toFixed(2)}×`, (r.rvol||0)>=3?'gn':'am',
        `${r.sector} · ${r.setup||r.family}<br/>Score <b>${r.score}</b> · entry <b>${r.entry_quality}</b>`, r.closes)).join('') || '<div class="sb-empty">no surges ≥1.5×</div>';
      const ai = DATA.panels.ai.map((r,i) => `<div class="sb-row">
        <span class="rk">#${i+1}</span>
        <span class="sym">${r.sym}</span>
        <span class="meta">p(up) <b>${(r.p_up*100).toFixed(0)}%</b><br/>${r.verdict}</span>
        <span class="val gn">${r.edge>=0?'+':''}${r.edge.toFixed(2)}%</span>
      </div>`).join('') || '<div class="sb-empty">ML cache empty · run ml.run_ml_edge</div>';
      const mom = DATA.panels.momentum.map((r,i) => sidebarRow(`#${i+1}`, r.sym, `${(r.momentum||0).toFixed(0)}`, (r.momentum||0)>=80?'gn':(r.momentum||0)>=60?'am':'',
        `${r.sector}<br/>Score <b>${r.score}</b> · RS <b>${r.rs ?? '—'}</b>`, r.closes)).join('') || '<div class="sb-empty">no momentum data</div>';

      const html = `
        <div class="sb-card">
          <div class="sb-hd open" onclick="toggleSb(this)"><div class="sb-hd-l"><span class="ico">⚡</span>Fresh Entries</div><div class="sb-hd-r"><span class="cnt">${DATA.panels.fresh.length}</span><span class="caret">▼</span></div></div>
          <div class="sb-body show">${fresh}</div>
        </div>
        <div class="sb-card">
          <div class="sb-hd" onclick="toggleSb(this)"><div class="sb-hd-l"><span class="ico">📅</span>Earnings This Week</div><div class="sb-hd-r"><span class="cnt">${DATA.panels.earnings.length}</span><span class="caret">▼</span></div></div>
          <div class="sb-body">${earn}</div>
        </div>
        <div class="sb-card">
          <div class="sb-hd" onclick="toggleSb(this)"><div class="sb-hd-l"><span class="ico">🔥</span>Volume Surges</div><div class="sb-hd-r"><span class="cnt">${DATA.panels.surges.length}</span><span class="caret">▼</span></div></div>
          <div class="sb-body">${surges}</div>
        </div>
        <div class="sb-card">
          <div class="sb-hd" onclick="toggleSb(this)"><div class="sb-hd-l"><span class="ico">✦</span>AI Edge Top 5</div><div class="sb-hd-r"><span class="cnt">${DATA.panels.ai.length}</span><span class="caret">▼</span></div></div>
          <div class="sb-body">${ai}</div>
        </div>
        <div class="sb-card">
          <div class="sb-hd" onclick="toggleSb(this)"><div class="sb-hd-l"><span class="ico">🚀</span>Top Momentum</div><div class="sb-hd-r"><span class="cnt">${DATA.panels.momentum.length}</span><span class="caret">▼</span></div></div>
          <div class="sb-body">${mom}</div>
        </div>
      `;
      document.getElementById('sidebar').innerHTML = html;
    }

    function toggleSb(el) {
      el.classList.toggle('open');
      el.nextElementSibling.classList.toggle('show');
    }

    // ─── TABLE ────────────────────────────────────────────────────────
    function tblSparkSvg(closes) {
      return sparkSvgFromCloses(closes ? closes.slice(-12) : null, 62, 18, false, false);
    }
    function fmt(v, dp=2) {
      if (v == null || v === undefined) return '—';
      const n = +v;
      if (isNaN(n)) return v;
      return n.toFixed(dp);
    }
    function renderTable() {
      const html = DATA.table.map(r => {
        const scoreCls = r.score >= 75 ? 'hi' : r.score >= 60 ? 'mid' : 'lo';
        return `<tr>
          <td><b style="color:var(--ink)">${r.sym}</b></td>
          <td class="num score-cell ${scoreCls}">${r.score}</td>
          <td><span class="vchip ${r.verdict||'NEUTRAL'}">${r.verdict||'—'}</span></td>
          <td>${r.tier||'—'}</td>
          <td>${(r.setup||r.family||'').slice(0,18)}</td>
          <td style="color:var(--mute)">${(r.sector||'').slice(0,16)}</td>
          <td class="num">${r.rs ?? '—'}</td>
          <td class="num">${fmt(r.rvol)}</td>
          <td class="num">${r.rsi ? r.rsi.toFixed(0) : '—'}</td>
          <td class="num" style="color:var(--gn)">${r.rr ? r.rr.toFixed(1)+':1' : '—'}</td>
          <td class="num">${r.entry_mid ? '$'+r.entry_mid.toFixed(2) : '—'}</td>
          <td class="num" style="color:var(--rd)">${r.stop ? '$'+r.stop.toFixed(2) : '—'}</td>
          <td class="num" style="color:var(--gn)">${r.t1 ? '$'+r.t1.toFixed(2) : '—'}</td>
          <td><span class="chip eq">${r.entry_quality||'—'}</span></td>
          <td class="num">${r.cat_tier ? 'T'+r.cat_tier : '—'}</td>
          <td>${tblSparkSvg(r.closes)}</td>
          <td class="num">${r.hold ? r.hold+'d' : '—'}</td>
        </tr>`;
      }).join('');
      document.getElementById('tb-body').innerHTML = html;
    }

    // Filter chips wiring
    document.querySelectorAll('.fchip').forEach(c => {
      c.addEventListener('click', () => {
        const siblings = c.parentNode.querySelectorAll('.fchip');
        siblings.forEach(s => s.classList.remove('on'));
        c.classList.add('on');
      });
    });

    // INIT
    renderPulse();
    renderMegaCards();
    renderSidebar();
    renderTable();
  </script>
</body>
</html>
'''

import re
payload_json = json.dumps(payload)
out = HTML.replace('__PAYLOAD__', payload_json)
OUT.write_text(out)
print(f'wrote {OUT.relative_to(BASE)} ({OUT.stat().st_size:,} bytes)')

"""Build scanner_v2_e.html — the FULL version with functional filters,
price/score/RR sliders, sortable table, live search, volume bars on
sparklines, in-zone badges, score histogram, sector heatmap.

Reads cache/last_bundle.json + cache/ml_edge_predictions.json and writes
infra/prototype/mockups/scanner_v2_e.html (self-contained).
"""
from __future__ import annotations
import json
from pathlib import Path
from collections import Counter

BASE = Path(__file__).resolve().parents[3]
BUNDLE = BASE / 'cache' / 'last_bundle.json'
ML     = BASE / 'cache' / 'ml_edge_predictions.json'
OUT    = Path(__file__).resolve().parent / 'scanner_v2_e.html'

print(f'reading {BUNDLE.relative_to(BASE)} ...')
b = json.loads(BUNDLE.read_text())
ml = json.loads(ML.read_text()) if ML.exists() else {}

ascored = b.get('all_scored') or []
regime  = b.get('regime') or {}

# ─── Verdict counts ────────────────────────────────────────────────
counts = Counter((t.get('verdict') or '').upper() for t in ascored)
TOTAL  = len(ascored)
BUY_N  = counts.get('BUY', 0)
WATCH_N= counts.get('WATCH', 0)
NEUT_N = counts.get('WAIT', 0) + counts.get('NEUTRAL', 0)
KILL_N = counts.get('AVOID', 0) + counts.get('SHORT', 0)

# ─── Sector counts ─────────────────────────────────────────────────
sector_counts = Counter()
sector_buys   = Counter()
sector_kills  = Counter()
for t in ascored:
    s = t.get('sector') or 'Other'
    sector_counts[s] += 1
    v = (t.get('verdict') or '').upper()
    if v == 'BUY':   sector_buys[s]  += 1
    if v == 'AVOID': sector_kills[s] += 1

SECTORS_LIST = [s for s, _ in sector_counts.most_common()]

# ─── Score histogram bins ──────────────────────────────────────────
def score_bin(s):
    s = s or 0
    if s >= 85: return '85+'
    if s >= 75: return '75-84'
    if s >= 65: return '65-74'
    if s >= 55: return '55-64'
    if s >= 45: return '45-54'
    if s >= 35: return '35-44'
    if s >= 25: return '25-34'
    return '<25'
hist_bins = ['<25','25-34','35-44','45-54','55-64','65-74','75-84','85+']
hist_counts = Counter(score_bin(t.get('score', 0)) for t in ascored)
hist_data = [(b, hist_counts.get(b, 0)) for b in hist_bins]

# ─── Compact row ───────────────────────────────────────────────────
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
    e_low = tp.get('entry_low'); e_high = tp.get('entry_high')
    e_mid = (e_low + e_high)/2 if e_low and e_high else (t.get('price') or 0)
    oh = t.get('ohlcv') or []
    closes = [r.get('close') for r in oh[-28:] if isinstance(r, dict) and r.get('close') is not None] if isinstance(oh, list) else []
    volumes = [r.get('volume') for r in oh[-28:] if isinstance(r, dict) and r.get('volume') is not None] if isinstance(oh, list) else []
    # "in zone" status
    price = t.get('price') or 0
    in_zone = None
    if e_low and e_high and price:
        if e_low <= price <= e_high:
            in_zone = 'IN ZONE'
        elif price < e_low and (e_low - price)/price < 0.05:
            in_zone = 'NEAR'
        elif price > e_high and (price - e_high)/price < 0.05:
            in_zone = 'PAST'
    dollar_vol = (price or 0) * (t.get('avg_volume') or 0)
    # T·F·S·N mini-bars: technicals / fundamentals / smart-money / news (0..1 each)
    sm_pct = (sb.get('smart_money', 0) or 0) / 15.0
    qg_pct = (sb.get('quality_gate', 0) or 0) / 10.0
    tech_pct = (sb.get('tech', 0) or 0) / 35.0
    ns_raw = t.get('news_sentiment_score') or 0
    if isinstance(ns_raw, dict):
        ns_raw = ns_raw.get('score') or ns_raw.get('value') or ns_raw.get('compound') or 0
    try:
        ns_raw = float(ns_raw)
    except (TypeError, ValueError):
        ns_raw = 0
    # news_score is roughly -1 to 1, normalize to 0..1
    n_pct = max(0, min(1, (ns_raw + 1) / 2)) if ns_raw else 0
    tfsn = [round(tech_pct, 2), round(qg_pct, 2), round(sm_pct, 2), round(n_pct, 2)]
    # ticker source pretty label
    src_raw = (t.get('ticker_source') or '').lower()
    src_map = {
        'sp500':'SP500', 'russell1000':'R1000', 'russell2000':'R2000',
        'sp_midcap_400':'MID400', 'sp_smallcap_600':'SML600',
        'recent_ipo':'IPO', 'crypto_adjacent':'CRYPTO',
        'screener_momentum':'MOM', 'etf_holding':'ETF',
    }
    src_label = src_map.get(src_raw, src_raw.upper()[:6] if src_raw else '—')
    return {
        'sym':  t.get('ticker'),
        'name': (t.get('name') or '').replace('"', "'")[:40],
        'score': int(round(t.get('score') or 0)),
        'verdict': t.get('verdict'),
        'tier': ctp.get('conviction_tier') or '—',
        'setup': tp.get('setup_type') or t.get('setup_family') or '—',
        'family': t.get('setup_family') or '—',
        'sector': t.get('sector') or 'Other',
        'industry': (t.get('industry') or '').replace('"',"'")[:34],
        'rs': t.get('rs_rank'),
        'rsi': t.get('rsi'),
        'rvol': t.get('rvol'),
        'price': t.get('price'),
        'pct_change_1d': t.get('pct_change_1d') or t.get('day_chg_pct') or 0,
        'avg_vol': t.get('avg_volume'),
        'dvol_m': round(dollar_vol / 1_000_000, 1) if dollar_vol else 0,
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
        'tfsn': tfsn,
        'closes': closes,
        'volumes': volumes,
        'star': t.get('star_rating') or 0,
        'g_g': t.get('grade_growth'),
        'g_v': t.get('grade_value'),
        'g_m': t.get('grade_momentum'),
        'g_vgm': t.get('grade_vgm'),
        'in_zone': in_zone,
        'momentum': t.get('raw_momentum_score'),
        'allocation_pct': tp.get('allocation_pct'),
        'src': src_label,
        'rank_delta': None,  # filled below from prior bundle if available
    }

# Build full universe (sorted by score desc); cap to 150 for prototype perf
universe = sorted(
    [compact_row(t) for t in ascored],
    key=lambda r: -(r['score'] or 0),
)[:150]

# ─── Rank delta from picks_history: yesterday's run rank vs today ────
PH = BASE / 'cache' / 'picks_history.json'
prev_rank = {}
if PH.exists():
    try:
        ph = json.loads(PH.read_text())
        runs = ph.get('runs') or []
        # find most recent prior run (anything before today)
        if len(runs) >= 2:
            prior = runs[-2]  # second-most-recent
            for i, p in enumerate(prior.get('picks', [])):
                prev_rank[p.get('ticker')] = i + 1
    except Exception as ex:
        print(f'  prev rank load failed: {ex}')

for i, r in enumerate(universe):
    today_rk = i + 1
    prev = prev_rank.get(r['sym'])
    if prev is not None:
        r['rank_delta'] = prev - today_rk   # positive = moved up
print(f'  rank deltas computed: {sum(1 for r in universe if r["rank_delta"] is not None)} of {len(universe)}')

buys = [r for r in universe if r['verdict'] == 'BUY']

# Sidebar panels
def panel_fresh():
    rows = [r for r in universe if r['entry_quality'] == 'FRESH']
    return sorted(rows, key=lambda r: -r['score'])[:5]
def panel_earn():
    rows = [r for r in universe if r['earn_days'] is not None and 0 <= r['earn_days'] <= 7]
    return sorted(rows, key=lambda r: r['earn_days'])[:5]
def panel_surge():
    rows = [r for r in universe if (r['rvol'] or 0) >= 1.5]
    return sorted(rows, key=lambda r: -(r['rvol'] or 0))[:5]
def panel_mom():
    rows = [r for r in universe if (r['momentum'] or 0) > 0]
    return sorted(rows, key=lambda r: -(r['momentum'] or 0))[:5]
def panel_ai():
    pool = (ml.get('predictions') or {}).get('swing') or {}
    items = []
    for sym, p in pool.items():
        d = p.get('direction') or {}
        items.append({'sym': sym, 'p_up': d.get('p_up') or 0,
                      'edge': (p.get('verdict') or {}).get('edge') or 0,
                      'verdict': (p.get('verdict') or {}).get('text', '—')})
    return sorted(items, key=lambda x: -x['p_up'])[:5]

panels = {'fresh': panel_fresh(), 'earnings': panel_earn(),
          'surges': panel_surge(), 'momentum': panel_mom(), 'ai': panel_ai()}

# Price range bounds
prices = [r['price'] for r in universe if r['price']]
PRICE_MIN = round(min(prices), 2) if prices else 0
PRICE_MAX = round(max(prices), 2) if prices else 1000

vix = (regime.get('vix') or {})
pulse = {
    'regime4': regime.get('regime4') or 'neutral',
    'regime_label': (regime.get('regime4') or 'neutral').replace('_', ' ').upper(),
    'vix': vix.get('vix_current') or regime.get('vix_current') or 0,
    'vix_state': vix.get('vol_state', '—'),
    'breadth': regime.get('breadth_pct_50d') or 0,
    'spy_price': regime.get('spy_price'),
    'spy_chg': regime.get('spy_daily_chg'),
}

payload = {
    'last_scan': b.get('run_timestamp') or '—',
    'pulse': pulse,
    'counts': {'total': TOTAL, 'buy': BUY_N, 'watch': WATCH_N, 'neut': NEUT_N, 'kill': KILL_N},
    'sector_data': [{'name': s, 'count': c, 'buys': sector_buys.get(s,0), 'kills': sector_kills.get(s,0)} for s, c in sector_counts.most_common(11)],
    'hist': hist_data,
    'price_min': PRICE_MIN,
    'price_max': PRICE_MAX,
    'universe': universe,
    'buys': buys,
    'panels': panels,
}
print(f'  universe rows: {len(universe)} · BUYs: {len(buys)} · sectors: {len(sector_counts)}')
print(f'  price range: ${PRICE_MIN} - ${PRICE_MAX}')
print(f'  score histogram: {dict(hist_counts)}')

HTML = r'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Signal Scanner · Option E · Full Workspace · Best</title>
  <style>
    :root {
      --bg:#08090c; --bg-1:#0d1014; --bg-2:#11151b; --card:#12161d; --card-hi:#171c25;
      --border:#1f2937; --border-hi:#334155; --border-soft:rgba(255,255,255,0.06);
      --ink:#f3f4f6; --ink-2:#d1d5db; --mute:#9ca3af; --mute-2:#6b7280; --mute-3:#4b5563;
      --copper:#c97b3a; --copper-hi:#e09850; --copper-d:#8b5a2e;
      --gn:#10b981; --gn-hi:#34d399; --gn-bg:rgba(16,185,129,0.10); --gn-glow:rgba(16,185,129,0.30);
      --rd:#f87171; --rd-bg:rgba(248,113,113,0.10); --rd-glow:rgba(248,113,113,0.25);
      --am:#f59e0b; --am-hi:#fbbf24; --am-bg:rgba(245,158,11,0.10);
      --bl:#3b82f6; --bl-bg:rgba(59,130,246,0.10);
      --pl:#a78bfa; --pl-bg:rgba(167,139,250,0.10);
      --ti:#22d3ee;
    }
    *{box-sizing:border-box}
    body{margin:0;background:radial-gradient(ellipse 80% 50% at top, #0c1115 0%, var(--bg) 60%);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Inter,sans-serif;padding:14px 22px 64px;min-height:100vh;line-height:1.45;font-feature-settings:'cv02','cv11'}
    .back{color:var(--mute);font-size:0.78rem;text-decoration:none;margin-bottom:12px;display:inline-block}
    .back:hover{color:var(--copper-hi)}
    .wrap{max-width:1880px;margin:0 auto}
    /* Custom scrollbar */
    ::-webkit-scrollbar{width:10px;height:10px}
    ::-webkit-scrollbar-track{background:var(--bg-1)}
    ::-webkit-scrollbar-thumb{background:var(--border);border-radius:5px;border:2px solid var(--bg-1)}
    ::-webkit-scrollbar-thumb:hover{background:var(--border-hi)}
    ::-webkit-scrollbar-corner{background:var(--bg-1)}

    /* ════ HEADER ════ */
    .hd{display:flex;align-items:center;justify-content:space-between;margin:4px 0 14px;padding:13px 18px;background:linear-gradient(180deg,var(--card) 0%,var(--bg-1) 100%);border:1px solid var(--border);border-radius:14px;position:relative;overflow:hidden}
    .hd::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,var(--gn),var(--copper),var(--am))}
    .hd-l{display:flex;align-items:center;gap:14px}
    .hd-l .dot{width:9px;height:9px;border-radius:50%;background:var(--gn);animation:pulse 2.4s infinite}
    @keyframes pulse{0%{box-shadow:0 0 0 0 var(--gn-glow)}70%{box-shadow:0 0 0 8px transparent}100%{box-shadow:0 0 0 0 transparent}}
    .hd-l .brand{color:var(--copper);font-weight:700;font-size:0.72rem;letter-spacing:0.14em;text-transform:uppercase}
    .hd-l h1{font-family:'Playfair Display',Georgia,serif;font-style:italic;font-weight:400;margin:0;font-size:1.6rem;background:linear-gradient(180deg,#fff 0%,#cbd5e1 100%);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
    .hd-stats{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
    .hs-cell{display:flex;align-items:center;gap:8px;padding:0 11px;border-right:1px solid var(--border-soft);height:38px}
    .hs-cell:last-child{border-right:none}
    .hs-lbl{font-size:0.56rem;color:var(--mute-2);text-transform:uppercase;letter-spacing:0.08em;font-weight:700;line-height:1.1}
    .hs-val{font-size:1.05rem;font-weight:700;font-family:ui-monospace,monospace;color:var(--ink);line-height:1.1}
    .hs-val.gn{color:var(--gn)} .hs-val.am{color:var(--am)} .hs-val.rd{color:var(--rd)}
    .hs-pill{display:inline-flex;align-items:center;gap:5px;padding:4px 9px;border-radius:999px;font-size:0.66rem;font-weight:700;background:var(--am-bg);color:var(--am);border:1px solid var(--am);text-transform:uppercase}
    .hs-pill.gn{background:var(--gn-bg);color:var(--gn);border-color:var(--gn)}
    .hs-pill.rd{background:var(--rd-bg);color:var(--rd);border-color:var(--rd)}
    .hs-pill .pd{width:5px;height:5px;border-radius:50%;background:currentColor;animation:pulse 2s infinite}
    .hs-bar{width:60px;height:6px;background:var(--bg-2);border-radius:3px;overflow:hidden;position:relative}
    .hs-fill{height:100%;background:linear-gradient(90deg,var(--rd),var(--am),var(--gn));opacity:0.5}
    .hs-marker{position:absolute;top:-2px;width:2px;height:10px;background:var(--ink)}
    .hs-gauge{width:50px;height:28px}

    /* ════ VIEWPORTS row (histogram + sector mini-heatmap) ════ */
    .viewports{display:grid;grid-template-columns:1.2fr 1.8fr;gap:14px;margin-bottom:14px}
    .vp-card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:12px 16px;position:relative;overflow:hidden}
    .vp-card::before{content:'';position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,var(--copper-d) 50%,transparent)}
    .vp-hd{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:10px}
    .vp-ttl{font-size:0.78rem;font-weight:700;color:var(--ink);letter-spacing:0.02em}
    .vp-sub{font-size:0.66rem;color:var(--mute-2);font-family:ui-monospace,monospace}
    /* Histogram bars */
    .hist{display:flex;align-items:flex-end;gap:6px;height:90px;padding:0 4px}
    .hist-bar{flex:1;display:flex;flex-direction:column;align-items:center;gap:4px}
    .hist-fill{width:100%;background:linear-gradient(180deg,var(--copper) 0%,var(--copper-d) 100%);border-radius:4px 4px 0 0;min-height:2px;transition:height .3s;position:relative;cursor:pointer}
    .hist-fill:hover{background:linear-gradient(180deg,var(--copper-hi) 0%,var(--copper) 100%)}
    .hist-fill .cnt{position:absolute;top:-15px;left:50%;transform:translateX(-50%);font-family:ui-monospace,monospace;font-size:0.6rem;color:var(--ink-2);font-weight:700;opacity:0;transition:opacity .15s}
    .hist-fill:hover .cnt{opacity:1}
    .hist-lbl{font-size:0.58rem;color:var(--mute-2);font-family:ui-monospace,monospace;letter-spacing:0.02em}
    /* Sector mini-heatmap */
    .sec-mini{display:grid;grid-template-columns:repeat(11,1fr);gap:4px;height:90px}
    .sec-tile{background:var(--bg-1);border:1px solid var(--border);border-radius:5px;padding:5px 4px;display:flex;flex-direction:column;justify-content:space-between;cursor:pointer;transition:transform .12s,border-color .12s;position:relative;overflow:hidden}
    .sec-tile:hover{transform:translateY(-1px);border-color:var(--copper);z-index:2}
    .sec-tile .sec-name{font-size:0.55rem;color:var(--ink-2);font-weight:700;font-family:ui-monospace,monospace;letter-spacing:0.02em;text-transform:uppercase;line-height:1.1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .sec-tile .sec-cnts{display:flex;justify-content:space-between;align-items:baseline;font-family:ui-monospace,monospace;font-size:0.62rem;font-weight:700}
    .sec-tile .sec-buy{color:var(--gn)}
    .sec-tile .sec-kill{color:var(--rd)}
    .sec-tile .sec-tot{color:var(--mute);font-size:0.55rem;font-weight:600}
    .sec-tile .sec-bar{height:4px;background:var(--bg-2);border-radius:2px;overflow:hidden;display:flex}
    .sec-tile .sec-bar .b{background:var(--gn);height:100%}
    .sec-tile .sec-bar .k{background:var(--rd);height:100%}

    /* ════ LAYOUT: main + sidebar ════ */
    .layout{display:grid;grid-template-columns:1fr 340px;gap:14px;margin-bottom:14px}
    @media (max-width:1200px){.layout{grid-template-columns:1fr}}

    /* ════ SECTION HD ════ */
    .sec-hd{display:flex;align-items:flex-end;justify-content:space-between;margin:4px 0 14px}
    .sec-hd .ttl{font-family:'Playfair Display',Georgia,serif;font-style:italic;font-size:1.4rem;color:var(--ink);font-weight:400;display:flex;align-items:baseline;gap:12px}
    .sec-hd .ttl .cnt{background:var(--gn-bg);color:var(--gn);border:1px solid var(--gn);padding:3px 10px;border-radius:999px;font-size:0.72rem;font-weight:700;font-style:normal;font-family:ui-monospace,monospace;letter-spacing:0.05em}
    .sec-hd .meta{color:var(--mute);font-size:0.72rem}

    /* ════ MEGA CARDS ════ */
    .megacards{display:grid;grid-template-columns:repeat(auto-fit,minmax(380px,1fr));gap:14px;margin-bottom:18px}
    .mc{background:linear-gradient(160deg,var(--card) 0%,var(--bg-1) 100%);border:1px solid var(--border);border-radius:14px;padding:16px 16px 14px;position:relative;overflow:hidden;cursor:pointer;transition:all .2s cubic-bezier(0.4,0,0.2,1);display:flex;flex-direction:column;gap:11px}
    .mc::before{content:'';position:absolute;top:0;left:0;right:0;height:4px;background:linear-gradient(90deg,var(--gn) 0%,var(--copper) 60%,var(--am) 100%)}
    .mc::after{content:'';position:absolute;top:-30px;right:-30px;width:140px;height:140px;background:radial-gradient(circle,var(--gn-glow) 0%,transparent 70%);opacity:0;transition:opacity .25s}
    .mc:hover{transform:translateY(-2px);border-color:var(--gn);box-shadow:0 12px 32px rgba(16,185,129,0.12),0 4px 12px rgba(0,0,0,0.5)}
    .mc:hover::after{opacity:1}

    .mc-row1{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;position:relative;z-index:2}
    .mc-left{display:flex;flex-direction:column;gap:5px}
    .mc-sym{font-size:1.85rem;font-weight:800;font-family:ui-monospace,monospace;color:var(--ink);line-height:1}
    .mc-name{font-size:0.62rem;color:var(--mute-2);line-height:1.2;max-width:200px;font-family:ui-monospace,monospace}
    .mc-livepx{display:flex;align-items:baseline;gap:7px;font-family:ui-monospace,monospace;font-size:0.78rem;color:var(--mute);margin-top:4px}
    .mc-livepx b{color:var(--ink-2);font-weight:700;font-size:0.95rem}
    .mc-livepx .pct{font-weight:700;padding:1px 6px;border-radius:5px}
    .mc-livepx .pct.up{color:var(--gn);background:rgba(16,185,129,0.12)}
    .mc-livepx .pct.dn{color:var(--rd);background:rgba(248,113,113,0.12)}

    .mc-right{text-align:right;display:flex;flex-direction:column;align-items:flex-end;gap:3px}
    .mc-score{font-size:2.3rem;font-weight:800;font-family:ui-monospace,monospace;color:var(--gn);line-height:1;text-shadow:0 0 24px var(--gn-glow)}
    .mc-score-lbl{font-size:0.6rem;color:var(--mute-2);text-transform:uppercase;letter-spacing:0.1em;font-weight:700}
    .mc-tier-row{display:flex;gap:5px;margin-top:4px;flex-wrap:wrap;justify-content:flex-end}
    .mc-zone-badge{display:inline-block;padding:3px 9px;border-radius:6px;font-size:0.62rem;font-weight:700;letter-spacing:0.04em;font-family:ui-monospace,monospace;text-transform:uppercase;margin-top:3px}
    .mc-zone-badge.in-zone{background:var(--gn);color:#000}
    .mc-zone-badge.near{background:var(--am);color:#000}
    .mc-zone-badge.past{background:var(--rd-bg);color:var(--rd);border:1px solid var(--rd)}

    .chip{display:inline-block;padding:3px 8px;border-radius:6px;font-size:0.64rem;font-weight:700;letter-spacing:0.04em;background:var(--bg-2);color:var(--mute);border:1px solid var(--border);font-family:ui-monospace,monospace;text-transform:uppercase}
    .chip.tier1{background:var(--gn-bg);color:var(--gn);border-color:var(--gn)}
    .chip.tier2{background:var(--bl-bg);color:var(--bl);border-color:var(--bl)}
    .chip.tier3{background:var(--am-bg);color:var(--am);border-color:var(--am)}
    .chip.setup{background:var(--copper);color:#fff;border-color:var(--copper)}
    .chip.eq{background:var(--pl-bg);color:var(--pl);border-color:var(--pl)}

    .mc-mid{display:grid;grid-template-columns:1.6fr 1fr;gap:11px;align-items:stretch}
    .mc-spark-wrap{position:relative;background:var(--bg-1);border:1px solid var(--border-soft);border-radius:9px;padding:7px 9px;display:flex;flex-direction:column;gap:2px}
    .mc-spark-hdr{display:flex;justify-content:space-between;font-family:ui-monospace,monospace;font-size:0.6rem;color:var(--mute-2)}
    .mc-spark-hdr b{color:var(--ink-2);font-weight:700}
    .mc-spark{height:54px;width:100%;display:block}
    .mc-vol-bars{height:18px;width:100%;display:block;margin-top:2px}
    .mc-radar-wrap{background:var(--bg-1);border:1px solid var(--border-soft);border-radius:9px;padding:7px;display:flex;align-items:center;justify-content:center;position:relative}
    .mc-radar{width:100%;height:82px}
    .mc-radar-lbl{position:absolute;top:5px;left:8px;font-size:0.58rem;color:var(--mute-2);text-transform:uppercase;letter-spacing:0.08em;font-weight:700;font-family:ui-monospace,monospace}

    .mc-ladder{background:var(--bg-1);border:1px solid var(--border-soft);border-radius:9px;padding:12px 10px 6px;font-family:ui-monospace,monospace}
    .mc-ladder-hdr{display:flex;justify-content:space-between;font-size:0.6rem;color:var(--mute-2);text-transform:uppercase;letter-spacing:0.08em;font-weight:700;margin-bottom:7px}
    .mc-ladder-track{position:relative;height:26px;margin:0 6px}
    .mc-ladder-line{position:absolute;top:12px;left:0;right:0;height:3px;background:linear-gradient(90deg,var(--rd) 0%,#dc2626 8%,var(--am) 35%,#34d399 60%,var(--gn) 100%);border-radius:2px}
    .mc-ladder-tick{position:absolute;top:8px;width:2px;height:11px;background:rgba(255,255,255,0.55);border-radius:1px}
    .mc-ladder-dot{position:absolute;top:4px;width:16px;height:16px;border-radius:50%;background:var(--ink);border:3px solid var(--bg-1);box-shadow:0 0 0 1.5px var(--ink);transform:translateX(-8px)}
    .mc-ladder-lbl{position:absolute;font-size:0.58rem;font-weight:700;letter-spacing:0.04em;transform:translateX(-50%);white-space:nowrap}
    .mc-ladder-lbl.bot{top:24px}

    .rrbar{display:flex;align-items:center;gap:9px;font-size:0.72rem;color:var(--mute);font-family:ui-monospace,monospace;padding:0 2px}
    .rrlbl{color:var(--mute-2);font-weight:700;font-size:0.6rem;letter-spacing:0.1em;text-transform:uppercase;flex-shrink:0}
    .rrtrack{flex-grow:1;height:8px;background:var(--bg-2);border-radius:5px;position:relative;overflow:hidden;display:flex;border:1px solid var(--border-soft)}
    .rrtrack .risk{background:linear-gradient(90deg,#dc2626,var(--rd));height:100%}
    .rrtrack .reward{background:linear-gradient(90deg,var(--gn),var(--gn-hi));height:100%}
    .rrbar b{color:var(--gn);font-weight:800;flex-shrink:0;font-size:0.85rem}

    .mc-narr{font-size:0.72rem;color:var(--mute);line-height:1.5;font-style:italic;padding:9px 11px;background:var(--bg-1);border-radius:8px;border-left:3px solid var(--copper)}
    .mc-actions{display:flex;gap:6px}
    .mc-action{flex:1;background:var(--bg-2);border:1px solid var(--border);color:var(--ink-2);font-size:0.72rem;padding:8px;border-radius:8px;font-weight:700;letter-spacing:0.04em;cursor:pointer;font-family:inherit;transition:all .15s;text-transform:uppercase}
    .mc-action:hover{background:var(--copper);border-color:var(--copper);color:#fff;transform:translateY(-1px)}
    .mc-action.primary{background:var(--gn);color:#000;border-color:var(--gn)}
    .mc-action.primary:hover{background:var(--gn-hi);border-color:var(--gn-hi);box-shadow:0 4px 12px var(--gn-glow)}

    /* ════ SIDEBAR ════ */
    .sidebar{display:flex;flex-direction:column;gap:10px}
    .sb-card{background:var(--card);border:1px solid var(--border);border-radius:12px;overflow:hidden}
    .sb-hd{padding:11px 14px;display:flex;align-items:center;justify-content:space-between;cursor:pointer;transition:background .15s}
    .sb-hd:hover{background:var(--bg-2)}
    .sb-hd-l{display:flex;align-items:center;gap:8px;font-size:0.85rem;font-weight:700}
    .sb-hd .ico{font-size:1.05rem}
    .sb-hd-r{display:flex;align-items:center;gap:9px;font-size:0.72rem;color:var(--mute);font-family:ui-monospace,monospace}
    .sb-hd-r .cnt{background:var(--bg-2);color:var(--ink-2);padding:2px 8px;border-radius:5px;font-weight:700}
    .sb-hd .caret{color:var(--mute-2);transition:transform .15s;font-size:0.7rem}
    .sb-hd.open .caret{transform:rotate(180deg)}
    .sb-body{padding:8px 12px 12px;display:none;border-top:1px solid var(--border-soft)}
    .sb-body.show{display:block}
    .sb-row{display:flex;align-items:center;gap:8px;padding:7px 4px;border-bottom:1px dashed var(--border-soft);cursor:pointer;border-radius:5px}
    .sb-row:last-child{border-bottom:none}
    .sb-row:hover{background:var(--bg-2)}
    .sb-row .rk{font-family:ui-monospace,monospace;font-size:0.62rem;color:var(--mute-2);font-weight:700;flex-shrink:0;width:18px}
    .sb-row .sym{font-family:ui-monospace,monospace;font-weight:700;font-size:0.85rem;flex-shrink:0;width:58px}
    .sb-row .meta{font-size:0.66rem;color:var(--mute);flex-grow:1;line-height:1.35}
    .sb-row .meta b{color:var(--ink-2)}
    .sb-row .val{font-family:ui-monospace,monospace;font-weight:700;font-size:0.8rem;flex-shrink:0;text-align:right}
    .sb-row .val.gn{color:var(--gn)} .sb-row .val.am{color:var(--am)} .sb-row .val.rd{color:var(--rd)}
    .sb-row .mini-spark{width:38px;height:14px;flex-shrink:0}
    .sb-empty{padding:18px 6px;color:var(--mute-2);font-style:italic;font-size:0.74rem;text-align:center}

    /* ════ FILTER BAR ════ */
    .filterbar-wrap{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:13px 16px;margin-bottom:14px;position:relative}
    .filterbar-wrap::before{content:'';position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,var(--copper-d) 50%,transparent)}
    .fb-row{display:flex;flex-wrap:wrap;gap:7px;margin-bottom:10px;align-items:center}
    .fb-row:last-child{margin-bottom:0}
    .fb-lbl{font-size:0.6rem;color:var(--mute-2);text-transform:uppercase;letter-spacing:0.1em;font-weight:700;margin-right:8px;flex-shrink:0;min-width:62px}
    .fchip{background:var(--bg-1);border:1px solid var(--border);color:var(--mute);font-size:0.72rem;padding:5px 10px;border-radius:7px;font-weight:600;cursor:pointer;font-family:inherit;display:flex;align-items:center;gap:5px;transition:all .15s}
    .fchip:hover{color:var(--ink);border-color:var(--border-hi)}
    .fchip.on{background:var(--copper);color:#fff;border-color:var(--copper)}
    .fchip .cnt{background:rgba(0,0,0,0.25);padding:0 5px;border-radius:3px;font-size:0.62rem;font-family:ui-monospace,monospace}
    .fchip:not(.on) .cnt{background:var(--bg-2);color:var(--mute-2)}
    .fb-search{margin-left:auto;display:flex;align-items:center;gap:6px}
    .fb-search input{background:var(--bg-1);border:1px solid var(--border);color:var(--ink);font-size:0.74rem;padding:6px 10px;border-radius:7px;width:220px;font-family:inherit;outline:none;transition:border-color .15s}
    .fb-search input:focus{border-color:var(--copper)}
    .fb-search input::placeholder{color:var(--mute-2)}
    .fb-reset{background:transparent;border:1px solid var(--border);color:var(--mute);font-size:0.7rem;padding:5px 10px;border-radius:7px;cursor:pointer;font-family:inherit;font-weight:600}
    .fb-reset:hover{color:var(--ink);border-color:var(--copper)}

    /* Sliders */
    .slider-cell{display:flex;align-items:center;gap:9px;background:var(--bg-1);border:1px solid var(--border);border-radius:8px;padding:6px 12px;min-width:240px}
    .slider-cell .lbl{font-size:0.6rem;color:var(--mute-2);text-transform:uppercase;letter-spacing:0.08em;font-weight:700;flex-shrink:0}
    .slider-track{flex-grow:1;position:relative;height:24px}
    .slider-bg{position:absolute;top:11px;left:0;right:0;height:3px;background:var(--bg-2);border-radius:2px}
    .slider-fill{position:absolute;top:11px;height:3px;background:linear-gradient(90deg,var(--copper-d),var(--copper));border-radius:2px}
    .slider-handle{position:absolute;top:4px;width:14px;height:14px;border-radius:50%;background:var(--ink);border:2px solid var(--copper);box-shadow:0 0 0 1px var(--bg);cursor:grab;transform:translateX(-7px);transition:transform .1s}
    .slider-handle:active{cursor:grabbing;transform:translateX(-7px) scale(1.1)}
    .slider-val{font-family:ui-monospace,monospace;font-size:0.7rem;color:var(--ink-2);font-weight:700;min-width:62px;text-align:right}

    .sector-dd{position:relative}
    .sector-btn{background:var(--bg-1);border:1px solid var(--border);color:var(--ink-2);font-size:0.72rem;padding:6px 10px;border-radius:7px;cursor:pointer;font-family:inherit;font-weight:600;display:flex;align-items:center;gap:6px}
    .sector-btn:hover{border-color:var(--border-hi)}
    .sector-btn.has-filter{background:var(--copper);color:#fff;border-color:var(--copper)}
    .sector-menu{position:absolute;top:100%;left:0;margin-top:5px;background:var(--card);border:1px solid var(--copper);border-radius:8px;padding:6px;z-index:30;box-shadow:0 8px 24px rgba(0,0,0,0.6);display:none;min-width:200px;max-height:300px;overflow-y:auto}
    .sector-menu.show{display:block}
    .sector-menu label{display:flex;align-items:center;gap:7px;padding:6px 8px;font-size:0.72rem;color:var(--ink-2);cursor:pointer;border-radius:5px}
    .sector-menu label:hover{background:var(--bg-2)}
    .sector-menu input{accent-color:var(--copper)}
    .sector-menu .cnt{margin-left:auto;font-family:ui-monospace,monospace;font-size:0.65rem;color:var(--mute)}

    /* ════ TABLE ════ */
    .table-wrap{background:var(--card);border:1px solid var(--border);border-radius:12px;overflow:hidden}
    .tb-hd{padding:12px 16px;border-bottom:1px solid var(--border-soft);display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap}
    .tb-title{font-family:'Playfair Display',Georgia,serif;font-style:italic;font-size:1.05rem;font-weight:400}
    .tb-meta{font-size:0.7rem;color:var(--mute);font-family:ui-monospace,monospace}
    .tb-meta b{color:var(--copper-hi)}
    .tb-actions{display:flex;gap:6px}
    .tb-action{background:var(--bg-1);border:1px solid var(--border);color:var(--ink-2);font-size:0.7rem;padding:5px 10px;border-radius:6px;cursor:pointer;font-family:inherit;font-weight:600;letter-spacing:0.04em}
    .tb-action:hover{border-color:var(--copper);color:#fff}
    .tb-scroll{max-height:560px;overflow:auto}
    table{width:100%;border-collapse:collapse;font-size:0.74rem;font-family:ui-monospace,monospace;min-width:1380px}
    thead{position:sticky;top:0;background:var(--bg-2);z-index:2}
    th{padding:9px 10px;text-align:left;font-weight:700;color:var(--mute-2);text-transform:uppercase;letter-spacing:0.06em;font-size:0.6rem;border-bottom:1px solid var(--border);white-space:nowrap;cursor:pointer;user-select:none;transition:color .12s}
    th:hover{color:var(--copper-hi)}
    th.num{text-align:right}
    th.sorted{color:var(--copper)}
    th.sorted::after{content:'';display:inline-block;margin-left:4px;border:4px solid transparent;border-top-color:var(--copper);vertical-align:middle}
    th.sorted.asc::after{border-top-color:transparent;border-bottom-color:var(--copper);margin-bottom:4px}
    td{padding:8px 10px;border-bottom:1px solid var(--border-soft);color:var(--ink-2);white-space:nowrap}
    td.num{text-align:right}
    tr:hover td{background:var(--bg-2)}
    .vchip{display:inline-block;padding:1px 7px;border-radius:5px;font-size:0.6rem;font-weight:700;letter-spacing:0.04em}
    .vchip.BUY{background:var(--gn-bg);color:var(--gn);border:1px solid var(--gn)}
    .vchip.WATCH{background:var(--am-bg);color:var(--am);border:1px solid var(--am)}
    .vchip.WAIT,.vchip.NEUTRAL{background:var(--bg-2);color:var(--mute);border:1px solid var(--border)}
    .vchip.AVOID,.vchip.SHORT{background:var(--rd-bg);color:var(--rd);border:1px solid var(--rd)}
    .score-cell{font-weight:700}
    .score-cell.hi{color:var(--gn)}
    .score-cell.mid{color:var(--am)}
    .score-cell.lo{color:var(--mute)}
    .tbl-spark{width:64px;height:18px}
    .empty-state{padding:48px;text-align:center;color:var(--mute-2);font-style:italic}

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

    <!-- VIEWPORTS: histogram + sector mini -->
    <div class="viewports">
      <div class="vp-card">
        <div class="vp-hd"><div class="vp-ttl">Score distribution</div><div class="vp-sub">universe of 636 · click bar to filter</div></div>
        <div class="hist" id="hist"></div>
      </div>
      <div class="vp-card">
        <div class="vp-hd"><div class="vp-ttl">Sector verdicts</div><div class="vp-sub">●green=BUY · ●red=AVOID · count = total · click to filter</div></div>
        <div class="sec-mini" id="sec-mini"></div>
      </div>
    </div>

    <!-- LAYOUT -->
    <div class="layout">
      <div>
        <div class="sec-hd">
          <div class="ttl">Today's BUYs <span class="cnt" id="buy-cnt"></span></div>
          <div class="meta">click → trade plan · panels in sidebar →</div>
        </div>
        <div class="megacards" id="megacards"></div>
      </div>
      <div class="sidebar" id="sidebar"></div>
    </div>

    <!-- FILTER BAR -->
    <div class="filterbar-wrap">
      <div class="fb-row">
        <span class="fb-lbl">Verdict</span>
        <div class="fchip on" data-fg="verdict" data-fv="all">All <span class="cnt" id="cnt-all"></span></div>
        <div class="fchip" data-fg="verdict" data-fv="BUY">BUY <span class="cnt" id="cnt-buy"></span></div>
        <div class="fchip" data-fg="verdict" data-fv="WATCH">WATCH <span class="cnt" id="cnt-watch"></span></div>
        <div class="fchip" data-fg="verdict" data-fv="WAIT">WAIT <span class="cnt" id="cnt-neut"></span></div>
        <div class="fchip" data-fg="verdict" data-fv="AVOID">AVOID <span class="cnt" id="cnt-kill"></span></div>
        <div class="fb-search">
          <span style="color:var(--mute-2);font-size:0.78rem">🔍</span>
          <input type="text" id="search" placeholder="search ticker (/ to focus)">
          <button class="fb-reset" id="reset-btn">⟲ Reset</button>
        </div>
      </div>
      <div class="fb-row">
        <span class="fb-lbl">Entry</span>
        <div class="fchip on" data-fg="eq" data-fv="all">All</div>
        <div class="fchip" data-fg="eq" data-fv="FRESH">FRESH</div>
        <div class="fchip" data-fg="eq" data-fv="PULLBACK">PULLBACK</div>
        <div class="fchip" data-fg="eq" data-fv="VALID">VALID</div>
        <div class="fchip" data-fg="eq" data-fv="EXTENDED">EXTENDED</div>
        <div class="fchip" data-fg="eq" data-fv="MISSED">MISSED</div>
        <div class="fchip" data-fg="zone" data-fv="IN ZONE">In Zone Now</div>
        <div class="fchip" data-fg="zone" data-fv="NEAR">Near Zone</div>
      </div>
      <div class="fb-row">
        <span class="fb-lbl">Range</span>
        <div class="slider-cell">
          <span class="lbl">Price $</span>
          <div class="slider-track" data-slider="price">
            <div class="slider-bg"></div>
            <div class="slider-fill"></div>
            <div class="slider-handle" data-h="lo"></div>
            <div class="slider-handle" data-h="hi"></div>
          </div>
          <span class="slider-val" id="val-price">—</span>
        </div>
        <div class="slider-cell">
          <span class="lbl">Score</span>
          <div class="slider-track" data-slider="score">
            <div class="slider-bg"></div>
            <div class="slider-fill"></div>
            <div class="slider-handle" data-h="lo"></div>
            <div class="slider-handle" data-h="hi"></div>
          </div>
          <span class="slider-val" id="val-score">0–100</span>
        </div>
        <div class="slider-cell">
          <span class="lbl">Min R:R</span>
          <div class="slider-track" data-slider="rr">
            <div class="slider-bg"></div>
            <div class="slider-fill"></div>
            <div class="slider-handle" data-h="lo"></div>
            <div class="slider-handle" data-h="hi"></div>
          </div>
          <span class="slider-val" id="val-rr">0–10</span>
        </div>
        <div class="sector-dd">
          <button class="sector-btn" id="sector-btn">📂 Sector <span id="sector-count">(all)</span> ▾</button>
          <div class="sector-menu" id="sector-menu"></div>
        </div>
      </div>
    </div>

    <!-- TABLE -->
    <div class="table-wrap">
      <div class="tb-hd">
        <div class="tb-title">Full Universe</div>
        <div class="tb-meta">showing <b id="tb-count">0</b> of <b id="tb-total">0</b> · click header to sort</div>
        <div class="tb-actions">
          <button class="tb-action" id="csv-btn">📥 CSV</button>
          <button class="tb-action" id="cols-btn">⚙ Columns</button>
        </div>
      </div>
      <div class="tb-scroll">
        <table id="universe-table">
          <thead><tr>
            <th class="num" style="width:36px">#</th>
            <th data-k="rank_delta" class="num" style="width:42px">Δ</th>
            <th data-k="sym">SYM</th>
            <th data-k="setup">SETUP</th>
            <th data-k="verdict">VERDICT</th>
            <th data-k="tier">TIER</th>
            <th data-k="score" class="num sorted desc">SCORE</th>
            <th>T·F·S·N</th>
            <th data-k="price" class="num">PX</th>
            <th>ENTRY</th>
            <th data-k="star" class="num">★</th>
            <th data-k="pct_change_1d" class="num">Δ%</th>
            <th data-k="rs" class="num">RS</th>
            <th data-k="rvol" class="num">RVOL</th>
            <th data-k="rr" class="num">R:R</th>
            <th data-k="earn_days" class="num">EARN</th>
            <th data-k="cat_tier" class="num">CAT</th>
            <th data-k="entry_quality">ENTRY Q</th>
            <th data-k="sector">SECTOR</th>
            <th data-k="src">SRC</th>
          </tr></thead>
          <tbody id="tb-body"></tbody>
        </table>
      </div>
    </div>

    <div class="legend">All data live from <b style="color:var(--copper)">cache/last_bundle.json</b> · build by <b>build_scanner_v2_e.py</b> · v2-E</div>
  </div>

  <script id="data-payload" type="application/json">__PAYLOAD__</script>
  <script>
    const DATA = JSON.parse(document.getElementById('data-payload').textContent);

    // ─── STATE ───────────────────────────────────────────────────────
    const STATE = {
      verdict: 'all',
      eq: 'all',
      zone: null,
      sectors: new Set(),
      search: '',
      priceLo: DATA.price_min, priceHi: DATA.price_max,
      scoreLo: 0, scoreHi: 100,
      rrLo: 0, rrHi: 10,
      sortKey: 'score', sortDir: 'desc',
    };

    // ─── HEADER PULSE ────────────────────────────────────────────────
    function renderPulse() {
      const p = DATA.pulse, c = DATA.counts;
      const rc = p.regime4.includes('panic')||p.regime4.includes('risk_off') ? 'rd' : p.regime4.includes('choppy') ? 'am' : 'gn';
      const vixPct = Math.min(Math.max((p.vix - 10) / 40, 0), 1);
      const a = 180 + vixPct * 180;
      const nx = 50 + 25 * Math.cos(a * Math.PI/180), ny = 45 + 25 * Math.sin(a * Math.PI/180);
      const br = p.breadth || 0;
      document.getElementById('hd-stats').innerHTML = `
        <div class="hs-cell"><div class="hs-pill ${rc}"><span class="pd"></span>${p.regime_label}</div></div>
        <div class="hs-cell">
          <svg class="hs-gauge" viewBox="0 0 100 50">
            <path d="M 10 45 A 40 40 0 0 1 90 45" fill="none" stroke="#1f2937" stroke-width="6" stroke-linecap="round"/>
            <path d="M 10 45 A 40 40 0 0 1 42 8" fill="none" stroke="#10b981" stroke-width="6" stroke-linecap="round"/>
            <path d="M 42 8 A 40 40 0 0 1 58 8" fill="none" stroke="#f59e0b" stroke-width="6"/>
            <path d="M 58 8 A 40 40 0 0 1 90 45" fill="none" stroke="#f87171" stroke-width="6" stroke-linecap="round"/>
            <line x1="50" y1="45" x2="${nx.toFixed(1)}" y2="${ny.toFixed(1)}" stroke="#fff" stroke-width="2" stroke-linecap="round"/>
            <circle cx="50" cy="45" r="3" fill="#c97b3a"/>
          </svg>
          <div><div class="hs-lbl">VIX</div><div class="hs-val">${p.vix.toFixed(1)}</div></div>
        </div>
        <div class="hs-cell">
          <div><div class="hs-lbl">Breadth</div><div class="hs-val">${br.toFixed(0)}%</div></div>
          <div class="hs-bar"><div class="hs-fill" style="width:100%"></div><div class="hs-marker" style="left:${br}%"></div></div>
        </div>
        <div class="hs-cell"><div><div class="hs-lbl">SPY</div><div class="hs-val">${(p.spy_price||0).toFixed(0)} <span style="font-size:0.6rem;color:${(p.spy_chg||0)>=0?'var(--gn)':'var(--rd)'}">${(p.spy_chg||0)>=0?'+':''}${(p.spy_chg||0).toFixed(1)}%</span></div></div></div>
        <div class="hs-cell"><div><div class="hs-lbl">Scored</div><div class="hs-val">${c.total}</div></div></div>
        <div class="hs-cell"><div><div class="hs-lbl">BUY</div><div class="hs-val gn">${c.buy}</div></div></div>
        <div class="hs-cell"><div><div class="hs-lbl">WATCH</div><div class="hs-val am">${c.watch}</div></div></div>
        <div class="hs-cell"><div><div class="hs-lbl">AVOID</div><div class="hs-val rd">${c.kill}</div></div></div>
        <div class="hs-cell"><div><div class="hs-lbl">Scan</div><div class="hs-val" style="font-size:0.72rem;color:var(--mute);font-weight:600">${(DATA.last_scan||'').slice(0,16).replace('T',' ')}</div></div></div>
      `;
      document.getElementById('cnt-all').textContent   = c.total;
      document.getElementById('cnt-buy').textContent   = c.buy;
      document.getElementById('cnt-watch').textContent = c.watch;
      document.getElementById('cnt-neut').textContent  = c.neut;
      document.getElementById('cnt-kill').textContent  = c.kill;
      document.getElementById('buy-cnt').textContent   = `${c.buy} ACTIVE`;
    }

    // ─── HISTOGRAM ────────────────────────────────────────────────────
    function renderHistogram() {
      const maxCount = Math.max(...DATA.hist.map(([_, n]) => n)) || 1;
      const html = DATA.hist.map(([bin, n]) => {
        const pct = (n / maxCount) * 100;
        return `<div class="hist-bar">
          <div class="hist-fill" style="height:${pct}%" title="${bin}: ${n} tickers"><span class="cnt">${n}</span></div>
          <div class="hist-lbl">${bin}</div>
        </div>`;
      }).join('');
      document.getElementById('hist').innerHTML = html;
    }

    // ─── SECTOR HEATMAP MINI ──────────────────────────────────────────
    function renderSectorMini() {
      const html = DATA.sector_data.map(s => {
        const buyPct = s.count ? (s.buys / s.count * 100) : 0;
        const killPct = s.count ? (s.kills / s.count * 100) : 0;
        const shortName = s.name.length > 8 ? s.name.slice(0, 7) + '…' : s.name;
        return `<div class="sec-tile" data-sector="${s.name}" title="${s.name}: ${s.count} names · ${s.buys} BUY · ${s.kills} AVOID">
          <div class="sec-name">${shortName}</div>
          <div class="sec-cnts">
            <span class="sec-buy">${s.buys}</span>
            <span class="sec-tot">${s.count}</span>
            <span class="sec-kill">${s.kills}</span>
          </div>
          <div class="sec-bar">
            <div class="b" style="width:${buyPct}%"></div>
            <div class="k" style="width:${killPct}%"></div>
          </div>
        </div>`;
      }).join('');
      document.getElementById('sec-mini').innerHTML = html;
      // wire click
      document.querySelectorAll('.sec-tile').forEach(t => {
        t.addEventListener('click', () => {
          const s = t.dataset.sector;
          if (STATE.sectors.has(s)) STATE.sectors.delete(s); else STATE.sectors.add(s);
          syncSectorMenu();
          applyFilters();
        });
      });
    }

    // ─── SPARKLINE w/ optional volume bars ───────────────────────────
    function sparkSvgFromCloses(closes, w, h) {
      if (!closes || closes.length < 2) return `<svg viewBox="0 0 ${w} ${h}"><line x1="0" y1="${h/2}" x2="${w}" y2="${h/2}" stroke="#374151" stroke-dasharray="2 2"/></svg>`;
      const min = Math.min(...closes), max = Math.max(...closes), range = max - min || 1;
      const pad = 3;
      const pts = closes.map((v, i) => [pad + (i/(closes.length-1))*(w-2*pad), h - pad - ((v-min)/range)*(h-2*pad)]);
      const polyStr = pts.map(p => p.map(n => n.toFixed(1)).join(',')).join(' ');
      const trend = closes[closes.length-1] > closes[0] ? 'up' : 'down';
      const stroke = trend === 'up' ? '#10b981' : '#f87171';
      const fill = trend === 'up' ? 'rgba(16,185,129,0.15)' : 'rgba(248,113,113,0.15)';
      const area = `${pad},${h-pad} ${polyStr} ${w-pad},${h-pad}`;
      const [lx, ly] = pts[pts.length-1];
      return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
        <polyline points="${area}" fill="${fill}" stroke="none"/>
        <polyline points="${polyStr}" fill="none" stroke="${stroke}" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/>
        <circle cx="${lx.toFixed(1)}" cy="${ly.toFixed(1)}" r="2.8" fill="#fff" stroke="${stroke}" stroke-width="1.5"/>
      </svg>`;
    }
    function volBarsSvg(volumes, w, h) {
      if (!volumes || volumes.length < 2) return `<svg viewBox="0 0 ${w} ${h}"></svg>`;
      const max = Math.max(...volumes) || 1;
      const barW = (w - 4) / volumes.length;
      const bars = volumes.map((v, i) => {
        const bh = (v / max) * (h - 2);
        const x = 2 + i * barW;
        const y = h - bh;
        return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${(barW*0.7).toFixed(1)}" height="${bh.toFixed(1)}" fill="rgba(201,123,58,0.55)" rx="0.5"/>`;
      }).join('');
      return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">${bars}</svg>`;
    }

    // ─── RADAR ────────────────────────────────────────────────────────
    function radarSvg(pillars) {
      const max = [35, 20, 20, 15, 10], labels = ['TEC','CAT','RS','SM','QG'];
      const cx = 60, cy = 45, r = 32, n = 5, ang = i => -Math.PI/2 + (i*2*Math.PI/n);
      const polyAt = vals => vals.map((v, i) => {
        const nr = Math.min(v/max[i], 1);
        return `${(cx + r*nr*Math.cos(ang(i))).toFixed(1)},${(cy + r*nr*Math.sin(ang(i))).toFixed(1)}`;
      }).join(' ');
      let grid = '';
      [0.33, 0.66, 1.0].forEach(l => {
        const pts = [];
        for (let i = 0; i < n; i++) pts.push(`${(cx + r*l*Math.cos(ang(i))).toFixed(1)},${(cy + r*l*Math.sin(ang(i))).toFixed(1)}`);
        grid += `<polygon points="${pts.join(' ')}" fill="none" stroke="#1f2937" stroke-width="0.7"/>`;
      });
      let axes = '', tx = '';
      for (let i = 0; i < n; i++) {
        const x = cx + r*Math.cos(ang(i)), y = cy + r*Math.sin(ang(i));
        axes += `<line x1="${cx}" y1="${cy}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}" stroke="#1f2937" stroke-width="0.7"/>`;
        const lx = cx + (r+7)*Math.cos(ang(i)), ly = cy + (r+7)*Math.sin(ang(i)) + 2;
        tx += `<text x="${lx.toFixed(1)}" y="${ly.toFixed(1)}" font-size="6.5" fill="#6b7280" font-family="ui-monospace,monospace" text-anchor="middle" font-weight="700">${labels[i]}</text>`;
      }
      return `<svg class="mc-radar" viewBox="0 0 120 90">${grid}${axes}<polygon points="${polyAt(pillars)}" fill="rgba(201,123,58,0.25)" stroke="#c97b3a" stroke-width="1.4"/>${tx}</svg>`;
    }

    function tierClass(t) { return t === 'T1' ? 'tier1' : t === 'T2' ? 'tier2' : 'tier3'; }
    function priceLadder(b) {
      if (!b.stop || !b.t1) return '<div class="mc-ladder" style="color:var(--mute-2);font-size:0.7rem;text-align:center">trade plan not generated for this BUY</div>';
      const range = b.t1 - b.stop;
      const now = b.price || b.entry_mid || b.stop;
      const entry = b.entry_mid || b.entry_low || now;
      const np = Math.max(0, Math.min(100, ((now-b.stop)/range)*100));
      const ep = Math.max(0, Math.min(100, ((entry-b.stop)/range)*100));
      return `<div class="mc-ladder">
        <div class="mc-ladder-hdr">
          <span style="color:var(--rd)">STOP ${b.stop.toFixed(2)}</span>
          <span style="color:var(--copper-hi)">ENTRY ${entry.toFixed(2)}</span>
          <span style="color:var(--gn)">T1 ${b.t1.toFixed(2)}</span>
        </div>
        <div class="mc-ladder-track">
          <div class="mc-ladder-line"></div>
          <div class="mc-ladder-tick" style="left:${ep}%"></div>
          <div class="mc-ladder-dot" style="left:${np}%"></div>
          <div class="mc-ladder-lbl bot" style="left:${np}%;color:var(--ink)">NOW ${now.toFixed(2)}</div>
        </div>
      </div>`;
    }

    function renderMegaCards() {
      const buys = DATA.buys;
      if (!buys.length) {
        document.getElementById('megacards').innerHTML = '<div style="grid-column:1/-1;padding:48px;text-align:center;color:var(--mute-2);background:var(--card);border:1px dashed var(--border);border-radius:12px;font-style:italic">No BUY signals in this scan</div>';
        return;
      }
      const html = buys.map(b => {
        const rr = b.rr || 0;
        const riskPct = (1/(1+rr))*100, rewardPct = (rr/(1+rr))*100;
        const chg = b.closes && b.closes.length >= 2 ? ((b.closes[b.closes.length-1] - b.closes[b.closes.length-2])/b.closes[b.closes.length-2]*100) : 0;
        const pCls = chg >= 0 ? 'up' : 'dn', pSign = chg >= 0 ? '+' : '';
        const sHi = b.closes && b.closes.length ? Math.max(...b.closes).toFixed(2) : '—';
        const sLo = b.closes && b.closes.length ? Math.min(...b.closes).toFixed(2) : '—';
        const zoneBadge = b.in_zone ? `<div class="mc-zone-badge ${b.in_zone==='IN ZONE'?'in-zone':b.in_zone==='NEAR'?'near':'past'}">● ${b.in_zone}</div>` : '';
        const narr = `${b.setup||b.family} · ${b.sector} · RS ${b.rs??'—'} · RVOL ${(b.rvol||0).toFixed(2)} · catalyst T${b.cat_tier??'—'}${b.earn_days!=null ? ` · earnings ${b.earn_days}d` : ''}${b.star ? ` · ★${b.star}` : ''}`;
        return `<div class="mc">
          <div class="mc-row1">
            <div class="mc-left">
              <div class="mc-sym">${b.sym}</div>
              ${b.name ? `<div class="mc-name">${b.name}</div>` : ''}
              <div class="mc-livepx"><b>$${(b.price||0).toFixed(2)}</b><span class="pct ${pCls}">${pSign}${chg.toFixed(2)}%</span></div>
            </div>
            <div class="mc-right">
              <div class="mc-score">${b.score}</div>
              <div class="mc-score-lbl">composite</div>
              <div class="mc-tier-row">
                <span class="chip ${tierClass(b.tier)}">${b.tier}</span>
                <span class="chip setup">${(b.setup||b.family).slice(0,11)}</span>
              </div>
              ${zoneBadge}
            </div>
          </div>
          <div class="mc-mid">
            <div class="mc-spark-wrap">
              <div class="mc-spark-hdr"><span>28-day · <b>${sLo}</b>→<b>${sHi}</b></span><span style="color:var(--mute-2)">$Vol ${b.dvol_m}M</span></div>
              <div class="mc-spark">${sparkSvgFromCloses(b.closes, 240, 54)}</div>
              <div class="mc-vol-bars">${volBarsSvg(b.volumes, 240, 18)}</div>
            </div>
            <div class="mc-radar-wrap"><div class="mc-radar-lbl">5-Pillar</div>${radarSvg(b.pillars)}</div>
          </div>
          ${priceLadder(b)}
          <div class="rrbar">
            <span class="rrlbl">Risk : Reward</span>
            <span class="rrtrack"><span class="risk" style="width:${riskPct}%"></span><span class="reward" style="width:${rewardPct}%"></span></span>
            <b>${rr ? rr.toFixed(1) : '—'}:1</b>
          </div>
          <div class="mc-narr">${narr}</div>
          <div class="mc-actions"><button class="mc-action primary">▶ BUY</button><button class="mc-action">⭐ Watch</button><button class="mc-action">📋 Plan</button></div>
        </div>`;
      }).join('');
      document.getElementById('megacards').innerHTML = html;
    }

    // ─── SIDEBAR ────────────────────────────────────────────────────
    function sidebarRow(rk, sym, val, valCls, m, closes) {
      const sp = closes && closes.length ? sparkSvgFromCloses(closes.slice(-12), 38, 14) : '';
      return `<div class="sb-row" data-sym="${sym}">
        <span class="rk">${rk}</span>
        <span class="sym">${sym}</span>
        <span class="meta">${m}</span>
        <div class="mini-spark">${sp}</div>
        <span class="val ${valCls||''}">${val}</span>
      </div>`;
    }
    function renderSidebar() {
      const fresh = DATA.panels.fresh.map((r,i) => sidebarRow(`#${i+1}`, r.sym, r.score, r.score>=75?'gn':r.score>=60?'am':'', `${r.setup||r.family} · ${r.sector}<br/>RVOL <b>${(r.rvol||0).toFixed(2)}</b> · RS <b>${r.rs??'—'}</b>`, r.closes)).join('') || '<div class="sb-empty">no FRESH entries</div>';
      const earn = DATA.panels.earnings.map((r,i) => sidebarRow(`#${i+1}`, r.sym, r.earn_days===0?'TODAY':`+${r.earn_days}d`, r.earn_days<=1?'rd':r.earn_days<=3?'am':'', `${r.sector} · ${r.setup||r.family}<br/>${r.industry.slice(0,28)}`, r.closes)).join('') || '<div class="sb-empty">no earnings ≤7d</div>';
      const sg = DATA.panels.surges.map((r,i) => sidebarRow(`#${i+1}`, r.sym, `${(r.rvol||0).toFixed(2)}×`, (r.rvol||0)>=3?'gn':'am', `${r.sector} · ${r.setup||r.family}<br/>Score <b>${r.score}</b> · entry <b>${r.entry_quality}</b>`, r.closes)).join('') || '<div class="sb-empty">no surges ≥1.5×</div>';
      const ai = DATA.panels.ai.map((r,i) => `<div class="sb-row"><span class="rk">#${i+1}</span><span class="sym">${r.sym}</span><span class="meta">p(up) <b>${(r.p_up*100).toFixed(0)}%</b><br/>${r.verdict}</span><span class="val gn">${r.edge>=0?'+':''}${r.edge.toFixed(2)}%</span></div>`).join('') || '<div class="sb-empty">ML cache empty</div>';
      const mom = DATA.panels.momentum.map((r,i) => sidebarRow(`#${i+1}`, r.sym, `${(r.momentum||0).toFixed(0)}`, (r.momentum||0)>=80?'gn':(r.momentum||0)>=60?'am':'', `${r.sector}<br/>Score <b>${r.score}</b> · RS <b>${r.rs??'—'}</b>`, r.closes)).join('') || '<div class="sb-empty">no momentum</div>';

      document.getElementById('sidebar').innerHTML = `
        <div class="sb-card"><div class="sb-hd open" onclick="toggleSb(this)"><div class="sb-hd-l"><span class="ico">⚡</span>Fresh Entries</div><div class="sb-hd-r"><span class="cnt">${DATA.panels.fresh.length}</span><span class="caret">▼</span></div></div><div class="sb-body show">${fresh}</div></div>
        <div class="sb-card"><div class="sb-hd" onclick="toggleSb(this)"><div class="sb-hd-l"><span class="ico">📅</span>Earnings This Week</div><div class="sb-hd-r"><span class="cnt">${DATA.panels.earnings.length}</span><span class="caret">▼</span></div></div><div class="sb-body">${earn}</div></div>
        <div class="sb-card"><div class="sb-hd" onclick="toggleSb(this)"><div class="sb-hd-l"><span class="ico">🔥</span>Volume Surges</div><div class="sb-hd-r"><span class="cnt">${DATA.panels.surges.length}</span><span class="caret">▼</span></div></div><div class="sb-body">${sg}</div></div>
        <div class="sb-card"><div class="sb-hd" onclick="toggleSb(this)"><div class="sb-hd-l"><span class="ico">✦</span>AI Edge Top 5</div><div class="sb-hd-r"><span class="cnt">${DATA.panels.ai.length}</span><span class="caret">▼</span></div></div><div class="sb-body">${ai}</div></div>
        <div class="sb-card"><div class="sb-hd" onclick="toggleSb(this)"><div class="sb-hd-l"><span class="ico">🚀</span>Top Momentum</div><div class="sb-hd-r"><span class="cnt">${DATA.panels.momentum.length}</span><span class="caret">▼</span></div></div><div class="sb-body">${mom}</div></div>
      `;
    }
    function toggleSb(el) { el.classList.toggle('open'); el.nextElementSibling.classList.toggle('show'); }
    window.toggleSb = toggleSb;

    // ─── SLIDERS ────────────────────────────────────────────────────
    function bindSlider(sliderEl, min, max, onChange, format) {
      const fill = sliderEl.querySelector('.slider-fill');
      const hLo  = sliderEl.querySelector('[data-h="lo"]');
      const hHi  = sliderEl.querySelector('[data-h="hi"]');
      let lo = min, hi = max;
      const update = () => {
        const loPct = ((lo - min) / (max - min)) * 100;
        const hiPct = ((hi - min) / (max - min)) * 100;
        hLo.style.left = `${loPct}%`;
        hHi.style.left = `${hiPct}%`;
        fill.style.left = `${loPct}%`;
        fill.style.width = `${hiPct - loPct}%`;
        onChange(lo, hi);
        const label = sliderEl.parentElement.querySelector('.slider-val');
        if (label) label.textContent = format(lo, hi);
      };
      update();

      function drag(handle, isLo) {
        let active = false;
        const start = e => { active = true; e.preventDefault(); };
        const move = e => {
          if (!active) return;
          const rect = sliderEl.getBoundingClientRect();
          const x = (e.clientX || (e.touches && e.touches[0].clientX)) - rect.left;
          const pct = Math.max(0, Math.min(1, x / rect.width));
          const v = min + pct * (max - min);
          if (isLo) lo = Math.min(v, hi - (max-min)*0.02);
          else      hi = Math.max(v, lo + (max-min)*0.02);
          update();
        };
        const stop = () => { active = false; };
        handle.addEventListener('mousedown', start);
        handle.addEventListener('touchstart', start);
        window.addEventListener('mousemove', move);
        window.addEventListener('touchmove', move);
        window.addEventListener('mouseup', stop);
        window.addEventListener('touchend', stop);
      }
      drag(hLo, true);
      drag(hHi, false);
      return () => { lo = min; hi = max; update(); };
    }

    let resetPrice, resetScore, resetRR;
    function initSliders() {
      const pSlider = document.querySelector('[data-slider="price"]');
      const sSlider = document.querySelector('[data-slider="score"]');
      const rSlider = document.querySelector('[data-slider="rr"]');
      resetPrice = bindSlider(pSlider, DATA.price_min, DATA.price_max,
        (l, h) => { STATE.priceLo = l; STATE.priceHi = h; applyFilters(); },
        (l, h) => `$${l.toFixed(0)}–$${h.toFixed(0)}`);
      resetScore = bindSlider(sSlider, 0, 100,
        (l, h) => { STATE.scoreLo = l; STATE.scoreHi = h; applyFilters(); },
        (l, h) => `${l.toFixed(0)}–${h.toFixed(0)}`);
      resetRR = bindSlider(rSlider, 0, 10,
        (l, h) => { STATE.rrLo = l; STATE.rrHi = h; applyFilters(); },
        (l, h) => `${l.toFixed(1)}–${h.toFixed(1)}`);
    }

    // ─── SECTOR MULTI-SELECT ─────────────────────────────────────────
    function renderSectorMenu() {
      const html = DATA.sector_data.map(s => `
        <label><input type="checkbox" data-sector="${s.name}"> ${s.name} <span class="cnt">${s.count}</span></label>
      `).join('');
      document.getElementById('sector-menu').innerHTML = html;
      document.querySelectorAll('#sector-menu input').forEach(cb => {
        cb.addEventListener('change', () => {
          const s = cb.dataset.sector;
          if (cb.checked) STATE.sectors.add(s); else STATE.sectors.delete(s);
          updateSectorBtn();
          applyFilters();
        });
      });
    }
    function syncSectorMenu() {
      document.querySelectorAll('#sector-menu input').forEach(cb => {
        cb.checked = STATE.sectors.has(cb.dataset.sector);
      });
      updateSectorBtn();
    }
    function updateSectorBtn() {
      const btn = document.getElementById('sector-btn');
      const c = document.getElementById('sector-count');
      if (STATE.sectors.size === 0) {
        c.textContent = '(all)';
        btn.classList.remove('has-filter');
      } else {
        c.textContent = `(${STATE.sectors.size})`;
        btn.classList.add('has-filter');
      }
    }
    document.getElementById('sector-btn').addEventListener('click', e => {
      e.stopPropagation();
      document.getElementById('sector-menu').classList.toggle('show');
    });
    document.addEventListener('click', e => {
      if (!e.target.closest('.sector-dd')) {
        document.getElementById('sector-menu').classList.remove('show');
      }
    });

    // ─── FILTER CHIPS ────────────────────────────────────────────────
    document.querySelectorAll('.fchip[data-fg]').forEach(c => {
      c.addEventListener('click', () => {
        const fg = c.dataset.fg, fv = c.dataset.fv;
        // single-select per group
        document.querySelectorAll(`.fchip[data-fg="${fg}"]`).forEach(x => x.classList.remove('on'));
        c.classList.add('on');
        if (fg === 'zone') { STATE.zone = fv === 'all' ? null : fv; }
        else STATE[fg] = fv;
        applyFilters();
      });
    });

    document.getElementById('search').addEventListener('input', e => {
      STATE.search = e.target.value.trim().toUpperCase();
      applyFilters();
    });

    document.getElementById('reset-btn').addEventListener('click', () => {
      STATE.verdict='all'; STATE.eq='all'; STATE.zone=null; STATE.sectors.clear(); STATE.search='';
      document.getElementById('search').value = '';
      document.querySelectorAll('.fchip').forEach(c => c.classList.remove('on'));
      document.querySelectorAll('.fchip[data-fv="all"]').forEach(c => c.classList.add('on'));
      syncSectorMenu();
      if (resetPrice) resetPrice();
      if (resetScore) resetScore();
      if (resetRR) resetRR();
      applyFilters();
    });

    // ─── HISTOGRAM bar click → score filter ──────────────────────────
    document.addEventListener('click', e => {
      if (e.target.classList.contains('hist-fill')) {
        // future: filter by bin
      }
    });

    // ─── FILTER APPLY + TABLE RENDER ─────────────────────────────────
    function applyFilters() {
      let rows = DATA.universe.slice();
      if (STATE.verdict !== 'all') rows = rows.filter(r => (r.verdict||'').toUpperCase() === STATE.verdict);
      if (STATE.eq !== 'all') rows = rows.filter(r => (r.entry_quality||'').toUpperCase() === STATE.eq);
      if (STATE.zone) rows = rows.filter(r => r.in_zone === STATE.zone);
      if (STATE.sectors.size) rows = rows.filter(r => STATE.sectors.has(r.sector));
      if (STATE.search) rows = rows.filter(r => (r.sym||'').toUpperCase().includes(STATE.search) || (r.name||'').toUpperCase().includes(STATE.search));
      rows = rows.filter(r => (r.price||0) >= STATE.priceLo && (r.price||0) <= STATE.priceHi);
      rows = rows.filter(r => (r.score||0) >= STATE.scoreLo && (r.score||0) <= STATE.scoreHi);
      rows = rows.filter(r => (r.rr||0) >= STATE.rrLo && (r.rr||0) <= STATE.rrHi);

      // Sort
      rows.sort((a, b) => {
        const va = a[STATE.sortKey], vb = b[STATE.sortKey];
        const na = (va == null) ? -Infinity : va, nb = (vb == null) ? -Infinity : vb;
        const cmp = (typeof na === 'string') ? na.localeCompare(nb) : (na - nb);
        return STATE.sortDir === 'asc' ? cmp : -cmp;
      });

      renderTable(rows);
      document.getElementById('tb-count').textContent = rows.length;
      document.getElementById('tb-total').textContent = DATA.universe.length;
    }

    function fmt(v, dp=2) {
      if (v == null) return '—';
      const n = +v;
      return isNaN(n) ? v : n.toFixed(dp);
    }
    // helpers for table cell rendering ─────────────────────────────
    function scoreBar(score, w) {
      const pct = Math.min(100, score);
      const color = score >= 75 ? '#10b981' : score >= 60 ? '#f59e0b' : '#6b7280';
      return `<span style="display:inline-block;width:${w}px;height:5px;background:#1f2937;border-radius:3px;margin-left:6px;vertical-align:middle;overflow:hidden"><span style="display:block;height:100%;width:${pct}%;background:${color};border-radius:3px"></span></span>`;
    }
    function tfsnBars(tfsn) {
      const labels = ['T','F','S','N'];
      const colors = tfsn.map(v => v >= 0.66 ? '#10b981' : v >= 0.33 ? '#f59e0b' : '#f87171');
      const bars = tfsn.map((v, i) => {
        const h = Math.max(3, v * 16);
        return `<span style="display:inline-flex;flex-direction:column;align-items:center;gap:1px;margin-right:2px">
          <span style="display:block;width:5px;height:16px;background:#1f2937;border-radius:1px;position:relative;overflow:hidden">
            <span style="position:absolute;bottom:0;left:0;right:0;height:${h}px;background:${colors[i]};border-radius:1px"></span>
          </span>
          <span style="font-size:0.5rem;color:#6b7280;font-family:ui-monospace,monospace;font-weight:700">${labels[i]}</span>
        </span>`;
      }).join('');
      return `<span style="display:inline-flex;align-items:flex-end">${bars}</span>`;
    }
    function entryWithIcon(q) {
      const qq = (q||'').toUpperCase();
      if (qq === 'FRESH')    return `<span style="color:var(--gn)">⚡ FRESH</span>`;
      if (qq === 'PULLBACK') return `<span style="color:var(--am)">⚡ PULLBACK</span>`;
      if (qq === 'VALID')    return `<span style="color:var(--bl)">↗ VALID</span>`;
      if (qq === 'EXTENDED') return `<span style="color:var(--copper-hi)">↑ EXTENDED</span>`;
      if (qq === 'MISSED')   return `<span style="color:var(--rd)">✕ MISSED</span>`;
      return `<span style="color:var(--mute-2)">—</span>`;
    }
    function starsRating(n) {
      n = Math.max(0, Math.min(5, n || 0));
      const filled = '★'.repeat(n);
      const empty  = '☆'.repeat(5 - n);
      const color = n >= 4 ? '#10b981' : n >= 3 ? '#f59e0b' : '#f87171';
      return `<span style="color:${color};letter-spacing:1px;font-size:0.85rem">${filled}<span style="color:#374151">${empty}</span></span>`;
    }
    function rankDelta(d) {
      if (d == null) return `<span style="color:var(--mute-3)">·</span>`;
      if (d === 0)  return `<span style="color:var(--mute-2)">0</span>`;
      if (d > 0)    return `<span style="color:var(--gn);font-weight:700">+${d}</span>`;
      return `<span style="color:var(--rd);font-weight:700">${d}</span>`;
    }
    function srcPill(src) {
      const COLORS = {
        'SP500': 'var(--gn)', 'R1000': 'var(--bl)', 'R2000': 'var(--copper)',
        'MID400': 'var(--pl)', 'SML600': 'var(--am)',
        'IPO': 'var(--ti)', 'CRYPTO': 'var(--ti)',
        'MOM': 'var(--am)', 'ETF': 'var(--mute-2)',
      };
      const color = COLORS[src] || 'var(--mute-2)';
      return `<span style="display:inline-block;padding:2px 7px;border:1px solid ${color};color:${color};border-radius:5px;font-size:0.62rem;font-weight:700;font-family:ui-monospace,monospace;letter-spacing:0.04em">${src||'—'}</span>`;
    }
    function pctChip(pct) {
      if (pct === null || pct === undefined || isNaN(pct)) return `<span style="color:var(--mute-2)">—</span>`;
      const cls = pct >= 0 ? 'var(--gn)' : 'var(--rd)';
      const sign = pct >= 0 ? '+' : '';
      return `<span style="color:${cls};font-weight:700">${sign}${pct.toFixed(2)}</span>`;
    }

    function renderTable(rows) {
      if (!rows.length) {
        document.getElementById('tb-body').innerHTML = `<tr><td colspan="20" class="empty-state">No tickers match these filters · <a href="#" onclick="document.getElementById('reset-btn').click();return false;" style="color:var(--copper)">reset</a></td></tr>`;
        return;
      }
      const html = rows.map((r, i) => {
        const sc = r.score >= 75 ? 'hi' : r.score >= 60 ? 'mid' : 'lo';
        const idx = String(i + 1).padStart(2, '0');
        return `<tr>
          <td class="num" style="color:var(--mute-2);font-weight:700">${idx}</td>
          <td class="num">${rankDelta(r.rank_delta)}</td>
          <td><b style="color:var(--ink);font-size:0.86rem;letter-spacing:0.02em">${r.sym}</b></td>
          <td style="color:var(--ink-2)">${(r.setup||r.family||'').slice(0,18)}</td>
          <td><span class="vchip ${r.verdict||'NEUTRAL'}">${(r.verdict||'—').toUpperCase()}</span></td>
          <td style="color:var(--ink-2);font-weight:700">${r.tier||'—'}</td>
          <td class="num"><b class="score-cell ${sc}">${r.score}</b>${scoreBar(r.score, 38)}</td>
          <td>${tfsnBars(r.tfsn)}</td>
          <td class="num" style="color:var(--ink-2);font-weight:700">${r.price ? r.price.toFixed(2) : '—'}</td>
          <td>${entryWithIcon(r.entry_quality)}</td>
          <td class="num">${starsRating(r.star)}</td>
          <td class="num">${pctChip(r.pct_change_1d)}</td>
          <td class="num">${r.rs??'—'}</td>
          <td class="num">${fmt(r.rvol)}×</td>
          <td class="num" style="color:var(--gn);font-weight:700">${r.rr?'1:'+r.rr.toFixed(1):'—'}</td>
          <td class="num" style="color:${r.earn_days!=null && r.earn_days<=7 ? 'var(--am)' : 'var(--mute-2)'}">${r.earn_days==null?'—':(r.earn_days===0?'TODAY':'+'+r.earn_days+'d')}</td>
          <td class="num">${r.cat_tier?'<span style="color:var(--copper-hi);font-weight:700">T'+r.cat_tier+'</span>':'<span style="color:var(--mute-2)">—</span>'}</td>
          <td style="color:var(--ink-2);font-weight:600">${(r.entry_quality||'—').toUpperCase()}</td>
          <td style="color:var(--mute)">${(r.sector||'').slice(0,15)}</td>
          <td>${srcPill(r.src)}</td>
        </tr>`;
      }).join('');
      document.getElementById('tb-body').innerHTML = html;
    }

    // ─── SORTABLE COLUMNS ────────────────────────────────────────────
    document.querySelectorAll('th[data-k]').forEach(th => {
      th.addEventListener('click', () => {
        const k = th.dataset.k;
        if (STATE.sortKey === k) STATE.sortDir = STATE.sortDir === 'asc' ? 'desc' : 'asc';
        else { STATE.sortKey = k; STATE.sortDir = 'desc'; }
        document.querySelectorAll('th').forEach(x => x.classList.remove('sorted','asc','desc'));
        th.classList.add('sorted', STATE.sortDir);
        applyFilters();
      });
    });

    // ─── KEYBOARD ────────────────────────────────────────────────────
    document.addEventListener('keydown', e => {
      if (e.key === '/' && document.activeElement.tagName !== 'INPUT') {
        e.preventDefault();
        document.getElementById('search').focus();
      }
      if (e.key === 'Escape') {
        document.getElementById('search').blur();
      }
    });

    // ─── CSV EXPORT ──────────────────────────────────────────────────
    document.getElementById('csv-btn').addEventListener('click', () => {
      const rows = DATA.universe;
      const cols = ['sym','score','verdict','tier','setup','sector','price','dvol_m','rs','rvol','rsi','rr','stop','t1','entry_quality','cat_tier','hold'];
      const csv = [cols.join(',')].concat(rows.map(r => cols.map(c => JSON.stringify(r[c] ?? '')).join(','))).join('\n');
      const blob = new Blob([csv], {type: 'text/csv'});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = `scanner_${new Date().toISOString().slice(0,10)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    });

    // ─── INIT ────────────────────────────────────────────────────────
    renderPulse();
    renderHistogram();
    renderSectorMini();
    renderMegaCards();
    renderSidebar();
    renderSectorMenu();
    initSliders();
    applyFilters();
  </script>
</body>
</html>
'''

OUT.write_text(HTML.replace('__PAYLOAD__', json.dumps(payload)))
print(f'wrote {OUT.relative_to(BASE)} ({OUT.stat().st_size:,} bytes)')

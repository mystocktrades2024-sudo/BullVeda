"""Build scanner_v2_f.html — the "best last shot" with distinctive UX:
Decision Funnel · Conviction Compass · Bento mega-cards · Spark w/ price markers ·
Trade Simulator slider · Sector Orbit · Ticker Tape · all filters from v2_e.
"""
from __future__ import annotations
import json
from pathlib import Path
from collections import Counter

BASE = Path(__file__).resolve().parents[3]
BUNDLE = BASE / 'cache' / 'last_bundle.json'
ML     = BASE / 'cache' / 'ml_edge_predictions.json'
OUT    = Path(__file__).resolve().parent / 'scanner_v2_f.html'

print(f'reading {BUNDLE.relative_to(BASE)} ...')
b = json.loads(BUNDLE.read_text())
ml = json.loads(ML.read_text()) if ML.exists() else {}

ascored = b.get('all_scored') or []
regime  = b.get('regime') or {}

# ─── Compute per-setup-family win rate from picks_history (real WR) ────
import math
def wilson_lb(wins, n, z=1.96):
    if n == 0: return 0.0
    p = wins / n
    denom = 1 + z*z/n
    centre = p + z*z/(2*n)
    spread = z * math.sqrt((p*(1-p) + z*z/(4*n)) / n)
    return max(0.0, (centre - spread) / denom)
SETUP_WR = {}
PH = BASE / 'cache' / 'picks_history.json'
if PH.exists():
    ph = json.loads(PH.read_text())
    from collections import defaultdict
    by_setup = defaultdict(list)
    for t in (ph.get('trades') or []):
        sf = t.get('setup_family') or t.get('setup_type')
        if sf: by_setup[sf].append(t)
    for sf, ts in by_setup.items():
        wins = sum(1 for t in ts if t.get('win'))
        n = len(ts)
        SETUP_WR[sf] = { 'wr': round(wins/n, 3) if n else 0, 'lb': round(wilson_lb(wins, n), 3), 'n': n }
print(f'  setup-WR stats loaded: {len(SETUP_WR)} setups · sample top 3: {dict(list(SETUP_WR.items())[:3])}')

# ─── Mechanism hypotheses (per CLAUDE.md MECHANISM_HYPOTHESES) ─────────
MECHANISM_MAP = {
    'VCP Breakout':        'supply absorption · base contraction',
    'Breakout Expansion':  'institutional accumulation breakout',
    'Trend Continuation':  'momentum persistence · EMA re-add',
    'EMA21 Pullback':      'fast-trend institutional re-add',
    'EMA50 Pullback':      'mid-trend buy-the-dip absorption',
    'Pocket Pivot':        'first institutional thrust off base',
    'Near-VCP Breakout':   'pre-pivot absorption · early position',
    'Impulse Catalyst':    'PEAD / earnings-revision front-run',
    'Squeeze Expansion':   'volatility compression → expansion',
    'Squeeze Breakout':    'bollinger squeeze release',
    'Stage 2 Breakout (52w high)': 'supply exhausted at prior cap',
    'Insider Cluster':     'informed-buyer signal · cluster',
    'Defensive Rotation':  'risk-off sector rotation',
    'Mean Reversion':      'oversold + uptrend bounce',
    'PEAD':                'post-earnings drift (Bernard-Thomas)',
    'ESP Play':            'Zacks ESP pre-earnings drift',
}

counts = Counter((t.get('verdict') or '').upper() for t in ascored)
TOTAL   = len(ascored)
BUY_N   = counts.get('BUY', 0)
WATCH_N = counts.get('WATCH', 0)
NEUT_N  = counts.get('WAIT', 0) + counts.get('NEUTRAL', 0)
KILL_N  = counts.get('AVOID', 0) + counts.get('SHORT', 0)

# Decision funnel: scored → passed price gate → passed score floor (60) → passed gates → BUY
price_ok = [t for t in ascored if (t.get('price') or 0) >= 5 and (t.get('price') or 0) <= 1000]
score_60 = [t for t in price_ok if (t.get('score') or 0) >= 60]
rr_ok    = [t for t in score_60 if ((t.get('trade_plan') or {}).get('rr_ratio') or 0) >= 2.0]
watch    = [t for t in rr_ok if (t.get('verdict') or '').upper() in ('WATCH','BUY')]
buys     = [t for t in watch if (t.get('verdict') or '').upper() == 'BUY']

funnel = [
    {'label':'Universe',         'value': TOTAL,                    'detail': f'{TOTAL} tickers scanned'},
    {'label':'Liquidity gate',   'value': len(price_ok),            'detail': '$5-$1000 price · $10M+ ADV'},
    {'label':'Score ≥ 60',       'value': len(score_60),            'detail': 'cleared composite floor'},
    {'label':'R:R ≥ 2.0',        'value': len(rr_ok),               'detail': 'risk/reward acceptable'},
    {'label':'WATCH+',           'value': len(watch),               'detail': 'verdict ≥ WATCH'},
    {'label':'BUY',              'value': len(buys),                'detail': 'final BUYs'},
]
print(f'  funnel: {[(f["label"], f["value"]) for f in funnel]}')

# Sector counts
sector_counts = Counter()
sector_buys   = Counter()
sector_kills  = Counter()
for t in ascored:
    s = t.get('sector') or 'Other'
    sector_counts[s] += 1
    v = (t.get('verdict') or '').upper()
    if v == 'BUY':   sector_buys[s]  += 1
    if v == 'AVOID': sector_kills[s] += 1

# Score histogram
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
    closes  = [r.get('close')  for r in oh[-28:] if isinstance(r, dict) and r.get('close')  is not None] if isinstance(oh, list) else []
    volumes = [r.get('volume') for r in oh[-28:] if isinstance(r, dict) and r.get('volume') is not None] if isinstance(oh, list) else []
    # Full OHLC bars for TradingView LWC chart (featured cards) — last 60 bars
    bars = []
    if isinstance(oh, list):
        for r in oh[-60:]:
            if not isinstance(r, dict): continue
            tm = r.get('time')
            if tm is None: continue
            bars.append({
                'time': int(tm),
                'open':  float(r.get('open')  or r.get('close') or 0),
                'high':  float(r.get('high')  or r.get('close') or 0),
                'low':   float(r.get('low')   or r.get('close') or 0),
                'close': float(r.get('close') or 0),
                'volume':float(r.get('volume') or 0),
            })
    price = t.get('price') or 0
    in_zone = None
    if e_low and e_high and price:
        if e_low <= price <= e_high: in_zone = 'IN ZONE'
        elif price < e_low and (e_low - price)/price < 0.05: in_zone = 'NEAR'
        elif price > e_high and (price - e_high)/price < 0.05: in_zone = 'PAST'
    dollar_vol = (price or 0) * (t.get('avg_volume') or 0)
    sm_pct   = (sb.get('smart_money', 0) or 0) / 15.0
    qg_pct   = (sb.get('quality_gate', 0) or 0) / 10.0
    tech_pct = (sb.get('tech', 0) or 0) / 35.0
    ns_raw = t.get('news_sentiment_score') or 0
    if isinstance(ns_raw, dict):
        ns_raw = ns_raw.get('score') or ns_raw.get('value') or 0
    try: ns_raw = float(ns_raw)
    except: ns_raw = 0
    n_pct = max(0, min(1, (ns_raw + 1) / 2)) if ns_raw else 0
    tfsn = [round(tech_pct, 2), round(qg_pct, 2), round(sm_pct, 2), round(n_pct, 2)]
    src_raw = (t.get('ticker_source') or '').lower()
    src_map = {'sp500':'SP500','russell1000':'R1000','russell2000':'R2000','sp_midcap_400':'MID400','sp_smallcap_600':'SML600','recent_ipo':'IPO','crypto_adjacent':'CRYPTO','screener_momentum':'MOM','etf_holding':'ETF'}
    return {
        'sym': t.get('ticker'),
        'name': (t.get('name') or '').replace('"', "'")[:40],
        'score': int(round(t.get('score') or 0)),
        'verdict': t.get('verdict'),
        'tier': ctp.get('conviction_tier') or '—',
        'setup': tp.get('setup_type') or t.get('setup_family') or '—',
        'family': t.get('setup_family') or '—',
        'sector': t.get('sector') or 'Other',
        'industry': (t.get('industry') or '').replace('"',"'")[:34],
        'rs': t.get('rs_rank'), 'rsi': t.get('rsi'), 'rvol': t.get('rvol'),
        'price': t.get('price'),
        'pct_change_1d': t.get('pct_change_1d') or t.get('day_chg_pct') or 0,
        'dvol_m': round(dollar_vol / 1_000_000, 1) if dollar_vol else 0,
        'entry_low': e_low, 'entry_high': e_high,
        'entry_mid': round(e_mid, 2) if e_mid else None,
        'stop': tp.get('stop') or ctp.get('stop'),
        't1': tp.get('target1') or ctp.get('target1'),
        't2': tp.get('target2') or ctp.get('target2'),
        'rr': tp.get('rr_ratio'),
        'hold': tp.get('max_hold_days'),
        'entry_quality': t.get('entry_quality') or '—',
        'cat_tier': t.get('catalyst_tier'),
        'earn_days': e.get('days_to_earnings'),
        'pillars': pillars, 'tfsn': tfsn,
        'closes': closes, 'volumes': volumes,
        'bars': bars,
        'star': t.get('star_rating') or 0,
        'in_zone': in_zone,
        'momentum': t.get('raw_momentum_score'),
        'allocation_pct': tp.get('allocation_pct'),
        'src': src_map.get(src_raw, src_raw.upper()[:6] if src_raw else '—'),
        'rank_delta': None,
        # WR (LB-N) for this setup_family, from picks_history
        'wr_stats': SETUP_WR.get(t.get('setup_family')) or SETUP_WR.get(tp.get('setup_type')) or {'wr':None,'lb':None,'n':0},
        # Mechanism hypothesis
        'mechanism': MECHANISM_MAP.get(t.get('setup_family')) or MECHANISM_MAP.get(tp.get('setup_type')) or '—',
    }

universe = sorted([compact_row(t) for t in ascored], key=lambda r: -(r['score'] or 0))[:150]

# Add derived sort-friendly fields so JS can sort on every column
EQ_ORDER = {'FRESH': 5, 'PULLBACK': 4, 'VALID': 3, 'EXTENDED': 2, 'MISSED': 1, '—': 0, '': 0}
for r in universe:
    pillars = r.get('pillars') or [0,0,0,0,0]
    r['tfsn_sum'] = round(sum(r.get('tfsn') or [0,0,0,0]), 3)
    r['entry_quality_ord'] = EQ_ORDER.get((r.get('entry_quality') or '').upper(), 0)
    r['wr_lb'] = (r.get('wr_stats') or {}).get('lb') or 0

# CORE vs ALPHA segmentation (matches the original Signal Scanner TRACK split)
CORE_SRCS  = {'SP500', 'R1000'}
ALPHA_SRCS = {'R2000', 'MID400', 'SML600', 'IPO', 'CRYPTO', 'MOM', 'ETF'}
core_n  = sum(1 for r in universe if r['src'] in CORE_SRCS)
alpha_n = sum(1 for r in universe if r['src'] in ALPHA_SRCS)
core_buy_n  = sum(1 for r in universe if r['src'] in CORE_SRCS  and r['verdict'] == 'BUY')
alpha_buy_n = sum(1 for r in universe if r['src'] in ALPHA_SRCS and r['verdict'] == 'BUY')
print(f'  CORE: {core_n} (BUYs {core_buy_n}) · ALPHA: {alpha_n} (BUYs {alpha_buy_n})')

PH = BASE / 'cache' / 'picks_history.json'
prev_rank = {}
if PH.exists():
    try:
        ph = json.loads(PH.read_text())
        runs = ph.get('runs') or []
        if len(runs) >= 2:
            for i, p in enumerate(runs[-2].get('picks', [])):
                prev_rank[p.get('ticker')] = i + 1
    except Exception: pass

for i, r in enumerate(universe):
    prev = prev_rank.get(r['sym'])
    if prev is not None: r['rank_delta'] = prev - (i + 1)

buys_rows = [r for r in universe if r['verdict'] == 'BUY']

# Sidebar panels (same as v2_e)
def panel_fresh():    return sorted([r for r in universe if r['entry_quality']=='FRESH'], key=lambda r: -r['score'])[:5]
def panel_earn():     return sorted([r for r in universe if r['earn_days'] is not None and 0 <= r['earn_days'] <= 7], key=lambda r: r['earn_days'])[:5]
def panel_surge():    return sorted([r for r in universe if (r['rvol'] or 0) >= 1.5], key=lambda r: -(r['rvol'] or 0))[:5]
def panel_mom():      return sorted([r for r in universe if (r['momentum'] or 0) > 0], key=lambda r: -(r['momentum'] or 0))[:5]
def panel_ai():
    pool = (ml.get('predictions') or {}).get('swing') or {}
    items = []
    for sym, p in pool.items():
        d = p.get('direction') or {}
        items.append({'sym': sym, 'p_up': d.get('p_up') or 0,
                      'edge': (p.get('verdict') or {}).get('edge') or 0,
                      'verdict': (p.get('verdict') or {}).get('text', '—')})
    return sorted(items, key=lambda x: -x['p_up'])[:5]

panels = {'fresh': panel_fresh(), 'earnings': panel_earn(), 'surges': panel_surge(), 'momentum': panel_mom(), 'ai': panel_ai()}

# Conviction compass scatter — all universe with score>30 plotted
scatter = [{'sym':r['sym'],'score':r['score'],'rr':r['rr'] or 0,'verdict':r['verdict'],'sector':r['sector'],'price':r['price'] or 0,'tier':r['tier']} for r in universe if (r['score'] or 0) >= 30]
print(f'  scatter points: {len(scatter)}')

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
    'counts': {'total': TOTAL, 'buy': BUY_N, 'watch': WATCH_N, 'neut': NEUT_N, 'kill': KILL_N,
               'core': core_n, 'alpha': alpha_n, 'core_buy': core_buy_n, 'alpha_buy': alpha_buy_n},
    'core_srcs':  sorted(CORE_SRCS),
    'alpha_srcs': sorted(ALPHA_SRCS),
    'funnel': funnel,
    'sector_data': [{'name': s, 'count': c, 'buys': sector_buys.get(s,0), 'kills': sector_kills.get(s,0)} for s, c in sector_counts.most_common(11)],
    'hist': hist_data,
    'scatter': scatter,
    'price_min': PRICE_MIN, 'price_max': PRICE_MAX,
    'universe': universe,
    'buys': buys_rows,
    'panels': panels,
}

HTML = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Signal Scanner · F · Distinctive</title>
<script src="https://unpkg.com/lightweight-charts@4.2.3/dist/lightweight-charts.standalone.production.js"></script>
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
  --ti:#22d3ee; --ti-bg:rgba(34,211,238,0.10);
}
*{box-sizing:border-box}
body{margin:0;background:radial-gradient(ellipse 80% 50% at top, #0c1115 0%, var(--bg) 60%);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Inter,sans-serif;padding:14px 22px 80px;min-height:100vh;line-height:1.45}
.back{color:var(--mute);font-size:0.78rem;text-decoration:none;margin-bottom:12px;display:inline-block}
.back:hover{color:var(--copper-hi)}
.wrap{max-width:1880px;margin:0 auto}
::-webkit-scrollbar{width:10px;height:10px} ::-webkit-scrollbar-track{background:var(--bg-1)}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:5px;border:2px solid var(--bg-1)}
::-webkit-scrollbar-thumb:hover{background:var(--border-hi)}

/* HEADER */
.hd{display:flex;align-items:center;justify-content:space-between;margin:4px 0 14px;padding:13px 18px;background:linear-gradient(180deg,var(--card) 0%,var(--bg-1) 100%);border:1px solid var(--border);border-radius:14px;position:relative;overflow:hidden}
.hd::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,var(--gn),var(--copper),var(--am))}
.hd-l{display:flex;align-items:center;gap:14px}
.hd-l .dot{width:9px;height:9px;border-radius:50%;background:var(--gn);animation:pulse 2.4s infinite}
@keyframes pulse{0%{box-shadow:0 0 0 0 var(--gn-glow)}70%{box-shadow:0 0 0 8px transparent}100%{box-shadow:0 0 0 0 transparent}}
.hd-l .brand{color:var(--copper);font-weight:700;font-size:0.72rem;letter-spacing:0.14em;text-transform:uppercase}
.hd-l h1{font-family:'Playfair Display',Georgia,serif;font-style:italic;font-weight:400;margin:0;font-size:1.65rem;background:linear-gradient(180deg,#fff 0%,#cbd5e1 100%);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.paper-badge{margin-left:6px;background:rgba(34,211,238,0.12);color:var(--ti);border:1px solid var(--ti);padding:4px 10px;border-radius:999px;font-size:0.66rem;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;font-family:ui-monospace,monospace;display:inline-flex;align-items:center;gap:4px;cursor:help}
.hd-stats{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.hs-cell{display:flex;align-items:center;gap:8px;padding:0 11px;border-right:1px solid var(--border-soft);height:38px}
.hs-cell:last-child{border-right:none}
.hs-lbl{font-size:0.56rem;color:var(--mute-2);text-transform:uppercase;letter-spacing:0.08em;font-weight:700;line-height:1.1}
.hs-val{font-size:1.05rem;font-weight:700;font-family:ui-monospace,monospace;color:var(--ink);line-height:1.1}
.hs-val.gn{color:var(--gn)} .hs-val.am{color:var(--am)} .hs-val.rd{color:var(--rd)}
.hs-pill{display:inline-flex;align-items:center;gap:5px;padding:4px 9px;border-radius:999px;font-size:0.66rem;font-weight:700;background:var(--am-bg);color:var(--am);border:1px solid var(--am);text-transform:uppercase}
.hs-pill.gn{background:var(--gn-bg);color:var(--gn);border-color:var(--gn)}
.hs-pill .pd{width:5px;height:5px;border-radius:50%;background:currentColor;animation:pulse 2s infinite}
.hs-bar{width:60px;height:6px;background:var(--bg-2);border-radius:3px;overflow:hidden;position:relative}
.hs-fill{height:100%;background:linear-gradient(90deg,var(--rd),var(--am),var(--gn));opacity:0.5}
.hs-marker{position:absolute;top:-2px;width:2px;height:10px;background:var(--ink)}
.hs-gauge{width:50px;height:28px}

/* ════ DECISION FUNNEL ════ */
.funnel{background:linear-gradient(180deg,var(--card) 0%,var(--bg-1) 100%);border:1px solid var(--border);border-radius:14px;padding:14px 18px;margin-bottom:14px;position:relative;overflow:hidden}
.funnel::before{content:'';position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,var(--copper-d) 50%,transparent)}
.funnel-hd{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:14px}
.funnel-ttl{font-family:'Playfair Display',Georgia,serif;font-style:italic;font-size:1.15rem;font-weight:400;color:var(--ink)}
.funnel-sub{font-size:0.7rem;color:var(--mute-2);font-family:ui-monospace,monospace}
.funnel-steps{display:flex;align-items:center;gap:0;position:relative}
.fstep{flex:1;min-width:0;background:var(--bg-1);border:1px solid var(--border);border-radius:10px;padding:12px 14px;position:relative;transition:all .2s;display:flex;flex-direction:column;gap:5px}
.fstep::after{content:'';position:absolute;top:50%;right:-13px;transform:translateY(-50%);width:0;height:0;border-left:8px solid var(--border);border-top:8px solid transparent;border-bottom:8px solid transparent;z-index:2}
.fstep:last-child::after{display:none}
.fstep:hover{border-color:var(--copper)}
.fstep.final{border-color:var(--gn);background:linear-gradient(180deg,rgba(16,185,129,0.12) 0%,var(--bg-1) 100%)}
.fstep.final::after{border-left-color:var(--gn)}
.fstep-cnt{font-family:ui-monospace,monospace;font-size:1.65rem;font-weight:800;color:var(--ink);line-height:1}
.fstep.final .fstep-cnt{color:var(--gn)}
.fstep-lbl{font-size:0.7rem;color:var(--ink-2);font-weight:700;letter-spacing:0.04em}
.fstep-det{font-size:0.62rem;color:var(--mute-2);font-family:ui-monospace,monospace}
.fstep-pct{font-size:0.62rem;color:var(--copper-hi);font-family:ui-monospace,monospace;font-weight:700;margin-left:auto}
.fstep-bar{position:absolute;bottom:0;left:0;height:3px;background:linear-gradient(90deg,var(--copper-d),var(--copper));border-radius:0 0 0 9px;transition:width .4s}
.fstep:hover .fstep-bar{background:linear-gradient(90deg,var(--copper),var(--copper-hi))}

/* ════ VIEWPORTS — Conviction Compass + Sector Orbit ════ */
.viewports{display:grid;grid-template-columns:1.6fr 1fr;gap:14px;margin-bottom:14px}
.vp-card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:14px 18px;position:relative;overflow:hidden}
.vp-card::before{content:'';position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,var(--copper-d) 50%,transparent)}
.vp-hd{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:8px}
.vp-ttl{font-size:0.85rem;font-weight:700;color:var(--ink);letter-spacing:0.02em;display:flex;align-items:baseline;gap:8px}
.vp-ttl .em{font-style:italic;font-family:'Playfair Display',Georgia,serif;font-weight:400;color:var(--copper-hi)}
.vp-sub{font-size:0.66rem;color:var(--mute-2);font-family:ui-monospace,monospace}

/* CONVICTION COMPASS */
.compass{position:relative;height:260px;background:var(--bg-1);border:1px solid var(--border-soft);border-radius:10px;overflow:hidden}
.compass-axes{position:absolute;inset:0}
.compass-quad{position:absolute;font-family:ui-monospace,monospace;font-size:0.62rem;font-weight:700;letter-spacing:0.05em;text-transform:uppercase;padding:6px 8px;opacity:0.5}
.compass-quad.sweet{top:6px;right:8px;color:var(--gn)}
.compass-quad.spec{top:6px;left:8px;color:var(--am)}
.compass-quad.tired{bottom:6px;right:8px;color:var(--bl)}
.compass-quad.junk{bottom:6px;left:8px;color:var(--rd)}
.compass-dot{position:absolute;border-radius:50%;cursor:pointer;transition:transform .15s,box-shadow .15s}
.compass-dot:hover{transform:scale(1.6);z-index:10;box-shadow:0 0 12px currentColor}
.compass-axis-lbl{position:absolute;font-size:0.6rem;color:var(--mute-2);font-family:ui-monospace,monospace;letter-spacing:0.06em;text-transform:uppercase;font-weight:600}
.compass-tooltip{position:fixed;background:#000;border:1px solid var(--copper);border-radius:6px;padding:7px 9px;font-family:ui-monospace,monospace;font-size:0.7rem;pointer-events:none;z-index:200;display:none;box-shadow:0 4px 14px rgba(0,0,0,0.6)}
.compass-tooltip b{color:var(--copper);font-size:0.8rem}
.compass-tooltip .ln{color:var(--mute)}
.compass-tooltip .ln b{color:var(--ink-2);font-size:0.7rem}

/* SECTOR ORBIT */
.orbit{position:relative;height:260px;display:flex;align-items:center;justify-content:center}
.orbit svg{display:block}
.orbit-tooltip{position:fixed;background:#000;border:1px solid var(--copper);border-radius:6px;padding:7px 9px;font-family:ui-monospace,monospace;font-size:0.7rem;pointer-events:none;z-index:200;display:none}

/* LAYOUT — full width, sidebar removed; view tabs already handle that nav */
.layout{display:block;margin-bottom:14px}

.sec-hd{display:flex;align-items:flex-end;justify-content:space-between;margin:4px 0 14px}
.sec-hd .ttl{font-family:'Playfair Display',Georgia,serif;font-style:italic;font-size:1.4rem;color:var(--ink);font-weight:400;display:flex;align-items:baseline;gap:12px}
.sec-hd .ttl .cnt{background:var(--gn-bg);color:var(--gn);border:1px solid var(--gn);padding:3px 10px;border-radius:999px;font-size:0.72rem;font-weight:700;font-style:normal;font-family:ui-monospace,monospace;letter-spacing:0.05em}
.sec-hd .meta{color:var(--mute);font-size:0.72rem}

/* ════ VIEW TABS ════ */
.view-tabs{display:flex;gap:4px;background:var(--card);border:1px solid var(--border);border-radius:10px;padding:5px;margin-bottom:14px;overflow-x:auto}
.view-tab{flex:1;min-width:fit-content;background:transparent;border:none;color:var(--mute);font-size:0.76rem;padding:8px 14px;border-radius:7px;cursor:pointer;font-family:inherit;font-weight:700;letter-spacing:0.02em;display:flex;align-items:center;gap:7px;transition:all .15s;white-space:nowrap;justify-content:center}
.view-tab:hover{color:var(--ink);background:var(--bg-2)}
.view-tab.on{background:var(--copper);color:#fff;box-shadow:0 2px 8px rgba(201,123,58,0.3)}
.view-tab .ico{font-size:1rem}
.view-tab .cnt{background:rgba(0,0,0,0.25);padding:1px 6px;border-radius:4px;font-size:0.65rem;font-family:ui-monospace,monospace;color:rgba(255,255,255,0.85);font-weight:700}
.view-tab:not(.on) .cnt{background:var(--bg-2);color:var(--mute-2)}

/* ════ UNIFORM COMPACT TILES ════ */
.bento{display:grid;grid-template-columns:repeat(auto-fill,minmax(310px,1fr));gap:12px;margin-bottom:18px}
.mc{background:linear-gradient(160deg,var(--card) 0%,var(--bg-1) 100%);border:1px solid var(--border);border-radius:12px;padding:12px;position:relative;overflow:hidden;cursor:pointer;transition:all .2s cubic-bezier(0.4,0,0.2,1);display:flex;flex-direction:column;gap:9px}
.mc::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,var(--gn) 0%,var(--copper) 60%,var(--am) 100%)}
.mc::after{content:'';position:absolute;top:-30px;right:-30px;width:120px;height:120px;background:radial-gradient(circle,var(--gn-glow) 0%,transparent 70%);opacity:0;transition:opacity .25s}
.mc:hover{transform:translateY(-2px);border-color:var(--gn);box-shadow:0 10px 28px rgba(16,185,129,0.10),0 4px 12px rgba(0,0,0,0.4)}
.mc:hover::after{opacity:1}
.mc.is-selected{border-color:var(--copper);box-shadow:0 0 0 1px var(--copper),0 8px 22px rgba(201,123,58,0.18)}
.mc.is-selected::before{height:4px;background:linear-gradient(90deg,var(--copper),var(--copper-hi),var(--gn))}

.mc-row1{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;position:relative;z-index:2}
.mc-left{display:flex;flex-direction:column;gap:2px;min-width:0;flex-grow:1}
.mc-sym{font-size:1.35rem;font-weight:800;font-family:ui-monospace,monospace;color:var(--ink);line-height:1;letter-spacing:0.01em}
.mc-name{font-size:0.58rem;color:var(--mute-2);line-height:1.2;max-width:200px;font-family:ui-monospace,monospace;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mc-livepx{display:flex;align-items:baseline;gap:6px;font-family:ui-monospace,monospace;font-size:0.7rem;color:var(--mute);margin-top:3px}
.mc-livepx b{color:var(--ink-2);font-weight:700;font-size:0.82rem}
.mc-livepx .pct{font-weight:700;padding:1px 5px;border-radius:4px;font-size:0.68rem}
.mc-livepx .pct.up{color:var(--gn);background:rgba(16,185,129,0.12)}
.mc-livepx .pct.dn{color:var(--rd);background:rgba(248,113,113,0.12)}
.mc-right{text-align:right;display:flex;flex-direction:column;align-items:flex-end;gap:3px}
.mc-score{font-size:1.55rem;font-weight:800;font-family:ui-monospace,monospace;color:var(--gn);line-height:1;text-shadow:0 0 14px var(--gn-glow)}
.mc-score-lbl{font-size:0.52rem;color:var(--mute-2);text-transform:uppercase;letter-spacing:0.1em;font-weight:700}
.mc-tier-row{display:flex;gap:4px;margin-top:3px;flex-wrap:wrap;justify-content:flex-end}
.mc-zone-badge{display:inline-block;padding:2px 7px;border-radius:5px;font-size:0.58rem;font-weight:700;letter-spacing:0.04em;font-family:ui-monospace,monospace;text-transform:uppercase}
.mc-zone-badge.in-zone{background:var(--gn);color:#000}
.mc-zone-badge.near{background:var(--am);color:#000}
.mc-zone-badge.past{background:var(--rd-bg);color:var(--rd);border:1px solid var(--rd)}

/* ════ DETAIL PANEL — appears below grid when a tile is selected ════ */
.detail-panel{background:linear-gradient(160deg,var(--card) 0%,var(--bg-1) 100%);border:1px solid var(--copper);border-radius:14px;padding:16px;margin-bottom:18px;display:none;position:relative;overflow:hidden}
.detail-panel.show{display:block;animation:slideDown .25s ease-out}
@keyframes slideDown{from{opacity:0;transform:translateY(-6px)}to{opacity:1;transform:translateY(0)}}
.detail-panel::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,var(--copper),var(--copper-hi),var(--gn))}
.dp-hd{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px}
.dp-hd-l{display:flex;align-items:baseline;gap:14px}
.dp-sym{font-family:ui-monospace,monospace;font-weight:800;font-size:1.8rem;color:var(--ink)}
.dp-meta{font-size:0.74rem;color:var(--mute);display:flex;flex-direction:column;gap:2px}
.dp-meta b{color:var(--ink-2)}
.dp-close{background:transparent;border:1px solid var(--border);color:var(--mute);font-size:1rem;padding:4px 10px;border-radius:6px;cursor:pointer;font-family:inherit}
.dp-close:hover{color:var(--rd);border-color:var(--rd)}
.dp-grid{display:grid;grid-template-columns:1.4fr 1fr;gap:14px}
@media (max-width:1000px){.dp-grid{grid-template-columns:1fr}}
.dp-chart-wrap{background:var(--bg-1);border:1px solid var(--border-soft);border-radius:10px;padding:8px;overflow:hidden}
.dp-chart{width:100%;height:300px;position:relative;overflow:hidden}
.dp-side{display:flex;flex-direction:column;gap:10px}
.dp-card-mini{background:var(--bg-1);border:1px solid var(--border-soft);border-radius:9px;padding:10px 12px}
.dp-card-mini .lbl{font-size:0.6rem;color:var(--mute-2);text-transform:uppercase;letter-spacing:0.08em;font-weight:700;margin-bottom:6px}

.chip{display:inline-block;padding:2px 7px;border-radius:5px;font-size:0.6rem;font-weight:700;letter-spacing:0.04em;background:var(--bg-2);color:var(--mute);border:1px solid var(--border);font-family:ui-monospace,monospace;text-transform:uppercase}
.chip.tier1{background:var(--gn-bg);color:var(--gn);border-color:var(--gn)}
.chip.tier2{background:var(--bl-bg);color:var(--bl);border-color:var(--bl)}
.chip.tier3{background:var(--am-bg);color:var(--am);border-color:var(--am)}
.chip.setup{background:var(--copper);color:#fff;border-color:var(--copper)}

/* Chart container — compact for uniform tiles */
.mc-chart-wrap{position:relative;background:var(--bg-1);border:1px solid var(--border-soft);border-radius:9px;padding:7px 9px;display:flex;flex-direction:column;gap:3px;overflow:hidden}
.mc-chart-hdr{display:flex;justify-content:space-between;font-family:ui-monospace,monospace;font-size:0.58rem;color:var(--mute-2);z-index:2;position:relative}
.mc-chart-hdr b{color:var(--ink-2);font-weight:700}
.mc-chart{height:78px;width:100%;display:block;position:relative;overflow:hidden;border-radius:6px}
.mc-chart svg{display:block;overflow:hidden}
.mc-vol-bars{height:18px;width:100%;display:block;margin-top:2px;overflow:hidden;border-radius:3px}
.mc-vol-bars svg{display:block;overflow:hidden}
/* TV chart wrapper */
.tv-chart{width:100%;height:100%;position:relative}
.tv-chart .tv-legend{position:absolute;top:8px;left:10px;z-index:5;font-family:ui-monospace,monospace;font-size:0.7rem;color:var(--ink);background:rgba(13,16,20,0.72);backdrop-filter:blur(8px);padding:5px 9px;border-radius:6px;border:1px solid var(--border-soft);display:flex;gap:10px}
.tv-chart .tv-legend b{color:var(--ink-2);font-weight:700}
.tv-chart .tv-legend .gn{color:var(--gn)} .tv-chart .tv-legend .rd{color:var(--rd)} .tv-chart .tv-legend .copper{color:var(--copper-hi)}

/* Radar */
.mc-side{display:grid;grid-template-columns:1fr 1.4fr;gap:8px}
.mc-radar-wrap{background:var(--bg-1);border:1px solid var(--border-soft);border-radius:9px;padding:5px;display:flex;align-items:center;justify-content:center;position:relative;min-height:78px}
.mc-radar{width:100%;height:72px}
.mc-radar-lbl{position:absolute;top:4px;left:7px;font-size:0.52rem;color:var(--mute-2);text-transform:uppercase;letter-spacing:0.08em;font-weight:700;font-family:ui-monospace,monospace}

/* Plan-summary tile (replaces in-card trade-sim; sim moved to detail panel) */
.mc-plan{background:var(--bg-1);border:1px solid var(--border-soft);border-radius:9px;padding:8px 10px;font-family:ui-monospace,monospace;display:flex;flex-direction:column;gap:4px;font-size:0.66rem;line-height:1.35}
.mc-plan-row{display:flex;justify-content:space-between}
.mc-plan-row .lbl{color:var(--mute-2);text-transform:uppercase;letter-spacing:0.06em;font-size:0.55rem;font-weight:700}
.mc-plan-row .val{font-weight:700;color:var(--ink-2)}
.mc-plan-row .val.gn{color:var(--gn)} .mc-plan-row .val.rd{color:var(--rd)} .mc-plan-row .val.cp{color:var(--copper-hi)}

/* Trade Sim (now ONLY in detail panel) */
.tsim{background:var(--bg-1);border:1px solid var(--border-soft);border-radius:9px;padding:10px 14px;font-family:ui-monospace,monospace;display:flex;flex-direction:column;gap:8px}
.tsim-hdr{display:flex;justify-content:space-between;font-size:0.58rem;color:var(--mute-2);text-transform:uppercase;letter-spacing:0.08em;font-weight:700}
.tsim-hdr b{color:var(--copper-hi);font-family:ui-monospace,monospace}
.tsim-sl{display:flex;align-items:center;gap:9px}
.tsim-sl input[type="range"]{flex-grow:1;-webkit-appearance:none;background:transparent;height:18px;cursor:pointer}
.tsim-sl input[type="range"]::-webkit-slider-runnable-track{height:4px;background:linear-gradient(90deg,var(--copper-d),var(--copper));border-radius:2px}
.tsim-sl input[type="range"]::-webkit-slider-thumb{-webkit-appearance:none;width:14px;height:14px;border-radius:50%;background:var(--ink);border:2px solid var(--copper);margin-top:-5px;box-shadow:0 0 0 1px var(--bg)}
.tsim-sl-val{font-size:0.78rem;font-weight:800;color:var(--ink);min-width:64px;text-align:right}
.tsim-row{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;font-size:0.62rem;text-align:center}
.tsim-cell{background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:5px 4px}
.tsim-cell .lbl{color:var(--mute-2);font-size:0.55rem;text-transform:uppercase;letter-spacing:0.06em;font-weight:700}
.tsim-cell .val{font-weight:800;font-size:0.85rem;font-family:ui-monospace,monospace}
.tsim-cell.win .val{color:var(--gn)}
.tsim-cell.loss .val{color:var(--rd)}

/* R:R bar */
.rrbar{display:flex;align-items:center;gap:8px;font-size:0.68rem;color:var(--mute);font-family:ui-monospace,monospace}
.rrlbl{color:var(--mute-2);font-weight:700;font-size:0.58rem;letter-spacing:0.1em;text-transform:uppercase;flex-shrink:0}
.rrtrack{flex-grow:1;height:7px;background:var(--bg-2);border-radius:4px;position:relative;overflow:hidden;display:flex;border:1px solid var(--border-soft)}
.rrtrack .risk{background:linear-gradient(90deg,#dc2626,var(--rd));height:100%}
.rrtrack .reward{background:linear-gradient(90deg,var(--gn),var(--gn-hi));height:100%}
.rrbar b{color:var(--gn);font-weight:800;flex-shrink:0;font-size:0.8rem}

.mc-narr{font-size:0.68rem;color:var(--mute);line-height:1.5;font-style:italic;padding:8px 10px;background:var(--bg-1);border-radius:7px;border-left:3px solid var(--copper)}
.mc-actions{display:flex;gap:5px;margin-top:auto}
.mc-action{flex:1;background:var(--bg-2);border:1px solid var(--border);color:var(--ink-2);font-size:0.66rem;padding:7px;border-radius:7px;font-weight:700;letter-spacing:0.04em;cursor:pointer;font-family:inherit;text-transform:uppercase}
.mc-action:hover{background:var(--copper);border-color:var(--copper);color:#fff;transform:translateY(-1px)}
.mc-action.primary{background:var(--gn);color:#000;border-color:var(--gn)}

/* SIDEBAR */
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
.sb-body{padding:10px;display:none;border-top:1px solid var(--border-soft)}
.sb-body.show{display:block}
.sb-empty{padding:18px 6px;color:var(--mute-2);font-style:italic;font-size:0.74rem;text-align:center}
/* TILES — 2-column grid */
.sb-tiles{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.sb-tile{position:relative;background:linear-gradient(160deg,var(--bg-1) 0%,var(--bg-2) 100%);border:1px solid var(--border);border-radius:9px;padding:8px 9px 7px;cursor:pointer;transition:all .15s;overflow:hidden;display:flex;flex-direction:column;gap:4px;min-height:96px}
.sb-tile::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,var(--copper-d),var(--copper));opacity:0.5;transition:opacity .15s}
.sb-tile:hover{transform:translateY(-1px);border-color:var(--copper);box-shadow:0 6px 18px rgba(0,0,0,0.4)}
.sb-tile:hover::before{opacity:1}
.sb-tile.gn::before{background:linear-gradient(90deg,#047857,var(--gn))}
.sb-tile.am::before{background:linear-gradient(90deg,#b45309,var(--am))}
.sb-tile.rd::before{background:linear-gradient(90deg,#7f1d1d,var(--rd))}
.sb-tile-row1{display:flex;align-items:baseline;justify-content:space-between;gap:6px}
.sb-tile-sym{font-family:ui-monospace,monospace;font-weight:800;font-size:0.92rem;color:var(--ink);letter-spacing:0.01em;line-height:1}
.sb-tile-val{font-family:ui-monospace,monospace;font-weight:800;font-size:0.85rem;line-height:1}
.sb-tile-val.gn{color:var(--gn)} .sb-tile-val.am{color:var(--am)} .sb-tile-val.rd{color:var(--rd)} .sb-tile-val.cp{color:var(--copper-hi)}
.sb-tile-rank{position:absolute;top:6px;right:9px;font-family:ui-monospace,monospace;font-size:0.55rem;color:var(--mute-3);font-weight:700;letter-spacing:0.04em}
.sb-tile-spark{height:24px;margin:2px 0}
.sb-tile-spark svg{display:block;overflow:hidden}
.sb-tile-meta{display:flex;flex-direction:column;gap:1px;font-family:ui-monospace,monospace;font-size:0.6rem;color:var(--mute);line-height:1.3;margin-top:auto}
.sb-tile-meta b{color:var(--ink-2);font-weight:700}
.sb-tile-chips{display:flex;gap:3px;flex-wrap:wrap;margin-top:2px}
.sb-tile-chip{display:inline-block;padding:1px 5px;border-radius:3px;font-family:ui-monospace,monospace;font-size:0.55rem;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;border:1px solid var(--border);background:var(--bg);color:var(--mute)}
.sb-tile-chip.gn{background:var(--gn-bg);color:var(--gn);border-color:rgba(16,185,129,0.4)}
.sb-tile-chip.am{background:var(--am-bg);color:var(--am);border-color:rgba(245,158,11,0.4)}
.sb-tile-chip.rd{background:var(--rd-bg);color:var(--rd);border-color:rgba(248,113,113,0.4)}
.sb-tile-chip.bl{background:var(--bl-bg);color:var(--bl);border-color:rgba(59,130,246,0.4)}
.sb-tile-chip.cp{background:rgba(201,123,58,0.12);color:var(--copper-hi);border-color:rgba(201,123,58,0.4)}

/* ════ FILTER BAR — restructured into clean groups ════ */
.filterbar-wrap{background:linear-gradient(180deg,var(--card) 0%,var(--bg-1) 100%);border:1px solid var(--border);border-radius:14px;padding:14px 16px;margin-bottom:14px;position:relative;overflow:hidden}
.filterbar-wrap::before{content:'';position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,var(--copper-d) 50%,transparent)}
.fb-hd{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:12px}
.fb-hd-ttl{font-family:'Playfair Display',Georgia,serif;font-style:italic;font-size:1.05rem;font-weight:400;color:var(--ink)}
.fb-hd-sub{font-size:0.68rem;color:var(--mute-2);font-family:ui-monospace,monospace}
.fb-hd-sub b{color:var(--copper-hi)}

/* Group containers — 4 columns now (Universe + Verdict + Entry + Zone) */
.fb-grid{display:grid;grid-template-columns:1fr 1.3fr 1.4fr 0.9fr;gap:10px;margin-bottom:10px}
@media (max-width:1400px){.fb-grid{grid-template-columns:1fr 1fr;grid-auto-rows:auto}}
@media (max-width:800px){.fb-grid{grid-template-columns:1fr}}
.fb-group{background:var(--bg-1);border:1px solid var(--border-soft);border-radius:9px;padding:9px 11px;display:flex;flex-direction:column;gap:7px}
.fb-group-hd{display:flex;align-items:center;justify-content:space-between}
.fb-group-lbl{font-size:0.6rem;color:var(--copper-hi);text-transform:uppercase;letter-spacing:0.12em;font-weight:700}
.fb-group-meta{font-size:0.62rem;color:var(--mute-2);font-family:ui-monospace,monospace}
.fb-chips{display:flex;flex-wrap:wrap;gap:5px}
.fchip{background:var(--bg-2);border:1px solid var(--border);color:var(--mute);font-size:0.7rem;padding:4px 9px;border-radius:6px;font-weight:600;cursor:pointer;font-family:inherit;display:inline-flex;align-items:center;gap:5px;transition:all .15s}
.fchip:hover{color:var(--ink);border-color:var(--border-hi)}
.fchip.on{background:var(--copper);color:#fff;border-color:var(--copper);box-shadow:0 1px 4px rgba(201,123,58,0.3)}
.fchip .cnt{background:rgba(0,0,0,0.3);padding:0 5px;border-radius:3px;font-size:0.6rem;font-family:ui-monospace,monospace;font-weight:700}
.fchip:not(.on) .cnt{background:var(--bg);color:var(--mute-2)}

/* Range row */
.fb-range-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:10px}
@media (max-width:1200px){.fb-range-grid{grid-template-columns:repeat(2,1fr)}}
@media (max-width:600px){.fb-range-grid{grid-template-columns:1fr}}
.slider-cell{display:flex;flex-direction:column;gap:6px;background:var(--bg-1);border:1px solid var(--border-soft);border-radius:9px;padding:9px 12px}
.slider-cell-hd{display:flex;justify-content:space-between;align-items:baseline}
.slider-cell .lbl{font-size:0.6rem;color:var(--copper-hi);text-transform:uppercase;letter-spacing:0.12em;font-weight:700}
.slider-cell .slider-track{position:relative;height:18px}
.slider-bg{position:absolute;top:8px;left:0;right:0;height:3px;background:var(--bg-2);border-radius:2px}
.slider-fill{position:absolute;top:8px;height:3px;background:linear-gradient(90deg,var(--copper-d),var(--copper));border-radius:2px}
.slider-handle{position:absolute;top:2px;width:14px;height:14px;border-radius:50%;background:var(--ink);border:2px solid var(--copper);box-shadow:0 0 0 1px var(--bg);cursor:grab;transform:translateX(-7px)}
.slider-val{font-family:ui-monospace,monospace;font-size:0.72rem;color:var(--ink-2);font-weight:700;text-align:right}

/* Bottom row: search + sector dropdown + reset */
.fb-actions{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.fb-search{flex-grow:1;display:flex;align-items:center;gap:6px;background:var(--bg-1);border:1px solid var(--border-soft);border-radius:9px;padding:5px 12px;min-width:240px}
.fb-search input{background:transparent;border:none;color:var(--ink);font-size:0.78rem;padding:4px 0;flex-grow:1;font-family:inherit;outline:none}
.fb-search input::placeholder{color:var(--mute-2)}
.fb-search kbd{background:var(--bg-2);border:1px solid var(--border);border-radius:4px;padding:0 5px;font-family:ui-monospace,monospace;font-size:0.62rem;color:var(--mute-2)}
.fb-reset{background:var(--bg-1);border:1px solid var(--border-soft);color:var(--mute);font-size:0.74rem;padding:7px 14px;border-radius:9px;cursor:pointer;font-family:inherit;font-weight:600;display:flex;align-items:center;gap:5px}
.fb-reset:hover{color:var(--ink);border-color:var(--rd);background:var(--rd-bg)}

.sector-dd{position:relative}
.sector-btn{background:var(--bg-1);border:1px solid var(--border-soft);color:var(--ink-2);font-size:0.74rem;padding:7px 12px;border-radius:9px;cursor:pointer;font-family:inherit;font-weight:600;display:flex;align-items:center;gap:6px}
.sector-btn.has-filter{background:var(--copper);color:#fff;border-color:var(--copper)}
.sector-menu{position:absolute;top:100%;left:0;margin-top:5px;background:var(--card);border:1px solid var(--copper);border-radius:8px;padding:6px;z-index:30;box-shadow:0 8px 24px rgba(0,0,0,0.6);display:none;min-width:220px;max-height:340px;overflow-y:auto}
.sector-menu.show{display:block}
.sector-menu label{display:flex;align-items:center;gap:7px;padding:6px 8px;font-size:0.72rem;color:var(--ink-2);cursor:pointer;border-radius:5px}
.sector-menu label:hover{background:var(--bg-2)}
.sector-menu input{accent-color:var(--copper)}
.sector-menu .cnt{margin-left:auto;font-family:ui-monospace,monospace;font-size:0.65rem;color:var(--mute)}

/* ════ TOP-5 MATCHES STRIP — live preview under filter bar ════ */
.top5-wrap{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:12px 14px;margin-bottom:14px}
.top5-hd{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:10px}
.top5-ttl{font-size:0.78rem;font-weight:700;color:var(--ink);letter-spacing:0.02em;display:flex;align-items:center;gap:8px}
.top5-ttl .pulse-dot{width:6px;height:6px;border-radius:50%;background:var(--gn);animation:pulse 2s infinite}
.top5-sub{font-size:0.66rem;color:var(--mute-2);font-family:ui-monospace,monospace}
.top5-sub b{color:var(--copper-hi)}
.top5-tiles{display:grid;grid-template-columns:repeat(5,1fr);gap:8px}
@media (max-width:1100px){.top5-tiles{grid-template-columns:repeat(3,1fr)}}
@media (max-width:700px){.top5-tiles{grid-template-columns:repeat(2,1fr)}}
.t5-tile{background:linear-gradient(160deg,var(--bg-1) 0%,var(--bg-2) 100%);border:1px solid var(--border);border-radius:9px;padding:9px 10px;cursor:pointer;transition:all .15s;display:flex;flex-direction:column;gap:5px;position:relative;overflow:hidden}
.t5-tile::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,var(--copper-d),var(--copper));opacity:0.5}
.t5-tile:hover{transform:translateY(-1px);border-color:var(--copper);box-shadow:0 6px 18px rgba(0,0,0,0.4)}
.t5-tile.gn::before{background:linear-gradient(90deg,#047857,var(--gn));opacity:1}
.t5-tile.am::before{background:linear-gradient(90deg,#b45309,var(--am));opacity:1}
.t5-tile.rd::before{background:linear-gradient(90deg,#7f1d1d,var(--rd));opacity:0.8}
.t5-tile-row1{display:flex;justify-content:space-between;align-items:baseline}
.t5-tile-sym{font-family:ui-monospace,monospace;font-weight:800;font-size:0.92rem;color:var(--ink);letter-spacing:0.01em}
.t5-tile-score{font-family:ui-monospace,monospace;font-weight:800;font-size:0.92rem}
.t5-tile-score.gn{color:var(--gn)}
.t5-tile-score.am{color:var(--am)}
.t5-tile-score.mute{color:var(--mute)}
.t5-tile-spark{height:22px;width:100%}
.t5-tile-spark svg{display:block;overflow:hidden}
.t5-tile-row2{display:flex;justify-content:space-between;align-items:center;font-family:ui-monospace,monospace;font-size:0.6rem;color:var(--mute);gap:5px}
.t5-tile-row2 b{color:var(--ink-2);font-weight:700}
.t5-tile-row2 .vchip{font-size:0.55rem;padding:1px 5px;border-radius:3px;font-weight:700;letter-spacing:0.04em}
.t5-tile-row2 .vchip.BUY{background:var(--gn-bg);color:var(--gn);border:1px solid var(--gn)}
.t5-tile-row2 .vchip.WATCH{background:var(--am-bg);color:var(--am);border:1px solid var(--am)}
.t5-tile-row2 .vchip.WAIT{background:var(--bg-2);color:var(--mute);border:1px solid var(--border)}
.t5-tile-row2 .vchip.AVOID{background:var(--rd-bg);color:var(--rd);border:1px solid var(--rd)}
.t5-empty{grid-column:1/-1;padding:24px;text-align:center;color:var(--mute-2);font-style:italic;font-size:0.78rem}

/* TABLE */
.table-wrap{background:var(--card);border:1px solid var(--border);border-radius:12px;overflow:hidden}
.tb-hd{padding:12px 16px;border-bottom:1px solid var(--border-soft);display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap}
.tb-title{font-family:'Playfair Display',Georgia,serif;font-style:italic;font-size:1.05rem}
.tb-meta{font-size:0.7rem;color:var(--mute);font-family:ui-monospace,monospace}
.tb-meta b{color:var(--copper-hi)}
.tb-actions{display:flex;gap:6px}
.tb-action{background:var(--bg-1);border:1px solid var(--border);color:var(--ink-2);font-size:0.7rem;padding:5px 10px;border-radius:6px;cursor:pointer;font-family:inherit;font-weight:600}
.tb-action:hover{border-color:var(--copper);color:#fff}
.tb-scroll{max-height:560px;overflow:auto}
table{width:100%;border-collapse:collapse;font-size:0.74rem;font-family:ui-monospace,monospace;min-width:1700px}
.wr-cell{display:inline-flex;align-items:baseline;gap:6px;font-family:ui-monospace,monospace}
.wr-cell .wr-val{font-weight:700;font-size:0.78rem}
.wr-cell .wr-lb{color:var(--mute-2);font-size:0.62rem}
.wr-cell .wr-n{background:var(--bg-2);padding:1px 5px;border-radius:3px;font-size:0.6rem;font-weight:700;color:var(--ink-2)}
.wr-cell.gn .wr-val{color:var(--gn)} .wr-cell.am .wr-val{color:var(--am)} .wr-cell.rd .wr-val{color:var(--rd)}
.mech-cell{color:var(--ink-2);font-style:italic;font-size:0.7rem;max-width:230px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;display:inline-block}
.stop-t1-cell{display:flex;flex-direction:column;gap:1px;font-family:ui-monospace,monospace;line-height:1.2}
.stop-t1-cell .stop{color:var(--rd);font-size:0.66rem;font-weight:700}
.stop-t1-cell .t1{color:var(--gn);font-size:0.66rem;font-weight:700}
.tbl-actions{display:flex;gap:4px;justify-content:center}
.tbl-action{background:var(--bg-2);border:1px solid var(--border);color:var(--ink-2);font-size:0.78rem;width:28px;height:24px;border-radius:5px;cursor:pointer;font-family:inherit;display:inline-flex;align-items:center;justify-content:center;transition:all .12s}
.tbl-action:hover{transform:translateY(-1px)}
.tbl-action.buy{background:var(--gn-bg);border-color:var(--gn);color:var(--gn)}
.tbl-action.buy:hover{background:var(--gn);color:#000}
.tbl-action.track{background:var(--am-bg);border-color:var(--am);color:var(--am)}
.tbl-action.track:hover{background:var(--am);color:#000}
thead{position:sticky;top:0;background:var(--bg-2);z-index:2}
th{padding:9px 10px;text-align:left;font-weight:700;color:var(--mute-2);text-transform:uppercase;letter-spacing:0.06em;font-size:0.6rem;border-bottom:1px solid var(--border);white-space:nowrap;cursor:pointer;user-select:none}
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

/* TICKER TAPE */
.tape{position:fixed;bottom:0;left:0;right:0;background:linear-gradient(180deg,rgba(8,9,12,0.85) 0%,#08090c 100%);backdrop-filter:blur(12px);border-top:1px solid var(--border);height:38px;overflow:hidden;z-index:50;display:flex;align-items:center;padding:0 14px;gap:14px}
.tape-lbl{flex-shrink:0;color:var(--gn);font-size:0.72rem;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;display:flex;align-items:center;gap:6px}
.tape-lbl::before{content:'';width:6px;height:6px;border-radius:50%;background:var(--gn);animation:pulse 2s infinite}
.tape-track{flex-grow:1;overflow:hidden;position:relative}
.tape-strip{display:inline-flex;gap:36px;animation:tape-scroll 36s linear infinite;font-family:ui-monospace,monospace;font-size:0.85rem;white-space:nowrap;padding-left:14px}
@keyframes tape-scroll{0%{transform:translateX(0)}100%{transform:translateX(-50%)}}
.tape-tk{display:inline-flex;align-items:center;gap:6px}
.tape-tk b{color:var(--ink);font-weight:700;letter-spacing:0.02em}
.tape-tk .pct{font-weight:700}
.tape-tk .pct.up{color:var(--gn)}
.tape-tk .pct.dn{color:var(--rd)}
.tape-tk .px{color:var(--mute);font-size:0.78rem}

.legend{margin-top:18px;text-align:center;color:var(--mute-2);font-size:0.72rem;padding-top:14px;border-top:1px dashed var(--border-soft)}
</style>
</head>
<body>
<div class="wrap">
<a class="back" href="scanner_v2_index.html">← back to options</a>

<!-- HEADER -->
<div class="hd">
  <div class="hd-l">
    <span class="dot"></span>
    <span class="brand">KAIROS · LIVE</span>
    <h1>Signal Scanner</h1>
    <span class="paper-badge" title="No live orders — every action is a simulated paper trade">🔬 PAPER MODE</span>
  </div>
  <div class="hd-stats" id="hd-stats"></div>
</div>

<!-- ════ DECISION FUNNEL ════ -->
<div class="funnel">
  <div class="funnel-hd">
    <div class="funnel-ttl">Decision Funnel <span style="color:var(--copper-hi);font-style:normal;font-family:ui-monospace,monospace;font-size:0.72rem;margin-left:6px">how the universe narrowed to BUYs</span></div>
    <div class="funnel-sub">click step → drill into table</div>
  </div>
  <div class="funnel-steps" id="funnel-steps"></div>
</div>


<!-- MAIN — full width grid, sidebar removed -->
<div class="layout">
  <div class="sec-hd">
    <div class="ttl" id="bento-ttl">Today's Top Picks <span class="cnt" id="buy-cnt"></span></div>
    <div class="meta" id="bento-meta">click any tile → expand detail panel · tabs swap the view · all actions are simulated</div>
  </div>

  <!-- VIEW TABS -->
  <div class="view-tabs" id="view-tabs">
    <button class="view-tab on" data-view="buys"><span class="ico">⭐</span>Picks <span class="cnt" id="vt-buys">0</span></button>
    <button class="view-tab" data-view="fresh"><span class="ico">⚡</span>Fresh <span class="cnt" id="vt-fresh">0</span></button>
    <button class="view-tab" data-view="earnings"><span class="ico">📅</span>Earnings <span class="cnt" id="vt-earnings">0</span></button>
    <button class="view-tab" data-view="surges"><span class="ico">🔥</span>Surges <span class="cnt" id="vt-surges">0</span></button>
    <button class="view-tab" data-view="ai"><span class="ico">✦</span>AI Edge <span class="cnt" id="vt-ai">0</span></button>
    <button class="view-tab" data-view="momentum"><span class="ico">🚀</span>Momentum <span class="cnt" id="vt-momentum">0</span></button>
  </div>

  <!-- DETAIL PANEL — shows TV chart + Trade Sim for selected tile -->
  <div class="detail-panel" id="detail-panel">
    <div class="dp-hd">
      <div class="dp-hd-l">
        <span class="dp-sym" id="dp-sym">—</span>
        <div class="dp-meta" id="dp-meta"></div>
      </div>
      <button class="dp-close" id="dp-close">✕ close</button>
    </div>
    <div class="dp-grid">
      <div class="dp-chart-wrap">
        <div class="dp-chart" id="dp-chart"></div>
      </div>
      <div class="dp-side" id="dp-side"></div>
    </div>
  </div>

  <div class="bento" id="bento"></div>
</div>

<!-- FILTER BAR — restructured into clean grouped sections -->
<div class="filterbar-wrap">
  <div class="fb-hd">
    <div class="fb-hd-ttl">Filter the universe</div>
    <div class="fb-hd-sub">live filtering · <b id="fb-active-count">0</b> active filters · top 5 matches preview below</div>
  </div>

  <!-- Row 1: categorical filters in 4 grouped cards -->
  <div class="fb-grid">

    <div class="fb-group">
      <div class="fb-group-hd">
        <span class="fb-group-lbl">Universe</span>
        <span class="fb-group-meta">cap segmentation</span>
      </div>
      <div class="fb-chips">
        <div class="fchip on" data-fg="universe" data-fv="all">All <span class="cnt" id="cnt-univ-all"></span></div>
        <div class="fchip" data-fg="universe" data-fv="core" title="SP500 + Russell 1000 — large-cap mainstream universe">CORE <span class="cnt" id="cnt-core"></span></div>
        <div class="fchip" data-fg="universe" data-fv="alpha" title="R2000 + SML600 + MID400 + IPO + Crypto-adj + Momentum-screened — higher-beta universe">ALPHA <span class="cnt" id="cnt-alpha"></span></div>
      </div>
    </div>

    <div class="fb-group">
      <div class="fb-group-hd">
        <span class="fb-group-lbl">Verdict</span>
        <span class="fb-group-meta">636 total</span>
      </div>
      <div class="fb-chips">
        <div class="fchip on" data-fg="verdict" data-fv="all">All <span class="cnt" id="cnt-all"></span></div>
        <div class="fchip" data-fg="verdict" data-fv="BUY" title="Strong bullish technical setup">BULLISH <span class="cnt" id="cnt-buy"></span></div>
        <div class="fchip" data-fg="verdict" data-fv="WATCH" title="On the radar · monitor">WATCH <span class="cnt" id="cnt-watch"></span></div>
        <div class="fchip" data-fg="verdict" data-fv="WAIT" title="Conditions not yet met">NEUTRAL <span class="cnt" id="cnt-neut"></span></div>
        <div class="fchip" data-fg="verdict" data-fv="AVOID" title="Setup invalidated · stay clear">AVOID <span class="cnt" id="cnt-kill"></span></div>
      </div>
    </div>

    <div class="fb-group">
      <div class="fb-group-hd">
        <span class="fb-group-lbl">Entry Quality</span>
        <span class="fb-group-meta">closeness to pivot</span>
      </div>
      <div class="fb-chips">
        <div class="fchip on" data-fg="eq" data-fv="all">All</div>
        <div class="fchip" data-fg="eq" data-fv="FRESH">⚡ FRESH</div>
        <div class="fchip" data-fg="eq" data-fv="PULLBACK">↘ PULLBACK</div>
        <div class="fchip" data-fg="eq" data-fv="VALID">↗ VALID</div>
        <div class="fchip" data-fg="eq" data-fv="EXTENDED">↑ EXTENDED</div>
        <div class="fchip" data-fg="eq" data-fv="MISSED">✕ MISSED</div>
      </div>
    </div>

    <div class="fb-group">
      <div class="fb-group-hd">
        <span class="fb-group-lbl">Zone State</span>
        <span class="fb-group-meta">price vs entry zone</span>
      </div>
      <div class="fb-chips">
        <div class="fchip on" data-fg="zone" data-fv="all">All</div>
        <div class="fchip" data-fg="zone" data-fv="IN ZONE">● IN ZONE</div>
        <div class="fchip" data-fg="zone" data-fv="NEAR">○ NEAR</div>
        <div class="fchip" data-fg="zone" data-fv="PAST">⊘ PAST</div>
      </div>
    </div>
  </div>

  <!-- Row 2: range sliders -->
  <div class="fb-range-grid">
    <div class="slider-cell">
      <div class="slider-cell-hd"><span class="lbl">Price $</span><span class="slider-val" id="val-price">—</span></div>
      <div class="slider-track" data-slider="price">
        <div class="slider-bg"></div><div class="slider-fill"></div>
        <div class="slider-handle" data-h="lo"></div><div class="slider-handle" data-h="hi"></div>
      </div>
    </div>
    <div class="slider-cell">
      <div class="slider-cell-hd"><span class="lbl">Composite Score</span><span class="slider-val" id="val-score">0–100</span></div>
      <div class="slider-track" data-slider="score">
        <div class="slider-bg"></div><div class="slider-fill"></div>
        <div class="slider-handle" data-h="lo"></div><div class="slider-handle" data-h="hi"></div>
      </div>
    </div>
    <div class="slider-cell">
      <div class="slider-cell-hd"><span class="lbl">R:R Ratio</span><span class="slider-val" id="val-rr">0–10</span></div>
      <div class="slider-track" data-slider="rr">
        <div class="slider-bg"></div><div class="slider-fill"></div>
        <div class="slider-handle" data-h="lo"></div><div class="slider-handle" data-h="hi"></div>
      </div>
    </div>
    <div class="slider-cell" style="justify-content:center">
      <div class="slider-cell-hd"><span class="lbl">Sector</span><span class="slider-val" id="sector-summary">(all)</span></div>
      <div class="sector-dd">
        <button class="sector-btn" id="sector-btn" style="width:100%;justify-content:center">📂 Choose sectors ▾</button>
        <div class="sector-menu" id="sector-menu"></div>
      </div>
    </div>
  </div>

  <!-- Row 3: search + reset -->
  <div class="fb-actions">
    <div class="fb-search">
      <span style="color:var(--mute-2);font-size:0.9rem">🔍</span>
      <input type="text" id="search" placeholder="search ticker or name">
      <kbd>/</kbd>
    </div>
    <button class="fb-reset" id="reset-btn">⟲ Reset filters</button>
  </div>
</div>


<!-- TABLE -->
<div class="table-wrap">
  <div class="tb-hd">
    <div class="tb-title">Full Universe</div>
    <div class="tb-meta">showing <b id="tb-count">0</b> of <b id="tb-total">0</b> · click header to sort</div>
    <div class="tb-actions">
      <button class="tb-action" id="csv-btn">📥 CSV</button>
    </div>
  </div>
  <div class="tb-scroll">
    <table id="universe-table">
      <thead><tr>
        <th class="num" style="width:32px">#</th>
        <th data-k="rank_delta" class="num" style="width:38px">Δ</th>
        <th data-k="sym">SYM</th>
        <th data-k="setup">SETUP</th>
        <th data-k="verdict">VERDICT</th>
        <th data-k="tier">TIER</th>
        <th data-k="score" class="num sorted desc">SCORE</th>
        <th data-k="tfsn_sum">T·F·S·N</th>
        <th data-k="price" class="num">CURR $</th>
        <th data-k="entry_quality_ord">ENTRY</th>
        <th data-k="star" class="num">★</th>
        <th data-k="pct_change_1d" class="num">Δ%</th>
        <th data-k="rs" class="num">RS</th>
        <th data-k="rvol" class="num">RVOL</th>
        <th data-k="rr" class="num">R:R</th>
        <th data-k="cat_tier" class="num">CAT</th>
        <th data-k="entry_quality">ENTRY Q</th>
        <th data-k="sector">SECTOR</th>
        <th data-k="src">SRC</th>
        <th data-k="wr_lb" class="num" title="Wilson 95% lower bound · sample size">WR (LB · N)</th>
        <th data-k="mechanism">MECHANISM</th>
        <th data-k="t1" class="num">STOP / T1</th>
        <th style="text-align:center;width:84px">🛒 / TRACK</th>
      </tr></thead>
      <tbody id="tb-body"></tbody>
    </table>
  </div>
</div>

<div class="legend">v2-F · Unique · Decision Funnel · Conviction Compass · Bento · Trade Sim · Sector Orbit · Ticker Tape</div>
</div>

<!-- TICKER TAPE -->
<div class="tape" id="tape">
  <div class="tape-lbl">● TOP PICKS LIVE</div>
  <div class="tape-track"><div class="tape-strip" id="tape-strip"></div></div>
</div>

<!-- Tooltips -->
<div class="compass-tooltip" id="ctip"></div>
<div class="orbit-tooltip" id="otip"></div>

<script id="data-payload" type="application/json">__PAYLOAD__</script>
<script>
const DATA = JSON.parse(document.getElementById('data-payload').textContent);
const STATE = {
  view:'buys',
  verdict:'all', eq:'all', zone:null, sectors:new Set(), search:'',
  universe:'all',  // 'all' | 'core' | 'alpha'
  priceLo:DATA.price_min, priceHi:DATA.price_max,
  scoreLo:0, scoreHi:100, rrLo:0, rrHi:10,
  sortKey:'score', sortDir:'desc',
};
const CORE_SRCS  = new Set(DATA.core_srcs  || []);
const ALPHA_SRCS = new Set(DATA.alpha_srcs || []);
// SEC-safe display labels — code/data still uses BUY/WATCH/WAIT/AVOID for filtering
const VERDICT_LABEL = { 'BUY':'BULLISH', 'WATCH':'WATCH', 'WAIT':'NEUTRAL', 'AVOID':'AVOID', 'SHORT':'BEARISH' };

// ─── HEADER ──────────────────────────────────────────────────────
function renderPulse() {
  const p = DATA.pulse, c = DATA.counts;
  const rc = p.regime4.includes('panic')||p.regime4.includes('risk_off') ? 'rd' : p.regime4.includes('choppy') ? 'am' : 'gn';
  const vixPct = Math.min(Math.max((p.vix-10)/40, 0), 1);
  const a = 180 + vixPct*180;
  const nx = 50 + 25*Math.cos(a*Math.PI/180), ny = 45 + 25*Math.sin(a*Math.PI/180);
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
      <div><div class="hs-lbl">Breadth</div><div class="hs-val">${(p.breadth||0).toFixed(0)}%</div></div>
      <div class="hs-bar"><div class="hs-fill" style="width:100%"></div><div class="hs-marker" style="left:${p.breadth}%"></div></div>
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
  // Universe chips
  const cua = document.getElementById('cnt-univ-all');
  if (cua) cua.textContent = (c.core || 0) + (c.alpha || 0);
  const ccx = document.getElementById('cnt-core');
  if (ccx) ccx.textContent = c.core || 0;
  const cax = document.getElementById('cnt-alpha');
  if (cax) cax.textContent = c.alpha || 0;
}

// ─── DECISION FUNNEL ─────────────────────────────────────────────
function renderFunnel() {
  const max = DATA.funnel[0].value;
  const html = DATA.funnel.map((s, i) => {
    const pct = max ? (s.value / max * 100) : 0;
    const isFinal = i === DATA.funnel.length - 1;
    const prevValue = i > 0 ? DATA.funnel[i-1].value : null;
    const dropPct = prevValue ? ((prevValue - s.value) / prevValue * 100).toFixed(0) : null;
    const dropTxt = dropPct ? `<span class="fstep-pct">-${dropPct}%</span>` : '';
    return `<div class="fstep ${isFinal?'final':''}">
      <div style="display:flex;align-items:baseline;justify-content:space-between">
        <span class="fstep-lbl">${s.label}</span>${dropTxt}
      </div>
      <span class="fstep-cnt">${s.value.toLocaleString()}</span>
      <span class="fstep-det">${s.detail}</span>
      <span class="fstep-bar" style="width:${pct}%"></span>
    </div>`;
  }).join('');
  document.getElementById('funnel-steps').innerHTML = html;
}

// ─── CONVICTION COMPASS ──────────────────────────────────────────
function renderCompass() {
  const compass = document.getElementById('compass');
  const W = compass.clientWidth || 640, H = compass.clientHeight || 260;
  // Score range 30–100 (we filtered), R:R range 0–6
  const scoreMin = 30, scoreMax = 100;
  const rrMin = 0, rrMax = 6;
  // axis lines via SVG overlay
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.setAttribute('preserveAspectRatio', 'none');
  svg.style.position = 'absolute'; svg.style.inset = '0'; svg.style.pointerEvents = 'none';
  svg.innerHTML = `
    <line x1="${W/2}" y1="0" x2="${W/2}" y2="${H}" stroke="#1f2937" stroke-width="1" stroke-dasharray="3 3"/>
    <line x1="0" y1="${H/2}" x2="${W}" y2="${H/2}" stroke="#1f2937" stroke-width="1" stroke-dasharray="3 3"/>
    <text x="${W*0.85}" y="${H/2 - 6}" font-size="9" fill="#374151" font-family="ui-monospace,monospace">R:R = 3</text>
    <text x="${W/2 + 6}" y="${H*0.93}" font-size="9" fill="#374151" font-family="ui-monospace,monospace">Score = 65</text>
  `;
  compass.appendChild(svg);
  // Plot all points
  DATA.scatter.forEach(p => {
    const sx = ((p.score - scoreMin) / (scoreMax - scoreMin)) * (W - 30) + 15;
    const sy = H - (((Math.min(p.rr, rrMax) - rrMin) / (rrMax - rrMin)) * (H - 30) + 15);
    const v = (p.verdict || '').toUpperCase();
    const color = v === 'BUY' ? '#10b981' : v === 'WATCH' ? '#f59e0b' : v === 'AVOID' ? '#f87171' : '#4b5563';
    const size = v === 'BUY' ? 8 : v === 'WATCH' ? 5 : 3;
    const op   = v === 'BUY' ? 1 : v === 'WATCH' ? 0.7 : 0.35;
    const dot = document.createElement('div');
    dot.className = 'compass-dot';
    dot.style.left = `${sx - size/2}px`;
    dot.style.top  = `${sy - size/2}px`;
    dot.style.width = `${size}px`;
    dot.style.height = `${size}px`;
    dot.style.background = color;
    dot.style.color = color;
    dot.style.opacity = op;
    dot.dataset.sym = p.sym;
    dot.dataset.score = p.score;
    dot.dataset.rr = p.rr;
    dot.dataset.v = p.verdict;
    dot.dataset.sector = p.sector;
    compass.appendChild(dot);
  });
  // Tooltip
  const tip = document.getElementById('ctip');
  compass.addEventListener('mouseover', e => {
    if (!e.target.classList.contains('compass-dot')) return;
    const d = e.target.dataset;
    tip.innerHTML = `<b>${d.sym}</b><br/>
      <span class="ln">Score <b>${d.score}</b> · R:R <b>${parseFloat(d.rr).toFixed(1)}</b></span><br/>
      <span class="ln">${d.sector} · ${d.v}</span>`;
    tip.style.display = 'block';
  });
  compass.addEventListener('mousemove', e => {
    tip.style.left = (e.clientX + 12) + 'px';
    tip.style.top  = (e.clientY + 12) + 'px';
  });
  compass.addEventListener('mouseleave', () => tip.style.display = 'none');
}

// ─── SECTOR ORBIT ────────────────────────────────────────────────
function renderOrbit() {
  const orbit = document.getElementById('orbit');
  const W = 320, H = 260, cx = W/2, cy = H/2;
  const sectors = DATA.sector_data;
  const maxCount = Math.max(...sectors.map(s => s.count)) || 1;
  const angleStep = (2 * Math.PI) / sectors.length;
  let svgHtml = `<svg viewBox="0 0 ${W} ${H}" width="100%" height="100%">`;
  // Center
  svgHtml += `<circle cx="${cx}" cy="${cy}" r="22" fill="#1f2937" stroke="#c97b3a" stroke-width="1.5"/>`;
  svgHtml += `<text x="${cx}" y="${cy - 2}" text-anchor="middle" font-size="10" fill="#e09850" font-weight="700" font-family="ui-monospace,monospace">228</text>`;
  svgHtml += `<text x="${cx}" y="${cy + 9}" text-anchor="middle" font-size="7" fill="#6b7280" font-family="ui-monospace,monospace">UNIVERSE</text>`;
  // Orbital rings
  [60, 90, 115].forEach(r => {
    svgHtml += `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="#1f2937" stroke-width="0.6" stroke-dasharray="2 3"/>`;
  });
  // Sector blobs
  sectors.forEach((s, i) => {
    const angle = -Math.PI/2 + i * angleStep;
    const dist = 60 + (s.count / maxCount) * 55;
    const x = cx + dist * Math.cos(angle);
    const y = cy + dist * Math.sin(angle);
    const buyPct = s.count ? (s.buys / s.count) : 0;
    const killPct = s.count ? (s.kills / s.count) : 0;
    let color = '#374151';
    if (buyPct > 0.05) color = '#10b981';
    else if (killPct > 0.5) color = '#f87171';
    else if (killPct > 0.3) color = '#b45309';
    const r = 8 + Math.sqrt(s.count) * 1.2;
    // line from center
    svgHtml += `<line x1="${cx}" y1="${cy}" x2="${x}" y2="${y}" stroke="${color}" stroke-width="0.6" opacity="0.35"/>`;
    // blob
    svgHtml += `<circle cx="${x}" cy="${y}" r="${r}" fill="${color}" fill-opacity="0.25" stroke="${color}" stroke-width="1.5" class="orb-blob"
                data-name="${s.name}" data-count="${s.count}" data-buys="${s.buys}" data-kills="${s.kills}" style="cursor:pointer"/>`;
    svgHtml += `<text x="${x}" y="${y - r - 3}" text-anchor="middle" font-size="7" fill="#9ca3af" font-family="ui-monospace,monospace" font-weight="700">${s.name.slice(0, 7)}</text>`;
    svgHtml += `<text x="${x}" y="${y + 3}" text-anchor="middle" font-size="8" fill="#fff" font-family="ui-monospace,monospace" font-weight="700">${s.count}</text>`;
    if (s.buys > 0) {
      svgHtml += `<text x="${x}" y="${y + r + 9}" text-anchor="middle" font-size="6" fill="#10b981" font-family="ui-monospace,monospace" font-weight="700">+${s.buys} BUY</text>`;
    }
  });
  svgHtml += `</svg>`;
  orbit.innerHTML = svgHtml;
  // tooltip
  const otip = document.getElementById('otip');
  orbit.querySelectorAll('.orb-blob').forEach(b => {
    b.addEventListener('mouseover', e => {
      const d = b.dataset;
      otip.innerHTML = `<b style="color:var(--copper)">${d.name}</b><br/>
        <span style="color:var(--mute)">Total <b style="color:var(--ink-2)">${d.count}</b></span><br/>
        <span style="color:var(--gn)">BUY <b>${d.buys}</b></span> · <span style="color:var(--rd)">AVOID <b>${d.kills}</b></span>`;
      otip.style.display = 'block';
    });
    b.addEventListener('mousemove', e => {
      otip.style.left = (e.clientX + 12) + 'px';
      otip.style.top  = (e.clientY + 12) + 'px';
    });
    b.addEventListener('mouseleave', () => otip.style.display = 'none');
    b.addEventListener('click', () => {
      STATE.sectors.clear();
      STATE.sectors.add(b.dataset.name);
      syncSectorMenu();
      applyFilters();
    });
  });
}

// ─── TradingView Lightweight Charts — FEATURED card ──────────────
const _tvCharts = new Map();
function mountTVChart(containerId, b) {
  if (typeof LightweightCharts === 'undefined') {
    document.getElementById(containerId).innerHTML = '<div style="padding:60px;text-align:center;color:var(--mute-2);font-style:italic">TradingView library failed to load · check network</div>';
    return;
  }
  const container = document.getElementById(containerId);
  if (!container) return;
  if (_tvCharts.has(containerId)) {
    try { _tvCharts.get(containerId).remove(); } catch(_) {}
  }
  container.innerHTML = '';
  const chart = LightweightCharts.createChart(container, {
    width: container.clientWidth,
    height: container.clientHeight,
    layout: {
      background: { type: 'solid', color: 'transparent' },
      textColor: '#9ca3af',
      fontFamily: 'ui-monospace, monospace',
      fontSize: 10,
    },
    grid: {
      vertLines: { color: 'rgba(31,41,55,0.4)', style: 1 },
      horzLines: { color: 'rgba(31,41,55,0.4)', style: 1 },
    },
    rightPriceScale: {
      borderColor: 'rgba(31,41,55,0.6)',
      scaleMargins: { top: 0.1, bottom: 0.25 },
    },
    timeScale: {
      borderColor: 'rgba(31,41,55,0.6)',
      timeVisible: false,
      secondsVisible: false,
      barSpacing: 8,
    },
    crosshair: {
      mode: LightweightCharts.CrosshairMode.Normal,
      vertLine: { color: '#c97b3a', width: 1, style: 2, labelBackgroundColor: '#c97b3a' },
      horzLine: { color: '#c97b3a', width: 1, style: 2, labelBackgroundColor: '#c97b3a' },
    },
    handleScroll: false,
    handleScale: false,
  });
  // Candlestick series
  const candles = chart.addCandlestickSeries({
    upColor: '#10b981', downColor: '#f87171',
    borderUpColor: '#10b981', borderDownColor: '#f87171',
    wickUpColor: '#10b981', wickDownColor: '#f87171',
    priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
  });
  candles.setData(b.bars || []);
  // Volume series on a separate price scale
  const volSeries = chart.addHistogramSeries({
    priceFormat: { type: 'volume' },
    priceScaleId: '',
    color: 'rgba(201,123,58,0.45)',
  });
  volSeries.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
  volSeries.setData((b.bars || []).map(bar => ({
    time: bar.time,
    value: bar.volume,
    color: bar.close >= bar.open ? 'rgba(16,185,129,0.45)' : 'rgba(248,113,113,0.45)',
  })));
  // Price lines for STOP / ENTRY / T1
  if (b.stop) candles.createPriceLine({ price: b.stop,  color: '#f87171', lineWidth: 2, lineStyle: 2, axisLabelVisible: true, title: '✕ STOP' });
  const entry = b.entry_mid || b.entry_low;
  if (entry)  candles.createPriceLine({ price: entry, color: '#e09850', lineWidth: 2, lineStyle: 2, axisLabelVisible: true, title: '→ ENTRY' });
  if (b.t1)   candles.createPriceLine({ price: b.t1,   color: '#10b981', lineWidth: 2, lineStyle: 2, axisLabelVisible: true, title: '★ T1' });
  if (b.t2)   candles.createPriceLine({ price: b.t2,   color: '#34d399', lineWidth: 1, lineStyle: 3, axisLabelVisible: false, title: 'T2' });
  chart.timeScale().fitContent();
  _tvCharts.set(containerId, chart);
  // Responsive: refit on window resize
  const ro = new ResizeObserver(() => {
    chart.applyOptions({ width: container.clientWidth, height: container.clientHeight });
  });
  ro.observe(container);
}

// ─── Simple sparkline for non-featured cards (FIXED) ─────────────
function sparkAnnoSvg(closes, stop, entry, t1, w, h) {
  if (!closes || closes.length < 2) return `<svg width="${w}" height="${h}"></svg>`;
  const allVals = [...closes];
  if (stop) allVals.push(stop);
  if (entry) allVals.push(entry);
  if (t1) allVals.push(t1);
  const min = Math.min(...allVals), max = Math.max(...allVals), range = max - min || 1;
  const pad = 4;
  const y = v => h - pad - ((v - min)/range) * (h - 2*pad);
  const pts = closes.map((v, i) => [pad + (i/(closes.length-1))*(w-2*pad), y(v)]);
  const polyStr = pts.map(p => p.map(n => n.toFixed(1)).join(',')).join(' ');
  const trend = closes[closes.length-1] > closes[0] ? 'up' : 'down';
  const stroke = trend === 'up' ? '#10b981' : '#f87171';
  const fill = trend === 'up' ? 'rgba(16,185,129,0.15)' : 'rgba(248,113,113,0.15)';
  const area = `${pad},${h-pad} ${polyStr} ${w-pad},${h-pad}`;
  const [lx, ly] = pts[pts.length-1];
  let markers = '';
  if (stop) {
    const sy = y(stop);
    markers += `<line x1="${pad}" y1="${sy.toFixed(1)}" x2="${w-pad}" y2="${sy.toFixed(1)}" stroke="#f87171" stroke-width="1" stroke-dasharray="3 3" opacity="0.65"/>
                <text x="${w-pad-3}" y="${(sy-2).toFixed(1)}" text-anchor="end" font-size="7" fill="#f87171" font-family="ui-monospace,monospace" font-weight="700">STOP $${stop.toFixed(2)}</text>`;
  }
  if (entry) {
    const ey = y(entry);
    markers += `<line x1="${pad}" y1="${ey.toFixed(1)}" x2="${w-pad}" y2="${ey.toFixed(1)}" stroke="#c97b3a" stroke-width="1" stroke-dasharray="3 3" opacity="0.65"/>
                <text x="${w-pad-3}" y="${(ey-2).toFixed(1)}" text-anchor="end" font-size="7" fill="#e09850" font-family="ui-monospace,monospace" font-weight="700">ENTRY $${entry.toFixed(2)}</text>`;
  }
  if (t1) {
    const ty = y(t1);
    markers += `<line x1="${pad}" y1="${ty.toFixed(1)}" x2="${w-pad}" y2="${ty.toFixed(1)}" stroke="#10b981" stroke-width="1" stroke-dasharray="3 3" opacity="0.65"/>
                <text x="${w-pad-3}" y="${(ty-2).toFixed(1)}" text-anchor="end" font-size="7" fill="#10b981" font-family="ui-monospace,monospace" font-weight="700">T1 $${t1.toFixed(2)}</text>`;
  }
  return `<svg width="100%" height="${h}" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" style="display:block;overflow:hidden">
    <polyline points="${area}" fill="${fill}" stroke="none"/>
    ${markers}
    <polyline points="${polyStr}" fill="none" stroke="${stroke}" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="${lx.toFixed(1)}" cy="${ly.toFixed(1)}" r="3" fill="#fff" stroke="${stroke}" stroke-width="1.5"/>
  </svg>`;
}
function volBarsSvg(volumes, w, h) {
  if (!volumes || volumes.length < 2) return `<svg width="${w}" height="${h}"></svg>`;
  const max = Math.max(...volumes) || 1;
  const bw = (w - 4) / volumes.length;
  return `<svg width="100%" height="${h}" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" style="display:block;overflow:hidden">${volumes.map((v, i) => {
    const bh = (v / max) * (h - 2);
    return `<rect x="${(2 + i*bw).toFixed(1)}" y="${(h-bh).toFixed(1)}" width="${(bw*0.7).toFixed(1)}" height="${bh.toFixed(1)}" fill="rgba(201,123,58,0.5)" rx="0.5"/>`;
  }).join('')}</svg>`;
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

// ─── VIEW SWITCHING — uniform tiles, sidebar+tabs swap content ───
const VIEW_META = {
  buys:     { title: "Today's Top Picks",   meta: 'highest-conviction technical setups · click tile → expand chart + paper-trade simulator' },
  fresh:    { title: 'Fresh Entries',       meta: 'entry within 0.75 ATR of pivot · best entry quality' },
  earnings: { title: 'Earnings This Week',  meta: 'binary catalysts in next 7d · close T2 EOD T-1' },
  surges:   { title: 'Volume Surges',       meta: 'RVOL ≥ 1.5× · institutional flow concentration' },
  ai:       { title: 'AI Edge Top 5',       meta: 'ML 3-headed forecast · swing 5d · ranked by p(up)' },
  momentum: { title: 'Top Momentum',        meta: 'highest momentum score · grade-A leaders' },
};

function getViewRows(view) {
  let rows;
  if (view === 'buys')          rows = DATA.buys;
  else if (view === 'fresh')    rows = DATA.panels.fresh;
  else if (view === 'earnings') rows = DATA.panels.earnings;
  else if (view === 'surges')   rows = DATA.panels.surges;
  else if (view === 'ai')       rows = DATA.panels.ai;
  else if (view === 'momentum') rows = DATA.panels.momentum;
  else rows = DATA.buys;
  // Cap to top 5 — keeps the grid a single clean row, no wrapping
  return (rows || []).slice(0, 5);
}

function renderTile(r, view) {
  // For AI rows (no full bar data), render a leaner variant
  if (view === 'ai') {
    return `<div class="mc" data-sym="${r.sym}" data-view="${view}">
      <div class="mc-row1">
        <div class="mc-left">
          <div class="mc-sym">${r.sym}</div>
          <div class="mc-livepx"><span style="color:var(--mute);font-size:0.66rem">ML forecast</span></div>
        </div>
        <div class="mc-right">
          <div class="mc-score" style="color:${r.edge>=0.5?'var(--gn)':r.edge>=0?'var(--am)':'var(--rd)'}">${r.edge>=0?'+':''}${r.edge.toFixed(2)}%</div>
          <div class="mc-score-lbl">edge · 5d</div>
          <div class="mc-tier-row"><span class="chip ${r.edge>=0.5?'tier1':r.edge>=0?'tier3':''}">${r.verdict}</span></div>
        </div>
      </div>
      <div class="mc-plan">
        <div class="mc-plan-row"><span class="lbl">p(up)</span><span class="val gn">${(r.p_up*100).toFixed(0)}%</span></div>
        <div class="mc-plan-row"><span class="lbl">verdict</span><span class="val">${r.verdict}</span></div>
        <div class="mc-plan-row"><span class="lbl">model edge</span><span class="val cp">${r.edge>=0?'+':''}${r.edge.toFixed(2)}%</span></div>
      </div>
      <div class="mc-narr" style="font-size:0.66rem">ML model 3-headed forecast · ranking by p(up) confidence over 5-day swing horizon</div>
      <div class="mc-actions">
        <button class="mc-action primary">📥 Paper Long</button>
        <button class="mc-action">⭐ Watch</button>
        <button class="mc-action">📋 Plan</button>
      </div>
    </div>`;
  }
  // Standard tile
  const rr = r.rr || 0;
  const riskPct = (1/(1+rr))*100, rewardPct = (rr/(1+rr))*100;
  const chg = r.closes && r.closes.length >= 2 ? ((r.closes[r.closes.length-1] - r.closes[r.closes.length-2])/r.closes[r.closes.length-2]*100) : 0;
  const pCls = chg >= 0 ? 'up' : 'dn', pSign = chg >= 0 ? '+' : '';
  const zb = r.in_zone ? `<div class="mc-zone-badge ${r.in_zone==='IN ZONE'?'in-zone':r.in_zone==='NEAR'?'near':'past'}">● ${r.in_zone}</div>` : '';
  // Headline value depends on view
  let headlineVal = r.score, headlineLbl = 'composite', headColor = 'var(--gn)';
  if (view === 'earnings') {
    headlineVal = r.earn_days===0 ? 'TODAY' : `+${r.earn_days}d`;
    headlineLbl = 'until earnings';
    headColor = r.earn_days<=1 ? 'var(--rd)' : r.earn_days<=3 ? 'var(--am)' : 'var(--copper-hi)';
  } else if (view === 'surges') {
    headlineVal = `${(r.rvol||0).toFixed(2)}×`;
    headlineLbl = 'RVOL';
    headColor = (r.rvol||0)>=3 ? 'var(--gn)' : 'var(--am)';
  } else if (view === 'momentum') {
    headlineVal = (r.momentum||0).toFixed(0);
    headlineLbl = 'momentum';
    headColor = (r.momentum||0)>=80 ? 'var(--gn)' : (r.momentum||0)>=60 ? 'var(--am)' : 'var(--mute)';
  }
  const entry = r.entry_mid || r.entry_low;
  const narr = `${r.setup||r.family} · ${r.sector} · RS ${r.rs??'—'} · RVOL ${(r.rvol||0).toFixed(2)} · catalyst T${r.cat_tier??'—'}${r.earn_days!=null ? ` · earnings ${r.earn_days}d` : ''}${r.star ? ` · ★${r.star}` : ''}`;
  return `<div class="mc" data-sym="${r.sym}" data-view="${view}">
    <div class="mc-row1">
      <div class="mc-left">
        <div class="mc-sym">${r.sym}</div>
        ${r.name ? `<div class="mc-name">${r.name}</div>` : ''}
        <div class="mc-livepx"><b>$${(r.price||0).toFixed(2)}</b><span class="pct ${pCls}">${pSign}${chg.toFixed(2)}%</span></div>
      </div>
      <div class="mc-right">
        <div class="mc-score" style="color:${headColor}">${headlineVal}</div>
        <div class="mc-score-lbl">${headlineLbl}</div>
        <div class="mc-tier-row">
          <span class="chip ${tierClass(r.tier)}">${r.tier||'—'}</span>
          <span class="chip setup">${(r.setup||r.family).slice(0,11)}</span>
        </div>
        ${zb}
      </div>
    </div>
    <div class="mc-chart-wrap">
      <div class="mc-chart-hdr"><span>28-day · stop/entry/T1 marked</span><span style="color:var(--mute-2)">$Vol ${r.dvol_m}M</span></div>
      <div class="mc-chart">${sparkAnnoSvg(r.closes, r.stop, entry, r.t1, 320, 78)}</div>
      ${r.volumes && r.volumes.length ? `<div class="mc-vol-bars">${volBarsSvg(r.volumes, 320, 18)}</div>` : ''}
    </div>
    <div class="mc-side">
      <div class="mc-radar-wrap"><div class="mc-radar-lbl">5-Pillar</div>${radarSvg(r.pillars)}</div>
      <div class="mc-plan">
        <div class="mc-plan-row"><span class="lbl">Entry</span><span class="val cp">${entry?'$'+entry.toFixed(2):'—'}</span></div>
        <div class="mc-plan-row"><span class="lbl">Stop</span><span class="val rd">${r.stop?'$'+r.stop.toFixed(2):'—'}</span></div>
        <div class="mc-plan-row"><span class="lbl">T1</span><span class="val gn">${r.t1?'$'+r.t1.toFixed(2):'—'}</span></div>
        <div class="mc-plan-row"><span class="lbl">Hold</span><span class="val">${r.hold ? r.hold + 'd' : '—'}</span></div>
      </div>
    </div>
    <div class="rrbar">
      <span class="rrlbl">R:R</span>
      <span class="rrtrack"><span class="risk" style="width:${riskPct}%"></span><span class="reward" style="width:${rewardPct}%"></span></span>
      <b>${rr ? rr.toFixed(1)+':1' : '—'}</b>
    </div>
    <div class="mc-narr">${narr}</div>
    <div class="mc-actions">
      <button class="mc-action primary">📥 Paper Long</button>
      <button class="mc-action">⭐ Watch</button>
      <button class="mc-action">📋 Plan</button>
    </div>
  </div>`;
}

function renderBento() {
  const view = STATE.view || 'buys';
  const rows = getViewRows(view);
  const meta = VIEW_META[view];
  document.getElementById('bento-ttl').innerHTML = `${meta.title} <span class="cnt">${rows.length} ACTIVE</span>`;
  document.getElementById('bento-meta').textContent = meta.meta;
  if (!rows.length) {
    document.getElementById('bento').innerHTML = `<div style="grid-column:1/-1;padding:48px;text-align:center;color:var(--mute-2);background:var(--card);border:1px dashed var(--border);border-radius:12px;font-style:italic">No items in this view today</div>`;
    return;
  }
  document.getElementById('bento').innerHTML = rows.map(r => renderTile(r, view)).join('');
  // Wire tile clicks → open detail panel
  document.querySelectorAll('#bento .mc').forEach(el => {
    el.addEventListener('click', e => {
      if (e.target.closest('.mc-action')) return;  // let action buttons fire
      const sym = el.dataset.sym;
      openDetail(sym, view);
      document.querySelectorAll('#bento .mc').forEach(x => x.classList.remove('is-selected'));
      el.classList.add('is-selected');
    });
  });
}

// ─── DETAIL PANEL (TV chart + Trade Sim) ─────────────────────────
let _dpTV = null;
function openDetail(sym, view) {
  // Look up row in current view first
  let r = (getViewRows(view) || []).find(x => x.sym === sym);
  // Fall back to universe for richer data
  if (!r || !r.bars) {
    r = DATA.universe.find(x => x.sym === sym) || r;
  }
  if (!r) return;
  const dp = document.getElementById('detail-panel');
  dp.classList.add('show');
  document.getElementById('dp-sym').textContent = r.sym;
  const entry = r.entry_mid || r.entry_low;
  document.getElementById('dp-meta').innerHTML = `
    <span>Score <b>${r.score}</b> · ${r.setup||r.family||'—'} · ${r.sector||'—'} · ${r.tier||'—'}</span>
    <span>RS <b>${r.rs??'—'}</b> · RVOL <b>${(r.rvol||0).toFixed(2)}</b> · cat <b>T${r.cat_tier??'—'}</b> · ${r.in_zone||'—'}</span>`;
  // Render side panel: Trade Sim + Plan summary
  document.getElementById('dp-side').innerHTML = `
    <div class="tsim">
      <div class="tsim-hdr">
        <span>Trade Simulator</span>
        <span>size: <b id="dp-tsim-sz">$10,000</b></span>
      </div>
      <div class="tsim-sl">
        <input type="range" id="dp-tsim-r" min="1000" max="50000" step="500" value="10000" oninput="updateDpSim()">
        <span class="tsim-sl-val" id="dp-tsim-v">$10K</span>
      </div>
      <div class="tsim-row">
        <div class="tsim-cell loss"><div class="lbl">If Stop</div><div class="val" id="dp-tsim-stop">—</div></div>
        <div class="tsim-cell"><div class="lbl">Shares</div><div class="val" id="dp-tsim-sh" style="color:var(--ink)">—</div></div>
        <div class="tsim-cell win"><div class="lbl">If T1</div><div class="val" id="dp-tsim-t1">—</div></div>
      </div>
    </div>
    <div class="dp-card-mini">
      <div class="lbl">Trade Plan</div>
      <div style="font-family:ui-monospace,monospace;font-size:0.74rem;display:grid;grid-template-columns:auto auto;gap:5px 14px">
        <span style="color:var(--mute)">Entry zone</span><span><b style="color:var(--copper-hi)">$${r.entry_low?r.entry_low.toFixed(2):'—'} – $${r.entry_high?r.entry_high.toFixed(2):'—'}</b></span>
        <span style="color:var(--mute)">Stop</span><span style="color:var(--rd);font-weight:700">${r.stop?'$'+r.stop.toFixed(2):'—'}</span>
        <span style="color:var(--mute)">T1</span><span style="color:var(--gn);font-weight:700">${r.t1?'$'+r.t1.toFixed(2):'—'}</span>
        <span style="color:var(--mute)">T2</span><span style="color:var(--gn-hi);font-weight:700">${r.t2?'$'+r.t2.toFixed(2):'—'}</span>
        <span style="color:var(--mute)">R:R</span><span style="color:var(--gn);font-weight:700">${r.rr?r.rr.toFixed(1)+':1':'—'}</span>
        <span style="color:var(--mute)">Hold</span><span style="color:var(--ink-2);font-weight:700">${r.hold?r.hold+'d':'—'}</span>
        <span style="color:var(--mute)">Allocation</span><span style="color:var(--ink-2);font-weight:700">${r.allocation_pct?r.allocation_pct.toFixed(1)+'%':'—'}</span>
      </div>
    </div>`;
  window.__dpRow = r;
  updateDpSim();
  // Mount TV chart
  if (_dpTV) { try { _dpTV.remove(); } catch(_) {} _dpTV = null; }
  document.getElementById('dp-chart').innerHTML = '';
  if (r.bars && r.bars.length) {
    requestAnimationFrame(() => {
      mountTVChart('dp-chart', r);
      _dpTV = _tvCharts.get('dp-chart');
    });
  } else {
    document.getElementById('dp-chart').innerHTML = `<div style="padding:60px;text-align:center;color:var(--mute-2);font-style:italic">No OHLCV bars available for ${sym}</div>`;
  }
  // Scroll into view
  dp.scrollIntoView({behavior:'smooth', block:'nearest'});
}
function closeDetail() {
  document.getElementById('detail-panel').classList.remove('show');
  document.querySelectorAll('#bento .mc').forEach(x => x.classList.remove('is-selected'));
}
document.getElementById('dp-close').addEventListener('click', closeDetail);

window.updateDpSim = function() {
  const r = window.__dpRow;
  if (!r) return;
  const sz = parseFloat(document.getElementById('dp-tsim-r').value);
  document.getElementById('dp-tsim-v').textContent = sz >= 1000 ? `$${(sz/1000).toFixed(1)}K` : `$${sz}`;
  document.getElementById('dp-tsim-sz').textContent = `$${sz.toLocaleString()}`;
  const px = r.price || 0;
  if (!px) return;
  const shares = Math.floor(sz / px);
  document.getElementById('dp-tsim-sh').textContent = shares.toLocaleString();
  if (r.stop && r.t1) {
    const lps = px - r.stop, wps = r.t1 - px;
    document.getElementById('dp-tsim-stop').textContent = `-$${Math.abs(shares*lps).toFixed(0)}`;
    document.getElementById('dp-tsim-t1').textContent   = `+$${(shares*wps).toFixed(0)}`;
  }
};

// ─── VIEW SWITCHING WIRE-UP ──────────────────────────────────────
function setView(view) {
  STATE.view = view;
  document.querySelectorAll('.view-tab').forEach(t => t.classList.toggle('on', t.dataset.view === view));
  closeDetail();
  renderBento();
}
document.querySelectorAll('.view-tab').forEach(t => t.addEventListener('click', () => setView(t.dataset.view)));

// counts on view-tab badges
function updateViewTabCounts() {
  document.getElementById('vt-buys').textContent     = DATA.buys.length;
  document.getElementById('vt-fresh').textContent    = DATA.panels.fresh.length;
  document.getElementById('vt-earnings').textContent = DATA.panels.earnings.length;
  document.getElementById('vt-surges').textContent   = DATA.panels.surges.length;
  document.getElementById('vt-ai').textContent       = DATA.panels.ai.length;
  document.getElementById('vt-momentum').textContent = DATA.panels.momentum.length;
}

// ─── SIDEBAR — TILE GRID (2-col, sparkline + key metric) ─────────
function tileSpark(closes) {
  if (!closes || closes.length < 2) {
    return `<svg width="100%" height="24" viewBox="0 0 100 24" preserveAspectRatio="none" style="display:block;overflow:hidden"><line x1="0" y1="12" x2="100" y2="12" stroke="#374151" stroke-dasharray="2 2"/></svg>`;
  }
  const s = closes.slice(-20);
  const min = Math.min(...s), max = Math.max(...s), range = max - min || 1;
  const W = 120, H = 24, pad = 2;
  const pts = s.map((v, i) => [pad + (i/(s.length-1))*(W-2*pad), H - pad - ((v-min)/range)*(H-2*pad)]);
  const polyStr = pts.map(p => p.map(n => n.toFixed(1)).join(',')).join(' ');
  const trend = s[s.length-1] > s[0] ? 'up' : 'down';
  const stroke = trend === 'up' ? '#10b981' : '#f87171';
  const fill   = trend === 'up' ? 'rgba(16,185,129,0.18)' : 'rgba(248,113,113,0.18)';
  const area = `${pad},${H-pad} ${polyStr} ${W-pad},${H-pad}`;
  const [lx, ly] = pts[pts.length-1];
  return `<svg width="100%" height="24" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="display:block;overflow:hidden">
    <polyline points="${area}" fill="${fill}" stroke="none"/>
    <polyline points="${polyStr}" fill="none" stroke="${stroke}" stroke-width="1.4" stroke-linejoin="round"/>
    <circle cx="${lx.toFixed(1)}" cy="${ly.toFixed(1)}" r="1.8" fill="#fff" stroke="${stroke}" stroke-width="1"/>
  </svg>`;
}

// Generic tile renderer
function sbTile(opts) {
  // opts: { rk, sym, val, valCls, accentCls, chips:[{label,cls}], meta:[{lbl,val}], closes }
  const chips = (opts.chips || []).map(c => `<span class="sb-tile-chip ${c.cls||''}">${c.label}</span>`).join('');
  const meta  = (opts.meta || []).map(m => `<span><span style="color:var(--mute-2)">${m.lbl}</span> <b>${m.val}</b></span>`).join('');
  return `<div class="sb-tile ${opts.accentCls||''}" data-sym="${opts.sym}">
    <span class="sb-tile-rank">#${opts.rk}</span>
    <div class="sb-tile-row1">
      <span class="sb-tile-sym">${opts.sym}</span>
      <span class="sb-tile-val ${opts.valCls||''}">${opts.val}</span>
    </div>
    <div class="sb-tile-spark">${tileSpark(opts.closes)}</div>
    <div class="sb-tile-meta">${meta}</div>
    ${chips ? `<div class="sb-tile-chips">${chips}</div>` : ''}
  </div>`;
}

function renderSidebar() {
  // ⚡ FRESH ENTRIES
  const fresh = DATA.panels.fresh.length
    ? `<div class="sb-tiles">${DATA.panels.fresh.map((r,i) => sbTile({
        rk: i+1, sym: r.sym, val: r.score,
        valCls: r.score>=75?'gn':r.score>=60?'am':'',
        accentCls: r.score>=75?'gn':r.score>=60?'am':'',
        chips: [
          { label: r.setup||r.family, cls:'cp' },
          { label: r.sector.slice(0,6), cls:'' },
        ],
        meta: [
          { lbl:'RVOL', val:(r.rvol||0).toFixed(2) },
          { lbl:'RS', val: r.rs??'—' },
        ],
        closes: r.closes,
      })).join('')}</div>`
    : '<div class="sb-empty">no FRESH entries</div>';

  // 📅 EARNINGS
  const earn = DATA.panels.earnings.length
    ? `<div class="sb-tiles">${DATA.panels.earnings.map((r,i) => sbTile({
        rk: i+1, sym: r.sym,
        val: r.earn_days===0?'TODAY':`+${r.earn_days}d`,
        valCls: r.earn_days<=1?'rd':r.earn_days<=3?'am':'cp',
        accentCls: r.earn_days<=1?'rd':r.earn_days<=3?'am':'',
        chips: [
          { label: r.sector.slice(0,8), cls:'' },
          { label: r.setup||r.family, cls:'cp' },
        ],
        meta: [
          { lbl:'PX', val: r.price?'$'+r.price.toFixed(2):'—' },
          { lbl:'★', val: r.star || '—' },
        ],
        closes: r.closes,
      })).join('')}</div>`
    : '<div class="sb-empty">no earnings ≤7d</div>';

  // 🔥 VOLUME SURGES
  const surge = DATA.panels.surges.length
    ? `<div class="sb-tiles">${DATA.panels.surges.map((r,i) => sbTile({
        rk: i+1, sym: r.sym,
        val: `${(r.rvol||0).toFixed(2)}×`,
        valCls: (r.rvol||0)>=3?'gn':'am',
        accentCls: (r.rvol||0)>=3?'gn':'am',
        chips: [
          { label: r.sector.slice(0,8), cls:'' },
          { label: r.entry_quality, cls:'bl' },
        ],
        meta: [
          { lbl:'Score', val: r.score },
          { lbl:'PX', val: r.price?'$'+r.price.toFixed(2):'—' },
        ],
        closes: r.closes,
      })).join('')}</div>`
    : '<div class="sb-empty">no surges ≥1.5×</div>';

  // ✦ AI EDGE (no closes — synthesize from p_up curve, fall back to flat)
  const ai = DATA.panels.ai.length
    ? `<div class="sb-tiles">${DATA.panels.ai.map((r,i) => sbTile({
        rk: i+1, sym: r.sym,
        val: `${r.edge>=0?'+':''}${r.edge.toFixed(2)}%`,
        valCls: r.edge>=0.5?'gn':r.edge>=0?'am':'rd',
        accentCls: r.edge>=0.5?'gn':r.edge>=0?'am':'',
        chips: [
          { label: r.verdict.slice(0,8), cls: r.edge>=0.5?'gn':r.edge>=0?'am':'rd' },
        ],
        meta: [
          { lbl:'p(up)', val: `${(r.p_up*100).toFixed(0)}%` },
          { lbl:'edge', val: `${r.edge.toFixed(2)}%` },
        ],
        closes: null,
      })).join('')}</div>`
    : '<div class="sb-empty">ML cache empty</div>';

  // 🚀 TOP MOMENTUM
  const mom = DATA.panels.momentum.length
    ? `<div class="sb-tiles">${DATA.panels.momentum.map((r,i) => sbTile({
        rk: i+1, sym: r.sym,
        val: `${(r.momentum||0).toFixed(0)}`,
        valCls: (r.momentum||0)>=80?'gn':(r.momentum||0)>=60?'am':'',
        accentCls: (r.momentum||0)>=80?'gn':(r.momentum||0)>=60?'am':'',
        chips: [
          { label: r.sector.slice(0,8), cls:'' },
        ],
        meta: [
          { lbl:'Score', val: r.score },
          { lbl:'RS', val: r.rs??'—' },
        ],
        closes: r.closes,
      })).join('')}</div>`
    : '<div class="sb-empty">no momentum data</div>';

  document.getElementById('sidebar').innerHTML = `
    <div class="sb-card"><div class="sb-hd open" onclick="toggleSb(this)"><div class="sb-hd-l"><span class="ico">⚡</span>Fresh Entries</div><div class="sb-hd-r"><span class="cnt">${DATA.panels.fresh.length}</span><span class="caret">▼</span></div></div><div class="sb-body show">${fresh}</div></div>
    <div class="sb-card"><div class="sb-hd" onclick="toggleSb(this)"><div class="sb-hd-l"><span class="ico">📅</span>Earnings This Week</div><div class="sb-hd-r"><span class="cnt">${DATA.panels.earnings.length}</span><span class="caret">▼</span></div></div><div class="sb-body">${earn}</div></div>
    <div class="sb-card"><div class="sb-hd" onclick="toggleSb(this)"><div class="sb-hd-l"><span class="ico">🔥</span>Volume Surges</div><div class="sb-hd-r"><span class="cnt">${DATA.panels.surges.length}</span><span class="caret">▼</span></div></div><div class="sb-body">${surge}</div></div>
    <div class="sb-card"><div class="sb-hd" onclick="toggleSb(this)"><div class="sb-hd-l"><span class="ico">✦</span>AI Edge Top 5</div><div class="sb-hd-r"><span class="cnt">${DATA.panels.ai.length}</span><span class="caret">▼</span></div></div><div class="sb-body">${ai}</div></div>
    <div class="sb-card"><div class="sb-hd" onclick="toggleSb(this)"><div class="sb-hd-l"><span class="ico">🚀</span>Top Momentum</div><div class="sb-hd-r"><span class="cnt">${DATA.panels.momentum.length}</span><span class="caret">▼</span></div></div><div class="sb-body">${mom}</div></div>
  `;
}
// Sidebar header behavior: shift+click (or icon click) switches the bento view;
// regular click expands/collapses the accordion body as before.
window.toggleSb = el => {
  // Map sidebar headers to view keys based on the icon
  const iconText = el.querySelector('.ico')?.textContent || '';
  const viewMap = {'⚡':'fresh','📅':'earnings','🔥':'surges','✦':'ai','🚀':'momentum'};
  const targetView = viewMap[iconText.trim()];
  if (targetView) setView(targetView);
  el.classList.toggle('open');
  el.nextElementSibling.classList.toggle('show');
};

// ─── TICKER TAPE ─────────────────────────────────────────────────
function renderTape() {
  const buys = DATA.buys;
  if (!buys.length) {
    document.getElementById('tape-strip').innerHTML = '<span class="tape-tk"><b style="color:var(--mute)">no BUYs in scan</b></span>';
    return;
  }
  const html = buys.map(b => {
    const chg = b.closes && b.closes.length >= 2 ? ((b.closes[b.closes.length-1] - b.closes[b.closes.length-2])/b.closes[b.closes.length-2]*100) : 0;
    const cls = chg >= 0 ? 'up' : 'dn';
    const sign = chg >= 0 ? '+' : '';
    return `<span class="tape-tk"><b>${b.sym}</b><span class="px">$${(b.price||0).toFixed(2)}</span><span class="pct ${cls}">${sign}${chg.toFixed(2)}%</span></span>`;
  }).join('');
  // Duplicate for seamless scroll
  document.getElementById('tape-strip').innerHTML = html + html;
}

// ─── SLIDERS ─────────────────────────────────────────────────────
function bindSlider(sliderEl, min, max, onChange, format) {
  const fill = sliderEl.querySelector('.slider-fill');
  const hLo  = sliderEl.querySelector('[data-h="lo"]');
  const hHi  = sliderEl.querySelector('[data-h="hi"]');
  let lo = min, hi = max;
  const update = () => {
    const lp = ((lo-min)/(max-min))*100, hp = ((hi-min)/(max-min))*100;
    hLo.style.left = `${lp}%`; hHi.style.left = `${hp}%`;
    fill.style.left = `${lp}%`; fill.style.width = `${hp-lp}%`;
    onChange(lo, hi);
    const label = sliderEl.parentElement.querySelector('.slider-val');
    if (label) label.textContent = format(lo, hi);
  };
  update();
  function drag(handle, isLo) {
    let act = false;
    const s = e => { act = true; e.preventDefault(); };
    const m = e => {
      if (!act) return;
      const rect = sliderEl.getBoundingClientRect();
      const x = (e.clientX || (e.touches && e.touches[0].clientX)) - rect.left;
      const pct = Math.max(0, Math.min(1, x/rect.width));
      const v = min + pct*(max-min);
      if (isLo) lo = Math.min(v, hi - (max-min)*0.02);
      else      hi = Math.max(v, lo + (max-min)*0.02);
      update();
    };
    handle.addEventListener('mousedown', s);
    handle.addEventListener('touchstart', s);
    window.addEventListener('mousemove', m);
    window.addEventListener('touchmove', m);
    window.addEventListener('mouseup', () => act = false);
    window.addEventListener('touchend', () => act = false);
  }
  drag(hLo, true); drag(hHi, false);
  return () => { lo=min; hi=max; update(); };
}
let resetPrice, resetScore, resetRR;
function initSliders() {
  resetPrice = bindSlider(document.querySelector('[data-slider="price"]'), DATA.price_min, DATA.price_max, (l,h)=>{STATE.priceLo=l;STATE.priceHi=h;applyFilters();}, (l,h)=>`$${l.toFixed(0)}–$${h.toFixed(0)}`);
  resetScore = bindSlider(document.querySelector('[data-slider="score"]'), 0, 100, (l,h)=>{STATE.scoreLo=l;STATE.scoreHi=h;applyFilters();}, (l,h)=>`${l.toFixed(0)}–${h.toFixed(0)}`);
  resetRR = bindSlider(document.querySelector('[data-slider="rr"]'), 0, 10, (l,h)=>{STATE.rrLo=l;STATE.rrHi=h;applyFilters();}, (l,h)=>`${l.toFixed(1)}–${h.toFixed(1)}`);
}

// ─── SECTOR MENU ─────────────────────────────────────────────────
function renderSectorMenu() {
  document.getElementById('sector-menu').innerHTML = DATA.sector_data.map(s => `<label><input type="checkbox" data-sector="${s.name}"> ${s.name} <span class="cnt">${s.count}</span></label>`).join('');
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
  document.querySelectorAll('#sector-menu input').forEach(cb => cb.checked = STATE.sectors.has(cb.dataset.sector));
  updateSectorBtn();
}
function updateSectorBtn() {
  const btn = document.getElementById('sector-btn');
  const c = document.getElementById('sector-count');
  const summary = document.getElementById('sector-summary');
  if (STATE.sectors.size === 0) {
    if (c) c.textContent = '(all)';
    if (summary) summary.textContent = '(all)';
    btn.classList.remove('has-filter');
  } else {
    const txt = `${STATE.sectors.size} selected`;
    if (c) c.textContent = `(${STATE.sectors.size})`;
    if (summary) summary.textContent = txt;
    btn.classList.add('has-filter');
  }
}
document.getElementById('sector-btn').addEventListener('click', e => {
  e.stopPropagation();
  document.getElementById('sector-menu').classList.toggle('show');
});
document.addEventListener('click', e => {
  if (!e.target.closest('.sector-dd')) document.getElementById('sector-menu').classList.remove('show');
});

// ─── FILTER CHIPS ────────────────────────────────────────────────
document.querySelectorAll('.fchip[data-fg]').forEach(c => {
  c.addEventListener('click', () => {
    const fg = c.dataset.fg, fv = c.dataset.fv;
    document.querySelectorAll(`.fchip[data-fg="${fg}"]`).forEach(x => x.classList.remove('on'));
    c.classList.add('on');
    if (fg === 'zone') STATE.zone = fv === 'all' ? null : fv;
    else STATE[fg] = fv;
    applyFilters();
  });
});
document.getElementById('search').addEventListener('input', e => { STATE.search = e.target.value.trim().toUpperCase(); applyFilters(); });
document.getElementById('reset-btn').addEventListener('click', () => {
  STATE.universe='all';STATE.verdict='all';STATE.eq='all';STATE.zone=null;STATE.sectors.clear();STATE.search='';
  document.getElementById('search').value='';
  document.querySelectorAll('.fchip').forEach(c => c.classList.remove('on'));
  document.querySelectorAll('.fchip[data-fv="all"]').forEach(c => c.classList.add('on'));
  syncSectorMenu();
  if (resetPrice) resetPrice(); if (resetScore) resetScore(); if (resetRR) resetRR();
  applyFilters();
});

// ─── TABLE CELL HELPERS ─────────────────────────────────────────
function scoreBar(score, w) {
  const pct = Math.min(100, score);
  const color = score >= 75 ? '#10b981' : score >= 60 ? '#f59e0b' : '#6b7280';
  return `<span style="display:inline-block;width:${w}px;height:5px;background:#1f2937;border-radius:3px;margin-left:6px;vertical-align:middle;overflow:hidden"><span style="display:block;height:100%;width:${pct}%;background:${color};border-radius:3px"></span></span>`;
}
function tfsnBars(tfsn) {
  const labels = ['T','F','S','N'];
  const colors = tfsn.map(v => v >= 0.66 ? '#10b981' : v >= 0.33 ? '#f59e0b' : '#f87171');
  return `<span style="display:inline-flex;align-items:flex-end">${tfsn.map((v, i) => {
    const h = Math.max(3, v * 16);
    return `<span style="display:inline-flex;flex-direction:column;align-items:center;gap:1px;margin-right:2px">
      <span style="display:block;width:5px;height:16px;background:#1f2937;border-radius:1px;position:relative;overflow:hidden">
        <span style="position:absolute;bottom:0;left:0;right:0;height:${h}px;background:${colors[i]};border-radius:1px"></span>
      </span>
      <span style="font-size:0.5rem;color:#6b7280;font-family:ui-monospace,monospace;font-weight:700">${labels[i]}</span>
    </span>`;
  }).join('')}</span>`;
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
  const filled = '★'.repeat(n), empty = '☆'.repeat(5 - n);
  const color = n >= 4 ? '#10b981' : n >= 3 ? '#f59e0b' : '#f87171';
  return `<span style="color:${color};letter-spacing:1px;font-size:0.85rem">${filled}<span style="color:#374151">${empty}</span></span>`;
}
function rankDelta(d) {
  if (d == null) return `<span style="color:var(--mute-3)">·</span>`;
  if (d === 0)   return `<span style="color:var(--mute-2)">0</span>`;
  if (d > 0)     return `<span style="color:var(--gn);font-weight:700">+${d}</span>`;
  return `<span style="color:var(--rd);font-weight:700">${d}</span>`;
}
function srcPill(src) {
  const C = {'SP500':'var(--gn)','R1000':'var(--bl)','R2000':'var(--copper)','MID400':'var(--pl)','SML600':'var(--am)','IPO':'var(--ti)','CRYPTO':'var(--ti)','MOM':'var(--am)','ETF':'var(--mute-2)'};
  const color = C[src] || 'var(--mute-2)';
  return `<span style="display:inline-block;padding:2px 7px;border:1px solid ${color};color:${color};border-radius:5px;font-size:0.62rem;font-weight:700;font-family:ui-monospace,monospace;letter-spacing:0.04em">${src||'—'}</span>`;
}
function pctChip(pct) {
  if (pct == null || isNaN(pct)) return `<span style="color:var(--mute-2)">—</span>`;
  const c = pct >= 0 ? 'var(--gn)' : 'var(--rd)';
  return `<span style="color:${c};font-weight:700">${pct >= 0 ? '+' : ''}${pct.toFixed(2)}</span>`;
}
function fmt(v, dp=2) { if (v == null) return '—'; const n = +v; return isNaN(n) ? v : n.toFixed(dp); }

// ─── TOP 5 MATCHES PREVIEW ──────────────────────────────────────
function t5Spark(closes) {
  if (!closes || closes.length < 2) {
    return `<svg width="100%" height="22" viewBox="0 0 100 22" preserveAspectRatio="none" style="display:block;overflow:hidden"><line x1="0" y1="11" x2="100" y2="11" stroke="#374151" stroke-dasharray="2 2"/></svg>`;
  }
  const s = closes.slice(-18);
  const min = Math.min(...s), max = Math.max(...s), range = max - min || 1;
  const W = 120, H = 22, pad = 2;
  const pts = s.map((v, i) => [pad + (i/(s.length-1))*(W-2*pad), H - pad - ((v-min)/range)*(H-2*pad)]);
  const polyStr = pts.map(p => p.map(n => n.toFixed(1)).join(',')).join(' ');
  const trend = s[s.length-1] > s[0] ? 'up' : 'down';
  const stroke = trend === 'up' ? '#10b981' : '#f87171';
  const fill   = trend === 'up' ? 'rgba(16,185,129,0.18)' : 'rgba(248,113,113,0.18)';
  const area = `${pad},${H-pad} ${polyStr} ${W-pad},${H-pad}`;
  const [lx, ly] = pts[pts.length-1];
  return `<svg width="100%" height="22" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="display:block;overflow:hidden">
    <polyline points="${area}" fill="${fill}" stroke="none"/>
    <polyline points="${polyStr}" fill="none" stroke="${stroke}" stroke-width="1.5" stroke-linejoin="round"/>
    <circle cx="${lx.toFixed(1)}" cy="${ly.toFixed(1)}" r="1.8" fill="#fff" stroke="${stroke}" stroke-width="1"/>
  </svg>`;
}
function renderTop5(rows) {
  const wrap = document.getElementById('top5-tiles');
  if (!wrap) return;
  const top = rows.slice(0, 5);
  if (!top.length) {
    wrap.innerHTML = `<div class="t5-empty">No matches with current filters · <a href="#" onclick="document.getElementById('reset-btn').click();return false;" style="color:var(--copper)">reset</a></div>`;
    return;
  }
  wrap.innerHTML = top.map(r => {
    const sc = r.score >= 75 ? 'gn' : r.score >= 60 ? 'am' : 'mute';
    const accent = r.verdict === 'BUY' ? 'gn' : r.verdict === 'WATCH' ? 'am' : (r.verdict === 'AVOID' ? 'rd' : '');
    const chg = r.pct_change_1d || 0;
    const chgStr = chg >= 0 ? `+${chg.toFixed(2)}%` : `${chg.toFixed(2)}%`;
    const chgColor = chg >= 0 ? 'var(--gn)' : 'var(--rd)';
    return `<div class="t5-tile ${accent}" data-sym="${r.sym}">
      <div class="t5-tile-row1">
        <span class="t5-tile-sym">${r.sym}</span>
        <span class="t5-tile-score ${sc}">${r.score}</span>
      </div>
      <div class="t5-tile-spark">${t5Spark(r.closes)}</div>
      <div class="t5-tile-row2">
        <span class="vchip ${r.verdict||'WAIT'}">${(VERDICT_LABEL[r.verdict]||r.verdict||'—').slice(0,8)}</span>
        <span><b>$${(r.price||0).toFixed(2)}</b></span>
        <span style="color:${chgColor};font-weight:700">${chgStr}</span>
      </div>
    </div>`;
  }).join('');
  // Click → scroll table and highlight
  wrap.querySelectorAll('.t5-tile').forEach(t => {
    t.addEventListener('click', () => {
      const sym = t.dataset.sym;
      openDetail(sym, STATE.view);
    });
  });
}

function activeFilterCount() {
  let n = 0;
  if (STATE.universe !== 'all') n++;
  if (STATE.verdict !== 'all') n++;
  if (STATE.eq !== 'all') n++;
  if (STATE.zone) n++;
  if (STATE.sectors.size) n++;
  if (STATE.search) n++;
  if (STATE.priceLo > DATA.price_min || STATE.priceHi < DATA.price_max) n++;
  if (STATE.scoreLo > 0 || STATE.scoreHi < 100) n++;
  if (STATE.rrLo > 0 || STATE.rrHi < 10) n++;
  return n;
}

// ─── APPLY + RENDER ─────────────────────────────────────────────
function applyFilters() {
  let rows = DATA.universe.slice();
  if (STATE.universe === 'core')  rows = rows.filter(r => CORE_SRCS.has(r.src));
  if (STATE.universe === 'alpha') rows = rows.filter(r => ALPHA_SRCS.has(r.src));
  if (STATE.verdict !== 'all') rows = rows.filter(r => (r.verdict||'').toUpperCase() === STATE.verdict);
  if (STATE.eq !== 'all') rows = rows.filter(r => (r.entry_quality||'').toUpperCase() === STATE.eq);
  if (STATE.zone) rows = rows.filter(r => r.in_zone === STATE.zone);
  if (STATE.sectors.size) rows = rows.filter(r => STATE.sectors.has(r.sector));
  if (STATE.search) rows = rows.filter(r => (r.sym||'').toUpperCase().includes(STATE.search) || (r.name||'').toUpperCase().includes(STATE.search));
  rows = rows.filter(r => (r.price||0) >= STATE.priceLo && (r.price||0) <= STATE.priceHi);
  rows = rows.filter(r => (r.score||0) >= STATE.scoreLo && (r.score||0) <= STATE.scoreHi);
  rows = rows.filter(r => (r.rr||0) >= STATE.rrLo && (r.rr||0) <= STATE.rrHi);
  rows.sort((a, b) => {
    const va = a[STATE.sortKey], vb = b[STATE.sortKey];
    const na = (va == null) ? -Infinity : va, nb = (vb == null) ? -Infinity : vb;
    const cmp = (typeof na === 'string') ? na.localeCompare(nb) : (na - nb);
    return STATE.sortDir === 'asc' ? cmp : -cmp;
  });
  renderTable(rows);
  document.getElementById('tb-count').textContent = rows.length;
  document.getElementById('tb-total').textContent = DATA.universe.length;
  const fac = document.getElementById('fb-active-count');
  if (fac) fac.textContent = activeFilterCount();
}
function renderTable(rows) {
  if (!rows.length) {
    document.getElementById('tb-body').innerHTML = `<tr><td colspan="20" style="padding:48px;text-align:center;color:var(--mute-2);font-style:italic">No matches · <a href="#" onclick="document.getElementById('reset-btn').click();return false;" style="color:var(--copper)">reset</a></td></tr>`;
    return;
  }
  document.getElementById('tb-body').innerHTML = rows.map((r, i) => {
    const sc = r.score >= 75 ? 'hi' : r.score >= 60 ? 'mid' : 'lo';
    const idx = String(i + 1).padStart(2, '0');
    // WR (LB · N)
    const wrs = r.wr_stats || {wr:null,lb:null,n:0};
    let wrCell;
    if (wrs.wr == null || wrs.n === 0) {
      wrCell = `<span style="color:var(--mute-2)">—</span>`;
    } else {
      const wrCls = wrs.lb >= 0.5 ? 'gn' : wrs.lb >= 0.4 ? 'am' : 'rd';
      wrCell = `<span class="wr-cell ${wrCls}"><span class="wr-val">${(wrs.wr*100).toFixed(0)}%</span><span class="wr-lb">LB ${(wrs.lb*100).toFixed(0)}%</span><span class="wr-n">n=${wrs.n}</span></span>`;
    }
    // STOP / T1 combined
    const stopT1 = (r.stop || r.t1)
      ? `<div class="stop-t1-cell"><span class="stop">${r.stop?'$'+r.stop.toFixed(2):'—'}</span><span class="t1">${r.t1?'$'+r.t1.toFixed(2):'—'}</span></div>`
      : '<span style="color:var(--mute-2)">—</span>';
    return `<tr data-sym="${r.sym}">
      <td class="num" style="color:var(--mute-2);font-weight:700">${idx}</td>
      <td class="num">${rankDelta(r.rank_delta)}</td>
      <td><b style="color:var(--ink);font-size:0.86rem">${r.sym}</b></td>
      <td style="color:var(--ink-2)">${(r.setup||r.family||'').slice(0,18)}</td>
      <td><span class="vchip ${r.verdict||'NEUTRAL'}">${VERDICT_LABEL[r.verdict] || (r.verdict||'—').toUpperCase()}</span></td>
      <td style="color:var(--ink-2);font-weight:700">${r.tier||'—'}</td>
      <td class="num"><b class="score-cell ${sc}">${r.score}</b>${scoreBar(r.score, 38)}</td>
      <td>${tfsnBars(r.tfsn)}</td>
      <td class="num" style="color:var(--ink-2);font-weight:700">${r.price?r.price.toFixed(2):'—'}</td>
      <td>${entryWithIcon(r.entry_quality)}</td>
      <td class="num">${starsRating(r.star)}</td>
      <td class="num">${pctChip(r.pct_change_1d)}</td>
      <td class="num">${r.rs??'—'}</td>
      <td class="num">${fmt(r.rvol)}×</td>
      <td class="num" style="color:var(--gn);font-weight:700">${r.rr?'1:'+r.rr.toFixed(1):'—'}</td>
      <td class="num">${r.cat_tier?'<span style="color:var(--copper-hi);font-weight:700">T'+r.cat_tier+'</span>':'<span style="color:var(--mute-2)">—</span>'}</td>
      <td style="color:var(--ink-2);font-weight:600">${(r.entry_quality||'—').toUpperCase()}</td>
      <td style="color:var(--mute)">${(r.sector||'').slice(0,15)}</td>
      <td>${srcPill(r.src)}</td>
      <td class="num">${wrCell}</td>
      <td><span class="mech-cell" title="${r.mechanism||''}">${r.mechanism||'—'}</span></td>
      <td class="num">${stopT1}</td>
      <td><div class="tbl-actions"><button class="tbl-action buy" data-act="buy" data-sym="${r.sym}" title="Add to Paper Long ${r.sym}">🛒</button><button class="tbl-action track" data-act="track" data-sym="${r.sym}" title="Track ${r.sym} in Watchlist">★</button></div></td>
    </tr>`;
  }).join('');

  // Wire action buttons
  document.querySelectorAll('#tb-body .tbl-action').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const sym = btn.dataset.sym, act = btn.dataset.act;
      if (act === 'buy') {
        alert(`▶ Add to Paper Long: ${sym}\n\n(would POST to /api/positions/open)`);
      } else {
        alert(`★ Tracking ${sym} in Watchlist\n\n(would POST to /api/custom/add)`);
      }
    });
  });
}

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

document.addEventListener('keydown', e => {
  if (e.key === '/' && document.activeElement.tagName !== 'INPUT') { e.preventDefault(); document.getElementById('search').focus(); }
  if (e.key === 'Escape') document.getElementById('search').blur();
});

document.getElementById('csv-btn').addEventListener('click', () => {
  const rows = DATA.universe;
  const cols = ['sym','score','verdict','tier','setup','sector','price','rs','rvol','rsi','rr','stop','t1','entry_quality','cat_tier','earn_days','hold','src'];
  const csv = [cols.join(',')].concat(rows.map(r => cols.map(c => JSON.stringify(r[c] ?? '')).join(','))).join('\n');
  const blob = new Blob([csv], {type:'text/csv'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = `scanner_${new Date().toISOString().slice(0,10)}.csv`;
  a.click();
});

// INIT
renderPulse();
renderFunnel();
updateViewTabCounts();
renderBento();
renderTape();
renderSectorMenu();
initSliders();
applyFilters();
</script>
</body>
</html>
'''

OUT.write_text(HTML.replace('__PAYLOAD__', json.dumps(payload)))
print(f'wrote {OUT.relative_to(BASE)} ({OUT.stat().st_size:,} bytes)')

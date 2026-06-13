#!/usr/bin/env python3
"""One-off forensic: per-field predictive value of every signal in picks_history.
Recomputed against CURRENT matured data (June trades now resolved).
Read-only. No config mutation."""
import json, math, statistics as st
from collections import defaultdict

T = json.load(open('cache/picks_history.json'))['trades']

def num(x):
    try:
        f = float(x);  return f if f == f else None
    except: return None

# outcome field: prefer realized_r, fallback pct_chg
def out_r(t):  return num(t.get('realized_r'))
def out_pct(t): return num(t.get('pct_chg'))

resolved = [t for t in T if out_pct(t) is not None and t.get('exit_date')]
print(f"=== UNIVERSE: {len(T)} trades, {len(resolved)} resolved w/ outcome ===")
# date range
dates = sorted(t['run_date'] for t in resolved if t.get('run_date'))
print(f"date range: {dates[0]} -> {dates[-1]}")

def pf(rows, key=out_pct):
    g = sum(v for t in rows if (v:=key(t)) is not None and v>0)
    l = sum(-v for t in rows if (v:=key(t)) is not None and v<0)
    return (g/l) if l>0 else float('inf')

def wr(rows):
    w=[1 for t in rows if out_pct(t) is not None and out_pct(t)>0]
    n=[t for t in rows if out_pct(t) is not None]
    return (len(w)/len(n)*100) if n else 0, len(n)

def wilson_lb(k,n,z=1.96):
    if n==0: return 0
    p=k/n; d=1+z*z/n
    c=p+z*z/(2*n); m=z*math.sqrt((p*(1-p)+z*z/(4*n))/n)
    return (c-m)/d*100

def pearson(xs,ys):
    n=len(xs)
    if n<3: return None,None
    mx,my=sum(xs)/n,sum(ys)/n
    sx=sum((x-mx)**2 for x in xs); sy=sum((y-my)**2 for y in ys)
    if sx==0 or sy==0: return None,None
    cov=sum((x-mx)*(y-my) for x,y in zip(xs,ys))
    r=cov/math.sqrt(sx*sy)
    t=r*math.sqrt((n-2)/(1-r*r)) if abs(r)<1 else float('inf')
    return r,t

# ---------- 1. CONTINUOUS FIELDS: Pearson vs realized return ----------
print("\n=== 1. CONTINUOUS SIGNAL -> RETURN (Pearson r, t-stat) ===")
print("  positive r = field RANKS outcomes correctly; negative = INVERTED")
cont = ['score','raw_total','tech_score','cat_score','rs_score','sm_score','qg_score',
        'bonus_total','wr_multiplier','rr_ratio','market_vix','market_breadth',
        'market_spy_1m','market_dist_days','hold_days','planned_risk']
print(f"{'field':16s} {'n':>5s} {'r':>7s} {'t':>7s}  verdict")
for f in cont:
    pairs=[(num(t.get(f)),out_pct(t)) for t in resolved if num(t.get(f)) is not None and out_pct(t) is not None]
    if len(pairs)<30: continue
    xs=[a for a,b in pairs]; ys=[b for a,b in pairs]
    r,tt=pearson(xs,ys)
    if r is None: continue
    tag = 'INVERTED' if r<-0.03 else ('weak+' if r>0.03 else 'flat~')
    print(f"{f:16s} {len(pairs):5d} {r:+7.3f} {tt:+7.1f}  {tag}")

# ---------- 2. PILLAR DECILE MONOTONICITY ----------
print("\n=== 2. SCORE-BAND PF (composite + each pillar) — does higher = better? ===")
def band_table(field, bins):
    rows_by=defaultdict(list)
    for t in resolved:
        v=num(t.get(field))
        if v is None: continue
        for lo,hi in bins:
            if lo<=v<hi: rows_by[(lo,hi)].append(t); break
    print(f"  [{field}]")
    for (lo,hi) in bins:
        rr=rows_by[(lo,hi)]
        if not rr: continue
        w,n=wr(rr)
        avg=st.mean([out_pct(t) for t in rr if out_pct(t) is not None])
        print(f"    {lo:>4.0f}-{hi:<4.0f} n={n:4d}  WR={w:4.1f}%  PF={pf(rr):4.2f}  avg={avg:+5.2f}%")

band_table('score',[(60,65),(65,70),(70,75),(75,80),(80,85),(85,90),(90,101)])
for p in ['tech_score','cat_score','rs_score','sm_score','qg_score']:
    band_table(p,[(0,5),(5,10),(10,15),(15,20),(20,26),(26,36)])

# ---------- 3. CATEGORICAL FIELDS ----------
print("\n=== 3. CATEGORICAL BREAKDOWNS (PF, WR, Wilson-LB) ===")
def cat_table(field):
    g=defaultdict(list)
    for t in resolved: g[t.get(field)].append(t)
    print(f"  [{field}]")
    rows=[]
    for k,rr in g.items():
        w,n=wr(rr)
        if n<10: continue
        kk=sum(1 for t in rr if out_pct(t) and out_pct(t)>0)
        rows.append((pf(rr),k,n,w,wilson_lb(kk,n),st.mean([out_pct(t) for t in rr if out_pct(t) is not None])))
    for p,k,n,w,wl,avg in sorted(rows,reverse=True):
        ps = '%.2f'%p if p!=float('inf') else 'inf'
        print(f"    {str(k):26s} n={n:4d}  WR={w:4.1f}%  PF={ps:>5s}  WilsonLB={wl:4.1f}%  avg={avg:+5.2f}%")
for f in ['verdict','conviction_tier','catalyst_tier','entry_quality','entry_subtype',
          'setup_family','setup_type','regime4','direction','sector']:
    cat_table(f)

# ---------- 4. TIME DECAY (matured) ----------
print("\n=== 4. EDGE DECAY BY MONTH (now matured) ===")
mg=defaultdict(list)
for t in resolved:
    rd=t.get('run_date','')
    if len(rd)>=7: mg[rd[:7]].append(t)
for m in sorted(mg):
    rr=mg[m]; w,n=wr(rr)
    print(f"    {m}  n={n:4d}  WR={w:4.1f}%  PF={pf(rr):4.2f}")

# ---------- 5. BUY vs WATCH, and score WITHIN regime ----------
print("\n=== 5. SCORE BANDS WITHIN EACH REGIME (regime-controlled) ===")
for reg in ['risk_on_trending','bull','risk_on_choppy','neutral','risk_off_trending']:
    sub=[t for t in resolved if t.get('regime4')==reg]
    if len(sub)<30: continue
    print(f"  regime={reg} (n={len(sub)})")
    for lo,hi in [(60,70),(70,80),(80,90),(90,101)]:
        rr=[t for t in sub if (v:=num(t.get('score'))) is not None and lo<=v<hi]
        if len(rr)<8: continue
        w,n=wr(rr)
        print(f"    {lo}-{hi}  n={n:4d}  WR={w:4.1f}%  PF={pf(rr):4.2f}")

# ---------- 6. BUY-only edge + alpha ----------
print("\n=== 6. ACTIONABLE (BUY) vs WATCH ===")
buys=[t for t in resolved if t.get('verdict')=='BUY']
watch=[t for t in resolved if t.get('verdict')=='WATCH']
for label,rr in [('BUY',buys),('WATCH',watch),('ALL',resolved)]:
    w,n=wr(rr)
    avg=st.mean([out_pct(t) for t in rr if out_pct(t) is not None]) if rr else 0
    print(f"    {label:6s} n={n:4d}  WR={w:4.1f}%  PF={pf(rr):4.2f}  avg={avg:+5.2f}%")

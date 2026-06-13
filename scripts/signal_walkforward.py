#!/usr/bin/env python3
"""Walk-forward validation of candidate ranking blends vs current composite score.
Read-only. Decides whether cat+qg's OOS edge is regime/time-robust or a one-month artifact.

Two tests:
  1. IC sign-stability across consecutive time bins, split by regime.
  2. PRACTICAL: per scan-day, rank candidates by blend vs by current score,
     take top tercile, compare realized PF of the picked set.
"""
import json, math
from collections import defaultdict
T = json.load(open('cache/picks_history.json'))['trades']

def num(x):
    try: f=float(x); return f if f==f else None
    except: return None

R = [t for t in T if num(t.get('pct_chg')) is not None and t.get('exit_date') and t.get('run_date')]

# ---- candidate blends (a-priori, mechanism-justified, NO weight fitting) ----
BLENDS = {
    'cat+qg':          {'cat_score':1.0,'qg_score':1.0},
    'cat+qg+0.3tech':  {'cat_score':1.0,'qg_score':1.0,'tech_score':0.3},
    'cat+qg+sm':       {'cat_score':1.0,'qg_score':1.0,'sm_score':0.5},
}
def blend_val(t, w):
    s=0.0
    for k,wt in w.items():
        v=num(t.get(k))
        if v is None: return None
        s += wt*v
    return s
def cand_val(t, name):
    if name=='CURRENT': return num(t.get('score'))
    return blend_val(t, BLENDS[name])

def ic(rows, name):
    xs=[];ys=[]
    for t in rows:
        x=cand_val(t,name); y=num(t.get('pct_chg'))
        if x is not None and y is not None: xs.append(x);ys.append(y)
    n=len(xs)
    if n<20: return None,n
    mx=sum(xs)/n;my=sum(ys)/n
    sx=sum((a-mx)**2 for a in xs);sy=sum((a-my)**2 for a in ys)
    if sx==0 or sy==0: return None,n
    return sum((a-mx)*(b-my) for a,b in zip(xs,ys))/math.sqrt(sx*sy),n
def pf(rows):
    g=sum(v for t in rows if (v:=num(t.get('pct_chg')))>0)
    l=sum(-v for t in rows if (v:=num(t.get('pct_chg')))<0)
    return g/l if l>0 else 9.99

# ---------- TEST 1: rolling time bins x regime ----------
BINS = [('2026-04-06','2026-04-17'),('2026-04-18','2026-04-30'),
        ('2026-05-01','2026-05-12'),('2026-05-13','2026-05-23'),
        ('2026-05-24','2026-06-05')]
def in_bin(t,lo,hi): return lo<=t['run_date']<=hi
def regseg(rows,kind):
    if kind=='trend': return [t for t in rows if t.get('regime4') in ('risk_on_trending','bull')]
    if kind=='chop':  return [t for t in rows if t.get('regime4')=='risk_on_choppy']
    return rows

print("=== TEST 1: IC across 5 consecutive time bins (sign-stability) ===")
cands=['CURRENT']+list(BLENDS)
for kind,lbl in [('all','ALL REGIMES'),('chop','CHOPPY only'),('trend','TRENDING only')]:
    print(f"\n  -- {lbl} --")
    hdr="  ".join(f"{b[0][5:]}" for b in BINS)
    print(f"  {'blend':16s} {hdr}")
    for c in cands:
        cells=[]
        for lo,hi in BINS:
            seg=regseg([t for t in R if in_bin(t,lo,hi)],kind)
            r,n=ic(seg,c)
            cells.append(f"{r:+.2f}" if r is not None else " -- ")
        # sign-stability flag
        vals=[float(x) for x in cells if x.strip()!='--']
        pos=sum(1 for v in vals if v>0.02)
        flag = ' STABLE+' if pos>=len(vals)-1 and len(vals)>=4 else ''
        print(f"  {c:16s} {'   '.join(cells)}{flag}")

# ---------- TEST 2: practical per-day top-tercile ranking ----------
print("\n=== TEST 2: PRACTICAL — rank each scan-day's candidates, take top tercile ===")
print("    (does ranking by the blend pick a better-PF subset than ranking by score?)")
byday=defaultdict(list)
for t in R: byday[t['run_date']].append(t)
days=[d for d,rows in byday.items() if len(rows)>=6]
print(f"    {len(days)} scan-days with >=6 candidates\n")
def topk_pool(name, frac=0.34):
    pool=[]
    for d in days:
        rows=[t for t in byday[d] if cand_val(t,name) is not None]
        if len(rows)<6: continue
        rows.sort(key=lambda t: cand_val(t,name), reverse=True)
        k=max(1,int(len(rows)*frac))
        pool += rows[:k]
    return pool
print(f"    {'rank-by':16s} {'n':>5s} {'WR':>6s} {'PF':>6s} {'avg%':>7s}")
for name in cands:
    pool=topk_pool(name)
    n=len(pool); w=sum(1 for t in pool if num(t['pct_chg'])>0)
    avg=sum(num(t['pct_chg']) for t in pool)/n if n else 0
    print(f"    {name:16s} {n:5d} {w/n*100:5.1f}% {pf(pool):6.2f} {avg:+6.2f}%")
# baseline: bottom tercile by score (what we'd avoid)
def botk_pool(name, frac=0.34):
    pool=[]
    for d in days:
        rows=[t for t in byday[d] if cand_val(t,name) is not None]
        if len(rows)<6: continue
        rows.sort(key=lambda t: cand_val(t,name))
        k=max(1,int(len(rows)*frac))
        pool += rows[:k]
    return pool
bp=botk_pool('CURRENT'); n=len(bp); w=sum(1 for t in bp if num(t['pct_chg'])>0)
print(f"    {'(score BOTTOM)':16s} {n:5d} {w/n*100:5.1f}% {pf(bp):6.2f} {sum(num(t['pct_chg']) for t in bp)/n:+6.2f}%")

# ---------- TEST 3: regime-conditional practical (the proposed design) ----------
print("\n=== TEST 3: REGIME-CONDITIONAL rank (proposed live design) ===")
print("    trending day -> rank by cat+qg+0.3tech ; choppy day -> rank by cat+qg ; top tercile")
pool=[]
for d in days:
    rows=byday[d]
    chop = sum(1 for t in rows if t.get('regime4')=='risk_on_choppy') >= len(rows)/2
    name = 'cat+qg' if chop else 'cat+qg+0.3tech'
    rr=[t for t in rows if cand_val(t,name) is not None]
    if len(rr)<6: continue
    rr.sort(key=lambda t: cand_val(t,name), reverse=True)
    pool += rr[:max(1,int(len(rr)*0.34))]
n=len(pool); w=sum(1 for t in pool if num(t['pct_chg'])>0)
print(f"    regime-conditional top-tercile: n={n}  WR={w/n*100:.1f}%  PF={pf(pool):.2f}  avg={sum(num(t['pct_chg']) for t in pool)/n:+.2f}%")

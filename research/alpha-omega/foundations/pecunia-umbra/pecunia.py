"""Offline economic accounting. All monetary quantities are integer USD micros."""
from fractions import Fraction

def integer(x):
    if type(x) is not int or x < 0: raise ValueError('invalid nonnegative integer')
    return x

def account(schedule, events, outcomes):
    # schedule: ordered paired task IDs; events: unique charge IDs, lane, task or None (upfront), category, actual, shadow.
    if not schedule or len(set(schedule)) != len(schedule): raise ValueError('invalid schedule')
    lanes=('control','beast'); keys={(l,t) for l in lanes for t in schedule}
    seen={}; charges=set(); costs={l:{t:[0,0] for t in [None,*schedule]} for l in lanes}; categories={l:{} for l in lanes}
    for r in outcomes:
        k=(r['lane'],r['task'])
        if k not in keys or k in seen or type(r['success']) is not bool: raise ValueError('invalid outcome')
        seen[k]=r['success']
    if set(seen)!=keys: raise ValueError('missing outcome')
    for e in events:
        l,t,c,i=e['lane'],e['task'],e['category'],e['id']
        if not isinstance(i,str) or not i or i in charges or l not in lanes or (t is not None and (l,t) not in keys): raise ValueError('invalid charge identity')
        if c not in ('acquisition','execution','governance','retention','distribution','adaptation'): raise ValueError('invalid category')
        charges.add(i); a,s=integer(e['actual']),integer(e['shadow'])
        for dest in (costs[l][t],categories[l].setdefault(c,[0,0])): dest[0]+=a; dest[1]+=s
    curves=[]; totals={l:costs[l][None][:] for l in lanes}; successes=dict.fromkeys(lanes,0)
    for t in schedule:
        for l in lanes:
            totals[l]=[a+b for a,b in zip(totals[l],costs[l][t])]; successes[l]+=seen[l,t]
        curves.append({'task':t,'totals':{l:totals[l][:] for l in lanes},'successes':successes.copy()})
    def ratio(a,b): return str(Fraction(a,b)) if b else None
    def crossing(j):
        # First observed prefix with equal positive success counts and no greater cost, sustained through final prefix.
        good=[r['successes']['beast']==r['successes']['control']>0 and r['totals']['beast'][j]<=r['totals']['control'][j] for r in curves]
        return next((i+1 for i in range(len(good)) if all(good[i:])),None)
    return {'totals':totals,'categories':categories,'successes':successes,'cost_per_success':{l:[ratio(v,successes[l]) for v in totals[l]] for l in lanes},'observed_sustained_break_even':{'actual':crossing(0),'shadow':crossing(1)},'curves':curves,'billing_reconciled':False,'scientific_authorization':False}

def allocate(amount, weights):
    """Largest remainder allocation, deterministic ties by string ID; conserves charge exactly."""
    integer(amount)
    if not weights or any(not isinstance(k,str) for k in weights): raise ValueError('invalid weights')
    total=sum(integer(v) for v in weights.values())
    if not total: raise ValueError('zero weights')
    shares={k:Fraction(amount*v,total) for k,v in weights.items()}; out={k:int(v) for k,v in shares.items()}
    for k in sorted(shares,key=lambda k:(-(shares[k]-out[k]),k))[:amount-sum(out.values())]: out[k]+=1
    return out

def depreciation(purchase,salvage,lifetime_seconds,used_seconds):
    for v in (purchase,salvage,lifetime_seconds,used_seconds): integer(v)
    if salvage>purchase or not lifetime_seconds or used_seconds>lifetime_seconds: raise ValueError('invalid depreciation assumptions')
    return Fraction((purchase-salvage)*used_seconds,lifetime_seconds)

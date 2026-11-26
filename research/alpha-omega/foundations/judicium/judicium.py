"""Offline paired cluster bootstrap. No authenticated evidence admission."""
import json, random, math, argparse
from collections import defaultdict

def evaluate(schedule, rows, *, draws=10000, seed=20261126, margin=.02, saving=.20, min_clusters=30):
    if type(draws) is not int or draws<1000 or min_clusters<2 or not 0<=margin<1 or not 0<saving<1: raise ValueError('invalid protocol')
    expected={}
    for x in schedule:
        k=x['task']
        if not isinstance(k,str) or not k or k in expected or not isinstance(x['cluster'],str) or not x['cluster']: raise ValueError('invalid schedule')
        expected[k]=x['cluster']
    seen={}
    for r in rows:
        k=(r['task'],r['lane'])
        if k in seen or r['task'] not in expected or r['lane'] not in ('control','beast') or r['cluster']!=expected[r['task']]: raise ValueError('unexpected or duplicate row')
        if type(r['success']) is not bool or type(r['cost_micros']) is not int or r['cost_micros']<0: raise ValueError('invalid outcome')
        seen[k]=r
    if not expected or len(seen)!=2*len(expected): raise ValueError('incomplete pairs')
    groups=defaultdict(lambda:[0]*5)
    for task,cluster in sorted(expected.items()):
        a,b=(seen[task,l] for l in ('control','beast'))
        g=groups[cluster]
        for i,v in enumerate((1,int(a['success']),int(b['success']),a['cost_micros'],b['cost_micros'])): g[i]+=v
    gs=[groups[k] for k in sorted(groups)]
    def metrics(g):
        n,a,b,c,d=map(sum,zip(*g))
        return (b-a)/n, (1-d*a/(c*b)) if a and b and c else None, {'tasks':n,'control_successes':a,'beast_successes':b,'control_cost_micros':c,'beast_cost_micros':d}
    diff, gain, totals=metrics(gs)
    result={'clusters':len(gs),'totals':totals,'success_difference':diff,'cost_per_success_saving':gain,'verdict':'INDETERMINATUM','scientific_authorization':False,'protocol':dict(draws=draws,seed=seed,margin=margin,saving=saving,min_clusters=min_clusters)}
    if len(gs)<min_clusters or gain is None: return result
    rng=random.Random(seed); ds=[]; es=[]; undefined=0
    for _ in range(draws):
        d,e,_=metrics(rng.choices(gs,k=len(gs))); ds.append(d)
        if e is None: undefined+=1
        else: es.append(e)
    result['undefined_bootstrap_draws']=undefined
    def interval(xs):
        xs.sort(); return [xs[math.floor(.025*(len(xs)-1))],xs[math.ceil(.975*(len(xs)-1))]]
    di=interval(ds); result['success_interval']=di
    if undefined: return result
    ei=interval(es); result['saving_interval']=ei
    if di[0]>=-margin and ei[0]>=saving: result['verdict']='THRESHOLDS_SUPPORTED'
    elif di[1]<-margin or ei[1]<saving: result['verdict']='THRESHOLDS_CONTRADICTED'
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('input'); args=p.parse_args()
    with open(args.input) as f: x=json.load(f)
    print(json.dumps(evaluate(x['schedule'],x['rows'],**x.get('protocol',{})),indent=2,allow_nan=False))

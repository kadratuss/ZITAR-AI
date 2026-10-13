"""Explain inactivity from aligned recorded decisions; no model training."""
from collections import Counter


def diagnose(report):
    seeds=report['seed_results']
    traces=[seed['test'].get('decisions',[]) for seed in seeds]
    if len(traces)<2 or not traces[0] or any(len(t)!=len(traces[0]) for t in traces):
        raise ValueError('complete aligned seed traces required')
    disagree=unanimous_cash=unanimous_exposure=0
    for points in zip(*traces):
        if len({p['signal_date'] for p in points})!=1:raise ValueError('unaligned traces')
        actions={p['action'] for p in points}
        if len(actions)>1:disagree+=1
        elif actions=={0}:unanimous_cash+=1
        else:unanimous_exposure+=1
    combination=report['combination']['test']
    rule=combination['zitar_hourly']['decisions']
    combined=combination['combined']['decisions']
    if len(rule)!=len(traces[0]) or len(combined)!=len(rule):raise ValueError('incomplete arm traces')
    blocked=0
    for points,r,c in zip(zip(*traces),rule,combined):
        if r['signal_date']!=c['signal_date'] or r['signal_date']!=points[0]['signal_date']:
            raise ValueError('unaligned arm traces')
        if r['action']!=0 and c['action']==0:blocked+=1
    return dict(run=report['run'],market=report['market'],bars_decisions=len(rule),
        seeds={str(s['seed']):dict(Counter(str(p['action']) for p in t)) for s,t in zip(seeds,traces)},
        disagreement_bars=disagree,unanimous_cash_bars=unanimous_cash,
        unanimous_exposure_bars=unanimous_exposure,
        rsi_exposure_bars=sum(p['action']!=0 for p in rule),
        combined_exposure_bars=sum(p['action']!=0 for p in combined),
        rsi_exposure_to_combined_cash_bars=blocked,
        action_labels={'0':'cash','1':'long','2':'short'},
        limitation='Recorded decisions explain behavior; they do not establish why PPO learned it.')

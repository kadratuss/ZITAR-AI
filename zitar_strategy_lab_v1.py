"""Continuous measurement of a frozen, prospective paired hypothesis. No promotion."""
from copy import deepcopy
from zitar_futures_paper_engine_v1 import fresh, number, digest

NAMES=('ZITAR_CONTROL_V1','ZITAR_SELECTIVE_V1')
SPEC={'version':'SELECTIVITY_EXPERIMENT_V1','hypothesis':'Matching 1h direction and 15m symbol reentry cooldown may reduce churn losses',
      'control':'Unmodified shared MTF rules','candidate':'Require matching closed 1h majority; wait 15m after symbol exit',
      'promotion':'NONE','screening_min_days':7,'screening_min_closed_each':50,
      'goal':'Consistency toward daily net 3–4%; never automatically increase leverage'}

def ensure_experiment(state,ms):
    if 'strategy_lab_spec' not in state:
        if any(n in state['books'] for n in NAMES):raise ValueError('PARTIAL_LAB_STATE')
        state['strategy_lab_spec']=dict(spec=deepcopy(SPEC),hash=digest(SPEC),started_ms=ms)
        for name in NAMES:
            book=deepcopy(fresh(ms,[])['books']['BASELINE'])
            book.update(started_ms=ms,cursors={},evaluations={},rules=deepcopy(SPEC))
            state['books'][name]=book
    if state['strategy_lab_spec']['hash']!=digest(SPEC):raise ValueError('LAB_POLICY_CHANGED')
    if not all(n in state['books'] for n in NAMES):raise ValueError('MISSING_LAB_ACCOUNT')

def summarize(state,ms,errors,names=NAMES,spec=SPEC,spec_key='strategy_lab_spec'):
    report={'updated_ms':ms,'spec':spec,'started_ms':state[spec_key]['started_ms'],'books':{},'automatic_promotion':False}
    for name in names:
        b=state['books'][name];closed=b['closed'];groups={}
        for row in closed:
            key=row.get('timeframe','unknown');g=groups.setdefault(key,dict(closed=0,wins=0,net='0'))
            g['closed']+=1;g['wins']+=number(row['net_pnl'])>0;g['net']=str(number(g['net'])+number(row['net_pnl']))
        report['books'][name]=dict(equity=b['equity'],net_return_pct=str((number(b['equity'])/10000-1)*100),closed=len(closed),
            fees=b['fees_total'],drawdown_pct=b['max_drawdown_pct'],by_timeframe=groups)
    control,candidate=[report['books'][n] for n in names]
    report['candidate_minus_control_pct']=str(number(candidate['net_return_pct'])-number(control['net_return_pct']))
    bad=bool(errors) or any(state['books'][n].get('accounting_pending') or any(q in ['MONITORING_GAP','MISSING_MARK_OR_FUNDING','FUNDING_PROVISIONAL'] for q in state['books'][n]['quality']) or any(any(q in ['MONITORING_GAP','MISSING_MARK_OR_FUNDING','FUNDING_PROVISIONAL'] for q in d['quality']) for d in state['books'][n]['daily']) for n in names)
    enough=ms-report['started_ms']>=7*86400000 and min(control['closed'],candidate['closed'])>=50
    report['status']='DATA_QUALITY_REVIEW' if bad else 'READY_FOR_REVIEW_NOT_PROVEN' if enough else 'COLLECTING_EVIDENCE'
    return report

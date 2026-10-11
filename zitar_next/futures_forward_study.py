"""Collect fresh bars and replay fixed models in a separate research study.

No registry changes, paper activation, broker orders or model retraining.
Ineligible candidates may be observed diagnostically, never promoted by this tool.
"""
import argparse
import json
import hashlib
import importlib.metadata
from datetime import datetime,timedelta,timezone
from pathlib import Path
from zitar_next.store import atomic,digest,stamp,workspace
from zitar_next.market import fetch
from zitar_next.decision_diagnostics import diagnose


def featured_history(records,as_of_ms):
    from causal_indicators import add_indicators
    rows=add_indicators(records,as_of_ms=as_of_ms)
    closes=[]
    for row in rows:
        closes.append(row['close'])
        row['sma50']=sum(closes[-50:])/50 if len(closes)>=50 else None
    return rows


def code_identity():
    base=Path(__file__).resolve().parent.parent
    paths=['causal_indicators.py','research_environment.py','online_research_pipeline.py',
           'chronological_split.py','online_finrl_data.py']
    paths+=['zitar_next/'+name+'.py' for name in ('worker','combination','paper','futures','finrl_pipeline','store','market','forward_study')]
    paths+=['zitar_next/vendor/zitar_hourly_signals.py']
    return dict(files={name:hashlib.sha256((base/name).read_bytes()).hexdigest() for name in paths},
        dependencies={name:importlib.metadata.version(name) for name in ('numpy','gymnasium','torch','stable-baselines3')})


def verify_code_lock(study,current):
    path=Path(study)/'code-lock.json'
    if path.is_symlink(): raise ValueError('code lock symlink rejected')
    if not path.exists():
        status=Path(study)/'forward-status.json'
        if status.exists() and any(r.get('collected_bars',0)>0 for r in json.loads(status.read_text()).get('reports',[])):
            raise ValueError('cannot retroactively pin code after fresh evidence')
        atomic(path,dict(identity=current,sha256=digest(current),created=stamp()))
    locked=json.loads(path.read_text())
    if locked['sha256']!=digest(locked['identity']) or locked['identity']!=current:
        raise ValueError('frozen study code or dependencies changed')
    return locked['sha256']


def select_fresh(records,start,end):
    rows=[r for r in records if start<=r['date']<end]
    dates=[datetime.strptime(r['date'],'%Y-%m-%d %H:%M:%S') for r in rows]
    if len(set(dates))!=len(dates) or any(b-a!=timedelta(hours=1) for a,b in zip(dates,dates[1:])):
        raise ValueError('fresh history has gaps or duplicates')
    return rows


def cycle(root,study):
    root=workspace(root);study=Path(study).resolve(strict=True)
    manifest=json.loads((study/'protocol.json').read_text())
    if digest(manifest['protocol'])!=manifest['protocol_sha256']:raise ValueError('protocol mismatch')
    code_sha=verify_code_lock(study,code_identity())
    created=datetime.fromisoformat(manifest['created_utc'])
    start=(created.replace(minute=0,second=0,microsecond=0)+timedelta(hours=1)).astimezone(timezone.utc)
    end=start+timedelta(days=30)
    fmt=lambda d:d.strftime('%Y-%m-%d %H:%M:%S')
    reports=[]
    from zitar_next.finrl_pipeline import load_run
    from zitar_next.worker import env_for
    from zitar_next.futures import evaluate
    from zitar_next.paper import vote
    from zitar_next.combination import rule_map,blend
    from causal_indicators import add_indicators
    for market,item in manifest['candidates'].items():
        if market!='futures':continue
        report,old,scaler,models=load_run(root,item['report']['run'])
        # Byte hashes frozen at registration; refuse altered models or run artifacts.
        import hashlib
        for name,expected in item['artifacts'].items():
            path=root/'runs'/report['run']/name
            if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
                raise ValueError('frozen artifact changed')
        diagnostics=diagnose(report)
        atomic(study/('diagnostics-'+market+'.json'),diagnostics)
        state_path=study/('bars-'+market+'.json')
        previous=json.loads(state_path.read_text()) if state_path.exists() else dict(records=[])
        now=datetime.now(timezone.utc)
        snapshot=fetch(market,report['symbol'],count=1000) if now<end else None
        by_date={r['date']:r for r in previous['records']}
        if snapshot:
            for row in snapshot['records']:
                existing=by_date.get(row['date'])
                if existing is not None and digest(existing)!=digest(row):raise ValueError('historical bar revised')
                by_date[row['date']]=row
        records=[by_date[d] for d in sorted(by_date)]
        fresh=select_fresh(records,fmt(start),fmt(end))
        if fresh and fresh[0]['date']!=fmt(start):raise ValueError('study start missing; no silent truncated evaluation')
        atomic(state_path,dict(records=records,real_orders=False))
        featured=featured_history(records,as_of_ms=int(now.timestamp()*1000)) if records else []
        rows=select_fresh(featured,fmt(start),fmt(end))
        if any(not r['features_ready'] or r['sma50'] is None for r in rows):raise ValueError('fresh features not ready')
        result=dict(market=market,symbol=report['symbol'],run=report['run'],
            start_utc=fmt(start),end_utc=fmt(end),collected_bars=len(rows),
            scope='DIAGNOSTIC_RESEARCH_ONLY_NOT_APPROVED_PAPER',real_orders=False,
            protocol_sha256=manifest['protocol_sha256'],code_sha256=code_sha,model_frozen=True,
            status='WAITING_FOR_NEW_BARS',diagnostics=diagnostics)
        if len(rows)>=2:
            current=dict(market=market,records=records)
            rules=rule_map(current,market,'RSI14')
            ai=lambda obs,row:vote(models,obs)
            rule=lambda obs,row:rules[row['date']]
            weight=item['report']['selected_ai_weight']
            combined=lambda obs,row:blend(rule(obs,row),ai(obs,row),market,weight)
            policies=dict(zitar_hourly=rule,learned_ppo=ai,combined=combined,cash=lambda obs,row:0,
                long=lambda obs,row:1,sma=lambda obs,row:1 if row['sma']>row['sma50'] else (2 if market=='futures' else 0))
            result.update(status='COLLECTING_FRESH_EVIDENCE',
                test={name:evaluate(env_for(market,rows,scaler),fn) for name,fn in policies.items()},
                stress={name:evaluate(env_for(market,rows,scaler,True),fn) for name,fn in policies.items()})
        if now>=end:
            result['status']='WINDOW_ENDED_REVIEW_REQUIRED' if len(rows)==720 else 'WINDOW_ENDED_INCOMPLETE_DATA'
        reports.append(result)
    atomic(study/'forward-status.json',dict(updated=stamp(),reports=reports,real_orders=False,
        automatic_activation=False,warning='Provisional results; every cycle includes a terminal simulated close.'))
    return reports


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',required=True);parser.add_argument('--study',required=True)
    args=parser.parse_args()
    import fcntl
    with (Path(args.study)/'study.lock').open('a') as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        print(json.dumps([dict(market=r['market'],status=r['status'],bars=r['collected_bars'],
            diagnostics=r['diagnostics']) for r in cycle(args.root,args.study)]))

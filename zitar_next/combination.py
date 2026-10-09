"""Isolated hourly ZITAR + PPO decision bridge and validation-only blend selection."""
import json
from datetime import datetime,timezone
from pathlib import Path
from zitar_next.vendor.zitar_hourly_signals import signals
from zitar_next.store import atomic,digest,stamp,workspace

WEIGHTS=(.25,.5,.75)


def blend(rule_action,ai_action,market,ai_weight):
    allowed=(0,1) if market=='spot' else (0,1,2) if market=='futures' else ()
    if not allowed or type(rule_action) is not int or type(ai_action) is not int or rule_action not in allowed or ai_action not in allowed or ai_weight not in WEIGHTS:
        raise ValueError('bounded actions/market/blend required')
    direction=lambda action: (0,1,-1)[action]
    score=(1-ai_weight)*direction(rule_action)+ai_weight*direction(ai_action)
    return 1 if score>=.5 else 2 if market=='futures' and score<=-.5 else 0


def rule_map(snapshot,market):
    """Invoke exact pinned pure signal functions on each closed prefix."""
    result={};candles=[]
    for row in snapshot['records']:
        opened=int(datetime.strptime(row['date'],'%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc).timestamp()*1000)
        candles.append([opened,row['open'],row['high'],row['low'],row['close'],row['volume'],opened+3599999])
        if len(candles)<60:
            continue
        sig=signals(candles[-150:],opened+3600000)
        # Selected spot RSI14 roster is long below 30, otherwise flat.
        # Futures uses the explicit ZITAR_V1 hourly confluence reference.
        d=sig['RSI14'] if market=='spot' else sig['ZITAR_V1']
        result[row['date']]=1 if d==1 else 2 if market=='futures' and d==-1 else 0
    return result


def choose(validation_results):
    if set(validation_results)!=set(WEIGHTS):
        raise ValueError('complete fixed validation grid required')
    # Fixed risk penalty and stable tie break; final test never enters selection.
    return max(WEIGHTS,key=lambda w:(validation_results[w]['return_pct']-.5*validation_results[w]['max_drawdown_pct'],-abs(w-.5)))


def compare(root,run):
    from zitar_next.finrl_pipeline import load_run
    from online_research_pipeline import prepare
    from zitar_next.worker import env_for
    from zitar_next.futures import evaluate
    from zitar_next.paper import vote
    root=workspace(root)
    report,snapshot,scaler,models=load_run(root,run)
    market=report['market'];parts=prepare(snapshot);rules=rule_map(snapshot,market)
    rule=lambda obs,row:rules[row['date']]
    ai=lambda obs,row:vote(models,obs)
    policy=lambda w:lambda obs,row:blend(rule(obs,row),ai(obs,row),market,w)
    validation={w:evaluate(env_for(market,parts['validation'],scaler),policy(w)) for w in WEIGHTS}
    selected=choose(validation)
    policies=dict(zitar_hourly=rule,learned_ppo=ai,combined=policy(selected))
    test={name:evaluate(env_for(market,parts['test'],scaler),fn,trace=True) for name,fn in policies.items()}
    stress={name:evaluate(env_for(market,parts['test'],scaler,True),fn) for name,fn in policies.items()}
    issues=['INTEGRATION_REPLAY_NOT_FRESH_HOLDOUT','COMBINED_WALK_FORWARD_NOT_YET_VALIDATED']
    if test['combined']['return_pct']<=max(test['zitar_hourly']['return_pct'],test['learned_ppo']['return_pct']):
        issues.append('COMBINATION_DID_NOT_IMPROVE_RETURN')
    result=dict(schema='ZITAR_AI_COMBINATION_V1',run=run,market=market,symbol=report['symbol'],updated=stamp(),
                selected_ai_weight=selected,selection='validation return minus 0.5 * drawdown; fixed three weights',
                validation=[dict(ai_weight=w,metrics=v) for w,v in validation.items()],test=test,stress=stress,
                snapshot_sha256=report['snapshot_sha256'],source_proposal=report['proposal_id'],
                bridge_sha256=digest(Path(__file__).read_text(encoding='utf-8')),
                rules_sha256=digest(Path(__file__).with_name('vendor').joinpath('zitar_hourly_signals.py').read_text(encoding='utf-8')),
                eligible=False,issues=issues,real_orders=False,production_connected=False,
                scope='hourly rule signals + PPO; common USDT simulator; not full runtime parity',
                limitations=['Existing held-out period has already been inspected; replay is integration evidence only.',
                             'Does not reproduce multi-coin roster, radar, 5m/15m confluence, quote-depth or production stops.',
                             'Original TRY spot accounting is not converted; only RSI14 rule is replayed on USDT.',
                             'No production imports, model replacement, registry approval or real execution.'])
    folder=root/'combination_reports';folder.mkdir(exist_ok=True)
    if folder.is_symlink():
        raise ValueError('report directory symlink rejected')
    atomic(folder/(run+'.json'),result)
    return result


def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',required=True);p.add_argument('--run',required=True)
    args=p.parse_args();r=compare(args.root,args.run)
    print(json.dumps(dict(market=r['market'],selected_ai_weight=r['selected_ai_weight'],
                         returns={k:v['return_pct'] for k,v in r['test'].items()},eligible=r['eligible'],issues=r['issues'])))


if __name__=='__main__':
    main()


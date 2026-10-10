"""Independent RSI-entry-filter experiment. No registry or broker writes."""
import argparse
import hashlib
import json
from pathlib import Path
import gymnasium as gym
import numpy as np
from stable_baselines3 import PPO
from stable_baselines3.common.env_checker import check_env
from online_research_pipeline import prepare
from research_environment import TrainScaler
from zitar_next.combination import rule_map
from zitar_next.futures import evaluate
from zitar_next.history_archive import fetch_history
from zitar_next.store import atomic, digest, stamp, workspace
from zitar_next.worker import env_for, assess

PROTOCOL = dict(schema='RSI_ENTRY_FILTER_V1',symbols=['BTCUSDT','ETHUSDT'],
                markets=['spot','futures'],bars=8760,interval='1h',seeds=[42,73],
                budgets=[2048,8192],rule='RSI14',initial_usdt=10000,
                selection='mean validation return minus 0.5 * drawdown; smaller budget wins ties',
                action='0 rejects NEW entry, 1 permits RSI entry; existing RSI exits unchanged',
                fresh_holdout=False,real_orders=False,production_connected=False)


def filtered_action(rule, current, permit):
    if rule not in (0,1,2) or current not in (0,1,2) or permit not in (0,1):
        raise ValueError('bounded rule, position and binary permission required')
    # Keep an existing position while RSI holds it, even if permission changes.
    # Flat RSI always exits. A reversed RSI exits and needs permission to reenter.
    return rule if rule == current or permit else 0


def prepare_filter(snapshot,market):
    parts=prepare(snapshot)
    rules=rule_map(snapshot,market,'RSI14')
    # Indicator readiness precedes the pinned RSI signal's 60-bar warmup.
    # Never invent a flat signal for an unavailable prefix.
    for partition in ('train','validation','test'):
        old=parts[partition]
        rows=[row for row in old if row['date'] in rules]
        if len(rows)<100 or (partition!='train' and len(rows)!=len(old)):
            raise ValueError('incomplete RSI signal coverage')
        parts[partition]=rows
        parts['metadata']['partitions'][partition].update(retained_rows=len(rows),retained_timestamps=len(rows),
            first_date=rows[0]['date'],last_date=rows[-1]['date'],signal_warmup_excluded=len(old)-len(rows))
    return parts,rules


class EntryFilterEnv(gym.Wrapper):
    def __init__(self, env, rules, market):
        super().__init__(env)
        self.rules, self.market = rules, market
        self.action_space = gym.spaces.Discrete(2)
        self.observation_space = gym.spaces.Box(-10,10,shape=(env.observation_space.shape[0]+1,),dtype=np.float32)

    @property
    def records(self): return self.env.records
    @property
    def index(self): return self.env.index
    @property
    def account(self): return self.env.account
    @property
    def curve(self): return self.env.curve

    def observation(self, obs):
        rule = self.rules[self.records[self.index]['date']]
        return np.concatenate((obs,np.asarray([(0,1,-1)[rule]],dtype=np.float32)))

    def reset(self, *, seed=None, options=None):
        obs,info = self.env.reset(seed=seed,options=options)
        return self.observation(obs),info

    def step(self, action):
        if not self.action_space.contains(action):
            raise ValueError('binary permission required')
        current = (1 if self.account.qty else 0) if self.market == 'spot' else (
            1 if self.account.position and self.account.position['direction'] == 1 else
            2 if self.account.position else 0)
        rule = self.rules[self.records[self.index]['date']]
        target = filtered_action(rule,current,int(action))
        obs,reward,done,truncated,info = self.env.step(target)
        return self.observation(obs),reward,done,truncated,dict(info,executed_target=target)


def run(root, name):
    import re
    if not re.fullmatch(r'[a-z0-9-]{1,64}',name):
        raise ValueError('simple experiment name required')
    root = workspace(root)
    parent = root/'entry_filter_studies'
    parent.mkdir(exist_ok=True)
    if parent.is_symlink(): raise ValueError('symlink output rejected')
    output = parent/name
    output.mkdir(exist_ok=False)
    protocol = dict(PROTOCOL,created=stamp())
    atomic(output/'protocol.json',dict(protocol,sha256=digest(protocol)))
    results = []
    status = dict(state='RUNNING',updated=stamp(),completed=[],real_orders=False)
    atomic(output/'status.json',status)
    for market in PROTOCOL['markets']:
        for symbol in PROTOCOL['symbols']:
            status.update(current=market+' '+symbol,phase='DATA',updated=stamp())
            atomic(output/'status.json',status)
            snapshot = fetch_history(market,symbol,PROTOCOL['bars'])
            folder = output/(market+'-'+symbol)
            folder.mkdir()
            atomic(folder/'snapshot.json',snapshot)
            parts,rules = prepare_filter(snapshot,market)
            scaler = TrainScaler().fit(parts['train'])
            atomic(folder/'scaler.json',dict(mean=scaler.mean.tolist(),scale=scaler.scale.tolist()))
            wrapped = lambda partition,stress=False: EntryFilterEnv(env_for(market,parts[partition],scaler,stress),rules,market)
            check_env(wrapped('train'),warn=True)
            choices, saved = [],{}
            for budget in PROTOCOL['budgets']:
                models, metrics = [],[]
                for seed in PROTOCOL['seeds']:
                    status.update(phase='TRAINING',budget=budget,seed=seed,updated=stamp())
                    atomic(output/'status.json',status)
                    model = PPO('MlpPolicy',wrapped('train'),seed=seed,device='cpu',n_steps=128,
                                batch_size=64,n_epochs=4,policy_kwargs=dict(net_arch=[32,32]),verbose=0)
                    model.learn(total_timesteps=budget)
                    model.save(folder/('ppo-'+str(budget)+'-'+str(seed)))
                    metric = evaluate(wrapped('validation'),lambda obs,row,m=model:int(m.predict(obs,deterministic=True)[0]))
                    models.append(model); metrics.append(dict(seed=seed,metrics=metric))
                score = sum(m['metrics']['return_pct']-.5*m['metrics']['max_drawdown_pct'] for m in metrics)/len(metrics)
                choices.append(dict(budget=budget,validation=metrics,score=score))
                saved[budget] = models
            selected = max(choices,key=lambda c:(c['score'],-c['budget']))['budget']
            # Persist selection BEFORE the first final-test evaluation.
            atomic(folder/'selection.json',dict(selected_budget=selected,choices=choices,updated=stamp()))
            models = saved[selected]
            seed_results = []
            for seed, model in zip(PROTOCOL['seeds'],models):
                policy = lambda obs,row,m=model:int(m.predict(obs,deterministic=True)[0])
                seed_results.append(dict(seed=seed,test=evaluate(wrapped('test'),policy),stress=evaluate(wrapped('test',True),policy)))
            unanimous = lambda obs,row:int(all(int(m.predict(obs,deterministic=True)[0])==1 for m in models))
            test = evaluate(wrapped('test'),unanimous)
            stress = evaluate(wrapped('test',True),unanimous)
            baselines = dict(rsi=evaluate(env_for(market,parts['test'],scaler),lambda obs,row:rules[row['date']]),
                             cash=evaluate(env_for(market,parts['test'],scaler),lambda obs,row:0),
                             long=evaluate(env_for(market,parts['test'],scaler),lambda obs,row:1),
                             sma=evaluate(env_for(market,parts['test'],scaler),lambda obs,row:int(row['close']>row['sma50'])))
            reference_stress = evaluate(env_for(market,parts['test'],scaler,True),lambda obs,row:rules[row['date']])
            issues = assess(seed_results+[dict(seed='unanimous',test=test,stress=stress)],baselines,parts['test'])
            issues += ['HISTORICAL_EXPLORATION_NOT_FRESH_HOLDOUT','ENTRY_FILTER_WALK_FORWARD_NOT_VALIDATED','PRODUCTION_PARITY_NOT_VALIDATED']
            report = dict(schema='RSI_ENTRY_FILTER_RESULT_V1',market=market,symbol=symbol,updated=stamp(),
                          snapshot_sha256=digest(snapshot),protocol_sha256=digest(protocol),partitions=parts['metadata'],
                          selected_budget=selected,validation=choices,seed_results=seed_results,
                          unanimous=dict(test=test,stress=stress),baselines=baselines,rsi_stress=reference_stress,
                          delta_vs_rsi_pct=test['return_pct']-baselines['rsi']['return_pct'],
                          eligible=False,issues=sorted(set(issues)),real_orders=False,production_connected=False,
                          limitations=['Research simulator, not full production stop/portfolio parity.',
                                       'Historical final test has been examined; cannot establish fresh future performance.',
                                       'Small budget may not traverse all training rows; no reward shaping or profitable-trade guarantee.'])
            report['artifacts'] = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.is_file()}
            atomic(folder/'report.json',report)
            results.append(report)
            status['completed'].append(market+' '+symbol)
            status.update(phase='DATASET_COMPLETE',updated=stamp())
            atomic(output/'status.json',status)
    summary = dict(state='COMPLETE',updated=stamp(),results=results,real_orders=False,eligible=False)
    atomic(output/'summary.json',summary)
    atomic(output/'status.json',dict(status,state='COMPLETE',updated=stamp()))
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',required=True);p.add_argument('--name',required=True)
    args=p.parse_args()
    import re
    if not re.fullmatch(r'[a-z0-9-]{1,64}',args.name):
        raise ValueError('simple experiment name required')
    try:
        result=run(args.root,args.name)
        print(json.dumps(dict(state=result['state'],datasets=len(result['results']),real_orders=False)))
    except FileExistsError:
        raise
    except Exception:
        output=workspace(args.root)/'entry_filter_studies'/args.name
        # Do not overwrite an existing completed experiment on a duplicate name.
        if output.is_dir() and (output/'status.json').is_file():
            old=json.loads((output/'status.json').read_text())
            if old.get('state')!='COMPLETE':
                atomic(output/'status.json',dict(old,state='FAILED',updated=stamp()))
        raise


if __name__=='__main__': main()

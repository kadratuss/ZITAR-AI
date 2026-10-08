"""Opt-in standalone periodic retraining; recommendations never auto-activate."""
import argparse
import hashlib
import json
import time
import uuid
from pathlib import Path
import numpy as np
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.env_checker import check_env
from causal_indicators import add_indicators
from online_research_pipeline import prepare
from research_environment import CandleEnv, TrainScaler
from zitar_next.futures import FuturesEnv, evaluate
from zitar_next.market import fetch
from zitar_next.store import Registry, WorkerLock, atomic, digest, init, stamp, workspace

POLICY = dict(version=1,minimum_test_bars=150,minimum_trades=20,maximum_drawdown_pct=5.,
              minimum_advantage_pct=1.,minimum_seeds=2,stress_must_be_positive=True,
              approval='HUMAN_REQUIRED',real_orders=False)


def env_for(market,rows,scaler,stress=False):
    multiplier = 2 if stress else 1
    if market == 'spot':
        return CandleEnv(rows,scaler,fee=.001*multiplier,slippage=.001*multiplier)
    if market == 'futures':
        return FuturesEnv(rows,scaler,fee=.0005*multiplier,slippage=.0002*multiplier)
    raise ValueError('invalid market')


class History(BaseCallback):
    def __init__(self,market,parts,scaler,status,root,interval=512):
        super().__init__()
        self.market,self.parts,self.scaler = market,parts,scaler
        self.status,self.root,self.interval = status,root,interval
        self.points,self.episodes = [],[]
        self.total_reward = 0.

    def record(self):
        step = self.model.num_timesteps
        if self.points and self.points[-1]['step'] == step:
            return
        policy = lambda obs,row:int(self.model.predict(obs,deterministic=True)[0])
        point = dict(step=step)
        for part in ('train','validation'):
            point[part] = evaluate(env_for(self.market,self.parts[part],self.scaler),policy)
        self.points.append(point)
        self.status.update(state='TRAINING',step=step,updated=stamp(),learning=dict(checkpoints=self.points,episodes=self.episodes))
        atomic(self.root/'status.json',self.status)

    def _on_rollout_start(self):
        if self.model.num_timesteps % self.interval == 0:
            self.record()

    def _on_training_end(self):
        self.record()

    def _on_step(self):
        self.total_reward += float(self.locals['rewards'][0])
        if self.locals['dones'][0]:
            self.episodes.append(dict(step=self.num_timesteps,reward=self.total_reward))
            self.total_reward = 0.
        return True


def assess(seed_results,baselines,rows,previous_test_end=None):
    issues = []
    seed_count = len({r['seed'] for r in seed_results if 'seed' in r}) if any('seed' in r for r in seed_results) else len(seed_results)
    if seed_count < POLICY['minimum_seeds']:
        issues.append('AT_LEAST_TWO_SEEDS_REQUIRED')
    if len(rows) < POLICY['minimum_test_bars']:
        issues.append('TEST_SAMPLE_TOO_SHORT')
    if previous_test_end and rows[0]['date'] <= previous_test_end:
        issues.append('TEST_PERIOD_OVERLAPS_PREVIOUS_ROUND')
    best = max(v['return_pct'] for v in baselines.values())
    for result in seed_results:
        metric = result['test']
        numbers = [metric['return_pct'],metric['max_drawdown_pct'],metric['trades'],result['stress']['return_pct']]
        if not all(np.isfinite(v) for v in numbers):
            raise ValueError('nonfinite candidate metrics')
        if metric['trades'] < POLICY['minimum_trades']:
            issues.append('INSUFFICIENT_TRADES')
        if metric['max_drawdown_pct'] > POLICY['maximum_drawdown_pct']:
            issues.append('DRAWDOWN_BUDGET_EXCEEDED')
        if metric['return_pct'] < best+POLICY['minimum_advantage_pct']:
            issues.append('BASELINE_ADVANTAGE_NOT_MET')
        if result['stress']['return_pct'] <= 0:
            issues.append('COST_STRESS_NOT_POSITIVE')
        if metric.get('liquidations',0):
            issues.append('MODEL_LIQUIDATION_OCCURRED')
    return sorted(set(issues))


def walk_forward(root,market,snapshot,steps,seeds,test_start):
    """Three disjoint earlier test windows; final held-out test is excluded."""
    featured=add_indicators(snapshot['records'],as_of_ms=snapshot['server_time_ms'])
    closes=[];ready=[]
    for row in featured:
        closes.append(row['close'])
        row['sma50']=sum(closes[-50:])/50 if len(closes)>=50 else None
        if row['features_ready'] and row['sma50'] is not None and row['date']<test_start:
            ready.append(row)
    width=200
    first=len(ready)-3*width
    if first-202<300:
        return dict(folds=[],issues=['LONGER_WALK_FORWARD_HISTORY_REQUIRED'])
    folds=[];issues=[]
    for fold in range(3):
        start=first+fold*width
        train=ready[:start-202]
        validation=ready[start-201:start-1]
        test=ready[start:start+width]
        scaler=TrainScaler().fit(train)
        baseline=evaluate(env_for(market,test,scaler),lambda obs,row:0)
        candidates=[];models=[]
        for seed in seeds:
            atomic(root/'status.json',dict(state='WALK_FORWARD',market=market,fold=fold+1,seed=seed,updated=stamp(),real_orders=False))
            model=PPO('MlpPolicy',env_for(market,train,scaler),seed=seed,device='cpu',n_steps=128,batch_size=64,n_epochs=4,
                      policy_kwargs={'net_arch':[32,32]},verbose=0)
            model.learn(total_timesteps=steps)
            policy=lambda obs,row:int(model.predict(obs,deterministic=True)[0])
            metric=evaluate(env_for(market,test,scaler),policy)
            stress=evaluate(env_for(market,test,scaler,True),policy)
            validation_metric=evaluate(env_for(market,validation,scaler),policy)
            candidates.append(dict(seed=seed,test=metric,stress=stress,validation=validation_metric))
            models.append(model)
        from zitar_next.paper import vote
        ensemble_policy=lambda obs,row:vote(models,obs)
        ensemble=dict(test=evaluate(env_for(market,test,scaler),ensemble_policy),
                      stress=evaluate(env_for(market,test,scaler,True),ensemble_policy))
        long=evaluate(env_for(market,test,scaler),lambda obs,row:1)
        sma=evaluate(env_for(market,test,scaler),lambda obs,row:1 if row['sma']>row['sma50'] else (2 if market=='futures' else 0))
        issues.extend('WALK_FORWARD_'+v for v in assess(candidates+[ensemble],dict(cash=baseline,long=long,sma=sma),test))
        folds.append(dict(train_end=train[-1]['date'],validation_start=validation[0]['date'],validation_end=validation[-1]['date'],
                          test_start=test[0]['date'],test_end=test[-1]['date'],seeds=candidates,ensemble=ensemble,baselines=dict(cash=baseline,long=long,sma=sma)))
    return dict(folds=folds,issues=sorted(set(issues)),selection='fixed policy and seeds; no best-fold or seed selection')


def train_round(root,market,symbol,steps=2048,seeds=(42,73),snapshot=None):
    root = workspace(root)
    if type(steps) is not int or not 128 <= steps <= 100000 or not seeds or len(set(seeds)) != len(seeds) or len(seeds)>5 or any(type(s) is not int or s<0 or s>2**31-1 for s in seeds):
        raise ValueError('bounded steps and unique seeds required')
    if market not in ('spot','futures'):
        raise ValueError('invalid market')
    import torch
    torch.set_num_threads(1)
    state_path = root/'cursor.json'
    cursors = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {}
    key = market+':'+symbol
    previous = cursors.get(key,{})
    atomic(root/'status.json',dict(state='FETCHING',market=market,symbol=symbol,updated=stamp(),real_orders=False))
    snapshot = snapshot if snapshot is not None else fetch(market,symbol)
    if snapshot.get('market') != market or snapshot.get('interval') != '1h' or {r['tic'] for r in snapshot['records']} != {symbol}:
        raise ValueError('snapshot market/symbol/interval mismatch')
    cutoff = snapshot['closed_before_ms']
    if cutoff < previous.get('cutoff',0):
        raise ValueError('market cutoff moved backwards')
    # Compare overlapping immutable history before allowing a new training round.
    old_rows = previous.get('record_hashes',{})
    if old_rows:
        overlap = [r for r in snapshot['records'] if r['date'] in old_rows]
        if not overlap or any(digest(r) != old_rows[r['date']] for r in overlap):
            raise ValueError('disconnected or changed closed history')
    if cutoff == previous.get('cutoff') and len(snapshot['records'])==len(old_rows):
        atomic(root/'status.json',dict(state='WAITING_NEW_CANDLE',market=market,symbol=symbol,updated=stamp(),real_orders=False))
        return None
    parts = prepare(snapshot)
    scaler = TrainScaler().fit(parts['train'])
    run_id = market+'-'+uuid.uuid4().hex
    folder = root/'runs'/run_id
    folder.mkdir(exist_ok=False)
    atomic(folder/'snapshot.json',snapshot)
    scaler_data = dict(mean=scaler.mean.tolist(),scale=scaler.scale.tolist())
    atomic(folder/'scaler.json',scaler_data)
    results,models = [],[]
    status = dict(state='TRAINING',market=market,symbol=symbol,run=run_id,requested_steps=steps,
                  interval='1h',leverage=3 if market=='futures' else 1,margin_mode='ISOLATED' if market=='futures' else 'SPOT',real_orders=False)
    for seed in seeds:
        status.update(seed=seed)
        env = env_for(market,parts['train'],scaler)
        check_env(env,warn=True)
        model = PPO('MlpPolicy',env,seed=seed,device='cpu',n_steps=128,batch_size=64,n_epochs=4,
                    policy_kwargs={'net_arch':[32,32]},verbose=0)
        history = History(market,parts,scaler,status,root)
        model.learn(total_timesteps=steps,callback=history)
        atomic(root/'status.json',dict(status,state='EVALUATING',updated=stamp()))
        policy = lambda obs,row:int(model.predict(obs,deterministic=True)[0])
        metric = evaluate(env_for(market,parts['test'],scaler),policy,trace=True)
        stress = evaluate(env_for(market,parts['test'],scaler,True),policy)
        model.save(str(folder/('ppo-'+str(seed))))
        model_hash = hashlib.sha256((folder/('ppo-'+str(seed)+'.zip')).read_bytes()).hexdigest()
        results.append(dict(seed=seed,steps=model.num_timesteps,model_sha256=model_hash,test=metric,stress=stress,
                            learning=dict(checkpoints=history.points,episodes=history.episodes)))
        models.append(model)
    rows = parts['test']
    baselines = dict(cash=evaluate(env_for(market,rows,scaler),lambda obs,row:0),
                     long=evaluate(env_for(market,rows,scaler),lambda obs,row:1),
                     sma=evaluate(env_for(market,rows,scaler),lambda obs,row:1 if row['sma']>row['sma50'] else (2 if market=='futures' else 0)))
    from zitar_next.paper import vote
    ensemble_policy=lambda obs,row:vote(models,obs)
    ensemble=dict(test=evaluate(env_for(market,rows,scaler),ensemble_policy,trace=True),
                  stress=evaluate(env_for(market,rows,scaler,True),ensemble_policy))
    issues = assess(results+[ensemble],baselines,rows,previous.get('test_end'))
    forward = walk_forward(root,market,snapshot,steps,seeds,rows[0]['date'])
    issues = sorted(set(issues+forward['issues']))
    hypothesis=dict(market=market,interval='1h',algorithm='PPO_MLP',
                    claim='Learned hourly exposure improves net risk-controlled return versus cash, long and SMA',
                    failure_criteria=POLICY,generated_rules=False)
    body = dict(schema='ZITAR_NEXT_PROPOSAL_V1',run=run_id,market=market,symbol=symbol,interval='1h',
                hypothesis=hypothesis,hypothesis_id=digest(hypothesis),
                leverage=3 if market=='futures' else 1,margin_mode='ISOLATED' if market=='futures' else 'SPOT',
                sizing='10% equity collateral per isolated position' if market=='futures' else 'full equity long/flat',
                strategy='PPO_MLP',seeds=list(seeds),snapshot_sha256=digest(snapshot),scaler_sha256=digest(scaler_data),split=parts['metadata'],
                policy=POLICY,seed_results=results,ensemble=ensemble,baselines=baselines,walk_forward=forward,issues=issues,eligible=not issues,
                paper_only=True,real_orders=False,automatic_activation=False,
                limitations=['bounded hourly history; long-term live forward results not yet available',
                             'fixed slippage and full fills; no order book execution',
                             'futures maintenance/liquidation fees are model assumptions, not exchange tiers',
                             'pessimistic intrabar mark excursion before intrabar funding',
                             'all seeds are one candidate family; no best-seed selection'])
    identity = Registry(root).propose(body)
    atomic(folder/'report.json',dict(body,proposal_id=identity))
    cursors[key] = dict(cutoff=cutoff,test_end=rows[-1]['date'],record_hashes={r['date']:digest(r) for r in snapshot['records']})
    atomic(state_path,cursors)
    atomic(root/'status.json',dict(status,state='COMPLETED',updated=stamp(),proposal=identity,issues=issues,eligible=not issues))
    from zitar_next.bridge import summary
    atomic(root/'next_summary.json',summary(root))
    return body


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',required=True)
    parser.add_argument('--init',action='store_true')
    parser.add_argument('--steps',type=int,default=2048)
    parser.add_argument('--symbol',default='BTCUSDT')
    parser.add_argument('--cycles',type=int,default=1,help='0: ongoing; positive: bounded rounds')
    parser.add_argument('--pause',type=float,default=300)
    args = parser.parse_args()
    if args.cycles<0 or not 60 <= args.pause <= 86400:
        parser.error('cycles >=0 and pause 60..86400 required')
    root = init(args.root) if args.init else workspace(args.root)
    with WorkerLock(root):
        cycle = 0
        market_path=root/'market_status.json'
        market_status=json.loads(market_path.read_text(encoding='utf-8')) if market_path.exists() else {}
        while args.cycles==0 or cycle<args.cycles:
            for market in ('spot','futures'):
                try:
                    snapshot = fetch(market,args.symbol)
                    from zitar_next.paper import tick
                    paper = tick(root,market,args.symbol,snapshot)
                    body = train_round(root,market,args.symbol,args.steps,snapshot=snapshot)
                    market_status[market]=dict(state='COMPLETED' if body else 'WAITING_NEW_CANDLE',updated=stamp(),paper=paper['state'],error=None)
                    print(json.dumps(dict(market=market,state='COMPLETED' if body else 'WAITING_NEW_CANDLE',issues=body['issues'] if body else [])),flush=True)
                except Exception as exc:
                    market_status[market]=dict(state='ERROR',updated=stamp(),error=str(exc))
                    atomic(root/'status.json',dict(state='ERROR',market=market,error=str(exc),updated=stamp(),real_orders=False))
                    print(json.dumps(dict(market=market,error=str(exc))),flush=True)
                atomic(market_path,market_status)
            from zitar_next.bridge import summary
            atomic(root/'next_summary.json',summary(root))
            cycle += 1
            if args.cycles==0 or cycle<args.cycles:
                time.sleep(args.pause)


if __name__ == '__main__':
    main()

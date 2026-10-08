"""Approved Next-only shadow account; records simulated fills after bar close."""
import hashlib
import json
import re
from datetime import datetime,timedelta
import numpy as np
from stable_baselines3 import PPO
from causal_indicators import add_indicators
from research_environment import PaperAccount,TrainScaler
from zitar_next.futures import IsolatedAccount
from zitar_next.finrl_bridge import ZitarWeightStrategy
from zitar_next.store import Registry,atomic,digest,stamp,workspace


def approved(root,market,symbol):
    root=workspace(root)
    registry=Registry(root).all()
    scope=market+':'+symbol+':1h'
    active=next((r for r in registry['active'] if r['scope']==scope),None)
    if not active:
        return None
    item=next(p for p in registry['proposals'] if p['id']==active['proposal'])
    if item['state']!='ACTIVE_PAPER' or item['body'].get('eligible') is not True:
        raise ValueError('approved active paper proposal required')
    body=item['body']
    run=body['run']
    if not re.fullmatch('(spot|futures)-[a-f0-9]{32}',run):
        raise ValueError('invalid run identity')
    folder=root/'runs'/run
    if folder.is_symlink() or folder.resolve().parent!=(root/'runs').resolve():
        raise ValueError('invalid model directory')
    for seed in body['seed_results']:
        path=folder/('ppo-'+str(seed['seed'])+'.zip')
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=seed['model_sha256']:
            raise ValueError('approved model hash mismatch')
    # Scaler and snapshot are bound to the approval through snapshot and scaler digest.
    if (folder/'scaler.json').is_symlink():
        raise ValueError('scaler symlink rejected')
    scaler_data=json.loads((folder/'scaler.json').read_text(encoding='utf-8'))
    if digest(scaler_data)!=body['scaler_sha256']:
        raise ValueError('approved scaler hash mismatch')
    scaler=TrainScaler()
    scaler.mean=np.asarray(scaler_data['mean'])
    scaler.scale=np.asarray(scaler_data['scale'])
    models=[PPO.load(str(folder/('ppo-'+str(r['seed'])+'.zip')),device='cpu') for r in body['seed_results']]
    return item,scaler,models


def vote(models,observation):
    actions=[int(m.predict(observation,deterministic=True)[0]) for m in models]
    # Unanimity prevents choosing a best seed after seeing test outcomes.
    return actions[0] if len(set(actions))==1 else 0


def tick(root,market,symbol,snapshot):
    root=workspace(root)
    if snapshot['market']!=market or snapshot['interval']!='1h' or {r['tic'] for r in snapshot['records']}!={symbol}:
        raise ValueError('paper market mismatch')
    selected=approved(root,market,symbol)
    if selected is None:
        return dict(state='WAITING_HUMAN_APPROVAL',market=market,real_orders=False)
    item,scaler,models=selected
    featured=add_indicators(snapshot['records'],as_of_ms=snapshot['server_time_ms'])
    if not featured[-1]['features_ready']:
        raise ValueError('features not ready')
    path=root/('paper-'+market+'-'+symbol+'.json')
    state=json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
    # On an explicitly approved version change, archive old paper account and start flat.
    if state and state['proposal']!=item['id']:
        archive=root/('archived-paper-'+market+'-'+state['proposal']+'.json')
        if not archive.exists():
            atomic(archive,state)
        state=None
    account=IsolatedAccount() if market=='futures' else PaperAccount()
    if state:
        account.__dict__.update(state['account'])
        old=state['last_date']
        overlap=[r for r in snapshot['records'] if r['date']==old]
        if len(overlap)!=1 or digest(overlap[0])!=state['last_record_hash']:
            raise ValueError('paper history changed or disconnected')
        fresh=[r for r in featured if r['date']>old]
        if fresh and datetime.strptime(fresh[0]['date'],'%Y-%m-%d %H:%M:%S')!=datetime.strptime(old,'%Y-%m-%d %H:%M:%S')+timedelta(hours=1):
            raise ValueError('paper candle gap')
        for row in fresh:
            before=account.trades
            if market=='futures':
                account.advance(row,state['pending'])
                mark=row['mark_close']
            else:
                account.execute(state['pending'],row['open'])
                mark=row['close']
            equity=account.equity(mark)
            p=account.position if market=='futures' else None
            position=p['direction']*p['qty']*mark/equity if p and equity else (account.qty*mark/equity if market=='spot' and equity else 0.)
            observation=np.concatenate((scaler.transform(row),np.clip([account.cash/max(equity,1e-12),position],-10,10).astype(np.float32)))
            next_action=vote(models,observation)
            state['events'].append(dict(date=row['date'],event='SIMULATED_AFTER_CLOSE',action=state['pending'],fills=account.trades-before,equity=equity,next_action=next_action))
            state['pending']=next_action
        state['events']=state['events'][-500:]
    else:
        row=featured[-1]
        observation=np.concatenate((scaler.transform(row),np.asarray([1.,0.],dtype=np.float32)))
        state=dict(proposal=item['id'],market=market,symbol=symbol,interval='1h',pending=vote(models,observation),events=[],
                   started=stamp(),mode='SHADOW_AFTER_CLOSE_NO_BROKER',real_orders=False)
        fresh=[]
    last=featured[-1]
    intent=ZitarWeightStrategy(market).generate_weights(dict(symbol=symbol,date=last['date'],action=state['pending']))
    state.update(state='PAPER_OBSERVING' if fresh else 'WAITING_NEW_CANDLE',account=account.__dict__,last_date=last['date'],
                 last_record_hash=digest(snapshot['records'][-1]),updated=stamp(),entry_exposure_intent=float(intent.weights.iloc[0]['weight']))
    atomic(path,state)
    return state

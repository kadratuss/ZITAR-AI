"""3x isolated margin research model; not exchange liquidation parity."""
import math
from datetime import datetime, timezone
import gymnasium as gym
import numpy as np
from research_environment import FEATURE_KEYS


class IsolatedAccount:
    leverage = 3
    def __init__(self, initial=10000., fraction=.1, fee=.0005, slippage=.0002, maintenance=.005, liquidation_fee=.005):
        if not all(math.isfinite(v) for v in (initial, fraction, fee, slippage, maintenance, liquidation_fee)) or initial <= 0 or not 0 < fraction <= .1 or not all(0 <= v < .1 for v in (fee, slippage, maintenance, liquidation_fee)):
            raise ValueError('invalid isolated model parameters')
        self.initial = self.cash = initial
        self.fraction, self.fee, self.slippage = fraction, fee, slippage
        self.maintenance, self.liquidation_fee = maintenance, liquidation_fee
        self.position = None
        self.trades = self.liquidations = 0
        self.funding_total = self.fees_total = 0.

    def equity(self, mark):
        p = self.position
        return self.cash + (max(0., p['margin']+p['direction']*p['qty']*(mark-p['entry'])) if p else 0.)

    def close(self, price, liquidated=False):
        p = self.position
        if not p:
            return
        execution = price*(1-self.slippage*p['direction'])
        cost = p['qty']*execution*(self.fee+(self.liquidation_fee if liquidated else 0))
        self.cash += max(0., p['margin']+p['direction']*p['qty']*(execution-p['entry'])-cost)
        self.fees_total += cost
        self.position = None
        self.trades += 1
        self.liquidations += int(liquidated)

    def target(self, direction, price):
        if direction not in (-1, 0, 1) or not math.isfinite(price) or price <= 0:
            raise ValueError('invalid target/price')
        if self.position and self.position['direction'] != direction:
            self.close(price)
        if direction and not self.position:
            margin = self.cash*self.fraction/(1+self.leverage*self.fee)
            if margin <= 0:
                return
            entry = price*(1+self.slippage*direction)
            qty = margin*self.leverage/entry
            cost = qty*entry*self.fee
            self.cash -= margin+cost
            self.fees_total += cost
            self.position = dict(direction=direction, entry=entry, qty=qty, margin=margin)
            self.trades += 1

    def bar(self, row):
        p = self.position
        if not p:
            return
        # Pessimistic OHLC ordering: adverse mark excursion before intrabar funding.
        adverse = row['mark_low'] if p['direction'] == 1 else row['mark_high']
        value = p['margin']+p['direction']*p['qty']*(adverse-p['entry'])
        threshold = p['qty']*adverse*(self.maintenance+self.liquidation_fee)
        if value <= threshold:
            self.close(adverse, True)
            return
        for event in row['funding']:
            payment = -p['direction']*p['qty']*float(event['markPrice'])*float(event['fundingRate'])
            p['margin'] += payment
            self.funding_total += payment
        mark = row['mark_close']
        if p['margin']+p['direction']*p['qty']*(mark-p['entry']) <= p['qty']*mark*(self.maintenance+self.liquidation_fee):
            self.close(mark, True)

    def advance(self,row,action):
        opened = int(datetime.strptime(row['date'],'%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc).timestamp()*1000)
        p = self.position
        if p:
            for event in row['funding']:
                if event['fundingTime'] == opened:
                    payment = -p['direction']*p['qty']*float(event['markPrice'])*float(event['fundingRate'])
                    p['margin'] += payment
                    self.funding_total += payment
        if p and p['margin']+p['direction']*p['qty']*(row['mark_open']-p['entry']) <= p['qty']*row['mark_open']*(self.maintenance+self.liquidation_fee):
            self.close(row['mark_open'],True)
        else:
            self.target((0,1,-1)[int(action)],row['open'])
        self.bar(dict(row,funding=[e for e in row['funding'] if e['fundingTime']>opened]))


class FuturesEnv(gym.Env):
    metadata = {'render_modes': []}
    def __init__(self, records, scaler, fee=.0005, slippage=.0002):
        if len(records) < 2 or len({r['tic'] for r in records}) != 1:
            raise ValueError('one symbol and two bars required')
        if any(b['date'] <= a['date'] for a,b in zip(records, records[1:])):
            raise ValueError('chronological bars required')
        for row in records:
            if any(not math.isfinite(row[k]) or row[k] <= 0 for k in ('mark_open','mark_high','mark_low','mark_close')) or row['mark_low'] > min(row['mark_open'],row['mark_close']) or row['mark_high'] < max(row['mark_open'],row['mark_close']):
                raise ValueError('valid futures mark OHLC required')
            if not isinstance(row['funding'], list):
                raise ValueError('funding events required')
            opened = int(datetime.strptime(row['date'],'%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc).timestamp()*1000)
            previous = opened-1
            for event in row['funding']:
                rate,price = float(event['fundingRate']),float(event['markPrice'])
                t = event['fundingTime']
                if type(t) is not int or not previous < t < opened+3600000 or not math.isfinite(rate) or not math.isfinite(price) or price <= 0:
                    raise ValueError('invalid or duplicate funding event')
                previous = t
        self.records, self.scaler, self.fee, self.slippage = records, scaler, fee, slippage
        self.action_space = gym.spaces.Discrete(3)
        self.observation_space = gym.spaces.Box(-10,10,shape=(len(FEATURE_KEYS)+2,),dtype=np.float32)
        self.done = True

    def _obs(self):
        row = self.records[self.index]
        equity = max(1e-12,self.account.equity(row['mark_close']))
        p = self.account.position
        exposure = p['direction']*p['qty']*row['mark_close']/equity if p else 0.
        return np.concatenate((self.scaler.transform(row),np.clip([self.account.cash/equity,exposure],-10,10).astype(np.float32)))

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self.index, self.done = 0, False
        self.account = IsolatedAccount(fee=self.fee,slippage=self.slippage)
        self.curve = [self.account.initial]
        return self._obs(),{}

    def step(self, action):
        if self.done or not self.action_space.contains(action):
            raise ValueError('reset required or invalid action')
        previous = self.curve[-1]
        self.index += 1
        row = self.records[self.index]
        self.account.advance(row,action)
        self.done = self.index == len(self.records)-1
        if self.done:
            self.account.close(row['close'])
        equity = self.account.equity(row['mark_close'])
        self.curve.append(equity)
        return self._obs(),(equity-previous)/self.account.initial,self.done,False,dict(equity=equity,trades=self.account.trades,
                          liquidations=self.account.liquidations,funding=self.account.funding_total,fees=self.account.fees_total)


def evaluate(env, policy, trace=False):
    obs,_ = env.reset()
    done, decisions = False,[]
    while not done:
        i = env.index
        action = int(policy(obs,env.records[i]))
        before = env.account.trades
        obs,_,done,_,info = env.step(action)
        if trace:
            decisions.append(dict(signal_date=env.records[i]['date'],execution_date=env.records[env.index]['date'],
                                  action=action,fills=info['trades']-before,equity=info['equity'],terminal=done))
    curve = np.asarray(env.curve)
    peaks = np.maximum.accumulate(curve)
    result = dict(return_pct=float((curve[-1]/curve[0]-1)*100),max_drawdown_pct=float(np.max((peaks-curve)/peaks)*100),
                  trades=info['trades'],final_equity=float(curve[-1]),transitions=len(curve)-1)
    result.update({k:info[k] for k in ('funding','fees','liquidations') if k in info})
    if trace:
        result['decisions'] = decisions
    return result

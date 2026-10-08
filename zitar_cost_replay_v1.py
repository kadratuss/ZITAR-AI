"""Read-only execution replay and bounded public depth observation."""
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import re
import urllib.request
import urllib.parse

D = Decimal


def number(x):
    value = D(str(x))
    if not value.is_finite():
        raise ValueError('NONFINITE_NUMBER')
    return value


def replay(trades):
    lots, matched, seen = defaultdict(deque), [], set()
    for t in sorted(trades, key=lambda row: datetime.fromisoformat(row['executed_at_utc'])):
        if t['trade_id'] in seen:
            raise ValueError('DUPLICATE_TRADE_ID')
        seen.add(t['trade_id'])
        key = (t['strategy'], t['symbol'])
        q, fill, fee, ref = [number(t[k]) for k in ('quantity','modeled_fill_price','fee_try','reference_price')]
        if min(q, fill, ref) <= 0 or fee < 0:
            raise ValueError('INVALID_TRADE')
        if t['side'] == 'BUY':
            lots[key].append({'row':t,'remaining':q,'original':q})
            continue
        if t['side'] != 'SELL':
            raise ValueError('UNKNOWN_SIDE')
        left, segments, net = q, [], D(0)
        while left > 0:
            if not lots[key]:
                raise ValueError('UNMATCHED_SELL:'+t['trade_id'])
            lot = lots[key][0]
            buy = lot['row']
            take = min(left, lot['remaining'])
            entry_fee = number(buy['fee_try'])*take/lot['original']
            exit_fee = fee*take/q
            modeled = take*(fill-number(buy['modeled_fill_price']))-entry_fee-exit_fee
            reference = take*(ref-number(buy['reference_price']))
            buy_mid=(number(buy['observed_bid'])+number(buy['observed_ask']))/2
            sell_mid=(number(t['observed_bid'])+number(t['observed_ask']))/2
            midpoint=take*(sell_mid-buy_mid)
            segments.append(dict(buy_id=buy['trade_id'], quantity=str(take),
                modeled_net_try=str(modeled), reference_no_fee_slippage_try=str(reference),
                midpoint_no_cost_try=str(midpoint), fee_try=str(entry_fee+exit_fee),
                slippage_try=str(reference-modeled-entry_fee-exit_fee), spread_try=str(midpoint-reference)))
            net += modeled
            lot['remaining']-=take
            left-=take
            if lot['remaining']==0:
                lots[key].popleft()
        logged = number(t['realized_pnl_try'])
        if abs(net-logged)>D('.01'):
            raise ValueError('REALIZED_REPLAY_MISMATCH:'+t['trade_id'])
        matched.append(dict(strategy=key[0], symbol=key[1], sell_id=t['trade_id'],
                            closed_utc=t['executed_at_utc'], modeled_net_try=str(net),
                            logged_realized_try=str(logged), segments=segments))
    strategies={name:{'closed_trades':0,'modeled_net_try':D(0),'reference_no_fee_slippage_try':D(0),
                      'midpoint_no_cost_try':D(0),'fee_try':D(0),'slippage_try':D(0),'spread_try':D(0)}
                for name in sorted({t['strategy'] for t in trades})}
    for closed in matched:
        total=strategies[closed['strategy']]
        total['closed_trades']+=1
        for segment in closed['segments']:
            for key in total:
                if key!='closed_trades': total[key]+=number(segment[key])
    return dict(status='PASS', scope='FIFO, same recorded quantities and timing; not a reinvested counterfactual backtest',
                closed_trades=matched, strategies={k:{n:str(v) if isinstance(v,D) else v for n,v in a.items()}
                                                   for k,a in strategies.items()},
                unmatched_open_lots=sum(len(q) for q in lots.values()),
                limitation='Four or few closes cannot establish a reliable strategy ranking; zero closes means no closed-trade evidence.')


def validate_book(book):
    bids=[[number(x[0]),number(x[1])] for x in book['bids']]
    asks=[[number(x[0]),number(x[1])] for x in book['asks']]
    if not bids or not asks or any(p<=0 or q<=0 for p,q in bids+asks):
        raise ValueError('EMPTY_OR_INVALID_BOOK')
    if any(bids[i][0]<bids[i+1][0] for i in range(len(bids)-1)) or any(asks[i][0]>asks[i+1][0] for i in range(len(asks)-1)):
        raise ValueError('UNSORTED_BOOK')
    if bids[0][0]>asks[0][0]: raise ValueError('CROSSED_BOOK')
    return bids, asks


def walk_quote_buy(asks, budget):
    remaining, qty = number(budget), D(0)
    for price, available in asks:
        spend=min(remaining,price*available)
        qty+=spend/price
        remaining-=spend
        if remaining==0: break
    if remaining>D('1e-18'): return {'status':'INSUFFICIENT_VISIBLE_DEPTH','unfilled_quote_try':str(remaining)}
    return {'status':'FILLED_IN_SNAPSHOT','quantity':str(qty),'vwap':str(number(budget)/qty)}


def walk_base_sell(bids, quantity):
    remaining, proceeds=number(quantity),D(0)
    for price, available in bids:
        take=min(remaining,available)
        proceeds+=take*price
        remaining-=take
        if remaining==0: break
    if remaining>D('1e-18'): return {'status':'INSUFFICIENT_VISIBLE_DEPTH','unfilled_quantity':str(remaining)}
    return {'status':'FILLED_IN_SNAPSHOT','proceeds_try':str(proceeds),'vwap':str(proceeds/number(quantity))}


def analyze_book(book, budgets, fee):
    bids,asks=validate_book(book)
    f=number(fee)
    if not 0<=f<1: raise ValueError('INVALID_FEE')
    result={}
    for budget in budgets:
        budget=number(budget)
        if budget<=0: raise ValueError('INVALID_BUDGET')
        buy=walk_quote_buy(asks,budget/(1+f))
        item={'buy':buy}
        if buy['status']=='FILLED_IN_SNAPSHOT':
            sell=walk_base_sell(bids,number(buy['quantity']))
            item['sell_same_book']=sell
            item['buy_impact_bps']=str((number(buy['vwap'])/asks[0][0]-1)*10000)
            if sell['status']=='FILLED_IN_SNAPSHOT':
                net=number(sell['proceeds_try'])*(1-f)
                item['net_return_pct']=str((net/budget-1)*100)
                item['sell_impact_bps']=str((1-number(sell['vwap'])/bids[0][0])*10000)
        result[str(budget)]=item
    return {'spread_bps':str((asks[0][0]-bids[0][0])/((asks[0][0]+bids[0][0])/2)*10000),
            'scenarios':result,'scope':'Instantaneous same-book roundtrip with fee and visible depth; no extra fixed slippage; not historical execution or guaranteed fill'}


def fetch_depth(symbol):
    if not re.fullmatch('[A-Z0-9]{3,25}',symbol): raise ValueError('INVALID_SYMBOL')
    url='https://api.binance.me/api/v3/depth?'+urllib.parse.urlencode({'symbol':symbol,'limit':100})
    req=urllib.request.Request(url,headers={'User-Agent':'ZITAR-Paper-Research/1.0'})
    with urllib.request.urlopen(req,timeout=6) as response:
        raw=response.read(2_000_001)
        if len(raw)>2_000_000: raise ValueError('RESPONSE_TOO_LARGE')
    book=json.loads(raw)
    if isinstance(book,dict) and 'data' in book: book=book['data']
    return book,hashlib.sha256(raw).hexdigest(),url


def observe_depth(symbols,budgets,fee,fetch=fetch_depth):
    def one(symbol):
        try:
            book,digest,url=fetch(symbol)
            return symbol,dict(status='OK',received_utc=datetime.now(timezone.utc).isoformat(),
                source=url,response_sha256=digest,last_update_id=book.get('lastUpdateId'),
                book=book,analysis=analyze_book(book,budgets,fee))
        except Exception as exc:
            return symbol,dict(status='ERROR',error=str(exc),checked_utc=datetime.now(timezone.utc).isoformat())
    with ThreadPoolExecutor(max_workers=4) as pool:
        return dict(pool.map(one,sorted(set(symbols))))

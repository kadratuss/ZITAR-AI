"""Bounded long-history public GET archive, independent of the hourly worker."""
import math
import re
from datetime import datetime,timezone
from online_finrl_data import _get_json
from zitar_next.market import HOUR, get, parse


def funding_history(symbol,start,cutoff,request=get):
    events=[];cursor=start
    for _ in range(20):
        page=request('/fapi/v1/fundingRate',dict(symbol=symbol,startTime=cursor,endTime=cutoff-1,limit=1000))
        if not isinstance(page,list) or len(page)>1000:
            raise ValueError('invalid funding page')
        previous=events[-1]['fundingTime'] if events else start-1
        for event in page:
            t=event.get('fundingTime')
            rate,price=float(event['fundingRate']),float(event['markPrice'])
            if event.get('symbol')!=symbol or type(t)is not int or not cursor<=t<cutoff or t<=previous or not math.isfinite(rate) or not math.isfinite(price) or price<=0:
                raise ValueError('invalid, repeated or unordered funding event')
            if t-previous>8*HOUR+60000:
                raise ValueError('funding history gap')
            previous=t
        events.extend(page)
        if len(page)<1000: break
        cursor=previous+1
    else: raise ValueError('funding page budget exceeded')
    if not events or cutoff-events[-1]['fundingTime']>8*HOUR+60000:
        raise ValueError('missing or stale funding history')
    return events


def fetch_history(market,symbol,count=8760):
    if market not in ('spot','futures') or symbol not in ('BTCUSDT','ETHUSDT') or type(count)is not int or not 200<=count<=17520:
        raise ValueError('bounded BTC/ETH spot/futures history required')
    now=_get_json('/api/v3/time')['serverTime'] if market=='spot' else get('/fapi/v1/time')['serverTime']
    if type(now)is not int or now<=count*HOUR: raise ValueError('invalid server clock')
    cutoff=now//HOUR*HOUR; start=cutoff-count*HOUR
    rows=[];marks=[]
    for offset in range(0,count,1000):
        size=min(1000,count-offset);opened=start+offset*HOUR
        params=dict(symbol=symbol,interval='1h',startTime=opened,endTime=opened+size*HOUR-1,limit=size)
        request=_get_json if market=='spot' else get
        rows.extend(parse(request('/api/v3/klines' if market=='spot' else '/fapi/v1/klines',params),opened,size,symbol))
        if market=='futures': marks.extend(parse(get('/fapi/v1/markPriceKlines',params),opened,size,symbol))
    if market=='futures':
        events=funding_history(symbol,start,cutoff)
        by_hour={}
        for event in events: by_hour.setdefault(event['fundingTime']//HOUR*HOUR,[]).append(event)
        for i,(row,mark) in enumerate(zip(rows,marks)):
            row.update(mark_open=mark['open'],mark_high=mark['high'],mark_low=mark['low'],mark_close=mark['close'],funding=by_hour.get(start+i*HOUR,[]))
    return dict(source='Binance global spot' if market=='spot' else 'Binance USD-M perpetual',market=market,
                quote_currency='USDT',interval='1h',server_time_ms=now,closed_before_ms=cutoff,records=rows,
                funding_scope='historical paginated events, maximum 8h gap plus 60s tolerance' if market=='futures' else None)

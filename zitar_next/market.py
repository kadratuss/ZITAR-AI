"""Public GET-only spot/perpetual data; separate market identities."""
import json
import math
import re
import time
from urllib.error import HTTPError
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, build_opener
from online_finrl_data import _NoRedirect, _get_json

HOUR = 3600000


def get(path, params=None):
    if path not in ('/fapi/v1/time', '/fapi/v1/klines', '/fapi/v1/markPriceKlines', '/fapi/v1/fundingRate'):
        raise ValueError('public market endpoint required')
    request = Request('https://fapi.binance.com'+path+('?' + urlencode(params) if params else ''),
                      headers={'User-Agent': 'ZITAR-Next-research/1.0'}, method='GET')
    for attempt in range(3):
        try:
            with build_opener(_NoRedirect()).open(request, timeout=20) as response:
                raw = response.read(2000001)
            if len(raw) > 2000000:
                raise ValueError('oversized data response')
            return json.loads(raw)
        except HTTPError as exc:
            code=exc.code
            exc.close()
            if code in (418,429) or code<500 or attempt==2:
                raise RuntimeError('futures public data HTTP '+str(code)+'; stop this cycle; no spot fallback') from exc
        except (OSError,TimeoutError) as exc:
            if attempt==2:
                raise RuntimeError('futures public data unavailable; no spot fallback') from exc
        time.sleep(2**attempt)


def parse(page, start, count, symbol):
    if not isinstance(page, list) or len(page) != count:
        raise ValueError('incomplete candle series')
    records = []
    for i, row in enumerate(page):
        if not isinstance(row, list) or len(row) < 7 or row[0] != start+i*HOUR or row[6] != row[0]+HOUR-1:
            raise ValueError('gapped or unclosed candle series')
        op, hi, lo, cl, volume = map(float, row[1:6])
        if not all(math.isfinite(v) for v in (op, hi, lo, cl, volume)) or min(op, lo, hi, cl) <= 0 or volume < 0 or lo > min(op, cl) or hi < max(op, cl):
            raise ValueError('invalid OHLCV')
        date = datetime.fromtimestamp(row[0]/1000, timezone.utc)
        records.append(dict(date=date.strftime('%Y-%m-%d %H:%M:%S'), tic=symbol,
                            open=op, high=hi, low=lo, close=cl, volume=volume, day=date.weekday()))
    return records


def fetch(market, symbol='BTCUSDT', count=3000):
    if market not in ('spot', 'futures') or not re.fullmatch('[A-Z0-9]{1,20}USDT', symbol) or type(count) is not int or not 200 <= count <= 6000:
        raise ValueError('spot/futures, USDT symbol and 200..6000 hourly bars required')
    now = _get_json('/api/v3/time')['serverTime'] if market=='spot' else get('/fapi/v1/time')['serverTime']
    if type(now) is not int or now <= count*HOUR:
        raise ValueError('invalid server clock')
    cutoff = now//HOUR*HOUR
    start = cutoff-count*HOUR
    records,marks = [],[]
    for offset in range(0,count,1000):
        size=min(1000,count-offset)
        page_start=start+offset*HOUR
        params = dict(symbol=symbol, interval='1h', startTime=page_start, endTime=page_start+size*HOUR-1, limit=size)
        if market=='spot':
            records.extend(parse(_get_json('/api/v3/klines',params),page_start,size,symbol))
        else:
            records.extend(parse(get('/fapi/v1/klines', params),page_start,size,symbol))
            marks.extend(parse(get('/fapi/v1/markPriceKlines', params),page_start,size,symbol))
    if market=='spot':
        return dict(source='Binance global spot',market='spot',quote_currency='USDT',interval='1h',
                    server_time_ms=now,closed_before_ms=cutoff,records=records)
    events = get('/fapi/v1/fundingRate', dict(symbol=symbol, startTime=start, endTime=cutoff-1, limit=1000))
    if not isinstance(events, list) or not events or len(events) >= 1000:
        raise ValueError('funding history missing or truncated')
    previous = start-1
    for event in events:
        t = event['fundingTime']
        rate, price = float(event['fundingRate']), float(event['markPrice'])
        if event['symbol'] != symbol or type(t) is not int or not previous < t < cutoff or t < start or not math.isfinite(rate) or not math.isfinite(price) or price <= 0:
            raise ValueError('invalid funding history')
        # Conservative continuity requirement: varying schedules shorter than 8h work.
        if t-previous > 8*HOUR+60000:
            raise ValueError('funding history gap')
        previous = t
    if cutoff-previous > 8*HOUR+60000:
        raise ValueError('stale funding history')
    for row, mark in zip(records, marks):
        opened = int(datetime.strptime(row['date'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc).timestamp()*1000)
        row.update(mark_open=mark['open'], mark_high=mark['high'], mark_low=mark['low'], mark_close=mark['close'],
                   funding=[e for e in events if opened <= e['fundingTime'] < opened+HOUR])
    return dict(source='Binance USD-M perpetual', market='futures', quote_currency='USDT', interval='1h',
                server_time_ms=now, closed_before_ms=cutoff, records=records,
                funding_scope='public historical events; maximum 8h gap plus 60s timestamp tolerance required')

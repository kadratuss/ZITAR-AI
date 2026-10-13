"""Read-only position chart data. Public market GETs; never changes accounts."""
import json
import math
import re
import time
import threading
from collections import OrderedDict
from urllib.parse import urlencode
from urllib.request import Request, build_opener
from online_finrl_data import _NoRedirect

INTERVALS = {'5m', '15m', '1h', '4h', '1d'}
_cache = OrderedDict()
_lock = threading.Lock()


def read_json(url):
    with build_opener(_NoRedirect()).open(Request(url, method='GET'), timeout=10) as response:
        raw = response.read(20000001)
    if len(raw) > 20000000:
        raise ValueError('response too large')
    return json.loads(raw)


def candles(market, symbol, interval):
    if market != 'futures' or not re.fullmatch(r'[A-Z0-9]{1,24}(?:USDT|TRY)', symbol) or interval not in INTERVALS:
        raise ValueError('invalid chart selection')
    if market == 'futures' and not symbol.endswith('USDT'):
        raise ValueError('futures requires USDT')
    key = market, symbol, interval
    with _lock:
        cached = _cache.get(key)
        if cached and time.time() - cached['fetched_ms']/1000 < 60:
            return cached
    # Same spot exchange API host as the production quote reader. No currency conversion.
    base = 'https://fapi.binance.com/fapi/v1/markPriceKlines'
    page = read_json(base + '?' + urlencode(dict(symbol=symbol, interval=interval, limit=1000)))
    if not isinstance(page, list) or not page or len(page) > 1000:
        raise ValueError('candles unavailable')
    rows = []
    for p in page:
        if not isinstance(p,list) or len(p)<7:raise ValueError('invalid candle row')
        t = int(p[0]); o, h, l, c = map(float, p[1:5])
        if t<0 or not all(math.isfinite(v) and v > 0 for v in (o,h,l,c)) or l > min(o,c) or h < max(o,c) or (rows and t <= rows[-1]['time']):
            raise ValueError('invalid candles')
        rows.append(dict(time=t, open=o, high=h, low=l, close=c, closed=int(p[6]) < time.time()*1000))
    result = dict(market=market, symbol=symbol, interval=interval, rows=rows,
                  price_type='Vadeli mark fiyatı' if market == 'futures' else 'Spot işlem fiyatı', fetched_ms=int(time.time()*1000))
    with _lock:
        _cache[key] = result; _cache.move_to_end(key)
        while len(_cache) > 32:
            _cache.popitem(last=False)
    return result


def normalize(p, market, account, index):
    symbol = p.get('symbol', '')
    if not re.fullmatch(r'[A-Z0-9]{1,24}(?:USDT|TRY)', symbol):
        raise ValueError('invalid position symbol')
    def first(*keys):
        return next((p[k] for k in keys if p.get(k) is not None), None)
    return dict(id=f'{market}:{account}:{symbol}:{index}', market=market, account=account,
                symbol=symbol, currency='TRY' if symbol.endswith('TRY') else 'USDT',
                direction=p.get('direction',1), entry=first('entry','entry_fill_price','modeled_entry'),
                stop=first('trailing_stop','pa_stop','stop_price'), mark=first('mark','live_bid','last_mark_price','bid'),
                quantity=p.get('quantity'), pnl=first('unrealized','unrealized_pnl_try','unrealized_try'),
                opened=first('opened_ms','opened_utc','executed_at'), quote_time=first('quote_ms','quote_received_utc'),
                timeframe=p.get('timeframe','1h'), entry_fee=first('entry_fee','entry_fee_try'), funding=p.get('funding'))


def positions(port):
    rows,errors=[],[]
    try:
        d=read_json(f'http://127.0.0.1:{port}/api/indicator-lab')
        for name,b in d.get('books',{}).items():
            if b.get('market')!='futures' or b.get('retired_ms'):continue
            ps=b.get('positions',{})
            for i,p in enumerate(ps.values()):rows.append(normalize(p,'futures',name,i))
    except (OSError,ValueError,TypeError,KeyError):errors.append('indicator-lab')
    return dict(positions=rows,unavailable=errors,served_ms=int(time.time()*1000),real_orders=False)

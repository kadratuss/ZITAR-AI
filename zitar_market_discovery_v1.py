"""Separate spot TRY / perpetual USDT selection and bounded rotating radar."""
import json,time,urllib.request,urllib.parse,urllib.error,threading,math,http.client
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from zitar_indicator_panel_v1 import analyze
from zitar_full_paper_runtime_v1 import atomic_json
from zitar_paper_supervisor_v1 import FileLock

CONFIG={'spot':{'url':'https://api.binance.me/api/v3/','quote':'TRY','notional':1000},'futures':{'url':'https://fapi.binance.com/fapi/v1/','quote':'USDT','notional':3000}}
STABLE={'USDT','USDC','FDUSD','BUSD','DAI','TUSD','USDP'}
def get(market,endpoint,params=None,timeout=10):
    if market=='spot' and (Path(__file__).parent/'zitar_futures_only.flag').exists():raise ValueError('SPOT_DISABLED_BY_USER')
    if endpoint not in {'exchangeInfo','ticker/24hr','depth','klines'}:raise ValueError('PUBLIC_DATA_ONLY')
    url=CONFIG[market]['url']+endpoint+('?' +urllib.parse.urlencode(params) if params else '')
    for attempt in range(2):
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Zitar-Discovery'}),timeout=timeout) as r:return json.load(r)
        except urllib.error.HTTPError:raise
        except (OSError,TimeoutError,http.client.RemoteDisconnected):
            if attempt:raise
            time.sleep(.5)

def impact(levels,notional):
    if not levels:raise ValueError('EMPTY_BOOK')
    best=float(levels[0][0]);need=notional/best;qty=0;cost=0
    for price,size in levels:
        price=float(price);size=float(size)
        if not math.isfinite(price+size) or price<=0 or size<0:raise ValueError('INVALID_BOOK')
        take=min(need-qty,size);qty+=take;cost+=price*take
        if qty>=need-1e-10:break
    if qty<need-1e-10:return None
    return abs(cost/qty/best-1)*10000

def liquidity(depth,notional):
    bid=float(depth['bids'][0][0]);ask=float(depth['asks'][0][0])
    if not math.isfinite(bid+ask) or bid<=0 or ask<bid:raise ValueError('INVALID_SPREAD')
    spread=(ask-bid)/((ask+bid)/2)*10000
    buy=impact(depth['asks'],notional);sell=impact(depth['bids'],notional)
    reasons=[]
    if spread>20:reasons.append('SPREAD_GT_20BPS')
    if buy is None or sell is None:reasons.append('INSUFFICIENT_DEPTH')
    elif max(buy,sell)>10:reasons.append('IMPACT_GT_10BPS')
    return dict(bid=bid,ask=ask,spread_bps=spread,buy_impact_bps=buy,sell_impact_bps=sell,notional=notional,eligible=not reasons,reasons=reasons)

class Discovery:
    def __init__(self,base):self.base=Path(base);self.cursor={'spot':0,'futures':0};self.meta={};self.meta_at={}
    def scan(self,market):
        now=int(time.time()*1000);cfg=CONFIG[market]
        if market not in self.meta or time.time()-self.meta_at.get(market,0)>3600:
            self.meta[market]=get(market,'exchangeInfo');self.meta_at[market]=time.time()
        eligible={r['symbol'] for r in self.meta[market]['symbols'] if r.get('status')=='TRADING' and r.get('quoteAsset')==cfg['quote'] and r.get('baseAsset') not in STABLE and (market!='futures' or r.get('contractType')=='PERPETUAL') and (market!='spot' or r.get('isSpotTradingAllowed',True))}
        ticks=[r for r in get(market,'ticker/24hr') if r['symbol'] in eligible and math.isfinite(float(r['quoteVolume'])) and float(r['quoteVolume'])>0]
        ticks.sort(key=lambda r:float(r['quoteVolume']),reverse=True);top=ticks[:30]
        rest=ticks[30:];start=self.cursor[market];rotated=(rest[start:]+rest[:start])[:10];self.cursor[market]=(start+10)%max(1,len(rest))
        batch=top+rotated
        def inspect(t):
            symbol=t['symbol'];row=dict(symbol=symbol,volume_24h=float(t['quoteVolume']),scan_ms=int(time.time()*1000),scope='MAIN' if t in top else 'ROTATING_RADAR')
            try:
                depth=get(market,'depth',{'symbol':symbol,'limit':100});row.update(liquidity(depth,cfg['notional']))
                row['depth_ms']=int(time.time()*1000)
                if row['eligible']:
                    bars=get(market,'klines',{'symbol':symbol,'interval':'5m','limit':201})
                    row['analysis']=analyze(bars,int(time.time()*1000))
                    if market=='spot':
                        from zitar_pump_early_v1 import observe
                        row['early_observation']=observe(bars,int(time.time()*1000))
                row['status']='OK'
            except Exception as exc:row.update(status='ERROR',eligible=False,error=str(exc),reasons=['DATA_UNAVAILABLE'])
            return row
        with ThreadPoolExecutor(max_workers=3) as pool:rows=list(pool.map(inspect,batch))
        early=[]
        if market=='spot':
            from zitar_pump_early_v1 import advance
            path=self.base/'zitar_pump_early_v1.json'
            previous=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
            for row in rows:
                if row.get('eligible') and row.get('early_observation'):
                    previous[row['symbol']]=advance(previous.get(row['symbol']),row['early_observation'],now)
            previous={k:v for k,v in previous.items() if now-v.get('updated_ms',0)<3600000}
            atomic_json(path,previous)
            early=[dict(symbol=k,**v) for k,v in previous.items() if v.get('stage') in ('EARLY','CONFIRMED')]
        main=[r['symbol'] for r in rows if r['scope']=='MAIN' and r.get('eligible') and r.get('status')=='OK'][:20]
        return dict(started_ms=now,updated_ms=int(time.time()*1000),quote=cfg['quote'],universe_count=len(ticks),scanned=len(rows),main=main,rows=rows,early_candidates=early,
          radar=[r['symbol'] for r in rows if r.get('analysis',{}).get('radar')],limitations=['30 highest-volume candidates plus 10 rotating symbols per cycle; not every token simultaneously','Depth threshold models 1000 TRY spot / 3000 USDT futures; actual order sizes require recheck','Snapshot polling is not a pump forecast; no automatic execution from this module'])
    def cycle(self):
        result=dict(schema='MARKET_DISCOVERY_V1',generated_ms=int(time.time()*1000),markets={},real_orders=False)
        for market in CONFIG:
            if market=='spot' and (self.base/'zitar_futures_only.flag').exists():continue
            try:result['markets'][market]=self.scan(market)
            except Exception as exc:result['markets'][market]={'status':'ERROR','error':str(exc),'main':[],'rows':[],'radar':[]}
        result['completed_ms']=int(time.time()*1000);atomic_json(self.base/'zitar_market_discovery_v1.json',result);return result
def loop(base):
    lock=FileLock(Path(base)/'zitar_market_discovery_v1.lock')
    if not lock.acquire():return
    try:
        worker=Discovery(base)
        while True:
            try:worker.cycle()
            except Exception as exc:atomic_json(Path(base)/'zitar_market_discovery_error_v1.json',{'ms':int(time.time()*1000),'error':str(exc)})
            time.sleep(60)
    finally:lock.close()
def start_worker(base):threading.Thread(target=loop,args=(base,),daemon=True,name='zitar-discovery').start()

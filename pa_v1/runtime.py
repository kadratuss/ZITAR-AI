"""Independent paper worker; public GET only, no exchange order interface."""
import json,time,threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from .config import Config
from .features import evaluate
from .paper import create,tick
from zitar_candle_cache_v1 import CandleCache
from zitar_market_discovery_v1 import get
from zitar_full_paper_runtime_v1 import atomic_json
from zitar_paper_supervisor_v1 import FileLock
class Worker:
 def __init__(self,base):
  self.base=Path(base);self.path=self.base/'zitar_pa_v1.json';self.c=Config().validate();self.metadata={};self.metadata_at=0
  self.cache=CandleCache(lambda s,i:get('spot','klines',{'symbol':s,'interval':i,'limit':201},timeout=4))
 def cycle(self):
  ms=int(time.time()*1000);c=self.c;errors=[]
  state=json.loads(self.path.read_text(encoding='utf-8-sig')) if self.path.exists() else create(ms,c)
  try:selection=json.loads((self.base/'zitar_market_discovery_v1.json').read_text(encoding='utf-8-sig'))['markets']['spot']
  except (OSError,ValueError,KeyError):selection={}
  selected=set(selection.get('main',[])[:c.top_n]) if 0<=ms-selection.get('updated_ms',0)<=180000 else set()
  if not selected:errors.append('STALE_OR_EMPTY_UNIVERSE')
  if ms-self.metadata_at>3600000:
   try:self.metadata={x['symbol']:x for x in get('spot','exchangeInfo',timeout=4)['symbols']};self.metadata_at=ms
   except Exception:errors.append('METADATA_UNAVAILABLE')
  retained={s for b in state['books'].values() for s in b['positions']};symbols=sorted(selected|retained);raw=self.cache.snapshot(symbols,ms)
  def read(symbol):
   try:
    depth=get('spot','depth',{'symbol':symbol,'limit':100},timeout=4);now=int(time.time()*1000)
    result=dict(depth=depth,quote=dict(time=now,bid=str(depth['bids'][0][0]),ask=str(depth['asks'][0][0]),mark=str(depth['bids'][0][0]),funding_rate='0',next_funding=now+86400000))
    row=self.metadata.get(symbol,{})
    if row.get('status')=='TRADING' and 0<=now-self.metadata_at<=3600000:
     filters={x['filterType']:x for x in row['filters']};lot=filters['LOT_SIZE'];result['contract']=dict(step=lot['stepSize'],min_qty=lot['minQty'],max_qty=lot['maxQty'],min_notional=filters.get('NOTIONAL',filters.get('MIN_NOTIONAL',{})).get('minNotional','0'))
    return symbol,result,None
   except Exception as exc:return symbol,None,type(exc).__name__
  with ThreadPoolExecutor(max_workers=4) as pool:received=list(pool.map(read,symbols))
  market={s:m for s,m,e in received if m is not None};errors.extend(s+':'+e for s,m,e in received if e);now=int(time.time()*1000)
  features={s:evaluate(s,raw.get(s,{}),now,c) for s in symbols}
  for s,f in features.items():
   if s not in selected:f['reasons'].append('OUTSIDE_FRESH_UNIVERSE');f['decision']='NO_TRADE'
   if 'contract' not in market.get(s,{}):f['reasons'].append('METADATA_UNAVAILABLE');f['decision']='NO_TRADE'
  journal=self.base/'outputs/pa_v1';journal.mkdir(parents=True,exist_ok=True)
  with (journal/'observations.jsonl').open('a',encoding='utf-8') as h:h.write(json.dumps(dict(ms=now,config_hash=c.hash(),features=features,market=market),allow_nan=False)+'\n')
  tick(state,market,features,now,c);cache=self.cache.status(raw)
  state.update(errors=errors,cache=cache,state='DEGRADED' if errors or cache['ready_intervals']<cache['expected_intervals'] else 'RUNNING',last_cycle_ms=now)
  atomic_json(self.path,state);return state

def overview(base):
 p=Path(base)/'zitar_pa_v1.json'
 if not p.exists():return dict(state='NOT_STARTED',mode='PAPER',real_orders=False,books={})
 s=json.loads(p.read_text(encoding='utf-8-sig'));s['age_seconds']=(time.time()*1000-s['heartbeat_ms'])/1000
 if s['age_seconds']>60:s['state']='STALE'
 for b in s['books'].values():b.pop('seen',None);b.pop('samples',None);b['decisions']=b['decisions'][-20:]
 return s

def loop(base):
 base=Path(base);lock=FileLock(base/'zitar_pa_v1.lock')
 if not lock.acquire():return
 worker=Worker(base)
 try:
  while True:
   try:worker.cycle()
   except Exception as exc:atomic_json(base/'zitar_pa_v1_error.json',dict(ms=int(time.time()*1000),error=type(exc).__name__+': '+str(exc)))
   time.sleep(15)
 finally:worker.cache.close();lock.close()

def start_worker(base):threading.Thread(target=loop,args=(base,),daemon=True,name='zitar-pa-v1').start()

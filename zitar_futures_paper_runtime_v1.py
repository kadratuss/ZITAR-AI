"""Public-data-only futures paper worker. Uses GET on an explicit market-data allowlist."""
import argparse,json,time,os,urllib.request,urllib.parse,urllib.error,threading,http.client
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from zitar_futures_paper_engine_v1 import fresh,apply_cycle,POLICY,digest
from zitar_full_paper_runtime_v1 import atomic_json
from zitar_paper_supervisor_v1 import FileLock
STATE='zitar_futures_paper_v1.json'
PATHS={'exchangeInfo','premiumIndex','depth','klines','fundingRate','time'}
def get(endpoint,params=None):
 if endpoint not in PATHS:raise ValueError('PUBLIC_DATA_ONLY')
 url='https://fapi.binance.com/fapi/v1/'+endpoint
 if params:url+='?'+urllib.parse.urlencode(params)
 req=urllib.request.Request(url,headers={'User-Agent':'Zitar-Paper-Research'})
 for attempt in range(2):
  try:
   with urllib.request.urlopen(req,timeout=4) as response:return json.load(response)
  except urllib.error.HTTPError:
   # Do not multiply requests after rate limiting or an API rejection.
   raise
  except (urllib.error.URLError,TimeoutError,ConnectionError,http.client.RemoteDisconnected):
   if attempt:raise
   time.sleep(0.3)
def contracts(all_symbols=False):
 from zitar_mtf_research_v2 import FROZEN_21
 bases={s[:-3] for s in FROZEN_21}-{'USDT','USDC','BUSD','DAI','FDUSD','TUSD'}
 result={}
 for row in get('exchangeInfo')['symbols']:
  if (not all_symbols and row['baseAsset'] not in bases) or row['quoteAsset']!='USDT' or row['marginAsset']!='USDT' or row['contractType']!='PERPETUAL' or row['status']!='TRADING':continue
  filters={f['filterType']:f for f in row['filters']};lot=filters.get('MARKET_LOT_SIZE',filters['LOT_SIZE'])
  result[row['symbol']]=dict(step=lot['stepSize'],min_qty=lot['minQty'],max_qty=lot['maxQty'],min_notional=filters.get('MIN_NOTIONAL',{}).get('notional','5'))
 if not result:raise ValueError('NO_VALID_CONTRACTS')
 return result
class Futures:
 def __init__(self,base):
  self.base=Path(base);self.path=self.base/STATE;self.candles={};self.metadata=None;self.metadata_day=None
  from zitar_candle_cache_v1 import CandleCache
  self.signal_cache=CandleCache(lambda symbol,interval:get('klines',{'symbol':symbol,'interval':interval,'limit':501 if interval in ('5m','15m') else 151}))
  from zitar_rsi_timeframes_v1 import Experiment
  self.timeframe_experiment=Experiment(self.base)
  self.signal_pool=self.signal_cache.pool
  self.signal_jobs=self.signal_cache.jobs;self.signal_errors=self.signal_cache.errors
 def signal_snapshot(self,symbols,ms):return self.signal_cache.snapshot(symbols,ms)
 def cycle(self):
  ms=int(time.time()*1000)
  state=json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else None
  metadata_error=None
  if self.metadata is None or self.metadata_day!=ms//86400000:
   try:self.metadata=contracts(all_symbols=True);self.metadata_day=ms//86400000
   except Exception as exc:
    metadata_error=str(exc)
    if self.metadata is None:self.metadata={}
  if state is None:state=fresh(ms,sorted(contracts()))
  from zitar_strategy_selection_v1 import configure, prepare_reset, finish_reset
  configure(self.base,state,'futures',ms)
  from zitar_market_controls_v1 import read as read_market_control
  state['entry_control']=read_market_control(self.base,'futures')
  for book in state['books'].values():book['entries_paused']=state['entry_control']['paused']
  prepare_reset(self.base,state,'futures')
  POLICY['leverage']=state['policy']['leverage']
  from zitar_futures_settings_v1 import consume_request
  state=consume_request(self.base,state,ms)
  if state['policy_hash']!=digest(POLICY):raise ValueError('POLICY_CHANGED_NEW_EXPERIMENT_REQUIRED')
  discovery_path=self.base/'zitar_market_discovery_v1.json'
  try:selection=json.loads(discovery_path.read_text(encoding='utf-8'))['markets']['futures']
  except (OSError,ValueError,KeyError):selection={}
  state['discovery_selection']=selection
  dynamic=set(selection.get('main',[])+selection.get('radar',[])) if 0<=ms-selection.get('updated_ms',0)<=180000 else set()
  retained={p['symbol'] for b in state['books'].values() for p in list(b['positions'].values())+[x for x in b['closed'] if x.get('funding_pending')]}
  symbols=sorted(set(state['universe'])|dynamic|retained,key=lambda symbol:(symbol not in retained,symbol))
  signals_cache=self.signal_snapshot(symbols,ms)
  premium={r['symbol']:r for r in get('premiumIndex')}
  def one(symbol):
   try:
    p=premium[symbol];depth=get('depth',{'symbol':symbol,'limit':100})
    timeframes=signals_cache[symbol] if symbol in self.metadata else {}
    funding_books=list(state['books'].values())+self.timeframe_experiment.books()
    positions=[b['positions'][symbol] for b in funding_books if symbol in b['positions']]
    due=[pos for pos in positions if pos.get('funding_pending') or int(pos['next_funding_ms'])<=ms]+[pos for b in funding_books for pos in b['closed'] if pos['symbol']==symbol and pos.get('funding_pending')]
    funding=[]
    funding_error=None
    try:
     if due:
      funding=get('fundingRate',{'symbol':symbol,'startTime':min(pos['opened_ms'] if pos.get('funding_pending') else max([pos['opened_ms']]+pos['funding_events']) for pos in due)+1,'endTime':ms,'limit':1000})
      if len(funding)>=1000:raise ValueError('FUNDING_HISTORY_TRUNCATED')
    except Exception as exc:funding_error=str(exc)
    return symbol,dict(quote=dict(bid=depth['bids'][0][0],ask=depth['asks'][0][0],mark=p['markPrice'],time=int(p['time']),book_time=int(depth['E']),next_funding=int(p['nextFundingTime']),funding_rate=p['lastFundingRate']),candles=timeframes.get('1h',[]),timeframes=timeframes,contract=self.metadata.get(symbol,{}),funding=funding,funding_error=funding_error,depth=depth),None
   except Exception as exc:return symbol,None,type(exc).__name__+': '+str(exc)
  with ThreadPoolExecutor(max_workers=4) as pool:received=list(pool.map(one,symbols))
  market={symbol:data for symbol,data,error in received if data is not None}
  state=apply_cycle(state,market,int(time.time()*1000))
  state['errors'].extend(symbol+':'+error for symbol,data,error in received if error)
  if state['errors']:state['state']='DEGRADED'
  state['pid']=os.getpid()
  state['data_pipeline_version']='INTERVAL_CACHE_RISK_V2'
  state['signal_status']=self.signal_cache.status(signals_cache)
  if metadata_error:state['errors'].append('METADATA:'+metadata_error);state['state']='DEGRADED'
  state['signal_downloads_pending']=len(self.signal_jobs)
  state['signal_download_errors']={':'.join(k):v for k,v in self.signal_errors.items()}
  finish_reset(self.base,state,'futures',int(time.time()*1000))
  atomic_json(self.path,state)
  try:self.timeframe_experiment.cycle(state['universe'],market,int(time.time()*1000))
  except Exception as exc:atomic_json(self.base/'zitar_rsi_timeframes_error_v1.json',dict(time_ms=int(time.time()*1000),error=str(exc)))
  return state

def loop(base,once=False):
 base=Path(base);lock=FileLock(base/'zitar_futures_paper_v1.lock')
 if not lock.acquire():return
 try:
  worker=Futures(base)
  while True:
   try:
    state=worker.cycle()
    if once:
     state['state']='INITIALIZED' if not state['errors'] else 'DEGRADED'
     atomic_json(worker.path,state)
     print(json.dumps({'state':state['state'],'universe':state['universe'],'errors':state['errors']},ensure_ascii=False));return
   except Exception as exc:
    atomic_json(base/'zitar_futures_paper_error_v1.json',{'time_ms':int(time.time()*1000),'error':str(exc)})
    if once:raise
   time.sleep(15)
 finally:
  if 'worker' in locals():worker.signal_cache.close()
  lock.close()
def start_worker(base):threading.Thread(target=loop,args=(base,),daemon=True,name='zitar-futures-paper').start()
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--base',type=Path,default=Path(__file__).parent);ap.add_argument('--once',action='store_true');args=ap.parse_args();loop(args.base,args.once)

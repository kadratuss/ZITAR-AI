"""Paired VOLUME vs VOLUME + BB/KC squeeze-release paper experiment."""
import copy,json,time,gzip
from pathlib import Path
from zitar_momentum_experiment_v2 import initial,advance
from zitar_full_paper_runtime_v1 import atomic_json
from zitar_market_controls_v1 import read
from zitar_futures_paper_engine_v1 import day
FILE='zitar_bollinger_pair_v1.json'
def gate(book,symbol,target,a,data,ms):
 if book['bb_filter'] and a.get('bb_breakout')!=target:return 'BB_SQUEEZE_BREAKOUT_FILTER'
 return None
class Experiment:
 def __init__(self,base):
  self.base=Path(base);self.path=self.base/FILE
  self.state=json.loads(self.path.read_text(encoding='utf-8-sig')) if self.path.exists() else {}
 def cycle(self,snapshots,signals,universe,ms):
  if not self.state:
   s=initial(ms,universe);books={}
   for market in ('spot','futures'):
    for flag in (False,True):
     b=copy.deepcopy(s['books'][market+'_VOLUME']);b.update(bb_filter=flag,label='BOLLINGER' if flag else 'CONTROL')
     books[market+'_'+b['label']]=b
   s.update(books=books,schema='BOLLINGER_PAIR_V1',definition='Closed 15m BB20/2 within KC20/SMA-TR20/1.5 on previous bar; release now and close beyond matching BB band. Same-bar RSI50 cross, EMA200 1h and volume1.2 remain mandatory.')
   self.state=s
  if self.state['universe']!=universe:raise ValueError('UNIVERSE_CHANGED')
  paused=read(self.base,'bollinger')['paused'];folder=self.base/'bollinger_pair_inputs';folder.mkdir(exist_ok=True)
  error=None
  try:
   with gzip.open(folder/(str(self.state['started_ms'])+'_'+day(ms)+'.jsonl.gz'),'at',encoding='utf-8') as f:f.write(json.dumps(dict(ms=ms,snapshots=snapshots,signals=[dict(key=k,value=v) for k,v in signals.items()]))+'\n')
  except OSError as exc:paused=True;error=type(exc).__name__
  advance(self.state,snapshots,signals,ms,paused,gate)
  self.state['recording_error']=error
  if error:self.state['state']='DEGRADED'
  atomic_json(self.path,self.state)
def overview(base):
 p=Path(base)/FILE
 if not p.exists():return dict(state='NOT_STARTED',books={})
 d=json.loads(p.read_text(encoding='utf-8-sig'));d['age_seconds']=(time.time()*1000-d['heartbeat_ms'])/1000
 if d['age_seconds']>60:d['state']='STALE'
 return d

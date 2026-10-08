"""Predeclared RSI repair ladder; paper only, independently persisted."""
import copy,json,time,gzip
from pathlib import Path
from decimal import Decimal as D
from zitar_full_paper_runtime_v1 import atomic_json
from zitar_futures_paper_engine_v1 import fresh,POLICY,day
VARIANTS=('CONTROL','EXIT50','RECOVERY','COOLDOWN')
FILE='zitar_rsi_repair_v1.json'
def gate(b,symbol,target,a,data,ms):
 if b['variant']=='COOLDOWN':
  losses=[p for p in b['closed'] if p['symbol']==symbol and D(p['net_pnl'])<0]
  if losses and ms-losses[-1]['closed_ms']<3600000:return 'LOSS_COOLDOWN_1H'
 eq=max(D(0),D(b['equity']));policy=b['execution_policy'];cost=D('.02')+2*(D(policy['fee_rate'])+D(policy['slippage_rate']))
 used=sum(D(p['quantity'])*D(p['entry'])*cost for p in b['positions'].values())
 risk=min(eq*D('.0025'),max(D(0),eq*D('.01')-used))
 if risk<=0:return 'TOTAL_RISK_LIMIT'
 b['slot']=str(min(eq/10,risk/(D(policy['leverage'])*cost)))
 return None
class Experiment:
 def __init__(self,base):
  self.base=Path(base);self.path=self.base/FILE
  self.state=json.loads(self.path.read_text(encoding='utf-8-sig')) if self.path.exists() else {}
 def cycle(self,snapshots,signals,universe,ms):
  from zitar_indicator_lab_v1 import apply_book
  from zitar_market_controls_v1 import read
  if not self.state:
   books={}
   for market in ('spot','futures'):
    for v in VARIANTS:
     b=copy.deepcopy(fresh(ms,[])['books']['BASELINE']);b.update(variant=v,market=market,interval='15m',rule='RSI' if v=='CONTROL' else 'RSI_BASE',started_ms=ms,cursors={},decisions=[],daily_limit='OPEN',stop_pct='.02',execution_policy=dict(POLICY,leverage=1 if market=='spot' else 3,fee_rate='.001' if market=='spot' else '.0005',slippage_rate='.001' if market=='spot' else '.0002'))
     books[market+'_'+v]=b
   self.state=dict(version=1,started_ms=ms,universe=copy.deepcopy(universe),books=books,real_orders=False)
  if self.state['universe']!=universe:raise ValueError('REPAIR_UNIVERSE_CHANGED')
  folder=self.base/'rsi_repair_inputs';folder.mkdir(exist_ok=True)
  with gzip.open(folder/(str(self.state['started_ms'])+'_'+day(ms)+'.jsonl.gz'),'at',encoding='utf-8') as f:f.write(json.dumps(dict(ms=ms,snapshots=snapshots,signals=[dict(key=k,value=v) for k,v in signals.items() if k[2]=='15m']))+'\n')
  for b in self.state['books'].values():
   if b.get('loss_day')!=day(ms):b['loss_day']=day(ms);b['loss_locked']=False;b['loss_start']=b['equity']
   if D(b['equity'])<=D(b['loss_start'])*D('.98'):b['loss_locked']=True
   b['entries_paused']=read(self.base,'repair')['paused'] or b['loss_locked']
   analyses={}
   for symbol in universe[b['market']]:
    raw=signals.get((b['market'],symbol,'15m'))
    if not raw:continue
    a=dict(raw)
    if b['variant'] in ('RECOVERY','COOLDOWN'):a['RSI_BASE']=1 if a['previous_rsi']<=30<a['rsi']<50 else -1 if a['previous_rsi']>=70>a['rsi']>50 else 0
    analyses[symbol]=a
   apply_book(b,snapshots.get(b['market'],{}),analyses,ms,before_entry=gate)
  self.state['heartbeat_ms']=ms
  atomic_json(self.path,self.state)
def overview(base):
 p=Path(base)/FILE
 if not p.exists():return dict(state='NOT_STARTED',books={})
 d=json.loads(p.read_text(encoding='utf-8-sig'));d['age_seconds']=(time.time()*1000-d['heartbeat_ms'])/1000;d['state']='STALE' if d['age_seconds']>60 else 'PAPER';return d

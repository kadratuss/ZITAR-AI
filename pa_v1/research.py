"""Readonly local OHLCV replay; no network, no mutation of production books."""
import sqlite3,json,bisect,copy,time,argparse
from pathlib import Path
from dataclasses import asdict,replace
from collections import defaultdict,Counter
from .config import Config,duration
from .features import evaluate
from .paper import create,tick,partial
from .metrics import summary
from zitar_futures_paper_engine_v1 import signals,fresh,open_position,close_position,mark,day,POLICY
from zitar_discovery_spot_v1 import RULES
from zitar_full_paper_runtime_v1 import atomic_json

def aggregate(rows,step):
 out=[];groups=defaultdict(list)
 for r in rows:groups[int(r[0])//step*step].append(r)
 for t,x in sorted(groups.items()):
  if len(x)!=step//60000 or any(int(r[0])!=t+i*60000 for i,r in enumerate(x)):continue
  out.append([t,x[0][1],max(r[2] for r in x),min(r[3] for r in x),x[-1][4],sum(r[5] for r in x),t+step-1])
 return out

def load(base,c):
 selection=json.loads((base/'zitar_market_discovery_v1.json').read_text(encoding='utf-8-sig'))['markets']['spot'];universe=selection['main'][:c.top_n]
 con=sqlite3.connect((base/'learning_lab.db').as_uri()+'?mode=ro',uri=True);data={};missing=[]
 for symbol in universe:
  rows=con.execute("select open_time_ms,open_price,high_price,low_price,close_price,volume,close_time_ms from candles where symbol=? and interval='1m' order by open_time_ms",(symbol,)).fetchall()
  rows=[[int(r[0]),*map(float,r[1:6]),int(r[6])] for r in rows]
  if len(rows)<c.history*duration(c.regime_tf)//60000:missing.append(symbol);continue
  data[symbol]={tf:aggregate(rows,duration(tf)) for tf in {c.entry_tf,c.structure_tf,c.regime_tf}}
 con.close();return data,dict(universe_requested=universe,universe_missing=missing,selection_timestamp=selection['updated_ms'],survivorship_bias=True,historical_depth='UNAVAILABLE',lot_tick_rules='PROXY_NOT_HISTORICAL',fill='NEXT_ENTRY_BAR_OPEN_SAMPLED_STOPS_NO_INTRABAR_PATH')

def replay(data,c,start,end,include_references=True):
 state=create(start,c);refs={}
 for n in (('RSI14','SMA20_50','EMA12_26') if include_references else ()):
  b=copy.deepcopy(fresh(start,[])['books']['BASELINE']);b.update(execution_policy=dict(POLICY,leverage=1,fee_rate=RULES['fee'],slippage_rate=RULES['slippage']),samples=[]);refs[n]=b
 indexes={s:{tf:[r[6] for r in rs] for tf,rs in frames.items()} for s,frames in data.items()};opens={s:{r[0]:r for r in frames[c.entry_tf]} for s,frames in data.items()};reasons=Counter()
 for ms in range(start,end,duration(c.entry_tf)):
  market={};features={};raws={}
  for symbol,frames in data.items():
   row=opens[symbol].get(ms)
   if not row:continue
   q=dict(time=ms,bid=str(row[1]),ask=str(row[1]),mark=str(row[1]),funding_rate='0',next_funding=ms+999999999)
   market[symbol]=dict(quote=q,contract=dict(step='0.00000001',min_qty='0.00000001',max_qty='1e20',min_notional='1'))
   raw={tf:rs[max(0,bisect.bisect_left(indexes[symbol][tf],ms)-120):bisect.bisect_left(indexes[symbol][tf],ms)] for tf,rs in frames.items()};raws[symbol]=raw
   f=evaluate(symbol,raw,ms,c);features[symbol]=f;reasons.update(f['reasons'])
  tick(state,market,features,ms,c,historical=True)
  quotes={s:x['quote'] for s,x in market.items()}
  for name,b in refs.items():
   if day(ms)!=b['period']:
    b['daily'].append(dict(date=b['period'],return_pct=(float(b['equity'])/float(b['period_start'])-1)*100,partial=b['period']==day(start)));b.update(period=day(ms),period_start=b['equity'],slot=str(float(b['equity'])/10))
   for symbol,raw in raws.items():
    try:target=signals(raw[c.entry_tf],ms,duration(c.entry_tf))[name]
    except ValueError:continue
    q=quotes[symbol];p=b['positions'].get(symbol)
    if p:
     p['best_price']=str(max(float(p['best_price']),float(q['bid'])))
     if float(q['bid'])<=float(p['best_price'])*.98 or target!=1:close_position(b,symbol,q,ms,'STOP_OR_SIGNAL')
    if target==1 and symbol not in b['positions']:open_position(b,symbol,1,q,market[symbol]['contract'],ms,'REFERENCE')
   if set(b['positions']).issubset(quotes):mark(b,quotes)
  last_market=market
 # Liquidate only historical comparison books at last observed quote, with fees.
 for b in state['books'].values():
  for symbol in list(b['positions']):
   if symbol in last_market:partial(b,symbol,last_market[symbol]['quote'],end,'END_OF_TEST')
  if not b['positions']:mark(b,{})
 for b in refs.values():
  for symbol in list(b['positions']):
   if symbol in last_market:close_position(b,symbol,last_market[symbol]['quote'],end,'END_OF_TEST')
  if not b['positions']:mark(b,{})
 return dict(start=start,end=end,PA={k:summary(b,c.initial) for k,b in state['books'].items()},references={k:summary(b,c.initial) for k,b in refs.items()},rejections=dict(reasons),open_remaining={k:len(b['positions']) for k,b in state['books'].items()})

def run(base):
 c=Config().validate();data,manifest=load(base,c)
 if not data:raise ValueError('NO_HISTORICAL_DATA')
 step=duration(c.entry_tf);start=max(v[c.regime_tf][c.history]['t'] if isinstance(v[c.regime_tf][c.history],dict) else v[c.regime_tf][c.history][6]+1 for v in data.values());start=(start+step-1)//step*step
 end=min(v[c.entry_tf][-1][0] for v in data.values());count=(end-start)//step
 bounds=[start,start+(count*6//10)*step,start+(count*8//10)*step,end];out=dict(config=asdict(c),manifest=manifest,bounds=bounds,symbols=list(data),verdict='NEEDS_MORE_DATA',results={})
 for i,name in enumerate(('DEVELOPMENT','VALIDATION','OUT_OF_SAMPLE')):
  out['results'][name]=replay(data,c,bounds[i],bounds[i+1]);print(name,json.dumps(out['results'][name]['PA']),flush=True)
  atomic_json(base/'outputs/pa_v1/historical_results.json',out)
 # Predeclared one-factor development-only grid, never select using OOS.
 trials=[]
 for field,values in [('min_score',[65,70,80,85]),('volume_ratio',[1.2,1.8,2.0]),('min_rr',[1.5,2.5,3.0])]:
  for value in values:
   r=replay(data,replace(c,**{field:value}),bounds[0],bounds[1]);trials.append(dict(parameter=field,value=value,PA=r['PA']));out['controlled_trials']=trials;atomic_json(base/'outputs/pa_v1/historical_results.json',out);print('grid',field,value,flush=True)
 out['controlled_trials']=trials;atomic_json(base/'outputs/pa_v1/historical_results.json',out)
 return out
if __name__=='__main__':run(Path(__file__).resolve().parents[1])

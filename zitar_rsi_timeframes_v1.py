"""Same production RSI execution, isolated simultaneous timeframe controls."""
import copy,json,time
from pathlib import Path
from zitar_futures_paper_engine_v1 import fresh,apply_cycle,POLICY
from zitar_full_paper_runtime_v1 import atomic_json
FILE='zitar_rsi_timeframes_v1.json'
STEPS={'5m':300000,'10m':600000,'1h':3600000}
def aggregate_10m(rows,ms):
    groups={}
    for r in rows:
        start=int(r[0]);bucket=start//600000*600000
        if int(r[6])>=ms:continue
        groups.setdefault(bucket,[]).append(r)
    result=[]
    for start,pair in sorted(groups.items()):
        pair=sorted(pair,key=lambda r:int(r[0]))
        if len(pair)!=2 or [int(r[0]) for r in pair]!=[start,start+300000]:continue
        if any(int(r[6])!=int(r[0])+299999 for r in pair):continue
        r=list(pair[0]);r[2]=str(max(float(x[2]) for x in pair));r[3]=str(min(float(x[3]) for x in pair));r[4]=pair[1][4];r[5]=str(sum(float(x[5]) for x in pair));r[6]=start+599999
        result.append(r)
    return result
class Experiment:
    def __init__(self,base):
        self.base=Path(base);self.path=self.base/FILE
        self.data=json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {}
    def books(self):return [s['books']['RSI14'] for s in self.data.get('accounts',{}).values()]
    def cycle(self,universe,market,ms):
        if not self.data:
            accounts={}
            for interval in STEPS:
                s=copy.deepcopy(fresh(ms,list(universe)));s['active_strategy_names']=['RSI14'];s['books']={'RSI14':s['books']['RSI14']}
                s['books']['RSI14']['execution_policy']=copy.deepcopy(POLICY)
                accounts[interval]=s
            self.data=dict(started_ms=ms,accounts=accounts,universe=list(universe),real_orders=False)
        if list(universe)!=self.data['universe']:raise ValueError('TIMEFRAME_UNIVERSE_CHANGED')
        from zitar_market_controls_v1 import read
        paused=read(self.base,'futures')['paused']
        for interval,state in self.data['accounts'].items():
            state['books']['RSI14']['entries_paused']=paused
            inputs={}
            for symbol,d in market.items():
                if symbol not in universe:continue
                item=dict(d);tf=d.get('timeframes',{})
                item['candles']=aggregate_10m(tf.get('5m',[]),ms) if interval=='10m' else tf.get(interval,[])
                inputs[symbol]=item
            apply_cycle(state,inputs,ms,STEPS[interval])
            state['errors'].extend(s+':MISSING_QUOTE' for s in universe if s not in inputs)
            if state['errors']:state['state']='DEGRADED'
            state['decisions']=state['decisions'][-2000:]
        self.data['heartbeat_ms']=ms
        atomic_json(self.path,self.data)
def overview(base):
    path=Path(base)/FILE
    if not path.exists():return dict(state='NOT_STARTED',accounts={})
    d=json.loads(path.read_text(encoding='utf-8'));d['age_seconds']=(time.time()*1000-d['heartbeat_ms'])/1000
    d['state']='STALE' if d['age_seconds']>60 else 'DEGRADED' if any(s['errors'] for s in d['accounts'].values()) else 'RUNNING'
    return d

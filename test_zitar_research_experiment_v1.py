import copy,json,tempfile,unittest
from pathlib import Path
from zitar_research_experiment_v1 import initial,advance,entry_gate,metrics,Experiment,HASH
T=1790863200000

def data(ms):
 q=dict(bid='100',ask='100.01',mark='100',time=ms,next_funding=ms+3600000,funding_rate='0')
 return dict(quote=q,contract=dict(step='.001',min_qty='.001',max_qty='999999',min_notional='1'),funding=[],eligible=True,depth=dict(bids=[['100','100000']],asks=[['100.01','100000']]))

def analysis(ms):return dict(candle_ms=ms-1,rsi=20,previous_rsi=25,wilder_rsi=35,previous_wilder_rsi=29,close=100,ema200=95,ema200_previous=94)

class Tests(unittest.TestCase):
 def test_calculation_and_confirmation_are_distinct(self):
  s=initial(T-3600000,{'spot':['X'],'futures':['X']});q={m:{'X':data(T)} for m in ('spot','futures')};a={(m,'X','1h'):analysis(T) for m in q}
  advance(s,q,a,T)
  self.assertIn('X',s['books']['spot_SIMPLE']['positions']);self.assertFalse(s['books']['spot_WILDER']['positions']);self.assertIn('X',s['books']['spot_CONFIRM']['positions'])
  before=s['books']['spot_SIMPLE']['positions']['X']['quantity'];cash=s['books']['spot_SIMPLE']['cash'];advance(s,q,a,T+1);self.assertEqual(before,s['books']['spot_SIMPLE']['positions']['X']['quantity']);self.assertEqual(cash,s['books']['spot_SIMPLE']['cash'])
 def test_paused_allows_exit(self):
  s=initial(T-3600000,{'spot':['X'],'futures':['X']});q={m:{'X':data(T)} for m in ('spot','futures')};a={(m,'X','1h'):analysis(T) for m in q};advance(s,q,a,T)
  later=T+3600000;q={m:{'X':data(later)} for m in q};a={k:dict(analysis(later),rsi=55,wilder_rsi=55) for k in a};advance(s,q,a,later,True)
  self.assertFalse(s['books']['spot_SIMPLE']['positions']);self.assertEqual(len(s['books']['spot_SIMPLE']['closed']),1)
 def test_risk_and_depth(self):
  b=initial(T,{'spot':['X'],'futures':['X']})['books']['futures_RISK']
  self.assertIsNone(entry_gate(b,'X',1,analysis(T),data(T),T));self.assertLess(float(b['slot']),400)
  small=data(T);small['depth']['asks']=[['100.01','.001']];self.assertEqual(entry_gate(b,'X',1,analysis(T),small,T),'EXPERIMENT_DEPTH_FILTER')
 def test_stop_and_regime(self):
  b=initial(T,{'spot':['X'],'futures':['X']})['books']['spot_TWO_STOP'];b['closed']=[dict(symbol='X',closed_ms=T-4*3600000,exit_reason='TRAILING_STOP')]*2
  self.assertEqual(entry_gate(b,'X',1,analysis(T),data(T),T),'TWO_STOPS_TODAY')
  b['variant']='REGIME';b['closed']=[];a=dict(analysis(T),close=90);self.assertEqual(entry_gate(b,'X',1,a,data(T),T),'REGIME_FILTER')
 def test_version_rejection(self):
  with tempfile.TemporaryDirectory() as td:
   s=initial(T,{'spot':['X'],'futures':['X']});s['manifest_hash']='changed';Path(td,'zitar_research_experiment_v1.json').write_text(json.dumps(s))
   with self.assertRaisesRegex(ValueError,'VERSION_CHANGED'):Experiment(td)
 def test_no_false_success(self):
  b=initial(T,{'spot':['X'],'futures':['X']})['books']['spot_SIMPLE'];m=metrics(b,T+3600000);self.assertEqual(m['verdict'],'KANIT_YETERSIZ');self.assertFalse(m['automatic_promotion'])
 def test_record_and_replay(self):
  from zitar_research_replay_v1 import replay
  with tempfile.TemporaryDirectory() as td:
   exp=Experiment(td);q={m:{'X':data(T)} for m in ('spot','futures')};a={(m,'X','1h'):analysis(T) for m in q};u={m:['X'] for m in q}
   exp.cycle(q,a,u,T)
   later=T+3600000;q={m:{'X':data(later)} for m in q};a={k:analysis(later) for k in a};exp.cycle(q,a,u,later)
   result=replay(Path(td)/'research_experiment_inputs'/str(T))
   self.assertEqual(result['state']['books'],exp.state['books'])
   self.assertFalse(result['unseen_validation'])
 def test_stress_is_cost_only(self):
  books=initial(T,{'spot':['X'],'futures':['X']})['books'];a=books['futures_REGIME']['execution_policy'];b=books['futures_STRESS']['execution_policy'];self.assertEqual(float(b['slippage_rate']),float(a['slippage_rate'])*2)
  self.assertEqual({k:v for k,v in a.items() if k!='slippage_rate'},{k:v for k,v in b.items() if k!='slippage_rate'})
if __name__=='__main__':unittest.main()

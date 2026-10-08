import tempfile,unittest,copy
from pathlib import Path
from zitar_momentum_experiment_v2 import initial,advance,entry_gate,Experiment,overview
from test_zitar_research_experiment_v1 import T,data,analysis
class Tests(unittest.TestCase):
 def inputs(self,t):
  q={m:{'X':data(t)} for m in ('spot','futures')};a={}
  for m in q:
   a[m,'X','15m']=dict(analysis(t),wilder_rsi=52,previous_wilder_rsi=48,volume_ratio=1.4)
   a[m,'X','1h']=dict(analysis(t),close=100,ema200=95,ema200_previous=94)
  return q,a
 def test_filters_and_risk(self):
  s=initial(T-900000,{'spot':['X'],'futures':['X']});q,a=self.inputs(T);advance(s,q,a,T)
  self.assertEqual(len(s['books']),10)
  for b in s['books'].values():
   self.assertIn('X',b['positions']);p=b['positions']['X'];self.assertLessEqual(float(p['quantity'])*float(p['entry'])*(.02+2*(float(b['execution_policy']['fee_rate'])+float(b['execution_policy']['slippage_rate']))),25.001)
 def test_missing_higher_blocks_only_candidates(self):
  s=initial(T-900000,{'spot':['X'],'futures':['X']});q,a=self.inputs(T);a={k:v for k,v in a.items() if k[2]=='15m'};advance(s,q,a,T)
  self.assertTrue(s['books']['spot_MOMENTUM']['positions']);self.assertFalse(s['books']['spot_TREND']['positions'])
 def test_volume_is_separate(self):
  s=initial(T-900000,{'spot':['X'],'futures':['X']});q,a=self.inputs(T)
  for k in a:a[k]['volume_ratio']=.5
  advance(s,q,a,T);self.assertTrue(s['books']['spot_TREND']['positions']);self.assertFalse(s['books']['spot_VOLUME']['positions'])
 def test_exit_and_reset(self):
  from zitar_reset_control_v1 import request
  with tempfile.TemporaryDirectory() as td:
   e=Experiment(td);u={'spot':['X'],'futures':['X']};q,a=self.inputs(T);e.cycle(q,a,u,T)
   q,a=self.inputs(T+900000);e.cycle(q,a,u,T+900000);self.assertTrue(e.state['books']['spot_TREND']['positions'])
   request(Path(td),{'confirm':'RESET_PAPER_10000'});q,a=self.inputs(T+900001);e.cycle(q,a,u,T+900001)
   self.assertTrue(all(float(b['cash'])==10000 and not b['positions'] for b in e.state['books'].values()))
   self.assertEqual(overview(td)['evaluation']['spot_TREND']['costs']['closed_fees'],'0')
 def test_retired_discovery_does_not_read_missing_5m(self):
  from zitar_discovery_futures_v1 import evaluate,NAMES
  errors=[];evaluate({'books':{n:{'retired_ms':1} for n in NAMES}}, {'X':{}},{'X':{}},T,set(),errors);self.assertEqual(errors,[])
if __name__=='__main__':unittest.main()

import tempfile,unittest
from zitar_bollinger_pair_v1 import Experiment
from test_zitar_momentum_experiment_v2 import Tests as Fixtures
from test_zitar_research_experiment_v1 import T
class Tests(unittest.TestCase):
 def test_paired_gate_and_exit(self):
  with tempfile.TemporaryDirectory() as d:
   e=Experiment(d);u={'spot':['X'],'futures':['X']}
   def run(t,bb,r=52,prev=48):
    q,a=Fixtures().inputs(t)
    for k,v in a.items():v.update(bb_breakout=bb,wilder_rsi=r,previous_wilder_rsi=prev)
    e.cycle(q,a,u,t)
   run(T,0);run(T+900000,0)
   for m in u:
    self.assertTrue(e.state['books'][m+'_CONTROL']['positions']);self.assertFalse(e.state['books'][m+'_BOLLINGER']['positions'])
   run(T+1800000,1)
   for m in u:self.assertTrue(e.state['books'][m+'_BOLLINGER']['positions'])
   run(T+2700000,0,48,52)
   for m in u:self.assertFalse(e.state['books'][m+'_BOLLINGER']['positions'])
 def test_closed_bollinger_release(self):
  from zitar_indicator_lab_signals_v1 import analyze
  step=900000;t=step*10000
  rows=[[t-(220-i)*step,100,101,99,100,10,t-(219-i)*step-1] for i in range(220)]
  rows[-1][2]=111;rows[-1][4]=110
  a=analyze(rows,t,'15m');self.assertEqual(a['bb_breakout'],1)
  rows.append([t,110,200,1,1,10,t+step-1])
  self.assertEqual(analyze(rows,t,'15m')['bb_breakout'],1)
if __name__=='__main__':unittest.main()

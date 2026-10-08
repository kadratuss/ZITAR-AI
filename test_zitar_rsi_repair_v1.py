import unittest,tempfile
from zitar_rsi_repair_v1 import Experiment,gate
from test_zitar_research_experiment_v1 import T,data,analysis
class Tests(unittest.TestCase):
 def test_ladder_risk_and_cooldown(self):
  with tempfile.TemporaryDirectory() as d:
   e=Experiment(d);u={'spot':['X'],'futures':['X']}
   def run(t,r,prev):
    q={m:{'X':dict(data(t),eligible=True)} for m in u};a={(m,'X','15m'):dict(analysis(t),rsi=r,previous_rsi=prev,RSI=1 if r<30 else 0,RSI_BASE=1 if r<30 else 0) for m in u};e.cycle(q,a,u,t)
   run(T,25,26);run(T+900000,25,26)
   self.assertTrue(e.state['books']['futures_CONTROL']['positions']);self.assertFalse(e.state['books']['futures_RECOVERY']['positions'])
   run(T+1800000,35,25)
   self.assertFalse(e.state['books']['futures_CONTROL']['positions']);self.assertTrue(e.state['books']['futures_EXIT50']['positions']);self.assertTrue(e.state['books']['futures_RECOVERY']['positions'])
   b=e.state['books']['futures_COOLDOWN'];p=b['positions']['X'];self.assertLessEqual(float(p['entry'])*float(p['quantity'])*.0214,25.01)
   b['closed'].append(dict(symbol='X',net_pnl='-1',closed_ms=T+1800000))
   self.assertEqual(gate(b,'X',1,{}, {},T+1800001),'LOSS_COOLDOWN_1H')
if __name__=='__main__':unittest.main()

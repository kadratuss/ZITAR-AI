import unittest
from unittest.mock import patch
from zitar_futures_paper_engine_v1 import fresh
from zitar_trigger_lab_v2 import ensure_trigger,NAMES,report_trigger
from zitar_futures_shared_v1 import evaluate
class TriggerTests(unittest.TestCase):
 def test_transition_cap_and_no_repeat(self):
  t=1790456400000;s=fresh(t,[]);ensure_trigger(s,t);b=s['books'][NAMES[1]]
  q=dict(bid='100',ask='100',mark='100',time=t,book_time=t,next_funding=t+9999999,funding_rate='0')
  c=dict(step='0.01',min_qty='0.01',max_qty='10000',min_notional='5')
  market={str(i):dict(quote=q,contract=c,timeframes={'5m':[],'15m':[],'1h':[]}) for i in range(5)}
  quotes={k:q for k in market}
  for tick,direction in [(1,0),(2,1),(3,1)]:
   def sig(rows,ms,interval_ms=3600000):return dict(BASELINE=direction if interval_ms==300000 else 0,candle_close_ms=t+tick*300000-1 if interval_ms==300000 else t-1)
   with patch('zitar_futures_shared_v1.signals',side_effect=sig):evaluate(s,market,quotes,t+tick*300000,set(),[],name=NAMES[1])
   if tick==1:self.assertFalse(b['positions'])
   if tick==2:self.assertEqual(len(b['positions']),3)
  self.assertEqual(len(b['positions']),3)
  self.assertEqual(b['evaluations']['4:5m']['reason'],'WAIT_NEW_DIRECTION')
  self.assertEqual(s['books'][NAMES[0]]['cash'],'10000')
  self.assertFalse(report_trigger(s,t+900000,[])['automatic_promotion'])
if __name__=='__main__':unittest.main()

import unittest
from unittest.mock import patch
from zitar_futures_paper_engine_v1 import fresh
from zitar_strategy_lab_v1 import ensure_experiment,summarize,NAMES
from zitar_futures_shared_v1 import evaluate

class LabTests(unittest.TestCase):
 def test_equal_start_and_persistence(self):
  s=fresh(1000,[]);ensure_experiment(s,2000)
  self.assertEqual(s['books'][NAMES[0]],s['books'][NAMES[1]])
  s['books'][NAMES[0]]['cash']='9000';ensure_experiment(s,3000)
  self.assertEqual(s['books'][NAMES[0]]['cash'],'9000')
  self.assertFalse(summarize(s,4000,[])['automatic_promotion'])
  self.assertEqual(summarize(s,4000,['ERROR'])['status'],'DATA_QUALITY_REVIEW')
 def test_candidate_blocks_neutral_upper_control_enters(self):
  t=1790456400000;s=fresh(t,[]);ensure_experiment(s,t)
  q=dict(bid='100',ask='100',mark='100',time=t+300000,book_time=t+300000,next_funding=t+9999999,funding_rate='0')
  c=dict(step='0.01',min_qty='0.01',max_qty='10000',min_notional='5')
  data=dict(quote=q,contract=c,timeframes={'5m':[], '15m':[], '1h':[]})
  def sig(rows,ms,interval_ms=3600000):return {'BASELINE':1 if interval_ms==300000 else 0,'candle_close_ms':t+299999 if interval_ms==300000 else t-1}
  with patch('zitar_futures_shared_v1.signals',side_effect=sig):
   for name in NAMES:evaluate(s,{'BTC':data},{'BTC':q},t+300000,set(),[],name=name)
  self.assertIn('BTC',s['books'][NAMES[0]]['positions'])
  self.assertFalse(s['books'][NAMES[1]]['positions'])

if __name__=='__main__':unittest.main()

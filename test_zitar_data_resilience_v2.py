import json,tempfile,unittest
from pathlib import Path
from concurrent.futures import Future
from unittest.mock import patch
from zitar_candle_cache_v1 import CandleCache,DURATIONS
from zitar_discovery_spot_v1 import Spot,fresh

class ResilienceTests(unittest.TestCase):
 def test_incomplete_candle_cannot_age_into_valid_cache(self):
  t=1800000000000
  cache=CandleCache(lambda s,i:[[0,0,0,0,0,0,t-1],[0,0,0,0,0,0,t+299999]],intervals=('5m',))
  def immediate(fn):
   job=Future();job.set_result(fn());return job
  with patch.object(cache.pool,'submit',side_effect=immediate):
   cache.snapshot(['BTC'],t)
   result=cache.snapshot(['BTC'],t+1)
   self.assertEqual([r[6] for r in result['BTC']['5m']],[t-1])
   result=cache.snapshot(['BTC'],t+300000)
   self.assertNotIn('5m',result['BTC'])
  cache.close()
 def test_only_closed_interval_refreshed_and_no_duplicate_jobs(self):
  cache=CandleCache(lambda s,i:[]);t=1800000000000
  for interval,d in DURATIONS.items():cache.rows[('BTC',interval)]=[[0,0,0,0,0,0,t//d*d-1]]
  pending=Future()
  with patch.object(cache.pool,'submit',return_value=pending) as submit:
   got=cache.snapshot(['BTC'],t);self.assertEqual(len(got['BTC']),3);submit.assert_not_called()
   got=cache.snapshot(['BTC'],t+300000);self.assertNotIn('5m',got['BTC']);self.assertIn('1h',got['BTC'])
   self.assertEqual(submit.call_count,1)
   cache.snapshot(['BTC'],t+300001);self.assertEqual(submit.call_count,1)
  cache.close()
 def test_failed_refresh_never_returns_old_candle_and_has_backoff(self):
  cache=CandleCache(lambda s,i:[],intervals=('5m',));job=Future();job.set_exception(OSError('offline'));cache.jobs[('BTC','5m')]=job
  with patch.object(cache.pool,'submit') as submit:
   self.assertEqual(cache.snapshot(['BTC'],1800000000000),{'BTC':{}});submit.assert_not_called()
   self.assertIn('BTC:5m',cache.status({'BTC':{}})['errors'])
  cache.close()
 def test_spot_stop_survives_missing_selection_metadata_and_candles(self):
  t=1800000000000
  with tempfile.TemporaryDirectory() as root:
   path=Path(root)/'zitar_discovery_spot_v1.json';s=fresh(t-1000)
   b=s['books']['SINGLE'];b.update(cash='9000',equity='10000')
   b['positions']['XRPTRY']=dict(qty='10',entry='100',cost='1000',best='100',stop='98',value='1000',opened_ms=t-1000)
   path.write_text(json.dumps(s));worker=Spot(root)
   def get(market,endpoint,params=None,**kwargs):
    if endpoint=='depth':return {'bids':[['95','1000']],'asks':[['96','1000']]}
    raise OSError('metadata unavailable')
   with patch('zitar_discovery_spot_v1.get',side_effect=get),patch('zitar_discovery_spot_v1.time.time',return_value=t/1000),patch.object(worker.cache,'snapshot',return_value={'XRPTRY':{}}):result=worker.cycle()
   self.assertFalse(result['books']['SINGLE']['positions'])
   self.assertEqual(result['books']['SINGLE']['closed'][0]['exit_reason'],'TRAILING_STOP')
   self.assertEqual(result['state'],'DEGRADED')
   worker.cache.close()

if __name__=='__main__':unittest.main()

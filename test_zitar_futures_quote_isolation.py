import copy,json,tempfile,unittest,urllib.error
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import Future
import zitar_futures_paper_runtime_v1 as runtime
from zitar_futures_paper_engine_v1 import fresh,open_position

class QuoteIsolationTests(unittest.TestCase):
 def test_transient_retry(self):
  response=unittest.mock.MagicMock();response.__enter__.return_value.read.return_value=b'{}'
  with patch.object(runtime.urllib.request,'urlopen',side_effect=[urllib.error.URLError('reset'),response]) as call,patch.object(runtime.time,'sleep'):
   self.assertEqual(runtime.get('time'),{});self.assertEqual(call.call_count,2)
 def test_rate_limit_not_retried(self):
  with patch.object(runtime.urllib.request,'urlopen',side_effect=urllib.error.HTTPError('url',429,'limited',{},None)) as call:
   with self.assertRaises(urllib.error.HTTPError):runtime.get('time')
   self.assertEqual(call.call_count,1)
 def test_pending_candles_do_not_block_snapshot(self):
  with tempfile.TemporaryDirectory() as root:
   worker=runtime.Futures(root);pending=Future();worker.signal_jobs.update({('BTCUSDT',i):pending for i in ('5m','15m','1h')})
   self.assertEqual(worker.signal_snapshot(['BTCUSDT'],1790621000000),{'BTCUSDT':{}})
   worker.signal_pool.shutdown(wait=False)
 def test_stop_survives_missing_candles_and_no_unnecessary_funding(self):
  t=1790621000000;c=dict(step='0.01',min_qty='0.01',max_qty='10000',min_notional='5')
  q=dict(bid='100',ask='100',mark='100',time=t,book_time=t,next_funding=t+3600000,funding_rate='0')
  state=fresh(t-1000,['BTCUSDT']);open_position(state['books']['BASELINE'],'BTCUSDT',1,q,c,t-500,'test')
  with tempfile.TemporaryDirectory() as root:
   path=Path(root)/runtime.STATE;path.write_text(json.dumps(state))
   worker=runtime.Futures(root);worker.metadata={'BTCUSDT':c};worker.metadata_day=t//86400000
   def get(endpoint,params=None):
    if endpoint=='premiumIndex':return [dict(symbol='BTCUSDT',markPrice='95',time=t,nextFundingTime=t+3600000,lastFundingRate='0')]
    if endpoint=='depth':return dict(bids=[['95','1000']],asks=[['95','1000']],E=t)
    raise AssertionError('Unexpected blocking request: '+endpoint)
   with patch.object(worker,'signal_snapshot',return_value={'BTCUSDT':{}}),patch.object(runtime,'get',side_effect=get),patch.object(runtime.time,'time',return_value=t/1000):
    result=worker.cycle()
   self.assertFalse(result['books']['BASELINE']['positions'])
   self.assertEqual(result['books']['BASELINE']['closed'][0]['exit_reason'],'TRAILING_STOP_2PCT')
   self.assertFalse(any('MISSING_POSITION_QUOTE' in e for e in result['errors']))
   worker.signal_pool.shutdown(wait=False)

if __name__=='__main__':unittest.main()

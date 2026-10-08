import json,tempfile,unittest
from pathlib import Path
from copy import deepcopy
from zitar_futures_paper_engine_v1 import fresh,POLICY
from zitar_futures_settings_v1 import request_change,consume_request,read_request
from zitar_full_paper_runtime_v1 import atomic_json
class FuturesSettingsTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name);self.original=POLICY['leverage'];POLICY['leverage']=3;self.addCleanup(POLICY.__setitem__,'leverage',self.original)
  self.state=deepcopy(fresh(1790456400000,['BTCUSDT']));atomic_json(self.base/'zitar_futures_paper_v1.json',self.state)
 def test_archive_restart_and_idempotency(self):
  req=request_change(self.base,2);new=consume_request(self.base,self.state,1790456500000)
  self.assertEqual(new['policy']['leverage'],2);self.assertEqual(read_request(self.base)['status'],'APPLIED')
  archive=json.loads((self.base/'futures_paper_archives'/(req['id']+'.json')).read_text())
  self.assertEqual(archive['policy']['leverage'],3)
  self.assertEqual(consume_request(self.base,new,1790456600000)['started_ms'],new['started_ms'])
 def test_positions_block_even_if_opened_after_request(self):
  request_change(self.base,2);self.state['books']['BASELINE']['positions']['BTCUSDT']={}
  result=consume_request(self.base,self.state,1790456500000)
  self.assertEqual(read_request(self.base)['status'],'REJECTED');self.assertEqual(result['policy']['leverage'],3)
 def test_invalid_or_duplicate_request(self):
  for value in [True,0,100,'3']:
   with self.assertRaises(ValueError):request_change(self.base,value)
  request_change(self.base,2)
  with self.assertRaises(ValueError):request_change(self.base,5)

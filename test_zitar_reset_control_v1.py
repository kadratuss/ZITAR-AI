import json,tempfile,unittest
from pathlib import Path
from zitar_reset_control_v1 import request,status
from zitar_strategy_selection_v1 import prepare_reset,finish_reset
from zitar_indicator_lab_v1 import initial
class ResetControlTests(unittest.TestCase):
 def test_confirmation_dedup_and_scalping_archive(self):
  with tempfile.TemporaryDirectory() as tmp:
   base=Path(tmp)
   with self.assertRaises(ValueError):request(base,{})
   r=request(base,{'confirm':'RESET_PAPER_10000'})
   self.assertEqual(request(base,{'confirm':'RESET_PAPER_10000'})['id'],r['id'])
   s=initial(1700000000000);s['active_strategy_names']=['SCALP20'];b=s['books']['SCALP20'];b['cash']='9500';b['entries_paused']=True
   prepare_reset(base,s,'scalping');b['accounting_pending']=True
   finish_reset(base,s,'scalping',1700000001000)
   self.assertIn('pending_active_reset_id',s)
   b['accounting_pending']=False;finish_reset(base,s,'scalping',1700000002000)
   b=s['books']['SCALP20'];self.assertEqual(b['cash'],'10000');self.assertEqual(b['execution_policy']['leverage'],20);self.assertTrue(b['entries_paused'])
   self.assertEqual(status(base)['markets']['scalping']['currency'],'USDT')
   archive=json.loads((base/'paper_reset_archives'/r['id']/'scalping_before.json').read_text())
   self.assertEqual(archive['books']['SCALP20']['cash'],'9500')
   b['cash']='9999';prepare_reset(base,s,'scalping');finish_reset(base,s,'scalping',1700000003000);self.assertEqual(b['cash'],'9999')

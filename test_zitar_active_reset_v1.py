import json,tempfile,unittest
from pathlib import Path
from zitar_strategy_selection_v1 import configure,prepare_reset,finish_reset
from zitar_discovery_spot_v1 import fresh,apply
from test_zitar_confluence_v1 import T

class ResetTests(unittest.TestCase):
 def test_futures_templates_preserved_and_retired_not_revived(self):
  from zitar_futures_paper_engine_v1 import fresh as ff,apply_cycle
  base,_=self.setup_state();s=ff(T,[]);apply_cycle(s,{},T+1);configure(base,s,'futures',T+2)
  old_hash=s['books']['ZITAR_CONFLUENCE_5M']['rules_hash'];prepare_reset(base,s,'futures');finish_reset(base,s,'futures',T+3)
  for name in s['active_strategy_names']:
   self.assertEqual(s['books'][name]['cash'],'10000');self.assertFalse(s['books'][name]['positions']);self.assertFalse(s['books'][name]['closed'])
  self.assertEqual(s['books']['ZITAR_CONFLUENCE_5M']['rules_hash'],old_hash)
  self.assertTrue(s['books']['BASELINE']['retired_ms'])
 def setup_state(self):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);base=Path(tmp.name)
  (base/'zitar_strategy_selection_v1.json').write_text(json.dumps({'version':'SELECTED_PAPER_V1'}))
  (base/'zitar_active_reset_request_v1.json').write_text(json.dumps({'id':'test-reset'}))
  s=fresh(T);configure(base,s,'spot',T);s['books']['RADAR']['cash']='9800';s['books']['RADAR']['equity']='9800'
  return base,s
 def test_reset_archives_and_is_one_shot(self):
  base,s=self.setup_state();prepare_reset(base,s,'spot');finish_reset(base,s,'spot',T+1)
  self.assertEqual(s['books']['RADAR']['cash'],'10000');self.assertEqual(s['books']['RSI14']['cash'],'10000')
  self.assertTrue(s['books']['SINGLE']['retired_ms'])
  before=json.loads((base/'paper_reset_archives/test-reset/spot_before.json').read_text(encoding='utf-8'))
  self.assertEqual(before['books']['RADAR']['cash'],'9800')
  s['books']['RADAR']['cash']='9990';prepare_reset(base,s,'spot');finish_reset(base,s,'spot',T+2)
  self.assertEqual(s['books']['RADAR']['cash'],'9990')
 def test_wait_for_quote_close_with_costs_then_reset(self):
  base,s=self.setup_state();b=s['books']['RADAR'];b['positions']['TEST']=dict(qty='1',cost='100',value='100',best='100',stop='98',entry='100')
  prepare_reset(base,s,'spot');apply(s,{}, {},T+1);finish_reset(base,s,'spot',T+1)
  self.assertIn('TEST',b['positions']);self.assertNotIn('last_active_reset_id',s)
  apply(s,{'TEST':dict(ms=T+2,bid='100',ask='100')},{},T+2);finish_reset(base,s,'spot',T+2)
  closed=json.loads((base/'paper_reset_archives/test-reset/spot_closed.json').read_text(encoding='utf-8'))
  self.assertLess(float(closed['books']['RADAR']['closed'][0]['net_pnl']),0)
  self.assertFalse(s['books']['RADAR']['positions']);self.assertEqual(s['books']['RADAR']['cash'],'10000')
 def test_funding_pending_blocks_reset(self):
  base,s=self.setup_state();s['books']['RADAR']['accounting_pending']=True;prepare_reset(base,s,'spot');finish_reset(base,s,'spot',T+1)
  self.assertNotIn('last_active_reset_id',s)

if __name__=='__main__':unittest.main()

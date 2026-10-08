import csv,json,shutil,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from zitar_candidate_runtime_v1 import Candidate,entry_policy,prepare,STATE
from zitar_candidate_monitor_v1 import overview
SOURCE=Path(__file__).parent
class CandidateTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name)
  for n in ['zitar_master_paper_engine_v1.py','zitar_master_portfolio_v1.py']:shutil.copy2(SOURCE/n,self.base/n)
  self.t=datetime(2026,9,26,10,tzinfo=timezone.utc)
  self.rows=[];self.write()
  with patch('zitar_candidate_runtime_v1.now',return_value=self.t):prepare(self.base)
  self.w=Candidate(self.base,clock=lambda:self.t,fetch=lambda symbols:{s:{'bid':'10','ask':'10.01'} for s in symbols})
 def write(self):
  with (self.base/'multistrategy_live_trades_v3.csv').open('w',newline='') as f:
   w=csv.DictWriter(f,fieldnames=['trade_id','strategy','symbol','side','reference_price','executed_at_utc','observed_bid','observed_ask']);w.writeheader();w.writerows(self.rows)
 def event(self):
  self.t+=timedelta(seconds=1);self.rows.append(dict(trade_id='a',strategy='RSI14',symbol='TESTTRY',side='BUY',reference_price='10.01',executed_at_utc=self.t.isoformat(),observed_bid='10',observed_ask='10.01'));self.write()
 def test_isolation_missing_evidence_restart_and_periods(self):
  self.w.cycle();self.event();s=self.w.cycle()
  self.assertEqual(s['books']['MASTER']['account']['open_position_count'],1)
  self.assertEqual(s['books']['ZITAR_V1']['account']['open_position_count'],0)
  self.assertIn('FILTERED:',s['events'][0]['strategy_result'])
  self.assertEqual(len(self.w.cycle()['events']),1)
  self.assertFalse((self.base/'zitar_master_portfolio_v1.json').exists())
  monitor=overview(self.base)
  self.assertFalse(monitor['books']['MASTER']['weeks'][0]['complete'])
  self.assertFalse(monitor['books']['MASTER']['months'][0]['complete'])
 def test_equal_execution_when_accepted(self):
  self.event()
  with patch('zitar_candidate_runtime_v1.entry_policy',return_value=(True,'ACCEPTED')):s=self.w.cycle()
  import copy
  accounts=[copy.deepcopy(s['books'][n]['account']) for n in ['MASTER','ZITAR_V1']]
  for account in accounts:
   for position in account['positions'].values():position.pop('entry_reason',None)
  self.assertEqual(*accounts)
 def test_delayed_event_excluded_both(self):
  self.event();self.t+=timedelta(seconds=121);s=self.w.cycle()
  self.assertEqual(s['events'][0]['result'],'EXCLUDED_DELAYED_EVENT_BOTH_BOOKS')
  self.assertEqual(s['books']['MASTER']['account']['open_position_count'],0)
 def test_policy_fails_closed_and_exit_allowed(self):
  self.assertEqual(entry_policy(self.base,{'side':'SELL'}),(True,'SOURCE_EXIT'))
  self.assertFalse(entry_policy(self.base,{'side':'BUY','observed_bid':'10','observed_ask':'11'})[0])
 def test_no_mid_test_rule_change(self):
  self.w.cycle()
  with patch('zitar_candidate_runtime_v1.POLICY',{'version':'changed'}):
   with self.assertRaisesRegex(ValueError,'POLICY_CHANGED'):self.w.cycle()

 def test_position_details_and_closed_ledger_idempotent(self):
  self.event()
  with patch('zitar_candidate_runtime_v1.entry_policy',return_value=(True,'ACCEPTED')):self.w.cycle()
  view=overview(self.base)
  self.assertEqual(view['books']['ZITAR_V1']['open_positions'][0]['entry_reason'],'V1 giriş filtreleri sağlandı')
  self.t+=timedelta(seconds=1)
  self.rows.append(dict(self.rows[0],trade_id='sell',side='SELL',executed_at_utc=self.t.isoformat(),reference_price='10'))
  self.write();s=self.w.cycle();self.w.cycle()
  for name in ['MASTER','ZITAR_V1']:
   book=s['books'][name]
   self.assertEqual(len(book['closed_positions']),1)
   self.assertEqual(book['account']['open_position_count'],0)
   self.assertEqual(float(book['closed_positions'][0]['realized_pnl_try']),float(book['account']['realized_pnl_try']))
  self.assertEqual(len(overview(self.base)['books']['ZITAR_V1']['closed_positions']),1)

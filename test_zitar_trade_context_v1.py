import unittest
from zitar_trade_context_v1 import match_entry
class TradeContextTests(unittest.TestCase):
 def test_no_future_or_old_context(self):
  entry={'symbol':'BTCTRY','executed_at_utc':'2026-09-26T12:00:00+00:00'}
  def record(t):return {'symbol':'BTCTRY','observed_utc':t,'source_generated_utc':t,'record_id':'r','observation':{}}
  self.assertEqual(match_entry(entry,[record('2026-09-26T12:01:00+00:00')])['status'],'NO_PRIOR_ANALYSIS')
  self.assertEqual(match_entry(entry,[record('2026-09-26T10:00:00+00:00')])['status'],'STALE_ANALYSIS')
  self.assertEqual(match_entry(entry,[record('2026-09-26T11:30:00+00:00')])['status'],'MATCHED')
 def test_symbol_isolation(self):
  self.assertEqual(match_entry({'symbol':'XRPTRY','executed_at_utc':'2026-09-26T12:00:00+00:00'},[{'symbol':'BTCTRY','observed_utc':'2026-09-26T11:30:00+00:00'}])['status'],'NO_PRIOR_ANALYSIS')

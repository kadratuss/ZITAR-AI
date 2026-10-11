import copy,unittest
from zitar_next.scalping_diagnostics import report
class DiagnosticsTests(unittest.TestCase):
 def book(self,side=1):
  return dict(execution_policy={'slippage_rate':'.0002'},closed=[dict(symbol='TEST',direction=side,quantity='10',entry='100',exit='99' if side==1 else '101',entry_fee='1',exit_fee='1',net_pnl='-12',planned_risk='10',trailing_stop='99.5' if side==1 else '100.5',exit_reason='TRAILING_STOP',closed_ms=100)])
 def test_long_and_no_mutation(self):
  b=self.book();before=copy.deepcopy(b);r=report(b);self.assertEqual(b,before);self.assertEqual(r['rows'][0]['stop_overshoot_usdt'],'5.0');self.assertEqual(r['rows'][0]['risk_excess'],'2');self.assertEqual(r['closed_fees'],'2');self.assertIsNone(r['rows'][0]['stop_detection_delay_ms'])
 def test_short(self):self.assertEqual(report(self.book(-1))['rows'][0]['stop_overshoot_usdt'],'5.0')
 def test_missing_planned_risk(self):
  b=self.book();del b['closed'][0]['planned_risk'];self.assertIsNone(report(b)['rows'][0]['risk_excess'])
 def test_signal_exit_not_stop(self):
  b=self.book();b['closed'][0]['exit_reason']='SIGNAL_EXIT';self.assertIsNone(report(b)['rows'][0]['stop_overshoot_usdt'])
 def test_empty(self):self.assertEqual(report(dict(closed=[]))['closed_count'],0)
if __name__=='__main__':unittest.main()

import unittest
from zitar_discovery_spot_v1 import fresh,apply,day
class SpotRiskTests(unittest.TestCase):
 def setup_book(self):
  ms=1790787600000;s=fresh(ms-600000);b=s['books']['RADAR'];s['books']={'RADAR':b}
  b['cash']='9000';b['positions']={'TEST':dict(qty='10',cost='1000',entry='100',best='100',stop='98',value='1000',opened_ms=ms-600000)}
  q=dict(ms=ms,bid='100',ask='100',analysis=dict(candle_close_ms=ms-1,radar=False,radar_direction=1))
  return ms,s,b,q
 def test_faded_volume_keeps_position(self):
  ms,s,b,q=self.setup_book();apply(s,{'TEST':q},{},ms);self.assertIn('TEST',b['positions'])
 def test_radar_reverse_does_not_exit_before_stop(self):
  ms,s,b,q=self.setup_book();q['analysis']['radar_direction']=-1;apply(s,{'TEST':q},{},ms);self.assertIn('TEST',b['positions'])
 def test_loss_closes_and_latches(self):
  ms,s,b,q=self.setup_book();b['cash']='8700';apply(s,{'TEST':q},{},ms)
  self.assertEqual(b['daily_limit'],'LOSS_STOP');self.assertEqual(b['closed'][0]['exit_reason'],'DAILY_LOSS_STOP')
  b['cash']='10000';apply(s,{}, {},ms+1000);self.assertEqual(b['daily_limit'],'LOSS_STOP')
 def test_profit_has_no_daily_cap(self):
  ms,s,b,q=self.setup_book();b['cash']='9400';apply(s,{'TEST':q},{},ms)
  self.assertEqual(b['daily_limit'],'OPEN');self.assertIn('TEST',b['positions'])
  b['daily_limit']='PROFIT_LOCK';apply(s,{'TEST':q},{},ms+1);self.assertEqual(b['daily_limit'],'OPEN')
 def test_next_day_resets_limit(self):
  ms,s,b,q=self.setup_book();b.update(limit_day=b['period'],daily_limit='LOSS_STOP');b['positions']={};apply(s,{}, {},ms+86400000)
  self.assertEqual(b['daily_limit'],'OPEN');self.assertEqual(b['slot'],'900')
if __name__=='__main__':unittest.main()

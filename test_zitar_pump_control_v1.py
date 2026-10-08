import tempfile,unittest
from unittest.mock import patch
from zitar_discovery_spot_v1 import fresh,apply
from zitar_spot_control_v1 import read_control,update
class PumpControl(unittest.TestCase):
 def test_one_position_and_paused_entry(self):
  ms=1790787600000;s=fresh(ms-600000);s['books']={'RADAR':s['books']['RADAR']}
  def q(v):return dict(ms=ms,bid='100',ask='100',step='0.01',min_qty='0.01',max_qty='10000',min_notional='1',depth={},analysis=dict(candle_close_ms=ms-1,radar=True,radar_direction=1,volume_ratio=v,move_5m_pct=2))
  market={'A':q(3),'B':q(5)};sel=dict(radar=['A','B'],updated_ms=ms,early_candidates=[dict(symbol=n,stage='CONFIRMED',candle_ms=ms-1,confirmed_ms=ms-1) for n in ['A','B']])
  with patch('zitar_discovery_spot_v1.liquidity',return_value={'eligible':True}):
   apply(s,market,sel,ms)
  self.assertEqual(list(s['books']['RADAR']['positions']),['B'])
  s=fresh(ms-600000);s['books']={'RADAR':s['books']['RADAR']};s['entries_paused']=True
  apply(s,market,sel,ms);self.assertFalse(s['books']['RADAR']['positions'])
 def test_controls(self):
  with tempfile.TemporaryDirectory() as d:
   update(d,'stop');self.assertTrue(read_control(d)['paused'])
   update(d,'start');self.assertFalse(read_control(d)['paused'])
   with self.assertRaises(ValueError):update(d,'real_orders')
if __name__=='__main__':unittest.main()

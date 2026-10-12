import unittest
from unittest.mock import patch
from zitar_next.position_charts import positions,candles
class ChartScopeTests(unittest.TestCase):
 def test_active_lab_positions_only(self):
  sample={'books':{'RSI_BASE_FUTURES':{'market':'futures','positions':{'BTCUSDT':{'symbol':'BTCUSDT','entry':'100','trailing_stop':'98','opened_ms':1}}},'OLD':{'market':'futures','retired_ms':1,'positions':{'ETHUSDT':{'symbol':'ETHUSDT'}}},'SPOT':{'market':'spot','positions':{'BTCTRY':{'symbol':'BTCTRY'}}}}}
  with patch('zitar_next.position_charts.read_json',return_value=sample) as read:r=positions(5020)
  self.assertEqual(len(r['positions']),1);self.assertEqual(r['positions'][0]['account'],'RSI_BASE_FUTURES');self.assertTrue(read.call_args.args[0].endswith('/api/indicator-lab'))
 def test_spot_request_rejected(self):
  with self.assertRaises(ValueError):candles('spot','BTCTRY','1h')
 def test_invalid_interval_rejected(self):
  with self.assertRaises(ValueError):candles('futures','BTCUSDT','bad')
if __name__=='__main__':unittest.main()

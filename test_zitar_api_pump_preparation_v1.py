import unittest
from zitar_pump_early_v1 import advance
from zitar_api_vault_v1 import protect,save
class PreparationTests(unittest.TestCase):
 def test_distinct_bar_required(self):
  o=dict(candle_ms=100,close=100,ceiling=101,early=True,volume_ratio=2,buy_fraction=.7)
  p=advance(None,o,110);self.assertEqual(p['stage'],'EARLY')
  self.assertEqual(advance(p,dict(o,close=102),120)['stage'],'EARLY')
  self.assertEqual(advance(p,dict(o,close=102,candle_ms=200),210)['stage'],'CONFIRMED')
 def test_expiry(self):
  p=dict(stage='EARLY',identified_ms=0,candle_ms=1,ceiling=100)
  self.assertEqual(advance(p,dict(candle_ms=2000000,early=False),2000000)['stage'],'WATCH')
 def test_encryption_and_invalid_input(self):
  raw=b'fake-test-only-not-a-key';self.assertNotIn(raw,protect(raw))
  with self.assertRaises(ValueError):save('.',dict(exchange='unknown'))
if __name__=='__main__':unittest.main()

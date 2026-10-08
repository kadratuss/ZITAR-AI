import unittest
from unittest.mock import MagicMock
from zitar_public_exchange_v1 import PublicExchange,NoRedirect
class AdapterTests(unittest.TestCase):
 def test_deny(self):
  p=PublicExchange('binance')
  for s in ['../order','BTCUSDT&signature=secret','http://localhost']:
   with self.assertRaises(ValueError):p.orderbook(s)
  with self.assertRaises(PermissionError):p.place_order()
  with self.assertRaises(PermissionError):p.withdraw()
  with self.assertRaises(ValueError):NoRedirect().redirect_request(None,None,None,None,None,None)
 def test_normalize_and_throttle(self):
  for name,raw in [('binance',b'{"bids":[["100","2"]],"asks":[["101","3"]]}'),('bybit',b'{"retCode":0,"result":{"b":[["100","2"]],"a":[["101","3"]]}}')]:
   p=PublicExchange(name);p.opener=MagicMock();p.opener.open.return_value.__enter__.return_value.read.return_value=raw
   self.assertEqual(p.orderbook('BTCUSDT')['bids'][0],['100','2'])
   with self.assertRaises(ValueError):p.orderbook('BTCUSDT')
if __name__=='__main__':unittest.main()

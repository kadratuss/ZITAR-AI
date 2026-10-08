import unittest,json
from unittest.mock import patch,MagicMock
from zitar_api_verify_v1 import verify
class ApiVerifyTests(unittest.TestCase):
 def test_bybit_readonly(self):
  m=MagicMock();m.open.return_value.__enter__.return_value.read.return_value=json.dumps(dict(retCode=0,result=dict(readOnly=1,ips=['192.0.2.1'],permissions={}))).encode()
  with patch('urllib.request.build_opener',return_value=m):self.assertEqual(verify('bybit','fakekey1','fakesecret1')['status'],'READ_ONLY_VERIFIED')
 def test_trade_key_rejected(self):
  m=MagicMock();m.open.return_value.__enter__.return_value.read.return_value=b'{"retCode":0,"result":{"readOnly":0}}'
  with patch('urllib.request.build_opener',return_value=m),self.assertRaises(ValueError):verify('bybit','fakekey1','fakesecret1')
 def test_error_redacted(self):
  with patch('urllib.request.build_opener',side_effect=Exception('secret')),self.assertRaisesRegex(ValueError,'EXCHANGE_VERIFICATION_FAILED'):verify('binance','fakekey1','fakesecret1')
if __name__=='__main__':unittest.main()

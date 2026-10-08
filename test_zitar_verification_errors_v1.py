import io,json,unittest,urllib.error,socket
from unittest.mock import patch,MagicMock
from zitar_api_verify_v1 import verify,SAFE_ERRORS
class Tests(unittest.TestCase):
 def test_http_codes_no_sensitive_message(self):
  for code,kind in [(-1021,'CLOCK'),(-1022,'SIGNATURE'),(-2015,'KEY'),(-2014,'FORMAT'),(-9999,'HTTP')]:
   error=urllib.error.HTTPError('https://example.invalid/?signature=secret',400,'secret',{},io.BytesIO(json.dumps(dict(code=code,msg='secret')).encode()))
   with patch('urllib.request.build_opener') as builder:
    builder.return_value.open.side_effect=error
    with self.assertRaises(ValueError) as caught:verify('binance','test','secret')
    self.assertEqual(str(caught.exception),SAFE_ERRORS[kind]);self.assertNotIn('signature=secret',str(caught.exception))
 def test_network(self):
  for error,kind in [(urllib.error.URLError('sensitive'),'NETWORK'),socket.timeout('sensitive') and (socket.timeout('sensitive'),'TIMEOUT')]:
   with patch('urllib.request.build_opener') as builder:
    builder.return_value.open.side_effect=error
    with self.assertRaises(ValueError) as caught:verify('binance','test','secret')
    self.assertEqual(str(caught.exception),SAFE_ERRORS[kind])
 def test_invalid_body(self):
  with patch('urllib.request.build_opener') as builder:
   builder.return_value.open.return_value.__enter__.return_value.read.return_value=b'[]'
   with self.assertRaises(ValueError) as caught:verify('binance','test','secret')
   self.assertEqual(str(caught.exception),SAFE_ERRORS['RESPONSE'])
if __name__=='__main__':unittest.main()

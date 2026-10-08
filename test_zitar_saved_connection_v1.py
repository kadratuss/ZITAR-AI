import unittest,tempfile,json,os,time
from pathlib import Path
from unittest.mock import patch
import zitar_api_vault_v1 as v
class Tests(unittest.TestCase):
 def setUp(self):v._checks.clear()
 def test_roundtrip(self):
  try:encrypted=v.protect(b'nonsecret-test')
  except ValueError as exc:self.skipTest('Windows DPAPI unavailable in tool session: '+str(exc))
  self.assertEqual(v.unprotect(encrypted),b'nonsecret-test')
 def test_missing(self):
  with tempfile.TemporaryDirectory() as td,patch.dict(os.environ,{'LOCALAPPDATA':td}):
   self.assertEqual(v.verify_saved('binance')['error'],'NO_STORED_KEY')
 def test_saved_and_expiry(self):
  with tempfile.TemporaryDirectory() as td,patch.dict(os.environ,{'LOCALAPPDATA':td}):
   folder=Path(td)/'Zitar'/'credentials';folder.mkdir(parents=True);(folder/'binance.dpapi').write_bytes(b'fake')
   with patch.object(v,'unprotect',return_value=b'{"key":"test-key","secret":"test-secret"}'),patch('zitar_api_verify_v1.verify',return_value={'status':'READ_ONLY_VERIFIED'}) as check:
    result=v.verify_saved('binance');self.assertTrue(v.verification_status('binance')['live_verified']);v.verify_saved('binance');self.assertEqual(check.call_count,1);self.assertNotIn('secret',json.dumps(result));v._checks['binance']['checked_ms']-=61000;self.assertFalse(v.verification_status('binance')['live_verified'])
 def test_error_redacted(self):
  with tempfile.TemporaryDirectory() as td,patch.dict(os.environ,{'LOCALAPPDATA':td}):
   folder=Path(td)/'Zitar'/'credentials';folder.mkdir(parents=True);(folder/'binance.dpapi').write_bytes(b'fake')
   with patch.object(v,'unprotect',side_effect=RuntimeError('secret-sensitive')):
    self.assertEqual(v.verify_saved('binance')['error'],'STORED_KEY_VERIFICATION_FAILED')
 def test_path_rejected(self):
  with self.assertRaises(ValueError):v.verify_saved('../anything')
if __name__=='__main__':unittest.main()

import tempfile,threading,unittest,urllib.request,urllib.error
from pathlib import Path
from unittest.mock import patch
from zitar_app_manager_v1 import Manager,server
class Tests(unittest.TestCase):
 def test_recovery_dedup(self):
  m=Manager(Path('.'))
  with patch('zitar_app_manager_v1.threading.Thread') as t:
   self.assertEqual(m.recover()['state'],'RUNNING');m.recover();self.assertEqual(t.call_count,1)
  m.job={'state':'FAILED'};self.assertEqual(m.recover()['state'],'COOLDOWN')
 def test_failure_never_success(self):
  m=Manager(Path('.'))
  with patch('zitar_app_manager_v1.subprocess.run',side_effect=OSError):m.run()
  self.assertEqual(m.job['state'],'START_FAILED')
 def test_http_rejects_foreign_origin_and_host(self):
  with tempfile.TemporaryDirectory() as tmp:
   # Port chosen before factory because Host validation uses the configured port.
   import socket
   s=socket.socket();s.bind(('127.0.0.1',0));port=s.getsockname()[1];s.close()
   http=server(Path(tmp),port);t=threading.Thread(target=http.serve_forever,daemon=True);t.start()
   try:
    for headers in ({'Host':'evil.test'},{'Origin':'https://evil.test','X-Zitar-CSRF':'bad'}):
     req=urllib.request.Request(f'http://127.0.0.1:{port}/recover',data=b'',headers=headers,method='POST')
     with self.assertRaises(urllib.error.HTTPError) as err:urllib.request.urlopen(req)
     self.assertEqual(err.exception.code,403)
   finally:http.shutdown();http.server_close();t.join()

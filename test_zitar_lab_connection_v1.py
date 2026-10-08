import json,tempfile,threading,time,unittest,urllib.request
from pathlib import Path
from unittest.mock import patch,MagicMock
import zitar_indicator_lab_v1 as lab

class ConnectionTests(unittest.TestCase):
 def test_old_state_visible_but_stale_and_not_rewritten(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/lab.STATE;raw=json.dumps(dict(state='RUNNING',heartbeat_ms=1,books={'test':{'cash':'9123'}}));p.write_text(raw)
   result=lab.overview(Path(td));self.assertEqual(result['state'],'STALE');self.assertEqual(result['books']['test']['cash'],'9123');self.assertEqual(p.read_text(),raw)
 def test_same_origin_route_reads_without_reset(self):
  from zitar_full_paper_dashboard_v1 import make_server
  with tempfile.TemporaryDirectory() as td,patch.object(lab,'start_worker') as start:
   p=Path(td)/lab.STATE;raw=json.dumps(dict(state='RUNNING',heartbeat_ms=int(time.time()*1000),books={'test':{'cash':'9123'}}));p.write_text(raw)
   server=make_server(Path(td),0);worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
   try:
    with urllib.request.urlopen('http://127.0.0.1:'+str(server.server_port)+'/api/indicator-lab',timeout=3) as response:
     result=json.load(response);self.assertEqual(result['books']['test']['cash'],'9123');self.assertEqual(result['state'],'RUNNING')
    self.assertEqual(p.read_text(),raw);start.assert_called_once()
   finally:server.shutdown();server.server_close();worker.join(3)
 def test_worker_start_is_idempotent(self):
  with tempfile.TemporaryDirectory() as td,patch.object(lab.threading,'Thread') as constructor:
   fake=MagicMock();fake.is_alive.return_value=True;constructor.return_value=fake
   first=lab.start_worker(td);second=lab.start_worker(td);self.assertIs(first,second);constructor.assert_called_once();fake.start.assert_called_once()
   lab._workers.pop(str(Path(td).resolve()),None)

if __name__=='__main__':unittest.main()

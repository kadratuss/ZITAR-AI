import json
import tarfile
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from unittest.mock import patch
from zitar_next.dashboard import handler as console
from zitar_next.gateway import handler as gateway
from zitar_next.hosting import check,backup
from zitar_next.store import init,Registry
from test_zitar_next import proposal

class HostingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)/'runtime';self.base.mkdir()
        self.root=init(Path(self.temp.name)/'next')
    def server(self,make):
        server=ThreadingHTTPServer(('127.0.0.1',0),BaseHTTPRequestHandler)
        server.RequestHandlerClass=make(server.server_port)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        return server
    def test_same_origin_gateway_preserves_human_approval(self):
        target=self.server(lambda port:console(self.root,port))
        entrance=self.server(lambda port:gateway(port,research_port=target.server_port))
        origin='http://127.0.0.1:'+str(entrance.server_port)
        with urlopen(origin+'/zitar-next/') as response:
            self.assertIn(b'data-next-base="/zitar-next"',response.read())
        with urlopen(origin+'/zitar-next/api/state') as response:token=json.load(response)['csrf']
        identity=Registry(self.root).propose(proposal())
        for action in ('ACCEPT','ACTIVATE'):
            request=Request(origin+'/zitar-next/api/decision',data=json.dumps(dict(id=identity,decision=action,note='fixture human decision')).encode(),
                            headers={'Origin':origin,'Content-Type':'application/json','X-Next-CSRF':token},method='POST')
            with urlopen(request) as response:self.assertEqual(response.status,200)
        self.assertEqual(len(Registry(self.root).all()['active']),1)
        bad=Request(origin+'/zitar-next/api/decision',data=b'{}',headers={'Origin':'https://foreign.example'},method='POST')
        with self.assertRaises(HTTPError) as error:urlopen(bad)
        self.assertEqual(error.exception.code,403);error.exception.close()
    def test_handoff_and_real_order_flags_fail_closed(self):
        master=dict(schema='ZITAR_MASTER_PORTFOLIO_V1',authorities=dict(real_order=False,futures_allocation=False),rules=dict(futures_enabled=False))
        (self.base/'zitar_master_portfolio_v1.json').write_text(json.dumps(master))
        with self.assertRaises(FileNotFoundError):check(self.base,self.root)
        (self.base/'HOSTING_HANDOFF.json').write_text(json.dumps(dict(source_owners_stopped=True,real_orders=False)))
        self.assertTrue(check(self.base,self.root)['paper_only'])
        master['authorities']['real_order']=True
        (self.base/'zitar_master_portfolio_v1.json').write_text(json.dumps(master))
        with self.assertRaises(ValueError):check(self.base,self.root)

    def test_entry_filter_report_is_read_only_and_cannot_be_redirected(self):
        folder=Path(self.temp.name)/'filter';folder.mkdir()
        (folder/'status.json').write_text(json.dumps(dict(state='COMPLETE')))
        (folder/'summary.json').write_text(json.dumps(dict(state='COMPLETE',real_orders=False)))
        entrance=self.server(lambda port:gateway(port,filter_root=folder))
        origin='http://127.0.0.1:'+str(entrance.server_port)
        with urlopen(origin+'/api/entry-filter') as response:
            self.assertFalse(json.load(response)['real_orders'])
        request=Request(origin+'/api/entry-filter',data=b'{}',headers={'Origin':origin},method='POST')
        with self.assertRaises(HTTPError) as error:urlopen(request)
        self.assertEqual(error.exception.code,405);error.exception.close()

    def test_operations_observation_endpoint_is_read_only(self):
        status=Path(self.temp.name)/'ops.json'
        status.write_text(json.dumps(dict(status='OBSERVING_24H',real_orders=False)))
        entrance=self.server(lambda port:gateway(port,ops_status=status))
        origin='http://127.0.0.1:'+str(entrance.server_port)
        with urlopen(origin+'/api/operations-study') as response:
            self.assertEqual(json.load(response)['status'],'OBSERVING_24H')
        with self.assertRaises(HTTPError) as error:
            urlopen(Request(origin+'/api/operations-study',data=b'{}',headers={'Origin':origin},method='POST'))
        self.assertEqual(error.exception.code,405);error.exception.close()

    def test_legacy_adapter_exposes_reads_only(self):
        from types import SimpleNamespace
        from zitar_next.legacy_data import handler
        class Original(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def send_bytes(self,body,mime,status=200):
                self.send_response(status);self.end_headers();self.wfile.write(body)
            def do_GET(self):self.send_bytes(b'{"strategies":{}}','application/json')
        server=self.server(lambda port:handler(SimpleNamespace(Handler=Original)))
        origin='http://127.0.0.1:'+str(server.server_port)
        with urlopen(origin+'/api/dashboard') as response:self.assertEqual(response.status,200)
        for request in (Request(origin+'/api/chat-proxy/chat',data=b'{}',method='POST'),Request(origin+'/unknown')):
            with self.assertRaises(HTTPError) as error:urlopen(request)
            self.assertIn(error.exception.code,(404,405));error.exception.close()
    def test_backup_restore_preserves_registry_and_has_no_deletion(self):
        identity=Registry(self.root).propose(proposal(False))
        (self.base/'account.json').write_text('{"cash":"10000"}')
        with patch('zitar_next.hosting.assert_stopped'):
            result=backup(self.base,self.root,Path(self.temp.name)/'backups')
        self.assertFalse(result['automatic_deletion'])
        with tarfile.open(result['path']) as archive:
            self.assertEqual(archive.extractfile('runtime/account.json').read(),b'{"cash":"10000"}')
            restored=Path(self.temp.name)/'restored';archive.extractall(restored,filter='data')
        self.assertEqual(Registry(restored/'next').all()['proposals'][0]['id'],identity)

if __name__=='__main__':unittest.main()

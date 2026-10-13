import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from html.parser import HTMLParser
from zitar_next.store import init
from zitar_next.integration import ResearchASGI, mount_fastapi


class UnifiedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)/'next'
        init(self.root)
        self.app = ResearchASGI(self.root,'http://127.0.0.1:9000')

    def request(self,path,method='GET',headers=None,body=b''):
        output=[]
        async def receive():
            return dict(type='http.request',body=body)
        async def send(value):
            output.append(value)
        scope=dict(type='http',method=method,path=path,query_string=b'',
                   headers=headers or [(b'host',b'127.0.0.1:9000')])
        asyncio.run(self.app(scope,receive,send))
        return output[0]['status'],output[-1]['body']

    def test_prefix_and_unique_ids(self):
        status,body=self.request('/zitar-next/')
        self.assertEqual(status,200)
        html=body.decode()
        self.assertIn('data-next-base="/zitar-next"',html)
        ids=[]
        class Parser(HTMLParser):
            def handle_starttag(self,tag,attrs):
                ids.extend(v for k,v in attrs if k=='id')
        Parser().feed(html)
        self.assertEqual(len(ids),len(set(ids)))
        self.assertIn('hist_chart',ids)
        self.assertIn('strategies',ids)

    def test_optional_history_and_state(self):
        status,body=self.request('/zitar-next/api/history/runs')
        self.assertEqual((status,json.loads(body)),(200,{'runs':[]}))
        self.assertEqual(self.request('/zitar-next/api/state')[0],200)

    def test_security_and_size(self):
        self.assertEqual(self.request('/zitar-next/api/decision','POST',body=b'{}')[0],403)
        self.assertEqual(self.request('/zitar-next/',headers=[(b'host',b'evil.example')])[0],403)
        self.assertEqual(self.request('/zitar-next/','POST',body=b'x'*4097)[0],413)

    def test_mount_is_explicit_and_origin_is_local(self):
        class App:
            def mount(self,*args,**kwargs):
                self.args=args
        app=App()
        mount_fastapi(app,self.root,'http://127.0.0.1:9000')
        self.assertEqual(app.args[0],'/zitar-next')
        for origin in ['https://example.com','http://localhost:9000','http://127.0.0.1:9000/path']:
            with self.assertRaises(ValueError):
                ResearchASGI(self.root,origin)


if __name__=='__main__':
    unittest.main()

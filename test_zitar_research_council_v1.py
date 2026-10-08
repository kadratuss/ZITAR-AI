import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from zitar_research_council_v1 import enqueue,get_job,execute,audit_claims,remember,database,ROLES
from zitar_public_reader_v1 import validate_url,PublicHTTPS

TEXT='The issuer reports that research observations require independent verification before trading decisions.'
PAGE=dict(source_id='s0',status='READ_NOT_VERIFIED',text=TEXT,final_url='https://example.com/report',sha256='abc',retrieved_utc='2026-09-26T00:00:00+00:00')

def ask(role,instruction,data):
    if role=='extractor': return dict(claims=[dict(text='Araştırma gözlemleri bağımsız doğrulama gerektirir.',evidence=[dict(source_id='s0',quote=TEXT)])])
    if role=='skeptic': return dict(summary='Alıntı iddiayı destekliyor.',challenged_claim_ids=[])
    if role=='experiment_designer': return dict(proposals=[dict(hypothesis='Maliyet filtresi net getiriyi iyileştirebilir.',test='İzole karşılaştırma.',failure_criterion='Net getiri düşerse reddet.')])
    return dict(summary='Yetersiz güncel veri; sonuç sınırlı.')

class CouncilTests(unittest.TestCase):
    def test_ten_stages_persist_and_no_execution(self):
        with tempfile.TemporaryDirectory() as d:
            job=enqueue(d,'maliyet araştırması','one')
            self.assertEqual(enqueue(d,'maliyet araştırması','one'),job)
            r=execute(d,job,'maliyet araştırması',ask,lambda q:dict(urls=['https://example.com']),lambda urls:[PAGE])
            self.assertEqual(set(r['agent_outputs']),set(ROLES))
            self.assertFalse(r['verified']);self.assertFalse(r['execution_authority'])
            self.assertEqual(get_job(d,job,'one')['state'],'COMPLETED_WITH_LIMITATIONS')
            with self.assertRaises(KeyError):get_job(d,job,'other')
            self.assertEqual(remember(d,'araştırma')[0]['status'],'CITED_NOT_VERIFIED')
            self.assertEqual([p.name for p in Path(d).iterdir()],['zitar_research_council_v1.sqlite3'])
    def test_fabricated_quote_rejected(self):
        a=audit_claims([dict(text='Yüksek getiri kesin.',evidence=[dict(source_id='s0',quote='This sentence is not in the source document.')])],[PAGE])
        self.assertEqual(a['cited'],[])
    def test_critic_failure_blocks_learning(self):
        def failing(role,instruction,data):
            if role=='skeptic':raise TimeoutError('offline')
            return ask(role,instruction,data)
        with tempfile.TemporaryDirectory() as d:
            job=enqueue(d,'maliyet araştırması','one')
            execute(d,job,'maliyet araştırması',failing,lambda q:dict(urls=[]),lambda urls:[PAGE])
            self.assertEqual(remember(d,'araştırma'),[])
    def test_challenged_evidence_blocks_proposals(self):
        def challenged(role,instruction,data):
            if role=='skeptic':return dict(summary='Kanıt yetersiz.',challenged_claim_ids=['c0'])
            return ask(role,instruction,data)
        with tempfile.TemporaryDirectory() as d:
            job=enqueue(d,'ZİTAR maliyet araştırması','one')
            result=execute(d,job,'ZİTAR maliyet araştırması',challenged,lambda q:dict(urls=[]),lambda urls:[PAGE])
            self.assertEqual(result['proposals'],[])
    def test_dashboard_job_roundtrip(self):
        import threading,json,urllib.request
        from zitar_full_paper_dashboard_v1 import make_server
        with tempfile.TemporaryDirectory() as d:
            server=make_server(Path(d),0)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                url='http://127.0.0.1:'+str(server.server_port)
                body=json.dumps(dict(question='XRP araştır',session_id='http-test')).encode()
                req=urllib.request.Request(url+'/api/chat-proxy/chat',data=body,headers={'Content-Type':'application/json'})
                with urllib.request.urlopen(req) as response: accepted=json.load(response)
                job=accepted['council_job_id']
                execute(d,job,'XRP araştır',ask,lambda q:dict(urls=[]),lambda urls:[PAGE])
                with urllib.request.urlopen(url+'/api/research-job?id='+job+'&session_id=http-test') as response:
                    result=json.load(response)
                self.assertEqual(result['state'],'COMPLETED_WITH_LIMITATIONS')
                with urllib.request.urlopen(url+'/api/chat-proxy/history?session_id=http-test') as response:
                    history=json.load(response)
                self.assertIn('Kaynaklardan',history['turns'][0]['answer'])
            finally:
                server.shutdown();server.server_close();thread.join(2)
    def test_public_reader_blocks_local_destinations(self):
        for url in ['http://example.com','https://user:pass@example.com','https://example.com:5020']:
            with self.assertRaises(ValueError):validate_url(url)
        with patch('socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]):
            with self.assertRaises(ValueError):PublicHTTPS('example.com').connect()

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from io import BytesIO
import zitar_model_provider_v1 as provider

class ProviderTests(unittest.TestCase):
    def setup_files(self,d):
        base=Path(d)
        config=dict(provider='ollama',base_url='http://127.0.0.1:11434',model='zitar:base-v1',
                    base_model='qwen2.5:7b',fine_tuned=False,identity_file='identity.txt',timeout_seconds=30,
                    roles={'skeptic':'another-local-model'})
        (base/'identity.txt').write_text('Sen ZİTAR.',encoding='utf-8')
        (base/'zitar_model_config_v1.json').write_text(json.dumps(config),encoding='utf-8')
        return base,config
    def test_role_selection_and_identity(self):
        with tempfile.TemporaryDirectory() as d:
            base,_=self.setup_files(d)
            response=BytesIO(json.dumps({'message':{'content':'{"summary":"ok"}'}}).encode())
            with patch.object(provider.urllib.request,'urlopen',return_value=response) as request:
                result=provider.chat([dict(role='user',content='test')],role='skeptic',json_mode=True,base=base)
                payload=json.loads(request.call_args.args[0].data)
                self.assertEqual(payload['model'],'another-local-model')
                self.assertIn('ZİTAR',payload['messages'][0]['content'])
                self.assertEqual(result,{'summary':'ok'})
    def test_remote_endpoint_not_silently_allowed(self):
        with tempfile.TemporaryDirectory() as d:
            base,c=self.setup_files(d);c['base_url']='https://example.com'
            (base/'zitar_model_config_v1.json').write_text(json.dumps(c))
            with self.assertRaises(ValueError):provider.settings(base)
    def test_invalid_json_is_not_success(self):
        with tempfile.TemporaryDirectory() as d:
            base,_=self.setup_files(d)
            with patch.object(provider.urllib.request,'urlopen',return_value=BytesIO(b'{"message":{"content":"[]"}}')):
                with self.assertRaises(ValueError):provider.chat([],json_mode=True,base=base)

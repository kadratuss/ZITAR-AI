import io
import json
import unittest
from unittest.mock import patch
from assistant_foundation import zitar_model_provider_v1 as provider


class LatencyTests(unittest.TestCase):
    def test_bounded_conversation_and_keepalive(self):
        config={'model':'test','roles':{},'base_url':'http://127.0.0.1:11434','timeout_seconds':100}
        with patch.object(provider,'settings',return_value=(config,'identity')), patch.object(provider.urllib.request,'urlopen',return_value=io.BytesIO(b'{"message":{"content":"ok"}}')) as call:
            self.assertEqual(provider.chat([{'role':'user','content':'hello'}],max_tokens=450),'ok')
        payload=json.loads(call.call_args.args[0].data)
        self.assertEqual(payload['options']['num_ctx'],4096)
        self.assertEqual(payload['options']['num_predict'],300)
        self.assertEqual(payload['keep_alive'],'30m')
        self.assertEqual(call.call_args.kwargs['timeout'],180)

    def test_planner_preserves_json_limit(self):
        config={'model':'test','roles':{},'base_url':'http://127.0.0.1:11434','timeout_seconds':100}
        with patch.object(provider,'settings',return_value=(config,'identity')), patch.object(provider.urllib.request,'urlopen',return_value=io.BytesIO(b'{"message":{"content":"{\\"expression\\":\\"2+2\\"}"}}')) as call:
            self.assertEqual(provider.chat([],role='tool_planner',json_mode=True,max_tokens=100)['expression'],'2+2')
        payload=json.loads(call.call_args.args[0].data)
        self.assertEqual(payload['format'],'json');self.assertEqual(payload['options']['num_predict'],100)

if __name__=='__main__':unittest.main()

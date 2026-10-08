import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
import zitar_runtime_v1 as core
import zitar_unified_chat_v1 as chat

class ChatTests(unittest.TestCase):
    def test_hey_after_research_does_not_enqueue(self):
        with tempfile.TemporaryDirectory() as temp:
            chat.answer(temp,'xrp durumu nedir','social')
            before=len(chat.pending_gaps(temp))
            with patch('zitar_research_council_v1.enqueue') as enqueue:
                result=chat.answer(temp,'hey','social')
                self.assertEqual(result['route'],'CONVERSATION')
                self.assertNotIn('council_job_id',result)
                enqueue.assert_not_called()
            self.assertEqual(len(chat.pending_gaps(temp)),before)
    def test_research_dialogue_uses_tools_not_model(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(chat, 'web_search', return_value=dict(status='NO_RESULTS',sources=[])) as search, patch.object(chat, 'converse') as model:
            for question in ['xrp durumu nedir', 'et o zaman', 'bist bieny hissesini arastir']:
                result = chat.answer(temp, question, 'research')
                self.assertEqual(result['route'], 'WEB_RESEARCH')
            from zitar_research_council_v1 import database
            with database(temp) as db:
                self.assertEqual([r['question'] for r in db.execute('SELECT question FROM jobs ORDER BY created')], ['xrp durumu nedir','bist bieny hissesini arastir'])
            model.assert_not_called()
            self.assertEqual(len(chat.pending_gaps(temp)),2)

    def test_greeting_never_creates_research(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(core, 'answer') as lookup:
            result = chat.answer(temp, 'selam', 'hello')
            self.assertEqual(result['route'], 'CONVERSATION')
            self.assertIn('Selam', result['answer'])
            self.assertEqual(chat.pending_gaps(temp), [])
            lookup.assert_not_called()

    def test_model_receives_previous_turn_and_is_not_verified(self):
        with tempfile.TemporaryDirectory() as temp:
            chat.answer(temp, 'selam', 'context')
            with patch.object(core, 'answer', return_value=dict(route='KNOWLEDGE_GAP', grounded=False)), patch.object(chat, 'converse', return_value='Birlikte konuşabiliriz.') as model:
                result = chat.answer(temp, 'Sohbet edelim', 'context')
                self.assertEqual(model.call_args.args[1][0]['question'], 'selam')
                self.assertFalse(result['grounded'])
                self.assertEqual(chat.pending_gaps(temp), [])

    def test_model_failure_is_explicit(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(core, 'answer', return_value=dict(route='KNOWLEDGE_GAP', grounded=False)), patch.object(chat, 'converse', side_effect=TimeoutError):
            result = chat.answer(temp, 'Biraz konuşalım', 'failure')
            self.assertEqual(result['route'], 'CONVERSATION_UNAVAILABLE')
            self.assertEqual(chat.pending_gaps(temp), [])

    def test_real_renderer_preserves_symbol_and_missing_evidence(self):
        from zitar_finance_grounded_renderer_v1 import render
        sample = dict(requested_symbol='ETHUSDT', status='EVIDENCE_AVAILABLE',
                      evidence=dict(funding=0.1, basis_bps=2, oi24h_pct=3,
                                    long_short_ratio=4, taker_ratio=5),
                      temporal={}, policy=dict(directional_allowed=False))
        answer = render(sample)
        self.assertIn('ETHUSDT', answer)
        self.assertNotIn('BTCUSDT', answer)
        missing = render(dict(requested_symbol='BTCTRY', status='SYMBOL_NOT_FOUND'))
        self.assertIn('BTCTRY', missing)
        self.assertIn('bulunamadı', missing)

    def test_symbol_is_not_replaced_with_btc(self):
        for question, symbol in [('ETH funding', 'ETHUSDT'), ('SOLUSDT piyasa', 'SOLUSDT'), ('BTCTRY piyasa', 'BTCTRY')]:
            with patch.object(core, 'build_finance', return_value={}) as build, patch.object(core, 'render_finance', return_value='evidence'):
                result = core.answer(question, 'test')
                build.assert_called_once_with(symbol)
                self.assertEqual(result['symbol'], symbol)

    def test_ambiguous_symbol_asks(self):
        for question in ['piyasa nasıl', 'BTC ETH funding']:
            with patch.object(core, 'build_finance') as build:
                self.assertEqual(core.answer(question)['route'], 'CLARIFICATION')
                build.assert_not_called()

    def test_persistence_dedup_and_session_isolation(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(chat, 'web_search', return_value=dict(status='NO_RESULTS',sources=[])), patch.object(chat, 'converse', return_value='Test yanıtı'), patch.object(core, 'answer', side_effect=lambda *a: dict(route='KNOWLEDGE_GAP', source='CORE_RUNTIME', answer='missing')):
                chat.answer(temp, 'likidite maliyet etkisini araştır', 'one')
                chat.answer(temp, 'likidite maliyet etkisini araştır', 'one')
            self.assertEqual(len(chat.pending_gaps(temp)), 1)
            self.assertEqual(len(chat.history(temp, 'one')), 2)
            self.assertEqual(chat.history(temp, 'two'), [])
            self.assertFalse(chat.history(temp, 'one')[0]['authority']['execution'])

    def test_invalid_session_does_not_write(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                chat.answer(temp, 'test', '../outside')
            self.assertEqual(list(Path(temp).iterdir()), [])

if __name__ == '__main__':
    unittest.main()




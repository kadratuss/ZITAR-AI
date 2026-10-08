import unittest
from zitar_chat_search_v1 import resolve, search, render

class SearchTests(unittest.TestCase):
    def test_social_message_does_not_inherit_research(self):
        for history in [[{'search_query':'XRP'}],[{'route':'CLARIFICATION'}]]:
            for text in ['hey','Hey!','selam','nasılsın','teşekkürler','tamam']:
                self.assertIsNone(resolve(text,history))
        self.assertIsNone(resolve('anladım',[{'search_query':'XRP'}]))
    def test_user_screenshot_sequence(self):
        topic = 'xrp durumu nedir'
        self.assertEqual(resolve(topic, []), topic)
        self.assertEqual(resolve('et ozaman', []), '')
        self.assertEqual(resolve('et o zaman', [{'question':topic}]), topic)
        self.assertEqual(resolve('bist bieny hissesini arastir', [{'question':topic}]), 'bist bieny hissesini arastir')
        self.assertEqual(resolve('et o zaman', []), '')

    def test_do_not_resume_stale_topic_after_greeting(self):
        self.assertEqual(resolve('et o zaman', [{'search_query':'XRP'}, {'question':'merhaba'}]), '')

    def test_xrp_followup(self):
        self.assertEqual(resolve('xrp',[{'route':'CLARIFICATION'}]), 'xrp')
        self.assertEqual(resolve('sen araştır',[{'question':'xrp','search_query':'xrp'}]), 'xrp')
        self.assertEqual(resolve('sen arastir',[{'question':'xrp'}]), 'xrp')
    def test_global_stock(self):
        self.assertEqual(resolve('Japon borsasında Toyota hissesini araştır',[]),'Japon borsasında Toyota hissesini araştır')
        self.assertIsNone(resolve('selam',[]))
        self.assertEqual(resolve('sen araştır',[]),'')
    def test_search_is_not_verified(self):
        def fetcher(*args):
            return b'', '<rss><channel><item><title>Toyota Issuer</title><link>https://example.com/ir</link><description>Public information</description></item></channel></rss>', {}, ''
        evidence=search('Toyota',fetcher)
        self.assertFalse(evidence['verified'])
        self.assertIn('henüz doğrulanmadı',render(evidence))
    def test_failure_honest(self):
        def fetcher(*args): raise TimeoutError('timeout')
        self.assertIn('TimeoutError',render(search('XRP',fetcher)))

    def test_unrelated_results_are_rejected(self):
        def fetcher(*args):
            return b'', '<rss><channel><item><title>Windows applications</title><link>https://example.com/</link><description>Computer news</description></item></channel></rss>', {}, ''
        result = search('xrp durumu nedir', fetcher)
        self.assertEqual(result['sources'], [])
        self.assertEqual(result['status'], 'NO_RELEVANT_RESULTS')

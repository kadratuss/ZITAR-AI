import unittest
from zitar_research_council_v1 import retry_query
from zitar_chat_search_v1 import resolve,search
class LearningFoundation(unittest.TestCase):
 def test_conversation_topic(self):
  for n in (1,2,3):
   q=retry_query('kendini konuşma düzeyini geliştirmek için araştırmanı istiyorum',n)
   self.assertIn('conversational AI',q)
   self.assertNotIn('likidite',q)
 def test_general_retry_not_finance(self):
  self.assertNotIn('işlem maliyeti',retry_query('Türkçe öğrenme yöntemleri',3))
 def test_humor_stays_conversation(self):
  self.assertIsNone(resolve('piyasa hakkında bir espri yap',[]))
  self.assertIsNotNone(resolve('yapay zeka mizah yeteneğini araştır',[]))
 def test_printer_results_rejected(self):
  xml='<rss><channel><item><title>Printer official research</title><link>https://example.com/printer</link><description>printer model context</description></item><item><title>Conversational AI dialogue evaluation</title><link>https://example.com/dialogue</link><description>research</description></item></channel></rss>'
  r=search('conversational AI dialogue context natural conversation evaluation',lambda *a:(None,xml,None,None))
  self.assertEqual(len(r['sources']),1)
  self.assertEqual(r['rejected_count'],1)
if __name__=='__main__':unittest.main()

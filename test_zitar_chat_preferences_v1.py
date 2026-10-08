import tempfile
import unittest
from unittest.mock import patch
import zitar_unified_chat_v1 as chat
from zitar_chat_preferences_v1 import handle
class PreferenceTests(unittest.TestCase):
 def test_persist_overwrite_isolate_delete(self):
  with tempfile.TemporaryDirectory() as d:
   handle(d,'a','esprili konuş')
   self.assertEqual(handle(d,'a','merhaba')[0]['tone'],'playful')
   self.assertEqual(handle(d,'b','merhaba')[0],{})
   handle(d,'a','daha ciddi ol')
   self.assertEqual(handle(d,'a','merhaba')[0]['tone'],'serious')
   handle(d,'a','konuşma tercihlerimi unut')
   self.assertEqual(handle(d,'a','merhaba')[0],{})
 def test_no_inferred_preference(self):
  with tempfile.TemporaryDirectory() as d:
   self.assertEqual(handle(d,'a','Arkadaşım esprili konuş dedi')[0],{})
 def test_model_receives_preference(self):
  with tempfile.TemporaryDirectory() as d, patch.object(chat.core,'answer',return_value={'route':'KNOWLEDGE_GAP','grounded':False}),patch.object(chat,'converse',return_value='Merhaba.') as model:
   r=chat.answer(d,'kısa cevap ver','a')
   self.assertEqual(r['route'],'CONVERSATION_PREFERENCE')
   model.assert_not_called()
   chat.answer(d,'Biraz konuşalım','a')
   self.assertIn('kısa',model.call_args.args[2])
   self.assertEqual(chat.pending_gaps(d),[])
if __name__=='__main__':unittest.main()

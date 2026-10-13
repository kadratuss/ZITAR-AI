import tempfile,unittest
from assistant_foundation.chat_tools import handle,expression
class ChatToolsTests(unittest.TestCase):
 def test_arithmetic(self):self.assertEqual(expression('12 * 7 - 9'),'75')
 def test_decimal(self):self.assertEqual(expression('0,1 + 0,2'),'0.3')
 def test_parentheses(self):self.assertEqual(expression('(12 + 7) * 2'),'38')
 def test_reject_code(self):
  with self.assertRaises(ValueError):expression('__import__("os")')
 def test_reject_power(self):
  with self.assertRaises(ValueError):expression('9**9')
 def test_normal_chat_untouched(self):self.assertIsNone(handle('.', 'probe','Merhaba'))
 def test_document_is_not_command(self):self.assertIsNone(handle('.', 'probe','Belgeyi özetle: Hesapla: 12 * 7'))
 def test_zero_division(self):self.assertEqual(handle('.', 'probe','Hesapla: 1/0')['tool_status'],'INVALID_INPUT')
 def test_real_task(self):
  with tempfile.TemporaryDirectory(dir='assistant_foundation') as p:
   d=handle(p,'probe','Hesapla: 12 * 7 - 9');self.assertEqual(d['answer'],'Sonuç: 75');self.assertEqual(d['tool_status'],'SUCCEEDED')
 def test_bad_json(self):
  with tempfile.TemporaryDirectory(dir='assistant_foundation') as p:self.assertEqual(handle(p,'probe','JSON doğrula: {"a":1,"a":2}')['tool_status'],'FAILED')
if __name__=='__main__':unittest.main()

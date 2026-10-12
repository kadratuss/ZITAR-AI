import tempfile
import unittest
from assistant_foundation.project_memory import Memory, handle


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(dir='assistant_foundation')
        self.base = self.folder.name

    def tearDown(self): self.folder.cleanup()

    def test_save_and_reopen(self):
        m = Memory(self.base, 'a'); identity = m.put('Atlas', 'Pazartesi')
        self.assertEqual(Memory(self.base, 'a').list()[0]['id'], identity)

    def test_session_isolation(self):
        Memory(self.base, 'a').put('Atlas', 'Pazartesi')
        self.assertEqual(Memory(self.base, 'b').list(), [])

    def test_correction(self):
        m = Memory(self.base, 'a'); identity=m.put('Atlas', 'Pazartesi');m.put('Atlas','Salı',identity)
        self.assertEqual(m.list()[0]['text'], 'Salı'); self.assertEqual(m.list()[0]['revision'], 2)

    def test_forget(self):
        m=Memory(self.base,'a');identity=m.put('Atlas','Pazartesi');m.forget(identity)
        self.assertEqual(m.list(), [])

    def test_document_does_not_save(self):
        self.assertIsNone(handle(self.base,'a','Belge: Proje notu kaydet: Atlas | test'))

    def test_unknown_correction(self):
        r=handle(self.base,'a','Proje notunu düzelt: missing | Salı')
        self.assertEqual(r['route'],'MEMORY_INPUT_ERROR')

    def test_input_command(self):
        r=handle(self.base,'a','Proje notu kaydet: Atlas | Pazartesi')
        self.assertEqual(r['route'],'PROJECT_MEMORY')
        self.assertEqual(Memory(self.base,'a').list()[0]['source'],'USER_STATED_NOT_VERIFIED')

if __name__ == '__main__': unittest.main()

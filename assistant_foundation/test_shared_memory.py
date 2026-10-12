import tempfile
import unittest
from assistant_foundation.project_memory import Memory, scope, handle


class SharedTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory(dir='assistant_foundation');self.base=self.folder.name

    def tearDown(self): self.folder.cleanup()

    def test_two_devices_share_selected_project(self):
        scope(self.base,'pc','ZİTAR');scope(self.base,'phone','zitar')
        identity=Memory(self.base,'pc').put('ZİTAR','Hedef genel asistan.')
        self.assertEqual(Memory(self.base,'phone').list()[0]['id'],identity)

    def test_different_projects_isolated(self):
        scope(self.base,'pc','ZİTAR');Memory(self.base,'pc').put('ZİTAR','Test')
        scope(self.base,'phone','Atlas');self.assertEqual(Memory(self.base,'phone').list(),[])

    def test_private_notes_not_migrated(self):
        Memory(self.base,'pc').put('Atlas','Özel')
        scope(self.base,'pc','Atlas');self.assertEqual(Memory(self.base,'pc').list(),[])
        scope(self.base,'pc',private=True);self.assertEqual(Memory(self.base,'pc').list()[0]['text'],'Özel')

    def test_wrong_project_rejected(self):
        scope(self.base,'pc','Atlas')
        with self.assertRaises(ValueError):Memory(self.base,'pc').put('ZİTAR','Test')

    def test_project_binding_survives_reopen(self):
        handle(self.base,'pc','Ortak proje seç: Atlas')
        self.assertEqual(scope(self.base,'pc'),'Atlas')

    def test_foreign_session_path_rejected(self):
        with self.assertRaises(ValueError):scope(self.base,'../','Atlas')

    def test_shared_correction(self):
        scope(self.base,'pc','Atlas');scope(self.base,'phone','Atlas')
        identity=Memory(self.base,'pc').put('Atlas','Pazartesi')
        handle(self.base,'phone','Proje notunu düzelt: '+identity+' | Salı')
        self.assertEqual(Memory(self.base,'pc').list()[0]['text'],'Salı')

if __name__ == '__main__':unittest.main()

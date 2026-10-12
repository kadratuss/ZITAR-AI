import tempfile
import unittest
from assistant_foundation.project_memory import scope, Memory
from assistant_foundation.conversations import conversation_session


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory(dir='assistant_foundation');self.base=self.folder.name

    def tearDown(self):self.folder.cleanup()

    def test_same_project_same_conversation(self):
        scope(self.base,'pc','ZİTAR');scope(self.base,'phone','zitar')
        self.assertEqual(conversation_session(self.base,'pc'),conversation_session(self.base,'phone'))

    def test_different_projects_different_conversation(self):
        scope(self.base,'pc','ZİTAR');scope(self.base,'phone','Atlas')
        self.assertNotEqual(conversation_session(self.base,'pc'),conversation_session(self.base,'phone'))

    def test_alias_is_stable(self):
        scope(self.base,'pc','Atlas');identity=conversation_session(self.base,'pc')
        self.assertEqual(identity,conversation_session(self.base,identity))
        self.assertEqual(Memory(self.base,identity).project,'Atlas')

    def test_project_switch_does_not_move_other_device(self):
        scope(self.base,'pc','Atlas');scope(self.base,'phone','Atlas')
        identity=conversation_session(self.base,'phone');scope(self.base,'pc','ZİTAR')
        self.assertEqual(conversation_session(self.base,'phone'),identity)
        self.assertNotEqual(conversation_session(self.base,'pc'),identity)

    def test_private_return(self):
        scope(self.base,'pc','Atlas');scope(self.base,'pc',private=True)
        self.assertEqual(conversation_session(self.base,'pc'),'pc')

if __name__=='__main__':unittest.main()

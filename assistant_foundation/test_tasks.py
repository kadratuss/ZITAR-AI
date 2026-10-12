import tempfile
import unittest
from assistant_foundation.tasks import Tasks


class TaskTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(dir='assistant_foundation')
        self.tasks = Tasks(self.folder.name)

    def tearDown(self): self.folder.cleanup()

    def test_real_result_and_reopen(self):
        identity = self.tasks.submit('calculate', {'operation': 'multiply', 'operands': [12, 7]})
        self.assertEqual(self.tasks.get(identity)['state'], 'QUEUED')
        result = self.tasks.execute(identity)
        self.assertEqual(result['state'], 'SUCCEEDED')
        self.assertEqual(result['result']['result'], '84')
        reopened = Tasks(self.folder.name)
        self.assertEqual(reopened.get(identity), result)
        self.assertEqual(reopened.execute(identity), result)

    def test_failure_never_claims_success(self):
        identity = self.tasks.submit('calculate', {'operation': 'divide', 'operands': [1, 0]})
        result = self.tasks.execute(identity)
        self.assertEqual(result['state'], 'FAILED')
        self.assertIsNone(result['result'])

    def test_unregistered_tool_rejected(self):
        with self.assertRaises(ValueError): self.tasks.submit('shell', {'command': 'anything'})

    def test_workspace_isolation(self):
        identity = self.tasks.submit('validate_json', {'text': '{}'})
        with tempfile.TemporaryDirectory(dir='assistant_foundation') as folder:
            with self.assertRaises(KeyError): Tasks(folder).get(identity)

if __name__ == '__main__': unittest.main()

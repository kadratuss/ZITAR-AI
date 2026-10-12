import tempfile
import unittest
from assistant_foundation.natural_tools import candidate, route


class NaturalTests(unittest.TestCase):
    question = '7 kutuda 12 kalem var, 9 kullanıldı. Kaç kalem kaldı?'

    def test_plan_executed_by_exact_tool(self):
        with tempfile.TemporaryDirectory(dir='assistant_foundation') as root:
            r = route(root, 'a', self.question, lambda q: {'expression': '7*12-9'})
            self.assertEqual(r['tool_result']['result'], '75')
            self.assertEqual(r['tool_status'], 'SUCCEEDED')

    def test_invented_numbers(self):
        r = route('.', 'a', self.question, lambda q: {'expression': '999+1'})
        self.assertEqual(r['tool_status'], 'PLAN_NOT_VERIFIED')

    def test_code_is_rejected(self):
        r = route('.', 'a', self.question, lambda q: {'expression': '__import__("os")'})
        self.assertEqual(r['tool_status'], 'PLAN_NOT_VERIFIED')

    def test_ambiguous(self):
        self.assertEqual(route('.', 'a', self.question, lambda q: {'clarify': True})['tool_status'], 'PLAN_NOT_VERIFIED')

    def test_document_does_not_trigger(self):
        self.assertFalse(candidate('Belgeyi özetle: 12 kalem, 7 kutu; hesapla.'))

    def test_normal_conversation(self): self.assertIsNone(route('.', 'a', 'Nasılsın?'))

    def test_extra_actions_rejected(self):
        r = route('.', 'a', self.question, lambda q: {'expression': '7*12-9', 'shell': 'anything'})
        self.assertEqual(r['tool_status'], 'PLAN_NOT_VERIFIED')

if __name__ == '__main__': unittest.main()

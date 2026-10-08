import copy
import json
import tempfile
import unittest
from pathlib import Path
from zitar_training_data_v1 import TRAIN,EVAL,validate,build
from zitar_model_evaluation_v1 import score

class TrainingTests(unittest.TestCase):
    def test_separation_and_draft_gate(self):
        with tempfile.TemporaryDirectory() as d:
            manifest=build(d)
            self.assertFalse(manifest['training_approved'])
            self.assertFalse(manifest['trained'])
            self.assertEqual(manifest['training_examples'],12)
            self.assertEqual(len((Path(d)/'zitar_training'/'evaluation.jsonl').read_text(encoding='utf-8').splitlines()),8)
    def test_duplicate_and_leakage_blocked(self):
        with self.assertRaises(ValueError):validate(TRAIN+[TRAIN[0]],EVAL)
        evaluation=copy.deepcopy(EVAL)
        evaluation[0]['messages']=TRAIN[0]['messages'][:-1]
        with self.assertRaises(ValueError):validate(TRAIN,evaluation)
    def test_rubric_requires_review_even_when_keywords_pass(self):
        result=score(EVAL[0],'Ben ZİTAR, temel modelim Qwen.')
        self.assertTrue(result['heuristic_pass'])
        self.assertTrue(result['human_review_required'])
        self.assertFalse(score(EVAL[0],'Ben başka bir modelim.')['heuristic_pass'])

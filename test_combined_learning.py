import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from test_zitar_next import snapshot
from zitar_next.paper import decision
from zitar_next.store import init,Registry,digest
from zitar_next.worker import train_round

class CombinedLearningTests(unittest.TestCase):
    def test_actual_paper_decision_uses_approved_blend(self):
        models=[Mock(),Mock()]
        for model in models:model.predict.return_value=(2,None)
        body=dict(market='futures',combination=dict(selected_ai_weight=.5))
        self.assertEqual(decision(body,models,None,dict(date='closed'),{'closed':1}),0)
        self.assertEqual(decision(body,models,None,dict(date='closed'),{'closed':2}),2)

    def test_training_registers_combination_and_freezes_holdout_anchor(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=init(Path(temporary)/'next')
            body=train_round(root,'futures','BTCUSDT',128,snapshot=snapshot(count=300))
            self.assertEqual(body['strategy'],'PPO_ZITAR_RSI14')
            self.assertEqual(body['combination']['rule_name'],'RSI14')
            registry=Registry(root).all()
            self.assertEqual(registry['proposals'][0]['id'],digest(body))
            self.assertFalse(body['eligible'])
            anchor=json.loads((root/'heldout_anchors.json').read_text())
            train_round(root,'futures','BTCUSDT',128,snapshot=snapshot(count=301))
            self.assertEqual(anchor,json.loads((root/'heldout_anchors.json').read_text()))
            self.assertEqual(Registry(root).all()['active'],[])

if __name__=='__main__':unittest.main()

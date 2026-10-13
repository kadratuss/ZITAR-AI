import unittest
from unittest.mock import patch
from test_zitar_next import snapshot
from zitar_next.combination import blend,choose,rule_map,WEIGHTS


class CombinationTests(unittest.TestCase):
    def test_disagreement_and_direction(self):
        self.assertEqual(blend(1,2,'futures',.5),0)
        self.assertEqual(blend(1,2,'futures',.75),2)
        self.assertEqual(blend(2,1,'futures',.75),1)
        self.assertEqual(blend(1,0,'spot',.75),0)
        with self.assertRaises(ValueError):
            blend(2,1,'spot',.5)
        with self.assertRaises(ValueError):
            blend(True,1,'spot',.5)

    def test_selection_uses_validation_risk(self):
        metrics={.25:dict(return_pct=8,max_drawdown_pct=20),.5:dict(return_pct=3,max_drawdown_pct=1),.75:dict(return_pct=2,max_drawdown_pct=1)}
        self.assertEqual(choose(metrics),.5)
        with self.assertRaises(ValueError):
            choose({.25:metrics[.25]})

    def test_prefix_invariance_no_network(self):
        s=snapshot('futures',150)
        with patch('socket.socket.connect',side_effect=AssertionError('network forbidden')):
            prefix=rule_map(dict(s,records=s['records'][:100]),'futures')
            full=rule_map(s,'futures')
        self.assertEqual(prefix,{k:full[k] for k in prefix})
        self.assertEqual(set(full.values())-{0,1,2},set())
        self.assertEqual(set(rule_map(s,'spot').values())-{0,1},set())


if __name__=='__main__':
    unittest.main()


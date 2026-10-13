import copy
import unittest
from unittest.mock import patch
from test_zitar_next import snapshot
from zitar_next.finrl_pipeline import backtest
from zitar_next.vendor.finrl_backtest_engine import fetch_price_data


class FinrlPipelineTests(unittest.TestCase):
    def run_case(self,market,action):
        rows=snapshot(market,12)['records']
        for i,row in enumerate(rows):
            row.update(open=100+i,close=100+i+.5)
        decisions=[dict(signal_date=a['date'],execution_date=b['date'],action=action) for a,b in zip(rows,rows[1:])]
        with patch('socket.socket.connect',side_effect=AssertionError('network forbidden')):
            result=backtest(market,rows,decisions,dict(return_pct=123.,trades=10))
        return rows,decisions,result

    def test_spot_long_and_cash(self):
        _,_,long=self.run_case('spot',1)
        _,_,cash=self.run_case('spot',0)
        self.assertGreater(long['weight_backtest']['return_pct'],0)
        self.assertAlmostEqual(cash['weight_backtest']['return_pct'],0)
        self.assertEqual(long['authoritative_net_metrics']['return_pct'],123.)
        self.assertFalse(long['real_orders'])

    def test_futures_signed_partial_exposure(self):
        _,_,long=self.run_case('futures',1)
        _,_,short=self.run_case('futures',2)
        self.assertGreater(long['weight_backtest']['return_pct'],0)
        self.assertLess(short['weight_backtest']['return_pct'],0)
        self.assertEqual({v['weight'] for v in long['weights']},{.3})
        self.assertEqual({v['weight'] for v in short['weights']},{-.3})
        self.assertLess(long['weight_backtest']['return_pct'],5)

    def test_causality_and_inputs(self):
        rows,decisions,_=self.run_case('spot',1)
        bad=copy.deepcopy(decisions);bad[0]['execution_date']=bad[0]['signal_date']
        with self.assertRaisesRegex(ValueError,'causal'):
            backtest('spot',rows,bad,{})
        bad=copy.deepcopy(decisions);bad[0]['action']=2
        with self.assertRaises(ValueError):
            backtest('spot',rows,bad,{})
        rows[2]['date']=rows[1]['date']
        with self.assertRaises(ValueError):
            backtest('spot',rows,decisions,{})

    def test_upstream_external_fetch_disabled(self):
        with self.assertRaisesRegex(RuntimeError,'disabled'):
            fetch_price_data(['SPY'],'2020-01-01','2021-01-01')


if __name__=='__main__':
    unittest.main()


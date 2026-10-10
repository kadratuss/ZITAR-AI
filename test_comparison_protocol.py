import unittest
from zitar_next.comparison_protocol import comparison,PROTOCOL


class ComparisonProtocolTests(unittest.TestCase):
    def body(self):
        metric=lambda r:dict(return_pct=r,max_drawdown_pct=2,trades=22)
        return dict(run='example',market='spot',symbol='BTCUSDT',interval='1h',eligible=False,
            issues=['TEST_PERIOD_OVERLAPS_PREVIOUS_ROUND'],
            split=dict(partitions=dict(test=dict(retained_rows=590))),
            baselines={arm:metric(0) for arm in ('cash','long','sma')},
            combination=dict(rule_name='RSI14',selected_ai_weight=.25,
                test=dict(zitar_hourly=metric(-2),learned_ppo=metric(-1),combined=metric(1)),
                stress=dict(combined=metric(-1))))

    def test_improvement_is_not_eligibility_or_freshness(self):
        result=comparison(self.body())
        self.assertEqual(result['delta_vs_rsi_percentage_points']['combined'],3)
        self.assertFalse(result['eligible']);self.assertFalse(result['fresh_validation'])

    def test_missing_reference_rejected(self):
        body=self.body();del body['baselines']['cash']
        with self.assertRaises(ValueError):comparison(body)

    def test_protocol_preserves_risk_and_approval(self):
        self.assertEqual(PROTOCOL['futures']['leverage'],3)
        self.assertEqual(PROTOCOL['minimum_trades'],20)
        self.assertFalse(PROTOCOL['real_orders'])


if __name__=='__main__':unittest.main()

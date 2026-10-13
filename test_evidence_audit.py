import unittest
from zitar_next.evidence_audit import audit


class EvidenceAuditTests(unittest.TestCase):
    def candidate(self, eligible=False, issues=None, returns=(1., -1.), trades=(12, 38)):
        return dict(id='example', state='PENDING', body=dict(eligible=eligible,
            issues=issues or [], seed_results=[dict(seed=i,test=dict(return_pct=r,trades=t))
                for i,r,t in zip((42,73),returns,trades)]))

    def test_contradictory_eligibility_is_not_green(self):
        report=audit(dict(proposals=[self.candidate(True,['INSUFFICIENT_TRADES'])]))
        self.assertEqual(report['eligible_count'],0)

    def test_zero_trades_are_not_positive_evidence(self):
        report=audit(dict(proposals=[self.candidate(returns=(0.,0.),trades=(0,0))]))
        self.assertEqual(report['zero_trade_count'],1)
        self.assertEqual(report['eligible_count'],0)

    def test_seed_disagreement_and_reused_test(self):
        report=audit(dict(proposals=[self.candidate(issues=['TEST_PERIOD_OVERLAPS_PREVIOUS_ROUND'])]))
        self.assertEqual(report['mixed_seed_return_count'],1)
        self.assertEqual(report['reused_test_count'],1)

    def test_combined_metrics_take_precedence(self):
        candidate=self.candidate()
        candidate['body']['combination']=dict(seed_results=[dict(seed=42,test=dict(return_pct=0.,trades=0))])
        self.assertEqual(audit(dict(proposals=[candidate]))['zero_trade_count'],1)

    def test_no_secret_token_in_report(self):
        report=audit(dict(csrf='secret', proposals=[self.candidate(True)], active=[]))
        self.assertNotIn('csrf',report)
        self.assertEqual(report['eligible_count'],1)
        self.assertFalse(report['automatic_activation'])


if __name__=='__main__':
    unittest.main()

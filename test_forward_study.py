import unittest
from zitar_next.forward_study import select_fresh,featured_history,verify_code_lock
import tempfile
from pathlib import Path
from datetime import datetime,timezone
from zitar_next.decision_diagnostics import diagnose


class ForwardStudyTests(unittest.TestCase):
    def test_future_filter_excludes_prior_and_end(self):
        rows=[dict(date=f'2026-10-10 {h}:00:00') for h in ('18','19','20')]
        self.assertEqual(select_fresh(rows,'2026-10-10 19:00:00','2026-10-10 20:00:00'),[rows[1]])

    def test_gaps_rejected(self):
        with self.assertRaises(ValueError):select_fresh([dict(date='2026-10-10 19:00:00'),dict(date='2026-10-10 21:00:00')],'2026-10-10 19:00:00','2026-10-11 00:00:00')

    def test_disagreement_separate_from_cash(self):
        trace=lambda a:[dict(signal_date=str(i),action=v) for i,v in enumerate(a)]
        report=dict(run='example',market='spot',seed_results=[dict(seed=42,test=dict(decisions=trace([0,1]))),dict(seed=73,test=dict(decisions=trace([0,0])))],combination=dict(test=dict(zitar_hourly=dict(decisions=trace([1,1])),combined=dict(decisions=trace([0,0])))))
        result=diagnose(report)
        self.assertEqual(result['disagreement_bars'],1)
        self.assertEqual(result['unanimous_cash_bars'],1)
        self.assertEqual(result['rsi_exposure_to_combined_cash_bars'],2)

    def test_sma_baseline_receives_causal_history(self):
        start=1700000000000//3600000*3600000
        rows=[dict(date=datetime.fromtimestamp((start+i*3600000)/1000,timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
            tic='BTCUSDT',open=100.+i,high=101.+i,low=99.+i,close=100.+i,volume=1.,day=0) for i in range(100)]
        featured=featured_history(rows,start+100*3600000)
        self.assertEqual(featured[60]['sma50'],sum(r['close'] for r in rows[11:61])/50)
        self.assertTrue(featured[60]['features_ready'])
        changed=[dict(r) for r in rows];changed[-1]['close']+=.1
        self.assertEqual(featured_history(changed,start+100*3600000)[60],featured[60])

    def test_code_change_invalidates_fixed_study(self):
        with tempfile.TemporaryDirectory() as temporary:
            verify_code_lock(temporary,{'version':'one'})
            verify_code_lock(temporary,{'version':'one'})
            with self.assertRaisesRegex(ValueError,'changed'):
                verify_code_lock(temporary,{'version':'two'})


if __name__=='__main__':unittest.main()

import unittest
from zitar_next.operations_watch import progress


class OperationsTests(unittest.TestCase):
    def test_24h_requires_observed_span_not_just_service_start(self):
        state=progress(None,100,'boot',[])
        self.assertEqual(state['status'],'OBSERVING_24H')
        for minute in range(15,24*60+1,15): state=progress(state,100+minute*60,'boot',[])
        self.assertEqual(state['status'],'24H_SAMPLED_CHECKS_PASSED')

    def test_gap_or_reboot_restarts_observation(self):
        first=progress(None,100,'boot',[])
        self.assertEqual(progress(first,2000,'boot',[])['observed_hours'],0)
        self.assertEqual(progress(first,1000,'other',[])['observed_hours'],0)

    def test_unexpected_failure_restarts_but_backup_does_not(self):
        first=progress(None,100,'boot',[])
        bad=progress(first,1000,'boot',['production inactive'])
        self.assertIsNone(bad['stable_since'])
        self.assertEqual(progress(bad,1900,'boot',[])['observed_hours'],0)
        planned=progress(first,1000,'boot',['production inactive'],True)
        self.assertEqual(planned['stable_since'],100)
        self.assertEqual(planned['status'],'PLANNED_BACKUP')


if __name__=='__main__': unittest.main()

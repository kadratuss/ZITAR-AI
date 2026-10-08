import tempfile
import unittest
from zitar_research_council_v1 import evidence_summary, dashboard, database, enqueue, dump

class EvidenceDisplayTests(unittest.TestCase):
    def test_missing_is_not_success(self):
        self.assertFalse(evidence_summary(None)['available'])
        self.assertFalse(evidence_summary('{}')['available'])

    def test_challenges_and_reader_errors(self):
        result={'agent_outputs':{'reader':{'pages':[{'url':'https://example.org','status':'ERROR','error':'timeout'}]},'evidence_auditor':{'cited':[{'id':'c0','evidence':[]}],'rejected':[{}]},'skeptic':{'summary':'Alıntı iddiayı desteklemiyor.','challenged_claim_ids':['c0']}},'proposals':[]}
        summary=evidence_summary(result)
        self.assertEqual(summary['unchallenged'],0)
        self.assertEqual(summary['challenged'],1)
        self.assertEqual(summary['sources'][0]['error'],'timeout')
        self.assertFalse(summary['verified'])

    def test_history_scoped_and_no_raw_results(self):
        with tempfile.TemporaryDirectory() as base:
            job=enqueue(base,'Test araştırma konusu','mine')
            enqueue(base,'Gizli başka araştırma','other')
            with database(base) as db:
                db.execute('INSERT INTO attempt_history VALUES (?,?,?,?,?,?)',(job,1,1,'ilk sorgu',dump({}),'2026-09-26'))
            jobs=dashboard(base,'mine')['jobs']
            self.assertEqual(len(jobs),1)
            self.assertEqual(jobs[0]['attempts'][0]['query'],'ilk sorgu')
            self.assertNotIn('result',jobs[0])

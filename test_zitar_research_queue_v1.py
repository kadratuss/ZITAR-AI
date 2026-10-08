import tempfile
import unittest
from pathlib import Path
from zitar_research_council_v1 import replenish_research,database,enqueue,work_once,dashboard,retry_query

class ResearchQueueTests(unittest.TestCase):
    def test_backlog_dedup_and_visibility(self):
        with tempfile.TemporaryDirectory() as base:
            Path(base,'zitar_cost_liquidity_study_v1.json').write_text('{}')
            self.assertEqual(replenish_research(base),5)
            self.assertEqual(replenish_research(base),0)
            self.assertEqual(len(dashboard(base,'user')['jobs']),5)
            with database(base) as db:db.execute("UPDATE jobs SET state='WAITING_24H'")
            self.assertEqual(replenish_research(base),0)

    def test_user_priority_and_waiting_does_not_block(self):
        with tempfile.TemporaryDirectory() as base:
            Path(base,'zitar_cost_liquidity_study_v1.json').write_text('{}')
            replenish_research(base)
            user=enqueue(base,'Kullanıcı araştırması','user')
            called=[]
            def finish(base,job,question,**kw):
                called.append(job)
                with database(base) as db:db.execute("UPDATE jobs SET state='COMPLETED_WITH_LIMITATIONS',result='{}' WHERE id=?",(job,))
            work_once(base,finish)
            self.assertEqual(called,[user])
            with database(base) as db:db.execute("UPDATE jobs SET state='WAITING_24H' WHERE id=(SELECT id FROM jobs WHERE state='QUEUED' LIMIT 1)")
            self.assertTrue(work_once(base,finish))
            self.assertEqual(len(called),2)

    def test_queries_drop_internal_name(self):
        q='ZİTAR strateji maliyeti: komisyon tarifesi ile paper ücret varsayımını karşılaştır'
        self.assertNotIn('ZİTAR',retry_query(q,1))
        self.assertNotEqual(retry_query(q,1),retry_query(q,2))

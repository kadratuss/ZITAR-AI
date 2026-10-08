import tempfile
import unittest
from zitar_research_council_v1 import enqueue,work_once,database,get_job

class RetryTests(unittest.TestCase):
    def test_three_attempts_then_day_and_other_jobs(self):
        def fail(base,job,question,**kwargs):
            with database(base) as db:db.execute("UPDATE jobs SET state='INSUFFICIENT_EVIDENCE',result='{}' WHERE id=?",(job,))
        with tempfile.TemporaryDirectory() as base:
            job=enqueue(base,'XRP kaynak araştırması','s')
            for t in [100,104,108]:self.assertTrue(work_once(base,fail,lambda:t))
            result=get_job(base,job,'s')
            self.assertEqual(result['state'],'WAITING_24H')
            self.assertEqual(result['retry']['attempt'],3)
            self.assertEqual(result['retry']['next_at'],86508)
            self.assertFalse(work_once(base,fail,lambda:109))
            with database(base) as db:
                queries=[r['query'] for r in db.execute('SELECT query FROM attempt_history')]
            self.assertEqual(len(set(queries)),3)
            other=enqueue(base,'Başka konu araştırması','b')
            self.assertTrue(work_once(base,fail,lambda:110))
            self.assertEqual(get_job(base,other,'b')['retry']['attempt'],1)
            self.assertTrue(work_once(base,fail,lambda:86508))
            self.assertEqual(get_job(base,job,'s')['retry']['cycle'],2)
            self.assertEqual(get_job(base,job,'s')['retry']['attempt'],1)

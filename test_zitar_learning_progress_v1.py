import tempfile,unittest,json
from unittest.mock import patch
from zitar_research_council_v1 import database,enqueue,work_once
from zitar_learning_progress_v1 import overview,record_progress
class Tests(unittest.TestCase):
 def test_service_error_does_not_consume_evidence_attempt(self):
  with tempfile.TemporaryDirectory() as d:
   job=enqueue(d,'araştırma konusu','user')
   def fail(base,j,q,**kw):
    with database(base) as db:db.execute("UPDATE jobs SET state='INSUFFICIENT_EVIDENCE',result=? WHERE id=?",(json.dumps({'agent_outputs':{'extractor':{'error':'offline'}}}),j))
   work_once(d,fail,clock=lambda:1000)
   with database(d) as db:
    self.assertEqual(db.execute('SELECT state FROM jobs').fetchone()[0],'SERVICE_WAIT');r=db.execute('SELECT attempt,next_at FROM retry_schedule').fetchone();self.assertEqual(tuple(r),(0,1060));self.assertEqual(db.execute('SELECT count(*) FROM service_incidents').fetchone()[0],1)
 def test_actual_evidence_still_three_attempts(self):
  with tempfile.TemporaryDirectory() as d:
   enqueue(d,'araştırma konusu','user')
   def empty(base,j,q,**kw):
    with database(base) as db:db.execute("UPDATE jobs SET state='INSUFFICIENT_EVIDENCE',result='{}' WHERE id=?",(j,))
   for t in [1000,1004,1008]:work_once(d,empty,clock=lambda:t)
   with database(d) as db:self.assertEqual(db.execute('SELECT state FROM jobs').fetchone()[0],'WAITING_24H')
 def test_no_model_no_work(self):
  with tempfile.TemporaryDirectory() as d:
   enqueue(d,'araştırma konusu','user')
   with patch('zitar_research_readiness_v1.ready',return_value=False),patch('zitar_research_council_v1.execute') as execute:
    self.assertFalse(work_once(d));execute.assert_not_called()
 def test_levels_not_inflated(self):
  with tempfile.TemporaryDirectory() as d:
   j=enqueue(d,'araştırma konusu','user');self.assertEqual(overview(d)['jobs'][0]['level'],0)
   with database(d) as db:
    db.execute('INSERT INTO observations VALUES (?,?,?,?,?,?)',('o',j,'text','[]','CITED_NOT_VERIFIED','now'))
    db.execute('INSERT INTO proposals VALUES (?,?,?,?,?)',('p',j,'{}','PROPOSED_NOT_TESTED','now'))
   self.assertEqual(overview(d)['jobs'][0]['level'],2);self.assertEqual(overview(d)['measured_improvements'],0);record_progress(d);record_progress(d)
   from pathlib import Path
   self.assertEqual(len(json.loads(Path(d,'zitar_learning_progress_v1.json').read_text())['events']),1)
if __name__=='__main__':unittest.main()

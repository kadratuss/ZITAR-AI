import tempfile,unittest,sqlite3
from contextlib import closing
from pathlib import Path
from zitar_next.equity_samples import record
class EquityTests(unittest.TestCase):
 def test_dedup_and_next_minute(self):
  with tempfile.TemporaryDirectory(dir='research_artifacts') as p:
   s=dict(heartbeat_ms=120001,books={'A':dict(equity='10000',started_ms=1,health='OK'),'OLD':dict(equity='9000',started_ms=1,retired_ms=1)})
   record(p,s);s['books']['A']['equity']='10010';record(p,s);s['heartbeat_ms']=180001;record(p,s)
   with closing(sqlite3.connect(Path(p)/'zitar_equity_samples_v1.sqlite3')) as d:r=d.execute('select equity from samples order by minute').fetchall()
   self.assertEqual(r,[('10000',),('10010',)])
if __name__=='__main__':unittest.main()

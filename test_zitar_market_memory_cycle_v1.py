import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from zitar_market_memory_cycle_v1 import refresh,metadata
class MarketMemoryCycleTests(unittest.TestCase):
 def test_order_and_interval(self):
  with tempfile.TemporaryDirectory() as d:
   calls=[]
   def run(args,**kw):calls.append(Path(args[-1]).name);return SimpleNamespace(returncode=0)
   self.assertEqual(refresh(d,runner=run,clock=lambda:100)['state'],'UPDATED')
   self.assertEqual(calls,['zitar_mtf_research_v2.py','zitar_research_memory_v1.py'])
   refresh(d,runner=run,clock=lambda:101)
   self.assertEqual(len(calls),2)
 def test_failure_does_not_publish_memory(self):
  with tempfile.TemporaryDirectory() as d:
   calls=[]
   def run(args,**kw):calls.append(args);return SimpleNamespace(returncode=1,stderr='source unavailable')
   self.assertEqual(refresh(d,runner=run,clock=lambda:100)['state'],'ERROR')
   self.assertEqual(len(calls),1)
   self.assertIsNone(metadata(d)['last_success_utc'])

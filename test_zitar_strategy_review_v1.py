import unittest
from zitar_candidate_recovery_v1 import signal
from zitar_futures_paper_engine_v1 import open_position
class ReviewTests(unittest.TestCase):
 def test_block_precedes_order(self):
  self.assertEqual(open_position({'entries_disabled':True},'BTC',1,{}, {},0,''),'ENTRIES_DISABLED_BY_REVIEW')
 def test_candidate(self):
  self.assertEqual(signal(39,45,110,105,100,1.5,5),1)
  self.assertEqual(signal(61,55,90,95,100,1.5,5),-1)
  self.assertEqual(signal(39,45,110,105,100,1.5,30),0)
  self.assertEqual(signal(45,46,110,105,100,1.5,5),0)
if __name__=='__main__':unittest.main()

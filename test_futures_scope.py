import importlib.util
import unittest
from pathlib import Path
from zitar_next.futures_scope import public

class ScopeTests(unittest.TestCase):
 def test_public_drops_spot_proposals_and_keeps_futures(self):
  value={'proposals':[{'body':{'market':'spot'}},{'body':{'market':'futures'},'id':'keep'}], 'markets':{'spot':{},'futures':{'state':'RUNNING'}}}
  self.assertEqual(public(value),{'proposals':[{'body':{'market':'futures'},'id':'keep'}],'markets':{'futures':{'state':'RUNNING'}}})
 def test_spot_never_reaches_execution(self):
  spec=importlib.util.spec_from_file_location('scope_lab',Path(__file__).with_name('zitar_indicator_lab_v1.py'))
  lab=importlib.util.module_from_spec(spec);spec.loader.exec_module(lab);lab.FUTURES_ONLY=True
  b={'market':'spot','cash':'10000','positions':{}}
  lab.apply_book(b,{'bad':'must not be accessed'},{},0)
  self.assertEqual(b['positions'],{});self.assertTrue(b['entries_paused']);self.assertEqual(b['health'],'DISABLED_BY_USER')
 def test_futures_public_metrics_are_unchanged(self):
  b={'market':'futures','equity':'9510','positions':{'BTCUSDT':{'entry':'100'}}}
  self.assertEqual(public(b),b)

if __name__=='__main__':unittest.main()

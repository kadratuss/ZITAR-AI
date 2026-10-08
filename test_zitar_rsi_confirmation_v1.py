import json,tempfile,unittest
from pathlib import Path
from zitar_indicator_lab_v1 import initial,Lab,cooling_down,apply_book
from test_zitar_indicator_lab_v1 import T,market
class Tests(unittest.TestCase):
 def test_existing_history_survives_migration(self):
  with tempfile.TemporaryDirectory() as td:
   base=Path(td);s=initial(T)
   for k in list(s['books']):
    if k.startswith(('RSI_BASE_','RSI_CONFIRM_')):del s['books'][k];del s['specs'][k]
   s['books']['SCALP20']['cash']='9754'
   (base/'zitar_indicator_lab_v1.json').write_text(json.dumps(s))
   # specs is shared constant; restore from a clean module load for the migration test.
   import importlib,zitar_indicator_lab_v1 as mod
   importlib.reload(mod)
   lab=mod.Lab(base)
   self.assertEqual(lab.state['books']['SCALP20']['cash'],'9754')
   self.assertEqual(lab.state['books']['RSI_CONFIRM_SPOT']['cash'],'10000')
   self.assertTrue(list((base/'paper_strategy_archives').glob('*.json')));lab.pool.shutdown()
 def test_cooldown_symbol_and_expiry(self):
  b={'interval':'1h','closed':[{'symbol':'A','closed_ms':3600001,'exit_reason':'TRAILING_STOP'}]}
  self.assertTrue(cooling_down(b,'A',14400000));self.assertFalse(cooling_down(b,'A',18000000));self.assertFalse(cooling_down(b,'B',7200000))
 def test_confirmed_entry_neutral_hold_and_midpoint_exit(self):
  b=initial(T)['books']['RSI_CONFIRM_FUTURES']
  def a(ms,target,rsi):return {'TEST':{'candle_ms':ms-1,'RSI_CONFIRM':target,'rsi':rsi}}
  apply_book(b,market(T+1000),a(T+1000,1,31),T+1000);self.assertTrue(b['positions'])
  apply_book(b,market(T+3601000),a(T+3601000,0,40),T+3601000);self.assertTrue(b['positions'])
  apply_book(b,market(T+7201000),a(T+7201000,0,51),T+7201000);self.assertFalse(b['positions'])

import json,tempfile,unittest
from pathlib import Path
from zitar_market_controls_v1 import update,read
from zitar_strategy_selection_v1 import configure
from zitar_futures_paper_engine_v1 import fresh,open_position,apply_cycle

class RsiOnlyTests(unittest.TestCase):
 def test_independent_controls_and_pump_disabled(self):
  with tempfile.TemporaryDirectory() as td:
   update(td,'spot','stop');self.assertTrue(read(td,'spot')['paused']);self.assertFalse(read(td,'futures')['paused'])
   update(td,'futures','stop');update(td,'spot','start');self.assertTrue(read(td,'futures')['paused']);self.assertFalse(read(td,'spot')['paused'])
   with self.assertRaises(ValueError):update(td,'pump','start')
 def test_paused_entry_does_not_disable_stop(self):
  t=1790863200000;s=fresh(t,[]);b=s['books']['RSI14'];q=dict(bid='100',ask='100',mark='100',time=t,book_time=t,next_funding=t+3600000,funding_rate='0');c=dict(step='.001',min_qty='.001',max_qty='10000',min_notional='1')
  open_position(b,'TEST',1,q,c,t,'test');b['entries_paused']=True
  self.assertEqual(open_position(b,'OTHER',1,q,c,t,'test'),'ENTRIES_PAUSED')
  q.update(bid='95',ask='95',mark='95',time=t+1000,book_time=t+1000)
  apply_cycle(s,{'TEST':dict(quote=q,contract=c,candles=[],funding=[])},t+1000)
  self.assertFalse(b['positions']);self.assertEqual(b['closed'][0]['exit_reason'],'TRAILING_STOP_2PCT')
 def test_roster_archives_without_resetting_rsi(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td);(p/'zitar_strategy_selection_v1.json').write_text(json.dumps({'version':'SELECTED_PAPER_V1','futures':['RSI14']}));s=fresh(1,[]);s['books']['RSI14']['cash']='10500'
   configure(p,s,'futures',2);self.assertEqual(s['active_strategy_names'],['RSI14']);self.assertEqual(s['books']['RSI14']['cash'],'10500');self.assertEqual(s['books']['SMA20_50']['retired_ms'],2);self.assertTrue(Path(s['roster_archive']).exists())

if __name__=='__main__':unittest.main()

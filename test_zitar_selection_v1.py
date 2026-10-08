import json,tempfile,unittest
from pathlib import Path
from zitar_strategy_selection_v1 import configure,KEEP_FUTURES
from zitar_futures_paper_engine_v1 import fresh,open_position,apply_cycle
from zitar_discovery_spot_v1 import fresh as spot_fresh,apply as spot_apply
from test_zitar_confluence_v1 import T,Q,C

class SelectionTests(unittest.TestCase):
 def configured(self,state,market):
  folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup);p=Path(folder.name)
  (p/'zitar_strategy_selection_v1.json').write_text(json.dumps({'version':'SELECTED_PAPER_V1'}))
  configure(p,state,market,T+1)
  return p
 def test_archive_precedes_retirement_and_kept_cash_unchanged(self):
  s=fresh(T,[]);p=self.configured(s,'futures');arch=json.loads(Path(s['selection_archive']).read_text(encoding='utf-8'))
  self.assertNotIn('retired_ms',arch['books']['BASELINE'])
  self.assertEqual(s['books']['RSI14']['cash'],'10000');self.assertNotIn('retired_ms',s['books']['RSI14'])
  configure(p,s,'futures',T+2);self.assertEqual(len(list((p/'paper_strategy_archives').glob('*'))),1)
 def test_futures_close_only_on_fresh_quote_and_no_reopen(self):
  s=fresh(T,[]);b=s['books']['BASELINE'];open_position(b,'TEST',1,Q,C,T,'TEST');self.configured(s,'futures')
  apply_cycle(s,{},T+10);self.assertIn('TEST',b['positions'])
  apply_cycle(s,{'TEST':dict(quote=Q,contract=C,funding=[],candles=[],timeframes={})},T+20)
  self.assertFalse(b['positions']);self.assertEqual(b['closed'][-1]['exit_reason'],'USER_STRATEGY_RETIRED')
  self.assertEqual(open_position(b,'TEST',1,Q,C,T+30,'TEST'),'RETIRED')
  self.assertTrue(all(b.get('retired_ms') for n,b in s['books'].items() if n not in KEEP_FUTURES))
 def test_spot_rsi_uses_hourly_and_retired_books_cannot_enter(self):
  s=spot_fresh(T);self.configured(s,'spot')
  q=dict(ms=T+2,bid='100',ask='100',step='0.001',min_qty='0.001',max_qty='10000',min_notional='5',depth={'bids':[['100','10000']],'asks':[['100','10000']]},rsi_analysis={'candle_close_ms':T+2,'RSI14':1})
  spot_apply(s,{'TEST':q},{'main':['TEST'],'updated_ms':T+2},T+3)
  self.assertIn('TEST',s['books']['RSI14']['positions']);self.assertEqual(s['books']['RSI14']['positions']['TEST']['timeframe'],'1h')
  self.assertFalse(s['books']['SINGLE']['positions'])
  q['rsi_analysis']={'candle_close_ms':T+4,'RSI14':0};q['ms']=T+4
  spot_apply(s,{'TEST':q},{'main':['TEST'],'updated_ms':T+4},T+5)
  self.assertFalse(s['books']['RSI14']['positions'])

if __name__=='__main__':unittest.main()

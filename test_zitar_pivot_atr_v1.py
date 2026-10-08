import math,unittest
from copy import deepcopy
from zitar_pivot_atr_v1 import signal,confirmed_pivot,ensure,NAMES
from zitar_futures_paper_engine_v1 import fresh,apply_cycle,open_position,number
from test_zitar_confluence_v1 import T,Q,C

def bars(count=500):
 return [[T+i*300000,c,c+.1,c-.1,c,100,T+(i+1)*300000-1] for i in range(count) for c in [100+2*math.sin(i*.12)]]

class PivotTests(unittest.TestCase):
 def test_pivot_only_confirmed_after_two_right_bars(self):
  high=[1,2,5,3,2];low=[.1,.2,.3,.2,.1]
  self.assertIsNone(confirmed_pivot(high,low,3))
  self.assertEqual(confirmed_pivot(high,low,4),5)
 def test_long_short_and_no_future_leak(self):
  rows=bars();directions=set()
  for n in range(400,501):
   ms=T+n*300000
   a=signal(rows[:n],ms,300000);directions.add(a['direction'])
   self.assertEqual(a,signal(rows,ms,300000))
   if a['pivot_confirmation_ms']:self.assertLess(a['pivot_confirmation_ms'],ms)
  self.assertTrue({-1,1}.issubset(directions))
 def test_gap_stale_invalid_rejected(self):
  rows=bars();ms=T+500*300000
  with self.assertRaisesRegex(ValueError,'CANDLE_GAP'):signal(rows[:200]+rows[201:],ms,300000)
  with self.assertRaisesRegex(ValueError,'STALE'):signal(rows,ms+600000,300000)
  rows[-1][4]=float('nan')
  with self.assertRaisesRegex(ValueError,'INVALID'):signal(rows,ms,300000)
 def test_existing_books_unchanged_and_restart_idempotent(self):
  s=fresh(T,[]);old=deepcopy(s['books']);ensure(s,T)
  for n,b in old.items():self.assertEqual(b,s['books'][n])
  snapshot=deepcopy(s);ensure(s,T+100);self.assertEqual(s,snapshot)
 def test_uses_shared_risk_when_candles_missing(self):
  s=fresh(T,[]);ensure(s,T);b=s['books']['ZITAR_PIVOT_ATR_5M']
  open_position(b,'TEST',1,Q,C,T,'TEST');p=b['positions']['TEST'];p.update(quantity_step='0.001',trailing_stop=str(number(p['entry'])*number('.99')))
  q=dict(Q,bid='98',ask='98',mark='98')
  apply_cycle(s,{'TEST':dict(quote=q,contract=C,funding=[],candles=[],timeframes={})},T+1)
  self.assertFalse(b['positions']);self.assertEqual(b['closed'][0]['exit_reason'],'CONFLUENCE_STOP')

if __name__=='__main__':unittest.main()

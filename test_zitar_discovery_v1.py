import unittest
from copy import deepcopy
from zitar_indicator_panel_v1 import analyze
from zitar_market_discovery_v1 import liquidity,get
from zitar_discovery_spot_v1 import fresh,apply

class DiscoveryTests(unittest.TestCase):
 def test_dynamic_futures_entry_and_exit_after_deselection(self):
  from unittest.mock import patch
  from zitar_futures_paper_engine_v1 import fresh as future_state
  from zitar_discovery_futures_v1 import ensure,evaluate,NAMES
  t=1790456400000;s=future_state(t,[]);ensure(s,t);ms=t+300000
  s['discovery_selection']=dict(updated_ms=ms,main=['NEW'],radar=['NEW'])
  q=dict(bid='100',ask='100.01',mark='100',time=ms,book_time=ms,next_funding=ms+999999,funding_rate='0')
  data=dict(timeframes={'5m':[]},depth={'bids':[['100','1000']],'asks':[['100.01','1000']]},contract=dict(step='.001',min_qty='.001',max_qty='10000',min_notional='5'))
  a=dict(candle_close_ms=ms-1,single=1,majority=1,grouped=1,radar=True,radar_direction=1)
  with patch('zitar_discovery_futures_v1.analyze',return_value=a):evaluate(s,{'NEW':data},{'NEW':q},ms,set(),[])
  self.assertTrue(all('NEW' in s['books'][n]['positions'] for n in NAMES))
  s['discovery_selection']=dict(updated_ms=ms,main=[],radar=[])
  a.update(candle_close_ms=ms+299999,single=0,majority=0,grouped=0,radar=False)
  with patch('zitar_discovery_futures_v1.analyze',return_value=a):evaluate(s,{'NEW':data},{'NEW':q},ms+300000,set(),[])
  self.assertTrue(all(not s['books'][n]['positions'] for n in NAMES))
 def rows(self):
  return [[i*300000,100+i,102+i,99+i,101+i,1000, (i+1)*300000-1] for i in range(201)]
 def test_closed_only_and_ten_formulas(self):
  rows=self.rows();ms=200*300000
  a=analyze(rows,ms);self.assertEqual(len(a['indicators']),10)
  rows[-1][4]=999999
  self.assertEqual(a,analyze(rows,ms))
  self.assertGreater(a['single'],0);self.assertEqual(a['candle_close_ms'],ms-1)
 def test_gap_rejected(self):
  rows=self.rows();rows.pop(100)
  with self.assertRaisesRegex(ValueError,'GAP'):analyze(rows,200*300000)
 def test_liquidity_not_volume_alone(self):
  self.assertFalse(liquidity({'bids':[['99','1000']],'asks':[['101','1000']]},1000)['eligible'])
  self.assertFalse(liquidity({'bids':[['100','1']],'asks':[['100.01','1']]},1000)['eligible'])
  self.assertTrue(liquidity({'bids':[['100','1000']],'asks':[['100.01','1000']]},1000)['eligible'])
 def test_no_order_endpoint(self):
  with self.assertRaises(ValueError):get('spot','order')
 def test_spot_entry_dedup_removed_symbol_exit_and_cash(self):
  t=1790456400000;s=fresh(t);ms=t+300000
  a=dict(candle_close_ms=ms-1,single=1,majority=1,grouped=1,radar=True,radar_direction=1)
  q=dict(ms=ms,bid=100,ask=100.01,depth={'bids':[['100','1000']],'asks':[['100.01','1000']]},analysis=a,step='.001',min_qty='.001',max_qty='100000',min_notional='5')
  selection=dict(updated_ms=ms,main=['X'],radar=['X'],early_candidates=[dict(symbol='X',stage='CONFIRMED',candle_ms=ms-1,confirmed_ms=ms-1)])
  apply(s,{'X':q},selection,ms);apply(s,{'X':q},selection,ms)
  for b in s['books'].values():self.assertEqual(len(b['positions']),1);self.assertGreaterEqual(float(b['cash']),0)
  q.update(ms=ms+1,bid=90,ask=90.01)
  apply(s,{'X':q},dict(updated_ms=ms,main=[],radar=[]),ms+1)
  for b in s['books'].values():self.assertFalse(b['positions']);self.assertEqual(len(b['closed']),1);self.assertEqual(b['cash'],b['equity'])
 def test_stale_selection_no_new_entry(self):
  t=1790456400000;s=fresh(t);ms=t+300000
  q=dict(ms=ms,bid=100,ask=100,analysis=dict(candle_close_ms=ms-1,single=1,majority=1,grouped=1,radar=True,radar_direction=1))
  apply(s,{'X':q},dict(updated_ms=t,main=['X'],radar=['X']),ms)
  self.assertTrue(all(not b['positions'] for b in s['books'].values()))

if __name__=='__main__':unittest.main()

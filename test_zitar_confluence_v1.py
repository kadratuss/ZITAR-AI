import unittest
from copy import deepcopy
from unittest.mock import patch
from zitar_futures_paper_engine_v1 import fresh, open_position, close_position, mark, number, apply_cycle
from zitar_confluence_v1 import ensure, risk, evaluate, signal, NAMES

T=1800000000000
Q=dict(bid='100',ask='100',mark='100',time=T,book_time=T,next_funding=T+28800000,funding_rate='0')
C=dict(step='0.001',min_qty='0.001',max_qty='1000000',min_notional='5')

class ConfluenceTests(unittest.TestCase):
 def test_real_four_factor_long_short_and_volume_gate(self):
  closes=[98+.001*i for i in range(350)]+[101-(i-350)/30 for i in range(350,380)]+[100+.005*(-1)**i for i in range(20)]+[100.06]
  for side in (1,-1):
   values=closes if side==1 else [200-x for x in closes]
   rows=[[T-(401-i)*300000,c,c+.005,c-.005,c,300 if i==400 else 100,T-(400-i)*300000-1] for i,c in enumerate(values)]
   self.assertEqual(signal(rows,T,300000)['direction'],side)
   rows[-1][5]=100
   self.assertEqual(signal(rows,T,300000)['direction'],0)
 def test_restart_preserves_account_and_version(self):
  s,b,p=self.setup_book();old=deepcopy(s);ensure(s,T+10000);self.assertEqual(s,old)
  b['rules_hash']='bad'
  with self.assertRaisesRegex(ValueError,'RULES_CHANGED'):ensure(s,T+20000)
 def test_24h_snapshot_once_only(self):
  s=fresh(T,[]);ensure(s,T);evaluate(s,{}, {},T+86400001,set(),[])
  b=s['books']['ZITAR_CONFLUENCE_5M'];snap=deepcopy(b['review_24h']);b['equity']='10001'
  evaluate(s,{}, {},T+86400002,set(),[]);self.assertEqual(b['review_24h'],snap)
 def setup_book(self,side=1):
  s=fresh(T,[]);ensure(s,T);b=s['books']['ZITAR_CONFLUENCE_5M']
  self.assertEqual(open_position(b,'TEST',side,Q,C,T,'TEST'),'OPENED')
  p=b['positions']['TEST'];e=number(p['entry']);p.update(quantity_step='0.001',trailing_stop=str(e*(1-number('.01')*side)))
  return s,b,p
 def quote(self,price):return dict(Q,bid=str(price),ask=str(price),mark=str(price))
 def test_partial_and_final_accounting_both_sides(self):
  for side in (1,-1):
   s,b,p=self.setup_book(side);entry=number(p['entry']);original=number(p['quantity']);q=self.quote(entry*(1+number('.02')*side))
   risk(b,'TEST',q,T+1,number(1000),number(10))
   self.assertTrue(b['positions']['TEST']['partial_done']);self.assertEqual(len(b['closed']),1)
   self.assertEqual(number(b['positions']['TEST']['quantity'])+number(b['closed'][0]['quantity']),original)
   close_position(b,'TEST',q,T+2,'TEST_EXIT');mark(b,{})
   self.assertAlmostEqual(float(number(b['equity'])-10000),float(number(b['realized'])),places=8)
   self.assertEqual(number(b['realized']),sum(number(x['net_pnl']) for x in b['closed']))
 def test_break_even_covers_entry_exit_fees_and_slippage(self):
  for side in (1,-1):
   s,b,p=self.setup_book(side);entry=number(p['entry']);q=self.quote(entry*(1+number('.012')*side))
   risk(b,'TEST',q,T+1,number(1000),number(10));stop=number(p['trailing_stop'])
   self.assertTrue(p['break_even_active'])
   risk(b,'TEST',self.quote(stop),T+2,number(1000),number(10))
   self.assertFalse(b['positions']);self.assertAlmostEqual(float(b['realized']),0,places=8)
 def test_daily_loss_closes_and_latches(self):
  s,b,p=self.setup_book();b['equity']='9799';evaluate(s,{}, {'TEST':Q},T+1,set(),[])
  self.assertEqual(b['daily_limit'],'LOSS_STOP');self.assertFalse(b['positions'])
  b['equity']='10000';evaluate(s,{}, {},T+2,set(),[]);self.assertEqual(b['daily_limit'],'LOSS_STOP')
  b['period']='NEXT_DAY';evaluate(s,{}, {},T+3,set(),[]);self.assertEqual(b['daily_limit'],'OPEN')
 def test_daily_profit_blocks_entries_but_keeps_position(self):
  s,b,p=self.setup_book();b['equity']='10301';evaluate(s,{}, {'TEST':Q},T+1,set(),[])
  self.assertEqual(b['daily_limit'],'PROFIT_LOCK');self.assertIn('TEST',b['positions'])
 def test_independent_cost_policy_does_not_change_legacy(self):
  s,b,p=self.setup_book();old=s['books']['BASELINE'];open_position(old,'TEST',1,Q,C,T,'OLD')
  self.assertEqual(p['entry'],'100.100');self.assertEqual(old['positions']['TEST']['entry'],'100.0200')
  self.assertNotEqual(b['fees_total'],old['fees_total'])
 def test_empty_and_stale_and_open_bar(self):
  with self.assertRaisesRegex(ValueError,'WARMUP'):signal([],T,300000)
  rows=[[T-(401-i)*300000,'100','101','99','100','100',T-(400-i)*300000-1] for i in range(401)]
  a=signal(rows,T,300000);self.assertEqual(a['direction'],0)
  forming=[T,'100','10000','1','9999','1000000',T+299999]
  self.assertEqual(signal(rows+[forming],T,300000),a)
  with self.assertRaisesRegex(ValueError,'STALE'):signal(rows,T+600000,300000)
 def test_fresh_signal_entry_deduplicated_and_volume_filtered(self):
  s=fresh(T,[]);ensure(s,T);s['discovery_selection']=dict(updated_ms=T+1,main=['TEST'],rows=[dict(symbol='TEST',volume_24h=20000000)])
  a=dict(direction=1,candle_close_ms=T+1,atr=1)
  market={'TEST':dict(timeframes={},contract=C,depth={})}
  with patch('zitar_confluence_v1.signal',return_value=a),patch('zitar_market_discovery_v1.liquidity',return_value={'eligible':True}):
   evaluate(s,market,{'TEST':Q},T+2,set(),[])
   b=s['books']['ZITAR_CONFLUENCE_5M'];self.assertIn('TEST',b['positions']);self.assertEqual(b['positions']['TEST']['trailing_stop'],'99.09900')
   cash=b['cash'];evaluate(s,market,{'TEST':Q},T+3,set(),[]);self.assertEqual(cash,b['cash'])
  s=fresh(T,[]);ensure(s,T);s['discovery_selection']=dict(updated_ms=T+1,main=['TEST'],rows=[dict(symbol='TEST',volume_24h=1)])
  with patch('zitar_confluence_v1.signal',return_value=a):evaluate(s,market,{'TEST':Q},T+2,set(),[])
  self.assertFalse(s['books']['ZITAR_CONFLUENCE_5M']['positions'])
 def test_stop_without_candles_in_integrated_cycle(self):
  s,b,p=self.setup_book();q=self.quote(98)
  apply_cycle(s,{'TEST':dict(quote=q,contract=C,funding=[],timeframes={},candles=[])},T+1000)
  self.assertFalse(b['positions']);self.assertEqual(b['closed'][0]['exit_reason'],'CONFLUENCE_STOP')

if __name__=='__main__':unittest.main()

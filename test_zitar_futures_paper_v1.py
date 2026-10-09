import unittest,copy
from zitar_futures_paper_engine_v1 import *
class FuturesPaperTests(unittest.TestCase):
 def setUp(self):
  self.t=1790456400000;self.s=fresh(self.t,['BTCUSDT']);self.b=self.s['books']['BASELINE']
  self.q=dict(bid='100',ask='100',mark='100',time=self.t,book_time=self.t,next_funding=self.t+100000,funding_rate='0.0001')
  self.c=dict(step='0.01',min_qty='0.01',max_qty='10000',min_notional='5')
 def test_long_short_accounting_and_cost(self):
  for direction in [1,-1]:
   b=fresh(self.t,[])['books']['BASELINE'];open_position(b,'BTCUSDT',direction,self.q,self.c,self.t,'test')
   close_position(b,'BTCUSDT',self.q,self.t+1,'TEST');mark(b,{})
   self.assertLess(number(b['equity']),10000)
   self.assertAlmostEqual(float(number(b['equity'])-10000),float(number(b['realized'])),places=8)
 def test_funding_direction_and_idempotency(self):
  for direction in [1,-1]:
   b=fresh(self.t,[])['books']['BASELINE'];open_position(b,'BTCUSDT',direction,self.q,self.c,self.t,'test')
   e=[dict(fundingTime=self.t+1,markPrice='100',fundingRate='0.001')]
   settle_funding(b,'BTCUSDT',e,self.t+2);v=b['funding_total'];settle_funding(b,'BTCUSDT',e,self.t+2)
   self.assertEqual(v,b['funding_total']);self.assertEqual(number(v)>0,direction==-1)
 def test_trailing_never_retreats_and_closes(self):
  open_position(self.b,'BTCUSDT',1,self.q,self.c,self.t,'test')
  def tick(price,offset):
   q=dict(self.q,bid=str(price),ask=str(price),mark=str(price),time=self.t+offset,book_time=self.t+offset)
   apply_cycle(self.s,{'BTCUSDT':dict(quote=q,funding=[],candles=[],contract=self.c)},self.t+offset)
  tick(110,1);stop=self.b['positions']['BTCUSDT']['trailing_stop'];tick(109,2)
  self.assertEqual(stop,self.b['positions']['BTCUSDT']['trailing_stop']);tick(107,3)
  self.assertFalse(self.b['positions']);self.assertEqual(self.b['closed'][0]['exit_reason'],'PROFIT_LOCK_5PCT_80PCT')
 def test_stale_price_cannot_close(self):
  open_position(self.b,'BTCUSDT',1,self.q,self.c,self.t,'test')
  apply_cycle(self.s,{'BTCUSDT':dict(quote=dict(self.q,mark='1'),candles=[],funding=[],contract=self.c)},self.t+31000)
  self.assertTrue(self.b['positions']);self.assertEqual(self.s['state'],'DEGRADED')
 def test_liquidation_isolated_loss_cap(self):
  open_position(self.b,'BTCUSDT',1,self.q,self.c,self.t,'test');cash=self.b['cash']
  q=dict(self.q,mark='1',bid='1',ask='1')
  apply_cycle(self.s,{'BTCUSDT':dict(quote=q,candles=[],funding=[],contract=self.c)},self.t)
  self.assertEqual(self.b['cash'],cash);self.assertEqual(self.b['closed'][0]['exit_reason'],'MODEL_LIQUIDATION')
 def test_closed_candles_only_and_gap(self):
  rows=[[self.t-3600000*(61-i),'100','101','99',str(100+i),'1',self.t-3600000*(60-i)-1] for i in range(61)]
  a=signals(rows,self.t);rows.append([self.t,'1','1','1','1','1',self.t+3599999])
  self.assertEqual(a,signals(rows,self.t));rows.pop(5)
  with self.assertRaisesRegex(ValueError,'CANDLE_GAP'):signals(rows,self.t)
 def test_policy_mutation_blocked(self):
  self.s['policy_hash']='wrong'
  with self.assertRaisesRegex(ValueError,'POLICY_CHANGED'):apply_cycle(self.s,{},self.t)
 def test_no_order_api(self):
  from zitar_futures_paper_runtime_v1 import get
  with self.assertRaisesRegex(ValueError,'PUBLIC_DATA_ONLY'):get('order')

 def test_short_trailing_stop(self):
  open_position(self.b,'BTCUSDT',-1,self.q,self.c,self.t,'test')
  for price,offset in [(90,1),(91,2)]:
   q=dict(self.q,mark=str(price),bid=str(price),ask=str(price),time=self.t+offset,book_time=self.t+offset)
   apply_cycle(self.s,{'BTCUSDT':dict(quote=q,candles=[],funding=[],contract=self.c)},self.t+offset)
  self.assertEqual(number(self.b['positions']['BTCUSDT']['trailing_stop']),number('91.8'))
  q=dict(self.q,mark='92',bid='92',ask='92')
  apply_cycle(self.s,{'BTCUSDT':dict(quote=q,candles=[],funding=[],contract=self.c)},self.t+3)
  self.assertFalse(self.b['positions'])
 def test_missing_funding_blocks_valuation(self):
  open_position(self.b,'BTCUSDT',1,self.q,self.c,self.t,'test')
  ms=self.t+100001;q=dict(self.q,time=ms,book_time=ms,next_funding=ms+100000)
  apply_cycle(self.s,{'BTCUSDT':dict(quote=q,candles=[],funding=[],contract=self.c)},ms)
  self.assertTrue(any('FUNDING_PENDING' in x for x in self.s['errors']))
  self.assertEqual(self.b['positions']['BTCUSDT']['funding'],'0')
 def test_daily_rollover_and_restart_idempotent(self):
  ms=self.t+86400000
  apply_cycle(self.s,{},ms);apply_cycle(self.s,{},ms)
  self.assertEqual(len(self.b['daily']),1)
  self.assertEqual(number(self.b['slot']),1000)

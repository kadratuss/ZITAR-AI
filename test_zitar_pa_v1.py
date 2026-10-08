import unittest
from pa_v1.config import Config
from pa_v1.features import candles,structure,patterns,atr,evaluate,trendline
class FeatureTests(unittest.TestCase):
 def setUp(self):self.c=Config();self.t=3600000*1000
 def raw(self,step=300000):return [[self.t-(100-i)*step,100,102,98,101,10,self.t-(99-i)*step-1] for i in range(100)]
 def test_closed_and_gap(self):
  r=self.raw();a=candles(r,self.t,'5m',self.c);r.append([self.t,1,1,1,1,1,self.t+299999]);self.assertEqual(a,candles(r,self.t,'5m',self.c));r.pop(50)
  with self.assertRaisesRegex(ValueError,'CANDLE_GAP'):candles(r,self.t,'5m',self.c)
 def test_invalid(self):
  r=self.raw();r[-1][5]=-1
  with self.assertRaisesRegex(ValueError,'INVALID'):candles(r,self.t,'5m',self.c)
 def test_pattern_context(self):
  e=candles(self.raw(),self.t,'5m',self.c);e[-1].update(o=100,c=101,h=101.1,l=96)
  p={x['pattern_name']:x for x in patterns(e,True,self.c)};self.assertTrue(p['HAMMER']['valid']);self.assertTrue(p['LONG_LOWER_SHADOW']['valid']);self.assertFalse(any(p['valid'] for p in patterns(e,False,self.c)))
 def test_confirmed_swings_only(self):
  e=candles(self.raw(),self.t,'5m',self.c)
  for i,r in enumerate(e):r.update(h=102+i%7,l=98+i%7)
  st=structure(e,self.c)
  self.assertTrue(all(x['confirmed_at']<=e[-1]['end'] for x in st['swings']))
  self.assertTrue(all(x['timestamp']<e[-2]['end'] for x in st['swings']))
 def test_failclosed(self):
  self.assertEqual(evaluate('X',{},self.t,self.c)['decision'],'NO_TRADE')
  self.assertEqual(evaluate('X',{},self.t,Config(mode='LIVE'))['reasons'],['PAPER_MODE_NOT_CONFIRMED'])
from pa_v1.paper import create,tick
from pa_v1.config import Config
from decimal import Decimal as D
class PaperTests(unittest.TestCase):
 def setUp(self):
  self.c=Config();self.t=3600000000;self.s=create(self.t,self.c)
  self.f=dict(strategy_id='ZITAR_PA_V1',decision='PAPER_BUY',reasons=[],signal_id='a',signal_timestamp=self.t,stop_price=98,resistance=110,setup_type='TREND_PULLBACK',PA_SCORE=100,volume_ratio=2,regime='UPTREND',atr=1,support=98)
 def market(self,price=100):return {'X':dict(quote=dict(time=self.t,bid=str(price),ask=str(price),mark=str(price),next_funding=self.t+999999,funding_rate='0'),contract=dict(step='.001',min_qty='.001',max_qty='100000',min_notional='1'))}
 def test_entry_partial_exit_and_identity(self):
  tick(self.s,self.market(),{'X':self.f},self.t,self.c,historical=True)
  for b in self.s['books'].values():self.assertTrue(b['positions']);self.assertLessEqual(float(b['positions']['X']['initial_risk']),25.001)
  tick(self.s,self.market(),{'X':self.f},self.t,self.c,historical=True)
  for b in self.s['books'].values():self.assertEqual(len(b['positions']),1)
  tick(self.s,self.market(103),{},self.t,self.c,historical=True)
  for b in self.s['books'].values():self.assertEqual(len(b['closed']),1);self.assertTrue(b['positions']['X']['tp1'])
  tick(self.s,self.market(97),{},self.t,self.c,historical=True)
  for b in self.s['books'].values():
   self.assertFalse(b['positions']);self.assertAlmostEqual(float(b['cash'])-10000,sum(float(x['net_pnl']) for x in b['closed']),places=7)
 def test_safety_missing_liquidity_and_daily_halt(self):
  tick(self.s,self.market(),{'X':self.f},self.t,self.c)
  self.assertTrue(all(not b['positions'] for b in self.s['books'].values()))
  for b in self.s['books'].values():b['cash']='9890';b['equity']='9890'
  tick(self.s,self.market(),{'X':dict(self.f,signal_id='b')},self.t,self.c,historical=True)
  self.assertTrue(all(b['halted'] and not b['positions'] for b in self.s['books'].values()))
  self.s['mode']='LIVE'
  with self.assertRaisesRegex(ValueError,'PAPER_MODE'):tick(self.s,{}, {},self.t,self.c)
 def test_stale_cannot_fill(self):
  m=self.market();m['X']['quote']['time']-=31000
  tick(self.s,m,{'X':self.f},self.t,self.c,historical=True)
  self.assertFalse(self.s['books']['A_BE']['positions'])
class RegressionTests(PaperTests):
 def test_partial_trade_not_counted_as_completed(self):
  from pa_v1.metrics import summary
  self.f['R']=2
  tick(self.s,self.market(),{'X':self.f},self.t,self.c,historical=True)
  tick(self.s,self.market(103),{},self.t,self.c,historical=True)
  for b in self.s['books'].values():self.assertEqual(summary(b)['total_trades'],0)
  tick(self.s,self.market(97),{},self.t,self.c,historical=True)
  for b in self.s['books'].values():self.assertEqual(summary(b)['total_trades'],1)
 def test_restart_duplicate_and_stop_never_loosen(self):
  import json
  tick(self.s,self.market(),{'X':self.f},self.t,self.c,historical=True);self.s=json.loads(json.dumps(self.s))
  tick(self.s,self.market(103),{},self.t,self.c,historical=True)
  stop=float(self.s['books']['A_BE']['positions']['X']['pa_stop'])
  tick(self.s,self.market(102),{'X':dict(self.f,support=80,signal_timestamp=self.t+1)},self.t,self.c,historical=True)
  self.assertGreaterEqual(float(self.s['books']['A_BE']['positions']['X']['pa_stop']),stop)
  self.assertEqual(len(self.s['books']['A_BE']['positions']),1)
 def test_net_rr_gate_and_cap(self):
  tick(self.s,self.market(),{'X':dict(self.f,resistance=101)},self.t,self.c,historical=True)
  self.assertFalse(self.s['books']['A_BE']['positions'])
  self.assertIn('INSUFFICIENT_RR',self.s['books']['A_BE']['decisions'][-1]['reasons'])
 def test_config_nonfinite(self):
  with self.assertRaises(ValueError):Config(volume_ratio=float('nan')).validate()

class IntegrationTests(unittest.TestCase):
 def test_worker_isolated_no_network_no_other_state_mutation(self):
  import tempfile,json
  from pathlib import Path
  from unittest.mock import patch
  from pa_v1.runtime import Worker,overview
  from contextlib import nullcontext
  import uuid
  folder=Path(__file__).parent/'outputs'/'pa_v1'/('test_'+uuid.uuid4().hex);folder.mkdir(parents=True)
  with nullcontext(folder) as folder:
   base=Path(folder);existing=base/'zitar_master_portfolio_v1.json';existing.write_text('{"sentinel":true}')
   with patch('pa_v1.runtime.get',side_effect=RuntimeError('offline')):
    w=Worker(base)
    try:s=w.cycle()
    finally:w.cache.close()
   self.assertEqual(s['state'],'DEGRADED');self.assertEqual(existing.read_text(),'{"sentinel":true}')
   self.assertTrue(all(not b['positions'] for b in s['books'].values()))
   self.assertFalse(overview(base)['real_orders'])
 def test_pattern_engulfing_piercing_and_stars(self):
  c=Config();rows=[dict(o=10,h=11,l=7,c=8,v=10,t=i,end=i) for i in range(20)]
  rows[-1]=dict(o=7.9,h=11.1,l=7.8,c=10.5,end=20)
  self.assertTrue(next(x for x in patterns(rows,True,c) if x['pattern_name']=='BULLISH_ENGULFING')['valid'])
  rows[-1]['c']=9.5
  self.assertTrue(next(x for x in patterns(rows,True,c) if x['pattern_name']=='PIERCING_LINE')['valid'])
  rows[-3]=dict(o=11,h=11.1,l=7.9,c=8);rows[-2]=dict(o=7.9,h=8.3,l=7.5,c=7.95);rows[-1]=dict(o=8,h=10.8,l=7.9,c=10.5,end=20)
  matches={x['pattern_name']:x['valid'] for x in patterns(rows,True,c)}
  self.assertTrue(matches['MORNING_STAR']);self.assertTrue(matches['MORNING_DOJI_STAR'])
 def test_aggregation_incomplete_rejected(self):
  from pa_v1.research import aggregate
  rows=[[i*60000,1,2,.5,1,1,(i+1)*60000-1] for i in range(5)]
  self.assertEqual(len(aggregate(rows,300000)),1);self.assertFalse(aggregate(rows[:-1],300000))
class RouteTests(unittest.TestCase):
 def test_readonly_route_without_server_or_workers(self):
  import io,json
  from unittest.mock import patch,Mock
  from zitar_full_paper_dashboard_v1 import make_server
  with patch('zitar_indicator_lab_v1.start_worker'),patch('pa_v1.runtime.start_worker'),patch('zitar_full_paper_dashboard_v1.ThreadingHTTPServer') as server:
   make_server('.')
   handler_class=server.call_args.args[1];handler=object.__new__(handler_class);handler.path='/api/pa-v1';handler.wfile=io.BytesIO();handler.send_response=Mock();handler.send_header=Mock();handler.end_headers=Mock()
   with patch('pa_v1.runtime.overview',return_value={'state':'NOT_STARTED','books':{}}):handler.do_GET()
   self.assertEqual(json.loads(handler.wfile.getvalue())['state'],'NOT_STARTED')
class SafetyFeatureTests(unittest.TestCase):
 def test_future_candles_do_not_change_decision(self):
  t=3600000000;c=Config();raw={}
  for tf,step in [('5m',300000),('15m',900000),('1h',3600000)]:
   raw[tf]=[[t-(100-i)*step,100,102,98,101,10,t-(99-i)*step-1] for i in range(100)]
  before=evaluate('X',raw,t,c)
  for tf,rows in raw.items():rows.append([t,999,99999,1,999,999999,t+99999999])
  self.assertEqual(before,evaluate('X',raw,t,c))
 def test_positive_three_touch_trendline_and_break(self):
  c=Config();rows=[{'c':100+i} for i in range(10)];st={'atr':1,'swings':[{'kind':'LOW','index':i,'price':100+i} for i in [0,3,6]]}
  self.assertEqual(trendline(st,rows,c)['state'],'SUPPORT');rows[-1]['c']=90
  self.assertEqual(trendline(st,rows,c)['state'],'BROKEN')
 def test_high_score_cannot_override_volume_gate(self):
  from unittest.mock import patch
  c=Config(min_score=0);t=3600000000
  rows=[dict(o=100,c=101,h=102,l=98,v=10,t=i,end=t-1) for i in range(100)]
  rows[-1].update(o=100,c=101,h=101.1,l=97,v=1)
  st=dict(state='BULLISH',atr=1,swings=[dict(kind='LOW',price=98,index=90,timestamp=90,confirmed_at=92),dict(kind='HIGH',price=120,index=80,timestamp=80,confirmed_at=82)])
  with patch('pa_v1.features.candles',return_value=rows),patch('pa_v1.features.structure',return_value=st),patch('pa_v1.features.atr',return_value=1):
   result=evaluate('X',{'1h':[],'15m':[],'5m':[]},t,c)
  self.assertEqual(result['decision'],'NO_TRADE');self.assertIn('VOLUME_TOO_LOW',result['reasons'])
if __name__=='__main__':unittest.main()

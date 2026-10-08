import copy,tempfile,unittest
from pathlib import Path
from zitar_indicator_lab_v1 import initial,apply_book,Lab
from zitar_indicator_lab_signals_v1 import analyze
from zitar_futures_paper_engine_v1 import POLICY

T=1790863200000
def market(ms,price='100'):
 return {'TEST':dict(quote=dict(bid=price,ask=price,mark=price,time=ms,next_funding=ms+3600000,funding_rate='0'),contract=dict(step='.001',min_qty='.001',max_qty='999999',min_notional='1'),funding=[],eligible=True)}
def sig(ms,**kw):return {'TEST':dict(candle_ms=ms-1,UT=0,RSI=0,WT=0,SQ=0,SCALP=0,wilder_rsi=40,**kw)}
def signal(ms,rule,value):
 a=sig(ms);a['TEST'][rule]=value;return a

class LabTests(unittest.TestCase):
 def test_initial_policy_isolation(self):
  s=initial(T);self.assertEqual(s['books']['SCALP20']['execution_policy']['leverage'],20);self.assertEqual(s['books']['UT5']['execution_policy']['leverage'],3);self.assertEqual(POLICY['leverage'],3)
  with tempfile.TemporaryDirectory() as td:self.assertEqual(len(Lab(Path(td)).state['books']),13)
 def test_20x_notional_fee_and_equity(self):
  b=initial(T)['books']['SCALP20'];apply_book(b,market(T+1000),signal(T+1000,'SCALP',1),T+1000)
  p=b['positions']['TEST'];self.assertAlmostEqual(float(p['quantity'])*float(p['entry']),20000,delta=.11)
  self.assertAlmostEqual(float(b['cash']),8990,delta=.02);self.assertLess(float(b['equity']),10000)
 def test_stale_quote_blocks_entry(self):
  b=initial(T)['books']['UT5'];apply_book(b,market(T),signal(T+40000,'UT',1),T+40000);self.assertFalse(b['positions'])
 def test_old_signal_blocks_entry(self):
  b=initial(T)['books']['UT5'];apply_book(b,market(T+1000),signal(T,'UT',1),T+1000);self.assertFalse(b['positions'])
 def test_duplicate_candle_no_reentry(self):
  b=initial(T)['books']['UT5'];a=signal(T+1000,'UT',1);apply_book(b,market(T+1000),a,T+1000);apply_book(b,market(T+2000,'97'),a,T+2000);self.assertFalse(b['positions']);self.assertEqual(len(b['closed']),1)
 def test_spot_short_forbidden(self):
  b=initial(T)['books']['WT15'];apply_book(b,market(T+1000),signal(T+1000,'WT',-1),T+1000);self.assertFalse(b['positions'])
 def test_spot_trend_required(self):
  b=initial(T)['books']['WT15'];apply_book(b,market(T+1000),signal(T+1000,'WT',1),T+1000);self.assertFalse(b['positions'])
 def test_scalp_midpoint_exit(self):
  b=initial(T)['books']['SCALP20'];apply_book(b,market(T+1000),signal(T+1000,'SCALP',1),T+1000)
  a=sig(T+61000);a['TEST']['wilder_rsi']=51;apply_book(b,market(T+61000,'100.2'),a,T+61000);self.assertEqual(b['closed'][0]['exit_reason'],'SIGNAL_EXIT')
 def test_daily_loss_latches(self):
  b=initial(T)['books']['SCALP20'];b['cash']='9790';apply_book(b,market(T+1000),signal(T+1000,'SCALP',1),T+1000);self.assertEqual(b['daily_limit'],'LOSS_STOP');self.assertFalse(b['positions'])
 def test_rollover_carries_equity(self):
  b=initial(T)['books']['UT5'];b['cash']='10100';apply_book(b,{}, {},T+86400000);self.assertEqual(len(b['daily']),1);self.assertEqual(float(b['period_start']),10100);self.assertEqual(float(b['slot']),1010)
 def test_future_candle_excluded(self):
  rows=[[T+i*60000,100,101,99,100,1000,T+(i+1)*60000-1] for i in range(251)]
  a=analyze(rows,T+250*60000,'1m');rows[-1][4]=999
  self.assertEqual(a,analyze(rows,T+250*60000,'1m'));self.assertEqual(a['SCALP'],0)
 def test_gap_rejected(self):
  rows=[[T+i*60000,100,101,99,100,1000,T+(i+1)*60000-1] for i in range(251)];rows.pop(100)
  with self.assertRaisesRegex(ValueError,'CANDLE_GAP'):analyze(rows,T+251*60000,'1m')

if __name__=='__main__':unittest.main()

import unittest
from decimal import Decimal as D
from zitar_indicator_lab_v1 import initial,apply_book
from zitar_next.scalping_risk import enter,RULES

T=1791754200000
def quote(ms=T+1000,price='100'):
 return dict(bid=price,ask=price,mark=price,time=ms,next_funding=ms+3600000,funding_rate='0')
C=dict(step='.001',min_qty='.001',max_qty='999999',min_notional='1')
def book():return initial(T)['books']['SCALP_RISK']
def market(ms):return {'TEST':dict(quote=quote(ms),contract=C,funding=[],eligible=True)}
def signal(ms):return {'TEST':dict(candle_ms=ms-1,SCALP=1,wilder_rsi=35)}
class RiskTests(unittest.TestCase):
 def test_sizes_cost_inclusive_risk_and_restores_slot(self):
  b=book();slot=b['slot'];self.assertEqual(enter(b,'TEST',1,quote(),C,T+1000,T+999),'OPENED')
  p=b['positions']['TEST'];self.assertLessEqual(D(p['planned_risk']),D('25'));self.assertLess(D(p['margin']),D('200'));self.assertEqual(b['slot'],slot)
 def test_short_has_same_risk_budget(self):
  b=book();enter(b,'TEST',-1,quote(),C,T+1000,T+999)
  self.assertLessEqual(D(b['positions']['TEST']['planned_risk']),D('25'))
 def test_three_position_cap(self):
  b=book()
  for i in range(3):self.assertEqual(enter(b,str(i),1,quote(),C,T+1000,T+999),'OPENED')
  self.assertEqual(enter(b,'four',1,quote(),C,T+1000,T+999),'RISK_SLOTS_FULL')
 def test_portfolio_risk_blocks_entry(self):
  b=book();b['positions']={'OLD':{'planned_risk':'100','initial_margin':'100'}}
  self.assertEqual(enter(b,'TEST',1,quote(),C,T+1000,T+999),'PORTFOLIO_RISK_BUDGET')
 def test_daily_fee_budget_blocks(self):
  b=book();b['fees_total']='25'
  self.assertEqual(enter(b,'TEST',1,quote(),C,T+1000,T+999),'DAILY_FEE_BUDGET')
 def test_close_cooldown_requires_three_closed_bars(self):
  b=book();b['closed']=[dict(symbol='TEST',closed_ms=T)]
  self.assertEqual(enter(b,'TEST',1,quote(),C,T+60000,T+59999),'SCALP_COOLDOWN_3_BARS')
  self.assertEqual(enter(b,'TEST',1,quote(),C,T+241000,T+239999),'OPENED')
 def test_one_percent_daily_loss_latches(self):
  b=book();b['cash']='9890';apply_book(b,market(T+1000),signal(T+1000),T+1000)
  self.assertEqual(b['daily_limit'],'LOSS_STOP');self.assertFalse(b['positions'])
 def test_control_sizing_is_not_changed(self):
  b=initial(T)['books']['SCALP20'];apply_book(b,market(T+1000),signal(T+1000),T+1000)
  self.assertGreater(D(b['positions']['TEST']['margin']),D('999'));self.assertNotIn('risk_rules',b)
 def test_real_execution_metadata(self):
  b=book();self.assertEqual(b['execution_policy']['signal_interval'],'1m');self.assertEqual(b['execution_policy']['trailing_stop_price_pct'],'.005');self.assertTrue(b['diagnostic_only'])
 def test_bad_quote_never_spends_cash(self):
  b=book();q=quote();q['ask']='99'
  with self.assertRaises(ValueError):enter(b,'TEST',1,q,C,T+1000,T+999)
  self.assertEqual(b['cash'],'10000');self.assertFalse(b['positions'])

if __name__=='__main__':unittest.main()

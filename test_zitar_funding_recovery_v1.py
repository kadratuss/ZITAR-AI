import unittest
from zitar_futures_paper_engine_v1 import fresh,open_position,apply_cycle,number
from zitar_futures_funding_recovery_v1 import reconcile_closed

class FundingRecovery(unittest.TestCase):
 def test_forecast_before_entry_is_not_a_missing_payment(self):
  from zitar_futures_funding_recovery_v1 import update_pending
  p=dict(opened_ms=1790481611159,next_funding_ms=1790481600000,funding_events=[],funding_pending=True)
  update_pending(p,[],1790493000000)
  self.assertFalse(p['funding_pending'])
  p['next_funding_ms']=p['opened_ms']
  update_pending(p,[],1790493000000)
  self.assertFalse(p['funding_pending'])
  p['next_funding_ms']=p['opened_ms']+1
  update_pending(p,[],1790493000000)
  self.assertTrue(p['funding_pending'])
 def test_pending_keeps_mark_stops_and_other_books_alive(self):
  t=1790456400000;s=fresh(t,[])
  q=dict(bid='100',ask='100',mark='100',time=t,book_time=t,next_funding=t+1000,funding_rate='0')
  c=dict(step='0.01',min_qty='0.01',max_qty='10000',min_notional='5')
  for name in ['BASELINE','SMA20_50']:open_position(s['books'][name],'BTC',1,q,c,t,'test')
  ms=t+2000;q.update(bid='101',ask='101',mark='101',time=ms,book_time=ms,next_funding=t+9000)
  market={'BTC':dict(quote=q,contract=c,candles=[],funding=[])}
  apply_cycle(s,market,ms)
  for name in ['BASELINE','SMA20_50']:
   b=s['books'][name];self.assertEqual(b['positions']['BTC']['quote_ms'],ms);self.assertTrue(b['accounting_pending']);self.assertEqual(b['valuation_ms'],ms)
   self.assertEqual(open_position(b,'ETH',1,q,c,ms,'test'),'ACCOUNTING_PENDING')
  q.update(bid='90',ask='90',mark='90',time=ms+1,book_time=ms+1)
  apply_cycle(s,market,ms+1)
  b=s['books']['BASELINE'];self.assertFalse(b['positions']);self.assertEqual(b['closed'][0]['exit_reason'],'TRAILING_STOP_2PCT')
  self.assertEqual(number(b['equity']),number(b['cash']))
  before=number(b['cash']);market['BTC']['funding']=[dict(fundingTime=t+1001,markPrice='100',fundingRate='0.001')]
  reconcile_closed(b,market,ms+2);after=number(b['cash']);self.assertLess(after,before);self.assertFalse(b['closed'][0]['funding_pending'])
  reconcile_closed(b,market,ms+3);self.assertEqual(number(b['cash']),after)

if __name__=='__main__':unittest.main()

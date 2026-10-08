import unittest
from unittest.mock import patch
from zitar_futures_paper_engine_v1 import fresh, apply_cycle, number, mark, open_position
from zitar_futures_shared_v1 import ensure_book, evaluate, NAME

class SharedTests(unittest.TestCase):
    def setUp(self):
        self.t=1790456400000
        self.s=fresh(self.t,[]);ensure_book(self.s,self.t);self.b=self.s['books'][NAME]
        self.q=dict(bid='100',ask='100',mark='100',time=self.t+300000,book_time=self.t+300000,next_funding=self.t+999999999,funding_rate='0')
        self.c=dict(step='0.01',min_qty='0.01',max_qty='10000',min_notional='5')
    def test_all_timeframes_share_ten_slots(self):
        market={str(i):dict(quote=self.q,contract=self.c,timeframes={'5m':[], '15m':[], '1h':[]}) for i in range(12)}
        with patch('zitar_futures_shared_v1.signals',return_value={'BASELINE':1,'candle_close_ms':self.t+299999}):
            evaluate(self.s,market,{s:self.q for s in market},self.t+300000,set(),[])
        self.assertEqual(len(self.b['positions']),10)
        self.assertGreaterEqual(number(self.b['cash']),0)
        self.assertEqual({p['timeframe'] for p in self.b['positions'].values()},{'1h'})
    def test_five_minute_does_not_wait_for_hour(self):
        def sig(rows,ms,interval_ms=3600000):
            return {'BASELINE':1,'candle_close_ms':self.t+299999 if interval_ms==300000 else self.t-1}
        data=dict(quote=self.q,contract=self.c,timeframes={'5m':[], '15m':[], '1h':[]})
        with patch('zitar_futures_shared_v1.signals',side_effect=sig):
            evaluate(self.s,{'BTC':data},{'BTC':self.q},self.t+300000,set(),[])
        self.assertEqual(self.b['positions']['BTC']['timeframe'],'5m')
    def test_other_timeframe_cannot_close_position(self):
        open_position(self.b,'BTC',1,self.q,self.c,self.t,'test');self.b['positions']['BTC']['timeframe']='5m'
        data=dict(quote=self.q,contract=self.c,timeframes={'5m':[], '15m':[], '1h':[]})
        def sig(rows,ms,interval_ms=3600000):
            return {'BASELINE':-1,'candle_close_ms':self.t-1 if interval_ms==300000 else self.t+299999}
        with patch('zitar_futures_shared_v1.signals',side_effect=sig):
            evaluate(self.s,{'BTC':data},{'BTC':self.q},self.t+300000,set(),[])
        self.assertEqual(self.b['positions']['BTC']['direction'],1)
    def test_rollover_compounds_once(self):
        self.b.update(cash='10300',equity='10300')
        apply_cycle(self.s,{},self.t+86400000)
        self.assertEqual(number(self.b['slot']),1030)
        apply_cycle(self.s,{},self.t+86400001)
        self.assertEqual(len(self.b['daily']),1)
    def test_initialization_preserves_existing_accounts(self):
        self.s['books']['BASELINE']['cash']='123'
        ensure_book(self.s,self.t+1)
        self.assertEqual(self.s['books']['BASELINE']['cash'],'123')
        self.assertEqual(self.b['started_ms'],self.t)

if __name__=='__main__':unittest.main()

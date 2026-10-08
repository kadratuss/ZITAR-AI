import tempfile,unittest,copy
from pathlib import Path
from zitar_rsi_timeframes_v1 import Experiment,aggregate_10m
from zitar_futures_paper_engine_v1 import fresh,apply_cycle
class TimeframeTests(unittest.TestCase):
 def test_aggregation_requires_complete_aligned_pair(self):
  rows=[[i*300000,'100','103','98',str(100+i),'4',i*300000+299999] for i in range(4)]
  a=aggregate_10m(rows,1200000)
  self.assertEqual(len(a),2);self.assertEqual(a[0][4],'101');self.assertEqual(a[0][6],599999)
  self.assertEqual(len(aggregate_10m(rows,599999)),0)
  self.assertEqual(len(aggregate_10m(rows[1:],1200000)),1)
 def test_hourly_matches_production_and_isolated(self):
  t=1791201600000
  with tempfile.TemporaryDirectory() as d:
   e=Experiment(Path(d));e.cycle(['BTCUSDT'],{},t)
   reference=copy.deepcopy(e.data['accounts']['1h'])
   ms=t+3600001
   frames={}
   for tf,step in [('5m',300000),('1h',3600000)]:
    end=(ms//step)*step
    frames[tf]=[[end-(151-i)*step,'200','201','40',str(200-i),'1',end-(150-i)*step-1] for i in range(151)]
   q=dict(bid='50',ask='50',mark='50',time=ms,book_time=ms,next_funding=ms+3600000,funding_rate='0')
   x=dict(quote=q,funding=[],timeframes=frames,candles=frames['1h'],contract=dict(step='.01',min_qty='.01',max_qty='100000',min_notional='5'))
   # Existing engine deliberately skips its first observed candle.
   for s in e.data['accounts'].values():s['last_candles']['BTCUSDT']=t-1
   reference['last_candles']['BTCUSDT']=t-1
   apply_cycle(reference,{'BTCUSDT':x},ms)
   e.cycle(['BTCUSDT'],{'BTCUSDT':x},ms)
   self.assertEqual(e.data['accounts']['1h']['books']['RSI14'],reference['books']['RSI14'])
   for s in e.data['accounts'].values():self.assertEqual(len(s['books']['RSI14']['positions']),1)
   loaded=Experiment(Path(d));loaded.cycle(['BTCUSDT'],{'BTCUSDT':x},ms)
   for s in loaded.data['accounts'].values():self.assertEqual(len(s['books']['RSI14']['positions']),1)
if __name__=='__main__':unittest.main()

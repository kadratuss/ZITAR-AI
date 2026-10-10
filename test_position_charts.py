import unittest
from unittest.mock import patch
from zitar_next.position_charts import normalize,candles,positions,_cache

class PositionChartTests(unittest.TestCase):
    def test_spot_and_futures_are_not_interchanged(self):
        p=normalize(dict(symbol='MINAUSDT',entry='0.084536904',mark='0.08437589',quantity='35487',direction=1,unrealized='-5.713903818',trailing_stop='0.0837214'),'futures','RSI',0)
        self.assertAlmostEqual(float(p['quantity'])*(float(p['mark'])-float(p['entry'])),-5.713903818)
        self.assertEqual(p['currency'],'USDT');self.assertEqual(p['stop'],'0.0837214')
        self.assertIsNone(normalize(dict(symbol='MINATRY',entry_fill_price='4'),'spot','Master',0)['stop'])
        self.assertEqual(normalize(dict(symbol='GTRY',entry_fill_price='4'),'spot','Master',0)['currency'],'TRY')
    def test_public_endpoint_identity_and_validation(self):
        _cache.clear()
        with patch('zitar_next.position_charts.read_json',return_value=[[0,'1','2','.5','1.5',0,100]]) as fetch:
            self.assertEqual(candles('futures','MINAUSDT','1h')['rows'][0]['close'],1.5)
            self.assertIn('markPriceKlines',fetch.call_args.args[0])
        for args in [('futures','MINATRY','1h'),('spot','../../x','1h'),('spot','MINATRY','2h')]:
            with self.assertRaises(ValueError):candles(*args)
    def test_missing_source_is_explicit(self):
        with patch('zitar_next.position_charts.read_json',side_effect=OSError):
            d=positions(5020)
        self.assertFalse(d['real_orders']);self.assertEqual(d['positions'],[]);self.assertIn('futures-paper',d['unavailable'])

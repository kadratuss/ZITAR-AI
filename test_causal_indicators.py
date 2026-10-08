import copy
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from causal_indicators import add_indicators, FEATURES

H = 3600000


def rows(prices=range(10, 20), symbol="BTCUSDT"):
    return [dict(date=(datetime(1970, 1, 1)+timedelta(hours=i)).strftime("%Y-%m-%d %H:%M:%S"),
                 tic=symbol, open=float(p), high=float(p+1), low=float(p-1),
                 close=float(p), volume=1., extra={"a": []}) for i, p in enumerate(prices)]


class IndicatorTests(unittest.TestCase):
    def calc(self, records=None, **kwargs):
        options = dict(as_of_ms=100*H, sma_period=3, ema_period=3,
                       rsi_period=3, atr_period=3, macd_fast=2, macd_slow=3, macd_signal=2)
        options.update(kwargs)
        return add_indicators(rows() if records is None else records, **options)

    def test_sma_ema_known_values(self):
        result = self.calc()
        self.assertIsNone(result[1]["sma"])
        self.assertEqual(result[2]["sma"], 11.)
        self.assertEqual(result[2]["ema"], 11.)
        self.assertEqual(result[3]["ema"], 12.)
        self.assertEqual(result[3]["sma"], 12.)

    def test_rsi_wilder_known_sequence(self):
        result = self.calc(rows([10, 11, 10, 12, 11]))
        self.assertIsNone(result[2]["rsi"])
        self.assertAlmostEqual(result[3]["rsi"], 75.)
        self.assertAlmostEqual(result[4]["rsi"], 600/11)

    def test_rsi_flat_up_down(self):
        for prices, expected in (([10]*5, 50.), (range(10, 15), 100.), (range(15, 10, -1), 0.)):
            self.assertEqual(self.calc(rows(prices))[-1]["rsi"], expected)

    def test_atr_includes_price_gaps(self):
        result = self.calc(rows([10, 15, 14, 14]))
        self.assertAlmostEqual(result[2]["atr"], 10/3)
        self.assertAlmostEqual(result[3]["atr"], 26/9)

    def test_macd_and_signal_seed(self):
        result = self.calc()
        self.assertAlmostEqual(result[2]["macd"], .5)
        self.assertIsNone(result[2]["macd_signal"])
        self.assertAlmostEqual(result[3]["macd_signal"], .5)
        self.assertAlmostEqual(result[3]["macd_hist"], 0.)

    def test_warmup_no_backfill(self):
        result = add_indicators(rows(range(10, 60)), as_of_ms=100*H)
        self.assertFalse(result[32]["features_ready"])
        self.assertTrue(result[33]["features_ready"])
        self.assertIsNone(result[0]["ema"])

    def test_prefix_invariance(self):
        full = self.calc()
        for size in range(1, 11):
            self.assertEqual(self.calc(rows()[:size]), full[:size])
        changed = rows()
        for r in changed[6:]:
            r.update(open=1000., high=1001., low=999., close=1000.)
        self.assertEqual(self.calc(changed)[:6], full[:6])

    def test_symbol_isolation_sorting_and_copy(self):
        original = rows()+rows(range(100, 110), "ETHUSDT")
        before = copy.deepcopy(original)
        mixed = self.calc(original[::-1])
        self.assertEqual([r for r in mixed if r["tic"] == "BTCUSDT"], self.calc())
        mixed[0]["extra"]["a"].append(1)
        self.assertEqual(original, before)

    def test_duplicate_gap_and_grid_mismatch(self):
        for data in (rows()+rows()[:1], rows()[:2]+rows()[3:], rows()+rows(range(100,109), "ETHUSDT")):
            with self.assertRaises(ValueError):
                self.calc(data)

    def test_invalid_options(self):
        for kwargs in ({"sma_period": 0}, {"ema_period": True}, {"rsi_period": 1.5},
                       {"macd_fast": 4}, {"interval": "1m"}, {"as_of_ms": -1}):
            with self.assertRaises(ValueError):
                self.calc(**kwargs)

    def test_invalid_candles(self):
        for field, value in (("close", "NaN"), ("volume", -1), ("high", 1),
                             ("date", "1970-01-01"), ("tic", ""), ("sma", 1)):
            data = rows()
            data[0][field] = value
            with self.assertRaises(ValueError):
                self.calc(data)
        with self.assertRaises(ValueError):
            self.calc(as_of_ms=9*H)

    def test_closed_boundary_and_empty(self):
        self.assertEqual(len(self.calc(rows()[:1], as_of_ms=H)), 1)
        with self.assertRaises(ValueError):
            self.calc(rows()[:1], as_of_ms=H-1)
        self.assertEqual(self.calc([]), [])

    def test_period_one(self):
        result = self.calc(sma_period=1, ema_period=1, atr_period=1, rsi_period=1)
        self.assertEqual(result[0]["sma"], 10.)
        self.assertEqual(result[0]["ema"], 10.)
        self.assertEqual(result[1]["rsi"], 100.)

    def test_no_io_or_network(self):
        with patch("builtins.open", side_effect=AssertionError("IO")), patch("socket.socket", side_effect=AssertionError("network")):
            self.assertEqual(len(self.calc()), 10)


if __name__ == "__main__":
    unittest.main()

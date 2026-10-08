import io
import json
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from online_finrl_data import _get_json, fetch_latest_records, main

H = 3600000


def page(start=H, n=2):
    return [[start+i*H, "10", "12", "9", "11", "0", start+(i+1)*H-1] for i in range(n)]


class OnlineTests(unittest.TestCase):
    def fetch(self, data=None):
        with patch("online_finrl_data._get_json", side_effect=[{"serverTime": 3*H+100}, page() if data is None else data]):
            return fetch_latest_records(["BTCUSDT"], count=2)

    def test_mapping_closed_cutoff(self):
        result = self.fetch()
        self.assertEqual(result["quote_currency"], "USDT")
        self.assertEqual(result["closed_before_ms"], 3*H)
        self.assertEqual(result["records"][0]["date"], "1970-01-01 01:00:00")
        self.assertEqual(result["records"][0]["close"], 11.)

    def test_joint_snapshot_and_parameters(self):
        with patch("online_finrl_data._get_json", side_effect=[{"serverTime": 3*H}, page(), page()]) as get, patch("online_finrl_data.time.sleep"):
            result = fetch_latest_records(["ETHUSDT", "BTCUSDT"], count=2)
        self.assertEqual(len(result["records"]), 4)
        self.assertEqual(get.call_args_list[1].args[1], {"symbol": "BTCUSDT", "interval": "1h", "startTime": H, "endTime": 3*H-1, "limit": 2})

    def test_invalid_inputs_before_network(self):
        with patch("online_finrl_data._get_json", side_effect=AssertionError("network")):
            for symbols in ([], "BTCUSDT", ["BTCTRY"], ["BTCUSDT", "BTCUSDT"], ["btcUSDT"]):
                with self.assertRaises(ValueError):
                    fetch_latest_records(symbols)
            for kwargs in ({"count": True}, {"count": 1001}, {"interval": "1m"}):
                with self.assertRaises(ValueError):
                    fetch_latest_records(["BTCUSDT"], **kwargs)

    def test_bad_server_clock(self):
        for clock in ({}, {"serverTime": True}, [], {"serverTime": -1}):
            with patch("online_finrl_data._get_json", return_value=clock), self.assertRaises(ValueError):
                fetch_latest_records(["BTCUSDT"])

    def test_bad_pages(self):
        for data in ([], {"code": -1}, page(n=1), page(start=0), [page()[0], page()[0]], [[1]]):
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.fetch(data)

    def test_ohlcv(self):
        for column, value in ((1, "NaN"), (2, "8"), (3, "12"), (4, "0"), (5, "-1"), (5, None)):
            data = page()
            data[0][column] = value
            with self.assertRaises(ValueError):
                self.fetch(data)

    def test_daily(self):
        duration = 86400000
        candle = [0, "10", "12", "9", "11", "0", duration-1]
        with patch("online_finrl_data._get_json", side_effect=[{"serverTime": duration}, [candle]]):
            self.assertEqual(len(fetch_latest_records(["BTCUSDT"], "1d", 1)["records"]), 1)

    def test_http_get_only(self):
        response = Mock()
        response.read.return_value = b'{"serverTime": 1}'
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        opener = Mock()
        opener.open.return_value = response
        with patch("online_finrl_data.build_opener", return_value=opener):
            self.assertEqual(_get_json("/api/v3/time"), {"serverTime": 1})
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.full_url, "https://data-api.binance.vision/api/v3/time")
        self.assertIsNone(request.data)
        self.assertFalse(request.has_header("X-mbx-apikey"))
        with self.assertRaises(ValueError):
            _get_json("/api/v3/order")

    def test_rate_limits_stop_without_retry(self):
        for status in (418, 429):
            opener = Mock()
            opener.open.side_effect = HTTPError("url", status, "limit", {"Retry-After": "60"}, None)
            with patch("online_finrl_data.build_opener", return_value=opener), patch("online_finrl_data.time.sleep") as sleep, self.assertRaises(RuntimeError):
                _get_json("/api/v3/time")
            self.assertEqual(opener.open.call_count, 1)
            sleep.assert_not_called()

    def test_connection_retries_bounded(self):
        opener = Mock()
        opener.open.side_effect = URLError("offline")
        with patch("online_finrl_data.build_opener", return_value=opener), patch("online_finrl_data.time.sleep"), self.assertRaises(RuntimeError):
            _get_json("/api/v3/time")
        self.assertEqual(opener.open.call_count, 3)

    def test_cli(self):
        with patch("online_finrl_data.fetch_latest_records", return_value={"records": []}), patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(main(["BTCUSDT", "--count", "2"]), 0)
            self.assertEqual(json.loads(out.getvalue()), {"records": []})


if __name__ == "__main__":
    unittest.main()

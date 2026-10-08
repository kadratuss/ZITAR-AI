import hashlib
import json
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from research_dashboard import ResearchStore, make_handler
from test_causal_indicators import rows


def report():
    metric = dict(return_pct=-3.8, max_drawdown_pct=4.5, final_equity=9620., trades=2)
    results = {s: dict(metric) for s in ("ppo", "buy_hold", "sma20_50", "cash")}
    partition = dict(retained_rows=10, first_date="1970-01-01 00:00:00", last_date="1970-01-01 09:00:00")
    return dict(symbol="BTCUSDT", actual_timesteps=2048, seed=42,
                results={"test": results, "validation": results},
                split={"partitions": {k: partition for k in ("train", "validation", "test")}},
                fee_per_side=.001, slippage_per_side=.001, snapshot_sha256="fixture",
                shadow={"events": [{"event": "no_new_closed_candle"}], "simulated_trades": 0})


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root/"test-run"
        self.folder.mkdir()
        self.snapshot = {"records": rows(range(100,160)), "server_time_ms": 60*3600000,
                         "interval": "1h", "source": "Binance global"}
        self.write("report.json", report())
        self.write("snapshot.json", self.snapshot)
        self.store = ResearchStore(self.root)

    def write(self, name, data):
        (self.folder/name).write_text(json.dumps(data), encoding="utf-8")

    def test_runs_and_validated_payload(self):
        (self.root/"unfinished").mkdir()
        self.assertEqual(self.store.runs(), ["test-run"])
        data = self.store.load("test-run")
        self.assertEqual(data["quality"]["checked_rows"], 60)
        self.assertEqual(data["quality"]["ready_rows"], 27)
        self.assertNotIn("records", data["snapshot"])
        self.assertEqual(len(data["candles"]), 60)

    def test_never_mutates_files(self):
        def digest():
            return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.folder.iterdir()}
        before = digest()
        self.store.runs()
        self.store.load("test-run")
        self.assertEqual(digest(), before)

    def test_path_traversal_and_invalid_identifier(self):
        for name in ("../test-run", "/etc", "test-run/../", "", "a"*101):
            with self.assertRaises(ValueError):
                self.store.load(name)

    def test_invalid_snapshot_and_metric(self):
        data = report()
        data["results"]["test"]["ppo"]["return_pct"] = float("nan")
        self.write("report.json", data)
        with self.assertRaises(ValueError):
            self.store.load("test-run")
        self.write("report.json", report())
        self.snapshot["records"][0]["close"] = -1
        self.write("snapshot.json", self.snapshot)
        with self.assertRaises(ValueError):
            self.store.load("test-run")

    def test_invalid_json_and_missing_file(self):
        (self.folder/"report.json").write_text("{broken", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.store.load("test-run")
        (self.folder/"report.json").unlink()
        with self.assertRaises(FileNotFoundError):
            self.store.load("test-run")

    def test_market_cache_and_failure_not_fake_success(self):
        payload = dict(self.snapshot)
        payload["closed_before_ms"] = payload["server_time_ms"]
        with patch("research_dashboard.fetch_latest_records", return_value=payload) as fetch:
            self.assertFalse(self.store.market("BTCUSDT")["cached"])
            self.assertTrue(self.store.market("BTCUSDT")["cached"])
            self.assertEqual(fetch.call_count, 1)
        with patch("research_dashboard.fetch_latest_records", side_effect=RuntimeError("rate limited")):
            with self.assertRaises(RuntimeError):
                self.store.market("ETHUSDT")

    def test_http_get_routes_security_and_empty_state(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.store))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            base = "http://127.0.0.1:"+str(server.server_port)
            with urlopen(base+"/api/runs") as response:
                self.assertEqual(json.load(response)["runs"], ["test-run"])
                self.assertEqual(response.headers["X-Frame-Options"], "DENY")
            with urlopen(base+"/") as response:
                self.assertIn("Araştırma kontrol paneli", response.read().decode())
            for path, code in (("/api/run?id=..%2Ftest-run", 400), ("/unknown", 404)):
                with self.assertRaises(HTTPError) as caught:
                    urlopen(base+path)
                self.assertEqual(caught.exception.code, code)
                caught.exception.close()
            with self.assertRaises(HTTPError) as caught:
                urlopen(Request(base+"/api/runs", headers={"Host": "external.example"}))
            self.assertEqual(caught.exception.code, 403)
            caught.exception.close()
            with self.assertRaises(HTTPError) as caught:
                urlopen(Request(base+"/api/runs", data=b"{}", method="POST"))
            self.assertEqual(caught.exception.code, 501)
            caught.exception.close()
        finally:
            server.shutdown()
            server.server_close()
            worker.join()


if __name__ == "__main__":
    unittest.main()

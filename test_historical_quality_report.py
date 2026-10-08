import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch

from historical_quality_report import audit_history, main

H = 3_600_000


class QualityReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "snapshot # test.db"
        self.sql("""CREATE TABLE historical_candles (
            symbol TEXT, interval TEXT, open_time_ms INTEGER,
            close_time_ms INTEGER, open_price TEXT, high_price TEXT,
            low_price TEXT, close_price TEXT, volume TEXT, fetched_at TEXT)""")

    def sql(self, query, args=()):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(query, args)

    def add(self, t=0, symbol="BTCTRY", interval="1h", **changes):
        row = dict(symbol=symbol, interval=interval, open_time_ms=t,
                   close_time_ms=t + (86400000 if interval == "1d" else H) - 1,
                   open_price="10", high_price="12", low_price="9",
                   close_price="11", volume="0", fetched_at="fixture")
        row.update(changes)
        self.sql("INSERT INTO historical_candles VALUES (?,?,?,?,?,?,?,?,?,?)",
                 tuple(row.values()))

    def audit(self, **kwargs):
        return audit_history(self.path, as_of_ms=10*H, **kwargs)

    def test_healthy_and_alignment(self):
        for symbol in ("ETHTRY", "BTCTRY"):
            for t in (2*H, 0, H):
                self.add(t, symbol)
        report = self.audit()
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["total_rows"], 6)
        group = report["groups"][0]
        self.assertEqual(group["symbol"], "BTCTRY")
        self.assertEqual(group["coverage_ratio"], 1.)
        self.assertEqual(group["longest_contiguous_candles"], 3)
        self.assertEqual(report["alignment"][0]["common_candles"], 3)
        self.assertTrue(report["alignment"][0]["identical_grids"])

    def test_gaps_are_exact_and_bounded(self):
        for t in (0, 2*H, 4*H, 100*H):
            self.add(t)
        report = audit_history(self.path, as_of_ms=101*H, sample_limit=1)
        group = report["groups"][0]
        self.assertEqual(group["missing_candles_in_observed_span"], 97)
        self.assertEqual(group["expected_candles_in_observed_span"], 101)
        self.assertEqual(group["longest_contiguous_candles"], 1)
        self.assertEqual(len(group["examples"]["gaps"]), 1)
        self.assertEqual(group["examples"]["gaps"][0]["first_missing_ms"], H)

    def test_duplicate_and_invalid_candle(self):
        self.add()
        self.add()
        self.add(H, volume="-1")
        self.add(2*H)
        group = self.audit()["groups"][0]
        self.assertEqual(group["issues"], {"duplicate_open_time": 1, "invalid_ohlcv": 1})
        self.assertEqual(group["valid_unique_closed_candles"], 2)
        self.assertEqual(group["missing_candles_in_observed_span"], 1)

    def test_malformed_values(self):
        for i, changes in enumerate((dict(open_price="NaN"), dict(volume="inf"),
                                    dict(high_price="8"), dict(low_price="12"),
                                    dict(close_price="0"), dict(volume=None),
                                    dict(open_price="bad"))):
            self.add(i*H, **changes)
        self.assertEqual(self.audit()["groups"][0]["issues"]["invalid_ohlcv"], 7)

    def test_invalid_times_and_identity(self):
        self.add(open_time_ms=-1)
        self.add(H, close_time_ms=0)
        self.add(2*H, open_time_ms="broken")
        self.add(3*H, symbol="")
        self.add(4*H, interval="1m")
        report = self.audit()
        self.assertEqual(report["status"], "attention")
        counts = {}
        for group in report["groups"]:
            for key, value in group["issues"].items():
                counts[key] = counts.get(key, 0) + value
        self.assertEqual(counts["invalid_times"], 3)
        self.assertEqual(counts["invalid_symbol"], 1)
        self.assertEqual(counts["unsupported_interval"], 1)

    def test_unclosed_boundary(self):
        self.add()
        group = audit_history(self.path, as_of_ms=H-1)["groups"][0]
        self.assertEqual(group["unclosed_rows"], 1)
        self.assertEqual(group["valid_unique_closed_candles"], 0)
        self.assertEqual(audit_history(self.path, as_of_ms=H)["status"], "ok")

    def test_different_grids(self):
        self.add()
        self.add(H, "ETHTRY")
        alignment = self.audit()["alignment"][0]
        self.assertFalse(alignment["identical_grids"])
        self.assertEqual(alignment["union_candles"], 2)
        self.assertEqual(alignment["common_candles"], 0)
        self.assertEqual(self.audit()["status"], "attention")

    def test_daily(self):
        self.add(interval="1d")
        self.add(86400000, interval="1d")
        group = audit_history(self.path, as_of_ms=2*86400000)["groups"][0]
        self.assertEqual(group["longest_contiguous_candles"], 2)

    def test_empty_schema_and_arguments(self):
        self.assertEqual(self.audit()["status"], "attention")
        for kwargs in ({"as_of_ms": True}, {"as_of_ms": -1}, {"sample_limit": -1}):
            with self.assertRaises(ValueError):
                audit_history(self.path, **kwargs)
        self.sql("DROP TABLE historical_candles")
        with self.assertRaisesRegex(ValueError, "missing columns"):
            self.audit()

    def test_missing_path_and_sidecars(self):
        missing = self.path.with_name("absent.db")
        with self.assertRaises(FileNotFoundError):
            audit_history(missing)
        self.assertFalse(missing.exists())
        for suffix in ("-wal", "-shm", "-journal"):
            sidecar = Path(str(self.path) + suffix)
            sidecar.write_bytes(b"fixture")
            with self.assertRaisesRegex(ValueError, "snapshot"):
                self.audit()
            sidecar.unlink()

    def test_readonly_and_no_network(self):
        self.add()
        digest = hashlib.sha256(self.path.read_bytes()).digest()
        before = sorted(p.name for p in self.path.parent.iterdir())
        original = sqlite3.connect
        connections = []
        def connect(database, **kwargs):
            self.assertTrue(database.endswith("?mode=ro&immutable=1"))
            db = original(database, **kwargs)
            connections.append(db)
            with self.assertRaises(sqlite3.OperationalError):
                db.execute("DELETE FROM historical_candles")
            return db
        with patch("historical_quality_report.sqlite3.connect", side_effect=connect), \
                patch("socket.socket", side_effect=AssertionError("network forbidden")):
            self.audit()
        self.assertEqual(digest, hashlib.sha256(self.path.read_bytes()).digest())
        self.assertEqual(before, sorted(p.name for p in self.path.parent.iterdir()))
        with self.assertRaises(sqlite3.ProgrammingError):
            connections[0].execute("SELECT 1")

    def test_cli_json_and_exit_codes(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(main([str(self.path), "--as-of-ms", str(H)]), 1)
        self.assertEqual(json.loads(out.getvalue())["total_rows"], 0)
        self.add()
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main([str(self.path), "--as-of-ms", str(H)]), 0)
        with redirect_stderr(err):
            self.assertEqual(main([str(self.path), "--sample-limit", "-1"]), 2)
        self.assertIn("Audit failed", err.getvalue())

    def test_zero_samples_still_counts(self):
        self.add(volume="-1")
        group = self.audit(sample_limit=0)["groups"][0]
        self.assertEqual(group["issues"]["invalid_ohlcv"], 1)
        self.assertEqual(group["examples"]["invalid_ohlcv"], [])


if __name__ == "__main__":
    unittest.main()

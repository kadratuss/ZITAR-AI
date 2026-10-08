import hashlib
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from finrl_data_adapter import COLUMNS, load_finrl_dataframe, read_finrl_records

HOUR = 3_600_000


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "history # offline.db"
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("""CREATE TABLE historical_candles (
                symbol TEXT NOT NULL, interval TEXT NOT NULL,
                open_time_ms INTEGER NOT NULL, close_time_ms INTEGER NOT NULL,
                open_price TEXT NOT NULL, high_price TEXT NOT NULL,
                low_price TEXT NOT NULL, close_price TEXT NOT NULL,
                volume TEXT NOT NULL, fetched_at TEXT NOT NULL,
                PRIMARY KEY(symbol, interval, open_time_ms))""")
            for symbol in ("BTCTRY", "ETHTRY"):
                for t in (0, HOUR, 2 * HOUR):
                    db.execute("INSERT INTO historical_candles VALUES (?,?,?,?,?,?,?,?,?,?)",
                               (symbol, "1h", t, t + HOUR - 1,
                                "10", "12", "9", "11", "0", "fixture"))

    def read(self, **kwargs):
        return read_finrl_records(self.path, ["ETHTRY", "BTCTRY"],
                                  as_of_ms=3 * HOUR, **kwargs)

    def mutate(self, sql, args=()):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(sql, args)

    def test_mapping_sort_and_utc(self):
        rows = self.read()
        self.assertEqual(len(rows), 6)
        self.assertEqual(tuple(rows[0]), COLUMNS)
        self.assertEqual(rows[0], dict(date="1970-01-01 00:00:00", tic="BTCTRY",
                                      open=10., high=12., low=9., close=11.,
                                      volume=0., day=3))
        self.assertEqual(rows[2]["date"], "1970-01-01 01:00:00")

    def test_half_open_window(self):
        self.assertEqual(len(self.read(start_ms=HOUR, end_ms=2 * HOUR)), 2)

    def test_unclosed_excluded(self):
        rows = read_finrl_records(self.path, ["BTCTRY"], as_of_ms=HOUR - 1)
        self.assertEqual(rows, [])
        self.assertEqual(len(read_finrl_records(self.path, ["BTCTRY"],
                                               as_of_ms=HOUR)), 1)

    def test_missing_database_never_created(self):
        path = self.path.with_name("missing.db")
        with self.assertRaises(FileNotFoundError):
            read_finrl_records(path, ["BTCTRY"])
        self.assertFalse(path.exists())

    def test_readonly_offline_no_sidecars(self):
        before = hashlib.sha256(self.path.read_bytes()).digest()
        files = sorted(p.name for p in self.path.parent.iterdir())
        original = sqlite3.connect
        connections = []
        def connect(database, **kwargs):
            self.assertTrue(database.endswith("?mode=ro&immutable=1"))
            conn = original(database, **kwargs)
            connections.append(conn)
            with self.assertRaises(sqlite3.OperationalError):
                conn.execute("DELETE FROM historical_candles")
            return conn
        with patch("finrl_data_adapter.sqlite3.connect", side_effect=connect), \
                patch("socket.socket", side_effect=AssertionError("network forbidden")):
            self.read()
        self.assertEqual(before, hashlib.sha256(self.path.read_bytes()).digest())
        self.assertEqual(files, sorted(p.name for p in self.path.parent.iterdir()))
        with self.assertRaises(sqlite3.ProgrammingError):
            connections[0].execute("SELECT 1")

    def test_invalid_prices_and_volume(self):
        for column, value in (("open_price", "NaN"), ("high_price", "inf"),
                              ("low_price", "11"), ("close_price", "0"),
                              ("volume", "-1"), ("volume", "garbage")):
            with self.subTest(column=column, value=value):
                self.mutate(f"UPDATE historical_candles SET {column}=? WHERE open_time_ms=0", (value,))
                with self.assertRaises(ValueError):
                    self.read()
                self.mutate("UPDATE historical_candles SET open_price='10', high_price='12', low_price='9', close_price='11', volume='0'")

    def test_bad_timestamp(self):
        self.mutate("UPDATE historical_candles SET close_time_ms=1 WHERE open_time_ms=0")
        with self.assertRaises(ValueError):
            self.read()

    def test_gap_and_missing_symbol(self):
        self.mutate("DELETE FROM historical_candles WHERE open_time_ms=?", (HOUR,))
        with self.assertRaises(ValueError):
            self.read()
        with self.assertRaises(ValueError):
            read_finrl_records(self.path, ["BTCTRY", "UNKNOWN"], end_ms=HOUR)

    def test_duplicate_without_schema_constraint(self):
        self.mutate("CREATE TABLE copy AS SELECT * FROM historical_candles")
        self.mutate("DROP TABLE historical_candles")
        self.mutate("ALTER TABLE copy RENAME TO historical_candles")
        self.mutate("INSERT INTO historical_candles SELECT * FROM historical_candles WHERE open_time_ms=0")
        with self.assertRaises(ValueError):
            self.read()

    def test_arguments_and_sql_parameterization(self):
        for kwargs in ({"interval": "1m"}, {"start_ms": -1},
                       {"end_ms": 0}, {"start_ms": True}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.read(**kwargs)
        for symbols in ([], "BTCTRY", ["BTCTRY", "BTCTRY"]):
            with self.assertRaises(ValueError):
                read_finrl_records(self.path, symbols)
        self.assertEqual(read_finrl_records(self.path, ["' OR 1=1 --"]), [])

    def test_daily_and_empty(self):
        self.mutate("UPDATE historical_candles SET interval='1d', close_time_ms=86399999 WHERE open_time_ms=0")
        rows = self.read(interval="1d")
        self.assertEqual(rows, [])
        rows = read_finrl_records(self.path, ["BTCTRY"], "1d", as_of_ms=86400000)
        self.assertEqual(len(rows), 1)

    def test_dataframe_shared_index_and_empty_dtypes(self):
        frame = load_finrl_dataframe(self.path, ["BTCTRY", "ETHTRY"], as_of_ms=3*HOUR)
        self.assertEqual(frame.index.tolist(), [0, 0, 1, 1, 2, 2])
        self.assertEqual(list(frame.columns), list(COLUMNS))
        empty = load_finrl_dataframe(self.path, ["BTCTRY"], as_of_ms=0)
        self.assertTrue(empty.empty)
        self.assertEqual(str(empty.close.dtype), "float64")


if __name__ == "__main__":
    unittest.main()

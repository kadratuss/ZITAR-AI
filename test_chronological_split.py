import copy
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from chronological_split import split_records


def date(i):
    return (datetime(2024, 1, 1) + timedelta(hours=i)).strftime("%Y-%m-%d %H:%M:%S")


def fixtures(n=18):
    return [dict(date=date(i), tic=s, close=float(i+1), extras={"value": [i]})
            for i in range(n) for s in ("BTCTRY", "ETHTRY")]


class SplitTests(unittest.TestCase):
    def split(self, rows=None, **kwargs):
        options = dict(validation_start=date(6), test_start=date(12))
        options.update(kwargs)
        return split_records(fixtures() if rows is None else rows, **options)

    def test_half_open_and_joint_symbols(self):
        result = self.split()
        self.assertEqual(result["train"][-1]["date"], date(5))
        self.assertEqual(result["validation"][0]["date"], date(6))
        self.assertEqual(result["test"][0]["date"], date(12))
        self.assertEqual(result["excluded"], [])
        for name in ("train", "validation", "test"):
            self.assertEqual(len(result[name]), 12)
            times = {r["date"] for r in result[name]}
            for stamp in times:
                self.assertEqual({r["tic"] for r in result[name] if r["date"] == stamp},
                                 {"BTCTRY", "ETHTRY"})

    def test_unordered_input_deterministic(self):
        self.assertEqual(self.split(fixtures()[::-1]), self.split())
        self.assertEqual(self.split(iter(fixtures())), self.split())

    def test_purge_embargo_and_conservation(self):
        result = self.split(label_horizon_steps=2, embargo_steps=1)
        self.assertEqual(result["train"][-1]["date"], date(3))
        self.assertEqual(result["validation"][0]["date"], date(7))
        self.assertEqual(result["validation"][-1]["date"], date(9))
        self.assertEqual(result["test"][0]["date"], date(13))
        self.assertEqual(len(result["excluded"]), 12)
        self.assertEqual(sum(len(result[k]) for k in ("train", "validation", "test", "excluded")), 36)
        all_keys = [(r["date"], r["tic"]) for k in ("train", "validation", "test", "excluded") for r in result[k]]
        self.assertEqual(len(set(all_keys)), 36)

    def test_forward_labels_stay_inside_raw_partition(self):
        horizon = 2
        result = self.split(label_horizon_steps=horizon)
        for name, boundary in (("train", 6), ("validation", 12)):
            for row in result[name]:
                index = int((datetime.strptime(row["date"], "%Y-%m-%d %H:%M:%S") - datetime(2024, 1, 1)).total_seconds() / 3600)
                self.assertLess(index + horizon, boundary)

    def test_window_selection(self):
        result = self.split(start=date(2), end=date(16))
        self.assertEqual(result["train"][0]["date"], date(2))
        self.assertEqual(result["test"][-1]["date"], date(15))

    def test_copy_isolation(self):
        rows = fixtures()
        before = copy.deepcopy(rows)
        result = self.split(rows)
        self.assertEqual(rows, before)
        result["train"][0]["extras"]["value"].append(100)
        self.assertEqual(rows, before)

    def test_future_values_cannot_change_earlier_output(self):
        rows = fixtures()
        before = self.split(rows)
        for row in rows:
            if row["date"] >= date(12):
                row["close"] = -999
        after = self.split(rows)
        self.assertEqual(before["train"], after["train"])
        self.assertEqual(before["validation"], after["validation"])

    def test_duplicate_and_unbalanced(self):
        for rows in (fixtures()+[fixtures()[0]], fixtures()[1:]):
            with self.assertRaises(ValueError):
                self.split(rows)

    def test_invalid_record_and_date(self):
        for row in ({}, {"date": date(0), "tic": ""}, {"date": "2024-01-01", "tic": "X"},
                    {"date": "2024-1-01 00:00:00", "tic": "X"},
                    {"date": "2024-01-01T00:00:00+03:00", "tic": "X"}, None):
            with self.subTest(row=row), self.assertRaises(ValueError):
                self.split([row])

    def test_bad_boundaries_and_options(self):
        for options in ({"validation_start": date(12)}, {"start": date(6)},
                        {"end": date(12)}, {"label_horizon_steps": -1},
                        {"embargo_steps": True}, {"embargo_steps": 1.5}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.split(**options)

    def test_empty_partitions_fail(self):
        for options in ({"label_horizon_steps": 6}, {"embargo_steps": 6},
                        {"validation_start": date(0)}, {"test_start": date(18)}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.split(**options)
        with self.assertRaises(ValueError):
            self.split([])

    def test_no_io_or_network(self):
        with patch("builtins.open", side_effect=AssertionError("IO forbidden")), \
                patch("socket.socket", side_effect=AssertionError("network forbidden")):
            self.assertEqual(len(self.split()["test"]), 12)


if __name__ == "__main__":
    unittest.main()

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
from stable_baselines3 import PPO
from stable_baselines3.common.env_checker import check_env

from causal_indicators import add_indicators
from online_research_pipeline import LearningHistory, SnapshotStream, prepare, shadow_poll
from research_environment import CandleEnv, PaperAccount, TrainScaler, evaluate
from test_causal_indicators import rows

H = 3600000


def features():
    return [r for r in add_indicators(rows(range(100, 300)), as_of_ms=200*H) if r["features_ready"]]


class ResearchTests(unittest.TestCase):
    def test_small_ppo_training_and_saved_model(self):
        import torch
        torch.set_num_threads(1)
        data = features()[:50]
        scaler = TrainScaler().fit(data)
        model = PPO("MlpPolicy", CandleEnv(data, scaler), seed=42, n_steps=32,
                    batch_size=16, n_epochs=1, policy_kwargs={"net_arch": [8, 8]}, verbose=0)
        model.learn(total_timesteps=64)
        obs = CandleEnv(data, scaler).reset()[0]
        expected = model.predict(obs, deterministic=True)[0]
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory)/"model")
            model.save(path)
            restored = PPO.load(path)
            self.assertEqual(expected, restored.predict(obs, deterministic=True)[0])

    def test_learning_checkpoints_keep_test_untouched(self):
        import torch
        torch.set_num_threads(1)
        data = features()[:40]
        scaler = TrainScaler().fit(data)
        # No test partition supplied: callback must use only train/validation.
        callback = LearningHistory({"train": data, "validation": data}, scaler, every=32)
        model = PPO("MlpPolicy", CandleEnv(data, scaler), seed=42, n_steps=32,
                    batch_size=16, n_epochs=1, policy_kwargs={"net_arch": [8, 8]}, verbose=0)
        with patch("online_research_pipeline.evaluate", wraps=evaluate) as evaluator:
            model.learn(total_timesteps=64, callback=callback)
        self.assertEqual([p["step"] for p in callback.points], [0, 32, 64])
        self.assertEqual(evaluator.call_count, 6)
        self.assertEqual(len(callback.episodes), 1)
        self.assertTrue(np.isfinite(callback.episodes[0]["reward"]))
        self.assertNotIn("test", callback.points[-1])

    def test_decision_trace_next_open_and_terminal_fills(self):
        data = features()[:3]
        scaler = TrainScaler().fit(data)
        result = evaluate(data, scaler, lambda obs, row: 1, include_trace=True)
        decisions = result["decisions"]
        self.assertEqual(len(decisions), 2)
        self.assertEqual(decisions[0]["signal_date"], data[0]["date"])
        self.assertEqual(decisions[0]["execution_date"], data[1]["date"])
        self.assertEqual([d["fills"] for d in decisions], [1, 1])
        self.assertTrue(decisions[-1]["terminal_liquidation"])
        self.assertEqual(result["trades"], sum(d["fills"] for d in decisions))
        self.assertNotIn("decisions", evaluate(data, scaler, lambda obs, row: 0))

    def test_environment_contract(self):
        data = features()
        scaler = TrainScaler().fit(data)
        env = CandleEnv(data, scaler)
        check_env(env, warn=True)
        obs, _ = env.reset(seed=42)
        self.assertTrue(env.observation_space.contains(obs))

    def test_next_open_and_costs(self):
        data = features()[:2]
        data[1].update(open=200., close=220.)
        scaler = TrainScaler().fit(data)
        env = CandleEnv(data, scaler, fee=.01, slippage=.02)
        env.reset()
        _, reward, done, _, info = env.step(1)
        qty = 10000/(200*1.02*1.01)
        expected = qty*220*.98*.99
        self.assertAlmostEqual(info["equity"], expected)
        self.assertAlmostEqual(reward, (expected-10000)/10000)
        self.assertTrue(done)
        self.assertEqual(info["trades"], 2)
        with self.assertRaises(RuntimeError):
            env.step(1)

    def test_cash_baseline_and_terminal(self):
        data = features()
        scaler = TrainScaler().fit(data)
        result = evaluate(data, scaler, lambda obs, row: 0)
        self.assertEqual(result["return_pct"], 0.)
        self.assertEqual(result["max_drawdown_pct"], 0.)
        self.assertEqual(result["trades"], 0)
        self.assertEqual(result["transitions"], len(data)-1)

    def test_observation_does_not_see_future_prices(self):
        data = features()
        scaler = TrainScaler().fit(data[:30])
        changed = copy.deepcopy(data)
        changed[1]["open"] *= 10
        env1, env2 = CandleEnv(data, scaler), CandleEnv(changed, scaler)
        np.testing.assert_array_equal(env1.reset()[0], env2.reset()[0])

    def test_scaler_is_not_refitted_on_validation(self):
        scaler = TrainScaler().fit(features()[:30])
        mean, scale = scaler.mean.copy(), scaler.scale.copy()
        evaluate(features()[30:], scaler, lambda obs, row: 0)
        np.testing.assert_array_equal(mean, scaler.mean)
        np.testing.assert_array_equal(scale, scaler.scale)

    def test_paper_account_idempotent_target(self):
        account = PaperAccount(fee=0, slippage=0)
        account.execute(1, 100)
        account.execute(1, 120)
        self.assertEqual(account.trades, 1)
        account.execute(0, 120)
        self.assertEqual(account.cash, 12000)
        self.assertEqual(account.qty, 0)

    def test_stream_duplicate_and_history_change(self):
        snapshot = {"records": rows()[:3], "server_time_ms": 3*H}
        stream = SnapshotStream("BTCUSDT", 3)
        with patch("online_research_pipeline.fetch_latest_records", return_value=snapshot):
            self.assertEqual(len(stream.poll()[1]), 3)
            self.assertEqual(stream.poll()[1], [])
        changed = copy.deepcopy(snapshot)
        changed["records"][0]["close"] += 1
        with patch("online_research_pipeline.fetch_latest_records", return_value=changed), self.assertRaises(ValueError):
            stream.poll()

    def test_stream_backward_clock_and_disconnect(self):
        snapshot = {"records": rows()[:3], "server_time_ms": 3*H}
        stream = SnapshotStream("BTCUSDT", 3)
        with patch("online_research_pipeline.fetch_latest_records", return_value=snapshot):
            stream.poll()
        for next_snapshot in ({"records": rows()[:3], "server_time_ms": 2*H},
                              {"records": rows()[5:8], "server_time_ms": 8*H}):
            with patch("online_research_pipeline.fetch_latest_records", return_value=next_snapshot), self.assertRaises(ValueError):
                stream.poll()

    def test_prepare_and_split_counts(self):
        snapshot = {"records": rows(range(100, 400)), "server_time_ms": 300*H}
        parts = prepare(snapshot)
        self.assertLess(parts["train"][-1]["date"], parts["validation"][0]["date"])
        self.assertLess(parts["validation"][-1]["date"], parts["test"][0]["date"])
        self.assertTrue(all(r["features_ready"] for r in parts["test"]))
        with self.assertRaises(ValueError):
            prepare({"records": snapshot["records"] + rows(range(100, 400), "ETHUSDT"),
                     "server_time_ms": 300*H})

    def test_shadow_connection_failures_are_bounded(self):
        stream = SnapshotStream("BTCUSDT", 200)
        stream.records = {r["date"]: r for r in rows(range(100, 300))}
        stream.last_server_time = 200*H
        model = Mock()
        model.predict.return_value = (np.array(0), None)
        with patch.object(stream, "poll", side_effect=RuntimeError("connection failed")) as poll, patch("online_research_pipeline.time.sleep"):
            result = shadow_poll(stream, model, TrainScaler().fit(features()), polls=10)
        self.assertEqual(poll.call_count, 3)
        self.assertEqual(result["simulated_trades"], 0)

    def test_shadow_no_new_candle_does_not_fill(self):
        raw = rows(range(100, 300))
        snapshot = {"records": raw, "server_time_ms": 200*H}
        stream = SnapshotStream("BTCUSDT", 200)
        with patch("online_research_pipeline.fetch_latest_records", return_value=snapshot):
            stream.poll()
        model = Mock()
        model.predict.return_value = (np.array(1), None)
        scaler = TrainScaler().fit(features())
        with patch.object(stream, "poll", return_value=(snapshot, [])), patch("online_research_pipeline.time.sleep"):
            result = shadow_poll(stream, model, scaler, polls=2)
        self.assertEqual(result["simulated_trades"], 0)
        self.assertEqual(result["events"][-1]["event"], "no_new_closed_candle")

    def test_shadow_rate_limit_stops(self):
        stream = SnapshotStream("BTCUSDT", 200)
        stream.records = {r["date"]: r for r in rows(range(100, 300))}
        stream.last_server_time = 200*H
        model = Mock()
        model.predict.return_value = (np.array(0), None)
        with patch.object(stream, "poll", side_effect=RuntimeError("rate limited HTTP 429")) as poll, patch("online_research_pipeline.time.sleep"):
            result = shadow_poll(stream, model, TrainScaler().fit(features()), polls=10)
        self.assertEqual(poll.call_count, 1)
        self.assertEqual(result["events"][-1]["event"], "connection_error")

    def test_shadow_fills_prior_decision_at_new_open(self):
        raw = rows(range(100, 300))
        new = rows(range(100, 301))[-1]
        stream = SnapshotStream("BTCUSDT", 200)
        stream.records = {r["date"]: r for r in raw}
        stream.last_server_time = 200*H
        def poll():
            stream.records[new["date"]] = new
            return {"server_time_ms": 201*H}, [new]
        model = Mock()
        model.predict.return_value = (np.array(1), None)
        with patch.object(stream, "poll", side_effect=poll), patch("online_research_pipeline.time.sleep"):
            result = shadow_poll(stream, model, TrainScaler().fit(features()), polls=1)
        self.assertEqual(result["simulated_trades"], 1)
        self.assertEqual(result["events"][-1]["event"], "simulated_bar")


if __name__ == "__main__":
    unittest.main()

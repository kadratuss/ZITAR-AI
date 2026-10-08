"""Opt-in bounded online research; never touches application databases/services."""

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from stable_baselines3 import PPO
from stable_baselines3.common.env_checker import check_env
from stable_baselines3.common.callbacks import BaseCallback

from causal_indicators import add_indicators
from chronological_split import split_records
from online_finrl_data import fetch_latest_records
from research_environment import CandleEnv, PaperAccount, TrainScaler, evaluate


class LearningHistory(BaseCallback):
    """Evaluate train/validation after updates; never inspect test checkpoints."""
    def __init__(self, parts, scaler, every=512):
        super().__init__()
        self.parts, self.scaler, self.every = parts, scaler, every
        self.points, self.episodes = [], []
        self.episode_reward = 0.

    def _on_step(self):
        self.episode_reward += float(self.locals["rewards"][0])
        if self.locals["dones"][0]:
            self.episodes.append({"step": self.num_timesteps, "reward": self.episode_reward})
            self.episode_reward = 0.
        return True

    def record(self):
        step = self.model.num_timesteps
        if self.points and self.points[-1]["step"] == step:
            return
        policy = lambda obs, row: int(self.model.predict(obs, deterministic=True)[0])
        point = {"step": step}
        for name in ("train", "validation"):
            point[name] = evaluate(self.parts[name], self.scaler, policy)
        self.points.append(point)

    def _on_rollout_start(self):
        if self.model.num_timesteps % self.every == 0:
            self.record()

    def _on_training_end(self):
        self.record()


class SnapshotStream:
    """Bounded polling state: overlap checks, deduplication and gap rejection."""
    def __init__(self, symbol, count=1000):
        self.symbol, self.count = symbol, count
        self.records = {}
        self.last_server_time = None

    def poll(self):
        snapshot = fetch_latest_records([self.symbol], count=self.count)
        clock = snapshot["server_time_ms"]
        if self.last_server_time is not None and clock < self.last_server_time:
            raise ValueError("server clock moved backwards")
        incoming = snapshot["records"]
        if self.records and incoming[0]["date"] > max(self.records):
            raise ValueError("disconnected history; restart with a new research snapshot")
        for row in incoming:
            old = self.records.get(row["date"])
            if old is not None and old != row:
                raise ValueError("historical candle changed; stop research")
        fresh = [r for r in incoming if r["date"] not in self.records]
        self.records.update({r["date"]: r for r in incoming})
        self.last_server_time = clock
        return snapshot, fresh


def prepare(snapshot):
    if len({r["tic"] for r in snapshot["records"]}) != 1:
        raise ValueError("research one explicitly selected symbol at a time")
    featured = add_indicators(snapshot["records"], as_of_ms=snapshot["server_time_ms"])
    closes = []
    ready = []
    for row in featured:
        closes.append(row["close"])
        row["sma50"] = sum(closes[-50:])/50 if len(closes) >= 50 else None
        if row["features_ready"] and row["sma50"] is not None:
            ready.append(row)
    if len(ready) < 150:
        raise ValueError("at least 150 fully featured closed candles required")
    n = len(ready)
    parts = split_records(ready, validation_start=ready[int(n*.6)]["date"],
                          test_start=ready[int(n*.8)]["date"],
                          label_horizon_steps=1, embargo_steps=1)
    return parts


def shadow_poll(stream, model, scaler, polls=2, poll_seconds=1):
    """Short live paper observation. Pending decisions fill only on newer bars.

    Every fresh closed bar replays a prior decision at that bar's actual open,
    then values at close. Such fills are simulations learned after close.
    Without a new closed bar, no fill or performance claim is made.
    """
    account = PaperAccount()
    rows = sorted(stream.records.values(), key=lambda r: r["date"])
    first = add_indicators(rows, as_of_ms=stream.last_server_time)[-1]
    def decide(row):
        equity = account.equity(row["close"])
        obs = np.concatenate((scaler.transform(row), np.asarray(
            [account.cash/equity, account.qty*row["close"]/equity], dtype=np.float32)))
        return int(model.predict(obs, deterministic=True)[0])
    pending = decide(first)
    events = [{"date": first["date"], "event": "pending_decision", "action": pending}]
    failures = 0
    for _ in range(polls):
        time.sleep(poll_seconds)
        try:
            snapshot, fresh = stream.poll()
        except RuntimeError as exc:
            events.append({"event": "connection_error", "message": str(exc)})
            failures += 1
            if "rate limited" in str(exc) or failures >= 3:
                break
            continue
        failures = 0
        if not fresh:
            events.append({"event": "no_new_closed_candle"})
            continue
        features = add_indicators(sorted(stream.records.values(), key=lambda r: r["date"]),
                                  as_of_ms=snapshot["server_time_ms"])
        feature_map = {r["date"]: r for r in features}
        for row in fresh:
            account.execute(pending, row["open"])
            equity = account.equity(row["close"])
            pending = decide(feature_map[row["date"]])
            events.append({"event": "simulated_bar", "date": row["date"],
                           "equity": equity, "next_action": pending})
    return {"events": events, "simulated_trades": account.trades,
            "cash": account.cash, "quantity": account.qty,
            "mode": "bounded shadow; no broker; no real fills"}


def run(symbol="BTCUSDT", count=1000, timesteps=2048, seed=42, paper_polls=2, poll_seconds=1):
    if type(timesteps) is not int or not 128 <= timesteps <= 1000000:
        raise ValueError("timesteps must be 128..1000000")
    if type(paper_polls) is not int or not 0 <= paper_polls <= 60 or not 1 <= poll_seconds <= 3600:
        raise ValueError("paper polls must be 0..60; poll seconds 1..3600")
    import torch
    torch.set_num_threads(1)
    stream = SnapshotStream(symbol, count)
    snapshot, _ = stream.poll()
    parts = prepare(snapshot)
    scaler = TrainScaler().fit(parts["train"])
    env = CandleEnv(parts["train"], scaler)
    check_env(env, warn=True)
    model = PPO("MlpPolicy", env, seed=seed, device="cpu", n_steps=128,
                batch_size=64, n_epochs=4, verbose=0,
                policy_kwargs={"net_arch": [32, 32]})
    history = LearningHistory(parts, scaler)
    model.learn(total_timesteps=timesteps, callback=history)
    policy = lambda obs, row: int(model.predict(obs, deterministic=True)[0])
    results = {}
    for name in ("validation", "test"):
        rows = parts[name]
        results[name] = {
            "ppo": evaluate(rows, scaler, policy, include_trace=True),
            "buy_hold": evaluate(rows, scaler, lambda obs, row: 1),
            "sma20_50": evaluate(rows, scaler, lambda obs, row: int(row["sma"] > row["sma50"])),
            "cash": evaluate(rows, scaler, lambda obs, row: 0)}
        results[name]["ppo_double_costs"] = evaluate(rows, scaler, policy, fee=.002, slippage=.002)
    shadow = shadow_poll(stream, model, scaler, paper_polls, poll_seconds) if paper_polls else None
    serialized = json.dumps(snapshot, sort_keys=True, allow_nan=False).encode()
    report = {"mode": "research only", "symbol": symbol, "seed": seed,
            "interval": "1h", "actions": {"0": "cash / sell existing position", "1": "long / buy or hold"},
            "learning_history": {"checkpoints": history.points, "episodes": history.episodes,
                                 "test_policy": "evaluated only after training; no checkpoint selection"},
            "requested_timesteps": timesteps, "actual_timesteps": model.num_timesteps,
            "snapshot_sha256": hashlib.sha256(serialized).hexdigest(),
            "snapshot": snapshot, "split": parts["metadata"],
            "scaler_fit": "train only", "fee_per_side": .001, "slippage_per_side": .001,
            "execution": "signal at close, fill next open, terminal liquidation",
            "results": results, "shadow": shadow,
            "limits": "short initial experiment; not evidence of profitability; test is held out; no hyperparameter selection"}
    return report, model, scaler


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--timesteps", type=int, default=2048)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--paper-polls", type=int, default=2)
    parser.add_argument("--poll-seconds", type=float, default=1)
    parser.add_argument("--output-dir", required=True, help="new dedicated research output folder")
    args = parser.parse_args(argv)
    output = Path(args.output_dir).resolve()
    # Exclusive creation prevents overwriting any existing research or app data.
    output.mkdir(parents=True, exist_ok=False)
    report, model, scaler = run(args.symbol, args.count, args.timesteps, args.seed,
                               args.paper_polls, args.poll_seconds)
    snapshot = report.pop("snapshot")
    (output/"snapshot.json").write_text(json.dumps(snapshot, indent=2, allow_nan=False), encoding="utf-8")
    (output/"report.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    model.save(str(output/"ppo_model"))
    (output/"scaler.json").write_text(json.dumps({"mean": scaler.mean.tolist(),
                                                 "scale": scaler.scale.tolist()}), encoding="utf-8")
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()

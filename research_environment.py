"""Isolated long/flat Gymnasium environment with next-open simulated fills."""

import gymnasium as gym
import numpy as np

FEATURE_KEYS = ("close", "sma", "ema", "rsi", "macd", "macd_signal", "macd_hist", "atr")


class TrainScaler:
    def fit(self, records):
        values = np.asarray([[r[k] for k in FEATURE_KEYS] for r in records], dtype=np.float64)
        if len(values) < 2 or not np.isfinite(values).all():
            raise ValueError("finite training features required")
        self.mean = values.mean(axis=0)
        self.scale = values.std(axis=0)
        self.scale[self.scale == 0] = 1
        return self

    def transform(self, row):
        values = (np.asarray([row[k] for k in FEATURE_KEYS]) - self.mean) / self.scale
        if not np.isfinite(values).all():
            raise ValueError("nonfinite features")
        return np.clip(values, -10, 10).astype(np.float32)


class PaperAccount:
    """In-memory simulator; contains no broker or persistence capability."""
    def __init__(self, initial=10000., fee=.001, slippage=.001):
        if not np.isfinite([initial, fee, slippage]).all() or initial <= 0 or not 0 <= fee < 1 or not 0 <= slippage < 1:
            raise ValueError("invalid cost or cash")
        self.initial, self.cash, self.qty = initial, initial, 0.
        self.fee, self.slippage, self.trades = fee, slippage, 0

    def execute(self, action, price):
        if action not in (0, 1) or not np.isfinite(price) or price <= 0:
            raise ValueError("invalid action/price")
        if action == 1 and self.qty == 0:
            self.qty = self.cash / ((price * (1+self.slippage)) * (1+self.fee))
            self.cash = 0.
            self.trades += 1
        elif action == 0 and self.qty:
            self.cash += self.qty * price * (1-self.slippage) * (1-self.fee)
            self.qty = 0.
            self.trades += 1

    def equity(self, price):
        return self.cash + self.qty * price


class CandleEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, records, scaler, fee=.001, slippage=.001):
        super().__init__()
        if len(records) < 2 or len({r["tic"] for r in records}) != 1:
            raise ValueError("at least two rows of one symbol required")
        if any(b["date"] <= a["date"] for a, b in zip(records, records[1:])):
            raise ValueError("records must be chronological")
        self.records, self.scaler = records, scaler
        self.fee, self.slippage = fee, slippage
        self.action_space = gym.spaces.Discrete(2)
        self.observation_space = gym.spaces.Box(-10, 10, shape=(len(FEATURE_KEYS)+2,), dtype=np.float32)
        self.account = None
        self.done = True

    def _obs(self):
        row = self.records[self.index]
        equity = self.account.equity(row["close"])
        state = [self.account.cash/equity, self.account.qty*row["close"]/equity]
        return np.concatenate((self.scaler.transform(row), np.asarray(state, dtype=np.float32)))

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self.index, self.done = 0, False
        self.account = PaperAccount(fee=self.fee, slippage=self.slippage)
        self.curve = [self.account.initial]
        return self._obs(), {}

    def step(self, action):
        if self.done:
            raise RuntimeError("reset required after episode end")
        if not self.action_space.contains(action):
            raise ValueError("invalid discrete action")
        previous = self.curve[-1]
        self.index += 1
        row = self.records[self.index]
        # Observation was at candle i close; execution is at i+1 open.
        self.account.execute(int(action), row["open"])
        self.done = self.index == len(self.records)-1
        if self.done:
            self.account.execute(0, row["close"])
        equity = self.account.equity(row["close"])
        self.curve.append(equity)
        reward = (equity-previous)/self.account.initial
        return self._obs(), reward, self.done, False, {"equity": equity, "trades": self.account.trades}


def evaluate(records, scaler, policy, fee=.001, slippage=.001, include_trace=False):
    env = CandleEnv(records, scaler, fee, slippage)
    obs, _ = env.reset()
    done = False
    decisions = []
    while not done:
        action = int(policy(obs, records[env.index]))
        signal = records[env.index]
        before = env.account.trades
        obs, _, done, _, info = env.step(action)
        if include_trace:
            decisions.append({"signal_date": signal["date"], "execution_date": records[env.index]["date"],
                              "action": action, "target": "long" if action else "cash",
                              "fills": info["trades"]-before, "equity": info["equity"],
                              "terminal_liquidation": done})
    curve = np.asarray(env.curve)
    peaks = np.maximum.accumulate(curve)
    result = {"return_pct": float((curve[-1]/curve[0]-1)*100),
            "max_drawdown_pct": float(np.max((peaks-curve)/peaks)*100),
            "final_equity": float(curve[-1]), "trades": info["trades"],
            "transitions": len(records)-1}
    if include_trace:
        result["decisions"] = decisions
    return result

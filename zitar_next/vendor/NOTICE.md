# FinRL-X strategy contract

finrl_base_strategy.py is an unmodified copy of src/strategies/base_strategy.py
from AI4Finance-Foundation/FinRL-Trading, inspected at commit
4409abe925c904e570be78ebfb5e77ac3491dff8. License: Apache-2.0 (included).
Source: https://github.com/AI4Finance-Foundation/FinRL-Trading/blob/4409abe925c904e570be78ebfb5e77ac3491dff8/src/strategies/base_strategy.py

Only its BaseStrategy, StrategyConfig and StrategyResult contract is used.
No upstream data collector, paid API, Alpaca executor, CLI or broker modules
are installed/imported. This is strategy-interface integration, not the full
upstream platform or evidence its stock backtest supports 3x crypto margin.

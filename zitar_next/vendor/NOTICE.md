# FinRL-X strategy contract

finrl_base_strategy.py is an unmodified copy of src/strategies/base_strategy.py
from AI4Finance-Foundation/FinRL-Trading, inspected at commit
4409abe925c904e570be78ebfb5e77ac3491dff8. License: Apache-2.0 (included).
Source: https://github.com/AI4Finance-Foundation/FinRL-Trading/blob/4409abe925c904e570be78ebfb5e77ac3491dff8/src/strategies/base_strategy.py

finrl_backtest_engine.py is derived from src/backtest/backtest_engine.py at the
same commit and under the same license. Modifications: remove provider import,
project_root / sys.path mutation and print; replace fetch_price_data with an
explicit offline rejection; remove the example __main__ CLI. The backtest class,
configuration and result definitions remain upstream code. Runtime subclasses in
finrl_pipeline.py adapt fees, disable stock annualization and provide local data.

Source: https://github.com/AI4Finance-Foundation/FinRL-Trading/blob/4409abe925c904e570be78ebfb5e77ac3491dff8/src/backtest/backtest_engine.py

No upstream broker, paid provider, web app or main entrypoint is imported.
The research dependency bt brings free yfinance transitively; our pipeline never
calls its download functionality. Tests reject network connects during backtests.


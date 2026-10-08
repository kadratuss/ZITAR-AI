"""FinRL-X BaseStrategy contract only; no upstream broker/data startup."""
import pandas as pd
from zitar_next.vendor.finrl_base_strategy import BaseStrategy,StrategyConfig,StrategyResult


class ZitarWeightStrategy(BaseStrategy):
    def __init__(self,market):
        if market not in ('spot','futures'):
            raise ValueError('invalid market')
        super().__init__(StrategyConfig(name='ZITAR_NEXT_'+market.upper()))
        self.market = market

    def generate_weights(self,data,target_date=None):
        # One explicit target timestamp/symbol. No implicit daily expansion.
        symbol,date,action = data['symbol'],data['date'],data['action']
        choices = (0,1) if self.market=='spot' else (0,1,2)
        if type(action) is not int or action not in choices or (target_date is not None and target_date!=date):
            raise ValueError('target date/action mismatch')
        # Exposure intent at entry: futures 10% isolated collateral x 3 leverage.
        weight = (0.,1.)[action] if self.market=='spot' else (0.,.3,-.3)[action]
        return StrategyResult(strategy_name=self.config.name,
                              weights=pd.DataFrame([dict(date=date,tic=symbol,weight=weight)]),
                              metadata=dict(interval='1h',market=self.market,real_orders=False,paper_only=True,
                                            scope='entry exposure intent; not margin/liquidation execution parity',
                                            upstream_commit='4409abe925c904e570be78ebfb5e77ac3491dff8'))

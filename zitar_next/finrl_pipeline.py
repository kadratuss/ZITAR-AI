"""FinRL-X research backtests from causal ZITAR decisions; no broker imports."""
import hashlib
import json
import re
from pathlib import Path
import bt
import numpy as np
import pandas as pd
from zitar_next.finrl_bridge import ZitarWeightStrategy
from zitar_next.vendor.finrl_backtest_engine import BacktestConfig, BacktestEngine
from zitar_next.store import atomic, digest, workspace

UPSTREAM = '4409abe925c904e570be78ebfb5e77ac3491dff8'


def backtest(market, rows, decisions, authoritative):
    """Secondary weight-rebalanced comparison, never isolated-margin evidence."""
    if market not in ('spot','futures') or len(rows)<2:
        raise ValueError('market and at least two bars required')
    symbol=rows[0]['tic']
    if len({r['tic'] for r in rows})!=1 or len(decisions)!=len(rows)-1:
        raise ValueError('one symbol and complete causal trace required')
    dates=pd.to_datetime([r['date'] for r in rows])
    if dates.has_duplicates or not (dates.to_series().diff().dropna()==pd.Timedelta(hours=1)).all():
        raise ValueError('continuous hourly bars required')
    prices=[float(rows[0]['close'])]+[float(r['open']) for r in rows[1:]]+[float(rows[-1]['close'])]
    if not np.isfinite(prices).all() or min(prices)<=0:
        raise ValueError('finite positive prices required')
    strategy=ZitarWeightStrategy(market)
    exported=[]
    for index,decision in enumerate(decisions):
        if decision['signal_date']!=rows[index]['date'] or decision['execution_date']!=rows[index+1]['date']:
            raise ValueError('next-open causal trace mismatch')
        result=strategy.generate_weights(dict(symbol=symbol,date=decision['signal_date'],action=decision['action']))
        exported.append(dict(signal_date=decision['signal_date'],execution_date=decision['execution_date'],
                             weight=float(result.weights.iloc[0]['weight'])))
    index=dates.append(pd.DatetimeIndex([dates[-1]+pd.Timedelta(hours=1)]))
    cash_price=min(prices)/2
    price_frame=pd.DataFrame({symbol:prices,'ZITAR_CASH':cash_price},index=index)
    # A constant-price cash leg preserves partial and negative exposure through
    # upstream normalization: long .3 + cash .7; short -.3 + cash 1.3.
    exposures=[0.]+[r['weight'] for r in exported]+[0.]
    weights=pd.DataFrame({symbol:exposures,'ZITAR_CASH':[1.-w for w in exposures]},index=index)
    config=BacktestConfig(start_date=str(index[0]),end_date=str(index[-1]),initial_capital=10000.,
                          transaction_cost=0.,benchmark_tickers=[],integer_positions=False)
    class OfflineEngine(BacktestEngine):
        def _build_bt_backtest(self,strategy,price_data_wide,price_data_long):
            # Cash transfers are free; fees apply only to the risky asset.
            fee=.001 if market=='spot' else .0005
            return bt.Backtest(strategy,price_data_wide,initial_capital=10000.,integer_positions=False,
                               commissions=lambda q,p:abs(q)*p*fee if p!=cash_price else 0.)
        def _calculate_comprehensive_metrics(self,result,returns):
            # Upstream assumes 252 daily observations. Hourly crypto metrics
            # below use the actual equity curve without daily annualization.
            return {}
    result=OfflineEngine(config).run_backtest(strategy.config.name,price_frame,weights)
    equity=result.portfolio_values.to_numpy(dtype=float)
    if not np.isfinite(equity).all() or equity[0]<=0:
        raise ValueError('nonfinite upstream result')
    peak=np.maximum.accumulate(equity)
    metric=dict(return_pct=float((equity[-1]/equity[0]-1)*100),
                max_drawdown_pct=float(np.max((peak-equity)/peak)*100),final_equity=float(equity[-1]))
    return dict(schema='ZITAR_FINRLX_RESEARCH_V1',upstream_commit=UPSTREAM,
                strategy=strategy.config.name,market=market,symbol=symbol,interval='1h',
                backend='FinRL-X BacktestEngine / bt',status='COMPLETED',real_orders=False,
                authoritative_net_metrics={k:v for k,v in authoritative.items() if k!='decisions'},
                weight_backtest=metric,weights=exported,
                equity=[dict(date=str(d),equity=float(v)) for d,v in result.portfolio_values.items()],
                assumptions=['Weight backtest rebalances each bar; authoritative simulator holds discrete positions.',
                             'Weight backtest uses next-open prices and terminal close; no intrabar mark or funding.',
                             'Fees on risky exposure only; slippage/funding/liquidation remain in authoritative net metrics.',
                             'Isolated 3x futures eligibility uses ZITAR FuturesEnv, never the upstream stock simulator.',
                             'No daily stock annualization; cash leg prevents short/partial exposure normalization.'])


def replay(root, run):
    """Read immutable trained artifacts, produce a separate research report."""
    root=workspace(root)
    if not re.fullmatch(r'(spot|futures)-[a-f0-9]{32}',run):
        raise ValueError('invalid run')
    folder=root/'runs'/run
    if folder.is_symlink() or folder.resolve().parent!=(root/'runs').resolve():
        raise ValueError('invalid run path')
    for name in ('report.json','snapshot.json','scaler.json'):
        if (folder/name).is_symlink():
            raise ValueError('symlink rejected')
    report=json.loads((folder/'report.json').read_text(encoding='utf-8'))
    snapshot=json.loads((folder/'snapshot.json').read_text(encoding='utf-8'))
    scaler_data=json.loads((folder/'scaler.json').read_text(encoding='utf-8'))
    if digest(snapshot)!=report['snapshot_sha256'] or digest(scaler_data)!=report['scaler_sha256']:
        raise ValueError('snapshot/scaler hash mismatch')
    from stable_baselines3 import PPO
    from online_research_pipeline import prepare
    from research_environment import TrainScaler
    from zitar_next.worker import env_for
    from zitar_next.futures import evaluate
    from zitar_next.paper import vote
    models=[]
    for seed in report['seed_results']:
        path=folder/('ppo-'+str(seed['seed'])+'.zip')
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=seed['model_sha256']:
            raise ValueError('model hash mismatch')
        models.append(PPO.load(str(path),device='cpu'))
    scaler=TrainScaler();scaler.mean=np.asarray(scaler_data['mean']);scaler.scale=np.asarray(scaler_data['scale'])
    rows=prepare(snapshot)['test']
    metric=evaluate(env_for(report['market'],rows,scaler),lambda obs,row:vote(models,obs),trace=True)
    result=backtest(report['market'],rows,metric['decisions'],metric)
    result.update(run=run,snapshot_sha256=report['snapshot_sha256'],proposal_id=report['proposal_id'],
                  eligible=report['eligible'],issues=report['issues'])
    output=root/'finrlx_reports';output.mkdir(exist_ok=True)
    if output.is_symlink():
        raise ValueError('output symlink rejected')
    atomic(output/(run+'.json'),result)
    return result


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',required=True)
    parser.add_argument('--run',required=True)
    args=parser.parse_args()
    result=replay(args.root,args.run)
    print(json.dumps({k:result[k] for k in ('status','market','backend','weight_backtest','authoritative_net_metrics','eligible')},allow_nan=False))


if __name__=='__main__':
    main()


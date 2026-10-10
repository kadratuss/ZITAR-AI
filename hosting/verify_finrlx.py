"""Read-only replay of existing trained decisions through the FinRL-X adapter."""
import json
import socket
from pathlib import Path
from unittest.mock import patch
from zitar_next.finrl_pipeline import backtest,load_run
from online_research_pipeline import prepare

def main():
    root=Path('research_artifacts/next-release')
    results=[]
    for run in ('spot-45deaf7b6d6a4b6c9935bba4971f2169','futures-1e82074dba634656afcd5caf056ef545'):
        with patch.object(socket.socket,'connect',side_effect=AssertionError('network forbidden')):
            report,snapshot,scaler,models=load_run(root,run)
            rows=prepare(snapshot)['test']
            metric=report['ensemble']['test']
            result=backtest(report['market'],rows,metric['decisions'],metric)
            saved=json.loads((root/'runs'/run/'finrlx.json').read_text())
            for key,value in result['weight_backtest'].items():
                if abs(value-saved['weight_backtest'][key])>1e-8:
                    raise AssertionError('saved FinRL-X result mismatch: '+key)
            results.append(dict(run=run,models_verified=len(models),rows=len(rows),backend=result['backend'],
                                upstream_commit=result['upstream_commit'],weight_backtest=result['weight_backtest'],
                                saved_result_matches=True,network_disabled=True,real_orders=False))
    print(json.dumps(results,indent=2))

if __name__=='__main__':main()

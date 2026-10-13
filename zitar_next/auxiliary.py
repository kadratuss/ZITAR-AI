"""Guarded Linux counterparts of explicitly inventoried Windows paper tasks."""
import argparse
import subprocess
import sys
from pathlib import Path
from zitar_next.hosting import check
TASKS={'forward':'forward_hourly_runner_v1.py','history':'historical_data.py',
       'intelligence':'zitar_futures_temporal_intelligence_v1.py','liquidity':'zitar_liquidity_observer_v1.py'}
def main():
    p=argparse.ArgumentParser();p.add_argument('task',choices=TASKS);a=p.parse_args()
    base=Path('/srv/zitar/runtime');check(base,'/srv/zitar/data/next')
    from zitar_paper_supervisor_v1 import FileLock
    lock=FileLock(base/('zitar_aux_'+a.task+'.lock'))
    if not lock.acquire():raise RuntimeError('auxiliary task already running')
    try:subprocess.run([sys.executable,'-B',str(base/TASKS[a.task])],cwd=base,check=True,timeout=1800)
    finally:lock.close()
if __name__=='__main__':main()

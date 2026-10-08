"""Explicit operator reset. Prepare is read-only; commit requires stopped writers."""
import argparse, copy, hashlib, json, os, shutil, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from decimal import Decimal

BASE = Path(__file__).resolve().parent
def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def encoded(v): return (json.dumps(v, ensure_ascii=False, indent=2)+'\n').encode('utf-8')
def sha(raw): return hashlib.sha256(raw).hexdigest()

def prepare(base, moment):
    from zitar_master_portfolio_v1 import default_state
    from zitar_candidate_runtime_v1 import Candidate
    from zitar_comparison_runtime_v1 import Comparison
    from zitar_futures_paper_engine_v1 import fresh, POLICY
    from zitar_futures_shared_v1 import ensure_book
    from zitar_strategy_lab_v1 import ensure_experiment
    from zitar_trigger_lab_v2 import ensure_trigger
    from zitar_discovery_futures_v1 import ensure
    from zitar_discovery_spot_v1 import fresh as spot_fresh
    stamp=moment.isoformat(); ms=int(moment.timestamp()*1000); changes={}; counts={}
    def put(name, value): changes[name]=encoded(value)
    master=default_state(); old=read(base/'zitar_master_portfolio_v1.json')
    master.update(created_utc=stamp,last_updated_utc=stamp,processed_event_ids=[])
    master['rules']=copy.deepcopy(old['rules'])
    put('zitar_master_portfolio_v1.json',master); counts['Master']=1
    # Reset source accounts and their logs as a single transaction with consumers.
    for version in ('v1','v3'):
        name=f'multistrategy_live_state_{version}.json'; state=read(base/name)
        state.update(created_at_utc=stamp,processed_candle_closes=[],last_successful_run_utc=None)
        for book in state['strategies'].values():
            book.clear(); book.update(cash_try='10000',initial_cash_try='10000',positions={},realized_pnl_try='0',trade_count=0)
        put(name,state); counts[version]=len(state['strategies'])
        for kind in ('signals','trades','runs'):
            path=base/f'multistrategy_live_{kind}_{version}.csv'
            if path.exists(): changes[path.name]=path.read_bytes().splitlines(keepends=True)[0].rstrip(b'\r\n')+b'\n'
    forward=read(base/'forward_paper_state_v1.json')
    forward.update(created_at_utc=stamp,execution_start_after_candle_close_utc=stamp,
                   initial_cash_try='10000',cash_try='10000',positions={},realized_pnl_try='0',trade_count=0,last_executor_run_utc=None)
    put('forward_paper_state_v1.json',forward); counts['Legacy forward']=1
    path=base/'forward_paper_trades_v1.csv'
    if path.exists(): changes[path.name]=path.read_bytes().splitlines(keepends=True)[0].rstrip(b'\r\n')+b'\n'
    for name in ('multistrategy_live_peaks_v3.json','multistrategy_risk_peaks_v2.json','multistrategy_risk_peaks_v3.json'):
        if (base/name).exists(): put(name,{'created_at_utc':stamp,'strategies':{n:{'peak_equity_try':'10000','last_equity_try':'10000','last_drawdown_fraction':'0','updated_at_utc':stamp} for n in state['strategies']},'updated_at_utc':stamp})
    for name in ('zitar_master_trade_events_v1.jsonl','zitar_daily_performance_v1.jsonl'): changes[name]=b''
    put('zitar_master_trade_watermark_v1.json',dict(schema='ZITAR_MASTER_TRADE_WATERMARK_V1',created_utc=stamp,source='multistrategy_live_trades_v3.csv',baseline_policy='FRESH_RESET',baseline_trade_count=0,baseline_sell_count=0,processed_trade_ids=[]))
    put('zitar_master_execution_bridge_v1.json',{'processed_event_ids':[]})
    for label, cls in [('comparison',Comparison),('candidate',Candidate)]:
        name=f'zitar_{label}_start_v1.json'; config=read(base/name)
        config.update(started_utc=stamp,baseline_trade_ids=[],initial_capital_try='10000.00',real_orders=False)
        put(name,config); s=cls(base,clock=lambda:moment).fresh(config)
        put(f'zitar_{label}_runtime_v1.json',s); counts[label]=len(s['books'])
    previous=read(base/'zitar_futures_paper_v1.json'); POLICY['leverage']=previous['policy']['leverage']
    futures=fresh(ms,previous['universe'])
    for fn in (ensure_book,ensure_experiment,ensure_trigger,ensure): fn(futures,ms)
    if set(previous['books'])-set(futures['books']): raise ValueError('Unknown futures book: reset refused')
    put('zitar_futures_paper_v1.json',futures); counts['Futures']=len(futures['books'])
    put('zitar_discovery_spot_v1.json',spot_fresh(ms)); counts['Discovery spot']=4
    from zitar_master_paper_engine_v1 import default_state as test_fresh
    put('zitar_master_paper_test_state_v1.json',test_fresh())
    # Remove derived status, pending leverage request and replay journals only after backup.
    remove=['zitar_full_paper_runtime_v1.json','zitar_paper_supervisor_v1.json','zitar_comparison_supervisor_v1.json',
            'zitar_research_supervisor_v1.json','zitar_futures_paper_error_v1.json','zitar_discovery_spot_error_v1.json',
            'zitar_futures_leverage_request_v1.json','multistrategy_risk_status_v1.json','multistrategy_risk_status_v2.json','multistrategy_risk_status_v3.json']
    remove += [str(p.relative_to(base)) for p in (base/'multistrategy_live_journal_v3').glob('*.json')]
    for name in remove:
        if (base/name).exists(): changes[name]=None
    from zitar_full_paper_runtime_v1 import Runtime
    Runtime(base).validate(master)
    for book in futures['books'].values():
        assert Decimal(book['cash'])==10000 and not book['positions'] and not book['closed']
    return changes,counts

def commit(base,changes,counts,moment):
    from zitar_paper_supervisor_v1 import FileLock
    guards=[]
    try:
        for name in ('zitar_paper_supervisor_v1','zitar_full_paper_runtime_v1','zitar_research_runtime_v1','zitar_comparison_runtime_v1','zitar_candidate_runtime_v1','zitar_futures_paper_v1','zitar_discovery_spot_v1','zitar_market_discovery_v1'):
            guard=FileLock(base/(name+'.lock'))
            if not guard.acquire(): raise RuntimeError('Writer still running: '+name)
            guards.append(guard)
        archive=base/'paper_reset_archives'/moment.strftime('%Y%m%dT%H%M%S%fZ'); archive.mkdir(parents=True)
        originals={}
        for name in changes:
            path=(base/name).resolve()
            if not path.is_relative_to(base.resolve()): raise ValueError('Invalid path')
            raw=path.read_bytes() if path.exists() else None; originals[name]=raw
            if raw is not None:
                backup=archive/name; backup.parent.mkdir(parents=True,exist_ok=True); backup.write_bytes(raw)
                if backup.read_bytes()!=raw: raise IOError('Backup verification failed')
        manifest=dict(status='PREPARED',started_utc=moment.isoformat(),accounts=counts,
                      files={n:sha(v) if v is not None else None for n,v in originals.items()})
        (archive/'manifest.json').write_bytes(encoded(manifest))
        try:
            for name,raw in originals.items():
                path=base/name
                if (path.read_bytes() if path.exists() else None)!=raw: raise RuntimeError('Concurrent writer: '+name)
            for name,raw in changes.items():
                path=base/name
                if raw is None: path.unlink(missing_ok=True)
                else:
                    temp=path.with_name(path.name+'.reset.tmp'); temp.write_bytes(raw); os.replace(temp,path)
            for name,raw in changes.items():
                path=base/name
                assert (path.read_bytes() if path.exists() else None)==raw, name
        except BaseException:
            for name,raw in originals.items():
                path=base/name
                if raw is None: path.unlink(missing_ok=True)
                else: path.write_bytes(raw)
            manifest['status']='ROLLED_BACK'; (archive/'manifest.json').write_bytes(encoded(manifest)); raise
        manifest.update(status='RESET_COMMITTED',observation_deadline_utc=(moment+timedelta(hours=1)).isoformat(),
                        archive=str(archive),real_orders=False,monitoring_status='AWAITING_RUNTIME_VERIFICATION')
        (archive/'manifest.json').write_bytes(encoded(manifest))
        (base/'zitar_paper_reset_v1.json').write_bytes(encoded(manifest))
        print(json.dumps({k:manifest[k] for k in ('status','started_utc','accounts','archive','monitoring_status')},ensure_ascii=False))
    finally:
        for guard in guards: guard.close()

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--commit',action='store_true'); ap.add_argument('--base',type=Path,default=BASE); args=ap.parse_args()
    moment=datetime.now(timezone.utc); changes,counts=prepare(args.base,moment)
    if args.commit: commit(args.base,changes,counts,moment)
    else: print(json.dumps({'mode':'READ_ONLY_PLAN','accounts':counts,'file_count':len(changes)},ensure_ascii=False))

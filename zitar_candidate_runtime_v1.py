"""Isolated forward comparison of V3 executions; never writes live Master/V3."""
import argparse
import copy
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import time
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from zoneinfo import ZoneInfo
from zitar_full_paper_runtime_v1 import atomic_json, read_json, load_module, Runtime
from zitar_paper_supervisor_v1 import FileLock
from zitar_comparison_performance_v1 import update_quality, performance

TZ = ZoneInfo('Europe/Istanbul')
STRATEGIES = ('SMA20_50', 'EMA12_26', 'RSI14')
STATE = 'zitar_candidate_runtime_v1.json'

def now():
    return datetime.now(timezone.utc)

def digest(row):
    return hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()

class Candidate:
    def __init__(self, base, fetch=None, clock=now):
        self.base = Path(base)
        self.clock = clock
        self.fetch = fetch or (lambda symbols: Runtime.fetch_book(None, symbols))
        self.engine = load_module(self.base, 'zitar_master_paper_engine_v1.py')
        self.portfolio = load_module(self.base, 'zitar_master_portfolio_v1.py')
        self.engine.qty = lambda n: n.quantize(self.engine.QTY, rounding=ROUND_DOWN)
        self.engine.save = lambda s: None
        self.engine.now_utc = lambda: self.clock().isoformat()
        self.path = self.base / STATE

    def fresh(self, config):
        started = datetime.fromisoformat(config['started_utc'].replace('Z', '+00:00'))
        day = started.astimezone(TZ).date().isoformat()
        books = {}
        for name in ('MASTER','ZITAR_V1'):
            book = self.portfolio.default_state()
            book['mode'] = 'ISOLATED_COMPARISON_ONLY'
            book['created_utc'] = config['started_utc']
            book['current_period']['period_id'] = day
            book['rules'].update(fee_rate='0.001', slippage_rate='0.001')
            book['processed_event_ids'] = []
            books[name] = book
        return dict(schema='ZITAR_COMPARISON_V1', started_utc=config['started_utc'],
                    initial_capital_try='10000.00', scope='ISOLATED_BASELINE_VS_ZITAR_ENTRY_FILTER_V1',policy=POLICY,policy_hash=digest(POLICY),
                    baseline_trade_ids=config['baseline_trade_ids'], processed={}, events=[], books=books,
                    samples=[], error_count=0, state='STARTING',
                    authorities={'real_order':False,'modify_master':False,'modify_v3':False})

    def rollover(self, state, moment):
        day = moment.astimezone(TZ).date().isoformat()
        for book in state['books'].values():
            old = book['current_period']['period_id']
            if day < old:
                raise ValueError('CLOCK_MOVED_BACKWARDS')
            if day == old:
                continue
            self.portfolio.current_period_id = lambda: day
            self.portfolio.now_utc = lambda: moment
            self.portfolio.save_state = lambda s: None
            self.portfolio.append_daily_record = lambda r: book.setdefault('runtime_daily_records', []).append(r)
            self.portfolio.rollover_if_needed(book)
            book['runtime_daily_records'][-1].update(actual_rollover_utc=moment.isoformat(),
                last_mtm_utc=state.get('last_mtm_utc'), valuation='LAST_COMMITTED_BID',next_period_id=day)

    def apply(self, book, row):
        eid = row['trade_id']
        before=copy.deepcopy(book['account']['positions'].get(row['symbol']))
        cash_before=Decimal(book['account']['cash_try'])
        pnl_before=Decimal(book['account']['realized_pnl_try'])
        fn = self.engine.buy if row['side'] == 'BUY' else self.engine.remove_support_or_sell
        result = fn(book,row['symbol'],row['strategy'],Decimal(row['reference_price']),eid)
        if result in ('MAX_POSITIONS','INSUFFICIENT_CASH'):
            book['processed_event_ids'].append(eid)
            result = 'REJECTED_' + result
        if eid not in book['processed_event_ids']:
            raise ValueError('MISSING_COMPARISON_RECEIPT')
        if result=='BOUGHT':
            book['account']['positions'][row['symbol']]['entry_reason']='V1 giriş filtreleri sağlandı' if book.get('experiment_account')=='ZITAR_V1' else 'Kaynak stratejinin BUY olayı kabul edildi'
        if result.startswith('SOLD ') and before:
            realized=Decimal(book['account']['realized_pnl_try'])-pnl_before
            book.setdefault('closed_positions',[]).append(dict(symbol=row['symbol'],entry_utc=before.get('opened_utc'),exit_utc=self.clock().isoformat(),quantity=before['quantity'],entry_fill_price=before['entry_fill_price'],total_cost_try=before['total_cost_try'],exit_reference_price=row['reference_price'],net_proceeds_try=str(Decimal(book['account']['cash_try'])-cash_before),realized_pnl_try=str(realized),entry_reason=before.get('entry_reason','Eski kayıtta giriş gerekçesi yok'),exit_reason='Son strateji desteği kalktı',exit_event_id=eid))
        self.engine.assert_identity(book)
        return result

    def cycle(self):
        config = read_json(self.base/'zitar_candidate_start_v1.json')
        if config['initial_capital_try'] != '10000.00' or config['real_orders'] is not False:
            raise ValueError('INVALID_COMPARISON_CONFIG')
        state = read_json(self.path) if self.path.exists() else self.fresh(config)
        if state['started_utc'] != config['started_utc'] or state['baseline_trade_ids'] != config['baseline_trade_ids']:
            raise ValueError('START_CONFIG_CHANGED')
        if state.get('policy_hash') != digest(POLICY): raise ValueError('POLICY_CHANGED_START_NEW_EXPERIMENT')
        for name,book in state['books'].items():
            book['experiment_account']=name
            book.setdefault('position_tracking_started_utc',self.clock().isoformat())
        moment = self.clock()
        raw = (self.base/'multistrategy_live_trades_v3.csv').read_bytes()
        if not raw.endswith(b'\n') or raw != (self.base/'multistrategy_live_trades_v3.csv').read_bytes():
            raise ValueError('SOURCE_CHANGING_RETRY')
        rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
        ids = [r['trade_id'] for r in rows]
        if not all(ids) or len(ids)!=len(set(ids)):
            raise ValueError('DUPLICATE_OR_MISSING_SOURCE_ID')
        if not (set(state['baseline_trade_ids']) | set(state['processed'])).issubset(ids):
            raise ValueError('SOURCE_HISTORY_REMOVED')
        # All books and receipts commit together, making restart replay idempotent.
        self.rollover(state, moment)
        start = datetime.fromisoformat(state['started_utc'].replace('Z','+00:00'))
        for row in rows:
            eid = row['trade_id']
            if eid in state['processed']:
                if state['processed'][eid] != digest(row):
                    raise ValueError('PROCESSED_SOURCE_MUTATED')
                continue
            if eid in state['baseline_trade_ids']:
                continue
            event_time = datetime.fromisoformat(row['executed_at_utc'].replace('Z','+00:00'))
            if event_time.tzinfo is None:
                raise ValueError('SOURCE_TIME_MISSING_ZONE')
            state['processed'][eid] = digest(row)
            if event_time <= start:
                state['events'].append(dict(event_id=eid,result='EXCLUDED_PRE_START_LATE_ROW'))
                continue
            if event_time > moment:
                raise ValueError('SOURCE_FROM_FUTURE')
            if row['strategy'] not in STRATEGIES or row['side'] not in ('BUY','SELL') or not row['symbol'].isalnum() or not row['symbol'].endswith('TRY'):
                raise ValueError('INVALID_SOURCE_EVENT')
            price = Decimal(row['reference_price'])
            if not price.is_finite() or price<=0:
                raise ValueError('INVALID_REFERENCE_PRICE')
            if (moment-event_time).total_seconds()>120:
                state['events'].append(dict(event_id=eid,result='EXCLUDED_DELAYED_EVENT_BOTH_BOOKS',source_utc=row['executed_at_utc']))
                continue
            result = self.apply(state['books']['MASTER'],row)
            allowed,reason = entry_policy(self.base,row)
            strategy_result = self.apply(state['books']['ZITAR_V1'],row) if allowed else 'FILTERED:'+reason
            state['events'].append(dict(event_id=eid,utc=moment.isoformat(),source_utc=row['executed_at_utc'],
                strategy=row['strategy'],symbol=row['symbol'],side=row['side'],reference_price=str(price),
                master_result=result,strategy_result=strategy_result,
                delay_seconds=round((moment-event_time).total_seconds(),1)))
            state['events'][-1]['timing_quality'] = 'DELAYED_REPLAY' if (moment-event_time).total_seconds()>120 else 'FORWARD'
            if (moment-event_time).total_seconds()>120:
                state['has_delayed_replay'] = True
        # Common observed BID snapshot; no per-account time/price advantage.
        symbols = set().union(*(b['account']['positions'] for b in state['books'].values()))
        try:
            quotes = self.fetch(symbols)
            if symbols-set(quotes):
                raise ValueError('MISSING_QUOTES')
            marks = {}
            for symbol in symbols:
                bid,ask = Decimal(str(quotes[symbol]['bid'])),Decimal(str(quotes[symbol]['ask']))
                if not bid.is_finite() or not ask.is_finite() or bid<=0 or ask<bid:
                    raise ValueError('INVALID_QUOTES')
                marks[symbol] = bid
            stamp = self.clock().isoformat()
            for book in state['books'].values():
                self.engine.recalculate(book, marks)
                self.engine.assert_identity(book)
                for symbol,pos in book['account']['positions'].items():
                    pos.update(quote_received_utc=stamp,live_bid=str(marks[symbol]),live_ask=str(quotes[symbol]['ask']))
            state.update(last_mtm_utc=stamp,valuation_state='OK')
        except Exception as exc:
            # Preserve executed events while clearly exposing stale valuation.
            state.update(valuation_state='STALE',last_valuation_error=str(exc))
            state['error_count'] += 1
        stamp = self.clock().isoformat()
        minute = stamp[:16]
        values = {name:round((float(b['account']['equity_try'])/10000-1)*100,6) for name,b in state['books'].items()}
        sample = {'utc':stamp,'returns':values,'valuation_state':state['valuation_state']}
        if state['samples'] and state['samples'][-1]['utc'][:16] == minute:
            state['samples'][-1] = sample
        else:
            state['samples'].append(sample)
        # Retain all data, compact older samples to hourly after 7 days.
        if len(state['samples'])>11000:
            older={s['utc'][:13]:s for s in state['samples'][:-10080]}
            state['samples']=list(older.values())+state['samples'][-10080:]
        update_quality(state,self.clock())
        state['performance']=performance(state)
        state.update(pid=os.getpid(),heartbeat_utc=stamp,last_success_utc=stamp,
                     state='RUNNING' if state['valuation_state']=='OK' else 'DEGRADED',
                     source_trade_count=len(rows))
        atomic_json(self.path,state)
        return state

POLICY={'version':'ZITAR_ENTRY_FILTER_V1','max_spread_bps':20,'max_analysis_age_seconds':3600,'max_1h_candle_age_seconds':7200,'allowed_agreement':['MEDIUM','HIGH'],'blocked_medium':['DOWN','INSUFFICIENT','MISSING'],'exit':'V3 support removal','max_positions':10,'daily_slot':'equity / 10','fee_rate':'0.001','slippage_rate':'0.001','hypothesis':'Filtering wide spreads and adverse/unknown context may improve net returns; unvalidated.'}

def entry_policy(base,row):
    if row['side']=='SELL': return True,'SOURCE_EXIT'
    try:
        bid,ask=Decimal(row['observed_bid']),Decimal(row['observed_ask'])
        if not bid.is_finite() or not ask.is_finite() or bid<=0 or ask<bid:return False,'INVALID_SPREAD'
        if (ask-bid)/((ask+bid)/2)*10000>POLICY['max_spread_bps']:return False,'WIDE_SPREAD'
        from zitar_trade_context_v1 import match_entry
        from zitar_research_rag_api_v1 import validate_chain
        records=[json.loads(x) for x in (Path(base)/'zitar_research_memory_v1.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
        if not validate_chain(records)[0]:return False,'INVALID_MEMORY_CHAIN'
        context=match_entry(row,records,POLICY['max_analysis_age_seconds'])
        if context['status']!='MATCHED':return False,context['status']
        snapshot=json.loads((Path(base)/'zitar_mtf_research_v2.json').read_text(encoding='utf-8'))
        event=datetime.fromisoformat(row['executed_at_utc'])
        generated=datetime.fromisoformat(snapshot['generated_utc'])
        if generated>event:return False,'NO_ASOF_CANDLE_SNAPSHOT'
        evidence=next((r.get('evidence',[]) for r in snapshot.get('results',[]) if r.get('symbol')==row['symbol']),[])
        candle=next((e.get('last_open_time_ms') for e in evidence if e.get('timeframe')=='1h'),None)
        if candle is None:return False,'MISSING_CANDLE_TIME'
        age=event.timestamp()-float(candle)/1000
        if not 0<=age<=POLICY['max_1h_candle_age_seconds']:return False,'STALE_OR_FUTURE_CANDLE'
        obs=context['observation']
        if obs.get('agreement') not in POLICY['allowed_agreement']:return False,'WEAK_AGREEMENT'
        if obs.get('medium') not in ('UP','MIXED'):return False,'ADVERSE_OR_UNKNOWN_MEDIUM'
        return True,'ACCEPTED'
    except (OSError,ValueError,KeyError,TypeError):return False,'MISSING_OR_INVALID_EVIDENCE'

def prepare(base):
    base=Path(base);path=base/'zitar_candidate_start_v1.json'
    if not path.exists():
        raw=(base/'multistrategy_live_trades_v3.csv').read_bytes()
        if not raw.endswith(b'\n'): raise ValueError('SOURCE_INCOMPLETE')
        rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
        atomic_json(path,dict(started_utc=now().isoformat(),baseline_trade_ids=[r['trade_id'] for r in rows],initial_capital_try='10000.00',real_orders=False))

def start_worker(base):
    if (Path(base)/'zitar_futures_only.flag').exists():return
    import threading
    def run():
        guard=FileLock(Path(base)/'zitar_candidate_runtime_v1.lock')
        if not guard.acquire():return
        try:
            prepare(base);worker=Candidate(base)
            while True:
                try:worker.cycle()
                except Exception as exc:print('CANDIDATE_ERROR',str(exc),flush=True)
                time.sleep(15)
        finally:guard.close()
    threading.Thread(target=run,daemon=True,name='zitar-candidate').start()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',type=Path,default=Path(__file__).resolve().parent)
    parser.add_argument('--once',action='store_true')
    args=parser.parse_args()
    guard=FileLock(args.base/'zitar_candidate_runtime_v1.lock')
    if not guard.acquire(): return
    try:
        prepare(args.base)
        worker=Candidate(args.base)
        while True:
            try:
                state=worker.cycle()
                if args.once:
                    state['state']='INITIALIZED'
                    atomic_json(worker.path,state)
                    print(json.dumps({'state':state['state'],'started_utc':state['started_utc'],'events':len(state['events'])}))
                    return
            except Exception as exc:
                print(now().isoformat(),repr(exc),flush=True)
                if args.once: raise
                try:
                    state=read_json(worker.path) if worker.path.exists() else worker.fresh(read_json(args.base/'zitar_candidate_start_v1.json'))
                    state.update(state='ERROR',heartbeat_utc=now().isoformat(),pid=os.getpid(),last_error=str(exc))
                    state['error_count']+=1
                    atomic_json(worker.path,state)
                except Exception as write_error: print(repr(write_error),flush=True)
            time.sleep(15)
    finally: guard.close()

if __name__=='__main__': main()

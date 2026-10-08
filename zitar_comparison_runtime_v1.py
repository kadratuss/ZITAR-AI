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
STATE = 'zitar_comparison_runtime_v1.json'

def now():
    return datetime.now(timezone.utc)

def digest(row):
    return hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()

class Comparison:
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
        for name in ('MASTER',) + STRATEGIES:
            book = self.portfolio.default_state()
            book['mode'] = 'ISOLATED_COMPARISON_ONLY'
            book['created_utc'] = config['started_utc']
            book['current_period']['period_id'] = day
            book['rules'].update(fee_rate='0.001', slippage_rate='0.001')
            book['processed_event_ids'] = []
            books[name] = book
        return dict(schema='ZITAR_COMPARISON_V1', started_utc=config['started_utc'],
                    initial_capital_try='10000.00', scope='FORWARD_SOURCE_TRADES_NOT_FRESH_SIGNAL_BACKTEST',
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
        fn = self.engine.buy if row['side'] == 'BUY' else self.engine.remove_support_or_sell
        result = fn(book,row['symbol'],row['strategy'],Decimal(row['reference_price']),eid)
        if result in ('MAX_POSITIONS','INSUFFICIENT_CASH'):
            book['processed_event_ids'].append(eid)
            result = 'REJECTED_' + result
        if eid not in book['processed_event_ids']:
            raise ValueError('MISSING_COMPARISON_RECEIPT')
        self.engine.assert_identity(book)
        return result

    def cycle(self):
        config = read_json(self.base/'zitar_comparison_start_v1.json')
        if config['initial_capital_try'] != '10000.00' or config['real_orders'] is not False:
            raise ValueError('INVALID_COMPARISON_CONFIG')
        state = read_json(self.path) if self.path.exists() else self.fresh(config)
        if state['started_utc'] != config['started_utc'] or state['baseline_trade_ids'] != config['baseline_trade_ids']:
            raise ValueError('START_CONFIG_CHANGED')
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
            result = self.apply(state['books']['MASTER'],row)
            strategy_result = self.apply(state['books'][row['strategy']],row)
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
                    pos.update(quote_received_utc=stamp,live_bid=str(marks[symbol]))
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

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',type=Path,default=Path(__file__).resolve().parent)
    parser.add_argument('--once',action='store_true')
    args=parser.parse_args()
    guard=FileLock(args.base/'zitar_comparison_runtime_v1.lock')
    if not guard.acquire(): return
    try:
        worker=Comparison(args.base)
        while True:
            try:
                state=worker.cycle()
                if args.once:
                    print(json.dumps({'state':state['state'],'started_utc':state['started_utc'],'events':len(state['events'])}))
                    return
            except Exception as exc:
                print(now().isoformat(),repr(exc),flush=True)
                if args.once: raise
                try:
                    state=read_json(worker.path) if worker.path.exists() else worker.fresh(read_json(args.base/'zitar_comparison_start_v1.json'))
                    state.update(state='ERROR',heartbeat_utc=now().isoformat(),pid=os.getpid(),last_error=str(exc))
                    state['error_count']+=1
                    atomic_json(worker.path,state)
                except Exception as write_error: print(repr(write_error),flush=True)
            time.sleep(15)
    finally: guard.close()

if __name__=='__main__': main()

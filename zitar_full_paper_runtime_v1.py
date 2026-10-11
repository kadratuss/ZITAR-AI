"""Single-writer Master paper adapter. Existing V3 and engine sources are unchanged.

The external V3 scheduler remains its only producer. No private exchange API,
credentials, real-order endpoint or research execution authority is used here.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import csv
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import threading
import time
import urllib.request
import urllib.error
import http.client
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from zoneinfo import ZoneInfo

TZ = ZoneInfo('Europe/Istanbul')
BOOK_URL = 'https://api.binance.me/api/v3/ticker/bookTicker'


def utcnow():
    return datetime.now(timezone.utc)


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def atomic_bytes(path, payload):
    path = Path(path)
    tmp = path.with_name(path.name + '.runtime.tmp')
    with tmp.open('wb') as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())
    # Windows readers (including PowerShell/AV) can briefly hold a handle that
    # denies replacement. Keep the old file intact and retry only those errors.
    for attempt in range(8):
        try:
            os.replace(tmp, path)
            break
        except OSError as exc:
            if getattr(exc, 'winerror', None) not in (5, 32, 33) or attempt == 7:
                raise
            time.sleep(min(0.025 * 2 ** attempt, 0.5))


def atomic_json(path, value):
    atomic_bytes(path, json.dumps(value, ensure_ascii=False, indent=2,
                                  allow_nan=False).encode('utf-8'))


def jsonl(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding='utf-8-sig').splitlines() if line.strip()]


def write_jsonl(path, rows):
    atomic_bytes(path, ''.join(json.dumps(x, ensure_ascii=False, allow_nan=False) + '\n'
                               for x in rows).encode('utf-8'))


def load_module(base, filename):
    spec = importlib.util.spec_from_file_location('runtime_' + filename[:-3], base / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class WriterLock:
    def __init__(self, base):
        self.path = base / 'zitar_full_paper_runtime_v1.lock'

    def __enter__(self):
        self.fh = self.path.open('a+b')
        if self.path.stat().st_size == 0:
            self.fh.write(b'0')
            self.fh.flush()
        self.fh.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.fh.close()
            raise RuntimeError('Another ZITAR full-paper runtime owns the writer lock')
        return self

    def __exit__(self, *args):
        self.fh.close()


class Runtime:
    def __init__(self, base, fetch=None, clock=utcnow):
        self.base = Path(base).resolve()
        self.clock = clock
        self.fetch = fetch or self.fetch_book
        self.master = self.base / 'zitar_master_portfolio_v1.json'
        self.status_path = self.base / 'zitar_full_paper_runtime_v1.json'
        self.events_path = self.base / 'zitar_master_trade_events_v1.jsonl'
        self.watermark_path = self.base / 'zitar_master_trade_watermark_v1.json'
        self.bridge_path = self.base / 'zitar_master_execution_bridge_v1.json'
        self.daily_path = self.base / 'zitar_daily_performance_v1.jsonl'
        self.engine = load_module(self.base, 'zitar_master_paper_engine_v1.py')
        # Floor purchased quantity so gross+fee never exceeds the daily slot,
        # including a final slot whose budget equals remaining cash.
        self.engine.qty = lambda value: value.quantize(self.engine.QTY, rounding=ROUND_DOWN)
        self.detector = load_module(self.base, 'zitar_master_trade_detector_v1.py')
        self.bridge = load_module(self.base, 'zitar_master_execution_bridge_v1.py')
        self.portfolio = load_module(self.base, 'zitar_master_portfolio_v1.py')
        self.engine.STATE = self.master
        self.status = read_json(self.status_path) if self.status_path.exists() else {}
        self.status.update(schema='ZITAR_FULL_PAPER_RUNTIME_V1', pid=os.getpid(),
                           started_utc=self.stamp(), state='STARTING', active_stage=None,
                           safety={'mode': 'PAPER', 'real_orders': False,
                                   'master_v3_write': False, 'futures': False},
                           scheduler={'mode': 'EXTERNAL_EXISTING_V3', 'configuration_verified': False})
        self.status.setdefault('cycle_count', 0)
        self.status.setdefault('error_count', 0)
        self.status.setdefault('recent_errors', [])
        self.status.setdefault('stages', {})
        self.mutex = threading.RLock()

    def stamp(self):
        return self.clock().isoformat()

    def publish(self):
        with self.mutex:
            self.status['heartbeat_utc'] = self.stamp()
            atomic_json(self.status_path, self.status)

    def validate(self, state):
        if state.get('schema') != 'ZITAR_MASTER_PORTFOLIO_V1':
            raise ValueError('Unexpected Master schema; never initialize/reset automatically')
        auth, rules = state['authorities'], state['rules']
        if auth.get('real_order') is not False or rules.get('futures_enabled') is not False:
            raise ValueError('Safety flags are not explicitly OFF')
        if auth.get('futures_allocation') is not False or auth.get('modify_v3', False) is not False:
            raise ValueError('Unauthorized futures/V3 authority')
        if rules.get('max_spot_positions') != 10:
            raise ValueError('Unexpected max positions')
        if Decimal(rules['fee_rate']) != self.engine.FEE_RATE or Decimal(rules['slippage_rate']) != self.engine.SLIPPAGE_RATE:
            raise ValueError('Cost model mismatch')
        ids = state['processed_event_ids']
        if len(ids) != len(set(ids)):
            raise ValueError('Duplicate Master processed IDs')
        a, p = state['account'], state['current_period']
        for k in ('cash_try', 'position_market_value_try', 'equity_try', 'realized_pnl_try', 'unrealized_pnl_try'):
            if not Decimal(a[k]).is_finite():
                raise ValueError('Nonfinite accounting field: ' + k)
        self.engine.assert_identity(state)
        if Decimal(a['cash_try']) < 0 or a['open_position_count'] != len(a['positions']):
            raise ValueError('Invalid cash/position count')
        if a['equity_try'] != p['current_equity_try']:
            raise ValueError('Period equity mismatch')
        if a['realized_pnl_try'] != state['lifetime']['total_realized_pnl_try']:
            raise ValueError('Lifetime realized mismatch')
        check = copy.deepcopy(state)
        self.engine.recalculate(check)
        if check['account'] != a:
            raise ValueError('Position/account valuation mismatch')
        for pos in a['positions'].values():
            if not pos['strategy_support'] or len(set(pos['strategy_support'])) != len(pos['strategy_support']):
                raise ValueError('Invalid strategy supporters')
            for key in ('quantity', 'last_mark_price', 'total_cost_try'):
                x = Decimal(pos[key])
                if not x.is_finite() or x <= 0:
                    raise ValueError('Invalid position ' + key)

    def read_master(self):
        raw = self.master.read_bytes()
        state = json.loads(raw.decode('utf-8-sig'))
        self.validate(state)
        return state, raw

    def commit(self, state, expected):
        self.validate(state)
        if self.master.read_bytes() != expected:
            raise RuntimeError('Concurrent Master writer detected; refusing overwrite')
        state['last_updated_utc'] = self.stamp()
        atomic_json(self.master, state)

    def detect(self):
        # V3 CSV must be stable and newline-complete before it is consumed.
        path = self.base / 'multistrategy_live_trades_v3.csv'
        raw = path.read_bytes()
        if not raw.endswith(b'\n') or path.read_bytes() != raw:
            raise RuntimeError('V3 CSV incomplete/changing; retry next cycle')
        rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
        source_ids = [x.get('trade_id', '').strip() for x in rows]
        if not all(source_ids) or len(source_ids) != len(set(source_ids)):
            raise ValueError('Missing/duplicate V3 trade IDs')
        watermark = read_json(self.watermark_path)
        events = jsonl(self.events_path)
        known = {x['source_trade_id'] for x in events}
        if len(known) != len(events):
            raise ValueError('Duplicate event log IDs')
        processed = set(watermark['processed_trade_ids'])
        if not processed.issubset(set(source_ids)):
            raise ValueError('V3 source history truncated or replaced')
        # Event file commits first. On restart reconcile event IDs into watermark.
        recovered = known - processed
        processed |= known
        new = []
        for row in rows:
            if row['trade_id'] in processed:
                continue
            event = dict(schema='ZITAR_MASTER_TRADE_EVENT_V1', detected_utc=self.stamp(),
                         source=path.name, source_trade_id=row['trade_id'],
                         executed_at_utc=row.get('executed_at_utc'),
                         signal_candle_close_utc=row.get('signal_candle_close_utc'),
                         strategy=row.get('strategy'), symbol=row.get('symbol'), side=row.get('side'),
                         reference_price=row.get('reference_price'), modeled_fill_price=row.get('modeled_fill_price'),
                         source_quantity=row.get('quantity'), source_realized_pnl_try=row.get('realized_pnl_try'),
                         policy=dict(event_is_master_execution=False, source_pnl_is_master_pnl=False,
                                     master_order_authority=False))
            self.validate_event(event)
            new.append(event)
            processed.add(row['trade_id'])
        if new:
            write_jsonl(self.events_path, events + new)
        watermark.update(processed_trade_ids=sorted(processed), last_detector_run_utc=self.stamp(),
                         last_detector_source_trade_count=len(rows), last_detector_new_trade_count=len(new),
                         master_imported_trade_count=len(events) + len(new),
                         master_imported_sell_count=sum(x['side'] == 'SELL' for x in events + new),
                         last_source_trade_id=source_ids[-1] if source_ids else None)
        atomic_json(self.watermark_path, watermark)
        return {'new_events': len(new), 'recovered_event_ids': len(recovered), 'source_trades': len(rows)}

    def validate_event(self, event):
        self.bridge.validate_event(event)
        price = Decimal(event['reference_price'])
        if not price.is_finite() or price <= 0:
            raise ValueError('Invalid event price')
        if event['strategy'] not in {'SMA20_50', 'EMA12_26', 'RSI14'}:
            raise ValueError('Unknown strategy')
        if not event['symbol'].isalnum() or not event['symbol'].endswith('TRY'):
            raise ValueError('Not a TRY spot symbol')
        if event.get('policy', {}).get('master_order_authority') is not False:
            raise ValueError('Event authority must be false')

    def execute(self):
        events = jsonl(self.events_path)
        ids = [x['source_trade_id'] for x in events]
        if len(ids) != len(set(ids)):
            raise ValueError('Duplicate event log IDs')
        bridge = read_json(self.bridge_path)
        master, _ = self.read_master()
        if not set(bridge['processed_event_ids']).issubset(set(master['processed_event_ids'])):
            raise ValueError('Bridge ahead of Master; manual investigation required')
        done = set(bridge['processed_event_ids'])
        results = []
        for event in events:
            self.validate_event(event)
            eid = event['source_trade_id']
            if eid in done:
                continue
            self.rollover()  # also protect a batch that crosses midnight
            state, before = self.read_master()
            if eid in state['processed_event_ids']:
                result = 'DUPLICATE_EVENT_RECOVERED'
            else:
                # Preserve engine transaction in memory, then commit receipt+state together.
                self.engine.save = lambda state: None
                fn = self.engine.buy if event['side'] == 'BUY' else self.engine.remove_support_or_sell
                result = fn(state, event['symbol'], event['strategy'], Decimal(event['reference_price']), eid)
                if result in ('MAX_POSITIONS', 'INSUFFICIENT_CASH'):
                    # Terminal risk rejection: never retry a stale BUY behind a later SELL.
                    state['processed_event_ids'].append(eid)
                    result = 'REJECTED_' + result
                if eid not in state['processed_event_ids']:
                    raise RuntimeError('Engine did not commit event: ' + result)
                state.setdefault('runtime_execution_receipts', []).append(
                    dict(event_id=eid, utc=self.stamp(), side=event['side'], symbol=event['symbol'],
                         strategy=event['strategy'], result=result,
                         source_executed_at_utc=event.get('executed_at_utc'),
                         accounting_period=state['current_period']['period_id']))
                self.commit(state, before)
            done.add(eid)
            bridge.update(processed_event_ids=sorted(done), last_processed_event_id=eid,
                          last_result=result, last_processed_utc=self.stamp())
            atomic_json(self.bridge_path, bridge)
            results.append(result)
        return {'applied': len(results), 'results': results}

    def fetch_book(self, symbols):
        if not symbols:
            return {}
        request = urllib.request.Request(BOOK_URL, headers={'User-Agent': 'ZITAR-Paper-MTM/1.0'})
        # Retry transport interruptions only; never hide HTTP limits or serve old marks as fresh.
        for attempt in range(2):
            try:
                with urllib.request.urlopen(request, timeout=5) as response:
                    data = json.load(response)
                break
            except urllib.error.HTTPError:
                raise
            except (OSError, TimeoutError, http.client.RemoteDisconnected):
                if attempt: raise
                time.sleep(.5)
        if not isinstance(data, list):
            raise ValueError('Unexpected public bookTicker response')
        return {row['symbol']: {'bid': row['bidPrice'], 'ask': row['askPrice']}
                for row in data if row.get('symbol') in symbols}

    def mtm(self):
        state, before = self.read_master()
        positions = state['account']['positions']
        quotes = self.fetch(set(positions))
        if set(positions) - set(quotes):
            raise ValueError('Missing live quotes: ' + ','.join(set(positions) - set(quotes)))
        stamp = self.stamp()
        marks = {}
        for symbol, pos in positions.items():
            bid, ask = Decimal(str(quotes[symbol]['bid'])), Decimal(str(quotes[symbol]['ask']))
            if not bid.is_finite() or not ask.is_finite() or bid <= 0 or ask < bid:
                raise ValueError('Invalid/crossed live book: ' + symbol)
            marks[symbol] = bid
            pos.update(live_bid=str(bid), live_ask=str(ask), quote_received_utc=stamp)
        realized = (state['account']['realized_pnl_try'], copy.deepcopy(state['lifetime']),
                    state['current_period']['daily_realized_pnl_try'])
        self.engine.recalculate(state, marks)
        if realized != (state['account']['realized_pnl_try'], state['lifetime'],
                        state['current_period']['daily_realized_pnl_try']):
            raise ValueError('MTM changed realized accounting')
        state['runtime_mtm'] = dict(last_success_utc=stamp, source=BOOK_URL, valuation='BID',
                                    quote_count=len(quotes), exchange_timestamp_available=False)
        self.commit(state, before)
        return {'quote_count': len(quotes), 'equity_try': state['account']['equity_try'],
                'source': BOOK_URL, 'valuation': 'BID'}

    def rollover(self):
        state, before = self.read_master()
        today = self.clock().astimezone(TZ).date().isoformat()
        old = state['current_period']['period_id']
        if old > today:
            raise ValueError('Clock moved backwards; rollover blocked')
        changed = old != today
        if changed:
            # Existing portfolio calculation, with archive + new period in ONE Master commit.
            self.portfolio.current_period_id = lambda: today
            self.portfolio.now_utc = self.clock
            self.portfolio.append_daily_record = lambda r: state.setdefault('runtime_daily_records', []).append(r)
            self.portfolio.save_state = lambda s: None
            self.portfolio.rollover_if_needed(state)
            state['runtime_daily_records'][-1].update(
                last_mtm_utc=state.get('runtime_mtm', {}).get('last_success_utc'),
                rollover_valuation='LAST_COMMITTED_BID',
                actual_rollover_utc=self.stamp(), next_period_id=today)
            self.commit(state, before)
        # Idempotent projection: crash after Master save cannot duplicate daily record.
        records = jsonl(self.daily_path)
        by_day = {x['period_id']: x for x in records}
        if len(by_day) != len(records):
            raise ValueError('Duplicate daily archive periods')
        for record in state.get('runtime_daily_records', []):
            by_day[record['period_id']] = record
        updated = [by_day[k] for k in sorted(by_day)]
        if updated != records:
            write_jsonl(self.daily_path, updated)
        return {'rolled': changed, 'previous_period': old, 'period': today,
                'slot_budget_try': state['current_period']['spot_slot_budget_try']}

    def inspect_pipeline(self):
        state, _ = self.read_master()
        v3 = read_json(self.base / 'multistrategy_live_state_v3.json')
        wm = read_json(self.watermark_path)
        bridge = read_json(self.bridge_path)
        events = jsonl(self.events_path)
        eids = [e['source_trade_id'] for e in events]
        mids = set(state['processed_event_ids'])
        last = v3.get('last_successful_run_utc')
        age = (self.clock() - datetime.fromisoformat(last)).total_seconds() if last else None
        return dict(v3_status='RECENT_RUN' if age is not None and 0 <= age < 4500 else 'STALE',
                    v3_last_success_utc=last, v3_age_seconds=age,
                    last_processed_candle=max(v3.get('processed_candle_closes', []), default=None),
                    v3_trade_count=wm.get('last_detector_source_trade_count'),
                    detector_processed=len(wm['processed_trade_ids']), new_detector_events=wm.get('last_detector_new_trade_count'),
                    event_count=len(eids), bridge_processed=len(bridge['processed_event_ids']),
                    master_processed=len(mids), pending_events=len(set(eids) - set(bridge['processed_event_ids'])),
                    duplicate_status='PASS' if len(eids) == len(set(eids)) else 'FAIL',
                    accounting_identity='PASS', master_mode_metadata=state.get('mode'),
                    master_paper_authority_metadata=state['authorities'].get('paper_order'))

    def cycle(self):
        if (self.base/'zitar_futures_only.flag').exists():
            self.status.update(state='RUNNING',cycle_started_utc=self.stamp(),last_successful_cycle_utc=self.stamp(),active_stage=None,spot_disabled=True,stages={},pipeline={},legacy_events=[])
            self.publish();return True
        with self.mutex:
            self.status.update(state='RUNNING', cycle_started_utc=self.stamp())
        errors = []
        # Rollover before new execution: sells after midnight belong to the new day.
        # Closing value is the last committed pre-boundary bid; staleness is archived.
        for name, fn in [('rollover', self.rollover), ('detector', self.detect),
                         ('bridge', self.execute), ('mtm', self.mtm), ('master', self.inspect_pipeline)]:
            with self.mutex:
                self.status['active_stage'] = name
            self.publish()
            try:
                result = fn()
                with self.mutex:
                    self.status['stages'][name] = dict(status='OK', utc=self.stamp(), result=result)
                    if name == 'master':
                        self.status['pipeline'] = result
                        receipts = {x['event_id'] for x in read_json(self.master).get('runtime_execution_receipts', [])}
                        self.status['legacy_events'] = [dict(x, result='PRE_RUNTIME_PROCESSED') for x in jsonl(self.events_path)
                                                        if x['source_trade_id'] not in receipts][-30:]
            except Exception as exc:
                error = dict(stage=name, utc=self.stamp(), message=str(exc))
                errors.append(error)
                with self.mutex:
                    self.status['stages'][name] = dict(status='ERROR', **error)
                    self.status['last_error'] = error
                    self.status['error_count'] += 1
                    self.status['recent_errors'] = (self.status['recent_errors'] + [error])[-50:]
                # Never execute when rollover or detector integrity failed.
                if name in ('rollover', 'detector'):
                    break
        with self.mutex:
            self.status['cycle_count'] += 1
            self.status['active_stage'] = None
            self.status['state'] = 'DEGRADED' if errors else 'RUNNING'
            if self.status.get('pipeline', {}).get('v3_status') == 'STALE':
                self.status['state'] = 'DEGRADED'
            if not errors:
                self.status['last_successful_cycle_utc'] = self.stamp()
            self.status['cycle_finished_utc'] = self.stamp()
            history = self.status.setdefault('health_history', [])
            minute = self.stamp()[:16]
            if not history or history[-1]['minute'] != minute:
                history.append(dict(minute=minute, state=self.status['state'],
                                    errors=self.status['error_count'], pipeline=self.status.get('pipeline')))
                self.status['health_history'] = history[-1440:]
        self.publish()
        return not errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--interval', type=float, default=15)
    parser.add_argument('--port', type=int, default=5020)
    args = parser.parse_args()
    if args.interval < 2:
        parser.error('interval must be at least 2 seconds')
    with WriterLock(args.base):
        runtime = Runtime(args.base)
        runtime.read_master()  # refuse unsafe baseline before any writes
        if args.once:
            sys.exit(0 if runtime.cycle() else 1)
        from zitar_full_paper_dashboard_v1 import make_server
        server = make_server(args.base, args.port)  # fail if occupied; never kill existing services
        threading.Thread(target=server.serve_forever, daemon=True).start()
        print(f'ZITAR PAPER | http://127.0.0.1:{args.port} | PID {os.getpid()}', flush=True)
        stop = threading.Event()
        def heartbeat():
            while not stop.wait(5):
                try:
                    runtime.publish()
                except Exception as exc:
                    print('HEARTBEAT_WRITE_ERROR: ' + repr(exc), file=sys.stderr, flush=True)
        threading.Thread(target=heartbeat, daemon=True).start()
        try:
            while True:
                try:
                    runtime.cycle()
                except Exception as exc:
                    # A failed heartbeat/status write must not kill monitoring.
                    # No further trading stage runs after the failed cycle.
                    with runtime.mutex:
                        error = dict(stage='cycle_io', utc=runtime.stamp(), message=str(exc))
                        runtime.status.update(state='DEGRADED', last_error=error, active_stage=None)
                        runtime.status['error_count'] += 1
                        runtime.status['recent_errors'] = (runtime.status['recent_errors'] + [error])[-50:]
                    print('CYCLE_IO_ERROR: ' + repr(exc), file=sys.stderr, flush=True)
                time.sleep(args.interval)
        except KeyboardInterrupt:
            pass
        finally:
            stop.set()
            runtime.status.update(state='STOPPED', active_stage=None)
            try:
                runtime.publish()
            except Exception as exc:
                print('FINAL_STATUS_WRITE_ERROR: ' + repr(exc), file=sys.stderr, flush=True)
            server.shutdown()


if __name__ == '__main__':
    main()

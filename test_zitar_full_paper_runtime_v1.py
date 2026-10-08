import copy
import csv
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from zitar_full_paper_runtime_v1 import Runtime, WriterLock, atomic_json, read_json, jsonl, write_jsonl

SOURCE = Path(__file__).resolve().parent
BASELINE = SOURCE / 'zitar_test_fixture_v1'


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        for name in ('zitar_master_paper_engine_v1.py', 'zitar_master_trade_detector_v1.py',
                     'zitar_master_execution_bridge_v1.py', 'zitar_master_portfolio_v1.py'):
            shutil.copy2(SOURCE / name, self.base / name)
        for name in ('zitar_master_portfolio_v1.json', 'zitar_master_execution_bridge_v1.json',
                     'zitar_master_trade_events_v1.jsonl', 'zitar_master_trade_watermark_v1.json',
                     'multistrategy_live_trades_v3.csv', 'multistrategy_live_state_v3.json'):
            shutil.copy2(BASELINE / name, self.base / name)
        self.now = datetime(2026, 9, 25, 20, 59, 40, tzinfo=timezone.utc)
        self.rt = Runtime(self.base, fetch=lambda symbols: {s: {'bid': '0.11843', 'ask': '0.11866'} for s in symbols},
                          clock=lambda: self.now)
        self.v3_before = (self.base / 'multistrategy_live_trades_v3.csv').read_bytes()

    def tearDown(self):
        self.tmp.cleanup()

    def event(self, eid, side='BUY', symbol='TESTTRY', strategy='SMA20_50'):
        return dict(schema='ZITAR_MASTER_TRADE_EVENT_V1', source_trade_id=eid,
                    side=side, symbol=symbol, strategy=strategy, reference_price='100',
                    policy={'master_order_authority': False})

    def add_event(self, event):
        write_jsonl(self.rt.events_path, jsonl(self.rt.events_path) + [event])

    def add_source(self, eid='NEW_TRADE'):
        path = self.base / 'multistrategy_live_trades_v3.csv'
        with path.open(encoding='utf-8-sig', newline='') as fh:
            reader = csv.DictReader(fh)
            fields, rows = reader.fieldnames, list(reader)
        row = dict(rows[-1])
        row.update(trade_id=eid, symbol='TESTTRY', strategy='SMA20_50', reference_price='100')
        with path.open('a', encoding='utf-8', newline='') as fh:
            csv.DictWriter(fh, fields).writerow(row)

    def test_live_state_cycle_preserves_source_and_idempotency(self):
        self.assertTrue(self.rt.cycle())
        state = read_json(self.rt.master)
        self.assertEqual(state['account']['cash_try'], '9000.00')
        self.assertEqual(state['account']['equity_try'], '9987.99')
        self.assertEqual(state['current_period']['spot_slot_budget_try'], '1000.00')
        self.assertEqual(state['account']['realized_pnl_try'], '0.00')
        self.assertTrue(self.rt.cycle())
        self.assertEqual(len(read_json(self.rt.master)['processed_event_ids']), 1)
        self.assertEqual((self.base / 'multistrategy_live_trades_v3.csv').read_bytes(), self.v3_before)

    def test_detector_crash_between_event_and_watermark(self):
        self.add_source()
        real_save = atomic_json
        def fail_watermark(path, value):
            if path == self.rt.watermark_path:
                raise OSError('simulated crash')
            return real_save(path, value)
        with patch('zitar_full_paper_runtime_v1.atomic_json', fail_watermark):
            with self.assertRaises(OSError):
                self.rt.detect()
        self.assertEqual(len(jsonl(self.rt.events_path)), 2)
        self.assertEqual(self.rt.detect()['recovered_event_ids'], 1)
        self.assertEqual(len(jsonl(self.rt.events_path)), 2)
        self.assertEqual(self.rt.detect()['new_events'], 0)

    def test_bridge_crash_recovers_without_double_buy(self):
        self.add_event(self.event('NEW_BUY'))
        real_save = atomic_json
        def fail_bridge(path, value):
            if path == self.rt.bridge_path:
                raise OSError('simulated crash')
            return real_save(path, value)
        with patch('zitar_full_paper_runtime_v1.atomic_json', fail_bridge):
            with self.assertRaises(OSError):
                self.rt.execute()
        cash = read_json(self.rt.master)['account']['cash_try']
        result = self.rt.execute()
        self.assertEqual(result['results'], ['DUPLICATE_EVENT_RECOVERED'])
        self.assertEqual(read_json(self.rt.master)['account']['cash_try'], cash)
        self.assertEqual(len(read_json(self.rt.master)['runtime_execution_receipts']), 1)

    def test_rollover_projection_crash_and_restart(self):
        self.rt.mtm()
        self.now += timedelta(seconds=30)
        with patch('zitar_full_paper_runtime_v1.write_jsonl', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.rt.rollover()
        state = read_json(self.rt.master)
        self.assertEqual(state['current_period']['period_id'], '2026-09-26')
        self.assertEqual(state['current_period']['spot_slot_budget_try'], '998.80')
        self.assertEqual(len(state['runtime_daily_records']), 1)
        self.assertFalse(self.rt.rollover()['rolled'])
        self.assertEqual(len(jsonl(self.rt.daily_path)), 1)
        self.rt.rollover()
        self.assertEqual(len(jsonl(self.rt.daily_path)), 1)

    def test_mtm_failures_leave_master_unchanged(self):
        before = self.rt.master.read_bytes()
        for quotes in ({}, {'ONETRY': {'bid': 'NaN', 'ask': '1'}},
                       {'ONETRY': {'bid': '2', 'ask': '1'}}):
            self.rt.fetch = lambda symbols: quotes
            with self.assertRaises(ValueError):
                self.rt.mtm()
            self.assertEqual(self.rt.master.read_bytes(), before)

    def test_support_lifecycle_and_sell_after_midnight(self):
        self.add_event(self.event('ADD_EMA', symbol='ONETRY', strategy='EMA12_26'))
        self.rt.execute()
        self.assertEqual(read_json(self.rt.master)['account']['cash_try'], '9000.00')
        self.add_event(self.event('REMOVE_RSI', side='SELL', symbol='ONETRY', strategy='RSI14'))
        self.rt.execute()
        self.assertEqual(read_json(self.rt.master)['account']['open_position_count'], 1)
        self.now += timedelta(seconds=30)
        self.rt.rollover()
        self.add_event(self.event('SELL_EMA', side='SELL', symbol='ONETRY', strategy='EMA12_26'))
        self.rt.execute()
        state = read_json(self.rt.master)
        self.assertEqual(state['account']['open_position_count'], 0)
        self.assertEqual(state['current_period']['closed_trade_count'], 1)
        self.assertEqual(state['runtime_daily_records'][0]['closed_trade_count'], 0)
        self.assertEqual(state['current_period']['daily_realized_pnl_try'], state['lifetime']['total_realized_pnl_try'])

    def test_risk_rejection_does_not_block_sell(self):
        state, before = self.rt.read_master()
        state['current_period']['spot_slot_budget_try'] = '10000.00'
        self.rt.commit(state, before)
        self.add_event(self.event('REJECTED_BUY'))
        self.add_event(self.event('LATER_SELL', side='SELL', symbol='ONETRY', strategy='RSI14'))
        results = self.rt.execute()['results']
        self.assertEqual(results[0], 'REJECTED_INSUFFICIENT_CASH')
        self.assertTrue(results[1].startswith('SOLD'))
        self.assertEqual(self.rt.execute()['applied'], 0)

    def test_final_slot_rounding_never_exceeds_cash_or_budget(self):
        state, before = self.rt.read_master()
        state['account']['cash_try'] = '1000.00'
        self.rt.engine.recalculate(state)
        self.rt.commit(state, before)
        event = self.event('LAST_SLOT')
        event['reference_price'] = '103'
        self.add_event(event)
        self.assertEqual(self.rt.execute()['results'], ['BOUGHT'])
        state = read_json(self.rt.master)
        self.assertEqual(state['account']['cash_try'], '0.00')
        pos = state['account']['positions']['TESTTRY']
        from decimal import Decimal
        cost = Decimal(pos['quantity']) * Decimal(pos['entry_fill_price']) * Decimal('1.001')
        self.assertLessEqual(cost, Decimal('1000.00'))

    def test_concurrent_writer_and_duplicate_lock(self):
        state, before = self.rt.read_master()
        atomic_json(self.rt.master, dict(state, external_change=True))
        with self.assertRaisesRegex(RuntimeError, 'Concurrent'):
            self.rt.commit(state, before)
        with WriterLock(self.base):
            with self.assertRaises(RuntimeError):
                with WriterLock(self.base):
                    pass

    def test_unsafe_master_refuses_execution(self):
        state = read_json(self.rt.master)
        state['authorities']['real_order'] = True
        atomic_json(self.rt.master, state)
        with self.assertRaises(ValueError):
            self.rt.read_master()

    def test_duplicate_source_and_partial_source_fail_closed(self):
        self.add_source('b6781682254ef2477dfc089728058f725bc87734e5781c06694a5f2dffb71387')
        with self.assertRaises(ValueError):
            self.rt.detect()
        (self.base / 'multistrategy_live_trades_v3.csv').write_bytes(self.v3_before + b'partial')
        with self.assertRaises(RuntimeError):
            self.rt.detect()

    def test_windows_replace_retries_transient_sharing_failure(self):
        import os
        target = self.base / 'retry.json'
        atomic_json(target, {'version':1})
        real_replace = os.replace
        attempts = []
        def sharing_conflict(src, dst):
            attempts.append(dst)
            if len(attempts)<3:
                self.assertEqual(read_json(target), {'version':1})
                error = PermissionError('temporary shared handle')
                error.winerror = 32
                raise error
            return real_replace(src,dst)
        with patch('zitar_full_paper_runtime_v1.os.replace',sharing_conflict):
            atomic_json(target,{'version':2})
        self.assertEqual(len(attempts),3)
        self.assertEqual(read_json(target),{'version':2})

    def test_permanent_replace_failure_preserves_previous_state(self):
        target = self.base / 'retry.json'
        atomic_json(target, {'version':1})
        error = PermissionError('permanent denied')
        error.winerror = 5
        with patch('zitar_full_paper_runtime_v1.os.replace',side_effect=error) as replace:
            with patch('zitar_full_paper_runtime_v1.time.sleep'):
                with self.assertRaises(PermissionError):
                    atomic_json(target,{'version':2})
        self.assertEqual(replace.call_count,8)
        self.assertEqual(read_json(target),{'version':1})


if __name__ == '__main__':
    unittest.main(verbosity=2)

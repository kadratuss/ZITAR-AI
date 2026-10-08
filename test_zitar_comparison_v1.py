import csv
import json
import shutil
import tempfile
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from zitar_comparison_runtime_v1 import Comparison,STATE

SOURCE=Path(r'C:\Users\pars_\Documents\PortfolioAI-Backend')

class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        for name in ('zitar_master_paper_engine_v1.py','zitar_master_portfolio_v1.py'):
            shutil.copy2(SOURCE/name,self.base/name)
        self.time=datetime(2026,9,26,10,tzinfo=timezone.utc)
        (self.base/'zitar_comparison_start_v1.json').write_text(json.dumps(dict(
            started_utc=self.time.isoformat(),baseline_trade_ids=['old'],initial_capital_try='10000.00',real_orders=False)))
        self.rows=[self.row('old','SMA20_50','OLDTRY','BUY')]
        self.write()
        self.worker=Comparison(self.base,fetch=lambda symbols:{s:{'bid':'10','ask':'10.01'} for s in symbols},clock=lambda:self.time)
    def row(self,eid,strategy,symbol,side):
        return dict(trade_id=eid,strategy=strategy,symbol=symbol,side=side,reference_price='10',executed_at_utc=self.time.isoformat())
    def write(self):
        with (self.base/'multistrategy_live_trades_v3.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=self.rows[0].keys());w.writeheader();w.writerows(self.rows)
    def event(self,eid,strategy='SMA20_50',symbol='TESTTRY',side='BUY'):
        self.time+=timedelta(seconds=1);self.rows.append(self.row(eid,strategy,symbol,side));self.write()
    def test_common_fill_restart_and_support_divergence(self):
        s=self.worker.cycle();self.assertEqual(s['books']['MASTER']['account']['equity_try'],'10000.00')
        self.event('a');s=self.worker.cycle()
        self.assertEqual(s['books']['MASTER']['account'],s['books']['SMA20_50']['account'])
        self.assertEqual(len(s['events']),1)
        s=self.worker.cycle();self.assertEqual(len(s['events']),1)
        self.event('b','RSI14');s=self.worker.cycle()
        self.assertEqual(s['events'][-1]['master_result'],'SUPPORT_ADDED')
        self.assertEqual(s['events'][-1]['strategy_result'],'BOUGHT')
        self.event('c',side='SELL');s=self.worker.cycle()
        self.assertEqual(s['events'][-1]['master_result'],'SUPPORT_REMOVED_POSITION_HELD')
        self.assertEqual(s['books']['SMA20_50']['account']['open_position_count'],0)
        self.assertEqual(s['books']['MASTER']['account']['open_position_count'],1)
    def test_cash_cap_rejection_terminal(self):
        for i in range(11):self.event(str(i),symbol=f'A{i}TRY')
        s=self.worker.cycle();self.assertEqual(s['events'][-1]['master_result'],'REJECTED_MAX_POSITIONS')
        self.assertEqual(s['books']['MASTER']['account']['open_position_count'],10)
        self.assertGreaterEqual(float(s['books']['MASTER']['account']['cash_try']),0)
        self.assertEqual(len(self.worker.cycle()['events']),11)
    def test_old_sell_no_position_and_late_old_excluded(self):
        self.event('sell',side='SELL');s=self.worker.cycle()
        self.assertEqual(s['events'][-1]['master_result'],'NO_POSITION')
        row=self.row('late','RSI14','TESTTRY','BUY');row['executed_at_utc']='2026-09-25T01:00:00+00:00'
        self.rows.append(row);self.write();s=self.worker.cycle()
        self.assertEqual(s['events'][-1]['result'],'EXCLUDED_PRE_START_LATE_ROW')
        self.assertEqual(s['books']['MASTER']['account']['equity_try'],'10000.00')
    def test_rollover_atomic_and_stale_quotes(self):
        self.event('a');s=self.worker.cycle();equity=s['books']['MASTER']['account']['equity_try']
        self.time=datetime(2026,9,26,21,0,tzinfo=timezone.utc)
        s=self.worker.cycle();book=s['books']['MASTER']
        self.assertEqual(book['current_period']['start_equity_try'],equity)
        self.assertAlmostEqual(float(book['current_period']['spot_slot_budget_try']),round(float(equity)/10,2))
        self.assertEqual(len(self.worker.cycle()['books']['MASTER']['runtime_daily_records']),1)
        self.worker.fetch=lambda symbols:{}
        s=self.worker.cycle();self.assertEqual(s['state'],'DEGRADED');self.assertEqual(s['books']['MASTER']['account']['equity_try'],equity)
    def test_mutation_and_truncation_block_without_commit(self):
        self.event('a');self.worker.cycle();before=(self.base/STATE).read_bytes()
        self.rows[-1]['reference_price']='11';self.write()
        with self.assertRaisesRegex(ValueError,'MUTATED'):self.worker.cycle()
        self.assertEqual((self.base/STATE).read_bytes(),before)
        self.rows=self.rows[:1];self.write()
        with self.assertRaisesRegex(ValueError,'REMOVED'):self.worker.cycle()

if __name__=='__main__':unittest.main(verbosity=2)

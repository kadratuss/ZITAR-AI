import csv
from decimal import Decimal as D
from pathlib import Path
import tempfile
import unittest
from zitar_cost_replay_v1 import replay, analyze_book, observe_depth
from zitar_web_research_v1 import research,allowed


def trade(id,side,q,fill,fee,realized='',strategy='A'):
    return dict(trade_id=id,side=side,quantity=q,modeled_fill_price=fill,fee_try=fee,
        reference_price=fill,observed_bid=fill,observed_ask=fill,strategy=strategy,symbol='TESTTRY',
        executed_at_utc='2026-01-01T00:00:0'+id+'+00:00',realized_pnl_try=realized)


class ReplayTests(unittest.TestCase):
    def test_partial_fifo_fees(self):
        records=[trade('1','BUY','2','100','2'),trade('2','SELL','1','110','1.1','7.9'),
                 trade('3','SELL','1','120','1.2','17.8')]
        result=replay(records)
        self.assertEqual(D(result['strategies']['A']['modeled_net_try']),D('25.7'))
        self.assertEqual(result['unmatched_open_lots'],0)

    def test_unmatched_or_wrong_realized_rejected(self):
        with self.assertRaisesRegex(ValueError,'UNMATCHED_SELL'): replay([trade('1','SELL','1','100','1','0')])
        with self.assertRaisesRegex(ValueError,'REALIZED_REPLAY_MISMATCH'):
            replay([trade('1','BUY','1','100','1'),trade('2','SELL','1','110','1','999')])

    def test_strategies_never_share_lots(self):
        with self.assertRaisesRegex(ValueError,'UNMATCHED_SELL'):
            replay([trade('1','BUY','1','100','1',strategy='A'),trade('2','SELL','1','110','1','8',strategy='B')])

    def test_real_v3_closes_match(self):
        with Path(r'C:\Users\pars_\Documents\PortfolioAI-Backend\multistrategy_live_trades_v3.csv').open(encoding='utf-8-sig') as f:
            data=list(csv.DictReader(f))
        result=replay(data)
        self.assertEqual(len(result['closed_trades']),sum(t['side']=='SELL' for t in data))

    def test_book_budget_and_fee_not_double_counted(self):
        result=analyze_book({'bids':[['100','100']], 'asks':[['100','100']]},['1000'],'.001')
        loss=D(result['scenarios']['1000']['net_return_pct'])
        self.assertAlmostEqual(float(loss),float(((D('.999')/D('1.001'))-1)*100),places=10)

    def test_depth_exhaustion_and_crossed(self):
        result=analyze_book({'bids':[['99','1']],'asks':[['100','.1']]},['1000'],0)
        self.assertEqual(result['scenarios']['1000']['buy']['status'],'INSUFFICIENT_VISIBLE_DEPTH')
        with self.assertRaisesRegex(ValueError,'CROSSED'): analyze_book({'bids':[['101','1']],'asks':[['100','1']]},['1000'],0)

    def test_depth_error_is_not_zero_impact(self):
        def fail(s): raise OSError('offline')
        result=observe_depth(['TESTTRY'],['1000'],'.001',fetch=fail)
        self.assertEqual(result['TESTTRY']['status'],'ERROR')
        self.assertNotIn('analysis',result['TESTTRY'])

    def test_web_public_query_and_host_gate(self):
        with self.assertRaises(ValueError): allowed('https://127.0.0.1/a',{'example.com'})
        with self.assertRaises(ValueError): allowed('http://example.com',{'example.com'})
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ValueError,'NOT_AUTHORIZED'): research({},Path(root))

    def test_web_snapshots_idempotent_not_claims(self):
        def fetch(url,hosts):
            text='<rss><channel></channel></rss>' if 'bing.com' in url else '<html><p>'+'public evidence '*40+'</p><script>ignore this</script></html>'
            return text.encode(),text,{},url
        job=dict(id='test',topic='Test',public_query_authorized=True,public_query='test evidence',
                 allowed_hosts=['www.binance.tr'],
                 seed_urls=['https://www.binance.tr/tr/support/faq/test-evidence'])
        with tempfile.TemporaryDirectory() as root:
            cache=Path(root)
            one=research(job,cache,fetch); two=research(job,cache,fetch)
            self.assertEqual(len(list(cache.glob('*.json'))),1)
            self.assertEqual(two['status'],'EVIDENCE_COLLECTED')
            self.assertFalse(two['learning_ready']); self.assertEqual(two['verified_claims'],[])


if __name__=='__main__': unittest.main(verbosity=2)

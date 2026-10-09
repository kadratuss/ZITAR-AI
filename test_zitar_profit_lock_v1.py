import unittest
from decimal import Decimal as D
from zitar_profit_lock_v1 import update

class ProfitLockTests(unittest.TestCase):
    def position(self, side=1, margin='1000'):
        return dict(direction=side,quantity=str(D(margin)*3/100),entry='100',
                    initial_margin=margin,entry_fee='0',funding='0')

    def test_scaled_threshold_and_exit_both_directions(self):
        for margin in ('100','1000','10000'):
            for side in (1,-1):
                with self.subTest(margin=margin, side=side):
                    p=self.position(side,margin); qty=D(p['quantity'])
                    price=D('100')+side*(D(margin)*D('.05')/qty)
                    # Use ample precision to avoid threshold rounding.
                    price += side*D('.000000000000000000000001')
                    update(p,dict(bid=str(price),ask=str(price)),dict(fee_rate='0',slippage_rate='0'))
                    self.assertTrue(p['profit_lock_active'])
                    self.assertAlmostEqual(D(p['profit_lock_target_net']),D(margin)*D('.04'),places=18)
                    stop=p['profit_lock_stop']
                    self.assertTrue(update(p,dict(bid=stop,ask=stop),dict(fee_rate='0',slippage_rate='0')))

    def test_below_threshold(self):
        p=self.position();update(p,dict(bid='101',ask='101'),dict(fee_rate='0',slippage_rate='0'))
        self.assertFalse(p.get('profit_lock_active',False))

    def test_exact_threshold_and_persistent_restart(self):
        import json
        p=self.position();p['quantity']='50'
        execution=dict(fee_rate='0',slippage_rate='0')
        self.assertFalse(update(p,dict(bid='101',ask='101'),execution))
        self.assertEqual(D(p['profit_lock_target_net']),D('40'))
        p=json.loads(json.dumps(p))
        self.assertTrue(update(p,dict(bid='100.79',ask='100.79'),execution))

    def test_costs_funding_and_ratchet(self):
        for side in (1,-1):
            p=self.position(side);p.update(entry_fee='1.5',funding='-2')
            execution=dict(fee_rate='.0005',slippage_rate='.0002')
            price='103' if side==1 else '97'
            update(p,dict(bid=price,ask=price),execution)
            stop=D(p['profit_lock_stop']); fill=stop*(1-D('.0002')*side)
            net=D('30')*(fill-100)*side-D('3.5')-D('30')*fill*D('.0005')
            self.assertAlmostEqual(net,D(p['profit_lock_target_net']),places=20)
            price='104' if side==1 else '96'
            update(p,dict(bid=price,ask=price),execution)
            new=D(p['profit_lock_stop'])
            self.assertTrue(new>stop if side==1 else new<stop)
            update(p,dict(bid='100',ask='100'),execution)
            self.assertEqual(new,D(p['profit_lock_stop']))

if __name__=='__main__': unittest.main()

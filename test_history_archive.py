import unittest
from zitar_next.history_archive import funding_history
from zitar_next.market import HOUR


class HistoryTests(unittest.TestCase):
    @staticmethod
    def event(t):
        return dict(symbol='BTCUSDT',fundingTime=t,fundingRate='0.0001',markPrice='100')

    def test_full_page_is_followed_without_duplicate(self):
        rows=[self.event(i*HOUR) for i in range(1002)]
        calls=[]
        def request(path,params):
            calls.append(params['startTime'])
            return [r for r in rows if r['fundingTime']>=params['startTime']][:1000]
        result=funding_history('BTCUSDT',0,1002*HOUR,request)
        self.assertEqual(len(result),1002)
        self.assertEqual(calls,[0,999*HOUR+1])

    def test_missing_funding_rejected(self):
        with self.assertRaisesRegex(ValueError,'gap'):
            funding_history('BTCUSDT',0,20*HOUR,lambda *args:[self.event(0),self.event(10*HOUR)])

    def test_duplicate_across_pages_rejected(self):
        page=[self.event(i*HOUR) for i in range(1000)]
        calls=[]
        def request(*args):
            calls.append(1)
            return page if len(calls)==1 else [page[-1]]
        with self.assertRaises(ValueError): funding_history('BTCUSDT',0,1002*HOUR,request)


if __name__=='__main__': unittest.main()

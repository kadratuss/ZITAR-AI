import unittest
from zitar_next.open_strategy_signals import enrich,psar
class OpenTests(unittest.TestCase):
 def rows(self):return [[i*300000,str(100+i),'0','0',str(100+i),'1',(i+1)*300000-1] for i in range(120)]
 def bars(self):
  r=self.rows()
  for x in r:x[2]=str(float(x[4])+1);x[3]=str(float(x[4])-1)
  return r
 def test_coin_downcross(self):
  r=self.bars();r[-1][4]='212';r[-1][2]='220';r[-1][3]='211'
  self.assertEqual(enrich(r,36000000,'5m',dict(ST=0,wilder_rsi=60))['NEW_COIN'],1)
 def test_coin_rsi_gate(self):
  self.assertEqual(enrich(self.bars(),36000000,'5m',dict(ST=0,wilder_rsi=45))['NEW_COIN'],0)
 def test_unclosed_bar_ignored(self):
  r=self.bars();a=dict(ST=1,wilder_rsi=60);one=enrich(r,36000000,'5m',a);r.append([36000000,'1','99999','1','99999','1',36299999]);self.assertEqual(one,enrich(r,36000000,'5m',a))
 def test_sar_bull_then_reverse(self):
  h=[11,12,13,14,15,16,17,18,19,20,21];l=[x-2 for x in h];c=[x-1 for x in h];self.assertEqual(psar(h,l,c)[0],0);self.assertEqual(psar(h+[15],l+[10],c+[12])[0],-1)
 def test_sar_warmup(self):
  with self.assertRaises(ValueError):psar([1],[1],[1])
if __name__=='__main__':unittest.main()

"""Pinned ZITAR hourly signal functions; no runtime startup or production imports."""
from decimal import Decimal as D
def number(v):
 x=D(str(v))
 if not x.is_finite():raise ValueError('NONFINITE_NUMBER')
 return x

def signals(candles,ms,interval_ms=3600000):
 rows=sorted([r for r in candles if int(r[6])<ms],key=lambda r:int(r[0]))
 if len(rows)<60:raise ValueError('INSUFFICIENT_CLOSED_CANDLES')
 rows=rows[-150:]
 if len({r[0] for r in rows})!=len(rows) or any(int(b[0])-int(a[0])!=interval_ms for a,b in zip(rows,rows[1:])):raise ValueError('CANDLE_GAP')
 if ms-int(rows[-1][6])>interval_ms:raise ValueError('STALE_CANDLES')
 c=[number(r[4]) for r in rows]
 if min(c)<=0:raise ValueError('INVALID_CANDLES')
 def direction(x):return 1 if x>0 else -1 if x<0 else 0
 def ema(n):
  value=c[0];alpha=D(2)/D(n+1)
  for x in c[1:]:value=alpha*x+(1-alpha)*value
  return value
 sma=direction(sum(c[-20:])/20-sum(c[-50:])/50);em=direction(ema(12)-ema(26))
 deltas=[b-a for a,b in zip(c[-15:],c[-14:])];gain=sum(max(D(0),x) for x in deltas);loss=sum(max(D(0),-x) for x in deltas)
 rsi=D(100) if loss==0 and gain>0 else D(50) if gain==loss==0 else 100-100/(1+gain/loss)
 rs=1 if rsi<30 else -1 if rsi>70 else 0
 votes=sma+em+rs;baseline=1 if votes>=2 else -1 if votes<=-2 else 0
 candidate=sma if sma==em and ((sma==1 and 45<=rsi<=70) or (sma==-1 and 30<=rsi<=55)) else 0
 return {'SMA20_50':sma,'EMA12_26':em,'RSI14':rs,'BASELINE':baseline,'ZITAR_V1':candidate,'candle_close_ms':int(rows[-1][6]),'rsi_simple':str(rsi)}




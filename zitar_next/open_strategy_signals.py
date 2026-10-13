"""Documented-rule paper adaptations, not verified TradingView parity.
Coinrule: latest downward MA9 crossing; long-only. Supertrend uses existing
local ATR10 x3 implementation. PSAR uses .02/.02/.20. Shared 2% safety trail.
"""
from zitar_indicator_lab_signals_v1 import INTERVALS

def psar(high,low,close):
 if len(high)<3:raise ValueError('PSAR_WARMUP')
 up=close[1]>close[0];sar=low[0] if up else high[0];ep=max(high[:2]) if up else min(low[:2]);af=.02;direction=[]
 for i in range(2,len(high)):
  sar=sar+af*(ep-sar)
  if up:
   sar=min(sar,low[i-1],low[i-2])
   if low[i]<sar:up=False;sar=ep;ep=low[i];af=.02
   elif high[i]>ep:ep=high[i];af=min(.2,af+.02)
  else:
   sar=max(sar,high[i-1],high[i-2])
   if high[i]>sar:up=True;sar=ep;ep=high[i];af=.02
   elif low[i]<ep:ep=low[i];af=min(.2,af+.02)
  direction.append(1 if up else -1)
 return direction[-1] if len(direction)>1 and direction[-1]!=direction[-2] else 0,sar

def enrich(raw,ms,interval,a):
 rows=sorted((r for r in raw if int(r[6])<ms),key=lambda r:int(r[0]))[-500:]
 if len(rows)<100:raise ValueError('STRATEGY_WARMUP')
 c=[float(r[4]) for r in rows];h=[float(r[2]) for r in rows];l=[float(r[3]) for r in rows]
 ma9=sum(c[-9:])/9;previous=sum(c[-10:-1])/9
 coin=1 if sum(c[-50:])/50>sum(c[-100:])/100 and a['wilder_rsi']>50 and c[-2]>=previous and c[-1]<ma9 else 0
 sar,level=psar(h,l,c)
 return dict(a,NEW_COIN=coin,NEW_ST=a['ST'],NEW_SAR=sar,coin_exit=a['wilder_rsi']>70 or a['wilder_rsi']<30,sar_level=level)

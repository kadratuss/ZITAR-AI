"""Independent pivot/ATR hypothesis, not a replica of a protected indicator.

Pivots require two CLOSED bars to the right. Signals are timestamped at
confirmation, never moved backwards onto the pivot bar.
"""
from copy import deepcopy
import math
from zitar_confluence_v1 import RULES as RISK_RULES, ema, wilder, evaluate as shared_evaluate
from zitar_futures_paper_engine_v1 import fresh, digest

NAMES={'ZITAR_PIVOT_ATR_5M':300000,'ZITAR_PIVOT_ATR_15M':900000}
RULES=dict(RISK_RULES,version='PIVOT_ATR_V1',entry_reason='CONFIRMED_PIVOT_ATR_FLIP',
           pivot_left=2,pivot_right=2,trend_atr_period=10,trend_atr_factor=3,
           center='FIRST_PIVOT_THEN_TWO_THIRDS_OLD_ONE_THIRD_NEW',
           entry='NEW_TREND_FLIP_AND_EMA200',display_emas=[10,50,100,200],
           risk_note='Same ATR14 capped stop, BE, partial TP and daily limits as confluence; trend band is entry evidence')

def ensure(state,ms):
    for name,interval in NAMES.items():
        if name not in state['books']:
            b=deepcopy(fresh(ms,[])['books']['BASELINE'])
            b.update(started_ms=ms,cursors={},rules=deepcopy(RULES),rules_hash=digest(RULES),
                     execution_policy=deepcopy(RULES),interval_ms=interval,evaluations={},daily_limit='OPEN')
            state['books'][name]=b
        if state['books'][name]['rules_hash']!=digest(RULES):raise ValueError('PIVOT_RULES_CHANGED')

def confirmed_pivot(highs,lows,index):
    j=index-2
    if j<2:return None
    # Strict extrema: plateaus do not produce repeated pivots.
    high=all(highs[j]>highs[k] for k in range(j-2,j+3) if k!=j)
    low=all(lows[j]<lows[k] for k in range(j-2,j+3) if k!=j)
    if high and low:return (highs[j]+lows[j])/2
    return highs[j] if high else lows[j] if low else None

def signal(rows,ms,interval):
    rows=sorted((r for r in rows if int(r[6])<ms),key=lambda r:int(r[0]))
    if len(rows)<400:raise ValueError('WARMUP_400_CLOSED_BARS')
    if any(int(b[0])-int(a[0])!=interval for a,b in zip(rows,rows[1:])):raise ValueError('CANDLE_GAP')
    if ms-int(rows[-1][6])>interval:raise ValueError('STALE_CANDLE')
    values=[[float(r[i]) for i in (1,2,3,4,5)] for r in rows]
    if any(not all(math.isfinite(x) for x in v) or min(v[:4])<=0 or v[4]<0 or not v[2]<=min(v[0],v[3])<=max(v[0],v[3])<=v[1] for v in values):raise ValueError('INVALID_OHLCV')
    c=[v[3] for v in values];h=[v[1] for v in values];l=[v[2] for v in values]
    tr=[h[0]-l[0]]+[max(h[i]-l[i],abs(h[i]-c[i-1]),abs(l[i]-c[i-1])) for i in range(1,len(c))]
    atr=wilder(tr,10);center=None;lower=None;upper=None;trend=0;previous=0;confirmation=None
    for i in range(10,len(c)):
        pivot=confirmed_pivot(h,l,i)
        if pivot is not None:
            center=pivot if center is None else (2*center+pivot)/3
            confirmation=int(rows[i][6])
        previous=trend
        if center is None:continue
        raw_lower=center-3*atr[i];raw_upper=center+3*atr[i]
        if lower is None:lower=raw_lower;upper=raw_upper;continue
        trend=1 if c[i]>upper else -1 if c[i]<lower else trend
        lower=max(raw_lower,lower) if c[i-1]>lower else raw_lower
        upper=min(raw_upper,upper) if c[i-1]<upper else raw_upper
    averages={str(n):ema(c,n)[-1] for n in (10,50,100,200)}
    direction=trend if trend!=previous and ((trend==1 and c[-1]>averages['200']) or (trend==-1 and c[-1]<averages['200'])) else 0
    return dict(direction=direction,candle_close_ms=int(rows[-1][6]),atr=wilder(tr,14)[-1],
                trend_atr=atr[-1],trend=trend,previous_trend=previous,center=center,
                trend_band=lower if trend==1 else upper,pivot_confirmation_ms=confirmation,emas=averages)

def evaluate(state,market,quotes,ms,closed_now,errors):
    shared_evaluate(state,market,quotes,ms,closed_now,errors,names=NAMES,rules=RULES,signal_fn=signal)

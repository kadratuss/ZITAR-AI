"""Transparent local formulas; NOT a replica of TradingView Technical Ratings."""
import math, statistics

def sign(x):return 1 if x>0 else -1 if x<0 else 0
def ema(xs,n):
    out=[xs[0]];a=2/(n+1)
    for x in xs[1:]:out.append(a*x+(1-a)*out[-1])
    return out

def analyze(rows,now_ms,interval_ms=300000):
    rows=sorted([r for r in rows if int(r[6])<now_ms],key=lambda r:int(r[0]))[-200:]
    if len(rows)<100:raise ValueError('INSUFFICIENT_CLOSED_CANDLES')
    if any(int(b[0])-int(a[0])!=interval_ms for a,b in zip(rows,rows[1:])):raise ValueError('CANDLE_GAP')
    if now_ms-int(rows[-1][6])>interval_ms:raise ValueError('STALE_CANDLES')
    c=[float(r[4]) for r in rows];h=[float(r[2]) for r in rows];l=[float(r[3]) for r in rows];v=[float(r[5]) for r in rows]
    if any(not math.isfinite(x) for xs in [c,h,l,v] for x in xs for x in [x]) or min(c+l)<=0 or min(v)<0:raise ValueError('INVALID_CANDLES')
    if any(lo>cl or cl>hi for lo,cl,hi in zip(l,c,h)):raise ValueError('INVALID_OHLC')
    e12=ema(c,12);e26=ema(c,26);mac=[a-b for a,b in zip(e12,e26)];hist=mac[-1]-ema(mac,9)[-1]
    deltas=[b-a for a,b in zip(c,c[1:])];gain=sum(max(x,0) for x in deltas[:14])/14;loss=sum(max(-x,0) for x in deltas[:14])/14
    for x in deltas[14:]:gain=(gain*13+max(x,0))/14;loss=(loss*13+max(-x,0))/14
    rsi=100-100/(1+gain/loss) if loss else 100 if gain else 50
    span=max(h[-14:])-min(l[-14:]);stoch=100*(c[-1]-min(l[-14:]))/span if span else 50
    typical=[(a+b+d)/3 for a,b,d in zip(h,l,c)];mean=statistics.mean(typical[-20:]);dev=statistics.mean(abs(x-mean) for x in typical[-20:]);cci=(typical[-1]-mean)/(.015*dev) if dev else 0
    volume=sum(v[-20:]);vwma=sum(a*b for a,b in zip(c[-20:],v[-20:]))/volume if volume else c[-1]
    obv=sum(sign(c[i]-c[i-1])*v[i] for i in range(len(c)-20,len(c)))
    middle=statistics.mean(c[-20:]);sd=statistics.pstdev(c[-20:]);band=(c[-1]-middle)/(2*sd) if sd else 0
    breakout=1 if c[-1]>max(h[-21:-1]) else -1 if c[-1]<min(l[-21:-1]) else 0
    items=[('SMA20/50','trend',statistics.mean(c[-20:])-statistics.mean(c[-50:])),('EMA12/26','trend',e12[-1]-e26[-1]),('MACD12/26/9','trend',hist),
      ('RSI14 Wilder','momentum',rsi-55 if rsi>55 else rsi-45 if rsi<45 else 0),('Stochastic K14','momentum',stoch-60 if stoch>60 else stoch-40 if stoch<40 else 0),('CCI20','momentum',cci-100 if cci>100 else cci+100 if cci< -100 else 0),
      ('VWMA20','volume',c[-1]-vwma),('OBV change20','volume',obv),('Bollinger20/2 breakout','price',band-1 if band>1 else band+1 if band< -1 else 0),('Donchian20 breakout','price',breakout)]
    indicators=[dict(name=n,group=g,value=x,vote=sign(x)) for n,g,x in items]
    groups={g:sum(i['vote'] for i in indicators if i['group']==g)/sum(i['group']==g for i in indicators) for g in ['trend','momentum','volume','price']}
    score=sum(i['vote'] for i in indicators)/10;group_score=sum(groups.values())/4
    tr=[max(h[i]-l[i],abs(h[i]-c[i-1]),abs(l[i]-c[i-1])) for i in range(1,len(c))]
    atr=statistics.mean(tr[-14:])/c[-1]*100
    volbase=statistics.median(v[-21:-1]);volratio=v[-1]/volbase if volbase>0 else None
    move=(c[-1]/c[-2]-1)*100
    return dict(candle_close_ms=int(rows[-1][6]),indicators=indicators,groups=groups,majority=sign(score) if abs(score)>=.4 else 0,
      grouped=sign(group_score) if abs(group_score)>=.5 and sign(groups['trend'])==sign(group_score) else 0,
      single=indicators[0]['vote'],atr14_simple_pct=atr,move_5m_pct=move,volume_ratio=volratio,
      radar=volratio is not None and volratio>=3 and abs(move)>=1,radar_direction=sign(move),
      note='Local rules, not TradingView parity; closed candles only; ATR is a risk observation, not an extra vote.')

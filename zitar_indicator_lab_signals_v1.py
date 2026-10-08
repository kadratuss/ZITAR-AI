"""Deterministic local implementations; no claim of TradingView parity.
UT: ATR(10) Wilder x2 stop crossing. WT: ESA(10), deviation(10), CI,
EMA(21), SMA(4) signal; crosses beyond +/-53. ST: ATR(10) x3.
Squeeze: BB(20,2), KC(20,1.5 TR SMA), linear-regression momentum.
"""
import math

INTERVALS={'1h':3600000,'1m':60000,'5m':300000,'15m':900000,'4h':14400000}

def ema(xs,n):
    out=[xs[0]]; a=2/(n+1)
    for x in xs[1:]:out.append(a*x+(1-a)*out[-1])
    return out

def rma(xs,n):
    out=[None]*(n-1)+[sum(xs[:n])/n]
    for x in xs[n:]:out.append((out[-1]*(n-1)+x)/n)
    return out

def analyze(raw,ms,interval):
    step=INTERVALS[interval]
    rows=sorted((r for r in raw if int(r[6])<ms),key=lambda r:int(r[0]))[-500:]
    if len(rows)<220:raise ValueError('INSUFFICIENT_CLOSED_BARS')
    if any(int(b[0])-int(a[0])!=step for a,b in zip(rows,rows[1:])):raise ValueError('CANDLE_GAP')
    if not 0<=ms-int(rows[-1][6])<=step:raise ValueError('STALE_CANDLES')
    h=[float(r[2]) for r in rows];l=[float(r[3]) for r in rows];c=[float(r[4]) for r in rows];v=[float(r[5]) for r in rows]
    if any(not math.isfinite(x) or x<=0 for x in h+l+c) or any(not math.isfinite(x) or x<0 for x in v):raise ValueError('INVALID_BAR')
    if any(lo>cl or cl>hi for lo,cl,hi in zip(l,c,h)):raise ValueError('INVALID_OHLC')
    tr=[h[0]-l[0]]+[max(h[i]-l[i],abs(h[i]-c[i-1]),abs(l[i]-c[i-1])) for i in range(1,len(c))]
    atr=rma(tr,10); ut=[]; stops=[]; st=[]; upper=lower=0; direction=-1
    for i,x in enumerate(c):
        if atr[i] is None:ut.append(0);st.append(0);stops.append(x);continue
        loss=2*atr[i];prev=stops[-1] if i>9 else x-loss;pc=c[i-1]
        stop=max(prev,x-loss) if x>prev and pc>prev else min(prev,x+loss) if x<prev and pc<prev else x-loss if x>prev else x+loss
        ut.append(1 if pc<=prev and x>stop else -1 if pc>=prev and x<stop else 0);stops.append(stop)
        bu=(h[i]+l[i])/2+3*atr[i];bl=(h[i]+l[i])/2-3*atr[i]
        pu,pl=upper,lower
        upper=bu if i==9 or bu<pu or pc>pu else pu
        lower=bl if i==9 or bl>pl or pc<pl else pl
        old=direction
        direction=(1 if x>upper else -1) if old==-1 else (-1 if x<lower else 1)
        st.append(direction if direction!=old else 0)
    ap=[(a+b+d)/3 for a,b,d in zip(h,l,c)];esa=ema(ap,10);dev=ema([abs(a-b) for a,b in zip(ap,esa)],10)
    ci=[(a-b)/(.015*d) if d else 0 for a,b,d in zip(ap,esa,dev)];wt=ema(ci,21)
    sig=[sum(wt[max(0,i-3):i+1])/len(wt[max(0,i-3):i+1]) for i in range(len(wt))]
    wave=1 if wt[-2]<=sig[-2] and wt[-1]>sig[-1] and min(wt[-2:])<-53 else -1 if wt[-2]>=sig[-2] and wt[-1]<sig[-1] and max(wt[-2:])>53 else 0
    delta=[b-a for a,b in zip(c,c[1:])];g=sum(max(x,0) for x in delta[-14:]);loss=sum(max(-x,0) for x in delta[-14:]);rsi=100 if loss==0 and g else 50 if not loss else 100-100/(1+g/loss)
    pg=sum(max(x,0) for x in delta[-15:-1]);pl=sum(max(-x,0) for x in delta[-15:-1]);previous_simple=100 if pl==0 and pg else 50 if not pl else 100-100/(1+pg/pl)
    confirmed=1 if previous_simple<=30<rsi else -1 if previous_simple>=70>rsi else 0
    gains=rma([max(x,0) for x in delta],14);losses=rma([max(-x,0) for x in delta],14)
    def rs(g,l):return 100 if not l and g else 50 if not l else 100-100/(1+g/l)
    prev_rsi=rs(gains[-2],losses[-2]);wilder_rsi=rs(gains[-1],losses[-1])
    scalp=1 if prev_rsi<=30<wilder_rsi else -1 if prev_rsi>=70>wilder_rsi else 0
    squeeze=[]; momentum=[]
    for i in range(19,len(c)):
        window=c[i-19:i+1];mid=sum(window)/20;sd=(sum((x-mid)**2 for x in window)/20)**.5;rg=sum(tr[i-19:i+1])/20
        squeeze.append(2*sd<1.5*rg)
        momentum.append(c[i]-(max(h[i-19:i+1])+min(l[i-19:i+1])+2*mid)/4)
    ys=momentum[-20:];mean=sum(ys)/20;slope=sum((i-9.5)*(x-mean) for i,x in enumerate(ys))/665;mom=mean+slope*9.5
    release=squeeze[-2] and not squeeze[-1];vol=sum(v[-21:-1])/20
    sq=1 if release and mom>0 and c[-1]>max(h[-21:-1]) and v[-1]>=1.8*vol else -1 if release and mom<0 else 0
    bb_mid=sum(c[-20:])/20;bb_sd=(sum((x-bb_mid)**2 for x in c[-20:])/20)**.5
    bb_breakout=1 if release and c[-1]>bb_mid+2*bb_sd else -1 if release and c[-1]<bb_mid-2*bb_sd else 0
    return dict(bb_breakout=bb_breakout,bb_upper=bb_mid+2*bb_sd,bb_lower=bb_mid-2*bb_sd,bb_release=release,candle_ms=int(rows[-1][6]),UT=ut[-1],ST=st[-1],WT=wave,RSI=1 if rsi<30 else -1 if rsi>70 else 0,RSI_CONFIRM=confirmed,RSI_BASE=1 if rsi<30 else -1 if rsi>70 else 0,SCALP=scalp,wilder_rsi=wilder_rsi,previous_rsi=previous_simple,previous_wilder_rsi=prev_rsi,close=c[-1],ema200=ema(c,200)[-1],ema200_previous=ema(c,200)[-2],SQ=sq,trend=c[-1]>ema(c,200)[-1],rsi=rsi,wt=wt[-1],squeeze=squeeze[-1],volume_ratio=v[-1]/vol if vol else 0)

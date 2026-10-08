"""Frozen, isolated paper experiment; closed bars only, no execution API."""
from copy import deepcopy
from decimal import Decimal as D, ROUND_DOWN
import math
from zitar_futures_paper_engine_v1 import fresh, digest, number, open_position, close_position, mark

NAMES = {'ZITAR_CONFLUENCE_5M': 300000, 'ZITAR_CONFLUENCE_15M': 900000}
RULES = dict(version='CONFLUENCE_V1', leverage=3, fee_rate='0.00075', slippage_rate='0.001',
             volume_multiple=1.8, min_volume_24h_usdt=10000000, slots=10,
             vwap_anchor='UTC_DAY', ema=200, rsi=14, bb_length=20, bb_std=2,
             kc_length=20, kc_atr=20, kc_multiplier=1.5, atr_stop=1.5,
             max_stop_pct=1, break_even_pct=1.2, partial_pct=2, target_pct=2.5,
             trailing_pct=1, daily_profit_pct=3, daily_loss_pct=2,
             daily_basis='MARK_TO_MARKET_EQUITY_ISTANBUL', real_orders=False)

def ensure(state, ms):
    for name, interval in NAMES.items():
        if name not in state['books']:
            book = deepcopy(fresh(ms, [])['books']['BASELINE'])
            book.update(started_ms=ms, cursors={}, rules=deepcopy(RULES), rules_hash=digest(RULES),
                        execution_policy=deepcopy(RULES), interval_ms=interval, evaluations={}, daily_limit='OPEN')
            state['books'][name] = book
        if state['books'][name]['rules_hash'] != digest(RULES):
            raise ValueError('CONFLUENCE_RULES_CHANGED_NEW_VERSION_REQUIRED')

def ema(values, length):
    value = values[0]; out=[]; alpha=2/(length+1)
    for x in values:
        value += alpha*(x-value); out.append(value)
    return out

def wilder(values, length):
    if len(values)<length: raise ValueError('WARMUP')
    value=sum(values[:length])/length; out=[value]*length
    for x in values[length:]:
        value=(value*(length-1)+x)/length; out.append(value)
    return out

def signal(rows, ms, interval):
    rows=sorted((r for r in rows if int(r[6])<ms), key=lambda r:int(r[0]))
    if len(rows)<400: raise ValueError('WARMUP_400_CLOSED_BARS')
    if any(int(b[0])-int(a[0])!=interval for a,b in zip(rows,rows[1:])): raise ValueError('CANDLE_GAP')
    if ms-int(rows[-1][6])>interval: raise ValueError('STALE_CANDLE')
    vals=[[float(r[i]) for i in (1,2,3,4,5)] for r in rows]
    if any(not all(math.isfinite(x) for x in v) or min(v[:4])<=0 or v[4]<0 or not v[2]<=min(v[0],v[3])<=max(v[0],v[3])<=v[1] for v in vals): raise ValueError('INVALID_OHLCV')
    c=[v[3] for v in vals]; h=[v[1] for v in vals]; l=[v[2] for v in vals]; vol=[v[4] for v in vals]
    tr=[h[0]-l[0]]+[max(h[i]-l[i],abs(h[i]-c[i-1]),abs(l[i]-c[i-1])) for i in range(1,len(c))]
    atr=wilder(tr,14)[-1]; kc_atr=wilder(tr,20); kc=ema(c,20); trend=ema(c,200)[-1]
    delta=[b-a for a,b in zip(c,c[1:])]; gains=wilder([max(0,x) for x in delta],14); losses=wilder([max(0,-x) for x in delta],14)
    def rsi(i): return 50 if gains[i]==losses[i]==0 else 100 if losses[i]==0 else 100-100/(1+gains[i]/losses[i])
    r,prev=rsi(-1),rsi(-2)
    def bands(i):
        end=len(c)+i+1; window=c[end-20:end]; mid=sum(window)/20; sd=(sum((x-mid)**2 for x in window)/20)**.5
        return mid-2*sd,mid+2*sd
    lo,hi=bands(-1); plo,phi=bands(-2)
    squeezed=plo>kc[-2]-1.5*kc_atr[-2] and phi<kc[-2]+1.5*kc_atr[-2]
    release=squeezed and not (lo>kc[-1]-1.5*kc_atr[-1] and hi<kc[-1]+1.5*kc_atr[-1])
    anchor=int(rows[-1][0])//86400000
    session=[i for i,row in enumerate(rows) if int(row[0])//86400000==anchor]
    volume=sum(vol[i] for i in session)
    if volume<=0: raise ValueError('ZERO_SESSION_VOLUME')
    vwap=sum((h[i]+l[i]+c[i])/3*vol[i] for i in session)/volume
    avg=sum(vol[-21:-1])/20; spike=avg>0 and vol[-1]>=1.8*avg
    long=c[-1]>trend and c[-1]>vwap and 50<=r<=65 and r>prev and c[-1]>hi
    short=c[-1]<trend and c[-1]<vwap and 35<=r<=50 and r<prev and c[-1]<lo
    direction=(1 if long else -1 if short else 0) if spike and release else 0
    return dict(direction=direction, candle_close_ms=int(rows[-1][6]), atr=atr, rsi=r, vwap=vwap,
                ema200=trend, volume_spike=spike, squeeze_release=release,
                volume_ratio=vol[-1]/avg if avg else 0, long_gates=long, short_gates=short)

def partial(book, symbol, q, ms):
    p=book['positions'][symbol]; step=number(p['quantity_step']); qty=number(p['quantity'])
    cut=(qty/2/step).to_integral_value(rounding=ROUND_DOWN)*step
    if cut<=0 or qty-cut<=0: return
    ratio=cut/qty; remaining=deepcopy(p); piece=deepcopy(p)
    for key in ('quantity','margin','initial_margin','entry_fee','funding'):
        piece[key]=str(number(p[key])*ratio); remaining[key]=str(number(p[key])-number(piece[key]))
    piece['quantity']=str(cut); remaining['quantity']=str(qty-cut)
    book['positions'][symbol]=piece
    close_position(book,symbol,q,ms,'PARTIAL_TP_2PCT')
    remaining['partial_done']=True; book['positions'][symbol]=remaining

def risk(book, symbol, q, ms, value, maintenance):
    p=book['positions'][symbol]; side=p['direction']; entry=number(p['entry']); price=number(q['mark'])
    if value<=maintenance:
        close_position(book,symbol,q,ms,'MODEL_LIQUIDATION'); return True
    best=max(number(p['best_price']),price) if side==1 else min(number(p['best_price']),price)
    p['best_price']=str(best); gain=side*(best/entry-1)
    stop=number(p['trailing_stop'])
    if gain>=D('.012'):
        fee=number(RULES['fee_rate']); slip=number(RULES['slippage_rate']); qty=number(p['quantity'])
        # Solve net exit proceeds, including entry fee and accrued funding, for zero PnL.
        be=(entry+(number(p['entry_fee'])-number(p['funding']))/qty)/(1-fee)/(1-slip) if side==1 else (entry-(number(p['entry_fee'])-number(p['funding']))/qty)/(1+fee)/(1+slip)
        stop=max(stop,be) if side==1 else min(stop,be); p['break_even_active']=True
    p['trailing_stop']=str(stop)
    # A retracement takes precedence; do not award an earlier unobserved profit fill.
    if side*(price-stop)<=0:
        close_position(book,symbol,q,ms,'CONFLUENCE_STOP'); return True
    if side*(price/entry-1)>=D('.02') and not p.get('partial_done') and not p.get('funding_pending'):
        partial(book,symbol,q,ms); p=book['positions'][symbol]
    if side*(price/entry-1)>=D('.025'):
        close_position(book,symbol,q,ms,'TP_2_5PCT'); return True
    if p.get('partial_done'):
        trail=best*(1-D('.01')*side)
        p['trailing_stop']=str(max(stop,trail) if side==1 else min(stop,trail))
    return False

def evaluate(state, market, quotes, ms, closed_now, errors, names=None, rules=None, signal_fn=None):
    names=NAMES if names is None else names
    rules=RULES if rules is None else rules
    signal_fn=signal if signal_fn is None else signal_fn
    from zitar_market_discovery_v1 import liquidity
    selection=state.get('discovery_selection',{}); rows={r['symbol']:r for r in selection.get('rows',[])}
    for name,interval in names.items():
        b=state['books'][name]
        if b.get('retired_ms'):continue
        if not set(b['positions']).issubset(quotes): continue
        if ms-b['started_ms']>=86400000 and 'review_24h' not in b:
            b['review_24h']=dict(actual_ms=ms,started_ms=b['started_ms'],equity=b['equity'],
                                net_pnl=str(number(b['equity'])-10000),fees=b['fees_total'],
                                funding=b['funding_total'],open_positions=len(b['positions']),
                                exit_fills=len(b['closed']),quality=list(b['quality']),
                                accounting_pending=b.get('accounting_pending',False))
        if b.get('limit_day')!=b['period']: b.update(limit_day=b['period'],daily_limit='OPEN')
        change=number(b['equity'])/number(b['period_start'])-1
        if change<=D('-.02'): b['daily_limit']='LOSS_STOP'
        elif change>=D('.03') and b['daily_limit']=='OPEN': b['daily_limit']='PROFIT_LOCK'
        if b['daily_limit']=='LOSS_STOP':
            for symbol in list(b['positions']): close_position(b,symbol,quotes[symbol],ms,'DAILY_LOSS_STOP')
        b['daily_pnl_pct']=str(change*100)
        if b['daily_limit']!='OPEN' or b.get('accounting_pending'): continue
        for symbol,data in market.items():
            try:
                tf='5m' if interval==300000 else '15m'; a=signal_fn(data.get('timeframes',{}).get(tf,[]),ms,interval)
                candle=a['candle_close_ms']
                if candle<=b['cursors'].get(symbol,b['started_ms']): continue
                b['cursors'][symbol]=candle; reason='FILTERS_NOT_MET'; outcome='NO_ENTRY'
                if a['direction']:
                    row=rows.get(symbol,{})
                    if ms-candle>120000: reason='LATE_SIGNAL'
                    elif not 0<=ms-selection.get('updated_ms',0)<=180000: reason='STALE_SELECTION'
                    elif symbol not in selection.get('main',[]): reason='NOT_LIQUID_UNIVERSE'
                    elif row.get('volume_24h',0)<rules['min_volume_24h_usdt']: reason='LOW_24H_VOLUME'
                    elif (name,symbol) in closed_now: reason='CLOSED_THIS_CYCLE'
                    elif abs(number(quotes[symbol]['funding_rate']))>D('.001'): reason='HIGH_FUNDING'
                    elif not liquidity(data['depth'],float(number(b['slot'])*3))['eligible']: reason='LIQUIDITY_REJECT'
                    else:
                        reason=rules.get('entry_reason','FOUR_FACTOR_CONFIRMATION'); outcome=open_position(b,symbol,a['direction'],quotes[symbol],data['contract'],ms,reason)
                        if outcome=='OPENED':
                            p=b['positions'][symbol]; entry=number(p['entry']); distance=min(number(a['atr'])*D('1.5'),entry*D('.01'))
                            p.update(trailing_stop=str(entry-distance*p['direction']),timeframe=tf,quantity_step=data['contract']['step'],evidence=a)
                b['evaluations'][symbol]=dict(ms=ms,result=outcome,reason=reason,evidence=a)
                state['decisions'].append(dict(ms=ms,book=name,symbol=symbol,candle_close_ms=candle,direction=a['direction'],reason=reason,result=outcome))
            except (ValueError,KeyError) as exc:
                b['evaluations'][symbol]=dict(ms=ms,result='WAITING_DATA',reason=str(exc))

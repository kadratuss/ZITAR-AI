"""Separate long-only spot TRY paper books; never writes Master or V3."""
import json,time,threading
from pathlib import Path
from decimal import Decimal as D,ROUND_DOWN
from copy import deepcopy
from zitar_market_discovery_v1 import get,liquidity
from zitar_indicator_panel_v1 import analyze
from zitar_futures_paper_engine_v1 import day,digest
from zitar_full_paper_runtime_v1 import atomic_json
from zitar_paper_supervisor_v1 import FileLock
RULES={'version':'DISCOVERY_SPOT_V1','initial':10000,'slots':10,'fee':'.001','slippage':'.001','stop':'.02','interval':'5m','real_orders':False}
NAMES=('SINGLE','MAJORITY','GROUPED','RADAR')
def fresh(ms):
    return dict(started_ms=ms,policy=deepcopy(RULES),policy_hash=digest(RULES),heartbeat_ms=ms,books={n:dict(cash='10000',equity='10000',slot='1000',period=day(ms),period_start='10000',daily=[],positions={},closed=[],cursors={},fees='0') for n in NAMES},errors=[],decisions=[])
def close(b,s,q,ms,reason):
    p=b['positions'].pop(s);proceeds=D(p['qty'])*D(str(q['bid']))*(1-D(RULES['slippage']));fee=proceeds*D(RULES['fee']);net=proceeds-fee
    b.setdefault('reentry_after',{})[s]=ms+1800000
    b['cash']=str(D(b['cash'])+net);b['fees']=str(D(b['fees'])+fee);b['closed'].append(dict(p,symbol=s,closed_ms=ms,net_pnl=str(net-D(p['cost'])),exit_reason=reason))
def apply(s,market,selection,ms):
    if s['policy_hash']!=digest(RULES):raise ValueError('SPOT_DISCOVERY_POLICY_CHANGED')
    valid={k:v for k,v in market.items() if 0<=ms-v['ms']<=30000};errors=[]
    confirmations={c['symbol']:c for c in selection.get('early_candidates',[]) if c.get('stage')=='CONFIRMED' and 0<=ms-c.get('candle_ms',0)<=120000 and 0<=ms-c.get('confirmed_ms',0)<=120000}
    for name,b in s['books'].items():
        if b.get('retired_ms') or b.get('reset_pending'):
            for symbol in list(b['positions']):
                if symbol in valid:close(b,symbol,valid[symbol],ms,'USER_RESET' if b.get('reset_pending') else 'USER_STRATEGY_RETIRED')
                else:errors.append(symbol+':RETIREMENT_WAITING_QUOTE')
            b['equity']=str(D(b['cash'])+sum(D(p['value']) for p in b['positions'].values()))
            if not b['positions']:b['valuation_ms']=ms
            continue
        stopped=set()
        for symbol,p in list(b['positions'].items()):
            if symbol not in valid:errors.append(symbol+':MISSING_QUOTE');continue
            q=valid[symbol];p['best']=str(max(D(p['best']),D(str(q['bid']))));p['stop']=str(D(p['best'])*(1-D(RULES['stop'])))
            p['value']=str(D(p['qty'])*D(str(q['bid'])));p['quote_ms']=q['ms']
            if D(str(q['bid']))<=D(p['stop']):close(b,symbol,q,ms,'TRAILING_STOP');stopped.add(symbol)
        if not set(b['positions']).issubset(valid):continue
        b['equity']=str(D(b['cash'])+sum(D(p['value']) for p in b['positions'].values()));b['valuation_ms']=ms
        if day(ms)!=b['period']:
            b['daily'].append(dict(date=b['period'],start=b['period_start'],end=b['equity'],actual_rollover_ms=ms))
            b.update(period=day(ms),period_start=b['equity'],slot=str(D(b['equity'])/10))
        # Spot-only daily circuit breaker; equity is BID marked, thresholds latch until rollover.
        if b.get('limit_day')!=b['period']:
            b.update(limit_day=b['period'],daily_limit='OPEN')
        baseline=D(b['period_start'])
        change=D(b['equity'])/baseline-1 if baseline>0 else D('-1')
        if change<=D('-.02'): b['daily_limit']='LOSS_STOP'
        elif b['daily_limit']=='PROFIT_LOCK': b['daily_limit']='OPEN'  # Retire the old profit-entry cap.
        if b['daily_limit']=='LOSS_STOP':
            for symbol in list(b['positions']):close(b,symbol,valid[symbol],ms,'DAILY_LOSS_STOP')
            b['equity']=b['cash']
            continue
        candidates=sorted(valid.items(),key=lambda item:(-float((item[1].get('analysis') or {}).get('volume_ratio') or 0),-float((item[1].get('analysis') or {}).get('move_5m_pct') or 0),item[0])) if name=='RADAR' else valid.items()
        for symbol,q in candidates:
            a=q.get('rsi_analysis' if name=='RSI14' else 'analysis')
            if not a:continue
            if name=='RADAR':
                confirmed=confirmations.get(symbol)
                if not confirmed:continue
                a=dict(a,pump_confirmation=confirmed)
            candle=confirmed['candle_ms'] if name=='RADAR' else a['candle_close_ms']
            if candle<=b['cursors'].get(symbol,b.get('started_ms',s['started_ms'])):continue
            b['cursors'][symbol]=candle
            if ms-candle>120000:continue
            target=a['RSI14'] if name=='RSI14' else a[{'SINGLE':'single','MAJORITY':'majority','GROUPED':'grouped','RADAR':'radar_direction'}[name]]
            # A faded volume spike is absence of a new entry, not a reversal.
            exit_signal=False if name=='RADAR' else target!=1
            if symbol in b['positions'] and exit_signal:close(b,symbol,q,ms,'SIGNAL_CHANGED')
            if name=='RADAR':target=1
            result='NO_ENTRY';eligible=symbol in (confirmations if name=='RADAR' else selection.get('main',[])) and 0<=ms-selection.get('updated_ms',0)<=180000
            if not s.get('entries_paused',False) and b['daily_limit']=='OPEN' and (name!='RADAR' or ms>=b.get('reentry_after',{}).get(symbol,0)) and target==1 and eligible and symbol not in stopped and symbol not in b['positions'] and len(b['positions'])<(1 if name=='RADAR' else 10):
                budget=min(D(b['slot']),D(b['cash']));check=liquidity(q['depth'],float(budget)) if budget>0 else {'eligible':False}
                price=D(str(q['ask']))*(1+D(RULES['slippage']));step=D(q['step']);qty=(budget/(1+D(RULES['fee']))/price/step).to_integral_value(rounding=ROUND_DOWN)*step
                if check['eligible'] and qty>0 and qty>=D(q['min_qty']) and qty<=D(q['max_qty']) and qty*price>=D(q['min_notional']):
                    gross=qty*price;fee=gross*D(RULES['fee']);cost=gross+fee;b['cash']=str(D(b['cash'])-cost);b['fees']=str(D(b['fees'])+fee)
                    b['positions'][symbol]=dict(qty=str(qty),entry=str(price),cost=str(cost),best=str(price),stop=str(price*(1-D(RULES['stop']))),value=str(qty*D(str(q['bid']))),opened_ms=ms,quote_ms=q['ms'],timeframe='1h' if name=='RSI14' else '5m',evidence=a);result='OPENED'
            s['decisions'].append(dict(ms=ms,book=name,symbol=symbol,result=result,direction=target))
        b['equity']=str(D(b['cash'])+sum(D(p['value']) for p in b['positions'].values()))
    s.update(heartbeat_ms=ms,state='DEGRADED' if errors else 'RUNNING',errors=errors);return s

class Spot:
    def __init__(self,base):
        from zitar_candle_cache_v1 import CandleCache
        self.base=Path(base);self.path=self.base/'zitar_discovery_spot_v1.json'
        self.metadata={};self.metadata_at=0
        self.cache=CandleCache(lambda symbol,interval:get('spot','klines',{'symbol':symbol,'interval':interval,'limit':201},timeout=4),intervals=('5m','1h'))

    def cycle(self):
        from concurrent.futures import ThreadPoolExecutor
        ms=int(time.time()*1000);s=json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else fresh(ms)
        from zitar_strategy_selection_v1 import configure, prepare_reset, finish_reset
        configure(self.base,s,'spot',ms)
        prepare_reset(self.base,s,'spot')
        from zitar_spot_control_v1 import read_control
        control=read_control(self.base);s['entries_paused']=control['paused'];s['entry_control']=control
        errors=[]
        try:selection=json.loads((self.base/'zitar_market_discovery_v1.json').read_text(encoding='utf-8'))['markets']['spot']
        except (OSError,ValueError,KeyError) as exc:selection={};errors.append('SELECTION:'+str(exc))
        if time.time()-self.metadata_at>3600:
            try:self.metadata={r['symbol']:r for r in get('spot','exchangeInfo',timeout=4)['symbols']};self.metadata_at=time.time()
            except Exception as exc:errors.append('METADATA:'+str(exc))
        retained={k for book in s['books'].values() for k in book['positions']}
        selected=set(selection.get('main',[])+selection.get('radar',[])+[c['symbol'] for c in selection.get('early_candidates',[]) if c.get('stage')=='CONFIRMED']) if 0<=ms-selection.get('updated_ms',0)<=180000 else set()
        symbols=sorted(selected|retained,key=lambda symbol:(symbol not in retained,symbol))
        candles=self.cache.snapshot(symbols,ms)
        def one(symbol):
            try:
                depth=get('spot','depth',{'symbol':symbol,'limit':100},timeout=4)
                bid=D(str(depth['bids'][0][0]));ask=D(str(depth['asks'][0][0]))
                if not bid.is_finite() or not ask.is_finite() or bid<=0 or ask<bid:raise ValueError('INVALID_QUOTE')
                q=dict(depth=depth,bid=str(bid),ask=str(ask),ms=int(time.time()*1000))
                # Missing metadata/candles blocks entries, never quote-based stops.
                row=self.metadata.get(symbol)
                if row and row['status']=='TRADING':
                    try:
                        filters={x['filterType']:x for x in row['filters']};lot=filters['LOT_SIZE']
                        q.update(step=lot['stepSize'],min_qty=lot['minQty'],max_qty=lot['maxQty'],min_notional=filters.get('NOTIONAL',filters.get('MIN_NOTIONAL',{})).get('minNotional','0'))
                        if not D(q['step']).is_finite() or D(q['step'])<=0:raise ValueError('INVALID_LOT_STEP')
                    except Exception as exc:return symbol,q,'METADATA:'+str(exc)
                    if '5m' in candles[symbol]:
                        try:q['analysis']=analyze(candles[symbol]['5m'],int(time.time()*1000))
                        except Exception as exc:return symbol,q,'SIGNAL:'+str(exc)
                    if '1h' in candles[symbol]:
                        from zitar_futures_paper_engine_v1 import signals
                        try:q['rsi_analysis']=signals(candles[symbol]['1h'],int(time.time()*1000))
                        except (ValueError,KeyError):pass
                return symbol,q,None
            except Exception as exc:return symbol,None,type(exc).__name__+': '+str(exc)
        with ThreadPoolExecutor(max_workers=4) as pool:received=list(pool.map(one,symbols))
        market={symbol:q for symbol,q,error in received if q is not None}
        errors.extend(symbol+':'+error for symbol,q,error in received if error)
        s=apply(s,market,selection,int(time.time()*1000));s['errors'].extend(errors)
        if errors or not selection.get('updated_ms') or ms-selection.get('updated_ms',0)>180000:s['state']='DEGRADED'
        s['data_pipeline_version']='SPOT_CONFIRMED_PUMP_V4';s['signal_status']=self.cache.status(candles)
        finish_reset(self.base,s,'spot',int(time.time()*1000))
        atomic_json(self.path,s);return s

def loop(base):
    base=Path(base);lock=FileLock(base/'zitar_discovery_spot_v1.lock')
    if not lock.acquire():return
    worker=Spot(base)
    try:
        while True:
            try:worker.cycle()
            except Exception as exc:atomic_json(base/'zitar_discovery_spot_error_v1.json',{'ms':int(time.time()*1000),'error':str(exc)})
            time.sleep(15)
    finally:worker.cache.close();lock.close()

def start_worker(base):threading.Thread(target=loop,args=(base,),daemon=True,name='zitar-discovery-spot').start()

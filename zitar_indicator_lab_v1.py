"""Isolated paper laboratory. GET-only exchange data; owns only lab state/lock.
Read-only UI route on the existing dashboard, no credentials or order endpoints.
"""
import argparse,copy,json,os,threading,time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal as D
from zitar_full_paper_runtime_v1 import atomic_json
from zitar_paper_supervisor_v1 import FileLock
from zitar_futures_paper_runtime_v1 import get as fg,contracts
from zitar_market_discovery_v1 import get as mg,liquidity
from zitar_futures_paper_engine_v1 import fresh,open_position,close_position,mark,pnl,settle_funding,day,POLICY
from zitar_futures_funding_recovery_v1 import update_pending,reconcile_closed
from zitar_indicator_lab_signals_v1 import analyze,INTERVALS

STATE='zitar_indicator_lab_v1.json'
FUTURES_ONLY=(Path(__file__).parent/'zitar_futures_only.flag').exists()
# Label, market, closed signal interval, rule, leverage, trailing price distance.
SPECS={
 'RSI_BASE_SPOT':('RSI kontrol · 1sa','spot','1h','RSI_BASE',1,'.02'),
 'RSI_CONFIRM_SPOT':('RSI dönüş + bekleme · 1sa','spot','1h','RSI_CONFIRM',1,'.02'),
 'RSI_BASE_FUTURES':('RSI kontrol · 1sa','futures','1h','RSI_BASE',3,'.02'),
 'RSI_CONFIRM_FUTURES':('RSI dönüş + bekleme · 1sa','futures','1h','RSI_CONFIRM',3,'.02'),
 'UT5':('UT Bot · 5 dk','futures','5m','UT',3,'.02'),
 'UT15':('UT Bot · 15 dk','futures','15m','UT',3,'.02'),
 'ST15':('Supertrend · 15 dk','futures','15m','ST',3,'.02'),
 'RSI5':('RSI kontrol · 5 dk','futures','5m','RSI',3,'.02'),
 'RSI15':('RSI kontrol · 15 dk','futures','15m','RSI',3,'.02'),
 'WT15':('WaveTrend + 4sa trend · 15 dk','spot','15m','WT',1,'.02'),
 'SPOT_RSI15':('RSI kontrol · 15 dk','spot','15m','RSI',1,'.02'),
 'SQ5':('Squeeze / Pump · 5 dk','spot','5m','SQ',1,'.02'),
 'SCALP_RISK':('Scalping risk testi · 1 dk · 20×','futures','1m','SCALP_RISK',20,'.005'),
 'SCALP20':('RSI Scalping · 1 dk · 20×','futures','1m','SCALP',20,'.005'),
}

for rule,label in [('NEW_COIN','Coinrule kural uyarlaması'),('NEW_ST','SuperTrend ATR10 ×3 uyarlaması'),('NEW_SAR','Parabolic SAR uyarlaması')]:
    for interval in ('5m','15m','1h','4h'):
        SPECS[rule+'_'+interval]=(label+' · '+interval,'futures',interval,rule,3,'.02')

if FUTURES_ONLY:
    SPECS={k:v for k,v in SPECS.items() if v[1]=='futures'}

def initial(ms):
    books={}
    for key,(label,market,interval,rule,lev,stop) in SPECS.items():
        b=copy.deepcopy(fresh(ms,[])['books']['BASELINE'])
        b.update(label=label,market=market,interval=interval,rule=rule,stop_pct=stop,started_ms=ms,cursors={},decisions=[],daily_limit='OPEN',valuation_ms=0)
        b['execution_policy']=dict(POLICY,leverage=lev,fee_rate='.001' if market=='spot' else '.0005',slippage_rate='.001' if market=='spot' else '.0002')
        b['execution_policy'].update(signal_interval=interval,trailing_stop_price_pct=stop)
        if rule=='SCALP_RISK':
            from zitar_next.scalping_risk import RULES
            b.update(risk_rules=RULES.copy(),period_fees_start='0',diagnostic_only=True,approval='NOT_APPROVED_STRATEGY')
        if rule.startswith('NEW_'):b.update(diagnostic_only=True,approval='NOT_APPROVED_STRATEGY',source_parity='NOT_VERIFIED',adaptation='Shared 3x isolated model, 2% price safety trail, 10 equal slots; Coinrule long-only.')
        books[key]=b
    return dict(schema='INDICATOR_LAB_V1',specs=SPECS,started_ms=ms,heartbeat_ms=ms,last_success_ms=None,state='STARTING',books=books,universe={},errors=[],real_orders=False)

def cooling_down(book,symbol,candle):
    stops=[p['closed_ms'] for p in book.get('closed',[]) if p['symbol']==symbol and p.get('exit_reason') in ('TRAILING_STOP','MODEL_LIQUIDATION')]
    if not stops:return False
    step=INTERVALS[book['interval']]
    return candle<=((max(stops)//step)+3)*step


def apply_book(b,market,analyses,ms,before_entry=None):
    """Shared execution assumptions, isolated cash. Never trades an old candle."""
    if FUTURES_ONLY and b.get('market')=='spot':
        b.update(entries_paused=True,health='DISABLED_BY_USER');return
    quotes={s:d['quote'] for s,d in market.items() if 0<=ms-d['quote']['time']<=30000}
    closed_now=set()
    reconcile_closed(b,market,ms)
    b['accounting_pending']=any(p.get('funding_pending') for p in b['closed'])
    for symbol,p in list(b['positions'].items()):
        if symbol not in quotes:continue
        q=quotes[symbol];events=market[symbol].get('funding',[])
        settle_funding(b,symbol,events,ms);update_pending(p,events,ms)
        if p.get('funding_pending'):b['accounting_pending']=True
        elif q['next_funding']>ms:p['next_funding_ms']=q['next_funding']
        if b.get('reset_pending'):
            close_position(b,symbol,q,ms,'USER_RESET');closed_now.add(symbol);continue
        if b.get('retired_ms'):
            close_position(b,symbol,q,ms,'USER_STRATEGY_REMOVED');closed_now.add(symbol);continue
        value=D(p['margin'])+pnl(p,q['mark'])
        maintenance=D(p['quantity'])*D(q['mark'])*(D(POLICY['maintenance_rate'])+D(POLICY['liquidation_fee_rate']))
        best=max(D(p['best_price']),D(q['mark'])) if p['direction']==1 else min(D(p['best_price']),D(q['mark']))
        stop=best*(1-D(b['stop_pct'])*p['direction']);p.update(best_price=str(best),trailing_stop=str(stop))
        hit=D(q['mark'])<=stop if p['direction']==1 else D(q['mark'])>=stop
        reason='MODEL_LIQUIDATION' if b['market']=='futures' and value<=maintenance else 'TRAILING_STOP' if hit else None
        if reason:close_position(b,symbol,q,ms,reason);closed_now.add(symbol)
    if not set(b['positions']).issubset(quotes):b['health']='MISSING_POSITION_QUOTE';return
    mark(b,quotes);b['valuation_ms']=ms;b['health']='FUNDING_PENDING' if b['accounting_pending'] else 'OK'
    if b.get('retired_ms') or b.get('reset_pending'):return
    if b['rule']=='SCALP_RISK':
        b.setdefault('period_fees_start',b['fees_total'])
    if day(ms)!=b['period']:
        b['daily'].append(dict(date=b['period'],start=b['period_start'],end=b['equity'],return_pct=str((D(b['equity'])/D(b['period_start'])-1)*100),actual_rollover_ms=ms,quality=b['quality']))
        b.update(period=day(ms),period_start=b['equity'],slot=str(max(D(0),D(b['equity']))/10),daily_limit='OPEN',quality=[])
        if b['rule']=='SCALP_RISK':b['period_fees_start']=b['fees_total']
    # Isolated high-leverage test stops taking entries after a 2% daily loss.
    if b['rule']=='SCALP' and D(b['equity'])<=D(b['period_start'])*D('.98'):b['daily_limit']='LOSS_STOP'
    if b['rule']=='SCALP_RISK' and D(b['equity'])<=D(b['period_start'])*D('.99'):b['daily_limit']='LOSS_STOP'
    if b['daily_limit']=='LOSS_STOP':
        for symbol in list(b['positions']):close_position(b,symbol,quotes[symbol],ms,'DAILY_LOSS_STOP')
        mark(b,quotes);return
    for symbol,a in sorted(analyses.items()):
        if symbol not in quotes:continue
        candle=a['candle_ms']
        if candle<=b['cursors'].get(symbol,b['started_ms']):continue
        b['cursors'][symbol]=candle
        if ms-candle>min(120000,INTERVALS[b['interval']]):outcome='LATE_SIGNAL'
        else:
            target=a['SCALP' if b['rule']=='SCALP_RISK' else b['rule']];q=quotes[symbol];p=b['positions'].get(symbol)
            exit_signal=p and (target==-p['direction'] or (b['rule']=='RSI' and target!=p['direction']) or (b['rule'] in ('RSI_BASE','RSI_CONFIRM') and (a['rsi']>=50 if p['direction']==1 else a['rsi']<=50)) or (b['rule'] in ('SCALP','SCALP_RISK') and (a['wilder_rsi']>=50 if p['direction']==1 else a['wilder_rsi']<=50)))
            if b['rule']=='NEW_COIN' and p and a.get('coin_exit'):exit_signal=True
            if exit_signal:close_position(b,symbol,q,ms,'SIGNAL_EXIT');closed_now.add(symbol)
            if exit_signal and b['rule'] in ('NEW_ST','NEW_SAR'):closed_now.discard(symbol)
            if b['market']=='spot' and target<0:target=0
            if b['rule']=='WT' and target==1 and not a.get('higher_trend'):target=0
            cap=1 if b['rule']=='SQ' else 10
            if not target:outcome='NO_SIGNAL'
            elif b['rule']=='RSI_CONFIRM' and cooling_down(b,symbol,candle):outcome='STOP_COOLDOWN_3_BARS'
            elif symbol in closed_now:outcome='EXIT_THIS_CANDLE'
            elif len(b['positions'])>=cap:outcome='SLOTS_FULL'
            elif not market[symbol]['eligible']:outcome='LIQUIDITY_FILTER'
            elif abs(D(q['funding_rate']))>D('.001'):outcome='FUNDING_FILTER'
            else:
                blocked=before_entry(b,symbol,target,a,market[symbol],ms) if before_entry else None
                if blocked:outcome=blocked
                elif b['rule']=='SCALP_RISK':
                    from zitar_next.scalping_risk import enter
                    outcome=enter(b,symbol,target,q,market[symbol]['contract'],ms,candle)
                else:outcome=open_position(b,symbol,target,q,market[symbol]['contract'],ms,b['rule'])
                if outcome=='OPENED':
                    p=b['positions'][symbol];p.update(timeframe=b['interval'],evidence=a,trailing_stop=str(D(p['entry'])*(1-D(b['stop_pct'])*target)))
        b['decisions'].append(dict(ms=ms,symbol=symbol,candle_ms=candle,result=outcome))
    b['decisions']=b['decisions'][-500:];mark(b,quotes)

class Lab:
    def __init__(self,base):
        self.base=Path(base);self.path=self.base/STATE
        self.state=json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else initial(int(time.time()*1000))
        if FUTURES_ONLY:
            self.state['books']={k:b for k,b in self.state['books'].items() if b.get('market')!='spot'}
            self.state['specs']={k:v for k,v in self.state.get('specs',{}).items() if v[1]!='spot'}
            self.state.setdefault('universe',{})['spot']=[]
        existing=self.state.get('specs',{})
        if any(k not in SPECS or list(v)!=list(SPECS[k]) for k,v in existing.items()):raise ValueError('LAB_SPEC_CHANGED_ARCHIVE_REQUIRED')
        if set(existing)!=set(SPECS):
            archive=self.base/'paper_strategy_archives'/f'lab_rsi_experiment_{int(time.time()*1000)}.json';archive.parent.mkdir(parents=True,exist_ok=True);atomic_json(archive,self.state)
            additions=initial(int(time.time()*1000))
            for k in SPECS:
                if k not in self.state['books']:self.state['books'][k]=additions['books'][k]
            self.state['specs']=SPECS
        from zitar_research_experiment_v1 import Experiment
        self.experiment=Experiment(self.base)
        from zitar_momentum_experiment_v2 import Experiment as Momentum
        self.momentum=Momentum(self.base)
        from zitar_rsi_repair_v1 import Experiment as Repair
        self.repair=Repair(self.base)
        from zitar_bollinger_pair_v1 import Experiment as Bollinger
        self.bollinger=Bollinger(self.base)
        self.pool=ThreadPoolExecutor(max_workers=3);self.jobs={};self.cache={};self.retry={};self.meta={};self.meta_ms=0
    def candles(self,market,symbol,interval,ms):
        key=(market,symbol,interval);job=self.jobs.get(key)
        if job and job.done():
            del self.jobs[key]
            try:self.cache[key]=job.result();self.retry[key]=ms+5000
            except Exception:self.retry[key]=ms+30000
        rows=self.cache.get(key,[]);target=ms//INTERVALS[interval]*INTERVALS[interval]-1
        if rows and int(rows[-1][6])==target:return rows
        if key not in self.jobs and ms>=self.retry.get(key,0):
            def fetch():
                bars=mg(market,'klines',dict(symbol=symbol,interval=interval,limit=501),timeout=5)
                return [r for r in bars if int(r[6])<ms]
            self.jobs[key]=self.pool.submit(fetch)
        return None
    def cycle(self):
        ms=int(time.time()*1000);s=self.state;errors=[]
        selection=self.base/'zitar_indicator_lab_selection_v1.json'
        if selection.exists():
            chosen=json.loads(selection.read_text(encoding='utf-8')).get('enabled',[])
            if not s.get('selection_archive'):
                path=self.base/'paper_strategy_archives'/f'lab_roster_{ms}.json';path.parent.mkdir(parents=True,exist_ok=True);atomic_json(path,s);s['selection_archive']=str(path)
            for key,b in s['books'].items():
                if key not in chosen:b.setdefault('retired_ms',ms)
        from zitar_market_controls_v1 import read as read_control
        s['entry_control']=read_control(self.base,'scalping')
        for name in ('SCALP20','SCALP_RISK'):
            if name in s['books']:s['books'][name]['entries_paused']=s['entry_control']['paused']
        from zitar_strategy_selection_v1 import prepare_reset,finish_reset
        s['active_strategy_names']=[n for n,b in s['books'].items() if not b.get('retired_ms')]
        prepare_reset(self.base,s,'scalping')
        if not s['universe']:
            discovery=json.loads((self.base/'zitar_market_discovery_v1.json').read_text(encoding='utf-8'))
            selected={}
            for market in ('spot','futures'):
                section=discovery['markets'][market]
                if not 0<=ms-section['updated_ms']<180000:raise ValueError('DISCOVERY_STALE')
                selected[market]=[r['symbol'] for r in section['rows'] if r.get('eligible') and r.get('scope')=='MAIN'][:8]
                if not selected[market]:raise ValueError('EMPTY_UNIVERSE')
            s['universe']=selected
        if not self.meta or ms-self.meta_ms>3600000:
            futures=contracts(all_symbols=True);spot={}
            for row in ([] if FUTURES_ONLY else mg('spot','exchangeInfo')['symbols']):
                if row.get('status')!='TRADING':continue
                f={f['filterType']:f for f in row['filters']};lot=f['LOT_SIZE'];nf=f.get('NOTIONAL',f.get('MIN_NOTIONAL',{}))
                spot[row['symbol']]=dict(step=lot['stepSize'],min_qty=lot['minQty'],max_qty=lot['maxQty'],min_notional=nf.get('minNotional','0'))
            self.meta={'spot':spot,'futures':futures};self.meta_ms=ms
        premium={r['symbol']:r for r in fg('premiumIndex')}
        snapshots={};signals={};ready=expected=0
        for market,symbols in s['universe'].items():
            if FUTURES_ONLY and market=='spot':
                snapshots[market]={};continue
            snapshots[market]={}
            active=[b for b in s['books'].values() if b['market']==market and not b.get('retired_ms')]
            intervals={b['interval'] for b in active};intervals.update(('1h',) if (self.base/'zitar_two_rsi_only.flag').exists() else ('1h','15m'))
            if any(b['rule']=='WT' for b in active):intervals.add('4h')
            if not active and not self.experiment:
                symbols=sorted({p['symbol'] for b in s['books'].values() if b['market']==market for p in list(b['positions'].values())+[p for p in b['closed'] if p.get('funding_pending')]})
            for symbol in symbols:
                for interval in sorted(intervals):
                    expected+=1;rows=self.candles(market,symbol,interval,ms)
                    if rows:
                        try:
                            a=analyze(rows,ms,interval)
                            if any(b['rule'].startswith('NEW_') for b in active):
                                from zitar_next.open_strategy_signals import enrich
                                a=enrich(rows,ms,interval,a)
                            signals[(market,symbol,interval)]=a;ready+=1
                        except ValueError as e:errors.append(symbol+':'+str(e))
            def quote(symbol):
                depth=mg(market,'depth',dict(symbol=symbol,limit=100),timeout=4);now=int(time.time()*1000)
                # Depth impact must support the largest notional in this group.
                budget=max(float(b['slot'])*b['execution_policy']['leverage'] for b in s['books'].values() if b['market']==market)
                liq=liquidity(depth,budget)
                if market=='futures':
                    p=premium[symbol];q=dict(bid=str(liq['bid']),ask=str(liq['ask']),mark=p['markPrice'],time=int(p['time']),next_funding=int(p['nextFundingTime']),funding_rate=p['lastFundingRate'])
                    due=[p for b in list(s['books'].values())+list(self.experiment.state.get('books',{}).values())+list(self.momentum.state.get('books',{}).values())+list(self.repair.state.get('books',{}).values())+list(self.bollinger.state.get('books',{}).values()) if b['market']==market for p in list(b['positions'].values())+b['closed'] if p['symbol']==symbol and (p.get('funding_pending') or (not p.get('closed_ms') and p['next_funding_ms']<=now))]
                    funding=[]
                    if due:
                        funding=fg('fundingRate',dict(symbol=symbol,startTime=min(p['opened_ms'] for p in due)+1,endTime=now,limit=1000))
                        if len(funding)>=1000:raise ValueError('FUNDING_HISTORY_TRUNCATED')
                else:q=dict(bid=str(liq['bid']),ask=str(liq['ask']),mark=str(liq['bid']),time=now,next_funding=now+86400000000,funding_rate='0');funding=[]
                if now-q['time']>30000 or q['time']>now+5000:raise ValueError('STALE_QUOTE')
                return symbol,dict(quote=q,contract=self.meta[market][symbol],funding=funding,eligible=liq['eligible'],depth=depth)
            with ThreadPoolExecutor(max_workers=3) as pool:
                jobs={symbol:pool.submit(quote,symbol) for symbol in symbols}
                for symbol,job in jobs.items():
                    try:key,data=job.result();snapshots[market][key]=data
                    except Exception as e:errors.append(market+':'+symbol+':'+str(e))
        now=int(time.time()*1000)
        for b in s['books'].values():
            available={}
            for symbol in s['universe'][b['market']]:
                a=signals.get((b['market'],symbol,b['interval']))
                if not a:continue
                if b['rule']=='WT':
                    higher=signals.get(('spot',symbol,'4h'))
                    if not higher:continue
                    a=dict(a,higher_trend=higher['trend'])
                available[symbol]=a
            apply_book(b,snapshots[b['market']],available,now)
            if b.get('health')!='OK':errors.append(b['label']+':'+b.get('health','UNKNOWN'))
        try:
            if not (self.base/'zitar_two_rsi_only.flag').exists():self.experiment.cycle(snapshots,signals,s['universe'],now)
        except Exception as exc:errors.append('RESEARCH_EXPERIMENT:'+type(exc).__name__+':'+str(exc))
        try:
            if not (self.base/'zitar_two_rsi_only.flag').exists():self.bollinger.cycle(snapshots,signals,s['universe'],now)
        except Exception as exc:s['errors'].append('BOLLINGER_PAIR:'+str(exc))
        try:
            if not (self.base/'zitar_two_rsi_only.flag').exists():self.repair.cycle(snapshots,signals,s['universe'],now)
        except Exception as exc:s['errors'].append('RSI_REPAIR:'+str(exc))
        try:
            if not (self.base/'zitar_two_rsi_only.flag').exists():self.momentum.cycle(snapshots,signals,s['universe'],now)
        except Exception as exc:errors.append('MOMENTUM_EXPERIMENT:'+type(exc).__name__+':'+str(exc))
        finish_reset(self.base,s,'scalping',now)
        s.update(heartbeat_ms=now,pid=os.getpid(),errors=errors,state='DEGRADED' if errors else 'WARMING' if ready<expected else 'RUNNING',ready_intervals=ready,expected_intervals=expected)
        if not errors and ready==expected:s['last_success_ms']=now
        atomic_json(self.path,s)

def overview(base):
    path=Path(base)/STATE
    if not path.exists():return dict(state='STARTING',books={},errors=[],heartbeat_ms=0)
    result=json.loads(path.read_text(encoding='utf-8'))
    age=(int(time.time()*1000)-result.get('heartbeat_ms',0))/1000
    result['heartbeat_age_seconds']=age
    if not 0<=age<=60:
        result['recorded_state']=result.get('state');result['state']='STALE'
    from zitar_next.scalping_diagnostics import report
    for name in ('SCALP20','SCALP_RISK'):
        if name in result['books']:result['books'][name]['diagnostics']=report(result['books'][name])
    from zitar_next.scalping_diagnostics import report
    for name in ('SCALP20','SCALP_RISK'):
        if name in result['books']:result['books'][name]['diagnostics']=report(result['books'][name])
    return result

def loop(base):
    base=Path(base);lock=FileLock(base/'zitar_indicator_lab_v1.lock')
    if not lock.acquire():return
    lab=None
    try:
        lab=Lab(base);atomic_json(lab.path,lab.state)
        while True:
            try:lab.cycle()
            except Exception as e:
                lab.state.update(heartbeat_ms=int(time.time()*1000),state='DEGRADED',errors=[type(e).__name__+':'+str(e)]);atomic_json(lab.path,lab.state)
            time.sleep(5)
    finally:
        if lab:lab.pool.shutdown(wait=False,cancel_futures=True)
        lock.close()

_worker_guard=threading.Lock()
_workers={}

def start_worker(base):
    """Idempotent in-process watchdog; never kills another writer or resets cash."""
    base=Path(base).resolve();key=str(base)
    with _worker_guard:
        if key in _workers and _workers[key].is_alive():return _workers[key]
        def watch():
            while True:
                try:loop(base)
                except Exception as exc:
                    try:atomic_json(base/'zitar_indicator_lab_supervisor_v1.json',dict(ms=int(time.time()*1000),error=type(exc).__name__+':'+str(exc)))
                    except OSError:pass
                time.sleep(10)
        worker=threading.Thread(target=watch,name='zitar-indicator-lab-watchdog',daemon=True)
        _workers[key]=worker;worker.start();return worker

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',type=Path,default=Path(__file__).parent);loop(p.parse_args().base)

"""Versioned paper-only forward experiment. Never owns production accounts.
A paired ladder isolates one intervention per edge, not causal market proof.
Sampled quotes cannot reconstruct intracycle stops or exchange queue priority.
"""
import copy, gzip, hashlib, json, time
from pathlib import Path
from decimal import Decimal as D
from collections import defaultdict
from zitar_full_paper_runtime_v1 import atomic_json
from zitar_futures_paper_engine_v1 import fresh, POLICY, day
from zitar_market_discovery_v1 import liquidity
from zitar_market_controls_v1 import read

STATE='zitar_momentum_experiment_v2.json'
VARIANTS=('MOMENTUM','TREND','VOLUME','GUARD','STRESS')
MANIFEST=dict(version=2,interval='15m',trend_interval='1h',initial=10000,leverage={'spot':1,'futures':3},
 variants=VARIANTS,entry='Wilder RSI14 crosses 50; long <=65, short >=35',exit='opposite RSI50 cross or 2 percent trailing',
 trend='closed 1h close and EMA200 slope agree',volume_ratio=1.2,cooldown_bars=3,symbol_daily_stops=2,
 risk_per_trade=.0025,total_risk=.015,max_positions=10,
 minimum_days=30,minimum_closed=100,max_drawdown_pct=5,
 fee={'spot':.001,'futures':.0005},slippage={'spot':.001,'futures':.0002},
 limitations=['SAMPLED_STOPS','NO_PARTIAL_FILLS','NO_HISTORICAL_PARITY','PAPER_ONLY'])

HASH=hashlib.sha256(json.dumps(MANIFEST,sort_keys=True).encode()).hexdigest()

def initial(ms,universe):
    books={}
    for market in ('spot','futures'):
        for i,v in enumerate(VARIANTS):
            b=copy.deepcopy(fresh(ms,[])['books']['BASELINE'])
            policy=dict(POLICY,signal_interval='15m',leverage=MANIFEST['leverage'][market],fee_rate=str(MANIFEST['fee'][market]),
                        slippage_rate=str(MANIFEST['slippage'][market]*(2 if v=='STRESS' else 1)))
            b.update(label=v,variant=v,parent=VARIANTS[i-1] if i else None,market=market,interval='15m',rule='MOMENTUM',
                     stop_pct='.02',started_ms=ms,cursors={},decisions=[],daily_limit='OPEN',valuation_ms=0,execution_policy=policy)
            books[market+'_'+v]=b
    return dict(schema='MOMENTUM_EXPERIMENT_V2',manifest=MANIFEST,manifest_hash=HASH,started_ms=ms,universe=copy.deepcopy(universe),
                books=books,heartbeat_ms=0,cycles=0,gap_cycles=0,real_orders=False,state='STARTING')

def entry_gate(b,symbol,target,a,data,ms):
    stage=VARIANTS.index(b['variant'])
    if stage>=1:
        h=a.get('higher')
        if not h or not 0<=ms-h['candle_ms']<=3600000:return 'HIGHER_TIMEFRAME_NOT_READY'
        if target==1 and not(h['close']>h['ema200'] and h['ema200']>h['ema200_previous']):return 'TREND_FILTER'
        if target==-1 and not(h['close']<h['ema200'] and h['ema200']<h['ema200_previous']):return 'TREND_FILTER'
    if stage>=2 and a['volume_ratio']<1.2:return 'VOLUME_FILTER'
    if stage>=3:
        closed=[p for p in b['closed'] if p['symbol']==symbol]
        stops=[p for p in closed if p['exit_reason'] in ('TRAILING_STOP','MODEL_LIQUIDATION')]
        if stops and a['candle_ms']<=((stops[-1]['closed_ms']//900000)+3)*900000:return 'COOLDOWN_3_BARS'
        consecutive=0
        for p in reversed(closed):
            if day(p['closed_ms'])!=day(ms) or p['exit_reason'] not in ('TRAILING_STOP','MODEL_LIQUIDATION'):break
            consecutive+=1
        if consecutive>=2:return 'TWO_STOPS_TODAY'
    eq=max(D(0),D(b['equity']));lev=D(b['execution_policy']['leverage'])
    cost=D('.02')+2*(D(b['execution_policy']['fee_rate'])+D(b['execution_policy']['slippage_rate']))
    used=sum(D(p['quantity'])*D(p['entry'])*cost for p in b['positions'].values())
    risk=min(eq*D('.0025'),max(D(0),eq*D('.015')-used))
    if risk<=0:return 'RISK_LIMIT'
    b['slot']=str(min(eq/10,risk/(lev*cost)))
    if not data.get('depth') or not liquidity(data['depth'],float(D(b['slot'])*lev))['eligible']:return 'DEPTH_FILTER'
    return None

def advance(state,snapshots,signals,ms,paused=False,additional_gate=None):
    from zitar_indicator_lab_v1 import apply_book
    ready=0
    for b in state['books'].values():
        b['entries_paused']=paused;available={}
        for symbol in state['universe'][b['market']]:
            raw=signals.get((b['market'],symbol,'15m'))
            if not raw:continue
            a=dict(raw);r=a['wilder_rsi'];previous=a['previous_wilder_rsi']
            # Opposite crosses always exit, even outside the new-entry RSI band.
            crossing=1 if previous<=50<r else -1 if previous>=50>r else 0
            a.update(MOMENTUM=crossing,higher=signals.get((b['market'],symbol,'1h')))
            available[symbol]=a;ready+=1
        def gate(book,symbol,target,a,data,ms):
            if target==1 and a['wilder_rsi']>65 or target==-1 and a['wilder_rsi']<35:return 'OVEREXTENDED'
            blocked=entry_gate(book,symbol,target,a,data,ms)
            return blocked or (additional_gate(book,symbol,target,a,data,ms) if additional_gate else None)
        data={k:dict(v,eligible=True) for k,v in snapshots.get(b['market'],{}).items()}
        apply_book(b,data,available,ms,before_entry=gate)
    gap=bool(state.get('heartbeat_ms') and ms-state['heartbeat_ms']>30000)
    state['gap_cycles']+=int(gap);state['cycles']+=1;state['heartbeat_ms']=ms
    expected=sum(len(state['universe'][b['market']]) for b in state['books'].values())
    state.update(ready_intervals=ready,expected_intervals=expected)
    state['state']='DEGRADED' if gap or any(b.get('health')!='OK' for b in state['books'].values()) else 'WARMING' if ready<expected else 'RUNNING'

def metrics(b,ms):
    closed=b['closed'];values=[float(p['net_pnl']) for p in closed]
    symbol=defaultdict(float);days=defaultdict(float)
    for p in closed:
        symbol[p['symbol']]+=float(p['net_pnl']);days[day(p['closed_ms'])]+=float(p['net_pnl'])
    def concentration(group):
        gains=[max(0,v) for v in group.values()];return max(gains)/sum(gains) if sum(gains)>0 else None
    age=(ms-b['started_ms'])/86400000;n=len(closed);net=float(b['equity'])-10000
    issues=[]
    if age<30:issues.append('30 gün tamamlanmadı')
    if n<100:issues.append('100 kapanmış işlem yok')
    if not values or sum(values)<=0:issues.append('Net kapanmış işlem beklentisi pozitif değil')
    if float(b.get('max_drawdown_pct',0))>5:issues.append('Azami düşüş %5 bütçesini aştı')
    for label,share in [('Sembol',concentration(symbol)),('Gün',concentration(days))]:
        if share is None or share>.4:issues.append(label+' kazanç yoğunlaşması kriteri geçmedi')
    if b.get('health')!='OK':issues.append('Veri/muhasebe sağlığı doğrulanmadı')
    return dict(net=net,return_pct=net/100,closed=n,open=len(b['positions']),days=age,
                expectancy=sum(values)/n if n else None,win_rate=100*sum(v>0 for v in values)/n if n else None,
                max_drawdown_pct=float(b.get('max_drawdown_pct',0)),symbol_concentration=concentration(symbol),
                day_concentration=concentration(days),issues=issues,
                verdict='KANIT_YETERSIZ' if issues else 'EK_DOGRULAMA_ADAYI',automatic_promotion=False)

class Experiment:
    def __init__(self,base):
        self.base=Path(base);self.path=self.base/STATE
        self.state=json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {}
        if self.state and self.state.get('manifest_hash')!=HASH:raise ValueError('EXPERIMENT_VERSION_CHANGED_ARCHIVE_REQUIRED')
    def cycle(self,snapshots,signals,universe,ms):
        if not self.state:self.state=initial(ms,universe)
        if self.state['universe']!=universe:raise ValueError('EXPERIMENT_UNIVERSE_CHANGED')
        from zitar_strategy_selection_v1 import prepare_reset,finish_reset
        self.state['active_strategy_names']=list(self.state['books'])
        prepare_reset(self.base,self.state,'momentum')
        paused=read(self.base,'momentum')['paused']
        # Write inputs BEFORE executing; no fabricated recoveries if disk recording fails.
        folder=self.base/'momentum_experiment_inputs'/str(self.state['started_ms']);folder.mkdir(parents=True,exist_ok=True)
        record=dict(ms=ms,started_ms=self.state['started_ms'],universe=self.state['universe'],manifest_hash=HASH,paused=paused,snapshots=snapshots,
                    signals=[dict(market=k[0],symbol=k[1],interval=k[2],analysis=v) for k,v in signals.items() if k[2] in ('1h','15m')])
        try:
            with gzip.open(folder/(day(ms)+'.jsonl.gz'),'at',encoding='utf-8') as stream:
                stream.write(json.dumps(record,separators=(',',':'))+'\n')
        except OSError:
            advance(self.state,snapshots,signals,ms,paused=True)
            self.state.update(state='DEGRADED',recording_error='INPUT_RECORD_FAILED_ENTRIES_PAUSED')
            atomic_json(self.path,self.state)
            raise
        advance(self.state,snapshots,signals,ms,paused)
        pending=self.state.get('pending_active_reset_id')
        finish_reset(self.base,self.state,'momentum',ms)
        if pending and not self.state.get('pending_active_reset_id'):
            self.state.update(cycles=0,gap_cycles=0,state='STARTING')
        self.state['entry_control']=dict(paused=paused)
        atomic_json(self.path,self.state)

def overview(base):
    path=Path(base)/STATE
    if not path.exists():return dict(state='NOT_STARTED',books={},message='Motor yeniden başlatılınca deney oluşturulacak.')
    s=json.loads(path.read_text(encoding='utf-8'));ms=int(time.time()*1000)
    s['heartbeat_age_seconds']=(ms-s.get('heartbeat_ms',0))/1000
    if not 0<=s['heartbeat_age_seconds']<=30:s['state']='STALE'
    s['evaluation']={k:metrics(b,ms) for k,b in s['books'].items()}
    for k,b in s['books'].items():
        slip=D(b['execution_policy']['slippage_rate']);price=D(0);fees=D(0);funding=D(0);slippage=D(0)
        for p in b['closed']:
            qty=D(p['quantity']);direction=D(p['direction']);entry=D(p['entry']);exit_price=D(p['exit'])
            price+=qty*(exit_price-entry)*direction;fees+=D(p['entry_fee'])+D(p['exit_fee']);funding+=D(p['funding'])
            slippage+=qty*direction*(entry-entry/(1+slip*direction)+exit_price/(1-slip*direction)-exit_price)
        s['evaluation'][k]['costs']=dict(closed_price_pnl=str(price),closed_fees=str(fees),closed_funding=str(funding),embedded_slippage_estimate=str(slippage),note='Kayma fiyat PnL içinde; tekrar düşülmez. Açık pozisyon maliyetleri bu ayrımda yok.')
    for m in s['evaluation'].values():
        if s['state']!='RUNNING' or s.get('recording_error'):
            m['issues'].append('Çalışan çevrim veya kayıt sürekliliği doğrulanmadı');m['verdict']='KANIT_YETERSIZ'
        m['issues'].append('Dış doğrulama ve kısmi dolum modeli tamamlanmadı')
        m['automatic_promotion']=False
    for market in ('spot','futures'):
        baseline=s['evaluation'][market+'_GUARD'];stress=s['evaluation'][market+'_STRESS']
        stress['net_difference_vs_normal_slip']=stress['net']-baseline['net']
    return s

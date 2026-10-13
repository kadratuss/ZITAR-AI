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

STATE='zitar_research_experiment_v1.json'
VARIANTS=('SIMPLE','WILDER','CONFIRM','COOLDOWN','TWO_STOP','RISK','REGIME','STRESS')
MANIFEST=dict(version=1,interval='1h',initial=10000,leverage={'spot':1,'futures':3},
    variants=VARIANTS,stop_price_pct=.02,exit_rsi=50,cooldown_bars=3,
    symbol_daily_stops=2,risk_per_trade=.0025,total_risk=.015,max_positions=10,
    minimum_days=30,minimum_closed=100,max_drawdown_pct=5,
    max_positive_symbol_share=.4,max_positive_day_share=.4,
    fee={'spot':.001,'futures':.0005},slippage={'spot':.001,'futures':.0002},
    stress_slippage_multiplier=2,execution='sampled_bid_ask_plus_fixed_slippage_full_fill',
    limitations=['INTRACYCLE_PATH_UNKNOWN','PARTIAL_FILLS_NOT_MODELED','TRADINGVIEW_EXPORT_NOT_VALIDATED',
                 'UNSEEN_HISTORICAL_VALIDATION_PENDING','FIXED_UNIVERSE_SELECTION_BIAS'])
HASH=hashlib.sha256(json.dumps(MANIFEST,sort_keys=True).encode()).hexdigest()

def initial(ms,universe):
    books={}
    for market in ('spot','futures'):
        for i,v in enumerate(VARIANTS):
            b=copy.deepcopy(fresh(ms,[])['books']['BASELINE'])
            policy=dict(POLICY,leverage=MANIFEST['leverage'][market],fee_rate=str(MANIFEST['fee'][market]),
                        slippage_rate=str(MANIFEST['slippage'][market]*(2 if v=='STRESS' else 1)))
            b.update(label=v,variant=v,parent=VARIANTS[i-1] if i else None,market=market,interval='1h',rule='RSI_BASE',
                     stop_pct='.02',started_ms=ms,cursors={},decisions=[],daily_limit='OPEN',valuation_ms=0,execution_policy=policy)
            books[market+'_'+v]=b
    return dict(schema='RESEARCH_EXPERIMENT_V1',manifest=MANIFEST,manifest_hash=HASH,started_ms=ms,universe=copy.deepcopy(universe),
                books=books,heartbeat_ms=0,cycles=0,gap_cycles=0,real_orders=False,state='STARTING')

def entry_gate(b,symbol,target,a,data,ms):
    stage=VARIANTS.index(b['variant'])
    closed=[p for p in b['closed'] if p['symbol']==symbol]
    if stage>=3:
        stops=[p['closed_ms'] for p in closed if p['exit_reason'] in ('TRAILING_STOP','MODEL_LIQUIDATION')]
        if stops and a['candle_ms']<=((max(stops)//3600000)+3)*3600000:return 'STOP_COOLDOWN_3_BARS'
    if stage>=4:
        consecutive=0
        for p in reversed(closed):
            if day(p['closed_ms'])!=day(ms):break
            if p['exit_reason'] not in ('TRAILING_STOP','MODEL_LIQUIDATION'):break
            consecutive+=1
        if consecutive>=2:return 'TWO_STOPS_TODAY'
    if stage>=6:
        if target==1 and not (a['close']>a['ema200'] and a['ema200']>a['ema200_previous']):return 'REGIME_FILTER'
        if target==-1 and not (a['close']<a['ema200'] and a['ema200']<a['ema200_previous']):return 'REGIME_FILTER'
    eq=max(D(0),D(b['equity']));lev=D(b['execution_policy']['leverage'])
    fee=D(b['execution_policy']['fee_rate']);slip=D(b['execution_policy']['slippage_rate'])
    # Cost-aware stop risk estimate; gaps can exceed the estimate.
    risk_fraction=D('.02')+2*(fee+slip)
    slot=eq/10
    if stage>=5:
        used=sum(D(p['quantity'])*D(p['entry'])*risk_fraction for p in b['positions'].values())
        remaining=max(D(0),eq*D('.015')-used)
        allowed=min(eq*D('.0025'),remaining)
        if allowed<=0:return 'TOTAL_RISK_LIMIT'
        slot=min(slot,allowed/(lev*risk_fraction))
    b['slot']=str(slot)
    depth=data.get('depth')
    if not depth:return 'DEPTH_MISSING'
    if not liquidity(depth,float(slot*lev))['eligible']:return 'EXPERIMENT_DEPTH_FILTER'
    return None

def advance(state,snapshots,signals,ms,paused=False):
    from zitar_indicator_lab_v1 import apply_book
    for b in state['books'].values():
        b['entries_paused']=paused
        available={}
        for symbol in state['universe'][b['market']]:
            raw=signals.get((b['market'],symbol,'1h'))
            if not raw:continue
            a=dict(raw);stage=VARIANTS.index(b['variant'])
            r=a['rsi'] if stage==0 else a['wilder_rsi']
            prev=a['previous_rsi'] if stage==0 else a['previous_wilder_rsi']
            target=(1 if r<30 else -1 if r>70 else 0) if stage<2 else (1 if prev<=30<r else -1 if prev>=70>r else 0)
            a.update(rsi=r,RSI_BASE=target);available[symbol]=a
        # Re-evaluate liquidity at this account's budget, not legacy 20x budget.
        data={k:dict(v,eligible=True) for k,v in snapshots.get(b['market'],{}).items()}
        apply_book(b,data,available,ms,before_entry=entry_gate)
    gap=bool(state.get('heartbeat_ms') and ms-state['heartbeat_ms']>30000)
    state['gap_cycles']+=int(gap);state['cycles']+=1;state['heartbeat_ms']=ms
    state['state']='DEGRADED' if gap or any(b.get('health')!='OK' for b in state['books'].values()) else 'RUNNING'

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
        prepare_reset(self.base,self.state,'research')
        paused=read(self.base,'research')['paused']
        # Write inputs BEFORE executing; no fabricated recoveries if disk recording fails.
        folder=self.base/'research_experiment_inputs'/str(self.state['started_ms']);folder.mkdir(parents=True,exist_ok=True)
        record=dict(ms=ms,started_ms=self.state['started_ms'],universe=self.state['universe'],manifest_hash=HASH,paused=paused,snapshots=snapshots,
                    signals=[dict(market=k[0],symbol=k[1],interval=k[2],analysis=v) for k,v in signals.items() if k[2]=='1h'])
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
        finish_reset(self.base,self.state,'research',ms)
        if pending and not self.state.get('pending_active_reset_id'):
            self.state.update(cycles=0,gap_cycles=0,state='STARTING')
        self.state['entry_control']=dict(paused=paused)
        atomic_json(self.path,self.state)

def overview(base):
    path=Path(base)/STATE
    if not path.exists():return dict(state='NOT_STARTED',books={},message='Motor yeniden başlatılınca deney oluşturulacak.')
    s=json.loads(path.read_text(encoding='utf-8'));ms=int(time.time()*1000)
    if (Path(base)/'zitar_futures_only.flag').exists():
        s['books']={k:b for k,b in s['books'].items() if b.get('market')=='futures'}
    s['heartbeat_age_seconds']=(ms-s.get('heartbeat_ms',0))/1000
    if not 0<=s['heartbeat_age_seconds']<=30:s['state']='STALE'
    s['evaluation']={k:metrics(b,ms) for k,b in s['books'].items()}
    for m in s['evaluation'].values():
        if s['state']!='RUNNING' or s.get('recording_error'):
            m['issues'].append('Çalışan çevrim veya kayıt sürekliliği doğrulanmadı');m['verdict']='KANIT_YETERSIZ'
        m['issues'].append('Dış doğrulama ve kısmi dolum modeli tamamlanmadı')
        m['automatic_promotion']=False
    for market in {b['market'] for b in s['books'].values()}:
        baseline=s['evaluation'].get(market+'_REGIME');stress=s['evaluation'].get(market+'_STRESS')
        if baseline is None or stress is None:continue
        stress['net_difference_vs_normal_slip']=stress['net']-baseline['net']
    return s

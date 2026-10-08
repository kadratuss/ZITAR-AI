"""Dynamic universe experiments, separate from frozen legacy comparisons."""
from copy import deepcopy
from zitar_futures_paper_engine_v1 import fresh,digest,open_position,close_position,number
from zitar_indicator_panel_v1 import analyze
from zitar_market_discovery_v1 import liquidity
NAMES=('DISCOVERY_SINGLE','DISCOVERY_MAJORITY','DISCOVERY_GROUPED','DISCOVERY_RADAR')
SPEC={'version':'DISCOVERY_FUTURES_V1','interval':'5m','leverage':'existing paper leverage','slots':10,'closed_candle_only':True,'max_source_age_ms':180000,'max_spread_bps':20,'max_impact_bps':10,'max_funding':0.001,'promotion':False}
def ensure(state,ms):
    if 'discovery_spec' not in state:
        if any(n in state['books'] for n in NAMES):raise ValueError('PARTIAL_DISCOVERY_STATE')
        state['discovery_spec']={'hash':digest(SPEC),'started_ms':ms,'rules':deepcopy(SPEC)}
        for n in NAMES:
            b=deepcopy(fresh(ms,[])['books']['BASELINE']);b.update(started_ms=ms,cursors={},rules=deepcopy(SPEC));state['books'][n]=b
    if state['discovery_spec']['hash']!=digest(SPEC):raise ValueError('DISCOVERY_RULES_CHANGED')
def evaluate(state,market,quotes,ms,closed_now,errors):
    if not any(n in state['books'] and not state['books'][n].get('retired_ms') for n in NAMES):return
    selection=state.get('discovery_selection',{})
    selected=set(selection.get('main',[]));radar=set(selection.get('radar',[]))
    valid_selection=0<=ms-selection.get('updated_ms',0)<=SPEC['max_source_age_ms']
    for symbol,data in market.items():
        if symbol not in quotes:continue
        try:
            a=analyze(data['timeframes']['5m'],ms);candle=a['candle_close_ms'];q=quotes[symbol]
            for name in NAMES:
                b=state['books'][name]
                if b.get('retired_ms'):continue
                old=b['cursors'].get(symbol,b['started_ms'])
                if candle<=old:continue
                b['cursors'][symbol]=candle
                if ms-candle>120000:continue
                target=a[{'DISCOVERY_SINGLE':'single','DISCOVERY_MAJORITY':'majority','DISCOVERY_GROUPED':'grouped','DISCOVERY_RADAR':'radar_direction'}[name]]
                if name=='DISCOVERY_RADAR' and not a['radar']:target=0
                p=b['positions'].get(symbol)
                if p and p['direction']!=target:close_position(b,symbol,q,ms,'SIGNAL_CHANGED')
                reason='SIGNAL';result='NO_ENTRY'
                if (name,symbol) in closed_now:reason='STOP_THIS_CYCLE'
                elif not valid_selection:reason='STALE_SELECTION'
                elif symbol not in (radar if name=='DISCOVERY_RADAR' else selected):reason='NOT_SELECTED'
                elif not set(b['positions']).issubset(quotes):reason='MISSING_MARK'
                elif target:
                    from zitar_futures_paper_engine_v1 import POLICY
                    check=liquidity(data['depth'],float(number(b['slot'])*number(POLICY['leverage'])))
                    if not check['eligible']:reason='LIQUIDITY_REJECT'
                    elif abs(number(q['funding_rate']))>number('0.001'):reason='HIGH_FUNDING'
                    else:
                        result=open_position(b,symbol,target,q,data['contract'],ms,name)
                        if result=='OPENED':b['positions'][symbol].update(timeframe='5m',indicator_evidence=a)
                state['decisions'].append(dict(ms=ms,book=name,symbol=symbol,candle_close_ms=candle,direction=target,reason=reason,result=result))
        except (ValueError,KeyError) as exc:errors.append('DISCOVERY:'+symbol+':'+str(exc))

"""User-selected paper roster. Archives before retiring; never deletes history."""
import json
from copy import deepcopy
from zitar_full_paper_runtime_v1 import atomic_json

KEEP_FUTURES=('RSI14','DISCOVERY_RADAR','DISCOVERY_SINGLE','ZITAR_CONFLUENCE_5M','ZITAR_CONFLUENCE_15M')
KEEP_SPOT=('RSI14','RADAR')

def configure(base,state,market,ms):
    request=base/'zitar_strategy_selection_v1.json'
    if not request.exists():return
    spec=json.loads(request.read_text(encoding='utf-8'))
    if spec.get('version')!='SELECTED_PAPER_V1':raise ValueError('UNKNOWN_SELECTION_VERSION')
    allowed=KEEP_FUTURES if market=='futures' else KEEP_SPOT
    keep=tuple(spec.get(market,allowed))
    if not keep or any(n not in allowed for n in keep):raise ValueError('INVALID_SELECTED_ROSTER')
    if list(keep)!=state.get('active_strategy_names'):
        archive=base/'paper_strategy_archives'/f'roster_{market}_{ms}.json'
        archive.parent.mkdir(parents=True,exist_ok=True)
        atomic_json(archive,deepcopy(state))
        state['roster_archive']=str(archive)
    if not state.get('selection_archive'):
        archive=base/'paper_strategy_archives'/f'{market}_{ms}.json'
        archive.parent.mkdir(parents=True,exist_ok=True)
        atomic_json(archive,deepcopy(state))
        state['selection_archive']=str(archive)
    state['active_strategy_names']=list(keep)
    block_file=base/'zitar_strategy_entry_blocks_v1.json'
    blocked=json.loads(block_file.read_text(encoding='utf-8')).get(market,[]) if block_file.exists() else []
    for name,b in state['books'].items():
        if name in blocked:b['entries_disabled']=True;b['review_status']='ARCHIVED_EXIT_ONLY'

    for name,b in state['books'].items():
        if name not in keep:
            b.setdefault('retired_ms',ms);b['retirement_reason']='USER_SELECTED_ROSTER'
    if market=='spot' and 'RSI14' not in state['books']:
        from zitar_discovery_spot_v1 import fresh
        b=deepcopy(fresh(ms)['books']['SINGLE']);b.update(started_ms=ms,strategy='RSI14_SIMPLE_1H_LONG_BELOW_30_EXIT_OTHERWISE')
        state['books']['RSI14']=b


def prepare_reset(base,state,market):
    path=base/'zitar_active_reset_request_v1.json'
    if not path.exists():return
    req=json.loads(path.read_text(encoding='utf-8'));rid=req['id']
    if market not in req.get('markets',['spot','futures']):return
    if state.get('last_active_reset_id')==rid:return
    if state.get('pending_active_reset_id')!=rid:
        archive=base/'paper_reset_archives'/rid
        archive.mkdir(parents=True,exist_ok=True)
        atomic_json(archive/(market+'_before.json'),deepcopy(state))
        state['pending_active_reset_id']=rid
    for n,b in state['books'].items():
        if n in state.get('active_strategy_names',[]):b['reset_pending']=True

def finish_reset(base,state,market,ms):
    rid=state.get('pending_active_reset_id')
    if not rid:return
    names=state['active_strategy_names'];books=[state['books'][n] for n in names]
    if any(b['positions'] or b.get('accounting_pending') for b in books):return
    from zitar_futures_paper_engine_v1 import fresh as future_fresh
    from zitar_discovery_spot_v1 import fresh as spot_fresh
    archive=base/'paper_reset_archives'/rid
    atomic_json(archive/(market+'_closed.json'),deepcopy(state))
    for n in names:
        old=state['books'][n]
        if market=='momentum':
            from zitar_momentum_experiment_v2 import initial
            b=deepcopy(initial(ms,state['universe'])['books'][n])
        elif market=='research':
            from zitar_research_experiment_v1 import initial
            b=deepcopy(initial(ms,state['universe'])['books'][n])
        elif market=='scalping':
            from zitar_indicator_lab_v1 import initial
            b=deepcopy(initial(ms)['books'][n])
        else:b=deepcopy(future_fresh(ms,[])['books']['BASELINE'] if market=='futures' else spot_fresh(ms)['books']['SINGLE'])
        for key in ('rules','rules_hash','execution_policy','interval_ms','strategy','entries_disabled','review_status','entries_paused'):
            if key in old:b[key]=deepcopy(old[key])
        b.update(started_ms=ms,cursors={},evaluations={},daily_limit='OPEN',valuation_ms=ms)
        state['books'][n]=b
    state.update(started_ms=ms,last_candles={},decisions=[],last_active_reset_id=rid,active_reset_ms=ms)
    state.pop('pending_active_reset_id',None)
    atomic_json(archive/(market+'_receipt.json'),dict(status='RESET_COMMITTED',ms=ms,accounts=names,initial_per_account=10000,currency=('MIXED_BY_ACCOUNT' if len({b.get('market',market) for b in [state['books'][n] for n in names]})>1 else 'TRY' if all(state['books'][n].get('market',market)=='spot' for n in names) else 'USDT'),currencies={n:('TRY' if state['books'][n].get('market',market)=='spot' else 'USDT') for n in names}))

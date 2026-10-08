"""Prospective new-signal / direction concentration experiment; never promotes."""
from copy import deepcopy
from zitar_futures_paper_engine_v1 import fresh,digest
from zitar_strategy_lab_v1 import summarize
NAMES=('ZITAR_CONTROL_V2','ZITAR_TRIGGER_V2')
SPEC={'version':'TRIGGER_RISK_V2','candidate':'New nonzero majority direction vs immediately previous observed candle; max 3 positions per direction',
      'control':'Original shared MTF strategy','promotion':'NONE','slots':10,'per_direction':3,
      'sizing':'Daily equity / 10; unused slots remain cash','stop':'Unchanged 2 percent trailing',
      'hypothesis':'Joint entry and concentration change; cannot attribute improvement to either alone'}
def ensure_trigger(state,ms):
    if 'trigger_lab_spec' not in state:
        if any(n in state['books'] for n in NAMES):raise ValueError('PARTIAL_TRIGGER_STATE')
        state['trigger_lab_spec']=dict(spec=deepcopy(SPEC),hash=digest(SPEC),started_ms=ms)
        for n in NAMES:
            b=deepcopy(fresh(ms,[])['books']['BASELINE'])
            b.update(started_ms=ms,cursors={},evaluations={},rules=deepcopy(SPEC));state['books'][n]=b
    if state['trigger_lab_spec']['hash']!=digest(SPEC):raise ValueError('TRIGGER_POLICY_CHANGED')
    if not all(n in state['books'] for n in NAMES):raise ValueError('MISSING_TRIGGER_ACCOUNT')
def report_trigger(state,ms,errors):return summarize(state,ms,errors,NAMES,SPEC,'trigger_lab_spec')

"""Independent paper entry gates; stop never disables marking or exits."""
import json,time
from pathlib import Path
from zitar_full_paper_runtime_v1 import atomic_json
MARKETS=('spot','futures','pump','scalping','research','momentum','repair','bollinger')

def read(base,market):
 if market not in MARKETS:raise ValueError('INVALID_MARKET')
 if market=='pump':return dict(paused=True,disabled=True,mode='PAPER',reason='RSI_ONLY')
 path=Path(base)/('zitar_'+market+'_control_v1.json')
 if not path.exists():return dict(paused=False,mode='PAPER')
 try:
  d=json.loads(path.read_text(encoding='utf-8'))
  if type(d.get('paused')) is not bool:raise ValueError('INVALID_CONTROL')
  return dict(d,mode='PAPER',real_orders=False)
 except (OSError,ValueError):return dict(paused=True,error='INVALID_CONTROL',mode='PAPER')

def update(base,market,action):
 if market not in MARKETS or action not in ('start','stop'):raise ValueError('INVALID_ACTION')
 if market=='pump' and action=='start':raise ValueError('PUMP_DISABLED_RSI_ONLY')
 data=dict(paused=action=='stop',updated_ms=int(time.time()*1000),mode='PAPER',real_orders=False)
 atomic_json(Path(base)/('zitar_'+market+'_control_v1.json'),data)
 return dict(data,status='REQUESTED')

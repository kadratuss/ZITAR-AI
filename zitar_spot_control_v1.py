"""Paper spot entry control. Does not stop risk management or send exchange orders."""
import json,time
from pathlib import Path
from zitar_full_paper_runtime_v1 import atomic_json

def read_control(base):
 p=Path(base)/'zitar_spot_control_v1.json'
 if not p.exists():return dict(paused=False,mode='PAPER',real_orders=False)
 try:
  d=json.loads(p.read_text(encoding='utf-8'))
  if type(d.get('paused')) is not bool:raise ValueError('INVALID_CONTROL')
  return dict(paused=d['paused'],updated_ms=d.get('updated_ms'),mode='PAPER',real_orders=False)
 except (OSError,ValueError):return dict(paused=True,error='INVALID_CONTROL',mode='PAPER',real_orders=False)

def update(base,action):
 if action not in ('start','stop'):raise ValueError('INVALID_ACTION')
 d=dict(paused=action=='stop',updated_ms=int(time.time()*1000),mode='PAPER',real_orders=False)
 atomic_json(Path(base)/'zitar_spot_control_v1.json',d)
 return dict(d,status='REQUESTED',note='New entries only; stops continue. Worker acknowledgement required.')

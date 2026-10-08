"""Readiness and operational errors are separate from research evidence."""
import json,time,urllib.request
from pathlib import Path
from zitar_full_paper_runtime_v1 import atomic_json

STATE='zitar_research_readiness_v1.json'
def stage_errors(result):
 if not isinstance(result,dict):return False
 return bool(result.get('operational_error')) or any(isinstance(v,dict) and v.get('error') for v in result.get('agent_outputs',{}).values())

def ready(base,clock=time.time):
 path=Path(base)/STATE;now=clock()
 try:
  previous=json.loads(path.read_text(encoding='utf-8'))
  if 0<=now-previous['checked_at']<60:return previous['ready']
 except (OSError,ValueError,KeyError):pass
 status=dict(checked_at=now,ready=False,reason='MODEL_SERVICE_UNREACHABLE')
 try:
  from zitar_model_provider_v1 import settings
  from zitar_public_exchange_v1 import NoRedirect
  config,_=settings(base)
  with urllib.request.build_opener(NoRedirect()).open(config['base_url'].rstrip('/')+'/api/tags',timeout=3) as r:
   raw=r.read(1048577)
   if len(raw)>1048576:raise ValueError('MODEL_RESPONSE_TOO_LARGE')
   models={x['name'] for x in json.loads(raw)['models']}
  required=set(config.get('roles',{}).values())|{config['model']}
  missing=sorted(required-models)
  status.update(ready=not missing,reason='READY' if not missing else 'MODEL_NOT_INSTALLED',missing_models=missing)
 except Exception:pass
 atomic_json(path,status);return status['ready']

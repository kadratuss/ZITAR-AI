"""Queue paper-only resets; account files are written only by their owning motors."""
import json,time,uuid,threading
from zitar_full_paper_runtime_v1 import atomic_json
LOCK=threading.Lock()
MARKETS=('spot','futures','scalping','research','momentum')
def status(base):
 path=base/'zitar_active_reset_request_v1.json'
 if not path.exists():return dict(status='NONE',real_orders=False)
 req=json.loads(path.read_text(encoding='utf-8'));markets=req.get('markets',['spot','futures'])
 receipts={}
 for market in markets:
  f=base/'paper_reset_archives'/req['id']/(market+'_receipt.json')
  receipts[market]=json.loads(f.read_text(encoding='utf-8')) if f.exists() else {'status':'WAITING_FOR_MOTOR_OR_QUOTES'}
 for market,receipt in receipts.items():
  if receipt.get('status')=='RESET_COMMITTED':continue
  names={'spot':'zitar_discovery_spot_v1.json','futures':'zitar_futures_paper_v1.json','scalping':'zitar_indicator_lab_v1.json','research':'zitar_research_experiment_v1.json','momentum':'zitar_momentum_experiment_v2.json'}
  try:
   runtime=json.loads((base/names[market]).read_text(encoding='utf-8-sig'))
   age=(int(time.time()*1000)-runtime.get('heartbeat_ms',0))/1000
   receipt.update(heartbeat_age_seconds=age,reason='MOTOR_STALE' if not 0<=age<=90 else 'DATA_OR_ACCOUNTING_WAIT' if runtime.get('errors') or runtime.get('pending_active_reset_id') else 'WAITING_NEXT_CYCLE')
  except (OSError,ValueError,KeyError):receipt['reason']='MOTOR_STATUS_UNAVAILABLE'
 return dict(requested_ms=req.get('requested_ms'),id=req['id'],status='COMPLETED' if all(v.get('status')=='RESET_COMMITTED' for v in receipts.values()) else 'PENDING',markets=receipts,real_orders=False)
def request(base,payload):
 if payload!={'confirm':'RESET_PAPER_10000'}:raise ValueError('CONFIRMATION_REQUIRED')
 with LOCK:
  current=status(base)
  if current['status']=='PENDING':return current
  rid='ui-'+uuid.uuid4().hex
  atomic_json(base/'zitar_active_reset_request_v1.json',dict(id=rid,markets=list(MARKETS),requested_ms=int(time.time()*1000),real_orders=False))
  return status(base)

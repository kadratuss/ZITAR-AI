"""User-requested paper leverage changes start a new archived, flat-account experiment."""
import json,time,uuid
from pathlib import Path
from zitar_full_paper_runtime_v1 import atomic_json
from zitar_paper_supervisor_v1 import FileLock
from zitar_futures_paper_engine_v1 import POLICY,fresh
CHOICES=(1,2,3,5)
REQUEST='zitar_futures_leverage_request_v1.json'
def read_request(base):
 p=Path(base)/REQUEST
 return json.loads(p.read_text(encoding='utf-8')) if p.exists() else None

def request_change(base,leverage):
 if type(leverage) is not int or leverage not in CHOICES:raise ValueError('Kaldıraç 1, 2, 3 veya 5 olmalı.')
 base=Path(base);lock=FileLock(base/'zitar_futures_settings.lock')
 if not lock.acquire():raise ValueError('Ayar işlemi sürüyor; yeniden dene.')
 try:
  state=json.loads((base/'zitar_futures_paper_v1.json').read_text(encoding='utf-8'))
  if any(b['positions'] for b in state['books'].values()):raise ValueError('Açık pozisyon varken kaldıraç değiştirilemez.')
  old=read_request(base)
  if old and old['status']=='PENDING':raise ValueError('Önceki değişiklik henüz uygulanmadı.')
  if state['policy']['leverage']==leverage:raise ValueError('Bu kaldıraç zaten seçili.')
  req=dict(id=uuid.uuid4().hex,leverage=leverage,status='PENDING',requested_ms=int(time.time()*1000))
  atomic_json(base/REQUEST,req);return req
 finally:lock.close()

def consume_request(base,state,ms):
 base=Path(base);lock=FileLock(base/'zitar_futures_settings.lock')
 if not lock.acquire():return state
 try:
  req=read_request(base)
  if not req or req['status']!='PENDING':return state
  if state.get('applied_request')==req['id']:
   req['status']='APPLIED';atomic_json(base/REQUEST,req);return state
  if any(b['positions'] for b in state['books'].values()):
   req.update(status='REJECTED',reason='İstek işlenirken açık pozisyon bulundu; mevcut test korundu.');atomic_json(base/REQUEST,req);return state
  if type(req['leverage']) is not int or req['leverage'] not in CHOICES:raise ValueError('INVALID_LEVERAGE_REQUEST')
  folder=base/'futures_paper_archives';folder.mkdir(exist_ok=True)
  archive=folder/(req['id']+'.json')
  if not archive.exists():atomic_json(archive,state)
  POLICY['leverage']=req['leverage'];new=fresh(ms,state['universe']);new['applied_request']=req['id']
  atomic_json(base/'zitar_futures_paper_v1.json',new)
  req.update(status='APPLIED',applied_ms=ms,archive_file=archive.name);atomic_json(base/REQUEST,req)
  return new
 finally:lock.close()

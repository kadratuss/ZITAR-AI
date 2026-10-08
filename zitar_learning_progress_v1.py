"""Evidence-based progress. Never equate role completion or consensus with learning."""
import json,sqlite3,time
from pathlib import Path
from zitar_full_paper_runtime_v1 import atomic_json
LEVELS=[
 {'level':0,'name':'Soru tanımlandı','requirement':'Araştırma görevi kayıtlı.'},
 {'level':1,'name':'Kaynaklı bulgu','requirement':'Alıntısı denetlenmiş gözlem var; bağımsız doğrulama anlamına gelmez.'},
 {'level':2,'name':'Test önerisi','requirement':'Kanıta bağlı hipotez, karşılaştırma ve başarısızlık ölçütü kayıtlı.'},
 {'level':3,'name':'Deney çalışıyor','requirement':'Öneri kimliğiyle bağlı, sürümlü deney ve güncel çevrim kaydı gerekir.'},
 {'level':4,'name':'Sonuç doğrulandı','requirement':'Önceden belirlenmiş test ve örneklem koşulları tamamlanmalı; olumsuz sonuç da öğrenmedir.'},
 {'level':5,'name':'İyileşme doğrulandı','requirement':'Yeni sürümün bağımsız dönemde katkısı ve geri alma kaydı gerekir.'}]

def overview(base):
 base=Path(base);path=base/'zitar_research_council_v1.sqlite3';jobs=[];now=time.time()
 if path.exists():
  db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=5);db.row_factory=sqlite3.Row
  try:
   for row in db.execute('SELECT id,question,state,updated,result FROM jobs ORDER BY updated DESC'):
    observations=db.execute('SELECT count(*) FROM observations WHERE job=?',(row['id'],)).fetchone()[0]
    proposals=db.execute('SELECT id,content,state FROM proposals WHERE job=?',(row['id'],)).fetchall()
    result=json.loads(row['result'] or '{}')
    errors={k:v['error'] for k,v in result.get('agent_outputs',{}).items() if isinstance(v,dict) and v.get('error')}
    level=2 if proposals and observations else 1 if observations else 0
    jobs.append(dict(id=row['id'],question=row['question'],state=row['state'],updated=row['updated'],level=level,
                     observations=observations,proposals=len(proposals),errors=errors,
                     next_required='Öneriyi kimliğiyle sürümlü deneye bağla' if level==2 else 'Kanıtlı ve ölçülebilir deney önerisi üret' if level==1 else 'Konuya uygun kaynaklı bulgu çıkar',
                     proposal_details=[dict(id=p['id'],state=p['state'],content=json.loads(p['content'])) for p in proposals]))
  finally:db.close()
 try:
  readiness=json.loads((base/'zitar_research_readiness_v1.json').read_text(encoding='utf-8'))
  readiness['stale']=not 0<=now-readiness.get('checked_at',0)<=90
 except (OSError,ValueError):readiness=dict(ready=False,stale=True,reason='NOT_CHECKED')
 # Legacy proposals have no provenance link to an executed experiment. Never infer one from a similar name.
 return dict(levels=LEVELS,jobs=jobs,readiness=readiness,counts={str(i):sum(j['level']==i for j in jobs) for i in range(6)},
             measured_improvements=0,agent_linked_experiments=0,automatic_promotion=False,
             limitation='Öneri–deney bağlantısı ve bağımsız katkı doğrulaması henüz tamamlanmadı. Mevcut RSI deneyleri agent üretimi sayılmaz.')

def record_progress(base):
 data=overview(base);path=Path(base)/'zitar_learning_progress_v1.json'
 current={j['id']:j['level'] for j in data['jobs']}
 try:previous=json.loads(path.read_text(encoding='utf-8'))
 except (OSError,ValueError):previous=dict(levels={},events=[])
 events=previous.get('events',[])
 for job,level in current.items():
  if previous.get('levels',{}).get(job)!=level:events.append(dict(recorded_ms=int(time.time()*1000),job=job,level=level,baseline=job not in previous.get('levels',{})))
 atomic_json(path,dict(levels=current,events=events))

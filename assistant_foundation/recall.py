"""Source-only project recall. Note content is never passed as tool authority."""
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from assistant_foundation.project_memory import Memory, fold

STOP = {'proje','projenin','projesi','zitar','benim','bizim','nedir','neler','hangi','olan','icin','bana','bir','notu','notlar','notlari','hatirla','hatirliyor','musun','neydi','daha','once','hakkinda','soyle','olan','kayitli'}


def words(text):
    return {w for w in re.findall(r'[a-z0-9]+', fold(text)) if len(w)>=3 and w not in STOP and not w.isdigit()}


def recall(base, session, question):
    q=fold(question)
    if any(x in q for x in ('hesapla','arastir','rapor olustur','json','belge','ozetle','canli fiyat','bakiye','pozisyon','emir ac')):
        return None
    from assistant_foundation.natural_tools import candidate
    if candidate(question): return None
    cues=('hatirla','neydi','kayitli','notlar','butce','baslangic','hedef','sorumlu','tercih')
    if not any(x in q for x in cues): return None
    tokens=words(question)
    if not tokens: return None
    notes=Memory(base,session).list()
    scored=[]
    for note in notes:
        terms=words(note['text'])
        score=sum(any(a==b or (min(len(a),len(b))>=4 and (a.startswith(b) or b.startswith(a))) for b in terms) for a in tokens)
        if score:scored.append((score,note))
    selected=[n for _,n in sorted(scored,key=lambda x:(x[0],x[1]['updated']),reverse=True)[:3]]
    if not selected:return None
    lines=['Seçili hafızadaki ilgili kullanıcı notları; güncel durum ayrıca doğrulanmadı:']
    for note in selected:
        date=datetime.fromisoformat(note['updated']).astimezone(ZoneInfo('Europe/Istanbul')).strftime('%d.%m.%Y %H:%M')
        lines.append(note['project']+' · '+note['text']+'\nKaynak: kullanıcı notu · '+date+' · Sürüm '+str(note['revision'])+' · Not '+note['id'])
    return dict(route='PROJECT_RECALL',source='USER_STATED_MEMORY',grounded=False,answer='\n\n'.join(lines),
                memory_sources=[{k:n[k] for k in ('id','project','updated','revision','source')} for n in selected],
                limitation='Keyword retrieval; not semantic inference or independent verification.')

"""Application-owned research status. Model text never grants tool completion."""
import re
from zitar_chat_search_v1 import norm
from zitar_research_council_v1 import database

def status_question(question):
    q=norm(question)
    return bool(re.search(r'\b(arastirma\w*|inceleme\w*|is durumu|sonuc\w*)\b',q) and
                re.search(r'bit\w*|tamamlan\w*|durum\w*|sonuc\w*|running|queued',q))

def recorded_status(base,session):
    with database(base) as db:
        row=db.execute('SELECT id,question,state,updated FROM jobs WHERE session=? ORDER BY created DESC LIMIT 1',(session,)).fetchone()
    if not row:
        return dict(state='NO_JOB',answer='Bu konuşma için kayıtlı araştırma işi yok. Araştırmanın tamamlandığını söyleyemem.')
    job=dict(row)
    messages={
        'RETRY_WAIT':'Kanıt yetersiz; bir sonraki deneme bekleniyor.',
        'WAITING_24H':'Üç denemede yeterli kanıt bulunamadı; konu 24 saat beklemede.',
        'QUEUED':'Araştırma kuyrukta; henüz sonuç üretilmedi.',
        'RUNNING':'Araştırma kaydı çalışıyor durumunda; henüz tamamlanmış sonuç yok.',
        'COMPLETED_WITH_LIMITATIONS':'Araştırma raporu sınırlılıklarla üretildi. Bu, bütün iddiaların doğrulandığı anlamına gelmiyor.',
        'INSUFFICIENT_EVIDENCE':'İnceleme sona erdi ancak yeterli kanıt bulunamadı.',
        'ERROR':'Araştırma hata ile durdu; başarılı tamamlanma kaydı yok.'}
    job['answer']=messages.get(job['state'],'Araştırma durumu tanınmıyor; tamamlandığını doğrulayamıyorum.')
    job['answer']+='\nKonu: '+job['question']+'\nSon kayıt: '+job['updated']
    return job

def tool_claim(text):
    q=norm(text)
    return bool(re.search(r'\b(arastirdim|inceledim|dogruladim|taradim|kontrol ettim)\b',q) or
                re.search(r'(arastirma\w*|inceleme\w*).{0,45}(tamamla\w*|bitird\w*)',q))

def guard_response(base,session,text):
    # Heuristic fail-closed filter for unsupported action assertions, not a fact checker.
    if not tool_claim(text):return text,None
    evidence=recorded_status(base,session)
    return evidence['answer'],dict(reason='MODEL_TOOL_ASSERTION_REPLACED',state=evidence['state'],job_id=evidence.get('id'))

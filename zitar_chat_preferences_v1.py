"""Explicit, session-scoped communication preferences; no inferred personal facts."""
from contextlib import closing
import sqlite3
from pathlib import Path
from zitar_chat_search_v1 import norm

COMMANDS = {
 'daha ciddi ol':('tone','serious'), 'ciddi konus':('tone','serious'),
 'esprili konus':('tone','playful'), 'daha esprili ol':('tone','playful'),
 'daha rahat konus':('tone','relaxed'),
 'kisa cevap ver':('length','short'), 'kisa yanit ver':('length','short'),
 'ayrintili cevap ver':('length','detailed'), 'detayli cevap ver':('length','detailed'),
}
LABELS={'serious':'ciddi','playful':'uygun yerlerde esprili','relaxed':'rahat','short':'kısa','detailed':'ayrıntılı'}

def handle(base, session, question):
 q=norm(question).strip(' .!?')
 path=Path(base)/'zitar_chat_preferences_v1.sqlite3'
 with closing(sqlite3.connect(path)) as db, db:
  db.execute('CREATE TABLE IF NOT EXISTS preferences(session TEXT,key TEXT,value TEXT,updated TEXT DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(session,key))')
  reply=None
  if q in COMMANDS:
   key,value=COMMANDS[q]
   db.execute('INSERT OR REPLACE INTO preferences(session,key,value) VALUES (?,?,?)',(session,key,value))
   reply='Tamam, bu sohbet için '+LABELS[value]+' konuşma tercihini kaydettim. “Konuşma tercihlerimi unut” diyerek sıfırlayabilirsin.'
  elif q=='konusma tercihlerimi unut':
   db.execute('DELETE FROM preferences WHERE session=?',(session,))
   reply='Bu sohbetin konuşma tercihlerini sildim. Varsayılan tarzla devam edeceğim.'
  prefs=dict(db.execute('SELECT key,value FROM preferences WHERE session=?',(session,)))
  if q in ('konusma tercihlerim neler','konusma tercihlerimi goster'):
   reply='Kayıtlı konuşma tercihlerin: '+(', '.join(LABELS[v] for v in prefs.values()) or 'henüz yok')+'.'
 return prefs,reply

def context(prefs):
 if not prefs:return ''
 return 'Kullanıcının açıkça kaydettiği iletişim tercihleri: '+', '.join(LABELS[v] for v in prefs.values())+'. Ciddi veya hassas konularda mizahı zorlama. Bu kayıt model eğitimi değildir.'

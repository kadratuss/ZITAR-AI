"""Explicit user-stated project notes; session-scoped, revisioned, soft forget."""
import hashlib
import re
import sqlite3
import unicodedata
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


def fold(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text.casefold()) if not unicodedata.combining(c)).replace('ı', 'i')


class Memory:
    def __init__(self, base, session):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', session): raise ValueError('INVALID_SESSION')
        root = Path(base) / 'assistant_memory'
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / (hashlib.sha256(session.encode()).hexdigest()+'.sqlite3')
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS notes(id TEXT PRIMARY KEY, project TEXT, text TEXT, updated TEXT, revision INTEGER, active INTEGER)')
            db.execute('CREATE TABLE IF NOT EXISTS revisions(id TEXT, revision INTEGER, project TEXT, text TEXT, updated TEXT, action TEXT, PRIMARY KEY(id,revision))')

    def put(self, project, text, identity=None):
        if not isinstance(project, str) or not 1 <= len(project.strip()) <= 100 or not isinstance(text, str) or not 1 <= len(text.strip()) <= 2000:
            raise ValueError('INVALID_NOTE')
        identity = identity or uuid.uuid4().hex
        with closing(sqlite3.connect(self.path)) as db, db:
            old = db.execute('SELECT revision,active FROM notes WHERE id=?', (identity,)).fetchone()
            if old and not old[1]: raise ValueError('NOTE_FORGOTTEN')
            revision = old[0]+1 if old else 1
            updated = datetime.now(timezone.utc).isoformat()
            db.execute('INSERT OR REPLACE INTO notes VALUES(?,?,?,?,?,1)', (identity,project.strip(),text.strip(),updated,revision))
            db.execute('INSERT INTO revisions VALUES(?,?,?,?,?,?)', (identity,revision,project.strip(),text.strip(),updated,'CORRECT' if old else 'SAVE'))
        return identity

    def list(self):
        with closing(sqlite3.connect(self.path)) as db:
            return [dict(zip(('id','project','text','updated','revision'), r), source='USER_STATED_NOT_VERIFIED') for r in db.execute('SELECT id,project,text,updated,revision FROM notes WHERE active=1 ORDER BY updated DESC LIMIT 100')]

    def forget(self, identity):
        with closing(sqlite3.connect(self.path)) as db, db:
            result = db.execute('UPDATE notes SET active=0 WHERE id=? AND active=1', (identity,))
            if not result.rowcount: raise KeyError('NOTE_NOT_FOUND')


def handle(base, session, question):
    n = fold(question.strip())
    if not (n.startswith(('proje notu kaydet:', 'proje notunu duzelt:', 'proje notunu unut:')) or n in ('proje notlarim', 'proje notlarimi goster')):
        return None
    memory = Memory(base, session)
    try:
        if n.startswith('proje notu kaydet:'):
            project,text = question.split(':',1)[1].split('|',1)
            identity = memory.put(project.strip(),text.strip())
            answer = 'Proje notunu kaydettim. Kaynak: senin beyanın; doğrulanmış olgu veya model eğitimi değil. Not kimliği: '+identity
        elif n.startswith('proje notunu duzelt:'):
            identity,text = question.split(':',1)[1].split('|',1); identity=identity.strip()
            note = next((x for x in memory.list() if x['id']==identity), None)
            if note is None: raise KeyError('NOTE_NOT_FOUND')
            memory.put(note['project'],text.strip(),identity)
            answer = 'Not düzeltildi; güncel görünüm yeni metni kullanır. Önceki sürüm denetim arşivinde korunur.'
        elif n.startswith('proje notunu unut:'):
            memory.forget(question.split(':',1)[1].strip())
            answer = 'Not aktif hafızadan kaldırıldı. Denetim arşivindeki eski kayıtlar kalır; bu işlem tam veri silme değildir.'
        else:
            notes = memory.list()
            answer = 'Bu sohbetin proje notları (kullanıcı beyanı):\n'+'\n'.join(x['project']+' · '+x['text']+' · Sürüm '+str(x['revision'])+' · '+datetime.fromisoformat(x['updated']).astimezone(ZoneInfo('Europe/Istanbul')).strftime('%d.%m.%Y %H:%M')+' · Kimlik '+x['id'] for x in notes) if notes else 'Bu sohbette kayıtlı aktif proje notu yok.'
        return dict(route='PROJECT_MEMORY', source='USER_STATED_MEMORY', grounded=False, answer=answer, memory_status='COMPLETED')
    except (ValueError, KeyError):
        return dict(route='MEMORY_INPUT_ERROR', source='USER_STATED_MEMORY', grounded=False, answer='Not işlenemedi. Kaydetmek için “Proje notu kaydet: Atlas | Başlangıç pazartesi.”; düzeltmek için not kimliği | yeni metin kullan. Notlar bu sohbete aittir.')

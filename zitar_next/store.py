"""Own research workspace and transactional, human-controlled proposal registry."""
import hashlib
import json
import os
import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone


def stamp():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,allow_nan=False,separators=(',',':')).encode()).hexdigest()


def init(root):
    root = Path(root).resolve()
    # Never claim an existing folder as a writable research account.
    root.mkdir(parents=True,exist_ok=False)
    (root/'NEXT_RESEARCH_ONLY').write_text('ZITAR_NEXT_V1',encoding='utf-8')
    (root/'runs').mkdir()
    Registry(root)
    return root


def workspace(root):
    root = Path(root).resolve(strict=True)
    marker = root/'NEXT_RESEARCH_ONLY'
    if not marker.is_file() or marker.is_symlink() or marker.read_text(encoding='utf-8') != 'ZITAR_NEXT_V1':
        raise ValueError('dedicated Next workspace required')
    if (root/'runs').is_symlink() or not (root/'runs').is_dir():
        raise ValueError('invalid research runs folder')
    return root


def atomic(path,value):
    path = Path(path)
    if path.is_symlink():
        raise ValueError('symlink output rejected')
    raw = json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2).encode('utf-8')
    with tempfile.NamedTemporaryFile(dir=path.parent,prefix=path.name+'.',suffix='.tmp',delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.replace(temporary,path)
    finally:
        temporary.unlink(missing_ok=True)


class Registry:
    def __init__(self,root):
        self.root = workspace(root)
        self.path = self.root/'next_registry.sqlite3'
        if self.path.is_symlink():
            raise ValueError('registry symlink rejected')
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS proposals(id TEXT PRIMARY KEY,body TEXT NOT NULL,state TEXT NOT NULL,created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,proposal TEXT,event TEXT,created TEXT,note TEXT);
                CREATE TABLE IF NOT EXISTS active(scope TEXT PRIMARY KEY,proposal TEXT NOT NULL);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path,timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def propose(self,body):
        if body.get('market') not in ('spot','futures') or body.get('real_orders') is not False or body.get('paper_only') is not True:
            raise ValueError('paper-only market proposal required')
        identity = digest(body)
        with self.connect() as db:
            changed = db.execute('INSERT OR IGNORE INTO proposals VALUES(?,?,?,?)',
                                 (identity,json.dumps(body,allow_nan=False),'PENDING',stamp())).rowcount
            if changed:
                db.execute('INSERT INTO events(proposal,event,created,note) VALUES(?,?,?,?)',
                           (identity,'PROPOSED',stamp(),'Human decision required; no automatic activation'))
        return identity

    def all(self):
        with self.connect() as db:
            # Include active/archived accepted versions even after many new rejected candidates.
            proposals = [dict(id=r['id'],state=r['state'],created=r['created'],body=json.loads(r['body'])) for r in db.execute("SELECT * FROM proposals WHERE id IN (SELECT id FROM proposals ORDER BY created DESC LIMIT 50) OR state IN ('ACTIVE_PAPER','ARCHIVED','ACCEPTED') ORDER BY created DESC")]
            for row in proposals:
                if digest(row['body']) != row['id']:
                    raise ValueError('proposal content mismatch')
            return dict(proposals=proposals,active=[dict(r) for r in db.execute('SELECT * FROM active')],
                        events=[dict(r) for r in db.execute('SELECT * FROM events ORDER BY id DESC LIMIT 100')],real_orders=False)

    def decide(self,identity,decision,note):
        if decision not in ('ACCEPT','REJECT','ACTIVATE','ROLLBACK') or not isinstance(note,str) or not note.strip() or len(note)>500:
            raise ValueError('explicit decision and note required')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM proposals WHERE id=?',(identity,)).fetchone()
            if not row:
                raise ValueError('proposal not found')
            body = json.loads(row['body'])
            if digest(body) != identity:
                raise ValueError('proposal changed; new approval required')
            state = row['state']
            scope = body['market']+':'+body['symbol']+':'+body['interval']
            if decision == 'ACCEPT':
                if state != 'PENDING' or body.get('eligible') is not True or body.get('issues'):
                    raise ValueError('proposal is not eligible for acceptance')
                new = 'ACCEPTED'
            elif decision == 'REJECT':
                if state not in ('PENDING','ACCEPTED'):
                    raise ValueError('cannot reject active or already reviewed proposal')
                new = 'REJECTED'
            elif decision == 'ACTIVATE':
                if state != 'ACCEPTED':
                    raise ValueError('human acceptance required before paper activation')
                active = db.execute('SELECT proposal FROM active WHERE scope=?',(scope,)).fetchone()
                if active:
                    db.execute("UPDATE proposals SET state='ARCHIVED' WHERE id=?",(active['proposal'],))
                db.execute('INSERT OR REPLACE INTO active VALUES(?,?)',(scope,identity))
                new = 'ACTIVE_PAPER'
            else:
                if state not in ('ARCHIVED','ACTIVE_PAPER'):
                    raise ValueError('rollback requires previously accepted paper version')
                active = db.execute('SELECT proposal FROM active WHERE scope=?',(scope,)).fetchone()
                if active and active['proposal'] != identity:
                    db.execute("UPDATE proposals SET state='ARCHIVED' WHERE id=?",(active['proposal'],))
                db.execute('INSERT OR REPLACE INTO active VALUES(?,?)',(scope,identity))
                new = 'ACTIVE_PAPER'
            db.execute('UPDATE proposals SET state=? WHERE id=?',(new,identity))
            db.execute('INSERT INTO events(proposal,event,created,note) VALUES(?,?,?,?)',(identity,decision,stamp(),note))
        return new


class WorkerLock:
    def __init__(self,root):
        self.path = workspace(root)/'worker.lock'
        self.stream = None

    def __enter__(self):
        if self.path.is_symlink():
            raise ValueError('lock symlink rejected')
        self.stream = self.path.open('a+b')
        try:
            self.stream.seek(0)
            if self.stream.read(1) == b'':
                self.stream.write(b'0'); self.stream.flush()
            self.stream.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            self.stream.close()
            raise RuntimeError('Next worker already running')
        return self

    def __exit__(self,*args):
        self.stream.close()

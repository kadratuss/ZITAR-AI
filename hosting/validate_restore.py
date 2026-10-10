"""Exercise real archive/restore against disposable SQLite and approval state."""
import json
import sqlite3
import tarfile
import tempfile
from pathlib import Path
from zitar_next.hosting import backup
from zitar_next.backup_guard import verify
from zitar_next.store import init,Registry
from test_zitar_next import proposal

def main():
    with tempfile.TemporaryDirectory(prefix='zitar-restore-') as temporary:
        root=Path(temporary);base=root/'runtime';base.mkdir();next_root=init(root/'next')
        with sqlite3.connect(base/'historical_candles.sqlite') as db:
            db.execute('CREATE TABLE candles (symbol TEXT, close REAL)')
            db.execute('INSERT INTO candles VALUES (?,?)',('BTCUSDT',100.0))
        (base/'account.json').write_text(json.dumps(dict(cash=10000,real_orders=False)))
        (base/'.env').write_text('FIXTURE_ONLY=excluded')
        identity=Registry(next_root).propose(proposal(False))
        result=backup(base,next_root,root/'backups');verify(result['path'])
        restored=root/'restored'
        with tarfile.open(result['path']) as archive:archive.extractall(restored,filter='data')
        with sqlite3.connect(restored/'runtime/historical_candles.sqlite') as db:
            assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert db.execute('SELECT * FROM candles').fetchall()==[('BTCUSDT',100.0)]
        assert json.loads((restored/'runtime/account.json').read_text())['cash']==10000
        assert Registry(restored/'next').all()['proposals'][0]['id']==identity
        assert not (restored/'runtime/.env').exists()
        print(json.dumps(dict(sqlite_integrity='ok',account_restored=True,registry_restored=True,
                              checksum_verified=True,secrets_excluded=True,live_accounts_touched=False)))

if __name__=='__main__':main()

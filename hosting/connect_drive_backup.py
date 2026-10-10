"""Configure encrypted Drive backup and test an isolated cloud restore; no live state."""
import configparser
import json
import os
import secrets
import sqlite3
import subprocess
import tarfile
import tempfile
from pathlib import Path
from zitar_next.hosting import backup
from zitar_next.backup_guard import deliver,verify
from zitar_next.store import init

def main():
    os.umask(0o077)
    config=Path('/etc/zitar/rclone.conf')
    parser=configparser.ConfigParser(interpolation=None);parser.read(config)
    if 'zitar-drive' not in parser:raise ValueError('Google authorization missing')
    if 'zitarcrypt' not in parser:
        def obscure():
            return subprocess.run(['rclone','obscure',secrets.token_urlsafe(48)],capture_output=True,text=True,check=True).stdout.strip()
        parser['zitarcrypt']=dict(type='crypt',remote='zitar-drive:ZITAR-Encrypted-Backups',
                                 filename_encryption='standard',directory_name_encryption='true',
                                 password=obscure(),password2=obscure())
        temporary=config.with_suffix('.tmp')
        with temporary.open('w') as stream:parser.write(stream)
        temporary.chmod(0o600);temporary.replace(config)
    Path('/etc/zitar/backup.env').write_text("ZITAR_BACKUP_REMOTE='zitarcrypt:daily'\nZITAR_RCLONE_CONFIG='/etc/zitar/rclone.conf'\n")
    with tempfile.TemporaryDirectory(prefix='zitar-cloud-restore-') as directory:
        root=Path(directory);base=root/'runtime';base.mkdir();next_root=init(root/'next')
        with sqlite3.connect(base/'fixture.sqlite') as db:
            db.execute('CREATE TABLE account(cash INTEGER)');db.execute('INSERT INTO account VALUES(10000)')
        result=backup(base,next_root,root/'backups')
        delivery=deliver(root/'backups','zitarcrypt:validation',config)
        archive=Path(result['path']);download=root/archive.name
        subprocess.run(['rclone','--config',str(config),'copyto','zitarcrypt:validation/'+archive.name,str(download)],check=True,capture_output=True,timeout=600)
        download.with_suffix(download.suffix+'.sha256').write_text(archive.with_suffix(archive.suffix+'.sha256').read_text())
        verify(download)
        with tarfile.open(download) as bundle:bundle.extractall(root/'restored',filter='data')
        with sqlite3.connect(root/'restored/runtime/fixture.sqlite') as db:
            assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert db.execute('SELECT cash FROM account').fetchone()[0]==10000
        receipt=dict(encrypted_cloud_upload=True,download_checksum_verified=True,sqlite_restore='ok',
                     live_accounts_touched=False,archive=archive.name,remote='zitarcrypt:validation')
        Path('/etc/zitar/backup-cloud-validation.json').write_text(json.dumps(receipt,indent=2))
        print(json.dumps(receipt))

if __name__=='__main__':main()

"""Restore a verified encrypted cloud backup into an isolated disposable folder."""
import hashlib
import json
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from zitar_next.store import atomic,stamp


def main():
    backups=Path('/srv/zitar/backups')
    receipts=sorted(backups.glob('zitar-*.tar.gz.offsite.json'))
    if not receipts: raise ValueError('verified offsite receipt required')
    receipt=json.loads(receipts[-1].read_text())
    if receipt.get('verified') is not True or not receipt.get('remote','').startswith('zitarcrypt:'):
        raise ValueError('verified crypt destination required')
    area=Path('/srv/zitar/restore-tests')
    area.mkdir(exist_ok=True)
    if area.is_symlink(): raise ValueError('symlink test area rejected')
    with tempfile.TemporaryDirectory(prefix='cloud-restore-',dir=area) as temporary:
        folder=Path(temporary);archive_path=folder/'cloud.tar.gz'
        subprocess.run(['rclone','--config','/etc/zitar/rclone.conf','copyto',receipt['remote'],str(archive_path)],
                       check=True,timeout=1800,capture_output=True)
        with archive_path.open('rb') as stream: checksum=hashlib.file_digest(stream,'sha256').hexdigest()
        if checksum!=receipt['sha256']: raise ValueError('cloud archive checksum mismatch')
        restored=folder/'restored'
        with tarfile.open(archive_path,'r:gz') as archive:
            members=archive.getmembers()
            for member in members:
                path=PurePosixPath(member.name)
                if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] not in ('runtime','next') or not (member.isfile() or member.isdir()):
                    raise ValueError('unsafe archive member')
            if shutil.disk_usage(area).free<sum(m.size for m in members)+2*1024**3:
                raise ValueError('insufficient isolated restoration space')
            archive.extractall(restored,members=members,filter='data')
        databases=[];models=0
        for path in restored.rglob('*'):
            if not path.is_file(): continue
            with path.open('rb') as stream: header=stream.read(16)
            if header==b'SQLite format 3\x00':
                with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
                    if db.execute('PRAGMA integrity_check').fetchall()!=[('ok',)]:
                        raise ValueError('restored database integrity failed')
                databases.append(str(path.relative_to(restored)))
            if path.suffix=='.zip' and path.name.startswith(('ppo-','model-')):
                with zipfile.ZipFile(path) as model:
                    if model.testzip() is not None: raise ValueError('restored model checksum failed')
                models+=1
        if not databases: raise ValueError('no restored SQLite database')
        state=json.loads((restored/'runtime/zitar_master_portfolio_v1.json').read_text(encoding='utf-8-sig'))
        if state.get('authorities',{}).get('real_order') is not False:
            raise ValueError('restored paper-only authority required')
        with sqlite3.connect((restored/'next/next_registry.sqlite3').as_uri()+'?mode=ro',uri=True) as db:
            proposals=db.execute('SELECT count(*) FROM proposals').fetchone()[0]
        result=dict(schema='CLOUD_RESTORE_ACCEPTANCE_V1',state='PASSED',updated=stamp(),
                    archive=Path(receipt['remote']).name,sha256=checksum,cloud_download_verified=True,
                    sqlite_integrity_checked=databases,restored_model_archives_checked=models,
                    restored_proposals=proposals,real_orders=False,live_accounts_touched=False,
                    limitations=['Checks restoration and integrity in isolation, not startup of a duplicate trading service.',
                                 'Venv, private credentials and OS are excluded and must be provisioned separately.'])
        atomic(area/'acceptance.json',result)
        print(json.dumps(dict(state='PASSED',sqlite_databases=len(databases),models=models,live_accounts_touched=False)))


if __name__=='__main__': main()

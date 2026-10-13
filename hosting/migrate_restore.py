"""Restore a stopped source into a new Linux runtime; preserve prepared code."""
import argparse
import hashlib
import json
import shutil
import sqlite3
import tarfile
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('archive');p.add_argument('sha256');a=p.parse_args()
    archive=Path(a.archive)
    with archive.open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==a.sha256
    staging=Path('/srv/zitar/handoff-staging');staging.mkdir(exist_ok=False)
    with tarfile.open(archive,'r|gz') as bundle:bundle.extractall(staging,filter='data')
    verified=0
    for path in staging.rglob('*'):
        if path.is_file() and path.suffix.lower() in ('.db','.sqlite','.sqlite3'):
            with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
                assert db.execute('PRAGMA integrity_check').fetchall()==[('ok',)],path.name
            verified+=1
    master=json.loads((staging/'runtime/zitar_master_portfolio_v1.json').read_text(encoding='utf-8-sig'))
    assert master['authorities']['real_order'] is False
    target=Path('/srv/zitar/runtime');next_root=Path('/srv/zitar/data/next')
    assert not next_root.exists(),'Next target already exists'
    inventory=[]
    for source in (staging/'runtime').rglob('*'):
        relative=source.relative_to(staging/'runtime');dest=target/relative
        if source.is_dir():dest.mkdir(parents=True,exist_ok=True);continue
        if source.suffix in ('.py','.sh','.service','.timer','.conf') and dest.exists():continue
        if source.is_file():
            dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
            if source.suffix in ('.json','.jsonl','.csv','.db','.sqlite','.sqlite3'):
                digest=hashlib.sha256(source.read_bytes()).hexdigest()
                assert hashlib.sha256(dest.read_bytes()).hexdigest()==digest
                inventory.append(dict(path=str(relative),sha256=digest))
    shutil.copytree(staging/'next',next_root)
    (target/'HOSTING_HANDOFF.json').write_text(json.dumps(dict(source_owners_stopped=True,real_orders=False)))
    Path('/etc/zitar/handoff-inventory.json').write_text(json.dumps(dict(archive_sha256=a.sha256,sqlite_verified=verified,state_files=inventory),indent=2))
    print(json.dumps(dict(sqlite_verified=verified,state_files_verified=len(inventory),next_restored=True,real_orders=False)))

if __name__=='__main__':main()

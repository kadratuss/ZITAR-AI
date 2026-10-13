"""Verified encrypted offsite delivery; pruning requires a successful delivery receipt."""
import argparse
import hashlib
import json
import subprocess
import re
import tarfile
from pathlib import Path

def verify(path):
    path=Path(path)
    expected=path.with_suffix(path.suffix+'.sha256').read_text().split()[0]
    with path.open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
    if actual!=expected:raise ValueError('backup checksum mismatch')
    with tarfile.open(path,'r|gz') as archive:
        for member in archive:
            if member.isfile():
                stream=archive.extractfile(member)
                while stream.read(1024*1024):pass
    return actual

def deliver(directory,remote,config,keep=7,runner=subprocess.run,cloud_keep=None):
    directory=Path(directory).resolve(strict=True)
    if keep<2:raise ValueError('at least two local backups required')
    if not remote.startswith('zitarcrypt:') or any(c in remote for c in '\n\r'):
        raise ValueError('dedicated zitarcrypt encrypted remote required')
    archives=sorted(directory.glob('zitar-*.tar.gz'))
    if not archives:raise ValueError('no backup available')
    latest=archives[-1];digest=verify(latest)
    def run(*args):
        return runner(['rclone','--config',str(config),*args],check=True,timeout=3600,capture_output=True)
    kind=run('config','show','zitarcrypt').stdout
    if b'type = crypt' not in kind:raise ValueError('remote must use rclone crypt')
    if cloud_keep is not None:
        if cloud_keep<2:raise ValueError('at least two cloud backups required')
        quota=json.loads(run('about','zitar-drive:','--json').stdout)
        if quota.get('free',0)<latest.stat().st_size+2*1024**3:
            raise ValueError('cloud space insufficient; old backups preserved')
    target=remote.rstrip('/')+'/'+latest.name
    run('copyto',str(latest),target)
    run('copyto',str(latest)+'.sha256',target+'.sha256')
    # Download comparison decrypts the destination and compares full content.
    run('check',str(directory),remote,'--include',latest.name,'--download','--one-way')
    receipt=latest.with_suffix(latest.suffix+'.offsite.json')
    receipt.write_text(json.dumps(dict(sha256=digest,remote=target,verified=True)),encoding='utf-8')
    if cloud_keep is not None:
        items=json.loads(run('lsjson',remote,'--files-only').stdout)
        names=sorted(item['Name'] for item in items if re.fullmatch(r'zitar-\d{8}T\d{12}Z\.tar\.gz',item['Name']))
        if latest.name not in names:raise ValueError('verified latest cloud archive missing')
        # Dedicated encrypted directory only; never touch other Drive files.
        for name in names[:-cloud_keep]:
            if name>=latest.name:continue
            run('deletefile',remote.rstrip('/')+'/'+name,'--drive-use-trash=false')
            run('deletefile',remote.rstrip('/')+'/'+name+'.sha256','--drive-use-trash=false')
    removed=[]
    for old in archives[:-keep]:
        proof=old.with_suffix(old.suffix+'.offsite.json')
        if not proof.exists():continue
        data=json.loads(proof.read_text())
        if data.get('verified') is not True or data.get('sha256')!=verify(old):continue
        old.unlink();removed.append(old.name)
        old.with_suffix(old.suffix+'.sha256').unlink();proof.unlink()
    return dict(verified=True,archive=latest.name,removed=removed)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory',required=True);p.add_argument('--remote',required=True)
    p.add_argument('--config',required=True);p.add_argument('--keep',type=int,default=7)
    p.add_argument('--cloud-keep',type=int)
    a=p.parse_args();print(json.dumps(deliver(a.directory,a.remote,a.config,a.keep,cloud_keep=a.cloud_keep)))

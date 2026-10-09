"""Fail-closed handoff checks and snapshots; never changes source account files."""
import argparse
import hashlib
import json
import tarfile
from datetime import datetime,timezone
from pathlib import Path
from zitar_next.store import workspace

def check(base,next_root):
    base=Path(base).resolve(strict=True);next_root=workspace(next_root)
    state=json.loads((base/'zitar_master_portfolio_v1.json').read_text(encoding='utf-8-sig'))
    if state.get('schema')!='ZITAR_MASTER_PORTFOLIO_V1' or state.get('authorities',{}).get('real_order') is not False:
        raise ValueError('verified paper-only master required')
    rules=state['rules'];authorities=state['authorities']
    if rules.get('futures_enabled') is not False or authorities.get('futures_allocation') is not False or authorities.get('modify_v3',False) is not False:
        raise ValueError('unsupported master execution authority')
    receipt=json.loads((base/'HOSTING_HANDOFF.json').read_text(encoding='utf-8'))
    if receipt.get('source_owners_stopped') is not True or receipt.get('real_orders') is not False:
        raise ValueError('source owner shutdown receipt required')
    return dict(paper_only=True,source_owners_stopped=True,next_workspace=str(next_root))

def assert_stopped(base,next_root):
    from zitar_paper_supervisor_v1 import lock_held
    for name in ('zitar_paper_supervisor_v1','zitar_full_paper_runtime_v1','zitar_research_runtime_v1','zitar_comparison_runtime_v1','zitar_futures_paper_v1'):
        path=Path(base)/(name+'.lock')
        if path.exists() and lock_held(path):raise ValueError('source owner still running: '+name)
    path=Path(next_root)/'worker.lock'
    if path.exists() and lock_held(path):raise ValueError('learning worker still running')

def backup(base,next_root,output):
    base=Path(base).resolve(strict=True);next_root=workspace(next_root)
    assert_stopped(base,next_root)
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    if output==base or base in output.parents or output==next_root or next_root in output.parents:
        raise ValueError('backup must be outside source trees')
    filename='zitar-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.tar.gz'
    path=output/filename
    skipped=('.git','.venv','venv','__pycache__','.cache','.research-venv')
    with tarfile.open(path,'x:gz') as archive:
        for root,label in ((base,'runtime'),(next_root,'next')):
            for file in sorted(root.rglob('*')):
                relative=file.relative_to(root)
                if any(part in skipped for part in relative.parts) or file.is_symlink():continue
                if file.is_dir():
                    archive.add(file,arcname=str(Path(label)/relative),recursive=False);continue
                if not file.is_file():continue
                if '.env' in file.name or any(word in file.name.lower() for word in ('credential','secret','api_key')):continue
                archive.add(file,arcname=str(Path(label)/relative),recursive=False)
    path.chmod(0o600)
    with path.open('rb') as stream:checksum=hashlib.file_digest(stream,'sha256').hexdigest()
    path.with_suffix(path.suffix+'.sha256').write_text(checksum+'  '+filename+'\n',encoding='utf-8')
    return dict(path=str(path),sha256=checksum,automatic_deletion=False)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('check','backup'))
    p.add_argument('--base',required=True);p.add_argument('--next-root',required=True);p.add_argument('--output')
    a=p.parse_args()
    if a.action=='backup' and not a.output:p.error('--output required')
    result=check(a.base,a.next_root) if a.action=='check' else backup(a.base,a.next_root,a.output)
    print(json.dumps(result))

if __name__=='__main__':main()

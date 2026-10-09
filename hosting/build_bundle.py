"""Package code/assets only. Live balances, DBs, secrets and model states are excluded."""
import argparse
import hashlib
import json
import os
import shutil
import zipfile
from pathlib import Path

def build(workspace,production,output):
    workspace=Path(workspace).resolve(strict=True);production=Path(production).resolve(strict=True)
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    target=output/'runtime';target.mkdir()
    excluded={'.git','.venv','venv','__pycache__','research_artifacts','sources','.codex','node_modules','.research-venv','paper_code_backups','zitar_app'}
    suffixes={'.py','.js','.html','.css','.md','.sh','.service','.timer','.conf'}
    inventory=[]
    def copy(root,restricted=False):
        for directory,dirs,files in os.walk(root):
            dirs[:]=[d for d in dirs if d not in excluded and not d.startswith('.') and not Path(directory,d).is_symlink()]
            if Path(directory)==root and not restricted:
                dirs[:]=[d for d in dirs if d in ('pa_v1','zitar_ui','personal_ai')]
            dirs[:]=[d for d in dirs if not d.endswith('venv')]
            for name in files:
                source=Path(directory,name);relative=source.relative_to(root)
                if source.is_symlink():continue
                if source.suffix not in suffixes and name not in ('requirements.txt','LICENSE-FinRL-X.txt'):continue
                if restricted and not (relative.parts[0] in ('zitar_next','hosting') or len(relative.parts)==1):continue
                if name.startswith('prepare_') or name.startswith('patch_') or 'before_' in name or name.endswith('.bak'):continue
                destination=target/relative;destination.parent.mkdir(parents=True,exist_ok=True)
                if source.suffix in ('.sh','.service','.timer','.conf'):
                    destination.write_bytes(source.read_bytes().replace(b'\r\n',b'\n'))
                else:shutil.copyfile(source,destination)
    copy(production);copy(workspace,True)
    for source in sorted(target.rglob('*')):
        if source.is_file():inventory.append(dict(path=source.relative_to(output).as_posix(),sha256=hashlib.sha256(source.read_bytes()).hexdigest(),bytes=source.stat().st_size))
    manifest=dict(schema='ZITAR_HOSTING_CODE_BUNDLE_V1',target='Hostinger KVM2 / Ubuntu 24.04',files=inventory,
                  contains_account_state=False,contains_databases=False,contains_secrets_files=False,real_orders=False,
                  installation_status='PREPARED_NOT_DEPLOYED',linux_runtime_validated=False)
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    archive=output.with_suffix('.zip')
    if archive.exists():raise FileExistsError(archive)
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as bundle:
        for source in sorted(output.rglob('*')):
            if source.is_file():bundle.write(source,source.relative_to(output))
    return dict(archive=str(archive),files=len(inventory),sha256=hashlib.sha256(archive.read_bytes()).hexdigest())

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workspace',required=True);p.add_argument('--production',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();print(json.dumps(build(a.workspace,a.production,a.output)))

"""Import hash-verified trial evidence into the console; never accept or activate."""
import argparse
import json
import shutil
from zitar_next.store import Registry,workspace,digest,atomic
from zitar_next.finrl_pipeline import load_run

def import_trial(source,destination):
    source=workspace(source);destination=workspace(destination)
    if source==destination:raise ValueError('distinct workspaces required')
    imported=[]
    for proposal in Registry(source).all()['proposals']:
        body=proposal['body'];run=body['run']
        report,_,_,_=load_run(source,run)
        if digest({k:v for k,v in report.items() if k!='proposal_id'})!=proposal['id']:
            raise ValueError('trial proposal/report mismatch')
        if any(p.is_symlink() for p in (source/'runs'/run).rglob('*')):
            raise ValueError('trial artifact symlink rejected')
        target=destination/'runs'/run
        if not target.exists():shutil.copytree(source/'runs'/run,target,symlinks=False)
        # Verify copied artifacts before introducing the pending proposal.
        load_run(destination,run)
        identity=Registry(destination).propose(body)
        for category in ('combination_reports','finrlx_reports'):
            folder=destination/category;folder.mkdir(exist_ok=True)
            if folder.is_symlink():raise ValueError('report symlink rejected')
            atomic(folder/(run+'.json'),json.loads((source/category/(run+'.json')).read_text(encoding='utf-8')))
        imported.append(dict(proposal=identity,run=run,state='PENDING',eligible=body['eligible']))
    return imported

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True);p.add_argument('--destination',required=True)
    a=p.parse_args();print(json.dumps(import_trial(a.source,a.destination)))

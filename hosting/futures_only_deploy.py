"""Apply the reviewed futures-only deployment; run on the VPS as root."""
import json,sqlite3,subprocess,shutil,time
from pathlib import Path
stage=Path('/tmp/zitar-futures-only');base=Path('/srv/zitar/runtime');root=Path('/srv/zitar/data/next')
def run(*args):subprocess.run(args,check=True)
if subprocess.run(['systemctl','is-active','--quiet','zitar-backup.service']).returncode==0:
 raise RuntimeError('Backup currently running; retry after it completes')
run('systemctl','stop','zitar-learning.service','zitar-forward-study.timer','zitar-forward-study.service','zitar-production.service')
try:
 (base/'zitar_futures_only.flag').write_text('USER_REQUEST_FUTURES_ONLY\n')
 (base/'zitar_comparison_supervisor.pause').write_text('SPOT_DISABLED_BY_USER\n')
 for p in stage.glob('*.py'):
  if p.name in ('deploy.py','prepare.py','finish.py','test_futures_scope.py'):continue
  target=base/('zitar_next/'+p.name if p.name in ('gateway.py','position_charts.py','futures_worker.py','futures_forward_study.py','futures_scope.py') else p.name)
  shutil.copyfile(p,target);shutil.chown(target,user='zitar',group='zitar')
 shutil.copyfile(stage/'zitar_full_paper_dashboard_v1.html',base/'zitar_full_paper_dashboard_v1.html')
 # Remove only spot books from shared live ledgers; preserve futures byte values.
 for name in ('zitar_indicator_lab_v1.json','zitar_research_experiment_v1.json','zitar_momentum_experiment_v2.json','zitar_rsi_repair_v1.json','zitar_bollinger_pair_v1.json'):
  p=base/name
  if not p.exists():continue
  d=json.loads(p.read_text(encoding='utf-8-sig'))
  d['books']={k:v for k,v in d.get('books',{}).items() if v.get('market')!='spot'}
  if 'specs' in d:d['specs']={k:v for k,v in d['specs'].items() if v[1]!='spot'}
  if 'universe' in d:d['universe']['spot']=[]
  p.write_text(json.dumps(d,ensure_ascii=False));shutil.chown(p,user='zitar',group='zitar')
 db=sqlite3.connect(root/'next_registry.sqlite3')
 with db:
  ids=[r[0] for r in db.execute('SELECT id,body FROM proposals') if json.loads(r[1]).get('market')=='spot']
  for identity in ids:
   db.execute('DELETE FROM active WHERE proposal=?',(identity,))
   db.execute('DELETE FROM events WHERE proposal=?',(identity,))
   db.execute('DELETE FROM proposals WHERE id=?',(identity,))
 db.execute('VACUUM');db.close()
 for folder in ('runs','combination_reports','finrlx_reports','paper'):
  parent=root/folder
  if not parent.exists():continue
  for p in parent.iterdir():
   if not p.name.startswith('spot-') and not p.name.startswith('spot:'):continue
   resolved=p.resolve();assert resolved.is_relative_to(root.resolve()) and not p.is_symlink()
   if p.is_dir():shutil.rmtree(p)
   else:p.unlink()
 for name in ('market_status.json','cursor.json','heldout_anchors.json'):
  p=root/name
  if p.exists():
   d=json.loads(p.read_text());d={k:v for k,v in d.items() if k!='spot' and not k.startswith('spot:')}
   p.write_text(json.dumps(d));shutil.chown(p,user='zitar',group='zitar')
 for unit,module in [('zitar-learning','futures_worker'),('zitar-forward-study','futures_forward_study')]:
  drop=Path('/etc/systemd/system')/(unit+'.service.d');drop.mkdir(exist_ok=True)
  suffix='--root /srv/zitar/data/next --steps 2048 --cycles 0 --pause 300' if unit=='zitar-learning' else '--root /srv/zitar/data/next --study /srv/zitar/data/next/studies/20261010-v1'
  (drop/'futures-only.conf').write_text('[Service]\nExecStart=\nExecStart=/srv/zitar/venv/bin/python -B -m zitar_next.'+module+' '+suffix+'\n')
 run('systemctl','daemon-reload')
 run('systemctl','disable','--now','zitar-v3.timer')
 print(json.dumps({'spot_proposals_removed':len(ids),'scope':'FUTURES_ONLY','real_orders':False}))
finally:
 run('systemctl','start','zitar-production.service','zitar-learning.service','zitar-forward-study.timer')
run('systemctl','restart','zitar-gateway.service')

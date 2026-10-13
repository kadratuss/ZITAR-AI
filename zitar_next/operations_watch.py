"""Read-only service sampling for a bounded 24-hour operational observation."""
import argparse
import json
import subprocess
import time
from pathlib import Path
from zitar_next.store import atomic,workspace

SERVICES=('zitar-production','zitar-learning','zitar-gateway','zitar-console','zitar-mobile-monitor',
          'zitar-v3-data','zitar-chat','zitar-rag','ollama','tailscaled')


def progress(previous,now,boot,errors,maintenance=False):
    same=previous and previous.get('boot_id')==boot and 0<now-previous.get('updated_epoch',0)<=1800
    stable=previous.get('stable_since') if same else None
    if errors and not maintenance: stable=None
    elif stable is None and not maintenance: stable=now
    hours=max(0,(now-stable)/3600) if stable is not None else 0
    return dict(schema='OPERATIONS_OBSERVATION_V1',updated_epoch=now,boot_id=boot,
        stable_since=stable,observed_hours=hours,errors=errors,planned_backup=maintenance,
        status='PLANNED_BACKUP' if maintenance else 'ATTENTION_REQUIRED' if errors else
               '24H_SAMPLED_CHECKS_PASSED' if hours>=24 else 'OBSERVING_24H',
        real_orders=False,scope='15-minute samples; not proof of uninterrupted availability between samples')


def cycle(root):
    root=workspace(root);area=root/'operations';area.mkdir(exist_ok=True)
    if area.is_symlink(): raise ValueError('symlink output rejected')
    status=area/'status.json'
    if status.is_symlink(): raise ValueError('symlink status rejected')
    previous=json.loads(status.read_text()) if status.exists() else None
    active=lambda name:subprocess.run(['systemctl','show',name,'-p','ActiveState','--value'],check=True,capture_output=True,text=True,timeout=10).stdout.strip()
    maintenance=active('zitar-backup.service') in ('active','activating')
    errors=[name+' inactive' for name in SERVICES if active(name)!='active']
    master=json.loads(Path('/srv/zitar/runtime/zitar_master_portfolio_v1.json').read_text(encoding='utf-8-sig'))
    if master.get('authorities',{}).get('real_order') is not False:
        errors.append('paper-only authority invalid')
        maintenance=False
    result=progress(previous,time.time(),Path('/proc/sys/kernel/random/boot_id').read_text().strip(),errors,maintenance)
    atomic(status,result)
    print(json.dumps(dict(status=result['status'],observed_hours=result['observed_hours'],errors=errors)))
    if errors and not maintenance: raise SystemExit(1)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',required=True)
    cycle(p.parse_args().root)

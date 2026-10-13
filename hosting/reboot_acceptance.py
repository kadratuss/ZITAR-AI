"""Before/after controlled reboot checks, never changes accounts or approvals."""
import argparse
import json
import subprocess
from pathlib import Path
from urllib.request import urlopen
from zitar_next.store import atomic,digest,stamp

SERVICES=('zitar-production','zitar-learning','zitar-gateway','zitar-console','zitar-mobile-monitor',
          'zitar-v3-data','zitar-chat','zitar-rag','ollama','tailscaled')


def state():
    base=Path('/srv/zitar/runtime')
    master=json.loads((base/'zitar_master_portfolio_v1.json').read_text(encoding='utf-8-sig'))
    if master.get('authorities',{}).get('real_order') is not False:
        raise ValueError('paper-only master required')
    with urlopen('http://127.0.0.1:5020/api/paper-reset',timeout=30) as response: reset=json.load(response)
    if reset.get('status')!='COMPLETED' or reset.get('real_orders') is not False:
        raise ValueError('completed paper reset receipt required')
    with urlopen('http://127.0.0.1:8080/zitar-next/api/state',timeout=30) as response: learning=json.load(response)
    with urlopen('http://127.0.0.1:8080/api/entry-filter',timeout=30) as response: entry=json.load(response)
    if entry.get('state')!='COMPLETE': raise ValueError('completed experiment required')
    for service in SERVICES:
        subprocess.run(['systemctl','is-active','--quiet',service],check=True)
        subprocess.run(['systemctl','is-enabled','--quiet',service],check=True)
    for timer in ('zitar-backup.timer','zitar-backup-monitor.timer','zitar-forward-study.timer'):
        subprocess.run(['systemctl','is-active','--quiet',timer],check=True)
    return dict(updated=stamp(),boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                reset_sha256=digest(reset),reset_id=reset['id'],proposals=len(learning.get('proposals',[])),
                active=learning.get('active',[]),entry_result_sha256=digest(entry),real_orders=False)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('phase',choices=['before','after']);args=p.parse_args()
    area=Path('/srv/zitar/restore-tests');current=state()
    if args.phase=='before':
        atomic(area/'reboot-before.json',current)
    else:
        previous=json.loads((area/'reboot-before.json').read_text())
        if previous['boot_id']==current['boot_id']: raise ValueError('reboot not observed')
        if current['reset_sha256']!=previous['reset_sha256']: raise ValueError('reset receipt changed')
        if current['entry_result_sha256']!=previous['entry_result_sha256']: raise ValueError('research result changed')
        if current['active']!=previous['active']: raise ValueError('strategy activation changed')
        if current['proposals']<previous['proposals']: raise ValueError('proposal history lost')
        atomic(area/'reboot-acceptance.json',dict(current,state='PASSED',services=list(SERVICES),
            reset_receipt_preserved=True,research_results_preserved=True,active_strategy_state_preserved=True,
            limitations=['A short reboot check does not establish 24-hour availability.',
                         'Reset receipt/history checks do not replace exchange reconciliation for real orders.']))
    print(json.dumps(dict(phase=args.phase,checks='PASSED',real_orders=False)))


if __name__=='__main__': main()

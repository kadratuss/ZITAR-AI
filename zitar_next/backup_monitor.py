"""Local health signal; external notification target is configured at deployment."""
import argparse
import shutil
import time
from pathlib import Path

def health(directory,now=None):
    p=Path(directory);now=time.time() if now is None else now
    errors=[];disk=shutil.disk_usage(p)
    if disk.used/disk.total>=.8:errors.append('disk utilization >= 80%')
    if (p/'BACKUP_FAILED').exists():errors.append('backup failed')
    last=p/'BACKUP_LAST_SUCCESS'
    if not last.exists() or now-last.stat().st_mtime>26*3600:errors.append('verified offsite backup older than 26 hours or missing')
    return errors

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--directory',required=True);a=p.parse_args()
    errors=health(a.directory)
    if errors:raise SystemExit('; '.join(errors))
    print('Backup health OK')

#!/bin/sh
set -eu
umask 077
test -r /etc/zitar/backup.env || { echo 'Offsite backup configuration missing' >&2; exit 1; }
. /etc/zitar/backup.env
: "${ZITAR_BACKUP_REMOTE:?Encrypted offsite destination required}"
: "${ZITAR_RCLONE_CONFIG:?Private rclone configuration required}"
exec 9>/run/zitar-backup.lock
flock -n 9 || exit 1
services='zitar-gateway zitar-console zitar-learning zitar-production zitar-v3-data zitar-v3.timer'
active=''
for service in $services; do
    if systemctl is-active --quiet "$service"; then active="$active $service"; fi
done
test -n "$active" || exit 0
restart_services() { systemctl start $active; }
# STOP includes supervisor child groups; no state writer remains during snapshot.
trap restart_services EXIT
systemctl stop $active
systemctl stop zitar-v3.service
cd /srv/zitar/runtime
/srv/zitar/venv/bin/python -m zitar_next.hosting backup --base /srv/zitar/runtime --next-root /srv/zitar/data/next --output /srv/zitar/backups
# Resume trading simulation before potentially slow offsite upload.
restart_services
trap - EXIT
/srv/zitar/venv/bin/python -m zitar_next.backup_guard --directory /srv/zitar/backups --remote "$ZITAR_BACKUP_REMOTE" --config "$ZITAR_RCLONE_CONFIG" --keep 7
rm -f /srv/zitar/backups/BACKUP_FAILED
date -u > /srv/zitar/backups/BACKUP_LAST_SUCCESS

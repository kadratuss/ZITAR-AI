#!/bin/sh
set -eu
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

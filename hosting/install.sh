#!/bin/sh
# Ubuntu 24.04 preparation. Never starts a second portfolio owner.
set -eu
test "$(id -u)" = 0 || { echo 'Run as root on the selected VPS'; exit 1; }
test -f /srv/zitar/runtime/zitar_next/requirements.txt
apt-get update
apt-get install -y python3 python3-venv python3-pip rclone util-linux
id zitar >/dev/null 2>&1 || useradd --system --home-dir /srv/zitar --shell /usr/sbin/nologin zitar
install -d -o zitar -g zitar /srv/zitar/data /srv/zitar/backups
python3 -m venv /srv/zitar/venv
/srv/zitar/venv/bin/python -m pip install -r /srv/zitar/runtime/hosting/requirements.txt
/srv/zitar/venv/bin/python -m pip check
chown -R zitar:zitar /srv/zitar/runtime /srv/zitar/data /srv/zitar/backups
install -d -m 700 /srv/zitar/restore-tests
for service in production learning console gateway v3-data v3 chat rag mobile-monitor forward-study entry-filter cloud-restore-check operations-watch; do
    install -m 644 "/srv/zitar/runtime/hosting/zitar-$service.service" /etc/systemd/system/
done
install -m 644 /srv/zitar/runtime/hosting/zitar-backup.service /etc/systemd/system/
install -m 644 /srv/zitar/runtime/hosting/zitar-backup-alert.service /etc/systemd/system/
install -m 644 /srv/zitar/runtime/hosting/zitar-backup-monitor.service /etc/systemd/system/
install -m 644 /srv/zitar/runtime/hosting/zitar-backup-monitor.timer /etc/systemd/system/
install -m 644 /srv/zitar/runtime/hosting/zitar-backup.timer /etc/systemd/system/
install -m 644 /srv/zitar/runtime/hosting/zitar-v3.timer /etc/systemd/system/
install -m 644 /srv/zitar/runtime/hosting/zitar-forward-study.timer /etc/systemd/system/
install -m 644 /srv/zitar/runtime/hosting/zitar-operations-watch.timer /etc/systemd/system/
systemctl daemon-reload
echo 'Prepared only. Transfer state, verify dependencies and source-owner shutdown before enabling services.'

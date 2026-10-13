#!/bin/sh
set -eu
curl -fsSL https://ollama.com/install.sh -o /root/zitar-ollama-install.sh
sh /root/zitar-ollama-install.sh
mkdir -p /etc/systemd/system/ollama.service.d
cp /srv/zitar/runtime/hosting/ollama-kvm2.conf /etc/systemd/system/ollama.service.d/zitar.conf
systemctl daemon-reload
systemctl restart ollama
ollama pull qwen2.5:7b

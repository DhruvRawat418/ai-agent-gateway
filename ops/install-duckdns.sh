#!/usr/bin/env bash
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then
  echo 'Run with sudo bash ops/install-duckdns.sh on EC2.' >&2
  exit 1
fi
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
install -d -m 755 /usr/local/lib/gateway
install -m 644 "$script_dir/update_duckdns.py" /usr/local/lib/gateway/update_duckdns.py
install -m 644 "$script_dir/gateway-duckdns.service" /etc/systemd/system/gateway-duckdns.service
install -m 644 "$script_dir/gateway-duckdns.timer" /etc/systemd/system/gateway-duckdns.timer
python3 - <<'PY'
import getpass
import json
import os
from pathlib import Path
import re
path=Path('/etc/gateway-duckdns.json')
if path.exists():
    path.chmod(0o600)
    print('Using existing protected DuckDNS configuration.')
else:
    token=getpass.getpass('Paste your DuckDNS account token (hidden): ').strip()
    if not re.fullmatch(r'[A-Za-z0-9_-]+', token):
        raise SystemExit('Token is empty or invalid; no configuration saved.')
    fd=os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd,'w') as file:
        json.dump({'domain':'dhruvaigateway','token':token},file)
    print('Saved protected DuckDNS configuration.')
PY
systemctl daemon-reload
# Enable recurring updates only after the first request succeeds.
systemctl start gateway-duckdns.service
systemctl enable --now gateway-duckdns.timer
systemctl list-timers gateway-duckdns.timer --no-pager
journalctl -u gateway-duckdns.service -n 5 --no-pager
echo 'Installation completed. Verify the hostname resolves to the EC2 public IP.'

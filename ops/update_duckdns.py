#!/usr/bin/env python3
"""Run on the EC2 host. Never print request URLs or secret values."""
import ipaddress
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlencode
from urllib.request import Request, build_opener, ProxyHandler

CONFIG = Path('/etc/gateway-duckdns.json')

def update(config, opener=None):
    domain = config['domain']
    token = config['token'].strip()
    if not re.fullmatch(r'[a-z0-9-]+', domain) or not token:
        raise ValueError('Invalid configuration')
    # Metadata must be reached directly, not through an environment proxy.
    opener = opener or build_opener(ProxyHandler({}))
    def fetch(request):
        with opener.open(request, timeout=15) as response:
            return response.read(8192).decode().strip()
    metadata_token = fetch(Request('http://169.254.169.254/latest/api/token',
        method='PUT', headers={'X-aws-ec2-metadata-token-ttl-seconds':'60'}))
    address = fetch(Request('http://169.254.169.254/latest/meta-data/public-ipv4',
        headers={'X-aws-ec2-metadata-token':metadata_token}))
    ipaddress.IPv4Address(address)
    query = urlencode({'domains':domain, 'token':token, 'ip':address})
    result = fetch(Request('https://www.duckdns.org/update?' + query))
    if result != 'OK':
        raise RuntimeError('DNS provider rejected update')
    return address

def main():
    try:
        address = update(json.loads(CONFIG.read_text()))
        print('DuckDNS update accepted for public IPv4 ' + address)
        return 0
    except Exception:
        # HTTP errors can contain the full token-bearing URL; never log them.
        print('DuckDNS update failed. Check configuration and network access.', file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())

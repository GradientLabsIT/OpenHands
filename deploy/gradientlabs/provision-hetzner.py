import ipaddress
import json
import os
from pathlib import Path
import subprocess
import tempfile
import urllib.request
root = Path(__file__).parent
os.umask(0o077)
with tempfile.TemporaryDirectory(prefix='openhands-provider-') as cache:
    env = dict(os.environ, APX_CONFIG_DIR=str(root / 'recipes'), APX_CACHE_DIR=cache)
    def api(method, path, body=None):
        args = ['apx', 'req', '-q', 'gradientlabs-hetzner', method, path]
        if body is not None:
            args += ['-d', json.dumps(body)]
        result = subprocess.run(args, env=env, capture_output=True, text=True)
        if result.returncode:
            detail = json.loads(result.stdout).get('error', {}) if result.stdout.strip().startswith('{') else {}
            raise RuntimeError(f"Provider error: {detail.get('code', 'unknown')}: {detail.get('message', result.stderr[-200:])}")
        return json.loads(result.stdout) if result.stdout.strip() else {}
    name = 'openhands-01-gradientlabs'
    existing = [s for s in api('GET', '/servers')['servers'] if s['name'] == name]
    if existing:
        server = existing[0]
    else:
        source = str(ipaddress.ip_address(urllib.request.urlopen('https://api.ipify.org', timeout=15).read().decode())) + '/32'
        firewall = next(f for f in api('GET', '/firewalls')['firewalls'] if f['name'] == name + '-ingress')
        api('POST', f'/firewalls/{firewall["id"]}/actions/set_rules', {'rules': [
            {'direction': 'in', 'protocol': 'tcp', 'port': '22', 'source_ips': [source, '62.238.24.212/32'], 'description': 'Operator and private gateway SSH'},
            {'direction': 'in', 'protocol': 'udp', 'port': '41641', 'source_ips': ['0.0.0.0/0', '::/0'], 'description': 'Tailscale transport'},
            {'direction': 'in', 'protocol': 'icmp', 'source_ips': ['0.0.0.0/0', '::/0'], 'description': 'Network diagnostics'}]})
        cloud_init = '''#cloud-config
package_update: true
packages: [docker.io, docker-compose-v2, docker-buildx, git, curl, jq, python3, ca-certificates]
ssh_pwauth: false
runcmd:
  - [systemctl, enable, --now, docker]
'''
        server = api('POST', '/servers', {'name': name, 'server_type': os.environ.get('OPENHANDS_SERVER_TYPE', 'cax41'), 'image': 'ubuntu-24.04', 'location': os.environ.get('OPENHANDS_LOCATION', 'fsn1'), 'ssh_keys': [111858856, 25774052], 'firewalls': [{'firewall': firewall['id']}], 'labels': {'project': 'openhands', 'owner': 'gradientlabs'}, 'user_data': cloud_init})['server']
    output = {'provider': 'hetzner', 'id': server['id'], 'name': server['name'], 'public_ipv4': server['public_net']['ipv4']['ip'], 'server_type': server['server_type']['name'], 'memory_GB': server['server_type']['memory'], 'disk_GB': server['server_type']['disk']}
    (root / 'server.json').write_text(json.dumps(output, indent=2) + '\n')
    print(json.dumps(output))

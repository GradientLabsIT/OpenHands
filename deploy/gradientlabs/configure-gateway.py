import ipaddress
import json
import subprocess
import shlex
import time
import urllib.request
import urllib.error
from pathlib import Path

root = Path(__file__).parent
server = json.loads((root / 'server.json').read_text())
address = str(ipaddress.ip_address(server['public_ipv4']))
platform = 'root@100.87.94.92'
identity = str(Path.home() / '.ssh/id_ed25519_luca_gradientlabs')
host = 'root@' + address

def ssh(target, command, data=None):
    args = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10']
    if target == host:
        args += ['-i', identity]
    result = subprocess.run(args + [target, command], input=data, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.decode()[-400:])
    return result.stdout

ports = json.loads(ssh(host, 'cd /opt/openhands && PATH="$PWD:$PATH" ./dcx ports --json'))
port = int(ports['canvas']['8000'])
bridge_port = 18080
ssh(host, 'umask 077; cat > /opt/openhands/bridge.py.tmp && mv /opt/openhands/bridge.py.tmp /opt/openhands/bridge.py', (root / 'bridge.py').read_bytes())
ssh(host, 'cat > /etc/systemd/system/openhands-bridge.service.tmp && mv /etc/systemd/system/openhands-bridge.service.tmp /etc/systemd/system/openhands-bridge.service', (root / 'openhands-bridge.service').read_bytes())
ssh(host, "systemctl disable --now openhands-bridge.socket 2>/dev/null || true; systemctl stop 'openhands-bridge@*.service'; systemctl daemon-reload && systemctl enable openhands-bridge.service && systemctl restart openhands-bridge.service")
public_key = ssh(platform, 'cat /root/.ssh/openhands-gateway.pub').decode().strip()
host_key = ssh(host, 'cat /etc/ssh/ssh_host_ed25519_key.pub').decode().strip().split()[:2]
line = f'from="62.238.24.212",command="/bin/false",restrict,port-forwarding,permitopen="127.0.0.1:{bridge_port}" {public_key}'
ssh(host, "python3 -c " + shlex.quote((root / "update-authorized-keys.py").read_text()), line.encode())
ssh(platform, 'umask 077; cat > /root/.ssh/openhands-known-hosts', (address + ' ' + ' '.join(host_key) + '\n').encode())
unit = f'''[Unit]
Description=Private OpenHands gateway
After=network-online.target tailscaled.service
Wants=network-online.target

[Service]
ExecStart=/usr/bin/ssh -NT -i /root/.ssh/openhands-gateway -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=/root/.ssh/openhands-known-hosts -o ExitOnForwardFailure=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -L 127.0.0.1:18080:127.0.0.1:{bridge_port} root@{address}
Restart=always
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only

[Install]
WantedBy=multi-user.target
'''
(root / 'openhands-gateway.service').write_text(unit)
ssh(platform, 'cat > /etc/systemd/system/openhands-gateway.service', unit.encode())
ssh(platform, 'systemctl daemon-reload && systemctl enable openhands-gateway.service && systemctl restart openhands-gateway.service && tailscale serve --bg --https=10443 http://127.0.0.1:18080')
result = dict(server, deployment_path='/opt/openhands', port=port, gateway_port=bridge_port,
              url='https://platform-01-gradientlabs.tail7c4d08.ts.net:10443/canvas',
              image_version='1.25.0', image_digest='sha256:10190cdede885f74853567f4aa44b33de094139a940df75f4b204a2b6df73c57')
(root / 'deployment.json').write_text(json.dumps(result, indent=2) + '\n')
key = subprocess.check_output(['gradient-vault', '--vault', 'gradientlabs', 'get', 'OPENHANDS_SESSION_API_KEY'], text=True).strip()
base = result['url'].removesuffix('/canvas')
for attempt in range(25):
    try:
        request = urllib.request.Request(base + '/server_info', headers={'X-Session-API-Key': key})
        with urllib.request.urlopen(request, timeout=5) as response:
            if response.status == 200:
                break
    except (urllib.error.URLError, TimeoutError):
        pass
    time.sleep(2)
else:
    raise RuntimeError('Gateway backend did not become ready.')
print(json.dumps(result))

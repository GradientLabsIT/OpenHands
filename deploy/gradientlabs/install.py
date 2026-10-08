import ipaddress
import json
import subprocess
from pathlib import Path

root = Path(__file__).parent
server = json.loads((root / 'server.json').read_text())
address = str(ipaddress.ip_address(server['public_ipv4']))
identity = str(Path.home() / '.ssh/id_ed25519_luca_gradientlabs')
ssh = ['ssh', '-o', 'BatchMode=yes', '-i', identity, 'root@' + address]
subprocess.run(ssh + ['cloud-init status --wait && install -d -m 700 /opt/openhands/state /opt/openhands/projects /opt/openhands/state/acp-subscriptions/.claude /opt/openhands/state/acp-subscriptions/.codex && chown 10001:10001 /opt/openhands/state/acp-subscriptions /opt/openhands/state/acp-subscriptions/.claude /opt/openhands/state/acp-subscriptions/.codex'], check=True)
subprocess.run(['scp', '-o', 'BatchMode=yes', '-i', identity, str(root / 'compose.yaml'), str(root / 'Dockerfile'), str(root / '.dockerignore'), str(root / 'patch-codex-acp.py'), str(Path.home() / 'dev-tools/bin/dcx'), 'root@' + address + ':/opt/openhands/'], check=True)
values = {}
for name in ['OPENHANDS_SESSION_API_KEY', 'OPENHANDS_SETTINGS_ENCRYPTION_KEY']:
    values[name] = subprocess.check_output(['gradient-vault', '--vault', 'gradientlabs', 'get', name], text=True).strip()
if any(len(value) < 32 or any(c.isspace() for c in value) for value in values.values()):
    raise RuntimeError('Application credentials must contain at least 32 non-whitespace characters.')
data = 'LOCAL_BACKEND_API_KEY=' + values['OPENHANDS_SESSION_API_KEY'] + '\nOH_SESSION_API_KEYS_0=' + values['OPENHANDS_SESSION_API_KEY'] + '\nOH_SECRET_KEY=' + values['OPENHANDS_SETTINGS_ENCRYPTION_KEY'] + '\n'
subprocess.run(ssh + ['umask 077; cat > /opt/openhands/.env'], input=data, text=True, check=True)
command = '''cd /opt/openhands && chmod +x dcx && PATH="$PWD:$PATH" ./dcx build canvas &&
image=$(PATH="$PWD:$PATH" ./dcx config --format json | jq -r '.services.canvas.image') &&
docker run --rm --user root --entrypoint sh -v "$PWD/state:/state" -v "$PWD/projects:/projects" "$image" -c 'chown $(id -u openhands):$(id -g openhands) /state /projects && chmod 700 /state /projects' &&
PATH="$PWD:$PATH" ./dcx up -d &&
docker exec $(PATH="$PWD:$PATH" ./dcx ps -q canvas) python -c 'import os; forbidden=[name for name in ["ANTHROPIC_API_KEY","ANTHROPIC_AUTH_TOKEN","ANTHROPIC_BASE_URL","OPENAI_API_KEY","CODEX_API_KEY","OPENAI_BASE_URL"] if os.getenv(name)]; assert not forbidden, "Conflicting provider environment: " + ",".join(forbidden)' '''
subprocess.run(ssh + [command], check=True)

subprocess.run(["uv", "run", "--no-project", "python", str(root / "configure-gateway.py")], check=True)

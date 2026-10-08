"""Read native subscription catalogs from a candidate image without inference."""

import json
import ipaddress
from pathlib import Path
import subprocess
import urllib.request
import uuid
import shlex


ROOT = Path(__file__).parent
IMAGE = next(line.split(':', 1)[1].strip() for line in (ROOT / 'compose.yaml').read_text().splitlines() if line.strip().startswith('image:'))
SERVER = json.loads((ROOT / 'server.json').read_text())
SSH = ["ssh", "-o", "BatchMode=yes", "-i", str(Path.home() / '.ssh/id_ed25519_luca_gradientlabs'), "root@" + str(ipaddress.ip_address(SERVER['public_ipv4']))]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

CLAUDE_SCRIPT = r'''
import fs from "node:fs";
import { query } from "/acp-node/lib/node_modules/@agentclientprotocol/claude-agent-acp/node_modules/@anthropic-ai/claude-agent-sdk/sdk.mjs";
const input = JSON.parse(fs.readFileSync(0, "utf8"));
process.env.CLAUDE_CODE_OAUTH_TOKEN = input.token;
process.env.CLAUDE_CONFIG_DIR = "/tmp/claude-catalog-probe";
fs.mkdirSync(process.env.CLAUDE_CONFIG_DIR, { mode: 0o700, recursive: true });
async function* messages() { await new Promise(() => {}); }
const session = query({ prompt: messages(), options: {
  cwd: "/tmp", tools: [], mcpServers: {}, settingSources: [],
} });
try {
  const models = await session.supportedModels();
  console.log(JSON.stringify({ provider: "claude-code", models }));
} finally { session.close(); }
process.exit(0);
'''

CODEX_SCRIPT = r'''
import base64, hashlib, json, os, selectors, subprocess, time
from pathlib import Path
auth = Path("/probe-auth/auth.json")
original_hash = hashlib.sha256(auth.read_bytes()).digest()
original_stat = auth.stat()
access = json.loads(auth.read_text())["tokens"]["access_token"]
claims = json.loads(base64.urlsafe_b64decode(access.split(".")[1] + "=="))
if claims.get("exp", 0) - time.time() < 1800:
    raise RuntimeError("Refresh the native server login before probing: access token is near expiry.")
del access, claims
home = Path("/tmp/codex-catalog-probe")
home.mkdir(mode=0o700)
(home / "auth.json").symlink_to("/probe-auth/auth.json")
os.environ["CODEX_HOME"] = str(home)
cli = "/acp-node/lib/node_modules/@agentclientprotocol/codex-acp/node_modules/.bin/codex"
process = subprocess.Popen([cli, "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
buffer = bytearray()
def send(method, params, identifier=None):
    payload = dict(method=method, params=params)
    if identifier is not None: payload["id"] = identifier
    process.stdin.write(json.dumps(payload) + "\n"); process.stdin.flush()
def response(identifier):
    deadline = time.monotonic() + 40
    selector = selectors.DefaultSelector(); selector.register(process.stdout, selectors.EVENT_READ)
    try:
        while time.monotonic() < deadline:
            if b"\n" not in buffer:
                if not selector.select(timeout=1): continue
                data = os.read(process.stdout.fileno(), 65536)
                if not data: raise RuntimeError("Native Codex exited before answering.")
                buffer.extend(data)
                continue
            line, _, remainder = buffer.partition(b"\n")
            buffer[:] = remainder
            value = json.loads(line)
            if value.get("id") == identifier:
                if "error" in value: raise RuntimeError("Native Codex rejected the catalog request.")
                return value["result"]
    finally: selector.close()
    raise TimeoutError("Native Codex catalog timed out.")
try:
    send("initialize", {"clientInfo": {"name": "gradientlabs-model-probe", "version": "1"}}, 1); response(1)
    send("initialized", {})
    send("account/read", {"refreshToken": False}, 2)
    account = response(2)
    if (account.get("account") or {}).get("type") != "chatgpt": raise RuntimeError("Codex does not have a ChatGPT subscription login.")
    send("model/list", {"includeHidden": False, "limit": 100}, 3)
    models = response(3).get("data", [])
    if hashlib.sha256(auth.read_bytes()).digest() != original_hash or auth.stat().st_mtime_ns != original_stat.st_mtime_ns:
        raise RuntimeError("Native login cache changed during the catalog probe.")
    print(json.dumps({"provider": "codex", "auth_type": "chatgpt", "models": [{key: model.get(key) for key in ["id", "model", "displayName", "supportedReasoningEfforts"]} for model in models]}))
finally:
    process.terminate()
    try: process.wait(timeout=5)
    except subprocess.TimeoutExpired: process.kill(); process.wait()
'''


def probe(command, payload):
    name = 'openhands-catalog-probe-' + uuid.uuid4().hex
    command = command.replace('docker run --rm', 'docker run --rm --cap-drop ALL --security-opt no-new-privileges --name ' + name, 1)
    try:
        result = subprocess.run(SSH + [command], input=payload, text=True, capture_output=True, timeout=75)
        if result.returncode:
            raise RuntimeError('Candidate native catalog probe failed; provider output suppressed.')
        return json.loads(result.stdout)
    finally:
        subprocess.run(SSH + ['docker rm -f ' + name + ' >/dev/null 2>&1'], capture_output=True, timeout=20)


def main():
    key = subprocess.check_output(["gradient-vault", "--vault", "gradientlabs", "get", "OPENHANDS_SESSION_API_KEY"], text=True).strip()
    request = urllib.request.Request(
        "https://openhands.gradientlabs.it/api/settings/secrets/CLAUDE_CODE_OAUTH_TOKEN",
        headers={"X-Session-API-Key": key},
    )
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=15) as response:
        token = response.read().decode().strip()
    if not isinstance(token, str) or not token:
        raise RuntimeError("Claude subscription secret is unavailable.")
    command = "docker run --rm -i --user 10001:10001 --entrypoint node " + shlex.quote(IMAGE) + " --input-type=module -e " + shlex.quote(CLAUDE_SCRIPT)
    claude = probe(command, json.dumps({"token": token}))
    del token
    print(json.dumps(claude))
    command = "docker run --rm -i --user 10001:10001 -v /opt/openhands/state/acp-subscriptions/.codex/auth.json:/probe-auth/auth.json:ro --entrypoint python " + shlex.quote(IMAGE) + " -"
    codex = probe(command, CODEX_SCRIPT)
    print(json.dumps(codex))
    catalog = json.loads((ROOT / 'subscription-models.json').read_text())
    offered = {
        'claude-code': {row['value'] for row in claude['models']},
        'codex': {row['id'] for row in codex['models']},
    }
    for provider, entry in catalog.items():
        requested = {row['id'] for row in entry['available_models']}
        if not requested <= offered[provider]:
            raise RuntimeError('Native subscription does not offer every configured model: ' + provider)
    resolved = {row['value']: row.get('resolvedModel') for row in claude['models']}
    for alias, model in catalog['claude-code']['resolved_models'].items():
        if resolved.get(alias) != model:
            raise RuntimeError('Claude native alias no longer matches its displayed model version: ' + alias)
    print('All configured subscription model IDs are offered by the candidate native CLIs.')


if __name__ == "__main__":
    main()

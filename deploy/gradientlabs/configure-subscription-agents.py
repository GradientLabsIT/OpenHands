"""Configure separate ACP profiles without importing or replacing provider logins."""
import argparse
import json
import subprocess
import urllib.request

BASE = 'https://platform-01-gradientlabs.tail7c4d08.ts.net:10443'

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--activate-claude', action='store_true', help='Explicitly select Claude Code as the default agent.')
    args = parser.parse_args()
    key = subprocess.check_output(['gradient-vault', '--vault', 'gradientlabs', 'get', 'OPENHANDS_SESSION_API_KEY'], text=True).strip()
    opener = urllib.request.build_opener(NoRedirect())
    def api(path, body=None):
        req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(), headers={'X-Session-API-Key': key, 'Content-Type': 'application/json'})
        with opener.open(req, timeout=30) as response:
            return json.load(response)

    expected = [('Claude-Code-Subscription', 'claude-code', ['CLAUDE_CODE_OAUTH_TOKEN']), ('Codex-Subscription', 'codex', [])]
    listing = api('/api/agent-profiles')
    existing = {item['name'] for item in listing['profiles']}
    for name, provider, secrets in expected:
        if name in existing:
            saved = api('/api/agent-profiles/' + name)['profile']
            if saved.get('agent_kind') != 'acp' or saved.get('acp_server') != provider or saved.get('secret_refs') != secrets or saved.get('mcp_server_refs') != []:
                raise RuntimeError('Existing agent profile requires manual reconciliation: ' + name)
        else:
            profile = {'name': name, 'agent_kind': 'acp', 'acp_server': provider, 'acp_model': None, 'secret_refs': secrets, 'mcp_server_refs': [], 'acp_startup_timeout': 120}
            api('/api/agent-profiles/' + name, profile)
        print('Subscription profile ready: ' + name)
    if args.activate_claude:
        active = api('/api/agent-profiles/Claude-Code-Subscription')['profile']['id']
        api('/api/agent-profiles/' + active + '/activate', {})
        print('Default agent: Claude Code subscription.')

if __name__ == '__main__':
    main()

import argparse
import json
import subprocess
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument('--llm-profile', default='gradientlabs-default')
args = parser.parse_args()
if args.llm_profile != 'gradientlabs-default':
    parser.error('This deployment helper only configures the shared deployment profile.')
key = subprocess.check_output(['gradient-vault', '--vault', 'gradientlabs', 'get', 'OPENHANDS_SESSION_API_KEY'], text=True).strip()
base = 'https://platform-01-gradientlabs.tail7c4d08.ts.net:10443'
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None
opener = urllib.request.build_opener(NoRedirect())
def api(path, body=None):
    request = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                     headers={'X-Session-API-Key': key, 'Content-Type': 'application/json'})
    with opener.open(request, timeout=15) as response:
        return json.load(response)
api('/api/profiles/' + args.llm_profile)
profile = api('/api/agent-profiles/default')['profile']
if profile.get('agent_kind') != 'openhands':
    raise RuntimeError('Default profile belongs to another agent; refusing to overwrite it.')
profile['llm_profile_ref'] = args.llm_profile
api('/api/agent-profiles/default', profile)
api('/api/profiles/' + args.llm_profile + '/activate', {})
assert api('/api/agent-profiles/default')['profile']['llm_profile_ref'] == args.llm_profile
print('Default OpenHands agent linked to the existing deployment LLM profile.')

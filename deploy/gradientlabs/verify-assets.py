import argparse
import json
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--run', required=True)
args = parser.parse_args()
cli = Path(__file__).resolve().parents[2] / '.agents/skills/verify-openhands/scripts/control-openhands'
expression = r'''(async () => {
  const urls = new Set(performance.getEntriesByType('resource')
    .map(entry => entry.name)
    .filter(url => new URL(url).origin === location.origin && /\/assets\/.*\.(js|css)$/.test(new URL(url).pathname)));
  for (const node of document.querySelectorAll('script[src],link[href]')) {
    const url = node.src || node.href;
    if (new URL(url).origin === location.origin && /\/assets\/.*\.(js|css)$/.test(new URL(url).pathname)) urls.add(url);
  }
  for (const url of [...urls]) {
    if (/\/manifest-.*\.js$/.test(url)) {
      const response = await fetch(url, {cache: 'no-store'});
      const content = await response.text();
      for (const match of content.matchAll(/["']([^"']+\.(?:js|css))["']/g)) {
        const asset = new URL(match[1], location.origin);
        if (asset.origin === location.origin && asset.pathname.includes('/assets/')) urls.add(asset.href);
      }
    }
  }
  const results = await Promise.all([...urls].map(async url => {
    try {
      const response = await fetch(url, {cache: 'no-store'});
      await response.arrayBuffer();
      return {path: new URL(url).pathname, status: response.status};
    } catch (error) { return {path: new URL(url).pathname, status: 'fetch failed'}; }
  }));
  return {count: results.length, failed: results.filter(result => result.status !== 200)};
})()'''
p = subprocess.run([str(cli), 'browser', 'eval', expression, '--run', args.run], capture_output=True, text=True)
if p.returncode:
    raise SystemExit('Browser asset verification failed: ' + p.stdout[:500])
result = json.loads(p.stdout)['value']
print(json.dumps(result))
if result['count'] <= 64 or result['failed']:
    raise SystemExit(1)

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { mkdtempSync, writeFileSync, existsSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { spawn } from 'node:child_process';

const cli = resolve('.agents/skills/verify-openhands/scripts/control-openhands.mjs');
const call = args => new Promise(resolve => {
  const child = spawn(process.execPath, [cli, ...args]);
  let output = '';
  child.stdout.on('data', data => output += data);
  child.stderr.on('data', data => output += data);
  child.on('close', code => resolve({ code, output }));
});

test('remote verification authenticates, protects lifecycle, and purges only local credentials', async () => {
  const dir = mkdtempSync(join(tmpdir(), 'canvas-remote-test-'));
  const key = 'test-only-session-key';
  writeFileSync(join(dir, 'key'), key, { mode: 0o600 });
  const server = createServer((request, response) => {
    if (request.url !== '/canvas' && request.headers['x-session-api-key'] !== key) {
      response.writeHead(401).end('{}');
      return;
    }
    response.setHeader('Content-Type', 'application/json');
    response.end(JSON.stringify({ version: '1.53.0' }));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const url = `http://127.0.0.1:${server.address().port}/canvas`;
  const run = join(dir, 'run');
  try {
    let result = await call(['attach', '--url', url, '--run', run, '--api-key-file', join(dir, 'key')]);
    assert.equal(result.code, 0, result.output);
    assert.ok(!result.output.includes(key));
    result = await call(['doctor', '--run', run]);
    assert.equal(result.code, 0, result.output);
    for (const args of [['restart'], ['service', 'stop', 'agent-server'], ['workspace', 'open', 'relative-path']]) {
      result = await call([...args, '--run', run]);
      assert.equal(result.code, 2, result.output);
    }
    result = await call(['stop', '--run', run, '--purge-private']);
    assert.equal(result.code, 0, result.output);
    assert.equal(JSON.parse(result.output).launcherStopped, false);
    assert.equal(existsSync(join(run, 'private')), false);
    assert.equal((await fetch(url)).status, 200);
    writeFileSync(join(dir, 'bad-key'), 'invalid');
    const badRun = join(dir, 'bad-run');
    result = await call(['attach', '--url', url, '--run', badRun, '--api-key-file', join(dir, 'bad-key')]);
    assert.equal(result.code, 3, result.output);
    assert.equal(existsSync(badRun), false);
  } finally {
    await new Promise(resolve => server.close(resolve));
    rmSync(dir, { recursive: true, force: true });
  }
});

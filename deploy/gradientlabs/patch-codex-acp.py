"""Avoid unnecessary interactive reauthentication for a cached ChatGPT login."""
from pathlib import Path

path = Path('/acp-node/lib/node_modules/@agentclientprotocol/codex-acp/dist/index.js')
source = path.read_text()
original = 'async authenticateWithChatGpt() {\n    const accountResponse = await this.codexClient.accountRead({ refreshToken: true });'
replacement = original.replace('refreshToken: true', 'refreshToken: false')
if source.count(original) != 1:
    raise RuntimeError('Pinned Codex ACP implementation changed; review the cached-login patch.')
path.write_text(source.replace(original, replacement))

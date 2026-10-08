#!/usr/bin/env bash
set -euo pipefail
cd /opt/openhands
port=$(PATH="$PWD:$PATH" ./dcx ports --json | jq -er '.canvas["8000"]')
exec /usr/bin/socat STDIO "TCP:127.0.0.1:$port"

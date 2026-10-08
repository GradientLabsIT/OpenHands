# Gradientlabs OpenHands deployment

OpenHands Agent Canvas 1.25.0 is built from the official multi-architecture image, pinned by digest in `Dockerfile`, with the subscription-login patch described below. The fork contains deployment and verification tooling.

Host: Hetzner `openhands-01-gradientlabs`, CAX41, 16 ARM vCPUs, 32 GB RAM, 320 GB SSD, Falkenstein. The observed catalog price is €40.99/month plus the primary IPv4 charge. No extra volume is provisioned. Container resources are limited to 12 CPUs and 24 GB RAM; raise those limits when measured concurrency requires it.

URL: https://platform-01-gradientlabs.tail7c4d08.ts.net:10443/canvas

Connect to Tailscale, then enter the `OPENHANDS_SESSION_API_KEY` credential from the `gradientlabs` Agent Vault. The key is never embedded in HTML. Model credentials are configured in application settings and encrypted with `OPENHANDS_SETTINGS_ENCRYPTION_KEY`.

Only loopback publishes the application. The existing platform provides HTTPS through a dedicated Tailscale Serve port and a persistent SSH forwarding service. A single asynchronous loopback proxy caches Docker port discovery for sixty seconds and refreshes on connection failure, so VM and Docker restarts do not leave the gateway pointing at an old port. Gateway SSH access permits only the fixed bridge port and rejects commands. Existing platform Serve handlers are retained. Public access is not configured.

## Reproduce

Run from the repository root. Provider and application credentials are consumed privately from the shared vault. SSH uses the operator's existing key; the new host key must first be verified and enrolled in the operator's native known-hosts file.

```sh
OPENHANDS_SERVER_TYPE=cax41 OPENHANDS_LOCATION=fsn1 uv run --no-project python deploy/gradientlabs/provision-hetzner.py
uv run --no-project python deploy/gradientlabs/install.py
uv run --no-project python deploy/gradientlabs/configure-gateway.py
node --test deploy/gradientlabs/remote-verifier.test.mjs
ulimit -n 4096
uv run --no-project python deploy/gradientlabs/test_bridge.py
uv run --no-project python deploy/gradientlabs/test_gateway_keys.py
```

The provisioning script reuses a matching server. It does not delete servers. New provisioning requires the existing project SSH keys and OpenHands firewall. The gateway installer requires the existing platform gateway key pair.

Application state and settings live in `/opt/openhands/state`; agent project files live in `/opt/openhands/projects`. The default `/workspace/project` also mounts the persistent projects directory. Both directories are owned by the image's `openhands` UID/GID. The private `.env` is mode 0600. No Docker socket or host filesystem is exposed to the agent. This is a deployment for the subscription owner's trusted jobs, not separate tenant sandboxes.

## Updates and recovery

Before updating, stop the application with `PATH="$PWD:$PATH" ./dcx stop` from `/opt/openhands` and make a protected backup of `state`, `projects`, and `.env`. Preserve the vault encryption key; losing it prevents decrypting saved settings. Copy that backup off the VM using an approved private destination. A mounted state directory alone is not an off-host backup.

Change the pinned base release and digest together, run the installer, and rerun `configure-gateway.py`: `dcx` may allocate a different host port on recreation. The gateway helper refreshes its loopback bridge, restricted SSH key, pinned host key and systemd service, then restarts the forwarding connection. Recheck authenticated backend, automation health, UI login and a bounded asynchronous job. To roll back, restore the previous image pin and compatible state backup, then refresh the gateway again.

Linear credentials, repository authentication and the independent reviewer used by the `task` skill must be configured for each owning project. Do not substitute shared or retired-project credentials. The deployment does not by itself configure a ticket webhook or grant access to every repository.

The agent executes in the same container and Unix account as the services. It can access service environment and state, including model credentials and encryption material. Only the authorized subscription owner and reviewed repositories should use this deployment; encrypted settings do not isolate credentials from an agent. Use separately sandboxed workers for untrusted jobs.

No scheduled off-host backup is configured. Before important work, configure an approved backup destination and retention policy. Current state remains on the VM.

## First login and cold-browser verification

For the preconfigured shared deployment, choose **Skip for now** on first-run onboarding. On the connection screen, enter a host label and the `OPENHANDS_SESSION_API_KEY` from the `gradientlabs` vault, then connect. This is a server session key (64 hexadecimal characters), not an OpenAI/OpenRouter model key. The existing deployment model is already configured. Do not select OpenHands Cloud for this self-hosted server.

If running the full onboarding wizard resets the default agent to an unconfigured model profile, restore its reference to the existing LLM profile with:

```sh
uv run --no-project python deploy/gradientlabs/configure-default-agent.py
```

Infrastructure readiness checks do not prove that a fresh browser can render the app. Before handing off an update, attach a new verification run with `control-openhands`, start a fresh browser profile, clear the error tracker, skip onboarding for the existing configured backend, and perform API-key login. Require the home composer to render and a bounded real job to finish. Run the browser HTTP/2 asset gate, which fetches every discovered JS/CSS asset concurrently with `cache: no-store`:

```sh
uv run --no-project python deploy/gradientlabs/verify-assets.py --run "$OH_VERIFY_RUN"
```

Require zero asset failures and zero page/HTTP 502 errors. Repeat the fresh-browser flow after a full VM reboot without rerunning the gateway installer, then verify persisted conversations. A warm browser can hide missing JavaScript modules and does not replace this check.

## Subscription agents

The active agent is now `Claude-Code-Subscription` (Claude Code via ACP, dedicated Claude Max subscription token). `Codex-Subscription` is available under Settings → Agent and uses a separate server-side ChatGPT login. These profiles have no API-key secrets or MCP integrations enabled. Existing OpenHands/LLM profiles remain available for an explicit switch; their presence on Settings → LLM does not select them for an ACP conversation. Model selection is delegated to each provider unless an override is saved in its agent profile.

Claude uses a dedicated one-year OAuth token created with `claude setup-token` and stored encrypted as the `CLAUDE_CODE_OAUTH_TOKEN` application secret. Its profile permits only that secret. Codex uses a separate server-side ChatGPT login completed with `codex login --device-auth`; its native cache lives in `state/acp-subscriptions/.codex`, mode 0600. Both provider directories are bind-mounted persistently. Initial diagnostic copies of the Mac logins were replaced: the imported Claude credential file was removed and Codex's device login replaced its copied cache. Server and Mac no longer intentionally share refresh credentials. No unrelated Keychain/MCP tokens remain in the Claude credential file.

These credentials authorize use of the subscription account and are not limited to one repository. Agent processes and their terminal tools run under the same Unix account as the services and can read provider authentication and other service credentials. `secret_refs` restricts the application secret channel, not filesystem or environment access. This deployment is for the authorized owner's trusted jobs, not multi-tenant or untrusted repositories. Do not distribute a personal subscription to other users; provision separately authenticated workers for additional operators. Model usage follows the subscription's quota; no automatic API-key fallback is configured. The service healthcheck verifies service availability, not the provider's quota or login health.

Backups containing `state` or `.env` contain authentication material: encrypt them before off-host transfer. A restored cache can contain revoked or outdated login state and require fresh authentication. Claude's root config file can be recreated on container replacement; real Claude jobs were verified after replacement. Provider history/cache retention remains manual.

The deployment builds a small image from the same pinned upstream digest. Its only product patch changes Codex ACP's initial `account/read` to `refreshToken: false`: the adapter still requires an account of type `chatgpt`, and actual model requests still require valid provider authentication. The pinned adapter's forced refresh blocked for over ninety seconds despite a valid cached token and successful native Codex inference. The patch fails the build if that exact upstream function changes. Review it when updating the base image; it does not bypass provider authentication or enable an API-key fallback.

To reconcile subscription profiles without importing or replacing credentials:

```sh
uv run --no-project python deploy/gradientlabs/configure-subscription-agents.py
```

Authenticate providers through their native login flows, never by repeatedly cloning refresh credentials from another active device. For Claude, consume `claude setup-token` output privately into the application's `CLAUDE_CODE_OAUTH_TOKEN` secret; never paste it into chat or logs. For Codex, run its native CLI on the server as the `openhands` user with `login --device-auth` and complete browser authorization. To make Claude Code active explicitly, add `--activate-claude` to the profile helper. Otherwise rerunning it preserves the selected profile. Switch agents through Settings → Agent → profile menu → Set as active.

The service session key grants job execution under the subscription owner: do not distribute it to other account users. Claude's dedicated token was created on 2026-10-08 and the setup-token flow gives a one-year lifetime; schedule renewal before October 2027. On suspected compromise, stop access, revoke the provider session/token through native account controls, rotate the OpenHands session key in the vault, redeploy its environment and authenticate again. After a state rollback, discard restored provider login caches and complete fresh provider authentication rather than replaying old refresh tokens. Concurrent Codex jobs across a token-refresh boundary have not been verified; quota and auth health are not automatically monitored.

# Gradientlabs OpenHands deployment

OpenHands Agent Canvas 1.25.0 is deployed from the official multi-architecture image, pinned by digest in `compose.yaml`. The fork currently contains deployment and verification tooling; the deployed product image is the upstream release.

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

Application state and settings live in `/opt/openhands/state`; agent project files live in `/opt/openhands/projects`. The default `/workspace/project` also mounts the persistent projects directory. Both directories are owned by the image's `openhands` UID/GID. The private `.env` is mode 0600. No Docker socket or host filesystem is exposed to the agent. This is a shared trusted-team deployment, not separate tenant sandboxes.

## Updates and recovery

Before updating, stop the application with `PATH="$PWD:$PATH" ./dcx stop` from `/opt/openhands` and make a protected backup of `state`, `projects`, and `.env`. Preserve the vault encryption key; losing it prevents decrypting saved settings. Copy that backup off the VM using an approved private destination. A mounted state directory alone is not an off-host backup.

Change the pinned release and digest together, run the installer, and rerun `configure-gateway.py`: `dcx` may allocate a different host port on recreation. The gateway helper refreshes its loopback bridge, restricted SSH key, pinned host key and systemd service, then restarts the forwarding connection. Recheck authenticated backend, automation health, UI login and a bounded asynchronous job. To roll back, restore the previous image pin and compatible state backup, then refresh the gateway again.

Linear credentials, repository authentication and the independent reviewer used by the `task` skill must be configured for each owning project. Do not substitute shared or retired-project credentials. The deployment does not by itself configure a ticket webhook or grant access to every repository.

The agent executes in the same container and Unix account as the services. It can access service environment and state, including model credentials and encryption material. Only trusted operators and reviewed repositories should use this deployment; encrypted settings do not isolate credentials from an agent. Use separately sandboxed workers for untrusted jobs.

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

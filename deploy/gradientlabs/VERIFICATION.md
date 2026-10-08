# Deployment verification — 2026-10-08

Deployment: official Agent Canvas 1.25.0 image, pinned multiarch digest, on a dedicated Hetzner CAX41 with 32 GB RAM and 320 GB SSD. The fork deployment tooling is separate from the upstream product image.

Passed:

- Container starts with image-owned persistent state and project mounts; Docker reports healthy.
- Real private HTTPS URL serves Canvas, authenticated settings, SDK 1.53.0 and automation health.
- Unauthenticated settings access is rejected. HTML contains neither session nor settings encryption credentials.
- Real UI login, workspace selection, model profile validation and activation, conversation creation and follow-up messages work.
- A real coding job continued from `running` to `finished` after closing the verifier browser. The initial model incorrectly interpreted the requested marker as an environment variable; a follow-up corrected the fixture. Native execution then printed the literal `OPENHANDS_ASYNC_OK`.
- After a full VM reboot, the container returned healthy, the gateway reconnected through the stable loopback bridge without reconfiguration, authenticated doctor passed, the conversation remained finished, the file remained executable and its output stayed correct. The persisted conversation rendered in the real UI.
- Published Docker and bridge sockets bind only to loopback. Existing platform HTTPS handlers were retained.
- Node verifier authentication/lifecycle test and two SSH authorized-key preservation tests pass. Shell and Python syntax checks pass.
- Independent Claude CLI review of current deployment and harness changes completed with no unresolved Critical or High findings. Reviews used no tools or MCP capabilities.

A gateway key-filter bug initially removed the new VM's operator SSH keys. Recovery used Hetzner rescue, restored the original provider keys on the existing root disk, and returned to the installed OS. The updater now matches the gateway key blob, preserves operator keys, refuses an empty remaining key set, writes atomically and fsyncs. A fresh operator SSH connection passed after running the corrected helper. No data was lost.

The temporary OpenHands stack on the shared Pi was removed with its own `dcx down`; bind-mounted state was retained. Other applications were not stopped.

Remaining review observations and operational limits:

- The socket bridge performs port discovery for each connection and uses systemd's default connection limits. Large concurrency should be measured before raising limits or introducing a cached ingress.
- This is a trusted-team shared container; agent commands can access service environment and state. API authentication does not provide separate worker or tenant isolation.
- Automatic off-host backups are not configured. The documented backup/recovery procedure must be used before important updates; preserve the encryption key.
- Firewall operator/gateway addresses and provider SSH-key IDs are deployment-specific. Refresh them when network or operator access changes.
- Repo authentication, Linear integration/webhooks and native independent-reviewer authentication for the project `task` skill remain project setup, not validated ticket automation.
- The selected smoke-test profile uses OpenRouter `openai/gpt-4.1-mini`; production model choice and project budgets remain operator configuration.

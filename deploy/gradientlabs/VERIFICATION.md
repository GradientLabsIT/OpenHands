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

- The asynchronous proxy permits up to 1,024 connections, caches Docker port discovery and applies shared idle and backpressure timeouts. Capacity should still be measured for intended workloads.
- This is a trusted-team shared container; agent commands can access service environment and state. API authentication does not provide separate worker or tenant isolation.
- Automatic off-host backups are not configured. The documented backup/recovery procedure must be used before important updates; preserve the encryption key.
- Firewall operator/gateway addresses and provider SSH-key IDs are deployment-specific. Refresh them when network or operator access changes.
- Repo authentication, Linear integration/webhooks and native independent-reviewer authentication for the project `task` skill remain project setup, not validated ticket automation.
- The selected smoke-test profile uses OpenRouter `openai/gpt-4.1-mini`; production model choice and project budgets remain operator configuration.

## Follow-up: fresh-browser failures

A user report exposed a gap in the original verification: the browser previously used had cached JavaScript assets. A new profile reproduced a blank page with HTTP 502 errors, while single API readiness checks still passed. The host journal confirmed the socket-activated proxy dropping connections at `MaxConnections=64`.

The old per-connection helpers were replaced by one asyncio TCP proxy with serialized cached port discovery, negative caching, refresh on refusal, byte-stream flow control, half-close support and shared bidirectional idle activity. Regression tests cover 160 exchanges with 80 concurrent clients, a server-push stream with a quiet client, and coalesced port refresh plus cached failures.

The first-run wizard also selected an unconfigured default model profile. The shared default agent was linked to the existing `gradientlabs-default` LLM profile, and its saved LLM configuration was reactivated. `configure-default-agent.py` preserves the other agent fields and refuses to overwrite a default belonging to another agent kind.

A fresh Chrome profile rendered login; after authentication, a bounded real job finished. The browser-based no-store gate fetched 265 JavaScript/CSS assets concurrently with zero failures. The error tracker reported zero page errors and zero HTTP 502 errors. A separate Python stress test with many independent TLS connections encountered request timeouts, so it was replaced by the actual browser's HTTP/2 fetch path; it was not counted as a pass.

The post-fix full VM reboot check also passed: the replacement proxy and application recovered automatically; a fresh browser profile rendered the connection screen, login succeeded, all 265 browser no-store asset requests returned 200, authenticated doctor passed, and a new real job finished with the expected marker. No gateway reconfiguration or model repair was run after this reboot.

Independent review of the follow-up fixes completed with no Critical/High findings. Remaining Medium observations: verify Python >=3.11 for timeout semantics (the VM uses Ubuntu 24.04/Python 3.12), and keep real cold-page rendering/job checks alongside the status-based asset gate, since the asset gate alone cannot reject a hypothetical HTML fallback. The previously observed old-proxy negative control was the actual fresh-browser reproduction and host log, rather than reinstalling the broken proxy after the fix.

## Subscription-agent deployment — 2026-10-08

Two ACP profiles are configured: `Claude-Code-Subscription` (active, a dedicated Claude Max setup-token) and `Codex-Subscription` (a separate server device-auth ChatGPT login). Credentials are consumed privately; no provider API key or gateway override is set in the container environment. Claude's profile exposes only `CLAUDE_CODE_OAUTH_TOKEN`; Codex relies on its native persistent login cache. Both profiles disable MCP integration. Existing API-backed profiles are retained but do not drive these ACP jobs.

Actual Canvas UI jobs completed with terminal output:

- Claude initial native-login check: `0d835cd6-4ef0-4717-b3d1-16c8504d291a`, `CLAUDE_SUBSCRIPTION_OK`.
- Codex cached-login patch check: `41ea9e2b-b5b4-4615-99c2-fa345595ccee`, `CODEX_SUBSCRIPTION_OK`, runtime model `gpt-6-astra`.
- After a full container recreation: Claude `d3bbe8ca-3b67-48ed-8c84-ec39ed70d3d6`, `CLAUDE_PERSISTENCE_OK`; Codex `474a9d11-e2b4-441a-be1e-644b0eae264e`, `CODEX_PERSISTENCE_OK`.
- After replacing diagnostic credential copies with dedicated server authentication: Claude `92ef8d90-f76e-4564-bc91-60d6629c0961`, `CLAUDE_DEDICATED_LOGIN_OK`; Codex `0c850919-ee25-40c0-95a6-3124927db6e9`, `CODEX_DEDICATED_LOGIN_OK`.

Codex initially failed with `ACPAuthRequired: ChatGPT authentication did not complete in time. Please sign in again.` Native Codex subscription inference succeeded. A direct ACP handshake reproduced a forced-refresh stall for ninety seconds despite a valid cached access token. The derived pinned image changes only `authenticateWithChatGpt` to read the cached account without forcing token refresh; the account must still be ChatGPT and provider inference must authenticate normally. The patch is build-time checked against the pinned adapter source.

Service doctor passed all five remote checks. After the replacement completed, the browser HTTP/2 asset gate fetched 262 assets successfully. Expected HTTP/WebSocket 502 responses occurred while the container was being replaced; these were cleared before checking steady-state UI errors. No outage during replacement is represented as zero downtime.

Initial independent review identified shared refresh-credential risk. Dedicated Claude setup-token and separate Codex device login resolved it; the diagnostic Claude cache was deleted. README explicitly documents that same-UID agents can access account-wide authentication and service secrets, so this deployment is restricted to the owner's trusted jobs. It is not a multi-tenant boundary. Stale/revoked-token negative testing, periodic provider-auth monitoring, parallel token refresh and automatic cache retention remain unverified or unimplemented; service health alone does not establish subscription quota or auth health.

Final independent Claude CLI review found no unresolved Critical or High issues. Remaining Medium/Low limitations include account-wide credential exposure within the trusted single-owner runtime, stale/revoked auth detected on model use rather than a periodic monitor, unverified concurrent refresh, cache/history retention, and provider config recreation. Documentation records token lifetime and incident/rollback reauthentication. These limitations do not imply API-key fallback.

Final post-review Claude job `1f1c591e-5a2a-443b-9f95-f06de0e981cf` finished with `CLAUDE_FINAL_OK` after the imported native Claude cache was removed. A bounded scan found no Claude token prefix in persisted conversation files, the preceding thirty minutes of container logs, or Docker container configuration. This scan does not establish credential isolation or cover all possible files.

## Custom hostname preparation — 2026-10-08

Copied the 22 Squarespace records supplied by the user into the DigitalOcean root zone and retained OpenHands and the existing watchtower A record. API readback matched all 23 intended records; 72 authoritative record checks across the three DigitalOcean nameservers passed. The existing watchtower child zone and delegation were preserved. The user reported saving the registrar nameservers, but subsequent direct `.it` registry and Cloudflare/Google resolver checks still showed the Google delegation. Public OpenHands A resolution and custom-host end-to-end verification therefore remain pending; the custom URL is not reported live.

Installed `openhands-domain.timer` on the existing platform gateway. The helper waits for both public resolvers, then issues a separate DNS-01 certificate, activates a private Caddy reverse proxy, and checks renewal every five minutes. Certificate pairs switch through an atomic symlink. Credentials are consumed from the authorized shared Vault into private temporary runtime files, with systemd runtime-directory cleanup. Certificate failure backoff is six hours; existing shared certificates and Caddy services are preserved.

Four focused tests passed: pending delegation does not consume credentials, valid activation avoids provider access, failed issuance removes credentials, and activation under umask 0077 creates traversable certificate directories/readable route files while a failed reload remains retryable. The installer was rerun successfully. The real systemd service exited successfully while waiting for delegation; its timer and Caddy remained active. Vault consumption succeeded in a root systemd unit without displaying the credential. The DigitalOcean Certbot plugin was detected. The Caddy service user could traverse the existing certificate directory and validate the imported configuration; a real reload succeeded. The existing upstream returned HTTP 200.

Independent Claude CLI review found no unresolved Critical or High findings after permission and reload-recovery corrections. Certificate issuance, staging validation, the new-host browser flow, and real issued-certificate permissions remain unverified until delegation takes effect. Remaining limitations include no external renewal alerting, retained certificate history, possible stale challenge TXT after interrupted issuance, and reliance on the existing shared DNS credential grant. These preparation checks do not establish successful custom-host TLS or subscription inference through the new origin.

The `.it` registry subsequently switched to DigitalOcean during this session. Both public resolvers returned the expected OpenHands A, while Cloudflare retained an old recursive root NS answer. The helper was corrected to verify delegation directly at the registry and keep both public A checks; the correction received an independent review with no Critical/High findings. Certificate issuance completed successfully, Caddy activated the custom route, and the installed key was readable by the real Caddy user. The certificate expires 2027-01-06; transient runtime credentials were removed. HTTPS `/canvas` and authenticated `/server_info` returned 200. Remote doctor passed all five checks. A fresh browser logged in and job `2fb68057-fc0a-4285-aaa8-0f5847ade513` finished with `OPENHANDS_DOMAIN_OK`. The browser asset gate fetched 265 assets without failure. An initial pre-login settings-probe warning was observed; a subsequent reload rendered the finished job with zero page errors, app errors, or warnings. The global shared prompt now records DigitalOcean DNS authority and was applied to Codex and Claude.

## Subscription catalog refresh — 2026-10-08

Deployed `gradientlabs/openhands-canvas:1.25.0-subscriptions-2` after candidate checks. Canvas remains 1.25.0 and SDK remains 1.53.0. The derived image rebuilds the committed frontend at `57f28556956b964d66b206c6265571b0dbbfffb7`, updates both generated-client and Python SDK catalogs, and installs Claude ACP 0.88.0 / Anthropic Agent SDK 0.3.295 and Codex ACP 2.1.1 / Codex CLI 0.162.0. Native wrapper commands resolve to the preinstalled packages.

Three catalog tests passed, including preservation of unrelated authentication/providers, launch-version updates, UTF-8 AST offsets and fail-closed registry drift. Candidate native probes confirmed Claude aliases `fable`, `opus`, `sonnet`, `haiku` resolve to `claude-fable-5-1`, `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5`; Default resolves to Sonnet 5.5. Native Codex reported ChatGPT authentication and offered all four configured GPT-6 models, including `gpt-6.1-sol`. These probes read catalogs without inference and remove their ephemeral containers.

The conversation inventory had no running jobs before replacement. A protected mode-0600 state/projects/environment snapshot was made while the old service was stopped; the previous image recipe was retained for rollback. Replacement and gateway refresh completed, and the container became healthy. No provider API-key or gateway override environment was present. Dedicated native subscription credentials were preserved.

A fresh Chrome profile authenticated through `https://openhands.gradientlabs.it/canvas`. Both model menus displayed the updated labels and IDs. Real UI jobs completed:

- Claude Fable 5.1: `19f7a797-71f5-40af-aae9-4bbaa835b0f4`, finished with `CLAUDE_LATEST_OK`.
- GPT-6.1 Sol: `61da3bee-bd35-4a1b-bb8b-41ae562d0b22`, finished with `CODEX_LATEST_OK`.

Authenticated doctor passed all five checks. The browser no-store asset gate fetched 263 assets with zero failures. The earlier persisted conversation `2fb68057-fc0a-4285-aaa8-0f5847ade513` rendered its expected marker and the updated Claude selector. One pre-login settings-probe warning occurred during initial setup; after clearing and reloading, the steady-state browser had zero page errors, app errors and warnings. The original active Claude profile and both original null model overrides were restored after testing.

Independent CLI review of the final catalog/probe code reported no confirmed Critical, High or Medium issues. The remaining Low parsing observation concerns a future multi-service or quoted-image compose file; the current single-service image is unquoted. Catalogs are pinned deployment snapshots, not automatic model discovery. All configured choices were checked against native catalogs; actual inference was tested only for Fable 5.1 and GPT-6.1 Sol. Existing API-backed profiles were retained and were not migrated. No full VM reboot was repeated for this catalog-only update.

## Upstream Canvas upgrade — 2026-10-08

Pulled the official `ghcr.io/openhands/agent-canvas:latest` and verified image labels identify release 1.26.0. Deployment pins the multiarch index `sha256:ce4526401c08b47d74fd0be5ebf97e8219d6a02955cb6710e8cc3335f01291a6`, including ARM64 support. Upstream v1.26.0 merged cleanly into the fork at `83f51c0cfb8bab5af6950ecde98cabe229031cb8`; that committed source was archived and rebuilt with the model-catalog patch. The official image still supplies old static model choices, so retaining the patch is necessary. SDK 1.53.0 and automation 1.19.0 are unchanged.

The candidate was built through a separate `compose.candidate.yaml`, preserving the live 1.25.0 image/tag and compose until cutover. Catalog tests (3), remote-verifier authentication/lifecycle test (1), probe syntax and the real frontend build passed. A direct attempt to run the upstream verifier's Vitest test file locally could not run because this checkout has no installed Vitest dependencies; it is not recorded as a test pass. The deployment verifier's own regression test and live paths provide the applicable checks.

Candidate native probes passed for every configured model and confirmed ChatGPT login. The Codex probe now checks privately that the access token has at least 30 minutes remaining and compares cache hash/mtime afterward. This reduces expiry-refresh risk and detects local cache mutation, but cannot detect a hypothetical in-memory provider rotation on an unexpected 401 retry. It does not copy refresh credentials. Independent review reassessed the originally hypothetical refresh finding against this code and actual freshness evidence; no confirmed Critical, High or Medium findings remain. Other Low observations concern future multi-service image parsing, transitive npm reproducibility and concurrent legitimate cache writes causing a fail-closed probe.

Before cutover, the external gateway was stopped to close admission, then internal authenticated checks confirmed no active conversations and no enabled automations. The service was stopped, a consistent mode-0600 state/projects/environment snapshot was saved, and the candidate replaced the container. Gateway port discovery was refreshed and HTTPS returned. The previous image and protected snapshot remain available for recovery. Provider keys and native subscription logins were not replaced. No automatic restart/update scheduler is enabled.

A fresh browser profile was reset after cutover to exclude cached 1.25.0 assets. Login and home composer rendered; both selectors displayed the preserved current-model catalog. Authenticated doctor passed all five checks, and the no-store browser gate fetched 266 assets with zero failures. Two bounded real UI jobs finished with their requested markers: Claude Fable 5.1 `ccb15385-6ffa-40a4-8dd8-ca897619ce66` (`CLAUDE_126_OK`), and GPT-6.1 Sol `9c1f0132-4997-4a89-babb-1c76c3e0b481` (`CODEX_126_OK`). Both original null model overrides and the original active Claude profile were restored after verification.

A full VM reboot was then tested only after closing external admission and rechecking internally that no jobs or enabled automations were active. Docker initialization exceeded the first readiness deadline; a subsequent check recovered without rerunning the gateway installer. Container health, bridge, HTTPS and all five authenticated doctor checks passed. A fresh browser profile logged in again, fetched 268 no-store assets without failure, and continued both saved smoke conversations. Their agent `FinishAction` and observations contained `CLAUDE_126_REBOOT_OK` and `CODEX_126_REBOOT_OK`, with both conversations finished. Transient HTTP/WebSocket 502 errors occurred during the intentional maintenance interval; after clearing and reloading the completed job, steady-state page errors, app errors and warnings were all zero. This verifies persisted conversations and resumed native subscriptions; it does not claim uninterrupted execution of a job through container/VM replacement.

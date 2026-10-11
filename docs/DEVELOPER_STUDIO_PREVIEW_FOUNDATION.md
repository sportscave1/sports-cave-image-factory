> Historical pre-installation assessment. Superseded by [the current Phase 2/3 guide](DEVELOPER_STUDIO_PHASE2_PHASE3.md); retained for the safety decision record.

# Phase 2 safety foundation and approval boundary

Status: draft-management foundation implemented locally; full-application preview
BLOCKED and NOT verified. No application, limited UI preview, editor, background
service or production process has been started by this work.

## Existing task

Task 20261011-c24ca137; owner me/phase2. Continue its existing CORE worktree and
branch. Phase 1 stays intact; the original repository and Phase 1 setup/category
worktrees are not edited. The earlier DEVELOPER_STUDIO_PHASE2_BLOCKERS.md is
preserved as the historical preflight report.

## Local assessment â€” 11 October 2026

CIM reports Microsoft Windows 11 Home, 64-bit, build 26200, Ryzen 7 5800X,
approximately 16 GB RAM, HypervisorPresent=true and firmware virtualization=true.
SLAT reports false while the hypervisor is present; compatibility must be confirmed
by the runtime installer, not inferred from that single counter.

Docker/Podman commands and common Docker Desktop installation paths are absent.
WSL reports it is not installed. Windows Sandbox command is absent; Microsoft
lists Sandbox for supported Pro/Enterprise/Education editions, not Home.

No verified ready isolation runtime was found. A new Windows AppContainer broker
would need token, ACL, native-client and child-process validation; there is no
tested application-compatible implementation here. A separate user, ordinary
process, Python mock, localhost listener or stripped environment alone is not the
required boundary. Changing shared Python firewall rules could disrupt other
tasks and is not proposed. WSL by itself also exposes networking and host files;
it must not be treated as isolated application preview execution.

## Minimum recommended one-time setup â€” owner approval required

Do NOT run these installation steps without owner approval.

1. Save work. Open an Administrator PowerShell and run:
   wsl --install --no-distribution
   Restart Windows if requested. This enables/installs WSL without an unnecessary
   general-purpose Ubuntu distribution.
2. Install Docker Desktop for Windows x86_64 from its official installer, using
   Linux containers and the WSL 2 backend. The current installer supports per-user
   installation. Do not enable Kubernetes, Windows containers, extensions,
   host networking or a remotely exposed Docker API. No Windows Pro upgrade is
   proposed. The user must accept applicable installer/license terms.
3. Open Docker Desktop on demand and confirm:
   wsl --version
   docker version
   docker info --format '{{.OSType}}'
   The last command must report linux, and the server must be reachable.
   WSL must satisfy Docker's current minimum (2.1.5 at inspection).
4. Stop here and resume this task. Installation is a prerequisite, not proof that
   Sports Cave OS is safe to start. A reviewed dependency image and the negative
   probes below must be built/run BEFORE the full application is executed.

No installation, reboot, BIOS change, Windows feature change, Docker configuration
change, image download or service start has been performed in this task.
This is the smallest supported setup recommended here, not a claim that Docker
is the only theoretically possible isolation technology.

Official sources consulted narrowly:
- https://learn.microsoft.com/en-us/windows/wsl/basic-commands
- https://docs.docker.com/desktop/setup/install/windows-install/
- https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/
- https://docs.docker.com/engine/network/drivers/none/

## Proposed enforceable runtime (design only; not installed or tested)

Use one disposable Linux runtime per active preview. Execute the actual selected
application snapshot ONLY inside this runtime.

- Docker network mode none: no external network interface, only its own loopback.
  This applies below Python to libpq/native connections and child processes.
  Do not use bridge, host networking or rely on an internal bridge alone.
- Drop all capabilities; no-new-privileges; non-root UID; default seccomp; read-only
  root filesystem; bounded CPU/memory/process count; explicit per-draft writable
  runtime/cache/temp and synthetic-data storage. Never mount the Docker socket.
- No host user profile, original checkout, .git, .env, Streamlit secrets, cloud
  credentials, SSH agent, production dumps, Docker config or generic host paths
  inside the container. Use a reviewed allowlisted source export, never COPY .
  or an unrestricted worktree mount. Review assets/fixtures for customer data.
- Build dependency images separately without application credentials. Do not
  install dependencies or run build hooks on the host as part of preview launch.
  Pin the reviewed runtime image digest. Package/image downloads need approval.
- Put synthetic PostgreSQL and mock providers inside the same isolated runtime
  (Unix socket or container-local loopback). Never connect to host PostgreSQL.
  Initialize only disposable test schema/data. Unknown providers fail closed.
- Use a dedicated preview entry point, not the production launcher. Disable
  real worker/cron/IDLE/queue-consumer bootstrap and live migrations. Start only
  the explicitly allowlisted application, synthetic DB and relay processes.
  An application's child processes cannot be assumed absent: deny their external
  effects through the OS boundary and test the explicit worker startup guards.
- Keep all preview sessions below a resource budget and start them on demand.
  Idle timeout stops the named preview container and its child processes, never
  unrelated host processes. Each preview retains its own storage and ownership.

### Local browser access without giving the container egress

Network mode none cannot use ordinary published-container ports. Plan an
authenticated, loopback-only host gateway with a unique port per draft. It relays
HTTP/WebSocket streams through a fixed, audited docker-exec stdio relay to the
container-local application socket. It must not accept arbitrary commands,
container IDs, host paths or destination addresses from browser input.
The container gets no gateway network connection and no Docker API capability.

The gateway must enforce owner-scoped session tokens, Host/Origin validation,
CSRF protection and bounded requests. Never expose tokens in logs or send them
to application JavaScript.

Server isolation does not contain browser JavaScript. Before acceptance, every
application/component response must have restrictive CSP; all browser network
destinations must be limited to the exact assigned preview origin. Embed the app
in a sandboxed preview frame with external navigation/popups/forms/downloads
restricted; reject external redirects. Prove that Streamlit HTTP/WebSocket and
iframe components still work under those restrictions. Do not silently relax
policy to make a broken preview appear functional.

This gateway is a proposed design, not a working component. If it cannot safely
support the actual app, keep startup disabled and report the concrete failure.

## Required critical tests after setup

Run first against a small inert probe image, before application import/startup:

| Surface | Required negative result |
|---|---|
| Native PostgreSQL/libpq | Synthetic local DB succeeds; controlled off-runtime DB canary fails without contacting production |
| HTTP, DNS, raw TCP/UDP, IPv6 | Off-runtime canary traffic denied; no external interface/default route |
| Credential discovery | Controlled host canary files absent; no host profile, mounts, .env or credential sockets |
| Subprocesses/native tools | Same network/filesystem denials inherited; no privilege/capability escape |
| Background jobs | Real worker/cron/IDLE paths refused; any child remains confined and stops with its container |
| Browser JS, forms, images, iframe and WebSocket | External canaries blocked; only own preview origin works |
| Ownership/ports/storage | Two previews cannot share a worktree, owner session, port, volume or database |
| Recovery/lifecycle | Crash/restart/idle-stop preserve the right draft and cannot terminate unrelated tasks |

Use controlled synthetic canaries, never live production credentials/endpoints.
Persist results against the image digest, policy hash and draft source snapshot.
A changed image, policy or execution model requires re-verification.
Only after these gates pass, implement/verify full app behavior and the compact
Phase 2 Drafts/Previews interface. Phase 3 remains blocked until Phase 2 passes.

## Implemented now: safe named drafts

This task extends the existing scripts/studio/Studio.ps1 and studio.py. The
shared top-level Phase 1 launcher remains unchanged so other tasks do not consume
uncommitted tooling. Use the task-local launcher until changes are reviewed.

From this CORE worktree:

~~~powershell
$studio = '.\scripts\studio\Studio.ps1'
& $studio NewDraft -Id '20261011-c24ca137' -Owner 'me/phase2' -Name 'Phase 2 safety foundation'
& $studio ListDrafts -Owner 'me/phase2'
# Use the returned draft UUID for these commands:
& $studio SaveDraft -Id '<draft-uuid>' -Owner 'me/phase2' -ExpectedRevision 0 -Files 'scripts/studio/drafts.py','docs/DEVELOPER_STUDIO_PREVIEW_FOUNDATION.md'
& $studio OpenDraft -Id '<draft-uuid>' -Owner 'me/phase2' -Open
& $studio RecoverDraft -Id '<draft-uuid>' -Owner 'me/phase2' -Revision 1
~~~

NewDraft stores UUID/name, actual task/branch/path/owner/base/current commit,
revision history and a disabled full-application preview record in the existing
registry. One draft per task prevents multiple independent drafts sharing a
working folder. New independent drafts require separate tasks/worktrees.

SaveDraft checkpoints explicitly selected UTF-8 source files, not a whole
application or a security-reviewed runnable export. Approved extensions are
.py/.html/.css/.js/.mjs/.cjs/.jsx/.ts/.tsx/.md/.ps1. Selection is cumulative; deleted
selected files receive tombstones. A revision records the exact content hashes
and actual HEAD, including uncommitted selected changes. The expected revision is
mandatory, so stale saves fail. Concurrent source changes detected during capture
also fail. No source file, Git index, branch or commit is changed by saving.

Hidden, sensitive, runtime, traversal, alternate-stream, reparse and hardlinked
paths are refused. Size limits are 2 MiB per file / 20 MiB per draft / 100 files.
The existing secret-pattern check is only a supplemental heuristic; saved source
is NOT automatically safe for execution or export.

OpenDraft validates ownership/worktree/branch and stored hashes, reports changed
selected files and optionally opens the task's existing VS Code workspace.
RecoverDraft writes an old checkpoint to a new folder and manifest under
.studio/drafts/recovery; it never overwrites the active draft. Manual comparison
is possible now; source restoration/editor actions belong to later work.

The existing registry lock and atomic replacement protect metadata. Blobs are
content-addressed under .studio/drafts/blobs. A crash can leave an unreferenced
blob, never a silently accepted partial registered revision. Runtime data is not
committed. Ownership remains the Phase 1 cooperative local model, not protection
against another Windows process running as the same user and rewriting metadata.

## Verification scope and performance

Focused offline tests cover save/reopen/recovery, owner denial, duplicate tasks,
stale revisions, concurrent edits, original-checkout rejection, path restrictions,
hardlinks/reparse paths, sensitive/binary/oversized input, deleted files, corrupt
blobs, failed metadata writes and the unchanged preview-denial gate.
Phase 1 tests remain passing. These are draft-tool tests, not preview isolation
acceptance. No full-application safety gate is marked passed.

No added package dependency, service, polling or idle process. Work happens only
when a draft command runs. Costs scale with selected source bytes, with the caps
above; no full repository copy or full application benchmark is performed.

## Draft management screen (safe continuation)

The task-local launcher now supports:
~~~powershell
.\scripts\studio\Studio.ps1 DraftUI -Id 20261011-c24ca137 -Owner 'me/phase2' -Open
~~~
Run it from this assigned task worktree. It validates the registered task's Git
root, branch and owner before binding an OS-selected available 127.0.0.1 port.
The terminal prints a private per-process URL. The token is carried in its
fragment, removed from browser history on load, kept in page memory and sent
only in an authentication header. Reload using the original launcher URL;
tokens are not stored in browser storage or the registry.

The screen offers naming (if no draft exists), explicit-file checkpoints,
Open Draft / Refresh, changed-file indicators, revision selection, recovery to a
new folder, workspace identity and Stop Draft Studio. Application Start/Stop/
Restart Preview controls remain disabled, and the API refuses them. This is a
draft-management interface, not even a limited application UI preview. It never
renders checkpoint HTML or imports application modules.

The small stdlib HTTP service has no installation, background launcher, polling,
external assets or package dependencies. It starts on demand, handles requests
serially, expires after 15 minutes without authenticated activity, and can stop
via its authenticated button or Ctrl+C. Different sessions bind different
available ports and use independent random tokens. These are management-service
ports, NOT evidence of independent full-application previews.

Filesystem operations reuse the existing registry lock, task ownership validation,
source-path restrictions, bounded checkpoints and optimistic revision checks.
Browser requests cannot supply a different task, owner, root or executable.
Only three fixed UI assets and authenticated state/action endpoints are served.
Host and Origin checks, a restrictive CSP, no CORS, no-store responses, bounded
JSON bodies and text-only DOM rendering constrain browser access. No source write,
restore-over-source, arbitrary command, app-start or generic file-serving endpoint
exists. Authentication is a local bearer capability; this is not an OS boundary
against hostile processes running as the same Windows user. Do not share its URL.

The desktop two-column screen becomes one column below 720 px. This responsive
draft manager does not constitute desktop/mobile application preview verification.

## Continuation acceptance and remaining gates

The draft UI tests exercise two listener ports/tokens, authentication, Host/Origin
denial, owner changes, cross-task override refusal, save/reopen, stale revision
denial, recovery, path denial, blocked runtime actions, malformed/oversized input,
idle termination and authenticated shutdown. Tests use disposable synthetic
text fixtures; no application database or integration is accessed.

Phase 2 remains BLOCKED. Full-application synthetic databases, adapters,
start/stop/restart, two application previews, application recovery, native client /
network / credential / subprocess / worker isolation and browser egress probes
are NOT implemented or verified. Phase 3 is not started. No editor, publishing or
Phase 4 Release Manager is implemented. The checkpoint model and authenticated
task-scoped API are integration foundations only.

Next owner action: approve or perform the one-time WSL2 and Docker Desktop Linux
runtime setup above. No installation or Windows changes are performed by this
task. After setup, implement and pass the boundary probes before starting any
real application code. Installation alone does not satisfy Phase 2 acceptance.

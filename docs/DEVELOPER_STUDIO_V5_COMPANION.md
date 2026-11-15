# Developer Studio V5 Windows companion

Local implementation in CORE task 20261012-54a08610, owner me/studio-companion-v5,
based on fecab25fb01fb3cb4e4e783c00093be517676ac5. Not deployed or committed.

## Use

Run scripts/studio/Companion.ps1 Start -Id <task-id> -Owner <registered-owner>,
then the same command with Open. Supply -Python <existing-python.exe> if needed.
Start launches a hidden supervisor and worker; no terminal must remain open.
Open displays an authenticated localhost approval page without printing a private
URL or using the clipboard. Check the exact OS origin, select Trust This Computer,
and approve locally. In the OS, enter the printed stable localhost origin once
and click Connect. The initial local setup does not authorize any production action.

The address is remembered where browser storage permits. Reopening the OS may
require one Connect click to open a fresh local approval window. Saved trust then
resumes without PowerShell, copied private URLs or another approval. Keep that
local approval window open during use. Silent background cross-origin embedding
is intentionally unsupported: frame-ancestors remains none and CORS stays closed.
Browsers blocking loopback access/popups require their normal permission flow;
never bypass security warnings. Mobile browsers cannot reach a Windows companion
through their own localhost. Metadata is not fabricated while disconnected.

Disconnect clears hosted metadata and stops renewal but retains device trust.
Revoke This Computer in the local approval window invalidates trusted sessions
and saved trust. Stop Companion confirms locally, stops its previews and exits
normally; the supervisor does not resurrect an intentional stop. An explicit Start restarts it; the intentional-stop marker also blocks scheduled recovery. Local source files are preserved.

## Optional Windows sign-in startup

Only after owner approval, run Companion.ps1 EnableStartup with the same ID,
owner, Python and -ApproveStartup. It creates SportsCave-Studio-<task-id>, scoped
to the current interactive Windows user at Limited privilege. It uses pythonw.exe,
IgnoreNew, no execution time limit, three one-minute restart attempts, and a one-minute fallback trigger (IgnoreNew prevents launches while running).
Existing scheduled tasks are never overwritten. DisableStartup -ApproveStartup
removes only this exact task. No credentials are stored in Task Scheduler.
The owner approved and enabled startup. Task Scheduler launch, Limited privilege,
Interactive logon and IgnoreNew were verified. A real sign-out/sign-in is still
unverified. Forced termination did not reliably trigger Windows RestartOnFailure,
so the same task also has a fallback trigger. It adopts only an existing worker
that proves the DPAPI-protected bootstrap, and never replaces another listener.

## Security and lifecycle

- Native user-scoped DPAPI protects local bootstrap and device records. Other
  Windows users cannot decrypt them. Same-user malware/admin compromise is outside
  this boundary; do not treat localhost as protection against a compromised PC.
- Device refresh credentials remain HttpOnly, SameSite=Strict localhost cookies;
  no token is sent by postMessage to the OS or Render. The server stores only a
  DPAPI-protected hash and exact approved origin, task, owner and expiration.
- Refresh rotates the credential every renewal; replay of the old credential
  fails. Access sessions last five minutes, renew after four, and trust has an
  absolute 30-day limit. Revocation invalidates all trusted sessions for that task.
  Lost renewal responses or simultaneous refresh races can require fresh local
  approval: the implementation fails closed rather than accepting replay.
- Device endpoints require exact localhost Host and Origin, a custom header,
  bounded JSON and existing task ownership. Enrollment needs the locally opened
  bootstrap; a renewed session cannot replace enrollment. No arbitrary commands,
  provider credentials, remote shell, broad CORS or public listener is added.
- Bootstrap remains a process-scoped local launcher capability, protected by
  DPAPI at rest and replaced after process restart. Legacy launcher authentication
  is retained for compatibility; do not share its URL.
- A fixed port is allocated per task. Exclusive Windows socket binding and a
  lifetime byte-range lock prevent duplicate listeners and supervisors. No occupied
  port is taken over. Preview traffic is independently idle-limited to 15 minutes.
- Only a dead supervised worker's exact PID/lease/container may be recovered.
  Docker context and task labels are rechecked. Unknown/stale leases fail closed;
  no other session's container is removed. Existing Docker isolation is unchanged.
- Browser health checks run once per minute only while connected, without Git
  scans. Renewal may refresh metadata. There is no disconnected polling loop.
- All nine categories are discoverable. Actions retain exact task ownership;
  another owner's task stays read-only. Same-owner task handoffs use separate
  local workspaces. This does not grant the owner identity of another Codex task.
- Authentication recovery in the local editor does not reload its source fields.
  For a separate child workspace whose process/port is lost, retain the old editor
  and copy unsaved edits before reopening; durable unsaved-buffer recovery across
  killed child processes is not implemented. Saved revisions remain recoverable.
- Original repository, UI/UX task, production settings and Publish remain untouched.

## Acceptance

Run the existing focused Python suites test_companion, test_phase4a,
test_preview_safety and test_editor; run Node test_pairing.cjs and
 test_trusted_pairing.cjs. Tests use disposable synthetic registries.
verify_companion_runtime.py is an explicit local acceptance tool: it checks task
identity, samples idle CPU/memory, attempts a duplicate launch, terminates ONLY
that authenticated task worker, checks automatic restart, then stops it. Never
run it against an active editor/preview session containing user work.
verify_companion_browser.py serves only a disposable limited-UI fixture, not the
application. Its fixed synthetic token is never used by a real registered task.

Observed local browser acceptance: explicit synthetic trust; initial connection;
address remembered after reload; one-click authenticated reopen; revocation cleared
hosted metadata. A popup fragment-reuse bug found in this check was fixed by opening
fresh approval documents, preserving per-connection nonce/source verification.
Measured supervisor + worker + Windows launcher RSS: 66,646,016 bytes (63.6 MiB);
0.0 CPU seconds measured over a 20-second idle sample, not a long-duration benchmark.
Panel JS/HTML grew by 1,374 bytes before the final offline-status adjustment;
components remain lazy-loaded and no application startup imports changed.
V5 hosted HTTPS Chrome/Edge acceptance and real Windows logon remain unverified.
Prior Phase 4D browser evidence does not automatically certify V5.

Microsoft references: https://learn.microsoft.com/en-us/windows/win32/SecCrypto/example-c-program-using-cryptprotectdata
and https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/new-scheduledtasksettingsset


## Final local result (12 October 2026)

- 62 focused Python test executions passed: companion 21, Phase 4A 19,
  preview safety 11, editor recovery 11. Both Node pairing suites passed.
- Actual Windows DPAPI, fixed-port collision, owner-change denial, expiry,
  rotation/replay rejection and revocation passed.
- Real hidden-process duplicate/restart/intentional-stop tests passed.
- Scheduled watcher termination recovered automatically on the fallback trigger;
  the exact surviving worker was adopted with no duplicate listener.
- Synthetic browser trust, one-click reopen, address persistence, revocation and
  offline clearing passed in the in-app browser. No source edits were needed.
- The approved current-user startup task is enabled and Running; stable address
  http://127.0.0.1:18761. Initial trust of the actual production OS origin remains
  an explicit local user action. No production-origin trust was created by tests.
- Registry status is Tested for local evidence only; integration readiness is
  false while changes are uncommitted. No commit, push, merge or deployment.
- Pending: actual Windows sign-in, V5 hosted HTTPS Chrome/Edge acceptance, and
  final release approval. A fresh local approval window may require one Connect
  click when reopening the OS. Long-duration wall-clock idle/sleep/resume is not
  certified by the accelerated expiry tests and short resource sample.
- Keep this worktree and interpreter while startup is enabled. DisableStartup
  before archiving the worktree; never point the task at an unrelated checkout.

Files changed:

- components/developer_studio/panel.html
- components/developer_studio/panel.js
- scripts/studio/draft_ui.py
- scripts/studio/preview_runtime.py
- scripts/studio/ui/drafts.js
- scripts/studio/ui/pair.html
- scripts/studio/ui/pair.js
- scripts/studio/Companion.ps1
- scripts/studio/companion.py
- scripts/studio/device_trust.py
- scripts/studio/test_companion.py
- scripts/studio/test_pairing.cjs
- scripts/studio/test_trusted_pairing.cjs
- scripts/studio/verify_companion_browser.py
- scripts/studio/verify_companion_runtime.py
- docs/DEVELOPER_STUDIO_V5_COMPANION.md

## Acceptance follow-up and exact browser checklist

12 October 2026: fixed a real multi-browser enrollment defect: trusting Edge no
longer replaces Chrome's trust. DPAPI stores independent browser/origin records;
renewal rotates only that record. Revoke This Computer invalidates all records for
this task. Previous single-record credentials remain compatible. Added explicit
Chrome/Edge opening through their installed Windows App Paths; private URLs are
never printed. All 65 focused Python tests and both Node suites passed after these
changes (24 companion, 19 Phase 4A, 11 preview safety, 11 editor).

### One-time trust in each browser

Run this in PowerShell, choosing Chrome first, then Edge:

```powershell
$studio = 'C:\Dev\SportsCaveWorktrees\sports-cave-core-developer-studio-v5-always-connected-windo-20261012-54a08610'
$settings = @{
  Id = '20261012-54a08610'
  Owner = 'me/studio-companion-v5'
  Python = 'C:\Users\hello\Documents\sports-cave-image-factory\.venv\Scripts\python.exe'
}
& "$studio\scripts\studio\Companion.ps1" Open @settings -Browser Chrome
# For Edge, repeat the last command with -Browser Edge.
```

Use normal browser profiles, not Incognito/InPrivate. In the localhost approval
page, set OS origin to `http://127.0.0.1:18861`, select **Trust This Computer**, and
approve locally. Open `http://127.0.0.1:18861/` in that same browser. This is the
actual candidate panel in a clearly labelled limited-UI acceptance page, NOT a
full application preview or hosted HTTPS acceptance. Connect using address
`http://127.0.0.1:18761`. Keep its local approval popup open during use. Use normal
browser popup/local-network permission prompts; never bypass security warnings.

The temporary acceptance page stops after four hours. If unavailable, restart it
quietly from PowerShell (only when port 18861 is not already serving the page):

```powershell
Start-Process -WindowStyle Hidden -FilePath ($settings.Python -replace 'python.exe$', 'pythonw.exe') -ArgumentList @('-B', ('"' + $studio + '\scripts\studio\verify_companion_browser.py"'), '--panel-only')
```

1. Confirm task `20261012-54a08610`, owner `me/studio-companion-v5`, and draft
   **V5 Companion Acceptance**. Check Editor/Tests and disabled Publish. Do not
   alter another task. This new draft has no fabricated saved/test revisions.
2. Trust both browsers. Chrome must remain connected after trusting Edge. Leave
   both connected for 20 minutes without a Docker preview, then refresh draft
   discovery. Record any authentication error; this checks multiple renewals.
3. Close the panel and its approval popup. Reopen the panel and click Connect if
   needed. Saved trust should resume without PowerShell or private URL copying.
4. Disconnect Chrome: its task data should clear; Edge should still work. Reconnect.
5. In the local approval popup choose Revoke This Computer. Both browsers must lose
   authenticated access (display updates within the one-minute heartbeat). Fresh
   trust is required afterward. Never share cookies, private URLs or tokens.

### Hosted browser-policy smoke check and Windows sign-in

Open the launcher again in each browser. Trust the exact production origin
`https://sports-cave-image-factory.onrender.com`. Open the live OS using the owner
account, enter Developer Studio and connect to `http://127.0.0.1:18761`. Check real
draft discovery and Disconnect clearing. This tests the new companion under HTTPS
browser policy, but the live panel is still the OLD version: its old timeout does
not certify or disprove the candidate V5 panel's renewal behavior. Full hosted V5
acceptance requires the candidate panel in an approved HTTPS test environment;
no staging or production deployment is authorized by this checklist.

After saving all work, at a convenient time sign out of Windows and sign back in.
No terminal should be needed: open the OS and reconnect to the same local address.
A fresh Connect click may still be necessary for browser popup restrictions. Do
not sign out during unsaved work. Report Chrome/Edge versions, 20-minute renewal,
reopen, cross-browser trust/revocation, HTTPS smoke and Windows sign-in separately.
Unperformed checks remain unverified. Long sleep/resume is also unverified.

### Release approval boundary

V5 remains uncommitted on base fecab25fb01fb3cb4e4e783c00093be517676ac5.
GitHub main was observed at 2ee89e6ea4e4012558dea7051adaf51c9b7b4a68
(Deploy direct GA4 and GSC reporting). Its changed files do not overlap V5. That
is a textual compatibility check, not proof of combined runtime compatibility.
Preserve those reporting changes when preparing the authorized integration commit.
No new release commit exists yet; approval identifies a source fingerprint in the
local acceptance receipt. Registry stays Tested with integration readiness false.
Production approval remains gated by browser/sign-in results, candidate HTTPS
acceptance, a combined immutable revision and its focused integration checks.
Real Publish stays disabled. No commit, push, merge or deployment performed.


## Initial approval repair (12 October 2026)

The Connect popup has an untrusted correlation nonce, not the locally protected
launcher bootstrap. Its old handler parsed an empty private URL as a URL, producing
"Failed to construct URL: Invalid URL" before authentication. Empty input now
retries existing saved trust; when absent, it explains the required one-time
Companion.ps1 Open approval. It never enrolls without launcher authentication.
The authenticated launcher hides the legacy private URL field. Initial origin
input is validated as an exact origin before any request; a popup displays the
actual verified message origin and prevents editing it. After approving in the
launcher, the original popup's Check saved trust / Connect resumes the connection.
No token copying is necessary and no unauthenticated enrollment was introduced.

Close old approval popups and open fresh ones to load this repair. Use the exact
Chrome/Edge launcher commands above, trust http://127.0.0.1:18861 in each browser,
then return to the panel and Connect (or Check saved trust / Connect). Check both
browsers together, reopen, 20-minute renewal and global revocation as above.
Automated tests cover first enrollment without a private URL, failed initial
renewal followed by local enrollment and retry, malformed origin rejection,
independent browser records, 30-day expiry, renewal/replay and revocation.
Actual Chrome/Edge UI acceptance and 30-day wall-clock use remain unverified.
The companion serves these assets from disk; no running companion restart or
Windows startup change is needed. No production changes, commits or deployment.

## Release preparation update

The owner confirmed initial trusted-computer approval, a running companion, the
V5 Companion Acceptance workspace opening, and no private URL requirement.
Independent actual Chrome/Edge trust, 20-minute renewal/reopening, actual browser
revocation and Windows sign-in remain pending, not inferred from that report.
Automated protocol and separate-cookie tests are not actual browser acceptance.

Read-only Render evidence now identifies both the canonical OS and active worker
at 15bef54f709066e43138cf3b91706af6a6191ec9, also observed GitHub main. A local
candidate will preserve this base plus only the 16 V5 files, using a temporary Git
index and a separate candidate ref. Existing task/original/UI-UX worktree indexes,
branches and source are preserved. This candidate is for review, not authorization
to deploy. The registry's task source remains uncommitted and Tested locally;
its integration-readiness gate must not be bypassed.

Before production: record actual Chrome/Edge checks and representative HTTPS V5
acceptance, owner approval of the exact candidate commit, and unchanged GitHub
main (otherwise prepare/retest a new candidate). Pushing main automatically deploys
the existing services: no push is permitted before approval. Render's existing
pre-deploy command runs run_migrations.py --only 20260901_os_repair_requests.sql;
V5 adds no migrations, but that existing production step must be explicitly covered
by deployment approval. Preserve current service identities and configurations.
Do not activate real Developer Studio Publish; it remains disabled independently
of the manual owner-approved GitHub/Render release process.

Owner acceptance received during final preparation: the owner reports all checks
in the requested local Chrome/Edge checklist passed, including independent trust,
20-minute renewal, reopen/reconnect without PowerShell, and revocation. This is
owner-reported evidence, not agent-operated browser evidence. Browser versions
were not supplied. Representative hosted HTTPS V5 testing and actual Windows
sign-out/sign-in were not part of that checklist and remain unverified.

## Windows sign-in recovery repair (local only)

The failed owner sign-in test supersedes earlier local browser acceptance for
Windows restart recovery. Inspection found intact, unexpired DPAPI records, but
newest 18762 enrollments targeted the companion origin itself. These do not grant
access to the OS origin. Existing production-origin records were preserved; no
record was silently converted into a broader permission.

Local repair: reject companion-self enrollment on both client and server; explain
missing origin-specific browser cookies; restored local approval pages attempt
cookie-authenticated renewal for their remembered exact OS origin; launcher pages
also attempt renewal before asking for another approval. Web Locks serialize
cookie rotation across local approval/editor tabs. No tokens are stored in browser
localStorage and no authentication/origin checks are bypassed. Startup watch actions
were checked: neither contains Open or launches a browser. No automatic popup loop
was added, and no browser windows were opened during this repair.

Verification: 44 focused companion/Phase4A executions plus one new HTTP cookie-file
restart test passed; both Node pairing suites and JavaScript syntax passed. Two
persistent test cookie stores survive loss of in-memory server sessions independently
and revocation invalidates both. Actual idle 18762 worker restart passed; trust file
remained byte-identical and repaired assets are served. Actual Windows sign-in and
Chrome/Edge recovery require retesting and are not marked passed. If a browser has
only a companion-origin cookie or has deleted its OS-origin cookie, fresh approval
of https://sports-cave-image-factory.onrender.com is required; the server cannot
reconstruct a missing browser credential from its protected hash.

Retest: close old localhost approval tabs, open Sports Cave OS and click Connect
once using http://127.0.0.1:18762. Do not approve the companion address as the OS
origin. Valid saved OS trust should resume automatically. After this succeeds,
save work, sign out/in, wait up to one minute and repeat without PowerShell. One
Connect click can still be required by popup policy. No production code was changed,
committed or deployed for this repair; previous immutable release stays unchanged.


## Fresh authenticated Edge setup repair (2026-10-12, local only)

The installed production OS uses Edge Default. A restored public /pair page has
neither the process bootstrap fragment nor a usable production-origin cookie;
renewal cannot create that missing credential. Earlier bootstrap auto-renewal
could also overwrite the initial approval UI with the saved-trust failure.
The server cannot reconstruct a browser secret from its protected trust hash.

Companion.ps1 Open now authenticates locally with the existing DPAPI-protected
process bootstrap and obtains a random, single-use, five-minute setup session
bound to the exact OS origin. The launcher selects Edge Default explicitly.
The unique setup page locks the production origin, makes approval available
without cookie recovery, removes its ticket from browser history, and creates
trust only after the owner's click. The resulting HttpOnly cookie must renew
successfully before the page reports successful trust. No setup URL is printed.
Expiry, reuse, wrong origin, wrong owner, untrusted callers and operations other
than enrollment fail closed. Existing trust records and startup settings remain.
A same-localhost BroadcastChannel sends only an origin/ready hint to waiting
pairing pages; those pages must authenticate using their own browser cookie.
It carries no token or draft data and does not bypass the hosted popup handshake.
An already-open older popup may still require its Connect/Check saved trust action.

Focused verification: 48 companion/Phase4A Python tests passed (28.244 seconds),
both Node pairing suites passed, and the PowerShell launcher parsed. Tests include
initial approval with no saved cookie, cookie rejection, independent profiles,
rotation/restart, expiry, origin/owner restrictions and one-use setup replay.
The idle 18762 worker recovered under its existing supervisor; all three protected
trust records remained byte-identical. No active preview was interrupted.
One fresh Edge Default approval window was opened through Companion.ps1 for
https://sports-cave-image-factory.onrender.com. Actual approval, production draft
receipt and Windows sign-in acceptance remain pending owner confirmation.
No production deployment, source commit, Git push or other worktree edit occurred.


Owner acceptance after the fresh-session repair: the owner answered SUCCESS to
confirmation of clicking the production-origin trust button, seeing Computer
trusted, and the actual Sports Cave OS showing Local device connected with
Development Drafts. Recorded as owner-reported actual production Edge Default
acceptance, not agent-operated browser evidence. The authenticated localhost
catalog independently returned five registered drafts across all nine categories
(one actionable for this companion's owner); no previews or source edits were
started by that check. Prior ownership restrictions remain in force.

This resolves the reported initial approval and real OS connection failure.
Windows sign-out/restart recovery with this specific repair has not been repeated
and is not claimed verified. Existing silent startup was preserved; only an explicit
Open launched a browser. No new sign-in browser popup action was introduced.


## Editor and preview activation (12 October 2026, local only)

The hosted catalog already restricted actions by the task/draft owner. It was not
an editing capability: the secure handoff stopped at another private link. Local
confirmation now opens the exact validated draft workspace directly, with a local
link fallback if popup policy blocks it. No token, private URL, source or filesystem
operation is sent to Render. Different-owner drafts stay locked with an explanation.

The existing local workspace now has Draft & History, Editor, Preview and Tests
tabs that remain bound to its assigned draft. The editor discovers only its five
explicit mappings: app.py visual controls, components/sports_cave_top_bar/index.html,
mockups_page.css, orders_page.css and components/session_recovery.js. Missing files
or changed visual mappings are disabled without blocking other authorised files.
Arbitrary Python editing, directory traversal and sensitive files remain denied.
Save updates real draft source and checkpoint history; running preview refresh,
Undo, Restore Revision, unsaved-change warnings and stale-edit checks are reused.
Tests display recorded evidence only; an editor save never certifies a release.

Companion.ps1 Workspace -Intent Edit opens the configured task's registered draft
using its existing local authentication, without a pairing session or trust change.
It was used to open the UI/UX draft editor in Edge Default on port 18762. Its source
was not edited. The verified idle companion was restarted once to load the new
allowlisted file-list endpoint; the existing supervisor recovered and all device
trust identities/generations survived. No pairing approval was repeated.

Hosted panel changes prepared locally: remember the selected draft across Editor,
Preview and Tests; enable matching handoff buttons only for its owner; explain locks;
retain selection after catalog refresh and clear local data on disconnect. These
hosted HTML/JS changes are NOT deployed. The live page can still show its previous
read-only catalog wording. Inline hosted editing is not claimed: source operations
remain in the local workspace reached by the existing secure handoff. A separately
approved release is required to update the hosted tabs and wording.

Focused checks: 32 editor/Phase4A tests and one launcher test passed; pairing,
trusted-pairing and hosted-selection Node suites passed. JavaScript/PowerShell
syntax and git diff --check passed. The real V5 draft (not the unfinished UI/UX
draft) was visually edited and its rendered heading verified, source-edited and
compared inside the container, saved/reopened, subjected to stale-edit and path
rejection, undone/restored, and rendered at desktop 1280 and mobile 390 widths.
Both touched application files were restored byte-for-byte through editor history.
The original and UI/UX branches and all five editor-source hashes remained unchanged.
The test preview stopped and released only its own lease; other leases were retained.

Runtime evidence: .studio/editor-activation-20261012-54a08610.json (outside Git).
Preview startup 18.472 seconds; save-to-preview refresh 14.482 seconds. Network,
HTTP/SMTP/IMAP/native database, DNS, host credential and child-process isolation
checks passed. Synthetic data persisted across editor refresh. No new dependencies,
background polling, production code execution or services were added. Actual new
Edge editor clicks were not agent-operated; UI routing uses deterministic protocol
checks and runtime acceptance uses authenticated HTTP plus real container frames.

Files changed for activation: scripts/studio/draft_ui.py, editor.py, companion.py,
Companion.ps1, ui/pair.js, ui/drafts.js, ui/drafts.css, ui/index.html, ui/editor.js,
components/developer_studio/panel.html and panel.js, the focused editor/pairing/
launcher/selection tests, verify_editor_runtime.py, and this guide. Prior V5 changes
were preserved. No source commit, push or deployment occurred; Publish stays disabled.

Next visual-editing step: add reviewed mappings for more OS components and a safe
inspector inside the isolated preview. A click must resolve to a supported component
ID and editable property schema, with a selection overlay and the same revision/hash
checks, before enabling click-to-inspect. Do not treat arbitrary Streamlit/Python
screens as editable DOM or run draft scripts in the trusted companion browser.

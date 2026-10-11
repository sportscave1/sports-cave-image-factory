# Developer Studio Phase 4D staging proposal and acceptance

Status: existing owner-approved Starter staging is live; production remains unchanged.
The staging branch is codex/staging/developer-studio-4d-369a5c73 at
395c2c358334520b63e61a7d45e4b1878ea0a172. Temporary service
srv-db5m140473hc73bkpi50 has auto-deploy disabled. No additional service is needed.
The original Phase 4B/C acceptance is retained outside source control. Commit
6a1390396dae22f9939632da4421d7302afb2dcd contains its exact 15 accepted files despite
its misleading worker-fix title. The actual worker fix is
813c9d89a7480a86f08a811a9ad79652c9221795, reported live by Render on the app and worker.
Do not amend either commit or substitute their identities.

## Exact proposed resource

- Workspace: Nathan's workspace, tea-cut91gtsvqrc73e5acs0.
- Name: sports-cave-studio-pairing-369a5c73 (temporary test service, not a primary OS).
- Repository: sportscave1/sports-cave-image-factory.
- Dedicated branch: codex/staging/developer-studio-4d-369a5c73.
- Region: Oregon; one instance; auto-deploy disabled.
- Dockerfile: scripts/studio/staging.Dockerfile; context repository root.
- No Blueprint sync, pre-deploy command, database, disk, cron, worker, environment
  group, production credential or production service modification.
- Environment: STUDIO_STAGE_PASSWORD_SHA256 and STUDIO_STAGE_EXPIRES_AT only,
  besides Render's standard variables. Set a fixed expiry within 24 hours.
- Generate a NEW random 32-byte URL-safe staging password after resource approval.
  Keep its plaintext only in the owner's private local runtime storage; send only
  its SHA256 to Render. Never reuse an OS password or a local companion token.
- Health path: /healthz. The service and owner access fail closed after expiry.
  Expiry does NOT stop billing: suspend the service after acceptance or failure.

Cost requires owner approval before branch publication/resource creation. Free
compute consumes the workspace's shared 750-hour allowance; exhausting it can
suspend existing Free services, including the production webhook service. Starter
is listed at US$7/month, prorated by time. Both consume shared build/bandwidth
allowances and may incur overage charges. Current remaining allowances/spend limits
are unverified. No paid upgrade or unexpected charge is authorized by this file.
Sources: https://render.com/docs/free and
https://render.com/articles/render-vs-railway and
https://render.com/articles/how-much-does-cloud-application-hosting-cost-for-small-businesses

## Safety and scope

The image copies only the small authenticated host and the existing panel's three
assets. It does NOT copy or execute app.py, Streamlit, provider clients, workers,
migrations, the task registry or Windows files. It runs as a non-root user with no
new packages. Only root, /panel and public /healthz are served. Other filesystem
paths are rejected; all POST operations are rejected. Owner authentication uses a
separate high-entropy HTTP Basic credential over Render HTTPS, with server-enforced
expiry, exact hostname checks, no credential logging and no-store responses.
No permissive CORS, reverse tunnel, remote shell or hosted local-operation API is
introduced. CSP denies fetch/XHR connections; reviewed popup/postMessage pairing
remains in the browser. The server never receives registry/preview metadata.

This is a LIMITED UI pairing host, not a full-application staging environment or
an OS-level sandbox. Its environment checks catch misconfiguration; they are not
a security boundary for arbitrary application code. Existing application execution
remains inside the local verified Docker boundary. Never add production secrets
or start the full OS with this service.

The wrapper models a sandboxed component iframe, but is not Streamlit. Passing
this test establishes representative HTTPS pairing only; full application owner
routing and navigation, latest-main integration, worker compatibility and final
live acceptance remain separate launch gates. Local owner-predicate tests do not
prove the production account configuration. Real Publish remains disabled.

## Manual Windows acceptance (Chrome AND Edge)

Record browser name/version, UTC time, exact staging commit, origin and results.
Use a fresh browser profile/window without security overrides. Never bypass a
certificate, mixed-content, local-network or browser security warning.

1. Open the actual Render HTTPS URL returned after deployment. Confirm the expected
   staging hostname, valid certificate and LIMITED UI label. Check HTTP redirects
   to HTTPS BEFORE entering credentials. An unauthenticated/new private window
   must require the staging owner credential. Incorrect credentials must fail.
2. Sign in with username owner and the NEW staging-only password. Do not enter
   any production OS password here. Verify the panel is inside the wrapper iframe.
3. In PowerShell, cd to the allocated RELEASE worktree and run:
   ./scripts/studio/Studio.ps1 DraftUI -Id 20261011-369a5c73 -Owner me/studio-release-4bc-v2 -Open
   Keep the private launcher URL on the local device. Enter ONLY its public
   http://127.0.0.1:port origin in the hosted panel and choose Connect local device.
4. In the localhost approval popup, verify the exact requesting staging HTTPS
   origin. Paste the private launcher URL ONLY into that localhost popup and
   approve. Never paste the companion token into staging or a screenshot/report.
5. Refresh drafts; compare task IDs, owners, categories and recorded statuses with
   Studio List/ListDrafts. Check approved revisions; unfinished sources must show
   exclusion reasons. Do not relabel the development base or simulations as Live.
6. Open the assigned draft through local confirmation; check Edit/View Changes.
   For any reversible edit test, record original bytes and restore them afterward.
   Another owner's draft must remain non-actionable. Record stale-edit rejection
   using the existing editor conflict test procedure; never overwrite outside work.
7. Prepare only an already approved immutable source; test Review/Approve/Simulate
   through exact-SHA local confirmation. Real Publish must stay disabled. Novel
   uncommitted compositions must not become approved releases.
8. Start the isolated local Docker preview. Record successful isolation probes,
   actual synthetic application content, Desktop and Mobile sizes, then stop it.
   Do not use live customers, send emails or execute provider writes.
9. Disconnect/revoke locally. The hosted panel must return offline and clear local
   data. Closing the popup and refreshing must not invent current task data.
   Repeat in the other browser, including blocked-popup/offline handling.
10. Narrow the desktop browser to 390px. Check tabs, cards, controls and scrolling.
    A phone's localhost refers to the phone, not this Windows PC: phone viewing is
    offline-only here. Do not expose the companion on a LAN or tunnel to enable it.
11. Record expired-session rejection and stop the companion normally. Suspend the
    temporary Render service after testing. Preserve redacted results; never mark
    unperformed checks passed.

No production push until the exact combined latest-main revision, worker tests,
owner access, pairing, preview safety and release checks pass. Staging does not
implement a trusted real Publish executor or authorize production migrations.

## Phase 4D continuation evidence — 11 October 2026

Owner-reported Edge acceptance: HTTPS staging login, localhost companion pairing,
real task discovery, draft workspace opening, isolated Docker preview startup,
and actual synthetic OS login screen rendering succeeded. Browser version was
not supplied. This is manual evidence, not an automated browser result. Synthetic
sign-in, desktop/mobile layout, editor/release tabs and disconnect acceptance
remain pending; Chrome is unverified. Never equate this limited pairing host with
full hosted OS acceptance.

Focused Studio regression: 159 tests passed in 29.942 seconds. Node pairing
source/origin/nonce/approval/action/revocation/token checks and Render topology
validation passed. These synthetic fixture tests cover editing/recovery and
release safeguards without modifying the owner's selected source files.

Latest verified main and deployed app/worker revision:
813c9d89a7480a86f08a811a9ad79652c9221795. The Studio commit remains
6a1390396dae22f9939632da4421d7302afb2dcd. A temporary Git index resolved the single
app.py icon conflict by keeping both Developer Studio and main's Accounts &
Access settings icon. The resulting combined tree is
46417287f31310b41cc5397761f1cf387e7a9523. This is a Git TREE, not a release commit
or approved candidate. No branch, checkout or working file was merged/reset.
The combined worker fix files, migration runner and render.yaml exactly match
main. Combined runtime acceptance and an immutable release commit remain gates.
Detailed machine-local receipts are in .studio/phase4d-combined-tree.json and
.studio/phase4d-edge-continuation.json under the configured Studio home.

The running owner's preview lease must not be replaced to run acceptance tests.
Continue in its existing window: click Sign in as synthetic admin, then Desktop
and Mobile; inspect Editor, Tests, Releases and History. Confirm unfinished
sources explain their exclusion and real Publish remains disabled. Disconnect
and confirm local task data clears. Never paste a companion token into staging.

Production deployment requires the owner's final release approval after all
launch gates. Keep the existing temporary staging service only for the outstanding
manual checks and suspend it afterward; credential expiry alone does not stop
billing. A separate trusted Publish executor, exact application/worker revision
locking, migration compatibility/backup/recovery and health verification remain
requirements for real in-product publishing.

Combined-tree focused checks also passed: 19 owner/integration, 8 worker-memory
and 10 worker-supervisor/CRM-gate tests. The initial supervisor fixture omitted
CRM modules; the corrected fixture passed all 10. Mocked CRM maintenance emitted
fixture-only missing-dependency warnings; this is not full live CRM acceptance.

## Final testing continuation

Additional owner-reported Edge passes: Desktop 1280 x 900, Mobile 390 x 900,
OS sidebar/Developer Studio navigation, Stop Preview preserving draft source,
and Disconnect clearing task information and showing offline. Browser version
and connected Editor/Tests/Releases/History tab checks remain unverified.

A genuine preview-only login defect was reproduced: the application authenticated
but its cookie-cleanup POST received an unsupported response from plain Streamlit,
leaving the login form visible. The isolated Chromium controller now fulfils only
POST http://127.0.0.1:8501/api/os/auth/clear-cookie with an empty 204 response.
It does not set authentication cookies or bypass credential validation. The real
application creates its cookie and reloads; the controller waits for the form to
hide and the synthetic account to appear. All network, filesystem and subprocess
isolation remains enforced. Production authentication source was not changed.

Runtime tag: sports-cave-studio-runtime:phase4d-login-369a5c73. Restart the local
companion to load it. The local patch image reuses the existing verified image
f49e7c096249087d49d5872c1167c46adfc3d397a2d1cf0e19ea93c7fe0a7383 and replaces
only controller.py; no dependencies were installed. For a full reproducible build,
use the updated Runtime.Dockerfile command in DEVELOPER_STUDIO_PHASE2_PHASE3.md.

The corrected runtime passed synthetic authentication with the login form absent,
Desktop/Mobile, mandatory native/browser isolation probes, real release-catalog
exclusion reasons, unverified Live labels and backend Publish rejection. Login
completed in 3.527 seconds. Evidence: .studio/phase4d-login-fixed-v2.json.
The earlier login probe was insufficient because body text omits input placeholders;
its success flag must not be interpreted as proof that the login form disappeared.

The actual in-app Studio rendered at mobile width inside the synthetic OS. Hosted
HTTPS acceptance still uses the limited staging wrapper, not the full deployed OS.
Chrome is not connected to available browser tooling and remains manual/unverified.
Do not suspend the existing temporary staging service until required browser tests
finish and the owner approves suspension. No new staging resources are required.

## Production handoff sequence (not executed)

1. Finish the pending connected Edge tabs and Chrome acceptance. Record actual
   browser versions; never convert unperformed checks to passes. Verify the final
   owner configuration on the hosted OS and non-owner denial before launch sign-off.
2. Finalize the reviewed combined tree in an isolated RELEASE checkout, retaining
   main 813c9d89a7480a86f08a811a9ad79652c9221795 and Studio
   6a1390396dae22f9939632da4421d7302afb2dcd ancestry. Include the verified preview
   controller/runtime fix and focused tests/docs. Exclude staging-only host/image
   files, machine-local evidence, runtime data and credentials. Create an immutable
   candidate commit only under applicable explicit commit authorization. Rerun
   checks if its source differs from the tested tree; record its full SHA.
3. Request the owner's final production release approval for that exact commit.
   Recheck remote main; if it advanced, stop and re-integrate/retest. Do not force
   push. Publishing from the Developer Studio UI remains disabled.
4. Only after approval, push the exact approved descendant commit to existing main
   using the established Git workflow. Existing Render auto-deploy is enabled: the
   push is itself a deployment trigger. Do not create services or change config.
5. Match the existing Sports Cave OS application and SEO/CRM worker deployment
   commits to that exact SHA; inspect supporting webhook/cron deployment state.
   Check app health, worker memory/errors, owner Studio access and non-owner denial,
   plus focused read-only OS navigation. Do not send emails or invoke live writes.
6. Existing migration runner/render.yaml match current main; this task adds no
   production migration. Inspect the actual pre-deploy manifest before approval.
   Any new migration requires separate compatibility, backup and recovery approval.
   A code rollback never implies database rollback.
7. Suspend the temporary staging service after required browser evidence is
   complete and the owner approves suspension. Do not delete it or create a new one.

The preview relay now retains bounded controller error details. A combined-run
failure was traced to latest-main's account label including the Admin role; the
post-login wait supports both account layouts and still requires a hidden login
form. No production authentication, CRM, SEO, order or worker source was edited.

Final combined runtime passed (receipt phase4d-combined-runtime-v4.json): synthetic
authentication with no remaining login form, actual in-app Studio at 1280 x 900
and 390 x 900, and mandatory isolation probes. Startup was 11.914 seconds.
Editor acceptance preserved exact source bytes after visual/code save, preview
refresh, stale-edit rejection and revision recovery (phase4d-editor-acceptance.json).
An intermediate controller build failed closed on Windows text encoding; corrected
UTF-8 source was rebuilt and tested before recording this final pass.

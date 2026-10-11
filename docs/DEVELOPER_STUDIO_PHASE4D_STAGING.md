# Developer Studio Phase 4D staging proposal and acceptance

Status: prepared locally; no staging resource, branch push or production deployment created.
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

# Auto Editions unattended reliability — LOCAL ONLY

## Isolation and authority

INTEGRATIONS task `20261015-87d20b92`, owner `codex/auto-editions-reliability-20261015`.
Worktree: `C:/Dev/SportsCaveWorktrees/sports-cave-integrations-auto-editions-unattended-companion-and-sc3-20261015-87d20b92`.
Branch: `codex/task/integrations-auto-editions-unattended-companion-and-sc3-20261015-87d20b92`.
Baseline: `f36516699b5c7e724605ba526080f7af4cbed2a4`, independently verified on GitHub/main and all three existing Render services. Includes the SC3303 correction. Other tasks/worktrees remain untouched. No commits, pushes, deployments, live installation, Shopify/Supabase/Dropbox mutations or allocation changes were performed for this task.

## SC3304: exact read-only findings (15 October, AEDT)

Order allocation 679 is assigned edition 009 for product 10452302823731, Last to First: Larry Perkins & Russell Ingall Wall Art. Assignment 20:35:10; order urgency recorded 20:36:45; claim 22:07:15; Preparing checkpoint 22:07:29; terminal colour-profile failure 22:10:51. Approximately 92 minutes elapsed before claim; the durable Preparing interval itself was about 3 minutes 22 seconds. Historical browser display timing cannot be reconstructed from these database records alone.

The persisted queue is Blocked, attempts 1, priority 8, preparation_hash null. No recorded layout approval exists. The old lease expiry 22:52:15 remains on the terminal row; that does not mean work is still active. No completed package ZIP exists for that attempt. No valid upload checkpoint or approved JPG is available, so withholding Download JPG is correct. Do not bypass review or manufacture approval to clear this order.

Local Photoshop outputs independently expose the defect: original.png/reference-1.png contain a 3,144-byte ICC profile, SHA256 `3f6d674174f3804eb0dabdac90ae17486e898c5063a66f861c116ea033da8301`; master.png, number-1.png and reference-100.png have no embedded ICC profile. All full canvases are 11340 x 8016. The old Photoshop PNG save sequence omitted ICC metadata from subsequent exports; the compositor rejected the mismatch before completing preparation.

All 167 historical Deferred product mappings AND queue records still exist. Two were previously promoted to priority 8 for orders (10452302823731 and 8106693984563); 165 remain currently Deferred. This task did not reprioritise or change any of them.

## Confirmed reliability gaps and focused changes

- Existing sign-in startup already works: interactive scheduled task `SportsCave-Studio-20261011-7192d493`, logon plus one-minute recovery trigger, IgnoreNew, unlimited execution, battery allowed. It launches the existing hidden companion supervisor, not an editor/browser. Preserve it; no duplicate task/service is needed. Explicit owner Stop remains an intentional pause until resumed.
- The old supervisor stopped after five consecutive crashes. Recovery now continues under the SAME instance lock, with capped backoff up to 300 seconds and local diagnostics. It never deletes/steals a processor lock.
- Busy preparation previously skipped heartbeat writes. Existing host loop now sends one authenticated progress heartbeat per 30 seconds while busy (instead of a claim), reports Preparing/Uploading/Recovering, refreshes its existing lease, and uses bounded connection backoff. Orders/Edition Ops read current state without Dropbox calls. Stale activity becomes Recovering; expired legacy leases are not falsely Preparing.
- New host heartbeat endpoint requires the existing preparation capability, exact PID/token and original audited operator. It cannot approve, remap, allocate or renew a superseded lease. Renewal of an expired same-owner lease is rejected when another active processor owns work.
- Durable local journals retain exact source/revision/lease/geometry context and pending terminal checkpoints. Transfer bearer secrets and tickets are not persisted. Restart reconnects only the same owned lease, acknowledges lost successful responses, resumes verified packages, or repackages verified finished pixels without Photoshop. Complete hash-verified staged PSDs are reused; partial input and prior preparation folders are retained. Transient transport retries back off; source/ownership conflicts fail closed. New claims retry transient setup failure at most three attempts.
- Terminal build failures now report their checkpoint even when the preparation worker is called directly. Failure reports reconnect after Render restarts and persist pending acknowledgements. Existing Close/Stop refuses busy claims, work or checkpointing rather than killing daemon workers mid-transfer.
- New processor locks carry an owner nonce, PID and timestamp; release verifies ownership. Existing legacy/unknown locks are retained, never automatically removed. A hanging Photoshop COM call cannot be forcibly recovered safely: after the local activity window, lease renewal stops and diagnostics require operator inspection; the lock is retained.
- Paid/partially paid outstanding orders retain priority 8, ahead of catalogue work; Prepare Now retains 10. Within priority 8, recently activated work precedes older product creation dates. Deferred priority 0 stays ineligible. Existing registration, exact discovery and Add/Save enrolment remain in use; normal new mappings require no Resume.
- ICC restoration is metadata-only and only for newly staged exports with conclusive per-export Photoshop profile evidence. It requires a valid ICC in the independent original, the exact inspected document profile and identical profile names for every expected export. Conflicting/invalid/incomplete evidence fails closed BEFORE changes. PNG compressed IDAT bytes remain unchanged. All original pixel, outside-number, source and geometry checks still run; no supplier certification is inferred.
- Reimport can retain Cloud Ready only for an EXISTING product-wide approval of the exact immutable preparation hash/source, with no conflicting layout hash. No approval is created or copied. Changed/reset artwork retains mandatory review and V16 supplier requirements.
- Orders has actionable compact status links for failures and recovery rather than a misleading unavailable download. The existing status detail view polls only while visible and shows the JPG link only after the authoritative current readiness permits it. The download endpoint still enforces the existing allocation, source, variant and approval gates. No page-wide polling, whole-page rerender or per-row Dropbox reads were added.

## Validation

- Combined focused backend regressions: 154 passed, 2 optional PGlite-only skips. Native SQL tests used a disposable loopback PostgreSQL cluster under this task, port 56420; no live credentials.
- Final recovery/import/Reset lifecycle regression: 57 passed. Additional final acceptance: 20 reliability tests passed. These overlap the earlier regressions; counts are not additive.
- Status/API/host focused pass: 66 passed with 1 optional fixture skip; later final host/API checks 29 passed with 1 skip.
- Existing companion/session/startup suite: final 31 passed. One earlier preview fixture timed out; isolated retry and full final run passed without an unrelated preview code change.
- Seven browser scenarios passed: two new recovery/Uploading/Review/JPG-gate desktop/mobile scenarios, three existing native Reset/refresh scenarios and two V16 responsive quality scenarios. All intercepted/synthetic or loopback fixtures. No live order edited, no real allocation generated, no Photoshop or provider APIs used by tests.
- 167-row Deferred snapshot and allocation/certificate fixtures remain unchanged through recovery; heartbeat ownership, expired-lease fencing, multiple jobs, restart, repeated upload success acknowledgement, source change, profile conflicts and safe stop are covered.
- Synthetic 334-row comparison against CURRENT f3651669: one DB query, zero Dropbox calls; median 63.76 ms baseline versus 47.89 ms local (timing noise, not a hosted speed claim). Peak Python allocation 1,097,002 versus 1,090,256 bytes; response 79,252 versus 79,282 bytes. Connection state is returned once per batch, not repeated per row. No quantitative hosted memory/latency claim.
- Syntax, focused diff checks and canonical Render topology validation passed. Existing SC3303/allocation backend code is untouched.
- During the first test run an isolation defect created one empty staging folder in the real local staging directory. It was confirmed empty and removed; no network or Photoshop operation ran. The test path was corrected to the disposable fixture root before rerunning. No existing assets were changed.

## Installation and remaining blockers

Installed runtime remains `v9-auto-editions-oneclick-sc3284-handshake-20261014`; installed auto_editions_local.py SHA256 remains `4402cd3338c4ffffa39a3b7c458476094d923040de4cf87de404a635d9af0470`. The installed companion and scheduled task were only read, not updated/stopped. The live version does not yet have these reliability changes.

A separately approved release must deploy the tested server/API/Orders changes FIRST, preserving current V6/V15 flags and V16 quality policy. No additive migration, new dependency, paid infrastructure or new service is required. Do not run this new companion against an old server lacking its heartbeat endpoint.

At an owner-approved idle checkpoint window, use existing authorised Stop/Start controls and update the existing runtime's companion.py, draft_ui.py, auto_editions_local.py, scripts/prepare_auto_editions.py, scripts/photoshop/prepare_auto_editions.jsx and new auto_editions_colour.py. Preserve the installed home, owner, port, pairing capability, scheduled task and all journals/packages. Retain a rollback copy. Do not replace an active process or delete an uncertain Photoshop lock.

Actual Windows Photoshop execution of the new export evidence/ICC handling, sleep/wake, and interrupted real Dropbox upload remain UNTESTED live. They require a separately authorised idle installation and isolated artwork acceptance. The computer must be signed in interactively, awake, connected, have sufficient working disk (existing minimum 8 GiB), Photoshop.Application.200 and the exact artwork fonts/profiles. Locked or unavailable Photoshop requires operator repair; safe automation cannot steal its lock or bypass a blocking dialog.

SC3304 needs an authorised retry after release, using its existing edition 009. Its first successful current preparation still requires owner visual review because no existing approval was found. No real allocation should be created for acceptance. Supplier-ready automatic certification remains unavailable without approved production standards. No unrelated allocation/order correction is included.

## Exact file inventory

- `auto_editions_onboarding_api.py`
- `auto_editions_onboarding_store.py`
- `auto_editions_priority.py`
- `auto_editions_runtime.py`
- `auto_editions_setup_api.py`
- `auto_editions_status.py`
- `auto_editions_store.py`
- `components/auto_editions/status.html`
- `orders_page.py`
- `scripts/photoshop/prepare_auto_editions.jsx`
- `scripts/prepare_auto_editions.py`
- `scripts/studio/auto_editions_local.py`
- `scripts/studio/companion.py`
- `scripts/studio/draft_ui.py`
- `tests/test_auto_editions_preparation_host.py`
- `auto_editions_colour.py`
- `tests/test_auto_editions_reliability.py`
- `tests/test_auto_editions_reliability_ui.cjs`
- `docs/AUTO_EDITIONS_PERMANENT_RELIABILITY_LOCAL.md`

# Native automation publication

The editor's Publish now command saves current widget/content state, then calls
`AutomationStore.request_publish`. It never performs the authoritative publication
inline. The automation-only copy-review checkbox is removed. The accepted job's
frozen documents have `copy_reviewed=true`; the editable draft is not silently
approved. Campaign review controls and send paths are unchanged.
An automation-only browser barrier acknowledges the command immediately, blurs
native fields, waits for the existing section bridge's save acknowledgement and
the field rerun to settle, then submits the current button. If synchronization
fails it stays in the editor; pending content is never silently omitted.

## Acceptance and persistence

Acceptance checks authorization, native/editable status, exact saved revision,
flow/document structure, subject presence and truthful subject prefixes. It stores
the snapshot and `config.publication.state=PUBLISHING` in one transaction.
`crm_automations.status` remains its existing delivery state. This is deliberate:
the previously published ACTIVE version must continue operating during a replacement.

The additive migration `20261005061015_crm_automation_publication_jobs.sql` creates
a private, RLS-enabled job table with browser grants revoked. A partial unique
index allows one QUEUED/RUNNING job per automation; repeat submissions of the same
revision reuse the job. Successful identical requests reuse the completed result.
Failed requests can create a new attempt. No historical template version is changed.

## Worker and transactions

The existing leased `Engine.tick` in `crm_worker.py` consumes at most one publication
after refreshing trigger readiness, before its existing source/delivery work.
No new service, scheduler, browser future or standalone worker is introduced.
The existing worker loop wakes every 30 seconds; production completion latency
also depends on existing worker/provider load. This feature does not change that
cadence or unrelated worker tasks.

Claims use `FOR UPDATE SKIP LOCKED`, a five-minute lease and a three-attempt bound.
An interrupted claim is recoverable. Claim owner and attempt fence obsolete workers.
Storage failures requeue with a 30-second delay; validation failures persist a safe
operator reason immediately. After repeated interrupted claims the job becomes failed.

Rendering, checkout transformation, sanitizer/production checks, tracking and size
checks run outside the automation row lock. A short final transaction checks job
ownership, base publication version, lifecycle state and current job identity,
creates immutable template versions/steps, swaps the active publication, and marks
the job successful atomically. Draft N+1 is preserved when snapshot N completes.
Pausing/archiving/deleting during work prevents the job from reactivating the flow.
Publication itself never creates enrollments or calls email delivery.

## Home and error UX

Home shows Draft / Publishing / Live / Paused / Archived / Publish failed.
Publishing indicates its saved revision. A three-second Streamlit fragment reads
only publication status for visible pending rows. On a terminal transition it
invalidates list/count caches, retains KPI data, and does one normal repaint.
That removes the fragment, stopping publication polling. Existing 20-second Home
analytics refresh remains unchanged. Errors retain the last visible status.

Failed publication reasons are allowlisted messages, not provider exception text.
The editor displays them after reopening/reloading and enables retry. A failed
replacement does not pause or discard the existing live publication.

## Local verification and rollout

Tests use loopback PostgreSQL/PGlite and mocked transports, never a live automation
or real email. Browser tests run the publication executor in a separate local
process and observe Home's own status refresh at 1920, 1366, 750, 390 and 320px.
Observed click-to-Home times with immediate unsaved-field edits were 1059–1226ms;
durable acceptance in focused SQL
tests was approximately 6–18ms. These are local fixture measurements, not Render
latency guarantees.

The focused publication/email/migration set passed 88 tests and the additional
targeted CRM regression set passed 113. All three automation browser scripts
passed, including immediate subject/HTML edits, asynchronous success/failure,
menus and the existing composer at the five widths. The wider discovery run
executed 842 tests with 10 failures, 12 errors and one skip; all 22 failure/error
names reproduce against the unchanged baseline. It is not a green full suite.
Compilation, JavaScript syntax, migration manifest, topology and diff checks pass.

Apply the reviewed migration before deploying the updated OS and existing combined
CRM worker. No new environment variables or Render topology change is required.
Production migration, deployment and automation activation have not been performed.
Win Back currently exists as legacy functionality; no new native trigger or legacy
business rule is introduced by this change. Future supported native triggers use
the same publication pipeline.

# Automation publishing responsiveness

Local implementation, 8 October 2026. No production publication, customer sends, database migration or deployment was performed.

## Findings and changes

The existing system already persisted immutable snapshots in `crm_automation_publish_jobs` and processed them through `crm_engine.Engine.tick`. There is no new queue, service, browser-owned publishing task or mail transport.

The toolbar requested a durable job but reran only itself, leaving the user in the editor. Accepted publication now uses the existing `open_flow` route. Validation or persistence failure keeps the editor/draft available. The same toolbar polls only while publication is pending, using the existing two-second fragment wakeup; it displays Publishing changes, Published / Up to date, or a compact failure reason with Retry Publish. Status read failure stops the spinner and offers Retry status without claiming completion.

The client save barrier always waited for a 500ms quiet period across the entire editor, including unrelated previews. It now waits for native fields only when native input was edited, scopes observation to editing controls, and retains the existing server-acknowledged HTML-section flush and its ten-second timeout. Duplicate clicks are gated while saving; retries use the same server-side active-job uniqueness safeguards.

Worker validation rendered every enabled email twice: once for size checks and again for final tracking/transport validation. It now computes the validated final size once and passes that report into the existing production checks. No validation, sender/consent rule or template content is removed.

The existing three-attempt / five-minute lease recovery had no overall age limit for queued work when the worker was offline. Jobs now have a 20-minute acceptance-to-commit deadline. The worker checks it before expensive processing and again before commit. Flow status checks persistently fail overdue jobs even if the worker is offline. A resumed stale worker is fenced by terminal state/owner/attempt checks. Expiry changes only job status and publication metadata; saved drafts and previous live versions remain intact. The existing eight-second database connection/statement limits remain; acceptance and expiry additionally bound row-lock waits to two seconds.

Publication remains atomic. Existing recipients keep their published steps, paused flows stay paused, edits after acceptance remain unpublished, and publishing does not enroll customers or send emails.

## Local measurements

Synthetic two-email fixture, desktop Windows browser and loopback SQL. These are not production latency guarantees.

| Measurement | Before | After |
| --- | --- | --- |
| Saved-draft click to accepted UI | 1,404ms, stayed in editor | 339ms, arrived on Flow |
| Edited-subject click to Flow | No automatic handoff | 855–1,358ms across local desktop/mobile runs |
| Durable SQL acceptance | 6.3ms sampled | 9–34ms sampled; small bounded lock-setting overhead / run variance |
| Two-email preparation median, seven runs | 9.58ms | 6.72ms |
| Production renders for two emails | 4 | 2 |
| Separate worker process plus observed success UI | Not measured | Approximately 1.4–1.5s including process startup and status polling |

The backend request was already fast locally. The principal improvement is correct navigation and removing unnecessary browser waiting, not a claimed production database speedup. Worker queue latency depends on the existing CRM worker's health and cycle; no new polling/worker service is introduced. The 20-minute timeout is a safety ceiling, not an intentional delay.

## Verification

- 44 Python tests passed with `CRM_TEST_POSTGRES=1`: publication, lifestyle-image templates and checkout publication migration suites. Disposable PGlite on loopback only; external transport mocked/blocked.
- SQL coverage includes new/live/paused publication, multiple steps, lifestyle sections, immutable drafts, duplicate acceptance, worker restart/reclaim fencing, persistent retries, expiry before/after preparation, rollback and prior-version preservation. The local SQL adapter serializes transactions; this is not a production concurrency load test.
- Edge browser checks: desktop/mobile Flow handoff, unsaved subject and HTML flush, refreshed status, background completion while away, validation failure and safe retry, analytics unaffected by status polling.
- Chrome barrier checks: preview mutations do not block a saved request, double clicks, rejected save acknowledgement and retry.
- Chrome toolbar checks: compact/responsive layout, Flow Pause/Resume, publishing while paused, latest subject preserved, Send Test control and back navigation. Real test emails were not sent. Rapid editor lifecycle clicks during mounting were unreliable in the older fixture; lifecycle verification uses the fully rendered Flow controls. No lifecycle engine changes were made.
- Python compilation, JavaScript syntax checks and `git diff --check` passed. This Streamlit application has no separate frontend production bundle to build for these files.

## Files and rollout

- `crm_automation_toolbar.py`: accepted Flow navigation and compact persistent statuses.
- `components/crm_sections/automation_publish.js`: scoped save barrier and Retry Publish handling.
- `crm_automation_publication.py`: reuse final size validation, deadline fencing and bounded lock waits.
- `tests/test_crm_automation_publication.py`: timeout and multistep rendering regressions.
- `tests/test_crm_automation_publish_ui.cjs`: Flow handoff and background status browser regression.
- `tests/test_crm_automation_publish_barrier.cjs`: browser save-barrier regressions.
- `tests/test_crm_automation_toolbar_ui.cjs`: existing toolbar assertions updated for Flow handoff.

No new migration. Existing publication-job migration `20261005061015_crm_automation_publication_jobs.sql` must already be applied, as required by the current system. Release the updated code through the normal app and existing CRM worker deployment workflow; restart both so imported Python modules are refreshed. Do not create another Render service or change topology. No Render configuration was changed. Production latency, real infrastructure outages and physical mobile devices remain unverified.

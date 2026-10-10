# Campaigns V7.1 — Premium UI and schedule management

**Implemented locally. Not committed, pushed or deployed.**

Local implementation and regression verification are complete for the supported scheduling operations. Release acceptance is incomplete: true concurrent PostgreSQL sessions, Chrome/Edge acceptance and the detail performance target remain unverified or unmet. This report does not declare production readiness.

## 1. Audit and integration

Reviewed the Campaigns Home/data/progress/store/send/send-UI/schedule/snapshot/dispatch/page paths, engine/worker coordination, production-lock migration and regression fixtures. Existing dirty V7/V8 one-click sending, frozen batch delivery, authoring timing contracts, progress caching and concurrent unrelated work were retained. Presentation baselines were copied before changes to `tmp/campaign-v7-1-baseline`.

## 2. Root cause of bulky scheduled detail

The operational view inherited composer spacing, repeated a large progress heading and campaign name, rendered a progress bar for every state, and executed developer diagnostic reads inside a normal-page expander. Actions sat below the operational information. Home used large KPI cards, narrow status columns and CSS that concealed the actual action-button label.

## 3. Compact detail

The shared compact page presentation is applied only to operational detail. The campaign name and navigation/actions use a wrapping native header; the name truncates at desktop widths. Scheduled campaigns show audience count, persisted requested timing, next actual dispatch in browser-local time and a countdown. An unstarted scheduled campaign has no progress bar. Started campaigns retain durable processing counts; Queued is distinguished from actual processing. Completion remains worker-owned, and acceptance is never described as delivery. Preview remains a compact, explicit on-demand load.

## 4. Home presentation

Retained existing metrics, bounded SQL projections, filters, asynchronous reads and progress fragments. Reduced heading/card/row density, restored Segoe UI typography, widened desktop status presentation and moved mobile status onto a readable full-width row within the identity/status area. Essential actions remain visible. A native minimum-column width required a scoped override for mobile layout.

## 5. Ellipsis menu

The native popover now has the real visible label `⋯`, campaign-specific help, a scoped action container and compact menu styles. Label-concealing pseudo-element CSS was removed. Scheduled rows expose the shared Edit schedule and Send now dialogs. Sending/terminal rows do not offer another send. Duplicate/history/archive protections remain in their existing backend services. Popover opening is client-side and does not initiate an analytics reload. Existing native focus, outside-click and Escape behaviour is retained.

## 6. Scheduling restrictions

Only an untouched, frozen, SCHEDULED campaign may change timing. The transaction rejects attempts, claims, leases, request hashes, first submissions, provider IDs, accepted/uncertain/failed recipients and non-scheduled campaigns. Initial consent/suppression/eligibility blocks can remain blocked while eligible PENDING rows change. Outage blocks and already-due work require separate investigation and are never released here.

Recipient-local editing requires usable frozen timezone evidence. State/country/postcode mappings and validated address-timezone evidence are supported. Unverified legacy explicit timezones and unknown-location fallbacks fail closed. An original fixed campaign-timezone schedule cannot be silently relabelled as recipient-local; its existing explicit-timezone editor is retained.

## 7. Atomic architecture and audit

`change_pending()` is shared by both entry points. It checks active-account campaign-management permission and explicit confirmation, locks the campaign, checks the expected operation revision, locks every production recipient row, rechecks eligibility and refreshes the validation clock after waiting for locks. It computes due times from the immutable reviewed schedule, not a fresh audience or operator timezone. One JSON recordset update changes only eligible PENDING due times.

The current authorised schedule lives at `campaign-timing:<campaign-id>`. Append-only operation acknowledgements written by this service use distinct `campaign-timing-operation:<campaign-id>:<operation-id>` keys, protected by the existing runtime-state primary key. Campaign locking serializes competing amendments. Older acknowledged requests return their original receipt without reverting the newer schedule; conflicting payloads or stale revisions reject. Audit history, receipt, due times and campaign state commit together. An injected audit failure proved full rollback.

## 8. Database locking and migration decision

`crm_production_lock` was neither modified nor bypassed. Original `scheduled_at`, content, audience/snapshot identities, template versions, tracking identities and historical delivery data remain locked. Local SQL tests verified the trigger rejects original schedule mutation; a read-only inspection confirmed the live trigger definition matches those protections.

No new migration or permission grant is required. Existing server-only runtime-state storage, its primary-key constraint and existing campaign-history storage are reused. The current override is separate from original reviewed/frozen schedule metadata. The worker transition, progress reader, schedule gate and Home activity polling all use the effective override where applicable; recipient selection uses the updated queue due times. The native Scheduled-to-Sending transition locks campaigns first and then rechecks effective due times in a separate statement with a fresh READ COMMITTED snapshot. This prevents a pre-lock schedule read from marking a postponed campaign as Sending. The deployed connection must retain READ COMMITTED isolation.

Native batch preparation already locks the campaign before recipients. The outage gate now takes campaign locks in ID order before its recipient update, then reads the effective mode in a subsequent statement. This prevents a stale pre-lock scheduling-mode read from blocking a newly acknowledged Send now operation. Transaction work has no Shopify/Resend network calls.

## 9. Send now

The separate compact dialog requires `Confirm Send Now`. It moves the same campaign's eligible queued recipients to the existing immediate worker path, retaining every recipient ID and immutable payload. It creates no campaign, audience or delivery records. The transport configuration must permit a new operation; an already acknowledged operation can still replay its receipt after configuration changes. After commit the UI returns to Home with a queued acknowledgement. The existing worker retains consent-change, suppression, provider-stop-state, frequency and retry protections.

A local test invoked the actual native batch worker with mocked transport after Send now, verified acceptance on the original recipient IDs and asserted no Shopify customer lookup. Worker absence is not presented as active sending.

## 10. Timezone investigation and correction plan

An authorised, read-only inspection confirmed the Bathurst frozen snapshot:

| Recorded timezone | Recorded source | Recipients | Original UTC due |
|---|---|---:|---|
| Australia/Darwin | address_timezone | 1,041 | 10 Oct 2026 07:30 |
| UTC | global_utc_fallback | 43 | 10 Oct 2026 17:00 |
| Europe/London | address_timezone | 1 | 10 Oct 2026 16:00 |

All 1,085 rows were PENDING when inspected. No production record, schedule, migration or send was changed.

Confirmed provenance issue: legacy `resolve()` accepts either address-level or customer-level timezone values before geography, but labels both `address_timezone`. The frozen label therefore does not prove geographically verified NT residence. Current Shopify read projections request default-address timezone/geography, but the historical snapshot does not retain enough geographic evidence to establish whether the 1,041 Darwin values were genuine. The 43 UTC assignments are confirmed fallbacks, not verified recipient locations. A Darwin mapping defect is not proven.

Future schedules should use the existing strict recipient-zone resolver: address geography and IANA zone must agree, multizone countries require usable state evidence, and missing/conflicting data rejects. Audit address country/state/postcode against the source timezone before a new review. Never replace these values with Sydney/Darwin assumptions. A correction to this live campaign would require a separate reviewed, authorised timezone-evidence mechanism; this implementation deliberately does not provide an automatic release or mapping repair. Bathurst recipient-local rescheduling remains rejected while its evidence is unverified.

DST gap times and ambiguous repeated local times reject by default. Existing explicit ambiguity handling in the V7 fixed-zone authoring contract remains available. Original audience and timezone evidence are never rewritten by the editor.

## 11. Countdown correctness

The requested date/time and the next actual recipient due time are separate fields. The UI does not pretend that the earliest UTC batch is the send instant for everyone. Local display uses the browser's timezone and explicitly labels it as the operator's local time; no account-specific timezone preference was identified.

The progress SQL supplies server time along with the persisted due timestamp. A singleton client timer uses a per-node server-time/monotonic-clock anchor, rather than trusting a potentially skewed client wall clock. It performs no SQL/network requests each second, skips updates while hidden and disposes when no countdown/local-time nodes remain. New DOM nodes receive new anchors; repeated arm calls clear the previous timer. Saving invalidates only the relevant Home/progress projections while retaining search/filter state.

## 12. Comparative speed evidence

Warm Streamlit AppTest server-render timings, 20 samples per phase/view, fabricated local data and mocked external I/O. Before uses UI source captured from the existing dirty V7 work; backend/progress infrastructure is shared in both phases. Full Home includes metrics, filters and the table. These are server-render measurements, not browser-perceived or production database latency.

| View | Phase | Samples | p50 ms | p95 ms |
|---|---|---:|---:|---:|
| Detail | before | 20 | 326.2 | 380.7 |
| Detail | after | 20 | 369.5 | 526.3 |
| Home | before | 20 | 522.2 | 679.2 |
| Home | after | 20 | 508.0 | 580.2 |

Raw samples are in `campaign-v7-1-evidence/render-benchmarks.json`. An earlier row-only sample is retained separately. Full Home improved modestly in this run; detail became slower. No overall speed improvement or sub-100ms menu latency is claimed. Detail performance needs further profiling before release. Existing comparative bounded-progress tests also ran with one SQL statement and zero Shopify/provider requests.

## 13. Browser acceptance

The connected browser was Codex in-app Chromium. Chrome and Edge were not available as connected automation surfaces; their acceptance remains open.

Scheduled detail was checked at 1920, 1652, 1440, 1366, 1024, 820, 750, 430, 390 and 320 pixels: no document overflow, no empty scheduled progress bar, no normal diagnostics, and accessible actions. Both Home and detail invoke the same dialog. Browser interactions verified prefilled timing, a synthetic schedule save updating Home/countdown, explicit Send now confirmation and the resulting Queued state without another send action.

Full Home checks used the actual renderer, metrics, filters, sidebar and status projections with fabricated data. Settled-layout checks distinguished transient resize geometry from final layout. Native minimum columns and the 320px popover edge required scoped fixes. Final evidence and any remaining browser caveats are recorded in `campaign-v7-1-evidence/browser-acceptance.json`.

## 14. Regression results

The consolidated final suite passed **150 tests** using disposable embedded PostgreSQL (PGlite), existing local SQL migrations and mocked Shopify/Resend. It includes frozen-content/audience/identity preservation, distinct local due times, DST boundaries, no duplicate rows/campaigns, operation replay, stale revision rejection, atomic rollback, accepted/uncertain/attempted rejection, original production-lock protection, outage gating, worker restart reads, permission/confirmation checks and existing native dispatch/idempotency/stop-state tests. No existing tests were weakened.

PGlite and the Python fixture serialize transactions on one connection. They verify SQL, rollback and state transitions but do not prove interleaving of two independent PostgreSQL sessions. Multi-session editor/editor, editor/worker-claim and editor/outage-gate races remain a release acceptance dependency.

## 15. Files changed and dependencies

Changes for this task: `crm_campaign_schedule.py`, `crm_campaign_timing_ui.py`, `crm_campaign_progress.py`, `crm_campaign_progress_ui.py`, `crm_campaign_home.py`, `crm_campaign_countdown.py`, `crm_campaign_store.py`, `crm_engine.py`; new schedule-management tests, a fail-closed browser fixture, comparative benchmark harness, this report and evidence files.

Existing dirty V7/V8 changes in send, controls, engine, worker and other Campaigns modules were preserved; the engine received only the coordinated native schedule-transition integration described above. No Render topology, service identity or deployment configuration was changed. Baselines are presentation comparison artifacts, not a clean Git checkout.

Before any separately authorised release, verify the existing CRM schema/runtime-state permissions on the target database, deploy the UI and effective-schedule-aware worker together, complete true multi-session race tests and Chrome/Edge acceptance, and resolve the detail performance regression. No rollout command or production release is included.

## 16. Outstanding limitations

- Unverified legacy timezone evidence, including the inspected Bathurst distribution, cannot authorise recipient-local rescheduling through this feature.
- Original fixed-timezone delivery remains fixed-timezone unless a separately reviewed recipient-local schedule exists.
- Overdue/outage-blocked/started/uncertain campaigns are deliberately not recoverable through these controls.
- Independent PostgreSQL-session races, Chrome/Edge acceptance and production performance have not been proven.
- Detail server-render latency did not improve in the comparative sample.

**Implemented locally. Not committed, pushed or deployed.**

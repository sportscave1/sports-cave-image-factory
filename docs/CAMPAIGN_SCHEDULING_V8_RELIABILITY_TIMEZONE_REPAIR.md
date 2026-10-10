# Campaign scheduling V8: timezone and reliability repair

Local implementation and validation, 10 October 2026. Production investigation was read-only and aggregate-only. No real email was sent and no live campaign, queue, customer, consent, automation or provider setting was changed.

## 1. Root cause

The previous timing contract stored only `mode`, `date` and `time`. `crm_campaign_schedule.plan()` interpreted these as a separate wall-clock time for every recipient. The editor described recipient-local sending but provided no campaign timezone selection. Home displayed the earliest persisted UTC due time without the operator's intended timezone. This was a semantics mismatch, not evidence that a due job was missed.

The resolver accepted any syntactically valid explicit timezone before checking country/province and fell back to UTC for unrecognized geography. It also labelled customer-level timezone fallbacks as `address_timezone`. A valid IANA string does not establish reliable location provenance.

## 2. Live incident evidence

Authorised SELECT queries located the campaign in Supabase project `ceyzbfpuwuuxaiqwiltz`. The similarly named `sports-cave-image-factory` project did not contain `crm_campaigns`; it was not modified.

At **2026-10-10 06:18:31 UTC (17:18:31 Sydney)**, “V8 Supercars — Bathurst Race Feature” was SCHEDULED, with 1,085 PENDING jobs, no sending-start or completion timestamp, earliest due **07:30 UTC**, latest due **17:00 UTC**. A subsequent aggregate read found zero first-submission timestamps, zero provider receipts and zero claimed/submitting/uncertain rows.

| Persisted timezone | Persisted source | Jobs | Due UTC |
|---|---|---:|---|
| Australia/Darwin | address_timezone | 1,041 | 10 Oct 07:30 |
| UTC | global_utc_fallback | 43 | 10 Oct 17:00 |
| Europe/London | address_timezone | 1 | 10 Oct 16:00 |

Schedule health was enabled and checked at 06:18:56 UTC. The available worker-health record reported `ok`, marketing enabled, last completed cycle 06:15:17 UTC and duration 311,633 ms. These are observations, not proof that this campaign subsequently dispatched successfully. The supplied 17:06 screenshot and these reads occurred before the first persisted due time. They do not demonstrate a worker failure.

## 3. Darwin and UTC provenance

The local Shopify adapter requests `defaultAddress.timeZone` directly in campaign subscriber and batch-profile queries. It does not inject a Darwin/store/account default. Shopify describes this field as the address timezone in its [MailingAddress documentation](https://shopify.dev/docs/api/admin-graphql/2026-10/objects/MailingAddress).

The immutable snapshot records resolved zones and source labels, not the original country/province fields. Therefore it cannot establish whether the 1,041 addresses genuinely belonged to Northern Territory customers. Nor can it establish the original country/address completeness of the 43 UTC fallbacks or the London recipient. Native market membership can come from the Shopify country/tag segment and need not equal the current default-address country.

Automatic approval review rejected retrieval of individual frozen customer IDs as outside the authorised aggregate-only investigation. No customer IDs or profiles were retrieved through that rejected action; no workaround was attempted after the reason was available. A minimal Shopify geography query was schema-validated but never executed. The underlying address-data cause remains unverified.

## 4. New scheduling semantics

New schedules default to **Campaign timezone**. AU defaults to Australia/Sydney. All eligible recipients receive one persisted UTC due instant, irrespective of their own timezone metadata. For 10 October 2026 at 17:00 Sydney/AEDT that instant is **06:00 UTC**. Darwin's 17:00 is **07:30 UTC**, equivalent to 18:30 Sydney.

Recipient-local sending is an explicit alternate choice: “Each recipient’s own timezone”. Its explanation warns of a multi-hour window. Completed review displays the earliest/latest UTC window before the confirmation action.

## 5. Versioned timing model

Scheduled documents carry `policy_version: 2`, `time_basis: campaign_timezone | recipient_local`, date/time and an IANA timezone for fixed schedules. The optional `ambiguity` policy is reject/earlier/later. The saved document and reviewed immutable snapshot retain this contract. Immediate timing retains the existing strict `{mode: now}` contract.

Old three-field contracts remain readable and preserve their original recipient-local/first-occurrence interpretation. Existing queue rows are not migrated or recomputed. Opening a queued campaign cannot change its timing. Editing a legacy draft presents its recipient-local basis explicitly; a subsequent save/review uses the validated new contract.

## 6. UTC conversion and DST

IANA ZoneInfo conversion produces aware UTC datetimes. Fixed schedules convert once, then use the same result for every recipient. Round-trip validation rejects nonexistent spring-forward times. New ambiguous fall-back times are rejected unless the operator explicitly selects the earlier or later occurrence. Date and time strings must use exact YYYY-MM-DD and HH:MM formats. Past schedules fail before queue creation.

## 7. Market choices and recipient validation

AU exposes Sydney, Melbourne, Brisbane, Adelaide, Perth, Hobart, Darwin and Broken Hill; UK defaults London, US defaults New York with other US zones, NZ defaults Auckland. Canada requires an explicit choice among supported Canadian IANA zones. Global requires an explicit IANA entry, with no silent UTC default.

New reviewed market schedules block missing/conflicting default-address country with aggregate `market_country_mismatch` counts. They preserve Shopify membership and do not silently add or remove recipients. Fixed timing does not use recipient timezone metadata to override the campaign timezone.

New recipient-local schedules trust only address evidence consistent with supported country/state mappings. Invalid/conflicting/unknown/unverified timezone evidence blocks the review with aggregate counts. Account/customer/store timezone values and global UTC fallbacks cannot authorise new local scheduling. Ambiguous geography is held rather than guessed; coverage of multi-zone Canadian provinces and less common regional aliases is intentionally conservative.

## 8. Durable queue and worker

The existing worker, batch transport and `crm_marketing_sends` queue remain authoritative. Jobs use persisted UTC `due_at`; the dispatcher selects due rows only, in bounded batches of up to 100 with at most 12 batches prepared per tick. The worker remains independent of browser/session lifetime and performs no per-row Shopify lookups during native frozen dispatch.

A small server-only `campaign-timing:<campaign-id>` runtime record projects the effective timing for progress reads. Old queues fall back to their immutable template timing. This avoids returning content or recipient profiles from progress queries. No schema migration is needed.

## 9. Edit schedule and Send now

The shared Home/detail Edit schedule and Send now dialogs preserve the concurrent V7/V7.1 layout. They support explicit schedule-change or Send now confirmation using the shared timing validator. Opening a dialog sends nothing. Fixed timezone selection and explicit recipient-local selection are available in Edit schedule; legacy timing is labelled before an operator proposes a fixed correction.

`change_pending()` checks manage permission and explicit confirmation, locks the campaign and every receipt, validates the operation UUID and expected prior operation, and rejects stale concurrent corrections. Only untouched native SCHEDULED campaigns whose eligible jobs are still future, PENDING, unleased and unattempted are eligible. Initial eligibility exclusions may remain BLOCKED, with their original due time and status untouched. Outage-blocked, claimed, submitted, accepted, uncertain, completed and already-due jobs cannot be reset. Recipient-local amendments require a reviewed recipient-local snapshot with verified timezone evidence; fixed campaign zones or unverified legacy address timezone values cannot authorise them.

Corrections update existing pending due times and effective timing metadata in one transaction, with history/audit records. They preserve receipt IDs, idempotency keys, frozen content/audience and original locked `scheduled_at`. Individual operation acknowledgement records ensure repeating an older confirmed operation returns its receipt without reverting a newer correction. Failed audit writes roll back timing and acknowledgement changes. Send now additionally requires existing delivery configuration and marketing gates. Subsequent worker processing retains existing stop-state checks.

## 10. Delivery safeguards

Existing immutable publication triggers were retained unchanged. Consent webhooks, suppression, frequency limits, provider suppression, rate limits, durable batch manifests, provider idempotency, uncertain-submission holds, retry windows and worker leases remain active. The schedule gate still blocks already-due scheduled jobs after an OFF gap or an actual greater-than-five-minute worker gap; it does not automatically replay them. Healthy large-campaign backlog is not discarded merely for taking multiple batches.

## 11. Status and countdown

Home and detail show the fixed date/time, city and timezone abbreviation, or explicit recipient-local timing with verified next dispatch and end of window. Countdown markup uses the persisted UTC instant. Its browser interval performs no network or database requests, pauses updates while hidden, and stops when scheduled markup disappears. It never initiates sending.

Existing bounded progress polling remains separate from analytics/editor construction. Durable campaign/update timestamps protect against stale asynchronous responses, including schedule changes before any receipt changes. Missing reads show existing status-unavailable messages. Missed schedules show Needs attention; completed campaigns with failed or skipped jobs show issues. Provider acceptance remains distinct from delivery receipts and revenue metrics.

## 12. Concurrent V7/V7.1 integration

Existing one-click review acceptance, background audience/review preparation, Home navigation, compact table styling, cached analytics and durable progress contracts were preserved. V7/V7.1 shared Home/detail dialogs, compact operational header, local-time countdown companion, disabled unsafe actions, polling projections and stronger lock ordering arrived during final validation and were merged. Initial schedule, amendment and Send now share the same validator. The schedule dialog was updated to honour fixed campaign time and validated recipient-local timing. No Render topology, worker contract, campaign content or analytics formula was redesigned.

## 13. Bathurst recovery plan — no execution

The intended 17:00 Sydney time is already past. The observed queue instead has a legacy recipient-local window beginning at 18:30 Sydney. **No correction, cancellation, replacement queue or email was performed.**

Before any separately authorised recovery, obtain a fresh aggregate state: pending/claimed/submitting/accepted/uncertain counts, first-submission/provider-receipt counts, due window and current lease/worker health. The 06:18 observation must not be reused as present-state authorisation.

If every job is still untouched and future, an explicitly confirmed Send now or a new future campaign-time schedule may amend existing receipts atomically after the release is separately authorised. Never enter the missed 17:00 time as a new future schedule. Never recreate the same audience under new delivery keys. Review unresolved market geography before authorising a correction of a legacy audience.

If any job has been claimed/attempted/submitted/accepted or has become due, this amendment path rejects the whole correction. Partial dispatch or uncertain outcomes require a separate reviewed recovery plan preserving accepted receipts and provider keys, establishing transport outcome before considering any remaining jobs. No blanket resend is safe. This report does not claim the live campaign was repaired or delivered.

## 14. Before/after performance

Forty samples per phase used 1,085 synthetic eligible AU/NSW profiles and a disposable PostgreSQL fixture. Legacy and fixed planning produced the same 06:00 UTC instant for this equivalent audience. Values are milliseconds; the baseline files were copied before this task into `tmp/campaign-v8-before`.

| Local operation | Before p50/p95 | After p50/p95 |
|---|---:|---:|
| Schedule planning | 24.25 / 35.78 | 2.96 / 4.26 |
| Aggregate progress read | 6.29 / 30.79 | 5.32 / 22.21 |

Both progress paths used one SQL statement and zero Shopify/provider calls. Initial measurements found a progress regression; removing a redundant receipt scan and projecting compact timing reduced it. An intermediate run still had a median increase (9.21 to 12.52 ms); the final merged query measured faster in the later isolated run. This variability is disclosed. Final measurements are recorded in `tmp/campaign-v8-performance-final.log` and do not establish production performance or an application-wide speed improvement.

The synthetic browser comparison uses eight startup samples per browser/phase, external requests denied. Before/after changes select the copied/current timing controls within the same merged fixture; they are not complete deployed application builds.

| Browser fixture | Before p50/p95 | After p50/p95 |
|---|---:|---:|
| Chrome header | 160.16 / 333.20 | 210.30 / 229.71 |
| Chrome scheduled row | 249.91 / 346.60 | 223.16 / 268.49 |
| Edge header | 200.29 / 340.82 | 235.32 / 266.47 |
| Edge scheduled row | 301.87 / 380.67 | 249.16 / 283.21 |

Raw values and final summaries are in `campaign-v8-evidence/browser.json`, with CPU/SQL samples in `performance.json`. Browser timing is mixed and sensitive to warmup. No overall speed claim is made.

## 15. Browser validation

Chrome and Edge passed at 1920, 1440, 1366, 1024, 750, 430, 390 and 320px. Checks covered fixed Sydney default, selecting Darwin, explicit local scheduling explanation, no horizontal document overflow or Streamlit exceptions, advancing countdown, stopping countdown on terminal state, no snapshot reads before opening the amendment dialog, fixed-time Edit schedule, Save schedule and explicit Send now confirmation in the shared mocked dialogs. Screenshots and 16 results are in `campaign-v8-evidence`; the final integrated browser run is `tmp/campaign-v8-browser-shared-dialogs.log`.

The preview is synthetic. It does not verify authenticated production navigation, live Shopify preparation, provider delivery or a real corrected campaign.

## 16. Regression validation

Disposable PostgreSQL and mocked Shopify/Resend tests cover the incident-sized fixed queue, immutable snapshots/identities, legacy interpretation, strict formatting, all offered timezone round-trips, Sydney/Darwin offsets, London/US seasonal differences, cross-date conversion, spring gaps, explicit folds, unknown/conflicting geography, country mismatch, permission/confirmation rejection, optimistic concurrency, duplicate-operation protection, claimed/due rejection, future jobs not dispatching early, and Send now isolation.

Existing regression suites cover 1/99/100/101/1,095-recipient batch boundaries, worker completion, restart after uncertain submission, identical retry keys/payloads, rate limiting, suppression/consent changes, outage handling, durable progress and sending protections. V7.1 amendment tests cover three validated local timezone buckets, retained initial exclusions, older-operation replay without reverting, attempted/outage rejection and audit rollback. Before the concurrent UI merge, 151 cases passed. The merged suite encountered a disposable fixture timeout; the affected scheduling modules then passed all 26 cases separately. The final merged suite passed **167 cases in 46.893 seconds**, recorded in `tmp/campaign-v8-final-merged-validation.log`. Final performance validation also passed all six collected cases. The in-memory SQL adapter serializes fixture transactions; this is not a production multiprocess load test. There was no real provider end-to-end email test.

## 17. Files and release requirements

Implementation: `crm_campaign_schedule.py`, `crm_campaign_controls.py`, `crm_campaign_send.py`, `crm_campaign_send_ui.py`, `crm_campaign_progress.py`, `crm_campaign_home_progress.py`, `crm_campaign_home.py`, `crm_campaign_progress_ui.py`, `crm_email_diagnostics.py`, and the native scheduled-transition query in `crm_engine.py`.

New/shared modules: `crm_campaign_timing_ui.py`, `crm_campaign_countdown.py`. Tests/evidence: `tests/test_crm_campaign_v8.py`, `tests/test_crm_campaign_v8_performance.py`, `tests/fixtures/campaign_v8_preview.py`, `tests/check_campaign_v8_ui.py`, timing-projection/issue-label and compact UI expectations in `tests/test_crm_send_progress.py`, `tests/test_crm_home_live_progress.py` and `tests/test_crm_production_v2.py`, and `docs/campaign-v8-evidence/*`. Concurrent V7.1 additions include `tests/test_crm_campaign_v7_1.py` and effective timing in campaign polling projections; these were preserved.

No database migration or new environment variable is required. Existing campaign/runtime schema, server-only permissions, worker lease and sending configuration must already be present. Application and worker must eventually consume the same effective-timing implementation; older worker code would ignore timing amendments. Do not enable amendments during a mixed-version rollout. No deployment command is supplied and no release is requested.

## 18. Remaining limitations

Individual Shopify timezone geography is unverified due to the aggregate-only authorisation boundary and approval rejection. Rare/ambiguous local geography fails closed rather than being inferred. Already-due, blocked or partially attempted campaign recovery is deliberately unsupported by the automatic amendment path. No live delivery verification, production timing benchmark, exhaustive concurrent multiprocess test, complete fake-clock worker lifecycle for every geography, or authenticated whole-application browser test was performed. Those limits must not be represented as passing evidence. The existing isolated provider tests and SQL/browser fixtures substantiate the local changes, not production completion.

**Implemented locally. Not committed, pushed or deployed.**

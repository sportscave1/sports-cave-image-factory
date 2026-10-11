# Campaigns V7 — One-click send and schedule

Local implementation and evidence, 10 October 2026. **Implemented locally. Not committed, pushed or deployed.**

The final confirmation now persists a short, durable preparation request and returns to Campaigns Home. The existing worker performs final verification and publishes the existing immutable delivery queue. Acceptance is distinct from permission to deliver. This is **not a production-readiness declaration**: independent PostgreSQL-session races, Chrome/Edge acceptance and production timing remain unverified.

## 1. Root cause of delays and apparent repeated clicks

The prior `_review_finalization()` called `queue_campaign()` synchronously. That path reloads the immutable review, validates rendering/tracking/catalogue settings, fetches fresh recipient profiles in bounded batches, checks consent/suppression/unsubscribe data, constructs delivery metadata and inserts campaign/recipient work before returning a receipt. Audience size and external latency therefore affected the interactive final click.

The browser remained inside the confirmation dialog displaying Preparing while that work ran. Durable publication could precede its browser acknowledgement. Existing campaign uniqueness already prevented many duplicate submissions; repeated clicks alone do not establish duplicate sends. An exact lost-response/timeout sequence for the reported campaign cannot be established from the available database records.

The current UI uses Accepting campaign during the short transaction, disables the native final button immediately and preserves a stable operation UUID. It claims acceptance only after a committed receipt. A failed acknowledgement checks the durable record; an unavailable lookup leaves the outcome uncertain and prevents replacement sending.

## 2. Existing architecture and synchronous boundary reviewed

Reviewed the send/review/audience preparation/snapshot/market/store modules, campaign progress and Home projections, native schedule/dispatch/engine/worker path, database immutability triggers and existing campaign send reports. Previous local Campaigns V7.1 premium UI and safe schedule-management work remains integrated. Existing queue publication, delivery ledgers, analytics, tracking, suppression and provider submission handling are reused.

Audience preparation and final review still produce an authoritative immutable snapshot before confirmation becomes enabled. Valid audience jobs are reused through their existing fingerprint/freshness rules. Preview is optional. Confirmation does not regenerate Shopify membership or render the email.

## 3. Durable acceptance and receipt

`crm_campaign_preparation.accept()` verifies current server-side CRM manage permission, explicit confirmation, exact saved draft/version and a complete nonempty review less than five minutes old. It locks the draft, checks existing native/accepted state, inserts the request and records acceptance history in one transaction. The request captures campaign/version, snapshot reference, timing, reviewed count, operation UUID and credential-free actor permission evidence.

The short acceptance transaction does not fetch full recipient profiles or create recipient rows. Campaign identity is the existing draft UUID. A primary key on campaign identity and a unique operation identity prevent additional accepted operations. Replays for the same immutable review return its canonical receipt, including a replay with another browser-generated UUID. Changed review/version submissions reject. An accepted receipt can still be recovered when transport configuration later becomes unavailable.

## 4. Background verification and restart recovery

The existing `crm_worker.py` polls durable requests separately from delivery ticks. Its adapter wraps the general CRM store's connection factory in the existing `CampaignStore`, providing draft/render/history operations; that worker integration is exercised with disposable SQL. The executor thread owns no durable state. Database leases, `FOR UPDATE SKIP LOCKED`, operation uniqueness and fenced publication coordinate work across processes. Each request has up to three attempts, a five-minute lease and a thirty-second transient retry delay. Expired final attempts become Failed. Validation failures require attention; no automatic re-release of blocked or uncertain deliveries is introduced.

Preparation calls the existing `queue_campaign()` with the approved snapshot and current lease token. Fresh profile checks have a bounded 120-second batch deadline. The final publication transaction locks the draft/request, verifies the unexpired lease against the database clock, sets a transaction-local publication token and writes the native campaign, frozen template, recipient rows, history and READY receipt atomically. A crash before commit leaves no partial publication; a crash after commit is recovered as READY/native status. Stale workers cannot publish.

## 5. Audience, content and delivery protections

The reviewed membership cannot grow during background preparation. Exact saved content, approved snapshot, rendering settings, catalogue facts, sender/reply-to, tracking, unsubscribe correctness, size limits, market/country, fresh Shopify email/consent and local/global suppression remain checked. Failed eligibility creates blocked rows rather than silently adding or releasing recipients. Existing native send-time consent, suppression, frequency, provider, uncertain-outcome and duplicate-send safeguards remain authoritative.

The campaign's consent-event cutoff is now the database timestamp before fresh recipient verification starts. This closes a gap where an unsubscribe webhook arriving during preparation could otherwise precede a commit-time cutoff. Existing dispatch stop-state checks see that event. New strict recipient-local preparations also compare fresh recipient timezone evidence to the approved zone. Changed/invalid evidence blocks that recipient while preserving its reviewed schedule. These initial blocks remain blocked during any later safe schedule edit.

## 6. Navigation and browser/session recovery

After acceptance the existing `accepted_home()`/`return_home()` flow closes Review and reruns into Campaigns Home. The accepted row is seeded at the top until the bounded SQL projection arrives. Search/filter settings are adjusted only when needed to expose the accepted campaign. Other unsent drafts remain intact. Only table/count caches are invalidated; existing analytics caches remain.

A browser reload or campaign reopen consults the preparation record before showing an editor. PREPARING and FAILED requests have a read-only operational view. Accepted campaigns cannot create another review snapshot, change content, send another internal test or be permanently deleted. Terminal archive/restore metadata remains supported without reopening delivery or changing frozen content.

## 7. Status, progress and countdown

Before queue publication Home/detail show Preparing — accepted, verification pending. No empty delivery progress bar or fictional held recipients appear. FAILED shows Needs attention with safe remediation. Published campaign status takes precedence over the preparation receipt: Scheduled, Sending, Sent or existing issue states come from native records and recipient aggregates. Sent remains the existing worker completion condition; provider acceptance is never described as inbox delivery.

Home reuses the bounded campaign progress projection and scoped active refresh. No per-row provider/profile fetches or one-query-per-recipient status reads are introduced. Terminal progress polling stops. Existing Home analytics caching/parent refresh remains; this work does not claim zero analytics reads after completion.

The countdown uses the earliest authoritative upcoming pending recipient due time. Requested recipient-local timing is separate from the next actual dispatch, formatted in the browser's local timezone. Partial recipient-local sending shows real waiting recipients and the next batch. Browser timers use a server-anchored timestamp and never control delivery or query SQL each second. Timers pause when hidden/dispose without nodes; an authorised rerender restarts a singleton handler. This fixed a reproduced Preparing-to-Scheduled transition where an already-disposed handler failed to restart. Future waiting buckets use slower scoped polling, near dispatch faster polling.

## 8. Database migration and locking

Additive local migration: `migrations/20261010110000_crm_campaign_preparation.sql`. It creates the request table, pending index, RLS/revocations, immutable acceptance/draft guards and a BEFORE INSERT publication guard. No public/anon/authenticated access is granted. Existing server database access is required.

The publication guard requires the current lease and transaction-local token, original reviewed snapshot and matching frozen document/settings/schedule/operation. Old app instances cannot publish a new accepted request through the former synchronous path. The existing `crm_production_lock` is not removed, disabled or given a broad exception. Frozen campaign schedules/content and historical delivery records remain immutable. The earlier narrow effective-schedule override mechanism remains separate and unchanged except recognition of new initial timezone eligibility-block reasons.

## 9. Read-only investigation: Bathurst

Authorised read-only CRM inspection found one native campaign for V8 Supercars — Bathurst Race Feature, identity `f9ff9693-cc45-5ebd-8ba6-40bc07f15aa9`, snapshot `22c6baf0-0177-436f-aa8b-ca55dca747ac`, published operation `75eb508b-d8a9-4f6e-bcb3-7bf6f32be252`. At inspection it was SENDING, started at 10 October 2026 07:30:29 UTC; no terminal sent timestamp was recorded.

Its 1,085 queue rows had 1,085 distinct recipient hashes and Shopify customer IDs: 1,041 ACCEPTED and 44 PENDING. The next pending due time was 16:00 UTC. The reviewed snapshot had 1,112 members, 1,085 eligible and 27 excluded (26 local suppression, one smart sending), complete review at 05:46:04 UTC, and requested 10 October 17:00 recipient local. Three review snapshots existed; one native campaign was published. This confirms durable scheduling and dispatch activity, not inbox delivery or the exact browser acknowledgement history. No duplicate recipient records were found in that inspected campaign.

Earlier read-only timezone evidence showed 1,041 Darwin, 43 UTC and one London. Legacy provenance labels do not prove the Darwin recipients' actual locations. No live timezone, schedule, campaign or queue was changed. Future strict reviewed timezone evidence and changed-zone blocking provide a safe path; correction of legacy location data needs a separate evidence-backed review, never a retroactive assumption or release of this started campaign. Aggregate inspection evidence contains no customer contact details.

## 10. Comparative performance evidence

Tables below are generated from local evidence JSON. They measure disposable embedded PostgreSQL and mocked Shopify/Resend, not production network performance. Acceptance benchmark: five observations per size/mode/phase, 10 ms per mocked profile batch, at most two concurrent batches of fifty. At this sample size empirical p95 is the largest sample. The baseline is the prior local implementation captured before this task, including existing dirty work; it is not a clean Git checkout.

| Recipients | Timing | Before final click p50 / p95 ms | After durable acceptance p50 / p95 ms | Background verification p50 / p95 ms |
|---:|---|---:|---:|---:|
| 50 | now | 107.9 / 155.9 | 31.7 / 39.8 | 100.2 / 221.6 |
| 50 | recipient local | 127.3 / 162.2 | 7.3 / 21.9 | 119.9 / 215.8 |
| 250 | now | 159.5 / 188.6 | 34.2 / 48.4 | 262.7 / 287.1 |
| 250 | recipient local | 113.8 / 144.5 | 19.0 / 38.0 | 142.4 / 166.7 |
| 1,000 | now | 329.0 / 380.4 | 21.2 / 41.5 | 348.7 / 364.3 |
| 1,000 | recipient local | 378.8 / 416.6 | 8.3 / 54.9 | 475.2 / 543.5 |
| 1,100 | now | 412.6 / 419.9 | 20.0 / 38.0 | 426.5 / 477.3 |
| 1,100 | recipient local | 469.4 / 514.7 | 10.2 / 46.7 | 563.3 / 625.8 |
| 2,000 | now | 680.6 / 807.7 | 8.8 / 29.9 | 765.7 / 827.1 |
| 2,000 | recipient local | 630.4 / 697.5 | 7.1 / 10.3 | 700.5 / 719.1 |

The final click moved from synchronous verification/publication (14 explicit SQL statements plus profile batches) to six explicit SQL statements and zero profile batches. Background verification/publication used 23 statements for immediate and 24 for scheduled samples, including claims and safety checks. SQL counts exclude transaction delimiters. Before required `ceil(recipients / 50)` fresh profile batches; that work now runs after acceptance. Actual external HTTP calls were zero in every benchmark. No claim is made that background preparation or dispatch became faster.

Additional before/after review stages (prepared audience supplied to readiness):

| Recipients | Timing | Audience before p50 / p95 ms | Audience after p50 / p95 ms | Readiness before p50 / p95 ms | Readiness after p50 / p95 ms |
|---:|---|---:|---:|---:|---:|
| 50 | now | 34.4 / 41.5 | 35.2 / 45.3 | 12.2 / 28.4 | 8.5 / 28.9 |
| 50 | recipient local | 36.5 / 72.3 | 21.7 / 61.8 | 11.0 / 12.1 | 12.1 / 39.0 |
| 250 | now | 60.3 / 86.2 | 81.8 / 105.6 | 26.3 / 79.5 | 37.1 / 54.4 |
| 250 | recipient local | 54.3 / 79.4 | 54.6 / 69.0 | 28.7 / 34.8 | 20.3 / 33.8 |
| 1,000 | now | 187.8 / 237.6 | 199.0 / 259.7 | 13.6 / 64.2 | 12.7 / 29.5 |
| 1,000 | recipient local | 209.6 / 236.1 | 222.4 / 253.1 | 63.2 / 74.9 | 64.0 / 73.1 |
| 1,100 | now | 248.5 / 273.8 | 231.6 / 301.4 | 34.5 / 55.2 | 15.6 / 51.0 |
| 1,100 | recipient local | 271.2 / 281.6 | 243.6 / 291.7 | 76.5 / 86.9 | 79.2 / 119.3 |
| 2,000 | now | 485.8 / 562.3 | 489.5 / 509.1 | 31.0 / 39.9 | 32.0 / 41.8 |
| 2,000 | recipient local | 418.5 / 457.7 | 414.8 / 444.5 | 121.8 / 165.2 | 120.3 / 137.5 |

Native worker lifecycle checkpoint:

| Recipients | Timing | Dispatch before p50 / p95 ms | Dispatch after p50 / p95 ms | Completion tick before p50 / p95 ms | Completion tick after p50 / p95 ms | Mock batch sends |
|---:|---|---:|---:|---:|---:|---:|
| 50 | now | 123.9 / 154.0 | 92.3 / 113.8 | 358.1 / 406.1 | 236.5 / 267.4 | 1 |
| 50 | recipient local | 72.8 / 73.4 | 135.1 / 162.1 | 181.7 / 333.3 | 233.5 / 269.1 | 1 |
| 250 | now | 429.8 / 552.7 | 503.9 / 645.4 | 523.8 / 534.6 | 522.9 / 592.1 | 3 |
| 250 | recipient local | 365.6 / 542.0 | 421.4 / 443.1 | 431.6 / 459.1 | 316.0 / 319.1 | 3 |
| 1,000 | now | 1439.2 / 1513.9 | 1489.3 / 1671.3 | 266.5 / 291.3 | 503.2 / 545.6 | 10 |
| 1,000 | recipient local | 1379.2 / 1456.7 | 1320.8 / 1634.7 | 313.9 / 498.7 | 210.5 / 247.4 | 10 |
| 1,100 | now | 1359.5 / 1463.0 | 1371.9 / 1373.9 | 451.7 / 602.7 | 224.7 / 415.7 | 11 |
| 1,100 | recipient local | 1249.5 / 1356.4 | 1294.1 / 1408.9 | 167.6 / 280.2 | 196.4 / 236.9 | 11 |
| 2,000 | now | 2769.4 / 2959.5 | 3007.2 / 3958.6 | 196.1 / 248.0 | 189.7 / 389.0 | 20 |
| 2,000 | recipient local | 4060.9 / 4337.2 | 4081.5 / 4193.7 | 383.7 / 442.3 | 378.8 / 423.4 | 20 |

Worker construction, scheduled activation and completion-status projection p50/p95 are also recorded per cohort in `worker-lifecycle.json`. SQL statement and profile-batch counts are recorded per sample in `benchmarks.json`. The 13 requested stages are covered by these backend measurements and browser observations, except real daemon startup, browser paint, real network acknowledgement and production scheduling wait, which remain unmeasured.

Native lifecycle evidence uses three samples per cohort, fake SQL/engine clock, the existing native dispatch and Engine completion path with mocked transport. Scheduled lifecycle cohorts use verified NSW recipients; mixed-zone due semantics are covered separately. All synthetic recipients were accepted by the mock and the native campaign reached SENT. Worker construction is not operating-system process startup. The lifecycle checkpoint predates the final consent-cutoff/timezone-block additions; its dispatch/completion measurements do not benchmark those final preparation checks. An initial accumulated-history WASM fixture run timed out; resetting only disposable synthetic cohorts allowed the complete controlled run. It does not establish production database capacity.

Raw evidence: `campaign-v7-acceptance-evidence/benchmarks.json`, `worker-lifecycle.json`, `browser.json`, screenshots and final regression log.

## 11. Browser results and limits

Actual current Review and Home renderers were exercised through a synthetic editor/timing entry with fake accepted requests and no external providers/database. One final confirmation returned Home with exactly one operation, immediate and scheduled transitions appeared, and browser reload retained Scheduled plus one accepted job. Preparing-to-Scheduled countdown restart and browser-local dispatch formatting were verified.

Codex in-app Chromium tested 1920, 1440, 1366, 1024, 750, 390 and 320 pixels. Review's compact 560-pixel maximum dialog wraps to viewport; final controls remain enabled/in bounds, Home essential status/actions remain visible, no document horizontal overflow was measured. These are synthetic renderer tests, not the full production campaign authoring/OS shell journey. Earlier V7.1 layout results and its outstanding detail-performance issue remain in its separate report.

| Browser observation (five mock samples) | p50 / p95 ms |
|---|---:|
| Review opens | 72.6 / 78.2 |
| Review ready | 92.7 / 100.6 |
| Immediate native-button feedback | 0.2 / 0.3 |
| Confirmation to Home DOM | 175.7 / 207.1 |
| First status after Home DOM | 0.0 / 0.0 |

Both explicit Chrome and Edge entry attempts reported Browser unavailable. They remain acceptance requirements. Browser timings are DOM event/attribute/visibility observations under mocked acceptance; they do not measure paint or a real database round trip. Backend and browser timings must not be combined into a claimed production end-to-end result.

## 12. Regression results

Final consolidated suite: **207 tests passed in 69.988 seconds**, with disposable local PostgreSQL, mocked providers and Streamlit AppTest. Python compilation and scoped whitespace checks passed. Final log: `campaign-v7-acceptance-evidence/regression-final.log`.

Coverage includes repeated confirmations/canonical receipt, lost post-commit acknowledgement, stale review/version, permission and confirmation, no foreground profile/render work, immutable content/snapshot/request, rollback on audit/publication failure, changed consent/suppression/timezone, consent webhook during preparation, disabled configuration, bounded retries, expired lease recovery, stale worker publication rejection at service and database layers, and original native queue/worker/uncertain outcome/scheduling/analytics/cache regressions.

Existing test mocks were updated to the new acceptance boundary, not removed: no-send review tests now prohibit acceptance; mock SQL returns the added authoritative verification clock; the exact SQL reduction includes four additional bounded safety reads. The original duplicate/eligibility assertions remain.

PGlite executes PostgreSQL SQL but the fixture serializes transactions on one embedded connection. Two application-session requests were tested against that adapter; true independent-session editor/editor, preparation-worker/publication and claim races are not proven. Leases were reclaimed/fenced in SQL tests, not through a killed/restarted real production daemon. Network faults/provider retries use mocks. No live email was sent.

## 13. Files changed for this task

- New: `crm_campaign_preparation.py`, additive preparation migration, `tests/test_crm_campaign_preparation.py`, acceptance/lifecycle benchmark harnesses, this report and evidence artifacts.
- Send/review/worker integration: `crm_campaign_send.py`, `crm_campaign_send_ui.py`, `crm_worker.py`, `crm_campaign_snapshot.py`, `crm_campaign_page.py`, `crm_campaign_store.py`, `crm_campaign_delete.py`.
- Projection/UI integration: `crm_campaign_home_data.py`, `crm_campaign_home_progress.py`, `crm_campaign_home.py`, `crm_campaign_progress.py`, `crm_campaign_progress_ui.py`, `crm_campaign_countdown.py`, initial blocked-code set in `crm_campaign_schedule.py`.
- Fixtures/regressions: `tests/crm_postgres_server.mjs`, `tests/fixtures/crm_send_progress_preview.py`, `tests/test_crm_postgres.py`, `tests/test_crm_send_progress.py`, `tests/test_crm_fast_review.py`, `tests/test_crm_audience_prepare.py`.

The shared working tree contains pre-existing/concurrent V7/V8 and unrelated changes. No reset, commit, branch rewrite or removal of their work was performed. The native Engine/dispatch delivery architecture and prior V7.1 schedule controls were integrated, not replaced.

## 14. Future rollout dependencies and safety

No production migration or deployment was performed. A separately authorised consolidated release must first validate independent PostgreSQL-session races and Chrome/Edge/full OS acceptance; inspect target schema/server role permissions and prior schedule-override compatibility; apply the additive migration; deploy compatible preparation/delivery workers before enabling the new confirmation UI across all app instances. Verify accepted-request recovery and native recipient publication against non-customer fixtures before approval for live use.

Retain guards, request records and compatible workers during any rollback while PREPARING requests exist; downgrading to an old UI alone cannot prepare them. Do not remove accepted identities, bypass the production lock or automatically release failed/overdue/uncertain campaigns. Existing canonical Render services and identities are unchanged. This report provides no deployment commands.

## 15. Remaining issues and production limits

- Real production acceptance/network/Shopify latency, daemon startup delay and browser paint performance were not measured.
- Chrome/Edge, full OS authoring navigation and independent PostgreSQL-session concurrency remain outstanding.
- The initial database acceptance does not promise an available worker; it accurately means verification pending. Disabled transport prevents claims/releases. A due time passing during preparation rejects publication rather than silently catching up.
- Legacy Bathurst timezone evidence remains unverified and its campaign has started; it is not eligible for schedule edits or another Send now.
- Prior V7.1 detail-render performance regression remains documented; this task does not claim it resolved.
- Terminal failures require an explicitly reviewed duplicate/correction; no automatic resend or blocked-row recovery was added.

**Implemented locally. Not committed, pushed or deployed.**

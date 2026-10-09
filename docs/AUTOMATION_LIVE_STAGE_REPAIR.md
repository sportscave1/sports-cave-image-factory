# Live publication and stage repair — 10 October 2026

## Production evidence (read-only)

Authoritative database: `ceyzbfpuwuuxaiqwiltz`. Automation:
`76784f53-7878-40cc-85e4-ba60c2ea835a`.

- Live publication v7 contains two enabled stages, with delays 600 and 43200 seconds.
- Email 3 is retained as disabled in v7's published definition and excluded from
  its executable stages. The newer draft enables it with an 86400-second
  predecessor delay. The final UI check correctly shows Disabled.
- Two accepted v3 deliveries occurred after v7 was published. Enrollment snapshots
  and queued template versions, rather than the active publication, selected content.
- All 40 existing enrollments were terminal: 38 completed the original single stage;
  two completed a two-stage sequence. There were no active enrollments or pending
  native sends at the initial audit. No historical memberships were reactivated.
- The original single stage has the same stable ID as today's Email 2. This explains
  the 38 rows with Email 2 sent and Email 1 blank; no missing delivery is fabricated.
- A new v8 publish attempt at 21:45 UTC on 9 October failed with `DiscountHold`.
  Its Email 3 document contains discount variables without `recovery_discount`.
  v7 remains authoritative. The current draft subsequently restored the MYCAVE5
  selection (A$5 off). Publishing that enabled draft is a separate decision;
  this repair does not enable the currently disabled live stage.

## Operational contract

The existing publication transaction already atomically writes immutable template
versions and updates `crm_automations.steps` and `config.published_version`. It is
retained; no new schema, cache, queue or Render service is introduced.

`crm_automation_live.reconcile` locks automation then enrollment, reads persisted
receipts, and discovers all current live enabled stages. Enrollment steps become
an append-only stable-slot ledger. Receipt indexes and idempotency keys never move.
Accepted stages and legacy progressed stages cannot replay. A historical pass is
distinct from a successful delivery. Disabled/removed stages cannot newly send.
Unpublished drafts never enter the runtime sequence.

An active enrollment at the end waits for future published stages, polling in
bounded worker batches. Historical COMPLETED/STOPPED/RECOVERED enrollments remain
terminal. Configured re-entry can supersede an exhausted active enrollment after
its cooldown, provided no new live stage remains; it cannot create two active
memberships. Purchase, consent, suppression and retry guards remain in place.

Existing scheduled deadlines are preserved. Newly discovered stages use the
previous successful delivery timestamp plus their current configured delay.
Stage order follows the live definition even when stable storage slots differ.

Immediately before rendering, `resolve` reads the live stage's exact immutable
template. `Store.begin_send` takes the same automation lock as publication and
checks that the rendered version remains current and is the next eligible stage.
If publication wins the race, the claim returns to pending and renders again.
If reservation wins, that committed version is the audited delivery version.
No network operation occurs under the publication lock. Unknown provider outcomes
remain held; provider idempotency and unique queue keys are preserved.

## UI and diagnostics

Checkout columns merge published metadata with explicitly marked draft-only
stages. Statuses distinguish not published, disabled, historical not applicable,
awaiting reconciliation, predecessor waiting, countdown, processing, suppression,
failure, uncertain transport and provider acceptance. No draft HTML is fetched
by the listing query. Actual publication ID/version appears in receipt details.

`python scripts/diagnose_automation_live.py AUTOMATION_UUID` performs a read-only,
repeatable-read audit of stage pointers, counts, stable enrollment IDs, deadlines,
receipt versions, transport IDs and errors. It excludes names, customer IDs,
addresses, message content, recovery links and credentials. Reservation logs
identify the actual publication; discount publication errors are allowlisted.

## Verification and deployment

The isolated release excludes concurrent thumbnail edits. The 395-test CRM safety
suite passed; one timing-sensitive 4-second concurrency check needed an isolated
rerun and the full suite then passed. All 101 focused tests passed, covering
payload equality, drafts, existing queued recipients, stages 3–6 and 61 stages,
predecessor timing, restart, disabled/reordered stages, mixed histories, terminal
history, publication races, transaction rollback, diagnostics and re-entry.

Tests use loopback PGlite PostgreSQL with mocked Shopify/Resend. The fixture
serializes database transactions; publication races are deterministically injected
at the submission boundary. This is not a claim of production load testing.

No database migration or Blueprint sync is required. Deploy through `main` to the
existing primary `sports-cave-os` and existing `sports-cave-seo-worker` (which
supervises `crm_worker.py`). Never recreate the primary service. Verify both
Render deployment SHAs, health and privacy-safe database counts after rollout.
Publishing unfinished Email 3 or reopening completed cohorts is excluded from
the code release. Any later historical backfill requires a separately counted,
controlled decision.

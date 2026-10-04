# Webhook reliability repair

## Evidence and scope

`/healthz` already used a dependency-free async handler. The Resend route used
the shared ASGI thread pool and waited for `receive_resend`, which inserted
delivery facts and ran multi-statement CRM reconciliation plus suppression/cache
writes before returning 200. A burst could start many such operations without
route-specific admission control. Orders reconciliation also ran in the HTTP
interpreter and shared its global database pool. Low aggregate CPU does not
exclude pool contention or Python interpreter stalls.

These are confirmed code paths, not proof of the exact production incident.
No production traces or credentials were available to identify the specific
blocked resource at the reported restart. Synthetic timings exclude real
Shopify/Resend/Supabase latency.

## New internal flow

The unchanged signature check and body limit run first. At most four Resend
receipt transactions may run concurrently. Excess requests get the existing
retryable 503 contract. A transaction inserts minimal delivery facts and a
PENDING job in the existing `crm_webhook_events` ledger, then commits before
200. No raw customer payload is persisted. Duplicate Svix IDs remain unique;
queue jobs derive their identity from the stored delivery row.

A single bounded consumer polls every second, taking at most 50 jobs per cycle.
`FOR UPDATE SKIP LOCKED` protects cross-process ownership. It invokes the existing
reconciliation and suppression logic inside the same transaction as DONE. A
failure rolls back, leaves PENDING and adds a five-second retry delay using
existing fields. There is no terminal retry cutoff and no in-memory event queue.
The CRM engine excludes these jobs so its Shopify event loop cannot mark them
complete without processing. Other direct callers of `receive_resend` preserve
their synchronous behavior.

Orders reconciliation uses the identical routine, lease, limits, schedule and
allocation arguments in one child interpreter. It no longer shares the ASGI
interpreter or database pool. No Render service or configuration changed.

Shutdown stops intake through the server's normal draining lifecycle, asks the
consumer to stop and joins for ten seconds. The child receives SIGTERM and gets
fifteen seconds to finish; if necessary it is terminated, leaving uncommitted
database work rolled back. Accepted Resend work remains in the durable ledger.
The existing paid-order receipt/idempotency and order transaction behavior are
unchanged. No cancellation flag interrupts a Resend transaction midway.

Logs include received, queued, acknowledged, processed, duplicate ignored,
backpressure and failure stages, safe event IDs, error classes and durations.
No addresses, payloads or secrets are logged. Queue-depth scans are intentionally
not added to HTTP requests.

## Deployment review

No UI, template, send transport, allocation algorithm, schema, reporting formula,
webhook meaning or public response contract changed. Processing timing is the
only externally observable difference: reconciliation follows durable acceptance.

No health timeout increase or plan change is required by this code. After manual
deployment, monitor receipt latency, PENDING backlog, retries and memory for the
additional interpreter. The free Render plan in the existing Blueprint remains
unchanged; production load measurement is required before recommending capacity.

Tests use signed fixtures/mocked providers and a disposable loopback PostgreSQL
engine. They cover durable retries/rollback, duplicates, actual reconciliation,
signature rejection, burst admission, concurrent Orders work, health latency,
child lifecycle and bounded shutdown. Existing CRM and paid-order regressions
also run; no live emails or production writes are used.

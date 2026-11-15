# Campaign batch dispatch

Implemented locally; no live provider calls or production data changes.

## Confirmed old path

`queue_campaign` writes durable recipient jobs. The existing Render supervisor
starts `crm_worker.py` independently of the browser. `Engine.tick` previously
called `send_one` at most five times, then the worker waited 30 seconds.
For each native campaign recipient `send_one` fetched fresh Shopify state,
looked up Resend suppression and contact state in two paced HTTP calls,
ran readiness/render/size checks, rendered again with the native unsubscribe
URL, and committed multiple separate receipt/claim/stop-state transactions.
The Resend adapter paced each request with a fixed 0.55-second gap.
These are code-confirmed bottlenecks, not measurements of Peter Brock's live send.

## New queue and dispatch contract

Review, fresh queue-time Shopify eligibility/identity checks, suppression checks,
immutable snapshot/version checks, scheduling, rendering, size and tracking
validation remain in the existing queue boundary. That boundary now retains
minimal frozen delivery values (address and Shopify-native unsubscribe URL)
in the server-only immutable delivery template, alongside the already validated
production HTML/text, sender and reply-to. This is campaign delivery data,
not a general customer mirror. The reviewed audience can only shrink.

The shared render already contains canonical campaign/send tracking identifiers
and the conservative 2,000-character unsubscribe representative. Dispatch
substitutes only that URL, escaping HTML independently from plain text, and
checks actual UTF-8 HTML length locally. It does not sanitize, parse, render,
rebuild an audience, or call Shopify. Native URLs exceeding the validated
allowance are blocked during queue preparation.

`Engine.tick` invokes `crm_campaign_dispatch.dispatch` before its unchanged
automation/legacy-template single-send loop. New campaign rows cannot be claimed
by that loop. The existing server-side worker lease serializes batch ownership;
closing the browser does not stop dispatch. No Render command/config change.

At most 12 batches / 1,200 due recipients are prepared in a tick, ordered by
due time then recipient hash. Future scheduled recipients remain pending.
Maximum request batch size is 100: 1,095 recipients use ten batches of 100 and
one of 95. Each batch gets:

`sports-cave/{campaign_send_id}/batch/{batch_index}`

## Provider stop-state and rate limits

Before preparing batches, the documented paginated `/suppressions` and `/contacts`
reads build a transient hash-only stop set. This preserves provider suppression
and contact-unsubscribe semantics without two lookups per recipient. Complete
pagination is required, limited to 100 pages per source; malformed/incomplete
responses hold work. No stale consent cache. These metadata calls are additional
to the 11 email batch requests; large provider contact lists may still cost time.

Only the documented `POST /emails/batch` is used, through the existing reusable
requests session. Strict batch validation is explicit. Required recipient fields
are prevalidated individually; an invalid frozen address blocks that recipient
before batching. Unexpected strict request rejection fails that batch without
an automatic resend. Partial/malformed receipts are treated as uncertain;
the implementation never guesses an index mapping.

Concurrency starts at one and grows to at most two only when account response
headers establish sufficient capacity. `ratelimit-limit`, `remaining`, `reset`
and `retry-after` govern pacing. There is no per-email sleep or assumed account
rate. Long waits are deferred rather than blocking the worker. No Usage API was
added; response headers supply the actual account metadata.

## Persistence, retries and progress

Existing server-only `crm_runtime_state` holds one manifest per logical batch:
campaign/send identity, index, ordered receipt IDs, minimal frozen recipient
values, payload digest, idempotency key, status, attempt count, first/last request
start, retry time, acceptance time and safe error category. Common HTML is
stored once in the immutable template; it is not duplicated into manifests.

Manifests and SUBMITTING rows commit before HTTP submission. Before every wave,
campaign status is checked; before every submission, bounded local suppression,
smart-sending and later signed consent/deletion event checks run again.
Unattempted batches can remove newly blocked recipients. Previously attempted
unknown batches are held if stop-state changes; their payload is never changed
under the same key.

Provider receipts and all per-recipient ACCEPTED statuses commit atomically in a
bulk update. Accepted batches are never replayed. If Resend accepted but the DB
write failed, the exact original payload/key is replayed within the protected
window. Up to five attempts, exponential minimum backoff, and Retry-After apply.
After 23 hours, unknown acceptance is held as UNCERTAIN, with no automatic replay:
Resend keys are retained for only 24 hours. This protects restart safety beyond
provider key expiry.

Early verified webhooks are linked with a bulk receipt reconciliation pass.
The existing progress queries read ACCEPTED counts, so progress advances once
the batch transaction commits. Existing SENT completion waits for no pending,
claimed, submitting or uncertain rows, not for mailbox delivery. Final recipient
count includes accepted provider receipts only. Failure/held warnings remain.
Delivered/opened/clicked/bounced/complained remain verified-webhook facts.
The Home table adds a compact `submitted / planned` line beneath SENDING using
its existing bounded aggregate query. Only a visible sending table refreshes
at the existing 2.5-second progress cadence; KPI caches stay stable, and the
table returns to its normal refresh interval after completion. No new modal.

Safe INFO logs emit IDs, batch sizes, attempts, preparation/request/DB timings,
HTTP status, numeric rate metadata, counts and throughput. They omit bodies,
addresses, tokens, exception messages and secrets.

## Offline evidence

Baseline: unchanged `HEAD` implementation at `e0b67b5`.
Reproduce with the disposable fixture and:

`CRM_TEST_POSTGRES=1 python -m tests.benchmark_crm_batch_dispatch`

| Metric | Before | After |
| --- | ---: | ---: |
| Accepted recipients | 1,095 | 1,095 |
| Single-email calls | 1,095 | 0 |
| Batch-email calls | 0 | 11 |
| Shopify dispatch calls | 1,095 | 0 |
| SQL statements, including transaction control | 36,141 | 239 |
| SQL writes | 7,667 | 99 |
| Transactions | 10,952 | 42 |
| Fixture duration | 61.616 s | 2.706 s |
| Fixture throughput | 17.77/s | 404.60/s |
| First mock submission, UTC | 11:08:08.405456 | 11:09:11.495294 |
| Last mock submission, UTC | 11:09:09.914699 | 11:09:13.014442 |

Recorded 2026-10-02. Provider read/submission delays were synthetic 1ms/2ms;
provider stop-state reads were mocked in the new path. Before counts 3,285
provider calls (2,190 stop-state reads plus 1,095 sends), after counts 11 batch
calls plus the real deployment's paginated stop-state metadata reads. Neither
measurement includes production latency, actual API pacing or old 30s tick gaps.
This is reproducible local performance evidence, not a production guarantee.

## Deployment limitations

Previously queued templates lack delivery addresses/native unsubscribe URLs.
They keep the existing path and are never silently converted or requeued.
This repair accelerates newly accepted queues. Finish an existing in-flight
campaign normally; do not queue it again to adopt batching. An already accepted
provider submission must never be rebuilt under a new idempotency key.

Provider list permissions, real rate headers, account quotas and live throughput
remain unverified. No credentials, environment variables, migrations or new
infrastructure are required by the implementation. Tracking, attribution,
automation, unsubscribe handling and webhook infrastructure remain active.

## Changed files and validation

- `crm_campaign_dispatch.py`
- `crm_resend_batch.py`
- `crm_campaign_send.py`
- `crm_engine.py`
- `crm_store.py`
- `crm_worker.py`
- `crm_workspace_store.py`
- `crm_campaign_home.py`
- `crm_campaign_home_data.py`
- `tests/test_crm_batch_dispatch.py`
- `tests/benchmark_crm_batch_dispatch.py`
- `tests/test_crm_send_flow.py`
- `tests/test_crm_production_v2.py`
- `docs/CAMPAIGN_BATCH_DISPATCH.md`

Final combined run: 208 tests passed in 35.111 seconds, using the disposable
loopback database and mocked transports only. Suites: batch dispatch, send flow,
production v2, PostgreSQL, Resend marketing, native unsubscribe, email size,
review modal, send progress, Campaigns first paint, Campaigns Home, Home cache.
Python compilation on all changed Python files and `git diff --check` passed.
The production-v2 Home test was updated to the existing segmented-control API,
and worker tests now isolate their own disposable campaign queues.

Official semantics checked against [Resend batch API](https://resend.com/docs/api-reference/emails/send-batch-emails),
[batch idempotency](https://resend.com/changelog/batch-idempotency-keys),
[usage limits](https://resend.com/docs/api-reference/rate-limit),
[suppression listing](https://resend.com/docs/api-reference/suppressions/list-suppressions),
and [contact listing](https://resend.com/docs/api-reference/contacts/list-contacts).

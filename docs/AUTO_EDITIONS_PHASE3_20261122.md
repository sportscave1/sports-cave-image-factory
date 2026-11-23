# Phase 3: bounded immutable Dropbox publishing

The current owner requested Phase 3 of the November 22 latency plan. Work is
isolated in Studio task 20261121-c7b37e2e. No topology, source/profile/pixel,
allocation, Photoshop concurrency or user speed settings change.

## Diagnosis and implementation

The existing publisher makes one fresh folder listing, but its general Files
upload adapter then calls resolve_upload_destination for every missing asset.
A fresh 101-asset preparation therefore makes 101 redundant metadata reads in
addition to that listing and the uploads. Earlier prepared_metadata_requests
did not include these adapter-internal reads. Latest pre-change live publishing
samples were 60.091 s / 47,208,724 bytes, 54.355 s / 31,407,058 bytes and
66.154 s / 59,036,694 bytes, each reporting 101 logical asset uploads. These
different artworks are not controlled before/after measurements.

The edition-only adapter now uploads directly with Dropbox add,
autorename=False and strict_conflict=True. It never overwrites an existing file
or asks Dropbox to find another name. Every accepted receipt must match the
exact path, file id/revision, size and Dropbox content hash. Streamed bytes are
hashed again before commit; truncation, growth or changed bytes abort the save.
A concurrent add or
lost response triggers fresh exact receipt reconciliation before retransmission.
Only a typed not-found response means absent; permission and identity failures
are terminal. Earlier successful files remain reusable through the existing
fresh bounded folder listing, including after a partial failure.

The network pool remains three workers. Larger files stream in 8 MiB chunks,
up to the existing 128 MiB asset limit; no full large file buffer or parallel
Photoshop job is introduced. There are at most three application upload cycles,
each with one SDK error retry and one SDK rate-limit retry, with a 60 s request
timeout. The explicit positive SDK limits avoid clone(0)'s inherit-default
behaviour and the SDK's unlimited default rate-limit retries. SDK-observed
Retry-After is respected; an exhausted rate-limit response also imposes a shared
cooldown on subsequent calls from the three publishing workers. General Files
uploads keep their existing conflict choices.

Typed namespace-write contention also backs off across the pool. A closed or
missing upload session after an SDK finish retry is reconciled against the final
immutable receipt before a new session is considered; it cannot hide a committed
save behind the lost first response.

New preparation metrics count direct SDK calls, reconciliation reads, recovered
assets, application retry cycles and exhausted SDK rate limits. SDK internal
retries are excluded from direct-call counts; these are not wire-byte metrics.
Counters reset on fully reused publication. No existing publishing byte counter
is claimed to measure retransmitted TCP bytes.

## Validation and measurement

The controlled benchmark executes the old and new real publisher and upload
adapter paths against synthetic PNGs and a 10 ms/RPC simulator, three repeats
per case. Fresh publication removed exactly 101 metadata calls; uploads stayed
101 and observed concurrency stayed at most three. Final median time was 0.934 s
before and 0.609 s after (34.7% lower). A 50-asset partial retry was 0.572 s to
0.418 s. Fully reused publication makes no upload in either version; timing
differences there are noise, not a claimed improvement. This measures simulated
request overhead, not Dropbox capacity or a production speed promise.

Reproduce with scripts/benchmark_edition_asset_publisher.py --baseline-root
<unchanged released checkout> --output <new JSON file>. Raw local evidence is
retained in .studio/runtime/20261121-c7b37e2e/publisher-simulator.json.

Focused coverage includes strict no-preflight add, exact/conflicting concurrent
receipts, missing path/id/revision/size refusal, lost small-upload and large
session-finish responses without retransmission, streamed chunk bounds, 429
cooldown, 403 terminal handling, transient retry ceilings, partial successful
receipt reuse, durable Sessions, private acceptance and general Files uploads.

Two older broader tests fail identically on unchanged release 0f85b78a: the v18
snapshot-cache fixture lacks the category now required by its index; the v15
lifecycle fixture expects Review while current technical validation returns
Repair. They are recorded separately and not changed as part of publishing.

Run python scripts/validate_render_topology.py before release. No Blueprint
sync is needed. The server-side change needs no local companion replacement.
Record final focused count, commit/deployment, health, and any observed live
publishing metrics in this Studio task's release evidence. A live timing from
different artwork is observational and must not be presented as a controlled
comparison. Dropbox batch commits and higher concurrency remain deferred: the
redundant requests can be removed without introducing asynchronous batch
reconciliation or more competing namespace writes.

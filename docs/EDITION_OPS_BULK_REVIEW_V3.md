# Edition Ops Bulk Review V3 (local implementation)

No commit, push, deployment, live schema change or production approval is authorized or performed for this task.

## Confirmed causes

The old approval endpoint awaited every product in a sequential loop, including current Dropbox metadata, PNG transfers/checksums, ICC/geometry inspection and the final transaction. The browser abandoned that single request after 120 seconds and had no durable operation identity to query. A lost response could therefore obscure a committed approval.

Preview JPEGs lived only in a process-local LRU. A single global cold-build lock covered downloads and decoding. Eviction/restarts required another decode (and possibly large downloads), and another cold artwork could block an unrelated cache miss.

## Durable approvals

`auto_editions_bulk_jobs.py` stores batches, product jobs and batch membership in private RLS-enabled PostgreSQL tables. Submission performs bounded set-based SQL, records owner confirmation and an exact selection fingerprint, and returns HTTP 202 with the stable request UUID. It performs no provider I/O or integrity scans in the acknowledgement path. Reuse of a request UUID for another selection is rejected. A partial unique index permits one active job per product across all owners/batches. Repeated batches attach to existing active work, or to a committed matching TEST approval that is still present.

`auto_editions_bulk_runtime.py` is an isolated consumer owned by the web application's ASGI lifecycle. It does not run inside HTTP requests, Streamlit sessions, the Photoshop companion, the preparation worker or any unrelated Render service. PostgreSQL is the source of truth: threads are replaceable executors. Two consumers use atomic `FOR UPDATE SKIP LOCKED` claims, a short advisory transaction lock to enforce a global two-product limit across web instances, 90-second renewable leases, ownership tokens and bounded transient retries (three attempts, 15-second delay). Idle polling is 15 seconds; accepted submission wakes the consumers. Shutdown leaves unfinished work persisted. Startup immediately looks for pending/expired work, with expired claims recoverable after at most the remaining lease plus idle poll interval when the database is reachable.

Successful TEST layout approval, onboarding checkpoint, both existing audits and the job's Approved result commit in one transaction. Lost commit acknowledgements cannot replace a persisted success with a retry/failure. The original final product/mapping/checkpoint locks and authoritative status/evidence checks are retained. The lease and current administrator role are fenced in that transaction. Mandatory PNG transfer/inspection runs outside write locks; the existing final fresh Dropbox source lookup remains inside the transaction to retain its source-change fence. It may still extend that short final transaction by provider latency; removing it without an equivalent upstream fence would weaken safety.

The UI saves the request UUID and selection before submission. A delayed acknowledgement triggers read-only reconciliation of that UUID. An explicit retry rechecks it and reuses the same UUID; it never invents a new submission after an uncertain response. Refresh/reopening recovers the saved request and/or latest catalogue operation records. Pending/Processing are operation overlays only, not preparation states. The native Auto Editions column uses those overlays and a small spinner, while the existing authoritative projection always determines Cloud Ready, Needs Repair and supplier certification. Successful historical jobs are projected against current status before the gallery labels an artwork Cloud Ready.

Active progress polls every three seconds and stops at terminal results. Temporary progress failures retry with 3/6/12-second backoff, then retain an explicit Retry tracking control. Outages are reported as an inability to retrieve progress, never as evidence that an approval failed. Accepted work continues without the popup. Approve All Loaded Eligible is explicitly labelled; unloaded or unavailable previews are never selected. Owner visual confirmation remains mandatory.

## Persistent previews

Small 300px and 1200px browser-sRGB JPEGs are derived together from existing verified master/number PNGs once. No PSD, numbered original or full-resolution JPG is regenerated or modified. The cache identity includes renderer version, exact preparation hash, source and immutable receipts. Derived JPEGs up to 512 KiB each persist in a private PostgreSQL table; a bounded 32 MiB process LRU and the private browser cache avoid repeated reads. Larger JPEGs exceeding that persistence cap remain disposable. Striped identity locks deduplicate local builds, with two bounded cold decoders; independent warm cache hits bypass cold downloads. Preview Retry is per card and never changes preparation eligibility/state.

Approval file inspection evidence may be reused in a bounded cache only after fresh provider metadata matches the exact file ID, revision, size, path and Dropbox content hash. The key also binds preparation, SHA256, geometry, receipt and ICC policy identity. Current source checks, manifest/proof checks and final authoritative transaction are still required.

## Local verification and limits

Tests use synthetic identities, real synthetic PNG/ICC bytes and isolated PGlite PostgreSQL. The new failure suite exercises 1,000-design submission, partial success, slow provider metadata, corrupt bytes, stale preparation, overlapping submissions, expired leases/restart recovery, audit rollback, lost commit acknowledgement, administrator revocation during validation, persistent previews and unchanged allocation/certificate rows. Browser fixtures exercise desktop/mobile pagination, per-preview retry, dropped submission responses, reload, popup closure, progress recovery, terminal polling cleanup, native spinner and preservation of editor/scroll state.

Measured reports and JUnit results are under `output/bulk-v3/`; these are ignored local evidence, not production benchmarks. The 35-design comparison runs real validation on 200x100 synthetic artwork with a 10ms delay per provider metadata call. The earlier sequential path is compared with the two-consumer path using separate preparations. Tiny synthetic PNG/JPEG timings do not establish full-size cold-provider performance.

The native PostgreSQL benchmark is skipped; Docker is installed but its daemon is unavailable. PGlite executes the SQL and serializes fixture transactions, so it cannot prove real multi-process lock timing or connection-pool behavior. No live artwork is approved during testing. A release requires explicit authorization, the additive reviewed migration, and authenticated staging/production read verification. Long cold downloads/decode can still be slow; preview timeouts expose Retry without changing preparation state. Persistent cache storage grows with immutable preparation versions; no source assets or historical operation/audit rows are deleted.

## Scope

Changed code is limited to Bulk Review, its isolated storage/runtime, status presentation, web lifecycle registration and the additive migration manifest. No allocation/certificate/order/supplier write path, Photoshop script, companion file, preparation queue implementation, unrelated worker or deployment topology is changed.

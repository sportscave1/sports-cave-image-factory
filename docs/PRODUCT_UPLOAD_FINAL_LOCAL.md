# Product Uploads — consolidated local upload optimisation

Status: Implemented locally. Not committed, pushed, merged or deployed.
Task `20261018-4b18037e`, owner `codex-products-mockups-20261018`, existing branch
`codex/task/products-product-uploads-integrated-existing-mockup-20261018-4b18037e`.

## Completed result

The existing 8 MiB binary request now streams through an ordered writer in 4 MiB
checkpoint frames. Reception of the second frame overlaps storage of the first.
The final controlled Chromium comparison transfers the same 188.65 MiB PSD in
**61.22 → 53.52 seconds (12.6% less time)**. Selection-to-Uploaded falls from
**62.74 → 55.11 seconds**; effective transfer throughput rises from
**3.081 → 3.525 MiB/s**. HTTP chunk count stays at 24.

These are actual Chromium-to-local-HTTP measurements with simulated bandwidth,
latency and a disk storage double. **Real internet/Dropbox speed was not measured.**
No remote storage tests, production credentials/data, native jobs or production
writes were used. This concludes the authorised local implementation.

## Workspace preservation

Ran `git worktree list` from the main checkout and verified the requested root,
branch, registered task owner and existing changes. Read the Phase 1–2 reports
and retained all completed work. No additional relay implementation was present.
No new worktree or project folder was created. Saved the exact Phase 2 runtime
baseline in the existing ignored `output/product-upload-phase2` evidence folder:
`phase2-api.py`, `phase2-intake.py`, `phase2-app.js`. Historical reports and raw
results remain intact; no other task was edited.

## What changed and why

- **Bounded overlap inside the existing request:** one ordered provider writer,
  an AnyIO channel with one queued frame, and two frame permits. Active, queued
  and assembling frames together cannot exceed two 4 MiB buffers. The existing
  SDK needs at most one further 4 MiB immutable body copy. ASGI/network fragment
  and framework allocations are separate; no full PSD is buffered.
- **Admission across simultaneous uploads:** PostgreSQL transaction advisory
  locks allow at most two relay requests across processes sharing this database,
  and one request per intake. Admission happens before application body reads.
  Capacity exhaustion/uncertain prior writes return retryable 503 with Retry-After.
  At most two admission connections and two active checkpoint connections are
  needed concurrently. No durable queue, schema, service or infrastructure was added.
- **Authoritative progress:** each frame uses the existing row lock, validation,
  block digest, provider append and independent checkpoint transaction. An HTTP
  success waits for all its frames and the admission guard to settle. Queued or
  received bytes are never acknowledged as saved. The original per-block hashes,
  exact file identity and final independent storage hash remain authoritative.
- **Failure recovery:** cancellation stops further reception, discards uncommitted
  buffers and lets an active append/checkpoint settle. Restart resumes from SQL,
  without relying on a RAM queue. Replaying an 8 MiB legacy body revalidates the
  already confirmed prefix. An old 8 MiB provider append whose DB checkpoint was
  lost can be recovered as two verified 4 MiB checkpoints, with final storage-hash
  verification still required. Changed replay bytes are rejected.
- **Slow links:** binary requests now have a 60-second no-progress deadline,
  180-second post-send acknowledgement deadline and 15-minute absolute cap.
  Progress resets the idle deadline, so slow movement is distinct from a stall.
  Server reception has a 90-second idle deadline and 15-minute reception limit.
  Six attempts remain the maximum per operation; Interrupted retains the File.
- **Reconcile before replay/fallback:** the authenticated `resume` action obtains
  the same intake lease as the relay, returning only after prior writes settle.
  After an uncertain network/timeout error, the browser checks that authoritative
  offset before replay. A timeout selects supported 4 MiB requests only after
  reconciliation. Healthy connections keep 8 MiB. Older servers/clients retain
  compatible exact-body retry and 4 MiB fallback behaviour.
- **Connection safeguards:** actual database connections default to an eight-second
  idle-in-transaction limit. Upload-only guards use a transaction-local 20-minute
  limit; checkpoint provider-I/O transactions use a local five-minute limit.
  These reset on transaction completion and do not change DB-wide configuration.
  Append SDK clients clone the existing authenticated/rooted cached client while
  sharing its connection pool. Error/rate retries are limited to one each and
  socket timeout is 60 seconds; the SDK's formerly unlimited rate-retry default
  cannot retain relay capacity indefinitely through endless retries. Other cached
  clients/defaults remain unchanged. Provider-imposed waits are not real-world
  measurements or fixed wall-clock guarantees.

Hashing was left alone: it was already bounded and responsive. Original PSD bytes,
layers, quality, profiles, RGB8 checks, colour policy and 1 GiB limit are preserved.
No HTML/layout, manual workflow, integrated Mockups, separate Mockups page or
worker handoff was changed. Fresh pages still start empty without a stale preview;
explicit selection must validate the exact file before resuming. Upload alone
creates no worker jobs. Native processing is not included in transfer/finalisation.

## Small before/after comparison

Existing benchmark harness: `tests/benchmark_product_upload_browser.py`.
Same existing NON_PRODUCTION PSD: 197,816,894 bytes / 188.652891 MiB, content hash
`f1e90d6ef5f8f6083a0577c3846aec472050283c126a5a30cc8ccae4aa799c56`.
Actual headless Chromium, isolated loopback Uvicorn routes, disposable PGlite SQL,
synthetic account, disk provider. No full application server or native worker.

Controlled network profile is unchanged from Phase 2: 40 Mbps Chromium upload,
160 ms CDP latency, storage append delay 180 ms plus bytes at 100 Mbps. Browser
latency can overlap transmission. One new baseline and one final measurement per
profile; one initial relay measurement was retained before the final timeout/SDK
safeguards, then the final code was measured. No competing transfer system was built.

| Measurement | Phase 2 loopback | Final loopback | Phase 2 controlled profile | Final controlled profile |
|---|---:|---:|---:|---:|
| Selection to first send | 0.492 s | 0.386 s | 0.743 s | 0.834 s |
| Binary transfer incl. ACK | 1.622 s | 1.904 s | 61.222 s | 53.522 s |
| Finalisation | 0.185 s | 0.185 s | 0.757 s | 0.742 s |
| Selection to Uploaded | 2.311 s | 2.482 s | 62.739 s | 55.106 s |
| Effective transfer | 116.345 MiB/s | 99.108 MiB/s | 3.081 MiB/s | 3.525 MiB/s |
| HTTP chunks | 24 | 24 | 24 | 24 |
| Ordered provider appends/checkpoints | 24 | 48 | 24 | 48 |
| Peak sampled Python-process RSS | 89.75 MiB | 88.99 MiB | 90.99 MiB | 89.75 MiB |
| Python-process RSS growth | 9.25 MiB | 9.13 MiB | 9.70 MiB | 8.79 MiB |
| Peak sampled Chromium RSS sum | 313.37 MiB | 311.97 MiB | 321.95 MiB | 321.19 MiB |
| Main-thread tasks over 50 ms | 0 | 0 | 0 | 0 |

There is a **0.28-second loopback transfer regression** from additional framing,
checkpoints and admission/SQL safeguards when there is no storage/network delay to
hide. The intended latency profile saves 7.70 seconds; the change is retained for
that useful result rather than claiming every connection gets faster. Final hash
checks remain unchanged; no optimisation claim is made for startup/finalisation.

Controlled-stage totals explain the gain: browser reception remains approximately
40.3 → 40.2 seconds (ideal payload time at 40 Mbps is 39.56 seconds). Aggregate
provider time increases 20.30 → 24.73 seconds due to smaller appends, but now overlaps
reception; elapsed chunk service time decreases 60.83 → 53.23 seconds. Do not add
nested/overlapping Server-Timing durations. Validation/SQL remainder is approximately
0.216 → 0.369 seconds in this fixture. Both the extra checkpoints and their cost
are visible, rather than labelled an increase in connection bandwidth.

Memory samples run independently every 25 ms. Python RSS includes the isolated
server/test runner, excludes the Node SQL child; browser RSS sums Chromium processes.
Short transient peaks can be missed. The storage double does not reproduce TLS or
all SDK allocations. An actual-adapter test verifies the bounded immutable copy and
byte integrity. Global admission lock identities/lifetimes are tested with independent
connection doubles, alongside real disposable SQL service tests; native multi-worker
Postgres failover/concurrency and concurrent real Dropbox memory were not benchmarked.

Raw evidence retained in `output/product-upload-phase2`:
`phase2_baseline-browser.json`, `final-browser.json`, `final-comparison.json`,
`relay-before-transaction-timeouts-browser.json`, and the baseline runtime snapshots.

## Focused checks and finish

**133 tests and 56 subtests passed**, covering the changed relay plus existing
intake, browser recovery, handoff/deduplication, modes, mockups, colour validation
and shared Dropbox adapter. No new regressions remain. Tests explicitly cover:

- Reception overlaps one ordered writer; full storage hash matches original bytes.
- One queued frame, two frame permits, global two-upload and per-intake admission;
  capacity and unsettled writes fail closed without another provider append.
- Lost HTTP/provider ACK, cancellation, checkpoint failure and fresh-service resume.
- Legacy 8 MiB provider acceptance before a lost checkpoint; no duplicate bytes/jobs.
- Exact identity, altered retry blocks, size/alignment, old/new client compatibility.
- Real Chromium reload stays empty, explicit re-selection resumes, finish ACK loss
  finalises exactly once, and upload creates no unintended worker job.
- Virtual-clock deadline measurements: a 325-second progressing request completes
  without retry; a 60-second stall after progress reconciles before 4 MiB fallback;
  15-minute cap, busy reconciliation and six-attempt bounds remain in force.
- SDK clone shares pool/path-root and leaves shared defaults unchanged; retry limits
  and payload identity are verified without a provider request.

`node tests/test_product_upload_state.cjs` passed. The existing benchmark passed for
both versions/profiles, followed by the final timeout-safeguarded run. Known
Starlette/httpx and WebSockets deprecation warnings are unrelated.

Python command:
`python -m pytest -q tests/test_product_upload_relay.py tests/test_product_upload_intake.py tests/test_product_upload_browser_transport.py tests/test_product_upload_handoff.py tests/test_product_upload_modes.py tests/test_product_upload_mockups.py tests/test_mockup_upload_validation.py tests/test_dropbox_integration.py`

Benchmark uses the existing PGlite and explicitly NON_PRODUCTION PSD environment
settings, with `PHASE2_BENCH_MODE=phase2_baseline` or `final`.

Files changed for this completion:
`components/product_uploads/app.js`, `product_upload_api.py`, `product_upload_intake.py`,
new `product_upload_relay.py`, `product_upload_services.py`, `dropbox_integration.py`,
`tests/test_product_upload_relay.py`, `tests/test_product_upload_intake.py`,
`tests/test_product_upload_browser_transport.py`, `tests/test_product_upload_state.cjs`,
`tests/benchmark_product_upload_browser.py`, and this report. Prior local changes
remain present. No dependencies, infrastructure, deployment config or dashboards added.

The remaining limit is browser bandwidth plus provider acceptance and the durable
end-of-request tail. Actual internet/provider/DB connection latency, proxy buffering,
and production concurrency remain unmeasured. A buffering reverse proxy may reduce
overlap. Very slow links can still reach the finite cap and show Interrupted with
File retained. This is a completed local implementation, not a real Dropbox speed
claim or release authorisation. No commit, push, merge, deployment or production
mutation occurred.

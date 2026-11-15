# Product Uploads PSD transfer — local implementation evidence

18 October 2026. Status: Implemented locally. Not committed, pushed or deployed.

## Workspace and scope

First command was `git worktree list` in
`C:/Users/hello/Documents/sports-cave-image-factory`. Existing task
`20261018-4b18037e`, owner `codex-products-mockups-20261018`, was the matching
Product Uploads worktree. Verified its root, branch
`codex/task/products-product-uploads-integrated-existing-mockup-20261018-4b18037e`,
and clean starting tree at `5af8499eda5cb2b67f910813280818ea5fa7a7e9`.
The earlier Mockups task and category worktrees were preserved. Continued this
existing task under the user's explicit instruction; no worktree was created.
Studio history records this continuation separately from its prior release.

## Diagnosis: confirmed defects and limits of the evidence

The old UI unconditionally displayed “Reselect the same PSD to resume” after
every acknowledgement, including during a healthy active transfer. It was not
an interruption detector. Transfer and storage acknowledgement times were not
visible. The old loop retried a failing chunk only three times, then cleared the
input without retaining an accessible retry action. Retrying required another
selection and another full identity pass. Start and finish lacked retries, and
fetch requests had no application deadline. A transient FilesUploadError with a
503 status was incorrectly rewritten as permanent HTTP 409 by this API.

A controlled regression test reproduces the apparent 4 MiB stop in the original
code: allow chunk one, then fail the next four requests with 503. The old loop
stops at 4 MiB after three failed attempts and displays the reselect message.
The changed loop completes the identical scenario automatically, with one
identity pass and the same upload ID/offset. This demonstrates a concrete
failure mode, not proof that these were the original incident's failures.

There is no unconditional stop after the first chunk in the original loop.
Incremental framing and hashing passed an actual local non-production layered
188.7 MiB PSD, and a synthetic 272.7 MiB framing fixture passes all 69 chunks.
The initially suspected section-skip validator problem was ruled out and that
validator was not changed. No compositing, native Photoshop work or mockup
generation occurs in the chunk route. Processing is downstream of verified
storage and explicit image-generation/Shopify handoffs.

The original 272.7 MiB file, its browser/network traces and production request
logs were not available in this local task. Therefore the historical transfer's
underlying network, proxy, provider or authentication outage is undetermined.
No assertion is made that its connection bandwidth or storage was slow.

## Implementation

- Retain the original browser File while this page is open. Retry start, chunks
  and finalisation on transient network errors and HTTP 408/425/429/500/502/503/504.
  Six attempts per operation, exponential waits of 0.75/1.5/3/6/12 seconds,
  Retry-After capped at 30 seconds, and a 180-second request deadline.
- Exhaustion shows Interrupted and Retry upload with the retained File. A later
  online event can restart a transiently interrupted transfer automatically.
  Permanent validation/permission failures are not automatically retried.
- Every retry uses the same intake ID and chunk offset. Existing locked
  acknowledgements, per-block digests, deterministic storage destination,
  final storage hash and worker deduplication remain authoritative. No full-file
  restart, parallel appends, new upload platform or direct-upload credentials.
- Keep 4 MiB sequential binary chunks: this matches existing Dropbox hash blocks
  and persisted offsets. No measured proxy bottleneck justifies a protocol or
  infrastructure change. There is no sleep/poll/Streamlit value event between
  successful chunks. Height events are deduplicated; visibility changes do not
  emit value events while busy.
- Keep one bounded identity pass for a newly selected File, required by the
  existing exact-content resume protocol. Cache its small hash on the retained
  File so retries do not reread the entire PSD. Explicit re-selection after a
  reload always performs identity validation again. No PSD parsing/compositing,
  base64, recompression, flattening or whole-file buffers were introduced.
- Browser bytes sent are separate from durable bytes saved. Percentage, effective
  confirmed-byte speed and ETA exclude previously saved resume bytes. Uploading,
  Retrying, Interrupted and Processing are distinct. While storage acknowledgement
  is pending, the UI says so instead of counting those bytes as saved.
- Store only ID/name/size/hash as tab-scoped resumable metadata, separately from
  visible selection. Fresh pages do not fetch the latest intake or restore a
  preview. Only explicit selection plus full identity equality reuses its ID.
  Start another upload/Remove explicitly clear that metadata. Browser storage
  denial is tolerated; it limits reload recovery, not current-page retry.
- Keep all existing layout markup, manual features, mockup integration, separate
  Mockups page, RGB8/colour-policy/native validation and 1 GiB limit.
- Record native queued/claimed/completed/failed timestamps in existing render
  checkpoints, once per transition. Duplicate requests preserve timestamps and
  worker ownership; they do not enqueue or render twice.

## Timing interpretation

`window.productUploadMetrics` contains bounded lists (100 entries each) of
identity and request timings without tokens or artwork. Chunk metrics include
browser-reported send duration and total acknowledgement duration. Failed network
requests record timeout/network status. Browser upload progress is browser-reported
transport progress; it is not proof of durable storage.

Authenticated responses expose Server-Timing and structured timing logs:
`auth`, `receive` (ASGI body reception), `adapter`, `storage`, `intake`, `checks_db`
and `total`. Storage is nested within intake; checks_db is intake minus storage
and includes validation, hashing, SQL, lock wait and commit. Do not sum nested
metrics or treat proxy buffering/ASGI reception as pure link bandwidth. Start and
finish expose operation/storage durations; resolve/link expose handoff durations
including existing verification/queue work. Native checkpoint times separate queue
wait from claimed-to-completion processing, which includes host transfer/output
verification. The upload route does not perform that processing.

## Measured before/after

Reproducible opt-in benchmark: `tests/benchmark_product_upload_transfer.py`.
Baseline modules are read from Git `5af8499e` without resetting files. Both modes
use the identical non-production PSD, real disposable PGlite PostgreSQL, isolated
Uvicorn routes over loopback HTTP, and a disk storage double. No app.py startup,
production credentials, real Dropbox writes, live customer data or worker launch.
The input is an existing NON_PRODUCTION native acceptance fixture, read only.

Fixture: 197,816,894 bytes / 188.6529 MiB, 48 chunks. Dropbox content hash:
`f1e90d6ef5f8f6083a0577c3846aec472050283c126a5a30cc8ccae4aa799c56`.
Warm filesystem; two interleaved runs per version; Python 3.14 local environment.
Raw results: `output/product-upload-transfer/benchmark.json` (local ignored output).

| Measurement | Before | After |
|---|---:|---:|
| Binary transfer time | 1.188 / 1.245 s | 1.144 / 1.029 s |
| Effective loopback transfer | 158.7 / 151.6 MiB/s | 164.9 / 183.3 MiB/s |
| Local storage writes during transfer | 0.077 / 0.080 s | 0.081 / 0.058 s |
| Finalisation / storage identity verification | 0.152 / 0.169 s | 0.144 / 0.189 s |
| Peak Python transfer allocations | 8.97 / 9.04 MiB | 9.00 / 8.91 MiB |
| Sampled process working set | 82.81 / 82.14 MiB | 82.04 / 82.24 MiB |
| Working-set growth | 11.00 / 8.61 MiB | 8.52 / 9.12 MiB |

Python local identity hashing alone took 0.142 s; that is not browser timing.
Changed-route body reception totalled 0.509 / 0.478 s, storage 0.081 / 0.058 s,
and validation/SQL/lock/commit remainder 0.358 / 0.312 s across 48 chunks. No one
local stage explains a minutes-long stall. Differences between the two versions
are small, noisy local measurements; no internet speedup is claimed. The useful
measured improvement is successful automatic recovery under an identical fault
pattern, plus no repeated hash pass on retained-file retry.

Memory includes the isolated Python client/server and excludes PGlite's Node
child. The first attempted TestClient memory measurement retained test-client
objects and was discarded; the reported benchmark uses real loopback HTTP.
Disk writes use the OS cache, not a cloud durability/bandwidth model.

Unmeasured: original 272.7 MiB incident, actual browser memory/throughput, internet
and real Dropbox latency/bandwidth, native processing time and live worker handoff.
Native queued/processing timestamps are implemented and tested with doubles; no
native processing benchmark was executed for this upload task. Actual speed
remains bounded by the slower browser uplink, proxy path and storage acceptance.
After six failed attempts the user may need Retry upload; after a reload the
browser File reference is lost and explicit selection is needed. Expired provider
sessions require Start another upload. Background-tab suspension is browser policy.

## Tests and changed files

- `components/product_uploads/app.js`: retained File, bounded retries/deadlines,
  progress, independent resumable metadata, bounded metrics, reduced events.
- `product_upload_api.py`: timing headers/logs and transient HTTP status handling.
- `product_upload_render.py`: separate native queue and processing timestamps.
- `tests/test_product_upload_state.cjs`: fresh state, stale completion, clipboard,
  identity mismatch, resume ID reuse, lost ACK, timeout, permanent failures,
  4 MiB continuation, controlled old/new failure comparison.
- `tests/test_product_upload_intake.py`: timing/status/memory bound contracts,
  synthetic 272.7 MiB layered framing; existing integrity/dedup/limit coverage.
- `tests/test_product_upload_mockups.py`: checkpoint ordering/idempotence tests.
- `tests/benchmark_product_upload_transfer.py`: opt-in offline comparison above.
- This report.

Focused suite command:
`python -m pytest -q tests/test_product_upload_intake.py tests/test_product_upload_mockups.py tests/test_product_upload_handoff.py tests/test_product_upload_modes.py tests/test_mockup_upload_validation.py`
Result: 77 passed, 48 subtests passed. The render tests were rerun after adding
timestamps. `node tests/test_product_upload_state.cjs`, Python AST syntax checks,
Studio Verify and `git diff --check` passed. Benchmark: 1 passed. Existing
Starlette/httpx and Uvicorn/WebSockets deprecation warnings are unrelated.

Set AUTO_EDITIONS_TEST_PGLITE to the installed PGlite dist/index.js for the SQL
suite. For the benchmark also set PRODUCT_UPLOAD_BENCHMARK_PSD to an explicitly
non-production PSD and run `python -m pytest -q -s tests/benchmark_product_upload_transfer.py`.
No commits, pushes, deployments, main changes or production mutations occurred.

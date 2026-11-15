# Product Uploads Phase 2 — measured local speed optimisation

Status: Implemented locally. Not committed, pushed or deployed.
18 October 2026. Continuation of PRODUCTS task `20261018-4b18037e`, owner
`codex-products-mockups-20261018`, branch
`codex/task/products-product-uploads-integrated-existing-mockup-20261018-4b18037e`.

## Result and measurement boundary

The same 188.65 MiB non-production layered PSD uploaded in a real Chromium
browser under controlled network conditions in **65.83 s with Phase 1 and
61.02 s with Phase 2: 4.81 s / 7.3% less transfer time**. HTTP chunk requests,
storage append calls, account checks and intake transactions fell from 48 to 24.
No original artwork bytes or PSD processing behaviour changed.

This is an actual browser-to-isolated-local-server measurement with **simulated
bandwidth/latency and a local storage double**. Real browser-to-Dropbox internet
improvement has **not** been measured. No provider credentials, production
writes, live customer data, native workers or full application server were used.
The original 272.7 MiB incident file remains unmeasured. These results must not
be presented as production internet upload speed.

## Preservation and baseline

First ran `git worktree list` in
`C:/Users/hello/Documents/sports-cave-image-factory`, then read
`docs/PRODUCT_UPLOAD_TRANSFER_LOCAL.md`. Verified the existing Windows worktree
root, branch, task owner and all nine Phase 1 changed/untracked files. Preserved
an exact local snapshot and SHA-256 manifest under ignored
`output/product-upload-phase2/phase1` before changing code. No worktree or branch
was created. Existing Phase 1 render timestamps, mockup tests and evidence report
remain byte-identical to that snapshot. Other unfinished work was preserved.

The comparison baseline is the uncommitted **Phase 1 implementation**, not Git
HEAD (which predates Phase 1). Its browser script, API and intake were loaded
from that snapshot. A disposable PGlite database and a loopback-only Uvicorn app
serve only isolated test routes, with account lookup and storage explicitly
replaced. `app.py`, production launchers and schedulers are never started.

## Diagnosis and choice

Phase 1 already used bounded binary data and a cached Dropbox Team Space client.
Inspection of the installed SDK confirms that the client owns a reusable
requests connection pool. Per-request adapter construction accesses the existing
cached auth/context/client rather than setting up a new connection every time.
Caching permissions or bypassing validation would be unsafe and is unnecessary.

The actual shared adapter accepts **8 MiB appends**, but Product Uploads restricted
each HTTP body, provider append and intake transaction to one 4 MiB hash block.
Each successful chunk waited for browser transfer, provider acceptance and DB
commit before the next one began. Hash block size is not the transport limit.

In the controlled latency profile, Phase 1 measured:

- Initial browser identity hashing: 343 ms. No main-thread task exceeded 50 ms;
  maximum animation-frame gap was 16.8 ms. A hash worker is not justified here.
- Aggregate ASGI body reception: 40.31 s. The ideal 40 Mbps payload time is
  39.56 s: this leg is already close to its configured bandwidth limit.
- Provider time: 24.56 s, including a modelled 100 Mbps storage transfer plus
  180 ms fixed delay per storage call. This is separate from browser transfer.
- Validation/hash/SQL/lock/commit remainder: 0.305 s across 48 chunks.
- Transfer including acknowledgements: 65.83 s; finalisation: 0.765 s.

The chosen change combines **two stable 4 MiB hash blocks into one 8 MiB ordered
transport request**. It halves fixed append and transaction costs without adding
parallel appends, a queue, background browser upload service or another platform.
Larger bodies than the adapter supports, speculative/direct provider uploads and
relay concurrency would add protocol/recovery complexity without real-provider
measurement to justify them. The server still buffers at most one bounded body;
it does not allocate, decode, flatten, recompress or base64-encode a full PSD.

The performance target was set after the Phase 1 baseline and before changing
the implementation: save at least six seconds in the latency profile, with bounded
memory and unchanged integrity. The initial estimate was 24 fewer requests times
(160 + 180) ms = 8.16 s of fixed waiting, with margin. **The six-second target was
not met.** Actual Server-Timing shows that CDP browser latency substantially
overlaps body transmission. Provider time fell by 4.28 s, close to the 4.32 s
expected from eliminating 24 fixed 180 ms append waits. Browser reception stayed
40.22 s. The actual 4.81 s reduction is supported by the stage measurements;
there is no claim that browser uplink bandwidth increased.

## Implementation and compatibility

Runtime changes relative to Phase 1:

- `product_upload_intake.py`: add an 8 MiB transport cap; retain `CHUNK=4 MiB`
  for content identity and existing durable offset/hash format. Hash each bounded
  memoryview block separately. Accept 4 or 8 MiB aligned non-final bodies and
  bounded final partial bodies. Validate every block in duplicate replay ranges;
  reject altered second blocks, oversize, misalignment and unconfirmed overlaps.
- `product_upload_api.py`: enforce the 8 MiB request cap using the existing
  bounded binary stream collector. Phase 1 auth, timing, retryable status and
  storage verification paths are preserved.
- `components/product_uploads/app.js`: use `transport_chunk_bytes` from each
  authoritative response, capped to the recognised 8 MiB capability; otherwise
  send 4 MiB. Continue one request at a time. Keep the Phase 1 hash cache,
  selection, timers, retained File, retries, progress and independent resume data.

`public()` advertises transport capacity without changing saved session data.
An existing intake at 4 MiB can continue with 8 MiB and retain exactly the same
Dropbox content hash. Old browsers can continue sending 4 MiB to the new server;
new browsers fall back to 4 MiB against an older server. No migration, silent
session discard or hash identity version change is needed. A lost 8 MiB provider
ACK is retried with the same offset and complete body; existing provider-offset
reconciliation and the final independent content-hash check remain authoritative.

The original PSD layers, profiles, RGB8 validation, colour safeguards and 1 GiB
limit remain unchanged. No HTML/layout markup, manual tools, integrated Mockups,
separate Mockups page, worker dispatch or native render implementation changed.
Fresh pages remain empty; only explicit re-selection with validated full identity
may resume saved bytes. The 180-second request deadlines and bounded retry policy
remain in place. On extremely slow links an 8 MiB request can reach that deadline;
real link-specific adaptation has not been measured or introduced.

## Before/after measurements

Read-only input: existing `SC3284-NON_PRODUCTION-INPUT.psd` native acceptance
fixture, 197,816,894 bytes / 188.652891 MiB. Dropbox content hash:
`f1e90d6ef5f8f6083a0577c3846aec472050283c126a5a30cc8ccae4aa799c56`.
Same file, Chromium 153.0.8010.12, machine, page, routes, SQL and storage double.
One run per version/profile; differences in short loopback/startup timings are
not statistically established improvements.

Latency profile: Chromium CDP upload throughput 40,000,000 bits/s and latency
160 ms; download allowance 100,000,000 bytes/s; storage double adds 180 ms per
call plus content bytes at 100,000,000 bits/s for each append. OS-cached disk
writes implement storage. Chromium network delay can overlap upload transmission;
these inputs are not additive measured WAN round-trip times. Loopback profile
has no artificial bandwidth limit or provider delay.

| Measurement | Phase 1 loopback | Phase 2 loopback | Phase 1 latency profile | Phase 2 latency profile |
|---|---:|---:|---:|---:|
| Selection to first server body byte (separate startup run) | 0.334 s | 0.333 s | 0.713 s | 0.729 s |
| Selection to first binary request | 0.564 s | 0.345 s | 0.738 s | 0.725 s |
| Initial browser identity hashing | 0.517 s | 0.303 s | 0.343 s | 0.331 s |
| Binary transfer including ACKs | 1.806 s | 1.609 s | 65.834 s | 61.023 s |
| Finalisation | 0.211 s | 0.178 s | 0.765 s | 0.778 s |
| Selection to Uploaded | 2.595 s | 2.134 s | 67.347 s | 62.530 s |
| Effective transfer throughput | 104.44 MiB/s | 117.26 MiB/s | 2.866 MiB/s | 3.091 MiB/s |
| Chunk requests / provider appends | 48 / 48 | 24 / 24 | 48 / 48 | 24 / 24 |
| HTTP requests for upload incl. start/finish | 50 | 26 | 50 | 26 |
| Peak sampled Python-process RSS | 90.96 MiB | 89.84 MiB | 89.70 MiB | 90.35 MiB |
| Python-process RSS growth | 10.81 MiB | 10.02 MiB | 6.28 MiB | 9.97 MiB |
| Peak sampled Chromium-process RSS sum | 312.76 MiB | 311.82 MiB | 323.09 MiB | 321.03 MiB |
| Main-thread tasks over 50 ms | 0 | 0 | 0 | 0 |

Peak RSS samples were collected independently every 25 ms. Python RSS includes
the isolated server and Python test runner, excludes the PGlite child; browser
RSS sums the Chromium processes, not just JavaScript heap. Short-lived allocation
peaks can be missed. The disk double does not reproduce the SDK's immutable body
copy: a separate test calls the **actual existing storage wrapper** with an
8 MiB bytearray and fake SDK transport, proves the immutable bytes are unchanged,
and verifies its additional allocation remains below 12 MiB. Real provider SDK,
TLS, proxy and concurrent-user memory were not benchmarked. No full PSD buffer
is created by the runtime implementation.

Raw local evidence (ignored output, retained for review):

- `output/product-upload-phase2/phase1/manifest.json` and original Phase 1 files.
- `output/product-upload-phase2/phase1-browser.json`.
- `output/product-upload-phase2/phase2-browser.json`.
- `output/product-upload-phase2/phase1-startup.json` and `phase2-startup.json`
  (independent selection-to-first-server-body-byte checks, same profiles and file).
- `output/product-upload-phase2/comparison.json` (stage totals and differences).

The startup-only runs timestamp the first non-empty ASGI binary body event against
the browser's wall-clock selection time on the same Windows host, then close the
page. They measure actual server body arrival, rather than equating XHR.send with
first-byte receipt. They are separate runs, not extra samples in the full-transfer
measurements; differences of tens of milliseconds do not establish startup gains.

Browser metrics and Server-Timing are those already implemented in Phase 1;
benchmark instrumentation records request send/ACK times, browser long tasks,
animation frames and independent process memory. Processing/native rendering was
not invoked, so finalisation time must not be labelled PSD processing time.

## Focused validation

- Full focused suite: **80 passed, 48 subtests passed**, including the new actual
  Chromium lost-ACK/reload test, intake, handoff, modes, mockups and upload colour
  validation. Existing Starlette/httpx and WebSockets deprecation warnings only.
- Additional actual-adapter binary/memory contract: **1 passed**.
- `node tests/test_product_upload_state.cjs`: PASS, including negotiated 8 MiB,
  legacy fallback, exact offset retries, retained File/hash, timeout, identity
  mismatch, empty fresh page and controlled original 4 MiB stop comparison.
- Browser benchmark: one passing Phase 1 run and one passing Phase 2 run, each
  covering both profiles; source bytes verified by provider content hash. Two
  additional startup-only browser runs cover first-server-byte arrival.

The real Chromium recovery test lets the server commit the first 8 MiB, drops its
HTTP acknowledgement, verifies the same offset is replayed without another
provider append, then interrupts the next request. After reload it asserts an
empty file input/selection and no preview. Explicit re-selection recovers the same
intake/session at 8 MiB, a lost finish acknowledgement is retried, and exactly one
storage finalisation occurs. Original full-file identity matches and no worker
job is created by upload alone. Existing handoff tests prove repeated linking
still results in one product mapping/job. Backend tests also cover a legacy 4 MiB
confirmed offset followed by an 8 MiB append whose provider ACK is lost, differing
bytes in its second block, old-client replay, malformed size and partial overlap.

Commands (isolated environment with installed PGlite/Playwright):

```powershell
python -m pytest -q tests/test_product_upload_browser_transport.py tests/test_product_upload_intake.py tests/test_product_upload_mockups.py tests/test_product_upload_handoff.py tests/test_product_upload_modes.py tests/test_mockup_upload_validation.py
python -m pytest -q tests/test_product_upload_intake.py -k existing_storage_adapter
node tests/test_product_upload_state.cjs
# Set PRODUCT_UPLOAD_BENCHMARK_PSD to an explicitly non-production PSD.
# Set AUTO_EDITIONS_TEST_PGLITE to the installed PGlite dist/index.js.
$env:PHASE2_BENCH_MODE='phase1' # or 'phase2'
python -m pytest -q -s tests/benchmark_product_upload_browser.py
# Optional separate first-server-byte probe (closes the page at body arrival):
$env:PHASE2_BENCH_STARTUP_ONLY='1'
python -m pytest -q -s tests/benchmark_product_upload_browser.py
```

Additional changed testing/evidence files: `tests/test_product_upload_intake.py`,
`tests/test_product_upload_state.cjs`, new `tests/test_product_upload_browser_transport.py`,
new `tests/benchmark_product_upload_browser.py`, one additive `Client.base` field
in the Phase 1 local benchmark helper `tests/benchmark_product_upload_transfer.py`,
and this report. No new infrastructure/dependencies/dashboard/platform.

## Remaining limits

The measured improvement is real in the isolated Chromium experiment and its
network/storage model. It has not been verified against Dropbox over the
internet, real authentication DB latency, deployment proxy limits or production
concurrency. No credentials or remote writes were used to close that gap. A
future authorised provider test may expose bandwidth or proxy constraints that
this model cannot reproduce. Hashing already stayed responsive; startup delay
was not the meaningful bottleneck. Upload bandwidth is close to saturated on its
browser leg, while the serial relay still incurs a storage-transfer stage and
fixed storage acknowledgement waits. The six-second model target was missed;
its actual 4.81-second result is reported without changing the target after the
fact. No deployment or real-world speed guarantee is implied.

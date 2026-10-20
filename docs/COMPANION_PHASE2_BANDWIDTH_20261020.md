# Companion Phase 2: transfer controls and timing

Phase 3 continues this implementation locally; see
[durable upload/resume report](COMPANION_PHASE3_RESUMABLE_20261020.md).
The measurements and live limitations below remain the Phase 2 baseline.

Implemented locally on task `20261019-2a576331`, owner
`codex/companion-speed-20261020`. Phase 1 is preserved. No production upload,
recovery, companion replacement, startup change, commit, push, merge or deployment
was performed. Automatic backlog recovery remains unchanged and disabled.

Worktree:
`C:\Dev\SportsCaveWorktrees\sports-cave-integrations-companion-phase-1-processing-and-upload-sp-20261019-2a576331`

Branch:
`codex/task/integrations-companion-phase-1-processing-and-upload-sp-20261019-2a576331`

HEAD/base and installed companion remain
`dfe44257e207abe307560f21e64276990605b668`. Serving PID 29112 remained running.
Its installed normalized helper hash remains
`d49901dedeeec487bc98232cacb8c5e166533b3cd159c17d32b827953440cb69`.
The earlier SSD-recovery worktree and other tasks were not edited.

## Implemented behavior

- One lazily initialized, thread-safe aggregate upload controller, one active
  client upload, one reusable bulk HTTP Session shared only by that slot owner.
  Control requests use independent clients. Server provider concurrency stays 3.
- Manual Mbps converts using `Mbps * 1,000,000 / 8`. Balanced uses a supplied
  reliable sustainable rate minus configurable headroom (default 25%). Background
  uses a configurable fraction of Balanced (default 25%), selected by the user
  during working hours. There is no automatic working-hours schedule.
- Without a sustainable measurement, Balanced/Background show **Calibration
  needed** and prevent upload dispatch. Manual works without calibration.
  Maximum speed is an explicit uncapped choice with the same concurrency and
  integrity limits. Neither Phase 1's end-to-end rate nor Wi-Fi speed is capacity.
- The shared token bucket is capped at `min(16 KiB, max(1 KiB, rate * 0.1 s))`.
  Finite body reads are at most 16 KiB; the original bounded 1 MiB disk read-ahead
  is retained. Read-all/body-transforming adapters are rejected. HTTP Content-Length
  is explicit; redirects and implicit transport retries are disabled.
- Retries re-enter the same slot and budget. Existing transient-only bounded
  retry, exact-source reconnect and completed-receipt duplicate protection remain.
- Dynamic valid rate changes wake waiting readers and reset bucket credit.
  Settings persist atomically with fsync in the existing companion-owned
  `SportsCaveAutoEditions/transfer-settings.json` directory. This file has no
  credentials. Ordered audit revisions prevent delayed responses restoring an
  older cap. Calibration is supplied explicitly; no internet saturation test runs.
- **Pause after current transfer** blocks new upload/download dispatch and lets
  an active non-resumable transfer finish. Resume restores the selected settings.
  This never changes worker queue pause, enables recovery or regenerates artwork.
  No mid-file resumable protocol is advertised.
- Separate optional aggregate download allowance covers native preparation PSDs,
  pre-product render PSDs and the fixed edition-test PSD streaming path. It
  backpressures finite reads; TCP/TLS/OS receive buffering is outside application
  accounting. Downloads have a separate slot/budget and no upload protection
  claim is extended to browser uploads, Dropbox desktop sync or other devices.
- Existing independent heartbeats renew ownership while a worker is throttled
  or waiting. The same authenticated heartbeat can extend only an unexpired
  grant bound to its exact host, product and lease. Expired/superseded grants
  are not resurrected. Intentional waits do not consume the native watchdog;
  stuck native processing still has its existing recovery deadline. Socket
  inactivity and bounded retry limits remain separate.

Worker Health adds a compact mode/cap/apply/transfer-pause bar, expandable
calibration/headroom/download settings, payload progress, adequately sampled ETA,
and Uploading / Waiting for server verification / Cloud Ready labels. Cloud Ready
is taken only from the server's durable result. Requested settings remain distinct
until a later heartbeat acknowledges the exact persisted revision. Unsupported or
stale companions cannot falsely confirm protection. Existing polling, diagnostics,
queue controls and recovery controls are retained.

Settings use the existing administrator + same-origin `/api/worker-health/control`
endpoint, private audit records scoped to the registered companion instance, and
existing host claim/heartbeat responses. No public companion route, new monitoring
service, schema migration, privilege grant or provider setting was added. The
Supabase skill was used to review the existing private persistence/authentication
pattern; no Supabase API or schema was changed.

## Timing and the 288.020-second historical gap

Each job gets a correlation ID; each attempt gets a separate request ID. Timers
use monotonic clocks inside their own process. No client/server timestamps are
subtracted. Progress telemetry is a bounded scalar snapshot (maximum accepted
payload 4 KiB), with up to three local attempt records; no URLs, tickets, tokens,
credentials or bodies enter these records.

Client diagnostics now separate slot, pause, missing-calibration and intentional
allowance waits; request preparation; first/last body handoff; logical file reads;
response after last handoff; and client confirmation. Counters distinguish bytes
returned by the file reader, handed to the HTTP transport, and acknowledged by
the correlated server receipt. They are **application payload counters, not wire
bytes or internet capacity**. File read-ahead/physical disk I/O is separate.

Server diagnostics cover handler entry through authentication/context, first body,
body receive, validation, provider publication, source revalidation, registry save,
durable checkpoint work, technical verification, temporary-directory cleanup,
final durable status lookup and full handler duration. Existing cumulative timers
remain; they overlap the detailed timers and must not be added to them. The
`database_save_seconds` field is now separated from source revalidation, which
was included in that field previously.

Code inspection establishes that the old 105.177-second server timer already
started **before** `grant_context`, so authentication inside that package handler
was included. It ended before temporary-directory cleanup and the final status
lookup. Those previously uncovered operations now have explicit timers. The old
`requests.post(data=file)` path was streamed by the stock adapter, not deliberately
read into one complete client request body. New finite-read/adapter checks enforce
that contract. Requests/urllib3 do not expose independent DNS/TCP/TLS completion
milestones through this interface; `connection_seconds` is explicitly unknown.

The historical **288.020 s remains unattributed**. There is no retained evidence
that can assign it to sending, proxy/ingress buffering, connection handling, the
old timer's uncovered tail, or response transit. A residual client timer explicitly
retains transport plus response uncertainty; it is not labelled pure network time.
Production ingress/proxy measurements require an authorised instrumentation release.
This phase does not return an early response or weaken any verification gate.

## Controlled measurements

Evidence: `output/companion-phase2/measurements-bounded.json`. Loopback only,
warm/first-observed caches, unchanged Phase 1 Dale Earnhardt fixture, no Photoshop
run or external provider request. The exact retained source, template/settings,
all images and the original PSD were hashed before and after. The existing
exact-source colour approval was copied unchanged into task-local evidence and
validated; no policy was invented or relaxed.

Full package: **209,149,198 bytes**, SHA-256 in the report, 105 logical members.
It uses existing transport version 0 because this fixture's references do not meet
the existing compact-delta threshold. Package contents/encoding are unchanged.
Six full loopback transfers (three pairs) each used one attempt, zero retries and
the exact receiver SHA-256. This is not a Steve Smith upload or live asset replay.
The receiver imposed the same explicit 100 ms response-processing wait in both
conditions. No production ingress or household network capacity was simulated.

| Comparable local request measure | Before | After | Interpretation |
| --- | ---: | ---: | --- |
| Median wall time, three alternating pairs | 0.768489 s | 0.697096 s | Observed -0.071394 s / -9.29%; inconsistent across pairs |
| Mean wall time | 0.712415 s | 0.721925 s | +0.009510 s / +1.33% |
| Wall range | 0.588755–0.780001 s | 0.671869–0.796811 s | Two of three candidate pairs were slower |
| Median process CPU | 0.8125 s | 0.7500 s | Local receiver and sender share one process |
| Connections for three successive transfers | 3 | 1 | Two connections avoided; 66.7% fewer |
| Received payload per request | 209,149,198 B | 209,149,198 B | Exact hash match; zero retries |

There is **no demonstrated repeatable upload wall-time improvement**. Connection
reuse removes redundant connection creation, but its live TLS/latency benefit is
unmeasured. The controller adds per-chunk accounting; the original bounded disk
read-ahead was retained after checking that cost. No speculative concurrency,
image or package change is retained to inflate a speed claim.

For the after requests, construction took 0.330–0.440 ms; first body handoff
1.144–1.682 ms after dispatch; final handoff 0.566–0.690 s; response after final
handoff 0.1009 s, consistent with this receiver's configured 100 ms wait.
Intentional rate waits were exactly zero in Maximum speed. These are nested
milestones, not additive stages or measured connection times.

| Aggregate cap experiment | Observed |
| --- | ---: |
| Explicit fixture cap / converted allowance | 1.048576 Mbps / 131,072 B/s |
| Two competing transfers, combined receiver payload | 524,288 B |
| Total including receiver waits | 4.122160 s |
| Effective application payload rate | 1.017502 Mbps; 2.96% below cap including server waits |
| Maximum observed 100 ms receive window | 19,456 B |
| Bucket maximum at that rate | 13,107.2 B; 100 ms allowance + burst is 26,214.4 B |
| Small control requests / maximum local response time | 38 / 3.0895 ms |
| Attempts / retries | 2 / 0; retry cases exercised separately |
| Process CPU / sampled peak RSS | 0.046875 s / 53,878,784 B |

The unchanged server unpack/ICC/hash/pixel verification passed in **8.529129 s**,
with all **105 reconstructed members byte-identical** and source fixture unchanged.
It was local verification, not cloud publication or a new Cloud Ready decision.
Physical/system I/O and background network counters are retained in the report;
they include unrelated processes and are not per-job wire counts. Real household
browsing responsiveness and sustained internet capacity remain **unverified**.

An exploratory report, `measurements.json`, used an excessively detailed receiver
history for full packages. The harness was corrected to bound full-package samples
to approximately 512 points. That exploratory run is retained for audit and is not
used for the comparison above. A first unpack attempt correctly refused missing
local approval configuration; the unchanged exact approval was supplied before
the successful run. No validation bypass was used.

## Verification and reproduction

Use the repository virtualenv Python and existing PGlite fixture module:

```powershell
$env:AUTO_EDITIONS_TEST_PGLITE='C:/Users/hello/Documents/sports-cave-image-factory/output/email-idle-pg/node_modules/@electric-sql/pglite/dist/index.js'
python -m pytest tests/test_companion_phase2_transfers.py tests/test_worker_health.py tests/test_worker_health_queue.py tests/test_auto_editions_preparation_host.py tests/test_auto_editions_template_preflight.py tests/test_auto_editions_onboarding_api.py tests/test_auto_editions_v17.py tests/test_companion_phase1_pixels.py tests/test_auto_editions_package.py tests/test_auto_editions_speed.py -q
node tests/test_companion_phase2_ui.cjs
node tests/test_worker_health_ui.cjs
python scripts/benchmark_companion_phase2.py --fixture output/companion-phase1/fixture --colour-policies output/companion-phase2/colour-policies.json --report output/companion-phase2/new-measurement.json
```

Set `NODE_PATH` to the bundled runtime's node_modules for UI tests. The real
queue browser test is launched by its pytest fixture; running its CJS entry point
alone requires `WORKER_QUEUE_FIXTURE`. An initial standalone invocation omitted
that variable; the correctly configured pytest browser fixture passed.

Focused receiver tests cover aggregate rate/burst enforcement, exact Mbps
conversion, active rate changes, settings persistence/order, pause after current,
separate source dispatch pause/download cap, retry budgeting, slow readers,
stalled request bodies, response inactivity classification, responsive control
traffic, singleton initialization, watchdog/lease/grant renewal, unsupported and
stale UI states, request correlation and server body timing. The original
recovery mocks now target `Session.send`; their retry/receipt assertions remain.
Existing Phase 1's three stale mocked-preflight colour-test failures remain
documented there and were not rewritten or claimed fixed.

The expanded package/Phase 1/queue/recovery/controls selection passed **132 tests**
(3 warnings, 102.78 s). Final controls/receiver/host/native-render coverage passed
**67 tests**, with one unrelated baseline test deselected (51.90 s). That test,
`test_shopify_draft_live_completion_and_export_gate`, also fails when the original
`HEAD:product_upload_render.py` is loaded: its synthetic product lacks the verified
edition limit required by existing registration. It was not changed or described
as passing. New and existing Worker Health browser suites passed at 1280 and
390 pixels; the SQL-backed queue browser fixture also passed. Compile checks and
`git diff --check` passed. Final receiver-only checks are recorded in Studio.
UI screenshots: `output/companion-phase2/worker-health-1280.png` and
`worker-health-390.png`. This phase adds no dependency or image-quality change.

## Files and release compatibility

- `companion_transfer.py`: aggregate streaming controller, settings persistence,
  pause, bounded accounting and reusable bulk session.
- `companion_transfer_control.py`: bounded settings/evidence, per-instance private
  audit command and capability validation.
- `scripts/studio/auto_editions_local.py`: package/retry integration, settings
  acknowledgement, diagnostic sidecars, heartbeat/progress/watchdog integration.
- `scripts/studio/product_upload_render_local.py`,
  `scripts/studio/edition_test_local.py`: corresponding bulk/source stream paths.
- `auto_editions_onboarding_api.py`: commands on existing responses and scoped
  live grant renewal alongside the existing lease heartbeat.
- `auto_editions_setup_api.py`, `product_upload_render.py`: correlated server
  receipt and handler stage timings, with all existing verification retained.
- `worker_health.py`, `worker_health_api.py`,
  `components/worker_health/index.html`: private command, bounded status and compact UI.
- `scripts/benchmark_companion_phase2.py`,
  `tests/test_companion_phase2_transfers.py`, `tests/test_companion_phase2_ui.cjs`:
  controlled evidence and regression tests.
- Existing tests updated: preparation host, template preflight, V17, Worker Health
  and `tests/test_product_upload_mockups.py` (only the transport boundary in the
  existing retained-render retry test). Phase 1 runtime/proof changes and its
  documentation remain preserved.

Release must include both new controller modules, the companion integrations and
the backend/UI changes. Roll out the reviewed backend before the companion:
old backends reject the added bounded health/control fields. Old companions keep
working against the new backend but correctly appear **unsupported** for controls.
Existing Worker Health telemetry must be enabled with its already-established
private heartbeat table; absent telemetry cannot acknowledge or authorize controls.
The local host settings file survives a release replacement. A first install
without a reliable rate waits for calibration/manual cap or explicit Maximum speed.
No settings file or capability was written into the live companion's directory
by this work. The reviewed source and installed runtime are intentionally different.

Phase 3 should add a genuinely resumable, receipt-bound chunk protocol, retaining
source/template/output revisions and immutable publication gates. After an
authorised release, use correlation evidence to locate the remaining proxy/ingress
interval, obtain a reliable sustained rate and measure real browsing latency under
the chosen cap. Keep one client upload until those observations justify anything
else. No live speed or reduced internet-interference claim is supported yet.

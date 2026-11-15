# Companion Phase 5 — bandwidth, recovery and everyday controls

**Implemented locally. Not committed, pushed, merged or deployed.** No Render
restart/settings write, installed-companion replacement, startup change, live
design retry, production provider upload or backlog recovery occurred.

20 October 2026. Task `20261020-06c0d1d1`, owner
`codex/companion-phase4-20261020`; Studio continuation in
`C:/Dev/SportsCaveWorktrees/sports-cave-integrations-companion-phase-4-local-processing-and-pac-20261020-06c0d1d1`,
branch `codex/task/integrations-companion-phase-4-local-processing-and-pac-20261020-06c0d1d1`.
Git and Studio `worktree_path`, task and owner agree. HEAD remains
`58569c66bf569586321da6abea0623c18691c504`. All uncommitted Phase 4 changes and
its retained measurements were preserved. The original Phase 1–3 task remains
Released and untouched. No new worktree, native Photoshop window or repeated
three-pair processing benchmark was needed.

Read/reused [Phase 4 evidence](COMPANION_PHASE4_PROCESSING_20261020.md): edition
preparation saved 28.287s / 20.15% with equivalent outputs and a ~730 MiB
Photoshop memory trade-off. Its memory fallback, processing/colour code and
generation fingerprint remain unchanged:
`5549059f61becba7e740d9943a7f500a0d02e717c2071b0624aea0d2fb3bdd42`.
Phase 5 does not claim an additional Photoshop or full-job speed gain.

## Working controls and calibration

`companion_bandwidth.py` adds a small policy used by the existing shared
`companion_transfer.Controller`. No extra service, worker, dashboard, transfer
slot, HTTP calibration endpoint or automatic speed-test loop.

- A qualifying capacity observation must be **uncapped for the whole request**,
  successful, at least 2 MiB, with at least two seconds of client streaming and
  independently reported server body reception. Receipt bytes/correlation must
  match; duration ratio must be 0.5–2. Disk reads must occupy under 2% of the
  streaming interval; intentional allowance waits over 0.01s reject it. Any
  settings epoch change rejects it. Buffered ingress, brief requests, absent
  server timing, failed attempts and capped progress cannot calibrate capacity.
- Minimum three observations; at most seven retained. Conservative client/server
  payload rate, three-sample median, hysteresis, maximum 5% upward steps and
  bounded 20% downward steps. This is an available **sustainable transfer
  estimate**, not a claim of raw line capacity or speed available to every app.
- Automatic calibration expires after 24 hours. An already admitted finite body
  keeps its bounded allowance through expiry; the next transfer requires fresh
  evidence or an explicit manual/supplied rate. Explicit settings changes win.
- Balanced reserves existing configurable headroom (default 25%); Background is
  a configurable fraction of Balanced (default 25%). Manual remains authoritative.
  Maximum remains uncapped and never waits for calibration.
- Existing claim/heartbeat requests provide control RTT observations without
  increasing poll frequency. Three idle samples establish a median. Three
  sustained loaded samples exceeding both 2.5× idle and idle+100ms can cut the
  allowance by 20%, no more often than every 30s, down to 25% of the selected
  calibrated allowance. Five healthy observations allow 5% recovery steps,
  at least 60s apart, never above the calibrated allowance. A lone slow response
  does not change the limit. Existing polling is normally 30s: evidence-based
  response therefore takes several ordinary polls, not subsecond WAN control.
- Loaded control RTT includes server work; it does **not** prove network
  congestion or establish capacity. Durable chunk ACK and server verification
  waits are excluded from loaded sampling. No feedback from an enforced cap
  is used to lower the capacity estimate.
- Settings and calibration persist atomically/fsynced in the existing settings
  file; ordered requested acknowledgements preserved. Idle RTT baseline is
  rebuilt after restart rather than trusting an old network path. Manual rate,
  Maximum selection, download allowance and pause state survive restart.
  A failed settings write neither acknowledges the revision nor changes the
  effective allowance/adaptive factor. Capability capture and settings epoch
  are sampled together under the existing lock.

The Phase 4 32ms / maximum 256 KiB burst allowance and 16 KiB streaming reader
remain. Uploads, retries and resumed chunks share one budget/one bulk slot.
Downloads retain their separate optional allowance. No cap applies to browser
uploads, Dropbox desktop sync, other applications or household devices.

Strict observability can reject ordinary transfers, especially behind buffering
ingress. Balanced then honestly shows **Calibration needed**, with a reliable
operator-supplied rate or Manual cap as the next step. It never quietly becomes
unlimited. An operator-supplied calibration is labelled separately from observed
calibration. No switch out of the owner's Maximum mode occurred.

## Recovery and the production acceptance gap

Reused Phase 3's 8 MiB chunks, durable PostgreSQL session/processing row,
provider-backed data, independent archive validation, publication receipts,
authentication, leases and generation checks. No new schema or production
migration. Added client validation for session ID, expected size, generation,
completion offset and completed preparation identity. A server position below
persisted confirmed progress fails closed; no replay of allegedly lost durable
bytes. Server-confirmed status is persisted immediately on restart. Existing
clients may omit the newly returned generation field, but the server still
independently validates it; mismatches, when supplied, are rejected.

Pause still finishes the current non-resumable request. Supported resumable
packages pause only after a complete, durably acknowledged chunk. Waiting for
that ACK is its own state, with no transfer ETA/speed or congestion inference.
Resume keeps the same session, packet and job. Existing fresh host/original lease,
account, source/mapping and fingerprint gates remain; expired/superseded grants
are not resurrected. No partial resumable upload falls back to a full legacy one.

Lost finalisation acknowledgement was tested through real HTTP: the restarted
client recognised the durable completed session without another chunk or
publication. Existing tests still cover chunk lost ACK, backend HTTP restart,
provider ACK/finish faults, repeated/concurrent finalisation, process crash
rollback, corrupt packets, expiry, partial publication and verified receipt reuse.
The SQL/provider fixture is isolated; it is not production provider acceptance.

Cleanup previously treated a preparation hash as enough to write the cloud
confirmation receipt. It now requires the explicit server **Cloud Ready** result.
Accepted uploads still verifying keep their packet and diagnostics. This may
retain more staging disk until confirmed recovery; it avoids a false Cloud Ready
receipt or premature deletion. Source originals, receipts and existing retained
packets are untouched. New summaries distinguish in-progress/recovering/failed,
uploaded-verifying and Cloud Ready without changing existing queue/retry controls.

New-session capability now requires all of:

1. Existing `COMPANION_RESUMABLE_UPLOADS_ENABLED=true`.
2. Existing durable worker `SPORTS_CAVE_AUTO_EDITIONS_V6=true`.
3. Explicit release acceptance marker
   `COMPANION_RESUMABLE_ACCEPTANCE=provider-postgres-retention-v1`.
4. `COMPANION_RESUMABLE_ACCEPTANCE_GENERATION` equal to the exact deployed
   generation fingerprint.
5. `COMPANION_RESUMABLE_ACCEPTANCE_EVIDENCE_SHA256` containing the reviewed
   acceptance report's SHA-256.

These are operator acceptance attestations, **not automatically proven by a flag
or arbitrary hash**. Default is closed. Local fixture markers are synthetic and
cannot satisfy the required real provider/native PostgreSQL/retention checks.
Unaccepted create requests fail before provider initialisation. Already accepted
compatible sessions retain authenticated status/chunk/finalisation/worker paths
for draining when the existing runtime flag permits them. Gate-off never deletes
rows or data. Legacy negotiated uploads remain available for new work.

Read-only production check at **20 October 2026, 15:22:56 AEDT**:

- Backend primary remains `2859b999f88229d85e6c1c0d9d14ccd5be07e8d0`, from
  the unrelated previous release; this task did not deploy anything.
- Existing uploads/status probe returned 403 `Registered preparation host
  required.` Deployed code checks the resumable flag before that authentication
  error, establishing that **the old flag is still enabled**. No storage or
  authorised job was reached. This does not establish provider acceptance.
- Durable upload table had zero sessions when checked read-only.
- Companion heartbeat: e91d5d6ee2e33b57ba3cfb066b11b8125d1d40f8, helper hash
  `8ed083cf5b3ed5a24951084425abd9075402fa12494577b9624206f8e759d253`, Idle,
  no processor lock/checkpoint, capability 2. Effective **Maximum speed**,
  unpaused, acknowledged `request_5670`; no calibration. Installed code untouched.

[Exact configuration correction](COMPANION_PHASE5_CONFIGURATION_CORRECTION_20261020.json)
is prepared: patch **only** the primary service's
`COMPANION_RESUMABLE_UPLOADS_ENABLED=false`, preserving every other setting and
the deployed commit. **Not applied**: the user explicitly prohibits a production
configuration restart in this phase. Recheck sessions/jobs immediately before a
future authorised correction. Do not strand an intervening accepted session or
deploy this local branch as a side effect. Leave acceptance attestations unset
until real acceptance passes. This supersedes Phase 4's pending configuration
question; no new permission was requested to finish local work.

## Worker Health and measurement path

Kept the existing compact Developer → Worker Health layout and authenticated
control endpoints. Mode choices Balanced / Background / Maximum / Manual;
Manual input appears when relevant. Capability 3 adds calibration/adaptation
evidence, while backend/UI continue accepting capability 1/2 evidence. Older
companions honestly lack adaptive calibration. Backend must release before a
capability-3 companion. Requested settings remain pending until the effective
revision is acknowledged; stale requests cannot overwrite newer ones.

Pause wording depends on the **active transport**, not merely installed code:
legacy/no active resumable request says Pause after current transfer. Active
resumable data says Pause at chunk boundary. Transferred/total and server-received
bytes remain distinct. Payload speed uses active streaming time; server verification
does not lower the displayed transfer average. ETA requires at least three
seconds/256 KiB and is suppressed during pause, ACK wait and verification.
Uploaded — verifying and Cloud Ready remain separate. Recent failures with a
specific next step, memory pressure, calibration waits, pause and old backlog
failure counts are distinguishable. No recovery or queue semantics were loosened.

Demonstrated instrumentation fixes:

- Legacy response previously omitted its already recorded body timing. It now
  returns correlated handler, first-body-to-complete streaming and first-body
  wait durations. Resumable body reception similarly times actual streaming.
  Buffered ingress cannot qualify just because waiting for a first body took a
  long time. Unknown connection/proxy timing remains unknown.
- Chunk allowance waits accumulate even on failed requests, rather than only
  successful responses. Private controller fields never enter health telemetry.
- `job-summary.json` uses the existing correlation ID and bounded counters for
  queue/claim, source/cache, preparation, transfer and server validation/publication.
  Written with existing diagnostics at stage/progress/final/failure boundaries.
  Queue wait stays null if not independently recorded; claim request RTT is not
  relabelled queue wait. Nested stages are not added. No cross-process clocks
  are subtracted. Application bytes are not raw wire traffic.
- **288.020 seconds remains unexplained.** It is not labelled internet time by
  subtraction. No new ingress or household traffic experiment attributes it.

`scripts/check_companion_responsiveness.py` provides one bounded loopback fixture
or offline analysis of at most 32 already authorised control observations. It
cannot initiate a WAN speed test. Future authorised measurement can record idle
and loaded existing-heartbeat timings alongside transfer-only counters, then run
this analysis. It reports control-path latency including server work; real
browsing responsiveness needs separate observation. No extra dashboard/poll loop.

## Focused evidence, measurements and limitations

Reused Phase 4's 200-test and real-package/output-equivalence evidence; no
Photoshop processing code changed in Phase 5 and no native comparisons repeated.

- Focused transfer/recovery/health/Phase 4 regression subset: **87 passed**,
  81.47s, three dependency deprecation warnings, no skips/failures. Includes new
  policy, receiver, memory fallback, source/ICC preservation and Phase 3 faults.
- After strengthening acceptance to bind the report/generation: **12 passed**,
  24 intentionally deselected, 20.29s (acceptance, restart/ACK, pause and
  verification boundaries). Synthetic acceptance fields were updated in fixtures.
- Following summary/cleanup integration: **29 passed**, 36 intentionally
  deselected, 23.25s (journal, cancellation, leases/heartbeats, upload receipts,
  cleanup and summary boundaries). Counts overlap; they are not 128 unique tests.
- Final persistence/allowance boundary check: **11 passed**, 17 intentionally
  deselected, 4.44s, including failed-write atomicity and unchanged Manual mode.
  Five final summary/acceptance/expiry checks also passed after integration.
- Phase 5 and existing Phase 3 headless UI checks pass at 1280px and 390px:
  capability handling, Maximum preservation, requested/effective, pause/resume,
  hidden stale ETA, verification, memory next step and old backlog distinction.
- Topology validation, diff whitespace and Studio static/syntax/secret checks
  recorded with this task. No broad unrelated suite or provider write.

Initial focused integration exposed capability-3 acknowledgements being ignored
by an additional host-health compatibility check; fixed, tested. A float-exact
fixture assertion was corrected. Later boundary checks caught a mock response
without a numeric HTTP code and cleanup fixtures missing the newly required
Cloud Ready status: unknown HTTP code now cannot calibrate, and positive receipt
fixtures explicitly supply Cloud Ready. Negative unverified-completion tests
still assert packet retention. These failures were resolved, not excluded.
Earlier Phase 4 baseline exclusions were not rerun or weakened. No unresolved new
focused test failure remains.

Measured local functionality (not improved household throughput):

| Check | Observation |
|---|---|
| Real uncapped, receiver-paced calibration | Three 8 MiB requests, 25,165,824 application bytes; 15.4072, 15.4376, 15.4184 Mbps; estimate 15.4184 Mbps. Owner mode stayed Maximum; persisted calibration restored. Explicit local fixture, not internet capacity. |
| Simulated sustained latency → actual limited receiver | Balanced requested 16 Mbps, reduced to 12.8; 4,194,304 application bytes in 2.6252s, 12.7817 Mbps observed; 2.5906s allowance wait; 51,200-byte bounded burst. |
| Same fixture control latency | 3 idle / 10 loaded observations; median 1.328 / 1.763ms, maximum 3.641 / 1.898ms. Separate control requests remained responsive locally. |
| Lost finalise acknowledgement/restart | 3,005-byte complete validation fixture; 0 resent bytes, no duplicate publication through isolated SQL/provider/HTTP path. |
| Capped capacity feedback | Capped transfers add zero calibration samples; Manual rate survives adaptation and restart. |

Normal successful transfer request count/payload encoding/concurrency are unchanged;
timing headers and small bounded JSON/fsync work add overhead, not a claimed
speed improvement. Metadata lists hold at most seven capacity, seven idle and
five loaded observations. Existing 4 KiB health evidence, three retained transfer
traces, small totals and one per-job summary keep diagnostics bounded; settings
file admission is capped at 16 KiB. No new full-body buffering or Photoshop memory
allocation. Retaining accepted-but-unverified packets can use more staging disk.

Native PostgreSQL executables/service were unavailable locally. The existing
PGlite fixture executes PostgreSQL SQL and transactions with an isolated fsynced
provider, but serialises connections; it **cannot prove multi-process row-lock
contention, native DB restart/fsync behaviour or real-provider upload-session
durability/permissions/retention**. Those exact dependencies remain acceptance
requirements, not local implementation blockers. No new migration was needed.
Real ingress, loaded household browsing and Dropbox sync staging traffic remain
unmeasured. Local tests cannot establish reduced internet interference.

Evidence retained under this worktree's ignored `output/companion-phase5/`:
`final-tests.log/xml`, `acceptance-tests.log/xml`, `worker-boundaries-final.log`,
`ui-phase5.log`, `ui-phase3.log`, desktop/narrow screenshots,
`responsiveness.json`, `production-flag-readonly.json`. XML properties retain
calibration and lost-finalisation byte results. Earlier failed runs remain for
audit. Phase 4 fixtures, packets, approvals, journals and reports remain retained.
`installed-readonly.json` verifies unchanged installed helper hashes against
e91d5d6e and all **392** earlier journal hashes, without rewriting Phase 4 evidence.

## Files and coordinated release still required

New runtime modules: `companion_bandwidth.py`, `companion_job_summary.py`.
Modified: `companion_transfer.py`, `companion_transfer_control.py`,
`companion_package_api.py`, `companion_package_client.py`,
`companion_package_store.py`, `auto_editions_onboarding_api.py`,
`auto_editions_setup_api.py`, `scripts/studio/auto_editions_local.py`,
`worker_health.py`, `worker_diagnostics.py`,
`components/worker_health/index.html`, `.env.example`.
Added bounded check script, Phase 5 Python/UI tests, this report and configuration
correction JSON. Updated Phase 3 fixture acceptance/UI wording and two preparation
host success fixtures to include explicit verified status. Phase 4 processing
changes were preserved; their measurements are not reattributed to Phase 5.

Before Phase 4/5 operate together in production:

1. Obtain fresh authority for the exact reviewed integration/release and separate
   flag correction. Integrate the current production baseline's unrelated changes
   without overwriting them; this local branch intentionally stayed at 58569c66.
2. Recheck active jobs, sessions, retained packets and ownership. Arrange a safe
   coordinated idle window; keep automatic failed-backlog recovery disabled.
3. Correct the premature resumable flag, preserving other settings. Release the
   backend first (capability 3 evidence support, gate, timing and UI), then the
   matching companion/generation modules through its normal supervisor. Preserve
   Maximum/request_5670, settings, original sources, receipts and journals.
4. Phase 4 changes generation from released 0d078991… to 5549059f…; never label an
   old partial packet with the new fingerprint. Drain/recover compatible accepted
   sessions before switching; retain backend/storage during rollback. Legacy new
   work remains available and cannot replay partial resumable sessions.
5. Complete native multi-process PostgreSQL contention/restart, real provider
   receipt/hash/permissions, partial publication and expiry/cleanup acceptance
   under explicit production/test authority. Record the reviewed evidence hash
   and exact generation before setting acceptance attestations and enabling new
   resumable sessions. No Steve Smith or backlog authorisation is reused.
6. Separately authorise bounded normal-transfer and idle/loaded responsiveness
   observation. Establish usable sustainable rate/headroom for this connection;
   do not infer it from Phase 1's 0.3800 MiB/s, Wi-Fi speed, this loopback test or
   the unexplained 288-second interval. Household browsing improvement remains
   unverified until observed after release.

Local functionality is implemented and focused checks pass. **No Phase 4/5 live
speed or reduced-browsing-disruption claim; no release action performed.**

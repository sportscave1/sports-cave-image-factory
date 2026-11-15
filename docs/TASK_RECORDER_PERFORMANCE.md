# Task Recorder everyday speed and bandwidth

Task `20261020-fa5a2404`, owner `codex-recorder-performance-20261020`.
Based on released frame correction `2859b999`; separate INTEGRATIONS worktree.
Implementation and focused trials used isolated local storage. Recordings, pairing
and other companions are preserved during the authorised release.
No new runtime dependencies, continuous previews or browser timing changes.

## Changes

- The page requests compact long-poll responses. Unchanged selected-device state
  is omitted while connection/last-seen/ownership metadata stays fresh. The page
  merges only matching device ID and sequence; stale responses cannot restore old
  rows. Changed snapshots and older clients still receive full state.
- The helper negotiates optional delta uploads with the backend. Changed progress
  fields no longer resend the saved-recording catalogue. Every patch requires the
  exact prior state version, allowed fields and existing size bounds. A missing
  baseline requests a full resynchronisation. Reconnection always sends full state.
  Old helpers/backends continue using full snapshots. Protocol remains 3.
- Durable command acknowledgements wake the publisher immediately, replacing up
  to two seconds of idle publisher delay. Receipt GETs may long-poll for helper
  updates rather than polling every 350ms. Old servers use bounded backoff.
- Only one page state-poll loop runs. Hidden pages suspend state requests; returning
  reads acknowledged helper state without starting/stopping tasks. Page exit aborts
  outstanding requests, preserving uncertain command IDs for reconciliation. Fetches
  have a 50-second timeout. Page/PC connection errors back off to 30 seconds rather
  than repeatedly retrying every two/three seconds; helper retries include jitter.
- Existing revision binding, Stop priority, ownership checks, DPAPI storage,
  interruption handling and duplicate-command protection remain in use. No recorded
  action, condition wait or submission is skipped to improve speed.

## Focused verification

Commands (existing shared venv, all test storage isolated):

```
python -X utf8 -m pytest tests/test_task_recorder.py tests/test_task_recorder_upgrade.py tests/test_task_recorder_attention.py tests/test_task_recorder_relay.py tests/test_task_recorder_transport.py -q
node tests/task_recorder_panel_controls.cjs
node tests/task_recorder_transport.cjs
node --check task_recorder/panel.js
python scripts/task_recorder_preview.py --root <isolated-storage> --port 18965
python -X utf8 -m tests.task_recorder_performance_trial
```

Result: **30 passed, 14 subtests passed**; both Node checks and syntax passed.
Studio static/infrastructure verification also passed.

The new transport tests use the existing loopback PostgreSQL fixture at port55439;
never substitute a production database. They cover compact/full compatibility,
stale baseline rejection/full resync, bounded/allowlisted patches, invalid device
credentials, catalogue deletion propagation, receipt wake/duplicates and immediate
ack publishing. The Node check exercises snapshot merging, stale response rejection,
revocation, single polling, hidden-page suspension and error backoff.

Measured JSON response body with 80 synthetic recordings: **17,331 -> 174 bytes**
for an unchanged page response (about 99% less). Changed progress upload body is
also tested to be less than 10% of its full snapshot. These are fixture body sizes,
not claims about total internet traffic, TLS overhead or arbitrary websites.

The full local OS trial uses real account sign-in, explicit PC pairing, the actual
page/API/relay and Windows helper with a separate headed browser/profile. It proves
Record -> Stop/autosave -> Play after browser closure, verifies the replayed field,
and checks acknowledged Pause -> Resume at the current position -> Stop during a
pending wait. It changes a completed field while paused and asserts it is not
repeated after Resume. Page reload recovers stopped state without restarting.
The first control trial exposed a race in the test's final fast step; a second
blocking condition makes Stop verification deterministic. No engine change or
automatic retry of a user workflow was involved.

Local evidence: `%LOCALAPPDATA%\SportsCaveOS\TaskRecorderPerformance-fa5a2404`
(`trial-evidence.json`, `local-performance.png`, preview logs).

## Limits and rollout

Release authorised by the user on 20 October 2026: scoped commit/push to the
existing production branch, existing Render auto-deploy, then safe idle upgrade of
the installed Windows helper. Both combinations remain compatible; full bandwidth
savings require the updated helper and backend together. Live deployment/helper
results are recorded separately in the local release evidence and Studio status.

No frame-correction/Meta acceptance programme was repeated; existing coverage is
retained. The local trial is separate from subsequent live HTTPS and installed
helper release verification.
Hidden pages intentionally show fresh status only on return. Browser website
content/assets still consume whatever bandwidth that website itself needs.

# Task Recorder measured local performance phase — 20 October 2026

The requested worktree is verified at
`C:\Dev\SportsCaveWorktrees\sports-cave-integrations-local-task-recorder-v1-20261019-64cdf0b0`,
branch `codex/task/integrations-local-task-recorder-v1-20261019-64cdf0b0`,
Studio owner `codex-task-recorder-20261020-01a15682`, task `20261019-64cdf0b0`.
It was clean/Released before this phase. Its branch was fast-forwarded to existing
production commit `23103faf617d2cecd4e60b0bf5a4f36d4f3c4455`; no new commit was created.
Task Recorder at this base is the already-released optimisation `032ec41a` with
passive-frame correction/protocol 3. Installed helper sources matched that base
(normalising Windows line endings). Earlier release work and companion commits
are preserved. These additional performance changes are local only.

## Environment and method

- Windows 11 build26200, Python3.14.0, Playwright1.63.0, httpx0.28.1,
  installed headed Chrome155.0.8059.80; 16 logical CPUs.
- Full actual app.py page, sign-in, same-origin authenticated routes, PostgreSQL
  relay and separate Windows helper. Preview18966; helper18936; PostgreSQL55439,
  all loopback. Each final variant has its own database/synthetic administrator,
  task storage and fresh browser profile. The production helper on18931, its
  profile, credentials, pairings and tasks were never used by this benchmark.
- Immutable before/after package snapshots ensure the measured code does not
  change midway. Measured runtime hashes are retained. A subsequent UI-only guard clears old
  rows and blocks controls while a newly selected PC supplies its full snapshot;
  that metadata-only switch path was verified separately with focused tests and
  does not affect the single-PC benchmark path.
- 40 deterministic task summaries plus three automatically saved named recordings.
  Four-step navigation/form fixture for latency; 32-step local-only form-fill
  fixture for active traffic. No external submission, business workflow, customer,
  edition, Shopify, email or advertising writes.
- Three page loads with fresh frontend contexts/caches and an authenticated
  synthetic session; warmed application process. Cold Play recreates Chrome with
  the dedicated profile retained; warm Play reuses the healthy open context.
  Record samples are the same sequence in both variants: one warm, then two cold
  launches after Stop. Capture-active time uses the applied helper acknowledgement
  after recording hooks enable, rather than the earlier local recording flag.
- Helper state timestamps sampled every10ms. Resource samples every0.5s; values
  below include the same measurement hooks in both variants, and measure only the
  helper Python process, excluding Chrome/Node/preview/PostgreSQL/other companions.
- HTTP dispatch-to-helper delivery is distinct from a held long poll. Healthy
  long polls: before 15.08s median / 15.10s max, n=5; after 15.10s median / 15.14s max, n=6.
  The existing45s helper read budget for a15s poll and50s page timeout remain.
- Small samples and normal Windows scheduling are observations, not an SLA or
  evidence that every control became faster. Other companions were not stopped.

## Latency: median (maximum), milliseconds

| Observation | n before / after | Before | After |
|---|---:|---:|---:|
| Page usable | 3 / 3 | 1121 (1125) | 1106 (1131) |
| Cold Play → first action | 3 / 3 | 528 (933) | 539 (929) |
| Warm Play → first action | 3 / 3 | 112 (129) | 123 (127) |
| Record → hooks enabled (applied acknowledgement) | 3 / 3 | 565 (565) | 561 (658) |
| Play HTTP dispatch → helper delivery | 25 / 29 | 71 (124) | 68 (103) |
| Pause acknowledgement | 3 / 3 | 95 (99) | 88 (112) |
| Pause actually gated | 3 / 3 | 149 (156) | 223 (289) |
| Resume acknowledgement | 3 / 3 | 101 (113) | 130 (146) |
| Resume actually running | 3 / 3 | 145 (155) | 178 (195) |
| Stop acknowledgement | 4 / 4 | 267 (351) | 287 (357) |
| Stop actually stopped/browser closed | 3 / 3 | 354 (413) | 362 (424) |
| Completion → UI Completed | 6 / 6 | 828 (842) | 169 (845) |

Completion median improved about80%; its worst observation remains about0.85s.
Page usability, cold/warm start and control execution did not show a meaningful
speed gain. Pause/Resume execution samples were higher, not faster; the100ms
condition-check cadence and readiness/Stop safety waits were preserved.

## Bandwidth and requests

The minute-long trials measure **decoded application-body bytes** and completed
requests initiated in the observation window, not total broadband consumption.
Browser JSON responses can be gzip-compressed. A separate three-identical-run
probe therefore measures **actual encoded HTTP bodies plus headers** (Chromium
request sizes and HTTPX raw byte/header counts). Loopback uses HTTP/1.1; TCP/IP/TLS
framing is excluded. UI assets, website assets and other companions are separate.
The HTTP probe includes one unmeasured browser warm-up and waits for outstanding
responses after the measured window; each measured variant executes exactly3 runs.

| Encoded HTTP recorder traffic, three equal warm runs | Before | After |
|---|---:|---:|
| PC → backend, headers + body | 264,919 B | 48,185 B |
| Backend → PC, headers + encoded body | 92,053 B | 39,319 B |
| Total | 356,972 B | 87,504 B |
| HTTP requests | 59 | 59 |
| Website body bytes (separate, same work) | 19,875 B | 19,875 B |

**Actual HTTP traffic fell 75.5% for equivalent work**.
Decoded body bytes per run fell 93.0%; that is a different metric,
not a claim of the same percentage saving on a real network connection.

| 60s observation (normalised per minute) | Before | After |
|---|---:|---:|
| Idle recorder requests/min | 7.0 | 6.0 |
| Idle decoded body bytes/min, sent + received | 1608 B | 1215 B |
| Active recorder requests/min | 319.4 | 406.9 |
| Active decoded body bytes/min, sent + received | 2,867,200 B | 249,831 B |
| Completed synthetic active runs | 16 | 20 |
| Recorder requests per completed active run | 20.12 | 20.50 |
| Demo website body bytes per run | 6,625 B | 6,625 B |

Active windows were 60.48s / 60.45s; idle windows60.00s each.
Requests/min rose because more work completed and terminal-state notifications are
sent promptly. Requests per run stayed around20; this is a payload-size and
confirmation-latency improvement, not a claim of fewer requests per task.
The before active window carried 2,890,233 B of decoded recorder
traffic versus106,000 B of website bodies: catalogue updates dominated this sample.
Afterwards, website assets are proportionally more significant. Arbitrary image-
heavy websites and real WAN/Render latencies are not measured here.
The closed-page10s check generated zero page-control requests in both versions;
the outbound helper remained reachable and reconciled without replay.

## Helper resources: median (maximum)

| Observation | n before / after | Before | After |
|---|---:|---:|---:|
| Idle CPU % of one logical core | 118 / 118 | 0.00 (12.42) | 0.00 (24.75) |
| Idle Working set MB | 118 / 118 | 59.01 (59.03) | 59.26 (59.29) |
| Active CPU % of one logical core | 118 / 118 | 18.17 (51.98) | 18.58 (43.60) |
| Active Working set MB | 118 / 118 | 59.77 (60.44) | 60.08 (60.62) |

Idle CPU was already mostly quiet. No helper CPU or memory reduction is claimed;
working set stayed around60MB and active CPU remained similar, while the candidate
completed more synthetic runs. No privacy checks or browser waits were removed.
Five actual page revisits after forced renderer GC retained8 documents,2,924 nodes
and704 listeners on every visit. Retained JS heap ranged19.08–22.78MB and ended
lower; this is a bounded lifecycle check, not proof against every long-session leak.

## Changes and why

1. Version-bound task-summary upsert/remove patches on both helper uplink and held
   page polls. A one-row progress/result change no longer resends the catalogue.
   Optional capabilities preserve old helpers/backends. Missing baselines fall back
   to full snapshots; same ownership, key/field/size checks and durable revisions.
2. Other PCs contribute connection metadata, not repeated unselected catalogues,
   during compact polling. Device switches explicitly fetch the selected snapshot and block controls
   until it arrives, preventing old task IDs from targeting the new PC.
   Conditional acknowledgement refreshes return immediately rather than holding
   another long poll or needlessly loading unchanged full state.
3. Saved table rows are keyed by task ID and replaced only when their content or
   controls change. Focus/draft input/selection survive background refreshes.
4. Durable terminal/paused state wakes the existing publisher; no faster recurring
   polling or extra streaming. Step progress still uses the existing bounded cadence.
5. Cold Play advertises Starting with the intended task identity while preparing.
   Connection loss during this phase is interrupted, not stale Completed. Stop
   reports Recording saved only if it actually stopped a recording; playback Stop
   reports Stopped. Page retry backoff now includes bounded jitter.

Task-summary caching, lazy full-details loading, warm browser reuse and quiet
idle/closed-page polling were already efficient and were retained. No continuous
screenshots, video, full-DOM uploads, per-second elapsed-time polling, new UI
framework, settings, dependency, public endpoint or performance dashboard was added.
The existing compact embedded page and controls remain familiar.

## Verification and files

36 focused pytest tests +14 subtests passed; Node panel controls, compact transport
and JS syntax checks passed. Tests cover exact/missing baselines, malformed and
oversized deltas, catalogue add/remove/rename-compatible propagation, owner/device
checks, older-client fallback, immediate completion notification, cold-start state,
interruption, supported-action/attention/privacy coverage and reliable controls.
Full before/after application trials passed named recording/autosave, closed and
warm browser playback, actual form/URL checkpoints, Pause/Resume/Stop without
repeating completed steps, duplicate Play suppression, one disconnect/reconnect
without replay, refresh/draft/selection persistence and retained unchanged rows.
Each Play's first action executed exactly once. Three supplied recording names
persisted in each variant. No full Phase2/Meta programme was repeated.

Changed files:
- `task_recorder/state_updates.py`, `device.py`, `relay_store.py`, `hosted_api.py`:
  negotiated, validated catalogue deltas and acknowledged state delivery.
- `task_recorder/runner.py`: terminal/paused-state notification only; action timing,
  locators, privacy and supported actions preserved.
- `task_recorder/panel.js`: delta merge, keyed rows, conditional refresh and jitter.
- `scripts/task_recorder_preview.py`: explicit isolated benchmark package/database
  selection and safe exception-type/stack diagnostics, no credentials in logs.
- `scripts/benchmark_task_recorder.py`: reproducible local measurement harness.
- `tests/test_task_recorder_transport.py`, `tests/task_recorder_transport.cjs`.
- This report.

Evidence lives outside Git at
`%LOCALAPPDATA%\SportsCaveOS\TaskRecorderMeasured-64cdf0b0`:
`environment.json`, `comparison.json`, immutable package hashes, per-run summaries,
size/timing-only JSONL, screenshots and isolated profiles/databases.
Preliminary harness setup/contamination runs are excluded. One shared-fixture run
had an unclassified503; it did not recur in either fully isolated final trial.
No production fix is claimed for that preliminary error; preview diagnostics now
record exception type/stack without message/credentials for future diagnosis.

Reproduce using the shared test venv and fresh unique variant labels (database and
output already existing is rejected, rather than overwritten):

```powershell
$env:PYTHONPATH=(Get-Location).Path
python -X utf8 -m scripts.benchmark_task_recorder --variant before-new --recorder-source <frozen-baseline-parent>
python -X utf8 -m scripts.benchmark_task_recorder --variant after-new --repeat-visits
python -X utf8 -m scripts.benchmark_task_recorder --variant before-wire-new --wire-only --recorder-source <frozen-baseline-parent>
python -X utf8 -m scripts.benchmark_task_recorder --variant after-wire-new --wire-only
```

The baseline snapshot is the already-released recorder from23103faf/032ec41a,
not the original unoptimised V1. Use the local isolated PostgreSQL fixture on55439;
never substitute a production database. The harness creates only
`recorder_bench_64cdf0b0_*` databases on that loopback server. Benchmark profile/data
paths are restricted to its own AppData folder; the installed helper is not used.
There are no code changes to Edition Ops, Photoshop, other companions, upload
workflows, Render topology or production business data.

## Limits / next release

Cold/warm launch and active engine CPU remain the main unchanged costs. Completion
median improved but the observed0.85s worst case did not. Pause/Resume sampling was
not faster; small samples and100ms condition checks remain visible. Network headers
and compression matter, hence the separate actual-HTTP result. Real HTTPS/WAN
latency, arbitrary website assets and long-duration/whole-browser resources require
separate measurement. No new performance changes were committed, pushed, deployed
or installed; any future release requires a specific instruction.

Status: Performance improvements implemented and verified locally. Not committed, pushed or deployed.


## Integration preparation — 20 October 2026

The original owner was explicitly authorised to commit the completed infrastructure
and measured speed changes for the Windows Recorder release. Only the frozen
measured candidate, final PC-switch guard, relevant tests, isolated preview and
measurement harness are staged. Later editor, playback, toolbar, Product Uploads
and recording-experience drafts remain uncommitted and unchanged. The recorded
measurements above remain historical evidence; native Windows acceptance and
release integration belong to the Windows Recorder task. No push, deployment or
installed-helper update is performed by this preparation.

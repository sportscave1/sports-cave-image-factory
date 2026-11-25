# Phase 2: predictable inbox speed

25 November 2026. Implemented locally on top of released Phase 1
`58d8446f42f831cb792c84644575bb4cb2d45df6`. Deployment is pending separate
release authorization. No production credentials, mailbox bodies or live
customer fixtures were used in development or the benchmarks.

## What changed

The asynchronous inbox provider can retain one authenticated read connection
for a short browsing burst. It expires after ten idle seconds or sixty seconds
total, with an independent cleanup timer. It is serialized, always reselects
the folder read-only and validates UIDVALIDITY against the requested message.
A failed operation destroys the connection; existing safe-read reconnection
handles the next attempt on a fresh socket. Writes discard the idle read
connection and use their own connection. Shutdown and configuration rotation
close idle connections and prevent in-flight ones from being retained.

Reuse is enabled only for the inbox ReadService provider. The certificate
worker retains Phase 1's fresh-provider-per-pass recovery behavior. SMTP,
durable send deduplication, signature selection and certificate reply policy
are unchanged.

Selected bodies cancel optional history that has not started. History now
uses background admission, yielding to foreground work. Busy history retries
after a bounded deadline rather than blocking a loaded body or polling the
provider repeatedly. An active protocol operation is allowed to finish safely.

Browser header/body paint timings, server queue wait and connection reuse
are measured separately. Timing events contain stages, durations and cold/
cached classification, without email addresses, subjects or message IDs.
The inbox list also notices changed Companion receipt decorations without
requiring a mailbox revision change, preserving the lightweight sent tick.

## Before/after evidence

The loopback-only component workbench renders the actual released/current
component with synthetic controller models. Each version performs 100 uncached
and 100 cached selections. Its host acknowledgement is deliberately fixed at
80 ms; no live mailbox or application server is involved.

| Browser measurement | Released baseline p95 | Phase 2 p95 | Samples per version |
| --- | ---: | ---: | ---: |
| Uncached selection header paint | 7.1 ms | 7.1 ms | 100 |
| Uncached selection body paint | 97.9 ms | 103.8 ms | 100 |
| Cached selection header paint | 7.1 ms | 8.1 ms | 100 |
| Cached selection body paint | 14.1 ms | 14.1 ms | 100 |

The small uncached-body variation is browser scheduling overhead in this
fixture. The result demonstrates preserved fast cached painting, not an
improvement in real network latency. The new component emitted all 400
header/body stage events across 200 selections. Measurement begins in
selection handling; it excludes operating-system input delivery.

A separate disposable IMAP adapter performs 100 uncached MIME reads per mode.
Its connection/login/select/command/logout delays are explicitly modeled at
700/230/210/210/210 ms. Actual Python CPU timings are measured separately.

| Provider measurement | Fresh connection per read | Bounded reuse |
| --- | ---: | ---: |
| Connections for 100 reads | 100 | 2 |
| Read-only identity selections | 100 | 100 |
| Measured CPU p95 | 26.42 ms | 1.38 ms |
| Modeled network p95 | 1770 ms | 630 ms |

These modeled network figures are not production benchmarks. The first read
after an idle expiry still incurs connection/authentication cost. The main
gain is successive reads and history within an active browsing burst.
The proposed live cold-body p95 target below two seconds remains unverified
until an authorized deployment and representative live measurement.

## Safety and verification

Focused tests cover changed UIDVALIDITY, read/write isolation, reset recovery,
idle and absolute expiry, stale cleanup timers, concurrent callers, shutdown
while borrowed, history contention and privacy of timing events. Existing
certificate recovery, compose/drafts, sent attribution, HTML/image privacy,
durable delivery and inbox cache contracts are included in regression checks.

The old review-prompt test expected the retired Judge.me-specific sentence.
It now asserts the existing released instruction to avoid mentioning internal
review infrastructure; the production reply template was not changed.

Reproduction:

- `pytest tests/test_email_phase2_speed.py` plus the existing email suites.
- `node --test tests/test_email_phase2_timing.cjs` plus email component suites.
- `python tests/profile_email_phase2_provider.py <evidence.json>`.
- `python tests/profile_email_phase2_browser.py`, open its loopback URL and
  run each version. The server serves only allowlisted component/fixture assets.

Evidence files are retained in the task's Studio runtime directory under
`C:/Dev/SportsCaveWorktrees/.studio/runtime/20261125-email-speed*`.
No email was sent, automation reset, Render service changed or release pushed
while performing these local checks.

## Validation result

- Required email/reconnect/performance checks: 350 passed, 17 subtests passed,
  zero skips, 43.73 seconds. This includes the added safe background-retry
  priority fence and existing connection/poll recovery checks.
- Nine Node component suites passed, zero skips.
- Broader optional regression sweep: 711 passed and 63 subtests passed;
  45 existing opt-in native/disposable SQL tests were skipped because their
  separate fixtures were not configured. They are not counted as passed.
  The required gate selects the V2D controller classes explicitly; native
  contact SQL remains in its existing separate integration fixture.
- Render topology validation and changed-file static checks passed.
- Browser measurements: 100 cold + 100 cached selections for each version;
  100 uncached provider reads for each mode. All data was synthetic.

The implementation remains uncommitted and undeployed pending approval for
this new release. Existing production Phase 1 is unchanged.

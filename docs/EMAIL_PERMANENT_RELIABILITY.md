# Email reliability investigation — 27 September 2026

## Outcome and production evidence

**Local hardening is implemented. Production connectivity is NOT yet proven restored.**
No commit, push, deployment, credential change, mailbox mutation, message send,
database migration or production schema change was performed.

Read-only Render inspection identified the first failing stage as socket connection
establishment, before mailbox authentication. This is evidence of a network path
failure on the replacement instance, not proof of a credential, folder parser,
CRM, lease, semaphore or SSE failure.

| UTC time | Evidence |
|---|---|
| 09:37:03 | Previous deployment `493983b7ef543cf4e3d63df935a2f295a272cdfd` became live. |
| 09:57:00, 10:17:22, 10:37:43 | Old instance `plvt2` logged IDLE `abort`, each with 15-second reconnect. The older log did not identify the substage. |
| 10:56:01–10:56:07 | Old instance rendered Email; component assets returned HTTP 200. No foreground network failure appears in the retrieved window. User reports this version working. |
| 10:58:02 | New instance `prlmb` completed server startup. |
| 10:58:03 | CRM deployment `5f2f03fc2773bd0f6014929775e7b938adbcb4ca` became live. |
| 10:58:51 | New instance served the Email SSE endpoint with HTTP 200. |
| 10:59:24 | Foreground: `stage=connect code=network type=OSError errno=101 duration_ms=8214`. |
| 10:59:26 | Watcher: `type=OSError delay=15`. |
| 10:59:32 | Foreground retry: same `errno=101`, 8098 ms. |
| 11:00–11:13 | Watcher backs off 30/60/120 seconds; foreground connections repeatedly fail around 8 seconds. |

Linux errno 101 is `ENETUNREACH`. The current logs do **not** establish which
resolved address failed or whether an earlier address timed out. Python's
`socket.create_connection` normally discards earlier errors and raises the last
one. A fixture reproduces IPv4 timeout followed by IPv6 ENETUNREACH. That is a
diagnostic ambiguity, **not a proven production IPv6 root cause**. No forced IP
family, hardcoded endpoint, DNS change or TLS bypass was introduced.

The remote SSH endpoint was not accessible from this environment. No production
shell health check or authenticated real-mailbox test was performed. Determining
the underlying route/filter/provider cause requires the per-address diagnostics
or the health command from the affected deployment environment. A code patch
cannot guarantee recovery from unavailable external connectivity.

## Meaningful change chain and dependencies

`ffbe809` hardened polling; `d575b1a` optimized rendering; `493983b` added IDLE/SSE;
`5f2f03f` added CRM. The CRM commit contains 33 files: new CRM modules, tests,
documentation and migration, plus navigation metadata in `app.py`, `app_search.py`,
`os_accounts.py` and a CRM router in the separate `webhook_server.py` service.
It does not change `support_email*`, Email frontend assets, top bar, primary server
lifecycle, requirements, or Render configuration.

The two deployment build logs show the same complete installed package list,
including IMAPClient 3.0.1, Streamlit 1.64.0, Uvicorn 0.54.0, Starlette 1.7.0,
psycopg 3.3.6 and requests 2.34.2. No dependency downgrade/pin is justified by this
incident. The prior build explicitly reports Python 3.14.3.

The unrelated deployment replaced the instance and its in-memory session caches.
It exposed a new connection failure; no direct CRM cause has been demonstrated.
The optional support-metadata `UndefinedTable` warning also existed on the old
instance. It does not explain a socket failure before authentication and no
migration was attempted to address it.

## Connection ownership and isolation

Render confirms exactly one Standard primary instance, running
`python sports_cave_server.py`, with one Uvicorn process and no worker argument.

Before this patch: one leased persistent watcher plus up to two short-lived
connections in the process coordinator. The possible application peak was three,
even though sequential simulations happened to peak at two.

After this patch:

- One leased IDLE connection, owned by explicit ASGI lifecycle, not browser tabs.
- One short-lived slot shared by all production `ImapProvider` operations.
- Foreground requests wait up to the existing configuration timeout (8 seconds).
- Background requests defer when the slot is occupied or foreground work waits.
- No raw socket is cached, shared with notification polling, or returned after close.
- Connection failures and cancellation release transport resources and permits.
- Watcher initialization failure is caught without failing web-server startup.
- Watcher health cannot open or poison the foreground circuit breaker.

The short-lived cap is process-local, appropriate to the verified single-process,
single-instance deployment. During rolling deployment overlap, each process has
its own short-lived slot. **Do not claim a distributed short-lived cap of one.**
Recheck topology before adding replicas/workers; the persistent watcher remains
distributed-lease controlled. Manually running the diagnostic is an additional
explicit connection outside the application coordinator.

Existing `app_sync_state` lease behavior is retained: PostgreSQL clock, 60-second
expiry, fenced owner renewal/publish, local 35-second deadline, renewal every 15
seconds, direct transport shutdown on loss. An old lease can delay only IDLE
leadership. Foreground reads/actions do not query/acquire that lease. Crash expiry
and normal shutdown cleanup remain unchanged; no schema change is needed.

## Fallback, snapshots and health

Existing approximately 60-second STATUS fallback remains enabled. Existing
15/30/60/120-second retry backoff and one safe foreground read retry are retained.
Manual Refresh can make a controlled recovery attempt through the same slot; it
does not restart the watcher or create a timer.

IDLE publishes allowlisted status/version metadata. The shared transient STATUS
snapshot supplies notifications, unread badge and live-mail checks; notification
deduplication still uses the existing durable UIDVALIDITY/UID cursor. SSE failure
leaves the existing timer fallback intact. No browser implementation changed.

Existing successful folder/header/selected-body/composer state remains visible
on same-view refresh/poll failure with the existing reconnect/last-success label.
A new process or first-time session has no last-good display snapshot: showing
unavailable there is accurate. No permanent email-content copy was introduced.

`MailboxRuntime.health(scope)` now reports only diagnostic primitives:
HEALTHY/DEGRADED/RECONNECTING/UNAVAILABLE, last-success/failure timestamps,
failure stage, consecutive failures, watcher state and fallback state. These
fields do not drive mailbox truth or introduce UI. Watcher health is separate
from short-lived connection backoff.

Transport diagnostics preserve DNS resolver order and existing per-address
timeouts. Every failed TCP attempt logs only family, stage, exception class,
numeric errno and duration; TLS uses the original hostname with certificate
verification. Failed sockets close before the next address. Watcher logs now
distinguish lease/connect/authentication/capability/select/status/signal/idle/
idle_done/noop stages. No exception text, endpoint addresses or credentials are
logged. SMTP continues using its original untouched implementation.

## Mandatory local pre-deployment gate

Run after changes to requirements, bootstrap, routing/navigation, top bar,
threading, SSE, shared caches/runtime or database coordination:

```powershell
.venv/Scripts/python.exe scripts/test_email_reliability.py
git diff --check
```

The command discovers Email Python regression modules and runs the Email JS
component suites with Node. It uses fixtures/mocks, not a mailbox. No existing
CI workflow exists in this checkout; no new CI platform was introduced.
This is a documented local gate, not an automatic Render deployment blocker.

## Explicit post-deployment diagnostic

```text
python scripts/check_support_email_health.py
```

Run only deliberately in the deployment environment with its existing environment
variables. It checks configuration, DNS, TCP, verified TLS, capability, login,
read-only INBOX selection, STATUS and cleanup. Output is fixed PASS/FAIL stages,
safe category and timing. It never FETCHes mail, sends mail, changes flags, prints
credentials, or loads `.env` into output. No new environment variable is required.
It is not called by startup, CRM, a widget rerun, or the test gate.

## Verification and limits

- Final isolated Email gate: **267 Python tests passed; six Email JS suites passed**.
- Separate JS run including global-search component: seven suites passed.
- Shared navigation/sidebar/search/top-bar/CRM-boundary run: 62 tests, one known
  baseline failure: `test_sidebar_is_compact_and_has_no_brand_or_section_headings`.
- Python compilation of every changed/new Python file and `git diff --check` pass.
- Full discovery on unchanged `5f2f03f`: 3,352 tests, 131 failures, 36 errors,
  70 skips. Final discovery: 3,366 tests, the same 131 failures, 36 errors and
  70 skips. Compared all 167 failing identities: **zero new failures/errors**.
  The added CRM AppTest runs in a fresh interpreter because legacy full-suite
  tests leave a global Streamlit form context behind; it passes independently.
- Original focused lifecycle/IDLE baseline: 51 tests passed.
- New tests cover concurrent slot ownership, acquisition timeout/cleanup, stale
  lease with usable foreground access, watcher-start failure, health classification,
  per-address error masking, fallback address selection, TLS cleanup, safe health
  check, and all six CRM page renders/reruns with Email entry points forbidden.
- Existing tests protect SMTP/signatures, receipt/duplicate-send handling,
  attachment laziness, read/unread, last-good view, notification dedupe, IDLE/SSE
  fallback, component timer uniqueness, selection/composer preservation.
- No frontend asset, layout, composer, SMTP, signature, CRM production module,
  Files, Orders, search, requirements or Render configuration changed.
- JS component regression checks were run; a new interactive browser session and
  real VentraIP production acceptance were not performed for this backend patch.

Files changed:

| File | Change |
|---|---|
| `support_email_runtime.py` | One short-lived slot, bounded acquisition, internal health. |
| `support_email_provider.py` | Preserve safe failure stage; use instrumented IMAP transport. |
| `support_email_transport.py` | Per-address DNS/TCP/TLS diagnostics and transport cleanup. |
| `support_email_idle.py` | Safe watcher stages/health; optional startup cannot fail the app. |
| `scripts/check_support_email_health.py` | Explicit read-only environment diagnostic. |
| `scripts/test_email_reliability.py` | Offline Python and JS deployment gate. |
| `tests/test_email_permanent_reliability.py` | Fourteen new reliability/isolation regressions. |
| `tests/test_email_poll_recovery.py` | Assert foreground queueing under the new one-slot cap. |
| `docs/EMAIL_PERMANENT_RELIABILITY.md` | Evidence, topology, tests, limits and acceptance plan. |

One-hour compressed IDLE + consumer simulation (four sessions/tabs, five arrivals,
one disconnect/reconnect and fallback): one logical watcher; two watcher socket
lifetimes; 130 short-lived connections; 132 closed; peak two simultaneous; 66
STATUS commands; 10 header fetches (notification plus inbox headers); zero bodies;
five notifications; zero duplicate notifications; zero leaks. About 2.1 seconds
local fixture time, not a production-latency claim.

Separate ten-minute/four-session/400-interaction simulation includes a two-minute
outage: 19 attempts, 19 closed, peak one short-lived socket, eight STATUS calls,
zero body fetches, zero leaks. Manual Refresh, read/unread/flag, cached view and
CRM isolation are covered by separate deterministic regressions; do not describe
all these as one concurrent production soak.

## Post-deployment acceptance — only after approval

1. Run the health command from the affected service. If TCP fails, retain all
   per-family safe failures and timestamps for Render/VentraIP network diagnosis.
   Do not rotate credentials, force IPv4, or increase caps based on that alone.
2. A: Open Email and confirm Inbox/folders load.
3. B: Nathan sends one external test message to hello@sportscaveshop.com; verify
   automatic row, badge and one bell notification without Refresh.
4. C: Open/mark read, then mark unread; verify real shared-mailbox badge changes.
5. D: Navigate through CRM and return to Email; retain mailbox and composer state.
6. E: Open Nathan and Maria sessions plus another tab; verify one logical watcher.
7. F: Wait at least one fallback interval; verify no outage or duplicate arrival.
8. G: Inspect safe connection logs for failures, bounded reconnects and cleanup.
   Confirm external-client flag changes converge and Sent verification remains intact.

## Deployment decision

The local reliability changes are reviewable and tested, but **do not label this
incident permanently repaired or production-ready solely from mocks**. The
production TCP/network-path failure must pass the affected-environment health
check and acceptance above. No source patch can prevent every unrelated deployment
from encountering an external network outage. The concrete protections here are
bounded connections, deterministic cleanup, optional-IDLE startup isolation,
safe staged diagnostics, last-good-cache regressions and a repeatable local gate.

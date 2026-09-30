# Email Inbox reliability — 30 September 2026

Implemented locally only. No production migration, deployment, mailbox mutation,
credential change or TLS relaxation was performed.

## Confirmed failure chain

Read-only Render inspection used the already-authorized Nathan workspace and
canonical service `sports-cave-os` (`srv-d8kl4on7f7vs73dvavv0`), region **Oregon**.
At **2026-09-30 08:36:50 UTC**, the current instance logged an IPv4 TCP timeout
after **8,008 ms**. This is before TLS, authentication, SELECT, LIST or FETCH.
The immediately following zero-millisecond IPv6 timeout is the already-consumed
shared deadline, not proof of a second network attempt. Earlier supplied logs
also recorded IPv6 ENETUNREACH. New diagnostics distinguish skipped addresses.

At 08:11:21 UTC snapshot reads logged UndefinedTable; at 08:12:26 snapshot writes
did too. Support metadata also logged UndefinedTable through 08:20:23. Logs do
not name which optional metadata relation is missing; use the schema checker
below to identify it rather than guessing.

The repository contained all three private Email migrations but omitted them
from the SHA-reviewed deployment manifest. `sports_cave_server.py` calls that
manifest once before listening. Render's separate configured pre-deploy command
currently targets only the old OS repair-request migration; it does not apply
Email migrations. No Render settings were changed.

Consequently a new process cannot restore a private snapshot, and when its live
IMAP header fetch also times out it genuinely has no rows. A snapshot cannot
retroactively recover mail that was never successfully persisted.

**EXTERNAL CONNECTIVITY BLOCKER remains:** application hardening cannot restore
an unreachable Render-to-VentraIP route. The logs do not establish whether
VentraIP filtering, a firewall, or routing is responsible. Obtain the actual
configured host from the safe health command below (repository default:
`ventraip.email`, port 993); do not assume the production hostname is the default.
Give support the service, Oregon region, UTC timestamp, host/port and family
diagnostics. No credentials are needed in that evidence.

## Local fixes

- Register workflow, settings/preferences and Inbox snapshot migrations with
  reviewed SHA-256 values in the normal deployment path. Add a narrowly scoped
  `--email` apply/check mode and read-only `--verify-email-schema` mode.
- Verify private tables, RLS, primary indexes, client grants, server privileges,
  snapshot column types/nullability/size constraint, existing IDLE coordination
  table and migration ledger. No new migration or schema redesign.
- Keep the latest 50 headers in memory and restore the same credential/mailbox
  scope's persisted metadata asynchronously before network refresh. Retry a
  failed restore after the database cooldown if still empty. Never replace an
  already-live value with a late persisted read.
- Coalesce index sync, fence superseded local refreshes, and fence durable writes
  by **read-start time** instead of completion time. Equal/older observations
  cannot replace a newer stored snapshot. This timestamp fence assumes normal
  host clock synchronization; the IDLE owner lease uses database time.
- Exclude snippets as well as bodies, MIME, attachments and credentials from new
  persistent writes. Snapshot remains display-only; VentraIP stays authoritative.
- Missing-table database failures back off five minutes; other snapshot/support
  database failures back off one minute, with bounded safe category logs.
  Successful live reads still publish before optional database/folder work.
- Inbox heartbeats consume the shared read index rather than creating additional
  per-tab remote delta requests. Other folders/search retain existing read paths.
- IDLE establishment/login shares the process admission/circuit gate with reads
  and notification polling. The healthy leased IDLE socket then releases the
  establishment slot, so it cannot block normal reads for its lifetime. Existing
  database lease still limits IDLE to one owner across overlapping processes.
  Indexes remain one per process, not a new globally replicated mailbox service.
- Transient circuit backoff is exponential to 300 seconds plus up to 10% jitter;
  TLS/auth failures use 900 seconds. Forced retry opportunities are limited to
  one per 15 seconds and still respect active connection limits. Successful
  operations reset the circuit. Worker refresh carries the manual request into
  its own context rather than relying on the UI thread's context variable.
- Preserve selected conversation and session-cached opened bodies on outages.
  Existing UIDVALIDITY/body identity guards remain. Cold snapshots contain no
  bodies: those require a successful live read.
- Keep one compact status, with an explicit attention/Retry state for terminal
  errors. Healthy state comes from actual read success, not configuration alone.

## Production commands — run only after review

Use the reviewed checkout in the canonical Render shell. These first two commands
are read-only (the first validates local migration bytes without connecting):

```sh
python run_migrations.py --email --check
python run_migrations.py --verify-email-schema
```

The explicit apply command, **not run by Codex**, is:

```sh
python run_migrations.py --email
python run_migrations.py --verify-email-schema
```

It applies only the three existing private Email migrations, under the normal
advisory lock, verifies schema, and records the migration ledger atomically.
Existing OS accounts, Shopify order identity and app_sync_state tables are
dependencies. Do not run the unrestricted historical migration runner.

Expected success: `READY Email schema and migration ledger verified`.
Missing relations/grants/columns are named without reading message contents.

Read-only network/authentication diagnostic:

```sh
python scripts/check_support_email_health.py
```

Expected stages: PASS configuration, dns, tcp, tls, greeting, capability,
authentication, select and status. SELECT uses read-only EXAMINE semantics;
there is no FETCH, send, flag, move or delete. TLS verifies hostname/certificate.
The command prints UTC, configured host/port and Render identity/region when
available. Failure logs report safe stage/family/type/timing, never passwords
or provider response text. A TCP failure emits EXTERNAL CONNECTIVITY BLOCKER.

Local execution returned `FAIL configuration`: no usable local mailbox credentials.
No authenticated production check or production schema query was run in this task.
The live evidence above comes from read-only Render logs/service metadata.

## Validation

- Email gate: 420 Python tests, 417 passed / 3 skipped; 10 JavaScript test files passed.
- Separate startup: 6 passed; navigation performance: 23 passed. Navigation:
  6 run, 5 passed / 1 database-dependent skip (also included in Email gate).
- Disposable PostgreSQL/PGlite applied all three migrations twice. Checked
  snapshot primary index/RLS, trusted read/write, denied anon/authenticated and
  unprivileged PUBLIC-inheriting reads, scope isolation and stale-write fencing.
  Existing IDLE lease/fencing SQL checks passed independently.
- Python compilation, JavaScript syntax and git diff whitespace checks passed.
- Real Email component/controller in an offline Streamlit fixture: healthy,
  cached outage, new-worker persisted outage, no-snapshot outage and automatic
  recovery. Layout checked at 1366x768, 1440x900 and 1920x1080; retained list and
  selected cached body, compact warning, no console errors observed. These are
  fixture results, not authenticated production or the full OS navigation shell.
- Deterministic latency fixture: blocking list 703.31 ms versus cached list
  1.97 ms; body request returns in 0.41 ms while its simulated 800 ms fetch runs
  asynchronously. 50 rows, zero initial bodies/attachments/customer-order queries.
  These numbers do not measure VentraIP or promise production latency.

## Changed files

Runtime: support_email_reads.py, support_email_snapshot.py,
support_email_db_guard.py, support_email_runtime.py, support_email_idle.py,
support_email_store.py, support_email_workspace.py, support_email_transport.py,
components/support_email/mail.js.

Operations: run_migrations.py, support_email_schema.py,
scripts/check_support_email_health.py.

Validation: tests/test_email_never_blank.py, tests/test_email_inbox_reliability.py,
tests/test_email_poll_recovery.py, tests/test_support_email_idle.py,
tests/email_inbox_snapshot_postgres.mjs,
tests/fixtures/email_inbox_reliability_preview.py, this document.

Release remains conditional on the approved migration and successful read-only
health check from Render. No emails sent/read/marked/moved/deleted, no campaigns
changed, no production mutations, no commit, push or deployment by Codex.

# Daily Staff Reporting

Sports Cave OS generates one same-day staff report after 5:00 PM in
`Australia/Sydney`. It sends through the Resend HTTP API, stores delivery history
and an internal report snapshot in Supabase, and exposes that archive only on the
owner-approved Reporting page.

## Required Render Environment

Set these values on both the Sports Cave web service and the Render Cron Job.
Keep `RESEND_API_KEY` secret.

```text
RESEND_API_KEY=<Render secret>
ACTIVITY_DIGEST_ENABLED=true
ACTIVITY_DIGEST_FROM=Sports Cave OS <daily@reports.sportscaveshop.com>
ACTIVITY_DIGEST_TO=<daily report recipient>
ACTIVITY_DIGEST_REPLY_TO=<reply-to mailbox>
ACTIVITY_DIGEST_TIMEZONE=Australia/Sydney
ACTIVITY_DIGEST_HOUR=17
SPORTS_CAVE_REPORTING_OWNER_EMAIL=<Nathan's active Sports Cave admin email>
```

If `SPORTS_CAVE_REPORTING_OWNER_EMAIL` is absent, the app safely falls back to
`SPORTS_CAVE_ADMIN_EMAIL`. Reporting access fails closed if neither value matches
an active admin account. Workers never see the configured owner email.

The sender domain `reports.sportscaveshop.com` must remain verified in Resend.
Sports Cave OS never uses SMTP, IMAP, or the VentraIP mailbox password.

## Database Migration

Apply the additive migration before enabling the cron or opening the archive:

```text
python run_migrations.py
```

The reporting schema is in:

```text
migrations/20260728_daily_staff_reporting.sql
```

It creates database-backed delivery claims and archived report snapshots. A
partial unique index permits only one production report for each purpose,
and Sydney report date, even if the configured recipient changes during the
day. A separate unique idempotency key protects test and provider retries.

## Render Cron

Create this manually in Render after the migration and environment values are
ready:

```text
Name: sports-cave-daily-activity-report
Schedule: 0 * * * *
Command: python scripts/send_daily_activity_digest.py
```

The command is a one-shot process and exits after each run. It checks the
current `Australia/Sydney` time and sends only after the configured local hour.
Running hourly keeps the UTC cron expression unchanged across Australian
daylight-saving transitions. A delayed run later on the same Sydney date can
claim the report, but the command never walks historical dates or creates an
automatic backlog.

The report period begins at midnight on the current Sydney calendar date and
ends at the actual generation time. Those local boundaries are converted to UTC
before the bounded `audit_logs` query. Future and previous-day activity are not
included.

## Report Contents

Every active `os_users` account receives a staff section, including accounts
with no meaningful activity. Inactive accounts are excluded. Activity is
matched by authenticated user ID first, then normalized account email or unique
login/display identity for older records.

The central classifier excludes health checks, polling, caches, thumbnails,
webhooks, automatic operations, page refreshes, sign-in noise, and the report
delivery itself. Repeated work is grouped into short readable totals. The CSV
contains every included meaningful record and protects cells from spreadsheet
formula injection.

Nathan's Daily Execution subsection is loaded from
`daily_execution_sheets` using the configured owner's stable account ID and the
Sydney report date. It reports planned MIPs and other tasks, completed and
outstanding counts, completion percentage, notes, and recorded carry-over
status. Activity Log events are not used to infer task completion.

## Enabling Reporting Access

1. Sign in as the active admin account whose normalized email matches
   `SPORTS_CAVE_REPORTING_OWNER_EMAIL`.
2. Open **Accounts & Access**.
3. Under **Reporting Access**, tick **Reporting** and save.
4. The top-level **Reporting** page appears immediately.

The permission begins unticked. It is excluded from worker creation, worker
permission forms, bulk page assignment, admin fallback access, and forged
permission rows. Other administrators and all workers see a locked unticked
control and are denied by navigation, routing, archive reads, CSV downloads and
test delivery.

Unticking Reporting removes access immediately. The hourly cron is independent
of page access and continues to run while reporting delivery remains enabled.

## Test and Preview

On the Reporting page, **Send test email** sends one clearly labelled test to
the configured recipient. It exercises HTML, plain text, reply-to and a CSV
attachment, uses a test-only idempotency key, archives the test with a TEST
label, and logs the manual action once. It does not consume the production
daily key.

Generate a local current-day preview without sending or writing delivery
history:

```text
python scripts/send_daily_activity_digest.py --preview
```

Preview a historical Sydney date without sending:

```text
python scripts/send_daily_activity_digest.py --preview --date 2026-07-28
```

A date override is rejected unless `--preview` is present.

## Archive and Delivery Health

The Reporting page loads a bounded archive page rather than the full history.
Select an archived report to view the same HTML snapshot that was emailed and
use **Download CSV** for its stored detailed attachment.

Delivery Health shows whether required configuration is present, never the API
key itself. It also shows the sender, recipient, reply-to, timezone, send hour,
next expected run, recent attempts, last success, and the last sanitized
failure.

Production and test reports are first written as pending delivery/archive
records. Provider retries reuse the exact archived payload and the same Resend
idempotency header. Sent rows are terminal. Stale pending rows and retryable
failures can be reclaimed safely; permanent failures are not retried
automatically.

## Immediate Disable and Troubleshooting

Set this Render value and save:

```text
ACTIVITY_DIGEST_ENABLED=false
```

The next hourly run exits successfully without sending.

If Reporting is missing, confirm the dedicated owner email matches the active
admin account exactly after trimming and case normalization, then enable the
permission in Accounts & Access.

If delivery is unconfigured, check that the Resend key exists on the Cron Job,
the sender uses the verified `reports.sportscaveshop.com` domain, and sender,
recipient and reply-to values are valid mailboxes.

If the archive reports a migration requirement, apply the reporting migration
to the same Supabase database used by the web service and Cron Job.

If a delivery fails, inspect the sanitized Delivery Health message and the
provider message ID. Raw provider responses, credentials and exception traces
are intentionally not stored or displayed.

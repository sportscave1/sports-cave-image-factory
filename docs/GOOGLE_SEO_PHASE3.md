# Google SEO Phase 3 Operations

Phase 3 uses the existing encrypted Google refresh token and selected GSC and
GA4 properties. The Streamlit page only queues jobs and reads their saved
status. Google API work runs in a separate database-backed worker.

## Migration

Run once after deploying the Phase 3 code:

```bash
python run_migrations.py
```

The migration is rerun-safe and does not modify the encrypted refresh token or
the selected property identifiers.

## Durable worker

Add one Render Background Worker using the same repository, branch and
environment variables as the web service:

```bash
python google_seo_import.py worker --poll-seconds 15
```

The worker claims queued jobs with an expiring database lease. A restart leaves
the job and its last completed date in Postgres so another worker can resume it.

For a local one-job check:

```bash
python google_seo_import.py worker --once
```

## Daily Render Cron Job

Recommended schedule: `30 18 * * *` (18:30 UTC, daily).

Command:

```bash
python google_seo_import.py daily
```

The command queues GSC and GA4 independently, imports newly completed dates and
atomically replaces the previous seven completed dates. It uses the saved
encrypted refresh token, so no daily Google sign-in is required.

Do not run the historical import until the migration and Background Worker are
active. The first historical request is queued from SEO Overview and returns
immediately.

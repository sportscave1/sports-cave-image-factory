# Sports Cave SEO Growth Intelligence

## Daily Command

The existing Google SEO daily command is now the compatibility hook for the complete Growth Intelligence pipeline:

```bash
python google_seo_import.py daily
```

That command delegates to:

```bash
python seo_growth_intelligence.py daily
```

It runs one durable pipeline with these stages:

1. Connection health read
2. GSC seven-day refresh
3. GA4 seven-day refresh
4. Shopify page refresh
5. Shopify order refresh
6. GA4 transaction refresh
7. URL mapping
8. Revenue reconciliation
9. Joined reporting snapshots
10. Deterministic opportunity detection
11. Due 28/56/90-day measurements

Each stage records status in Postgres and uses existing import/Phase 4 locks and idempotent upserts. The command is safe to run repeatedly; overlapping pipeline runs are blocked by `seo_growth_pipeline_runs`.

## Render Schedule

No additional paid Render service is required by the repository.

If the existing paid morning automation already calls the Google SEO daily command, leave it as:

```bash
python google_seo_import.py daily
```

If creating or repairing the Render scheduled job outside this repo, use:

```bash
python seo_growth_intelligence.py daily
```

Recommended schedule: once each morning after Google delayed reporting data is normally available for the store timezone.

## Required Environment Variables

Set these on Render without exposing their values in logs or the UI:

- `DATABASE_URL` or the repository-supported Supabase/Postgres equivalent
- Google OAuth/client configuration already used by `google_seo.py`
- Shopify configuration already used by `shopify_sync.py`
- Optional: `SPORTS_CAVE_OPENAI_API_KEY` or `OPENAI_API_KEY`
- Optional: `SPORTS_CAVE_OPENAI_MODEL`
- Optional: `SEO_GROWTH_DAILY_SCHEDULE_LOCAL_TIME`

Emergency legacy mode for Google-only daily refresh:

```bash
SEO_GOOGLE_IMPORT_DAILY_ONLY=1 python google_seo_import.py daily
```

Use that only for temporary recovery if Phase 4 or Growth Intelligence must be bypassed while preserving GSC/GA4 daily imports.

## Manual Recovery

In Sports Cave OS, open:

SEO Overview -> Data Connections & Sync Settings -> Daily Growth Intelligence pipeline -> Run daily pipeline now

The button queues the durable pipeline. It does not expose credentials and does not run on ordinary Overview page load.

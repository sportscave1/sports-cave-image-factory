# Sports Cave SEO / Store Analytics

## Daily Command

The existing paid Render morning command remains the analytics entry point:

```bash
python google_seo_import.py daily
```

It now delegates to the analytics-only refresh command:

```bash
python seo_growth_intelligence.py daily
```

It runs one durable refresh with these internal stages:

1. Verify the additive analytics schema.
2. Refresh the recent GSC dates when GSC is configured.
3. Refresh the recent GA4 dates when GA4 is configured.
4. Read the existing Shopify/Supabase operational order ledger.
5. Refresh URL mapping and revenue reconciliation where their inputs exist.
6. Refresh joined reporting snapshots where possible.
7. Save source-specific data-through dates and refresh health.

The command does not run reports, recommendations, tasks or measurements. Each
stage records safe status in Postgres and uses the existing import locks,
idempotent upserts and the durable `seo_growth_pipeline_runs` lease. A later
failure does not delete previously saved analytics.

## Render Schedule

No additional paid Render service is required by the repository.

If the existing paid morning automation already calls the Google SEO daily command, leave it as:

```bash
python google_seo_import.py daily
```

Before the first analytics refresh after deployment, apply additive migrations:

```bash
python run_migrations.py
```

Then leave the existing paid Render morning command as:

```bash
python google_seo_import.py daily
```

For the one-time production activation after deployment, run:

```bash
python run_migrations.py && python google_seo_import.py daily
```

No cron service is added to `render.yaml`; the existing paid scheduler remains
the owner of this command. Run it once each morning after Google delayed data is
normally available.

## Required Environment Variables

Set these on Render without exposing their values in logs or the UI:

- `DATABASE_URL` or the repository-supported Supabase/Postgres equivalent
- Google OAuth/client configuration already used by `google_seo.py`
- The existing Supabase operational tables populated by Sports Cave OS
- Shopify configuration already used by the operational sync

Emergency legacy mode for Google-only daily refresh:

```bash
SEO_GOOGLE_IMPORT_DAILY_ONLY=1 python google_seo_import.py daily
```

Use that only for temporary Google import recovery.

## Manual Recovery

In Sports Cave OS, open `SEO / Store Analytics`, expand **Data Connections &
Sync Settings**, then select **Refresh analytics**. Ordinary page rendering and
filtering perform saved-database reads only; they do not call Google, Shopify or
OpenAI.

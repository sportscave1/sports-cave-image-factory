# GSC reporting snapshot investigation

Date: 2026-08-19 (Australia/Sydney)

This report separates production evidence from local implementation results. No
production data was changed, no OAuth connection was reset, and no commit,
push, deploy, or storefront request was performed.

## Production evidence

The supplied production screenshots show the exact selected Search Console
property as `https://www.sportscaveshop.com/`, last successful GSC sync at
`2026-08-18T18:37:57.587637Z`, and final data available through `2026-08-16`.
They also show these saved canonical counts:

| Canonical grain | Rows |
| --- | ---: |
| Property totals | 15 |
| Queries | 2,674 |
| Pages | 2,014 |
| Query/page | 2,543 |

At the same time, SEO Overview showed no compact snapshot, unavailable metrics,
and zero saved query rows. This proves that saved GSC data reached canonical
storage but stopped before the compact interactive read model.

Render's production topology is one Oregon web service, one Oregon worker
running `python google_seo_import.py worker --poll-seconds 15`, and one Oregon
daily cron running `python google_seo_import.py daily` at `30 18 * * *`. The
2026-08-18 cron ran from approximately 18:30Z to 18:47Z; the saved GSC sync time
falls inside that execution. Render logs did not expose per-stage row counts or
a saved snapshot error.

A new live database audit and current controlled Google API request could not be
run because this workstation has no production database URL and the available
Render shell did not have an authenticated SSH key. The read-only command is:

```text
python scripts/audit_gsc_connection_and_data.py --end-date 2026-08-16
```

It redacts OAuth credentials and now reports raw/canonical/compact counts,
snapshot history, source and snapshot revisions, exact property, and small
property/query/page/query-page Google probes.

## Root cause

`PostgresSEOInteractiveReader.reporting_context()` required a completed
`seo_reporting_snapshot_runs` record with non-null `common_reporting_date`.
The snapshot builder returned early without building compact tables when that
common date was null.

`common_reporting_date` is the minimum date across GSC, GA4 landing-page data,
Shopify state, GA4 transactions, and revenue reconciliation, and its surrounding
health state also depends on URL mapping. Pure GSC reporting was therefore
incorrectly blocked by unrelated analytics, mapping, and revenue readiness.

The builder also read the legacy GSC tables while the repaired import pipeline's
authoritative source is the exact-property canonical v2 table set. Normal
imports currently dual-write, so that mismatch was not sufficient by itself to
explain the screenshot, but it made snapshot repair fragile.

The first broken boundary was:

```text
Google API -> saved canonical GSC rows -X-> compact seo_reporting_* snapshot
```

## Local repair

The local implementation now:

- uses an independent `gsc_reporting_through_date` and GSC source revision;
- builds compact property, query, page, and opportunity rows directly from
  final, complete, `web` canonical v2 rows for the exact saved `siteUrl`;
- preserves Google's exact property identifier and does not combine URL-prefix,
  `www`, non-`www`, and domain properties;
- calculates CTR from aggregate clicks/impressions and position from saved
  impression weight;
- serves the last completed GSC snapshot as stale if a newer revision build
  fails, instead of blanking the workspace;
- queues an idempotent replacement whenever a completed GSC import advances the
  canonical revision;
- adds a durable, expiring, single-worker repair lease with bounded retries;
- adds a background-only **Sync / Repair SEO Data** action;
- backfills compact tables from existing canonical rows through an additive,
  idempotent migration without deleting canonical history;
- reads GSC landing pages independently of Shopify URL mapping and adds GA4
  sessions only as optional enrichment;
- records safe source/snapshot/repair health fields without credentials; and
- keeps Streamlit reporting database-only and makes zero public storefront
  requests.

The repaired chain is:

```text
Google API
  -> exact-property canonical final GSC rows + revision
  -> durable queued/leased compact snapshot repair
  -> GSC property/query/page/opportunity compact tables at the GSC watermark
  -> last-good database-only reader
  -> SEO Overview and subpages
```

GA4 and Shopify dates remain available for combined and revenue enrichment but
no longer decide whether pure GSC views are available.

## Verification

- Focused GSC/SEO/storefront safety suite: 182 tests passed, 1 skipped.
- Full repository suite: 1,999 tests; 73 failures and 19 errors, identical to the
  pre-existing baseline, with 2 skipped.
- `git diff --check`: passed.
- `python scripts/validate_render_topology.py`: passed; the canonical primary
  service remains unchanged.

Production compact row counts, the latest saved snapshot error, a current token
probe, and final live Overview metric values remain intentionally unclaimed
until the local changes are reviewed and an authenticated read-only production
audit can be run. No values were fabricated or substituted with zero.

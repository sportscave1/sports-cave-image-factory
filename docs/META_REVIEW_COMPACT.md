# Compact Meta Review

The live review opens with campaign metadata and campaign-level Insights. The
overview does not fetch ads or creatives. Its reporting period is explicitly
labelled **Available Meta history** (`date_preset=maximum`); the compact screen
has no hidden user date filter.

- Newest sorts by start time, falling back to creation time.
- ROAS and Purchases sort descending, with unavailable values below real zero.
- Missing metrics display as an em dash; numeric columns retain numeric sorting.
- Clicking a campaign cell or selecting its row opens a responsive dialog.
- Only that campaign's ads, creatives and ad-level Insights are loaded, using
  the existing brief live cache. Refresh From Meta invalidates the live cache.
- The dialog contains a compact summary, thumbnail comparison table and existing
  winner controls. Selecting an ad opens its full original details.
- Supabase selections, image persistence and the Creative Refresh handoff retain
  their existing paths. The winner engine, Creative Refresh and Posting are unchanged.

The overview uses the existing read-only Graph client and configured account/API
version: campaign metadata plus `/{ad_account_id}/insights?level=campaign`, with
unified attribution enabled and cursor pagination. No schema migration is needed.

## Local validation

185 tests passed across Meta Review, table helpers, live reads, winner refinement,
Creative Refresh and Posting handoffs. Python compilation and `git diff --check`
passed. A local browser fixture verified campaign-cell selection, wide dialog,
compact rows and native missing-value placeholders. No live Meta mutation,
production database operation, push or deployment was performed.

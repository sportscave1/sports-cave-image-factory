# Published review count and rating synchronization

The product title and reviews widget share the OS published-review total and rating, including published Shop imports. Pending/archived reviews are excluded. These remain store-wide totals, matching the existing widget.

Removed hard-coded 209/4.8/4.82 placeholders. Initial loading reserves the text width, then uses the existing shared feed. A small summary-only endpoint provides a single database snapshot with count, average, histogram and timestamp, cached for five seconds. Visible pages refresh every 30 seconds and refresh when returning to an old tab. Older responses cannot overwrite newer totals. Temporary errors retain the last good value with a bounded retry. No hidden-tab polling or extra customer data in summary responses.

Release theme files are under `shopify/reviews/releases/20261127-count-sync`. Upload only those three files to main theme 190889230643 after comparing remote files with the fresh baseline; do not publish the outdated connector theme snapshot. Uniform Verified buyer badges remain unchanged.

Validation: 55 focused Python tests passed with disposable SQL, including pending/published/archived Shop transitions; four browser tests passed against the exact minified release asset (two unrelated form cases skipped). Browser coverage includes shared count/rating updates, fractional stars, stale responses, network errors, lifecycle refresh, moderation decreases, AU/US badges. All three generated theme files passed Shopify validation; Render topology passed. Synthetic fixtures only; no test customer review or reward email was created.

Automatic refresh is bounded by Shop ingestion/publishing, five-second summary caching, and the visible-page 30-second refresh interval. Offline clients retain their last successful totals until reconnection.

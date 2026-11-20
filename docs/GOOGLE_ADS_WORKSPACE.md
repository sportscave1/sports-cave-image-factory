# Google workspace

Ads / Google is a private reporting page. It preserves existing Ads navigation and
requires both Ads page access and financial-reporting access before reading data.
It never creates or changes campaigns, pixels, consent, budgets or customer orders.

The page includes dated campaign setup, weekly platform claims, a separate
exclusive Shopify journey ledger, tracking evidence, research prompts and prepared
copy. Source status, dates and attribution basis remain visible. Manual Google Ads
figures are never relabelled as a current API connection.

## Existing source connections

Refresh connected data uses the existing Google reporting client (GA4 purchase
sessions by session source / medium), the read-only stored Shopify order aggregate
and fully paginated Meta Insights. GA4 must select the audited property. Each source
can independently be unavailable. Stored Shopify processed-date totals are labelled
separately from the scheduled review's Shopify created-date journey ledger.

## Weekly publication

The authenticated connector exposes submit_google_ads_review,
get_google_ads_reviews and get_google_ads_reporting. These use existing owner
scopes; the publisher independently rechecks current owner, session version and
Google reporting access. The read tool takes a completed Thursday as date.

Installed connector catalogs can continue using submit_daily_home_brief with
kind=meta and edition.destination=ads_google until their next tools/list refresh.
That explicit destination is intercepted before the Home brief handler and is never
published to Home. The compatibility path has the same independent Google owner
check as the dedicated tool.

The existing hosted brief worker calls the separate Google publication queue.
Accepted submissions are idempotent by week/revision. Different content for an
existing week/revision is rejected. Corrections use the next revision and preserve
earlier reports. Publication is complete only after the saved edition's digest
matches the accepted submission. Retry publication failures; reject revoked
sessions and invalid reports. Missing publications can be restored by resubmitting
the exact accepted edition. The worker does not need the desktop or browser to
remain open once a report has been accepted.

No schema migration, new credentials, exposed tables or grants are required.
Storage reuses the server-only app_settings connection and dedicated
google_ads_review: / google_ads_review_queue: keys.

## Edition contract

Required: date (Sydney publication day), period_start (Friday), period_end
(Thursday), currency (AUD), summary, platforms, channels, tracking, findings,
actions, sources. Optional: destination=ads_google, revision (1..99).
The publication day must follow the completed week and be within fourteen days.

Each platform has source (google_ads/meta_ads/ga4/shopify), status
(verified/partial/unavailable), period_start, period_end, currency, spend,
purchases, value and basis. Platform dates/currency must match the review.
Unavailable metrics are null. Partial values remain labelled known subtotals.

Each exclusive channel has channel, orders and value. Use the fixed channel
names in google_ads_reviews.CHANNELS. Complete exclusive counts and values must
reconcile to the verified Shopify summary; never reconcile them by adding
overlapping platform claims.

Each tracking check has label, status (live/verified/open/prepared), detail and
checked_on. findings, actions and sources are bounded lists of plain-text strings.
Keep customer contacts, individual journeys, credentials and HTML out of reports.
Historical audit findings may cover another period only when explicitly dated in
their text; the structured platform metrics always cover the weekly period.

## Verification

Synthetic PostgreSQL tests cover idempotency, corrections, exact readback, missing
publication recovery, transient failures and revoked access. MCP tests exercise the
installed-catalog compatibility route and scope boundaries. Source tests cover
full Meta pagination and unknown metrics; Streamlit AppTest renders the page and
checks that denied users cannot read storage. No production data or live marketing
writes are used in tests. Production verification checks the canonical Render
revision, existing service health and a real authorised report publication.

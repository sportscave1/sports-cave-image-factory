# Google workspace

Ads / Google is a private reporting page. It preserves existing Ads navigation and
requires both Ads page access and financial-reporting access before reading data.
It never creates or changes campaigns, pixels, consent, budgets or customer orders.

The page includes dated campaign setup, weekly platform claims, a separate
exclusive Shopify journey ledger, tracking evidence, research prompts and prepared
copy. Source status, dates and attribution basis remain visible. Manual Google Ads
figures are never relabelled as a current API connection.

## Google Ads automatic reporting connection

The optional Ads connection extends the existing encrypted Google OAuth grant.
Only the explicit /api/os/google/ads/connect route requests the standard adwords
scope; ordinary SEO connection requests retain their original read-only scopes.
The callback binds purpose to the single-use server-side OAuth state and requires
the Ads grant before saving a changed authorisation. An administrator must approve
Google's consent. Google has no separate read-only Ads OAuth scope; this adapter
contains only fixed SearchStream reporting requests and no mutation endpoints.

Enable Google Ads API in the same Cloud project that owns the existing OAuth
client and obtain Explorer or higher production access. Google sunset developer
tokens on 9 September 2026; do not request a new manager account/developer token.
No new client secret or database migration is needed. If an existing account
hierarchy requires it, GOOGLE_ADS_LOGIN_CUSTOMER_ID can identify that manager;
it never creates an account link.

google_ads_api_reporting fixes customer 6581121605 and campaign 24420240881,
uses API v26, validates AUD/account identity and completed account-timezone dates,
and reads campaign settings, delivery and primary PURCHASE conversions. Purchase
values use interaction-date attribution and can differ from store order-date
revenue. Fractional credit is retained. Cost micros are converted to AUD once.
Zero omitted protobuf fields represent zero only after a successful full response;
an authentication/API failure returns an explicit status without fabricated totals.
The observed budget is compared with A$20/day but is never changed.

On opening the Overview, campaign reporting loads automatically with a 15-minute
cache keyed to connection identity and requested dates. The dated weekly archive
remains separate. Refresh Google Ads clears that process cache. Connected-source
refresh and get_google_ads_reporting include Ads. For installed catalogs without
the new tool, get_growth_analytics also returns a google_ads member after checking
Ads Google page access independently. It reads the seven days ending on date.
The scheduled weekly review can use these fresh API figures and publish through
the existing verified archive; absent access remains explicitly unavailable.

Official setup references: https://developers.google.com/google-ads/api/docs/oauth/cloud-project
and https://developers.google.com/google-ads/api/docs/api-policy/developer-token .

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

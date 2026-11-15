# Meta Review: local implementation and operational notes

## Scope and verified root cause

The old `ads_meta_review_page._load_review(days)` synchronously called account,
campaign, ad-set, ad and summary-insight endpoints on page render. Each paginated
edge could take 25 requests at a 30-second request timeout. The five calls ran
serially, a five-minute Streamlit cache was the only storage, and only
`MetaAdsApiError` was caught. There was no overall deadline, database read path,
winner decision, or Creative Refresh handoff. This is the confirmed code-level
cause of long waits without useful content. No claim is made that a particular
production token/network incident was observed during this local task.

The old metric helper also added overlapping purchase aliases and treated missing
metrics as zero. The replacement selects one action scope and preserves unknowns.

No production Meta request, database migration, git commit, push or deployment was
performed for this implementation. No live ad objects are changed by Meta Review.

## Files and architecture

- `ads_meta_review_page.py`: Supabase history, date/search/status/target-market
  controls, campaign summaries, paginated original creative cards, winner board,
  persistent manual choices and saved handoff reopening.
- `meta_review_analysis.py`: pure action normalization, commercial metrics,
  original creative extraction, deterministic evidence decisions and component
  provenance. No network, LLM or database calls.
- `meta_review_sync.py`: explicit GET-only reporting coordinator using the
  existing `meta_ads_client._request`, credentials and configured API version.
- `meta_review_store.py`: existing server-side Postgres connection; existing Meta
  reporting tables, sync logs, action logs and product mappings. Reporting writes
  commit together. No application startup DDL.
- `meta_review_handoff.py`: permanent selected image and source-decision storage,
  hydration into the existing Creative Refresh copy/product inputs and reference
  panel. It does not publish or replace the generator.
- `ads_page.py`: a small hook shows/hydrates a Meta Review reference before the
  existing manual/campaign winner picker. Existing prompt, CSV, image slots,
  save, POST NOW, and Posting modules are unchanged.
- `migrations/20260912235112_meta_review_reporting.sql`: three additive tables
  and reporting lookup indexes. `run_migrations.py` pins the reviewed SHA.
- `tests/test_meta_review.py`, `tests/meta_review_sql_fixture.py`,
  `tests/meta_review_postgres.mjs`: pure, UI, mocked transport and real isolated
  PostgreSQL regression checks. One existing `test_meta_posting.py` source
  assertion now checks the stored-history architecture instead of expecting the
  removed eager Meta summary call.

## Database and migration

Reuse these existing tables: `meta_ad_accounts`, `meta_campaigns`, `meta_adsets`,
`meta_ads`, `meta_creatives`, `meta_ad_insights_daily`, `ads_product_mapping`,
`ads_sync_logs`, `ads_action_log`. No duplicate campaign or reporting store is
created. Existing `meta_creative_tags` and `ads_analysis_exports` are not needed
for this path and remain untouched.

New tables:

| Table | Purpose |
|---|---|
| `meta_review_asset_daily` | Separate daily asset breakdown rows keyed by account/ad/date/breakdown/asset. They are never added to base totals. |
| `meta_review_creative_observations` | Append-only creative JSON observations deduplicated by account/ad/content hash, so later syncs do not erase previously observed copy/assets. |
| `meta_review_media` | Content-addressed original selected winner image bytes and MIME type, maximum 8 MiB per image; survives Meta URL expiry and application restarts. |

All three new tables enable RLS and revoke direct `anon`/`authenticated` access.
They use the existing privileged server-side database connection, never a browser
service credential. No new infrastructure or storage account is required. Images
are archived only for an explicit winner handoff, not for every account image.

The existing Ads Intelligence v1/v2 migrations are prerequisites. On an existing
Sports Cave database with those installed, the exact later-approved command is:

```powershell
.venv/Scripts/python.exe run_migrations.py --only 20260912235112_meta_review_reporting.sql --check
.venv/Scripts/python.exe run_migrations.py --only 20260912235112_meta_review_reporting.sql
```

Only `--check` was run against the repository in this task. SQL was executed only
inside isolated PGlite. The new migration is SHA-reviewed but deliberately not
added to automatic production startup deployment, because deployment and
production schema changes were not authorized for this task. No unrelated
allocator migration needs to run. Missing schema yields an actionable UI error.

## Sync, history and failure behavior

Opening the page reads the selected account's Supabase history, with a 60-second
display cache. No Meta read happens on import, global startup or page open.
`Sync Meta` is the explicit external request boundary.

Sync reads account metadata; accessible active, paused, archived/deleted and
completed campaigns; ad sets (including targeting); ads and nested creatives;
daily insights; and optional asset breakdowns. It uses cursor pagination through
the original Graph path rather than following arbitrary token-bearing `next`
URLs. It limits each edge to 50 pages and the Meta phase to 180 seconds plus at
most one in-flight 30-second request. A transient 502/503/504 GET can retry once.
Authentication/permission/rate-limit errors remain visible. Unsupported optional
fields/breakdowns are reported without inventing missing data. Oversized syncs
fail explicitly instead of silently truncating.

Required reads finish before reporting writes begin. Campaigns, ad sets, ads,
creatives, daily/asset results and the success log commit in one transaction.
Failure rolls back that transaction. Existing rows absent from a later response
are retained; they are historical observations, not proof of current delivery.
An account advisory lock serializes commits, and an older started sync cannot
overwrite a newer successful sync. Each SQL statement has an eight-second timeout.
Upserts are batched in groups of 100 rows, with duplicate conflict identities
coalesced before SQL execution. The reporting write phase has a 90-second budget
checked between batches, plus at most one in-flight eight-second statement.
Failure logs are separate and sanitized. A missing completion marker is visible
as running/interrupted, not a permanent spinner.

Sync logs include source, date range, start/end, status, error, row counts,
campaign/ad-set/ad/daily/asset counts, account ID, API version and capability
warnings. Account and object metadata keep stable IDs, names/statuses, original
JSON, creation/update timestamps and sync timestamps. Campaign objective is
stored. Creative observations preserve the original available payload.

Daily reporting retains date, account/campaign/ad-set/ad identity, raw actions,
raw action values and delivery fields. It also maintains compatible normalized
columns for the existing reporting readers. Meta Review recomputes from raw
reporting payloads to avoid historical fake-zero defaults in those columns.

The UI supports 7/14/30/90 days, custom dates and available stored lifetime.
Campaign search/status and ad-set target-country filters apply to stored data.
Target country is explicitly not country-attributed revenue. Insights whose
objects are no longer readable still appear with their actual recorded names and
results, and unavailable creative is shown as unavailable. Cards are paginated
12 per page; winner comparison uses the full selected campaign, not only the
visible page. Oversized stored histories ask for a shorter range instead of
truncating invisibly.

## Metric definitions and limitations

- Purchases: first available, valid reporting scope from `omni_purchase`,
  `purchase`, pixel purchase, then onsite web purchase. Overlapping scopes are
  never summed.
- Add to cart: first valid omni/generic/pixel add-to-cart action.
- Initiate checkout: first valid omni/generic/pixel checkout action.
- Purchase value: the corresponding available purchase action-value reporting
  aliases; values are Meta attribution, not absolute Shopify revenue.
- ROAS: total known Meta purchase value divided by total spend. If value is not
  supplied, use reported `purchase_roas`; multiple reported ratios are
  spend-weighted, never naively averaged. No purchase value is manufactured from
  the ratio.
- CPA/cost per ATC/cost per checkout: spend divided by the corresponding known
  action count. A zero denominator is unavailable, not a zero cost.
- Link CTR: inline link clicks / impressions × 100. All-click CPC and cost per
  link click remain distinct. CPM uses spend / impressions × 1,000.
- Reactions, engagement, comments, shares, saves, video views and outbound clicks
  use available action entries. Absent/malformed/nonfinite values stay unknown.
- Optional Instant Experience opens, starts and outbound clicks use the API's
  explicit fields. Unsupported fields show `—`; they are not guessed from clicks.
- Daily counts/spend can be summed. Unique reach cannot be summed across days or
  ads, so multi-report reach/frequency display unavailable. Highest daily
  frequency is labelled separately and can support fatigue investigation.
- If any contributing report lacks a metric, its aggregate remains unknown
  rather than silently reporting a partial number as the complete total.

## Actual creative and attribution

The extractor retains exact original body/headline/description strings, including
paragraphs. It reads link/video/photo/template story data, CTA/destination,
carousel child images/headlines and all available asset-feed bodies, titles,
descriptions, images and videos. Dynamic image hashes without URLs are resolved
through the same account's `adimages` GET. It uses an original thumbnail if a
full image is unavailable. No placeholder artwork or copy is generated.

The Meta SDK lists `body_asset`, `title_asset`, `description_asset`, `image_asset`,
`video_asset`, and `call_to_action_asset`. Each is requested independently;
available matching results are labelled **DIRECT META ASSET RESULT**. A reported
asset may still lack purchase metrics. Unsupported/unmatched components are
labelled **INFERRED FROM WINNING ADS**, never direct purchase attribution.

Actual account support was not tested live during local implementation. Dynamic
assets may be exposed without performance breakdown permission/support. The
normal view does not show raw creative JSON. A complete dynamic/carousel ad can
have multiple candidates; the operator selects its reference assets explicitly.
That selection is not described as a proven served combination.

Creative snapshots mean “observed at sync,” not a reconstruction of what Meta
served months earlier. The previous-observations panel does not attach current
ad metrics to a specific old revision. Already expired remote image URLs may
need a new sync; a previously saved handoff can reopen its permanent image
without relying on that URL.

## Winner and confidence rules

The engine is deterministic and has no OpenAI dependency. Defaults are evidence
heuristics, not claimed Sports Cave profitability economics. Environment settings:

| Environment variable | Default | Meaning |
|---|---:|---|
| `META_REVIEW_MIN_PURCHASES` | 3 | Repeat purchase evidence floor |
| `META_REVIEW_HIGH_PURCHASES` | 10 | High evidence category |
| `META_REVIEW_MIN_SPEND` | 0 | Unset dollar floor; configure in account currency if wanted |
| `META_REVIEW_TARGET_CPA` | 0 | Unset; required for an economics-based kill recommendation |
| `META_REVIEW_TARGET_ROAS` | 0 | Unset; otherwise compare within the campaign |
| `META_REVIEW_POOR_SPEND_MULTIPLE` | 3 | Test-spend allowance relative to configured target CPA |
| `META_REVIEW_FATIGUE_FREQUENCY` | 3 | High daily-frequency evidence threshold |
| `META_REVIEW_FATIGUE_CHANGE` | 0.25 | Relative CTR decline or CPA increase |
| `META_REVIEW_MIN_CLICKS` | 50 | Click evidence threshold for downstream investigation |

Low confidence means inadequate purchase/spend evidence; Medium means the minimum
threshold is met; High means repeated purchases meet the higher threshold.
These are not statistical confidence intervals. A $5/one-purchase ROAS spike is
“NEEDS MORE SPEND,” not an automatic winner.

Commercially strong ads need known ROAS/CPA and sufficient purchases/spend, and
must meet configured targets or within-campaign median ROAS/CPA comparisons.
Qualified winners rank by purchases, then ROAS, then CPA, then stable ad ID.
Without an explicit ROAS target, at least two purchase-qualified ads are required
for a meaningful campaign comparison; a lone low-ROAS ad cannot crown itself.
Engagement cannot win an ad. Checkout, ATC, CTR and CPC appear as supporting
evidence in the explanation. No winner is forced if no ad qualifies.

Labels: INSUFFICIENT DATA, NEEDS MORE SPEND, WATCH, WINNER — REFRESH THIS,
SCALE CANDIDATE, KILL CANDIDATE, LANDING PAGE / PRODUCT ISSUE, REFRESH CREATIVE.
Scale requires high evidence and explicit economic targets. Kill requires a
configured CPA allowance and explicit zero purchases. Landing-page investigation
requires meaningful clicks and explicit zero ATC; it also mentions tracking and
message-match uncertainty. Fatigue compares earlier/recent halves of available
daily observations (at least three earlier observations), meaningful earlier
purchases, deteriorating CTR/CPA and high daily frequency. It does not claim
causality or take action in Meta.

## Selections and downstream workflow

The overall winner can be overridden by selecting an ad. Image/body/headline
candidates can be selected independently. Qualified direct asset evidence is
preferred; otherwise the selected winning ad supplies clearly labelled inferred
references. Saving a selection appends to `ads_action_log` with account,
campaign, date/market scope, component keys and operator. A reload restores the
saved selection for that scope.

**Refresh Winning Ad** requires image/text/headline from the same selected ad.
**Build From Best Components** allows cross-ad sources and prominently warns that
the new combination is untested. Both packages retain source IDs, campaign/name,
mapping, market, verbatim copy, image identity, description, CTA, destination,
metrics, confidence, explanation and selected dates.

Handoff first validates/downloads the chosen original Meta CDN image (bounded
size/time, no arbitrary redirects), persists its hash/bytes, saves the source
package in Supabase, then navigates to Creative Refresh. Copy is hydrated once so
later manual edits survive reruns. Product/market inputs are populated where
mapped; unmapped references do not inherit another product accidentally.

The original image is displayed and downloadable in Creative Refresh. The
existing workflow asks the operator to attach the reference image and canonical
artwork to ChatGPT; this integration supplies that exact file but does not invent
a second image-generation or publishing system. Existing three sibling outputs,
saved packages, CSV compatibility, image slots, Dropbox handoff, POST NOW and
Posting remain intact. Saved Meta Review handoffs can reopen after session loss.

## Validation and local testing

Focused tests cover normalization, missing values, exact copy/assets, dynamic and
carousel candidates, all decision classes, confidence, provenance, failed sync,
pagination/deadline, historical reads, actual Streamlit selection/save/navigation,
handoff modes, identity hydration and no Meta write transport.

The PostgreSQL runner applies the existing migrations plus the new migration
twice, runs SQL emitted by the actual repository writer, verifies idempotent
syncs, commits/rollback, normalized funnel values, creative observations,
persistent selections/images after an engine restart, RLS and untouched edition
guard state. It never connects to production.

Commands:

```powershell
.venv/Scripts/python.exe -m unittest tests.test_meta_review
$env:PGLITE_MODULE='C:/Users/hello/AppData/Local/Temp/sc-edition-local/node_modules/@electric-sql/pglite/dist/index.js'
& 'C:/Program Files/nodejs/node.exe' tests/meta_review_postgres.mjs
```

Additional regression suites include Meta Posting, Carousel, Collection
diagnostics/crops/templates, Creative Refresh, winner refinement, saved Posting
handoffs, Ads Intelligence, Ads page/image workflow and Posting CSV import.
Final counts are recorded in the task's final response.

Use a local database with the existing reporting prerequisites and new migration
for end-to-end local testing. Existing `DATABASE_URL` aliases and
`META_AD_ACCOUNT_ID` are required to load reporting history. Explicit sync also
requires the existing `META_ACCESS_TOKEN` with access to the ad account and
reporting (`ads_read` or equivalent existing permissions); keep the existing
`META_API_VERSION` (currently defaulting to v26.0). Asset-level and Page/creative
availability is subject to the token/account/format. No new Meta write permission,
OpenAI key or storage credential is required. No additional production permissions
were exercised or proven in this local test.

**SAFE FOR NATHAN TO TEST LOCALLY: YES, with an isolated database and the migration.**
Production rollout remains a separate approval step.

## Primary references checked

- [Meta SDK Insights fields/breakdowns](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/adsinsights.py)
- [Meta SDK account GET parameters](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/adaccount.py)
- [Supabase RLS](https://supabase.com/docs/guides/database/postgres/row-level-security)

The Meta prose breakdown page returned HTTP 429 during investigation, so the
current official generated SDK was used to confirm parameter/field names. Live
capability detection remains authoritative for a particular account.

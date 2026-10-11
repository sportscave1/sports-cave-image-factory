# Universal Personalised Email Templates V2

Local implementation and verification — 11 October 2026.

**Ready for local review, not approved for production or activation.** No operator
drafts or production records were changed. No email was sent, flow activated,
extension published, migration run against production, file staged, commit made,
push or deployment performed. Welcome, Post Purchase and Win Back remain subject
to the existing Draft activation lock. Win Back Email 4 remains disabled.

## 1. V1 implementation review

Read [the V1 report](UNIVERSAL_PERSONALISED_EMAIL_TEMPLATES_V1.txt), inspected the
dirty working tree, shared composer/library/rendering hooks, lifecycle definitions,
Shopify adapter, Edition Ops allocation reader, account extension and separate
Campaigns V8/product-tagging implementation before editing.

V1's four reusable designs, HTML marker format, compact Personalise Image control,
global header/footer selectors, saved versions and renderer remain. V2 does not
add a composer, interest database, scheduler or sender. V1 markers remain editable
and compatible with existing saved templates. Static/dynamic blocks still coexist.

The main V1 gap was recommendation matching by `productType` and `interest:` tags.
V2 replaces that with the shared standardized product sport mapping and verified
buyer-segment projection. Purchased artwork still uses the exact Shopify order,
customer and line; allocation reads remain read-only and exact. Existing timing,
consent, suppression, unsubscribe, purchase exits, ledger and publication logic
are unchanged. No automatic rewrite of the original ten drafts was performed.

## 2. Exact source of customer sport interests

`crm_collector_sports.py` reads the existing server-side projection through
`store.state(crm_buyer_segments.snapshot_key(shop))`. Its key is scoped to the
connected Shopify namespace. A timestamp must be neither future-dated nor older
than the synchronizer's 300-second TTL. Customer membership is matched by exact
Shopify customer GID; emails, names and browser-supplied interests are not used.

Bindings and definitions come from the existing background synchronizer. The
resolver does not start synchronization, enumerate customers, create segments,
write customer tags or keep a second interests table. It accepts only recognized
buyer names with the inspected purchase-tag query, optionally with the exact
corresponding `SC_HIST_*` alternative. A renamed saved ID remains bound through
the existing synchronizer. Changed/broadened/unrecognized definitions supply no
interest. A failed or stale projection supplies no membership-derived interest.

Verified qualifying, paid, non-cancelled, non-refunded purchases provide the
fallback and additional interests. Products are fetched by exact IDs and their
current standardized Shopify tags are interpreted through `product_sport_tags.TAGS`.
Already fetched ownership products are reused. At most 50 additional product IDs
are read for positive classification evidence; incomplete classification shows
fewer recommendations. This classification subset is never used as proof that
ownership is complete. Product types, athlete names, prose, direct customer sport
tags and legacy `interest:` tags do not establish interests.

Complete ownership IDs are collected separately from the already verified lifecycle
order history, with at most eight extra line-page reads. Missing history authority,
repeated cursors or budget exhaustion omit recommendations. Identity mismatches
are rejected before the optional fallback boundary. All previously purchased IDs
are excluded conservatively, including IDs on refunded orders; refunded purchases
do not supply fallback interests. Shopify's saved segment definitions can still
include historical members according to their own rules.

## 3. Integration with the 28 Shopify buyer segments

Inspected [the actual saved observation](shopify-buyer-segments-observed.json)
dated 11 October and [the existing V8 sync report](EMAIL_CAMPAIGNS_LOCATION_SEGMENTS_V8.md).
That observation contains the exact IDs and full queries. It is evidence only;
no store-specific IDs were hardcoded into the resolver. V2 did not repeat a live
Shopify read or independently verify a deployed application's access.

The first 23 segments use `products_purchased MATCHES (tag CONTAINS '<tag>') OR
customer_tags CONTAINS '<matching SC_HIST tag>'`. The five marked *purchase only*
have no historical customer-tag alternative.

| Buyer segment | Authoritative product tag |
|---|---|
| AFL | SC_SPORT_AFL |
| Basketball | SC_SPORT_BASKETBALL |
| Baseball | SC_SPORT_BASEBALL |
| Combat Sports | SC_SPORT_COMBAT |
| Cricket | SC_SPORT_CRICKET |
| Football | SC_SPORT_FOOTBALL |
| Golf | SC_SPORT_GOLF |
| Horse Racing | SC_SPORT_HORSE_RACING |
| Ice Hockey | SC_SPORT_ICE_HOCKEY |
| NFL | SC_SPORT_NFL |
| Olympics | SC_SPORT_OLYMPICS |
| Rugby League | SC_SPORT_RUGBY_LEAGUE |
| Rugby Union | SC_SPORT_RUGBY_UNION |
| Surfing | SC_SPORT_SURFING |
| Tennis | SC_SPORT_TENNIS |
| WWE | SC_SPORT_WWE |
| Athletics | SC_SPORT_ATHLETICS |
| Motorsport | SC_SPORT_MOTORSPORT |
| Formula One | SC_SPORT_FORMULA_ONE |
| NASCAR | SC_SPORT_NASCAR |
| V8 Supercars | SC_SPORT_V8_SUPERCARS |
| MotoGP | SC_SPORT_MOTOGP |
| Apparel | SC_CATEGORY_APPAREL |
| Motocross — purchase only | SC_SPORT_MOTOCROSS |
| Rally — purchase only | SC_SPORT_RALLY |
| Motorcycle Road Racing — purchase only | SC_SPORT_MOTORCYCLE_ROAD_RACING |
| Rally Raid — purchase only | SC_SPORT_RALLY_RAID |
| IndyCar — purchase only | SC_SPORT_INDYCAR |

All 28 observed definitions are tested. Apparel is recognized but intentionally
does not generate artwork interests. Historical membership is accepted only from
the authoritative projection, never by guessing that a customer's old tags mean
the same thing as product tags.

## 4. Recommendation ranking and fallback

1. Combine verified segment and qualifying-purchase sports. When a precise
   motorsport is present, remove its redundant broad Motorsport interest for
   ranking; WWE similarly takes precedence over Combat.
2. Exact sports rank first. A precise motorsport can next match parent-only
   Motorsport artwork, but never a product tagged with a different precise
   motorsport merely because it also has the parent tag. V8 Supercars stays exact:
   no separate verified Australian Motorsport tag exists in the shared mapping.
3. Multiple independent sports remain eligible. Stable selection order breaks
   relevance ties. Unclassified or unrelated candidates are omitted.
4. Discover up to four deterministic tag groups, 12 IDs each, in one GraphQL
   operation; precise groups precede optional parent fallback. The shortlist is
   bounded at 48 IDs. More than four interests can therefore yield fewer choices.
5. Reverify each candidate's current tags, publication, recipient market,
   saleability, title, URL and image in one fresh batch. Exclude owned IDs and
   deduplicate recommendations across blocks, including repeated markers.

An explicit collection never silently falls back to a different collection.
Operator-selected artwork/collections can serve a subscriber with unknown interests
and verified empty purchase history. No unconfigured default interest or hero is
invented. Existing purchases with no verifiable sport yield neutral copy/CTA.
Unknown recipient country, unavailable Shopify data or insufficient matches also
yield fewer/no cards. Optional recommendation failure preserves purchased cards
already verified in that resolution.

Verified New Releases retains V1's current-product creation-within-30-days filter;
this is not proof of a marketing launch date, and stage copy makes no new-release
claim. Bestsellers require an explicitly selected collection's Shopify
`BEST_SELLING` order. No stage asserts popularity, stock remaining, licensing,
autographs, discounts or a fixed edition size.

## 5. Lifecycle mapping and individual readiness

Every row is **local fixture verified only**. No row is staging-verified or
approved for sending. Original saved drafts are unchanged and may still contain
their old copy until an operator explicitly applies a reviewed starter.

| Email | Template/source | Preserved timing | Readiness and prerequisite |
|---|---|---|---|
| Welcome 1 | A / Featured Collection | Subscription + 0 days | Local ready; select an approved hero/collection, otherwise neutral CTA |
| Welcome 2 | C / Related | Subscription + 3 days | Local ready; verified interest or neutral fallback; no purchase presumed |
| Welcome 3 | C / Related | Subscription + 7 days | Local ready; same authority/fallback; no purchase presumed |
| Post Purchase 1 | B / Purchased, maximum 2 | Payment + 1 day | Local ready; verify order access and allocation data in staging; no shipped claim |
| Post Purchase 2 | B / Purchased + My Collection | Delivery + 7 days; existing configured fulfilment fallback unchanged | Local ready; account extension and truthful pending/available states require separate staging verification |
| Post Purchase 3 | C / Related, maximum 3 | Payment + 45 days; existing fulfilment requirement | Local ready; complete ownership, sport tags and recipient market needed for cards |
| Win Back 1 | D / Previous purchased artwork + related | Last purchase + 90 days | Local ready; exact prior order and complete ownership needed |
| Win Back 2 | C / Related | Last purchase + 105 days | Local ready; no unverified recent-release claim |
| Win Back 3 | C / Related | Last purchase + 120 days | Local ready; no incentive added; existing verified discount system remains operator-configurable |
| Win Back 4 | D / Review-only proposal | Last purchase + 150 days | Disabled; no selectable application action; not send-ready |

The existing 90-day Win Back inactivity/re-entry rules, purchase exits, stage IDs,
fulfilment requirements and Draft-only release lock are untouched. A fulfilment
fallback is not represented as confirmed delivery or certificate readiness.

Supported personalized card fields: Welcome 1–3 and PP3/WB2/WB3 use product image,
title and canonical product link. PP1/PP2 use exact purchased title, selected
variant label, exact variant/main product image and verified allocated edition
number when unambiguous. WB1 combines those purchased fields with recommendation
image/title/link. WB4 is review-only. No private order or certificate URL is put
in an email. Existing subject/preview variables remain `first_name`, `product_name`,
`short_product_name`, `sport_category`, `edition_number`, `discount_code` and
`discount_value`, resolved by the existing guarded resolver; V2 starters use
truthful generic subject/preview copy by default.

### Explicit operator workflow

Open an enabled lifecycle email in the existing composer, then its Templates
library. The original four V1 designs remain. V2 stage starters for that flow are
labelled **replace body**. Clicking **Use** deliberately replaces middle content,
subject and preview text, including old recommendation blocks. It preserves the
global header/footer, audience, discount configuration and timing. The existing
save path archives the prior complete lifecycle definition in
`crm_lifecycle_revisions` and rejects stale revisions. Merely viewing the library
does not save anything. The action is fixture-tested through the real library and
store methods, not a separate apply engine.

Review the result, use **Personalise Image** for source/count/approved selection,
and use existing desktop/mobile previews. Apply no stage starter to Win Back 4.
Original reusable V1 designs retain their existing insertion behavior (append
unless the body is empty); the explicit V2 stage action is the controlled whole-body
replacement. Existing template save/edit/duplicate/version behavior is retained.

## 6. Completed example previews

13 labelled synthetic examples, each at 600px and 375px: all ten stage proposals
plus neutral Welcome 2, PP2 and WB2. [Metrics](collector-email-v2/preview-metrics.json)
record image loading, natural/rendered dimensions and horizontal overflow.
26/26 captures passed. PP2 mobile and WB1 desktop were also visually inspected.

Public Sports Cave artwork comes from the V1 fixture manifest. Customers,
ownership, variant labels and allocations are explicitly synthetic. Welcome
examples say no purchase is presumed. No production customer was previewed and
no new customer-record access was introduced. Fixtures are never used at delivery.

| Stage | Desktop | Mobile | Notepad preview source |
|---|---|---|---|
| Welcome 1 | [600px](collector-email-v2/welcome-1-sample-600.png) | [375px](collector-email-v2/welcome-1-sample-375.png) | [TXT](collector-email-v2/welcome-1-sample-preview.txt) |
| Welcome 2 | [600px](collector-email-v2/welcome-2-sample-600.png) | [375px](collector-email-v2/welcome-2-sample-375.png) | [TXT](collector-email-v2/welcome-2-sample-preview.txt) |
| Welcome 3 | [600px](collector-email-v2/welcome-3-sample-600.png) | [375px](collector-email-v2/welcome-3-sample-375.png) | [TXT](collector-email-v2/welcome-3-sample-preview.txt) |
| Post Purchase 1 | [600px](collector-email-v2/post_purchase-1-sample-600.png) | [375px](collector-email-v2/post_purchase-1-sample-375.png) | [TXT](collector-email-v2/post_purchase-1-sample-preview.txt) |
| Post Purchase 2 | [600px](collector-email-v2/post_purchase-2-sample-600.png) | [375px](collector-email-v2/post_purchase-2-sample-375.png) | [TXT](collector-email-v2/post_purchase-2-sample-preview.txt) |
| Post Purchase 3 | [600px](collector-email-v2/post_purchase-3-sample-600.png) | [375px](collector-email-v2/post_purchase-3-sample-375.png) | [TXT](collector-email-v2/post_purchase-3-sample-preview.txt) |
| Win Back 1 | [600px](collector-email-v2/win_back-1-sample-600.png) | [375px](collector-email-v2/win_back-1-sample-375.png) | [TXT](collector-email-v2/win_back-1-sample-preview.txt) |
| Win Back 2 | [600px](collector-email-v2/win_back-2-sample-600.png) | [375px](collector-email-v2/win_back-2-sample-375.png) | [TXT](collector-email-v2/win_back-2-sample-preview.txt) |
| Win Back 3 | [600px](collector-email-v2/win_back-3-sample-600.png) | [375px](collector-email-v2/win_back-3-sample-375.png) | [TXT](collector-email-v2/win_back-3-sample-preview.txt) |
| Win Back 4 — disabled | [600px](collector-email-v2/win_back-4-sample-600.png) | [375px](collector-email-v2/win_back-4-sample-375.png) | [TXT](collector-email-v2/win_back-4-sample-preview.txt) |

Neutral mobile examples: [Welcome 2](collector-email-v2/welcome-2-neutral-375.png),
[PP2](collector-email-v2/post_purchase-2-neutral-375.png),
[WB2](collector-email-v2/win_back-2-neutral-375.png).
Reusable source exports: [A](collector-email-v2/collector-welcome-source.txt),
[B](collector-email-v2/collected-artwork-source.txt),
[C](collector-email-v2/build-collection-source.txt),
[D](collector-email-v2/collector-reengagement-source.txt).
All stage source exports also use `.txt`. No browser-opening HTML downloads.

## 7. Product, variant and image correctness

The exact order/customer is reread before purchased cards. The order line's
variant image is preferred only when its product identity matches that line;
otherwise the exact product main image is used. Titles/variant labels come from
the order, not a recommendation or another customer's last order. At most two
items are shown. Missing images or edition information are omitted.

Edition numbers use the existing unique, valid, identity-enforced
customer/order/product/line allocation read; there are no allocation writes.
Recommendations require ACTIVE status, current market publication, a sellable
variant, canonical public product URL and a durable image. Unknown inventory,
missing images, sold-out and unpublished candidates are omitted. Only the first
20 variants are inspected; this can omit a saleable product, never invent stock.
Existing image-format conversion and table markup retain proportions without
cropping. Temporary/signed asset URLs are rejected. Exact identities and escaped
fields prevent recipient A's rendered facts from being reused for recipient B.

## 8. My Collection and certificate findings

V1's configured `MySportsCaveCollection.jsx` still uses the authenticated Customer
Account API, not an Admin API/customer-ID lookup. Its loader follows up to 20 pages
of 50 orders, checks stable authenticated identity, unique orders and advancing
cursors, and rejects partial/error results. The existing UI retry starts a fresh
request. Eight pagination tests plus nine existing certificate/artwork tests pass.

Existing metadata with conflicting customer/order IDs or order names is filtered.
Legacy records without explicit identity fields inherit the authenticated parent
order's authority; they are not independently reverified against Edition Ops by
the extension. This existing compatibility behavior was preserved and should be
audited with approved staging metadata before release. Missing metadata produces
no certificate; a pending record without a PDF produces no invented download or
edition. No record is created, repaired, allocated or emailed.

The customer's reported “Your collection is waiting” cause is not confirmed:
pagination, missing/pending metadata, failed synchronization or permissions can
all matter. No real customer record was inspected. The pagination fix alone
cannot create an absent certificate.

PP2 says **“Once your certificate is available”**, linking only to
`https://account.sportscaveshop.com/pages/019ef355-648a-7996-8977-897320e5ffd7`.
It does not claim readiness, attach/embed/generate a certificate or add review
requests. Judge.me and existing account features are unchanged.

## 9. Performance and request counts

[Resolver measurements](collector-email-v2/resolver-performance.json) use in-memory
Shopify responses, not real network latency. For the same two-card re-engagement
fixture, explicit selection changes from 4 logical Shopify calls in V1 to 3 in
V2. Automatic selection is 4 cold / 3 warm in V2 versus 4 / 4 in V1. The new tag
discovery replaces the old cached product-type SQL shortlist; cold discovery has
a cost, while shared product reuse and cached discovery reduce repeat calls.

Discovery IDs use the existing bounded Shopify cache, scoped by store, query and
variables, for 180 seconds. Availability and classification are always fresh.
No recipient facts are stored in that discovery cache. Segment membership reuses
the existing projection and adds no Shopify call from delivery. Its database read
and at most two exact allocation reads are separate from API counts.

Worst-case logical Shopify budget remains bounded: purchase order/products 2,
ownership continuation pages 8, additional classification batch 1, at most four
selection/discovery operations, and availability batch 1 = at most 16. A discovery
operation contains up to four product-search aliases and 48 IDs. Existing lifecycle
history verification (up to 50 order pages) remains additional and unchanged.

A copied Shopify adapter gives optional artwork an 8-second between-request
deadline, at most 3 seconds per HTTP timeout and one attempt. It shares the existing
concurrency and rate-limit gates; waiting for a slot is bounded. The ordinary
adapter retains 20-second timeouts and three bounded transient attempts. Tests
exercise throttle exhaustion, shared-slot refusal and unchanged default policy.
Requests' connect/read timeout semantics and database reads mean this is not a
strict eight-second wall-clock SLA for the complete delivery operation.

Local rendering and HTML sizes are recorded separately in preview metrics; all
examples are comfortably below the existing 95KB rendered limit. There were zero
live Shopify calls and zero delivery calls in these measurements. No production
throughput or latency conclusion is claimed.

## 10. Files changed in V2

New implementation: `crm_collector_sports.py`, `crm_collector_stages.py`,
`crm_collector_transport.py`, `docs/collector-email-discovery.graphql`.

Extended V1 files: `crm_collector_resolver.py`, `crm_collector_images.py`,
`crm_collector_templates.py`. Narrow shared hooks: `crm_campaign_library.py`
(stage rows/explicit application/caption), `crm_shopify.py` (optional request
budget with default policy unchanged).

Tests: new `tests/test_crm_collector_v2.py`; sport tags added to V1 test fixtures in
`tests/test_crm_collector_personalisation.py`; narrow assertion/fixture corrections
in `tests/test_crm_flow_v4.py`, `tests/test_collector_vault.py`,
`tests/test_crm_native_automations.py`; two added account cases in
`shopify_customer_account/extensions/customer-certificate-vault/src/collection-order-pages.test.mjs`.

Evidence tools: `scripts/preview_collector_v2.py`,
`scripts/benchmark_collector_v2.py`, `scripts/check_collector_v2_baseline.py`;
this report and `docs/collector-email-v2/`. Baseline comparison tools use the
captured V1 files in `tmp/collector-v2-baseline`; they do not modify the checkout.

Inbox, Campaigns V8, Product Upload tagging, Edition Ops, storefront/theme and
Render configuration were not edited. Existing V1 account source changes remain
local. Shared files must be reviewed by hunk; never stage them wholesale. The
user-authorized coordinating chat was notified of the V2 exclusion boundary.

## 11. Tests, failures and skips

| Suite/evidence | Result |
|---|---|
| [Collector V1/V2 + account source contracts](collector-email-v2/targeted-tests.txt) | 59 passed, 0 skipped |
| [Lifecycle/Abandoned Cart regression](collector-email-v2/lifecycle-regression-final.txt) | 181 passed, 0 skipped |
| [Existing CRM/Shopify adapter tests](collector-email-v2/shopify-regression.txt) | 19 passed, 0 skipped |
| [Account pagination and certificate/artwork Node tests](collector-email-v2/account-tests.txt) | 17 passed, 0 skipped |
| [Isolated broader account/send/catalogue suite](collector-email-v2/extended-regression-isolated.txt) | 82 passed, 1 error, 0 skipped |
| [GraphQL 2026-04 validation](collector-email-v2/graphql-validation.txt) | Discovery query valid; `read_products` |
| [Render topology validation](collector-email-v2/topology-validation.txt) | Passed; no configuration change |
| Desktop/mobile captures | 26 passed; all images loaded, no distortion/overflow |

Coverage includes all designs/stages, 28 definitions, precise/parent/multiple sports,
stale membership fallback, owned exclusion, absent classification/images/editions,
variant identity, refunds/cancellations, AU/US/GB/NZ/CA markets, unavailable stock,
recipient isolation, optional failures/timeouts, duplicates, actual library Use,
save/reload/duplicate/conflict/history, frozen publication and delivery-ledger
regressions, consent/suppression and render-size checks. Providers are mocked and
SQL uses disposable loopback PGlite fixtures, never production migrations/data.

The three V1 failures were reviewed and corrected **in tests**, without weakening
application safeguards:

- Flow test now checks the actual checkout/lifecycle audience controls after the
  sequence and retains the admin diagnostics gate; the obsolete `recipient_details`
  source assertion is gone.
- Token test flips a decoded signature byte, guaranteeing actual tampering rather
  than changing only base64 padding bits. Expiry/audience checks remain.
- Render test validates the canonical topology and three unset framed-product
  variables on the one webhook service, rather than expecting a duplicate service.

A further pause/resume fixture compared a host timestamp to the application's
database clock and failed by four milliseconds. It now constructs its paused time
from that same database clock; the application and its timing semantics are unchanged.

**Remaining error:**
`tests.test_crm_send_flow.SendFlowUiTests.test_first_send_now_is_review_only_and_shows_off`
raises `concurrent.futures.CancelledError` while awaiting the Campaigns audience
job. It reproduced in an isolated database and with pre-V2 collector/Shopify/library
code loaded in memory: [baseline evidence](collector-email-v2/campaign-review-baseline.txt).
This is a separate unfinished Campaigns path, not certified fixed or green here.
The coordinating chat was notified; protected Campaigns code was left untouched.

Earlier broader attempts also include fixture interference/leftover-data failures
and a corrected test dependency assumption (PyYAML unavailable). Their logs are
retained for transparency; the isolated 83-test result above is the meaningful
final broader result. This is not a claim that the whole repository is green.

## 12. Production prerequisites

- Separately approve a cohesive release including V1/V2 and the already existing
  shared sport-tag mapping and buyer-segment projection dependencies. They are
  currently part of other local work; do not deploy isolated hooks without them.
- Verify the deployed application's actual Shopify scopes, full order history,
  protected customer-data access, fresh segment sync and market/inventory reads.
- Audit sport-tag accuracy and selected fallback artwork/collections. Approve
  each draft application, product claims, global branding and incentive settings.
- Independently stage-test real authenticated customer A/B isolation, pending and
  available certificates, old-order pagination, selected variants and international
  market availability using approved staging records.
- Resolve or explicitly disposition the remaining Campaigns regression with its
  owning work. No broader production-readiness claim is made here.
- Keep lifecycle Draft-only policy and Win Back 4 disabled. Deployment permission
  would not itself authorize activation or sending.

## 13. Database and Shopify permissions

No new table or migration. Reuse the existing CRM runtime state, template versions,
lifecycle revisions, send ledger and exact Edition Ops read contracts. Required
existing migrations must already be installed in any separately approved environment.
No permission broadening or credential changes were performed.

The lifecycle verifier requires `read_customers`, `read_orders`, `read_all_orders`.
Current checked-in app configuration includes customer/order/product/inventory
reads but does **not** list `read_all_orders`; verify and obtain the necessary
approved access before release, rather than weakening history checks. Catalogue
discovery requires `read_products`; inventory and market fields must be usable by
the deployed app token. Buyer definitions/membership require the existing customer
read/protected-data permissions. An external connector's read success proves
nothing about that token's permissions.

The account extension uses `customer_read_customers`, `customer_read_orders` and
its existing API access capabilities. Certificate metadata must be accessible to
the authenticated Customer Account API under the established configuration.
No new Admin access is exposed to the extension.

## 14. Deployment and rollback considerations

**No commands in this section were executed to build, authenticate, upload or
release.** Local CLI help was inspected; [build help](collector-email-v2/extension-build-help.txt)
and [deploy help](collector-email-v2/extension-deploy-help.txt) are retained.

The OS deployment and Shopify Customer Account extension release are separate:
Render does not publish the extension, and Shopify app deploy does not deploy the
OS web server. Keep the canonical existing `sports-cave-os` service identity.

For a future, explicitly approved extension release:

1. In `shopify_customer_account`, review the intended app config and extension
   list; the target remains `customer-account.page.render` with
   `src/MySportsCaveCollection.jsx`. Do not switch to the dormant redesign.
2. Validate with `shopify app config validate --json` after approval for any
   required authentication/config transmission. Run the local account tests.
3. Build with `shopify app build` using reviewed dependencies and the intended
   configuration. Inspect generated output and build errors. V2 did not build
   or alter generated extension bundles.
4. After separate upload authorization, `shopify app deploy --no-release` creates
   an unreleased app version. This still uploads configuration and **all extensions**;
   inspect the complete diff, including unrelated pixel extensions, before using it.
5. Stage-test the approved version and account destination with customer fixtures.
   Only separately approved release should make that version available to customers.
   Retain the prior Shopify app version for rollback.

See Shopify's [build command](https://shopify.dev/docs/api/shopify-cli/app/app-build)
and [deploy command](https://shopify.dev/docs/api/shopify-cli/app/app-deploy).
No authentication/release was needed for local fixture verification.

For an eventual OS release, review only this work's hunks and explicit dependencies;
do not include Inbox/Campaigns/Product Upload changes accidentally. There is no V2
data migration to reverse. Restore a prior lifecycle draft from its archived revision
through the normal versioned workflow if an operator later applies an unwanted
starter; never rewrite frozen publications or replay sends. Reverting V2 runtime
code must preserve V1 marker support and the separate unrelated working tree.

## 15. Outstanding limitations

No independent staging session, real recipient preview, API latency measurement,
live delivery, app build or extension release occurred. Email layout verification
used Chromium/Edge, not an Outlook/Gmail device lab. The existing account empty-state
incident is not diagnosed against a real customer.

Sport precision depends on accurate Shopify tags and recognized segment definitions.
The five-minute segment authority window is explicit, not instantaneous membership.
Four discovery groups, 48 candidate IDs, 50 additional classification products,
eight line continuation pages and 20 candidate variants intentionally favor safe
omission over exhaustive recommendations. V8 has no unverified geographic fallback.
Creation age is not a verified marketing release date. No incentive is generated.

Existing operator drafts remain untouched; old copy/catalogue blocks remain until
explicitly replaced. Unknown-interest Welcome needs an approved selection for a
hero, or displays its neutral CTA. The broader Campaigns cancellation error remains.
These limits and each stage's prerequisites must be reviewed before any separately
authorized deployment, application to drafts, activation or send.

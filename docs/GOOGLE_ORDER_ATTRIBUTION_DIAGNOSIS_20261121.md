# Google paid versus organic diagnosis — 21 November 2026

Read-only audit of 14–20 November, Australia/Sydney. No customer contact,
payment or address fields were requested. Order-level evidence stayed transient.
These observations describe the live version before this local correction.

## Verified observations

- Shopify returned all 36 non-test, non-cancelled orders, with no next page.
- Home showed 18 Facebook paid, 1 Google paid, 6 Organic, 2 Other and 9 Unresolved.
- Home matched 32 orders to GA4 and reported 4 unmatched orders.
- Its exact-ID reconciliation explicitly showed **Google paid → Organic: 3**.
  These are three of the four Google-paid purchase sessions for the same cohort.
- Two of the six organic-classified Shopify last visits had only Google
  `product_sync / sag_organic` feed tags; four had an explicit Shopify SEO tactic.
- One SEO last visit followed a first visit tagged Facebook paid. This is a
  concrete example of why last-visit classification does not establish that an
  advertising platform could not also claim credit.
- The connected fixed-account Google Ads API returned PM021126, AUD, Sydney,
  5 primary purchase conversions, A$1,540.853469814 conversion value and
  A$153.24204 spend: 10.06× ROAS. The configured daily budget was A$20.
  The purchase query selects PURCHASE conversions, not cart or checkout actions.
  Metrics use ad interaction dates, unlike Shopify order-creation dates.

## Diagnosis and limits

There are two issues, not evidence that all Google orders are organic:

1. Different attribution models and date bases are being displayed together.
   Shopify last visit can be SEO even when GA4's purchase session is Google paid,
   or when an ad platform claims an earlier interaction. Ads aggregate purchase
   credit cannot be matched to individual Shopify orders by subtracting counts.
2. The previous classifier asserted that feed-default `sag_organic` tags alone
   verified an unpaid listing. Merchant product landing URLs can be used for
   Shopping ads as well. The API evidence lacks independent unpaid-click proof;
   absence of a click ID from a recorded URL is insufficient. This affected two
   orders in the audited window. Neither can responsibly be forced to paid.

Shopify's “unknown source” display is also insufficient by itself: the structured
UTM record can still contain explicit `facebook / paid_social` evidence. The
existing classifier correctly handles that case and it is unchanged.

This audit does not establish whether every Google Ads conversion is unique,
unmodeled, or exactly which Shopify order it represents. The five credited
purchases are not proof of five distinct last-visit Google-paid Shopify orders.
No campaign, tracking, budget or historical analytics data was changed.

## Local correction

- Feed-tag-only Google visits stay Unresolved with a specific reason. Explicit
  paid tags/click evidence and explicit Shopify SEO evidence retain their meaning.
- Preserve the labelled Shopify last-visit table, counting each order once.
- Expose the separately deduplicated GA4 Google-paid count for that same cohort.
- Show Google Ads attributed purchases and its interaction-date basis beside
  that comparison; preserve fractional conversion credit and unavailable values.
- Put paid/organic disagreements and ambiguous listing counts above the closed
  coverage disclosure, and label the organic row “Organic (last visit)”.
- Version-three cache keys prevent old feed-as-organic snapshots being reused.
- Keep the CRM companion's attribution guidance consistent with these limits.

Under this correction, the two feed-only entries move from Organic to
Unresolved: the audited Shopify table would contain 4 Organic and 11 Unresolved,
with other source totals unchanged. The exact remaining model-difference count
must be recomputed by the live refresh; it must not be inferred from aggregates.

## References

- [Google: conversion tracking data and interaction versus conversion dates](https://support.google.com/google-ads/answer/6270625?hl=en)
- [Google Merchant Center: product performance tracking and separate ads/free-listing URLs](https://support.google.com/merchants/answer/15114528?hl=en-EN)
- [Google: auto-tagging and GCLID](https://support.google.com/google-ads/answer/1752125?hl=en)
- [Shopify: customer journey first/last visits](https://shopify.dev/docs/api/admin-graphql/2026-04/objects/CustomerJourneySummary)

## Release status

Validation: 89 focused checks passed, including disposable PostgreSQL snapshot
storage, source classification/deduplication, unavailable-value handling, Ads
reporting, Home integration and headless Edge layouts at 1600/820/390/320px.
One existing unrelated design-prompt assertion
(`test_full_edition_and_selected_story_design_prompt`) failed in the broader run
and was excluded from the focused rerun; it also failed in the preceding audit.
The operational Shopify query validated against Admin API 2026-04. Render
topology validation and whitespace checks passed.

Implemented locally in task 20261121-0dbcb847. No commit, push or deployment is
authorized by the current request. Repository AGENTS.md requires explicit
authorization for those actions. Production still uses the previous version.

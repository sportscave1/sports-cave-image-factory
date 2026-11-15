# Campaign audience freshness — local verification, 30 September 2026

## Diagnosis

The selector used `crm_segment_counts -> crm_campaign_markets.calculate`, displaying
`eligible`, not Shopify's subscribed segment size. That calculation scanned all
customer profiles, assigned countries using only `defaultAddress`, omitted fallback
tags, then deducted suppressions, invalid emails, duplicates, conflicting consent
and Smart Sending exclusions. It did not read the saved Shopify segment definition.
The display cache had a ten-minute TTL. Customer webhooks already invalidated a
shared `crm_runtime_state.cache_version`; segment-definition webhooks were absent.
Draft counts were not the selector's source. Existing customer pagination did advance
through all pages; a first-page truncation was not the root cause.

Read-only Shopify verification found:

| Query | Count |
|---|---:|
| Saved Australia segment (all consent states) | 1,995 |
| AU country OR SC_COUNTRY_AU, AND SUBSCRIBED | 1,085 |
| AU country only, AND SUBSCRIBED | 1,039 |
| USA subscribed, including fallback tag | 535 |
| UK subscribed, including fallback tag | 34 |
| Canada subscribed, including fallback tag | 8 |
| New Zealand subscribed, including fallback tag | 4 |
| All subscribed | 2,029 |

The saved Australia definition currently omits the subscription predicate. The app
therefore intersects its live query with SUBSCRIBED; it never assumes that a country
segment grants consent. No live definition was edited. The current tag-inclusive
versus country-only difference is 46. The historical displayed 1,038 cannot be fully
reconstructed without its old snapshot and exclusion state; attributing every one
of the historical 47 missing customers to caching would be unsupported.

## Implementation

- `crm_campaign_segments.py`: shared source resolution for counts and recipients.
  Bootstrap only an unambiguous established segment name, then persist its Shopify
  ID under a shop-scoped runtime-state key. Future renames retain the ID. Query and
  last-edit data are read fresh, never stored as permanent customer truth. A deleted
  bound segment fails closed. When no segment is bound, use the explicit canonical
  subscribed country/tag query evaluated by Shopify. No customer database is added.
- `crm_shopify.py`: one aliased GraphQL count batch for all six markets using
  `customerSegmentMembers.totalCount`. No customer records are fetched for counts.
  Separate fresh, cursor-paginated native member IDs are used only for review/send.
- `crm_segment_counts.py`: 60-second TTL, existing 10-second shared revision check,
  and existing two-second UI fragment. The six counts, definitions, fetched time and
  revision publish atomically. Smart Sending settings share the same subscriber
  count snapshot. Update races discard the batch and retry on the next fragment.
  Failures retain the last snapshot with an error flag and a 60-second retry backoff.
- `crm_campaign_controls.py`: stable market keys remain the selector identity.
  A caption identifies the numbers as Shopify subscribed segment sizes; the existing
  send review separately reports eligible recipients and exclusions. A small Refresh
  audiences action invalidates the shared revision and bypasses display TTL. Counts
  never come from the draft's saved review totals.
- `crm_webhooks.py`: reuse the existing signed Shopify webhook route and minimal
  event storage/invalidation. Existing create/update/delete/consent customer topics
  cover subscription, tag and address changes. Added supported segments/create,
  segments/update and segments/delete handling to the existing registration list.
  No subscriptions were registered during this task.
- `crm_campaign_markets.py`, `crm_campaign_send.py`: review/queue build reads current
  Shopify membership for the selected market, then runs the existing fresh profile,
  consent, valid-email, suppression, duplicate/conflicting-profile, Smart Sending and
  native unsubscribe checks. The full profile pass remains necessary to detect
  conflicting consent outside the selected segment. No display cache authorizes
  sending. Transport, queue semantics, confirmations and marketing flags are unchanged.
- Canada/New Zealand are added to the existing market enum and the existing price/
  currency maps in `crm_campaign_content.py`, `crm_catalogue.py`, `crm_email_blocks.py`
  and `crm_shopify.py`. Existing market legal-review gates still apply.

The legacy rule-shaped audience field remains for document compatibility; market
drafts resolve their stable market key through native membership, not those former
default-address rules. Existing non-market drafts retain their original rules.

Typical dropdown refresh: one segment-catalog page plus one count batch, instead
of a full profile scan and eligibility calculation. Between refreshes, only a cheap
revision read runs every ten seconds while the fragment is open. More catalog pages
are followed if necessary. Full recipient work occurs only on explicit review/send.

## Validation

- `CRM_TEST_POSTGRES=1 .venv/Scripts/python -m unittest discover -s tests -p 'test_crm*.py'`:
  **345 tests run, OK, one intentionally skipped**; disposable loopback PGlite only.
- 18 new focused tests in `tests/test_crm_audience_sync.py`: coherent batch, subscribe/
  unsubscribe, all five fallback tags, removal, country transfer, no double counting,
  source query edits/renames/deletion, missed-webhook TTL, cache reuse, manual refresh,
  outage retention, 2,251 members, pagination guards, draft independence, update races,
  and CA/NZ document compatibility. Existing CRM tests continue covering send safety.
- Updated fixtures and regression expectations in `tests/crm_fixtures.py`,
  `tests/test_crm_campaign_v2.py`, `tests/test_crm_segment_performance.py`,
  `tests/test_crm_native_unsubscribe.py`, `tests/test_crm_production_unsubscribe.py`.
- Broader `test_shopify*.py`: 213 tests, **178 passed, 34 skipped, one unrelated failure**.
  `test_render_services_do_not_gate_core_shopify_on_optional_marketplace_schema`
  expects an old Render preDeployCommand absent from unchanged `render.yaml`.
  Neither that test nor Render configuration was modified.
- All 17 changed/new Python files compile. `git diff --check` passes. No JavaScript
  changed. GraphQL count operations validated against the connected Shopify schema.
- Browser fixture `tests/fixtures/crm_audience_sync_preview.py`, using the real Campaign
  editor: checked 1440x900 and 1920x1080. All six options arrive together. A synthetic
  customer webhook automatically changes Australia 1→2 and All Subscribers 3→4;
  USA stays selected at 1. Manual refresh, Settings/Editor navigation and draft subject
  retention work. No browser console errors; 1920 viewport/document widths match.
  Screenshots: `validation/crm-audience-sync-1440.png` and `validation/crm-audience-sync-1920.png`.

## Verification limits / rollout

Live counts above were fetched through the connected read-only Shopify API using
the same count-query contract as the new helper. The local OS has no configured
Shopify domain/API version/credentials, so a live authenticated OS browser session,
live final exclusion totals, and the OS application's webhook registrations could
not be verified. The production OS count has not changed: this is a local patch.
Before a separately approved rollout, inspect existing subscriptions with the
existing `scripts/register_crm_webhooks.py` read-only command and review any missing
topics/forwarding. The minute-scale TTL reconciles missed/unregistered events without
requiring manual sync once this code runs.

Supported segment topics were verified in the official Admin API 2026-04
[WebhookSubscriptionTopic documentation](https://shopify.dev/docs/api/admin-graphql/2026-04/enums/WebhookSubscriptionTopic).
Count semantics use the documented
[CustomerSegmentMemberConnection](https://shopify.dev/docs/api/admin-graphql/2026-04/connections/customersegmentmemberconnection).

No live emails, test emails, campaigns, customers, segments, budgets or production
data were modified. No marketing activation, commit, push or deployment occurred.

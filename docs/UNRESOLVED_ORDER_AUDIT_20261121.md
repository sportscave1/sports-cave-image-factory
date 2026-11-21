# Remaining unresolved order audit, 21 November 2026

Cohort: 36 non-test, non-cancelled Shopify orders created 14-20 November in Australia/Sydney. Read all available journey moments for the nine unresolved orders (all pages complete), native sales-channel/app evidence, and exact GA4 transaction IDs in property 355333982. The native Transactions report covered 24 October-20 November and used Session source / medium; it reported 100% of available data. No historical events or orders were rewritten.

| Order | Shopify evidence | Exact GA4 purchase session | Result |
| --- | --- | --- | --- |
| SC3480 | Facebook referral; two recorded visits, no paid medium | facebook.com / referral | Facebook known; paid/organic unresolved |
| SC3487 | Etsy source, Marketplace Connect app, no website journey | No transaction found | Etsy sales channel |
| SC3488 | Facebook referral; no paid medium | m.facebook.com / referral | Facebook known; paid/organic unresolved |
| SC3489 | Facebook referral; Facebook_UA content without medium | (direct) / (none) | Shopify Facebook referral retained; no paid/organic proof |
| SC3493 | Facebook referral; Facebook_UA content without medium | facebook / referral | Facebook known; paid/organic unresolved |
| SC3498 | Etsy source, Marketplace Connect app, no website journey | No transaction found | Etsy sales channel |
| SC3505 | search.brave.com referral; no paid/organic tactic or medium | (not set) | Brave referral known; paid/organic unresolved |
| SC3506 | Facebook referral; no paid medium | m.facebook.com / referral | Facebook known; paid/organic unresolved |
| SC3507 | Etsy source, Marketplace Connect app, no website journey | No transaction found | Etsy sales channel |

## Changes

- Read the native order source and app ID. Etsy is established only by `sourceName=etsy` plus the observed Marketplace Connect app ID. An absent session or a referral alone cannot create an Etsy classification. Use fields validated against the existing 2026-04 application API; the audit connector's newer attribution field is not added to the production query.
- Show Etsy as a distinct ledger row, separate from storefront acquisition. Etsy attribution means the marketplace sales channel, not proof of Etsy Ads or Etsy organic search. Exclude Etsy from Shopify-versus-GA4 acquisition differences.
- Keep referral identity as an allowlisted aggregate for unresolved Facebook/Instagram/Google/Brave visits. Do not persist raw URLs, transaction IDs or journeys in Home snapshots. Missing/contradictory evidence stays unresolved. A Facebook_UA content value, Facebook click ID, social referrer or Brave referrer alone does not prove paid or organic.
- Separate expected Etsy imports without storefront GA4 matches from other unmatched orders. A missing storefront match is not automatically a tag failure or consent refusal; no specific cause is asserted without evidence.
- Remove stale `sc_channel`, `sc_network` and `_gl` parameters, alongside existing UTMs and click/ad IDs, when building a NEW marketing destination. Both organic social link generation and Meta ad destination validation use this cleaner. This avoids copying old Google paid diagnostics or a previous session linker into a different channel. No native pixel, consent, bidding or budget settings are changed.
- Version 5 invalidates old aggregate cache keys. Existing exact-transaction resolution of the two ambiguous Google feed orders remains in place.

Expected same-cohort totals after refresh: Facebook paid 18, Google paid 2, Organic 5, Etsy 3, Other 2, Unresolved 6. The six have known referral names but unresolved paid/organic status: Facebook 5, Brave Search 1. Of four unmatched GA4 transactions in the whole cohort, three are Etsy imports and one is another order.

Validate synthetic source/channel conflict cases, source query integration, aggregate privacy and deduplication, new organic/Meta link cleanup, and browser layout on desktop/tablet/mobile. Verify live counts and source coverage after the Render release. The audit cannot reconstruct lost click identifiers or establish advertising incrementality from referral/session labels.

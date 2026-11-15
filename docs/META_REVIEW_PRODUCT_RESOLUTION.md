# Meta Review canonical product handoff

The previous handoff used only an exact ad mapping from review preferences and
hydrated the product selector with a title rather than its canonical identity.
It did not resolve Posting provenance or child-card destinations, or hydrate the
canonical URL and URL-autofill bookkeeping.

`meta_review_products.enrich` now runs before durable handoff storage and when a
fresh tab loads that handoff. It uses the existing cached live product catalogue:
Supabase edition/Shopify product records, not session product guesses.

Resolution priority:

1. Existing mappings: ad, creative, campaign, then ad set. More-specific mappings
   win; conflicting or unresolved references require confirmation.
2. Exact identities in the existing `meta_posting_submissions` ledger, including
   multi-ad result records and their canonical product/destination.
3. Exact Sports Cave product destinations, including carousel child links.
   Multiple distinct product handles require confirmation. Canvas URLs are never
   treated as product URLs.
4. A unique complete distinctive product title can produce HIGH confidence;
   partial athlete/name matches only rank suggestions. EXACT and HIGH alone
   permit automatic selection.

The existing Product name selector ranks candidates. Selecting a canonical row
confirms the current ad mapping in `ads_product_mapping`, writes an audit event,
and enriches the durable handoff in one existing database transaction. A guarded
upsert refuses a conflicting existing ad handle. Explicit corrections remain in
Product Tagging Review. No Meta writes or new mapping tables are introduced.

The package retains product ID/title/handle, canonical URL, category and match
provenance. Hydration uses the selector's existing stable identity, restores URL
autofill state, and retains the original archived image, exact text/headline,
market, format, source metadata and performance context. Description and CTA
remain in existing source metadata; no new generator inputs were invented.

URLs prefer the stored canonical live product URL. Missing URLs use the existing
repository storefront/handle rule, never an example placeholder. Missing category
or uncertain market remains unselected rather than being inferred from ad names.

No new migration is required. Existing Ads Intelligence, product mapping v1,
Posting ledger and Meta Review handoff migrations remain prerequisites for their
respective storage operations. No production migrations were run for this change.

The live `210526 AUS KOBEVJORDAN` record was not verified: this local environment
has no configured database connection or callable Supabase connector. Tests cover
that style of ambiguous name without hardcoding a campaign/product association.
Its exact matching source must be checked in the connected application.

Validation includes resolver, Streamlit selector, fresh-tab hydration and existing
Meta Review/Creative Refresh/Posting regressions. The isolated PostgreSQL harness
executes the actual guarded confirmation SQL, tests conflict refusal, and reloads
the enriched handoff after a database restart. Production data is never used by
these tests.

Results: 252 focused Meta Review/Creative Refresh/Posting tests passed. The broader
Ads page suite passed 192 of 193; `test_dropdown_options_are_in_required_order`
expects the old category order while the existing definitions alphabetize it.
The same failure was reproduced using the category definitions from HEAD; those
definitions are unchanged here. Python compilation, JavaScript syntax validation,
isolated PostgreSQL checks and `git diff --check` passed.

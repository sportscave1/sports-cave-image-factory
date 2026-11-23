# Compact My Collection and Shopify Markets

Task 20261123-0861c78c; user explicitly authorized live release.

Removed the empty Page heading wrapper and internal 1200px cap so the compact review strip starts alongside native account navigation. Certificates use denser cards and adaptive columns; certificates and four recommendations use native horizontal scroll strips on mobile. Recommendations stay in one desktop row, shorten Wall Art in display titles, show genuine market compare-at RRP when higher, and include the contextual sale price in full-width add buttons.

The review stars and review button open a native account modal using the existing owner-bound Judge.me submission endpoint, rating, text and optional photo. Existing delivery/ownership eligibility and duplicate protection remain enforced. No review is posted during verification.

Storefront product reads use @inContext(country) from the live account country signal. All new carts carry buyerIdentity.countryCode; shared recommendation carts reset after market changes. Certificate pricing is re-read with the native Storefront API per country and available variant. The signed certificate handoff pins country; storefront handoff selects that country before merging into the existing cart.

Validation: 51 focused Python tests, 24 Node checks, two Storefront GraphQL queries validated against 2026-04, native Shopify app build/config validation. Bundled UI validator cannot resolve its own TypeScript dependency; native build and live desktop/mobile review provide validation instead.

No topology changes or Blueprint sync. Preserve canonical primary and supporting services. Current upstream inbox changes were fast-forwarded before release.

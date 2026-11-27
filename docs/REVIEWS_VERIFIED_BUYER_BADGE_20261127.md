# Uniform Verified buyer badge

User authorised the same Verified buyer badge for Shop-origin reviews, with Git/Render and storefront release. No review content, ratings, native order-verification records, rewards or layout changed.

Backend release `1b6f42e00d77460f12b3655c9dae9f8dc6d9eaef` was observed Live on the canonical primary and both existing supporting Render services. The feed now treats Shop's confirmed source verification as eligible for the existing buyer badge. Native `verified_purchase` remains unchanged. The public total remains 211.

The theme tool's working copy was older than the actual published asset. Its publisher correctly refused a bulk publication because other theme files had changed. That stale theme snapshot was not published. Instead, downloaded the actual current CDN asset, checked it still matched immediately before upload, changed only its Shop-badge branch and used Shopify CLI with an explicit `--only assets/sc-customer-reviews.js`, `--nodelete` and the existing live theme ID `190889230643`. CLI `--force` bypassed only its theme-directory detection for the single-file staging folder; no other files were uploaded or deleted. Exactly one file was uploaded. The initial tool save remains unpublished and must not be used to replace the live theme snapshot.

Fresh storefront readback matched the exact tested 21,146-byte release artifact under `shopify/reviews/releases/20261127-verified-buyer/assets/`. Live version URL: `https://www.sportscaveshop.com/cdn/shop/t/127/assets/sc-customer-reviews.js?v=78436630350678721491795752517`. Both new Tarsha reviews visibly show the same tick and Verified buyer label as Rob Kirk, Neil Whelan and Alan Carson. No Verified by Shop images remain in the rendered archive. Screenshot: `artifacts/verified-buyer-badge-20261127/live-proof.jpg`.

Validation: six focused Python tests passed; eight disposable SQL cases were not run for this display-only change. Two AU/US synthetic widget browser tests passed against both canonical source and the exact patched live artifact (two unrelated form cases skipped). Shopify asset validators and Node syntax checks passed. [Reviews CI 45937417168](https://github.com/sportscave1/sports-cave-image-factory/actions/runs/45937417168) passed. Public production API confirmed both Shop reviews use standard source verification while native order-verification flags remain false. No customer writes or email sends during testing.

CLI reference used: [single-file theme push](https://shopify.dev/docs/api/shopify-cli/theme/theme-push).

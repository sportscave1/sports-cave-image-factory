# Cart-only framed certificate

The existing Framed Collector Certificate product (`10332579103027`) uses Shopify's
UNLISTED status. Keep its Online Store publication: the account's exact-ID
Storefront price lookup and the existing browser cart/checkout require it.
Unlisted removes automatic search, collection, recommendation, sitemap and
sales-channel discovery without changing variant IDs or order fulfilment.

Assign `certificate-private` as its product template. This minimal template has
no product UI and sends direct product-page visits to the localized cart. It
includes explicit noindex/nofollow and a JavaScript-free redirect fallback.
The live theme's shared cart-item snippet omits the certificate's image/title
link destinations in both the cart drawer and full cart. Other products retain
their links. Do not archive, draft, delete or unpublish this product from the
Online Store: that would break the authorized account upsell.

Deployment order: release the backend's UNLISTED compatibility first; upload only
the private product template and shared cart-item snippet to the existing theme;
then set the existing product's template and UNLISTED status. Verify direct-page
redirect, public discovery exclusion, account pricing, cart add and checkout.
This does not change allocations, certificates, Orders or multi-item processing.


The system `seo.hidden` integer is also set to 1. A product-ID guard in the
existing shared product-block snippet hides this certificate from rendered
search/collection/recommendation cards even while Shopify search indexing catches
up. The full original snippet is preserved beneath that one-product guard.

The follow-up pair-card improvement batches at most 121 tag-only IDs in one read
and checks market/edition eligibility in groups of eight, preserving smart order,
all ownership exclusions and the eight-ID Storefront fallback shortlist. A bounded
30-second cache lives only inside the mounted account and keys country, seed and
owned-product fingerprint. It never persists customer data between accounts.
Pending requests retain a native loading spinner. Only two eagerly loaded,
responsive thumbnails are rendered; labels split explicit punctuation into an
edition heading and a subdued athlete line without modifying canonical titles.

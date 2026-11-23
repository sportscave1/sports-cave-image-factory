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

# Durable certificate cart previews

The cart previously saved an account asset URL that expired after 30 minutes.
Reopening a cart later produced HTTP 401 and a broken certificate thumbnail.

The cart now uses the existing random frame-request UUID as an image-only
capability. The thumbnail resolver verifies the saved request status, variant,
certificate, edition number and current owner before rendering a fixed 400px
framed preview. It never returns printable/PDF bytes or a source asset URL.
Cancelled/failed requests and mismatched/reassigned certificates are rejected.
The account's signed asset endpoints retain their original expiry checks.

The shared cart snippet derives this URL from the saved frame reference and
Shopify's actual variant SKU, rather than reusing the expiring image property.
This repairs existing carts too, without changing quantities or requiring a
second Add to cart. Fresh handoffs also save the durable preview URL. R2 source
signatures are generated server-side when needed; thumbnails use the existing
bounded image cache and composition coordinates.

Deploy the backend before updating the single live cart snippet. Verify the
previously broken cart line and a fresh account-to-cart handoff, preserving all
existing cart items. Product privacy, pricing, checkout, edition allocation and
Orders/multi-item processing remain unchanged.

# Storefront artwork deterrence

Configure from Sports Cave OS **Settings → Image Protection** (existing admin
permission only). Settings use the existing `app_settings` storage and are read
only by this page or the public config endpoint, never normal OS startup. The
public endpoint caches the ten harmless boolean flags for 60 seconds server-side
and 30 seconds in browsers. No credentials, sessions or customer data are returned.

Shopify Admin → Online Store → Themes → Edit code → `layout/theme.liquid`.
Place this once immediately before `</body>`:

```liquid
<script src="https://sports-cave-image-factory.onrender.com/storefront-protection.js" defer></script>
```

A Custom Liquid block can use the same line, but a product-only block does not
protect other pages. The global theme include is preferred. Do not include it in
checkout, customer-account extensions or invoice templates.

Explicitly mark extra artwork with `data-sc-protected="artwork"` or
`class="sc-protected-artwork"`. Known product-media images are detected automatically.

Test product navigation, variants, swipe/carousel, Add to Cart/cart drawer,
login forms, keyboard paste and mobile. Test right click on artwork and text
inputs separately. Print preview must hide marked artwork.

Remove the script line to disable the integration safely. If Render/config is
unavailable the script uses a basic local deterrence policy; storefront shopping
does not wait for it. No advertising events or credentials are sent.

The script runs only on `sportscaveshop.com` / `www.sportscaveshop.com`. It excludes
account/checkout/order pages, form controls and Wall Preview. Context menu and
copy controls are scoped to artwork; Save shortcuts are intercepted only while
artwork is targeted. Swipe/pointer movement and shopping controls are untouched.
The optional decorative watermark is off by default and ignores pointer input.
There is no public-image conversion, resizing or export hook in the OS.

Browser protection can discourage casual saving and copying but cannot completely
prevent operating-system screenshots or determined downloads. WebKit touch-callout
CSS is best-effort; mobile browser and accessibility behaviour can differ.

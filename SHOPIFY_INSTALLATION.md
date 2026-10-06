# Storefront artwork deterrence

Configure from Sports Cave OS **Image Protection** (main navigation, below Email) (existing admin
permission only). Settings use the existing `app_settings` storage and are read
only by this page or the public config endpoint, never normal OS startup. The
public endpoint caches the allowlisted artwork flags and watermark appearance for 60 seconds server-side
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
unavailable the script fails open; storefront shopping
does not wait for it. No advertising events or credentials are sent.

The script runs only on `sportscaveshop.com` / `www.sportscaveshop.com`. It excludes
account/checkout/order pages, form controls. Wall Preview media is protected separately without blocking its controls. Context menu and
copy controls are scoped to artwork; Save shortcuts are intercepted only while
artwork is targeted. Swipe/pointer movement and shopping controls are untouched.
The optional decorative watermark is off by default and ignores pointer input.
There is no public-image conversion, resizing or export hook in the OS.

Browser protection can discourage casual saving and copying but cannot completely
prevent operating-system screenshots or determined downloads. WebKit touch-callout
CSS is best-effort; mobile browser and accessibility behaviour can differ.

Configuration is read once per page load. Refresh an already-open page after changing settings. No polling, OS auth, browsing heartbeat or customer identifiers. ETags support conditional config requests.

Verified DEV: Sports Cave DEV — Codex, theme 189335863603 (unpublished). The settings-page Verify DEV installation action checks the public DEV page and config only when clicked. It reports verification time, not a fabricated heartbeat.

Image pipeline review: generated exports are capped at 1600px; previews at 900px. Wall Preview requests 2000px Shopify CDN derivatives. No master/source files or existing Shopify media are altered. Shopify CDN original availability is not access control.

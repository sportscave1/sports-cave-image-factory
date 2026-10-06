# Storefront artwork deterrence

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

Browsers cannot stop OS screenshots, developer tools, direct CDN downloads or
determined copying. Baked-in watermarks and limited public derivative resolution
protect the served file itself; CSS/JavaScript do not make images private.

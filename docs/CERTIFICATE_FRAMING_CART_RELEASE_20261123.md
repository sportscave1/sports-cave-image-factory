# Certificate framing and fulfilment release

Task 20261123-4d5bfa7c. User explicitly requested commit, push and live release.

- Account framing modal uses Small 21 x 30 cm and product frame swatch tiles.
- Native top close only; free print remains on collection cards.
- JSON UUID serialization fixed; signed 30-minute handoff preserves existing storefront cart, deduplicates certificate request and opens the native drawer on the last storefront page.
- Theme 190745575731: certificate cart JS plus one layout include and conditional certificate thumbnail in cart-item. Saved theme commit b35a105f2d6c388334a4a5ce3ea136511318d08a; published with explicit user release authorization.
- Paid certificate lines are independently tracked in app_settings, outside edition allocations. Original issued print/PDF is enlarged with the same bounded integer scale as PSD preparation and archived through the existing output store. Existing Small supplier mappings and Companion preparation/upload/QA handle the selected colour. Ordinary artwork paths remain unchanged.
- Certificate units revalidate paid order, owner, line, quantity, variant and original certificate before preparation/download. Refunds/cancellations stop preparation. Paid webhook persistence retries before acknowledgement.
- Added pypdfium2 5.15.2 for exact single-page issued PDF rasterization when no print JPG exists.

Validation: focused Python 122 passed with disposable PostgreSQL; account utility 15 passed; cart transfer 4 passed; native Shopify app build passed; Render topology validation passed. No purchase or supplier payment is part of verification.

Canonical Render primary srv-d8kl4on7f7vs73dvavv0 and existing webhook service only. No Blueprint sync or topology mutation.

Live verification: selected Oak for Nolan Ryan edition #027; Add showed Added to cart. Checkout now returned to the previous Formula One collection page with native cart drawer open, correct Oak variant, original edition and certificate thumbnail. Removed only the test cart line afterward; no order/payment placed. Modal changed to Shopify large-100 fixed size after visual review to retain two columns without max-height empty space. All three Small colour mappings validated with disposable SQL fixtures. Additional regression run: 140 passed.

Shopify released version: certificate-cart-layout-20261123 (1262124302337).

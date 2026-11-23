# My Collection setup review form — 2026-11-23

User explicitly authorized publishing these review refinements. Scope is the native account review form, one small Storefront product image query, and the optional Judge.me public display name. Orders, companions, multi-item processing and issued certificate files remain untouched.

- Name is required by the UI and safely bounded on the server; older clients retain the order-name fallback. The email and signed purchase reference still come from the authenticated purchase.
- Removed the Judge.me explanatory line. Retained existing photo validation and delivery, duplicate checks and provider error handling.
- Setup panel uses exactly product image 2 in Shopify product ordering, via images(first:2) and a 640px CDN transform. One query on product change, lazy image, purchased-artwork fallback. It never blocks opening or submitting the form.
- Native modal includes purchased-edition details, larger rating stars, setup panel and compact fields. No unsupported video control is advertised.

Validation: 59 Python tests plus 11 subtests; 14 focused Node checks; native component typecheck; Shopify config and production build. Toolkit component validator cannot start due to its missing TypeScript dependency; installed project types and build validate successfully. Live evidence is retained in Studio runtime.

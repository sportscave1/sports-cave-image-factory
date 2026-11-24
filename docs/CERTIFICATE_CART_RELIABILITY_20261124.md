# Live certificate cart reliability repair — 24 November 2026

The user explicitly authorized diagnosis, repair, testing, speed improvements and a live release.
Task worktree: `certificate-cart-reliability`, owner: this Codex chat. The host-managed isolated
worktree starts at `2acd8e00b4b9c4ee8dda4fc9ea6f7045d83c8fee` and uses
`codex/certificate-cart-reliability-20261124`; no other task checkout was edited.

## Cause

The newly published countdown theme did not contain the certificate cart bridge, its layout
script include, or the personalised cart-item image branch. A real account Add returned a
valid `sc_certificate_cart` parameter to the homepage, but no script consumed it and the cart
drawer stayed closed. These integrations had previously been installed in theme 190745575731;
publishing a different theme did not carry them forward automatically.

The account also created a separate Storefront API cart and posted its checkout URL before
using the browser-cart handoff. Those two operations were unnecessary for a storefront drawer.

## Repair

- Restored the bridge and one deferred layout include to the current live theme,
  `Sports Cave - 48 Hour Countdown - 24 Nov` (190888968499). Preserved its other source.
- Restored the existing durable certificate preview branch in shared `cart-item.liquid`,
  including actual frame colour from the selected variant SKU. It affects the drawer and full
  cart, without exposing a public certificate product link or an expiring printable asset.
- Return to the remembered storefront path, variant query, anchor and scroll position before
  the mutation. Open the drawer before waiting for the handoff/cart reads. Fill it and the
  header from Shopify's bundled cart-add sections, with no page navigation after an Add.
- Fetch independent handoff and cart reads concurrently, prewarm the authorised thumbnail,
  and eliminate separate account cart creation and its completion POST.
- Preserve all existing cart lines. Deduplicate by variant plus private frame request, serialize
  same-browser tabs with Web Locks, and reconcile ambiguous POST failures by reading the cart
  before enabling a retry. Keep a short-lived tab-local pending handoff so an interrupted page
  can recover. Invalid handoffs never mutate the cart.

## Release and verification

- Theme saved commit: `8ae943e00f0fb510c7bc134a317a7afab1ceb1db`; publication succeeded.
- Existing Sports Cave OS app release: `certificate-cart-reliable-20261124`, Shopify version
  1263378464769. No new scopes, backend deployment or infrastructure changes.
- Code commit: `c45b72240e62daffe29cd0a3a44282296bfcb976`; PR #33.
- 25 focused cart/account tests, 15 vault utility tests, 15 broader account/review tests passed.
  Account TypeScript, Shopify config validation, native app build and topology validation passed.
- Liquid layout passed validation. Cart-item passed with the expected advisory that its
  personalised image is served by the private preview service rather than Shopify's CDN.
  The separate component validator could not start because its bundled TypeScript dependency
  is absent; native Shopify build and TypeScript validation completed successfully instead.
- Live account: Black certificate added correctly; fresh Oak Add returned to the previous
  Shane Warne product and selected variant with the native drawer open. Both actual certificate
  thumbnails loaded in the selected frames. Repeating Oak Add on mobile retained exactly two
  distinct frame lines at quantity one each. No manual refresh, purchase or payment.
- Mobile at 390px showed no horizontal overflow. Removed only the two test lines and confirmed
  the original empty cart and closed drawer afterward.
- Local visual evidence is in `artifacts/certificate-cart-reliability/`; screenshots and source
  snapshots remain local and are deliberately excluded from this documentation commit.

Future theme replacements must carry the bridge asset, its single layout include and the
shared cart-item personalised preview branch together; deploying the backend/account alone
does not install storefront theme code.

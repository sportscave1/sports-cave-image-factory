# Account showcase and framed certificate overlay

Task `20261123-e25ef29e`, owner `codex-account-showcase-20261123`.
Local implementation based on production main `73fa0444`.

- Certificates and recommendations: two columns above a 750px container width,
  one full-width card per row below; removed horizontal mobile strips.
- Frame picker: native maximum-size modal, larger image column, responsive
  single-column mobile layout and generous spacing. The whole preview is contained.
- Successful Add switches the existing native modal into a framed-certificate
  cart confirmation over My Collection. It shows the selected frame, contextual
  market price and checkout/continue-browsing actions without navigation.
- Customer accounts cannot host the storefront theme drawer. This native overlay
  displays the framed item; existing storefront items remain included at checkout.
- Signed handoffs now pin a checkout destination. The existing storefront helper
  merges/deduplicates the certificate and goes directly to localized checkout.
  Older signed handoffs retain the existing drawer route. Cart clearing is absent.
- No Orders, Inbox, variant mapping or multi-item fulfilment code changed.

Validation: 59 focused Python checks, 11 subtests, no skips with disposable
PGlite; 30 Node checks including actual Add success/reused-cart/failure state
transitions and storefront merge/deduplication/checkout paths. Native Shopify
build and configuration validation passed, as did topology and diff checks.
Seven old certificate source assertions fail identically on the untouched base.
The skill component validator cannot resolve its bundled TypeScript dependency.

Not deployed or tested in the live account. Publication requires explicit release
authorization under AGENTS.md, then a coordinated backend, Shopify app and single
existing theme-helper asset update, followed by desktop/mobile verification.

## Reference popup and loading update, 23 November

Continued in the same task and owner; no certificate-design task files imported.
The native modal now says “Frame your certificate”, has a bounded 1200px content
area, a 1.25:1 image/details split above 750px, and a full-width image followed by
padded details below that breakpoint. It retains a contained square preview,
three frame cards with larger rounded edges and 44px label targets, italic edition
details and a full-width “Add to cart” button. Shopify's native modal owns the
header, close button, scroll/focus management, type scale, colours and borders;
arbitrary screenshot CSS, gold border colour and custom fonts are unavailable.

Performance: authenticated bootstrap begins with the account load instead of
waiting for the certificate list. One loader per mounted account deduplicates
in-flight bootstrap and country-specific price reads and retains successful
results for 60 seconds. Failed results are evicted for retry. No localStorage,
global customer cache or ownership bypass. Modal opens reuse the same signed
preview URL already used by the card; all three frame images are mounted eagerly
when the offer is ready so later colour switches can use the browser image cache.
Requests and the modal shell remain independent. Cold image/network latency is
still possible; no claim of guaranteed instant loading or measured live timings.

Current checks: 36 Node tests passed (including request deduplication, market
isolation, expiry/retry/account isolation, frame image mounting and cart paths);
10 focused Python checks plus three frame subtests passed. The full account JSX
passes TypeScript checkJs against installed native component types. Shopify app
build passed. The skill's separate component validator remains unavailable
because its own installed TypeScript dependency is missing. No native live/mobile
visual preview was run: Developer Studio Phase 1 disables development previews.
No commit, push, Shopify publication or Render deployment performed. Existing
certificates, the owner-only preview, Orders/Inbox and multi-item code are untouched.

# Marketplace homepage V2

Task `20261120-168edbd1`, owner `codex-marketplace-redesign-01a1f6fa-20261120`.
The user explicitly requested the Stillwhite-inspired homepage redesign and a
live GitHub/Render release.

Reviewed Stillwhite Australia's homepage, browse, individual listing, seller
landing and how-it-works templates in the browser, including rendered HTML,
semantic headings, forms, layout and navigation. The resulting Sports Cave
implementation uses original code, existing Sports Cave Montserrat typography,
gold/charcoal branding and a new original collector-room hero. Stillwhite's
photography, copy, statistics, stylesheets and scripts are not used.

The homepage now has a full-width photo, transparent navigation, central search,
sport links, category tabs, genuine listings and a concise seller invitation.
The new `/marketplace/browse` page preserves query/category/sport filters and
supports newest and price sorting. Existing root query links remain compatible.
The native browse disclosure works without JavaScript; outside click/Escape
close it when JavaScript is available. The shared seller and item pages retain
their existing forms, privacy and approval behaviour.

There are no invented sales, reviews or purchase-protection claims. The founding
listing offer and collector categories are real. Existing checkout/payout
limitations remain unchanged.

## Delivery

- Hero desktop WebP: 55,054 bytes; mobile: 19,462 bytes.
- Existing logo resized for web use: 4,818 bytes instead of 56,465.
- Responsive image source selection and priority preload; listing photos lazy.
- Existing gzip delivery and asset validators retained. No frontend framework.
- Server-rendered canonical, social and schema metadata; real SearchAction and
  CollectionPage/ItemList; browse URL added to sitemap; filtered results noindex.
- No database, infrastructure, credentials, services or production identity changes.

## Verification

`python -B scripts/test_marketplace.py` covers the existing flows plus responsive
asset budgets, semantic search, the browse route, price ordering, facet
preservation, query escaping and public asset allowlists. Also run syntax, JS
syntax, topology and Studio checks against the exact committed revision.

`scripts/preview_marketplace_static.py` exports synthetic view-only HTML without
starting an app server or using production credentials. Browser automation's
URL policy blocks local file navigation, so visual verification uses the
authorised deployed HTTPS page. No local-file policy workaround is used.

The hero was generated with the built-in image generation tool and exported as
WebP. Source prompt: original editorial photograph of a premium charcoal sports
collector room; burgundy framed jersey at left; framed action image, leather
football, basketball and trading-card slabs at right; understated warm gold;
quiet central wall for white headline and search; no readable logos, signatures,
watermarks, UI or real listing/authentication claims. Saved assets live in
`static/marketplace/collector-room-1600.webp` and `collector-room-800.webp`.

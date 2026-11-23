# Marketplace collector experience — 22 November 2026

Task `20261122-10168fad`, owner `codex-marketplace-paypal-01a1f6fa-20261122`.
Built on main `a2744466` in its assigned Commerce worktree. The task includes
the subsequent request for a restrained Whatnot-style product media experience.

## Result

- Keeps the Sports Cave collector-room hero, gold/charcoal palette, Montserrat
  fonts and lightweight server-rendered pages. Shorter homepage, no public
  sport/category menu or category counts. Existing search/filter URLs still work.
- Product pages use a large portrait media stage, keyboard-accessible thumbnails,
  seller identity, asking price/postage, item details and an enquiry action.
  No live streaming, fake ratings, invented sales or nonfunctional buy buttons.
- Sellers can add one recorded MP4/MOV/WebM clip, up to 15 MB and 60 seconds,
  alongside the existing 2–4 photos. FFmpeg validates and converts it to a
  metadata-free H.264/AAC MP4, at most 960px / 12 MB, with faststart enabled.
  CPU work is limited to one encoder; at most two submissions are read at once.
- Videos use the existing private R2 assets bucket under server-generated UUID
  paths. Only a private reference is stored in the existing runtime-state table.
  Pending/declined/withdrawn videos have no public access. Each GET/HEAD rechecks
  listing approval, supports byte ranges, and uses `no-store`. Public delivery
  is through the existing OS service, with no public R2 URLs or presigned links.
- Administrators can load a pending video in the existing listing reviewer.
  The preview is sent as an inline data URL to the authenticated OS session,
  without registering an anonymously reachable Streamlit media-server URL.
  If R2 is unconfigured the seller form explains this and disables video input;
  a direct video upload fails explicitly rather than discarding the clip.
- New `/marketplace/paypal` and `/marketplace/buyer-protection` pages, footer
  links, homepage information and a product-page protection link. They explain
  that marketplace checkout is not connected. Eligible PayPal Goods & Services
  purchases may qualify; PayPal decides claims. No blanket refund promise.
- Product/Breadcrumb schema remains server-rendered. Approved recorded videos
  add VideoObject metadata. New information pages are in the sitemap.

## References reviewed

- Stillwhite buyer protection and footer placement:
  https://www.stillwhite.com.au/buyer-protection
- Whatnot physical-item page, large gallery/seller/product-detail layout:
  https://www.whatnot.com/listing/TGlzdGluZ05vZGU6MjY0NDEwMTMxMw==
- PayPal Australian policy (reviewed 22 November 2026):
  https://www.paypal.com/au/legalhub/paypal/buyer-protection
- PayPal Australian protection overview:
  https://www.paypal.com/au/digital-wallet/buyer-purchase-protection

Sports Cave copy and styling are original. Stillwhite's US-dollar coverage
wording and integrated-payment claims were not copied to this Australian intake.

## Validation and release

Run `python -B scripts/test_marketplace.py`, `node tests/marketplace_gallery.cjs`,
`node --check static/marketplace/marketplace.js`,
`python -B scripts/validate_render_topology.py` and `git diff --check`.
Python tests run in the runner's credential-free allowlisted environment and
use synthetic images/video, a fake transaction store and mocked R2/Git clients.
No application preview, customer data or production writes are used for tests.

The user explicitly approved committing, pushing to GitHub main and releasing to
the existing Render service in this chat on 22 November 2026. The finished
candidate passed 61 Python acceptance tests plus the gallery interaction check,
JavaScript syntax, topology and Studio static checks before release preparation.
Retain the task worktree for review. No Render service, infrastructure,
credentials, database schema or provider permissions are changed.
The canonical deployment target remains `sports-cave-os` /
`srv-d8kl4on7f7vs73dvavv0`.

Visual research used the reference sites in the browser. Local visual preview
was unavailable under the current browser/Phase 1 preview restrictions. Once a
release is authorised, verify the actual desktop/mobile pages on the existing
HTTPS deployment. The empty catalogue does not justify publishing fake listings.

## What remains before taking payments

These pages do not constitute a PayPal integration. Production payments still
need the appropriate PayPal marketplace/seller onboarding arrangement, approved
credentials, verified server-side order capture/webhooks and fulfilment/refund
handling. Confirm those requirements with PayPal before implementing a sale or
promising the planned 5% on-platform seller fee.

# Compact collection and print downloads

Task 20261123-b598c0c3, owner codex-judgeme-review-20261123.
The owner explicitly authorized all updates live, including the pending review
delivery hardening. The isolated task was merged with current production main
7502e0b8 before these layout edits. Existing Orders, multi-item fulfilment and
certificate generation implementations remain intact; Orders stays separate.

The existing native Shopify account surface is retained. Within its host-managed
width, the desktop certificate panel grows from 60% to 65% and gaps tighten.
Mobile drops the duplicate My Collection heading and dropdown. Previous/next
buttons have their own 44px columns outside a controlled edition carousel and
wrap across editions. No unsupported native swipe/scroll callbacks are used.
Displayed variant sizes omit dimensions; stored identifiers/details are unchanged.
Two paired products use two columns even on narrow mobile. Frame certificate is
the primary action, View certificate stays alongside it, and PDF/free-print links
are replaced by one Download certificate link.

Download certificate uses the owner-bound print asset URL with Content-Disposition
attachment and no-store, not the Shopify CDN image/PDF link. Existing print JPGs
stream byte-for-byte. For historical certificates with only an issued PDF, the
same protected print token serves a 300dpi JPEG derivative of that original PDF.
No existing stored file is replaced, and no edition is reissued or regenerated.
PDFium executes in a short-lived isolated process with size/pixel/time/concurrency
bounds, keeping account downloads independent from supplier PDF rendering. The
existing dependency is reused; requirements and topology do not change.

The review banner has a cropped, full-height artwork column, compact gold stars
and a primary review button. The existing native Judge.me API form stays in place,
without a YouTube field. Included fixes convert WebP review photos to JPEG and
reject explicit provider-error responses even when HTTP 200. API moderation and
verification limits documented in ACCOUNT_REVIEW_JUDGEME_DELIVERY_20261123.md apply.

Checks before publication: 75 Python checks +14 subtests; 41 Node checks; native
JSX TypeScript checkJs, Shopify build/config, topology/diff checks. A synthetic
original PDF was rendered and visually inspected for full page/border/text at
300dpi. No real review was posted. The standalone Shopify skill validator still
lacks its own TypeScript package; installed native component types and build pass.
Live desktop/mobile and download verification are recorded in Studio runtime.
No whole-theme publication is part of this release.

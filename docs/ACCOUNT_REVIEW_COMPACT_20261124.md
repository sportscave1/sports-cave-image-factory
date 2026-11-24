# Compact My Collection review popup

24 November 2026, Australia/Sydney. Task `20261124-c419098d`. The user explicitly authorised the account-page layout change and live release.

Released Shopify app version **reviews-account-compact-final-20261124**:
https://dev.shopify.com/dashboard/74446509/apps/382007410689/versions/1263725871105

The popup now has one native photo/video selector, with its duplicate text removed. Full-width setup guidance sits above a full-width, shallow lifestyle-image preview of the purchased product, followed by the upload control. The redundant product thumbnail/edition header was removed, while the product title remains. Name and optional review title share a row, the review text area is compact, and rating controls occupy one row. Five stars remain the initial selection.

After file selection, a compact row of thumbnails/file indicators and individually labelled removal controls replaces the large empty drop area. Change photo/video returns to the native selector. Up to five files including one video, existing size checks, raw-file multipart submission, validation, consent value and OS endpoint are unchanged. The image query still requests only the first two product images at up to 640px; the lifestyle image remains the second ordered product image. Only the account component and its built bundle changed; no storefront theme or backend changes were made.

## Verification

- Ten focused JavaScript tests passed, including the existing product-image selection checks and a real FormData assertion for photo and video submission to `/api/collector-vault/review`.
- Official Shopify app build, deployment validation and release succeeded. The separately bundled skill validator could not run because its type index was absent; this is not reported as a passing validator.
- Verified the released extension on the actual signed-in My Collection page. Setup guidance appears above the correct Nolan Ryan room image; exactly one Add photo/video label is present, with Shopify's native Add file action below it.
- Checked requested mobile viewports 390×844 and 375×667 (host-reported CSS heights were 845/668 because of display scaling). The empty popup measured about 580px tall at the larger size. With four photos and one video selected at the smaller size, it measured about 560px tall, with matching client/scroll heights and widths: no popup overflow. All fields, previews, change/remove actions and submit/cancel actions were visible.
- Verified Change photo/video clears the selected list and restores the single selector. No real review was submitted during this layout check.
- Restored normal browser sizing and checked desktop: about 607px popup height within a 901px viewport, without overflow. Cancel closed the popup normally.

An on-screen keyboard, very small viewport, long validation messages or accessibility text scaling may still require the host's normal scrolling; controls remain accessible rather than being clipped. The single-row review field remains a multi-line text-area control and accepts the existing review length.

Proof screenshots and measured mobile dimensions are in `artifacts/account-review-compact-20261124/`. The account extension is hosted and released by Shopify; no Render backend rollout is required for this layout-only change.

# Sports Cave on-demand wall preview

Saved on 8 October 2026 to **Sports Cave - On-Demand Wall Preview**, theme `189389340979`, role `UNPUBLISHED`.

[Preview the unpublished theme](https://www.sportscaveshop.com/products/shohei-ohtani-wall-art?preview_theme_id=189389340979)

This directory contains the four changed files from a duplicate of live theme `189371023667` (Sports Cave - Lightweight Wall Preview V2). It is an overlay for that full theme, not a standalone theme or Render deployment. The older implementation in `shopify_theme/` is not the current live storefront version and was not overwritten.

## Changes

- `sections/main-product.liquid`: removes the eager artwork-helper script. Existing launcher HTML, theme settings, variant handling and purchase controls remain intact.
- `snippets/sc-wall-visualizer-v1.liquid`: initially emits only a lightweight context placeholder. The existing `sections/sc-wall-preview.liquid` serves the full original product-context markup after activation.
- `assets/sports-cave-wall-preview-loader.js`: click-only section/CSS/helper/engine loading, shared asset promises, per-root hydration guard, accessible branded loading dialog, close/Escape, error/retry, timeouts, focus restoration and reuse on reopening. Independent loads settle before a retry to prevent overlapping hydration.
- `assets/sports-cave-wall-preview.js`: accepts an explicit hydration event and skips roots without their modal markup. Existing rendering, camera, calibration, variant, analytics, archive and cart logic is preserved.

The source theme already deferred the main viewer JS and CSS, but downloaded the 8,089-character artwork helper and rendered the hidden preview UI on every product visit. All of those resources and the full preview DOM now wait for a click. There is no idle prefetch, polling, or added third-party library.

The original product-template CTA, layout and stylesheet were copied unchanged. Required existing files include `assets/sports-cave-wall-artwork.js`, `assets/sports-cave-wall-preview.css` and `sections/sc-wall-preview.liquid`; these are already present in the duplicate.

## Verification

- Liquid Theme Check passed on all four changed files, with only non-error snippet-reference/optional-parameter warnings. Both JavaScript files passed syntax checks.
- Desktop 1366px and mobile 390px: zero engine/helper/CSS/section requests and zero modal DOM before interaction; first opening requested each once; reopening caused no additional downloads.
- Mock camera capture, stopping the camera after capture, photo upload, all sizes, all four frame choices, true-scale calibration, artwork dragging, close/reopen and keyboard activation passed.
- Failed section loading showed an error and retry. Escape during retry kept the viewer closed when loading finished, restored launcher focus, and a subsequent opening reused the completed assets.
- Preview Add to Cart returned HTTP 200; both preview and normal product Add to Cart produced one item in isolated browser carts, which were cleared afterward. No orders were placed. Preview archive/analytics writes were intercepted during feature testing.
- Remote readback matched all four uploaded files. The live theme remains MAIN and the duplicate remains UNPUBLISHED. All 315 source files exist in the duplicate.

## Limits and concurrent changes

Intermittent desktop console errors originated in the unchanged theme gallery (`main.js` scrollTo) and Boostymark region-blocker script. Clean follow-up baseline runs on both themes produced neither error, so these intermittent errors were recorded rather than claimed fixed. No preview-loader stack errors were observed. Physical mobile cameras, Safari, native sharing, and a separate sold-out-product browser scenario were not verified. Sold-out gating and native purchase code were not changed. No Lighthouse speed-score improvement is claimed.

During testing the live `templates/product.json` changed independently (collector-details/CTA settings). The duplicate's product template still exactly matches the initial captured source. This task never wrote that template or any live theme file; review those concurrent live edits before any later publication.

Local browser evidence and test scripts are in `shopify_theme_reviews/on-demand-20261008/` (ignored review workspace): `qa-results.json`, `extra-results.json`, `baseline-results.json`, desktop/mobile screenshots, and `qa.cjs`, `extra.cjs`, `baseline.cjs`.

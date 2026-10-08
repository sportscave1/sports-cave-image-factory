# Email wall-preview auto-open

## Cause and scope

The observed Shopify CDN asset `sports-cave-wall-preview-loader.js?v=95333776912844262841791411548` (theme asset path `/cdn/shop/t/66/`) ended after registering its click handler. It contained no `sc_wall_preview` handling. The product page therefore remained closed with the query flag present. The repository had a newer, DOMContentLoaded-only implementation which could also miss a later-inserted trigger or root.

Only the storefront loader is changed. No email HTML, SC_WALL_PREVIEW_URL generation, viewer engine, camera implementation, Liquid product template, purchase code or CSS is changed.

## Implementation

Manual activation and email activation share `openPreview()`. On DOM readiness, an exact `sc_wall_preview=1` invokes that path when both the enabled trigger and product root exist. The existing `prepare()` promise waits for section markup, CSS, artwork helper and viewer initialization, then calls the existing `root.scWallOpen()` (showDialog). This opens the existing “Take a photo of your wall” interface, not an accordion or scroll target.

If markup is delayed, a MutationObserver and Shopify section-load listener watch for it. They disconnect on the accepted attempt (including manual activation) or after 20 seconds. That timeout is only a failure bound, never an artificial opening delay. Asset failure uses the existing retry/close interface. Re-including the script does not install handlers twice. Closing the popup does not reopen it.

The existing focus restoration, overlay mounted on body, scroll locking, camera opt-in and upload controls are reused. Only the consumed `sc_wall_preview` flag is removed; product path, variant, UTM parameters, hash and history state remain intact.

## Installation (not performed)

1. Use the existing current Shopify theme workflow. Copy ONLY `shopify/on-demand-wall-preview/assets/sports-cave-wall-preview-loader.js` to `assets/sports-cave-wall-preview-loader.js` in a current-theme duplicate.
2. Preview the duplicate using a product URL with `variant=...&sc_wall_preview=1&utm_source=email`. Confirm the same photo popup, selected variant and normal manual activation without the flag.
3. Publish the reviewed theme through the normal workflow. Alternatively an explicitly approved asset-only update to the current published theme would take effect without changing theme identity.

Do not blindly publish the old full on-demand duplicate: other theme changes may have happened since its creation. Do not replace `shopify_theme/`, which contains an older implementation. No Render/OS deployment or database migration is needed. No theme upload or publication was performed for this fix.

## Verification

`tests/test_wall_preview_email_link.cjs` uses the actual viewer engine, helper and existing modal HTML with synthetic product data. All requests are intercepted; no production writes or camera access occur. A fixture copy of the deployed CSS is used solely to check modal geometry.

Passed in Chrome and Edge, each at 1440x900 and 390x844:
- existing modal heading, Take photo, Upload and Close & continue shopping visible inside viewport;
- no scroll/second click, one modal, one initial section fetch;
- variant form value, URL variant, UTM fields and hash retained;
- no camera request on opening; mocked request only after Take photo;
- Upload launches the existing file chooser;
- close/escape, manual reopening and asset reuse;
- ordinary visits remain lazy; normal launcher works;
- independently delayed trigger/root insertion;
- failed section request and successful explicit retry;
- bounded observation on unavailable pages and duplicate script inclusion;
- no browser JavaScript errors.

These are desktop-browser tests with mobile viewport emulation, not physical iPhone/Android verification. Safari/WebKit is unavailable locally. Real camera capture and full photo processing were not re-tested; their code is unchanged. The Shopify skill validator could not start because its bundled `@shopify/theme-check-common` dependency is missing; JavaScript syntax and executable browser tests provide validation of the changed JS asset.

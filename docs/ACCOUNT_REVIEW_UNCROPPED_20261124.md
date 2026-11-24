# Uncropped account review popup

User authorised the responsive layout correction and live release on 24 November 2026.

Live Shopify app version: [account-review-screen-fit-20261124](https://dev.shopify.com/dashboard/74446509/apps/382007410689/versions/1263783706625).

The lifestyle image uses a square frame, `objectFit="contain"`, and a maximum width of 320px. It shrinks naturally within the available column instead of cropping the room image. The source remains the second ordered product image, requested at up to 640px through Shopify CDN. No additional media request or sizing timer was introduced.

Portrait mobile has the compact form followed by setup guidance, the full square image and one small native upload selector alongside it. Above a 500px content width, the form sits on the left and image/upload controls on the right, including landscape phones. Five selected files use a narrow list with contained photo thumbnails, file names, individual remove actions and Change files. Existing rating, text validation, native OS multipart submission, limits and Dropbox/reward handling remain intact.

Shopify's supported `size="max"` modal gives the largest host-defined area and moves the mobile popup higher than a content-sized popup. The host still imposes its own top inset (about 10% of viewport height in the observed mobile account). The extension API has no position/top property; this release does not claim edge-to-edge positioning or guaranteed zero scrolling with a software keyboard, accessibility zoom, arbitrarily small screens or expanded error text. Shopify's normal fallback scrolling remains available instead of clipping content. See [Shopify Modal properties](https://shopify.dev/docs/api/customer-account-ui-extensions/2026-04/web-components/overlays/modal).

## Verification

- Official Shopify configuration validation returned valid with no issues. App build and release validation passed. Account extension bundle is about 97.5KB original / 40.4KB compressed.
- Nineteen focused tests passed, including a real synthetic FormData assertion for review text plus photo/video at `/api/collector-vault/review`, correct image selection and account certificate behaviour.
- The separate bundled Shopify skill component validator could not load its missing TypeScript dependency. It is not counted as a passing validator; the official Shopify build/release checks passed.
- Verified the actual released account extension in the signed-in My Collection page. No real review or email was submitted for this layout task. Four tiny synthetic images and a selection-only video placeholder were used to test the five-file layout, not video playback.
- Final release: requested 320x568 and 375x667 portrait, 667x375 landscape, current 881x826 desktop and 1440x900 wide desktop. Display scaling reported 375x668 / 668x375 in some captures. Measured no horizontal/vertical scrollable overflow inside the popup; Submit review was within the viewport. Empty and five-file states were verified on the small portrait and landscape screens. The wide desktop image measured 320x320, with contain fit.
- Individual removal reduced five selected files to four. Change files restored the single native selector. Cancel closed the popup. Final console error list was empty; viewport override was reset.
- Proof screenshots and machine-readable measurements: `artifacts/account-review-uncropped-20261124/` (local evidence).

Only the account extension source/bundle and its layout regression assertions changed. No storefront theme, OS backend, database, customer emails or rewards configuration changed. This layout is hosted by Shopify and requires no Render backend rollout. Git uses the established `[skip render]` extension-only release convention.

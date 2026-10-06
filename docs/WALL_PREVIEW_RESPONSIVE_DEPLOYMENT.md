# Wall Preview and Image Protection deployment — 6 October 2026

Both DEV and LIVE are deployed and verified. Six feature files match between themes after normalising line endings. Existing layout content is preserved, with one protection render integration. No whole theme was published.

## Architecture (1–9)

1. Existing implementation: `shopify_theme/snippets/sc-wall-visualizer-v1.liquid`, `storefront-protection.js`, `image_protection.py`, `image_protection_ui.py`, `image_protection_status.py`, `storefront_protection_api.py`, and `shopify-storefront-protection.liquid`. Shopify `layout/theme.liquid` supplied the DEV legacy loader. The live Wall Preview was the current persistent-capture implementation; DEV had an older copy.
2. Created: `shopify_theme/assets/sports-cave-wall-preview.js`, `sports-cave-wall-preview.css`, `sports-cave-image-protection.js`, `sports-cave-image-protection.css`, and `shopify_theme/snippets/sports-cave-image-protection.liquid`. New tests: `tests/wall_preview_responsive_camera.cjs`, `wall_preview_faults.cjs`, `wall_preview_deployed.cjs`, `wall_preview_deployed_shopping.cjs`, `wall_preview_performance.cjs`.
3. Modified: existing Wall Preview Liquid; the five protection Python/JS/reference files listed in point 1; `tests/test_wall_preview_completion.py`, `test_storefront_protection.cjs`, `image_protection_wall_camera.cjs`, `wall_preview_completion_fixture.cjs`, `wall_preview_completion_queue.cjs`, and `wall_preview_completion_ui.cjs`. Both Shopify layouts received the scoped loader integration. This report records the deployment. Unrelated Inbox changes were not edited in this task.
4. Retired: giant inline Wall Preview CSS/JavaScript and the blocking rotate-phone overlay. The legacy Render script URL remains a compatibility loader; no database tables or history were removed.
5. Wall Preview structure: original named Liquid snippet retains markup and product JSON, loads dedicated CSS via `asset_url`, and deferred dedicated JS. Keeping the snippet name preserves existing product integrations.
6. Protection structure: small Liquid loader, dedicated CSS and deferred JS, existing OS settings and public config endpoint.
7. The original inline implementation was extracted rather than duplicated. The legacy protection loader reuses the same runtime asset source. Section unload removes instance listeners and camera resources.
8. Both features now use Shopify CDN assets with versioned `asset_url` URLs and independent browser caching. No new framework or SDK.
9. Render continues to serve only the small protection configuration to the Shopify installation: `https://sports-cave-image-factory.onrender.com/api/storefront-protection/config`. Existing archive/storage APIs are unchanged. The already-live config was sufficient for this theme deployment. No Render topology or environment change was performed in this task.

## Wall Preview (10–18)

10. Camera cropping came from competing outer visualViewport sizing, inner fullscreen `100vh`, and absolute control offsets. Browser chrome and short landscape heights made their coordinate systems disagree.
11. Unified viewport sizing and a camera grid reserve a real controls row. Removed the landscape-blocking rotate overlay. Preserved the artwork renderer, scaling, frame/size selection and cart logic.
12. Controls account for top/bottom safe areas and dynamic viewport height, with fallback sizing. Short layouts keep a usable shutter and library/close targets.
13. Generation fencing rejects late camera permission results after close. Streams stop on close, visibility loss and section destruction. Reopening cannot be stopped by an older asynchronous camera request. Permission denial and unsupported cameras return to a usable upload chooser.
14. Fixed desktop Download/Share interception by the existing theme header's document-level pointer handler using narrowly scoped window capture. Fixed silent artwork-load failure with an explicit retry state; blank artwork cannot be saved. Added section lifecycle cleanup and removed stale rotation blocking.
15. Camera/heavy preview initialization remains lazy. Product pages do not fetch the wall artwork before opening. Styles and runtime are independently cached; no recurring scans or polling were added.
16. Product HTML, alt text, canonicals, structured data and CDN media delivery were not changed. Existing web artwork derivatives remain unchanged; no print masters were published. Lab measurements below do not establish a field Core Web Vitals improvement.
17. Added visible keyboard focus, scoped modal focus trapping, suitable top-control targets and reduced-motion support. Existing Escape/close/focus restoration remain. Toast does not take focus.
18. Chrome and Edge local camera matrices passed. Deployed DEV and LIVE Chrome tests passed 20 viewport sizes: 320×568, 360×640, 375×667, 375×812, 390×844, 393×852, 412×915, 430×932, 568×320, 667×375, 844×390, 932×430, 768×1024, 820×1180, 1024×1366, 1280×720, 1366×768, 1440×900, 1920×1080 and 2560×1440. Camera tests use synthetic media. Physical iOS/Android cameras and actual Safari, Firefox and Samsung Internet were not available and are not claimed tested.

## Image Protection (19–30)

19. Found the prior mixed security work, subsequent OS-security removal, and isolated protection consolidation in git history, including `c599888`, `9f46399`, `401f38d` and `0dfdd5e`. The isolated website protection was active, with a DEV Render loader.
20. Reused its admin controls, app-setting key, allowlist, scoped selectors, print/copy/drag protections and watermark defaults. No OS session or screenshot-security system was restored.
21. Authoritative settings remain in the existing `app_settings` pattern under `storefront_image_protection`. Server cache is 60 seconds; public responses use a 30-second cache and ETag. Only harmless protection flags are exposed. The deferred script makes one bounded asynchronous config request and fails open. No migrations or setting changes were needed.
22. Right-click: enabled artwork blocked; disabled state and normal non-artwork interactions preserved in local tests. LIVE homepage, collection and product checks passed.
23. Drag: browser image dragging blocked on protected media; Wall Preview's intentional artwork positioning still passed.
24. Copy: scoped protection passed local assertions, leaving form input and ordinary text controls usable.
25. Long-press: scoped WebKit touch-callout and selection rules verified. Real hardware/browser long-press behaviour remains device-dependent and was not physically verified.
26. Print: protected media hidden in print emulation; normal page text retained. Local and deployed checks passed.
27. Watermarks remain OFF by default and were absent in deployed checks. Existing optional text, opacity, position and separate wall-preview setting remain; no source files or downloaded composites were altered.
28. Camera/upload/completed wall media are protected without pointer-move interference. Camera, drag, PLACE, size/cart controls and queued saves passed with protection active.
29. Official Download passed, including another Download while archive acceptance remained queued. Each deliberate action received a distinct capture request; local downloads did not wait for storage.
30. Browser deterrence cannot reliably stop iOS/Android hardware screenshots, Windows/macOS screenshot tools or another camera. No such guarantee is made. No DevTools detector, constant blur or heavy loop was added.

## File sizes, performance and validation (31–42)

Sizes below are uncompressed local file bytes, approximately; LF/CRLF changes affect raw byte counts without changing content. Shopify compressed transfer sizes are smaller.

31. Wall JS: 132,761 bytes; observed Shopify transfer about 27,277 bytes.
32. Wall CSS: 98,682 bytes; observed transfer about 13,792 bytes.
33. Wall Liquid: approximately 23.7 KB, down from approximately 256 KB of combined inline source.
34. Protection JS: 7,685 bytes; observed transfer about 2,659 bytes.
35. Protection CSS: 4,541 bytes; observed transfer about 997 bytes.
36. Protection Liquid: 386 bytes.
37. Public config: 505 bytes in the measured response.
38. Product feature loading: four CDN assets plus one asynchronous config request. Protection-only pages need two CDN assets plus config. These replace the former inline/external arrangement, so this is not a claim of five net additional requests on every page.
39. Runtime dependencies added: none. Playwright and Shopify's theme validator were used for testing.
40. Three-run product lab median LCP: baseline LIVE 2,496 ms, tested DEV 1,756 ms. Product CLS was approximately 0.000074 in both groups. This is a small, noisy sample, not causal proof. The final LIVE product shopping run recorded LCP 1,892 ms and the same CLS. INP was not measured as a representative post-release field metric. Existing Shopify 30-day figures were LCP p75 4,714 ms, INP p75 128 ms, CLS p75 0.12; they predate this change.
41. Final LIVE camera/completion run: no console errors. Shopping tests found an existing theme `main.js` gallery `scrollTo` error before Wall Preview opened. An intermittent existing Boosty extension error was also seen during earlier tests. Neither unrelated component was edited. No new feature runtime error occurred.
42. Tests: Python completion/protection suite 22 run, 19 passed, 3 skipped (disposable database unavailable); JS protection 131 assertions passed; local completion 16 journeys passed; camera 20 viewports each in Chrome and Edge passed; fault suite 5 scenarios passed; capture queue passed; protection/camera integration passed. Deployed DEV and LIVE camera/completion, homepage/collection/product protection, real isolated Add to Cart/cart drawer, scoped cart cleanup and HTTP-200 asset checks passed. Python compile, JS syntax, Render topology and git diff checks passed. Shopify validator: all six files valid, only unreferenced-snippet warnings because the repository is a partial theme. Tests intercepted synthetic preview POSTs: no production Dropbox test captures, checkout or customer order was created. Actual Dropbox end-to-end delivery was not retested by this frontend task.

## Deployments (43–55)

43. DEV: Sports Cave DEV — Codex.
44. DEV ID: 189335863603, UNPUBLISHED.
45. DEV deployment completed first: four assets, two snippets and the layout loader integration.
46. DEV responsive, completion, protection and shopping tests passed before LIVE integration was changed.
47. DEV URL: https://www.sportscaveshop.com/?preview_theme_id=189335863603
48. LIVE: Symmetry 9 Gifting.
49. LIVE ID: 188890644787, MAIN; re-confirmed before writing.
50. LIVE deployment completed using the authenticated Shopify code editor. New dependencies were created first, then the existing wall snippet and layout integration. Shopify API read-back verified final source.
51. Only these seven Shopify files were written: `assets/sports-cave-wall-preview.js`, `assets/sports-cave-wall-preview.css`, `assets/sports-cave-image-protection.js`, `assets/sports-cave-image-protection.css`, `snippets/sc-wall-visualizer-v1.liquid`, `snippets/sports-cave-image-protection.liquid`, `layout/theme.liquid`. No whole theme publication, product, checkout, cart source, theme settings or customer data changes.
52. LIVE post-deployment tests passed against ordinary published URLs without preview parameters. Test cart contained one expected variant and was emptied by removing only that session's test line. Checkout handoff presence was checked; no checkout was submitted.
53. LIVE URL: https://www.sportscaveshop.com/
54. Deployment correction: a concurrent local overwrite replaced the wall snippet with shell-command text. Read-back caught a brief incorrect snippet upload, and the preserved DEV-tested source was immediately restored before final testing. No full-theme rollback was needed. The local snippet is repaired as well, but this repair is not committed by this task. Existing theme/snippet backups remain under `output/responsive-backup`. Do not redeploy the corrupted snippet from commit `2edf22d`; use the repaired current working file.
55. Final API read-back confirms all six feature files match DEV and LIVE exactly after line-ending normalization. Layouts retain their respective existing content and the same protection loader. No manual installation remains for the user. This task did not make a Git commit or push; the checkout advanced concurrently to `2edf22d` during the work.

## Evidence

- `output/deployed-wall-189335863603.json` and `output/deployed-wall-188890644787.json`
- `output/deployed-shopping-189335863603.json` and `output/deployed-shopping-188890644787.json`
- `output/wall-preview-performance.json`
- `output/deployed-wall-188890644787.png`
- `output/responsive-backup/188890644787/` (original LIVE layout and wall snippet)

No credentials were placed in client assets. UGC permission remains separate from operational preview capture. Existing renderer, scale, product/variant/cart logic, analytics and persistent capture/archive protocol remain in place.

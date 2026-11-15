# Wall preview deployment — 8 October 2026

## Shopify

- Verified store: `sportscave-nb.myshopify.com`; public store `www.sportscaveshop.com`.
- Original/current published theme: **Sports Cave - On-Demand Wall Preview**, `189389340979`.
- Full backup: `189403627827`, **unpublished**, processing complete.
- Requested backup name: `SPORTS CAVE - LIVE BACKUP - 08 OCT 2026 - BEFORE WALL PREVIEW FIX`.
- Shopify stored the shortened name: `SPORTS CAVE - LIVE BACKUP - 08 OCT 2026 - BEFOR...`.
- All 314 downloaded backup files matched the original live theme byte-for-byte before deployment.
- Updated only `assets/sports-cave-wall-preview-loader.js`, using explicit store/theme IDs, `--only`, `--nodelete`, and `--allow-live`. No theme publication or replacement.
- Downloaded all 314 live files again after deployment: the loader was the **only** changed file.
- Local and published loader SHA-256: `01CB5B07388A114D683362E50445331646091AAB68E00FA3258B135957945E62`.
- Live page served `/cdn/shop/t/66/assets/sports-cave-wall-preview-loader.js?v=141024799056202201671791456231`.
- No Cave Apps store operations were performed.

## Git / Render

- Implementation already committed and pushed: `47a5a747c58834c2c135c30eb5231b60505267c7`.
- Fetched GitHub main and verified that commit is its ancestor. Remote main at verification: `e5dc732772626293babe45f72c684be4c44ad77d`.
- No duplicate implementation commit or redundant push was needed. Unrelated local Mockups changes were not staged or committed.
- Canonical Render service `sports-cave-os` (`srv-d8kl4on7f7vs73dvavv0`) automatic new-commit deployment `dep-db3n6lmgekts73dsfatg` is **live** at `e5dc732`.
- No manual Render deployment or infrastructure change. Shopify deployment was independently performed and verified.

## Verification

- JavaScript syntax check passed.
- Existing isolated browser suite passed in Chrome and Edge at 1440×900 and 390×844, including delayed initialization, retries, bounded observation, duplicate script inclusion, camera opt-in, upload chooser, and manual activation.
- Live product tested: `/products/peter-brock-tribute-art?variant=52547812589875&sc_wall_preview=1&utm_source=email&utm_campaign=wall-preview-verification`.
- Live Chrome and Edge checks passed at both sizes: correct shop/theme, automatic existing modal, exact selected variant, retained UTM parameters, controls within viewport, close/reopen, upload chooser, normal visit without auto-open, and manual launcher.
- Camera requests were mocked: none on initial opening; one after Take photo. No photos uploaded and no orders/customer messages created.
- Related Python suite: 28 tests, 19 passed and 9 skipped; no failures.
- Safari/WebKit, physical iPhone/Android, real camera capture and complete photo-processing upload were not tested.
- A raw HTTP request met a connection-verification challenge; actual Chrome and Edge product visits succeeded.

Evidence: `wall-preview-live-verification.json`, `wall-preview-live-chrome-1440.png`, `wall-preview-live-chrome-390.png`, and corresponding Edge screenshots in this directory. Verification runner: `verify-wall-preview-live.cjs` (read-only storefront actions, mocked camera).

## Rollback

The full unpublished backup remains on Shopify. For a targeted rollback, restore only its original `assets/sports-cave-wall-preview-loader.js` into live theme `189389340979` using the same explicit store and targeted push flags. Do not publish the backup unless separately authorized.

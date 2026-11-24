# Draft reviews: performance and collection form — 24 November 2026

The user authorised Git/Render releases and changes to the existing unpublished OS review theme, explicitly prohibiting changes to the live Shopify theme or customer automation activation.

## Scope and live-theme protection

- Live theme: `190888968499`, Sports Cave - 48 Hour Countdown - 24 Nov. No upload or publication command targeted this theme.
- Updated duplicate: `190889230643`, Sports Cave - OS Reviews Test - 24 Nov. It remains unpublished.
- Only three duplicate theme files were uploaded: `assets/sc-customer-reviews.js`, `sections/sc-customer-reviews.liquid`, and new `snippets/sc-review-os-preview.liquid`.
- Shopify readback matched all three prepared files byte for byte. Widget CSS is byte-identical to the live theme.
- A fresh readback of all seven sampled live files matched the before snapshot byte for byte: widget JS/CSS, section, original preview snippet, review/product templates and global settings.
- No customer-account extension, Judge.me setting, email automation publication, reward setting, discount, or customer record was changed by this task.

## What changed

The draft keeps the original card, archive, histogram, gallery and responsive layout. Its first four cards are rendered in Liquid with OS media URLs, so they appear without waiting for JavaScript or the feed. The original Australian and US priorities use the imported Judge.me UUID suffix, rather than the new internal database UUID. The selected original photo reviews remain featured; videos remain in OS/Dropbox but are hidden in this storefront view, matching the live restoration.

The new `/reviews/widget` endpoint returns the selected photo cards, aggregate/histogram and five archive rows in one small response. Further archive pages are fetched only on Load more; the browser no longer downloads all 209 reviews in the background. Country-scoped requests are shared, bounded, timed out and retryable. Partial-page failures preserve existing rows. Responses are cached for 30 seconds and invalidated with existing review moderation/settings actions.

The final query uses one round trip on the existing bounded application read pool. It selects only published reviews and approved copied Dropbox images. Source receipts stay on the server; public JSON exposes only opaque media routes. Approved media metadata is primed for the image route, avoiding another metadata query for every newly displayed photo. No schema, pool size, infrastructure topology or credential was changed.

The draft's existing Write a store review button opens the collection-style form: How does it look in your space, star rating, Show us your setup, name, optional title, review and photo/video attachments. It supports keyboard-accessible native rating radios, file previews, upload progress, bounded files and retry without discarding entries. Its script is authorised by a CSP hash; submissions remain same-origin and signed.

Submission routes remain `/reviews/write` with signed product/store context. Anonymous submissions enter OS Reviews as pending and unverified, with media unapproved until moderation. They cannot earn verified-order rewards. The existing `save_owned` path durably uploads originals to `/Sportscave Team Folder/03_ASSETS/Reviews` before creating Dropbox WebP copies/posters. No upload can silently fall back to Judge.me or another storage provider.

## Validation and evidence

- 36 focused Python tests passed against a disposable loopback PostgreSQL fixture: storefront SQL/country ordering/pagination/cache, collection boundaries, Dropbox-first media ownership, video posters/ranges, native submission/moderation, reward guards and existing account delivery.
- Three synthetic browser tests passed: AU/US first-card order, one initial feed request, pagination failure/retry, and a mobile collection form that preserves entries on error and sends photo/video multipart data to its same-origin endpoint.
- First synthetic cards rendered within the 1.5-second assertion; real initial cards additionally use server-rendered previews.
- JavaScript syntax and Shopify validation passed for all three theme files. The validator's informational external-image warnings are expected: the user explicitly requires Dropbox-backed OS media instead of Shopify-hosted copies.
- Browser checks covered both draft pages on desktop/mobile, product-to-review navigation, correct first cards, the OS iframe form, image loading and archive pagination. No production review, upload, email or discount was submitted during testing.
- Public media HEAD verification returned `image/webp`, 21,874 bytes for a 320px thumbnail, and five-minute public caching.
- Evidence images are under `artifacts/draft-review-verification/`.

The initial deployed version exposed excessive uncached database latency despite a small payload. This was measured and corrected with the final single-query pooled implementation; final production timings and release IDs are recorded below after rollout verification.

Studio's broader verification detects pre-existing trailing whitespace in `shopify_customer_account/extensions/customer-certificate-vault/src/Montserrat-OFL.txt`, brought in from existing main. That unrelated file was preserved. Focused checks and `git diff --check` for this task's own changes pass.

## Release verification

Final executable source: `a311ad29c4fa606e836491579850063a9d2fd4ff`. Documentation-only follow-ups do not redeploy the application. The existing canonical Render primary and supporting services are retained; no service or Blueprint was created or synced.

The primary deployment `dep-dc2ds795efls73bjqd20` became Live at 11:48 AEDT. Final measured public HTTP 200 responses from the local client were AU first page 0.816 seconds / 14,478 bytes, US first page 0.920 seconds / 13,881 bytes, cached AU 0.479 seconds, and US Load more 0.690 seconds / 1,736 bytes. These are observed samples, not guaranteed global timings. First pages contained 17 featured photo reviews and five archive rows; Load more contained five rows and no repeated featured payload.

Final browser verification showed the original AU first four cards, five loaded archive rows, OS-only media hosts and no review video. Mobile Load more increased the archive to ten rows without errors. The preview session was then exited through Shopify's UI: the preview bar disappeared and the normal live page loaded two Judge.me scripts. Browser viewport overrides were reset.

Final theme-file SHA256 values: widget JS `239fe9599a60fe2bdbf35fcab46b85f3c7ae2b7c451bece5db71559c52fcc824`; section `bda441a18b73ba991f437d30272a792a41d37232e2969cd12d9c59b84be192ff`; OS preview snippet `76059d6cebfcf2ceb92bdfb4fa8855ffc88d74d75ae8b1a081aff5ea2333381a`.

The duplicate can be reviewed at https://www.sportscaveshop.com/pages/reviews?preview_theme_id=190889230643. Do not publish this duplicate or activate request/reward automations until the separately controlled test-buyer approval and reward-delivery journey is completed. This task does not replace that end-to-end customer test.

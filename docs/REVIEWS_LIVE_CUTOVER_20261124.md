# Native reviews production cutover

24 November 2026, Australia/Sydney. Task `20261124-c419098d`, owner `codex-draft-parity-20261124-a39b`. This report supersedes earlier draft-only status reports. Publication and automation activation were explicitly authorised by the user.

## Released state

- Shopify theme **190889230643** is live, published using Shopify CLI and confirmed on the normal public reviews and product URLs. Previous Judge.me theme **190888968499** is retained, unpublished, for rollback. Its assets were not rewritten during this release.
- Main executable commit **b75166d506cdaa87df6ba7c3a7a227602c1406ee** is live on the existing primary OS, webhooks and SEO/CRM worker services. No infrastructure or service identity changes.
- Customer account extension version **reviews-native-media-20261124** is released. My Collection keeps the purchased-product lifestyle image and submits through authenticated OS review endpoints. No active account submission route calls Judge.me.
- Post Checkout automation **26b47e22-b962-4c0b-b964-392a6399caf4**, revision **116**, is ACTIVE with live publication **8**. All five reviewed emails are enabled: thank-you/collector access, three conditional product review requests, and collection follow-up. Runtime readback confirmed LIVE after the final deployment.
- Requests retain fulfilment +14/+19/+24 days online and +7/+12/+17 days POS, up to three purchased products, without reminders. Review links resolve to opaque OS order-bound forms. Email clients cannot reliably accept photo/video attachments inside an email form; the button opens the complete OS form.
- Photo and video rewards are enabled at **30%**. Delivery gate is enabled on primary and CRM worker; the deployed worker returned `NATIVE_REWARDS_WORKER_GATE True`. Rewards require a published, verified native purchase review and approved, copied media, irrespective of rating. Existing customer restriction, one-per-order, single-use, expiry and suppression guards remain.
- Judge.me requests are disabled separately for domestic, international and POS orders. The actual scheduled-request table was empty after disabling; its cached aggregate briefly lagged. Judge.me remains installed and its historical reviews are retained. Previously sent Judge.me emails cannot be recalled and retain their original links.

## Display and collection

The public store showed **209 reviews**, **4.82/5**, the existing rating breakdown, ordering, dates and Verified buyer presentation. All imported badges preserve the owner's stated verification. Existing customer photos and carousel presentation remain; legacy hidden videos remain hidden. Newly approved native videos can display on demand with lightweight posters and no initial video download.

Text-only product reviews now use the first product/black-frame image as a 68px thumbnail, requested at 136px for sharp displays, lazy loaded with asynchronous decoding. Customer images take precedence. A sampled thumbnail was 3,332 bytes with WebP negotiation. Catalogue images stay on Shopify's CDN; customer originals and generated variants stay in Dropbox.

Public, buyer-link and account forms start at five stars and place name, title and review above uploads. Visible publication notice, consent checkbox and new-tab fallback are removed. Automatic consent values and server validation remain. Originals reach Dropbox before acknowledgement, then the worker creates 320/640/1280 WebP images or video posters. Honest browser transfer progress remains; a server cannot fetch a local file without its bytes first uploading. Supported application limits remain 25MB/photo, 150MB/video and 250MB combined, up to five files including one video.

## Verification

- 128 focused Python tests passed, covering native account submissions, media storage/processing, widgets, deduplication and review journeys.
- 38 automation/publication/lifecycle tests passed, including already-reviewed request slots advancing without duplicate email sends.
- Five browser tests passed for country rules, ordering, dates, badges, thumbnails, pagination recovery, deferred video, multipart forms, default stars and editor CSP.
- Six account JavaScript utility tests and official Shopify app build/deploy validation passed. The bundled component validator could not run because its packaged dependencies/type resources were missing; this is not represented as a successful check.
- Topology validator passed. Existing unrelated license whitespace warning was preserved.
- After publication, actual public reviews and product widgets loaded the OS data. Live form iframe loaded, five stars were selected, customer photo viewer opened and Load more advanced from five to ten reviews. Signed-in My Collection showed the correct Nolan Ryan lifestyle image and native form.
- Earlier labelled photo/video test reached Dropbox and completed worker variants/posters; the QA review was archived. Shopify accepted the restricted QA reward definition, which is expired. No real customer's purchase review slot was consumed, no manual customer email was sent, and a real inbox receipt and coupon redemption were not claimed as tested.

## Performance and remaining work

Final desktop Lighthouse 13.6.0 on the published public reviews page: **70 performance**, **376ms FCP**, **4.95s LCP**, **1ms total blocking**, **0 CLS**, approximately **4.41MB**, **zero Judge.me requests**. Earlier Judge.me baseline was 42 performance and 1,272ms blocking. Both runs warned that background loading exceeded the audit time limit; results are indicative, not a guarantee. LCP remains slower than desirable and was not an improvement over that earlier baseline.

Further page-wide improvements: replace the decorative 696KB footer GIF with an efficient equivalent, audit duplicate Google tags and other advertising loads, and investigate the largest visible review image's loading priority. These affect broader store presentation/tracking and were not changed as part of the backend cutover. Review media already uses bounded responsive variants, lazy loading and on-demand viewers. Full metrics are in `artifacts/native-review-launch/performance.json`; screenshots document the live page, account form and disabled Judge.me requests.

Rollback requires restoring the previous Shopify theme and coordinating email ownership before re-enabling Judge.me requests, to prevent duplicate requests. OS review data and Dropbox media must be preserved.

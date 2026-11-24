# Draft reviews: live parity, editor form and image delivery

24 November 2026. Task `20261124-c419098d`.

The existing unpublished OS review theme `190889230643` was repaired. Live theme `190888968499` remains Judge.me. No publication command or live-theme upload was made. Review CSS is unchanged and byte-identical between both themes.

## Display parity

The draft retains the live carousel selection/order, Australian/US rules, rating summary, histogram, five-row Load more batches, date formatting, customer-photo thumbnails and enlarged viewer. Video remains hidden in this storefront view, matching live.

The merchant explicitly confirmed that all 209 imported reviews are verified buyers from their original platforms and requested that every imported review retain its Verified buyer badge. The OS retains that import attestation independently of native Shopify order verification; imported reviews do not become eligible for native-order rewards. Anonymous submissions remain pending and unverified.

Public presentation was reconciled against the current Judge.me storefront output. There are 27 display-name overrides for differences between CSV names and public display names. Original internal review names and media relationships were preserved. 201 unique public identity matches were recorded; eight repeated records had identical matching public authors, so their display names were reconciled without guessing identity aliases or merging records.

The live/draft browser comparison passed for the summary, all 17 carousel cards (visible text whitespace normalised), and the first five archive rows, including dates, badges and photo-button counts. Live currently has one customer-photo thumbnail among its first five rows; the draft follows that same rule rather than inventing photographs for text-only reviews. The archive photo button was tested: Alan Carson's review opens his correct 1280px Dropbox-backed photo.

## Blocked Write a review form

The screenshot was reproduced inside Shopify's editor. The form's Content Security Policy allowed the storefront but omitted its nested editor ancestors, `admin.shopify.com` and `online-store-web.shopifyapps.com`. Those exact trusted origins were added; unrelated ancestors remain blocked. Nested framing checks every ancestor, as documented by [MDN](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/frame-ancestors).

The repaired form was opened in the actual editor with its rating controls, photo/video input, name, title, review and display permission visible. A loading status and an external-form fallback link were added. Existing signed context, same-origin submission, upload bounds, moderation and Dropbox-first storage remain in place. No production test review, email, discount or automation publication was created.

## Media work

All 29 existing display-media objects (28 images and one video poster) were audited at 320px and 1280px. Original 1280px files totalled 2,279,556 bytes; 320px thumbnails totalled 291,436 bytes.

New 640px WebP carousel copies were generated, durably stored and hash-verified in the existing Dropbox Reviews folder. They total **853,098 bytes**, a **62.6% reduction** relative to the 1280px set; the largest is **81,052 bytes**. Existing originals, 320px archive thumbnails and 1280px enlarged-view copies were retained. New uploads also create the 640px variant.

The carousel now chooses 320px/640px files; the enlarged viewer requests 1280px only when opened. OS metadata reads use the existing bounded read pool. A hash-checked, bounded 8 MB/64-file transient WebP cache avoids repeated Dropbox downloads while visibility checks still run before bytes are served.

A direct temporary Dropbox-link delivery experiment scored 69, below the cached OS delivery score of 71, so it was removed. The selected path serves verified Dropbox WebP bytes through the bounded OS cache, retaining the published/approved visibility gate. Dropbox remains the durable media source.

Initial totals and the histogram are rendered from the OS snapshot with the photo previews, then refreshed by the native feed. This removes the initial header/layout jump. No widget CSS or visual layout was redesigned.

## Checks and remaining page weight

41 focused Python tests passed against synthetic/disposable fixtures. Four synthetic browser tests passed, including both country rules, date visibility, badges, image sizing, pagination failure/retry, form submissions and nested editor framing. Changed image bytes, hidden reviews and unapproved media fail closed. Shopify validation passed for all four changed draft files; external-image advisories are expected for the requested Dropbox-backed source.

Lighthouse 13.6 desktop runs are recorded in `artifacts/draft-review-parity/speed-results.json`. These are lab samples. The audits flagged background loading exceeding their time limit; draft runs also flag the expected Shopify preview redirect to the canonical URL. They are not a production Core Web Vitals guarantee. Source inspection confirmed that the draft audit loaded OS media and zero Judge.me review resources.

The live baseline scored 42, with 3.62s simulated LCP and 1,272ms blocking time. The initial optimised draft scored 70, then 71 with the byte-delivery cache; blocking time fell to 14ms and layout shift was approximately zero. The selected draft run had 5.22s simulated LCP versus 3.62s on live: LCP did not improve. Total page transfer remained approximately 5 MB. The better overall score primarily reflects less script blocking and reduced layout shift; this is not a claim that every loading metric improved.

Remaining measured page-wide weight includes a 696 KB decorative footer GIF and approximately 895 KB of Google tag scripts plus 225 KB of Meta scripts. Converting the animation to an efficient animated format and reviewing duplicate/early analytics loads would be useful separate work. Tracking configuration and global footer behaviour were preserved in this repair.

Studio's broader comparison still flags pre-existing trailing whitespace in `Montserrat-OFL.txt` brought in from main. That unrelated file was preserved; focused tests, changed-file syntax, topology validation and this task's own diff checks passed.

## Release record

Final executable release: `1a53ebefd84a282c91a54a51a9785ed8e8e7ca91`. Only four draft theme files were uploaded: the review script, review section, preview snippet and initial summary snippet. Final readback matches the prepared files. Six live-theme review/settings/template files remained byte-identical to their pre-change copies; no live-theme upload or publish command was issued.

All three existing Render services were confirmed Live at the final executable release. Primary deployment: `dep-dc2epuu7bikc73fkamf0`. A post-rollout public 640px WebP request returned HTTP 200. After exiting Shopify preview, normal browsing showed Judge.me scripts and the review archive, with no preview bar.

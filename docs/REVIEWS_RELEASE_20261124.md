# Reviews release — 24 November 2026

The owner explicitly authorized both reviews changes to be pushed live. This
release extends the existing OS reviews module and preserves Judge.me during
the transition. It creates no Render service or replacement storefront widget.

## Production import

The authenticated release helper imported 209 published Judge.me reviews in one
transaction: 68 product reviews and 141 store reviews. There were zero duplicates,
zero unmatched product reviews and zero failed media transfers. No hidden review
was included. All 29 attachments are approved, copied and linked to their review.

The restored video belongs to Cindy Ind's **“It was fantastic”** review, CSV row
204, native review `bddb3c38-6b1c-41f3-b210-11c8af0b31f9`. Judge.me's original
video publication state was not changed; its native attachment is approved as
requested. Historical imports created no rewards or customer messages.

## Dropbox and delivery

Folder: `/Sportscave Team Folder/03_ASSETS/Reviews`.

- 28 original photos and one original MP4, retained without loss.
- 58 WebP files: 320/1280 photos and video posters. The small previews total
  291,436 bytes; the largest is 21,874 bytes. Larger copies total 2,279,556 bytes.
- `judge-me-dropbox-manifest.json` pins all file IDs, revisions, hashes and review
  associations. `sports-cave-import.csv` is the exact imported CSV, with SHA-256
  `d577eabf85fbb62f38b85f1c0eec53fd1f93c37d943a3470f7188f49f5e2f5a6`.

Dropbox receives originals before display processing for new uploads. Display
copies remain in Dropbox, with no R2 fallback. The native API serves approved
WebP bytes and MP4/WebM byte ranges; it does not expose private IDs, paths,
credentials or temporary Dropbox links to the storefront. Videos load only when
opened, with controls, no autoplay and a bounded viewer.

Canonical public API: `https://sports-cave-image-factory.onrender.com/reviews/public`.
Display and collection use the existing paid OS and its verified Dropbox account.
New production request links use this origin; CRM signing, consent, suppression,
moderation and reward delivery gates still apply.

## Existing storefront layout

The live theme is **Sports Cave - Black Friday Countdown - 21 Nov**,
`190805672243`. Only `assets/sc-customer-reviews.js` and
`sections/sc-customer-reviews.liquid` belong to this theme change. The existing
carousel, archive and dialog layout are retained. Their displayed reviews and
media now come from the OS. Static Judge.me photo previews are removed; a
verified-buyer badge requires native verified-purchase evidence.

`shopify/reviews/native-review-methods.js` and
`scripts/patch_existing_reviews_widget.py` record the source and reproducible
patch. The authenticated Shopify CLI supports an explicit two-file push to the
existing live theme. The connector also had unrelated saved files awaiting
publication, so its whole-theme publish was deliberately not used.

The app extension was separately released as `reviews-576139a4`, Shopify version
`1263332589569`. Its optional blocks support the same native media API.

## Remaining before retiring Judge.me

1. Confirm the photo/video reward percentages. Defaults are 10% and 15%; live
   reward delivery remains disabled. Historical reviews never earn rewards.
2. Use approved test accounts to accept the complete order → request → upload →
   moderation → discount → email journey before activating native requests.
3. Move the remaining customer account submission and Add video entry points
   from Judge.me to native collection. During transition, account photo uploads
   go to Dropbox first and Judge.me can ingest a temporary copy. The existing
   store-review write form is also retained while Judge.me is live.
4. Reconcile new Judge.me reviews, replies and media received after this export.
   Compare counts and one complete collection cycle before disabling Judge.me.
5. Connect Facebook, Google, Etsy, eBay and Trustpilot when ready. Their setup
   buttons are present; provider authentication and synchronization are not active.

Keep the private export, original media and manifests for rollback. Dropbox copies
can be removed on a separate explicit request; no Judge.me originals were deleted.

## Validation

Synthetic PostgreSQL/API, account delivery and shared Dropbox transport tests
passed. Both widget suites passed, including a test against the current theme's
code with synthetic review data. Shopify accepted the app configuration and
generated assets; Theme Check accepted the existing section patch. The complete
SHA-reviewed deployment manifest, topology and Studio static checks passed.

Live acceptance verified all 209 reviews, all 29 WebP previews (HTTP 200), three
larger WebP samples, video byte ranges (HTTP 206, 1,024 requested bytes), and
video HEAD length (6,252,438). Cindy's video played to completion without a media
error in the actual storefront. At a 390px viewport the player measured about
343 × 193px and its dialog stayed within the screen. All displayed gallery
images used the paid OS media origin; unloaded offscreen images remained lazy.

The two live theme files were downloaded again and matched the prepared files
byte-for-byte. No whole-theme publish was used. The connector's saved review
connection was also aligned with the paid OS origin without publishing the
unrelated saved theme changes.

The OS table refresh now uses a Streamlit fragment timer only while reads are
pending, avoiding a lost browser-side one-shot refresh. No full OS development
preview or live customer email test was used.

After the final rollout, a fresh OS page populated itself with 209 reviews,
4.8 average rating, 25 visible first-page rows and no Streamlit exceptions.
The canonical health endpoint and public reviews API both returned HTTP 200.

Private acceptance evidence:
`.studio/runtime/20261123-5890db74/evidence/reviews-live-acceptance.json`.

## Released application revision

All three existing workloads reached `live` on
`eac365ce9194dc61d3cdc3d834ae7e6982dbbc1d`:

| Service | Deploy |
| --- | --- |
| sports-cave-os | `dep-dc2bpsff3r2c73de6lng` |
| sports-cave-os-webhooks | `dep-dc2bpsff3r2c73de6nmg` |
| sports-cave-seo-worker (CRM supervisor) | `dep-dc2bpsff3r2c73de6o00` |

The final focused suite passed 77 Python unittest cases, 17 account delivery
pytest cases and both isolated widget browser tests. The shared Marketplace
transport regression suite additionally passed 47 cases (some overlap with the
focused suite). No changes to infrastructure identity, plans or secret values
were needed. Later changes revert to the repository's local-only default and
require fresh release authorization.

This documentation-only closeout uses `[skip render]`; application code remains
the exact accepted revision above.

# Sports Cave reviews migration and launch report

24 November 2026, Australia/Sydney. This is the original migration design and
pre-release checklist. The owner subsequently authorized release; the production
import is complete. See [the release report](REVIEWS_RELEASE_20261124.md) for
current deployment, media verification and remaining cutover work. Judge.me remains live.

## Export and media archive

| Item | Verified result |
| --- | --- |
| Published reviews exported | 209, all `curated=ok` |
| Product reviews in the export | 68 |
| Store reviews in the export | 141 |
| Unique normalized review identities | 209 |
| Reviews containing photos | 27 |
| Original photo files downloaded | 28; every saved file matches its recorded SHA-256 |
| Additional video attachment downloaded | 1, 6,252,438 bytes |
| Hidden reviews included | 0 |
| Invalid exported rows | 0 |

The video belongs to Cindy Ind's published review, “It was fantastic” (CSV row
204). The owner has now explicitly requested that it be shown in the native
widget. Its release manifest approves that attachment. Judge.me is unchanged;
the production OS association and display await the authorized release/import.
The dashboard's Includes videos filter returned zero published video reviews.
The CSV alone cannot establish that every unpublished video attachment has been
enumerated; the archive does not claim that broader completeness.

Private files are outside Git and have not been used in development previews:

`C:\Dev\SportsCaveWorktrees\.studio\runtime\20261123-5890db74\judgeme-export\`

- `published-reviews-original.csv`: untouched published-only export, including replies.
- `sports-cave-import.csv`: all 209 rows, with explicit publication/type columns
  and the separately downloaded video's source URL attached to its matching row.
- `archive/manifest.json`: review identities, file associations and photo hashes.
- `archive/media/`: original downloaded photos and video, plus earlier normalized
  image copies retained during verification. Use the manifest for the 28 original photos.
- `archive/video-associations.json`: video association, hash and source visibility.

Original export SHA-256:
`cc99850aaf3aae5cf158a27f41c147b6bf1aafa474ae5c4c2542e0c84d2e4b5c`.

Judge.me's [export format](https://judge.me/help/en/articles/8236266-exporting-reviews)
includes image links and replies but excludes videos and verified status. Its
[review-list API](https://judge.me/help/en/articles/8409180-using-judge-me-api)
also omits video URLs and replies. The CSV and separate media archive are
therefore the migration source, rather than an API-only sync.

## What the OS changes provide

### Dropbox media source

The actual folder `/Sportscave Team Folder/03_ASSETS/Reviews` now contains all
87 media files: 28 original photos, one original video and 58 WebP copies
(320/1280 images and video posters). All upload receipts were checked for
Dropbox file ID, revision and size, and a complete folder listing found no
missing media. Folder ID: `id:u1tYiAa2O-AAAAAAAADIAQ`.

`dropbox-upload/judge-me-dropbox-manifest.json` links each original and display
copy to its exact CSV row/source URL, pins Dropbox revisions, and approves the
previously live photos plus the newly requested video. It includes no customer
email. The manifest is also saved in the Dropbox Reviews folder.

The 29 small WebP previews total 291,436 bytes (largest 21,874 bytes). Their
larger display copies total 2,279,556 bytes. Originals are retained without loss.
Videos remain playable MP4/WebM; WebP provides the video poster, not playback.
Native media URLs stream revision-pinned Dropbox bytes with ETags, short public
cache lifetimes and byte ranges. Private Dropbox IDs, paths and credentials
are not sent to the widget. There is no R2 fallback for review media.
These are measured file sizes, not a production load-time guarantee.

Dropbox copies can be removed on a separate explicit request if this change
needs to be reverted. Judge.me originals have not been deleted or altered.

The implementation extends the existing reviews module. It models Judge.me's
documented fields and visible workflow; it does not claim access to Judge.me's
proprietary database design.

| Area | Behavior |
| --- | --- |
| Overview | Existing searchable review table, ratings, publication states, product matching and replies; store reviews are identified separately. |
| Import reviews | CSV template, column mapping, validation, duplicate detection, published-only filtering, excluded-row counts, media counts and import history. Judge.me exports are detected from their columns. |
| Media | Separate records link each photo/video to its review. Dropbox Assets/Reviews holds originals first, then 320/1280 WebP images or video posters. A resumable worker exposes failed transfers and staff retry. |
| Moderation | Review publication and media approval are separate. Copied files stay unpublished until approved. Existing source replies and local moderation remain authoritative. |
| Collect and reward | Existing email automation draft handoff, order-bound collection form, photo/video uploads, editable reward percentages and reward status queue. |
| Connections | Labeled icon buttons for Facebook, Google Reviews, Etsy, eBay and Trustpilot with honest “Not connected” setup panels. No accounts have been connected. |
| Existing display | The existing widget now shows lazy WebP thumbnails and a bounded image/video dialog, including on 320px screens. Video loads only when opened. The API serves approved Dropbox copies without exposing private IDs or paths. |

The storage is deliberately small: existing `sc_reviews`, import jobs, tokens,
settings and audit history, plus `sc_review_media` and `sc_review_rewards`.
An identity-alias table reconciles CSV handles with API review IDs when a dated
review's product, content and email hash agree; subsequent source edits follow
the learned alias. Undated or email-less records require manual reconciliation
when the providers expose different identifiers.
Media records retain their original URL, owned object key, checksum, size,
copy state, consent and approval. Application review records keep an email hash;
the raw customer email remains only in the private original export. Public API
responses exclude customer/order identifiers and private source metadata.

## Collection and rewards

1. Create a review-request draft in the existing email automation editor.
2. Its link is bound to a verified customer, order and purchased product.
3. The customer submits review text and up to five files, including one video.
4. Staff moderate the review and approve the media independently.
5. An eligible native submission receives one reward, independent of star rating.

Images accept JPEG, PNG or WebP, up to 10 MB and 25 megapixels. Original bytes
are retained in Dropbox; public display uses WebP copies. Video remains MP4 or
WebM with WebP posters, byte-range playback and no autoplay. Video accepts MP4
or WebM signatures, up to 50 MB. Total
multipart upload size is bounded at 65 MB. Video playback/codec compatibility
still needs a release acceptance test on the supported customer devices.

Draft defaults are **10% for photos and 15% for videos**, editable in the OS.
Confirm these amounts before activation. Imported historical reviews never earn
rewards. For new verified reviews, the worker creates a customer-specific,
single-use Shopify percentage code, expiring 30 days after issue and unable to
combine with other discounts. It rechecks the discount before sending through
the existing Resend adapter. Shopify's
[discountCodeBasicCreate](https://shopify.dev/docs/api/admin-graphql/2026-04/mutations/discountCodeBasicCreate)
requires discount write permission; no permissions were changed during this task.

Live delivery defaults off. Enabling it requires the OS reward setting,
`REVIEW_REWARDS_DELIVERY_ENABLED=true`, and the existing configured CRM send gates.
Fresh customer identity, order ownership, marketing consent, local/provider
suppression and a native unsubscribe URL are checked. Non-subscribed customers
are held rather than emailed. This behavior needs owner review before launch.
Unknown mutation/send outcomes are held for reconciliation and never blindly
replayed. A sent reward stores its provider receipt. No real codes or emails
were created during development.

## Required before turning Judge.me off

1. Review and explicitly authorize the commit/deployment. Apply the new reviewed
   migration through the existing release process and update the current OS and
   existing CRM worker together. No Render service or branding change is needed.
2. Use the authenticated `reviews_dropbox_migration.import_archive` release
   helper with `sports-cave-import.csv` and `judge-me-dropbox-manifest.json`.
   It checks the exact CSV hash and every Dropbox revision before atomically
   importing reviews and linking approved media. Expect 209 unique reviews and
   29 media references. Compare products, store reviews, dates, ratings and replies;
   reconcile any ambiguous identity before proceeding. A second run must not duplicate reviews.
3. Confirm all 28 photos and Cindy Ind's approved video render through the native
   API. Check the configured OS Dropbox account can read/write Assets/Reviews.
   Missing Dropbox credentials must be resolved through the existing secret setup;
   the connector's account session is not copied into application configuration.
4. Confirm reward values and existing Shopify/Resend configuration; test the
   complete request, upload, moderation, discount and delivery journey using
   approved test accounts in the release environment. No uncontained production
   app preview was started under Developer Studio Phase 1.
5. Point existing customer entry points at the native flow. In particular,
   Collector Vault account reviews still submit to Judge.me and its Add video
   link still opens Judge.me. Those paths need a reviewed cutover before removal.
   Confirm the existing widget renders approved media returned by the native API;
   the updated assets belong to the existing extension and need its normal release.
6. Keep Judge.me running while comparing results. Export/sync the delta collected
   during that period, including any new media and replies.
7. Disable Judge.me request sending only once native requests are verified.
   Monitor one complete collection/reward cycle before uninstalling Judge.me.
   Retain the CSV, media files and manifests as the rollback archive.

Facebook, Google, Etsy, eBay and Trustpilot can be connected later, using supported
provider access and the correct business accounts. Their setup panels do not
imply that OAuth or review synchronization is already implemented.

## Local validation and task state

All 55 focused synthetic PostgreSQL/API tests passed, plus 17 account review
delivery tests and the isolated widget browser test at 320, 390 and 1440px.
They cover import idempotency and visibility,
store-review aggregates, media ownership/retries, authenticated photo uploads,
reward approval, single-use customer discounts, suppression and unknown send
outcomes. Shopify validated the new discount mutation against the configured
2026-04 schema. Shopify's validator also accepted both updated widget assets.

The real export was checked as a private migration artifact, not loaded into the
synthetic database. No production schema/data/configuration was changed. The
worktree and uncommitted changes are retained for review; commits and deployment
still require explicit authorization.

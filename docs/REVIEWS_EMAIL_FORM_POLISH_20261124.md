# Post Checkout email and native form polish

24 November 2026, Australia/Sydney. Task `20261124-c419098d`.

All five Post Checkout email bodies were inspected and shortened: thank-you/collector access (39 words), three product-specific review requests (64/62/62), and collection follow-up (30). Existing shared Sports Cave logo, gold styling, footer, certificate/account link and smart product catalogue were preserved. The collection email has a usable Explore editions button even when no sample product is available. These counts exclude shared branding/legal footer. Full rendered emails are approximately 9–10 KB.

Saved draft revision **116** of automation `26b47e22-b962-4c0b-b964-392a6399caf4`. Existing ACTIVE publication **version 7** and its published definition were preserved, with explicit before/after equality checks. No email was sent or published. All review-request buttons use the OS origin and opaque order-bound `/reviews/request/` link marker; runtime resolves each purchased product. The rendered documents contain no Judge.me destinations. Certificate links continue to the existing customer account and collection links to the store; those are not review-provider links.

Online/POS delays and eligibility rules are unchanged: fulfilment +14/+19/+24 days online, +7/+12/+17 POS, maximum three purchased products, no reminders. Photo/video reward amounts remain 30%, rating-neutral, and reward delivery stays off.

## Form

Both public storefront and order-bound email links now render the same collection form. Five stars are selected initially and can be changed. Name, review title and review text precede the photo/video upload. The checkbox is replaced by an automatic yes field and the visible notice, “By submitting, you agree to publish your review and attached media.” Server-side consent validation, moderation and verified-order reward guards remain. The website form’s new-tab fallback and the paragraph listing upload counts/limits were removed. Image and video previews appear immediately, filenames remain visible, upload percentage is shown and selected media remains visible after success. Inputs stay intact if a submission fails.

The [AMP email form specification](https://go.amp.dev/documentation/components/email/amp-form) excludes file inputs; standard email clients do not reliably support review forms and file uploads inside the email body. The branded button opens the OS form, which collects text, photos and video together without account sign-in for the buyer’s opaque link. No unsupported embedded email upload was represented as working.

## Upload handling

Supported bounds were raised to **25 MB per photo, 150 MB per video, 250 MB combined**, still up to five files including one video. These are the supported application limits, not Dropbox’s theoretical maximum. Two concurrent multipart submissions bound peak server memory. Supported image/video formats and image pixel bounds remain validated. An unlimited browser upload would not be reliable on the shared service.

The request stores the original bytes in Dropbox, verifies the durable receipt and writes a QUEUED media record before acknowledging success. It no longer performs WebP/poster generation on that request. The existing CRM worker verifies and downloads the original from Dropbox, checks its byte hash, generates 320/640/1280 WebP variants/posters and marks the record COPIED. Original revisions are not overwritten. Failed processing is retried with the existing bounded retry budget and is visible to staff; media cannot be approved/displayed until complete.

A file cannot be fetched from a customer’s device merely by notifying the OS: its bytes must first transfer. The new flow removes display-processing latency, retains honest progress and never reports success before a durable Dropbox receipt. Actual network/Dropbox transfer time remains. A real, labelled photo/video test returned HTTP 200 in **8.07 seconds** for the small test files; this is not a large-file throughput guarantee. The worker completed both image variants and video posters; all original/variant receipts verified. The test review was archived and remains unavailable publicly.

## Verification and release

77 focused Python tests passed, including deferred-original persistence, worker processing, unchanged review timing and native email links. Five browser tests passed, covering AU/US pagination, error/retry, public and buyer multipart form submissions, automatic consent/default stars and Shopify editor framing. The final collection CTA change passed its focused email test. All five rendered emails fit a 390px viewport with no horizontal overflow or broken images. Review/thank-you/collection previews were visually inspected.

Backend release `4622b4cbb2f2edc7df3ff29528c3f3cb07d1f767` is Live on the same three existing Render services. No migrations, new services or topology changes were required. Only `assets/sc-customer-reviews.js` was uploaded to unpublished theme `190889230643` in this pass; readback matched. The live Judge.me theme `190888968499` was not uploaded or published, and a fresh readback of six live review/settings/template files remained byte-identical to the pre-change baseline.

Draft publication, native request activation and reward delivery remain separate merchant-controlled steps. Existing My Collection account review integration was not switched. The prior page-wide speed caveats still apply; this change does not claim unlimited or instant network uploads.

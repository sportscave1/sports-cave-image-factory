# Native review collection and Post Checkout drafts — 24 November 2026

Task `20261123-3dc09a82`; owner `codex-reviews-flows-20261124-a39`.
User authorized deployment of OS changes, while explicitly retaining Judge.me,
keeping review emails in draft, and testing in a duplicate theme.

## Judge.me audit: actual Sports Cave settings

Read directly from the installed app without saving any Judge.me settings.

| Setting | Observed configuration |
|---|---|
| Domestic/international first request | 14 days after fulfilment |
| POS first request | 7 days after fulfilment |
| Reminders | None |
| Multi-product orders | Maximum 3 items; most expensive first; separate emails 5 days apart |
| Customer request limit | Every order; variant requests enabled |
| Missing/deleted product | Store review fallback enabled |
| Request email | Custom active template; 600px, pale background, greeting, short request, product/variant, star links, team sign-off, unsubscribe |
| Email subject | Please review your latest purchase from the shop |
| Media reminder | Off |
| Confirmation/reply/Q&A emails | On |
| Coupon | Enabled; generated unique THANKYOU suffix; 25% text, 30% photo/video; one per order |
| Coupon validity/combinations | No expiry; no combinations; reviewer-only eligibility |
| Website collection | Anyone can write; popup; confirm email after submission to verify |
| Email collection | External form |
| Form | Rating, review title with autofill, text, photos, videos; quick stars-only off |
| Moderation | Auto-publish at least 5 stars; personal-information masking and profanity masking; spam filter unchecked |

## Delivered behavior

Post Checkout `26b47e22-b962-4c0b-b964-392a6399caf4` draft revision **114**
replaces the old feedback and photo messages with three conditional native review
slots. Existing thank-you and later collection upsell are preserved. Online
deadlines are fulfilment +14/+19/+24 days; POS +7/+12/+17. Only purchased product
slots that exist can run. No reminders were added. Products are ranked by original
line value, with repeated variants combined into one product slot.

The Sports Cave email uses the existing logo, gold divider, white layout, team
copy, branded footer, and one clear review button. Runtime resolves the actual
order/product, opaque buyer link and product title. The same form accepts a review
and up to five media files, including one video. Dropbox originals and WebP
variants/posters remain the media source. No customer token is generated in an
editor sample.

Draft save preserved the existing active publication **version 7**, status,
activation timestamp, published definitions and executable steps. Before/after
live-definition fingerprint: `7e0fe7c26cfb326d8198245a801a502e`.
No publish job, enrollment, customer email, coupon mutation or reward delivery was
requested during setup/testing.

Collection settings now contain **30% photo / 30% video**, matching Judge.me's
media amounts, with reward tracking **off** during testing. Delivery also retains
its release gate. Reward eligibility requires a published native verified-buyer
review plus approved consented media, independent of star rating. An order lock
prevents multiple product reviews generating multiple rewards for one order.
Codes remain customer-specific, single-use, no stacking, and expire in 30 days.
Text-only 25% rewards and never-expiring coupons were not copied; the requested
native rewards are for photo/video submissions.

The current live theme at duplication was **190888968499**,
“Sports Cave - 48 Hour Countdown - 24 Nov”. Its unpublished duplicate is
**190889230643**, “Sports Cave - OS Reviews Test - 24 Nov”.

- [Preview reviews page](https://www.sportscaveshop.com/pages/reviews?preview_theme_id=190889230643)
- [Edit duplicate](https://admin.shopify.com/store/sportscave-nb/themes/190889230643/editor)

Only the duplicate received changes. Judge.me app blocks/embeds were removed from
that copy; legacy title-count dependencies now use OS summary updates. Existing
review cards, archive, histogram, galleries, CSS and layout were retained. The
existing reviews-page write button opens a native form in its existing modal.
Anonymous website submissions are explicitly unverified and pending moderation;
they cannot earn verified-order rewards. Email requests are order-verified.
The live theme and Judge.me collection/settings were untouched by this task.

## Validation and rollout

Rollout verification pending at source commit; append final release evidence below.

Synthetic-only validation covers order timing, POS timing, missing-product skips,
product pagination/ranking, buyer token rendering, duplicate submissions,
unverified anonymous collection, Dropbox-first storage, moderation, rating-neutral
rewards and one reward per order. No live customer data was used in local fixtures.
Shopify GraphQL and changed Liquid passed validation; existing section-context
warnings in the product title snippet are informational. Mobile email HTML is
10,627 bytes at 390px with no horizontal overflow.

Three wider automation-suite failures reproduce on the unmodified main source:
stale checkout capability fixtures, a legacy HTML expectation, and a stale
size-meter source assertion. They are outside this review change; no production
guard was relaxed to make those tests pass.

## Remaining cutover checks and useful additions

1. Complete an approved test-buyer journey: request → image and video upload →
   moderation → one customer-specific Shopify code → reward email → redemption.
   No real email or code was sent by this setup. Keep request drafts and reward
   delivery off until that controlled test passes.
2. Before publishing native requests, disable Judge.me requests together with the
   cutover to prevent duplicate requests; migrate or deliberately leave its already
   queued requests. Keep the app running until reconciliation is complete.
3. For website reviews, add email confirmation/order matching if verified badges
   or rewards should be available outside opaque buyer email links. Current public
   submissions remain unverified; no guessed verification.
4. Add a store-review fallback for deleted/unindexed products. Current native
   requests fail closed when the purchased product cannot be verified/indexed.
5. Optional: reply/confirmation notifications, PII/profanity masking, title
   autofill, spam triage, an upload progress indicator and a later media-only
   attachment link. Judge.me's media reminder is currently off, so no extra
   reminder automation is needed for parity.
6. Optional: per-variant requests, multilingual copy, Q&A, review SEO/structured
   data and platform synchronization. Existing Facebook, Google, Etsy, eBay and
   Trustpilot setup buttons are retained; they do not imply connected accounts.
7. Prefer consistent rating-neutral moderation. Native submissions are held for
   review for every rating; Judge.me's observed five-star auto-publication rule was
   not copied.

Do not publish the duplicate or disable Judge.me until the controlled cutover
checks above are complete. Recheck theme changes made after duplication before
any eventual publication.

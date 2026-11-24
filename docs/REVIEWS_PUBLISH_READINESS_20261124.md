# Draft review collection readiness — 24 November 2026

Task `20261124-c419098d`. User authorised controlled submission, Dropbox and reward checks, with no theme publication, live Judge.me changes or email activation.

## Outcome

The draft is ready for the theme publication decision. Storefront collection, moderation and Dropbox delivery passed actual service checks. The only code defect found was an OS moderation search that could remain on Loading reviews after a fragment filter change; overview filters now rerun the page so its asynchronous completion poll is registered. Release `fb6a9830c79a208feff4a60a6c8f8bb9988db054` is live on the existing services. The deployed UI search was retested successfully.

Request emails and reward delivery remain deliberately inactive. Theme publication does not activate those separate gates. No production review email or reward email was sent; no checkout order or redemption was created. Actual reward-email receipt and checkout redemption remain unexercised under this no-send test. This is not a claim that the full customer email-to-redemption journey has run live.

## Actual service checks

- The draft reviews-page modal submitted a labelled four-star text review and displayed its received/awaiting-review confirmation.
- A real multipart HTTP submission to the same public endpoint included a generated, labelled JPEG and a playable one-second MP4. It created one pending store review, both media records COPIED and initially unapproved. No real customer imagery was used. The browser upload automation could not capture its file chooser, so the real attachment transfer was tested over HTTP; synthetic browser tests cover the multipart form behaviour.
- Both Dropbox originals and all six 320/640/1280 WebP image/poster copies passed revision, file-ID, size and folder receipt checks. Dropbox remained the durable source.
- A separate two-star product submission mapped to `gid://shopify/Product/8141604290867` (Lionel Messi). Reposting the same signed form returned success without creating another review. No star-rating threshold was used to accept submissions.
- Pending review media returned HTTP 404. Approving both test media and publishing only that labelled test review exposed its correct image and video in the native public API. The image served WebP with HTTP 200; a video Range request returned HTTP 206 and the correct 1024-byte Content-Range. The image entered the featured carousel; the existing storefront rule that hides videos remained intact.
- Archive moderation removed the test review from the feed, restored the public count to 209 and blocked image/video URLs again with HTTP 404, including previously cached image bytes.
- All three labelled test reviews now have ARCHIVED status; none generated a reward. Their tiny test files and archived records are retained as auditable evidence, not published customer content.
- Missing consent and invalid photo bytes returned HTTP 400; a foreign Origin returned HTTP 403.
- Draft product-page review jump, archive Load more (5 to 10) and Alan Carson photo viewer worked. The actual mobile editor form fit its 293px inner viewport without horizontal overflow. Existing outer-page width/styling was preserved. AU/US mobile widget behaviour was also checked in synthetic 390px browser runs.

## Rewards and email isolation

Photo and video rewards remain configured at 30% each, matching the earlier Judge.me audit. Eligibility tracking is off and `REVIEW_REWARDS_DELIVERY_ENABLED` remains false on both primary and actual CRM worker. Imported reviews and anonymous website reviews do not earn verified-order rewards. Eligible buyer-link submissions require order/customer/product verification, publication and approved consented media, regardless of star rating.

An actual Shopify API discount test created a customer with a QA name/tag and no email, phone, address or order. The production discount-input function created a 30% code with its entire validity window in the past. Shopify accepted the mutation with no user errors and confirmed EXPIRED, usageLimit 1, appliesOncePerCustomer true and restriction to that QA customer. It cannot be redeemed. QA customer `31461331894579` and expired discount node `1618054447411` are retained for inspection. No real customer record was modified.

The synthetic SQL/provider suite verified actual eligibility transitions, order ownership, one reward per order, single issuance/delivery, consent/suppression checks, timeout holds and no blind retries. Synthetic mailer output is not a real email send.

Post Checkout remains on its existing ACTIVE publication version 7; draft revision 114 contains three review-request slots, while the existing published definition contains zero. Online timing remains fulfilment +14/+19/+24 days and POS +7/+12/+17, conditional on purchased products, with no reminders. The actual sending worker has a valid signing-key configuration and the correct OS public review origin. No keys were exposed or changed.

## Theme and validation

Shopify lists live theme `190888968499` as live and OS duplicate `190889230643` as unpublished. A fresh pull confirmed six live review/settings/template files byte-identical to the pre-change baseline. No theme upload or publication was performed in this readiness pass. On exit from preview, normal live browsing displayed Judge.me scripts and the reviews archive with no preview bar.

74 focused Python tests passed before the UI fix, then all 58 relevant review/journey/migration tests passed after it. Four synthetic browser tests passed without skips, covering AU/US cards, mobile pagination retry, form upload/error behaviour and editor framing. The reward mutation passed Shopify GraphQL validation. Render topology validation passed. The broader Studio comparison still has the previously documented unrelated Montserrat licence whitespace warning.

The previous Lighthouse results remain applicable: 42 live versus 71 selected draft, incomplete lab audits, approximately 5 MB overall page weight and draft LCP slower than live. This pass did not repeat or claim a new full-page speed score. The image resizing and cache fixes remain; global analytics and footer changes require separate scope.

## Publication decision

No further functional defect was found in these checks. Publish the draft only when the merchant chooses to cut over. Activate native request emails and reward delivery separately, coordinating Judge.me request scheduling to avoid duplicate emails. Keep the current Judge.me theme as the rollback copy. The existing My Collection account integration remains on Judge.me, as previously requested; this draft theme changes the storefront backend only and does not switch the account ecosystem.

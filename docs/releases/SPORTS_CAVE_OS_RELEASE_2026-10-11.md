# Sports Cave OS release — 11 October 2026

## Scope and safeguards

The user explicitly authorized repair, native PostgreSQL staging, GitHub main publication and coordinated deployment to the four existing Render services. No topology, production security settings, paid infrastructure or migration code is changed. Welcome, Post Purchase and Win Back must remain Draft. Customer emails, product pricing/inventory/customer records and historical edition allocations must not be changed by release verification.

The reviewed independent release contains Campaigns cancellation repair, Shopify buyer-segment integration, Product Upload saved-pricing repair and automatic sport tagging V2, Universal Personalised Templates V1/V2, their worker/webhook dependencies, and Customer Account order-history pagination. The exact file hashes are in `deploy/validated-2026-10-11.json`. The routine deployment helper and its sensitive-file protections remain unchanged; this explicitly approved coordinated release uses an isolated checkout and exact allowlist.

## Repairs

- Campaign review retains ownership of its pending audience job before its thread starts. A controls rerender can cancel only an unowned job. Stale cancelled jobs produce a review-again error. Current consent, audience checks and send review remain mandatory.
- Saved pricing repairs accept both proper Unicode dashes and legacy mojibake. Supplemental framed rows use a delimiter alternation instead of an incorrect character class. The approved Australian six-variant price-only exception remains exact; compare-at blanks, other sizes and regional prices are preserved.
- The isolated export caught missing Collector GraphQL runtime assets and buyer-segment fixture evidence. All are explicitly included; a working dirty checkout is not treated as packaging evidence.

## Verification

The isolated independent candidate completed 554 test executions across 25 modules: 520 passed, no failures/errors, and 34 existing retired unsafe-allocator tests were intentionally skipped. Campaigns' 90, product workflows' 113 and worker/template/vault integration's 175 targeted tests all pass without skips. Shopify's extension suites passed 31 tests; config validation, build and uploaded version validation passed. The topology validator passes.

Fresh disposable native PostgreSQL databases and stripped credentials were used. External network access was prohibited in the test runner; provider operations used synthetic transports. Production reads separately verified application-owned Shopify scopes and catalogue/customer/order/segment access; Google Search Console/Analytics, Dropbox, Meta Ads/Page, Resend and Judge.me credential checks passed without printing secrets or changing customer data. The public Judge.me key was checked against its documented widget endpoint, not its private product endpoint.

Every migration in the existing approved deployment manifest is present in production. Private Email tables have RLS and no grants to PUBLIC, anon or authenticated. Existing outbox state, including one unknown result, is preserved and must never be blindly replayed.

## Inbox V2A–V2D: complete local candidate, provider acceptance blocked

The coherent latest Inbox candidate remains local; no older partial Inbox implementation is substituted. `deploy/full.json` is regenerated from 189 explicit candidate files covering all 112 original inventory paths and additional dependencies. It is separate from the independently releasable manifest.

Inbox verification passed 534 integrated tests without skips, plus the final six native account/authentication/proxy/session tests and three independent-process PostgreSQL concurrency tests. These selections overlap and are not a single unique test total. Sixteen component/render JavaScript scripts passed. Actual full-OS browser testing used two synthetic local PostgreSQL accounts: actor-owned draft persistence, second-account isolation, logout, permission removal and session-version revocation passed. No real mailbox was used for destructive/failure/revocation tests.

The approved existing mailbox is `hello@sportscaveshop.com`. From the existing paid Render Oregon primary, TCP connections to `ventraip.email` / `110.232.143.200` on 993, 465 and 587 time out before TLS/login. The same endpoint connects from the user's computer, including verified TLS on 993/465. No mailbox, DNS, credentials or security settings were changed and no test email was sent. VentraIP diagnostic ticket **VIP-R2695883** is open. Provider resolution and successful bounded receive/SMTP/Sent acceptance involving only the own mailbox are required before publishing Inbox V2A–V2D.

Real Safari/Firefox/mobile hardware acceptance has not been performed. Synthetic fault tests and Chromium staging evidence do not claim live provider or cross-device acceptance.

## Deployment verification

The release operator must verify the exact main SHA on sports-cave-os, sports-cave-os-webhooks, sports-cave-seo-worker and sports-cave-seo-daily-sync; HTTP health, actual feature imports/UI, worker freshness, product webhook subscriptions and Draft statuses. Shopify version `consolidated-20261011` is separately uploaded and must be explicitly released and verified active. A GitHub/Render push alone does not publish the Shopify extension.

Rollback is a normal exact-revision Render deployment to the prior `2af257694032fb6a9aaaca4ebced7c364d4440d7`, without schema downgrade, data deletion, queue replay or changes to the original dirty checkout. Shopify's prior active version is `Email_Automations_v1`.

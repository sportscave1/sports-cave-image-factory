# Incoming Shop app reviews

24 November 2026, Australia/Sydney. Continuation of task `20261124-c419098d`.

The owner requested automatic publication of Shop-collected reviews into OS after retiring Judge.me. The store has the Shop channel and Shopify Flow installed, on Shopify Basic. The OS app has read_metaobjects/read_products/read_orders access, but not the restricted write_product_reviews scope. Its Dev Dashboard does not expose a Standard product reviews access request. Direct standard-review syndication therefore is not currently enabled.

Shopify separately provides the installed Shop channel's **Shop Review Published** Flow trigger. The Basic-compatible implementation uses that trigger and Shopify's built-in **Send Admin API request / metaobjectUpsert** action to write a merchant-private `sports_cave_shop_review_inbox` entry. This is an incoming event handoff, not Shopify's restricted standard product-review definition or an outbound syndication integration. The definition has no storefront access and contains no customer emails, phone numbers or addresses. OS reads it with its existing installed permissions; no app, paid plan, token or public ingestion endpoint is added.

Workflow: **Sports Cave — Shop reviews to OS**, ID `01a20bdf-a86e-7eb1-a52d-2856141c767a`. The generated draft version was `01M85XZA3B033DWR5MES5FH3NJ`. Inbox definition: `gid://shopify/MetaobjectDefinition/39026098483`.

The worker checks about once a minute, with ten entries per page, a durable pagination cursor, fixed scan boundary, overlap and a fenced lease. Failures leave the cursor/watermark intact for retry and show connection attention in OS. Every written review is validated against the actual order's purchased line item, product and variant before publication. Deleted products and rating-only reviews are skipped, matching the previous provider's written-review policy. An exact unique migrated match gains a Shop identity without creating a duplicate or undoing local moderation. Repeated identical inbox entries avoid product/order network reads. Later source updates preserve local moderation. Shop imports cannot issue native photo/video rewards.

New entries use `shop_app` provenance, retain the original submission date/display name/rating/body, carry the first product image and feed the normal transactional storefront totals. Both title and bottom widget counts continue to read that same OS summary. The normal small Shopify WebP thumbnail transformation applies. Shop-specific reviews show Shopify's unchanged official Verified by Shop badge; all other review presentation remains intact. The badge addition is a few hundred bytes after minification.

## Verification

- Ten new synthetic model/SQL tests cover validation, purchase mismatch, idempotency, totals, legacy reconciliation, local moderation, skipped entries, reward exclusion, retry and pagination. Uses only a disposable localhost PGlite database.
- Focused existing review/Dropbox/import/upload regressions were run with the new tests. Current widget country/pagination/media/Shop-badge tests and title/bottom count test were run against the production widget source. An older widget harness still targets `/reviews/public`; it is not the current `/reviews/widget` harness and is not counted as passing for this source.
- Shopify's bundled Admin 2026-04 validator accepted the final inbox/product/order operations without warnings. The product query uses MediaImage, avoiding deprecated Product images fields. Official Shopify app build and theme-extension Theme Check succeeded.
- Actual OS production token read the private inbox successfully. The published baseline is 209; no fake Shop review was published. The small source constraint migration was applied to the existing reviews database. RLS remains enabled and anon has no SELECT privilege on review/settings tables.
- Shopify Flow's safe simulation used the previously authorised business-account purchase. Its rendered configuration includes correct product/order/line-item/variant identities, review date, string rating and escaped quotes. The simulation deliberately stops before the mutating API action; this is not an actual Shop publication event or a successful live action run.
- The current live widget's normalised minified source matches the prior committed source before patching; preserve the downloaded original in the task's evidence folder. Only its Shop badge support needs a live theme asset update.

## Limits and operations

This trigger supplies new publication events only. It does not provide a historical review export, photo/video attachment URLs, Shop deletion/reply events or a two-way syndication guarantee. Existing OS migrated reviews remain intact. Historical Shop backfill or automatic later deletion/reply mirroring requires separate supported access, such as Shopify's approved review syndication program. A genuinely new customer Shop review must still exercise the live trigger/action end to end; do not claim that a simulated event proves live Shop delivery.

Disable the named workflow and set `sc_review_settings.shop_app_connection.enabled` false to stop this incoming connection. Leave reviews and identities intact. An invalid event/purchase reference holds the current scan for investigation rather than silently losing reviews; correct the private inbox entry and retry. No customer email automation, discount policy, form or collection upload transport is changed.

Primary references: [Shop review management and Flow trigger](https://help.shopify.com/en/manual/online-sales-channels/shop/product-reviews/manage), [Flow testing](https://help.shopify.com/en/manual/shopify-flow/manage/test-workflow), [Flow plan capabilities](https://help.shopify.com/en/manual/shopify-flow), [restricted review syndication program](https://shopify.dev/docs/apps/build/metaobjects/standard-review-metaobject).

Release and final observed status are recorded below after rollout.
